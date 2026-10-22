"""One approved offline grader check through canonical reservations and containers."""
import asyncio
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from aeep.assessment.extensions import invoke
from aeep.assessment.containment import container_name
from aeep.attempts import ExecutionAttempt, ExecutionAttemptState
from aeep.assessment.models import AssessmentEnvironment, AssessmentLimits, AssessmentScopeAmendment, AssessmentSubject, RecipeDefinition, RecipeMaterializationRequest, RecipeRuntimeBinding, content_digest
from aeep.assessment.repository_tasks import RepositoryCase, grade_repository_output
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.router import Router
from aeep.models import ExecutionReceipt, ResourceVector

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_attempt(connection, receipt, expected_executor):
    """Minimized receipts bind canonical attempts; container names derive from those IDs."""
    identity = receipt.metadata.get('attempt_id')
    assert isinstance(identity, str) and identity
    row = connection.execute('SELECT payload_json FROM execution_attempts WHERE attempt_id=?', (identity,)).fetchone()
    assert row is not None
    attempt = ExecutionAttempt.model_validate_json(row[0])
    assert attempt.state is ExecutionAttemptState.COMPLETED
    assert receipt.receipt_id in attempt.terminal_receipt_ids
    assert receipt.executor_id == attempt.executor_id == expected_executor
    assert receipt.executor_fingerprint and receipt.executor_fingerprint == attempt.executor_fingerprint
    return container_name(attempt.attempt_id)


