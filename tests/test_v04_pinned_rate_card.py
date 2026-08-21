from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal

import pytest
from test_v04_prepared_routing import (
    PROVIDER,
    QUOTE_HOST,
    MutableClock,
    _request,
    _route,
    _trust_verifier,
)

from aeep.economic.signing import Ed25519Signer
from aeep.errors import NoRouteError
from aeep.executors.base import BaseExecutor, ExecutionContext
from aeep.models import (
    AgentBudget,
    AuthorizationKind,
    AuthorizationMeterQuantity,
    AuthorizationPolicy,
    BoundedQuote,
    CapabilityOffer,
    CurrencyAmount,
    EconomicEvidenceConfig,
    ExecutionStatus,
    ExecutorKind,
    Manifest,
    PaymentReservationState,
    PreparedDecisionState,
    QuoteRequestV2,
    RateCardRate,
    RateCardSnapshot,
    RateType,
    RawExecution,
    ResourceVector,
)
from aeep.router import Router


class NoQuoteProvider:
    """Fail loudly if a pinned route ever reaches quote acquisition."""

    def __init__(self) -> None:
        self.calls = 0

    async def get_offers(
        self,
        capability: str,
        executor_ids: Sequence[str],
    ) -> tuple[CapabilityOffer, ...]:
        del capability, executor_ids
        self.calls += 1
        raise AssertionError("pinned rate-card routes must not request offers")

    async def request_quote(self, request: QuoteRequestV2) -> BoundedQuote:
        del request
        self.calls += 1
        raise AssertionError("pinned rate-card routes must not request quotes")


class RecordingExecutor(BaseExecutor):
    def __init__(self) -> None:
        self.calls: list[ExecutionContext] = []

    async def execute(self, context: ExecutionContext) -> RawExecution:
        self.calls.append(context)
        return RawExecution(
            status=ExecutionStatus.SUCCESS,
            output={"result": "ok"},
            resources=ResourceVector(latency_ms=1),
        )


def _snapshot(clock: MutableClock, *, conditional: bool = False) -> RateCardSnapshot:
    return RateCardSnapshot(
        provider=PROVIDER,
        product="fixed-action",
        model="fixed-v1",
        effective_from=clock() - timedelta(days=1),
        effective_until=clock() + timedelta(days=1),
        retrieved_at=clock(),
        source_uri="https://operator.example/rates.json",
        source_content_sha256=("2" if conditional else "1") * 64,
        currency="USD",
        rates=[
            RateCardRate(
                rate_id="request-rate",
                rate_type=RateType.OTHER,
                meter="requests",
                input_unit="request",
                output_unit="USD",
                unit_quantity=Decimal(1),
                rate_amount=Decimal("0.004"),
                region="private-tier" if conditional else None,
            )
        ],
    )


def _router(
    snapshot: RateCardSnapshot,
    clock: MutableClock,
    provider: NoQuoteProvider,
    executor: RecordingExecutor,
) -> Router:
    assert snapshot.snapshot_id is not None
    route = _route("remote.fixed-rate", latency_ms=1, cash="0.001", provider=True)
    manifest = Manifest(
        version="0.4",
        database=":memory:",
        executors=[route],
        budget=AgentBudget(
            daily_marketplace_limit_usd=1,
            max_per_action_usd=1,
            prepaid_balance_usd=1,
            authorization=AuthorizationPolicy(
                auto_approve_under_usd=1,
                financial_actions_require_human=False,
            ),
        ),
        economic_evidence=EconomicEvidenceConfig.model_validate(
            {
                "enabled": True,
                "live_quotes": {"enabled": True},
                "network": {"allowed_quote_hosts": [QUOTE_HOST]},
                "payment": {"adapter": "prepaid"},
                "requirements": {
                    "pinned_rate_cards": {
                        route.id: {
                            "rate_card_snapshot_id": snapshot.snapshot_id,
                            "meter_quantities": [
                                {
                                    "rate_id": "request-rate",
                                    "meter": "requests",
                                    "unit": "request",
                                    "quantity": "1",
                                }
                            ],
                        }
                    }
                }
            }
        ),
    )
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="provider-key")
    router = Router(
        manifest,
        quote_provider=provider,
        economic_verifier=_trust_verifier(signer, clock),
        clock=clock,
        executor_overrides={ExecutorKind.PYTHON: executor},
    )
    router.store.save_rate_card_snapshot(snapshot)
    return router


@pytest.mark.asyncio
async def test_pinned_unconditional_rate_prepares_reserves_executes_and_settles() -> None:
    clock = MutableClock()
    snapshot = _snapshot(clock)
    provider = NoQuoteProvider()
    executor = RecordingExecutor()
    router = _router(snapshot, clock, provider, executor)
    try:
        prepared = await router.prepare_route(
            _request(action_id="pinned-fixed-rate")
        )

        assert prepared.feasible
        assert prepared.quote_request_count == 0
        assert prepared.selected_quote_id is None
        assert prepared.selected_offer_id is None
        assert prepared.selected_rate_card_id == snapshot.snapshot_id
        assert prepared.authorization_kind is AuthorizationKind.PINNED_RATE_CARD
        assert prepared.authorization_id == snapshot.snapshot_id
        assert prepared.authorization_rate_ids == ("request-rate",)
        assert prepared.authorization_meter_quantities == (
            AuthorizationMeterQuantity(
                rate_id="request-rate",
                meter="requests",
                unit="request",
                quantity=Decimal(1),
            ),
        )
        assert prepared.maximum_cash_authorization == CurrencyAmount(
            amount=Decimal("0.004"), currency="USD"
        )
        assert provider.calls == 0

        outcome = await router.execute_prepared(
            prepared.prepared_id,
            payment_approved=True,
        )

        assert outcome.ok
        assert len(executor.calls) == 1
        assert provider.calls == 0
        reservations = router.store.list_payment_reservations_v2()
        settlements = router.store.list_settlement_receipts(
            prepared_id=prepared.prepared_id
        )
        assert len(reservations) == len(settlements) == 1
        assert reservations[0].state is PaymentReservationState.SETTLED
        assert reservations[0].quote_id is None
        assert reservations[0].authorization_kind is AuthorizationKind.PINNED_RATE_CARD
        assert reservations[0].maximum_amount.amount == Decimal("0.004")
        assert settlements[0].captured_amount.amount == Decimal("0.004")
        assert settlements[0].released_amount.amount == Decimal(0)
        stored = router.store.get_prepared_decision(prepared.prepared_id)
        assert stored is not None
        assert stored.state is PreparedDecisionState.SETTLED
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_conditional_pinned_rate_is_rejected_before_invocation() -> None:
    clock = MutableClock()
    snapshot = _snapshot(clock, conditional=True)
    provider = NoQuoteProvider()
    executor = RecordingExecutor()
    router = _router(snapshot, clock, provider, executor)
    try:
        prepared = await router.prepare_route(
            _request(action_id="conditional-pinned-rate")
        )

        assert not prepared.feasible
        assert prepared.selected_executor_id is None
        assert prepared.maximum_cash_authorization is None
        assert provider.calls == 0
        rejected = next(
            candidate
            for candidate in prepared.rejected_candidates
            if candidate.executor_id == "remote.fixed-rate"
        )
        assert "conditional pinned rates" in " ".join(rejected.reasons)

        with pytest.raises(NoRouteError, match="no feasible selected route"):
            await router.execute_prepared(prepared.prepared_id)
        assert executor.calls == []
        assert router.store.list_payment_reservations_v2() == []
    finally:
        await router.close()
