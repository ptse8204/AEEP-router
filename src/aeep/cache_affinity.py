"""Privacy-preserving cache-affinity estimates for soft route ranking."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from typing import Any

from .errors import ConfigurationError
from .models import (
    CacheAffinityEstimate,
    CacheAffinityObservation,
    CacheRoutingContext,
    EvidenceSource,
    EvidenceStatus,
    MeasurementEvidence,
    ModelAccessChannel,
    ModelTokenUsage,
    ResourceVector,
    TrustLevel,
)


def cache_hmac(secret: bytes, *parts: str) -> str:
    if len(secret) < 32:
        raise ValueError("cache-affinity HMAC secret must contain at least 32 bytes")
    payload = "\x1f".join(parts).encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def estimate_cache_affinity(
    context: CacheRoutingContext,
    *,
    cold_resources: ResourceVector,
    warm_resources: ResourceVector,
    latest: CacheAffinityObservation | None = None,
    half_life_seconds: float = 3600,
    at: datetime | None = None,
) -> CacheAffinityEstimate:
    if half_life_seconds <= 0:
        raise ValueError("cache half-life must be positive")
    now = (at or datetime.now(UTC)).astimezone(UTC)
    identity = float(context.route_id == (latest.route_id if latest else context.route_id))
    prefix = (
        min(1.0, context.common_prefix_tokens_estimate / context.eligible_cached_tokens_estimate)
        if context.eligible_cached_tokens_estimate
        else 0.0
    )
    if latest is None or context.last_seen_at is None:
        freshness = 0.0
        continuity = 0.0
    else:
        age = max(0.0, (now - context.last_seen_at.astimezone(UTC)).total_seconds())
        freshness = 2 ** (-age / half_life_seconds)
        continuity = float(
            context.previous_state_digest_hmac is not None
            and context.previous_state_digest_hmac == latest.state_digest_hmac
            and context.stable_prefix_digest_hmac == latest.stable_prefix_digest_hmac
            and context.compaction_generation == latest.compaction_generation
            and context.context_reset_reason is None
        )
    reliability = (context.observed_hits + 1) / (context.observed_attempts + 2)
    probability = min(1.0, max(0.0, identity * prefix * freshness * continuity * reliability))
    expected = cold_resources.scale(1 - probability).plus(
        warm_resources.scale(probability)
    )
    return CacheAffinityEstimate(
        warm_probability=probability,
        identity_match=identity,
        prefix_match=prefix,
        freshness_decay=freshness,
        continuity_probability=continuity,
        observed_reliability=reliability,
        cold_resources=cold_resources,
        warm_resources=warm_resources,
        expected_resources=expected,
        expected_reusable_input_tokens=round(
            probability * context.eligible_cached_tokens_estimate
        ),
        switch_penalty_latency_ms=max(
            0.0,
            cold_resources.latency_ms - expected.latency_ms,
        ),
        compaction_generation=context.compaction_generation,
    )


def normalize_cache_usage(
    value: dict[str, Any],
    *,
    provider: str,
    model: str,
    access_channel: ModelAccessChannel = ModelAccessChannel.UNKNOWN,
) -> ModelTokenUsage:
    raw_usage = value.get("usage")
    usage: dict[str, Any] = raw_usage if isinstance(raw_usage, dict) else value
    raw_details = usage.get("input_tokens_details")
    details: dict[str, Any] = raw_details if isinstance(raw_details, dict) else {}
    input_tokens = _integer(usage, "input_tokens", "prompt_tokens")
    cached = _integer(usage, "cached_input_tokens")
    if cached == 0:
        cached = _integer(details, "cached_tokens")
    cache_write = _integer(
        usage,
        "cache_write_input_tokens",
        "cache_creation_input_tokens",
    )
    output = _integer(usage, "output_tokens", "completion_tokens")
    reasoning = _integer(usage, "reasoning_output_tokens")
    output_details = usage.get("output_tokens_details")
    if reasoning == 0 and isinstance(output_details, dict):
        reasoning = _integer(output_details, "reasoning_tokens")
    if cached + cache_write > input_tokens or reasoning > output:
        raise ConfigurationError("cache usage token subsets exceed their totals")
    return ModelTokenUsage(
        provider=provider,
        model=model,
        access_channel=access_channel,
        input_tokens=input_tokens,
        cached_input_tokens=cached,
        cache_write_input_tokens=cache_write,
        output_tokens=output,
        reasoning_output_tokens=reasoning,
        evidence=MeasurementEvidence(
            status=EvidenceStatus.COMPLETE,
            source=EvidenceSource.LOCAL_METER,
            trust=TrustLevel.OBSERVED,
        ),
    )


def _integer(value: dict[str, Any], *names: str) -> int:
    for name in names:
        item = value.get(name)
        if item is None:
            continue
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise ConfigurationError(f"cache usage {name} must be a non-negative integer")
        return int(item)
    return 0
