"""One supported native rateLimits-only observation; no account/auth/model calls."""
import asyncio,hashlib,json,time
from pathlib import Path
from aeep.router import Router
from aeep.models import ExecutorSpec,StrictModel
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.models import AssessmentPlanningRequest,AssessmentLimits,content_digest
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_app_server import CodexAppServerAdapter
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
SOURCE='ade3b4e98078a7a33a9a1ff9bf1a917063872dbc4eeba96d42ee33cec554a3d1'
BINARY=Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
BINARY_SHA='50ac633af64851511f9bbc71032cdae7f1ba20b3234c189687d61ba846c354c5'
class Definition(StrictModel):
 source_digest:str
 driver_sha256:str
 binary_sha256:str
 method:str='account/rateLimits/read'
 maximum_seconds:int=30
 maximum_operations:int=1
 maximum_model_turns:int=0
 cash_usd:int=0
 classification:str='native rateLimits-only capacity; no worker/principal equivalence, no account/auth/model calls'
async def main():
 assert verification_source_digest(ROOT)==SOURCE
 assert not(OUT/'native-capacity-refresh-ade3-result.json').exists()
 with BINARY.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==BINARY_SHA
 r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');q=AssessmentRepository(r.store)
 old=AssessmentPlanningRequest.model_validate(q.get('planning_request','planning_8e8a10fdfd7f49b891cf9f3f44c35228'))
 definition=Definition(source_digest=SOURCE,driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),binary_sha256=BINARY_SHA)
 digest=q.put('capacity_refresh_definition','native-principal-ade3',definition);q.review(digest)
 request=old.model_copy(update={'plan_id':'planning_native_capacity_ade3','mapping_digest':digest,'definition_digests':[*old.definition_digests,digest]});q.put('planning_request',request.plan_id,request);q.review(content_digest(request));q.authorize(request)
 operation='capacity:'+request.plan_id
 (OUT/'native-capacity-refresh-ade3-exact-review.json').write_text(json.dumps({'delegation':'September25/27 finite amendment; parent narrow authorization overrides earlier operational waiting hold','definition':definition.model_dump(mode='json'),'definition_digest':digest,'request_digest':content_digest(request),'operation_id':operation,'authentication':'Codex-owned; no account/read or auth-state inspection','no_model_list_thread_or_turn':True},indent=2)+'\n')
 q.reserve(request,operation,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=30,max_cash_usd=0),stage='capacity_introspection')
 started=time.perf_counter();deadline=asyncio.get_running_loop().time()+30;adapter=None;record={'recorded_at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'source_digest':SOURCE,'operation_id':operation,'model_turns':0,'cash_usd':0,'controlled_worker_principal_equivalence':'unknown; no transfer inferred','capacity':None,'cleanup_confirmed':False}
 try:
  async with asyncio.timeout_at(deadline-5):
   adapter=CodexAppServerAdapter(argv=(str(BINARY),'app-server'),resource_id='native-codex-subscription',principal_salt=r.store.host_principal_key)
   await adapter.transport.start()
   observation=await adapter.snapshot_capacity()
   record['capacity']=observation.model_dump(mode='json')
 except BaseException as exc:
  record['error_type']=type(exc).__name__;record['error_message_bytes']=len(str(exc).encode());record['error_message_sha256']=hashlib.sha256(str(exc).encode()).hexdigest()
 finally:
  try:
   async with asyncio.timeout_at(deadline):
    if adapter is not None:
     await adapter.close()
     process=adapter.transport._process
     record['cleanup_confirmed']=(process is None or process.returncode is not None) and not adapter.transport._dynamic_tasks
  except BaseException as exc:record['cleanup_error_type']=type(exc).__name__
  finally:
   record['elapsed_seconds']=time.perf_counter()-started
   q.finish_operation(operation,elapsed_seconds=record['elapsed_seconds'])
   record['source_unchanged']=verification_source_digest(ROOT)==SOURCE
   await r.close()
   (OUT/'native-capacity-refresh-ade3-result.json').write_text(json.dumps(record,indent=2)+'\n')
   print(json.dumps(record),flush=True)
if __name__=='__main__':
 import sys
 if sys.argv[1:]!=['--execute-reviewed-native-capacity']:raise SystemExit('INERT: exact parent runtime authorization required')
 asyncio.run(main())
