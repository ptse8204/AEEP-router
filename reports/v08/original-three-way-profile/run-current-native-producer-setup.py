"""Finite zero-model protected service setup; no native process is launched."""
import asyncio,hashlib,importlib.util,json,time
from pathlib import Path
from aeep.router import Router
from aeep.models import StrictModel
from aeep.assessment.models import AssessmentPlanningRequest,AssessmentLimits,content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
SOURCE='ade3b4e98078a7a33a9a1ff9bf1a917063872dbc4eeba96d42ee33cec554a3d1'
PRODUCER=OUT/'current-native-workbook-producer.py'
PIN='bc3369fdcdb5b86603b468395f7004b6a4fb3ae832c7eff54d991e0f98d910a7'
PROJECT=ROOT/'.aeep/current-composed-workbook-ade3'
class Definition(StrictModel):
 source_digest:str
 driver_sha256:str
 producer_sha256:str
 project:str
 maximum_seconds:int=30
 maximum_operations:int=1
 maximum_model_turns:int=0
 cash_usd:int=0
async def main():
 assert verification_source_digest(ROOT)==SOURCE
 assert hashlib.sha256(PRODUCER.read_bytes()).hexdigest()==PIN
 assert not PROJECT.exists()
 r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');q=AssessmentRepository(r.store)
 old=AssessmentPlanningRequest.model_validate(q.get('planning_request','planning_8e8a10fdfd7f49b891cf9f3f44c35228'))
 definition=Definition(source_digest=SOURCE,driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),producer_sha256=PIN,project=str(PROJECT))
 digest=q.put('native_setup_definition','current-composed-workbook-ade3',definition);q.review(digest)
 request=old.model_copy(update={'plan_id':'planning_current_composed_workbook_ade3','mapping_digest':digest,'definition_digests':[*old.definition_digests,digest]})
 q.put('planning_request',request.plan_id,request);q.review(content_digest(request));q.authorize(request)
 operation='setup:'+request.plan_id
 (OUT/'current-native-producer-setup-exact-review.json').write_text(json.dumps({'definition':definition.model_dump(mode='json'),'definition_digest':digest,'request_digest':content_digest(request),'operation_id':operation,'delegation':'September25/27 finite amendment; parent exact review'},indent=2)+'\n')
 q.reserve(request,operation,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=30,max_cash_usd=0),stage='native_service_setup')
 started=time.perf_counter();record={'operation_id':operation,'source_digest':SOURCE,'model_turns':0,'cash_usd':0,'setup_complete':False};native_router=None
 try:
  module=importlib.util.spec_from_file_location('current_native_producer',PRODUCER);producer=importlib.util.module_from_spec(module);module.loader.exec_module(producer)
  native_router,scope,spec,native,fixed,aeep=producer.setup(PROJECT)
  record.update({'setup_complete':True,'project':str(PROJECT),'scope':scope.model_dump(mode='json'),'spec':spec.model_dump(mode='json'),'native':native.model_dump(mode='json'),'aeep_declarations':aeep.list_tools(),'fixed_declarations':fixed.list_tools()})
 except BaseException as exc:
  record.update({'error_type':type(exc).__name__,'error_bytes':len(str(exc).encode()),'error_sha256':hashlib.sha256(str(exc).encode()).hexdigest()})
 finally:
  if native_router is not None:await native_router.close()
  record['elapsed_seconds']=time.perf_counter()-started;q.finish_operation(operation,elapsed_seconds=record['elapsed_seconds'])
  record['source_unchanged']=verification_source_digest(ROOT)==SOURCE
  await r.close();(OUT/'current-native-producer-setup-result.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({'setup_complete':record['setup_complete'],'elapsed_seconds':record['elapsed_seconds'],'error_type':record.get('error_type')}))
asyncio.run(main())
