from __future__ import annotations

import pytest

from aeep.models import (
    ActionConstraints,
    ActionContext,
    ComputeAvailability,
    ExecutorKind,
    ExecutorSpec,
    Locality,
    MetricWeights,
    PolicyConfig,
    ResourceVector,
    RouteEstimate,
    SideEffect,
)
from aeep.policy import merge_constraints, policy_from_weights
from aeep.scoring import score_candidate


def spec(*, kind=ExecutorKind.COMMAND, locality=Locality.LOCAL, network=False):
    return ExecutorSpec(
        id="x",
        capability="x",
        kind=kind,
        description="test",
        locality=locality,
        requires_network=network,
        side_effect=SideEffect.NONE,
        estimate=RouteEstimate(),
        config={"argv": ["true"]} if kind == ExecutorKind.COMMAND else {},
    )


def test_resource_vector_math():
    first = ResourceVector(cpu_ms=2, network_bytes=3, context_tokens=4)
    second = ResourceVector(cpu_ms=5, network_bytes=7, context_tokens=6)
    assert first.plus(second).cpu_ms == 7
    assert first.plus(second).network_bytes == 10
    assert second.scale(0.5).context_tokens == 3


def test_weights_must_not_be_all_zero():
    with pytest.raises(ValueError):
        MetricWeights(monetary=0, latency=0, compute=0, reliability=0, quality=0, risk=0)


def test_merge_constraints_never_weakens_policy():
    policy = ActionConstraints(
        max_cost_usd=0.10,
        min_success_probability=0.9,
        max_side_effect=SideEffect.READ,
        allow_network=False,
        allowed_executor_kinds=[ExecutorKind.COMMAND, ExecutorKind.PYTHON],
    )
    request = ActionConstraints(
        max_cost_usd=1.0,
        min_success_probability=0.5,
        max_side_effect=SideEffect.WRITE,
        allow_network=True,
        allowed_executor_kinds=[ExecutorKind.PYTHON, ExecutorKind.HTTP],
    )
    merged = merge_constraints(policy, request)
    assert merged.max_cost_usd == 0.10
    assert merged.min_success_probability == 0.9
    assert merged.max_side_effect == SideEffect.READ
    assert merged.allow_network is False
    assert merged.allowed_executor_kinds == [ExecutorKind.PYTHON]


def test_hard_constraints_reject_before_scoring():
    executor = spec(locality=Locality.INTERNET, network=True)
    estimate = RouteEstimate(
        resources=ResourceVector(monetary_usd=2, latency_ms=10_000),
        success_probability=0.5,
        risk_score=0.8,
    )
    policy = PolicyConfig(
        constraints=ActionConstraints(
            max_cost_usd=1,
            max_latency_ms=1000,
            min_success_probability=0.8,
            max_risk_score=0.2,
            allow_network=False,
        )
    )
    result = score_candidate(executor, estimate, policy, ActionContext())
    assert not result.feasible
    joined = " ".join(result.rejection_reasons)
    assert "cost" in joined
    assert "latency" in joined
    assert "success probability" in joined
    assert "risk" in joined
    assert "network" in joined


def test_context_quota_rejects_total_model_tokens():
    executor = spec()
    estimate = RouteEstimate(
        resources=ResourceVector(context_tokens=500, input_tokens=700, output_tokens=100)
    )
    context = ActionContext(
        compute=ComputeAvailability(context_tokens_remaining=1000)
    )
    result = score_candidate(executor, estimate, PolicyConfig(), context)
    assert not result.feasible
    assert any("context" in reason for reason in result.rejection_reasons)


def test_custom_weights_constructor():
    policy = policy_from_weights(monetary=1, latency=2, compute=3)
    normalized = policy.weights.normalized()
    assert pytest.approx(sum(normalized.values())) == 1
    assert normalized["compute"] > normalized["latency"] > normalized["monetary"]


def test_allowed_executor_ids_are_hard_constraints():
    executor = spec()
    policy = PolicyConfig(
        constraints=ActionConstraints(allowed_executor_ids=["another-executor"])
    )
    result = score_candidate(executor, RouteEstimate(), policy, ActionContext())
    assert not result.feasible
    assert any("allowed id set" in reason for reason in result.rejection_reasons)


def test_allowed_executor_ids_intersect_when_merging():
    merged = merge_constraints(
        ActionConstraints(allowed_executor_ids=["a", "b"]),
        ActionConstraints(allowed_executor_ids=["b", "c"]),
    )
    assert merged.allowed_executor_ids == ["b"]


def test_max_context_tokens_applies_to_aggregate_model_tokens():
    from aeep.models import ActionConstraints, ActionContext, ExecutorKind, ExecutorSpec, Locality
    from aeep.scoring import rejection_reasons

    spec = ExecutorSpec(
        id="model",
        capability="x",
        kind=ExecutorKind.DELEGATE,
        description="model route",
        locality=Locality.LOCAL,
        estimate=RouteEstimate(),
    )
    estimate = RouteEstimate(
        resources=ResourceVector(context_tokens=20, input_tokens=40, output_tokens=50)
    )
    policy = PolicyConfig(
        name="bounded",
        constraints=ActionConstraints(max_context_tokens=100),
    )
    reasons = rejection_reasons(spec, estimate, policy, ActionContext())
    assert any("total model/context tokens" in reason for reason in reasons)


def test_resource_vectors_reject_non_finite_values():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ResourceVector(monetary_usd=float("nan"))
    with pytest.raises(ValidationError):
        ResourceVector(latency_ms=float("inf"))


def test_manifest_rejects_unknown_protocol_version():
    from pydantic import ValidationError

    from aeep.models import Manifest

    with pytest.raises(ValidationError):
        Manifest(version="9.9")
