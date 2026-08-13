from __future__ import annotations

from typing import Any

import pytest

from aeep.models import (
    ExecutorKind,
    ExecutorSpec,
    Locality,
    Manifest,
    ResourceVector,
    RouteEstimate,
    SideEffect,
)


@pytest.fixture
def text_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
        "additionalProperties": False,
    }


@pytest.fixture
def stats_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "characters": {"type": "integer"},
            "words": {"type": "integer"},
            "lines": {"type": "integer"},
        },
        "required": ["characters", "words", "lines"],
        "additionalProperties": False,
    }


def python_spec(
    executor_id: str,
    callable_path: str,
    *,
    latency_ms: float = 5,
    cost: float = 0,
    capability: str = "text.stats",
    input_schema: dict[str, Any] | None = None,
    output_schema: dict[str, Any] | None = None,
    side_effect: SideEffect = SideEffect.NONE,
    idempotent: bool = True,
    safe: bool = True,
) -> ExecutorSpec:
    return ExecutorSpec(
        id=executor_id,
        capability=capability,
        kind=ExecutorKind.PYTHON,
        description=executor_id,
        input_schema=input_schema
        or {"type": "object", "properties": {}, "additionalProperties": True},
        output_schema=output_schema,
        estimate=RouteEstimate(
            resources=ResourceVector(
                monetary_usd=cost,
                latency_ms=latency_ms,
                cpu_ms=latency_ms / 2,
                peak_memory_mb=16,
            ),
            success_probability=0.99,
            quality_score=0.99,
            risk_score=0.01,
            confidence=0.8,
        ),
        side_effect=side_effect,
        locality=Locality.IN_PROCESS,
        idempotent=idempotent,
        safe_to_auto_execute=safe,
        config={"callable": callable_path},
    )


def manifest_with(*specs: ExecutorSpec, policies=None) -> Manifest:
    return Manifest(
        database=":memory:",
        policies=policies or {},
        executors=list(specs),
    )
