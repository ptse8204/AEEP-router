from __future__ import annotations

import asyncio

import pytest

from aeep.errors import ApprovalRequired, NoRouteError
from aeep.models import (
    ActionConstraints,
    ActionRequest,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    Locality,
    PolicyConfig,
    ResourceVector,
    RouteEstimate,
    SideEffect,
)
from aeep.router import Router

from conftest import manifest_with, python_spec


@pytest.mark.asyncio
async def test_route_and_execute_best_python(text_schema, stats_schema):
    fast = python_spec(
        "fast",
        "aeep.examples.tools:text_stats",
        latency_ms=2,
        input_schema=text_schema,
        output_schema=stats_schema,
    )
    slow = python_spec(
        "slow",
        "aeep.examples.tools:text_stats",
        latency_ms=200,
        cost=0.01,
        input_schema=text_schema,
        output_schema=stats_schema,
    )
    router = Router(manifest_with(slow, fast))
    decision = router.route(ActionRequest(capability="text.stats", input={"text": "a b"}))
    assert decision.selected_executor_id == "fast"
    assert decision.candidates[0].rank == 1
    outcome = await router.execute(decision)
    assert outcome.ok
    assert outcome.output == {"characters": 3, "words": 2, "lines": 1}
    assert outcome.receipts[0].output_valid is True
    assert router.store.get_decision(decision.decision_id) is not None
    await router.close()


@pytest.mark.asyncio
async def test_fallback_on_failure(text_schema, stats_schema):
    broken = python_spec(
        "a-broken",
        "aeep.examples.tools:always_fail",
        latency_ms=1,
        input_schema=text_schema,
        output_schema=stats_schema,
    )
    good = python_spec(
        "b-good",
        "aeep.examples.tools:text_stats",
        latency_ms=20,
        input_schema=text_schema,
        output_schema=stats_schema,
    )
    router = Router(manifest_with(broken, good))
    outcome = await router.execute(ActionRequest(capability="text.stats", input={"text": "ok"}))
    assert outcome.ok
    assert [r.executor_id for r in outcome.receipts] == ["a-broken", "b-good"]
    assert outcome.receipts[0].status == ExecutionStatus.FAILED
    await router.close()


@pytest.mark.asyncio
async def test_validation_failure_can_fallback(text_schema, stats_schema):
    invalid = python_spec(
        "a-invalid",
        "aeep.examples.tools:invalid_stats",
        latency_ms=1,
        input_schema=text_schema,
        output_schema=stats_schema,
    )
    good = python_spec(
        "b-good",
        "aeep.examples.tools:text_stats",
        latency_ms=10,
        input_schema=text_schema,
        output_schema=stats_schema,
    )
    router = Router(manifest_with(invalid, good))
    outcome = await router.execute(ActionRequest(capability="text.stats", input={"text": "ok"}))
    assert outcome.ok
    assert outcome.receipts[0].status == ExecutionStatus.SUCCESS
    assert outcome.receipts[0].output_valid is False
    assert len(outcome.receipts) == 2
    await router.close()


@pytest.mark.asyncio
async def test_non_idempotent_failure_does_not_fallback(text_schema, stats_schema):
    broken = python_spec(
        "a-write",
        "aeep.examples.tools:always_fail",
        latency_ms=1,
        input_schema=text_schema,
        output_schema=stats_schema,
        side_effect=SideEffect.WRITE,
        idempotent=False,
    )
    good = python_spec(
        "b-good",
        "aeep.examples.tools:text_stats",
        latency_ms=2,
        input_schema=text_schema,
        output_schema=stats_schema,
        side_effect=SideEffect.WRITE,
    )
    custom = PolicyConfig(name="write", constraints=ActionConstraints(max_side_effect=SideEffect.WRITE))
    router = Router(manifest_with(broken, good, policies={"write": custom}))
    request = ActionRequest(
        capability="text.stats",
        input={"text": "x"},
        policy="write",
        constraints=ActionConstraints(max_side_effect=SideEffect.WRITE),
    )
    outcome = await router.execute(request, approved_side_effect=SideEffect.WRITE)
    assert not outcome.ok
    assert len(outcome.receipts) == 1
    await router.close()


