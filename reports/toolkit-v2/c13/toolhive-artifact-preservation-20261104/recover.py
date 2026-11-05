"""Preserve exact downloaded bytes separately from Go's mutable module cache."""
import argparse,hashlib,json,shutil,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
SOURCE=Path(json.loads((HERE.parent/'workflow-telemetry-20261104/source-snapshot.json').read_bytes())['coordinator_source_snapshot']);sys.path.insert(0,str(SOURCE/'src'))
from aeep.assessment.models import AssessmentAuthorization,AssessmentLimits,RecipeMaterializationRequest,content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.models import ExecutionReceipt,ResourceVector,StrictModel,utc_now
from aeep.store import ReceiptStore
def load(p):return json.loads(Path(p).read_bytes())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n')
class Scope(StrictModel):
    role:str
    preservation_plan_sha256:str

def execute(review,identity):
    for p,h in review['assets'].items():assert sha(p)==h,p
    assert shutil.disk_usage(ROOT).free>=50*1024**3+768*1024**2
    with (HERE/'execution-started.json').open('x') as f:json.dump({'review_sha256':identity,'authority':'actual grouped post-build repeat approval'},f)
    prepared=load(HERE/'prepared.json');request=RecipeMaterializationRequest.model_validate(prepared['request']);grant=AssessmentAuthorization.model_validate(prepared['grant'])
    result={'passed':False,'models':0,'native_or_upstream_execution':False,'cache_files_overwritten':0,'downloaded':False,'comparisons':'PAUSED'}
    with ReceiptStore(review['ledger']) as store:
        repo=AssessmentRepository(store);assert not store._connection.execute('SELECT 1 FROM assessment_grants WHERE id=?',(grant.authorization_id,)).fetchone()
        for ref,value in prepared['scopes'].items():assert repo.put('toolkit_artifact_preservation_scope',ref,Scope.model_validate(value))==ref;repo.review(ref)
        repo.grant(grant);operation=request.plan_id+':preserve-originals';repo.reserve(request,operation,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=180),stage='toolhive_original_artifact_preservation')
        began=time.perf_counter();started=utc_now();error=None
        try:
            repo.authorize(request)
            plan=load(review['acquisition_plan']);acquisition=load(review['acquisition_result']);root=Path(review['artifact_work'])/'mod-cache/cache/download'
            orders={x['module']:x['format'] for x in load(review['encoding_diagnosis'])['results']}
            destination=Path(review['destination']);destination.mkdir(mode=0o700)
            lookup={(x['module'],x['version'],x['kind']):x for x in acquisition['assets']};recovered=[];rows=[];total=0
            for row in plan['assets']:
                assert shutil.disk_usage(ROOT).free>=50*1024**3
                file=root/row['cache_path'];expected=lookup[(row['module'],row['version'],row['kind'])]['sha256'];body=file.read_bytes()
                if hashlib.sha256(body).hexdigest()!=expected:
                    assert row['kind']=='info';data=json.loads(body);style=orders[row['module']];assert style is not None
                    ordered={k:({key:data[k][key] for key in style['origin_order']} if k=='Origin' else data[k]) for k in style['top_order']}
                    ending={"''":'',"'\\n'":'\n'}[style['ending']]
                    body=(json.dumps(ordered,indent=style['indent'],separators=tuple(style['separators']) if style['separators'] else None)+ending).encode()
                    assert hashlib.sha256(body).hexdigest()==expected
                    recovered.append(row['cache_path'])
                target=destination/row['cache_path'];assert target.resolve().is_relative_to(destination.resolve());target.parent.mkdir(parents=True,exist_ok=True)
                with target.open('xb') as f:f.write(body)
                target.chmod(0o444);total+=len(body);rows.append({'path':row['cache_path'],'sha256':expected,'bytes':len(body)})
            result.update(passed=True,preserved_files=len(rows),preserved_bytes=total,reconstructed_original_info_files=recovered,inventory=rows,
                exact_original_hashes_match=True,reason='Go reordered Origin Ref/Hash JSON keys; all21 original .info hashes are reproduced by value-preserving field ordering. Source ZIP/mod bytes never changed.')
        except BaseException as failure:error=type(failure).__name__;result['error_type']=error
        finally:
            elapsed=time.perf_counter()-began;receipt=ExecutionReceipt(decision_id=operation,action_id=operation,capability='toolkit.upstream-engineering@1',executor_id='toolhive.artifact-preservation',executor_kind='python',
                status='success' if result['passed'] else 'failed',started_at=started,ended_at=utc_now(),estimated={},actual_resources=ResourceVector(latency_ms=elapsed*1000),execution_success=result['passed'],error_type=error,
                metadata={'review_sha256':identity,'observed_resource_dimensions':['latency_ms'],'legacy_vector_defaults_are_not_observations':True,'no_download_or_program_replay':True})
            repo.store.save_receipt(receipt);repo.finish_operation(operation,elapsed_seconds=elapsed,resources=receipt.actual_resources)
            write(HERE/'receipt.json',receipt.model_dump(mode='json'));write(HERE/'operation-ledger.json',repo.operation_ledger(request.plan_id).model_dump(mode='json'))
            result['grant_counters']=list(store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(grant.authorization_id,)).fetchone())
            result['free_bytes_after']=shutil.disk_usage(ROOT).free;write(HERE/'summary.json',result)
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute-approved');args=p.parse_args();review=load(HERE/'operation-review.json');identity=sha(HERE/'operation-review.json')
    if args.execute_approved is None:print(json.dumps({'review_sha256':identity,'execution':False}));raise SystemExit(0)
    approval=load(HERE/'operator-approval.json');assert args.execute_approved==identity==approval['review_sha256'] and approval['approved'] is True
    result=execute(review,identity);print(json.dumps({k:v for k,v in result.items() if k not in ('inventory','reconstructed_original_info_files')}))
    if not result['passed']:raise SystemExit(1)
