"""One offline source-derived ToolHive build/info pipeline; no MCP service."""
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
from aeep.execution import ExecutionEvidence,persist_execution_events
from aeep.models import ActionRequest,ExecutionReceipt,ExecutorSpec,ResourceVector,SideEffect,StrictModel,utc_now
from aeep.store import ReceiptStore

def load(p):return json.loads(Path(p).read_bytes())
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n')
class Scope(StrictModel):
    role:str
    source_revision:str
    plan_sha256:str
class Built(StrictModel):
    binary_sha256:str
    source_revision:str
    build_review_sha256:str
    binary_path:str

def validate(review):
    assert datetime.now(UTC)<datetime.fromisoformat(review['expires_at'].replace('Z','+00:00'))
    assert shutil.disk_usage(ROOT).free>=50*1024**3
    for p,h in review['assets'].items():assert sha(p)==h,p
    assert verification_source_digest(SOURCE)==review['source']

def verify_sdk(review):
    inventory=load(review['sdk_inventory']);root=Path(inventory['sdk_root'])
    actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() or p.is_symlink()}
    assert actual=={row['path'] for row in inventory['entries']}
    for row in inventory['entries']:
        p=root/row['path']
        if 'symlink' in row:assert p.is_symlink() and p.readlink().as_posix()==row['symlink']
        else:assert p.is_file() and not p.is_symlink() and sha(p)==row['sha256']

def verify_inputs(review):
    acquisition=load(review['acquisition_result']);root=Path(review['artifact_work'])
    for relative,h in acquisition['source']['source_file_sha256'].items():
        p=root/'source'/relative
        if p.is_symlink():body=p.readlink().as_posix().encode();assert hashlib.sha256(body).hexdigest()==h
        else:assert sha(p)==h
    plan=load(review['acquisition_plan']);lookup={(r['module'],r['version'],r['kind']):r for r in acquisition['assets']}
    for row in plan['assets']:
        p=root/'mod-cache/cache/download'/row['cache_path'];assert sha(p)==lookup[(row['module'],row['version'],row['kind'])]['sha256']

async def command(repo,request,review,identity,row):
    validate(review);name=row['name'];operation=request.plan_id+':'+name;started=utc_now();clock=time.perf_counter();raw=None;error=None;ref=None
    repo.reserve(request,operation,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=row['timeout_seconds']+10),stage='toolhive_native_'+name)
    argv=row['argv'];spec=ExecutorSpec(id='toolhive.native.'+name,capability='toolkit.upstream-engineering@1',kind='command',side_effect='write',
        description='Reviewed offline compiler or informational ToolHive invocation only',config={'argv':['/usr/bin/sandbox-exec','-f',str(HERE/'native.sb'),*argv],
        'argv_literal':True,'inherit_env':False,'env':review['environment'],'cwd':review['source_directory'],'timeout_seconds':row['timeout_seconds'],'max_output_bytes':1048576,'output':{'type':'text'}})
    executor=CommandExecutor()
    try:
        def authorize():
            validate(review);repo.authorize(request)
            if row.get('compiled_binary'):
                built=load(HERE/'built-identity.json');assert built['binary_sha256']==sha(review['binary']) and built['build_review_sha256']==identity
                repo.authorize(request.model_copy(update={'definition_digests':[*request.definition_digests,content_digest(Built.model_validate(built))]}))
            return identity
        with persist_execution_events(lambda key,event:repo.put('execution_event',key+':'+str(event.sequence),event)):
            handle=await executor.start(ExecutionContext(request=ActionRequest(action_id=operation,capability=spec.capability),spec=spec,estimate=spec.estimate,attempt=1,attempt_id=operation,approved_side_effect=SideEffect.WRITE,invocation_check=authorize))
            while not handle.task.done():
                await asyncio.wait({handle.task},timeout=1)
                if shutil.disk_usage(ROOT).free<50*1024**3:await executor.cancel(handle);raise RuntimeError('HostReserveCrossed')
            raw=await handle.task
        evidence=ExecutionEvidence.model_validate(raw.metadata['execution_evidence']);assert evidence.complete
        ref=repo.put('execution_evidence',evidence.digest(),evidence)
    except BaseException as failure:error=type(failure).__name__
    finally:
        await executor.close();elapsed=time.perf_counter()-clock
        receipt=ExecutionReceipt(decision_id=operation,action_id=operation,capability=spec.capability,executor_id=spec.id,executor_kind=spec.kind,
            status=raw.status if raw else 'failed',started_at=started,ended_at=utc_now(),estimated=spec.estimate,actual_resources=ResourceVector(latency_ms=elapsed*1000),
            execution_success=raw is not None and raw.exit_code==0 and error is None,error_type=error or (raw.error_type if raw else None),metadata={
                'review_sha256':identity,'execution_evidence_ref':ref,'observed_resource_dimensions':['latency_ms'],'legacy_vector_defaults_are_not_observations':True,
                'cpu_memory_cash_measurements':'UNKNOWN','no_model_or_MCP_service':True})
        repo.store.save_receipt(receipt);repo.finish_operation(operation,elapsed_seconds=elapsed,resources=receipt.actual_resources)
        write(HERE/('receipt-'+name+'.json'),receipt.model_dump(mode='json'))
        write(HERE/('process-'+name+'.json'),{'exit_code':raw.exit_code if raw else None,'error_type':error,'stdout':(raw.stdout or '')[:65536] if raw else None,'stderr':(raw.stderr or '')[:65536] if raw else None})
    return raw,elapsed,error

