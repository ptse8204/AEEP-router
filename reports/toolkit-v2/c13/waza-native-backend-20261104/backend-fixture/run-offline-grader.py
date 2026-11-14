"""Check Waza's actual local text grader using two explicitly synthetic replies."""

import argparse
import asyncio
import hashlib
import json
import shutil
import time
from datetime import timedelta
from pathlib import Path

from aeep.assessment.models import (
    AssessmentBudgetAmendment, AssessmentLimits, RecipeMaterializationRequest, content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.execution import ExecutionEvidence, persist_execution_events
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutionReceipt, ExecutionStatus, ExecutorSpec, SideEffect, utc_now
from aeep.store import ReceiptStore

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
TAG = "waza-native-offline-grader-20261113"


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def consume(raw, output):
    assert raw.status == ExecutionStatus.SUCCESS and raw.exit_code == 0
    assert not output.is_symlink() and output.stat().st_size <= 65536
    grade, outcome = json.loads(raw.stdout), read(output)
    assert grade["overall_score"] == 0.5 and grade["passed"] is False
    [task] = outcome["tasks"]
    assert task["test_id"] == "receipt-total" and task["status"] == "failed"
    scores = []
    for index, trial in enumerate(task["runs"], 1):
        result = trial["validations"]["exact-total"]
        assert trial["run_number"] == index and result["type"] == "text"
        assert trial["status"] == ("passed" if index == 1 else "failed")
        assert result["passed"] is (index == 1) and result["score"] == int(index == 1)
        scores.append(result["score"])
    assert scores == [1, 0]
    return {"synthetic_reference_score": 1, "synthetic_wrong_reply_score": 0}


async def execute(repository, request, review, identity, workspace):
    spec = ExecutorSpec(
        id="toolkit.waza.offline-grade", capability="toolkit.upstream-engineering@1",
        kind="command", description="Run pinned Waza text checks with network and credentials denied",
        side_effect="write", config={"argv": review["command"], "argv_literal": True,
            "inherit_env": False, "env": review["environment"], "cwd": str(workspace),
            "timeout_seconds": 25, "max_output_bytes": 32768, "output": {"type": "text"}},
    )

    def recheck():
        assert verification_source_digest(ROOT) == review["implementation_source"]
        assert all(sha(path) == digest for path, digest in review["pins"].items())
        assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
        repository.authorize(request)
        return identity

    recheck()
    repository.reserve(request, TAG, AssessmentLimits(max_operations=1, max_elapsed_seconds=40),
                       stage="waza_offline_grade", require_settled_plan=True)
    began, started = time.perf_counter(), utc_now()
    executor = CommandExecutor()
    error, execution_evidence, scores, raw = None, None, {}, None
    try:
        with persist_execution_events(lambda journal, event: repository.put(
                "execution_event", journal + ":" + str(event.sequence), event)):
            handle = await executor.start(ExecutionContext(
                request=ActionRequest(action_id=TAG, capability=spec.capability), spec=spec,
                estimate=spec.estimate, attempt=1, attempt_id=TAG,
                invocation_check=recheck, approved_side_effect=SideEffect.WRITE,
            ))
            raw = await handle.task
        observed = ExecutionEvidence.model_validate(raw.metadata["execution_evidence"])
        assert observed.complete and observed.attempt_id == TAG
        execution_evidence = repository.put("execution_evidence", observed.digest(), observed)
        scores = consume(raw, workspace / "graded.json")
    except BaseException as failure:
        error = type(failure).__name__
    finally:
        await executor.close()
    success = error is None
    receipt = ExecutionReceipt(
        decision_id=TAG, action_id=TAG, capability=spec.capability, executor_id=spec.id,
        executor_kind=spec.kind, status="success" if success else "failed",
        started_at=started, ended_at=utc_now(), estimated=spec.estimate,
        actual_resources=raw.resources if raw else {}, error_type=error, execution_success=success,
        metadata={"review_sha256": identity, "execution_evidence_ref": execution_evidence,
                  "synthetic_grader_control": True, "provider_contact": False,
                  "model_turns": 0, "scores": scores,
                  "stdout_sha256": hashlib.sha256((raw.stdout or "").encode()).hexdigest() if raw else None,
                  "stderr_sha256": hashlib.sha256((raw.stderr or "").encode()).hexdigest() if raw else None},
    )
    repository.store.save_receipt(receipt)
    ref = repository.put("toolkit_component_receipt", TAG, receipt)
    repository.finish_operation(TAG, elapsed_seconds=time.perf_counter()-began, resources=receipt.actual_resources)
    return {"passed": success, "receipt_ref": ref, "execution_evidence_ref": execution_evidence,
            "scores": scores, "error_type": error, "models": 0, "live_waza_backend_verified": False}


def main(path, identity):
    review = read(path)
    assert sha(path) == identity and review["pins"][str(Path(__file__).resolve())] == sha(__file__)
    assert all(sha(file) == digest for file, digest in review["pins"].items())
    assert verification_source_digest(ROOT) == review["implementation_source"]
    workspace = Path(review["working_directory"])
    assert workspace == path.parent and not (workspace / "graded.json").exists()
    previous = read(HERE.parent / "operation-review.json")
    request = RecipeMaterializationRequest.model_validate(read(HERE.parent / "prepared.json")["request"])
    request = request.model_copy(update={"plan_id": TAG})
    with ReceiptStore(previous["ledger"]) as store:
        repository = AssessmentRepository(store)
        counters = list(store._connection.execute(
            "SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?",
            (request.authorization_id,),
        ).fetchone())
        assert counters == review["counter_start"] and not store._connection.execute(
            "SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",
            (request.authorization_id,),
        ).fetchone()
        amendment = AssessmentBudgetAmendment.model_validate(review["amendment"])
        assert amendment.authorization_id == request.authorization_id
        write(workspace / "started.json", {"review_sha256": identity, "standing_first_attempt": True})
        repository.approve_budget_amendment(amendment)
        results = asyncio.run(execute(repository, request, review, identity, workspace))
        results.update(review_sha256=identity, source_revision=review["source_revision"],
                       measurement_ref=content_digest(repository.get("operation_measurement", TAG)))
        write(workspace / "result.json", results)
        print(json.dumps(results, indent=2))
        return not results["passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("review", type=Path)
    parser.add_argument("--execute-delegated", required=True)
    args = parser.parse_args()
    raise SystemExit(main(args.review.resolve(), args.execute_delegated))
