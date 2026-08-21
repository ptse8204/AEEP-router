from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
from test_v04_acceptance import _execution_router
from test_v04_prepared_execution_edges import EconomicExecutor
from test_v04_prepared_routing import (
    MutableClock,
    SignedQuoteProvider,
    _manifest,
    _route,
    _router,
)

from aeep.economic.signing import Ed25519Signer
from aeep.models import (
    ActionRequest,
    AgentBudget,
    AuthorizationPolicy,
    ExecutionStatus,
    PreparedDecisionState,
    ProviderExecutionStatus,
    QuoteRequestV2,
)
from aeep.workflow import (
    WorkflowBudget,
    WorkflowInputBinding,
    WorkflowOutputProjection,
    WorkflowRequest,
    WorkflowStatus,
    WorkflowStep,
)


def _signer() -> Ed25519Signer:
    return Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="provider-key")


class OrderedQuoteProvider(SignedQuoteProvider):
    def __init__(
        self,
        signer: Ed25519Signer,
        clock: MutableClock,
        events: list[str],
        *,
        amounts: dict[str, tuple[str | None, str]] | None = None,
    ) -> None:
        super().__init__(signer, clock, amounts=amounts)
        self.events = events

    async def request_quote(self, request: QuoteRequestV2):
        self.events.append(f"quote:{request.action_id}")
        return await super().request_quote(request)


class OrderedExecutor(EconomicExecutor):
    def __init__(
        self,
        signer: Ed25519Signer,
        clock: MutableClock,
        events: list[str],
    ) -> None:
        super().__init__(signer, clock)
        self.events = events

    async def execute(self, context):
        self.events.append(f"execute:{context.request.action_id}")
        return await super().execute(context)


class ConcurrentQuoteProvider(SignedQuoteProvider):
    def __init__(
        self,
        signer: Ed25519Signer,
        clock: MutableClock,
        *,
        expected_actions: int,
        amounts: dict[str, tuple[str | None, str]],
    ) -> None:
        super().__init__(signer, clock, amounts=amounts)
        self.expected_actions = expected_actions
        self.started: set[str] = set()
        self.all_started = asyncio.Event()

    async def request_quote(self, request: QuoteRequestV2):
        self.started.add(request.action_id)
        if len(self.started) == self.expected_actions:
            self.all_started.set()
        await asyncio.wait_for(self.all_started.wait(), timeout=1)
        return await super().request_quote(request)


def _paid_router(
    provider: SignedQuoteProvider,
    signer: Ed25519Signer,
    clock: MutableClock,
    *routes,
):
    manifest = _manifest(*routes)
    manifest.budget = AgentBudget(
        daily_marketplace_limit_usd=1,
        max_per_action_usd=1,
        prepaid_balance_usd=1,
        authorization=AuthorizationPolicy(
            auto_approve_under_usd=1,
            financial_actions_require_human=False,
        ),
    )
    return _router(manifest, provider, signer, clock)


