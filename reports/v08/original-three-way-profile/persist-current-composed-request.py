"""Persist only the exact parent-reviewed definitions; no host or model execution."""
import asyncio,hashlib,importlib.util,json
from pathlib import Path
from aeep.router import Router
from aeep.models import ActionRequest
from aeep.assessment.models import ConformanceProbeRequest,content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.boundary import BoundaryProbeDefinition
from aeep.hosts.codex_pair_inspection import ComposedPairDefinition
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
BUNDLE_SHA='7466d36a2c8194a6d2eccfe4cec184f54900fa0604a757dbbe4e4d29d89fb157'
async def main():
 path=OUT/'current-composed-assembly.json';assert hashlib.sha256(path.read_bytes()).hexdigest()==BUNDLE_SHA
 x=json.loads(path.read_text());module=importlib.util.spec_from_file_location('current_union',OUT/'native-dynamic-operator-composition.py');composition=importlib.util.module_from_spec(module);module.loader.exec_module(composition)
 r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');q=AssessmentRepository(r.store)
 try:
  entries=[('codex_dynamic_tools',digest,composition.DynamicDefinition.model_validate(doc)) for digest,doc in x['callbacks'].items()]
  entries += [('composed_pair_definition',x['pair_digest'],ComposedPairDefinition.model_validate(x['pair'])),('boundary_probe_definition',x['definition_digest'],BoundaryProbeDefinition.model_validate(x['definition'])),('composed_callback_action',x['action_digest'],ActionRequest.model_validate(x['action']))]
  request=ConformanceProbeRequest.model_validate(x['request']);entries.append(('conformance_request',request.plan_id,request))
  for kind,identity,value in entries:
   digest=q.put(kind,identity,value);assert digest==content_digest(value);q.review(digest)
  q.authorize(request)
  print(json.dumps({'request_digest':content_digest(request),'exact_definitions_reviewed':len(entries),'hosts_started':0}))
 finally:await r.close()
asyncio.run(main())
