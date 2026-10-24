"""Reopen completed evidence without replaying tasks, graders or installers."""
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import subprocess

from aeep.assessment.containment import container_name
from aeep.assessment.models import content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.benchmarking import BenchmarkTrial
from aeep.models import ExecutionReceipt
from aeep.router import Router
from aeep_toolkit.telemetry import bound_journal, candidate_loading, token_capture

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')
DOCKER = ['/usr/local/bin/docker', '--host', 'unix:///Users/edwintse/.docker/run/docker.sock']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name):
    return json.loads((HERE / name).read_text())


def main():
    bundle = load('approval-bundle.json')
    terminal = load('bundle-execution-result.json')
    execution = load('execution-result.json')
    model = load('model-result.json')
    proposal = load('collector-definitions.json')
    review = load('operation-review.json')
    assert terminal['review_sha256'] == sha(HERE / 'approval-bundle.json')
    assert execution['review_sha256'] == sha(HERE / 'operation-review.json')
    for path, expected in bundle['assets'].items():
        assert sha(Path(path)) == expected, path
    assert verification_source_digest(ROOT) == bundle['source_digest']
    names = set(subprocess.check_output([*DOCKER, 'ps', '-a', '--format', '{{.Names}}'], text=True, timeout=20).splitlines())
    for image in bundle['model_worker_images']:
        assert not subprocess.check_output([*DOCKER, 'ps', '-a', '--filter', 'ancestor=' + image, '--format', '{{.Names}}'], text=True, timeout=20).strip()
    assert subprocess.check_output([*DOCKER, 'inspect', '--format', '{{.State.Running}}', review['proxy_name']], text=True, timeout=20).strip() == 'false'
    router = Router.from_manifest(BASE / 'aeep.json')
    try:
        service = AssessmentService(router, BASE / '.aeep/assessments')
        repo = service.repository
        probe = load('grader-probes-result.json')
        plan_ids = {r['plan_id'] for r in proposal['requests']}
        plan_ids.update([probe['operation_ledger']['plan_id'], model['plan_id']])
        operations = []
        for plan_id in sorted(plan_ids):
            ledger = repo.operation_ledger(plan_id)
            for operation in ledger.operations:
                state = router.store._connection.execute('SELECT state FROM assessment_operations WHERE id=?', (operation.operation_id,)).fetchone()[0]
                assert state == 'complete' and math.isfinite(operation.elapsed_seconds) and operation.elapsed_seconds >= 0
                operations.append(operation.model_dump(mode='json'))
        assert len(operations) == execution['operations_delta']
        charged_seconds = sum(o['elapsed_seconds'] for o in operations)
        assert math.isclose(charged_seconds, execution['charged_seconds_delta'], abs_tol=1e-6)
        grader_records = []
        for plan_id in sorted(plan_ids):
            for path in (service.directory / plan_id / 'recipe-operations').glob('*.sqlite3'):
                with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as connection:
                    for raw, in connection.execute('SELECT payload_json FROM receipts'):
                        receipt = ExecutionReceipt.model_validate_json(raw)
                        attempt_id = receipt.metadata['attempt_id']
                        state = connection.execute('SELECT state FROM execution_attempts WHERE attempt_id=?', (attempt_id,)).fetchone()[0]
                        assert state == 'COMPLETED' and container_name(attempt_id) not in names
                        assert content_digest(repo.get('recipe_receipt', receipt.receipt_id)) == content_digest(receipt)
                        grader_records.append({'receipt_ref': content_digest(receipt), 'attempt_id': attempt_id, 'state': state, 'container_absent': True})
        directory = service.directory / model['plan_id']
        with sqlite3.connect((directory / 'campaign.sqlite3').as_uri() + '?mode=ro', uri=True) as campaign:
            trials = {key: BenchmarkTrial.model_validate_json(raw) for key, raw in campaign.execute('SELECT trial_id,payload_json FROM trials')}
            stores = dict(campaign.execute('SELECT trial_id,database_path FROM trial_stores'))
            receipts = dict(campaign.execute('SELECT trial_id,payload_json FROM trial_receipts'))
        expected = {(c['case'], c['role']): c['instruction_sha256'] for c in load('task-delivery-check.json')['checks']}
        rows = []
        for trial_id, raw in receipts.items():
            trial = trials[trial_id]
            receipt = ExecutionReceipt.model_validate_json(raw)
            saved = model['records'][trial_id]
            assert saved['receipt_ref'] == content_digest(receipt) and saved['canonical_trial_ref'] == content_digest(trial)
            assert receipt.receipt_id in trial.receipt_ids and trial.route_id == receipt.executor_id
            path = Path(stores[trial_id]).resolve(strict=True)
            assert path.parent == directory / 'attempts'
            with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as original:
                canonical = ExecutionReceipt.model_validate_json(original.execute('SELECT payload_json FROM receipts WHERE receipt_id=?', (receipt.receipt_id,)).fetchone()[0])
                assert content_digest(canonical) == content_digest(receipt)
                attempt = receipt.metadata['attempt_id']
                assert original.execute('SELECT state FROM execution_attempts WHERE attempt_id=?', (attempt,)).fetchone()[0] == 'COMPLETED'
                journal_raw = original.execute("SELECT payload_json FROM assessment_records WHERE kind='execution_evidence' AND digest=?", (receipt.metadata['execution_evidence_digest'],)).fetchone()[0]
            journal = bound_journal(receipt, json.loads(journal_raw))
            tokens = token_capture(receipt, journal)
            treatment = receipt.executor_id == proposal['definitions'][proposal['pair_definition_digest']]['treatment']['id']
            pair = proposal['definitions'][proposal['pair_definition_digest']]
            loading = candidate_loading(receipt, journal, skill_sha256=pair['candidate_skill_digest'] if treatment else None)
            assert tokens == saved['token_capture'] and loading == saved['candidate_loading']
            role = 'skill' if treatment else 'turn'
            case = trial.case_id.removeprefix('development-')
            assert receipt.metadata['task_instruction_sha256'] == expected[(case, role)]
            assert receipt.metadata['worker_cleanup_confirmed'] is True
            independently_graded = isinstance(trial.valid, bool) and any(v.kind.value == 'callback' and v.trust.value == 'verified' and isinstance(v.valid, bool) for v in trial.case_validation)
            assert independently_graded == saved['independent_grader_observed']
            rows.append({'case': case, 'arm': 'treatment' if treatment else 'control', 'trial_id': trial_id, 'receipt_ref': content_digest(receipt), 'trial_ref': content_digest(trial), 'execution_status': receipt.status.value, 'independent_grade': trial.valid if independently_graded else None, 'agent_wall_seconds': trial.wall_time_ms / 1000 if trial.wall_time_ms is not None else None, 'verification_wall_seconds': trial.grading_wall_time_ms / 1000 if trial.grading_wall_time_ms is not None else None, 'receipt_latency_seconds': receipt.actual_resources.latency_ms / 1000, 'raw_model_usage': [u.model_dump(mode='json') for u in receipt.accounting.model_usage], 'cash': receipt.accounting.cash.model_dump(mode='json'), 'token_capture': tokens, 'candidate_loading': loading, 'artifact_sha256': receipt.metadata.get('artifact_sha256'), 'artifact_bytes': receipt.metadata.get('artifact_bytes'), 'worker_cleanup_confirmed': True, 'task_instruction_sha256': receipt.metadata['task_instruction_sha256']})
        assert len(rows) == len(model['records']) == execution['model_turns_delta']
        assert execution['review_counters_within_ceiling'] and execution['grant_after'][3] == execution['grant_before'][3]
        for component in terminal['components']:
            path = Path(component['result_file'])
            assert sha(path) == component['result_sha256']
        output = {'passed': True, 'source_digest': review['source_digest'], 'review_sha256': terminal['review_sha256'], 'engineering_journey_completed': execution['development_journey_completed'], 'bundle_all_components_passed': terminal['all_components_passed'], 'canonical_operations': len(operations), 'charged_operation_seconds': charged_seconds, 'model_turns_charged': execution['model_turns_delta'], 'independently_graded_tasks': sum(r['independent_grade'] is not None for r in rows), 'verified_successes': sum(r['independent_grade'] is True for r in rows), 'verified_token_capture_chains': sum(r['token_capture']['status'] == 'verified' for r in rows), 'positive_treatment_instruction_loads': sum(r['arm'] == 'treatment' and r['candidate_loading']['instructions_loaded'] is True for r in rows), 'semantic_use_established': False, 'provider_internal_meter_verified': False, 'actual_provider_cash': None, 'grant_before': execution['grant_before'], 'grant_after': execution['grant_after'], 'grader_receipts_attempts_reopened': grader_records, 'rows': sorted(rows, key=lambda r: (r['case'], r['arm'])), 'operations': operations, 'all_owned_graders_absent': True, 'all_reviewed_model_workers_absent': True, 'proxy_restored_stopped': True, 'formal_qualification_or_usefulness_or_selection_or_admission': False}
        with (HERE / 'completion-audit.json').open('x') as stream:
            json.dump(output, stream, indent=2, allow_nan=False)
            stream.write('\n')
        print(json.dumps({k: v for k, v in output.items() if k not in ('rows', 'operations', 'grader_receipts_attempts_reopened')}))
    finally:
        router.store.close()


if __name__ == '__main__':
    main()
