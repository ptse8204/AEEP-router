from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal

import pytest
from test_v04_acceptance import FailOncePrepaidAdapter, _execution_router, _signer
from test_v04_pinned_rate_card import NoQuoteProvider, RecordingExecutor, _snapshot
from test_v04_prepared_execution_edges import (
    EconomicExecutor,
    FixedOfferFallbackProvider,
    _fixed_offer,
    _offer_requirements,
)
from test_v04_prepared_routing import (
    PROVIDER,
    UNSIGNED,
    MutableClock,
    SignedQuoteProvider,
    _manifest,
    _request,
    _route,
    _trust_verifier,
)

from aeep.economic.canonical import canonical_payload
from aeep.economic.prepared import executor_fingerprint
from aeep.economic.signing import Ed25519Signer
from aeep.errors import ConfigurationError, NoRouteError
from aeep.executors.base import BaseExecutor, ExecutionContext
from aeep.models import (
    AgentBudget,
    AuthorizationKind,
    AuthorizationPolicy,
    BillingTrigger,
    BoundedQuote,
    CurrencyAmount,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    FailureChargePolicy,
    Manifest,
    PaymentReservationState,
    PaymentReservationV2,
    PreparedDecisionState,
    ProviderExecutionStatus,
    QuoteRequestV2,
    RawExecution,
    ResourceVector,
    UsageStatement,
)
from aeep.payments import PrepaidBalanceAdapterV2
from aeep.registry import Registry
from aeep.router import Router


class TermsQuoteProvider(SignedQuoteProvider):
    def __init__(
        self,
        signer: Ed25519Signer,
        clock: MutableClock,
        billing_trigger: BillingTrigger = BillingTrigger.ON_SUCCESS,
        failure_charge_policy: FailureChargePolicy = FailureChargePolicy.NO_CHARGE,
        amounts: dict[str, tuple[str | None, str]] | None = None,
    ) -> None:
        super().__init__(signer, clock, amounts=amounts)
        self.billing_trigger = billing_trigger
        self.failure_charge_policy = failure_charge_policy

    async def request_quote(self, request: QuoteRequestV2) -> BoundedQuote:
        quote = await super().request_quote(request)
        changed = quote.model_copy(
            update={
                "billing_trigger": self.billing_trigger,
                "failure_charge_policy": self.failure_charge_policy,
            }
        )
        return changed.model_copy(
            update={"signature": self.signer.sign(canonical_payload(changed))}
        )


class TimedUsageExecutor(BaseExecutor):
    def __init__(
        self,
        signer: Ed25519Signer,
        clock: MutableClock,
        *,
        local_status: ExecutionStatus = ExecutionStatus.SUCCESS,
        provider_status: ProviderExecutionStatus = ProviderExecutionStatus.SUCCESS,
        amount: str = "0.0038",
        include_started_at: bool = False,
        issued_offset: timedelta = timedelta(),
    ) -> None:
        self.signer = signer
        self.clock = clock
        self.local_status = local_status
        self.provider_status = provider_status
        self.amount = amount
        self.include_started_at = include_started_at
        self.issued_offset = issued_offset
        self.calls: list[ExecutionContext] = []

    async def execute(self, context: ExecutionContext) -> RawExecution:
        self.calls.append(context)
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
            provider_calculated_amount=CurrencyAmount(
                amount=Decimal(self.amount),
                currency="USD",
            ),
            started_at=self.clock() if self.include_started_at else None,
            completed_at=self.clock(),
            issued_at=self.clock() + self.issued_offset,
            signature=UNSIGNED,
        )
        statement = statement.model_copy(
            update={"signature": self.signer.sign(canonical_payload(statement))}
        )
        return RawExecution(
            status=self.local_status,
            output={
                "output": {"result": "ok"},
                "usage_statement": statement.model_dump(mode="json"),
            },
            resources=ResourceVector(latency_ms=1),
            error_type=(
                "ProviderFailure"
                if self.local_status is not ExecutionStatus.SUCCESS
                else None
            ),
        )


class SelectiveReleaseFailureAdapter(PrepaidBalanceAdapterV2):
    async def _release_external(
        self,
        reservation: PaymentReservationV2,
        reason: str,
        idempotency_key: str,
    ) -> object:
        del reason, idempotency_key
        if reservation.action_id == "release-bad":
            raise RuntimeError("selected release failed")
        return None


