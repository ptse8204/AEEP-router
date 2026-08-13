"""Built-in policies and hard-constraint merging."""

from __future__ import annotations

from copy import deepcopy
from typing import TypeVar

from .errors import ConfigurationError
from .models import (
    ActionConstraints,
    FallbackConfig,
    MetricWeights,
    PolicyConfig,
    ReferenceScales,
    ShadowPrices,
)


def builtin_policies() -> dict[str, PolicyConfig]:
    """Return fresh policy objects so callers can safely mutate them."""

    common_refs = ReferenceScales()
    return {
        "balanced": PolicyConfig(
            name="balanced",
            description=(
                "Apply hard safety and capacity constraints, then balance expected "
                "cash cost, latency, compute pressure, reliability, quality, and risk."
            ),
            weights=MetricWeights(
                monetary=0.25,
                latency=0.20,
                compute=0.20,
                subscription=0.15,
                reliability=0.10,
                quality=0.05,
                risk=0.05,
            ),
            references=common_refs,
        ),
        "cheapest": PolicyConfig(
            name="cheapest",
            description="Minimize expected economic cost while retaining reliability gates.",
            weights=MetricWeights(
                monetary=0.60,
                latency=0.08,
                compute=0.10,
                subscription=0.10,
                reliability=0.07,
                quality=0.025,
                risk=0.025,
            ),
            references=ReferenceScales(),
        ),
        "fastest": PolicyConfig(
            name="fastest",
            description="Minimize latency while respecting cost, reliability, and safety limits.",
            weights=MetricWeights(
                monetary=0.08,
                latency=0.70,
                compute=0.08,
                subscription=0.08,
                reliability=0.08,
                quality=0.03,
                risk=0.03,
            ),
            references=ReferenceScales(),
        ),
        "resource_saver": PolicyConfig(
            name="resource_saver",
            description="Conserve context, CPU, memory, GPU, and network resources.",
            weights=MetricWeights(
                monetary=0.10,
                latency=0.10,
                compute=0.45,
                subscription=0.15,
                reliability=0.10,
                quality=0.05,
                risk=0.05,
            ),
            references=ReferenceScales(),
            resource_scarcity_multiplier=4.0,
        ),
        "reliable": PolicyConfig(
            name="reliable",
            description="Prefer the highest probability of a valid, high-quality result.",
            weights=MetricWeights(
                monetary=0.10,
                latency=0.10,
                compute=0.10,
                subscription=0.10,
                reliability=0.40,
                quality=0.20,
                risk=0.10,
            ),
            references=ReferenceScales(),
            constraints=ActionConstraints(
                min_success_probability=0.90,
                min_quality_score=0.80,
                max_risk_score=0.30,
            ),
            fallback=FallbackConfig(max_attempts=3),
        ),
    }


def resolve_policy(
    name: str,
    configured: dict[str, PolicyConfig] | None = None,
) -> PolicyConfig:
    policies = builtin_policies()
    if configured:
        policies.update({key: deepcopy(value) for key, value in configured.items()})
    try:
        return deepcopy(policies[name])
    except KeyError as exc:
        available = ", ".join(sorted(policies))
        raise ConfigurationError(f"unknown policy {name!r}; available: {available}") from exc


def _strictest_max(a: float | int | None, b: float | int | None) -> float | int | None:
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def _strictest_int_max(a: int | None, b: int | None) -> int | None:
    value = _strictest_max(a, b)
    return int(value) if value is not None else None


def _strictest_min(a: float, b: float) -> float:
    return max(a, b)


T = TypeVar("T")


def _intersection(a: list[T] | None, b: list[T] | None) -> list[T] | None:
    if a is None:
        return deepcopy(b)
    if b is None:
        return deepcopy(a)
    b_set = set(b)
    return [item for item in a if item in b_set]


def merge_constraints(
    policy_constraints: ActionConstraints,
    request_constraints: ActionConstraints,
) -> ActionConstraints:
    """Merge constraints without allowing a request to weaken policy guardrails."""

    max_side_effect = (
        policy_constraints.max_side_effect
        if policy_constraints.max_side_effect.rank <= request_constraints.max_side_effect.rank
        else request_constraints.max_side_effect
    )
    allowed_kinds = _intersection(
        policy_constraints.allowed_executor_kinds,
        request_constraints.allowed_executor_kinds,
    )
    allowed_ids = _intersection(
        policy_constraints.allowed_executor_ids,
        request_constraints.allowed_executor_ids,
    )
    residencies = _intersection(
        policy_constraints.allowed_data_residency,
        request_constraints.allowed_data_residency,
    )
    return ActionConstraints(
        max_cost_usd=_strictest_max(
            policy_constraints.max_cost_usd, request_constraints.max_cost_usd
        ),
        max_latency_ms=_strictest_max(
            policy_constraints.max_latency_ms, request_constraints.max_latency_ms
        ),
        max_cpu_ms=_strictest_max(
            policy_constraints.max_cpu_ms, request_constraints.max_cpu_ms
        ),
        max_memory_mb_seconds=_strictest_max(
            policy_constraints.max_memory_mb_seconds,
            request_constraints.max_memory_mb_seconds,
        ),
        max_peak_memory_mb=_strictest_max(
            policy_constraints.max_peak_memory_mb,
            request_constraints.max_peak_memory_mb,
        ),
        max_gpu_ms=_strictest_max(
            policy_constraints.max_gpu_ms, request_constraints.max_gpu_ms
        ),
        max_network_bytes=_strictest_int_max(
            policy_constraints.max_network_bytes, request_constraints.max_network_bytes
        ),
        max_context_tokens=_strictest_int_max(
            policy_constraints.max_context_tokens, request_constraints.max_context_tokens
        ),
        min_success_probability=_strictest_min(
            policy_constraints.min_success_probability,
            request_constraints.min_success_probability,
        ),
        min_quality_score=_strictest_min(
            policy_constraints.min_quality_score,
            request_constraints.min_quality_score,
        ),
        max_risk_score=min(
            policy_constraints.max_risk_score, request_constraints.max_risk_score
        ),
        max_side_effect=max_side_effect,
        allow_network=policy_constraints.allow_network and request_constraints.allow_network,
        require_local=policy_constraints.require_local or request_constraints.require_local,
        allowed_executor_kinds=allowed_kinds,
        allowed_executor_ids=allowed_ids,
        denied_executor_ids=sorted(
            set(policy_constraints.denied_executor_ids)
            | set(request_constraints.denied_executor_ids)
        ),
        allowed_data_residency=residencies,
    )


def policy_with_constraints(
    policy: PolicyConfig,
    request_constraints: ActionConstraints,
) -> PolicyConfig:
    updated = policy.model_copy(deep=True)
    updated.constraints = merge_constraints(policy.constraints, request_constraints)
    return updated


def policy_from_weights(
    *,
    monetary: float,
    latency: float,
    compute: float,
    subscription: float = 0.0,
    reliability: float = 0.10,
    quality: float = 0.05,
    risk: float = 0.05,
    shadow_prices: ShadowPrices | None = None,
) -> PolicyConfig:
    """Convenience constructor for embedding AEEP in another agent runtime."""

    return PolicyConfig(
        name="custom",
        description="Custom caller-provided policy.",
        weights=MetricWeights(
            monetary=monetary,
            latency=latency,
            compute=compute,
            subscription=subscription,
            reliability=reliability,
            quality=quality,
            risk=risk,
        ),
        shadow_prices=shadow_prices or ShadowPrices(),
    )
