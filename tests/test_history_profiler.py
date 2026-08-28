from __future__ import annotations

from datetime import UTC, datetime, timedelta

from conftest import manifest_with, python_spec

from aeep.estimator import HistoricalEstimator, action_features, evidence_cohort_digest
from aeep.models import (
    ActionRequest,
    ExecutionReceipt,
    ExecutionStatus,
    ExecutorKind,
    ResourceVector,
)
from aeep.profiler import ActionProfiler, approximate_tokens
from aeep.router import Router


def cohort_receipt(executor, **values):
    receipt = ExecutionReceipt(**values)
    receipt.executor_fingerprint, receipt.cohort_digest = evidence_cohort_digest(
        executor,
        receipt.action_features,
    )
    return receipt


def test_token_estimate_is_stable():
    assert approximate_tokens("abcd") == 1
    assert approximate_tokens({"a": "b"}) > 0


def test_action_profiler_records_external_work():
    executor = python_spec("x", "aeep.examples.tools:text_stats")
    router = Router(manifest_with(executor))
    with ActionProfiler(store=router.store, capability="custom", executor_id="browser") as profile:
        profile.add_cost(0.02)
        profile.add_tokens(input_tokens=100, output_tokens=20)
        profile.succeed(output_valid=True)
    assert profile.receipt is not None
    assert profile.receipt.actual_resources.monetary_usd == 0.02
    assert profile.receipt.actual_resources.input_tokens == 100
    import asyncio

    asyncio.run(router.close())


def test_history_blends_observed_success_and_ignores_delegated():
    executor = python_spec("x", "aeep.examples.tools:text_stats", latency_ms=100)
    router = Router(manifest_with(executor))
    now = datetime.now(UTC)
    delegated = cohort_receipt(
        executor,
        decision_id="d",
        action_id="a",
        capability="text.stats",
        executor_id="x",
        executor_kind=ExecutorKind.PYTHON,
        status=ExecutionStatus.DELEGATED,
        started_at=now,
        ended_at=now,
        estimated=executor.estimate,
    )
    success = cohort_receipt(
        executor,
        decision_id="d2",
        action_id="a2",
        capability="text.stats",
        executor_id="x",
        executor_kind=ExecutorKind.PYTHON,
        status=ExecutionStatus.SUCCESS,
        started_at=now,
        ended_at=now + timedelta(milliseconds=10),
        estimated=executor.estimate,
        actual_resources=ResourceVector(latency_ms=10),
        output_valid=True,
    )
    router.store.save_receipt(delegated)
    router.store.save_receipt(success)
    estimate = HistoricalEstimator(router.store).estimate(
        executor, router._policy_for(ActionRequest(capability="text.stats"))
    )
    assert estimate.sample_size == 1
    assert estimate.resources.latency_ms < 100
    import asyncio

    asyncio.run(router.close())


def test_history_keeps_all_token_dimensions_integral():
    executor = python_spec("x", "aeep.examples.tools:text_stats")
    router = Router(manifest_with(executor))
    now = datetime.now(UTC)
    router.store.save_receipt(
        cohort_receipt(
            executor,
            decision_id="d-token",
            action_id="a-token",
            capability="text.stats",
            executor_id="x",
            executor_kind=ExecutorKind.PYTHON,
            status=ExecutionStatus.SUCCESS,
            started_at=now,
            ended_at=now,
            estimated=executor.estimate,
            actual_resources=ResourceVector(
                input_tokens=118,
                cached_input_tokens=7424,
                cache_write_input_tokens=7,
                output_tokens=419,
                reasoning_output_tokens=404,
            ),
            output_valid=True,
        )
    )

    resources = HistoricalEstimator(router.store).estimate(
        executor, router._policy_for(ActionRequest(capability="text.stats"))
    ).resources

    assert isinstance(resources.cache_write_input_tokens, int)
    assert isinstance(resources.reasoning_output_tokens, int)
    import asyncio

    asyncio.run(router.close())


def test_invalid_output_counts_against_success_probability():
    executor = python_spec("x", "aeep.examples.tools:text_stats")
    router = Router(manifest_with(executor))
    now = datetime.now(UTC)
    for index in range(5):
        router.store.save_receipt(
            cohort_receipt(
                executor,
                decision_id=f"d{index}",
                action_id=f"a{index}",
                capability="text.stats",
                executor_id="x",
                executor_kind=ExecutorKind.PYTHON,
                status=ExecutionStatus.SUCCESS,
                started_at=now,
                ended_at=now,
                estimated=executor.estimate,
                actual_resources=ResourceVector(latency_ms=10),
                output_valid=False,
            )
        )
    policy = router._policy_for(ActionRequest(capability="text.stats"))
    estimate = HistoricalEstimator(router.store).estimate(executor, policy)
    assert estimate.success_probability < executor.estimate.success_probability
    assert estimate.uncertainty is not None
    assert estimate.uncertainty.sample_size == 5
    assert estimate.uncertainty.resources_p95.latency_ms == 10
    assert estimate.uncertainty.success_lower_bound == 0
    assert estimate.uncertainty.cash_p95_usd is None
    assert estimate.uncertainty.quality_sample_size == 0
    assert estimate.uncertainty.quality_lower_bound is None
    import asyncio

    asyncio.run(router.close())


def test_history_is_conditioned_on_input_size_bucket():
    executor = python_spec("x", "aeep.examples.tools:text_stats", latency_ms=100)
    router = Router(manifest_with(executor))
    now = datetime.now(UTC)
    for value, latency in [({"text": "x"}, 5), ({"text": "x" * 10_000}, 50_000)]:
        router.store.save_receipt(
            cohort_receipt(
                executor,
                decision_id=f"d{latency}",
                action_id=f"a{latency}",
                capability="text.stats",
                executor_id="x",
                executor_kind=ExecutorKind.PYTHON,
                status=ExecutionStatus.SUCCESS,
                started_at=now,
                ended_at=now,
                estimated=executor.estimate,
                action_features=action_features(value),
                actual_resources=ResourceVector(latency_ms=latency),
                output_valid=True,
            )
        )
    estimate = HistoricalEstimator(router.store).estimate(
        executor,
        router._policy_for(ActionRequest(capability="text.stats")),
        action_features({"text": "x"}),
    )
    assert estimate.sample_size == 1
    assert estimate.resources.latency_ms < 100
    import asyncio

    asyncio.run(router.close())


def test_history_never_crosses_executor_fingerprint() -> None:
    original = python_spec("x", "aeep.examples.tools:text_stats", latency_ms=100)
    changed = original.model_copy(deep=True)
    changed.config["callable"] = "aeep.examples.tools:count_words"
    router = Router(manifest_with(original))
    features = action_features({"text": "x"})
    now = datetime.now(UTC)
    router.store.save_receipt(
        cohort_receipt(
            original,
            decision_id="d",
            action_id="a",
            capability=original.capability,
            executor_id=original.id,
            executor_kind=original.kind,
            status=ExecutionStatus.SUCCESS,
            started_at=now,
            ended_at=now,
            estimated=original.estimate,
            action_features=features,
            actual_resources=ResourceVector(latency_ms=1),
            output_valid=True,
        )
    )

    estimate = HistoricalEstimator(router.store).estimate(
        changed,
        router._policy_for(ActionRequest(capability="text.stats")),
        features,
    )

    assert estimate.sample_size == 0
    assert estimate.resources.latency_ms == changed.estimate.resources.latency_ms
    import asyncio

    asyncio.run(router.close())
