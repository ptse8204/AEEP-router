"""OPERATOR TERMINAL ONLY: login without capturing or inspecting credentials."""
import argparse,hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
from datetime import UTC,datetime
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[4]
SOURCE=Path(json.loads((HERE.parents[1]/'workflow-telemetry-20261104/source-snapshot.json').read_bytes())['coordinator_source_snapshot']);sys.path.insert(0,str(SOURCE/'src'))
from aeep.assessment.models import AssessmentAuthorization,RecipeMaterializationRequest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutionReceipt,ResourceVector,StrictModel,utc_now
from aeep.store import ReceiptStore
def load(p):return json.loads(Path(p).read_bytes())
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
class Scope(StrictModel):
    role:str
    login_plan_sha256:str
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--operator-login',action='store_true');args=parser.parse_args()
    if not args.operator_login or not all(os.isatty(i) for i in (0,1,2)):
        raise SystemExit('Run only in your own interactive Terminal. Agent-captured sign-in is prohibited.')
    review=load(HERE/'protected-login-review.json');identity=sha(HERE/'protected-login-review.json')
    assert datetime.now(UTC)<datetime.fromisoformat(review['expires_at'].replace('Z','+00:00'))
    assert verification_source_digest(SOURCE)==review['source']
    for p,h in review['assets'].items():assert sha(p)==h
    assert shutil.disk_usage(ROOT).free>=50*1024**3
    # This confirms only this operator action; it grants no model or payment authority.
    answer=input('Run the pinned Copilot login only, with no model calls or paid enrollment? Type LOGIN: ')
    if answer!='LOGIN':raise SystemExit('No setup attempted.')
    with (HERE/'protected-login-started.json').open('x') as f:json.dump({'review_sha256':identity,'operator_terminal':True},f)
    prepared=load(HERE/'protected-login-prepared.json');request=RecipeMaterializationRequest.model_validate(prepared['request']);grant=AssessmentAuthorization.model_validate(prepared['grant'])
    with ReceiptStore(review['ledger']) as store:
        repo=AssessmentRepository(store)
        assert not store._connection.execute('SELECT 1 FROM assessment_grants WHERE id=?',(grant.authorization_id,)).fetchone()
        for ref,value in prepared['scopes'].items():assert repo.put('toolkit_protected_operator_setup',ref,Scope.model_validate(value))==ref;repo.review(ref)
        repo.grant(grant);operation=request.plan_id+':protected-sign-in';repo.reserve(request,operation,grant.limits,stage='protected_operator_copilot_sign_in')
        clock=time.perf_counter();started=utc_now();exit_code=None;error=None
        try:
            repo.authorize(request);home=Path(review['private_home']);home.mkdir(mode=0o700)
            for name in ('tmp','config','data','cache','state','workspace'):(home/name).mkdir(mode=0o700)
            env={'PATH':'/usr/bin:/bin','HOME':str(home),'COPILOT_HOME':str(home/'config'),'TMPDIR':str(home/'tmp'),
                 'XDG_CONFIG_HOME':str(home/'config'),'XDG_DATA_HOME':str(home/'data'),'XDG_CACHE_HOME':str(home/'cache'),'XDG_STATE_HOME':str(home/'state'),'LC_ALL':'C'}
            # Inherit the operator's terminal, never PIPE or capture_output. No auth files are read.
            done=subprocess.run(review['argv'],cwd=home/'workspace',env=env,timeout=1100,check=False)
            exit_code=done.returncode
        except BaseException as failure:error=type(failure).__name__
        finally:
            elapsed=time.perf_counter()-clock
            receipt=ExecutionReceipt(decision_id=operation,action_id=operation,capability='toolkit.upstream-engineering@1',executor_id='waza.operator.copilot-login',executor_kind='command',
                status='success' if exit_code==0 and error is None else 'failed',started_at=started,ended_at=utc_now(),estimated={},actual_resources=ResourceVector(latency_ms=elapsed*1000),execution_success=exit_code==0 and error is None,error_type=error,
                metadata={'review_sha256':identity,'observed_resource_dimensions':['latency_ms'],'legacy_vector_defaults_are_not_observations':True,'execution_mode':'protected_operator_terminal','terminal_output':'NOT_CAPTURED','credential_state':'NOT_INSPECTED','account_entitlement':'UNKNOWN','model_calls':0})
            repo.store.save_receipt(receipt);repo.finish_operation(operation,elapsed_seconds=elapsed,resources=receipt.actual_resources)
            (HERE/'protected-login-result.json').write_text(json.dumps({'review_sha256':identity,'exit_code':exit_code,'error_type':error,'account_entitlement':'UNKNOWN','credential_state':'NOT_INSPECTED','model_calls':0,'automatic_retry':False},indent=2)+'\n')
            print('Setup attempt recorded. Do not share terminal output or credentials. Report only whether sign-in completed.')
    return 0 if exit_code==0 and error is None else 1
if __name__=='__main__':raise SystemExit(main())
