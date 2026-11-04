"""First-party substitutes only; never executes Compose, guests or Langfuse."""
import asyncio,hashlib,importlib.util,json,tempfile,time
from pathlib import Path
from service_plan import compose,SECRETS,SERVICES,PROJECT,LABEL,ingestion_match
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('driver_controls',HERE/'run-service.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
from aeep.executors.base import BaseExecutor
from aeep.models import RawExecution,ResourceVector

checks=[]
def check(name,condition):
    assert condition,name;checks.append(name)

secrets={k:'FIRST_PARTY_PLACEHOLDER_'+k for k in SECRETS}
images={k:'example.invalid/image@sha256:'+'a'*64 for k in ('chainguard-minio','library-postgres','library-redis','clickhouse-clickhouse-server','langfuse-langfuse','langfuse-langfuse-worker')}
data=compose(images,'/owned/task',secrets)
check('bounded private topology and no automatic restart',set(data['services'])==set(SERVICES) and data['networks']['private']['internal'] and all(s['restart']=='no' and s['pull_policy']=='never' for s in data['services'].values()))
check('one loopback publication, no docker socket or host files',sum('ports' in s for s in data['services'].values())==1 and data['services']['web']['ports'][0]['host_ip']=='127.0.0.1' and [v['source'] for s in data['services'].values() for v in s.get('volumes',[]) if isinstance(v,dict)]==['/owned/task/mc'])
check('resource proposal is finite for this engineering journey',sum(int(data['services'][s]['mem_limit'][:-1]) for s in ('web','worker','postgres','minio','redis','clickhouse'))==4096)
check('write and root exceptions are explicit',all(s['read_only'] for n,s in data['services'].items() if n!='clickhouse') and data['services']['minio-owner']['command']==['65532:65532','/data'] and data['services']['minio-bucket']['user']=='501:20')
expected={'trace_id':'a'*32,'span_id':'b'*16,'source_receipt_sha256':'c'*64}
row={'id':expected['span_id'],'traceId':expected['trace_id'],'metadata':{'attributes':{'aeep.receipt.sha256':expected['source_receipt_sha256']}}}
check('exact receipt trace and span linkage',ingestion_match({'data':[row]},expected))
for key,bad in [('id','wrong'),('traceId','wrong'),('metadata',{'receipt':'prefix'+expected['source_receipt_sha256']})]:
    changed={**row,key:bad};assert not ingestion_match({'data':[changed]},expected)
check('mismatched IDs and nonexact receipt claims rejected',not ingestion_match({'data':'bad'},expected))

prepared=m.load(HERE/'prepared.json')
original_validate=m.validate
m.validate=lambda *_a,**_k:None
try:
  with tempfile.TemporaryDirectory(prefix='aeep-langfuse-driver-control-') as directory:
    work=Path(directory);(work/'service-execution').mkdir()
    with m.ReceiptStore(work/'first-party.sqlite3') as store:
      repo=m.AssessmentRepository(store)
      for ref,raw in prepared['scopes'].items():repo.review(repo.put('toolkit_langfuse_service_scope',ref,m.Scope.model_validate(raw)))
      for kind,file,model in [('toolkit_receipt_export','enabled-export.json',m.ReceiptExportDefinition),('toolkit_receipt_export','disabled-export.json',m.ReceiptExportDefinition),
                              ('toolkit_workflow_accounting','enabled-accounting.json',m.WorkflowAccountingDefinition),('toolkit_workflow_accounting','disabled-accounting.json',m.WorkflowAccountingDefinition)]:
          value=model.model_validate(m.load(HERE/file));repo.review(repo.put(kind,m.content_digest(value),value))
      repo.grant(m.AssessmentAuthorization.model_validate(prepared['grant']))
      request=m.RecipeMaterializationRequest.model_validate(prepared['request'])
      review={'work':str(work),'docker_config':str(work),'docker_socket':'/not-opened',
              'docker':'/not-executed/docker','maximum_driver_commands':47,'compose':'/not-executed/compose','executables':{}}
      journey=m.Journey(review,repo,request,'d'*64);journey.output=work/'service-execution'
      class Substitute(BaseExecutor):
        async def execute(self,context):
          context.invocation_check()
          if context.spec.id.endswith('failure'):raise TimeoutError('PRIVATE_FIRST_PARTY_EXCEPTION')
          if context.spec.id.endswith('nested'):
            nested=request.model_copy(update={'plan_id':'owned-inner-control'})
            repo.reserve(nested,'owned-inner-control',m.AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=1))
            clock=time.perf_counter();await asyncio.sleep(.02);elapsed=time.perf_counter()-clock
            repo.finish_operation('owned-inner-control',elapsed_seconds=elapsed,resources=ResourceVector(latency_ms=elapsed*1000))
          return RawExecution(status='success',exit_code=0,stdout='PRIVATE_FIRST_PARTY_STREAM',stderr='PRIVATE_FIRST_PARTY_ERROR')
      m.CommandExecutor=Substitute
      journey.command('nested',['not-executed'],1)
      receipt=json.loads((journey.output/'receipt-1.json').read_bytes())
      meta=receipt['metadata']
      check('nested canonical intervals excluded from wrapper charge',meta['excluded_canonical_child_seconds']>=.02 and abs(receipt['actual_resources']['latency_ms']/1000-(meta['whole_command_wall_seconds']-meta['excluded_canonical_child_seconds']))<1e-6)
      try:journey.command('failure',['not-executed'],1)
      except AssertionError:pass
      else:raise AssertionError('failure did not stop')
      check('failed command remains charged and settled',not store._connection.execute("SELECT 1 FROM assessment_operations WHERE state='reserved'").fetchone() and repo.operation_ledger(request.plan_id+':driver-commands').operations[-1].elapsed_seconds is not None)
      persisted=''.join(p.read_text() for p in journey.output.glob('*.json'))
      check('streams and exception payloads are not persisted',all(s not in persisted for s in ['PRIVATE_FIRST_PARTY_STREAM','PRIVATE_FIRST_PARTY_ERROR','PRIVATE_FIRST_PARTY_EXCEPTION']))
      before=journey.counters()[0]
      repo.review(request.definition_digests[0],revoke=True)
      journey.command('cleanup-control',['not-executed'],1,cleanup=True)
      check('prebudgeted cleanup remains possible after authority revocation',journey.counters()[0]==before and journey.cleanup_seconds>0)
      record=['sha256:owned','/'+PROJECT+'-web','sha256:image',{LABEL:PROJECT,'com.docker.compose.service':'web','com.docker.compose.project':PROJECT},'running',0]
      review['service_image_ids']={'web':'sha256:image'}
      journey.command=lambda *_a,**_k:' '.join(json.dumps(v) for v in record)+'\n'
      assert journey.inspect([PROJECT+'-web'])[0]['id']=='sha256:owned'
      record[3][LABEL]='someone-else'
      try:journey.inspect([PROJECT+'-web'])
      except AssertionError:pass
      else:raise AssertionError('foreign resource accepted')
      check('foreign ownership never permits cleanup',journey.owned=={'web':'sha256:owned'})
finally:m.validate=original_validate

result={'passed':True,'evidence_kind':'FIRST_PARTY_SUBSTITUTES_NOT_UPSTREAM_EXECUTION','checks':checks,'models':0,'services':0,'comparisons':'PAUSED'}
(HERE/'driver-controls.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
