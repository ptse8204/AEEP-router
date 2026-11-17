"""Attribute pretrial grader time in six historical runs using read-only receipts."""

import json
import math
import runpy
from datetime import timedelta
from pathlib import Path

from aeep.assessment.models import (
    AssessmentOperationLedger,
    AssessmentReport,
    AssessmentRunBinding,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.attempts import ExecutionAttemptState
from aeep.execution import ExecutionEvidence
from aeep.models import ExecutionReceipt
from aeep.store import ReceiptStore

from audit_skillsbench_resources import AUDITOR, HERE, PRIOR, audit as resource_audit

RESOURCES = HERE / "skillsbench-resource-observations.json"


def verify_charge(repo, binding, operation, successor_at, settled):
    if (
        operation.plan_id != binding.plan_id
        or settled(repo, operation.operation_id) != operation
        or operation.elapsed_seconds is None
        or not math.isfinite(operation.elapsed_seconds)
        or not 0 < operation.elapsed_seconds <= operation.reserved.max_elapsed_seconds
        or operation.reserved.max_model_turns != 0
        or not binding.started_at <= operation.started_at
        or operation.started_at + timedelta(seconds=operation.elapsed_seconds) > successor_at
    ):
        raise ValueError("pretrial operation is missing, unbound or outside its measured window")
    database = Path(binding.campaign_path).parent / "recipe-operations" / f"{operation.operation_id}.sqlite3"
    with ReceiptStore(database, read_only=True) as local:
        receipt, = local.list_receipts(limit=2)
        attempt_id = receipt.metadata["attempt_id"]
        attempt = local.get_execution_attempt(attempt_id)
        journal_ref = receipt.metadata["execution_evidence_digest"]
        journal = ExecutionEvidence.model_validate(AssessmentRepository(local).get("execution_evidence", journal_ref))
        if (
            receipt != ExecutionReceipt.model_validate(repo.get("recipe_receipt", receipt.receipt_id))
            or receipt.status != "success"
            or receipt.accounting != operation.accounting
            or receipt.accounting is None
            or receipt.accounting.model_usage
            or not operation.started_at <= receipt.started_at <= receipt.ended_at <= successor_at
            or not 0 < receipt.actual_resources.latency_ms <= operation.elapsed_seconds * 1000
            or attempt is None
            or attempt.state != ExecutionAttemptState.COMPLETED
            or attempt.terminal_receipt_ids != (receipt.receipt_id,)
            or attempt.executor_fingerprint != receipt.executor_fingerprint
            or journal.attempt_id != attempt_id
            or not journal.complete
            or content_digest(journal) != journal_ref
            or journal.events[-1].kind != "execution.completed"
        ):
            raise ValueError("pretrial receipt and completed journal do not match the charge")
    return {
        "stage": operation.stage,
        "operation_id": operation.operation_id,
        "settled_measurement_ref": content_digest(operation),
        "receipt_id": receipt.receipt_id,
        "receipt_ref": content_digest(receipt),
        "execution_evidence_ref": journal_ref,
        "executor_fingerprint": receipt.executor_fingerprint,
        "settled_wall_seconds": operation.elapsed_seconds,
        "contained_executor_wall_seconds": receipt.actual_resources.latency_ms / 1000,
        "journal_event_kinds": [event.kind for event in journal.events],
    }


def profile(repo, case, settled):
    report = AssessmentReport.model_validate(repo.get("report", case["report_ref"]))
    ledger = AssessmentOperationLedger.model_validate(repo.get("operation_ledger", report.operation_ledger_digest))
    binding = AssessmentRunBinding.model_validate(repo.get("run_binding", ledger.plan_id))
    wrapper = ExecutionReceipt.model_validate(repo.get("toolkit_workflow_receipt", case["wrapper"]["operation_id"]))
    if (
        content_digest(report) != case["report_ref"]
        or content_digest(ledger) != report.operation_ledger_digest
        or binding.plan_id != ledger.plan_id
        or binding.source_digest != case["implementation_source"]
        or content_digest(wrapper) != case["wrapper"]["receipt_ref"]
    ):
        raise ValueError("pretrial report, ledger or workflow binding changed")
    trial, = (op for op in ledger.operations if op.stage == "trial" and op.plan_id == ledger.plan_id)
    gaps = sorted(
        (op for op in ledger.operations if op.stage in {"grader_reference", "grader_probe"}),
        key=lambda op: op.started_at,
    )
    if (
        [op.stage for op in gaps] != ["grader_reference", *(["grader_probe"] * 7)]
        or len({op.operation_id for op in gaps}) != len(gaps)
        or not wrapper.started_at <= binding.started_at <= trial.started_at <= wrapper.ended_at
    ):
        raise ValueError("unexpected protected validation roles or execution interval")
    measured = [
        verify_charge(repo, binding, op, successor.started_at, settled)
        for op, successor in zip(gaps, [*gaps[1:], trial], strict=True)
    ]
    reference, *probes = measured
    reference_seconds = reference["settled_wall_seconds"]
    probe_seconds = math.fsum(row["settled_wall_seconds"] for row in probes)
    total_seconds = math.fsum((reference_seconds, probe_seconds))
    original_remainder = case["canonical_span_less_agent_and_grading_seconds"]
    if total_seconds > original_remainder:
        raise ValueError("over-attribution inside canonical wall span")
    return {
        "task_id": case["task_id"],
        "implementation_source": binding.source_digest,
        "report_ref": case["report_ref"],
        "operation_ledger_ref": report.operation_ledger_digest,
        "workflow_wrapper_ref": case["wrapper"]["receipt_ref"],
        "first_trial_operation_id": trial.operation_id,
        "prior_unattributed_seconds": original_remainder,
        "pretrial_reference_seconds": reference_seconds,
        "pretrial_probe_seconds": probe_seconds,
        "pretrial_validation_seconds": total_seconds,
        "remaining_unattributed_seconds": original_remainder - total_seconds,
        "protected_grader_operations": measured,
    }


def audit():
    source = runpy.run_path(str(AUDITOR))
    resources = resource_audit()
    if resources != source["read"](RESOURCES):
        raise ValueError("retained resource observation changed")
    database = source["read"](PRIOR / "domain-telemetry-preflight.json")["database"]
    with ReceiptStore(database, read_only=True) as store:
        repo = AssessmentRepository(store)
        domains = {
            domain: [profile(repo, case, source["settled"]) for case in section["cases"]]
            for domain, section in resources["domains"].items()
        }
    return {
        "schema_version": "aeep.c13.skillsbench-pretrial-attribution.v1",
        "source_resource_report_sha256": source["sha"](RESOURCES),
        "source_domain_audit_sha256": resources["source_audit_sha256"],
        "domains": domains,
        "scope": "Historical serial pretrial protected grader reference and probe charges inside the canonical span. Container executor latency is nested inside each corresponding charge.",
        "remaining_interval": "Arithmetic remainder beyond agent, protected task grading and attributed pretrial validation. No phase-level attribution is inferred.",
        "resource_acceptance": "OPEN",
        "new_model_calls": 0,
        "new_protected_grader_invocations": 0,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True, allow_nan=False))
