"""Read canonical evidence after each existing BenchmarkRunner trial."""
import json
from pathlib import Path
import sqlite3

from aeep.assessment.models import content_digest
from aeep.models import ExecutionReceipt
from aeep_toolkit.telemetry import bound_journal, candidate_loading, token_capture


def require_complete(record):
    checks = ('canonical_trial_complete', 'worker_cleanup_confirmed',
              'independent_grader_observed', 'task_prompt_bound')
    if not all(record.get(key) is True for key in checks):
        raise RuntimeError('Incomplete execution/grading/prompt/cleanup evidence; stop dispatch')
    if not record.get('token_capture') or record['token_capture'].get('status') != 'verified':
        raise RuntimeError('Missing bound token capture; stop dispatch without inferred zero')
    if not isinstance(record.get('task_grade'), bool):
        raise RuntimeError('Task grade is indeterminate; stop dispatch')
    # A verified candidate failure is a result. Optional loading may be absent or unknown.


def read_trial(connection, trial, pair, expected, attempt_root):
    rows = list(connection.execute('SELECT payload_json FROM trial_receipts WHERE trial_id=?', (trial.trial_id,)))
    assert len(rows) == 1
    receipt = ExecutionReceipt.model_validate_json(rows[0][0])
    assert receipt.receipt_id in trial.receipt_ids and receipt.executor_id == trial.route_id
    path = Path(connection.execute('SELECT database_path FROM trial_stores WHERE trial_id=?', (trial.trial_id,)).fetchone()[0]).resolve(strict=True)
    assert path.parent == attempt_root.resolve(strict=True)
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as source:
        canonical = ExecutionReceipt.model_validate_json(source.execute('SELECT payload_json FROM receipts WHERE receipt_id=?', (receipt.receipt_id,)).fetchone()[0])
        assert content_digest(canonical) == content_digest(receipt)
        row = source.execute("SELECT payload_json FROM assessment_records WHERE kind='execution_evidence' AND digest=?", (receipt.metadata.get('execution_evidence_digest'),)).fetchone()
    graded = isinstance(trial.valid, bool) and any(
        value.kind.value == 'callback' and value.trust.value == 'verified'
        and isinstance(value.valid, bool) for value in trial.case_validation)
    role = 'skill' if receipt.executor_id == pair.treatment.id else 'turn'
    record = {
        'trial_id': trial.trial_id, 'case_id': trial.case_id,
        'canonical_trial_ref': content_digest(trial), 'canonical_trial_complete': trial.state == 'complete',
        'receipt_ref': content_digest(receipt), 'receipt': receipt.model_dump(mode='json'),
        'worker_cleanup_confirmed': receipt.metadata.get('worker_cleanup_confirmed') is True,
        'independent_grader_observed': graded, 'task_grade': trial.valid if graded else None,
        'task_prompt_bound': receipt.metadata.get('task_instruction_sha256') == expected[(trial.case_id.removeprefix('development-'), role)],
        'token_capture': None, 'candidate_loading': None,
    }
    if row is not None:
        journal = bound_journal(receipt, json.loads(row[0]))
        record['token_capture'] = token_capture(receipt, journal)
        record['candidate_loading'] = candidate_loading(receipt, journal,
            skill_sha256=pair.candidate_skill_digest if role == 'skill' else None)
    return record
