"""First stopped ClickHouse public-log audit, under the existing service grant."""
import argparse,hashlib,importlib.util,json,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;OLD=HERE.parent/'langfuse-health-diagnosis-20261104'
spec=importlib.util.spec_from_file_location('readonly_health_bridge',OLD/'run.py');health=importlib.util.module_from_spec(spec);spec.loader.exec_module(health);base=health.base;base.HERE=HERE
from aeep.assessment.models import AssessmentLimits,RecipeMaterializationRequest,content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.models import ResourceVector
from aeep.store import ReceiptStore
load=base.load;sha=base.sha;write=base.write
def execute(review,identity):
    base.validate(review)
    with (HERE/'execution-started.json').open('x') as f:json.dump({'review_sha256':identity,'first_read_only_file_audit':True},f)
    (HERE/'service-execution').mkdir(mode=0o700)
    prepared=load(HERE/'prepared.json');request=RecipeMaterializationRequest.model_validate(prepared['request'])
    result={'passed':False,'models':0,'service_programs_executed':False,'raw_content_retained':False,'accounting_uncertain':False,'cleanup_uncertain':False,'comparisons':'PAUSED'}
    with ReceiptStore(review['ledger']) as store:
        repo=AssessmentRepository(store)
        assert list(store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(request.authorization_id,)).fetchone())==review['counters_before']
        scope=health.Scope.model_validate(prepared['scope']);ref=content_digest(scope);assert repo.put('toolkit_langfuse_health_scope',ref,scope)==ref;repo.review(ref)
        outer=request.plan_id+':exclusive-driver';repo.reserve(request,outer,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=30),stage='langfuse_stopped_log_audit_overhead')
        clock=time.perf_counter();journey=base.Journey(review,repo,request,identity)
        try:
            data=json.loads(journey.command('read-public-log-files',[review['diagnostic_python'],'-I','-B',str(HERE/'read-files.py'),'--review',identity],80))
            assert all(x['read'] for x in data['files']);result.update(passed=True,files=data['files'])
        except BaseException as failure:result['error_type']=type(failure).__name__
        finally:
            elapsed=max(0.,time.perf_counter()-clock-journey.child_seconds);repo.finish_operation(outer,elapsed_seconds=elapsed,resources=ResourceVector(latency_ms=elapsed*1000))
            result['accounting_uncertain']=store._connection.execute("SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",(request.authorization_id,)).fetchone() is not None
            result['grant_counters']=journey.counters();write(HERE/'operation-ledger.json',repo.operation_ledger(request.plan_id+':driver-commands').model_dump(mode='json'));write(HERE/'summary.json',result)
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute-delegated');args=p.parse_args();review=load(HERE/'operation-review.json');identity=sha(HERE/'operation-review.json')
    if args.execute_delegated is None:print(json.dumps({'execution':False,'review_sha256':identity}));raise SystemExit(0)
    a=load(HERE/'delegated-authority.json');assert args.execute_delegated==identity==a['review_sha256'] and a['first_attempt'] is True
    value=execute(review,identity);print(json.dumps({k:v for k,v in value.items() if k!='files'}))
    if not value['passed']:raise SystemExit(1)
