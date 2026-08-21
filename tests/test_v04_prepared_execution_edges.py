from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal

import pytest
from test_v04_acceptance import _execution_router, _signer
from test_v04_prepared_routing import (
    UNSIGNED,
    MutableClock,
    SignedQuoteProvider,
    _manifest,
    _request,
    _route,
    _router,
)

from aeep.economic.canonical import canonical_payload
from aeep.economic.prepared import executor_fingerprint
from aeep.economic.signing import Ed25519Signer
from aeep.errors import ConfigurationError
from aeep.executors.base import BaseExecutor, ExecutionContext
from aeep.models import (
    AgentBudget,
    AuthorizationKind,
    AuthorizationPolicy,
    BillingTrigger,
    BoundedQuote,
    CapabilityOffer,
    CurrencyAmount,
    EconomicEvidenceLevel,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    FailureChargePolicy,
    PaymentReservationState,
    PreparedDecisionState,
    PricingRule,
    ProviderExecutionStatus,
    QuoteFailurePolicy,
    QuoteRequestV2,
    RawExecution,
    ResourceVector,
    RetryChargePolicy,
    UsageStatement,
)


class EconomicExecutor(BaseExecutor):
    def __init__(
        self,
        signer: Ed25519Signer,
        clock: MutableClock,
        *,
        local_status: ExecutionStatus = ExecutionStatus.SUCCESS,
        provider_status: ProviderExecutionStatus = ProviderExecutionStatus.SUCCESS,
        amount: str | None = "0.0038",
        include_usage: bool = True,
        gated: bool = False,
    ) -> None:
        self.signer = signer
        self.clock = clock
        self.local_status = local_status
        self.provider_status = provider_status
        self.amount = amount
        self.include_usage = include_usage
        self.calls: list[ExecutionContext] = []
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        if not gated:
            self.release.set()

    async def execute(self, context: ExecutionContext) -> RawExecution:
        self.calls.append(context)
        self.entered.set()
        await self.release.wait()
        output: object = {"result": "ok"}
        if self.include_usage:
            assert context.prepared_id is not None
            assert context.quote_id is not None
            assert context.attempt_id is not None
            statement = UsageStatement(
                usage_statement_id=f"usage-{context.attempt_id}",
                quote_id=context.quote_id,
                prepared_id=context.prepared_id,
                action_id=context.request.action_id,
                attempt_id=context.attempt_id,
                provider_id=context.spec.provider_id or "",
                executor_id=context.spec.id,
                executor_fingerprint=executor_fingerprint(context.spec),
                execution_status=self.provider_status,
                provider_calculated_amount=(
                    CurrencyAmount(amount=self.amount, currency="USD")
                    if self.amount is not None
                    else None
                ),
                started_at=self.clock(),
                completed_at=self.clock(),
                issued_at=self.clock(),
                signature=UNSIGNED,
            )
            statement = statement.model_copy(
                update={"signature": self.signer.sign(canonical_payload(statement))}
            )
            output = {
                "output": output,
                "usage_statement": statement.model_dump(mode="json"),
            }
        return RawExecution(
            status=self.local_status,
            output=output,
            resources=ResourceVector(latency_ms=1),
            error_type=(
                "ProviderFailure"
                if self.local_status is not ExecutionStatus.SUCCESS
                else None
            ),
        )


class RouteDispatchExecutor(BaseExecutor):
    def __init__(
        self,
        signer: Ed25519Signer,
        clock: MutableClock,
        *,
        failed_executor_id: str,
        failed_status: ExecutionStatus = ExecutionStatus.FAILED,
        include_failed_usage: bool = True,
    ) -> None:
        self.failed_executor_id = failed_executor_id
        self.failed = EconomicExecutor(
            signer,
            clock,
            local_status=failed_status,
            provider_status=ProviderExecutionStatus.FAILED,
            amount="0",
            include_usage=include_failed_usage,
        )
        self.succeeded = EconomicExecutor(signer, clock)
        self.calls: list[ExecutionContext] = []

    async def execute(self, context: ExecutionContext) -> RawExecution:
        self.calls.append(context)
        target = (
            self.failed
            if context.spec.id == self.failed_executor_id
            else self.succeeded
        )
        return await target.execute(context)