@pytest.mark.asyncio
async def test_runtime_approval_is_separate_from_policy(text_schema, stats_schema):
    write = python_spec(
        "write",
        "aeep.examples.tools:text_stats",
        input_schema=text_schema,
        output_schema=stats_schema,
        side_effect=SideEffect.WRITE,
    )
    custom = PolicyConfig(name="write", constraints=ActionConstraints(max_side_effect=SideEffect.WRITE))
    router = Router(manifest_with(write, policies={"write": custom}))
    request = ActionRequest(
        capability="text.stats",
        input={"text": "x"},
        policy="write",
        constraints=ActionConstraints(max_side_effect=SideEffect.WRITE),
    )
    with pytest.raises(ApprovalRequired):
        await router.execute(request)
    outcome = await router.execute(request, approved_side_effect=SideEffect.WRITE)
    assert outcome.ok
    await router.close()


def test_schema_failure_explained(text_schema, stats_schema):
    executor = python_spec(
        "x",
        "aeep.examples.tools:text_stats",
        input_schema=text_schema,
        output_schema=stats_schema,
    )
    router = Router(manifest_with(executor))
    decision = router.route(ActionRequest(capability="text.stats", input={"wrong": 1}))
    assert decision.selected_executor_id is None
    assert "validation failed" in decision.candidates[0].rejection_reasons[0]
    asyncio.run(router.close())


@pytest.mark.asyncio
async def test_no_route_execute_raises():
    router = Router(manifest_with())
    with pytest.raises(NoRouteError):
        await router.execute(ActionRequest(capability="missing", input={}))
    await router.close()


@pytest.mark.asyncio
async def test_delegate_returns_plan_and_can_be_recorded():
    delegate = ExecutorSpec(
        id="browser",
        capability="page.read",
        kind=ExecutorKind.DELEGATE,
        description="host browser",
        input_schema={
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
            "additionalProperties": False,
        },
        estimate=RouteEstimate(resources=ResourceVector(latency_ms=1000, context_tokens=500)),
        side_effect=SideEffect.READ,
        locality=Locality.LOCAL,
        config={"instructions": "Open {input.url} and return its title."},
    )
    router = Router(manifest_with(delegate))
    outcome = await router.execute(ActionRequest(capability="page.read", input={"url": "https://example.com"}))
    assert outcome.status == ExecutionStatus.DELEGATED
    assert "example.com" in (outcome.delegated_instructions or "")
    receipt = router.record_external_outcome(
        {
            "decision_id": outcome.decision.decision_id,
            "executor_id": "browser",
            "status": "success",
            "actual_resources": {"latency_ms": 500, "context_tokens": 200},
            "output_valid": True,
        }
    )
    assert receipt.metadata["externally_reported"] is True
    await router.close()


def test_persisted_decision_redacts_sensitive_input_and_context(text_schema, stats_schema):
    executor = python_spec(
        "safe",
        "aeep.examples.tools:text_stats",
        input_schema=text_schema,
        output_schema=stats_schema,
    )
    router = Router(manifest_with(executor))
    request = ActionRequest(
        capability="text.stats",
        input={"text": "secret payload"},
        context={"labels": {"customer": "private"}},
    )
    decision = router.route(request)
    assert decision.action.input == {"text": "secret payload"}
    stored = router.store.get_decision(decision.decision_id)
    assert stored is not None
    assert stored.action.input == {"__aeep_redacted__": True}
    assert stored.action.context.labels == {"aeep.persistence": "context-redacted"}
    asyncio.run(router.close())


@pytest.mark.asyncio
async def test_redacted_persisted_decision_cannot_be_executed(text_schema, stats_schema):
    executor = python_spec(
        "safe",
        "aeep.examples.tools:text_stats",
        input_schema=text_schema,
        output_schema=stats_schema,
    )
    router = Router(manifest_with(executor))
    decision = router.route(ActionRequest(capability="text.stats", input={"text": "secret"}))
    stored = router.store.get_decision(decision.decision_id)
    assert stored is not None
    from aeep.errors import ConfigurationError

    with pytest.raises(ConfigurationError, match="redacted inputs"):
        await router.execute(stored)
    await router.close()


