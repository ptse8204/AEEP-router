"""Explicitly approved post-build audit repeat; never rerun the compiler."""
import argparse,asyncio,hashlib,importlib.util,json,shutil,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];OLD=HERE.parent/'toolhive-native-build-20261104';RECOVERY=HERE.parent/'toolhive-artifact-preservation-20261104'
def module(name,file):
    spec=importlib.util.spec_from_file_location(name,file);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
base=module('original_toolhive_build',OLD/'run.py');preserve=module('original_toolhive_artifacts',RECOVERY/'recover.py')
from aeep.assessment.models import AssessmentAuthorization,AssessmentBudgetAmendment,AssessmentLimits,RecipeMaterializationRequest,content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.models import ExecutionReceipt,ResourceVector,utc_now
from aeep.store import ReceiptStore
load=base.load;sha=base.sha;write=base.write

def artifact(expected,original,current,kind,version):
    assert sha(original)==expected
    if kind=='info':
        old,new=load(original),load(current)
        assert isinstance(old,dict) and isinstance(new,dict) and old.get('Version')==new.get('Version')==version
        assert old==new,'Version metadata values changed, not just JSON ordering'
    else:assert sha(current)==expected

def audit(review):
    base.verify_sdk(review)
    acquisition=load(review['acquisition_result']);root=Path(review['artifact_work'])
    for relative,expected in acquisition['source']['source_file_sha256'].items():
        p=root/'source'/relative
        value=hashlib.sha256(p.readlink().as_posix().encode()).hexdigest() if p.is_symlink() else sha(p)
        assert value==expected
    plan=load(review['acquisition_plan']);expected={(x['module'],x['version'],x['kind']):x['sha256'] for x in acquisition['assets']}
    for row in plan['assets']:
        artifact(expected[(row['module'],row['version'],row['kind'])],Path(review['immutable_downloads'])/row['cache_path'],root/'mod-cache/cache/download'/row['cache_path'],row['kind'],row['version'])
    assert sha(review['binary'])==review['binary_sha256']