class FixedOfferFallbackProvider(SignedQuoteProvider):
    def __init__(
        self,
        signer: Ed25519Signer,
        clock: MutableClock,
        offer: CapabilityOffer,
    ) -> None:
        super().__init__(signer, clock, failing={offer.executor_id})
        self.offer = offer

    async def get_offers(
        self,
        capability: str,
        executor_ids: Sequence[str],
    ) -> tuple[CapabilityOffer, ...]:
        self.offer_requests.extend(executor_ids)
        if self.offer.capability == capability and self.offer.executor_id in executor_ids:
            return (self.offer,)
        return ()

    async def request_quote(self, request: QuoteRequestV2) -> BoundedQuote:
        return await super().request_quote(request)


def _fixed_offer(
    signer: Ed25519Signer,
    clock: MutableClock,
    route: ExecutorSpec,
) -> CapabilityOffer:
    offer = CapabilityOffer(
        offer_id=f"offer-{route.id}",
        provider_id=route.provider_id or "",
        capability=route.capability,
        executor_id=route.id,
        executor_fingerprint=executor_fingerprint(route),
        pricing_rules=(
            PricingRule(
                rule_id="fixed",
                fixed_amount=CurrencyAmount(amount="0.0038", currency="USD"),
            ),
        ),
        billing_trigger=BillingTrigger.ON_SUCCESS,
        failure_charge_policy=FailureChargePolicy.NO_CHARGE,
        retry_charge_policy=RetryChargePolicy.EACH_ATTEMPT,
        settlement_currency="USD",
        valid_from=clock() - timedelta(minutes=1),
        valid_until=clock() + timedelta(hours=1),
        terms_digest=f"sha256:{'7' * 64}",
        issued_at=clock(),
        signature=UNSIGNED,
    )
    return offer.model_copy(update={"signature": signer.sign(canonical_payload(offer))})


def _offer_requirements() -> dict[str, object]:
    return {
        "require_binding_quote_for_paid_routes": False,
        "allow_verified_static_offer": True,
        "minimum_evidence_level": EconomicEvidenceLevel.PUBLISHED_OFFER,
        "quote_failure_policy": QuoteFailurePolicy.ALLOW_VERIFIED_OFFER,
    }