def execute(review,identity):
    validate(review);assert shutil.disk_usage(ROOT).free>=56*1024**3
    assert not Path(review['binary']).exists()
    with (HERE/'execution-started.json').open('x') as f:json.dump({'review_sha256':identity,'authority':'standing first-attempt delegation'},f)
    work=Path(review['work'])
    for name in ('bin','home','tmp','cache','gopath','xdg-config','xdg-data','xdg-cache','xdg-state'):(work/name).mkdir(mode=0o700,exist_ok=True)
    prepared=load(HERE/'prepared.json');request=RecipeMaterializationRequest.model_validate(prepared['request']);grant=AssessmentAuthorization.model_validate(prepared['grant'])
    result={'passed':False,'models':0,'compiler_executed':False,'toolhive_executed':False,'MCP_lifecycle':'NOT_EXECUTED','comparisons':'PAUSED','accounting_uncertain':False,'cleanup_uncertain':False,'phases':[]}
    with ReceiptStore(review['ledger']) as store:
        repo=AssessmentRepository(store);assert not store._connection.execute('SELECT 1 FROM assessment_grants WHERE id=?',(grant.authorization_id,)).fetchone()
        for ref,value in prepared['scopes'].items():assert repo.put('toolkit_toolhive_build_scope',ref,Scope.model_validate(value))==ref;repo.review(ref)
        repo.grant(grant);outer=request.plan_id+':exclusive-driver';repo.reserve(request,outer,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=60),stage='toolhive_native_driver_overhead')
        began=time.perf_counter();nested=0.
        try:
            verify_sdk(review);verify_inputs(review)
            result['source_dependency_sdk_fingerprints']='PASS'
            for row in review['commands']:
                result['failed_phase']=row['name']
                if row['name']=='compile':result['compiler_executed']=None
                if row['name']=='toolhive-version':result['toolhive_executed']=None
                raw,elapsed,error=asyncio.run(command(repo,request,review,identity,row));nested+=elapsed
                assert raw is not None and raw.exit_code==0 and error is None,(row['name'],error)
                if row['name']=='boundary':assert json.loads(raw.stdout)['passed']
                elif row['name']=='go-version':assert raw.stdout.strip()=='go version go1.27.1 darwin/arm64'
                elif row['name']=='compile':
                    assert Path(review['binary']).is_file();verify_inputs(review)
                    built=Built(binary_sha256=sha(review['binary']),source_revision=review['source_revision'],build_review_sha256=identity,binary_path=review['binary'])
                    write(HERE/'built-identity.json',built.model_dump(mode='json'));repo.review(repo.put('toolkit_built_toolhive_identity',content_digest(built),built));result.update(compiler_executed=True,binary_sha256=built.binary_sha256)
                elif row['name']=='build-info':assert 'github.com/stacklok/toolhive/cmd/thv' in raw.stdout and 'CGO_ENABLED=0' in raw.stdout
                elif row['name']=='toolhive-version':
                    value=json.loads(raw.stdout);assert value['commit']==review['source_revision'] and value['platform']=='darwin/arm64' and value['go_version']=='go1.27.1';result['toolhive_executed']=True;result['version']=value
                elif row['name']=='toolhive-help':assert 'ToolHive' in raw.stdout and 'run' in raw.stdout
                result['phases'].append(row['name'])
                result.pop('failed_phase',None)
            result['passed']=True
        except BaseException as failure:result['error_type']=type(failure).__name__
        finally:
            elapsed=max(0.,time.perf_counter()-began-nested)
            try:
                repo.finish_operation(outer,elapsed_seconds=elapsed,resources=ResourceVector(latency_ms=elapsed*1000))
                result['accounting_uncertain']=store._connection.execute("SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",(grant.authorization_id,)).fetchone() is not None
                result['grant_counters']=list(store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(grant.authorization_id,)).fetchone())
                write(HERE/'operation-ledger.json',repo.operation_ledger(request.plan_id).model_dump(mode='json'))
            except BaseException as failure:result.update(passed=False,accounting_uncertain=True,accounting_error_type=type(failure).__name__)
            result['free_bytes_after']=shutil.disk_usage(ROOT).free;write(HERE/'summary.json',result)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute-delegated');args=p.parse_args();review=load(HERE/'operation-review.json');identity=sha(HERE/'operation-review.json');validate(review)
    if args.execute_delegated is None:print(json.dumps({'review_sha256':identity,'execution':False}));raise SystemExit(0)
    authority=load(HERE/'delegated-authority.json');assert args.execute_delegated==identity==authority['review_sha256'] and authority['first_attempt'] is True
    result=execute(review,identity);print(json.dumps(result))
    if not result['passed']:raise SystemExit(1)