@pytest.mark.asyncio
async def test_workflow_quotes_only_dependency_resolved_inputs_and_settles_each_step() -> None:
    clock = MutableClock()
    signer = _signer()
    events: list[str] = []
    provider = OrderedQuoteProvider(
        signer,
        clock,
        events,
        amounts={"remote.workflow": ("0.0038", "0.0050")},
    )
    route = _route(
        "remote.workflow",
        latency_ms=1,
        cash="0.001",
        provider=True,
        disclosure=[
            {"source": "action_features.input_bytes", "name": "input_bytes"}
        ],
    )
    router = _execution_router(route, provider, signer, clock)
    executor = OrderedExecutor(signer, clock, events)
    router._executors[route.kind] = executor
    workflow = WorkflowRequest(
        workflow_id="economic-sequential",
        budget=WorkflowBudget(max_cash_usd=Decimal("0.0200")),
        steps=[
            WorkflowStep(
                step_id="first",
                action=ActionRequest(
                    action_id="workflow-first",
                    capability=route.capability,
                    input={"text": "real first input"},
                ),
            ),
            WorkflowStep(
                step_id="second",
                action=ActionRequest(
                    action_id="workflow-second",
                    capability=route.capability,
                    input={"text": "future placeholder must not be quoted"},
                ),
                depends_on=["first"],
                bindings=[
                    WorkflowInputBinding(
                        target_path="/text",
                        source_step_id="first",
                        source_path="/result",
                    )
                ],
            ),
        ],
        outputs=[
            WorkflowOutputProjection(name="result", step_id="second", path="/result")
        ],
    )
    try:
        outcome = await router.execute_workflow(workflow, payment_approved=True)

        assert outcome.status is WorkflowStatus.SUCCESS
        assert outcome.outputs == {"result": "ok"}
        assert events == [
            "quote:workflow-first",
            "execute:workflow-first",
            "quote:workflow-second",
            "execute:workflow-second",
        ]
        assert [request.action_id for request in provider.requests] == [
            "workflow-first",
            "workflow-second",
        ]
        assert provider.requests[1].disclosed_quote_features["input_bytes"] < (
            provider.requests[0].disclosed_quote_features["input_bytes"]
        )
        settlements = router.store.list_settlement_receipts()
        assert len(settlements) == 2
        assert all(item.captured_amount.amount == Decimal("0.0038") for item in settlements)
        assert all(item.released_amount.amount == Decimal("0.0012") for item in settlements)
        assert outcome.actual_cash_total_usd == Decimal("0.0076")
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_workflow_prepares_ready_steps_concurrently_and_cancels_over_budget() -> None:
    clock = MutableClock()
    signer = _signer()
    provider = ConcurrentQuoteProvider(
        signer,
        clock,
        expected_actions=2,
        amounts={"remote.workflow": ("0.0050", "0.0060")},
    )
    route = _route("remote.workflow", latency_ms=1, cash="0.001", provider=True)
    router = _execution_router(route, provider, signer, clock)
    executor = EconomicExecutor(signer, clock)
    router._executors[route.kind] = executor
    workflow = WorkflowRequest(
        workflow_id="economic-over-budget",
        budget=WorkflowBudget(max_cash_usd=Decimal("0.0100")),
        steps=[
            WorkflowStep(
                step_id="a",
                action=ActionRequest(
                    action_id="workflow-ready-a",
                    capability=route.capability,
                    input={"text": "a"},
                ),
            ),
            WorkflowStep(
                step_id="b",
                action=ActionRequest(
                    action_id="workflow-ready-b",
                    capability=route.capability,
                    input={"text": "b"},
                ),
            ),
        ],
    )
    try:
        outcome = await router.execute_workflow(workflow, payment_approved=True)

        assert outcome.status is WorkflowStatus.FAILED
        assert "maxima exceed" in (outcome.error or "")
        assert provider.started == {"workflow-ready-a", "workflow-ready-b"}
        assert executor.calls == []
        assert router.store.list_payment_reservations_v2() == []
        prepared = router.store.list_prepared_decisions()
        assert len(prepared) == 2
        assert all(item.state is PreparedDecisionState.CANCELLED for item in prepared)
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_non_idempotent_workflow_failure_never_falls_back_or_reinvokes() -> None:
    clock = MutableClock()
    signer = _signer()
    routes = [
        _route("remote.primary", latency_ms=1, cash="0.001", provider=True),
        _route("remote.fallback", latency_ms=2, cash="0.001", provider=True),
    ]
    for route in routes:
        route.idempotent = False
    provider = SignedQuoteProvider(
        signer,
        clock,
        amounts={
            "remote.primary": ("0.0038", "0.0050"),
            "remote.fallback": ("0.0038", "0.0050"),
        },
    )
    router = _paid_router(provider, signer, clock, *routes)
    executor = EconomicExecutor(
        signer,
        clock,
        local_status=ExecutionStatus.TIMEOUT,
        provider_status=ProviderExecutionStatus.TIMEOUT,
        amount=None,
    )
    router._executors[routes[0].kind] = executor
    workflow = WorkflowRequest(
        workflow_id="economic-non-idempotent",
        budget=WorkflowBudget(max_cash_usd=Decimal("0.0100")),
        steps=[
            WorkflowStep(
                step_id="submit",
                action=ActionRequest(
                    action_id="workflow-submit",
                    capability=routes[0].capability,
                    input={"text": "consequential payload"},
                ),
            )
        ],
    )
    try:
        outcome = await router.execute_workflow(workflow, payment_approved=True)

        assert outcome.status is WorkflowStatus.FAILED
        assert len(executor.calls) == 1
        assert len(router.store.list_prepared_decisions()) == 1
        assert set(provider.calls) == {"remote.primary", "remote.fallback"}
    finally:
        await router.close()
