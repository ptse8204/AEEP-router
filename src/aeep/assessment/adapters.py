"""Reviewed declarative argument and result mappings around existing executors."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, model_validator

from ..executors.base import ExecutionContext
from ..models import ExecutionStatus, RawExecution, ResourceVector, StrictModel, new_id
from ..qualification import behavior_fingerprint
from ..registry import validate_json
from ..templates import render
from ..workflow import WorkflowRequest, WorkflowStatus, pointer_get

if TYPE_CHECKING:
    from ..router import Router


class DeclarativeAdapter(StrictModel):
    input_transform: Literal["local_search_tree:1", "local_search_tree:2"] | None = None
    read_only_roots: list[str] = Field(default_factory=list)
    input_template: dict[str, Any] | None = None
    target_input_schema: dict[str, Any] | None = None
    output_pointer: str | None = None
    output_fields: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def exclusive_projection(self) -> DeclarativeAdapter:
        if self.input_transform and (not self.read_only_roots or self.input_template is not None):
            raise ValueError("local search mapping requires explicit roots and no input template")
        if any(not Path(root).is_absolute() or ".." in Path(root).parts for root in self.read_only_roots):
            raise ValueError("search mapping roots must be absolute")
        if self.output_pointer is not None and self.output_fields:
            raise ValueError("choose a root projection or named output fields")
        for pointer in [*self.output_fields.values(), *([self.output_pointer] if self.output_pointer is not None else [])]:
            if pointer and not pointer.startswith("/"):
                raise ValueError("adapter output paths must be JSON Pointers")
        return self


class WorkflowAdapter(StrictModel):
    workflow: WorkflowRequest
    case_input_bindings: dict[str, str]
    executor_fingerprints: dict[str, str]

    @model_validator(mode="after")
    def exact_routes(self) -> WorkflowAdapter:
        ids = set()
        for step in self.workflow.steps:
            allowed = step.action.constraints.allowed_executor_ids
            if allowed is None or len(allowed) != 1:
                raise ValueError("reviewed workflow steps must select exactly one executor")
            ids.add(allowed[0])
        if ids != set(self.executor_fingerprints):
            raise ValueError("workflow must bind every step executor fingerprint")
        return self


async def execute_workflow_adapter(router: Router, context: ExecutionContext) -> RawExecution:
    from ..benchmarking import BenchmarkCase, BenchmarkRoute, BenchmarkSplit, _case_workflow
    from ..errors import ConfigurationError

    adapter = WorkflowAdapter.model_validate(context.spec.config["assessment_workflow"])
    for executor_id, fingerprint in adapter.executor_fingerprints.items():
        spec = router.registry.get(executor_id)
        if behavior_fingerprint(spec) != fingerprint or "assessment_workflow" in spec.config:
            raise ConfigurationError("workflow dependency changed or contains nested dispatch")
    workflow = _case_workflow(BenchmarkRoute(route_id=context.spec.id, workflow=adapter.workflow, case_input_bindings=adapter.case_input_bindings), BenchmarkCase(case_id="invocation", split=BenchmarkSplit.HOLDOUT, action=context.request))
    workflow.workflow_id = new_id("workflow")
    outcome = await router.execute_workflow(workflow, approved_side_effect=context.approved_side_effect)
    resources = ResourceVector()
    for receipt in outcome.receipts:
        resources = resources.plus(receipt.actual_resources)
    resources.latency_ms = outcome.wall_time_ms
    resources.peak_memory_mb = outcome.peak_memory_mb
    raw = RawExecution(status=ExecutionStatus.SUCCESS if outcome.status == WorkflowStatus.SUCCESS else ExecutionStatus.FAILED, output=outcome.outputs, resources=resources, accounting=outcome.accounting, error_type=None if outcome.status == WorkflowStatus.SUCCESS else "WORKFLOW_FAILED", metadata={"component_receipt_ids": json.dumps([receipt.receipt_id for receipt in outcome.receipts])})
    projection = context.spec.config.get("assessment_adapter")
    return project_output(raw, DeclarativeAdapter.model_validate(projection) if projection else None)


def workflow_target(**_kwargs: Any) -> None:
    raise RuntimeError("workflow mappings require the controlled Router execution path")


def prepare_context(context: ExecutionContext) -> tuple[ExecutionContext, DeclarativeAdapter | None]:
    value = context.spec.config.get("assessment_adapter")
    if value is None:
        return context, None
    adapter = DeclarativeAdapter.model_validate(value)
    arguments = render(adapter.input_template, {"input": context.request.input}) if adapter.input_template is not None else context.request.input
    if adapter.read_only_roots:
        from ..errors import ConfigurationError
        root = Path(arguments["root"]).resolve(strict=True)
        if not any(root.is_relative_to(Path(allowed).resolve(strict=True)) for allowed in adapter.read_only_roots):
            raise ConfigurationError("search input lies outside reviewed read roots")
    if adapter.input_transform == "local_search_tree:1":
        from .recipes import search_files
        try:
            arguments = {"query": arguments["query"], "files": search_files(arguments["root"], arguments.get("path", "."))}
        except (ConfigurationError, OSError, UnicodeError, ValueError):
            arguments = {"invalid_input": True}
    elif adapter.input_transform == "local_search_tree:2":
        from .recipes import search_files
        # Copy the current tree, not the search result. The worker must still
        # implement query/path semantics, including rejecting root escapes.
        arguments = {"query": arguments["query"], "path": arguments.get("path", "."),
                     "files": search_files(str(root))}
    if adapter.target_input_schema is not None:
        validate_json(arguments, adapter.target_input_schema, label="mapped plugin input")
    return replace(context, request=context.request.model_copy(update={"input": arguments})), adapter


def project_output(raw: RawExecution, adapter: DeclarativeAdapter | None) -> RawExecution:
    if adapter is None or raw.status != ExecutionStatus.SUCCESS:
        return raw
    try:
        if adapter.output_pointer is not None:
            raw.output = pointer_get(raw.output, adapter.output_pointer)
        elif adapter.output_fields:
            raw.output = {name: pointer_get(raw.output, pointer) for name, pointer in adapter.output_fields.items()}
    except (ValueError, KeyError, IndexError, TypeError):
        raw.status = ExecutionStatus.FAILED
        raw.output = None
        raw.error_type = "ADAPTER_OUTPUT_MISMATCH"
        raw.error_message = "plugin output does not match the reviewed mapping"
    return raw
