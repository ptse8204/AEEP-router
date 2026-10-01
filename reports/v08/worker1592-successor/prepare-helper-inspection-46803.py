"""Prepare only: exact zero-model supplementary helper inspection on successor workers."""
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
    pair: dict
    program: str
    expected: dict
    maximum_operations: int = 2
    maximum_reserved_seconds: int = 130
    maximum_model_turns: int = 0


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
SOURCE = '46803ee2814c77977c4408b60768c6581fc0189f0c8fb9a8ccd7dd77ccc4b236'
assert verification_source_digest(ROOT) == SOURCE
assert not (OUT / 'helper-46803-review.json').exists()
prior = json.loads((OUT / 'conformance-review.json').read_text())
program = (OUT / 'helper-handshake-program.py').read_text()
router = Router.from_manifest(ROOT / '.aeep/live-review-v3/aeep.json')
service = AssessmentService(router, ROOT / '.aeep/live-review-v3/.aeep/assessments')
repo = service.repository
try:
    pair = repo.get('worker_pair_definition', prior['pair_definition_digest'])
    definition = Definition(source_digest=SOURCE, pair=pair, program=program,
        expected={'helper_ready': True, 'selected_version': 1, 'normal_exit': True})
    digest = content_digest(definition)
    definitions = {digest: definition}
    requests = []
    dependencies = runtime_dependencies()
    dependencies[str(OUT / 'helper-handshake-program.py')] = hashlib.sha256(program.encode()).hexdigest()
    dependencies[str(OUT / 'run-helper-inspection-46803.py')] = hashlib.sha256((OUT / 'run-helper-inspection-46803.py').read_bytes()).hexdigest()
    for source in prior['requests']:
        request = ConformanceProbeRequest(schema_version='assessment.conformance-request.v2', operation='worker_inspection',
            subject_digest=source['subject_digest'], recipe_digest=source['recipe_digest'],
            mapping_digest=digest, environment_digest=source['environment_digest'],
            authorization_id='onboarding', definition_digests=[digest, source['recipe_digest'], source['environment_digest']],
            worker_digest=source['worker_digest'], executable_dependencies=dependencies)
        repo.put('conformance_request', request.plan_id, request)
        definitions[content_digest(request)] = request
        for kind, key in [('subject', 'subject_digest'), ('recipe', 'recipe_digest'), ('environment', 'environment_digest')]:
            definitions[source[key]] = repo.get(kind, source[key])
        requests.append(request)
    repo.put('helper_inspection_definition', digest, definition)
    grant = AssessmentAuthorization.model_validate(repo.get('authorization', 'onboarding'))
    amendment = AssessmentScopeAmendment(authorization_id='onboarding', authorization_digest=content_digest(grant),
        subject_digests=list({r.subject_digest for r in requests}), recipe_digests=list({r.recipe_digest for r in requests}),
        environment_digests=list({r.environment_digest for r in requests}), reviewed_digests=list(definitions))
    review = {'authority': 'Standing finite assessment amendments; parent authorized exact zero-model helper readiness before pilot',
        'source_digest': SOURCE, 'definition_digest': digest, 'definition': definition.model_dump(mode='json'),
        'requests': [r.model_dump(mode='json') for r in requests], 'amendment': amendment.model_dump(mode='json'),
        'definitions': {d: o.model_dump(mode='json') if hasattr(o, 'model_dump') else o for d, o in definitions.items()},
        'maximum_operations': 2, 'maximum_reserved_seconds': 130, 'maximum_model_turns': 0, 'cash_usd': 0,
        'not_full_conformance': True, 'no_model_or_workbook_trial': True, 'no_image_change_or_auth_access': True}
    (OUT / 'helper-46803-review.json').write_text(json.dumps(review, indent=2) + '\n')
    print(json.dumps({'request_ids': [r.plan_id for r in requests], 'review_sha256': hashlib.sha256((OUT / 'helper-46803-review.json').read_bytes()).hexdigest(), 'inert': True}))
finally:
    router.store.close()
