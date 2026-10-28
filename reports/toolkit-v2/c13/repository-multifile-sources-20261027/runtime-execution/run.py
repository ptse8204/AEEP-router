"""One finite pre-adoption reproduction batch. No campaign or model dispatch."""
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
from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import (AssessmentEnvironment, AssessmentLimits, AssessmentScopeAmendment,
    AssessmentSubject, RecipeDefinition, RecipeMaterializationRequest, RecipeRuntimeBinding, content_digest)
from aeep.assessment.repository_suites import RepositorySuiteCase, grade_suite_output
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.attempts import ExecutionAttempt, ExecutionAttemptState
from aeep.execution import ExecutionEvidence
from aeep.errors import ConfigurationError
from aeep.models import ExecutionReceipt, ResourceVector
from aeep.router import Router
from classify import discrepancies
from operator_output import evaluation

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class StopDispatch(RuntimeError):
    """A common binding, accounting or cleanup failure is never a case exclusion."""


class CaseExecutionFailure(RuntimeError):
    """An isolated observer failed after canonical completion and confirmed cleanup."""


async def main():
    began = time.perf_counter()
    assert len(sys.argv) == 2 and sha(HERE / 'operation-review.json') == sys.argv[1]
    review = json.loads((HERE / 'operation-review.json').read_text())
    approval = json.loads((HERE / 'operator-approval.json').read_text())
    assert approval['approved'] and approval['review_sha256'] == sys.argv[1]
    for relative, expected in review['driver_files'].items():
        assert sha(HERE / relative) == expected
    parent_path = ROOT / review['parent_review']
    assert sha(parent_path) == review['parent_review_sha256']
    parent = json.loads(parent_path.read_text())
    recipe = RecipeDefinition.model_validate(parent['recipe'])
    request = RecipeMaterializationRequest.model_validate(review['request'])
    documents = {key: item for key, item in parent['documents'].items()
                 if item['kind'] in ('recipe', 'environment', 'recipe_runtime')}
    documents.update(review['new_documents'])
    assert set(documents) == set(review['reviewed_document_digests'])
    assert request.environment_digest == parent['request']['environment_digest']
    assert runtime_dependencies() == request.runtime_dependencies
    assert verification_source_digest(ROOT) == review['source_digest']
    assert shutil.disk_usage(ROOT).free > 50 * 1024**3
    assert subprocess.check_output([parent['docker'], '--host', parent['socket'], 'image', 'inspect',
        parent['image'], '--format', '{{.Id}}'], timeout=20).decode().strip() == parent['image']

    def verify_assets():
        if verification_source_digest(ROOT) != review['source_digest']:
            raise StopDispatch('Common source binding changed')
        for name, expected in review['assets'].items():
            path = Path(name)
            if path.is_symlink() or not path.is_file() or sha(path) != expected:
                raise StopDispatch('Reviewed asset binding changed')
        if shutil.disk_usage(ROOT).free <= 50 * 1024**3:
            raise StopDispatch('Host storage reserve reached')

    verify_assets()
    cases = [RepositorySuiteCase.model_validate(item)
             for item in json.loads((ROOT / review['cases_file']).read_text())]
    variants = json.loads((ROOT / review['variants_file']).read_text())
    assert [case.input.task_id for case in cases] == review['active_case_ids']
    with (HERE / 'execution-started.json').open('x') as stream:
        json.dump({'review_sha256': sys.argv[1], 'automatic_retry': False}, stream)
    router = Router.from_manifest(BASE / 'aeep.json')
    service = AssessmentService(router, BASE / '.aeep/assessments')
    repo = service.repository
    child_seconds, results, receipts, observations = [], [], [], []
    calls = 0
    validation_started = validation_cpu = None
    summary = {'batch_completed': False, 'review_sha256': sys.argv[1], 'source_digest': review['source_digest'],
        'model_turns': 0, 'qualification': False, 'admission': False, 'comparative_usefulness': False,
        'results': results, 'receipts': receipts, 'observations': observations}
    try:
        summary['grant_before'] = list(router.store._connection.execute(
            "SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
        assert content_digest(repo.get('authorization', 'onboarding')) == review['authorization_digest']
        import importlib.util
        budget_spec = importlib.util.spec_from_file_location('exact_review_budget', HERE.parent / 'review-budget.py')
        budget = importlib.util.module_from_spec(budget_spec); budget_spec.loader.exec_module(budget)
        envelope = json.loads((HERE.parent / 'runtime-review.json').read_text())
        initial = json.loads((HERE.parent / 'build-result.json').read_text())['grant_before']
        budget.install(repo, router.store._connection, initial, envelope)
        grant = repo.current_grant('onboarding')
        assert summary['grant_before'][0] + review['maximum_operations'] <= grant.limits.max_operations
        assert summary['grant_before'][2] + review['maximum_reserved_seconds'] <= grant.limits.max_elapsed_seconds
        models = {'subject': AssessmentSubject, 'recipe': RecipeDefinition, 'environment': AssessmentEnvironment,
            'recipe_runtime': RecipeRuntimeBinding, 'recipe_materialization_request': RecipeMaterializationRequest}
        for digest, item in documents.items():
            value = models[item['kind']].model_validate(item['document'])
            assert repo.put(item['kind'], item['id'], value) == digest
        repo.approve_bundle(AssessmentScopeAmendment.model_validate(review['amendment']),
                            {digest: item['document'] for digest, item in documents.items()})
        repo.reserve(request, request.plan_id + '-setup', AssessmentLimits(max_operations=1, max_elapsed_seconds=30),
                     stage='repository_curated_reproduction_setup')
        repo.finish_operation(request.plan_id + '-setup', elapsed_seconds=time.perf_counter() - began)
        repo.reserve(request, request.plan_id + '-analysis', AssessmentLimits(max_operations=1, max_elapsed_seconds=120),
                     stage='repository_curated_reproduction_analysis')
        validation_started, validation_cpu = time.perf_counter(), time.process_time()

        async def observe(name, payload, expected_sha):
            nonlocal calls
            verify_assets()
            repo.authorize(request)
            if calls >= review['maximum_contained_calls']:
                raise StopDispatch('Reviewed call ceiling reached')
            if hashlib.sha256(json.dumps(payload, separators=(',', ':')).encode()).hexdigest() != expected_sha:
                raise StopDispatch('Staged payload changed')
            calls += 1
            operation = request.plan_id + '-call-' + str(calls)
            output, execution_error = None, None
            try:
                output, _ = await invoke(service, request, recipe.extension.grader, payload,
                    stage='repository_curated_reproduction', operation_id=operation, elapsed_times=child_seconds)
            except ConfigurationError as exc:
                execution_error = type(exc).__name__
            # Keep the bounded public-test reply before any grader protocol validation.
            raw_path = HERE / ('raw-observation-' + str(calls) + '.json')
            with raw_path.open('x') as stream:
                json.dump({'name': name, 'operation_id': operation, 'output': output,
                           'execution_error_type': execution_error}, stream, indent=2)
                stream.write('\n')
            observations.append({'name': name, 'operation_id': operation, 'raw_file': raw_path.name,
                                 'raw_sha256': sha(raw_path), 'execution_error_type': execution_error})
            # No next case after uncertain accounting, identity or container lifecycle.
            try:
                database = service.directory / request.plan_id / 'recipe-operations' / (operation + '.sqlite3')
                with sqlite3.connect('file:' + str(database) + '?mode=ro', uri=True) as connection:
                    rows = connection.execute('SELECT payload_json FROM receipts').fetchall()
                    assert len(rows) == 1
                    receipt = ExecutionReceipt.model_validate_json(rows[0][0])
                    identity = receipt.metadata['attempt_id']
                    row = connection.execute('SELECT payload_json FROM execution_attempts WHERE attempt_id=?', (identity,)).fetchone()
                    assert row is not None
                    attempt = ExecutionAttempt.model_validate_json(row[0])
                    assert attempt.state in (ExecutionAttemptState.COMPLETED, ExecutionAttemptState.FAILED)
                    assert receipt.receipt_id in attempt.terminal_receipt_ids
                    assert receipt.executor_id == attempt.executor_id == recipe.extension.grader.id
                    assert receipt.executor_fingerprint == attempt.executor_fingerprint
                evidence_ref = receipt.metadata['execution_evidence_digest']
                row = connection.execute("SELECT payload_json FROM assessment_records WHERE kind='execution_evidence' AND digest=?", (evidence_ref,)).fetchone()
                assert row is not None
                evidence = ExecutionEvidence.model_validate_json(row[0])
                assert evidence.complete and evidence.attempt_id == identity and content_digest(evidence) == evidence_ref
                charged = next(item for item in repo.operation_ledger(request.plan_id).operations if item.operation_id == operation)
                assert charged.elapsed_seconds is not None and 0 <= charged.elapsed_seconds < float('inf')
                owned = container_name(identity)
                assert not subprocess.check_output([parent['docker'], '--host', parent['socket'], 'ps', '-a',
                    '--filter', 'name=^/' + owned + '$', '--format', '{{.ID}}'], timeout=15).decode().strip()
                receipts.append({'name': name, 'operation_id': operation, 'receipt_id': receipt.receipt_id,
                    'receipt_ref': content_digest(receipt), 'container_name': owned, 'container_removed': True,
                    'environment_digest': request.environment_digest, 'attempt_state': attempt.state.value})
            except Exception as exc:
                raise StopDispatch('Canonical completion or cleanup could not be verified') from exc
            verify_assets()
            if execution_error is not None:
                raise CaseExecutionFailure('Contained observer failed; no test grade inferred')
            return evaluation(output)

        for item in review['probes']:
            raw = await observe('probe-' + item['name'], item['payload'], item['payload_sha256'])
            if (not isinstance(raw, dict) or raw.get('exit_code') != 0
                    or raw.get('archive_sha256') != item['archive_sha256']
                    or raw.get('statuses', {}).get(item['expected_node']) != 'PASSED'):
                raise StopDispatch('Fresh runtime containment/state probe failed')

        for case in cases:
            result = {'case_id': case.input.task_id, 'reproduction_eligible': False, 'variants': []}
            results.append(result)
            labels=review['variant_labels'][case.input.task_id]
            for label in labels:
                staged = next(item for item in variants if item['case'] == case.input.task_id and item['variant'] == label)
                raw = None

                async def probe(payload):
                    nonlocal raw
                    raw = await observe(case.input.task_id + '-' + label, payload, staged['sha256'])
                    return raw

                record = {'variant': label, 'passed': False}
                result['variants'].append(record)
                try:
                    grade = await grade_suite_output(case.input.model_dump(mode='json'), case.truth.model_dump(mode='json'),
                                                     staged['artifact'], probe)
                except (ConfigurationError, CaseExecutionFailure) as exc:
                    record.update({'error_type': type(exc).__name__, 'reason': 'execution_or_protocol_failure'})
                    break
                record['grade'] = grade.model_dump(mode='json')
                expected = review['expectations'][case.input.task_id][label]
                record['discrepancies'] = discrepancies(raw, record['grade'], expected)
                record['passed'] = not record['discrepancies']
                if not record['passed']:
                    break
            result['reproduction_eligible'] = len(result['variants']) == len(labels) and all(item['passed'] for item in result['variants'])
        summary['batch_completed'] = True
    except BaseException as exc:
        summary['error_type'] = type(exc).__name__
        raise
    finally:
        try:
            if validation_started is not None:
                repo.finish_operation(request.plan_id + '-analysis',
                    elapsed_seconds=max(0, time.perf_counter() - validation_started - sum(child_seconds)),
                    resources=ResourceVector(cpu_ms=max(0, time.process_time() - validation_cpu) * 1000))
            ledger = repo.operation_ledger(request.plan_id)
            (HERE / 'operation-ledger.json').write_text(ledger.model_dump_json(indent=2) + '\n')
            summary.update({'ledger_operations': len(ledger.operations), 'contained_calls_started': calls,
                'elapsed_complete': all(item.elapsed_seconds is not None for item in ledger.operations),
                'containers_removed': len(receipts) == calls and all(item['container_removed'] for item in receipts),
                'source_unchanged': verification_source_digest(ROOT) == review['source_digest'],
                'eligible_cases': sum(item['reproduction_eligible'] for item in results),
                'grant_after': list(router.store._connection.execute(
                    "SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone()),
                'elapsed_seconds': time.perf_counter() - began, 'cases_adopted': 0})
        finally:
            await router.close()
            with (HERE / 'execution-result.json').open('x') as stream:
                json.dump(summary, stream, indent=2)
                stream.write('\n')


if __name__ == '__main__':
    asyncio.run(main())
