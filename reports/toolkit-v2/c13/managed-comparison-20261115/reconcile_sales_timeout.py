"""Settle the timed-out Sales treatment from its existing canonical evidence."""

import argparse
import json
import sqlite3
from pathlib import Path

from freeze_study import DATABASE
from prepare_renewal import snapshot
from prepare_runtime import WORK, read, sha, write
from run_dispatch import REVIEW, proxy_state

from aeep.assessment.models import AssessmentOperation, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.benchmarking import BenchmarkTrial
from aeep.execution import ExecutionEvidence
from aeep.models import ExecutionReceipt, ExecutionStatus
from aeep.store import ReceiptStore

HERE = Path(__file__).resolve().parent
RUN = WORK / "sales-handoff-continuation"
CONTINUATION = HERE / "sales-handoff-continuation-review.json"
OUTCOME = HERE / "sales-treatment-timeout.json"
REVIEW_SHA = "0650ab390a0e8fe6e8dbcc3fcbdd434e9fa0a272a6cc74024259b0a97cb4ab33"


def settlement():
    assert sha(CONTINUATION) == REVIEW_SHA
    review, result = read(CONTINUATION), read(RUN / "result.json")
    assert result["review_sha256"] == REVIEW_SHA and not result["completed"]
    assert result["error_type"] == "ConfigurationError" and result["proxy_restored_stopped"]
    assert not proxy_state(read(REVIEW)["proxy"]["Id"])["Running"]
    [operation_id] = result["new_unsettled_operations"]
    folder = RUN / "sales-pivot-analysis"
    with sqlite3.connect((folder / "campaign.sqlite3").as_uri() + "?mode=ro", uri=True) as db:
        [(trial_payload, row_payload, attempt_store)] = db.execute(
            "SELECT t.payload_json, r.payload_json, s.database_path FROM trials t "
            "JOIN trial_receipts r ON r.trial_id=t.trial_id "
            "JOIN trial_stores s ON s.trial_id=t.trial_id WHERE t.trial_id=?",
            (operation_id,),
        ).fetchall()
    trial = BenchmarkTrial.model_validate_json(trial_payload)
    receipt = ExecutionReceipt.model_validate_json(row_payload)
    attempt_path = Path(attempt_store).resolve(strict=True)
    assert attempt_path.parent == (folder / "attempts").resolve(strict=True)
    assert trial.trial_id == operation_id
    assert trial.route_id == receipt.executor_id == "sol-pilot-repair-1.treatment"
    assert trial.state == "complete" and trial.failure_category == "indeterminate"
    assert trial.retry_fallback_count == 0 and not trial.case_validation
    assert receipt.status is ExecutionStatus.TIMEOUT and receipt.error_type == "timeout"
    assert trial.receipt_ids == [receipt.receipt_id]
    flags = receipt.metadata
    assert flags["worker_cleanup_confirmed"] is True and flags["model_turn_count"] == 1
    assert flags["task_instruction_sha256"] == review["tasks"][0]["instruction_sha256"]
    assert flags["actual_model"] == review["model"] == trial.host_models[trial.route_id]
    assert trial.grading_wall_time_ms == 0
    assert trial.accounting.model_usage == receipt.accounting.model_usage
    [usage] = receipt.accounting.model_usage
    assert usage.evidence.status.value == "partial"
    with sqlite3.connect(attempt_path.as_uri() + "?mode=ro", uri=True) as db:
        [(canonical,)] = db.execute(
            "SELECT payload_json FROM receipts WHERE receipt_id=?", (receipt.receipt_id,)
        ).fetchall()
        [(journal_payload,)] = db.execute(
            "SELECT payload_json FROM assessment_records WHERE kind='execution_evidence' AND digest=?",
            (flags["execution_evidence_digest"],),
        ).fetchall()
    assert ExecutionReceipt.model_validate_json(canonical) == receipt
    journal = ExecutionEvidence.model_validate_json(journal_payload)
    assert content_digest(json.loads(journal_payload)) == flags["execution_evidence_digest"]
    assert journal.attempt_id == flags["attempt_id"]
    assert journal.boundary_digest == flags["boundary_digest"] and journal.boundary_digest
    assert journal.identity_digest is flags.get("host_runtime_digest") is None
    assert not journal.complete and journal.events[-1].kind == "execution.failed"
    evidence = [event for event in journal.events if event.source_id == "adapter:turn-usage"]
    [final_usage] = evidence
    assert final_usage.accounting.model_usage == receipt.accounting.model_usage
    assert trial.wall_time_ms is not None
    elapsed = trial.wall_time_ms / 1000
    return trial, receipt, elapsed


def reconcile():
    assert not OUTCOME.exists()
    trial, receipt, elapsed = settlement()
    operation_id = trial.trial_id
    _, _, before, amendment, pending = snapshot()
    historical = [row for row in pending if row[0] != operation_id]
    assert len(pending) == len(historical) + 1
    original = read(REVIEW)["grant"]
    assert content_digest(historical) == original["prior_reservations_sha256"]
    assert amendment == original["canonical_amendment_digest"]
    with ReceiptStore(DATABASE) as store:
        repo = AssessmentRepository(store)
        operation = AssessmentOperation.model_validate(repo.get("operation_start", operation_id))
        assert operation.stage == "managed_sol_trial" and operation.reserved.max_model_turns == 1
        assert operation.reserved.max_cash_usd == 0
        assert 300 <= elapsed <= operation.reserved.max_elapsed_seconds == 305
        repo.finish_operation(
            operation_id,
            elapsed_seconds=elapsed,
            accounting=trial.accounting,
            resources=trial.actual_resources,
        )
        measured = repo.get("operation_measurement", operation_id)
    _, _, after, final_amendment, final_pending = snapshot()
    assert final_pending == historical and final_amendment == amendment
    assert before[:3] == after[:3] and before[4] == after[4]
    assert abs(after[3] - (before[3] - (305 - elapsed))) < 1e-7
    outcome = {
        "review_sha256": REVIEW_SHA,
        "operation_id": operation_id,
        "trial_ref": content_digest(trial),
        "receipt_ref": content_digest(receipt),
        "execution_evidence_ref": receipt.metadata["execution_evidence_digest"],
        "measurement_ref": content_digest(measured),
        "status": "timeout",
        "grade": None,
        "worker_cleanup_confirmed": True,
        "proxy_stopped": True,
        "token_capture": "partial",
        "model_turns": 1,
        "agent_wall_seconds": elapsed,
        "provider_reported_tokens": {
            name: getattr(receipt.actual_resources, name)
            for name in (
                "input_tokens",
                "cached_input_tokens",
                "cache_write_input_tokens",
                "output_tokens",
                "reasoning_output_tokens",
            )
        },
        "original_reservations_preserved": True,
        "new_unsettled_operations": 0,
        "grant_after": list(after[1:]),
    }
    write(OUTCOME, outcome)
    print(json.dumps(outcome, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settle", action="store_true")
    args = parser.parse_args()
    if args.settle:
        reconcile()
    else:
        trial, receipt, elapsed = settlement()
        print(trial.trial_id, receipt.receipt_id, elapsed)
