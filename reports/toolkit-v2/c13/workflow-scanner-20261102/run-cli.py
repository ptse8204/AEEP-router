"""Execute only after parent review approval; use the ordinary CLI and core ledger."""
from __future__ import annotations
import asyncio,json,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
FROZEN=ROOT/'.aeep/stack-frozen-source-0116d754bc7a'
sys.path.insert(0,str(FROZEN/'src'))
from aeep.assessment.models import AssessmentAuthorization,AssessmentLimits,content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.executors.base import ExecutionContext
from aeep.models import ActionRequest,ExecutionReceipt,utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import file_digest
from aeep_toolkit.workflow_security import ScannerRuntimeDefinition,ScanContainerExecutor,scan_spec,require_scan


def cli(args):
    process=subprocess.run([sys.executable,'-m','aeep_toolkit',*args],cwd=ROOT,
        env={'PATH':'/usr/bin:/bin','PYTHONPATH':str(FROZEN/'src'),'PYTHONNOUSERSITE':'1',
             'PYTHONDONTWRITEBYTECODE':'1','LC_ALL':'C'},
        stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=180)
    if process.returncode or len(process.stdout)>1_048_576:
        raise RuntimeError('Ordinary CLI failed; retain canonical attempts and inspect the component records')
    return json.loads(process.stdout)


async def boundary(repo,definition,output,identity):
    request=definition.request.model_copy(update={'definition_digests':[*definition.request.definition_digests,content_digest(definition)]})
    repo.authorize(request)
    key='workflow-scanner:'+identity+':launch-boundary'
    repo.reserve(request,key,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=45),stage='workflow_scanner_launch_boundary')
    spec=scan_spec(definition).model_copy(deep=True)
    spec.config['argv']=['/opt/aeep-scanner/bin/python','-I','-B','-c',(HERE/'boundary-program.py').read_text()]
    spec.config['timeout_seconds']=20
    spec.config['max_stdin_bytes']=1_000_000
    executor=ScanContainerExecutor(definition.environment,runtime_digest=definition.executable_dependencies[str(definition.environment.container_runtime)])
    action=ActionRequest(capability=spec.capability,input={})
    context=ExecutionContext(request=action,spec=spec,estimate=spec.estimate,attempt=1,attempt_id=key,
        approved_side_effect=spec.side_effect,invocation_check=lambda:(repo.authorize(request),None)[1])
    raw=None;began=utc_now();clock=time.monotonic()
    try:
        raw=await(await executor.start(context)).task
    finally:
        await executor.close()
        repo.finish_operation(key,elapsed_seconds=time.monotonic()-clock,accounting=raw.accounting if raw else None,resources=raw.resources if raw else None)
    receipt=ExecutionReceipt(decision_id=key,action_id=action.action_id,capability=spec.capability,executor_id=spec.id,
        executor_kind=spec.kind,status=raw.status,started_at=began,ended_at=utc_now(),estimated=spec.estimate,
        actual_resources=raw.resources,accounting=raw.accounting,execution_success=raw.status.value=='success',error_type=raw.error_type,
        metadata={**raw.metadata,'cleanup_verified':executor.cleanup_verified,'review_sha256':identity})
    repo.store.save_receipt(receipt)
    (output/'boundary-receipt.json').write_text(receipt.model_dump_json(indent=2)+'\n')
    (output/'boundary-result.json').write_text(json.dumps(raw.output,indent=2)+'\n')
    assert raw.status.value=='success' and raw.output.get('passed') and executor.cleanup_verified,'boundary/cleanup failed; stop scanner dispatch'


def run(review,identity):
    output=HERE/'cli-execution';output.mkdir(mode=0o700)
    with (HERE/'cli-started.json').open('x') as f:json.dump({'review_sha256':identity},f)
    authority=json.loads((HERE/'cli-authority.json').read_bytes())
    runtime=ScannerRuntimeDefinition.model_validate_json((HERE/'scanner-runtime.json').read_bytes())
    database=Path(json.loads((HERE/'cli-manifest.json').read_text())['database'])
    result={'passed':False,'models':0,'cash_usd':0,'benchmark_execution':False,'full_stack_complete':False}
    clock=time.monotonic()
    with ReceiptStore(database) as store:
        repo=AssessmentRepository(store)
        for ref in authority['review_refs']:repo.review(ref)
        for item in authority['grants']:repo.grant(AssessmentAuthorization.model_validate(item))
        try:
            asyncio.run(boundary(repo,runtime,output,identity))
            args=['workflow','scan','--workflow',str(HERE/'cli-workflow.json'),'--configuration','document-data']
            preview=cli(args)
            assert preview['review_sha256']==review['cli_review_sha256']
            actual=cli([*args,'--accounting',str(HERE/'cli-accounting.json'),'--operation-id','reviewed-static-scan',
                        '--reviewed-digest',preview['review_sha256']])
            (output/'scan.json').write_text(json.dumps(actual,indent=2)+'\n')
            record=require_scan(repo,actual['scan_ref'],HERE/'cli-workflow.json','document-data')
            # Both selections share the same reviewed candidate/image. Check applicability, not another scan.
            require_scan(repo,actual['scan_ref'],HERE/'cli-workflow.json','software-engineering')
            assert record.observations['analyzers_executed']>0
            assert record.candidate_sha256==review['candidate_sha256']
            for request in (runtime.request,):
                ledger=repo.operation_ledger(request.plan_id)
                assert len(ledger.operations)==2 and all(row.elapsed_seconds is not None for row in ledger.operations)
                (output/'scanner-ledger.json').write_text(ledger.model_dump_json(indent=2)+'\n')
            wrapped=json.loads((HERE/'cli-accounting.json').read_text())['request']['plan_id']
            ledger=repo.operation_ledger(wrapped)
            assert len(ledger.operations)==1 and all(row.elapsed_seconds is not None for row in ledger.operations)
            (output/'wrapper-ledger.json').write_text(ledger.model_dump_json(indent=2)+'\n')
            result.update(passed=True,scan_ref=actual['scan_ref'],component_receipt_ref=record.receipt_ref,
                          source_bound_journal=record.execution_evidence_ref,
                          source_bound_both_configuration_applicability=True,operations=3)
        except BaseException as error:
            result['error_type']=type(error).__name__
        finally:
            result['wall_seconds']=time.monotonic()-clock
            (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
