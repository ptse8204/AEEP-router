"""Execute one reviewed semantic-fault observation; never replay positive results."""
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


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_fault_rejection(grade, raw):
    # Any documented nonzero pytest status is a rejected faulty source, never success.
    assert not grade.valid and grade.detail in ('test_failure', 'missing_test')
    assert type(raw['exit_code']) is int and raw['exit_code'] in (1, 2, 3, 4, 5)


async def main():
    began = time.perf_counter()
    assert len(sys.argv) == 2 and sha(HERE / 'operation-review.json') == sys.argv[1]
    review = json.loads((HERE / 'operation-review.json').read_text())
    approval = json.loads((HERE / 'operator-approval.json').read_text())
    assert approval['approved'] and approval['review_sha256'] == sys.argv[1]
    assert sha(Path(__file__)) == review['runner_sha256']
    parent_path = ROOT / review['parent_review']
    assert sha(parent_path) == review['parent_review_sha256']
    parent = json.loads(parent_path.read_text())
    documents = {key:item for key,item in parent['documents'].items() if item['kind'] in ('recipe','environment','recipe_runtime')}
    documents.update(review['new_documents'])
    documents = {key:item for key,item in documents.items() if key in review['reviewed_document_digests']}
    assert set(documents) == set(review['reviewed_document_digests'])
    effective = {**parent, **review}
    effective['documents'] = documents
    effective['definitions'] = {key:item['document'] for key,item in documents.items()}
    review = effective
    prior = ROOT / review['prior_observation_audit']
    assert sha(prior) == review['prior_observation_audit_sha256']
    assert json.loads(prior.read_text())['completed_observations_acceptable']
    assert verification_source_digest(ROOT) == review['source_digest']
    assert json.loads((ROOT / 'reports/toolkit-v2/c13/repository-suite-integration-20261022/validation-v2/source-stability.json').read_text())['all_passed']
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
    assert review['request']['environment_digest'] == parent['request']['environment_digest']
    with (HERE / 'execution-started.json').open('x') as stream:
        json.dump({'review_sha256': sys.argv[1], 'automatic_retry': False}, stream)
    router = Router.from_manifest(BASE / 'aeep.json')
    service = AssessmentService(router, BASE / '.aeep/assessments')
    repo = service.repository
    request = RecipeMaterializationRequest.model_validate(review['request'])
    recipe = RecipeDefinition.model_validate(review['recipe'])
    calls, child_seconds = 0, []
    results, receipts = [], []
    validation_started = validation_cpu = None
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
        repo.reserve(request, request.plan_id + '-analysis', AssessmentLimits(max_operations=1, max_elapsed_seconds=120), stage='repository_suite_validation')
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

        for case in cases:
            if case.input.task_id not in review['active_case_ids']:
                continue
            for label, artifact in [('reference', json.loads(case.reference.read())),
                ('unchanged', patch_artifact(RepositoryPatch(base_sha256=content_digest(case.input), files={}))),
                ('semantic_fault', case.fault_outputs[0])]:
                if label not in review['active_variants']:
                    continue
                staged = next(item for item in review['variants'] if item['case'] == case.input.task_id and item['variant'] == label)
                raw = None
                async def probe(payload):
                    nonlocal raw
                    raw = await observe(case.input.task_id + '-' + label, payload, staged['sha256'])
                    # Opt-in fixed public-test reply retention precedes protocol validation.
                    (HERE / 'raw-observation.json').write_text(json.dumps({'name':case.input.task_id+'-'+label, 'output':raw}, indent=2)+'\n')
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
                    audit_fault_rejection(grade, raw)
                    assert grade.detail == 'test_failure' and raw['exit_code'] == 1
                    assert set(required) <= raw['statuses'].keys()
                    assert all(raw['statuses'][key] in ('PASSED', 'FAILED') for key in required)
                    assert any(raw['statuses'][key] == 'FAILED' for key in case.truth.pass_to_pass)
                    assert all(raw['statuses'][key] == 'PASSED' for key in case.truth.fail_to_pass)
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
        (HERE / 'operation-ledger.json').write_text(ledger.model_dump_json(indent=2) + '\n')
        summary['ledger_operations'] = len(ledger.operations)
        summary['elapsed_complete'] = all(item.elapsed_seconds is not None for item in ledger.operations)
        summary['contained_calls_started'] = calls
        summary['containers_removed'] = len(receipts) == calls and all(item['container_removed'] for item in receipts)
        summary['source_unchanged'] = verification_source_digest(ROOT) == review['source_digest']
        summary['grant_after'] = list(router.store._connection.execute(
            "SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
        summary['fresh_canary_created'] = False
        summary['elapsed_seconds'] = time.perf_counter() - began
        await router.close()
        (HERE / 'execution-result.json').write_text(json.dumps(summary, indent=2) + '\n')


if __name__ == '__main__':
    asyncio.run(main())
