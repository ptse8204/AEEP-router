"""Read retained stopped-service metadata; never persist raw startup logs."""
import argparse,hashlib,importlib.util,json,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];OLD=HERE.parent/'langfuse-tmpfs-correction-20261104'
sys.path.insert(0,str(OLD))
spec=importlib.util.spec_from_file_location('reviewed_langfuse_commands',OLD/'run-service.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base);base.HERE=HERE
from aeep.assessment.models import AssessmentLimits,RecipeMaterializationRequest,content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.models import ResourceVector,StrictModel
from aeep.store import ReceiptStore
load=base.load;sha=base.sha;write=base.write
class Scope(StrictModel):
    role:str
    plan_sha256:str
CATEGORIES=('read-only file system','permission denied','access denied','authentication failed','config.json','connection refused','not enough space','no such file','out of memory','ready for connections','listening','fatal','error')
PUBLIC_PATHS=('/home/nonroot/.mc','/root/.mc','/etc/clickhouse-server','/var/lib/clickhouse','/var/log/clickhouse-server','/var/lib/postgresql','/var/run/postgresql','/tmp','/data')
def classify(text):
    lower=text.lower()
    return {'bytes':len(text.encode()),'sha256':hashlib.sha256(text.encode()).hexdigest(),'categories':[key for key in CATEGORIES if key in lower],'public_paths':[p for p in PUBLIC_PATHS if p in text],'raw_text_retained':False}
def execute(review,identity):
    base.validate(review)
    with (HERE/'execution-started.json').open('x') as f:json.dump({'review_sha256':identity,'first_read_only_health_diagnosis':True},f)
    (HERE/'service-execution').mkdir(mode=0o700)
    prepared=load(HERE/'prepared.json');request=RecipeMaterializationRequest.model_validate(prepared['request'])
    result={'passed':False,'models':0,'service_programs_executed':False,'raw_logs_retained':False,'comparisons':'PAUSED','accounting_uncertain':False,'cleanup_uncertain':False,'services':[]}
    with ReceiptStore(review['ledger']) as store:
        repo=AssessmentRepository(store)
        assert list(store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(request.authorization_id,)).fetchone())==review['counters_before']
        value=Scope.model_validate(prepared['scope']);ref=content_digest(value);assert repo.put('toolkit_langfuse_health_scope',ref,value)==ref;repo.review(ref)
        outer=request.plan_id+':exclusive-driver';repo.reserve(request,outer,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=30),stage='langfuse_health_diagnosis_overhead')
        began=time.perf_counter();journey=base.Journey(review,repo,request,identity)
        try:
            template='{{json .Id}} {{json .Name}} {{json .Image}} {{json .Config.Labels}} {{json .State}}'
            raw=journey.command('health-state',journey.docker('inspect','--format',template,*review['owned_container_ids'].values()),20)
            decoder=json.JSONDecoder();by_id={v:k for k,v in review['owned_container_ids'].items()}
            for line in raw.splitlines():
                values=[]
                while line.strip():
                    value,idx=decoder.raw_decode(line.lstrip());values.append(value);line=line.lstrip()[idx:]
                ident,name,image,labels,state=values;service=by_id[ident]
                assert name=='/'+base.PROJECT+'-'+service and labels[base.LABEL]==base.PROJECT
                assert image in review['service_image_allowed_ids'][service] and not state['Running']
                health=state.get('Health') or {}
                row={'service':service,'id':ident,'status':state['Status'],'exit_code':state['ExitCode'],'OOMKilled':state['OOMKilled'],'health_status':health.get('Status'),'health_log':[{'exit_code':x['ExitCode'],'diagnostic':classify(x.get('Output',''))} for x in health.get('Log',[])]}
                # Read only the stopped unhealthy/faulted startup's bounded tail.
                if health.get('Status')=='unhealthy' or 0<state['ExitCode']<128:
                    row['startup_log']=json.loads(journey.command('startup-log-'+service,[review['diagnostic_python'],'-I','-B',str(HERE/'log-categories.py'),'--container',ident,'--review',identity],20))
                result['services'].append(row)
            assert len(result['services'])==len(by_id);result['passed']=True
        except BaseException as error:result['error_type']=type(error).__name__
        finally:
            elapsed=max(0.,time.perf_counter()-began-journey.child_seconds);repo.finish_operation(outer,elapsed_seconds=elapsed,resources=ResourceVector(latency_ms=elapsed*1000))
            result['accounting_uncertain']=store._connection.execute("SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",(request.authorization_id,)).fetchone() is not None
            result['grant_counters']=journey.counters();write(HERE/'operation-ledger.json',repo.operation_ledger(request.plan_id+':driver-commands').model_dump(mode='json'));write(HERE/'summary.json',result)
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute-delegated');args=p.parse_args();review=load(HERE/'operation-review.json');identity=sha(HERE/'operation-review.json')
    if args.execute_delegated is None:print(json.dumps({'execution':False,'review_sha256':identity}));raise SystemExit(0)
    authority=load(HERE/'delegated-authority.json');assert args.execute_delegated==identity==authority['review_sha256'] and authority['first_attempt'] is True
    result=execute(review,identity);print(json.dumps({k:v for k,v in result.items() if k!='services'}))
    if not result['passed']:raise SystemExit(1)
