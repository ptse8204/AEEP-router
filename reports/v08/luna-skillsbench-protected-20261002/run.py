"""Execute one reviewed literal-only protected check; canonical operations forbid replay."""
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path

from aeep.assessment.extensions import bounded_batches, grader_results, invoke
from aeep.assessment.models import AssessmentScopeAmendment, RecipeDefinition, RecipeMaterializationRequest, content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.registry import validate_json
from aeep.router import Router

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent


async def main():
    review_path = OUT / 'review.json'
    assert len(sys.argv) == 2 and hashlib.sha256(review_path.read_bytes()).hexdigest() == sys.argv[1]
    review = json.loads(review_path.read_text())
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == review['runner_sha256']
    assert verification_source_digest(ROOT) == review['source_digest']
    # Exclusive marker retains interruptions and refuses blind replay.
    with (OUT / 'started.json').open('x') as stream:
        json.dump({'review_sha256': sys.argv[1], 'replay_allowed': False}, stream)
    router = Router.from_manifest(ROOT / '.aeep/live-review-v3/aeep.json')
    service = AssessmentService(router, ROOT / '.aeep/live-review-v3/.aeep/assessments')
    repo = service.repository
    request = RecipeMaterializationRequest.model_validate(review['request'])
    recipe = RecipeDefinition.model_validate(repo.get('recipe', request.recipe_digest))
    extension = recipe.extension
    assert extension is not None
    result = {'source_digest': review['source_digest'], 'request_id': request.plan_id,
        'request_digest': content_digest(request), 'operation_ids': [], 'passed': False,
        'model_turns': 0, 'qualifying_materialization': False, 'admission': False,
        'official_reproduction': False, 'replay_allowed': False}
    started = time.perf_counter()
    try:
        repo.approve_bundle(AssessmentScopeAmendment.model_validate(review['amendment']), review['definitions'])
        repo.authorize(request)
        fixtures = [*extension.independent_fixtures, *extension.transformed_fixtures]
        async with asyncio.timeout(review['maximum_reserved_seconds']):
            operation = request.plan_id + '-literal-reference'
            result['operation_ids'].append(operation)
            reference, _ = await invoke(service, request, extension.reference,
                {'inputs': [f.input for f in fixtures]}, stage='grader_reference', operation_id=operation)
            assert isinstance(reference, dict) and set(reference) == {'outputs'}
            assert isinstance(reference['outputs'], list) and len(reference['outputs']) == len(fixtures)
            examples, expected = [], []
            for fixture, output in zip(fixtures, reference['outputs'], strict=True):
                validate_json(output, recipe.output_schema, label='protected reference output')
                for value, correct in [(fixture.grader_output, True), (output, True),
                                       *[(fault, False) for fault in extension.fault_outputs]]:
                    examples.append({'input': fixture.input, 'output': value, 'expected': fixture.output})
                    expected.append(correct)
            batches = bounded_batches(examples)
            assert len(batches) <= review['maximum_grader_batches']
            observed, codes = [], []
            for index, batch in enumerate(batches):
                operation = request.plan_id + '-literal-grader-' + str(index)
                result['operation_ids'].append(operation)
                reply, _ = await invoke(service, request, extension.grader, {'examples': batch},
                    stage='grader_probe', operation_id=operation)
                checks = grader_results(reply, extension, len(batch))
                observed.extend(check.valid for check in checks)
                codes.extend(check.detail for check in checks)
            result.update(expected_decisions=expected, observed_decisions=observed,
                          failure_codes=codes, passed=observed == expected)
    except BaseException as exc:
        result['error_type'] = type(exc).__name__
    finally:
        result['elapsed_seconds'] = time.perf_counter() - started
        result['source_unchanged'] = verification_source_digest(ROOT) == review['source_digest']
        cursor = router.store._connection.execute('SELECT * FROM assessment_grants WHERE id=?', ('onboarding',))
        result['grant_after'] = dict(zip([col[0] for col in cursor.description], cursor.fetchone()))
        result['operations'] = []
        for operation in result['operation_ids']:
            cursor = router.store._connection.execute('SELECT * FROM assessment_operations WHERE id=?', (operation,))
            row = cursor.fetchone()
            result['operations'].append(dict(zip([col[0] for col in cursor.description], row)) if row else {'id': operation, 'state': 'not_reserved'})
        (OUT / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        await router.close()
    print(json.dumps(result))
    return 0 if result['passed'] and result['source_unchanged'] else 1


raise SystemExit(asyncio.run(main()))