class ReserveMutationAdapter(PrepaidBalanceAdapterV2):
    on_reserve: Callable[[PaymentReservationV2], None] | None = None

    async def _reserve_external(self, reservation: PaymentReservationV2) -> object:
        if self.on_reserve is not None:
            self.on_reserve(reservation)
        return None


def _budgeted_manifest(
    route: ExecutorSpec,
    *,
    requirements: dict[str, object] | None = None,
) -> Manifest:
    manifest = _manifest(route, requirements=requirements)
    manifest.budget = AgentBudget(
        daily_marketplace_limit_usd=1,
        max_per_action_usd=1,
        prepaid_balance_usd=1,
        authorization=AuthorizationPolicy(
            auto_approve_under_usd=1,
            financial_actions_require_human=False,
        ),
    )
    return manifest


def _assert_preinvocation_release(
    router: Router,
    *,
    prepared_id: str,
    executor: RecordingExecutor,
) -> None:
    assert executor.calls == []
    reservation = router.store.list_payment_reservations_v2(
        prepared_id=prepared_id
    )[0]
    settlement = router.store.list_settlement_receipts(prepared_id=prepared_id)[0]
    prepared = router.store.get_prepared_decision(prepared_id)
    assert prepared is not None and prepared.state is PreparedDecisionState.RELEASED
    assert reservation.state is PaymentReservationState.RELEASED
    assert settlement.captured_amount.amount == 0
    assert settlement.released_amount == reservation.maximum_amount


