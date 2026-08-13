"""Feasibility filtering and explainable multi-objective scoring."""

from __future__ import annotations

import math
from statistics import fmean

from .models import (
    ActionContext,
    CandidateScore,
    DataSensitivity,
    ExecutorSpec,
    Locality,
    PolicyConfig,
    RouteEstimate,
    ScoreBreakdown,
)


def _over(value: float, reference: float) -> float:
    return math.log1p(max(0.0, value) / reference)


def _effective_money(estimate: RouteEstimate, policy: PolicyConfig) -> float:
    resources = estimate.resources
    prices = policy.shadow_prices
    return (
        resources.monetary_usd
        + resources.cpu_ms * prices.cpu_ms_usd
        + resources.memory_mb_seconds * prices.memory_mb_second_usd
        + resources.gpu_ms * prices.gpu_ms_usd
        + resources.network_bytes * prices.network_byte_usd
        + resources.context_tokens * prices.context_token_usd
        + resources.input_tokens * prices.input_token_usd
        + resources.output_tokens * prices.output_token_usd
    )


def rejection_reasons(
    spec: ExecutorSpec,
    estimate: RouteEstimate,
    policy: PolicyConfig,
    context: ActionContext,
) -> list[str]:
    c = policy.constraints
    r = estimate.resources
    reasons: list[str] = []

    checks: list[tuple[float | int | None, float | int, str]] = [
        (c.max_cost_usd, _effective_money(estimate, policy), "cost"),
        (c.max_latency_ms, r.latency_ms, "latency"),
        (c.max_cpu_ms, r.cpu_ms, "CPU"),
        (c.max_memory_mb_seconds, r.memory_mb_seconds, "memory-time"),
        (c.max_peak_memory_mb, r.peak_memory_mb, "peak memory"),
        (c.max_gpu_ms, r.gpu_ms, "GPU"),
        (c.max_network_bytes, r.network_bytes, "network"),
        (
            c.max_context_tokens,
            r.context_tokens + r.input_tokens + r.output_tokens,
            "total model/context tokens",
        ),
    ]
    for maximum, actual, label in checks:
        if maximum is not None and actual > maximum:
            reasons.append(f"estimated {label} {actual:g} exceeds maximum {maximum:g}")

    if estimate.success_probability < c.min_success_probability:
        reasons.append(
            f"success probability {estimate.success_probability:.3f} is below "
            f"{c.min_success_probability:.3f}"
        )
    if estimate.quality_score < c.min_quality_score:
        reasons.append(
            f"quality {estimate.quality_score:.3f} is below {c.min_quality_score:.3f}"
        )
    if estimate.risk_score > c.max_risk_score:
        reasons.append(f"risk {estimate.risk_score:.3f} exceeds {c.max_risk_score:.3f}")
    if spec.side_effect.rank > c.max_side_effect.rank:
        reasons.append(
            f"side effect {spec.side_effect.value} exceeds allowed {c.max_side_effect.value}"
        )
    if not c.allow_network and spec.requires_network:
        reasons.append("network access is disabled")
    if c.require_local and spec.locality not in {Locality.IN_PROCESS, Locality.LOCAL}:
        reasons.append("policy requires a local executor")
    if c.allowed_executor_kinds is not None and spec.kind not in c.allowed_executor_kinds:
        reasons.append(f"executor kind {spec.kind.value} is not allowed")
    if c.allowed_executor_ids is not None and spec.id not in c.allowed_executor_ids:
        reasons.append("executor is not in the allowed id set")
    if spec.id in c.denied_executor_ids:
        reasons.append("executor is denied by id")
    if c.allowed_data_residency is not None and spec.locality in {
        Locality.LAN,
        Locality.INTERNET,
    }:
        if not spec.data_residency:
            reasons.append("remote executor has unknown data residency")
        elif not set(spec.data_residency).intersection(c.allowed_data_residency):
            reasons.append("executor data residency is outside allowed regions")
    if (
        context.data_sensitivity == DataSensitivity.RESTRICTED
        and spec.locality in {Locality.LAN, Locality.INTERNET}
        and not bool(spec.config.get("accepts_restricted_data", False))
    ):
        reasons.append("restricted data cannot be sent to this remote executor")

    available = context.compute
    if (
        available.context_tokens_remaining is not None
        and (r.context_tokens + r.input_tokens + r.output_tokens) > available.context_tokens_remaining
    ):
        reasons.append("estimated context usage exceeds remaining context budget")
    if (
        available.monetary_budget_remaining_usd is not None
        and _effective_money(estimate, policy) > available.monetary_budget_remaining_usd
    ):
        reasons.append("estimated cost exceeds remaining monetary budget")
    if (
        available.available_memory_mb is not None
        and r.peak_memory_mb > available.available_memory_mb
    ):
        reasons.append("estimated peak memory exceeds currently available memory")

    return reasons


