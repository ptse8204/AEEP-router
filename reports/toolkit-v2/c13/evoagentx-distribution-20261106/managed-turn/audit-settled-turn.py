"""Reconcile the terminal attempt read-only after final report serialization failed."""

import hashlib
import json
import math
import runpy
import sqlite3
from decimal import Decimal
from pathlib import Path

from aeep.assessment.models import content_digest
from aeep.execution import ExecutionEvidence

HERE = Path(__file__).resolve().parent
REVIEW = '4dbf1960893f298711b3f082da33ea3571b1d22d425bfbeaccea19a4cb065bfa'


def audit():
    driver = runpy.run_path(HERE / 'run.py')
    read, sha = driver['read'], driver['sha']
    review_file = HERE / 'operation-review.json'
    review = read(review_file)
    assert sha(review_file) == REVIEW
    assert all(sha(path) == digest for path, digest in review['assets'].items())
    assert read(HERE / 'operator-approval.json') == {'approved': True, 'review_sha256': REVIEW}
    assert read(HERE / 'started.json') == {
        'review_sha256': REVIEW, 'automatic_retries': False, 'comparisons': 'PAUSED',
    }
    ledger = read(HERE / 'ledger.json')
    ready = read(driver['WORK'] / 'evoagentx-readiness.json')
    assert ready['source_digest'] == review['source_sha256']
    assert ready['pair_definition_digest'] == review['pair_sha256']
    assert len(ready['request_ids']) == 2 and set(ready['boundaries']) == {'control', 'treatment'}
    operations = {op['operation_id']: op for part in ledger for op in part['operations']}
    turn_id = 'evoagentx-managed-proposal-20261106:turn'
    check_id = 'evoagentx-managed-turn-local-20261106:reply'
    assert set(operations) == {
        turn_id, check_id, 'evoagentx-managed-turn-local-20261106:overhead',
        *('pair-inspection:' + ident for ident in ready['request_ids']),
    }
    reply = read(HERE / 'validation-receipt.json')
    assert reply['action_id'] == check_id and reply['status'] == 'success'
    assert reply['execution_success'] and reply['metadata']['local_fixture'] is False
    assert reply['metadata']['request_sha256'] == review['request_sha256']

    with sqlite3.connect(Path(review['database']).as_uri() + '?mode=ro', uri=True) as connection:
        for ident, op in operations.items():
            row = connection.execute(
                "SELECT state,reserved_json FROM assessment_operations WHERE id=? AND grant_id='onboarding'",
                (ident,),
            ).fetchone()
            assert row and row[0] == 'complete' and json.loads(row[1]) == op['reserved']
            row = connection.execute(
                "SELECT payload_json FROM assessment_records WHERE kind='operation_measurement' AND id=?",
                (ident,),
            ).fetchone()
            assert row and json.loads(row[0]) == op
            assert 0 <= op['elapsed_seconds'] <= op['reserved']['max_elapsed_seconds']
        assert sum(op['reserved']['max_elapsed_seconds'] for op in operations.values()) <= review['maximum_reserved_seconds']
        assert sum(op['reserved']['max_model_turns'] for op in operations.values()) == review['maximum_model_turns'] == 1
        assert all(Decimal(str(op['reserved']['max_cash_usd'])) == 0 for op in operations.values())
        row = connection.execute("SELECT payload_json FROM receipts WHERE receipt_id=?", (reply['receipt_id'],)).fetchone()
        assert row and json.loads(row[0]) == reply
        row = connection.execute(
            "SELECT payload_json FROM assessment_records WHERE kind='execution_evidence' AND digest=?",
            (reply['metadata']['execution_evidence_ref'],),
        ).fetchone()
        assert row
        evidence = ExecutionEvidence.model_validate_json(row[0])
        assert evidence.complete and evidence.attempt_id == check_id
        receipts = connection.execute(
            "SELECT payload_json FROM assessment_records WHERE kind='planning_receipt' "
            "AND json_extract(payload_json,'$.action_id')=?",
            (turn_id,),
        ).fetchall()
        assert len(receipts) == 1
        receipt = json.loads(receipts[0][0])
        current = connection.execute(
            "SELECT revoked,operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'"
        ).fetchone()
        pending = connection.execute(
            "SELECT id,reserved_json FROM assessment_operations WHERE grant_id='onboarding' AND state='reserved' ORDER BY id"
        ).fetchall()

    assert receipt['status'] == 'success' and receipt['schema_valid'] is True and receipt['attempt'] == 1
    assert receipt['executor_id'] == 'evoagentx-proposal.control'
    meta = receipt['metadata']
    assert meta['model_turn_count'] == 1 and meta['actual_model'] == review['model']
    assert meta['worker_cleanup_confirmed'] is True and meta['tool_call_count'] == 0
    assert json.loads(meta['host_tools_used']) == []
    assert meta['boundary_digest'] == ready['boundaries']['control']['conformance_digest']
    assert meta['host_runtime_digest'] == ready['boundaries']['control']['identity_digest']
    _, _, prompt, _, wire = driver['payload']()
    assert meta['task_instruction_sha256'] == hashlib.sha256(prompt.encode()).hexdigest()
    assert wire == review['provider_text_sha256']
    assert receipt['accounting'] == operations[turn_id]['accounting']
    assert len(receipt['accounting']['model_usage']) == 1
    before = review['grant']['counters']
    elapsed = sum(op['elapsed_seconds'] for op in operations.values())
    assert current and not current[0]
    assert current[1] - before[0] == len(operations) == review['maximum_operations']
    assert current[2] - before[1] == 1 and math.isclose(current[3] - before[2], elapsed, abs_tol=1e-6)
    assert Decimal(current[4]) == Decimal(before[3]) == 0
    assert len(pending) == review['grant']['prior_reservations']
    assert content_digest(pending) == review['grant']['prior_reservations_sha256']
    assert driver['proxy_state'](review) == review['stopped_proxy']
    assert driver['named_container_absent'](review, review['local_validator_container'])
    return {
        'review_sha256': REVIEW, 'evidence_kind': 'read_only_reconciliation',
        'original_driver_exit': 1, 'original_driver_failure': 'sqlite3.Row is not JSON serializable in final summary',
        'original_summary_written': False, 'comparisons': 'PAUSED', 'provider_reply_validated': True,
        'model_turns_reserved': 1, 'model_turns_observed': 1, 'recorded_tool_calls': 0,
        'worker_receipt_id': receipt['receipt_id'], 'validator_receipt_id': reply['receipt_id'],
        'validator_execution_evidence': reply['metadata']['execution_evidence_ref'],
        'request_sha256': review['request_sha256'], 'reply_sha256': reply['metadata']['reply_sha256'],
        'provider_model_usage': receipt['accounting']['model_usage'][0],
        'stack_executed': False, 'worker_cleanup_confirmed': True, 'proxy_restored_stopped': True,
        'validator_container_absent': True, 'accounting_settled': True,
        'operations_completed': len(operations), 'measured_operation_seconds': elapsed,
        'grant_after': list(current[1:]), 'prior_reservations_preserved': len(pending),
        'ledger_sha256': sha(HERE / 'ledger.json'),
        'validation_receipt_sha256': sha(HERE / 'validation-receipt.json'),
    }


if __name__ == '__main__':
    print(json.dumps(audit(), indent=2, allow_nan=False))
