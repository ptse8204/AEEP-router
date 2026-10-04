"""Bind the existing proxy lifecycle and pair runner without starting either."""
import hashlib,json
from pathlib import Path
from aeep.assessment.models import AssessmentAuthorization,AssessmentScopeAmendment,ConformanceProbeRequest,content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.models import StrictModel
from aeep.router import Router
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
class Definition(StrictModel):
    values:dict
path=OUT/'pair-review.json';pair=json.loads(path.read_text())
if (OUT/'pair-execution-review.json').exists():raise RuntimeError('preserve existing review')
proxy={'proxy_name':'aeep-reviewed-model-proxy','proxy_id_prefix':'5f9a44f86633',
    'proxy_image':'sha256:5bf590eb0bf8a06187ff092f0f75cf83b540cc27bd6a75fd8bd91305ca7b13de',
    'network_id':pair['definitions'][pair['pair_definition_digest']]['control']['config']['managed_worker']['network_id'],
    'runner_sha256':hashlib.sha256((OUT/'run-pair.py').read_bytes()).hexdigest(),
    'pair_review_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'source_digest':pair['source_digest'],
    'maximum_proxy_seconds':600,'restore_prior_stopped_state':True}
router=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');repo=AssessmentRepository(router.store)
try:
    definition=Definition(values=proxy);digest=repo.put('proxy_lifecycle_definition',content_digest(definition),definition)
    first=ConformanceProbeRequest.model_validate(pair['requests'][0])
    request=ConformanceProbeRequest(schema_version='assessment.conformance-request.v2',operation='worker_inspection',
        subject_digest=first.subject_digest,recipe_digest=first.recipe_digest,mapping_digest=digest,
        environment_digest=first.environment_digest,authorization_id=first.authorization_id,
        definition_digests=[*first.definition_digests,digest],worker_digest=first.worker_digest,executable_dependencies=first.executable_dependencies)
    rd=repo.put('conformance_request',request.plan_id,request)
    definitions={**pair['definitions'],digest:definition.model_dump(mode='json'),rd:request.model_dump(mode='json')}
    amendment=AssessmentScopeAmendment.model_validate(pair['amendment']).model_copy(update={'reviewed_digests':list(definitions)})
    review={**proxy,'authority':'September25/27 finite conformance delegation; existing owned proxy restored after turn-free inspection',
        'proxy_request':request.model_dump(mode='json'),'definitions':definitions,'amendment':amendment.model_dump(mode='json'),
        'maximum_operations':3,'maximum_seconds':1080,'maximum_model_turns':0,'maximum_cash_usd':0,
        'accounting':'Proxy operation includes the paired wait; worker lifetimes are separately charged. No candidate timing or total economic-cost claim.',
        'no_authentication_state_access':True,'approval_committed':False}
    target=OUT/'pair-execution-review.json';target.write_text(json.dumps(review,indent=2)+'\n')
    print(json.dumps({'review_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'proxy_request_id':request.plan_id}))
finally:router.store.close()
