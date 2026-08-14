"""Caller-authored bounded workflow contracts and JSON Pointer helpers."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator, model_validator

from .models import (
    ActionConstraints,
    ActionRequest,
    ExecutionReceipt,
    PolicyValuation,
    ResourceAccounting,
    StrictModel,
)


class WorkflowStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    WAITING = "waiting"


class WorkflowBudget(StrictModel):
    max_cash_usd: Decimal | None = Field(default=None, ge=0)


class WorkflowInputBinding(StrictModel):
    target_path: str
    source_step_id: str | None = None
    source_path: str


class WorkflowStep(StrictModel):
    step_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]+$", max_length=100)
    action: ActionRequest
    depends_on: list[str] = Field(default_factory=list)
    bindings: list[WorkflowInputBinding] = Field(default_factory=list)

    @field_validator("depends_on")
    @classmethod
    def unique_dependencies(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("duplicate workflow dependency")
        return value


class WorkflowOutputProjection(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    step_id: str
    path: str


class WorkflowRequest(StrictModel):
    workflow_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]+$", max_length=200)
    input: dict[str, Any] = Field(default_factory=dict)
    constraints: ActionConstraints = Field(default_factory=ActionConstraints)
    budget: WorkflowBudget = Field(default_factory=WorkflowBudget)
    steps: list[WorkflowStep] = Field(min_length=1, max_length=64)
    outputs: list[WorkflowOutputProjection] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_dag(self) -> WorkflowRequest:
        ids = [step.step_id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate workflow step id")
        known = set(ids)
        by_id = {step.step_id: step for step in self.steps}
        for step in self.steps:
            if step.step_id in step.depends_on or not set(step.depends_on) <= known:
                raise ValueError(f"invalid dependency for step {step.step_id!r}")
            targets = [binding.target_path for binding in step.bindings]
            if len(targets) != len(set(targets)):
                raise ValueError(f"duplicate binding target for step {step.step_id!r}")
            for binding in step.bindings:
                if (
                    binding.source_step_id is not None
                    and binding.source_step_id not in step.depends_on
                ):
                    raise ValueError("binding source must be a declared dependency")
                _tokens(binding.target_path)
                _tokens(binding.source_path)
                pointer_get(step.action.input, binding.target_path)
                if binding.source_step_id is None:
                    pointer_get(self.input, binding.source_path)
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(step_id: str) -> None:
            if step_id in visiting:
                raise ValueError("workflow dependency cycle")
            if step_id in visited:
                return
            visiting.add(step_id)
            for dependency in by_id[step_id].depends_on:
                visit(dependency)
            visiting.remove(step_id)
            visited.add(step_id)

        for step_id in ids:
            visit(step_id)
        output_names = [item.name for item in self.outputs]
        if len(output_names) != len(set(output_names)):
            raise ValueError("duplicate workflow output name")
        for projection in self.outputs:
            if projection.step_id not in known:
                raise ValueError("workflow output references unknown step")
            _tokens(projection.path)
        return self

    @property
    def workflow_hash(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(canonical).hexdigest()


class WorkflowExecutionOutcome(StrictModel):
    workflow_id: str
    workflow_hash: str
    status: WorkflowStatus
    outputs: dict[str, Any] = Field(default_factory=dict)
    step_outputs: dict[str, Any] = Field(default_factory=dict)
    receipts: list[ExecutionReceipt] = Field(default_factory=list)
    accounting: ResourceAccounting = Field(default_factory=ResourceAccounting)
    known_cash_subtotal_usd: Decimal = Decimal(0)
    actual_cash_total_usd: Decimal | None = None
    policy_valuations: list[PolicyValuation] = Field(default_factory=list)
    wall_time_ms: float = Field(default=0, ge=0)
    critical_path_ms: float = Field(default=0, ge=0)
    peak_memory_mb: float = Field(default=0, ge=0)
    waiting_step_id: str | None = None
    waiting_decision_id: str | None = None
    error: str | None = Field(default=None, max_length=1000)


def _tokens(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise ValueError("workflow paths must be RFC 6901 JSON Pointers")
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]


def pointer_get(value: Any, pointer: str) -> Any:
    current = value
    for token in _tokens(pointer):
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            raise ValueError(f"JSON Pointer {pointer!r} does not exist")
    return current


def pointer_replace(value: Any, pointer: str, replacement: Any) -> None:
    tokens = _tokens(pointer)
    if not tokens:
        raise ValueError("binding cannot replace the action-input root")
    parent = value
    for token in tokens[:-1]:
        if isinstance(parent, dict) and token in parent:
            parent = parent[token]
        elif isinstance(parent, list) and token.isdigit() and int(token) < len(parent):
            parent = parent[int(token)]
        else:
            raise ValueError(f"binding target {pointer!r} does not exist")
    final = tokens[-1]
    if isinstance(parent, dict) and final in parent:
        parent[final] = replacement
    elif isinstance(parent, list) and final.isdigit() and int(final) < len(parent):
        parent[int(final)] = replacement
    else:
        raise ValueError(f"binding target {pointer!r} does not exist")


def schema_pointer_exists(schema: Any, pointer: str) -> bool:
    """Best-effort schema check used only when a caller supplied a schema inline."""

    if schema is None:
        return True
    current = schema
    for token in _tokens(pointer):
        if not isinstance(current, dict):
            return False
        properties = current.get("properties")
        if isinstance(properties, dict) and token in properties:
            current = properties[token]
        elif current.get("type") == "array" and token.isdigit():
            current = current.get("items")
        else:
            return current.get("additionalProperties") is True
    return True
