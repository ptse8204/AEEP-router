"""Execute only after parent review approval; use the ordinary CLI and core ledger."""
from __future__ import annotations
import asyncio,json,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
FROZEN=Path(json.loads((HERE/'source-snapshot.json').read_text())['path'])
sys.path.insert(0,str(FROZEN/'src'))
from aeep.assessment.models import AssessmentBudgetAmendment,AssessmentLimits,AssessmentScopeAmendment,content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.containment import container_name
from aeep.assessment.identity import verify_dependencies
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.models import ActionRequest,ExecutionReceipt,ExecutorSpec,RawExecution,ResourceVector,SideEffect,utc_now
from aeep.executors.command import CommandExecutor
from aeep.execution import persist_execution_events
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
    spec.config['timeout_seconds']=20
    spec.config['max_stdin_bytes']=1_000_000
    executor=ScanContainerExecutor(definition.environment,runtime_digest=definition.executable_dependencies[str(definition.environment.container_runtime)])
    action=ActionRequest(capability=spec.capability,input=json.loads((HERE/'bootstrap-input.json').read_bytes()))
    context=ExecutionContext(request=action,spec=spec,estimate=spec.estimate,attempt=1,attempt_id=key,
        approved_side_effect=spec.side_effect,invocation_check=lambda:(repo.authorize(request),None)[1])
    argv,_=executor.command(context)
    image_index=argv.index(definition.environment.container_image)
    assert argv[argv.index('--entrypoint')+1]=='python3'
    argv=argv[:image_index+1]+['-B','-c',(HERE/'bootstrap-probe.py').read_text()]
    launch=ExecutorSpec(id='toolkit.scanner-bootstrap',capability=spec.capability,kind='command',
        description='Reviewed parent-Python bootstrap and boundary; no Cisco import',side_effect='read',
        config={'argv':argv,'argv_literal':True,'inherit_env':False,'stdin_json':True,
                'max_stdin_bytes':16384,'max_output_bytes':65536,'timeout_seconds':25,'output':{'type':'json'}})
    def authorize():
        repo.authorize(request);verify_dependencies(definition.executable_dependencies)
        assert verification_source_digest(FROZEN)==json.loads((HERE/'source-snapshot.json').read_text())['source']
    context=ExecutionContext(request=action,spec=launch,estimate=launch.estimate,attempt=1,attempt_id=key,
        approved_side_effect=SideEffect.READ,invocation_check=authorize)
    raw=None;began=utc_now();clock=time.monotonic();adapter=CommandExecutor()
    try:
        status,found=await executor.checked_docker('container','inspect',container_name(key))
        assert status!=0 and b'No such' in found,'preserve existing or uncertain container'
        with persist_execution_events(lambda journal,event:repo.put('execution_event',journal+':'+str(event.sequence),event)):
            raw=await(await adapter.start(context)).task
    except BaseException as error:
        raw=RawExecution(status='failed',error_type=type(error).__name__)
    finally:
        await adapter.close()
        await executor.cleanup(key)
        elapsed=time.monotonic()-clock
        repo.finish_operation(key,elapsed_seconds=elapsed,accounting=raw.accounting if raw else None,resources=ResourceVector(latency_ms=elapsed*1000))
        ledger=repo.operation_ledger(request.plan_id)
        (output/'boundary-ledger.json').write_text(ledger.model_dump_json(indent=2)+'\n')
        (output/'boundary-cleanup.json').write_text(json.dumps({'verified':executor.cleanup_verified})+'\n')
    assert raw is not None,'No terminal command result; stop dispatch'
    okay=raw.status.value=='success' and isinstance(raw.output,dict) and raw.output.get('passed') is True and executor.cleanup_verified
    receipt=ExecutionReceipt(decision_id=key,action_id=action.action_id,capability=spec.capability,executor_id=launch.id,
        executor_kind=launch.kind,status='success' if okay else 'failed',started_at=began,ended_at=utc_now(),estimated=launch.estimate,
        actual_resources=ResourceVector(latency_ms=elapsed*1000),accounting=raw.accounting,execution_success=okay,error_type=raw.error_type or (None if okay else 'BootstrapOrContainmentFailed'),
        metadata={**raw.metadata,'process_status':raw.status.value,'cleanup_verified':executor.cleanup_verified,'review_sha256':identity,'container_resource_usage':'unavailable'})
    repo.store.save_receipt(receipt)
    (output/'boundary-receipt.json').write_text(receipt.model_dump_json(indent=2)+'\n')
    (output/'boundary-result.json').write_text(json.dumps(raw.output,indent=2)+'\n')
    assert okay,'boundary/cleanup failed; stop scanner dispatch'


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
        try:
            for grant,expected in authority['baseline'].items():
                row=store._connection.execute('SELECT revoked,operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(grant,)).fetchone()
                assert dict(zip(('revoked','operations','model_turns','elapsed_seconds','cash_usd'),row,strict=True))==expected,'grant counters changed; no reset or retry'
                assert store._connection.execute("SELECT count(*) FROM assessment_operations WHERE grant_id=? AND state='reserved'",(grant,)).fetchone()[0]==0
            budget=AssessmentBudgetAmendment.model_validate(authority['budget_amendment'])
            for value in authority['scope_amendments']:
                amendment=AssessmentScopeAmendment.model_validate(value)
                repo.approve_bundle(amendment,authority['definitions'],budget_amendment=budget if amendment.authorization_id==budget.authorization_id else None)
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
                ledger=repo.operation_ledger(request.plan_id,source_plan_ids=[authority['previous_scanner_plan_id']])
                assert len(ledger.operations)==3 and all(row.elapsed_seconds is not None for row in ledger.operations)
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
            unsettled=store._connection.execute("SELECT count(*) FROM assessment_operations WHERE state='reserved' AND grant_id IN (?,?)",tuple(authority['baseline'])).fetchone()[0]
            result['accounting_uncertain']=unsettled>0
            cleanup=output/'boundary-cleanup.json'
            result['cleanup_uncertain']=cleanup.exists() and not json.loads(cleanup.read_bytes())['verified']
        finally:
            result['wall_seconds']=time.monotonic()-clock
            (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
