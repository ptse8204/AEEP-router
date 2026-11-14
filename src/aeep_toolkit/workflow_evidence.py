"""Resolve a finished workflow and its independent checks from retained records."""

from __future__ import annotations

import hashlib
import json
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode

from pydantic import Field

from aeep.assessment.identity import protected_directory
from aeep.assessment.models import (
    AssessmentOperation,
    AssessmentOperationLedger,
    AssessmentPlan,
    AssessmentReport,
    AssessmentRunBinding,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.benchmarking import BenchmarkCampaignReport
from aeep.errors import ConfigurationError
from aeep.hosts.codex_accounting import TOKEN_FIELDS
from aeep.models import ExecutionReceipt, StrictModel
from aeep.store import ReceiptStore
from aeep.telemetry import receipt_otlp_preview

from .benchmarks import BenchmarkPack, task_input
from .cli import read_bytes, read_json
from .install_runtime import canonical, digest, load_state, paths
from .models import Digest, EvidenceBundle, Identifier, SourcePin, TokenObservation
from .reporting import render, summarize, task_observation
from .telemetry import token_capture
from .workflow import StackWorkflow, WorkflowFile, _read, prepare_stack
from .workflow_accounting import (
    WorkflowAccountingDefinition,
    WorkflowOperationBinding,
    WorkflowPlanLink,
)
from .workflow_runtime import RuntimeLifecycleRecord, lifecycle_preview
from .workflow_telemetry import ReceiptExportDefinition, campaign_receipt_and_journal

KIND = "toolkit_workflow_completion_evidence"
WORKFLOW_COMPONENTS = {
    "workflow-document-data": "document-data",
    "workflow-software-engineering": "software-engineering",
}
WRAPPER = "toolkit_workflow_receipt"


class OperationLink(StrictModel):
    operation_id: str
    receipt_ref: Digest


class LifecycleLinks(StrictModel):
    store: str
    workflow: WorkflowFile
    operation_review: WorkflowFile
    runtime: Identifier
    setup: OperationLink
    readiness: OperationLink
    removal_configuration: Identifier
    removal_setup: OperationLink
    removal: OperationLink


class TelemetryLinks(StrictModel):
    store: str
    readback: OperationLink
    transport: OperationLink
    disabled: OperationLink
    disabled_workflow: WorkflowFile
    observation_review: WorkflowFile
    observed_result: WorkflowFile


class EvidenceRequest(StrictModel):
    schema_version: Literal["aeep.toolkit.workflow-evidence-request.v1"] = (
        "aeep.toolkit.workflow-evidence-request.v1"
    )
    configuration: Identifier
    report_id: Identifier
    original_workflow: WorkflowFile
    selected_workflow: WorkflowFile
    report_directory: str
    compatibility_basis: str | None = Field(default=None, min_length=1, max_length=2000)
    lifecycle: LifecycleLinks | None = None
    telemetry: tuple[TelemetryLinks, ...] = Field(default=(), max_length=12)


class WorkflowEvidence(StrictModel):
    schema_version: Literal["aeep.toolkit.workflow-completion-evidence.v1"] = (
        "aeep.toolkit.workflow-completion-evidence.v1"
    )
    component: Identifier
    implementation_source: Digest
    original_source: Digest
    request: EvidenceRequest
    observations: dict[str, Any]


def open_store(path: str) -> ReceiptStore:
    file = canonical(path)
    if (
        not file.is_file()
        or file.stat().st_nlink != 1
        or protected_directory(file)
        or file.name.casefold() in {"auth.json", "credentials.json"}
        or file.name.casefold().startswith(".env")
    ):
        raise ConfigurationError("evidence requires an existing unlinked ledger")
    return ReceiptStore(file, read_only=True)


def _file(binding: WorkflowFile) -> bytes:
    if not Path(binding.path).is_absolute():
        raise ConfigurationError("evidence requires absolute input paths")
    return _read(binding, Path("/"))[1]


def _read_workflow(binding: WorkflowFile) -> StackWorkflow:
    return StackWorkflow.model_validate_json(_file(binding))


def _settled(repo: AssessmentRepository, operation_id: str) -> AssessmentOperation:
    with repo.store._lock:
        state = repo.store._connection.execute(
            "SELECT state FROM assessment_operations WHERE id=?", (operation_id,)
        ).fetchone()
    start = AssessmentOperation.model_validate(repo.get("operation_start", operation_id))
    end = AssessmentOperation.model_validate(repo.get("operation_measurement", operation_id))
    if (
        state is None
        or state[0] != "complete"
        or end.elapsed_seconds is None
        or end.elapsed_seconds > start.reserved.max_elapsed_seconds
        or start.operation_id != operation_id
        or start
        != end.model_copy(update={"elapsed_seconds": None, "accounting": None, "resources": None})
    ):
        raise ConfigurationError("workflow operation accounting is incomplete or differs")
    return end


def _receipt(
    repo: AssessmentRepository,
    link: OperationLink,
    *,
    kind: str | None = None,
    success: bool = True,
) -> tuple[ExecutionReceipt, AssessmentOperation]:
    if kind:
        row = repo.get(kind, link.operation_id)
    else:
        with repo.store._lock:
            rows = repo.store._connection.execute(
                "SELECT payload_json FROM receipts WHERE decision_id=?", (link.operation_id,)
            ).fetchall()
        if len(rows) != 1:
            raise ConfigurationError("evidence requires one canonical operation receipt")
        receipt = ExecutionReceipt.model_validate_json(rows[0][0])
        row = receipt.model_dump(mode="json")
    receipt = ExecutionReceipt.model_validate(row)
    if (
        link.receipt_ref != content_digest(receipt)
        or receipt.decision_id != link.operation_id
        or repo.store.get_receipt(receipt.receipt_id) != receipt
        or (success and (receipt.status != "success" or receipt.execution_success is not True))
    ):
        raise ConfigurationError("operation receipt differs from the canonical execution")
    return receipt, _settled(repo, link.operation_id)


def _wrapper(
    repo: AssessmentRepository,
    link: OperationLink,
    *,
    configuration: str,
    stage: str,
    workflow: WorkflowFile,
) -> tuple[WorkflowAccountingDefinition, AssessmentOperation, ExecutionReceipt]:
    receipt, charge = _receipt(repo, link, kind=WRAPPER)
    operation = WorkflowOperationBinding.model_validate(
        repo.get("toolkit_workflow_operation", link.operation_id)
    )
    scope = WorkflowAccountingDefinition.model_validate(
        repo.get("toolkit_workflow_accounting", operation.definition_ref)
    )
    if (
        operation.operation_id != link.operation_id
        or operation.workflow_sha256 != workflow.sha256
        or operation.configuration != configuration
        or operation.stage != stage
        or content_digest(scope) != operation.definition_ref
        or scope.workflow_sha256 != workflow.sha256
        or configuration not in scope.configurations
        or stage not in scope.operations
        or charge.plan_id != scope.request.plan_id
        or charge.stage != "workflow_" + stage + "_overhead"
        or receipt.metadata.get("workflow_accounting", {}).get("definition_ref")
        != operation.definition_ref
        or charge.resources != receipt.actual_resources
        or charge.reserved.max_model_turns != 0
    ):
        raise ConfigurationError("receipt is for a different workflow configuration or step")
    return scope, charge, receipt


def _same_plan(repo: AssessmentRepository, plan: AssessmentPlan, operation_id: str) -> None:
    link = WorkflowPlanLink.model_validate(repo.get("toolkit_workflow_plan_link", operation_id))
    if (
        link.operation_id != operation_id
        or link.assessment_plan_id != plan.plan_id
        or link.assessment_plan_digest != content_digest(plan)
    ):
        raise ConfigurationError("workflow operation is bound to a different assessment")


def _original_run(
    repo: AssessmentRepository,
    request: EvidenceRequest,
    plan: AssessmentPlan,
    report: AssessmentReport,
    bundle: EvidenceBundle,
    report_root: Path,
) -> tuple[dict[str, Any], dict[str, ExecutionReceipt]]:
    report_ref = content_digest(report)
    campaign = BenchmarkCampaignReport.model_validate(repo.get("campaign", report.campaign_digest))
    ledger_ref = report.operation_ledger_digest or ""
    ledger = AssessmentOperationLedger.model_validate(repo.get("operation_ledger", ledger_ref))
    binding = AssessmentRunBinding.model_validate(repo.get("run_binding", plan.plan_id))
    with repo.store._lock:
        jobs = repo.store._connection.execute(
            "SELECT id,state,error_code,report_id FROM assessment_jobs WHERE plan_id=?",
            (plan.plan_id,),
        ).fetchall()
    if (
        len(jobs) != 1
        or jobs[0]["state"] != "complete"
        or jobs[0]["error_code"] is not None
        or jobs[0]["report_id"] != report.report_id
        or binding.plan_id != plan.plan_id
        or content_digest(campaign) != report.campaign_digest
        or content_digest(ledger) != ledger_ref
        or ledger.plan_id != plan.plan_id
        or report.plan_digest != content_digest(plan)
        or report.report_id != request.report_id
        or campaign.suite_id != plan.suite.suite_id
        or bundle.adapter.implementation_sha256 != binding.source_digest
    ):
        raise ConfigurationError(
            "workflow evidence requires the completed canonical job and report"
        )
    operation = read_json(report_root / "operation.json")
    managed = read_json(report_root / "managed-evidence.json")
    if operation.get("state") != "exported" or operation.get("plan_id") != plan.plan_id:
        raise ConfigurationError("workflow report export is incomplete")
    wrapper_id = managed["workflow_accounting"]["operation_id"]
    wrapper_link = OperationLink(
        operation_id=wrapper_id, receipt_ref=content_digest(repo.get(WRAPPER, wrapper_id))
    )
    scope, wrapper_charge, wrapper = _wrapper(
        repo,
        wrapper_link,
        configuration=request.configuration,
        stage="run",
        workflow=request.original_workflow,
    )
    _same_plan(repo, plan, wrapper_id)
    if (
        scope.source_digest != binding.source_digest
        or managed.get("plan_sha256") != content_digest(plan)
        or managed.get("report_sha256") != report_ref
        or managed.get("operation_ledger_sha256") != ledger_ref
        or managed.get("campaign_sha256") != report.campaign_digest
        or managed.get("normalization_gaps") != []
        or managed.get("workflow_accounting") != wrapper.metadata["workflow_accounting"]
    ):
        raise ConfigurationError("report files do not match the canonical workflow run")

    cases = {case.case_id: case for case in plan.suite.cases}
    expected = {
        (case, route.route_id, condition, rep)
        for case in cases
        for route in plan.suite.routes
        for condition in plan.suite.conditions
        for rep in range(plan.suite.repetitions)
    }
    trials = {trial.trial_id: trial for trial in campaign.trials}
    positions = {
        (trial.case_id, trial.route_id, trial.condition, trial.repetition)
        for trial in trials.values()
    }
    if (
        not expected
        or len(expected) != len(campaign.trials)
        or positions != expected
        or len(trials) != len(bundle.runs)
        or set(trials) != {run.run_id for run in bundle.runs}
        or any(entry.elapsed_seconds is None for entry in ledger.operations)
    ):
        raise ConfigurationError("workflow has missing trials or unresolved accounting")
    recorded_charges = {item.operation_id: item for item in ledger.operations}
    if len(recorded_charges) != len(ledger.operations):
        raise ConfigurationError("workflow ledger repeats a charged operation")
    with repo.store._lock:
        unsettled = repo.store._connection.execute(
            "SELECT 1 FROM assessment_operations o JOIN assessment_records s ON s.id=o.id "
            "WHERE s.kind='operation_start' AND json_extract(s.payload_json, '$.plan_id')=? "
            "AND o.state!='complete' LIMIT 1",
            (plan.plan_id,),
        ).fetchone()
    if unsettled:
        raise ConfigurationError("workflow has an unresolved assessment operation")
    graders = [
        item
        for item in ledger.operations
        if item.stage == "recipe_grading" and item.plan_id == plan.plan_id
    ]
    if len(graders) < len(trials) or any(
        _settled(repo, item.operation_id) != item for item in graders
    ):
        raise ConfigurationError("workflow is missing settled protected grading")
    observations = []
    originals = {}
    used_grader_operations: set[str] = set()
    for run in bundle.runs:
        trial = trials[run.run_id]
        case = cases[trial.case_id]
        if (
            len(trial.receipt_ids) != 1
            or len(case.validators) != 1
            or len(trial.case_validation) != 1
            or case.validators[0].kind != "callback"
            or trial.status != "success"
            or (trial.failure_category not in (None, "task_failure"))
        ):
            raise ConfigurationError("workflow trial is missing a protected result")
        grade = trial.case_validation[0]
        receipt, journal = campaign_receipt_and_journal(
            repo, report_ref, trial.receipt_ids[0], plan, scope.request
        )
        ref = content_digest(receipt)
        charge = _settled(repo, trial.trial_id)
        in_trial = [
            item
            for item in graders
            if trial.ended_at is not None and trial.started_at <= item.started_at <= trial.ended_at
        ]
        if (
            grade.kind != "callback"
            or grade.trust != "verified"
            or type(grade.valid) is not bool
            or grade.valid != trial.valid
            or grade.quality_score != int(grade.valid)
            or receipt.status != "success"
            or receipt.execution_success is not True
            or charge != recorded_charges.get(trial.trial_id)
            or charge.plan_id != plan.plan_id
            or not in_trial
            or any(item.operation_id in used_grader_operations for item in in_trial)
            or trial.route_fingerprint != plan.route_fingerprints.get(trial.route_id)
            or receipt.metadata.get("worker_digest") != run.worker_sha256
            or receipt.metadata.get("actual_model") != run.model
            or receipt.metadata.get("task_instruction_sha256") != run.prompt_sha256
            or run.evidence_kind != "live"
            or run.receipt_refs != (ref,)
            or run.plan_ref != report.plan_digest
            or run.task_sha256 != content_digest(case)
            or run.verification_ref != content_digest(trial)
            or run.verifier_sha256 != plan.recipe_digest
            or run.status != "completed"
            or run.arm != ("treatment" if trial.route_id == plan.candidate_id else "control")
            or run.verification != ("pass" if grade.valid else "fail")
            or run.retries != trial.retry_fallback_count
            or run.agent_wall_seconds
            != (None if trial.wall_time_ms is None else trial.wall_time_ms / 1000)
            or run.verification_wall_seconds
            != (None if trial.grading_wall_time_ms is None else trial.grading_wall_time_ms / 1000)
        ):
            raise ConfigurationError(
                "receipt, protected grade or accounting differs from the trial"
            )
        capture = token_capture(receipt, journal)
        if (
            journal is None
            or not journal.complete
            or journal.events[-1].kind != "execution.completed"
        ):
            raise ConfigurationError("trial has no completed original execution journal")
        fields = set(capture["known_fields"])
        expected_tokens = (
            TokenObservation(
                source_ref=ref,
                cached_semantics="included_in_input",
                reasoning_semantics="included_in_output",
                **{
                    field: getattr(receipt.actual_resources, field)
                    for field in fields
                    if field != "cache_write_input_tokens"
                },
            )
            if fields
            else None
        )
        if run.tokens != expected_tokens:
            raise ConfigurationError("report token counts differ from canonical receipt")
        used_grader_operations.update(item.operation_id for item in in_trial)
        observations.append(
            {
                "case_id": case.case_id,
                **task_observation(run),
                "charge_ref": content_digest(charge),
                "protected_grading_measurement_refs": [content_digest(item) for item in in_trial],
                "token_capture": capture,
                "provider_tokens": {
                    field: getattr(receipt.actual_resources, field) if field in fields else None
                    for field in TOKEN_FIELDS.values()
                },
            }
        )
        originals[ref] = receipt
    return {
        "original_source": binding.source_digest,
        "job_id": jobs[0]["id"],
        "report_ref": report_ref,
        "campaign_ref": report.campaign_digest,
        "ledger_ref": ledger_ref,
        "plan_ref": content_digest(plan),
        "run_receipt_ref": wrapper_link.receipt_ref,
        "run_measurement_ref": content_digest(wrapper_charge),
        "trials": observations,
        "grader_operation_refs": [content_digest(item) for item in graders],
        "workflow_accounting": managed["workflow_accounting"],
    }, originals


def _reports(
    directory: Path,
    bundle: EvidenceBundle,
    run: dict[str, Any],
    report: AssessmentReport,
    originals: dict[str, ExecutionReceipt],
) -> dict[str, str]:
    summary = read_json(directory / "summary.json")
    analysis = summary["managed_analysis"]
    report_fields = (
        "outcome",
        "qualification_passed",
        "paired_savings",
        "savings_interval",
        "measured_usage",
        "measurement_coverage",
        "paired_measurement_cases",
        "condition_comparisons",
        "utility_evidence",
        "break_even_uses",
        "distinct_holdout_cases",
        "distinct_paired_cases",
        "correctness_failures",
        "execution_failures",
    )
    if (
        summary.get("evidence_sha256") != content_digest(bundle.model_dump(mode="json"))
        or analysis.get("analysis_ref") != run["report_ref"]
        or analysis.get("plan_ref") != run["plan_ref"]
        or analysis.get("operation_ledger_ref") != run["ledger_ref"]
        or analysis.get("campaign_ref") != run["campaign_ref"]
        or analysis.get("workflow_accounting") != run["workflow_accounting"]
        or any(
            analysis.get(key) != 0
            for key in (
                "missing_trial_positions",
                "unexpected_trial_positions",
                "duplicate_trial_positions",
                "unresolved_operations",
            )
        )
        or analysis.get("expected_trial_positions") != len(bundle.runs)
        or any(
            analysis.get(field) != report.model_dump(mode="json")[field] for field in report_fields
        )
    ):
        raise ConfigurationError("report summary does not match the canonical report")
    expected = summarize(
        bundle,
        accounting_records={
            ref: receipt.model_dump(mode="json") for ref, receipt in originals.items()
        },
    )
    if any(
        summary.get(key) != expected[key]
        for key in ("schema", "outcome", "cohorts", "candidate", "adapter", "inspection_references")
    ):
        raise ConfigurationError("report summary differs from verified task observations")
    files = {}
    for format, suffix in (("markdown", "md"), ("html", "html")):
        name = f"report.{suffix}"
        body = read_bytes(directory / name)
        if render(summary, format).encode() != body:
            raise ConfigurationError("retained report rendering differs from its bound summary")
        files[name] = hashlib.sha256(body).hexdigest()
    return files


def _runtime(
    links: LifecycleLinks,
    request: EvidenceRequest,
    target: StackWorkflow,
    pack: BenchmarkPack,
    plan: AssessmentPlan,
) -> dict[str, Any]:
    workflow = _read_workflow(links.workflow)
    configuration = request.configuration
    review = json.loads(_file(links.operation_review))
    actions = {(name, stage): ref for name, stage, ref in review["actions"]}
    if review["workflow"]["sha256"] != links.workflow.sha256:
        raise ConfigurationError("lifecycle review binds another workflow")
    selected = target.configurations[configuration]
    setup = workflow.configurations[configuration]
    if (
        setup.runtimes != selected.runtimes
        or set(selected.runtimes) != {links.runtime}
        or setup.task_ids != selected.task_ids
        or setup.benchmark.sha256 != selected.benchmark.sha256
        or setup.asset_root != selected.asset_root
        or links.removal_configuration == configuration
    ):
        raise ConfigurationError("lifecycle receipts do not cover the selected runtime")
    steps: tuple[tuple[str, Literal["setup", "readiness", "remove"], OperationLink], ...] = (
        (configuration, "setup", links.setup),
        (configuration, "readiness", links.readiness),
        (links.removal_configuration, "setup", links.removal_setup),
        (links.removal_configuration, "remove", links.removal),
    )
    records: dict[str, Any] = {}
    ended: dict[str, datetime] = {}
    with closing(open_store(links.store)) as store:
        repo = AssessmentRepository(store)
        for name, stage, link in steps:
            scope, charge, receipt = _wrapper(
                repo, link, configuration=name, stage=stage, workflow=links.workflow
            )
            preview, plans = lifecycle_preview(
                Path(links.workflow.path), name, (links.runtime,), operation=stage
            )
            installation = plans[links.runtime]
            installation_ref = digest(installation)
            facts = {
                key: preview[key]
                for key in (
                    "workflow",
                    "configuration",
                    "operation",
                    "runtime_ids",
                    "installation_plans",
                    "shared_references",
                    "implementation_source",
                )
            }
            facts["implementation_source"] = scope.source_digest
            review_ref = content_digest(facts)
            if (
                preview["blockers"]
                or review["source_sha256"] != scope.source_digest
                or actions.get((name, stage)) != review_ref
            ):
                raise ConfigurationError("lifecycle operation differs from its original review")
            observation = preview["observations"][links.runtime]
            value = {
                "configuration": name,
                "stage": stage,
                "original_source": scope.source_digest,
                "operation": link.model_dump(mode="json"),
                "measurement_ref": content_digest(charge),
                "installation_ref": installation_ref,
                "review_ref": review_ref,
                "installation_journal_sha256": observation["journal_sha256"],
            }
            if stage != "readiness":
                record = RuntimeLifecycleRecord.model_validate(
                    repo.get(
                        "toolkit_runtime_lifecycle", link.operation_id + ":" + installation_ref
                    )
                )
                if (
                    record.operation_id != link.operation_id
                    or record.operation != stage
                    or record.workflow_review != review_ref
                    or record.installation_digest != installation_ref
                    or record.runtime_ids != (links.runtime,)
                    or not record.journal_sha256
                    or record.status != ("installed" if stage == "setup" else "removed")
                    or record.error_type is not None
                ):
                    raise ConfigurationError(
                        "runtime lifecycle record differs from the owned change"
                    )
                value["lifecycle_ref"] = content_digest(record)
                if (
                    stage == "remove" or name == configuration
                ) and record.journal_sha256 != observation["journal_sha256"]:
                    raise ConfigurationError(
                        "owned runtime journal changed after the lifecycle operation"
                    )
            if stage == "readiness" and (
                observation["installed"] is not True
                or installation.destination != selected.asset_root
            ):
                raise ConfigurationError("selected runtime installation is unavailable or changed")
            if stage == "remove" and (
                observation["installed"] is not False
                or observation["installer_status"] != "removed"
            ):
                raise ConfigurationError("disposable runtime removal is unresolved")
            if stage != "setup" and ended[name] > receipt.started_at:
                raise ConfigurationError("runtime observation precedes its ordered setup")
            ended[name] = receipt.ended_at
            _, journal_path = paths(installation)
            _, journal = load_state(journal_path)
            value["installed_tree_ref"] = journal["applied_tree_sha256"]
            records[f"{name}:{stage}"] = value
    # Match installed inputs to the protected plan, not just to a configuration label.
    for case in plan.suite.cases:
        if case.action.input != task_input(pack, Path(selected.asset_root), case.case_id):
            raise ConfigurationError("installed task inputs differ from the completed plan")
    return records


def _telemetry(
    repo: AssessmentRepository,
    links: TelemetryLinks,
    request: EvidenceRequest,
    plan: AssessmentPlan,
    run: dict[str, Any],
    originals: dict[str, ExecutionReceipt],
) -> dict[str, Any]:
    receipt, charge = _receipt(
        repo, links.transport, kind="toolkit_receipt_export_transport", success=False
    )
    original_ref = receipt.metadata.get("source_receipt_sha256")
    if original_ref not in originals:
        raise ConfigurationError("telemetry transport belongs to a different trial receipt")
    span = receipt_otlp_preview(originals[original_ref])["payload"]["resourceSpans"][0][
        "scopeSpans"
    ][0]["spans"][0]
    trace_id, span_id = span["traceId"], span["spanId"]
    definition_ref = receipt.metadata.get("definition_ref")
    if not isinstance(definition_ref, str):
        raise ConfigurationError("telemetry transport lacks its reviewed definition")
    enabled = ReceiptExportDefinition.model_validate(
        repo.get("toolkit_receipt_export", definition_ref)
    )
    disabled_workflow = _read_workflow(links.disabled_workflow)
    selected = disabled_workflow.configurations[request.configuration]
    if selected.telemetry is None or selected.assessment is None:
        raise ConfigurationError("disabled control requires its bound telemetry and plan")
    disabled = ReceiptExportDefinition.model_validate_json(
        _read(selected.telemetry, Path(links.disabled_workflow.path).parent)[1]
    )
    scope, off_charge, off_receipt = _wrapper(
        repo,
        links.disabled,
        configuration=request.configuration,
        stage="report",
        workflow=links.disabled_workflow,
    )
    deployment = repo.get("toolkit_receipt_export_deployment", enabled.deployment_review_ref)
    if (
        content_digest(enabled) != definition_ref
        or not enabled.enabled
        or content_digest(deployment) != enabled.deployment_review_ref
        or deployment.get("port") != enabled.port
        or disabled != enabled.model_copy(update={"enabled": False})
        or enabled.assessment_report_ref != run["report_ref"]
        or scope.request != disabled.request
        or content_digest(
            AssessmentPlan.model_validate_json(
                _read(
                    selected.assessment.plan,
                    Path(links.disabled_workflow.path).parent,
                    integration_plan=True,
                )[1]
            )
        )
        != content_digest(plan)
        or receipt.metadata.get("trace_id") != trace_id
        or receipt.capability != "toolkit.receipt-export@1"
        or receipt.executor_id != "toolkit.langfuse-export"
        or receipt.decision_id != f"receipt-export:{definition_ref}:{original_ref}"
        or charge.plan_id != enabled.request.plan_id
        or charge.stage != "workflow_receipt_export"
        or charge.reserved.max_model_turns != 0
        or charge.resources != receipt.actual_resources
        or off_receipt.ended_at > receipt.started_at
    ):
        raise ConfigurationError(
            "telemetry transport or disablement differs from the selected receipt"
        )
    with repo.store._lock:
        unexpected = repo.store._connection.execute(
            "SELECT 1 FROM assessment_operations WHERE id=?",
            (f"receipt-export:{content_digest(disabled)}:{original_ref}",),
        ).fetchone()
    if unexpected:
        raise ConfigurationError("disabled configuration recorded a transport operation")
    with closing(open_store(links.store)) as store:
        readback, read_charge = _receipt(AssessmentRepository(store), links.readback)
    query = urlencode(
        {
            "traceId": trace_id,
            "fields": "core,metadata",
            "expandMetadata": "attributes",
            "limit": 10,
        }
    )
    route_id = hashlib.sha256(("/api/public/v2/observations?" + query).encode()).hexdigest()[:12]
    observation = json.loads(_file(links.observed_result))
    result = observation.get("domains", {}).get(request.configuration, observation)
    review = json.loads(_file(links.observation_review))
    scope_binding = review.get("scope", {}).get(request.configuration)
    if isinstance(scope_binding, dict) and "receipt" in scope_binding:
        scoped = scope_binding == {"receipt": original_ref, "trace": trace_id, "span": span_id}
        scoped = scoped and review.get("retained_namespace") == deployment.get(
            "native_service_namespace"
        )
    else:
        # The Spring continuation pins the original paired review and narrows its scope.
        parent = json.loads(
            _file(WorkflowFile(path=review["parent_review"], sha256=review["parent_review_sha256"]))
        )
        scoped = (
            review.get("trace_id") == trace_id
            and review.get("export_operation") == receipt.decision_id
            and parent["scope"][request.configuration]
            == {"receipt": original_ref, "trace": trace_id, "span": span_id}
            and parent.get("retained_namespace") == deployment.get("native_service_namespace")
        )
    if (
        not scoped
        or observation["review_sha256"] != links.observation_review.sha256
        or readback.metadata.get("review_sha256") != links.observation_review.sha256
        or readback.metadata.get("http_status") != 200
        or readback.executor_id != "langfuse.local-readonly-observer"
        or f":observe:{route_id}:" not in readback.decision_id
        or read_charge.stage != "langfuse_readonly_observation"
        or read_charge.reserved.max_model_turns != 0
        or read_charge.resources != readback.actual_resources
        or readback.started_at < receipt.ended_at
        or result.get("trace_id") != trace_id
        or result.get("span_id") != span_id
        or result.get("source_receipt_sha256") != original_ref
        or result.get("ingestion_verified") is not True
        or result.get("disabled_export_verified") is not True
        or result.get("post_invocations") != 1
    ):
        raise ConfigurationError("telemetry readback is missing or belongs to a different trace")
    return {
        "source_receipt_sha256": original_ref,
        "trace_id": trace_id,
        "span_id": span_id,
        "deployment_review_ref": enabled.deployment_review_ref,
        "original_source": scope.source_digest,
        "transport_status": receipt.status.value,
        "acknowledgement": receipt.metadata.get("acknowledgement"),
        "http_status": result.get("post_response", {}).get("http_status"),
        "transport_receipt_ref": links.transport.receipt_ref,
        "transport_measurement_ref": content_digest(charge),
        "readback_receipt_ref": links.readback.receipt_ref,
        "readback_measurement_ref": content_digest(read_charge),
        "ingestion_verified": True,
        "disabled_export_verified": True,
        "disabled_receipt_ref": links.disabled.receipt_ref,
        "disabled_measurement_ref": content_digest(off_charge),
    }


def inspect_workflow(
    repo: AssessmentRepository, request: EvidenceRequest, source: str
) -> WorkflowEvidence:
    original, selected = map(_read_workflow, (request.original_workflow, request.selected_workflow))
    run = original.configurations[request.configuration]
    target = selected.configurations[request.configuration]
    if (
        run.assessment is None
        or target.assessment != run.assessment
        or target.task_ids != run.task_ids
        or target.candidate.sha256 != run.candidate.sha256
        or target.evaluator != run.evaluator
        or target.benchmark.sha256 != run.benchmark.sha256
        or target.benchmark_recipe != run.benchmark_recipe
        or target.scheduler != run.scheduler
        or target.scanner != run.scanner
        or target.catalog != run.catalog
        or target.components != run.components
    ):
        raise ConfigurationError("selected workflow differs from the completed run")
    root = Path(request.original_workflow.path).parent
    plan = AssessmentPlan.model_validate_json(
        _read(run.assessment.plan, root, integration_plan=True)[1]
    )
    report = AssessmentReport.model_validate(repo.get("report", request.report_id))
    benchmark = BenchmarkPack.model_validate_json(_read(run.benchmark, root)[1])
    tasks = [benchmark.task(task_id) for task_id in run.task_ids]
    component = "workflow-" + request.configuration
    if (
        component not in WORKFLOW_COMPONENTS
        or benchmark.pack_id != "skillsbench"
        or any(task.domain != WORKFLOW_COMPONENTS[component] for task in tasks)
        or tuple(case.case_id for case in plan.suite.cases) != run.task_ids
        or content_digest(repo.get("plan", plan.plan_id)) != content_digest(plan)
    ):
        raise ConfigurationError("completed plan does not match the selected SkillsBench domain")
    preview = prepare_stack(Path(request.selected_workflow.path), request.configuration)
    if preview["blockers"] or preview["implementation_source"] != source:
        raise ConfigurationError("current workflow preparation is blocked or source changed")
    directory = canonical(request.report_directory)
    bundle = EvidenceBundle.model_validate_json(read_bytes(directory / "toolkit-evidence.json"))
    original_source = SourcePin.model_validate_json(_read(run.assessment.source, root)[1])
    if (
        bundle.candidate != original_source
        or bundle.candidate.artifact_sha256 != run.candidate.sha256
    ):
        raise ConfigurationError("report candidate differs from the plan")
    facts, originals = _original_run(repo, request, plan, report, bundle, directory)
    facts["report_files"] = _reports(directory, bundle, facts, report, originals)
    facts["prepared_workflow_ref"] = preview["review_sha256"]
    facts["lifecycle"] = (
        _runtime(request.lifecycle, request, selected, benchmark, plan) if request.lifecycle else {}
    )
    facts["telemetry"] = [
        _telemetry(repo, link, request, plan, facts, originals) for link in request.telemetry
    ]
    if len(facts["telemetry"]) != len(
        {entry["source_receipt_sha256"] for entry in facts["telemetry"]}
    ):
        raise ConfigurationError("telemetry evidence contains duplicate observations")
    facts["checks"] = {
        "ordinary_cli": bool(facts["lifecycle"] and facts["telemetry"]),
        "canonical_report": True,
    }
    return WorkflowEvidence(
        component=component,
        implementation_source=source,
        original_source=facts["original_source"],
        request=request,
        observations=facts,
    )


def verify_workflow(
    repo: AssessmentRepository, record: WorkflowEvidence, *, component: str, source: str
) -> None:
    if record.component != component or record.implementation_source != source:
        raise ConfigurationError(
            "workflow completion evidence belongs to another component or source"
        )
    # The operator review binds every observation, original source and current
    # source. Historical compatibility is an explicit decision, never inferred.
    actual = inspect_workflow(repo, record.request, source)
    original_sources = {
        actual.original_source,
        *(item["original_source"] for item in actual.observations["lifecycle"].values()),
        *(item["original_source"] for item in actual.observations["telemetry"]),
    }
    if original_sources - {source} and not (record.request.compatibility_basis or "").strip():
        raise ConfigurationError(
            "historical evidence requires an explicit source compatibility basis"
        )
    if actual != record or not all(actual.observations["checks"].values()):
        raise ConfigurationError(
            "workflow completion evidence changed or required observations are missing"
        )
