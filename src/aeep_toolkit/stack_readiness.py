"""Resolve the operator's stack-completion gate from existing canonical records.

This module never installs, probes, reviews, starts a service or grants authority.
Functional observations must come from reviewed, charged upstream checks. Their
semantic adequacy remains the responsibility of the exact reviewed check code.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, TypeVar

from pydantic import Field, model_validator

from aeep.assessment.boundary import BoundaryProbe, BoundaryProbeDefinition
from aeep.assessment.identity import verify_dependencies
from aeep.assessment.models import AssessmentPlan, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.errors import ConfigurationError
from aeep.execution import ExecutionEvidence
from aeep.models import StrictModel

from .models import Digest, Identifier

REQUIRED_CHECKS: dict[str, tuple[str, ...]] = {
    "agent-skill-eval": ("controlled_dispatch", "grading_accounting_cleanup"),
    "aeep-evaluator": ("managed_workflow", "recovery_accounting"),
    "waza": ("real_agent", "grading_accounting_cleanup"),
    "skillrank": ("search_show", "bounded_diagnostic_evaluation"),
    "skillsbench": ("document_data", "software_engineering", "protected_verifiers"),
    "mcpmark": ("reference_task", "state_cleanup"),
    "mcp-universe": ("reference_task", "state_cleanup"),
    "skill-scanner": ("static_scan", "findings_and_failures"),
    "toolhive": ("launch_invoke", "permissions_stop"),
    "semantic-conventions": ("receipt_export", "privacy_disable"),
    "langfuse": ("ingestion_linkage", "export_disable"),
    "langgraph": ("conditional_loop", "interruption_recovery"),
    "evoagentx": ("real_proposal", "proposal_validation"),
    "aflow": ("bounded_optimization", "protected_grading_accounting"),
    "agent-framework": ("approved_workflow", "interruption_accounting"),
    "aeep-router": ("optional_execution", "essentials_independence"),
    "github-sponsors": ("source_attribution", "authorized_link"),
    "workflow-document-data": ("ordinary_cli", "canonical_report"),
    "workflow-software-engineering": ("ordinary_cli", "canonical_report"),
}


class IntegrationDefinition(StrictModel):
    schema_version: Literal["aeep.toolkit.integration-definition.v1"] = (
        "aeep.toolkit.integration-definition.v1"
    )
    component: Identifier
    source_revision: str = Field(pattern=r"^(?:[a-f0-9]{40}|[a-f0-9]{64})$")
    implementation_source: Digest
    runtime_digest: Digest
    executable_dependencies: dict[str, Digest] = Field(min_length=1, max_length=2048)
    probe_definitions: dict[Identifier, Digest]

    @model_validator(mode="after")
    def required_checks(self) -> IntegrationDefinition:
        if self.component not in REQUIRED_CHECKS or set(self.probe_definitions) != set(
            REQUIRED_CHECKS[self.component]
        ):
            raise ValueError("integration requires every check in its selected functional role")
        return self


class IntegrationEvidence(StrictModel):
    schema_version: Literal["aeep.toolkit.integration-evidence.v1"] = (
        "aeep.toolkit.integration-evidence.v1"
    )
    definition_ref: Digest
    probe_refs: dict[Identifier, Digest]


class StackCompletion(StrictModel):
    schema_version: Literal["aeep.toolkit.stack-completion.v1"] = "aeep.toolkit.stack-completion.v1"
    implementation_source: Digest
    components: dict[Identifier, Digest]

    @model_validator(mode="after")
    def complete_inventory(self) -> StackCompletion:
        if set(self.components) != set(REQUIRED_CHECKS):
            raise ValueError(
                "stack completion requires every integration and both composed workflows"
            )
        if len(set(self.components.values())) != len(self.components):
            raise ValueError("one component evidence record cannot stand in for another")
        return self


class EngineeringRunReview(StrictModel):
    """An exact, finite bootstrap check; it is never a value-trial exemption."""

    schema_version: Literal["aeep.toolkit.engineering-run.v1"] = "aeep.toolkit.engineering-run.v1"
    purpose: Literal["stack_integration_only"] = "stack_integration_only"
    plan_digest: Digest
    implementation_source: Digest
    scope_request_id: Identifier
    case_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=6)
    maximum_model_turns: int = Field(strict=True, ge=1, le=12)


def require_engineering_run(
    repository: AssessmentRepository, digest: str, *, plan: AssessmentPlan, source_digest: str
) -> EngineeringRunReview:
    review = _resolve(
        repository, "toolkit_engineering_run", digest, EngineeringRunReview, reviewed=True
    )
    request = RecipeMaterializationRequest.model_validate(
        repository.get("recipe_materialization_request", review.scope_request_id)
    )
    experiment = plan.comparison.experiment if plan.comparison else None
    if (
        review.plan_digest != content_digest(plan)
        or review.implementation_source != source_digest
        or request.plan_id != review.scope_request_id
        or digest not in request.definition_digests
        or not set(plan.definition_digests) <= set(request.definition_digests)
        or any(
            getattr(request, key) != getattr(plan, key)
            for key in (
                "subject_digest",
                "recipe_digest",
                "mapping_digest",
                "environment_digest",
                "authorization_id",
            )
        )
        or experiment is None
        or experiment.stage != "qualification"
        or experiment.exposure != "required"
        or experiment.challengers
        or plan.suite.repetitions != 1
        or len(plan.suite.conditions) != 1
        or plan.suite.warmup_cases
        or not 1 <= len(plan.suite.cases) <= 6
        or len(plan.suite.routes) not in {1, 2}
        or {route.executor_id for route in plan.suite.routes}
        != ({plan.candidate_id} if len(plan.suite.routes) == 1 else {plan.candidate_id, plan.baseline_id})
        or any(case.split.value != "qualification" for case in plan.suite.cases)
        or tuple(case.case_id for case in plan.suite.cases) != review.case_ids
        or review.maximum_model_turns != len(plan.suite.cases) * len(plan.suite.routes)
    ):
        raise ConfigurationError(
            "engineering scope is not an exact bounded required-use qualification check"
        )
    # Reuses the existing grant: this record neither creates authority nor resets counters.
    repository.authorize(request)
    return review


Model = TypeVar("Model", bound=StrictModel)


def _resolve(
    repository: AssessmentRepository,
    kind: str,
    digest: str,
    model: type[Model],
    *,
    reviewed: bool = False,
) -> Model:
    value = model.model_validate(repository.get(kind, digest))
    if content_digest(value) != digest:
        raise ConfigurationError("canonical stack evidence digest differs")
    if reviewed:
        with repository.store._lock:
            row = repository.store._connection.execute(
                "SELECT revoked FROM assessment_reviews WHERE digest=?", (digest,)
            ).fetchone()
        if row is None or row[0]:
            raise ConfigurationError("stack definition is unreviewed or revoked")
    return value


def source_revisions(source_digest: str) -> dict[str, str]:
    entries = json.loads(Path(__file__).with_name("catalog.json").read_text(encoding="utf-8"))
    result = {entry["id"]: entry["source_revision"] for entry in entries}
    result.update(
        {
            key: source_digest
            for key in REQUIRED_CHECKS
            if key.startswith("workflow-") or key == "github-sponsors"
        }
    )
    return result


def require_integration(
    repository: AssessmentRepository, digest: str, *, component: str, source_digest: str
) -> IntegrationEvidence:
    evidence = _resolve(repository, "toolkit_integration_evidence", digest, IntegrationEvidence)
    definition = _resolve(
        repository,
        "toolkit_integration_definition",
        evidence.definition_ref,
        IntegrationDefinition,
        reviewed=True,
    )
    if (
        definition.component != component
        or definition.implementation_source != source_digest
        or definition.source_revision != source_revisions(source_digest)[component]
        or set(evidence.probe_refs) != set(definition.probe_definitions)
    ):
        raise ConfigurationError("integration source, role or required check set differs")
    verify_dependencies(definition.executable_dependencies)
    for name, probe_ref in evidence.probe_refs.items():
        probe = _resolve(repository, "boundary_probe", probe_ref, BoundaryProbe)
        check = _resolve(
            repository,
            "boundary_probe_definition",
            definition.probe_definitions[name],
            BoundaryProbeDefinition,
            reviewed=True,
        )
        expected = {
            "component": component,
            "check": name,
            "source_revision": definition.source_revision,
            "implementation_source": source_digest,
            "mode": "upstream_functional",
        }
        if (
            check.name != component + "." + name
            or probe.name != check.name
            or probe.implementation_digest != content_digest(check)
            or probe.worker_digest != definition.runtime_digest
            or any(check.expected.get(key) != value for key, value in expected.items())
            or len(check.expected) <= len(expected)
            or any(
                type(probe.observed.get(key)) is not type(value) or probe.observed.get(key) != value
                for key, value in check.expected.items()
            )
        ):
            raise ConfigurationError(
                "functional check does not match its reviewed upstream observation"
            )
        journal = _resolve(
            repository, "execution_evidence", probe.execution_evidence_digest, ExecutionEvidence
        )
        if (
            not journal.complete
            or not journal.events
            or journal.events[-1].kind != "execution.completed"
            or journal.boundary_digest != definition.runtime_digest
            or not any(
                event.kind == "artifact.created"
                and event.source_id == "probe-result"
                and event.evidence_ref == content_digest(probe.observed)
                for event in journal.events
            )
        ):
            raise ConfigurationError(
                "functional observation has no complete bound execution journal"
            )
        with repository.store._lock:
            operation = repository.store._connection.execute(
                "SELECT state FROM assessment_operations WHERE id=?", (journal.attempt_id,)
            ).fetchone()
        if operation is None or operation[0] != "complete":
            raise ConfigurationError("functional check accounting is absent or unresolved")
    return evidence


def require_stack_complete(
    repository: AssessmentRepository, digest: str | None, *, source_digest: str
) -> StackCompletion:
    if digest is None:
        raise ConfigurationError(
            "new comparisons are paused until the complete upstream stack is verified"
        )
    record = _resolve(
        repository, "toolkit_stack_completion", digest, StackCompletion, reviewed=True
    )
    if record.implementation_source != source_digest:
        raise ConfigurationError("stack completion belongs to another implementation source")
    for component, reference in record.components.items():
        require_integration(repository, reference, component=component, source_digest=source_digest)
    return record


def checklist() -> dict[str, Any]:
    return {
        "policy": "all_upstream_integrations_before_comparisons",
        "components": [
            {
                "component": name,
                "required_checks": list(checks),
                "functional_status": "NOT_RESOLVED",
            }
            for name, checks in REQUIRED_CHECKS.items()
        ],
        "comparison_dispatch": "BLOCKED_WITHOUT_CANONICAL_CURRENT_STACK_COMPLETION",
        "candidate_usefulness": "NOT_ASSESSED",
        "selection_usefulness": "NOT_ASSESSED",
        "notice": "Requirements only. No runtime, database, installation, service or model was inspected or started.",
    }