def _offer_router(
    route: ExecutorSpec,
    provider: FixedOfferFallbackProvider,
    signer: Ed25519Signer,
    clock: MutableClock,
):
    manifest = _manifest(route, requirements=_offer_requirements())
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
async def test_confirmed_free_prepared_execution_needs_no_payment_record() -> None:
    clock = MutableClock()
    signer = _signer()
    provider = SignedQuoteProvider(signer, clock)
    router = _router(
        _manifest(_route("local.free", latency_ms=1, cash="0")),
        provider,
        signer,
        clock,
    )
    executor = EconomicExecutor(signer, clock, include_usage=False)
    router._executors[ExecutorKind.PYTHON] = executor
    try:
        prepared = await router.prepare_route(_request(action_id="free-action"))
        outcome = await router.execute_prepared(prepared.prepared_id)

        assert outcome.ok
        assert len(executor.calls) == 1
        assert router.store.get_prepared_decision(prepared.prepared_id).state is (
            PreparedDecisionState.SETTLED
        )
        assert router.store.list_payment_reservations_v2() == []
        assert router.store.list_settlement_receipts(prepared_id=prepared.prepared_id) == []
        assert outcome.receipts[0].accounting.cash.actual_cash_cost("USD") == Decimal(0)
        assert outcome.receipts[0].metadata["cash_evidence_level"] == (
            EconomicEvidenceLevel.OPERATOR_ATTESTED.value
        )
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_missing_usage_keeps_reservation_indeterminate_and_unsettled() -> None:
    clock = MutableClock()
    signer = _signer()
    provider = SignedQuoteProvider(
        signer,
        clock,
        amounts={"remote.dynamic": ("0.0038", "0.0050")},
    )
    router = _execution_router(
        _route("remote.dynamic", latency_ms=1, cash="0.001", provider=True),
        provider,
        signer,
        clock,
    )
    executor = EconomicExecutor(signer, clock, include_usage=False)
    router._executors[ExecutorKind.PYTHON] = executor
    try:
        prepared = await router.prepare_route(_request(action_id="missing-usage"))
        outcome = await router.execute_prepared(
            prepared.prepared_id,
            payment_approved=True,
        )

        assert not outcome.ok
        assert router.store.get_prepared_decision(prepared.prepared_id).state is (
            PreparedDecisionState.INDETERMINATE
        )
        reservation = router.store.list_payment_reservations_v2()[0]
        assert reservation.state is PaymentReservationState.INDETERMINATE
        assert router.store.list_usage_statements(prepared_id=prepared.prepared_id) == []
        assert router.store.list_settlement_receipts(prepared_id=prepared.prepared_id) == []
        assert outcome.receipts[0].accounting.cash.actual_cash_cost("USD") is None
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_local_provider_status_conflict_is_indeterminate_without_capture() -> None:
    clock = MutableClock()
    signer = _signer()
    provider = SignedQuoteProvider(
        signer,
        clock,
        amounts={"remote.dynamic": ("0.0038", "0.0050")},
    )
    router = _execution_router(
        _route("remote.dynamic", latency_ms=1, cash="0.001", provider=True),
        provider,
        signer,
        clock,
    )
    executor = EconomicExecutor(
        signer,
        clock,
        local_status=ExecutionStatus.FAILED,
        provider_status=ProviderExecutionStatus.SUCCESS,
    )
    router._executors[ExecutorKind.PYTHON] = executor
    try:
        prepared = await router.prepare_route(_request(action_id="status-conflict"))
        outcome = await router.execute_prepared(
            prepared.prepared_id,
            payment_approved=True,
        )

        assert not outcome.ok
        assert outcome.status is ExecutionStatus.FAILED
        assert router.store.get_prepared_decision(prepared.prepared_id).state is (
            PreparedDecisionState.INDETERMINATE
        )
        assert router.store.list_payment_reservations_v2()[0].state is (
            PaymentReservationState.INDETERMINATE
        )
        assert len(router.store.list_usage_statements(prepared_id=prepared.prepared_id)) == 1
        assert router.store.list_settlement_receipts(prepared_id=prepared.prepared_id) == []
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_provider_amount_above_quote_maximum_opens_dispute_without_capture() -> None:
    clock = MutableClock()
    signer = _signer()
    provider = SignedQuoteProvider(
        signer,
        clock,
        amounts={"remote.dynamic": ("0.0038", "0.0050")},
    )
    router = _execution_router(
        _route("remote.dynamic", latency_ms=1, cash="0.001", provider=True),
        provider,
        signer,
        clock,
    )
    executor = EconomicExecutor(signer, clock, amount="0.0051")
    router._executors[ExecutorKind.PYTHON] = executor
    try:
        prepared = await router.prepare_route(_request(action_id="over-maximum"))
        outcome = await router.execute_prepared(
            prepared.prepared_id,
            payment_approved=True,
        )

        assert not outcome.ok
        assert router.store.get_prepared_decision(prepared.prepared_id).state is (
            PreparedDecisionState.DISPUTED
        )
        disputes = router.store.list_pricing_disputes(prepared_id=prepared.prepared_id)
        assert len(disputes) == 1
        assert disputes[0].quoted_maximum.amount == Decimal("0.0050")
        assert disputes[0].provider_claimed_amount.amount == Decimal("0.0051")
        assert router.store.list_payment_reservations_v2()[0].state is (
            PaymentReservationState.INDETERMINATE
        )
        assert router.store.list_settlement_receipts(prepared_id=prepared.prepared_id) == []
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_cancel_reserved_decision_releases_full_authorization() -> None:
    clock = MutableClock()
    signer = _signer()
    provider = SignedQuoteProvider(
        signer,
        clock,
        amounts={"remote.dynamic": ("0.0038", "0.0050")},
    )
    router = _execution_router(
        _route("remote.dynamic", latency_ms=1, cash="0.001", provider=True),
        provider,
        signer,
        clock,
    )
    try:
        prepared = await router.prepare_route(_request(action_id="cancel-reserved"))
        assert prepared.authorization_kind is not None
        assert prepared.authorization_id is not None
        assert prepared.maximum_cash_authorization is not None
        claim_token = "test-cancel-claim"
        router.store.claim_prepared_decision(
            prepared.prepared_id,
            claim_token=claim_token,
            claimed_at=clock(),
        )
        assert router.budget_manager is not None
        reservation = await router.budget_manager.reserve_v2(
            prepared_id=prepared.prepared_id,
            quote_id=prepared.selected_quote_id,
            authorization_kind=prepared.authorization_kind,
            authorization_id=prepared.authorization_id,
            action_id=prepared.action_id,
            attempt_id="attempt-cancel",
            charge_id="charge-cancel",
            maximum_amount=prepared.maximum_cash_authorization,
            idempotency_key="reserve-cancel",
            claim_token=claim_token,
            payment_approved=True,
            executor_id=prepared.selected_executor_id or "",
        )

        cancelled = await router.cancel_prepared(prepared.prepared_id)

        assert cancelled.state is PreparedDecisionState.RELEASED
        stored = router.store.get_payment_reservation_v2(reservation.reservation_id)
        assert stored is not None and stored.state is PaymentReservationState.RELEASED
        settlements = router.store.list_settlement_receipts(prepared_id=prepared.prepared_id)
        assert len(settlements) == 1
        assert settlements[0].captured_amount.amount == Decimal(0)
        assert settlements[0].released_amount.amount == Decimal("0.0050")
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_fixed_published_offer_fallback_executes_and_settles_full_charge() -> None:
    clock = MutableClock()
    signer = _signer()
    route = _route("remote.fixed", latency_ms=1, cash="0.001", provider=True)
    offer = _fixed_offer(signer, clock, route)
    provider = FixedOfferFallbackProvider(signer, clock, offer)
    router = _offer_router(route, provider, signer, clock)
    executor = EconomicExecutor(signer, clock, include_usage=False)
    router._executors[ExecutorKind.PYTHON] = executor
    try:
        prepared = await router.prepare_route(_request(action_id="fixed-offer"))

        assert prepared.selected_quote_id is None
        assert prepared.selected_offer_id == offer.offer_id
        assert prepared.authorization_kind is AuthorizationKind.PUBLISHED_OFFER
        assert prepared.authorization_id == offer.offer_id
        assert prepared.maximum_cash_authorization == CurrencyAmount(
            amount="0.0038",
            currency="USD",
        )

        outcome = await router.execute_prepared(
            prepared.prepared_id,
            payment_approved=True,
        )

        assert outcome.ok
        assert len(executor.calls) == 1
        reservations = router.store.list_payment_reservations_v2()
        settlements = router.store.list_settlement_receipts(prepared_id=prepared.prepared_id)
        assert len(reservations) == len(settlements) == 1
        assert reservations[0].quote_id is None
        assert reservations[0].authorization_kind is AuthorizationKind.PUBLISHED_OFFER
        assert reservations[0].authorization_id == offer.offer_id
        assert settlements[0].reserved_amount.amount == Decimal("0.0038")
        assert settlements[0].captured_amount.amount == Decimal("0.0038")
        assert settlements[0].released_amount.amount == Decimal(0)
        assert router.store.get_prepared_decision(prepared.prepared_id).state is (
            PreparedDecisionState.SETTLED
        )
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_failed_fixed_offer_captures_only_signed_attempt_fee() -> None:
    clock = MutableClock()
    signer = _signer()
    route = _route("remote.fixed-fee", latency_ms=1, cash="0.001", provider=True)
    base_offer = _fixed_offer(signer, clock, route)
    unsigned_offer = base_offer.model_copy(
        update={
            "billing_trigger": BillingTrigger.ON_ATTEMPT,
            "failure_charge_policy": FailureChargePolicy.CHARGE_FIXED_ATTEMPT_FEE,
            "fixed_attempt_fee": CurrencyAmount(amount="0.0004", currency="USD"),
            "signature": UNSIGNED,
        }
    )
    offer = unsigned_offer.model_copy(
        update={"signature": signer.sign(canonical_payload(unsigned_offer))}
    )
    provider = FixedOfferFallbackProvider(signer, clock, offer)
    router = _offer_router(route, provider, signer, clock)
    executor = EconomicExecutor(
        signer,
        clock,
        local_status=ExecutionStatus.FAILED,
        include_usage=False,
    )
    router._executors[ExecutorKind.PYTHON] = executor
    try:
        prepared = await router.prepare_route(_request(action_id="fixed-attempt-fee"))
        outcome = await router.execute_prepared(
            prepared.prepared_id,
            payment_approved=True,
        )

        assert not outcome.ok
        settlements = router.store.list_settlement_receipts(
            prepared_id=prepared.prepared_id
        )
        assert len(settlements) == 1
        assert settlements[0].reserved_amount.amount == Decimal("0.0038")
        assert settlements[0].captured_amount.amount == Decimal("0.0004")
        assert settlements[0].released_amount.amount == Decimal("0.0034")
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_revoked_published_offer_rejects_before_reservation() -> None:
    clock = MutableClock()
    signer = _signer()
    route = _route("remote.fixed", latency_ms=1, cash="0.001", provider=True)
    offer = _fixed_offer(signer, clock, route)
    provider = FixedOfferFallbackProvider(signer, clock, offer)
    router = _offer_router(route, provider, signer, clock)
    executor = EconomicExecutor(signer, clock, include_usage=False)
    router._executors[ExecutorKind.PYTHON] = executor
    try:
        prepared = await router.prepare_route(_request(action_id="revoked-offer"))
        router.store.revoke_capability_offer(offer.offer_id, revoked_at=clock())

        with pytest.raises(ConfigurationError, match="offer is unavailable or revoked"):
            await router.execute_prepared(
                prepared.prepared_id,
                payment_approved=True,
            )

        assert executor.calls == []
        assert router.store.list_payment_reservations_v2() == []
        assert router.store.get_prepared_decision(prepared.prepared_id).state is (
            PreparedDecisionState.PREPARED
        )
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_concurrent_and_repeated_execution_claims_invoke_once() -> None:
    clock = MutableClock()
    signer = _signer()
    provider = SignedQuoteProvider(signer, clock)
    router = _router(
        _manifest(_route("local.free", latency_ms=1, cash="0")),
        provider,
        signer,
        clock,
    )
    executor = EconomicExecutor(signer, clock, include_usage=False, gated=True)
    router._executors[ExecutorKind.PYTHON] = executor
    try:
        prepared = await router.prepare_route(_request(action_id="single-use"))
        first = asyncio.create_task(router.execute_prepared(prepared.prepared_id))
        await executor.entered.wait()

        with pytest.raises(ConfigurationError, match=r"not executable|not claimable"):
            await router.execute_prepared(prepared.prepared_id)

        executor.release.set()
        outcome = await first
        assert outcome.ok
        assert len(executor.calls) == 1
        with pytest.raises(ConfigurationError, match="not executable"):
            await router.execute_prepared(prepared.prepared_id)
        assert len(executor.calls) == 1
    finally:
        executor.release.set()
        await router.close()


