"""Finite zero-model scope enrollment; no native process is launched."""
import asyncio,hashlib,importlib.util,json,time
from pathlib import Path
from aeep.router import Router
from aeep.models import StrictModel
from aeep.assessment.models import AssessmentPlanningRequest,AssessmentLimits,content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
SOURCE='5fffda8a321005abc175e63f887f118b2297097542a5c1332560cb60f409f9bc'
PRODUCER=OUT/'current-native-workbook-scope-5fff.py'
PIN='000145a263a52f58d721bdb25949bbedd1e9165ad2956eed13b2183cdd98fd75'
PROJECT=ROOT/'.aeep/current-composed-workbook-ade3'
RESULT=OUT/'current-native-scope-enrollment-5fff-native-only-result.json'
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
 assert not RESULT.exists()
 prerequisite_review=ROOT/'reports/v08/native-only-validation-prerequisite-5fff-review.json'
 assert hashlib.sha256(prerequisite_review.read_bytes()).hexdigest()=='e9f899c8c61ec0085c23330fff539547cd8276004be9a61e717d84cb2b7df230'
 native_review=json.loads(prerequisite_review.read_text());assert native_review['execution_authorized'] is True and native_review['source_digest']==SOURCE
 helper=ROOT/'reports/v08/native-only-validation-prerequisite-5fff.py'
 assert hashlib.sha256(helper.read_bytes()).hexdigest()=='fd9fcb6b0bc58f36c7127be0824732313dc3d5f899685b785392d19e23591c1e'
 loaded=importlib.util.spec_from_file_location('exact_native_validation_prerequisite',helper);prerequisite=importlib.util.module_from_spec(loaded);loaded.loader.exec_module(prerequisite)
 prerequisite.validate(ROOT,native_review,SOURCE)
 assert verification_source_digest(ROOT)==SOURCE
 assert hashlib.sha256(PRODUCER.read_bytes()).hexdigest()==PIN
 assert PROJECT.exists()
 r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');q=AssessmentRepository(r.store)
 old=AssessmentPlanningRequest.model_validate(q.get('planning_request','planning_8e8a10fdfd7f49b891cf9f3f44c35228'))
 definition=Definition(source_digest=SOURCE,driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),producer_sha256=PIN,project=str(PROJECT))
 digest=q.put('native_setup_definition','current-composed-workbook-5fff-native-only',definition);q.review(digest)
 request=old.model_copy(update={'plan_id':'planning_current_composed_workbook_5fff_native_only','mapping_digest':digest,'definition_digests':[*old.definition_digests,digest]})
 q.put('planning_request',request.plan_id,request);q.review(content_digest(request));q.authorize(request)
 operation='setup:'+request.plan_id
 (OUT/'current-native-scope-enrollment-5fff-native-only-exact-review.json').write_text(json.dumps({'definition':definition.model_dump(mode='json'),'definition_digest':digest,'request_digest':content_digest(request),'operation_id':operation,'delegation':'September25/27 finite amendment; parent exact review'},indent=2)+'\n')
 q.reserve(request,operation,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=30,max_cash_usd=0),stage='native_service_setup')
 started=time.perf_counter();record={'operation_id':operation,'source_digest':SOURCE,'model_turns':0,'cash_usd':0,'setup_complete':False};native_router=None
 try:
  module=importlib.util.spec_from_file_location('current_native_producer',PRODUCER);producer=importlib.util.module_from_spec(module);module.loader.exec_module(producer)
  record.update(producer.enroll());record['setup_complete']=True
 except BaseException as exc:
  record.update({'error_type':type(exc).__name__,'error_bytes':len(str(exc).encode()),'error_sha256':hashlib.sha256(str(exc).encode()).hexdigest()})
 finally:
  if native_router is not None:await native_router.close()
  record['elapsed_seconds']=time.perf_counter()-started
  try:q.finish_operation(operation,elapsed_seconds=record['elapsed_seconds']);record['accounting_finished']=True
  except BaseException as exc:record.update(accounting_finished=False,accounting_error_type=type(exc).__name__)
  record['source_unchanged']=verification_source_digest(ROOT)==SOURCE
  RESULT.write_text(json.dumps(record,indent=2)+'\n')
  try:await r.close();record['main_close_confirmed']=True
  except BaseException as exc:record.update(main_close_confirmed=False,close_error_type=type(exc).__name__)
  RESULT.write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({'setup_complete':record['setup_complete'],'elapsed_seconds':record['elapsed_seconds'],'error_type':record.get('error_type')}))
asyncio.run(main())
