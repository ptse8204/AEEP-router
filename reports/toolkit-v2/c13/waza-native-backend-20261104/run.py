"""First native backend information checks; no Waza evaluation or sign-in."""
import argparse,asyncio,hashlib,importlib.util,json,re,shutil,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
spec=importlib.util.spec_from_file_location('canonical_native_command',HERE.parent/'toolhive-native-build-20261104/run.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base);base.HERE=HERE
from aeep.assessment.models import AssessmentAuthorization,AssessmentLimits,RecipeMaterializationRequest
from aeep.assessment.repository import AssessmentRepository
from aeep.models import ResourceVector
from aeep.store import ReceiptStore
load=base.load;sha=base.sha;write=base.write
def validate_artifacts(review):
    base.validate(review)
    for path,expected in review['binary_sha256'].items():assert sha(path)==expected
def execute(review,identity):
    validate_artifacts(review)
    with (HERE/'execution-started.json').open('x') as f:json.dump({'review_sha256':identity,'first_native_backend_attempt':True},f)
    work=Path(review['work']);work.mkdir(mode=0o700)
    for name in ('home','tmp','copilot-home','xdg-config','xdg-cache','xdg-state','xdg-data'):(work/name).mkdir(mode=0o700)
    canary=Path(review['canary']);canary.write_text('AEEP synthetic unrelated-file denial control\n');canary.chmod(0o600)
    prepared=load(HERE/'prepared.json');request=RecipeMaterializationRequest.model_validate(prepared['request']);grant=AssessmentAuthorization.model_validate(prepared['grant'])
    result={'passed':False,'models':0,'comparisons':'PAUSED','provider_authentication':'NOT_ATTEMPTED','real_Waza_evaluation':'OPEN','Waza_program_executed':False,'accounting_uncertain':False,'cleanup_uncertain':False,'phases':[]}
    with ReceiptStore(review['ledger']) as store:
        repo=AssessmentRepository(store);assert not store._connection.execute('SELECT 1 FROM assessment_grants WHERE id=?',(grant.authorization_id,)).fetchone()
        for ref,value in prepared['scopes'].items():assert repo.put('toolkit_native_backend_scope',ref,base.Scope.model_validate(value))==ref;repo.review(ref)
        repo.grant(grant);outer=request.plan_id+':exclusive-driver';repo.reserve(request,outer,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=60),stage='waza_backend_driver_overhead')
        began=time.perf_counter();nested=0.
        try:
            for row in review['commands']:
                result['active_phase']=row['name'];validate_artifacts(review)
                raw,elapsed,error=asyncio.run(base.command(repo,request,review,identity,row));nested+=elapsed
                assert raw is not None and raw.exit_code==0 and error is None,(row['name'],error)
                if row['name']=='boundary':assert json.loads(raw.stdout)['passed']
                elif row['name']=='waza-build-provenance':
                    assert 'github.com/microsoft/waza' in raw.stdout
                    revision=re.search(r'vcs.revision=(\w+)',raw.stdout)
                    result['Waza_embedded_VCS_revision']=revision.group(1) if revision else None
                    result['Waza_source_attribution']='MATCHED' if revision and revision.group(1)==review['source_revision'] else 'UNKNOWN_OR_CONFLICTING'
                elif row['name']=='copilot-version':assert re.search(r'\b1\.0\.85\b',raw.stdout);result['Copilot_version']=raw.stdout.strip()
                else:assert '--help' in raw.stdout and '--version' in raw.stdout;result['Copilot_help']='PASS'
                result['phases'].append(row['name']);result.pop('active_phase',None)
            assert sha(canary)==review['canary_sha256']
            result.update(passed=True,existing_binary_hashes_unchanged=True,canary_preserved=True,real_backend_ready=False)
        except BaseException as error:result['error_type']=type(error).__name__
        finally:
            elapsed=max(0.,time.perf_counter()-began-nested)
            try:
                repo.finish_operation(outer,elapsed_seconds=elapsed,resources=ResourceVector(latency_ms=elapsed*1000))
                result['accounting_uncertain']=store._connection.execute("SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",(grant.authorization_id,)).fetchone() is not None
                result['grant_counters']=list(store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(grant.authorization_id,)).fetchone())
                write(HERE/'operation-ledger.json',repo.operation_ledger(request.plan_id).model_dump(mode='json'))
            except BaseException as error:result.update(passed=False,accounting_uncertain=True,accounting_error_type=type(error).__name__)
            result['free_bytes_after']=shutil.disk_usage(ROOT).free;write(HERE/'summary.json',result)
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute-delegated');args=p.parse_args();review=load(HERE/'operation-review.json');identity=sha(HERE/'operation-review.json')
    if args.execute_delegated is None:print(json.dumps({'execution':False,'review_sha256':identity}));raise SystemExit(0)
    authority=load(HERE/'delegated-authority.json');assert args.execute_delegated==identity==authority['review_sha256'] and authority['first_attempt'] is True
    result=execute(review,identity);print(json.dumps(result))
    if not result['passed']:raise SystemExit(1)
