from __future__ import annotations

from datetime import UTC, datetime, timedelta

from conftest import manifest_with, python_spec

from aeep.estimator import HistoricalEstimator
from aeep.models import (
    ActionRequest,
    ExecutionReceipt,
    ExecutionStatus,
    ExecutorKind,
    ResourceVector,
)
from aeep.profiler import ActionProfiler, approximate_tokens
from aeep.router import Router


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
    delegated = ExecutionReceipt(
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
    success = ExecutionReceipt(
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
    estimate = HistoricalEstimator(router.store).estimate(executor, router._policy_for(ActionRequest(capability="text.stats")))
    assert estimate.sample_size == 1
    assert estimate.resources.latency_ms < 100
    import asyncio
    asyncio.run(router.close())


def test_invalid_output_counts_against_success_probability():
    executor = python_spec("x", "aeep.examples.tools:text_stats")
    router = Router(manifest_with(executor))
    now = datetime.now(UTC)
    for index in range(5):
        router.store.save_receipt(
            ExecutionReceipt(
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
    import asyncio
    asyncio.run(router.close())