@pytest.mark.asyncio
async def test_recovery_accepts_success_usage_without_provider_start_and_enriches_receipt() -> None:
    clock = MutableClock()
    signer = _signer()
    provider = TermsQuoteProvider(
        signer,
        clock,
        amounts={"remote.dynamic": ("0.0038", "0.0050")},
    )
    adapter = FailOncePrepaidAdapter(clock)
    router = _execution_router(
        _route("remote.dynamic", latency_ms=1, cash="0.001", provider=True),
        provider,
        signer,
        clock,
        adapter=adapter,
    )
    executor = TimedUsageExecutor(signer, clock, include_started_at=False)
    router._executors[ExecutorKind.PYTHON] = executor
    try:
        prepared = await router.prepare_route(_request(action_id="recover-no-start"))
        with pytest.raises(RuntimeError, match="crash window"):
            await router.execute_prepared(prepared.prepared_id, payment_approved=True)

        recovery = await router.economic_recover()

        assert recovery["settled"] == 1, recovery
        assert len(executor.calls) == 1
        settlement = router.store.list_settlement_receipts(
            prepared_id=prepared.prepared_id
        )[0]
        reservation = router.store.list_payment_reservations_v2(
            prepared_id=prepared.prepared_id
        )[0]
        receipt = router.store.list_receipts()[0]
        assert settlement.captured_amount.amount == Decimal("0.0038")
        assert receipt.accounting.cash.actual_cash_cost("USD") == Decimal("0.0038")
        assert receipt.metadata["settlement_id"] == settlement.settlement_id
        links = router.store.list_economic_evidence_links(
            charge_id=reservation.charge_id,
            limit=100,
        )
        assert any(
            link.authoritative
            and link.evidence_type == "settlement_receipt"
            and link.evidence_id == settlement.settlement_id
            for link in links
        )
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_reservation_crossing_quote_expiry_releases_without_invocation() -> None:
    clock = MutableClock()
    signer = _signer()
    provider = TermsQuoteProvider(
        signer,
        clock,
        amounts={"remote.dynamic": ("0.0038", "0.0050")},
    )
    adapter = ReserveMutationAdapter(
        CurrencyAmount(amount=Decimal(1), currency="USD"),
        clock=clock,
    )
    router = _execution_router(
        _route("remote.dynamic", latency_ms=1, cash="0.001", provider=True),
        provider,
        signer,
        clock,
        adapter=adapter,
    )
    executor = RecordingExecutor()
    router._executors[ExecutorKind.PYTHON] = executor
    try:
        action_key = "expire-during-reserve-key"
        request = _request(action_id="expire-during-reserve").model_copy(
            update={"idempotency_key": action_key}
        )
        prepared = await router.prepare_route(request)
        adapter.on_reserve = lambda _reservation: setattr(
            clock,
            "now",
            prepared.expires_at + timedelta(microseconds=1),
        )

        with pytest.raises(ConfigurationError, match="expired while reserving"):
            await router.execute_prepared(prepared.prepared_id, payment_approved=True)

        _assert_preinvocation_release(
            router,
            prepared_id=prepared.prepared_id,
            executor=executor,
        )
        assert router.store.get_prepared_action_idempotency(prepared.prepared_id) is None
        assert router.store.claim_idempotency(action_key, prepared.action_digest) is None
        router.store.abandon_idempotency(action_key)
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_recovery_finalizes_keyed_confirmed_free_action_without_reexecution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = MutableClock()
    signer = _signer()
    provider = TermsQuoteProvider(signer, clock)
    router = _execution_router(
        _route("local.free", latency_ms=1, cash="0", provider=False),
        provider,
        signer,
        clock,
    )
    executor = RecordingExecutor()
    router._executors[ExecutorKind.PYTHON] = executor
    action_key = "free-finalization-key"
    request = _request(
        action_id="free-finalization",
        idempotency_key=action_key,
    )
    original_complete = router.store.complete_idempotency
    failed = False

    def fail_once(
        key: str,
        *,
        decision_id: str,
        status: str,
        receipt_ids: list[str],
    ) -> None:
        nonlocal failed
        if not failed:
            failed = True
            raise RuntimeError("crash after free prepared settlement")
        original_complete(
            key,
            decision_id=decision_id,
            status=status,
            receipt_ids=receipt_ids,
        )

    monkeypatch.setattr(router.store, "complete_idempotency", fail_once)
    try:
        prepared = await router.prepare_route(request)
        with pytest.raises(RuntimeError, match="crash after free"):
            await router.execute_prepared(prepared.prepared_id)

        stored = router.store.get_prepared_decision(prepared.prepared_id)
        assert stored is not None and stored.state is PreparedDecisionState.SETTLED
        assert len(executor.calls) == 1

        recovery = await router.economic_recover()

        assert recovery["settled"] == 1, recovery
        assert len(executor.calls) == 1
        existing = router.store.claim_idempotency(action_key, prepared.action_digest)
        assert existing is not None and existing["state"] == "complete"
        assert router.store.settled_free_actions_needing_finalization() == []
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_recovery_settles_preterminal_confirmed_free_action_without_reexecution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = MutableClock()
    signer = _signer()
    router = _execution_router(
        _route("local.free", latency_ms=1, cash="0", provider=False),
        TermsQuoteProvider(signer, clock),
        signer,
        clock,
    )
    executor = RecordingExecutor()
    router._executors[ExecutorKind.PYTHON] = executor
    request = _request(
        action_id="free-preterminal-recovery",
        idempotency_key="free-preterminal-key",
    )
    original_transition = router._transition_prepared
    failed = False

    def fail_once(
        prepared_id: str,
        from_state: PreparedDecisionState,
        to_state: PreparedDecisionState,
        reason: str,
    ) -> None:
        nonlocal failed
        if (
            not failed
            and from_state is PreparedDecisionState.INVOKING
            and to_state is PreparedDecisionState.SETTLING
        ):
            failed = True
            raise RuntimeError("crash before free settlement transition")
        original_transition(prepared_id, from_state, to_state, reason)

    monkeypatch.setattr(router, "_transition_prepared", fail_once)
    try:
        prepared = await router.prepare_route(request)
        with pytest.raises(RuntimeError, match="crash before free"):
            await router.execute_prepared(prepared.prepared_id)

        stored = router.store.get_prepared_decision(prepared.prepared_id)
        assert stored is not None and stored.state is PreparedDecisionState.INDETERMINATE
        assert len(executor.calls) == 1

        recovery = await router.economic_recover()

        assert recovery["settled"] == 1, recovery
        assert len(executor.calls) == 1
        stored = router.store.get_prepared_decision(prepared.prepared_id)
        assert stored is not None and stored.state is PreparedDecisionState.SETTLED
        receipt = router.store.list_receipts()[0]
        assert receipt.accounting.cash.actual_cash_cost("USD") == 0
        assert (
            receipt.metadata["cash_evidence_level"]
            == "OPERATOR_ATTESTED"
        )
        existing = router.store.claim_idempotency(
            "free-preterminal-key", prepared.action_digest
        )
        assert existing is not None and existing["state"] == "complete"
    finally:
        await router.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["suspend_route", "revoke_key"])
