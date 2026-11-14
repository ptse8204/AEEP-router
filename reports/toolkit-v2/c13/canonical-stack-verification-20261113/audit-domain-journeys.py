"""Join the retained CLI reports, protected grades and telemetry without replay."""

import argparse
import hashlib
import json
from pathlib import Path

from aeep.assessment.models import (
    AssessmentOperation, AssessmentPlan, AssessmentReport, AssessmentRunBinding,
    RecipeMaterializationRequest, content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.benchmarking import BenchmarkCampaignReport
from aeep.models import ExecutionReceipt
from aeep.store import ReceiptStore
from aeep_toolkit.models import EvidenceBundle
from aeep_toolkit.reporting import task_observation
from aeep_toolkit.workflow_accounting import WorkflowOperationBinding, WorkflowPlanLink
from aeep_toolkit.workflow_telemetry import campaign_receipt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
REPORTS = {
    "sales-pivot-analysis": "skillsbench-sales-handoff-20261105/sales-result",
    "invoice-fraud-detection": "skillsbench-document-managed-20261106/managed-execution/invoice-result",
    "exceltable-in-ppt": "skillsbench-document-managed-20261106/managed-execution/excel-result",
    "spring-boot-jakarta-migration": "skillsbench-managed-worker-preparation-20261105/engineering/spring-result",
    "react-performance-debugging": "skillsbench-react-managed-preparation-20261107/sol-permitted-path-live-execution/react-result",
    "llm-prefix-cache-replay": "skillsbench-software-substitute-20261109/managed-preparation/cli-execution/prefix-cache-result",
}
RAW_FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
              "output_tokens", "reasoning_output_tokens")


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def settled(repo, identity):
    state = repo.store._connection.execute(
        "SELECT state FROM assessment_operations WHERE id=?", (identity,)
    ).fetchone()
    assert state is not None and state[0] == "complete"
    start = AssessmentOperation.model_validate(repo.get("operation_start", identity))
    end = AssessmentOperation.model_validate(repo.get("operation_measurement", identity))
    assert start.operation_id == end.operation_id == identity
    assert start.plan_id == end.plan_id and start.stage == end.stage
    assert start.reserved == end.reserved and end.elapsed_seconds is not None
    return end


