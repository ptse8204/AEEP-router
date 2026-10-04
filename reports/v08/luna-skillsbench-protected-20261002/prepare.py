"""Prepare exact literal-only recipe checks; no container or model is started."""
import hashlib
import json
import shutil
from pathlib import Path

from aeep.assessment.extensions import bounded_batches, prepare
from aeep.assessment.models import (
    AssessmentAuthorization, AssessmentEnvironment, AssessmentScopeAmendment,
    AssessmentSubject, content_digest,
)
from aeep.assessment.service import AssessmentService
from aeep.assessment.skillsbench_recipe import skillsbench_offer_letter_recipe
from aeep.assessment.verification import verification_source_digest
from aeep.router import Router

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
assert not (OUT / 'review.json').exists(), 'preparation must not replace an existing request'
router = Router.from_manifest(ROOT / '.aeep/live-review-v3/aeep.json')
service = AssessmentService(router, ROOT / '.aeep/live-review-v3/.aeep/assessments')
repo = service.repository
try:
    recipe = skillsbench_offer_letter_recipe()
    extension = recipe.extension
    assert extension is not None
    program = ROOT / 'integrations/assessment-runtime/skillsbench_offer_letter_program.py'
    subject = AssessmentSubject(kind='command', location=str(program),
        dependency_digests={program.name: hashlib.sha256(program.read_bytes()).hexdigest()},
        description='Protected literal recipe validation only; no candidate comparison or admission.')
    environment = AssessmentEnvironment(environment_id='skillsbench-literals-20261002',
        kind='container', identity={'purpose': 'Protected literal reference and grader checks; no holdouts'},
        container_image='sha256:9e3b3712bae59607d06a162f275f0afbd916a70bcb91b544e9f350b6a6712fd7',
        container_runtime=shutil.which('docker'),
        container_socket=str(Path.home() / '.docker/run/docker.sock'), memory_mb=256, process_limit=64)
    for kind, identity, value in [('subject', subject.subject_id, subject),
                                  ('recipe', recipe.recipe_id, recipe)]:
        repo.put(kind, identity, value)
    request = prepare(service, subject_id=subject.subject_id, recipe_id=recipe.recipe_id,
        authorization_id='onboarding', environment=environment, seed=2026100201)
    definitions = {content_digest(subject): subject.model_dump(mode='json'),
        content_digest(recipe): recipe.model_dump(mode='json'),
        content_digest(environment): environment.model_dump(mode='json'),
        content_digest(request): request.model_dump(mode='json')}
    for digest in request.definition_digests:
        if digest not in definitions:
            definitions[digest] = repo.get('recipe_runtime', digest)
    fixtures = [*extension.independent_fixtures, *extension.transformed_fixtures]
    # Bound unknown reference output using its reviewed output-schema ceiling.
    examples = []
    for fixture in fixtures:
        for output in [fixture.grader_output, {'document_b64': 'x' * 200000}, *extension.fault_outputs]:
            examples.append({'input': fixture.input, 'output': output, 'expected': fixture.output})
    max_batches = len(bounded_batches(examples))
    operations = 1 + max_batches
    original = AssessmentAuthorization.model_validate(repo.get('authorization', 'onboarding'))
    amendment = AssessmentScopeAmendment(authorization_id='onboarding',
        authorization_digest=content_digest(original), subject_digests=[content_digest(subject)],
        recipe_digests=[content_digest(recipe)], environment_digests=[content_digest(environment)],
        reviewed_digests=list(definitions))
    page_count = router.store._connection.execute('PRAGMA page_count').fetchone()[0]
    page_size = router.store._connection.execute('PRAGMA page_size').fetchone()[0]
    database_bytes = page_count * page_size
    review = {'authority': 'September25/27 standing finite scope/test-definition delegation; user resumed after macOS available-capacity correction.',
        'purpose': 'Protected literal reference/grader validation only; no generation, holdout, model, qualification or admission.',
        'source_digest': verification_source_digest(ROOT),
        'runner_sha256': hashlib.sha256((OUT / 'run.py').read_bytes()).hexdigest(),
        'request': request.model_dump(mode='json'), 'definitions': definitions,
        'amendment': amendment.model_dump(mode='json'), 'maximum_operations': operations,
        'maximum_grader_batches': max_batches, 'maximum_reserved_seconds': operations * 35,
        'maximum_model_turns': 0, 'maximum_cash_usd': 0,
        'literal_count': len(fixtures), 'expected_positive_count': 2 * len(fixtures),
        'expected_negative_count': len(fixtures) * len(extension.fault_outputs),
        'measured_fixture_request_upper_bytes': len(json.dumps({'examples': examples}).encode()),
        'measured_canonical_database_bytes': database_bytes,
        'conservative_storage_allowance_bytes': 2 * operations * database_bytes + 100_000_000,
        'storage_basis': 'Measured full current canonical database bounds each scoped authority copy; extra factor covers journals and result records. Not extrapolated from a small preparation snapshot.',
        'effective_grant': repo.current_grant('onboarding').limits.model_dump(mode='json'),
        'approval_committed': False}
    (OUT / 'review.json').write_text(json.dumps(review, indent=2) + '\n')
    print(json.dumps({key: review[key] for key in ['source_digest', 'maximum_operations',
        'maximum_reserved_seconds', 'conservative_storage_allowance_bytes']}))
    print(json.dumps({'request_id': request.plan_id,
        'review_sha256': hashlib.sha256((OUT / 'review.json').read_bytes()).hexdigest()}))
finally:
    router.store.close()
