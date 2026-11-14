"""Verify original component evidence without treating reconciliation as a new run."""

from __future__ import annotations

import hashlib
import json
from contextlib import closing
from pathlib import Path
from typing import Literal

from pydantic import Field

from aeep.assessment.identity import verify_dependencies
from aeep.assessment.models import (
    AssessmentOperationLedger,
    AssessmentPlan,
    AssessmentReport,
    AssessmentRunBinding,
    RecipeDefinition,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.benchmarking import BenchmarkCampaignReport, BenchmarkTrial
from aeep.economic.prepared import executor_fingerprint
from aeep.errors import ConfigurationError
from aeep.execution import ExecutionEvidence
from aeep.models import ExecutionReceipt, StrictModel

from .benchmarks import BenchmarkPack
from .models import Digest, Identifier
from .stack_readiness import (
    IntegrationEvidence,
    _resolve,
    require_check,
    source_revisions,
    verify_integration,
)
from .workflow import WorkflowFile, _read
from .workflow_evidence import (
    OperationLink,
    TelemetryLinks,
    _file,
    _read_workflow,
    _receipt,
    _settled,
    _wrapper,
    open_store,
    verify_telemetry_receipts,
)
from .workflow_telemetry import (
    ReceiptExportDefinition,
    ReceiptExportRecord,
    campaign_receipt,
    campaign_receipt_and_journal,
)

KIND = "toolkit_stack_receipt_evidence"


class TelemetryProof(StrictModel):
    kind: Literal["telemetry"]
    configuration: Identifier
    export_record_ref: Digest
    receipts: TelemetryLinks


class SponsorsProof(StrictModel):
    kind: Literal["sponsors"]
    integration_evidence_ref: Digest


class ScannerProof(StrictModel):
    kind: Literal["scanner"]
    store: str
    scan_ref: Digest
    configuration: Identifier
    workflow: WorkflowFile
    wrapper: OperationLink


class MCPReferenceProof(StrictModel):
    kind: Literal["mcp_reference"]
    review: WorkflowFile
    prepared: WorkflowFile
    result: WorkflowFile
    receipts: dict[Identifier, OperationLink]


class ToolHiveProof(StrictModel):
    kind: Literal["toolhive"]
    review: WorkflowFile
    result: WorkflowFile
    boundary: WorkflowFile
    listener: WorkflowFile
    receipts: dict[Identifier, OperationLink]


class ScheduledProof(StrictModel):
    kind: Literal["scheduled"]
    report_ref: Digest


class SkillRankProof(StrictModel):
    kind: Literal["skillrank"]
    catalog_store: str
    catalog_source: Digest
    search_ref: Digest
    show_ref: Digest
    diagnostic_report_ref: Digest


class ManagedProof(StrictModel):
    kind: Literal["managed"]
    report_ref: Digest
    recovery_ref: Digest
    recovery_source: Digest
    recovery_audit: WorkflowFile


class SkillsBenchRun(StrictModel):
    report_ref: Digest
    original_source: Digest
    pack: WorkflowFile


class VerifierControl(StrictModel):
    review: WorkflowFile
    reference: OperationLink
    negative: OperationLink
    reference_result: WorkflowFile
    negative_result: WorkflowFile


class SkillsBenchProof(StrictModel):
    kind: Literal["skillsbench"]
    verifier_store: str
    runs: dict[Identifier, SkillsBenchRun]
    verifiers: dict[Identifier, VerifierControl]


class SDKProof(StrictModel):
    kind: Literal["sdk"]
    review: WorkflowFile
    result: WorkflowFile
    process_store: str
    process_receipt_id: Identifier
    process_receipt_ref: Digest
    step_store: str


class ProposalProof(StrictModel):
    kind: Literal["proposal"]
    review: WorkflowFile
    result: WorkflowFile
    validator: OperationLink


class RouterProof(StrictModel):
    kind: Literal["router"]
    review: WorkflowFile
    result: WorkflowFile
    store: str


class StackReceiptEvidence(StrictModel):
    schema_version: Literal["aeep.toolkit.stack-receipt-evidence.v1"] = (
        "aeep.toolkit.stack-receipt-evidence.v1"
    )
    component: Literal[
        "langfuse",
        "semantic-conventions",
        "github-sponsors",
        "skill-scanner",
        "mcpmark",
        "mcp-universe",
        "toolhive",
        "skillrank",
        "agent-skill-eval",
        "aeep-evaluator",
        "skillsbench",
        "langgraph",
        "agent-framework",
        "evoagentx",
        "aflow",
        "aeep-router",
    ]
    source_revision: str = Field(pattern=r"^(?:[a-f0-9]{40}|[a-f0-9]{64})$")
    implementation_source: Digest
    original_source: Digest
    compatibility_basis: str = Field(min_length=1, max_length=2000)
    proof: (
        TelemetryProof
        | SponsorsProof
        | ScannerProof
        | MCPReferenceProof
        | ToolHiveProof
        | SkillRankProof
        | ScheduledProof
        | ManagedProof
        | SkillsBenchProof
        | SDKProof
        | ProposalProof
        | RouterProof
    ) = Field(discriminator="kind")


def verify_receipt_evidence(
    repository: AssessmentRepository,
    evidence: StackReceiptEvidence,
    *,
    component: str,
    source: str,
) -> dict[str, str]:
    if (
        evidence.component != component
        or evidence.implementation_source != source
        or evidence.source_revision != source_revisions(source)[component]
        or not evidence.compatibility_basis.strip()
    ):
        raise ConfigurationError("component receipt evidence differs from its source or review")
    proof = evidence.proof
    if component in {"evoagentx", "aflow"} and isinstance(proof, ProposalProof):
        return _proposal(repository, proof, evidence)
    if component == "aeep-router" and isinstance(proof, RouterProof):
        return _router(proof, evidence.original_source)
    if component in {"langgraph", "agent-framework"} and isinstance(proof, SDKProof):
        return _sdk(proof, evidence)
    if component == "aeep-evaluator" and isinstance(proof, ManagedProof):
        return _managed(repository, proof, evidence.original_source)
    if component == "skillsbench" and isinstance(proof, SkillsBenchProof):
        if evidence.original_source not in {run.original_source for run in proof.runs.values()}:
            raise ConfigurationError("SkillsBench record omits its historical workflow source")
        return _skillsbench(repository, proof, evidence.source_revision)
    if component == "toolhive" and isinstance(proof, ToolHiveProof):
        return _toolhive(proof, evidence)
    if component == "skillrank" and isinstance(proof, SkillRankProof):
        return _skillrank(repository, proof, evidence)
    if component == "agent-skill-eval" and isinstance(proof, ScheduledProof):
        scheduler, refs = _scheduled_report(
            repository,
            proof.report_ref,
            evidence.original_source,
            evidence.source_revision,
            "agent-skill-eval.controlled.v1",
            1,
        )
        return {
            "controlled_dispatch": scheduler,
            "grading_accounting_cleanup": next(iter(refs.values())),
        }
    if component == "skill-scanner" and isinstance(proof, ScannerProof):
        return _scanner(proof, evidence.original_source, evidence.source_revision)
    if component in {"mcpmark", "mcp-universe"} and isinstance(proof, MCPReferenceProof):
        return _mcp(proof, evidence)
    if component == "github-sponsors" and isinstance(proof, SponsorsProof):
        original = _resolve(
            repository,
            "toolkit_integration_evidence",
            proof.integration_evidence_ref,
            IntegrationEvidence,
        )
        integration = verify_integration(
            repository,
            original,
            component=component,
            source_digest=evidence.original_source,
        )
        receipts = {}
        for name, ref in original.probe_refs.items():
            probe, _ = require_check(repository, integration, name, ref)
            if probe.host_receipt_digest is None:
                raise ConfigurationError("retained Sponsors probe lacks a canonical receipt")
            receipts[name] = probe.host_receipt_digest
        return receipts
    if component not in {"langfuse", "semantic-conventions"} or not isinstance(
        proof, TelemetryProof
    ):
        raise ConfigurationError("component receipt evidence requires the corresponding proof")

    export = _resolve(
        repository, "toolkit_receipt_export_record", proof.export_record_ref, ReceiptExportRecord
    )
    definition = _resolve(
        repository,
        "toolkit_receipt_export",
        export.definition_ref,
        ReceiptExportDefinition,
        reviewed=True,
    )
    if (
        definition.schema_version != "aeep.toolkit.receipt-export.v3"
        or definition.assessment_report_ref is None
        or export.operation_id != proof.receipts.transport.operation_id
        or export.transport_receipt_ref != proof.receipts.transport.receipt_ref
    ):
        raise ConfigurationError("telemetry requires the reviewed canonical campaign export")
    report_ref = definition.assessment_report_ref
    report = _resolve(repository, "report", report_ref, AssessmentReport)
    plan = _resolve(repository, "plan", report.plan_digest, AssessmentPlan)
    original_receipt = campaign_receipt(
        repository, report_ref, export.source_receipt_id, plan, definition.request
    )
    observed = verify_telemetry_receipts(
        repository,
        proof.receipts,
        proof.configuration,
        plan,
        report_ref,
        {content_digest(original_receipt): original_receipt},
    )
    if observed["original_source"] != evidence.original_source:
        raise ConfigurationError("component receipt evidence changes the historical source")
    if component == "langfuse":
        return {
            "ingestion_linkage": proof.receipts.readback.receipt_ref,
            "export_disable": proof.receipts.disabled.receipt_ref,
        }
    return {
        "receipt_export": export.transport_receipt_ref,
        "privacy_disable": proof.receipts.disabled.receipt_ref,
    }


def _settled_journal(
    repo: AssessmentRepository, ref: str, operation: str, *, wire_ref: bool = False
) -> None:
    journal = ExecutionEvidence.model_validate(repo.get("execution_evidence", ref))
    if (
        (journal.digest() if wire_ref else content_digest(journal)) != ref
        or journal.attempt_id != operation
        or not journal.complete
        or journal.events[-1].kind != "execution.completed"
    ):
        raise ConfigurationError("retained operation lacks a complete execution journal")


def _scanner(proof: ScannerProof, original_source: str, revision: str) -> dict[str, str]:
    from .workflow_security import ScannerRuntimeDefinition, WorkflowScanRecord, scan_spec

    with closing(open_store(proof.store)) as store:
        repo = AssessmentRepository(store)
        record = _resolve(repo, "toolkit_workflow_scan", proof.scan_ref, WorkflowScanRecord)
        runtime = _resolve(
            repo,
            "toolkit_scanner_runtime",
            record.definition_ref,
            ScannerRuntimeDefinition,
            reviewed=True,
        )
        wrapper, charge, _ = _wrapper(
            repo,
            proof.wrapper,
            configuration=proof.configuration,
            stage="scan",
            workflow=proof.workflow,
        )
        receipt, measured = _receipt(
            repo,
            OperationLink(operation_id=record.operation_id, receipt_ref=record.receipt_ref),
            kind="toolkit_component_receipt",
        )
        _settled_journal(repo, record.execution_evidence_ref, record.operation_id)
        workflow = _read_workflow(proof.workflow).configurations[proof.configuration]
        scanner = workflow.scanner
        observations = record.observations
        workers = [
            path
            for path, digest in runtime.executable_dependencies.items()
            if Path(path).name == "scanner_worker.py" and digest == runtime.worker_sha256
        ]
        if len(workers) != 1:
            raise ConfigurationError("retained scan has no exact worker fingerprint")
        spec = scan_spec(runtime)
        spec.config["argv"][3] = workers[0]
        if (
            scanner is None
            or "skill-scanner" not in workflow.components
            or ScannerRuntimeDefinition.model_validate_json(
                _read(scanner, Path(proof.workflow.path).parent)[1]
            )
            != runtime
            or workflow.candidate.sha256 != runtime.candidate_sha256
            or wrapper.source_digest != record.implementation_source
            or original_source != record.implementation_source
            or runtime.source_revision != revision
            or record.candidate_sha256 != runtime.candidate_sha256
            or record.environment_digest != content_digest(runtime.environment)
            or record.wrapper_operation_id != proof.wrapper.operation_id
            or record.request_plan_id != measured.plan_id
            or runtime.request.plan_id != measured.plan_id
            or measured.stage != "workflow_static_scan"
            or receipt.executor_id != spec.id
            or record.authorization_id != runtime.request.authorization_id
            or charge.reserved.max_model_turns != 0
            or measured.reserved.max_model_turns != 0
            or measured.resources != receipt.actual_resources
            or receipt.executor_fingerprint != executor_fingerprint(spec)
            or receipt.metadata.get("runtime_ref") != record.definition_ref
            or receipt.metadata.get("scan_observation_sha256") != content_digest(observations)
            or receipt.metadata.get("cleanup_verified") is not True
            or not record.cleanup_verified
            or observations.get("analyzers_executed", 0) < 1
            or observations.get("findings_count") != len(observations["findings"])
            or observations.get("failed_analyzers") != len(observations["analyzer_failures"])
        ):
            raise ConfigurationError("retained scanner output differs from its reviewed scan")
        verify_dependencies(runtime.executable_dependencies)
    return dict.fromkeys(("static_scan", "findings_and_failures"), record.receipt_ref)


def _mcp(proof: MCPReferenceProof, evidence: StackReceiptEvidence) -> dict[str, str]:
    review = json.loads(_file(proof.review))
    result = json.loads(_file(proof.result))
    prepared = json.loads(_file(proof.prepared))
    request = RecipeMaterializationRequest.model_validate(prepared["request"])
    component = evidence.component
    names = {
        "seed-start",
        "missing-start",
        "execute-sql",
        "reference-start",
        "db-stopped",
        "server-stopped",
    }
    if (
        review["pins"][proof.prepared.path] != proof.prepared.sha256
        or review["source"] != evidence.original_source
        or review["source_revision"] != evidence.source_revision
        or set(proof.receipts) != names
        or set(result["containers"]) != {"db", "seed", "missing", "server", "reference"}
        or not all(
            entry["started"] is True
            and entry["retained"] is True
            and entry["terminal"]["Status"] == "exited"
            and entry["terminal"]["OOMKilled"] is False
            for entry in result["containers"].values()
        )
        or result["passed"] is not True
        or result["reference_reward"] != 1
        or result["missing_output_reward"] != 0
        or result["cleanup_uncertain"] is not False
        or result["accounting_uncertain"] is not False
        or review["comparison_eligible"] is not False
        or result["models"] != 0
    ):
        raise ConfigurationError("MCP reference task or its cleanup is incomplete")

    with closing(open_store(review["ledger"])) as store:
        repo = AssessmentRepository(store)
        for ref, scope in prepared["scopes"].items():
            if (
                content_digest(scope) != ref
                or repo.get(f"toolkit_{component}_reference_scope", ref) != scope
                or ref not in request.definition_digests
                or not _reviewed(repo, ref)
            ):
                raise ConfigurationError("MCP reference scope differs from the original review")
        for name, link in proof.receipts.items():
            receipt, charge = _receipt(repo, link)
            if (
                link.operation_id != request.plan_id + ":" + name
                or receipt.executor_id != component + ".postgres-reference"
                or receipt.metadata.get("review_sha256") != proof.review.sha256
                or charge.reserved.max_model_turns != 0
                or charge.plan_id != request.plan_id
                or charge.resources != receipt.actual_resources
            ):
                raise ConfigurationError("MCP observation belongs to a different execution")
            if name == "execute-sql":
                if (
                    receipt.executor_kind != "mcp"
                    or receipt.metadata.get("tool_error") is not False
                    or receipt.metadata.get("sql_sha256") != review["reference_sql_sha256"]
                ):
                    raise ConfigurationError("MCP tool call does not match the original reference")
                continue
            _settled_journal(repo, receipt.metadata["execution_evidence_ref"], link.operation_id)
            if name.endswith("-start"):
                phase = result["phases"][name.removesuffix("-start")]
                # The driver reads one JSON line and retained its exact stdout hash.
                expected = hashlib.sha256((json.dumps(phase) + "\n").encode()).hexdigest()
                role = name.removesuffix("-start")
                if (
                    receipt.metadata.get("stdout_sha256") != expected
                    or phase["runtime_error"] is not False
                    or phase["upstream_exit_code"] != (1 if role == "missing" else 0)
                    or (role == "missing" and phase["missing_results"] is not True)
                    or (role == "reference" and phase["all_checks_passed"] is not True)
                ):
                    raise ConfigurationError("MCP reference phase differs from the observed result")
    return {
        "reference_task": proof.receipts["reference-start"].receipt_ref,
        "state_cleanup": proof.receipts["db-stopped"].receipt_ref,
    }


def _reviewed(repo: AssessmentRepository, ref: str) -> bool:
    with repo.store._lock:
        row = repo.store._connection.execute(
            "SELECT revoked FROM assessment_reviews WHERE digest=?", (ref,)
        ).fetchone()
    return row is not None and not row[0]


def _toolhive(proof: ToolHiveProof, evidence: StackReceiptEvidence) -> dict[str, str]:
    review = json.loads(_file(proof.review))
    summary = json.loads(_file(proof.result))
    boundary = json.loads(_file(proof.boundary))
    listener = json.loads(_file(proof.listener))
    steps = (
        "foreground-service",
        "verify-loopback-listener",
        "container-inspect",
        "boundary-call",
        "aeep-client",
        "stopped-inspect-discover",
    )
    if (
        review["source"] != evidence.original_source
        or review["source_revision"] != evidence.source_revision
        or review["endpoint"] != f"http://127.0.0.1:{review['port']}/mcp"
        or set(steps) != set(proof.receipts)
        or summary["passed"] is not True
        or summary["MCP_server_permissions"] != "PASS"
        or summary["owned_container_stopped_or_removed"] is not True
        or summary["cleanup_uncertain"] is not False
        or summary["accounting_uncertain"] is not False
        or listener["observed_address"] != "127.0.0.1"
        or listener["port"] != review["port"]
        or listener["matched_listeners"] != 1
        or boundary["uid"] != 65534
        or any(
            boundary[name] is not True
            for name in (
                "reviewed_input_read",
                "reviewed_input_write_denied",
                "external_connect_denied",
                "docker_socket_absent",
                "host_canary_absent",
            )
        )
    ):
        raise ConfigurationError(
            "ToolHive lifecycle lacks the reviewed listener, permissions or cleanup"
        )
    verify_dependencies(
        {
            review["toolhive"]: review["toolhive_sha256"],
            review["controller_profile"]: review["assets"][review["controller_profile"]],
        }
    )
    with closing(open_store(review["ledger"])) as store:
        repo = AssessmentRepository(store)
        plans = set()
        for name, link in proof.receipts.items():
            receipt, charge = _receipt(repo, link)
            if (
                link.operation_id != charge.plan_id + ":" + name
                or receipt.executor_id != "toolhive.mcp." + name
                or receipt.metadata.get("review_sha256") != proof.review.sha256
                or receipt.metadata.get("actual_upstream_toolhive") is not True
                or charge.reserved.max_model_turns != 0
                or charge.resources != receipt.actual_resources
            ):
                raise ConfigurationError("ToolHive receipt belongs to a different lifecycle")
            _settled_journal(
                repo, receipt.metadata["execution_evidence_ref"], link.operation_id, wire_ref=True
            )
            plans.add(charge.plan_id)
        if len(plans) != 1:
            raise ConfigurationError("ToolHive lifecycle evidence mixes attempts")
    return {
        "launch_invoke": proof.receipts["aeep-client"].receipt_ref,
        "permissions_stop": proof.receipts["stopped-inspect-discover"].receipt_ref,
    }


def _completed_trials(
    repo: AssessmentRepository,
    report_ref: str,
    original_source: str,
) -> tuple[AssessmentPlan, list[BenchmarkTrial], dict[str, str]]:
    report = _resolve(repo, "report", report_ref, AssessmentReport)
    plan = _resolve(repo, "plan", report.plan_digest, AssessmentPlan)
    binding = AssessmentRunBinding.model_validate(repo.get("run_binding", plan.plan_id))
    campaign = _resolve(repo, "campaign", report.campaign_digest, BenchmarkCampaignReport)
    ledger = _resolve(
        repo, "operation_ledger", report.operation_ledger_digest or "", AssessmentOperationLedger
    )
    charges = {item.operation_id: item for item in ledger.operations}
    expected = {
        (case.case_id, route.route_id, condition, rep)
        for case in plan.suite.cases
        for route in plan.suite.routes
        for condition in plan.suite.conditions
        for rep in range(plan.suite.repetitions)
    }
    if (
        binding.plan_id != plan.plan_id
        or binding.source_digest != original_source
        or ledger.plan_id != plan.plan_id
        or len(charges) != len(ledger.operations)
        or any(entry.elapsed_seconds is None for entry in charges.values())
        or not campaign.trials
        or len(expected) != len(campaign.trials)
        or expected
        != {
            (trial.case_id, trial.route_id, trial.condition, trial.repetition)
            for trial in campaign.trials
        }
    ):
        raise ConfigurationError(
            "managed campaign does not match its retained source, trial positions or accounting"
        )
    request = RecipeMaterializationRequest(
        **{
            key: getattr(plan, key)
            for key in (
                "subject_digest",
                "recipe_digest",
                "mapping_digest",
                "environment_digest",
                "authorization_id",
                "definition_digests",
            )
        },
        seed=0,
    )
    refs = {}
    for trial in campaign.trials:
        if (
            len(trial.receipt_ids) != 1
            or trial.status != "success"
            or len(trial.case_validation) != 1
            or trial.retry_fallback_count != 0
            or trial.failure_category not in {None, "task_failure"}
            or trial.route_fingerprint != plan.route_fingerprints.get(trial.route_id)
        ):
            raise ConfigurationError("managed trial lacks one completed, protected result")
        grade = trial.case_validation[0]
        if (
            grade.kind != "callback"
            or grade.trust != "verified"
            or type(grade.valid) is not bool
            or grade.valid != trial.valid
            or grade.quality_score != int(grade.valid)
        ):
            raise ConfigurationError("managed trial lacks a protected binary grade")
        charge = _settled(repo, trial.trial_id)
        receipt, journal = campaign_receipt_and_journal(
            repo, report_ref, trial.receipt_ids[0], plan, request
        )
        if (
            charge != charges.get(trial.trial_id)
            or charge.plan_id != plan.plan_id
            or charge.stage != "trial"
            or charge.reserved.max_model_turns != 1
            or receipt.execution_success is not True
            or journal is None
            or not journal.complete
            or journal.events[-1].kind != "execution.completed"
        ):
            raise ConfigurationError("managed receipt and settled trial charge do not match")
        refs[trial.trial_id] = content_digest(receipt)
    return plan, campaign.trials, refs


def _scheduled_report(
    repo: AssessmentRepository,
    report_ref: str,
    original_source: str,
    revision: str,
    adapter: str,
    turns: int,
) -> tuple[str, dict[str, str]]:
    from aeep.assessment.scheduling import require_scheduler

    from .ase_scheduler import SchedulerObservation

    plan, trials, refs = _completed_trials(repo, report_ref, original_source)
    if plan.scheduler_digest is None or len(trials) != turns or not all(t.valid for t in trials):
        raise ConfigurationError("retained scheduler journey differs from the reviewed diagnostic")
    definition = require_scheduler(repo, plan.scheduler_digest)
    observation = SchedulerObservation.model_validate(
        repo.get("scheduler_observation", plan.plan_id)
    )
    operation = plan.plan_id + ":external-scheduler"
    receipt, charge = _receipt(
        repo,
        OperationLink(operation_id=operation, receipt_ref=observation.process_receipt_ref),
        kind="scheduler_receipt",
    )
    journal = ExecutionEvidence.model_validate(receipt.metadata.get("execution_evidence"))
    expected_slots = {str(i) for i in range(turns)}
    elapsed = charge.elapsed_seconds
    if elapsed is None:
        raise ConfigurationError("scheduler exclusive interval is unknown")
    charged_resources = receipt.actual_resources.model_copy(update={"latency_ms": elapsed * 1000})
    if (
        definition.adapter_id != adapter
        or definition.source_revision != revision
        or observation.definition_ref != plan.scheduler_digest
        or set(observation.trial_refs) != expected_slots
        or set(observation.trial_refs.values()) != {content_digest(trial) for trial in trials}
        or set(observation.grade_summaries) != expected_slots
        or any(
            summary != {"passed": 1, "failed": 0, "total": 1, "pass_rate": 1.0, "skipped": 0}
            for summary in observation.grade_summaries.values()
        )
        or receipt.metadata.get("scheduler_definition") != plan.scheduler_digest
        or receipt.metadata.get("upstream_timing_excluded") is not True
        or journal.digest() != receipt.metadata.get("execution_evidence_digest")
        or journal.attempt_id != operation
        or not journal.complete
        or journal.events[-1].kind != "execution.completed"
        or charge.plan_id != plan.plan_id
        or charge.stage != "external_scheduler"
        or charge.reserved.max_model_turns != 0
        or charge.resources != charged_resources
    ):
        raise ConfigurationError("scheduler evidence lacks a settled matching protected diagnostic")
    return observation.process_receipt_ref, refs


def _skillrank(
    repo: AssessmentRepository, proof: SkillRankProof, evidence: StackReceiptEvidence
) -> dict[str, str]:
    from aeep.assessment.scheduling import SKILLRANK_DIAGNOSTIC

    from .workflow_accounting import WorkflowAccountingDefinition, WorkflowOperationBinding
    from .workflow_catalog import CatalogRuntimeDefinition, WorkflowCatalogRecord

    with closing(open_store(proof.catalog_store)) as store:
        catalog = AssessmentRepository(store)
        records = []
        for mode, ref in (("search", proof.search_ref), ("show", proof.show_ref)):
            observation = _resolve(catalog, "toolkit_workflow_catalog", ref, WorkflowCatalogRecord)
            runtime = _resolve(
                catalog,
                "toolkit_catalog_runtime",
                observation.definition_ref,
                CatalogRuntimeDefinition,
                reviewed=True,
            )
            receipt, charge = _receipt(
                catalog,
                OperationLink(
                    operation_id=observation.operation_id, receipt_ref=observation.receipt_ref
                ),
                kind="toolkit_component_receipt",
            )
            _settled_journal(catalog, observation.execution_evidence_ref, observation.operation_id)
            wrapper = WorkflowOperationBinding.model_validate(
                catalog.get("toolkit_workflow_operation", observation.wrapper_operation_id)
            )
            scope = _resolve(
                catalog,
                "toolkit_workflow_accounting",
                wrapper.definition_ref,
                WorkflowAccountingDefinition,
                reviewed=True,
            )
            _settled(catalog, observation.wrapper_operation_id)
            if (
                runtime.source_revision != evidence.source_revision
                or observation.implementation_source != proof.catalog_source
                or scope.source_digest != proof.catalog_source
                or observation.mode != mode
                or observation.status != "completed"
                or observation.catalog_sha256 != runtime.catalog.sha256
                or receipt.executor_id != "toolkit.skillrank-catalog"
                or receipt.metadata.get("query_sha256") != observation.query_sha256
                or receipt.metadata.get("definition_ref") != observation.definition_ref
                or receipt.metadata.get("cleanup_verified") is not True
                or not observation.cleanup_verified
                or charge.plan_id != observation.request_plan_id
                or charge.stage != "workflow_catalog"
                or charge.reserved.max_model_turns != 0
                or charge.resources != receipt.actual_resources
            ):
                raise ConfigurationError("catalog evidence lacks a matching settled upstream query")
            _file(runtime.catalog)
            records.append(observation)
        search, show = records
        if (
            search.definition_ref != show.definition_ref
            or search.binary_sha256 != show.binary_sha256
            or search.installation_ref != show.installation_ref
        ):
            raise ConfigurationError("SkillRank search and show came from different installations")
    scheduler, _ = _scheduled_report(
        repo,
        proof.diagnostic_report_ref,
        evidence.original_source,
        evidence.source_revision,
        SKILLRANK_DIAGNOSTIC,
        2,
    )
    return {"search_show": show.receipt_ref, "bounded_diagnostic_evaluation": scheduler}


def _managed(repo: AssessmentRepository, proof: ManagedProof, source: str) -> dict[str, str]:
    from aeep.assessment.recovery import RecoveryRecord

    plan, _, receipts = _completed_trials(repo, proof.report_ref, source)
    report = _resolve(repo, "report", proof.report_ref, AssessmentReport)
    ledger = _resolve(
        repo, "operation_ledger", report.operation_ledger_digest or "", AssessmentOperationLedger
    )
    recovery = _resolve(repo, "recovery", proof.recovery_ref, RecoveryRecord)
    audit = json.loads(_file(proof.recovery_audit))
    with repo.store._lock:
        job = repo.store._connection.execute(
            "SELECT state, plan_id, report_id FROM assessment_jobs WHERE id=?",
            (recovery.assessment_id,),
        ).fetchone()
    if (
        plan.scheduler_digest is not None
        or len(receipts) != 1
        or job is None
        or job[0] != "indeterminate"
        or job[2] is not None
    ):
        raise ConfigurationError(
            "managed workflow or stopped recovery differs from its original job"
        )
    for charge in ledger.operations:
        if charge != _settled(repo, charge.operation_id):
            raise ConfigurationError("managed workflow accounting changed")
    stopped_plan = _resolve(repo, "plan", content_digest(repo.get("plan", job[1])), AssessmentPlan)
    anchor = AssessmentRunBinding.model_validate(repo.get("run_binding", stopped_plan.plan_id))
    settled = _settled(repo, recovery.assessment_id + ":report")
    findings = audit["unused_report_reservation_settled_from_verified_unstarted_body"]
    if (
        stopped_plan.scheduler_digest is not None
        or anchor.plan_id != stopped_plan.plan_id
        or anchor.source_digest != proof.recovery_source
        or audit["recovery"] != recovery.model_dump(mode="json")
        or audit["all_operations_complete"] is not True
        or audit["no_invocation_retried_or_model_allowance_refunded"] is not True
        or audit["all_owned_workers_graders_absent"] is not True
        or findings["recovery_record_digest"] != proof.recovery_ref
        or findings["source_digest"] != proof.recovery_source
        or findings["operation_id"] != settled.operation_id
        or findings["actual_report_not_created"] is not True
        or findings["report_body_started"] is not False
        or settled.plan_id != stopped_plan.plan_id
        or settled.stage != "report_generation"
        or settled.elapsed_seconds != 0
        or settled.reserved.max_operations != 1
    ):
        raise ConfigurationError("managed recovery did not preserve its original job and allowance")
    recovered = repo.operation_ledger(stopped_plan.plan_id)
    if any(item.elapsed_seconds is None for item in recovered.operations):
        raise ConfigurationError("stopped managed job still has unresolved accounting")
    return {
        "managed_workflow": next(iter(receipts.values())),
        "recovery_accounting": proof.recovery_ref,
    }


def _skillsbench(
    repo: AssessmentRepository, proof: SkillsBenchProof, revision: str
) -> dict[str, str]:
    domain_tasks = {
        "document_data": {"sales-pivot-analysis", "invoice-fraud-detection", "exceltable-in-ppt"},
        "software_engineering": {
            "spring-boot-jakarta-migration",
            "react-performance-debugging",
            "llm-prefix-cache-replay",
        },
    }
    expected = set().union(*domain_tasks.values())
    if set(proof.runs) != expected:
        raise ConfigurationError("SkillsBench readiness requires all six selected protected tasks")
    task_receipts = {}
    for task, item in proof.runs.items():
        plan, trials, refs = _completed_trials(repo, item.report_ref, item.original_source)
        if len(trials) != 1 or trials[0].case_id != task or plan.scheduler_digest is not None:
            raise ConfigurationError("SkillsBench result belongs to a different task or evaluator")
        (case,) = plan.suite.cases
        recipe = _resolve(repo, "recipe", plan.recipe_digest, RecipeDefinition)
        inputs = case.action.input
        if (
            not isinstance(inputs, dict)
            or inputs.get("task_id") != task
            or recipe.generator_config.get("integration_only") is not True
            or recipe.generator_config.get("official_reproduction") is not False
            or recipe.extension is None
            or recipe.extension.grader is None
        ):
            raise ConfigurationError("SkillsBench task lacks the original protected recipe")
        pack = BenchmarkPack.model_validate_json(_file(item.pack))
        if (
            pack.pack_id != "skillsbench"
            or pack.source.revision != revision
            or inputs.get("benchmark_pack_sha256") != content_digest(pack.model_dump(mode="json"))
            or pack.task(task).domain.replace("-", "_") not in domain_tasks
            or task not in domain_tasks[pack.task(task).domain.replace("-", "_")]
        ):
            raise ConfigurationError("SkillsBench task source or protected pack differs")
        task_receipts[task] = refs[trials[0].trial_id]

    with closing(open_store(proof.verifier_store)) as store:
        grading = AssessmentRepository(store)
        if set(proof.verifiers) != {"sales-pivot-analysis", "spring-boot-jakarta-migration"}:
            raise ConfigurationError("SkillsBench verifier proof requires both domain controls")
        for task, control in proof.verifiers.items():
            review = json.loads(_file(control.review))
            if (
                review.get("source_revision", review.get("revision")) != revision
                or review.get("ledger") != proof.verifier_store
                or review.get("task_id", task) != task
            ):
                raise ConfigurationError(
                    "SkillsBench grading control differs from its reviewed source"
                )
            for name, link, file in (
                ("reference", control.reference, control.reference_result),
                ("missing", control.negative, control.negative_result),
            ):
                verdict = json.loads(_file(file))
                receipt, charge = _receipt(grading, link)
                if (
                    receipt.executor_id
                    != (
                        "skillsbench.sales-reference"
                        if task == "sales-pivot-analysis"
                        else "skillsbench.spring-reference"
                    )
                    or link.operation_id != charge.plan_id + ":" + name + "-start"
                    or receipt.metadata.get("review_sha256") != control.review.sha256
                    or charge.reserved.max_model_turns != 0
                    or charge.resources != receipt.actual_resources
                    or verdict.get("upstream_binary_reward") != (1 if name == "reference" else 0)
                    or verdict.get("pytest_exit_code") != (0 if name == "reference" else 1)
                    or not set(verdict["selected_ids"]) == set(verdict["native"]["statuses"])
                ):
                    raise ConfigurationError(
                        "SkillsBench retained protected reference or rejection differs"
                    )
                _settled_journal(
                    grading, receipt.metadata["execution_evidence_ref"], link.operation_id
                )
    return {
        "document_data": task_receipts["sales-pivot-analysis"],
        "software_engineering": task_receipts["spring-boot-jakarta-migration"],
        "protected_verifiers": proof.verifiers["sales-pivot-analysis"].reference.receipt_ref,
    }


def _sdk(proof: SDKProof, evidence: StackReceiptEvidence) -> dict[str, str]:
    review = json.loads(_file(proof.review))
    result = json.loads(_file(proof.result))
    graph = evidence.component == "langgraph"
    sdk, version = ("langgraph", "1.2.14") if graph else ("agent-framework-core", "1.21.0")
    checks = (
        (
            "conditional_execution",
            "loop_ceiling",
            "interrupt_and_resume",
            "lost_checkpoint_and_denied_dispatch",
        )
        if graph
        else (
            "real_sdk_successor_consumption",
            "command_failure_stops_successors",
            "interruption_retains_receipt_refuses_replay",
            "separate_reviewed_continuation",
            "revoked_dispatch_denied",
        )
    )
    count = 6 if graph else 5
    receipts = result["receipts"]
    if (
        review["checkout_source"] != evidence.original_source
        or result["sdk"] != sdk
        or result["version"] != version
        or result["operations"] != count
        or result["models"] != 0
        or len(receipts) != count
        or [row["check"] for row in result["checks"]] != list(checks)
        or any(row["passed"] is not True for row in result["checks"])
    ):
        raise ConfigurationError(
            "SDK result lacks the required bounded flow and interruption observations"
        )
    with closing(open_store(proof.process_store)) as store:
        outer = store.get_receipt(proof.process_receipt_id)
        if (
            outer is None
            or content_digest(outer) != proof.process_receipt_ref
            or outer.execution_success is not True
            or outer.executor_id
            != ("toolkit.langgraph-sdk" if graph else "toolkit.current-sdk-framework")
            or outer.metadata.get("review_sha256") != proof.review.sha256
        ):
            raise ConfigurationError("SDK result is missing the reviewed original process receipt")

    with closing(open_store(proof.step_store)) as store:
        repo = AssessmentRepository(store)
        operations = set()
        for index, row in enumerate(receipts):
            ref = row if graph else row["ref"]
            receipt = _resolve(repo, "toolkit_integration_receipt", ref, ExecutionReceipt)
            key = receipt.decision_id.removeprefix("langgraph-" if graph else "framework-")
            charge = _settled(repo, key)
            journal = ExecutionEvidence.model_validate(receipt.metadata["execution_evidence"])
            succeeded = graph or index != 2
            terminal = "execution.completed" if succeeded else "execution.failed"
            if (
                repo.store.get_receipt(receipt.receipt_id) != receipt
                or receipt.metadata.get("review_sha256") != proof.review.sha256
                or receipt.execution_success is not succeeded
                or (
                    not graph
                    and (
                        row["key"] != key
                        or row["receipt_id"] != receipt.receipt_id
                        or row["succeeded"] is not succeeded
                    )
                )
                or journal.attempt_id != key
                or journal.digest() != receipt.metadata.get("execution_evidence_digest")
                or not journal.complete
                or journal.events[-1].kind != terminal
                or charge.stage != "sdk_approved_step"
                or charge.reserved.max_model_turns != 0
                or charge.resources != receipt.actual_resources
            ):
                raise ConfigurationError("SDK step receipt, interruption or accounting differs")
            operations.add(key)
        if len(operations) != count:
            raise ConfigurationError("SDK readiness repeats an observed step")
        plans = {_settled(repo, operation).plan_id for operation in operations}
        if len(plans) != 1:
            raise ConfigurationError("SDK proof combines separate attempts")
        ledger = AssessmentOperationLedger.model_validate(repo.get("operation_ledger", plans.pop()))
        if set(item.operation_id for item in ledger.operations) != operations:
            raise ConfigurationError("SDK recorded ledger differs from the observed steps")
    if graph:
        return {"conditional_loop": receipts[0], "interruption_recovery": receipts[-1]}
    return {"approved_workflow": receipts[0]["ref"], "interruption_accounting": receipts[-1]["ref"]}


def _proposal(
    repo: AssessmentRepository, proof: ProposalProof, evidence: StackReceiptEvidence
) -> dict[str, str]:
    component = evidence.component
    review = json.loads(_file(proof.review))
    result = json.loads(_file(proof.result))
    validator, charge = _receipt(repo, proof.validator)
    operation = f"{component}-managed-proposal-20261106:turn"
    with repo.store._lock:
        rows = repo.store._connection.execute(
            "SELECT digest FROM assessment_records WHERE kind='planning_receipt' AND "
            "json_extract(payload_json,'$.action_id')=?",
            (operation,),
        ).fetchall()
    if len(rows) != 1:
        raise ConfigurationError("proposal proof requires one original managed reply")
    turn = _resolve(repo, "planning_receipt", rows[0][0], ExecutionReceipt)
    turn_charge = _settled(repo, operation)
    _settled_journal(
        repo, validator.metadata["execution_evidence_ref"], proof.validator.operation_id
    )
    if (
        review["source_sha256"] != evidence.original_source
        or result["review_sha256"] != proof.review.sha256
        or result["provider_reply_validated"] is not True
        or result["stack_executed"] is not False
        or result["accounting_settled"] is not True
        or result["proxy_restored_stopped"] is not True
        or result["model_turns_observed"] != 1
        or turn.action_id != operation
        or turn.status != "success"
        or turn.schema_valid is not True
        or turn.executor_id != f"{component}-proposal.control"
        or turn.metadata.get("actual_model") != review["model"]
        or turn.metadata.get("worker_cleanup_confirmed") is not True
        or turn.metadata.get("tool_call_count") != 0
        or turn.metadata.get("model_turn_count") != 1
        or turn_charge.reserved.max_model_turns != 1
        or turn_charge.accounting != turn.accounting
        or validator.executor_id != f"{component}.offline-reply"
        or validator.metadata.get("local_fixture") is not False
        or validator.metadata.get("request_sha256") != review["request_sha256"]
        or charge.stage != f"{component}_reply_validation"
        or charge.reserved.max_model_turns != 0
        or charge.resources != validator.actual_resources
        or turn.ended_at > validator.started_at
    ):
        raise ConfigurationError(
            "proposal result lacks settled managed and protected upstream evidence"
        )
    if component == "evoagentx":
        if (
            result["worker_receipt_id"] != turn.receipt_id
            or result["validator_receipt_id"] != validator.receipt_id
            or result["request_sha256"] != review["request_sha256"]
            or result["reply_sha256"] != validator.metadata.get("reply_sha256")
            or result["validator_container_absent"] is not True
        ):
            raise ConfigurationError("EvoAgentX graph validation differs from the managed reply")
        return {
            "real_proposal": content_digest(turn),
            "proposal_validation": proof.validator.receipt_ref,
        }
    validation = result["validation"]
    if (
        result["receipts"] != [turn.receipt_id]
        or result["passed"] is not True
        or validation["upstream_optimizer_executed"] is not True
        or validation["upstream_experience_updated"] is not True
        or validation["status"] != "cycle_complete"
        or validation["proposal_requests"] != 1
        or validation["models_in_guest"] != 0
        or validation["generated_code_executed"] is not False
        or validation["initial_grade_sha256"] != review["initial_grade_sha256"]
        or validation["request_sha256"] != review["request_sha256"]
    ):
        raise ConfigurationError("AFlow optimization did not complete its protected calibration")
    return {
        "bounded_optimization": proof.validator.receipt_ref,
        "protected_grading_accounting": proof.validator.receipt_ref,
    }


def _router(proof: RouterProof, source: str) -> dict[str, str]:
    from aeep.stack_models import StackProposal

    review = json.loads(_file(proof.review))
    summary = json.loads(_file(proof.result))
    if (
        review["source"] != source
        or summary["passed"] is not True
        or summary["basic_catalog_router_inert"] is not True
        or summary["standing_activation_created"] is not False
        or summary["provider_calls"] != 0
        or summary["models"] != 0
        or summary["unreviewed_preflight_denied"] is not True
        or proof.store != str(Path(review["work"]) / "state.db")
        or len(summary["canonical_route_receipts"]) != 4
    ):
        raise ConfigurationError("optional Router execution or Essentials independence is unproven")
    with closing(open_store(proof.store)) as store:
        repo = AssessmentRepository(store)
        proposal = _resolve(
            repo, "stack_proposal", summary["proposal_digest"], StackProposal, reviewed=True
        )
        with store._lock:
            run = store._connection.execute(
                "SELECT state FROM stack_runs WHERE proposal_id=?", (proposal.proposal_id,)
            ).fetchone()
        if run is None or run[0] != "complete":
            raise ConfigurationError("optional Router stack did not finish")
        observed = set()
        for row in summary["canonical_route_receipts"]:
            receipt = store.get_receipt(row["receipt_id"])
            if (
                receipt is None
                or content_digest(receipt) != row["receipt_sha256"]
                or receipt.executor_id != row["executor"]
                or receipt.execution_success is not True
                or receipt.status != "success"
                or receipt.accounting.model_usage
            ):
                raise ConfigurationError("optional Router trace differs from its real node receipt")
            journal_ref = receipt.metadata.get("execution_evidence_digest")
            journal = _resolve(repo, "execution_evidence", journal_ref or "", ExecutionEvidence)
            if not journal.complete or journal.events[-1].kind != "execution.completed":
                raise ConfigurationError("optional Router node lacks a complete journal")
            observed.add(receipt.executor_id)
        if len(observed) != 4 or observed != {c.executor_id for c in proposal.components}:
            raise ConfigurationError("optional Router receipts do not cover the reviewed stack")
    return {
        "optional_execution": summary["canonical_route_receipts"][-1]["receipt_sha256"],
        "essentials_independence": proof.result.sha256,
    }
