"""Execute one exact approved v5 conformance attempt; no candidate/model execution."""
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time

from aeep.assessment.containment import container_name
from aeep.assessment.extensions import invoke
from aeep.assessment.models import (AssessmentEnvironment, AssessmentLimits, AssessmentScopeAmendment,
    AssessmentSubject, RecipeDefinition, RecipeMaterializationRequest, RecipeRuntimeBinding, content_digest)
from aeep.assessment.repository_suites import RepositorySuiteCase, grade_suite_output, patch_artifact
from aeep.assessment.repository_tasks import RepositoryPatch
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.attempts import ExecutionAttempt, ExecutionAttemptState
from aeep.models import ExecutionReceipt, ResourceVector
from aeep.router import Router

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')
CANARY = 'AEEP v5 grader host-only synthetic canary.\n'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def main():
    began = time.perf_counter()
    assert len(sys.argv) == 2 and sha(HERE / 'grader-operation-review.json') == sys.argv[1]
    review = json.loads((HERE / 'grader-operation-review.json').read_text())
    approval = json.loads((HERE / 'grader-operator-approval.json').read_text())
    assert approval['approved'] and approval['review_sha256'] == sys.argv[1]
    assert sha(Path(__file__)) == review['runner_sha256']
    assert verification_source_digest(ROOT) == review['source_digest']
    assert json.loads((HERE / 'validation-v2/source-stability.json').read_text())['all_passed']
    assert shutil.disk_usage(ROOT).free > 50 * 1024**3
    image = subprocess.check_output([review['docker'], '--host', review['socket'], 'image',
        'inspect', review['image'], '--format', '{{.Id}}'], timeout=20).decode().strip()
    assert image == review['image']
    def verify_assets():
        for name, expected in review['assets'].items():
            path = Path(name)
            assert not path.is_symlink() and sha(path) == expected
    verify_assets()
    cases = [RepositorySuiteCase.model_validate(value) for value in json.loads((ROOT / review['cases_file']).read_text())]
    canary = ROOT / review['host_canary']
    assert not canary.exists() and not canary.is_symlink()
    with (HERE / 'grader-execution-started.json').open('x') as stream:
        json.dump({'review_sha256': sys.argv[1], 'automatic_retry': False}, stream)
    router = Router.from_manifest(BASE / 'aeep.json')
    service = AssessmentService(router, BASE / '.aeep/assessments')
    repo = service.repository
    request = RecipeMaterializationRequest.model_validate(review['request'])
    recipe = RecipeDefinition.model_validate(review['recipe'])
    calls, child_seconds = 0, []
    results, receipts = [], []
    validation_started = validation_cpu = None
    created_canary = False
    summary = {'passed': False, 'review_sha256': sys.argv[1], 'source_digest': review['source_digest'],
        'model_turns': 0, 'qualification': False, 'admission': False, 'comparative_usefulness': False,
        'results': results, 'receipts': receipts}
    try:
        summary['grant_before'] = list(router.store._connection.execute(
            "SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
        assert content_digest(repo.get('authorization', 'onboarding')) == review['authorization_digest']
        grant = repo.current_grant('onboarding')
        assert summary['grant_before'][0] + review['maximum_operations'] <= grant.limits.max_operations
        assert summary['grant_before'][2] + review['maximum_reserved_seconds'] <= grant.limits.max_elapsed_seconds
        models = {'subject': AssessmentSubject, 'recipe': RecipeDefinition, 'environment': AssessmentEnvironment,
            'recipe_runtime': RecipeRuntimeBinding, 'recipe_materialization_request': RecipeMaterializationRequest}
        for digest, item in review['documents'].items():
            document = models[item['kind']].model_validate(item['document'])
            assert repo.put(item['kind'], item['id'], document) == digest
        repo.approve_bundle(AssessmentScopeAmendment.model_validate(review['amendment']), review['definitions'])
        repo.reserve(request, request.plan_id + '-setup', AssessmentLimits(max_operations=1, max_elapsed_seconds=30), stage='repository_suite_setup')
        repo.finish_operation(request.plan_id + '-setup', elapsed_seconds=time.perf_counter() - began)
        with canary.open('x') as stream:
            stream.write(CANARY)
        created_canary = True
        repo.reserve(request, request.plan_id + '-analysis', AssessmentLimits(max_operations=1, max_elapsed_seconds=180), stage='repository_suite_validation')
        validation_started, validation_cpu = time.perf_counter(), time.process_time()

        async def observe(name, payload, expected_sha):
            nonlocal calls
            assert calls < review['maximum_contained_calls']
            assert verification_source_digest(ROOT) == review['source_digest']
            verify_assets()
            assert hashlib.sha256(json.dumps(payload, separators=(',', ':')).encode()).hexdigest() == expected_sha
            calls += 1
            operation = request.plan_id + '-call-' + str(calls)
            output, _ = await invoke(service, request, recipe.extension.grader, payload,
                stage='repository_suite_development', operation_id=operation, elapsed_times=child_seconds)
            database = service.directory / request.plan_id / 'recipe-operations' / (operation + '.sqlite3')
            with sqlite3.connect('file:' + str(database) + '?mode=ro', uri=True) as connection:
                rows = connection.execute('SELECT payload_json FROM receipts').fetchall()
                assert len(rows) == 1
                receipt = ExecutionReceipt.model_validate_json(rows[0][0])
                identity = receipt.metadata.get('attempt_id')
                assert isinstance(identity, str) and identity
                row = connection.execute('SELECT payload_json FROM execution_attempts WHERE attempt_id=?', (identity,)).fetchone()
                assert row is not None
                attempt = ExecutionAttempt.model_validate_json(row[0])
                assert attempt.state is ExecutionAttemptState.COMPLETED
                assert receipt.receipt_id in attempt.terminal_receipt_ids
                assert receipt.executor_fingerprint == attempt.executor_fingerprint
            owned_name = container_name(identity)
            remaining = subprocess.check_output([review['docker'], '--host', review['socket'], 'ps', '-a',
                '--filter', 'name=^/' + owned_name + '$', '--format', '{{.ID}}'], timeout=15).decode().strip()
            assert not remaining, 'Owned container cleanup incomplete; stop dispatch.'
            receipts.append({'name': name, 'operation_id': operation, 'receipt_id': receipt.receipt_id,
                'receipt_ref': content_digest(receipt), 'container_name': owned_name,
                'container_removed': True, 'environment_digest': request.environment_digest})
            return output

        for item in review['probes']:
            payload = json.loads((ROOT / item['payload']).read_text())
            output = await observe(item['name'], payload, item['payload_sha256'])
            results.append({'name': item['name'], 'passed': False, 'observations': output})
            assert set(output) == {'exit_code','statuses','archive_sha256','python','pytest'}
            assert output['archive_sha256'] == item['archive_sha256']
            assert output['python'] == '3.13' and output['pytest'] == '8.3.5' and output['exit_code'] == 0
            assert output['statuses'] == {item['expected_node']: 'PASSED'}
            results[-1]['passed'] = True
        for case in cases:
            for label, artifact in [('reference', json.loads(case.reference.read())),
                ('unchanged', patch_artifact(RepositoryPatch(base_sha256=content_digest(case.input), files={}))),
                ('semantic_fault', case.fault_outputs[0])]:
                staged = next(item for item in review['variants'] if item['case'] == case.input.task_id and item['variant'] == label)
                raw = None
                async def probe(payload):
                    nonlocal raw
                    raw = await observe(case.input.task_id + '-' + label, payload, staged['sha256'])
                    return raw
                grade = await grade_suite_output(case.input.model_dump(mode='json'), case.truth.model_dump(mode='json'), artifact, probe)
                results.append({'name':case.input.task_id+'-'+label,'passed':False,'grade':grade.model_dump(mode='json'), 'observations':raw})
                assert raw is not None
                required = case.truth.fail_to_pass + case.truth.pass_to_pass
                if label != 'semantic_fault':
                    assert set(required) <= raw['statuses'].keys(), 'Missing upstream test identity.'
                if label == 'reference':
                    assert grade.valid and raw['exit_code'] == 0 and all(raw['statuses'][key] == 'PASSED' for key in required)
                elif label == 'unchanged':
                    assert not grade.valid and grade.detail == 'test_failure' and raw['exit_code'] == 1
                    assert all(raw['statuses'][key] == 'FAILED' for key in case.truth.fail_to_pass)
                    assert all(raw['statuses'][key] == 'PASSED' for key in case.truth.pass_to_pass)
                else:
                    # The scoped import-time fault may prevent collection entirely.
                    assert not grade.valid and grade.detail in ('test_failure', 'missing_test') and raw['exit_code'] in (1, 2)
                results[-1]['passed'] = True
        assert calls == review['maximum_contained_calls']
        summary['passed'] = True
    except BaseException as exc:
        summary['error_type'] = type(exc).__name__
        raise
    finally:
        if validation_started is not None:
            repo.finish_operation(request.plan_id + '-analysis',
                elapsed_seconds=max(0, time.perf_counter() - validation_started - sum(child_seconds)),
                resources=ResourceVector(cpu_ms=max(0, time.process_time() - validation_cpu) * 1000))
        ledger = repo.operation_ledger(request.plan_id)
        (HERE / 'grader-operation-ledger.json').write_text(ledger.model_dump_json(indent=2) + '\n')
        summary['ledger_operations'] = len(ledger.operations)
        summary['elapsed_complete'] = all(item.elapsed_seconds is not None for item in ledger.operations)
        summary['contained_calls_started'] = calls
        summary['containers_removed'] = len(receipts) == calls and all(item['container_removed'] for item in receipts)
        summary['source_unchanged'] = verification_source_digest(ROOT) == review['source_digest']
        summary['grant_after'] = list(router.store._connection.execute(
            "SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
        if created_canary and canary.is_file() and not canary.is_symlink() and canary.read_text() == CANARY:
            canary.unlink()
        summary['canary_removed'] = not canary.exists()
        summary['elapsed_seconds'] = time.perf_counter() - began
        await router.close()
        (HERE / 'grader-execution-result.json').write_text(json.dumps(summary, indent=2) + '\n')


if __name__ == '__main__':
    asyncio.run(main())