async def test_reservation_authority_change_releases_without_invocation(
    mutation: str,
) -> None:
    clock = MutableClock()
    signer = _signer()
    provider = TermsQuoteProvider(
        signer,
        clock,
        amounts={"remote.dynamic": ("0.0038", "0.0050")},
    )
    adapter = ReserveMutationAdapter(
        CurrencyAmount(amount=Decimal(1), currency="USD"),
        clock=clock,
    )
    router = _execution_router(
        _route("remote.dynamic", latency_ms=1, cash="0.001", provider=True),
        provider,
        signer,
        clock,
        adapter=adapter,
    )
    executor = RecordingExecutor()
    router._executors[ExecutorKind.PYTHON] = executor
    try:
        prepared = await router.prepare_route(
            _request(action_id=f"authority-change-{mutation}")
        )

        def mutate(_reservation: PaymentReservationV2) -> None:
            if mutation == "suspend_route":
                router.registry.get("remote.dynamic").enabled = False
            else:
                router.store.revoke_provider_signing_key(
                    PROVIDER,
                    signer.key_id,
                    revoked_at=clock(),
                )

        adapter.on_reserve = mutate
        with pytest.raises(
            (ConfigurationError, NoRouteError),
            match=r"active|trust changed|revoked",
        ):
            await router.execute_prepared(prepared.prepared_id, payment_approved=True)

        _assert_preinvocation_release(
            router,
            prepared_id=prepared.prepared_id,
            executor=executor,
        )
    finally:
        await router.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("route_change", ["suspended", "removed", "drifted"])
