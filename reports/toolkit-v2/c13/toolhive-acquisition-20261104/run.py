"""First delegated artifact-data pipeline, charged to the existing canonical store."""
import argparse,asyncio,hashlib,json,shutil,sys,time
from datetime import UTC,datetime
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
SOURCE=Path(json.loads((HERE.parent/'workflow-telemetry-20261104/source-snapshot.json').read_bytes())['coordinator_source_snapshot']);sys.path.insert(0,str(SOURCE/'src'))
from aeep.assessment.models import AssessmentAuthorization,AssessmentLimits,RecipeMaterializationRequest,content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.execution import persist_execution_events,ExecutionEvidence
from aeep.models import ActionRequest,ExecutionReceipt,ExecutorSpec,ResourceVector,SideEffect,StrictModel,utc_now
from aeep.store import ReceiptStore

def load(p):return json.loads(Path(p).read_bytes())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n')
class Scope(StrictModel):
    role:str
    source_revision:str
    plan_sha256:str

def validate(review):
    assert datetime.now(UTC)<datetime.fromisoformat(review['expires_at'].replace('Z','+00:00'))
    assert shutil.disk_usage(ROOT).free>=50*1024**3
    for p,h in review['assets'].items():assert sha(p)==h,p
    assert verification_source_digest(SOURCE)==review['source']