@pytest.mark.asyncio
async def test_invalid_output_without_fallback_has_failed_outcome(text_schema, stats_schema):
    from aeep.models import FallbackConfig

    invalid = python_spec(
        "invalid-only",
        "aeep.examples.tools:invalid_stats",
        input_schema=text_schema,
        output_schema=stats_schema,
    )
    policy = PolicyConfig(name="no-fallback", fallback=FallbackConfig(enabled=False))
    router = Router(manifest_with(invalid, policies={"no-fallback": policy}))
    outcome = await router.execute(
        ActionRequest(capability="text.stats", input={"text": "x"}, policy="no-fallback")
    )
    assert not outcome.ok
    assert outcome.status == ExecutionStatus.FAILED
    assert outcome.receipts[0].status == ExecutionStatus.SUCCESS
    assert outcome.receipts[0].output_valid is False
    await router.close()


@pytest.mark.asyncio
async def test_benchmark_executes_feasible_routes_and_ranks_actuals(text_schema, stats_schema):
    fast = python_spec(
        "fast-actual",
        "aeep.examples.tools:text_stats",
        latency_ms=2,
        input_schema=text_schema,
        output_schema=stats_schema,
    )
    slow = python_spec(
        "slow-actual",
        "aeep.examples.tools:slow_text_stats",
        latency_ms=60,
        input_schema=text_schema,
        output_schema=stats_schema,
    )
    router = Router(manifest_with(fast, slow))
    result = await router.benchmark(
        ActionRequest(capability="text.stats", input={"text": "one two"})
    )
    assert len(result.entries) == 2
    assert all(entry.ok for entry in result.entries)
    by_id = {entry.executor_id: entry for entry in result.entries}
    assert by_id["fast-actual"].actual_rank == 1
    assert by_id["slow-actual"].actual_rank == 2
    assert by_id["fast-actual"].receipt_id
    await router.close()


@pytest.mark.asyncio
async def test_external_outcome_can_only_report_selected_delegate_once(text_schema, stats_schema):
    delegate = ExecutorSpec(
        id="browser",
        capability="page.read",
        kind=ExecutorKind.DELEGATE,
        description="host browser",
        input_schema={"type": "object"},
        estimate=RouteEstimate(resources=ResourceVector(latency_ms=100)),
        side_effect=SideEffect.READ,
        locality=Locality.LOCAL,
        config={"instructions": "Read the page."},
    )
    other_delegate = delegate.model_copy(
        update={"id": "other", "estimate": RouteEstimate(resources=ResourceVector(latency_ms=9000))}
    )
    non_delegate = python_spec(
        "python",
        "aeep.examples.tools:text_stats",
        input_schema=text_schema,
        output_schema=stats_schema,
    )
    router = Router(manifest_with(delegate, other_delegate, non_delegate))
    try:
        outcome = await router.execute(ActionRequest(capability="page.read", input={}))
        assert outcome.decision.selected_executor_id == "browser"
        report = {
            "decision_id": outcome.decision.decision_id,
            "executor_id": "browser",
            "status": "success",
            "actual_resources": {"latency_ms": 50},
        }
        router.record_external_outcome(report)
        from aeep.errors import ConfigurationError

        with pytest.raises(ConfigurationError, match="already reported"):
            router.record_external_outcome(report)
        with pytest.raises(ConfigurationError, match="not the selected route"):
            router.record_external_outcome({**report, "executor_id": "other"})

        text_decision = router.route(
            ActionRequest(capability="text.stats", input={"text": "x"})
        )
        with pytest.raises(ConfigurationError, match="only accepted for delegate"):
            router.record_external_outcome(
                {
                    "decision_id": text_decision.decision_id,
                    "executor_id": "python",
                    "status": "success",
                }
            )
    finally:
        await router.close()


def test_external_outcome_requires_terminal_consistent_status():
    from pydantic import ValidationError

    from aeep.models import ExternalOutcomeReport

    with pytest.raises(ValidationError, match="must be final"):
        ExternalOutcomeReport(
            decision_id="dec_x",
            executor_id="browser",
            status=ExecutionStatus.UNKNOWN,
        )
    with pytest.raises(ValidationError, match="cannot declare output_valid"):
        ExternalOutcomeReport(
            decision_id="dec_x",
            executor_id="browser",
            status=ExecutionStatus.FAILED,
            output_valid=True,
        )