async def test_quote_recovery_uses_immutable_evidence_after_route_change(
    route_change: str,
) -> None:
    clock = MutableClock()
    signer = _signer()
    provider = TermsQuoteProvider(
        signer,
        clock,
        amounts={"remote.dynamic": ("0.0038", "0.0050")},
    )
    adapter = FailOncePrepaidAdapter(clock)
    router = _execution_router(
        _route("remote.dynamic", latency_ms=1, cash="0.001", provider=True),
        provider,
        signer,
        clock,
        adapter=adapter,
    )
    executor = TimedUsageExecutor(signer, clock, include_started_at=True)
    router._executors[ExecutorKind.PYTHON] = executor
    try:
        prepared = await router.prepare_route(
            _request(action_id=f"recover-route-{route_change}")
        )
        with pytest.raises(RuntimeError, match="crash window"):
            await router.execute_prepared(prepared.prepared_id, payment_approved=True)
        assert len(
            router.store.list_usage_statements(prepared_id=prepared.prepared_id)
        ) == 1
        assert len(router.store.list_receipts()) == 1

        if route_change == "suspended":
            router.registry.get("remote.dynamic").enabled = False
        elif route_change == "removed":
            router.registry = Registry()
        else:
            router.registry.get("remote.dynamic").config["callable"] = (
                "aeep.examples.tools:always_fail"
            )

        recovery = await router.economic_recover()

        assert recovery["settled"] == 1, recovery
        assert len(executor.calls) == 1
        settlement = router.store.list_settlement_receipts(
            prepared_id=prepared.prepared_id
        )[0]
        assert settlement.captured_amount.amount == Decimal("0.0038")
        assert router.store.get_prepared_decision(prepared.prepared_id).state is (
            PreparedDecisionState.SETTLED
        )
    finally:
        await router.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure_policy", "expected_capture"),
    [
        (FailureChargePolicy.NO_CHARGE, "0"),
        (FailureChargePolicy.CHARGE_MAXIMUM, "0.0050"),
    ],
)
async def test_recovery_applies_failure_policy_without_claimed_amount_mismatch(
    failure_policy: FailureChargePolicy,
    expected_capture: str,
) -> None:
    clock = MutableClock()
    signer = _signer()
    provider = TermsQuoteProvider(
        signer,
        clock,
        amounts={"remote.dynamic": ("0.0038", "0.0050")},
        failure_charge_policy=failure_policy,
    )
    adapter = FailOncePrepaidAdapter(clock)
    router = _execution_router(
        _route("remote.dynamic", latency_ms=1, cash="0.001", provider=True),
        provider,
        signer,
        clock,
        adapter=adapter,
    )
    executor = TimedUsageExecutor(
        signer,
        clock,
        local_status=ExecutionStatus.FAILED,
        provider_status=ProviderExecutionStatus.FAILED,
        amount="0.0017",
        include_started_at=True,
    )
    router._executors[ExecutorKind.PYTHON] = executor
    try:
        prepared = await router.prepare_route(
            _request(action_id=f"recover-{failure_policy.value.lower()}")
        )
        with pytest.raises(RuntimeError, match="crash window"):
            await router.execute_prepared(prepared.prepared_id, payment_approved=True)

        recovery = await router.economic_recover()

        assert recovery["settled"] == 1, (
            recovery,
            router.store.get_prepared_decision(prepared.prepared_id),
            router.store.list_payment_reservations_v2(prepared_id=prepared.prepared_id),
            router.store.list_receipts(),
        )
        settlement = router.store.list_settlement_receipts(
            prepared_id=prepared.prepared_id
        )[0]
        assert settlement.captured_amount.amount == Decimal(expected_capture)
        assert settlement.released_amount.amount == Decimal("0.0050") - Decimal(
            expected_capture
        )
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_provider_start_failure_without_signed_start_stays_indeterminate() -> None:
    clock = MutableClock()
    signer = _signer()
    provider = TermsQuoteProvider(
        signer,
        clock,
        amounts={"remote.dynamic": ("0.0038", "0.0050")},
        billing_trigger=BillingTrigger.ON_PROVIDER_START,
    )
    router = _execution_router(
        _route("remote.dynamic", latency_ms=1, cash="0.001", provider=True),
        provider,
        signer,
        clock,
    )
    executor = TimedUsageExecutor(
        signer,
        clock,
        local_status=ExecutionStatus.FAILED,
        provider_status=ProviderExecutionStatus.FAILED,
        include_started_at=False,
    )
    router._executors[ExecutorKind.PYTHON] = executor
    try:
        prepared = await router.prepare_route(_request(action_id="provider-start-unknown"))
        outcome = await router.execute_prepared(
            prepared.prepared_id,
            payment_approved=True,
        )

        assert not outcome.ok
        assert router.store.get_prepared_decision(prepared.prepared_id).state is (
            PreparedDecisionState.INDETERMINATE
        )
        recovery = await router.economic_recover()
        assert recovery["unresolved"] == 1
        assert router.store.list_settlement_receipts(prepared_id=prepared.prepared_id) == []
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_usage_issuance_outside_local_attempt_is_rejected_and_indeterminate() -> None:
    clock = MutableClock()
    signer = _signer()
    provider = TermsQuoteProvider(
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
    executor = TimedUsageExecutor(
        signer,
        clock,
        issued_offset=timedelta(minutes=1),
    )
    router._executors[ExecutorKind.PYTHON] = executor
    try:
        prepared = await router.prepare_route(_request(action_id="bad-usage-chronology"))
        with pytest.raises(ConfigurationError, match=r"clock skew|chronology"):
            await router.execute_prepared(prepared.prepared_id, payment_approved=True)

        assert router.store.get_prepared_decision(prepared.prepared_id).state is (
            PreparedDecisionState.INDETERMINATE
        )
        assert router.store.list_usage_statements(prepared_id=prepared.prepared_id) == []
        assert router.store.list_payment_reservations_v2()[0].state is (
            PaymentReservationState.INDETERMINATE
        )
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_fixed_offer_recovery_uses_historical_offer_after_revocation() -> None:
    clock = MutableClock()
    signer = _signer()
    route = _route("remote.fixed", latency_ms=1, cash="0.001", provider=True)
    offer = _fixed_offer(signer, clock, route)
    provider = FixedOfferFallbackProvider(signer, clock, offer)
    adapter = FailOncePrepaidAdapter(clock)
    manifest = _budgeted_manifest(route, requirements=_offer_requirements())
    router = Router(
        manifest,
        quote_provider=provider,
        economic_verifier=_trust_verifier(signer, clock),
        payment_adapter_v2=adapter,
        clock=clock,
    )
    executor = EconomicExecutor(
        signer,
        clock,
        include_usage=False,
    )
    router._executors[ExecutorKind.PYTHON] = executor
    try:
        prepared = await router.prepare_route(_request(action_id="recover-revoked-offer"))
        with pytest.raises(RuntimeError, match="crash window"):
            await router.execute_prepared(prepared.prepared_id, payment_approved=True)
        router.store.revoke_capability_offer(offer.offer_id, revoked_at=clock())

        recovery = await router.economic_recover()

        assert recovery["settled"] == 1, recovery
        settlement = router.store.list_settlement_receipts(
            prepared_id=prepared.prepared_id
        )[0]
        assert settlement.captured_amount.amount == Decimal("0.0038")
        assert len(executor.calls) == 1
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_pinned_rate_card_recovery_uses_durable_success_receipt() -> None:
    clock = MutableClock()
    snapshot = _snapshot(clock)
    assert snapshot.snapshot_id is not None
    route = _route("remote.fixed-rate", latency_ms=1, cash="0.001", provider=True)
    manifest = _budgeted_manifest(
        route,
        requirements={
            "pinned_rate_cards": {
                route.id: {
                    "rate_card_snapshot_id": snapshot.snapshot_id,
                    "meter_quantities": [
                        {
                            "rate_id": "request-rate",
                            "meter": "requests",
                            "unit": "request",
                            "quantity": "2",
                        }
                    ],
                }
            }
        },
    )
    manifest.economic_evidence.live_quotes.enabled = False
    provider = NoQuoteProvider()
    executor = RecordingExecutor()
    adapter = FailOncePrepaidAdapter(clock)
    router = Router(
        manifest,
        quote_provider=provider,
        payment_adapter_v2=adapter,
        clock=clock,
        executor_overrides={ExecutorKind.PYTHON: executor},
    )
    router.store.save_rate_card_snapshot(snapshot)
    try:
        prepared = await router.prepare_route(_request(action_id="recover-pinned-rate"))
        assert prepared.authorization_kind is AuthorizationKind.PINNED_RATE_CARD
        with pytest.raises(RuntimeError, match="crash window"):
            await router.execute_prepared(prepared.prepared_id, payment_approved=True)

        recovery = await router.economic_recover()

        assert recovery["settled"] == 1
        assert len(executor.calls) == 1
        settlement = router.store.list_settlement_receipts(
            prepared_id=prepared.prepared_id
        )[0]
        assert settlement.captured_amount == prepared.maximum_cash_authorization
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_recovery_isolates_release_failures_per_prepared_decision() -> None:
    clock = MutableClock()
    signer = _signer()
    provider = TermsQuoteProvider(
        signer,
        clock,
        amounts={"remote.dynamic": ("0.0038", "0.0050")},
    )
    adapter = SelectiveReleaseFailureAdapter(
        CurrencyAmount(amount=Decimal(1), currency="USD"),
        clock=clock,
    )
    router = _execution_router(
        _route("remote.dynamic", latency_ms=1, cash="0.001", provider=True),
        provider,
        signer,
        clock,
        adapter=adapter,
    )
    try:
        prepared_items = [
            await router.prepare_route(_request(action_id=action_id))
            for action_id in ("release-bad", "release-good")
        ]
        assert router.budget_manager is not None
        for prepared in prepared_items:
            assert prepared.authorization_kind is not None
            assert prepared.authorization_id is not None
            assert prepared.maximum_cash_authorization is not None
            claim = f"claim-{prepared.action_id}"
            router.store.claim_prepared_decision(
                prepared.prepared_id,
                claim_token=claim,
                claimed_at=clock(),
            )
            await router.budget_manager.reserve_v2(
                prepared_id=prepared.prepared_id,
                quote_id=prepared.selected_quote_id,
                authorization_kind=prepared.authorization_kind,
                authorization_id=prepared.authorization_id,
                action_id=prepared.action_id,
                attempt_id=f"attempt-{prepared.action_id}",
                charge_id=f"charge-{prepared.action_id}",
                maximum_amount=prepared.maximum_cash_authorization,
                idempotency_key=f"reserve-{prepared.action_id}",
                claim_token=claim,
                payment_approved=True,
                executor_id=prepared.selected_executor_id or "",
            )

        recovery = await router.economic_recover()

        assert recovery["released"] == 1
        assert recovery["unresolved"] == 1
        states = {
            item.action_id: item.state
            for item in router.store.list_payment_reservations_v2()
        }
        assert states == {
            "release-bad": PaymentReservationState.INDETERMINATE,
            "release-good": PaymentReservationState.RELEASED,
        }
    finally:
        await router.close()