def execute(review,identity):
    validate(review)
    assert shutil.disk_usage(ROOT).free>=54*1024**3
    with (HERE/'execution-started.json').open('x') as f:json.dump({'review_sha256':identity,'authority':'standing first-attempt pipeline delegation'},f)
    prepared=load(HERE/'prepared.json');request=RecipeMaterializationRequest.model_validate(prepared['request']);grant=AssessmentAuthorization.model_validate(prepared['grant'])
    work=Path(review['work']);work.mkdir(mode=0o700,parents=True,exist_ok=True)
    for name in ('home','tmp'):(work/name).mkdir(mode=0o700,exist_ok=True)
    result={'passed':False,'models':0,'compiler_executed':False,'upstream_programs_executed':False,'accounting_uncertain':False,'cleanup_uncertain':False,'comparisons':'PAUSED'}
    with ReceiptStore(review['ledger']) as store:
        repo=AssessmentRepository(store)
        assert not store._connection.execute('SELECT 1 FROM assessment_grants WHERE id=?',(grant.authorization_id,)).fetchone()
        for ref,value in prepared['scopes'].items():assert repo.put('toolkit_toolhive_artifact_scope',ref,Scope.model_validate(value))==ref;repo.review(ref)
        repo.grant(grant)
        outer=request.plan_id+':exclusive-driver';child=request.plan_id+':artifact-data-worker'
        repo.reserve(request,outer,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=60),stage='toolhive_artifact_driver_overhead')
        repo.reserve(request,child,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=1810),stage='toolhive_pinned_source_dependency_acquisition')
        clock=time.perf_counter();nested=0.
        async def command():
            spec=ExecutorSpec(id='toolhive.pinned-artifact-data',capability='toolkit.upstream-engineering@1',kind='command',side_effect='write',
                description='Exact public archive acquisition and static integrity/license inventory only; no Go or MCP program',
                config={'argv':['/usr/bin/sandbox-exec','-f',str(HERE/'download.sb'),'/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13','-I','-B',str(HERE/'acquire.py'),'--review-sha256',identity],
                    'argv_literal':True,'inherit_env':False,'env':{'PATH':'/usr/bin:/bin','HOME':str(work/'home'),'TMPDIR':str(work/'tmp'),'LC_ALL':'C'},
                    'cwd':str(work),'timeout_seconds':1800,'max_output_bytes':1048576,'output':{'type':'text'}})
            ex=CommandExecutor();began=time.perf_counter();started=utc_now();raw=None;error=None;ref=None
            try:
                def authorize():validate(review);repo.authorize(request);return identity
                with persist_execution_events(lambda key,event:repo.put('execution_event',key+':'+str(event.sequence),event)):
                    handle=await ex.start(ExecutionContext(request=ActionRequest(action_id=child,capability=spec.capability),spec=spec,estimate=spec.estimate,attempt=1,attempt_id=child,approved_side_effect=SideEffect.WRITE,invocation_check=authorize))
                    while not handle.task.done():
                        await asyncio.wait({handle.task},timeout=1)
                        if shutil.disk_usage(ROOT).free<50*1024**3:await ex.cancel(handle);raise RuntimeError('HostReserveCrossed')
                    raw=await handle.task
                evidence=ExecutionEvidence.model_validate(raw.metadata['execution_evidence']);assert evidence.complete
                ref=repo.put('execution_evidence',evidence.digest(),evidence)
            except BaseException as failure:error=type(failure).__name__
            finally:
                await ex.close();elapsed=time.perf_counter()-began
                receipt=ExecutionReceipt(decision_id=child,action_id=child,capability=spec.capability,executor_id=spec.id,executor_kind=spec.kind,
                    status=raw.status if raw else 'failed',started_at=started,ended_at=utc_now(),estimated=spec.estimate,actual_resources=ResourceVector(latency_ms=elapsed*1000),
                    execution_success=raw is not None and raw.exit_code==0 and error is None,error_type=error or (raw.error_type if raw else None),metadata={'review_sha256':identity,
                        'execution_evidence_ref':ref,'observed_resource_dimensions':['latency_ms'],'legacy_vector_defaults_are_not_observations':True,
                        'network_wire_bytes_cpu_memory_cash':'UNKNOWN','no_go_or_upstream_program_execution':True})
                repo.store.save_receipt(receipt);repo.finish_operation(child,elapsed_seconds=elapsed,resources=receipt.actual_resources)
                write(HERE/'worker-receipt.json',receipt.model_dump(mode='json'))
                write(HERE/'worker-process-status.json',{'exit_code':raw.exit_code if raw else None,'error_type':error,'stdout':(raw.stdout or '')[-8192:] if raw else None,'stderr':(raw.stderr or '')[-8192:] if raw else None})
            return raw,elapsed,error
        try:
            raw,nested,error=asyncio.run(command());assert raw is not None and raw.exit_code==0 and error is None
            data=load(HERE/'acquisition-result.json');assert data['passed'];result.update(passed=True,assets=len(data['assets']),source_blobs=data['source']['git_blobs_verified'],
                download_body_bytes=data['download_body_bytes'],uncompressed_hashed_bytes=data['uncompressed_hashed_bytes'],licenses_cleared=False)
        except BaseException as failure:result['error_type']=type(failure).__name__
        finally:
            elapsed=max(0.,time.perf_counter()-clock-nested)
            try:
                repo.finish_operation(outer,elapsed_seconds=elapsed,resources=ResourceVector(latency_ms=elapsed*1000))
                result['accounting_uncertain']=store._connection.execute("SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",(grant.authorization_id,)).fetchone() is not None
                result['grant_counters']=list(store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(grant.authorization_id,)).fetchone())
                write(HERE/'operation-ledger.json',repo.operation_ledger(request.plan_id).model_dump(mode='json'))
            except BaseException as failure:result.update(passed=False,accounting_uncertain=True,accounting_error_type=type(failure).__name__)
            result['free_bytes_after']=shutil.disk_usage(ROOT).free;write(HERE/'summary.json',result)
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute-delegated');args=parser.parse_args()
    review=load(HERE/'operation-review.json');identity=sha(HERE/'operation-review.json');validate(review)
    if args.execute_delegated is None:print(json.dumps({'execution':False,'review_sha256':identity}));raise SystemExit(0)
    assert args.execute_delegated==identity
    actual=load(HERE/'delegated-authority.json');assert actual['review_sha256']==identity and actual['first_attempt'] is True
    result=execute(review,identity);print(json.dumps(result))
    if not result['passed']:raise SystemExit(1)
