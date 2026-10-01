"""One same-worker sanitized capacity refresh; no authentication or model probe."""
import asyncio,hashlib,json,time
from pathlib import Path
from aeep.router import Router
from aeep.models import ExecutorSpec,StrictModel
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.models import AssessmentPlanningRequest,AssessmentLimits,content_digest
from aeep.assessment.verification import verification_source_digest
from aeep.assessment.containment import container_name
from aeep.hosts.codex_app_server import CodexAppServerAdapter
from aeep.hosts.codex_pair_inspection import docker
from aeep.hosts.workers import binding_from_config
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
SOURCE='5fffda8a321005abc175e63f887f118b2297097542a5c1332560cb60f409f9bc'
SPEC_SHA='68ff47df45e0bc79a9d5605fd5acad3a1a53d614047c0f8344451df354437cca'
WORKER='7ceec1d0a3149ad4412c940c6d7dadab84e20576d6032b3ac55c278386bcbc2d'
class Definition(StrictModel):
 source_digest:str
 driver_sha256:str
 spec_sha256:str
 worker_digest:str
 method:str='account/rateLimits/read'
 maximum_seconds:int=30
 maximum_operations:int=1
 maximum_model_turns:int=0
 cash_usd:int=0
 classification:str='same-worker read-only capacity introspection; no planner execution/conformance/inference'
async def main():
 validation=json.loads((ROOT/'reports/v08/delivery-boundary-validation-5fffda8a3210.json').read_text())
 assert validation['complete'] is True and validation['release_ready'] is True and validation['source_digest']==SOURCE
 assert len(validation['checks'])==22 and all(x['exit_code']==0 and x['source_unchanged'] is True for x in validation['checks'])
 assert verification_source_digest(ROOT)==SOURCE
 assert not(OUT/'capacity-refresh-composed-5fff-result.json').exists()
 path=OUT/'capacity-refresh-ade3-spec.json';assert hashlib.sha256(path.read_bytes()).hexdigest()==SPEC_SHA
 spec=ExecutorSpec.model_validate(json.loads(path.read_text()));cfg=spec.managed_host_config();worker=binding_from_config(cfg.managed_worker);assert worker.digest()==WORKER
 r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');q=AssessmentRepository(r.store)
 old=AssessmentPlanningRequest.model_validate(q.get('planning_request','planning_8e8a10fdfd7f49b891cf9f3f44c35228'))
 definition=Definition(source_digest=SOURCE,driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),spec_sha256=SPEC_SHA,worker_digest=WORKER)
 digest=q.put('capacity_refresh_definition','same-worker-composed-5fff',definition);q.review(digest)
 request=old.model_copy(update={'plan_id':'planning_same_worker_capacity_composed_5fff','mapping_digest':digest,'definition_digests':[*old.definition_digests,digest]});q.put('planning_request',request.plan_id,request);q.review(content_digest(request));q.authorize(request)
 operation='capacity:'+request.plan_id
 (OUT/'capacity-refresh-composed-5fff-exact-review.json').write_text(json.dumps({'delegation':'September25/27 finite amendment; parent narrow authorization overrides earlier operational waiting hold','definition':definition.model_dump(mode='json'),'definition_digest':digest,'request_digest':content_digest(request),'operation_id':operation,'authentication':'Codex-owned; no account/read or auth-state inspection','no_model_list_thread_or_turn':True},indent=2)+'\n')
 q.reserve(request,operation,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=30,max_cash_usd=0),stage='capacity_introspection')
 started=time.perf_counter();deadline=asyncio.get_running_loop().time()+30;adapter=None;record={'source_digest':SOURCE,'operation_id':operation,'worker_digest':WORKER,'executor_id':spec.id,'adapter_id':cfg.adapter_id,'configured_model_ids':cfg.model_constraints.allowed_model_ids,'model_turns':0,'cash_usd':0,'desktop_principal_equivalence':'unknown; no transfer inferred','capacity':None,'cleanup_confirmed':False}
 try:
  async with asyncio.timeout_at(deadline-5):
   adapter=CodexAppServerAdapter.from_executor(spec,principal_salt=r.store.host_principal_key,manifest_directory=r.manifest_path.parent)
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
     remaining=await docker(worker,'ps','-a','--filter','name=^/'+container_name(adapter._worker_process_id)+'$','--format','{{.ID}}')
     process=adapter.transport._process
     record['cleanup_confirmed']=remaining.strip()=='' and (process is None or process.returncode is not None) and not adapter.transport._dynamic_tasks
  except BaseException as exc:record['cleanup_error_type']=type(exc).__name__
  finally:
   record['elapsed_seconds']=time.perf_counter()-started
   try:q.finish_operation(operation,elapsed_seconds=record['elapsed_seconds']);record['accounting_finished']=True
   except BaseException as exc:record.update(accounting_finished=False,accounting_error_type=type(exc).__name__)
   record['source_unchanged']=verification_source_digest(ROOT)==SOURCE
   result_path=OUT/'capacity-refresh-composed-5fff-result.json';result_path.write_text(json.dumps(record,indent=2)+'\n')
   try:await r.close();record['main_close_confirmed']=True
   except BaseException as exc:record.update(main_close_confirmed=False,close_error_type=type(exc).__name__)
   result_path.write_text(json.dumps(record,indent=2)+'\n')
   print(json.dumps(record),flush=True)
asyncio.run(main())
