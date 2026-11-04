"""Optional operator accounting over the existing grant, ledger and receipt store."""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, SerializerFunctionWrapHandler, model_serializer, model_validator

from aeep.assessment.models import (
    AssessmentLimits,
    AssessmentPlan,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.errors import ConfigurationError
from aeep.models import (
    ExecutionReceipt,
    ExecutionStatus,
    ExecutorKind,
    ResourceVector,
    RouteEstimate,
    StrictModel,
    utc_now,
)
from aeep.router import Router

from .models import Digest, Identifier

WorkflowStage = Literal["plan", "prepare", "run", "report", "setup", "readiness", "remove", "scan", "catalog"]


class WorkflowAccountingDefinition(StrictModel):
    """An inert, reviewed scope; it cannot create or extend a grant."""

    schema_version: Literal["aeep.toolkit.workflow-accounting.v1", "aeep.toolkit.workflow-accounting.v2", "aeep.toolkit.workflow-accounting.v3", "aeep.toolkit.workflow-accounting.v4"] = "aeep.toolkit.workflow-accounting.v1"
    workflow_sha256: Digest
    configurations: tuple[Identifier, ...] = Field(min_length=1, max_length=16)
    operations: tuple[WorkflowStage, ...] = Field(min_length=1, max_length=9)
    source_digest: Digest
    manifest_path: str = Field(min_length=1, max_length=4096)
    manifest_sha256: Digest
    request: RecipeMaterializationRequest
    maximum_overhead_seconds: int = Field(strict=True, ge=1, le=3600)

    @model_validator(mode="after")
    def distinct_selections(self) -> WorkflowAccountingDefinition:
        if len(set(self.configurations)) != len(self.configurations) or len(set(self.operations)) != len(self.operations):
            raise ValueError("workflow accounting selections must be distinct")
        if self.schema_version.endswith('.v1') and (
            not set(self.operations) <= {"plan", "prepare", "run", "report"}
            or self.maximum_overhead_seconds > 600
        ):
            raise ValueError("lifecycle stages and larger reservations require accounting v2")
        if self.schema_version.endswith('.v2') and 'scan' in self.operations:
            raise ValueError('scanner execution requires explicit accounting v3')
        if not self.schema_version.endswith('.v4') and ('catalog' in self.operations or len(self.operations)>8):
            raise ValueError('catalog execution requires explicit accounting v4')
        return self


class WorkflowOperationBinding(StrictModel):
    definition_ref: Digest
    operation_id: str
    workflow_sha256: Digest
    configuration: str
    stage: WorkflowStage


class WorkflowPlanLink(StrictModel):
    operation_id: str
    assessment_plan_id: str
    assessment_plan_digest: Digest
    component_refs: dict[Identifier, Digest] = Field(default_factory=dict, max_length=16)

    @model_serializer(mode='wrap')
    def preserve_existing(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        value: dict[str, Any] = handler(self)
        if not self.component_refs:
            value.pop('component_refs', None)
        return value


class WorkflowMeter:
    def __init__(self, operation_id: str, definition_ref: str):
        self.operation_id, self.definition_ref = operation_id, definition_ref
        self.began, self.cpu = time.perf_counter(), time.process_time()
        self.started_at = utc_now()
        self.nested_seconds = 0.0
        self.nested_cpu = 0.0
        self.nested_active = False
        self.spans: list[dict[str, Any]] = []
        self.scope: WorkflowAccountingDefinition | None = None
        self.repository: AssessmentRepository | None = None
        self.plan_ids: list[str] = []
        self.outcome_error: str | None = None
        self.component_refs: dict[str, str] = {}
        self.component_observations: dict[str, Any] = {}

    def authorize(self) -> None:
        if self.scope is None or self.repository is None:
            raise ConfigurationError("workflow accounting scope is unavailable")
        request = self.scope.request.model_copy(update={
            "definition_digests": list(dict.fromkeys([*self.scope.request.definition_digests, self.definition_ref]))
        })
        self.repository.authorize(request)
        if verification_source_digest(Path(__file__).resolve().parents[2]) != self.scope.source_digest:
            raise ConfigurationError("workflow accounting source changed")

    def bind(self, plan: AssessmentPlan, manifest: Path | None = None) -> None:
        if self.scope is None or self.repository is None:
            raise ConfigurationError("workflow accounting scope is unavailable")
        expected = self.scope.request
        if any(getattr(plan, name) != getattr(expected, name) for name in (
            "authorization_id", "subject_digest", "recipe_digest", "mapping_digest", "environment_digest"
        )) or (manifest is not None and manifest.absolute() != Path(self.scope.manifest_path)):
            raise ConfigurationError("workflow accounting and canonical plan use different authority or definitions")
        self.repository.put("toolkit_workflow_plan_link", self.operation_id, WorkflowPlanLink(
            operation_id=self.operation_id, assessment_plan_id=plan.plan_id,
            assessment_plan_digest=content_digest(plan), component_refs=self.component_refs,
        ))
        if plan.plan_id not in self.plan_ids:
            self.plan_ids.append(plan.plan_id)

    @contextmanager
    def exclude(self, label: str) -> Iterator[None]:
        if self.nested_active:
            raise ConfigurationError("overlapping workflow accounting exclusions are unsupported")
        self.nested_active = True
        began, cpu = time.perf_counter(), time.process_time()
        try:
            yield
        finally:
            elapsed, used = time.perf_counter() - began, time.process_time() - cpu
            self.nested_seconds += elapsed
            self.nested_cpu += used
            self.spans.append({"stage": label, "wall_seconds": elapsed, "process_cpu_seconds": used})
            self.nested_active = False

    def describe(self) -> dict[str, Any]:
        return {
            **({"component_refs": self.component_refs} if self.component_refs else {}),
            "definition_ref": self.definition_ref,
            "operation_id": self.operation_id,
            "assessment_plan_ids": list(self.plan_ids),
            "ledger": "existing assessment operation_start / operation_measurement",
            "measurement_scope": "exclusive wrapper wall time and process CPU; canonical execution intervals excluded",
            "token_memory_cash_measurements": "UNKNOWN; no zero values inferred",
            "completion": "resolve the terminal operation_measurement after this command returns",
        }


_ACTIVE: ContextVar[WorkflowMeter | None] = ContextVar("aeep_workflow_meter", default=None)


def active_accounting() -> dict[str, Any] | None:
    meter = _ACTIVE.get()
    return meter.describe() if meter else None


def active_component_observations() -> dict[str, Any]:
    meter = _ACTIVE.get()
    return dict(meter.component_observations) if meter else {}


def bind_workflow_plan(plan: AssessmentPlan, manifest: Path | None = None) -> None:
    meter = _ACTIVE.get()
    if meter is not None:
        meter.bind(plan, manifest)


@contextmanager
def exclude_canonical_execution() -> Iterator[None]:
    meter = _ACTIVE.get()
    if meter is None:
        yield
    else:
        with meter.exclude("canonical_assessment_execution"):
            yield


@contextmanager
def account_workflow(
    scope_file: Path | None,
    *,
    workflow_file: Path,
    configuration: str,
    stage: WorkflowStage,
    operation_key: str | None,
    manifest: Path | None = None,
) -> Iterator[WorkflowMeter | None]:
    """Reserve before inspection/mutation. Never replay a reserved operation."""
    if scope_file is None and operation_key is None:
        yield None
        return
    if scope_file is None or operation_key is None or _ACTIVE.get() is not None:
        raise ConfigurationError("accounted workflow needs one scope and a fresh operation identity")
    from .cli import read_bytes, read_json
    from .install_runtime import canonical

    began, cpu, started_at = time.perf_counter(), time.process_time(), utc_now()
    definition = WorkflowAccountingDefinition.model_validate(read_json(scope_file))
    ref = content_digest(definition)
    # Identifier parsing rejects path-like or unbounded operation names.
    from pydantic import TypeAdapter

    key = TypeAdapter(Identifier).validate_python(operation_key)
    root = Path(__file__).resolve().parents[2]
    target = canonical(definition.manifest_path)
    if (
        configuration not in definition.configurations
        or stage not in definition.operations
        or hashlib.sha256(read_bytes(workflow_file)).hexdigest() != definition.workflow_sha256
        or hashlib.sha256(read_bytes(target)).hexdigest() != definition.manifest_sha256
        or verification_source_digest(root) != definition.source_digest
        or (manifest is not None and canonical(str(manifest.absolute())) != target)
    ):
        raise ConfigurationError("workflow accounting source, selection or manifest changed")
    router = Router.from_manifest(target)
    try:
        repository = AssessmentRepository(router.store)
        if content_digest(repository.get("toolkit_workflow_accounting", ref)) != ref:
            raise ConfigurationError("workflow accounting definition differs from its stored record")
        with router.store._lock:
            review = router.store._connection.execute(
                "SELECT revoked FROM assessment_reviews WHERE digest=?", (ref,)
            ).fetchone()
        if review is None or review[0]:
            raise ConfigurationError("workflow accounting requires current exact operator review")
        # Add the exact wrapper review to the existing atomic authority/debit
        # check. This only narrows authority; it never modifies the stored grant.
        request = definition.request.model_copy(update={
            "definition_digests": list(dict.fromkeys([*definition.request.definition_digests, ref]))
        })
        repository.authorize(request)
        operation_id = "workflow:" + request.plan_id + ":" + key
        repository.reserve(
            request, operation_id,
            AssessmentLimits(max_operations=1, max_model_turns=0,
                             max_elapsed_seconds=definition.maximum_overhead_seconds),
            stage="workflow_" + stage + "_overhead", require_settled_plan=True,
        )
        binding = WorkflowOperationBinding(
            definition_ref=ref, operation_id=operation_id,
            workflow_sha256=definition.workflow_sha256,
            configuration=configuration, stage=stage,
        )
        repository.put("toolkit_workflow_operation", operation_id, binding)
        meter = WorkflowMeter(operation_id, ref)
        meter.began, meter.cpu, meter.started_at = began, cpu, started_at
        meter.scope, meter.repository = definition, repository
        token = _ACTIVE.set(meter)
        failure = None
        try:
            yield meter
        except BaseException as error:
            failure = type(error).__name__
            raise
        finally:
            _ACTIVE.reset(token)
            failure = failure or meter.outcome_error
            drift = False
            if failure is None:
                try:
                    drift = (
                        verification_source_digest(root) != definition.source_digest
                        or hashlib.sha256(read_bytes(workflow_file)).hexdigest() != definition.workflow_sha256
                        or hashlib.sha256(read_bytes(target)).hexdigest() != definition.manifest_sha256
                    )
                except (ValueError, OSError):
                    drift = True
                if drift:
                    failure = "WorkflowSourceDrift"
            elapsed = time.perf_counter() - meter.began
            cpu = time.process_time() - meter.cpu
            resources = ResourceVector(
                latency_ms=max(0.0, elapsed - meter.nested_seconds) * 1000,
                cpu_ms=max(0.0, cpu - meter.nested_cpu) * 1000,
            )
            receipt = ExecutionReceipt(
                decision_id=operation_id, action_id=operation_id,
                capability="toolkit.workflow@1", executor_id="toolkit.workflow",
                executor_kind=ExecutorKind.PYTHON,
                status=ExecutionStatus.FAILED if failure else ExecutionStatus.SUCCESS,
                started_at=meter.started_at, ended_at=utc_now(),
                estimated=RouteEstimate(), actual_resources=resources,
                execution_success=failure is None, error_type=failure,
                metadata={
                    "workflow_accounting": meter.describe(),
                    "whole_wrapper_wall_seconds": elapsed,
                    "whole_wrapper_process_cpu_seconds": cpu,
                    "excluded_nested_intervals": meter.spans,
                    "observed_resource_dimensions": ["latency_ms", "cpu_ms"],
                    "legacy_vector_defaults_are_not_observations": True,
                    "finalization_scope": "measurement ends before receipt/ledger persistence and Router close",
                },
            )
            router.store.save_receipt(receipt)
            repository.put("toolkit_workflow_receipt", operation_id, receipt)
            repository.finish_operation(operation_id, elapsed_seconds=resources.latency_ms / 1000,
                                        resources=resources)
            if drift:
                raise ConfigurationError("workflow source changed; charges and partial outputs retained")
    finally:
        asyncio.run(router.close())
