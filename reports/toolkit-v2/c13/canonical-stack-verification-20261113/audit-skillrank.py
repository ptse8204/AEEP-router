"""Reconcile the retained SkillRank observations without dispatch or ledger writes."""

import json
from pathlib import Path

from aeep.assessment.models import (
    AssessmentOperation,
    AssessmentPlan,
    AssessmentReport,
    AssessmentRunBinding,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.scheduling import SKILLRANK_DIAGNOSTIC, require_scheduler
from aeep.benchmarking import BenchmarkCampaignReport
from aeep.execution import ExecutionEvidence
from aeep.models import ExecutionReceipt, ExecutionStatus
from aeep.store import ReceiptStore
from aeep_toolkit.ase_scheduler import SchedulerObservation
from aeep_toolkit.skillrank_scheduler import REVISION
from aeep_toolkit.stack_readiness import EngineeringRunReview
from aeep_toolkit.workflow_catalog import CatalogRuntimeDefinition, WorkflowCatalogRecord
from aeep_toolkit.workflow_telemetry import campaign_receipt

HERE = Path(__file__).resolve().parent
C13 = HERE.parent


def read(path):
    return json.loads(path.read_bytes())


def settled(repository, operation_id, plan_id, turns):
    start = AssessmentOperation.model_validate(repository.get("operation_start", operation_id))
    end = AssessmentOperation.model_validate(repository.get("operation_measurement", operation_id))
    state = repository.store._connection.execute(
        "SELECT state FROM assessment_operations WHERE id=?", (operation_id,)
    ).fetchone()
    assert state is not None and state[0] == "complete"
    assert start.operation_id == end.operation_id == operation_id
    assert start.plan_id == end.plan_id == plan_id and start.stage == end.stage
    assert start.reserved == end.reserved and end.reserved.max_model_turns == turns
    assert end.elapsed_seconds is not None
    return {"operation_id": operation_id, "measurement_ref": content_digest(end)}


def successful_receipt(repository, kind, operation_id, expected_ref):
    receipt = ExecutionReceipt.model_validate(repository.get(kind, operation_id))
    assert receipt.decision_id == operation_id and content_digest(receipt) == expected_ref
    assert receipt.status == ExecutionStatus.SUCCESS and receipt.execution_success is True
    assert repository.store.get_receipt(receipt.receipt_id) == receipt
    return receipt


def catalog_checks():
    original = read(C13 / "workflow-skillrank-20261103/workflow-preparation.json")
    outputs = C13 / "skillrank-cli-continuation-20261104/runtime-execution"
    with ReceiptStore(original["original_ledger"], read_only=True) as store:
        repository = AssessmentRepository(store)
        records = []
        for name, mode, status in (
            ("document-search", "search", "completed"),
            ("software-show", "show", "completed"),
            ("missing-show", "show", "not_found"),
        ):
            output = read(outputs / f"{name}.json")
            ref = output["catalog_ref"]
            record = WorkflowCatalogRecord.model_validate(repository.get("toolkit_workflow_catalog", ref))
            assert content_digest(record) == ref
            assert (record.mode, record.status) == (mode, status) and record.cleanup_verified
            assert record.result_sha256 == content_digest(output["result"])
            assert record.implementation_source == original["source"]
            runtime = CatalogRuntimeDefinition.model_validate(
                repository.get("toolkit_catalog_runtime", record.definition_ref)
            )
            assert content_digest(runtime) == record.definition_ref and runtime.source_revision == REVISION
            assert runtime.catalog.sha256 == record.catalog_sha256
            receipt = successful_receipt(
                repository, "toolkit_component_receipt", record.operation_id, record.receipt_ref
            )
            assert receipt.metadata["query_sha256"] == record.query_sha256
            assert receipt.metadata["definition_ref"] == record.definition_ref
            assert receipt.metadata["cleanup_verified"] is True
            journal = ExecutionEvidence.model_validate(
                repository.get("execution_evidence", record.execution_evidence_ref)
            )
            assert content_digest(journal) == record.execution_evidence_ref
            assert journal.attempt_id == record.operation_id and journal.complete
            assert journal.events[-1].kind == "execution.completed"
            records.append({
                "mode": mode, "status": status, "catalog_ref": ref,
                "original_source": record.implementation_source, "runtime_ref": record.definition_ref,
                "binary_sha256": record.binary_sha256, "catalog_sha256": record.catalog_sha256,
                "receipt_ref": record.receipt_ref, "journal_ref": record.execution_evidence_ref,
                "operations": [settled(repository, operation, record.request_plan_id, 0)
                               for operation in (record.operation_id, record.wrapper_operation_id)],
            })
    return records


def diagnostic_checks():
    directory = C13 / "skillrank-managed-diagnostic-20261107"
    review = read(directory / "operation-review.json")
    result = read(directory / "managed-result.json")
    plan_id = result["plan_id"]
    with ReceiptStore(review["database"], read_only=True) as store:
        repository = AssessmentRepository(store)
        plan = AssessmentPlan.model_validate(repository.get("plan", plan_id))
        assert plan.schema_version == "assessment.plan.v9" and plan.scheduler_digest == review["scheduler_ref"]
        scheduler = require_scheduler(repository, plan.scheduler_digest)
        assert scheduler.adapter_id == SKILLRANK_DIAGNOSTIC and scheduler.source_revision == REVISION
        binding = AssessmentRunBinding.model_validate(repository.get("run_binding", plan_id))
        assert binding.plan_id == plan_id and binding.source_digest == review["source"]
        report = AssessmentReport.model_validate(repository.get("report", result["report_id"]))
        campaign = BenchmarkCampaignReport.model_validate(repository.get("campaign", report.campaign_digest))
        assert content_digest(campaign) == report.campaign_digest and len(campaign.trials) == 2
        observation = SchedulerObservation.model_validate(repository.get("scheduler_observation", plan_id))
        assert observation.definition_ref == plan.scheduler_digest
        assert set(observation.trial_refs.values()) == {content_digest(t) for t in campaign.trials}
        assert set(observation.trial_refs) == set(observation.grade_summaries) == {"0", "1"}
        operation = plan_id + ":external-scheduler"
        process = successful_receipt(repository, "scheduler_receipt", operation, observation.process_receipt_ref)
        assert process.metadata["scheduler_definition"] == plan.scheduler_digest
        assert process.metadata["upstream_timing_excluded"] is True
        journal = ExecutionEvidence.model_validate(process.metadata["execution_evidence"])
        assert journal.digest() == process.metadata["execution_evidence_digest"]
        assert journal.attempt_id == operation and journal.complete
        assert journal.events[-1].kind == "execution.completed"
        engineering_ref = read(directory / "managed-dispatch-ready.json")["review"]
        engineering = EngineeringRunReview.model_validate(
            repository.get("toolkit_engineering_run", engineering_ref)
        )
        assert content_digest(engineering) == engineering_ref
        assert engineering.plan_digest == content_digest(plan)
        assert engineering.implementation_source == binding.source_digest
        request = RecipeMaterializationRequest.model_validate(
            repository.get("recipe_materialization_request", engineering.scope_request_id)
        )
        rows = []
        for slot, expected_route in (("0", plan.baseline_id), ("1", plan.candidate_id)):
            ref = observation.trial_refs[slot]
            trial, = (item for item in campaign.trials if content_digest(item) == ref)
            assert trial.route_id == expected_route and trial.retry_fallback_count == 0
            receipt_id, = trial.receipt_ids
            receipt = campaign_receipt(repository, content_digest(report), receipt_id, plan, request)
            assert receipt.metadata["actual_model"] == review["model"]
            assert receipt.metadata["model_turn_count"] == 1
            grade, = (item for item in trial.case_validation
                      if item.kind.value == "callback" and item.trust.value == "verified")
            assert grade.valid and grade.quality_score == 1
            assert observation.grade_summaries[slot] == {
                "passed": 1, "failed": 0, "total": 1, "pass_rate": 1.0, "skipped": 0,
            }
            rows.append({"slot": slot, "trial_ref": ref, "receipt_ref": content_digest(receipt),
                         "protected_score": grade.quality_score,
                         "operation": settled(repository, trial.trial_id, plan_id, 1)})
        return {
            "original_source": binding.source_digest, "scheduler_ref": plan.scheduler_digest,
            "scheduler_binary_sha256": scheduler.artifact_sha256,
            "scheduler_receipt_ref": observation.process_receipt_ref,
            "scheduler_journal_ref": journal.digest(), "report_ref": content_digest(report),
            "scheduler_operation": settled(repository, operation, plan_id, 0), "trials": rows,
        }


if __name__ == "__main__":
    print(json.dumps({
        "mode": "read_only_original_records", "source_revision": REVISION,
        "search_show": catalog_checks(), "bounded_diagnostic": diagnostic_checks(),
        "current_stack_check_registered": False, "new_model_turns": 0, "replays": 0,
    }, indent=2))
