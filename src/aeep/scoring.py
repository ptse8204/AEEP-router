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
    SubscriptionQuota,
    SubscriptionUsage,
)


def _over(value: float, reference: float) -> float:
    return math.log1p(max(0.0, value) / reference)


def policy_valuation_amount(estimate: RouteEstimate, policy: PolicyConfig) -> float:
    resources = estimate.resources
    prices = policy.shadow_prices
    return (
        resources.cpu_ms * prices.cpu_ms_usd
        + resources.memory_mb_seconds * prices.memory_mb_second_usd
        + resources.gpu_ms * prices.gpu_ms_usd
        + resources.network_bytes * prices.network_byte_usd
        + resources.context_tokens * prices.context_token_usd
        + resources.input_tokens * prices.input_token_usd
        + resources.output_tokens * prices.output_token_usd
    )


def _cash_amount(estimate: RouteEstimate) -> float | None:
    return float(estimate.cash.amount_usd) if estimate.cash.amount_usd is not None else None


def _cash_upper_bound(estimate: RouteEstimate) -> float | None:
    return (
        float(estimate.cash.upper_bound_usd) if estimate.cash.upper_bound_usd is not None else None
    )


def _subscription_units(spec: ExecutorSpec, estimate: RouteEstimate) -> float:
    if spec.resource_pool:
        entries = [
            item
            for item in estimate.subscription_usage
            if item.resource_pool == spec.resource_pool and item.consumed is not None
        ]
        if len(entries) == 1:
            return float(entries[0].consumed or 0)
    return estimate.resources.subscription_units


def subscription_score_components(
    *,
    resource_pool: str,
    unit: str,
    units: float,
    policy: PolicyConfig,
    quota: SubscriptionQuota | None,
    success_probability: float,
) -> tuple[float, float]:
    """Return dimensionless pressure and private USD policy value for one pool."""

    current = quota or SubscriptionQuota(unit=unit)
    if current.remaining_units is not None:
        remaining = float(current.remaining_units)
        pressure = units / remaining if remaining else float("inf")
    elif current.allowance_units is not None:
        allowance = float(current.allowance_units)
        pressure = units / allowance if allowance else float("inf")
    else:
        pressure = units * current.state.pressure
    rule = next(
        (
            item
            for item in policy.subscription_rules
            if item.resource_pool == resource_pool and item.unit == unit
        ),
        None,
    )
    pool_weight = rule.pressure_weight if rule else 1.0
    confidence_uncertainty = 1.0 - current.confidence
    burden = math.log1p(
        pressure * policy.subscription_scarcity_multiplier * pool_weight + confidence_uncertainty
    ) / max(success_probability, 0.001)
    value = (
        units * float(rule.policy_value_usd_per_unit)
        if rule and rule.policy_value_usd_per_unit is not None
        else 0.0
    )
    return burden, value


def add_subscription_vector(
    breakdown: ScoreBreakdown,
    estimate: RouteEstimate,
    policy: PolicyConfig,
    usage: list[SubscriptionUsage],
    quotas: dict[tuple[str, str], SubscriptionQuota | None],
) -> ScoreBreakdown:
    """Add provider-local pool burdens to an already aggregate plan score."""

    known = [item for item in usage if item.consumed is not None]
    if not known:
        return breakdown
    burdens: list[float] = []
    private_value = 0.0
    for item in known:
        burden, value = subscription_score_components(
            resource_pool=item.resource_pool,
            unit=item.unit,
            units=float(item.consumed or 0),
            policy=policy,
            quota=quotas.get((item.resource_pool, item.unit)),
            success_probability=estimate.success_probability,
        )
        burdens.append(burden)
        private_value += value
    weights = policy.weights.normalized()
    subscription = weights["subscription"] * max(burdens, default=0.0)
    base_value = policy_valuation_amount(estimate, policy)
    expected_multiplier = 1.0 / max(estimate.success_probability, 0.001)
    prior_policy_value = weights["monetary"] * _over(
        base_value * expected_multiplier, policy.references.monetary_usd
    )
    policy_value = weights["monetary"] * _over(
        (base_value + private_value) * expected_multiplier,
        policy.references.monetary_usd,
    )
    updated = breakdown.model_copy(deep=True)
    updated.subscription = subscription
    updated.policy_valuation += policy_value - prior_policy_value
    updated.monetary += policy_value - prior_policy_value
    updated.total += subscription + policy_value - prior_policy_value
    return updated