def task(repo, row, original_source):
    key = row["task_id"]
    directory = ROOT / ".aeep" / REPORTS[key]
    assert sha(HERE.parent / row["source_record"]) == row["source_record_sha256"]
    plan = AssessmentPlan.model_validate(repo.get("plan", row["plan_id"]))
    report = AssessmentReport.model_validate(repo.get("report", row["report_id"]))
    binding = AssessmentRunBinding.model_validate(repo.get("run_binding", plan.plan_id))
    assert binding.source_digest == original_source
    request = RecipeMaterializationRequest(**{
        name: getattr(plan, name) for name in (
            "subject_digest", "recipe_digest", "mapping_digest", "environment_digest",
            "authorization_id", "definition_digests",
        )
    }, seed=0)
    receipt = campaign_receipt(repo, content_digest(report), row["receipt_id"], plan, request)
    ref = content_digest(receipt)
    assert ref == row["receipt_ref"]
    campaign = BenchmarkCampaignReport.model_validate(repo.get("campaign", report.campaign_digest))
    trial, = (item for item in campaign.trials if item.receipt_ids == [receipt.receipt_id])
    assert trial.case_id == key and trial.retry_fallback_count == row["retries"]
    grade, = (item for item in trial.case_validation
              if item.kind.value == "callback" and item.trust.value == "verified")
    assert grade.quality_score == row["score"] and grade.valid is bool(row["score"])
    bundle = EvidenceBundle.model_validate(read(directory / "toolkit-evidence.json"))
    run, = bundle.runs
    assert run.run_id == trial.trial_id and run.receipt_refs == (ref,)
    assert run.verification_ref == content_digest(trial) and run.mode == "forced_diagnostic"
    assert run.verification == ("pass" if grade.valid else "fail")
    assert run.agent_wall_seconds == row["agent_wall_seconds"]
    assert run.verification_wall_seconds == row["grading_wall_seconds"]
    usage, = receipt.accounting.model_usage
    raw_tokens = {field: getattr(usage, field) for field in RAW_FIELDS}
    # React's original table omitted cache writes; the verified capture includes
    # the field. Check every originally published count against the receipt.
    published = row["provider_tokens"]
    assert all(value == published[key] for key, value in raw_tokens.items()
               if key in published or key != "cache_write_input_tokens")

    managed = read(directory / "managed-evidence.json")
    summary = read(directory / "summary.json")
    operation = read(directory / "operation.json")
    assert operation["state"] == "exported" and operation["plan_id"] == plan.plan_id
    assert managed["report_sha256"] == content_digest(report)
    assert managed["plan_sha256"] == content_digest(plan)
    assert not managed["normalization_gaps"] and not managed["unresolved_operations"]
    group, = summary["cohorts"]
    family, = group["families"]
    assert family["task_observations"] == [task_observation(run)]
    assert not family["task_comparisons"] and family["observed_pairs"] == 0
    assert summary["managed_analysis"]["analysis_ref"] == content_digest(report)
    capture = managed["telemetry_capture"][trial.trial_id]["tokens"]
    assert capture["receipt_ref"] == ref and capture["status"] == "verified"
    assert set(capture["known_fields"]) == set(RAW_FIELDS)

    op = managed["workflow_accounting"]["operation_id"]
    link = WorkflowPlanLink.model_validate(repo.get("toolkit_workflow_plan_link", op))
    assert link.assessment_plan_id == plan.plan_id and link.assessment_plan_digest == content_digest(plan)
    workflow = WorkflowOperationBinding.model_validate(repo.get("toolkit_workflow_operation", op))
    assert workflow.stage == "run" and workflow.operation_id == op
    wrapper = ExecutionReceipt.model_validate(repo.get("toolkit_workflow_receipt", op))
    assert wrapper.decision_id == op and wrapper.execution_success
    assert repo.store.get_receipt(wrapper.receipt_id) == wrapper
    assert wrapper.metadata["workflow_accounting"]["definition_ref"] == workflow.definition_ref
    charge = settled(repo, op)
    return {
        "task_id": key, "original_source": original_source, "frozen_workflow_sha256": workflow.workflow_sha256,
        "workflow_configuration": workflow.configuration, "trial_ref": content_digest(trial),
        "receipt_ref": ref, "assessment_report_ref": content_digest(report),
        "protected_score": row["score"], "score_maximum": 1, "execution_status": run.status,
        "provider_tokens": raw_tokens, "token_source": capture["source"],
        "token_capture": capture["status"], "provider_usage_independently_verified": False,
        "cached_semantics": run.tokens.cached_semantics, "reasoning_semantics": run.tokens.reasoning_semantics,
        "matched_token_delta": None, "agent_wall_seconds": run.agent_wall_seconds,
        "protected_grading_wall_seconds": run.verification_wall_seconds, "retries": run.retries,
        "run_wrapper": {"operation_id": op, "receipt_ref": content_digest(wrapper),
                        "measurement_ref": content_digest(charge)},
        "retained_cli_files": {name: sha(directory / name) for name in
                               ("operation.json", "summary.json", "report.md", "report.html")},
    }


def audit():
    plan = read(HERE / "domain-telemetry-preflight.json")
    original = read(HERE / "skillsbench-engineering-outcomes.json")
    sources = {row["task_id"]: row["implementation_source"]
               for row in read(HERE / "skillsbench-ledger-audit.json")["observations"]}
    sales = read(HERE / "domain-live-result.json")["domains"]["document-data"]
    spring = read(HERE / "spring-telemetry-result.json")
    historical = {
        "document-data": (sales, "domain-live-result.json"),
        "software-engineering": (spring, "spring-telemetry-result.json"),
    }
    result = {}
    with ReceiptStore(plan["database"], read_only=True) as store:
        repo = AssessmentRepository(store)
        for domain, rows in original["domains"].items():
            trace, file = historical[domain]
            tasks = [task(repo, row, sources[row["task_id"]]) for row in rows]
            subject, = (t for t in tasks if t["receipt_ref"] == trace["source_receipt_sha256"])
            assert trace["ingestion_verified"] and trace["disabled_export_verified"]
            installation = read(HERE / f"{domain}-installed-readiness.json")
            assert installation["observations"]["task-assets"]["tree_matches"]
            result[domain] = {
                "tasks": tasks,
                "historical_installation_observation": {
                    "source": installation["implementation_source"],
                    "journal_sha256": installation["observations"]["task-assets"]["journal_sha256"],
                },
                "retained_trace": {
                    "task_id": subject["task_id"], "trace_id": trace["trace_id"],
                    "span_id": trace["span_id"], "source": plan["implementation_source"],
                    "result_sha256": sha(HERE / file), "verified_readback": True,
                    "verified_export_disablement": True, "transport_acceptance": "FAILED_UNRECOGNIZED",
                },
            }
    return {
        "scope": "Read-only join of historical CLI workflows; not a fresh end-to-end run",
        "skillsbench_revision": original["skillsbench_revision"],
        "domains": result, "new_model_turns": 0, "new_exports": 0,
        "canonical_stack_complete": False, "comparisons": "PAUSED",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(audit(), indent=2, allow_nan=False))
