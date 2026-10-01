"""Inert exact offline image setup review; no build, worker or model call."""
import hashlib
import json
from pathlib import Path
from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import AssessmentAuthorization, AssessmentScopeAmendment, ConformanceProbeRequest, content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.models import StrictModel
from aeep.router import Router

class Definition(StrictModel):
    source_digest: str
    base_profile: dict
    base_reference: str
    files: dict
    maximum_operations: int = 1
    maximum_reserved_seconds: int = 90
    maximum_model_turns: int = 0

ROOT=Path(__file__).resolve().parents[3]; OUT=Path(__file__).parent
SOURCE='94f3fad31d2811368a2955a63b0531b5147f0d132551000f674292b7a5a280bb'
assert verification_source_digest(ROOT)==SOURCE
assert not (OUT/'linux-lifecycle-image-review.json').exists()
prior=json.loads((OUT/'linux-mcp-successor-review.json').read_text())
profile=prior['definition']['profiles']['outside_mcp']
profile=json.loads(json.dumps(profile));profile['config']['argv']=[profile['config']['argv'][0],'app-server']
files={str(f.resolve()):hashlib.sha256(f.read_bytes()).hexdigest() for f in (OUT/'immutable-lifecycle').iterdir() if f.is_file()}
definition=Definition(source_digest=SOURCE,base_profile=profile,files=files,base_reference='aeep-sol61-successor-control:1592');digest=content_digest(definition)
router=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');service=AssessmentService(router,ROOT/'.aeep/live-review-v3/.aeep/assessments');repo=service.repository
try:
    source=prior['requests'][0];dependencies=runtime_dependencies();dependencies.update(files)
    dependencies[str(OUT/'build-linux-lifecycle-image.py')]=hashlib.sha256((OUT/'build-linux-lifecycle-image.py').read_bytes()).hexdigest()
    request=ConformanceProbeRequest(schema_version='assessment.conformance-request.v2',operation='worker_inspection',subject_digest=source['subject_digest'],recipe_digest=source['recipe_digest'],mapping_digest=digest,environment_digest=source['environment_digest'],authorization_id='onboarding',definition_digests=[digest,source['recipe_digest'],source['environment_digest']],worker_digest=source['worker_digest'],executable_dependencies=dependencies)
    repo.put('conformance_request',request.plan_id,request);repo.put('linux_diagnostic_image_definition',digest,definition)
    definitions={digest:definition,content_digest(request):request}
    for kind,key in [('subject','subject_digest'),('recipe','recipe_digest'),('environment','environment_digest')]:definitions[source[key]]=repo.get(kind,source[key])
    grant=AssessmentAuthorization.model_validate(repo.get('authorization','onboarding'))
    amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=content_digest(grant),subject_digests=[source['subject_digest']],recipe_digests=[source['recipe_digest']],environment_digests=[source['environment_digest']],reviewed_digests=list(definitions))
    review={'execution_authorized':True,'authority':'Standing finite lifecycle prerequisite amendment authorized by parent; exact immutable layer reviewed before setup','source_digest':SOURCE,'request':request.model_dump(mode='json'),'definition_digest':digest,'definition':definition.model_dump(mode='json'),'amendment':amendment.model_dump(mode='json'),'definitions':{d:o.model_dump(mode='json') if hasattr(o,'model_dump') else o for d,o in definitions.items()},'bounds':{'operations':1,'setup_seconds':90,'build_seconds':60,'inspection_seconds':10,'model_turns':0,'cash_usd':0,'host_disk_growth_bytes':67108864,'minimum_free_bytes':134217728},'queued_diagnostic_bounds':{'operations':1,'elapsed_seconds':60,'model_turns':0,'cash_usd':0},'no_download_install_auth_or_existing_image_change':True,'not_third_profile_conformance':True,'cleanup':'Retain exact created image until bound diagnostic finishes; remove only that owned image later if no longer needed. Never prune.'}
    (OUT/'linux-lifecycle-image-review.json').write_text(json.dumps(review,indent=2)+'\n');print(json.dumps({'review_sha256':hashlib.sha256((OUT/'linux-lifecycle-image-review.json').read_bytes()).hexdigest(),'request_id':request.plan_id,'context_bytes':sum(Path(f).stat().st_size for f in files),'inert':True}))
finally:router.store.close()
