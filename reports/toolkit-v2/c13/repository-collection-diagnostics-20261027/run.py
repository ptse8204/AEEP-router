"""One exact operator diagnostic; existing contained dispatch and durable accounting."""
import asyncio
import hashlib
import json
import math
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time

from aeep.assessment.containment import container_name
from aeep.assessment.extensions import invoke
from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import (AssessmentEnvironment, AssessmentLimits, AssessmentScopeAmendment,
    AssessmentSubject, RecipeDefinition, RecipeMaterializationRequest, RecipeRuntimeBinding, content_digest)
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.attempts import ExecutionAttempt, ExecutionAttemptState
from aeep.models import ExecutionReceipt
from aeep.router import Router
from sanitize import validate_reply
import review_budget

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')
DOCKER = ['/usr/local/bin/docker', '--host', 'unix:///Users/edwintse/.docker/run/docker.sock']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    with (HERE / name).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def validate_review(review):
    assert verification_source_digest(ROOT) == review['source_digest']
    assert runtime_dependencies() == review['runtime_dependencies']
    assert review['maximum_contained_calls'] == 4 and review['maximum_operations'] == 6
    assert review['maximum_reserved_seconds'] == 290 and review['maximum_model_turns'] == review['cash_usd'] == 0
    assert review['automatic_retry'] is False
    for name, expected in review['assets'].items():
        path = Path(name)
        assert path.is_file() and not path.is_symlink() and sha(path) == expected
    models = {'subject': AssessmentSubject, 'recipe': RecipeDefinition, 'environment': AssessmentEnvironment,
              'recipe_runtime': RecipeRuntimeBinding, 'recipe_materialization_request': RecipeMaterializationRequest}
    for digest, item in review['documents'].items():
        assert content_digest(models[item['kind']].model_validate(item['document'])) == digest
    recipe = RecipeDefinition.model_validate(review['recipe'])
    assert recipe.recipe_id.startswith('operator-collection-diagnostic-')
    assert content_digest(recipe) in review['documents']
    assert recipe.extension.grader.id == 'repository.collection.diagnose'
    assert recipe.extension.grader.config['argv'][-1] == (HERE / 'diagnostic-program.py').read_text()
    assert recipe.dependencies['diagnostic_program'] == sha(HERE / 'diagnostic-program.py')
    assert len(review['groups']) == 2 and sum(len(g['diagnostics']) for g in review['groups']) == 4
    assert len({g['image_id'] for g in review['groups']}) == 2
    for group in review['groups']:
        request = RecipeMaterializationRequest.model_validate(group['request'])
        assert request.recipe_digest == request.mapping_digest == content_digest(recipe)
        assert request.subject_digest == review['subject_digest'] and request.authorization_id == 'onboarding'
        assert request.runtime_dependencies == review['runtime_dependencies']
        environment = AssessmentEnvironment.model_validate(review['documents'][request.environment_digest]['document'])
        assert environment.container_image == group['image_id'] and not environment.network and not environment.read_only_roots
        assert request.environment_digest in request.definition_digests
        assert group['probes'] == []
        for call in [*group['probes'], *group['diagnostics']]:
            payload = json.loads((ROOT / call['payload_file']).read_text())
            assert sha(ROOT / call['payload_file']) == call['payload_sha256']
            if call['kind'] == 'diagnostic':
                original = json.loads((ROOT / call['original_payload_file']).read_text())
                assert {k: v for k, v in payload.items() if k != 'reviewed_identifiers'} == original
                assert call['image_id'] == group['image_id']
                assert call['prior_failed_result_sha256'] == sha(ROOT / call['prior_failed_result'])
    return recipe


def store_review(repo, review):
    models = {'subject': AssessmentSubject, 'recipe': RecipeDefinition, 'environment': AssessmentEnvironment,
              'recipe_runtime': RecipeRuntimeBinding, 'recipe_materialization_request': RecipeMaterializationRequest}
    for digest, item in review['documents'].items():
        assert repo.put(item['kind'], item['id'], models[item['kind']].model_validate(item['document'])) == digest
    repo.approve_bundle(AssessmentScopeAmendment.model_validate(review['amendment']),
                        {k: v['document'] for k, v in review['documents'].items()})


