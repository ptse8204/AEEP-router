from pathlib import Path
import json,hashlib
from aeep.router import Router
from aeep.assessment.service import AssessmentService
from aeep.assessment.models import AssessmentAuthorization,AssessmentScopeAmendment,content_digest
from aeep.assessment.boundary import BoundaryProbeDefinition,prepare_model_probe
from aeep.models import ExecutorSpec
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');s=AssessmentService(r,ROOT/'.aeep/live-review-v3/.aeep/assessments');q=s.repository
try:
 pair=q.get('worker_pair_definition','a62371cc67388021616af291ec55e8c4c6e4952ec5003d558e84c0f1fe04b729');spec=ExecutorSpec.model_validate(pair['control']);config=spec.config.copy()
 config.update(instructions='Return exactly {"connected":true} as your final response. Do not use tools, skills, network commands or files. This is a harmless connectivity check only.',artifact=None,input_tree=None,timeout_seconds=60,invocation={'mode':'turn'},store_prompt=False,store_output=False)
 spec=spec.model_copy(update={'id':'sol61-1592-connectivity-control','capability':'aeep.conformance.connectivity@1','config':config,'input_schema':{'type':'object','additionalProperties':False},'output_schema':{'type':'object','required':['connected'],'additionalProperties':False,'properties':{'connected':{'const':True}}}})
 definition=BoundaryProbeDefinition(name='model_connectivity',executor=spec,expected={'connected':True})
 prior=q.get('conformance_request','conformance_probe_af71ab71bf3f420e9b1d39fe02ffb48a')
 row=r.store._connection.execute("SELECT id FROM assessment_records WHERE kind='plan' AND json_extract(payload_json,'$.subject_digest')=? AND json_extract(payload_json,'$.recipe_digest')=? LIMIT 1",(prior['subject_digest'],prior['recipe_digest'])).fetchone();assert row
 request=prepare_model_probe(s,source_plan_id=row[0],definition=definition);defs={content_digest(request):request}
 for d in request.definition_digests:
  for kind in ['boundary_probe_definition','environment','probe_runtime','recipe']:
   try:defs[d]=q.get(kind,d);break
   except Exception:pass
  else:raise ValueError('definition absent')
 defs[request.subject_digest]=q.get('subject',request.subject_digest)
 grant=AssessmentAuthorization.model_validate(q.get('authorization','onboarding'))
 amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=content_digest(grant),subject_digests=[request.subject_digest],recipe_digests=[request.recipe_digest],environment_digests=[request.environment_digest],reviewed_digests=list(defs))
 review={'authority':'Standing finite conformance authority; parent September30 instructed existing connectivity mechanism before workbook/full boundary','source_digest':'f55ebe5ca0764a8ebfbcfa653c49ee39cced7e85b0a78515d6bbbb6b2f0a1cc4','request':request.model_dump(mode='json'),'definitions':{d:o.model_dump(mode='json') if hasattr(o,'model_dump') else o for d,o in defs.items()},'amendment':amendment.model_dump(mode='json'),'maximum_operations':1,'maximum_model_turns':1,'maximum_reserved_seconds':65,'maximum_cash_usd':0,'purpose':'Candidate/background/MCP absent harmless connectivity only; no workbook, campaign, qualification or admission','replay_allowed':False}
 (OUT/'connectivity-schema-review.json').write_text(json.dumps(review,indent=2)+'\n');print(json.dumps({'request_id':request.plan_id,'review_sha256':hashlib.sha256((OUT/'connectivity-schema-review.json').read_bytes()).hexdigest()}))
finally:r.store.close()
