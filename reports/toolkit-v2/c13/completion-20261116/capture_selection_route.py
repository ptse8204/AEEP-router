"""Capture an approved study decision before the existing task runner can use it."""

import hashlib
import time
from pathlib import Path
from typing import Self

from pydantic import Field, model_validator

from aeep import router as router_module
from aeep.assessment.models import (
    AssessmentLimits,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.errors import ConfigurationError
from aeep.models import (
    ActionRequest,
    ExecutionReceipt,
    RouteDecision,
    StrictModel,
    UtcDateTime,
    utc_now,
)
from aeep.router import Router
from aeep_toolkit.models import Digest, Identifier, Measure
from aeep_toolkit.selection import SelectionCase, SelectionDecision

SCOPE = "toolkit_selection_route_scope"
CAPTURE = "toolkit_selection_route_capture"
STAGE = "selection_routing"


class SelectionRouteScope(StrictModel):
    study_ref: Digest
    request_id: Identifier
    policy: Identifier
    case_id: Identifier
    action_sha256: Digest
    task_sha256: Digest
    manifest_sha256: Digest
    source_sha256: Digest
    driver_sha256: Digest
    baseline_executor_id: Identifier
    candidates_by_executor: dict[Identifier, Identifier] = Field(min_length=1, max_length=24)
    reserved_seconds: int = Field(strict=True, gt=0, le=30)

    @model_validator(mode="after")
    def distinct_executors(self) -> Self:
        if self.baseline_executor_id in self.candidates_by_executor:
            raise ValueError("the baseline cannot stand in for a candidate")
        return self

    def operation_id(self) -> str:
        # Scope changes must not create another opportunity for this study slot.
        return "selection:" + content_digest(
            {"study": self.study_ref, "policy": self.policy, "case": self.case_id}
        )


class SelectionRouteCapture(StrictModel):
    scope_ref: Digest
    operation_id: Identifier
    decision_id: Identifier
    full_decision_ref: Digest
    persisted_decision_ref: Digest
    captured_at: UtcDateTime
    router_seconds: Measure


def implementation_source() -> str:
    return verification_source_digest(Path(router_module.__file__).resolve().parents[2])


def load_scope(repo: AssessmentRepository, ref: str) -> SelectionRouteScope:
    scope = SelectionRouteScope.model_validate(repo.get(SCOPE, ref))
    if content_digest(scope) != ref:
        raise ConfigurationError("selection scope does not match its reviewed digest")
    return scope


def capture_route(router: Router, scope_ref: str, action: ActionRequest) -> RouteDecision:
    """Reserve and record one local decision. Workload dispatch remains separate."""
    started = time.perf_counter()
    repo = AssessmentRepository(router.store)
    scope = load_scope(repo, scope_ref)
    request = RecipeMaterializationRequest.model_validate(
        repo.get("recipe_materialization_request", scope.request_id)
    )
    permitted = {scope.baseline_executor_id, *scope.candidates_by_executor}
    if (
        request.plan_id != scope.request_id
        or not {scope_ref, scope.study_ref} <= set(request.definition_digests)
        or content_digest(action) != scope.action_sha256
        or content_digest(action.input) != scope.task_sha256
        or set(action.constraints.allowed_executor_ids or []) != permitted
        or content_digest(router.manifest) != scope.manifest_sha256
        or router.manifest.persistence.store_action_inputs
        or router.manifest.persistence.store_action_context
        or implementation_source() != scope.source_sha256
        or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != scope.driver_sha256
    ):
        raise ConfigurationError("selection action, environment or reviewed scope changed")

    # Schema diagnostics can include rejected values. Reject before the Router saves them.
    compatible, errors = router.registry.compatible(action.capability, action.input)
    if errors or {item.id for item in compatible} != permitted:
        raise ConfigurationError("selection pool does not match the frozen input and inventory")

    operation_id = scope.operation_id()
    repo.reserve(
        request,
        operation_id,
        AssessmentLimits(max_operations=1, max_elapsed_seconds=scope.reserved_seconds),
        stage=STAGE,
        require_settled_plan=True,
    )
    # No remote discovery, protected grading or task execution is called here.
    decision = router.route(action)
    stored = repo.store.get_decision(decision.decision_id)
    if (
        stored is None
        or stored.action.input != {"__aeep_redacted__": True}
        or pool_signature(stored) != pool_signature(decision)
        or decision.policy != stored.policy
        or decision.action.action_id != action.action_id
        or decision.action.capability != action.capability
        or content_digest(decision.action.input) != scope.task_sha256
    ):
        raise ConfigurationError(
            "local selection decision could not be reconciled; inspect its reservation"
        )

    capture = SelectionRouteCapture(
        scope_ref=scope_ref,
        operation_id=operation_id,
        decision_id=decision.decision_id,
        full_decision_ref=content_digest(decision),
        persisted_decision_ref=content_digest(stored),
        captured_at=utc_now(),
        router_seconds=decision.routing_overhead_ms / 1000,
    )
    repo.put(CAPTURE, operation_id, capture)
    elapsed = time.perf_counter() - started
    repo.finish_operation(operation_id, elapsed_seconds=elapsed)
    if elapsed > scope.reserved_seconds:
        raise ConfigurationError("routing exceeded the reviewed time reservation")
    repo.authorize(request)
    # A blocked route is durable evidence of a stop. It cannot become an abstention.
    require_selected(decision, permitted)
    return decision


def pool_signature(decision: RouteDecision) -> dict[str, object]:
    return {
        "decision_id": decision.decision_id,
        "created_at": decision.created_at,
        "selected_executor_id": decision.selected_executor_id,
        "action_id": decision.action.action_id,
        "capability": decision.action.capability,
        "routing_overhead_ms": decision.routing_overhead_ms,
        "candidates": [(route.executor_id, route.feasible) for route in decision.candidates],
    }


def require_selected(decision: RouteDecision, permitted: set[str]) -> str:
    feasible = {route.executor_id for route in decision.candidates if route.feasible}
    selected = decision.selected_executor_id
    if selected is None or selected not in feasible or not feasible <= permitted:
        raise ConfigurationError("selection is blocked or selected outside its reviewed pool")
    return selected


def resolve_route(
    repo: AssessmentRepository,
    scope_ref: str,
    *,
    study_ref: str,
    case: SelectionCase,
    receipt_id: str | None = None,
) -> tuple[SelectionDecision, str | None]:
    """Read the settled decision and an optional matching execution receipt digest."""
    scope = load_scope(repo, scope_ref)
    if (scope.study_ref, scope.case_id, scope.task_sha256) != (
        study_ref,
        case.case_id,
        case.task_sha256,
    ):
        raise ConfigurationError("selection capture belongs to another frozen task or study")
    operation_id = scope.operation_id()
    capture = SelectionRouteCapture.model_validate(repo.get(CAPTURE, operation_id))
    decision = repo.store.get_decision(capture.decision_id)
    charges = [
        item
        for item in repo.operation_ledger(scope.request_id).operations
        if item.operation_id == operation_id
    ]
    if (
        capture.scope_ref != scope_ref
        or capture.operation_id != operation_id
        or decision is None
        or content_digest(decision) != capture.persisted_decision_ref
        or decision.action.input != {"__aeep_redacted__": True}
        or decision.created_at > capture.captured_at
        or len(charges) != 1
        or charges[0].stage != STAGE
        or charges[0].elapsed_seconds is None
        or not capture.router_seconds <= charges[0].elapsed_seconds <= scope.reserved_seconds
        or charges[0].reserved
        != AssessmentLimits(max_operations=1, max_elapsed_seconds=scope.reserved_seconds)
    ):
        raise ConfigurationError("selection capture or settled accounting is missing or changed")
    selected = require_selected(
        decision, {scope.baseline_executor_id, *scope.candidates_by_executor}
    )
    linked = None
    if receipt_id is not None:
        receipt = repo.store.get_receipt(receipt_id)
        if not matches(receipt, decision, selected, capture.captured_at):
            raise ConfigurationError("execution receipt is outside the captured selection")
        assert receipt is not None
        linked = content_digest(receipt)
    return SelectionDecision(
        policy=scope.policy,
        case_id=scope.case_id,
        selected=None
        if selected == scope.baseline_executor_id
        else scope.candidates_by_executor[selected],
        decision_ref=capture.full_decision_ref,
        decision_wall_seconds=charges[0].elapsed_seconds,
    ), linked


def matches(
    receipt: ExecutionReceipt | None,
    decision: RouteDecision,
    selected: str,
    captured_at: UtcDateTime,
) -> bool:
    return (
        receipt is not None
        and receipt.decision_id == decision.decision_id
        and receipt.action_id == decision.action.action_id
        and receipt.capability == decision.action.capability
        and receipt.executor_id == selected
        and captured_at <= receipt.started_at <= receipt.ended_at
    )
