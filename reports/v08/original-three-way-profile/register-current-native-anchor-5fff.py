"""Exact metadata-only typed registration; no worker, callback or model invocation."""
import asyncio,hashlib,importlib.util,json
from pathlib import Path
from aeep.models import StrictModel
from aeep.router import Router
from aeep.assessment.models import ConformanceProbeRequest,content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.boundary import BoundaryProbeDefinition
from aeep.assessment.identity import verify_dependencies
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_pair_inspection import ComposedPairDefinition
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
class DynamicDefinition(StrictModel):
 namespace:str
 tools:list[dict]
 identity:dict
 max_calls:int
 timeout_seconds:float
async def main():
 path=OUT/'current-composed-native-anchor-5fff-assembly.json'
 assert hashlib.sha256(path.read_bytes()).hexdigest()=='dc5c06821eca774237275c7e2ea911238d22fa1c28b8e6d829f1ec0f1f641650'
 bundle=json.loads(path.read_text());assert bundle['execution_authorized'] is True and verification_source_digest(ROOT)==bundle['source_digest']
 request=ConformanceProbeRequest.model_validate(bundle['request']);assert content_digest(request)==bundle['request_digest'] and request.composed_model_turns==0
 verify_dependencies(request.executable_dependencies)
 worker_bundle=json.loads((OUT/'composed-workers-5fff-assembly.json').read_text())
 collector_path=OUT/'collect-composed-workers-5fff.py'
 assert request.executable_dependencies[str(collector_path.resolve())]==hashlib.sha256(collector_path.read_bytes()).hexdigest()
 spec=importlib.util.spec_from_file_location('current_exact_worker_component',collector_path);collector=importlib.util.module_from_spec(spec);spec.loader.exec_module(collector)
 component=collector.WorkerComponentDefinition.model_validate(worker_bundle['component'])
 pair=ComposedPairDefinition.model_validate(bundle['composed_pair']);assert content_digest(pair)==bundle['pair_digest'] and component.composed==pair
 r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');repo=AssessmentRepository(r.store);written=[]
 def put(kind,identifier,value):
  digest=content_digest(value)
  with repo.store._lock:
   row=repo.store._connection.execute('SELECT revoked FROM assessment_reviews WHERE digest=?',(digest,)).fetchone()
  if row and row[0]:raise ValueError('revoked review cannot be reactivated')
  assert repo.put(kind,identifier,value)==digest;repo.review(digest);written.append({'kind':kind,'digest':digest})
 try:
  (OUT/'current-native-anchor-5fff-registration-exact-review.json').write_text(json.dumps({'authority':bundle['authority'],'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'bundle_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'request_digest':content_digest(request),'model_turns':0,'worker_starts':0,'native_task_calls':0},indent=2)+'\n')
  for digest,value in bundle['callbacks'].items():
   model=DynamicDefinition.model_validate(value);assert content_digest(model)==digest;put('codex_dynamic_tools',digest,model)
  put('composed_pair_definition',content_digest(pair),pair);put('composed_worker_component',content_digest(component),component)
  for digest,value in worker_bundle['probe_definitions'].items():
   model=BoundaryProbeDefinition.model_validate(value);assert content_digest(model)==digest;put('boundary_probe_definition',digest,model)
  put('conformance_request',request.plan_id,request);repo.authorize(request)
  print(json.dumps({'registration_passed':True,'typed_records':len(written),'request_id':request.plan_id,'model_turns':0,'native_calls':0}))
 finally:
  (OUT/'current-native-anchor-5fff-registration-result.json').write_text(json.dumps({'written':written,'request_id':request.plan_id,'model_turns':0,'worker_starts':0},indent=2)+'\n');await r.close()
asyncio.run(main())