@pytest.mark.asyncio
async def test_explicit_prepared_fallback_uses_fresh_action_quote_and_settlement() -> None:
    clock = MutableClock()
    signer = _signer()
    failed_route = _route("remote.fail", latency_ms=1, cash="0.001", provider=True)
    fallback_route = _route(
        "remote.fallback", latency_ms=20, cash="0.001", provider=True
    )
    provider = SignedQuoteProvider(
        signer,
        clock,
        amounts={
            failed_route.id: ("0.0038", "0.0050"),
            fallback_route.id: ("0.0038", "0.0050"),
        },
    )
    manifest = _manifest(failed_route, fallback_route)
    manifest.budget = AgentBudget(
        daily_marketplace_limit_usd=1,
        max_per_action_usd=1,
        prepaid_balance_usd=1,
        authorization=AuthorizationPolicy(
            auto_approve_under_usd=1,
            financial_actions_require_human=False,
        ),
    )
    router = _router(manifest, provider, signer, clock)
    executor = RouteDispatchExecutor(
        signer,
        clock,
        failed_executor_id=failed_route.id,
    )
    router._executors[ExecutorKind.PYTHON] = executor
    try:
        initial = await router.prepare_route(_request(action_id="fallback-initial"))
        assert initial.selected_executor_id == failed_route.id

        outcome = await router.execute_prepared_with_fallback(
            initial.prepared_id,
            payment_approved=True,
        )

        assert outcome.ok
        assert outcome.decision.selected_executor_id == fallback_route.id
        assert [call.spec.id for call in executor.calls] == [
            failed_route.id,
            fallback_route.id,
        ]
        assert provider.calls.count(fallback_route.id) == 2
        prepared = router.store.list_prepared_decisions()
        assert len(prepared) == 2
        assert {item.state for item in prepared} == {PreparedDecisionState.SETTLED}
        assert len({item.action_digest for item in prepared}) == 2
        settlements = router.store.list_settlement_receipts()
        assert len(settlements) == 2
        assert sorted(item.captured_amount.amount for item in settlements) == [
            Decimal(0),
            Decimal("0.0038"),
        ]
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_explicit_prepared_fallback_never_retries_timeout() -> None:
    clock = MutableClock()
    signer = _signer()
    failed_route = _route("remote.timeout", latency_ms=1, cash="0.001", provider=True)
    fallback_route = _route(
        "remote.not-used", latency_ms=20, cash="0.001", provider=True
    )
    provider = SignedQuoteProvider(signer, clock)
    manifest = _manifest(failed_route, fallback_route)
    manifest.budget = AgentBudget(
        daily_marketplace_limit_usd=1,
        max_per_action_usd=1,
        prepaid_balance_usd=1,
        authorization=AuthorizationPolicy(
            auto_approve_under_usd=1,
            financial_actions_require_human=False,
        ),
    )
    router = _router(manifest, provider, signer, clock)
    executor = RouteDispatchExecutor(
        signer,
        clock,
        failed_executor_id=failed_route.id,
        failed_status=ExecutionStatus.TIMEOUT,
        include_failed_usage=False,
    )
    router._executors[ExecutorKind.PYTHON] = executor
    try:
        initial = await router.prepare_route(_request(action_id="fallback-timeout"))
        calls_before = len(provider.calls)

        outcome = await router.execute_prepared_with_fallback(
            initial.prepared_id,
            payment_approved=True,
        )

        assert not outcome.ok and outcome.status is ExecutionStatus.TIMEOUT
        assert [call.spec.id for call in executor.calls] == [failed_route.id]
        assert len(provider.calls) == calls_before
        stored = router.store.get_prepared_decision(initial.prepared_id)
        assert stored is not None and stored.state is PreparedDecisionState.INDETERMINATE
    finally:
        await router.close()