def _compute_burden(
    estimate: RouteEstimate,
    policy: PolicyConfig,
    context: ActionContext,
) -> float:
    r = estimate.resources
    refs = policy.references
    components = [
        r.cpu_ms / refs.cpu_ms,
        r.memory_mb_seconds / refs.memory_mb_seconds,
        r.peak_memory_mb / refs.peak_memory_mb,
        r.gpu_ms / refs.gpu_ms,
        r.network_bytes / refs.network_bytes,
        (r.context_tokens + r.input_tokens + r.output_tokens) / refs.context_tokens,
    ]
    base = 0.0 if not any(components) else 0.6 * max(components) + 0.4 * fmean(components)

    scarcity = 0.0
    available = context.compute
    if available.context_tokens_remaining:
        token_pressure = r.context_tokens + r.input_tokens + r.output_tokens
        scarcity = max(scarcity, token_pressure / available.context_tokens_remaining)
    if available.available_memory_mb:
        scarcity = max(scarcity, r.peak_memory_mb / available.available_memory_mb)
    if available.available_gpu_ms is not None and available.available_gpu_ms > 0:
        scarcity = max(scarcity, r.gpu_ms / available.available_gpu_ms)
    if available.available_cpu_fraction:
        scarcity = max(scarcity, (r.cpu_ms / refs.cpu_ms) / available.available_cpu_fraction)
    if available.network_metered and r.network_bytes:
        scarcity = max(scarcity, r.network_bytes / refs.network_bytes)

    return math.log1p(base + policy.resource_scarcity_multiplier * scarcity)


def score_candidate(
    spec: ExecutorSpec,
    estimate: RouteEstimate,
    policy: PolicyConfig,
    context: ActionContext,
) -> CandidateScore:
    reasons = rejection_reasons(spec, estimate, policy, context)
    if reasons:
        return CandidateScore(
            executor_id=spec.id,
            feasible=False,
            rejection_reasons=reasons,
            estimate=estimate,
        )

    p_success = max(estimate.success_probability, 0.001)
    expected_multiplier = 1.0 / p_success
    weights = policy.weights.normalized()
    money = _over(
        _effective_money(estimate, policy) * expected_multiplier,
        policy.references.monetary_usd,
    )
    latency = _over(
        estimate.resources.latency_ms * expected_multiplier,
        policy.references.latency_ms,
    )
    compute = _compute_burden(estimate, policy, context) * expected_multiplier
    reliability = -math.log(p_success)
    quality = 1.0 - estimate.quality_score
    risk = estimate.risk_score

    locality_adjustment = 0.0
    if spec.locality in {Locality.IN_PROCESS, Locality.LOCAL}:
        locality_adjustment -= policy.prefer_local_bonus
    if context.state_locality is not None and context.state_locality == spec.locality:
        locality_adjustment -= policy.prefer_local_bonus

    total = (
        weights["monetary"] * money
        + weights["latency"] * latency
        + weights["compute"] * compute
        + weights["reliability"] * reliability
        + weights["quality"] * quality
        + weights["risk"] * risk
        + locality_adjustment
    )
    breakdown = ScoreBreakdown(
        monetary=weights["monetary"] * money,
        latency=weights["latency"] * latency,
        compute=weights["compute"] * compute,
        reliability=weights["reliability"] * reliability,
        quality=weights["quality"] * quality,
        risk=weights["risk"] * risk,
        locality_adjustment=locality_adjustment,
        total=total,
    )
    return CandidateScore(
        executor_id=spec.id,
        feasible=True,
        estimate=estimate,
        score=breakdown,
    )