def rejection_reasons(
    spec: ExecutorSpec,
    estimate: RouteEstimate,
    policy: PolicyConfig,
    context: ActionContext,
    subscription_quota: SubscriptionQuota | None = None,
) -> list[str]:
    c = policy.constraints
    r = estimate.resources
    reasons: list[str] = []

    checks: list[tuple[float | int | None, float | int, str]] = [
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

    cash_upper = _cash_upper_bound(estimate)
    if c.max_cost_usd is not None:
        if cash_upper is None:
            reasons.append("estimated cash upper bound is unavailable under a finite cost limit")
        elif cash_upper > c.max_cost_usd:
            reasons.append(f"estimated cost {cash_upper:g} exceeds maximum {c.max_cost_usd:g}")

    if estimate.success_probability < c.min_success_probability:
        reasons.append(
            f"success probability {estimate.success_probability:.3f} is below "
            f"{c.min_success_probability:.3f}"
        )
    if estimate.quality_score < c.min_quality_score:
        reasons.append(f"quality {estimate.quality_score:.3f} is below {c.min_quality_score:.3f}")
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
    if subscription_quota is not None and not math.isfinite(subscription_quota.state.pressure):
        reasons.append(f"subscription resource {spec.resource_pool!r} is exhausted")
    units = _subscription_units(spec, estimate)
    if (
        subscription_quota is not None
        and subscription_quota.remaining_units is not None
        and units > float(subscription_quota.remaining_units)
    ):
        reasons.append(f"subscription resource {spec.resource_pool!r} has insufficient units")
    if subscription_quota is not None and any(
        item.resource_pool == spec.resource_pool and item.unit != subscription_quota.unit
        for item in estimate.subscription_usage
    ):
        reasons.append(f"subscription resource {spec.resource_pool!r} unit does not match quota")

    available = context.compute
    if (
        available.context_tokens_remaining is not None
        and (r.context_tokens + r.input_tokens + r.output_tokens)
        > available.context_tokens_remaining
    ):
        reasons.append("estimated context usage exceeds remaining context budget")
    if available.monetary_budget_remaining_usd is not None:
        if cash_upper is None:
            reasons.append("estimated cash upper bound is unavailable under remaining budget")
        elif cash_upper > available.monetary_budget_remaining_usd:
            reasons.append("estimated cost exceeds remaining monetary budget")
    if (
        available.available_memory_mb is not None
        and r.peak_memory_mb > available.available_memory_mb
    ):
        reasons.append("estimated peak memory exceeds currently available memory")
    if available.available_gpu_ms is not None and r.gpu_ms > available.available_gpu_ms:
        reasons.append("estimated GPU usage exceeds currently available GPU capacity")

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
    subscription_quota: SubscriptionQuota | None = None,
) -> CandidateScore:
    reasons = rejection_reasons(spec, estimate, policy, context, subscription_quota)
    if reasons:
        return CandidateScore(
            executor_id=spec.id,
            feasible=False,
            rejection_reasons=reasons,
            estimate=estimate,
            resource_pool=spec.resource_pool,
            subscription_quota=subscription_quota,
        )

    p_success = max(estimate.success_probability, 0.001)
    expected_multiplier = 1.0 / p_success
    weights = policy.weights.normalized()
    cash_amount = _cash_amount(estimate)
    cash = _over(
        (cash_amount or 0.0) * expected_multiplier,
        policy.references.monetary_usd,
    )
    policy_value_amount = policy_valuation_amount(estimate, policy)
    latency = _over(
        estimate.resources.latency_ms * expected_multiplier,
        policy.references.latency_ms,
    )
    compute = _compute_burden(estimate, policy, context) * expected_multiplier
    subscription = 0.0
    if subscription_quota is not None and _subscription_units(spec, estimate):
        units = _subscription_units(spec, estimate)
        unit = subscription_quota.unit
        subscription, subscription_policy_value = subscription_score_components(
            resource_pool=spec.resource_pool or "",
            unit=unit,
            units=units,
            policy=policy,
            quota=subscription_quota,
            success_probability=estimate.success_probability,
        )
        policy_value_amount += subscription_policy_value
    policy_value = _over(
        policy_value_amount * expected_multiplier,
        policy.references.monetary_usd,
    )
    reliability = -math.log(p_success)
    quality = 1.0 - estimate.quality_score
    risk = estimate.risk_score
    uncertainty = (1.0 - estimate.confidence) * policy.uncertainty_penalty
    cash_uncertainty = policy.uncertainty_penalty if cash_amount is None else 0.0

    locality_adjustment = 0.0
    if spec.locality in {Locality.IN_PROCESS, Locality.LOCAL}:
        locality_adjustment -= policy.prefer_local_bonus
    if context.state_locality is not None and context.state_locality == spec.locality:
        locality_adjustment -= policy.prefer_local_bonus

    total = (
        weights["monetary"] * (cash + policy_value)
        + weights["latency"] * latency
        + weights["compute"] * compute
        + weights["subscription"] * subscription
        + weights["reliability"] * reliability
        + weights["quality"] * quality
        + weights["risk"] * risk
        + uncertainty
        + cash_uncertainty
        + locality_adjustment
    )
    breakdown = ScoreBreakdown(
        monetary=weights["monetary"] * (cash + policy_value),
        cash=weights["monetary"] * cash,
        policy_valuation=weights["monetary"] * policy_value,
        latency=weights["latency"] * latency,
        compute=weights["compute"] * compute,
        subscription=weights["subscription"] * subscription,
        reliability=weights["reliability"] * reliability,
        quality=weights["quality"] * quality,
        risk=weights["risk"] * risk,
        uncertainty=uncertainty,
        cash_uncertainty=cash_uncertainty,
        locality_adjustment=locality_adjustment,
        total=total,
    )
    return CandidateScore(
        executor_id=spec.id,
        feasible=True,
        estimate=estimate,
        resource_pool=spec.resource_pool,
        subscription_quota=subscription_quota,
        score=breakdown,
    )