async def main():
    began = time.perf_counter()
    assert len(sys.argv) == 2
    review = json.loads((HERE / 'grader-operation-review.json').read_text())
    assert sha(HERE / 'grader-operation-review.json') == sys.argv[1]
    approval = json.loads((HERE / 'grader-operator-approval.json').read_text())
    assert approval['approved'] and approval['review_sha256'] == sys.argv[1]
    assert sha(Path(__file__)) == review['runner_sha256']
    assert verification_source_digest(ROOT) == review['source_digest']
    assert json.loads((HERE / 'validation-v2/source-stability.json').read_text())['all_passed']
    for name, expected in review['inputs'].items():
        assert sha(ROOT / name) == expected
    assert shutil.disk_usage(ROOT).free > 51 * 1024**3
    image = subprocess.check_output([review['docker'], '--host', review['socket'], 'image', 'inspect',
        review['image'], '--format', '{{.Id}}'], timeout=30).decode().strip()
    assert image == review['image']
    with (HERE / 'grader-execution-started.json').open('x') as marker:
        json.dump({'review_sha256': sys.argv[1], 'automatic_retry': False}, marker)
    router = Router.from_manifest(BASE / 'aeep.json')
    service = AssessmentService(router, BASE / '.aeep/assessments')
    repo = service.repository
    request = RecipeMaterializationRequest.model_validate(review['request'])
    recipe = RecipeDefinition.model_validate(review['recipe'])
    calls = 0
    validation_started = None
    validation_cpu = None
    program_seconds = []
    canary_created = False
    results = []
    receipts = []
    summary = {'passed': False, 'source_digest': review['source_digest'], 'model_turns': 0,
        'cash_authorized': 0, 'qualification': False, 'admission': False, 'results': results}
    canary = ROOT / review['host_canary']
    try:
        before = list(router.store._connection.execute(
            "SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
        summary['grant_before'] = before
        assert content_digest(repo.get('authorization', 'onboarding')) == review['authorization_digest']
        grant = repo.current_grant('onboarding')
        assert before[0] + 25 <= grant.limits.max_operations
        assert before[2] + 1240 <= grant.limits.max_elapsed_seconds
        definitions = review['definitions']
        models = {'subject': AssessmentSubject, 'recipe': RecipeDefinition, 'environment': AssessmentEnvironment,
            'recipe_runtime': RecipeRuntimeBinding, 'recipe_materialization_request': RecipeMaterializationRequest}
        for digest, item in review['documents'].items():
            document = models[item['kind']].model_validate(item['document'])
            assert repo.put(item['kind'], item['id'], document) == digest
        amendment = AssessmentScopeAmendment.model_validate(review['amendment'])
        repo.approve_bundle(amendment, definitions)
        repo.reserve(request, request.plan_id + '-setup', AssessmentLimits(max_operations=1, max_elapsed_seconds=30), stage='grader_check_setup')
        repo.finish_operation(request.plan_id + '-setup', elapsed_seconds=time.perf_counter() - began)
        canary.parent.mkdir(parents=True, exist_ok=True)
        with canary.open('x') as handle:
            handle.write(review['host_canary_text'])
        canary_created = True
        repo.reserve(request, request.plan_id + '-validation', AssessmentLimits(max_operations=1, max_elapsed_seconds=400), stage='repository_grader_validation')
        validation_started, validation_cpu = time.perf_counter(), time.process_time()
        async def observe(payload):
            nonlocal calls
            assert verification_source_digest(ROOT) == review['source_digest']
            assert calls < review['maximum_contained_calls']
            calls += 1
            operation = request.plan_id + '-probe-' + str(calls)
            reply, elapsed = await invoke(service, request, recipe.extension.grader, payload,
                stage='repository_grader_check', operation_id=operation, elapsed_times=program_seconds)
            database = service.directory / request.plan_id / 'recipe-operations' / (operation + '.sqlite3')
            with sqlite3.connect('file:' + str(database) + '?mode=ro', uri=True) as connection:
                rows = connection.execute('SELECT payload_json FROM receipts').fetchall()
            assert len(rows) == 1
            receipt = ExecutionReceipt.model_validate_json(rows[0][0])
            with sqlite3.connect('file:' + str(database) + '?mode=ro', uri=True) as connection:
                name = audit_attempt(connection, receipt, recipe.extension.grader.id)
            assert content_digest(AssessmentEnvironment.model_validate(repo.get('environment', request.environment_digest))) == request.environment_digest
            remaining = subprocess.check_output([review['docker'], '--host', review['socket'], 'ps', '-a',
                '--filter', 'name=^/' + name + '$', '--format', '{{.ID}}'], timeout=15).decode().strip()
            assert not remaining, 'Owned grader container cleanup is incomplete; stop new dispatch.'
            receipts.append({'operation_id': operation, 'receipt_id': receipt.receipt_id,
                'receipt_ref': content_digest(receipt), 'container_name': name, 'container_removed': True,
                'environment_digest': request.environment_digest, 'image_from_reviewed_environment': review['image']})
            return reply
        for boundary in review['boundary_probes']:
            reply = await observe(boundary['payload'])
            assert reply == boundary['expected'], boundary['name']
            results.append({'name': boundary['name'], 'passed': True})
        cases = [RepositoryCase.model_validate(value) for value in json.loads((ROOT / review['cases']).read_text())]
        for case in cases:
            value, truth = case.input.model_dump(mode='json'), case.truth.model_dump(mode='json')
            variants = [('reference', case.reference_patch.model_dump(mode='json'), True),
                ('unchanged_snapshot', {'base_sha256': content_digest(value), 'files': {}}, case.input.family == 'adjacent-no-change'),
                ('invalid_scope', {'base_sha256': content_digest(value), 'files': {'../escape.py': 'raise SystemExit'}}, False)]
            variants.extend(('semantic_fault_' + str(index), patch.model_dump(mode='json'), False) for index, patch in enumerate(case.fault_patches))
            for label, output, expected in variants:
                result = await grade_repository_output(value, truth, output, observe)
                assert result.valid is expected
                if label.startswith('semantic_fault_'):
                    assert result.detail == 'behavior_mismatch'
                results.append({'case': case.input.task_id, 'variant': label, 'passed': True,
                    'valid': result.valid, 'failure_code': result.detail or None})
        assert calls == review['maximum_contained_calls']
        summary['passed'] = True
    except BaseException as exc:
        summary['error_type'] = type(exc).__name__
        raise
    finally:
        summary['contained_calls_started'] = calls
        summary['receipts'] = receipts
        summary['containers_removed'] = len(receipts) == calls and all(item['container_removed'] for item in receipts)
        summary['source_unchanged'] = verification_source_digest(ROOT) == review['source_digest']
        summary['grant_after'] = list(router.store._connection.execute(
            "SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
        if validation_started is not None:
            repo.finish_operation(request.plan_id + '-validation',
                elapsed_seconds=max(0, time.perf_counter() - validation_started - sum(program_seconds)),
                resources=ResourceVector(cpu_ms=max(0, time.process_time() - validation_cpu) * 1000))
        summary['grant_after'] = list(router.store._connection.execute(
            "SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
        ledger = repo.operation_ledger(request.plan_id)
        summary['ledger_operations'] = len(ledger.operations)
        summary['elapsed_complete'] = all(item.elapsed_seconds is not None for item in ledger.operations)
        (HERE / 'grader-operation-ledger.json').write_text(ledger.model_dump_json(indent=2) + '\n')
        if canary_created and canary.is_file() and not canary.is_symlink() and canary.read_text() == review['host_canary_text']:
            canary.unlink()
        summary['host_canary_removed'] = not canary.exists()
        summary['elapsed_seconds'] = time.perf_counter() - began
        await router.close()
        (HERE / 'grader-execution-result.json').write_text(json.dumps(summary, indent=2) + '\n')


if __name__ == '__main__':
    asyncio.run(main())
