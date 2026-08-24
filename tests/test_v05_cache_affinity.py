from __future__ import annotations

import sys
from datetime import UTC, datetime

from aeep.cache_affinity import estimate_cache_affinity, normalize_cache_usage
from aeep.models import (
    ActionConstraints,
    ActionContext,
    ActionRequest,
    CacheAffinityObservation,
    CacheAffinityPolicyConfig,
    CacheRoutingContext,
    ExecutorKind,
    ExecutorSpec,
    Manifest,
    PolicyConfig,
    ResourceVector,
    RouteEstimate,
    SideEffect,
)
from aeep.router import Router

NOW = datetime(2026, 8, 21, tzinfo=UTC)
DIGEST = "a" * 64


def cache_context(route_id: str) -> CacheRoutingContext:
    return CacheRoutingContext(
        cache_scope_key_hmac=DIGEST,
        provider="local",
        model="fixture-model",
        integration_adapter="fixture",
        route_id=route_id,
        stable_prefix_digest_hmac="b" * 64,
        previous_state_digest_hmac="c" * 64,
        common_prefix_tokens_estimate=800,
        eligible_cached_tokens_estimate=1000,
        observed_hits=8,
        observed_attempts=10,
        last_seen_at=NOW,
    )


def test_warm_probability_and_usage_normalization() -> None:
    context = cache_context("route-a")
    latest = CacheAffinityObservation(
        scope_key_hmac=context.cache_scope_key_hmac,
        route_id=context.route_id,
        stable_prefix_digest_hmac=context.stable_prefix_digest_hmac,
        state_digest_hmac=context.previous_state_digest_hmac,
        cache_hit=True,
        cached_input_tokens=800,
        cache_write_input_tokens=0,
        observed_at=NOW,
    )

    estimate = estimate_cache_affinity(
        context,
        cold_resources=ResourceVector(latency_ms=1000, input_tokens=1000),
        warm_resources=ResourceVector(
            latency_ms=100,
            input_tokens=1000,
            cached_input_tokens=800,
        ),
        latest=latest,
        at=NOW,
    )

    assert 0 < estimate.warm_probability < 1
    assert 100 < estimate.expected_resources.latency_ms < 1000
    usage = normalize_cache_usage(
        {
            "usage": {
                "input_tokens": 1000,
                "input_tokens_details": {"cached_tokens": 800},
                "cache_creation_input_tokens": 100,
                "output_tokens": 50,
                "output_tokens_details": {"reasoning_tokens": 10},
            }
        },
        provider="fixture",
        model="fixture-model",
    )
    assert usage.cached_input_tokens == 800
    assert usage.cache_write_input_tokens == 100
    assert usage.reasoning_output_tokens == 10


def test_cold_hard_feasibility_cannot_be_laundered_by_warm_estimate() -> None:
    route = ExecutorSpec(
        id="route-a",
        capability="fixture.cache@1",
        kind=ExecutorKind.COMMAND,
        description="Cache fixture",
        side_effect=SideEffect.NONE,
        estimate=RouteEstimate(resources=ResourceVector(latency_ms=1000)),
        config={
            "argv": [sys.executable],
            "cache_affinity": {"warm_resources": {"latency_ms": 10}},
        },
    )
    policy = PolicyConfig(
        name="cache",
        cache_affinity=CacheAffinityPolicyConfig(enabled=True),
    )
    router = Router(
        Manifest(
            database=":memory:",
            default_policy="cache",
            policies={"cache": policy},
            executors=[route],
        ),
        clock=lambda: NOW,
    )
    context = cache_context(route.id)
    router.store.save_cache_affinity_observation(
        CacheAffinityObservation(
            scope_key_hmac=context.cache_scope_key_hmac,
            route_id=route.id,
            stable_prefix_digest_hmac=context.stable_prefix_digest_hmac,
            state_digest_hmac=context.previous_state_digest_hmac,
            cache_hit=True,
            cached_input_tokens=800,
            cache_write_input_tokens=0,
            observed_at=NOW,
        )
    )

    decision = router.route(
        ActionRequest(
            capability=route.capability,
            constraints=ActionConstraints(max_latency_ms=100),
            context=ActionContext(cache_affinity=context),
        )
    )

    assert decision.selected_executor_id is None
    assert decision.candidates[0].cache_affinity is None
