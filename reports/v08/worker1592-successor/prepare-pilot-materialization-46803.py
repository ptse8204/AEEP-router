from pathlib import Path
import json,hashlib,shutil
from aeep.router import Router
from aeep.assessment.service import AssessmentService
from aeep.assessment.extensions import prepare
from aeep.assessment.models import AssessmentEnvironment,AssessmentAuthorization,AssessmentScopeAmendment,content_digest
from aeep.assessment.verification import verification_source_digest
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');s=AssessmentService(r,ROOT/'.aeep/live-review-v3/.aeep/assessments');q=s.repository
try:
 accepted=json.loads((OUT/'boundary-46803-verifier-result.json').read_text());assert accepted['full_boundary_verifier_accepted'];assert verification_source_digest(ROOT)==accepted['source_digest']
 pair=q.get('worker_pair_definition','a62371cc67388021616af291ec55e8c4c6e4952ec5003d558e84c0f1fe04b729');prior=q.get('conformance_request','conformance_probe_f027dac139e64fa2afa53b80aa1089b3')
 env=AssessmentEnvironment(environment_id='sol61-1592-workbook-timing-pilot',kind='container',identity={'purpose':'Fresh141case materialization for existing8case timing pilot only','source_digest':accepted['source_digest'],'seed':'107'},container_image='aeep-assessment-runtime@sha256:9e3b3712bae59607d06a162f275f0afbd916a70bcb91b544e9f350b6a6712fd7',container_runtime=shutil.which('docker'),container_socket=str(Path.home()/'.docker/run/docker.sock'),memory_mb=256,process_limit=64,conformance_digests={pair[role]['id']:accepted['records'][role]['digest'] for role in ['control','treatment']})
 request=prepare(s,subject_id=prior['subject_digest'],recipe_id=prior['recipe_digest'],authorization_id='onboarding',environment=env,seed=107);defs={content_digest(request):request,request.subject_digest:q.get('subject',request.subject_digest)}
 for d in request.definition_digests:
  for kind in ['recipe','environment','recipe_runtime']:
   try:defs[d]=q.get(kind,d);break
   except Exception:pass
  else:raise ValueError('definition missing')
 grant=AssessmentAuthorization.model_validate(q.get('authorization','onboarding'));amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=content_digest(grant),subject_digests=[request.subject_digest],recipe_digests=[request.recipe_digest],environment_digests=[request.environment_digest],reviewed_digests=list(defs))
 review={'authority':'Standing finite amendment authority; parent selected existing8case timing pilot, preserve141materialization; preparation only pending source scheduling','source_digest':accepted['source_digest'],'request':request.model_dump(mode='json'),'environment':env.model_dump(mode='json'),'definitions':{d:o.model_dump(mode='json') if hasattr(o,'model_dump') else o for d,o in defs.items()},'amendment':amendment.model_dump(mode='json'),'maximum_operations':1,'maximum_reserved_seconds':35,'maximum_model_turns':0,'maximum_cash_usd':0,'case_count':141,'pilot_screening_count':8,'no_model_start':True,'no_qualification_or_admission':True,'no_holdout_replay':True,'seed':107}
 (OUT/'pilot-materialization-46803-review.json').write_text(json.dumps(review,indent=2)+'\n');print(json.dumps({'request_id':request.plan_id,'review_sha256':hashlib.sha256((OUT/'pilot-materialization-46803-review.json').read_bytes()).hexdigest(),'inert':True}))
finally:r.store.close()