async def main():
    began = time.perf_counter()
    assert len(sys.argv) == 2 and sha(HERE / 'operation-review.json') == sys.argv[1]
    review = json.loads((HERE / 'operation-review.json').read_text())
    approval = json.loads((HERE / 'operator-approval.json').read_text())
    assert approval['approved'] and approval['review_sha256'] == sys.argv[1]
    recipe = validate_review(review)
    assert not (HERE / 'execution-started.json').exists()
    assert shutil.disk_usage(ROOT).free > 50 * 1024 ** 3
    for group in review['groups']:
        assert subprocess.check_output([*DOCKER, 'image', 'inspect', '--format', '{{.Id}}', group['image_tag']], text=True, timeout=20).strip() == group['image_id']
    router = Router.from_manifest(BASE / 'aeep.json')
    service = AssessmentService(router, BASE / '.aeep/assessments')
    repo = service.repository
    requests = [RecipeMaterializationRequest.model_validate(g['request']) for g in review['groups']]
    before = list(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
    assert content_digest(repo.get('authorization', 'onboarding')) == review['authorization_digest']
    grant = repo.current_grant('onboarding')
    assert before[0] + review['maximum_operations'] <= grant.limits.max_operations
    assert before[2] + review['maximum_reserved_seconds'] <= grant.limits.max_elapsed_seconds
    original_reserve = review_budget.install(repo, router.store._connection, before, review)
    save('execution-started.json', {'review_sha256': sys.argv[1], 'grant_before': before, 'automatic_retry': False})
    result = {'completed': False, 'review_sha256': sys.argv[1], 'grade_or_qualification': False, 'model_turns': 0,
              'grant_before': before, 'receipts': [], 'observations': []}
    child_times = []
    analysis_started = None
    call_count = 0

    def check_live():
        validate_review(review)
        assert shutil.disk_usage(ROOT).free > 50 * 1024 ** 3
        for request in requests:
            repo.authorize(request)

    def terminal_evidence(request, operation, spec):
        database = service.directory / request.plan_id / 'recipe-operations' / (operation + '.sqlite3')
        with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as connection:
            rows = connection.execute('SELECT payload_json FROM receipts').fetchall()
            assert len(rows) == 1
            receipt = ExecutionReceipt.model_validate_json(rows[0][0])
            attempt = ExecutionAttempt.model_validate_json(connection.execute('SELECT payload_json FROM execution_attempts WHERE attempt_id=?', (receipt.metadata['attempt_id'],)).fetchone()[0])
            assert attempt.state is ExecutionAttemptState.COMPLETED
            assert receipt.receipt_id in attempt.terminal_receipt_ids
            assert receipt.executor_id == attempt.executor_id == spec.id
            assert receipt.executor_fingerprint == attempt.executor_fingerprint
        assert content_digest(repo.get('recipe_receipt', receipt.receipt_id)) == content_digest(receipt)
        charged = next(o for o in repo.operation_ledger(request.plan_id).operations if o.operation_id == operation)
        assert charged.elapsed_seconds is not None and math.isfinite(charged.elapsed_seconds) and charged.elapsed_seconds >= 0
        owned = container_name(attempt.attempt_id)
        assert not subprocess.check_output([*DOCKER, 'ps', '-a', '--filter', 'name=^/' + owned + '$', '--format', '{{.ID}}'], text=True, timeout=20).strip()
        return {'operation_id': operation, 'receipt_id': receipt.receipt_id, 'receipt_ref': content_digest(receipt),
                'attempt_id': attempt.attempt_id, 'container_name': owned, 'owned_container_absent': True}

    try:
        store_review(repo, review)
        repo.reserve(requests[0], requests[0].plan_id + '-setup', AssessmentLimits(max_operations=1, max_elapsed_seconds=30), stage='collection_diagnostic_setup')
        repo.finish_operation(requests[0].plan_id + '-setup', elapsed_seconds=time.perf_counter() - began)
        repo.reserve(requests[0], requests[0].plan_id + '-analysis', AssessmentLimits(max_operations=1, max_elapsed_seconds=120), stage='collection_diagnostic_analysis')
        analysis_started = time.perf_counter()
        for group, request in zip(review['groups'], requests, strict=True):
            for call in group['diagnostics']:
                check_live()
                assert call_count < review['maximum_contained_calls']
                call_count += 1
                payload = json.loads((ROOT / call['payload_file']).read_text())
                spec = recipe.extension.grader
                operation = request.plan_id + '-call-' + str(call_count)
                # Any transport/authority/accounting/lifecycle uncertainty stops the entire bundle.
                # Ordinary diagnostic pytest exit2 is data, not a correctness grade.
                output, _ = await invoke(service, request, spec, payload, stage='operator_collection_diagnostic', operation_id=operation, elapsed_times=child_times)
                record = terminal_evidence(request, operation, spec)
                validate_reply(output, payload)
                filename = 'observation-' + str(call_count) + '.json'
                save(filename, {'name': call['name'], 'kind': call['kind'], 'image_id': group['image_id'], 'output': output})
                result['observations'].append({'name': call['name'], 'file': filename, 'sha256': sha(HERE / filename)})
                result['receipts'].append(record)
                check_live()
        result['completed'] = True
    except BaseException as exc:
        result['error_type'] = type(exc).__name__
    finally:
        try:
            if analysis_started is not None:
                repo.finish_operation(requests[0].plan_id + '-analysis', elapsed_seconds=max(0, time.perf_counter() - analysis_started - sum(child_times)))
            result['new_host_canaries_created'] = 0
            ledgers = [repo.operation_ledger(r.plan_id).model_dump(mode='json') for r in requests]
            save('operation-ledgers.json', ledgers)
            after = list(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
            result.update(grant_after=after, contained_calls=call_count, source_unchanged=verification_source_digest(ROOT) == review['source_digest'])
            if not result['source_unchanged']:
                result['completed'] = False
            save('execution-result.json', result)
        finally:
            repo.reserve = original_reserve
            await router.close()
    print(json.dumps({k: v for k, v in result.items() if k not in ('receipts', 'observations')}, allow_nan=False))
    if not result['completed']:
        raise SystemExit(1)


if __name__ == '__main__':
    asyncio.run(main())