def execute(review,identity):
    base.validate(review);assert shutil.disk_usage(ROOT).free>=50*1024**3+768*1024**2
    with (HERE/'execution-started.json').open('x') as f:json.dump({'review_sha256':identity,'specific_repeat_approved':True},f)
    result={'passed':False,'models':0,'compiler_repeated':False,'downloads_repeated':False,'comparisons':'PAUSED','MCP_lifecycle':'NOT_EXECUTED','accounting_uncertain':False,'cleanup_uncertain':False}
    recovery_review=load(RECOVERY/'operation-review.json');assert sha(RECOVERY/'operation-review.json')==review['recovery_review_sha256']
    recovery=preserve.execute(recovery_review,review['recovery_review_sha256'])
    if not recovery['passed']:
        result['error_type']='ArtifactPreservationFailed';write(HERE/'summary.json',result);return result
    prepared=load(OLD/'prepared.json');request=RecipeMaterializationRequest.model_validate(prepared['request']);grant=AssessmentAuthorization.model_validate(prepared['grant'])
    base.HERE=HERE
    with ReceiptStore(review['ledger']) as store:
        repo=AssessmentRepository(store)
        assert list(store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(grant.authorization_id,)).fetchone())==review['counters_before']
        repo.approve_budget_amendment(AssessmentBudgetAmendment.model_validate(load(HERE/'budget-amendment.json')))
        outer=request.plan_id+':post-build-continuation-overhead';repo.reserve(request,outer,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=60),stage='toolhive_post_build_continuation_overhead')
        began=time.perf_counter();nested=0.
        try:
            operation=request.plan_id+':corrected-post-build-audit';repo.reserve(request,operation,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=60),stage='toolhive_corrected_post_build_audit')
            clock=time.perf_counter();started=utc_now();failure=None
            try:audit(review)
            except BaseException as error:failure=type(error).__name__
            elapsed=time.perf_counter()-clock;nested+=elapsed
            receipt=ExecutionReceipt(decision_id=operation,action_id=operation,capability='toolkit.upstream-engineering@1',executor_id='toolhive.post-build-integrity',executor_kind='python',
                status='failed' if failure else 'success',started_at=started,ended_at=utc_now(),estimated={},actual_resources=ResourceVector(latency_ms=elapsed*1000),execution_success=failure is None,error_type=failure,
                metadata={'review_sha256':identity,'observed_resource_dimensions':['latency_ms'],'legacy_vector_defaults_are_not_observations':True,'original_compilation_review':review['original_build_review_sha256'],'compiler_not_repeated':True})
            repo.store.save_receipt(receipt);repo.finish_operation(operation,elapsed_seconds=elapsed,resources=receipt.actual_resources);write(HERE/'audit-receipt.json',receipt.model_dump(mode='json'));assert failure is None
            built=base.Built(binary_sha256=review['binary_sha256'],source_revision=review['source_revision'],build_review_sha256=identity,binary_path=review['binary'])
            write(HERE/'built-identity.json',built.model_dump(mode='json'));repo.review(repo.put('toolkit_built_toolhive_identity',content_digest(built),built))
            write(HERE/'binary-origin.json',{'original_compilation_review_sha256':review['original_build_review_sha256'],'continuation_artifact_review_sha256':identity,'binary_sha256':review['binary_sha256'],'recompiled':False})
            for row in review['commands']:
                assert row['name'] in ('build-info','toolhive-version','toolhive-help')
                assert not store._connection.execute('SELECT 1 FROM assessment_operations WHERE id=?',(request.plan_id+':'+row['name'],)).fetchone()
                raw,elapsed,error=asyncio.run(base.command(repo,request,review,identity,row));nested+=elapsed
                assert raw is not None and raw.exit_code==0 and error is None
                if row['name']=='build-info':assert 'github.com/stacklok/toolhive/cmd/thv' in raw.stdout and 'CGO_ENABLED=0' in raw.stdout
                elif row['name']=='toolhive-version':
                    value=json.loads(raw.stdout);assert value['commit']==review['source_revision'] and value['go_version']=='go1.27.1' and value['platform']=='darwin/arm64';result['version']=value
                else:assert 'ToolHive' in raw.stdout and 'run' in raw.stdout
            result.update(passed=True,binary_sha256=review['binary_sha256'],actual_toolhive_info_executed=True,artifact_preservation_files=recovery['preserved_files'])
        except BaseException as error:result['error_type']=type(error).__name__
        finally:
            elapsed=max(0.,time.perf_counter()-began-nested)
            try:
                repo.finish_operation(outer,elapsed_seconds=elapsed,resources=ResourceVector(latency_ms=elapsed*1000))
                result['accounting_uncertain']=store._connection.execute("SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",(grant.authorization_id,)).fetchone() is not None
                result['grant_counters']=list(store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(grant.authorization_id,)).fetchone());assert result['grant_counters'][0]<=9
                write(HERE/'operation-ledger.json',repo.operation_ledger(request.plan_id).model_dump(mode='json'))
            except BaseException as error:result.update(passed=False,accounting_uncertain=True,accounting_error_type=type(error).__name__)
            result['free_bytes_after']=shutil.disk_usage(ROOT).free;write(HERE/'summary.json',result)
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute-approved');args=p.parse_args();review=load(HERE/'operation-review.json');identity=sha(HERE/'operation-review.json')
    if args.execute_approved is None:print(json.dumps({'review_sha256':identity,'execution':False}));raise SystemExit(0)
    approval=load(HERE/'operator-approval.json');assert args.execute_approved==identity==approval['review_sha256'] and approval['approved'] is True
    result=execute(review,identity);print(json.dumps(result))
    if not result['passed']:raise SystemExit(1)
