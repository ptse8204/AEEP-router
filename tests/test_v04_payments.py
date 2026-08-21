from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from aeep.economic.canonical import canonical_payload
from aeep.economic.signing import Ed25519Signer
from aeep.economic.trust import TrustedProviderKey
from aeep.errors import ApprovalRequired, ConfigurationError
from aeep.models import (
    ActionFeatures,
    AgentBudget,
    AuthorizationKind,
    AuthorizationPolicy,
    BillingReconciliation,
    BillingTrigger,
    BoundedQuote,
    CurrencyAmount,
    EconomicEvidenceLevel,
    FailureChargePolicy,
    PaymentReservation,
    PaymentReservationState,
    PaymentReservationV2,
    PreparedDecisionState,
    PreparedRouteDecision,
    PreparedRouteTransition,
    ProviderExecutionStatus,
    Quote,
    QuoteRequestV2,
    ReconciliationStatus,
    RefundReceiptV2,
    RetryChargePolicy,
    SettlementEvidence,
    SettlementReceipt,
    SettlementStatus,
    SideEffect,
    SignatureAlgorithm,
    SignatureEnvelopeV2,
)
from aeep.payments import (
    BudgetManager,
    CallbackPaymentAdapterV2,
    FreePaymentAdapter,
    FreePaymentAdapterV2,
    InvoicePaymentAdapterV2,
    LocalLedgerPaymentAdapter,
    PaymentAdapterV2,
    PrepaidBalanceAdapter,
    PrepaidBalanceAdapterV2,
    billable_amount_for_execution,
    billable_amount_for_terms,
)
from aeep.store import ReceiptStore

NOW = datetime(2026, 8, 14, 12, tzinfo=UTC)
PAYMENT_SIGNER = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="test-key")


def money(amount: str, currency: str = "USD") -> CurrencyAmount:
    return CurrencyAmount(amount=Decimal(amount), currency=currency)


def reservation(
    *,
    maximum: str = "0.0050",
    currency: str = "USD",
    adapter: str = "prepaid",
    suffix: str = "1",
    idempotency_key: str | None = None,
) -> PaymentReservationV2:
    return PaymentReservationV2(
        reservation_id=f"reserve-{suffix}",
        charge_id=f"charge-{suffix}",
        prepared_id=f"prepared-{suffix}",
        quote_id=f"quote-{suffix}",
        authorization_kind=AuthorizationKind.SIGNED_QUOTE,
        authorization_id=f"quote-{suffix}",
        action_id=f"action-{suffix}",
        attempt_id=f"attempt-{suffix}",
        maximum_amount=money(maximum, currency),
        adapter=adapter,
        idempotency_key=idempotency_key or f"reserve-key-{suffix}",
        created_at=NOW,
        updated_at=NOW,
    )


def evidence(value: PaymentReservationV2, actual: str | None = None) -> SettlementEvidence:
    return SettlementEvidence(
        charge_id=value.charge_id,
        evidence_level=EconomicEvidenceLevel.SIGNED_USAGE_STATEMENT,
        provider_calculated_amount=(
            money(actual, value.maximum_amount.currency) if actual is not None else None
        ),
    )


def bounded_quote(
    *,
    maximum: str = "0.0050",
    billing_trigger: BillingTrigger = BillingTrigger.ON_SUCCESS,
    failure_policy: FailureChargePolicy = FailureChargePolicy.NO_CHARGE,
    retry_policy: RetryChargePolicy = RetryChargePolicy.EACH_ATTEMPT,
    fixed_attempt_fee: str | None = None,
) -> BoundedQuote:
    digest = f"sha256:{'a' * 64}"
    expected = min(Decimal("0.0038"), Decimal(maximum))
    return BoundedQuote(
        quote_id="quote-policy",
        quote_request_id="quote-request-policy",
        provider_id="provider.test",
        capability="demo.action@1",
        executor_id="executor.test",
        executor_fingerprint=digest,
        action_digest=digest,
        nonce="nonce-policy",
        expected_amount=CurrencyAmount(amount=expected, currency="USD"),
        maximum_amount=money(maximum),
        billing_trigger=billing_trigger,
        failure_charge_policy=failure_policy,
        retry_charge_policy=retry_policy,
        fixed_attempt_fee=(
            money(fixed_attempt_fee or "0.0004")
            if failure_policy is FailureChargePolicy.CHARGE_FIXED_ATTEMPT_FEE
            else None
        ),
        terms_digest=digest,
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
        signature=SignatureEnvelopeV2(
            algorithm=SignatureAlgorithm.ED25519,
            key_id="test-key",
            value="c2lnbmF0dXJl",
        ),
    )


def seed_payment_evidence(
    store: ReceiptStore,
    *,
    suffix: str,
    maximum: str,
) -> None:
    digest = f"sha256:{'a' * 64}"
    store.save_provider_signing_key(
        TrustedProviderKey(
            provider_id="provider.test",
            key_id="test-key",
            public_key=PAYMENT_SIGNER.public_key_base64url(),
            valid_from=NOW - timedelta(days=1),
            valid_until=NOW + timedelta(days=1),
            allowed_capabilities=("demo.action@1",),
        )
    )
    request = QuoteRequestV2(
        quote_request_id=f"quote-request-{suffix}",
        action_id=f"action-{suffix}",
        capability="demo.action@1",
        executor_id="executor.test",
        executor_fingerprint=digest,
        action_digest=digest,
        input_features=ActionFeatures(
            input_bytes=0,
            input_items=0,
            text_characters=0,
            max_depth=0,
            size_bucket="empty",
        ),
        desired_currency="USD",
        nonce=f"nonce-{suffix}-value",
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    quote = BoundedQuote(
        quote_id=f"quote-{suffix}",
        quote_request_id=request.quote_request_id,
        provider_id="provider.test",
        capability=request.capability,
        executor_id=request.executor_id,
        executor_fingerprint=request.executor_fingerprint,
        action_digest=request.action_digest,
        nonce=request.nonce,
        expected_amount=money(maximum),
        maximum_amount=money(maximum),
        billing_trigger=BillingTrigger.ON_SUCCESS,
        failure_charge_policy=FailureChargePolicy.NO_CHARGE,
        retry_charge_policy=RetryChargePolicy.EACH_ATTEMPT,
        terms_digest=digest,
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
        signature=SignatureEnvelopeV2(
            algorithm=SignatureAlgorithm.ED25519,
            key_id="test-key",
            value="c2lnbmF0dXJl",
        ),
    )
    quote = quote.model_copy(
        update={"signature": PAYMENT_SIGNER.sign(canonical_payload(quote))}
    )
    prepared = PreparedRouteDecision(
        prepared_id=f"prepared-{suffix}",
        action_id=request.action_id,
        action_digest=request.action_digest,
        effective_policy_digest=digest,
        selected_executor_id=request.executor_id,
        selected_executor_fingerprint=request.executor_fingerprint,
        selected_quote_id=quote.quote_id,
        quote_ids=(quote.quote_id,),
        maximum_cash_authorization=quote.maximum_amount,
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    store.save_quote_request_v2(request)
    store.save_bounded_quote(quote)
    store.save_prepared_decision(prepared)


def budget_manager(
    store: ReceiptStore,
    adapter: PaymentAdapterV2,
    *,
    limit: str,
    daily_limit: str | None = None,
    prepaid_limit: str | None = None,
) -> BudgetManager:
    return BudgetManager(
        AgentBudget(
            daily_marketplace_limit_usd=float(daily_limit or limit),
            max_per_action_usd=float(limit),
            prepaid_balance_usd=float(prepaid_limit or limit),
            authorization=AuthorizationPolicy(
                auto_approve_under_usd=float(limit),
                financial_actions_require_human=False,
            ),
        ),
        store,
        FreePaymentAdapter(),
        adapter_v2=adapter,
        clock=lambda: NOW,
    )


def advance_prepared(
    store: ReceiptStore,
    *,
    suffix: str,
    states: tuple[PreparedDecisionState, ...],
) -> None:
    prepared = store.get_prepared_decision(f"prepared-{suffix}")
    assert prepared is not None
    source = prepared.state
    for index, target in enumerate(states):
        if target is source:
            continue
        if (
            source is PreparedDecisionState.RESERVED
            and target is PreparedDecisionState.INVOKING
        ):
            assert prepared.authorization_kind is not None
            assert prepared.authorization_id is not None
            store.claim_prepared_for_paid_invocation(
                prepared.prepared_id,
                claim_token=f"claim-{suffix}",
                expected_action_digest=prepared.action_digest,
                expected_policy_digest=prepared.effective_policy_digest,
                expected_executor_id=prepared.selected_executor_id,
                expected_executor_fingerprint=prepared.selected_executor_fingerprint,
                expected_authorization_kind=prepared.authorization_kind,
                expected_authorization_id=prepared.authorization_id,
                invoked_at=NOW,
            )
            source = target
            continue
        store.save_prepared_transition(
            PreparedRouteTransition(
                transition_id=f"transition-{suffix}-{index}",
                prepared_id=f"prepared-{suffix}",
                from_state=source,
                to_state=target,
                occurred_at=NOW,
            )
        )
        source = target


async def reserve_with_manager(
    manager: BudgetManager,
    *,
    suffix: str,
    maximum: str,
) -> PaymentReservationV2:
    claim_token = f"claim-{suffix}"
    manager.store.claim_prepared_decision(
        f"prepared-{suffix}",
        claim_token=claim_token,
        claimed_at=NOW,
    )
    return await manager.reserve_v2(
        prepared_id=f"prepared-{suffix}",
        quote_id=f"quote-{suffix}",
        authorization_kind=AuthorizationKind.SIGNED_QUOTE,
        authorization_id=f"quote-{suffix}",
        action_id=f"action-{suffix}",
        attempt_id=f"attempt-{suffix}",
        charge_id=f"charge-{suffix}",
        maximum_amount=money(maximum),
        idempotency_key=f"reserve-key-{suffix}",
        claim_token=claim_token,
        payment_approved=True,
        executor_id="executor.test",
    )


@pytest.mark.asyncio
async def test_partial_settlement_captures_actual_and_releases_exact_remainder():
    adapter = PrepaidBalanceAdapterV2(money("1.0000"), clock=lambda: NOW)
    held = await adapter.reserve(reservation=reservation())
    settled = await adapter.settle(
        reservation=held,
        actual_amount=money("0.0038"),
        evidence=evidence(held, "0.0038"),
        idempotency_key="settle-partial",
    )

    assert settled.reserved_amount.amount == Decimal("0.0050")
    assert settled.captured_amount.amount == Decimal("0.0038")
    assert settled.released_amount.amount == Decimal("0.0012")
    assert settled.evidence_level is EconomicEvidenceLevel.PAYMENT_SETTLEMENT
    assert adapter.available_balance == money("0.9962")


@pytest.mark.asyncio
async def test_zero_exact_maximum_and_legacy_full_capture_wrapper():
    zero_adapter = FreePaymentAdapterV2(clock=lambda: NOW)
    zero = await zero_adapter.reserve(
        reservation=reservation(maximum="0", adapter="free", suffix="zero")
    )
    zero_settlement = await zero_adapter.settle(
        reservation=zero,
        actual_amount=money("0"),
        evidence=evidence(zero, "0"),
        idempotency_key="settle-zero",
    )
    assert zero_settlement.captured_amount.amount == 0
    assert zero_settlement.released_amount.amount == 0

    adapter = PrepaidBalanceAdapterV2(money("1"), clock=lambda: NOW)
    held = await adapter.reserve(reservation=reservation(suffix="maximum"))
    captured = await adapter.capture(
        reservation=held,
        evidence=evidence(held, "0.0050"),
        idempotency_key="capture-maximum",
    )
    assert captured.captured_amount == money("0.0050")
    assert captured.released_amount == money("0")


@pytest.mark.asyncio
async def test_identical_operations_are_idempotent_and_conflicts_fail():
    adapter = PrepaidBalanceAdapterV2(money("1"), clock=lambda: NOW)
    requested = reservation()
    first = await adapter.reserve(reservation=requested)
    assert await adapter.reserve(reservation=requested) is first
    with pytest.raises(ConfigurationError, match="idempotency key"):
        await adapter.reserve(
            reservation=reservation(maximum="0.006", idempotency_key=requested.idempotency_key)
        )

    settled = await adapter.settle(
        reservation=first,
        actual_amount=money("0.0038"),
        evidence=evidence(first, "0.0038"),
        idempotency_key="settle-once",
    )
    assert (
        await adapter.settle(
            reservation=first,
            actual_amount=money("0.0038"),
            evidence=evidence(first, "0.0038"),
            idempotency_key="settle-once",
        )
        is settled
    )
    with pytest.raises(ConfigurationError, match="idempotency key"):
        await adapter.settle(
            reservation=first,
            actual_amount=money("0.0037"),
            evidence=evidence(first, "0.0037"),
            idempotency_key="settle-once",
        )


@pytest.mark.asyncio
async def test_release_and_settlement_are_mutually_exclusive():
    adapter = PrepaidBalanceAdapterV2(money("1"), clock=lambda: NOW)
    released_reservation = await adapter.reserve(reservation=reservation(suffix="released"))
    released = await adapter.release(
        reservation=released_reservation,
        reason="cancelled before invocation",
        idempotency_key="release-once",
    )
    assert released.captured_amount == money("0")
    assert released.released_amount == money("0.0050")
    with pytest.raises(ConfigurationError, match="current state"):
        await adapter.settle(
            reservation=released_reservation,
            actual_amount=money("0"),
            evidence=evidence(released_reservation, "0"),
            idempotency_key="settle-after-release",
        )

    settled_reservation = await adapter.reserve(reservation=reservation(suffix="settled"))
    await adapter.settle(
        reservation=settled_reservation,
        actual_amount=money("0.004"),
        evidence=evidence(settled_reservation, "0.004"),
        idempotency_key="settle-before-release",
    )
    with pytest.raises(ConfigurationError, match="current state"):
        await adapter.release(
            reservation=settled_reservation,
            reason="too late",
            idempotency_key="release-after-settle",
        )


@pytest.mark.asyncio
async def test_refunds_are_cumulatively_bounded_and_idempotent():
    adapter = PrepaidBalanceAdapterV2(money("1"), clock=lambda: NOW)
    held = await adapter.reserve(reservation=reservation())
    settled = await adapter.capture(
        reservation=held,
        evidence=evidence(held, "0.0050"),
        idempotency_key="capture-for-refund",
    )
    first = await adapter.refund(
        settlement=settled,
        amount=money("0.003"),
        reason="partial correction",
        idempotency_key="refund-one",
    )
    assert (
        await adapter.refund(
            settlement=settled,
            amount=money("0.003"),
            reason="partial correction",
            idempotency_key="refund-one",
        )
        is first
    )
    await adapter.refund(
        settlement=settled,
        amount=money("0.002"),
        reason="remaining correction",
        idempotency_key="refund-two",
    )
    with pytest.raises(ConfigurationError, match="exceeds"):
        await adapter.refund(
            settlement=settled,
            amount=money("0.0001"),
            reason="over refund",
            idempotency_key="refund-three",
        )
    with pytest.raises(ConfigurationError, match="idempotency key"):
        await adapter.refund(
            settlement=settled,
            amount=money("0.003"),
            reason="changed reason",
            idempotency_key="refund-one",
        )


@pytest.mark.asyncio
async def test_currency_overcapture_free_and_explicit_unlimited_guards(tmp_path: Path):
    adapter = PrepaidBalanceAdapterV2(money("1", "USD"), clock=lambda: NOW)
    with pytest.raises(ConfigurationError, match="currency"):
        await adapter.reserve(reservation=reservation(currency="EUR"))

    held = await adapter.reserve(reservation=reservation())
    with pytest.raises(ConfigurationError, match="exceeds"):
        await adapter.settle(
            reservation=held,
            actual_amount=money("0.0051"),
            evidence=evidence(held),
            idempotency_key="overcapture",
        )

    free = FreePaymentAdapterV2(clock=lambda: NOW)
    with pytest.raises(ConfigurationError, match="paid"):
        await free.reserve(reservation=reservation(adapter="free", suffix="paid-free"))
    free_manager = budget_manager(
        ReceiptStore(tmp_path / "free-authorization.db"),
        free,
        limit="1",
    )
    with pytest.raises(ConfigurationError, match="free adapter"):
        free_manager.authorize_v2(
            money("0.001"),
            executor_id="executor.test",
            payment_approved=True,
        )
    with pytest.raises(ConfigurationError, match="explicit"):
        InvoicePaymentAdapterV2(unlimited_budget=False)
    invoice = InvoicePaymentAdapterV2(unlimited_budget=True, clock=lambda: NOW)
    assert invoice.available_balance is None

    with pytest.raises(ConfigurationError, match="independent external"):
        await adapter.reconcile("missing-external-billing-record")


@pytest.mark.asyncio
async def test_callback_adapter_preserves_external_reconciliation_evidence():
    callback_reservation = reservation(adapter="callback", suffix="callback")

    def reconcile(reference: str) -> BillingReconciliation:
        return BillingReconciliation(
            reconciliation_id="reconciliation-callback",
            settlement_id=reference,
            provider_id="provider.callback",
            billing_record_reference="billing-record-callback",
            expected_amount=money("0.0038"),
            billed_amount=money("0.0038"),
            discrepancy=money("0"),
            status=ReconciliationStatus.MATCHED,
            evidence_digest=f"sha256:{'b' * 64}",
            reconciled_at=NOW,
        )

    adapter = CallbackPaymentAdapterV2(
        "callback",
        reserve=lambda _reservation: {"external_reference": "hold-callback"},
        settle=lambda *_args: {"external_reference": "capture-callback"},
        release=lambda *_args: {"external_reference": "release-callback"},
        refund=lambda *_args: {"external_reference": "refund-callback"},
        reconcile=reconcile,
        provider_id="provider.callback",
        clock=lambda: NOW,
    )
    held = await adapter.reserve(reservation=callback_reservation)
    settled = await adapter.settle(
        reservation=held,
        actual_amount=money("0.0038"),
        evidence=evidence(held, "0.0038"),
        idempotency_key="callback-settle",
    )
    reconciled = await adapter.reconcile(settled.settlement_id)

    assert settled.external_reference == "capture-callback"
    assert reconciled.status is ReconciliationStatus.MATCHED
    assert reconciled.billing_record_reference == "billing-record-callback"


def test_billing_policy_returns_unknown_instead_of_inventing_charge():
    quote = bounded_quote()
    assert (
        billable_amount_for_execution(
            quote,
            execution_status=ProviderExecutionStatus.SUCCESS,
            provider_started=True,
            result_accepted=True,
            actual_usage_amount=None,
        )
        is None
    )

    actual_usage = bounded_quote(
        failure_policy=FailureChargePolicy.CHARGE_ACTUAL_USAGE
    )
    assert billable_amount_for_execution(
        actual_usage,
        execution_status=ProviderExecutionStatus.FAILED,
        provider_started=True,
        result_accepted=False,
        actual_usage_amount=money("0.0017"),
    ) == money("0.0017")

    attempt_fee = bounded_quote(
        failure_policy=FailureChargePolicy.CHARGE_FIXED_ATTEMPT_FEE
    )
    assert billable_amount_for_execution(
        attempt_fee,
        execution_status=ProviderExecutionStatus.FAILED,
        provider_started=True,
        result_accepted=False,
        actual_usage_amount=None,
    ) == money("0.0004")
    with pytest.raises(ConfigurationError, match="signed quote"):
        billable_amount_for_execution(
            attempt_fee,
            execution_status=ProviderExecutionStatus.FAILED,
            provider_started=True,
            result_accepted=False,
            actual_usage_amount=None,
            fixed_attempt_fee=money("0.0004"),
        )

    assert billable_amount_for_execution(
        quote,
        execution_status=ProviderExecutionStatus.FAILED,
        provider_started=True,
        result_accepted=False,
        actual_usage_amount=None,
    ) == money("0")
    assert (
        billable_amount_for_execution(
            quote,
            execution_status=ProviderExecutionStatus.INDETERMINATE,
            provider_started=True,
            result_accepted=None,
            actual_usage_amount=None,
        )
        is None
    )

    maximum_failure = bounded_quote(failure_policy=FailureChargePolicy.CHARGE_MAXIMUM)
    assert billable_amount_for_execution(
        maximum_failure,
        execution_status=ProviderExecutionStatus.FAILED,
        provider_started=True,
        result_accepted=False,
        actual_usage_amount=None,
    ) == money("0.0050")

    manual = bounded_quote(retry_policy=RetryChargePolicy.MANUAL_RECONCILIATION)
    assert (
        billable_amount_for_execution(
            manual,
            execution_status=ProviderExecutionStatus.SUCCESS,
            provider_started=True,
            result_accepted=True,
            actual_usage_amount=money("0.0038"),
        )
        is None
    )


@pytest.mark.asyncio
async def test_budget_manager_persists_partial_settlement_and_exact_retry(
    tmp_path: Path,
):
    store = ReceiptStore(tmp_path / "partial.db")
    seed_payment_evidence(store, suffix="partial", maximum="0.0050")
    adapter = PrepaidBalanceAdapterV2(money("1"), clock=lambda: NOW)
    manager = budget_manager(store, adapter, limit="0.0100")
    held = await reserve_with_manager(manager, suffix="partial", maximum="0.0050")
    advance_prepared(
        store,
        suffix="partial",
        states=(
            PreparedDecisionState.RESERVED,
            PreparedDecisionState.INVOKING,
            PreparedDecisionState.AWAITING_USAGE,
            PreparedDecisionState.SETTLING,
        ),
    )

    settled = await manager.settle_v2(
        held.reservation_id,
        actual_amount=money("0.0038"),
        evidence=evidence(held, "0.0038"),
        idempotency_key="settle-manager-partial",
    )
    retried = await manager.settle_v2(
        held.reservation_id,
        actual_amount=money("0.0038"),
        evidence=evidence(held, "0.0038"),
        idempotency_key="settle-manager-partial",
    )

    assert retried == settled
    assert settled.reserved_amount == money("0.0050")
    assert settled.captured_amount == money("0.0038")
    assert settled.released_amount == money("0.0012")
    stored = store.get_payment_reservation_v2(held.reservation_id)
    assert stored is not None
    assert stored.state is PaymentReservationState.SETTLED
    prepared = store.get_prepared_decision("prepared-partial")
    assert prepared is not None
    assert prepared.state is PreparedDecisionState.SETTLED


def test_v2_payment_approval_is_separate_and_required(tmp_path: Path):
    store = ReceiptStore(tmp_path / "approval.db")
    seed_payment_evidence(store, suffix="approval", maximum="0.0050")
    manager = budget_manager(
        store,
        PrepaidBalanceAdapterV2(money("1"), clock=lambda: NOW),
        limit="0.0100",
    )
    with pytest.raises(ApprovalRequired, match="payment approval"):
        manager.authorize_v2(
            money("0.0050"),
            executor_id="executor.test",
            payment_approved=False,
        )
    assert store.list_payment_reservations_v2(action_id="action-approval") == []


@pytest.mark.asyncio
async def test_atomic_concurrent_reservations_respect_budget(tmp_path: Path):
    database = tmp_path / "concurrent.db"
    first_store = ReceiptStore(database)
    seed_payment_evidence(first_store, suffix="concurrent-a", maximum="0.0040")
    seed_payment_evidence(first_store, suffix="concurrent-b", maximum="0.0040")
    second_store = ReceiptStore(database)
    first = budget_manager(
        first_store,
        PrepaidBalanceAdapterV2(money("1"), clock=lambda: NOW),
        limit="0.0050",
    )
    second = budget_manager(
        second_store,
        PrepaidBalanceAdapterV2(money("1"), clock=lambda: NOW),
        limit="0.0050",
    )

    outcomes = await asyncio.gather(
        reserve_with_manager(first, suffix="concurrent-a", maximum="0.0040"),
        reserve_with_manager(second, suffix="concurrent-b", maximum="0.0040"),
        return_exceptions=True,
    )

    assert sum(isinstance(item, PaymentReservationV2) for item in outcomes) == 1
    failures = [item for item in outcomes if isinstance(item, Exception)]
    assert len(failures) == 1
    assert isinstance(failures[0], ConfigurationError)
    assert "daily budget" in str(failures[0])


@pytest.mark.asyncio
async def test_atomic_prepaid_limit_cannot_be_overcommitted_across_managers(
    tmp_path: Path,
):
    database = tmp_path / "prepaid-concurrent.db"
    first_store = ReceiptStore(database)
    seed_payment_evidence(first_store, suffix="prepaid-a", maximum="0.0040")
    seed_payment_evidence(first_store, suffix="prepaid-b", maximum="0.0040")
    second_store = ReceiptStore(database)
    first = budget_manager(
        first_store,
        PrepaidBalanceAdapterV2(money("1"), clock=lambda: NOW),
        limit="1",
        daily_limit="1",
        prepaid_limit="0.0050",
    )
    second = budget_manager(
        second_store,
        PrepaidBalanceAdapterV2(money("1"), clock=lambda: NOW),
        limit="1",
        daily_limit="1",
        prepaid_limit="0.0050",
    )

    outcomes = await asyncio.gather(
        reserve_with_manager(first, suffix="prepaid-a", maximum="0.0040"),
        reserve_with_manager(second, suffix="prepaid-b", maximum="0.0040"),
        return_exceptions=True,
    )

    assert sum(isinstance(item, PaymentReservationV2) for item in outcomes) == 1
    assert sum(isinstance(item, ConfigurationError) for item in outcomes) == 1


@pytest.mark.asyncio
async def test_release_and_refund_restore_atomic_budget(tmp_path: Path):
    store = ReceiptStore(tmp_path / "restored.db")
    for suffix in ("released", "captured", "after-refund"):
        seed_payment_evidence(store, suffix=suffix, maximum="0.0050")
    adapter = PrepaidBalanceAdapterV2(money("1"), clock=lambda: NOW)
    manager = budget_manager(store, adapter, limit="0.0050")

    released_hold = await reserve_with_manager(
        manager, suffix="released", maximum="0.0050"
    )
    advance_prepared(
        store,
        suffix="released",
        states=(PreparedDecisionState.RESERVED,),
    )
    released = await manager.release_v2(
        released_hold.reservation_id,
        reason="cancelled before invocation",
        idempotency_key="release-manager",
    )
    assert released.captured_amount == money("0")
    assert released.released_amount == money("0.0050")

    captured_hold = await reserve_with_manager(
        manager, suffix="captured", maximum="0.0050"
    )
    advance_prepared(
        store,
        suffix="captured",
        states=(
            PreparedDecisionState.RESERVED,
            PreparedDecisionState.INVOKING,
            PreparedDecisionState.SETTLING,
        ),
    )
    captured = await manager.capture_v2(
        captured_hold.reservation_id,
        evidence=evidence(captured_hold, "0.0050"),
        idempotency_key="capture-manager",
    )
    refund = await manager.refund_v2(
        captured.settlement_id,
        amount=money("0.0050"),
        reason="billing correction",
        idempotency_key="refund-manager",
    )
    assert refund.amount == money("0.0050")

    restored = await reserve_with_manager(
        manager, suffix="after-refund", maximum="0.0050"
    )
    assert restored.maximum_amount == money("0.0050")


class FailingSettlementAdapter(PrepaidBalanceAdapterV2):
    async def _settle_external(
        self,
        _reservation: PaymentReservationV2,
        _actual_amount: CurrencyAmount,
        _evidence: SettlementEvidence,
        _idempotency_key: str,
    ) -> object:
        raise RuntimeError("simulated rail outage")


class FailingReleaseAdapter(PrepaidBalanceAdapterV2):
    async def _release_external(
        self,
        _reservation: PaymentReservationV2,
        _reason: str,
        _idempotency_key: str,
    ) -> object:
        raise RuntimeError("simulated release outage")


class RecordingRefundAdapter(PrepaidBalanceAdapterV2):
    def __init__(self) -> None:
        super().__init__(money("1"), clock=lambda: NOW)
        self.refund_calls = 0

    async def _refund_external(
        self,
        _settlement: SettlementReceipt,
        _amount: CurrencyAmount,
        _reason: str,
        _idempotency_key: str,
    ) -> object:
        self.refund_calls += 1
        await asyncio.sleep(0)
        return None


class FailOnceSettlementAdapter(PrepaidBalanceAdapterV2):
    def __init__(self) -> None:
        super().__init__(money("1"), clock=lambda: NOW)
        self.external_captures = 0
        self._seen_keys: set[str] = set()

    async def _settle_external(
        self,
        _reservation: PaymentReservationV2,
        _actual_amount: CurrencyAmount,
        _evidence: SettlementEvidence,
        idempotency_key: str,
    ) -> object:
        if idempotency_key not in self._seen_keys:
            self._seen_keys.add(idempotency_key)
            self.external_captures += 1
            raise RuntimeError("lost settlement response")
        return {"external_reference": "capture-already-completed"}


class FailOnceReleaseAdapter(PrepaidBalanceAdapterV2):
    def __init__(self) -> None:
        super().__init__(money("1"), clock=lambda: NOW)
        self.external_releases = 0
        self._seen_keys: set[str] = set()

    async def _release_external(
        self,
        _reservation: PaymentReservationV2,
        _reason: str,
        idempotency_key: str,
    ) -> object:
        if idempotency_key not in self._seen_keys:
            self._seen_keys.add(idempotency_key)
            self.external_releases += 1
            raise RuntimeError("lost release response")
        return {"external_reference": "release-already-completed"}


class FailOnceReserveAdapter(PrepaidBalanceAdapterV2):
    def __init__(self) -> None:
        super().__init__(money("1"), clock=lambda: NOW)
        self.external_holds = 0
        self._seen_keys: set[str] = set()

    async def _reserve_external(self, value: PaymentReservationV2) -> object:
        if value.idempotency_key not in self._seen_keys:
            self._seen_keys.add(value.idempotency_key)
            self.external_holds += 1
            raise RuntimeError("lost reservation response")
        return {"external_reference": "hold-already-created"}


class FailingRefundAdapter(PrepaidBalanceAdapterV2):
    async def _refund_external(
        self,
        _settlement: SettlementReceipt,
        _amount: CurrencyAmount,
        _reason: str,
        _idempotency_key: str,
    ) -> object:
        raise RuntimeError("simulated refund outage")


class CorruptSettlementAdapter(PrepaidBalanceAdapterV2):
    async def settle(
        self,
        *,
        reservation: PaymentReservationV2,
        actual_amount: CurrencyAmount,
        evidence: SettlementEvidence,
        idempotency_key: str,
    ) -> SettlementReceipt:
        receipt = await super().settle(
            reservation=reservation,
            actual_amount=actual_amount,
            evidence=evidence,
            idempotency_key=idempotency_key,
        )
        return receipt.model_copy(update={"settlement_id": "settlement-corrupt"})


class CorruptReleaseAdapter(PrepaidBalanceAdapterV2):
    async def release(
        self,
        *,
        reservation: PaymentReservationV2,
        reason: str,
        idempotency_key: str,
    ) -> SettlementReceipt:
        receipt = await super().release(
            reservation=reservation,
            reason=reason,
            idempotency_key=idempotency_key,
        )
        return receipt.model_copy(update={"status": SettlementStatus.SETTLED})


class CorruptRefundAdapter(PrepaidBalanceAdapterV2):
    async def refund(
        self,
        *,
        settlement: SettlementReceipt,
        amount: CurrencyAmount,
        reason: str,
        idempotency_key: str,
    ) -> RefundReceiptV2:
        receipt = await super().refund(
            settlement=settlement,
            amount=amount,
            reason=reason,
            idempotency_key=idempotency_key,
        )
        return receipt.model_copy(update={"refund_id": "refund-corrupt"})


@pytest.mark.asyncio
async def test_settlement_adapter_failure_preserves_indeterminate_reservation(
    tmp_path: Path,
):
    store = ReceiptStore(tmp_path / "indeterminate.db")
    seed_payment_evidence(store, suffix="indeterminate", maximum="0.0050")
    manager = budget_manager(
        store,
        FailingSettlementAdapter(money("1"), clock=lambda: NOW),
        limit="0.0100",
    )
    held = await reserve_with_manager(
        manager, suffix="indeterminate", maximum="0.0050"
    )
    advance_prepared(
        store,
        suffix="indeterminate",
        states=(
            PreparedDecisionState.RESERVED,
            PreparedDecisionState.INVOKING,
            PreparedDecisionState.SETTLING,
        ),
    )

    with pytest.raises(RuntimeError, match="rail outage"):
        await manager.settle_v2(
            held.reservation_id,
            actual_amount=money("0.0038"),
            evidence=evidence(held, "0.0038"),
            idempotency_key="settle-fails",
        )

    stored = store.get_payment_reservation_v2(held.reservation_id)
    assert stored is not None
    assert stored.state is PaymentReservationState.INDETERMINATE
    assert stored.maximum_amount == money("0.0050")
    assert store.list_settlement_receipts(prepared_id=held.prepared_id) == []
    operation = store.get_payment_operation("settle", "settle-fails")
    assert operation is not None
    assert operation["state"] == "indeterminate"
    with pytest.raises(ConfigurationError, match="releasable"):
        await manager.release_v2(
            held.reservation_id,
            reason="unsafe release after uncertain settlement",
            idempotency_key="unsafe-indeterminate-release",
        )
    still_held = store.get_payment_reservation_v2(held.reservation_id)
    assert still_held is not None
    assert still_held.state is PaymentReservationState.INDETERMINATE


@pytest.mark.asyncio
async def test_release_failure_keeps_the_full_hold_indeterminate(tmp_path: Path):
    store = ReceiptStore(tmp_path / "release-indeterminate.db")
    seed_payment_evidence(store, suffix="release-indeterminate", maximum="0.0050")
    manager = budget_manager(
        store,
        FailingReleaseAdapter(money("1"), clock=lambda: NOW),
        limit="0.0100",
    )
    held = await reserve_with_manager(
        manager,
        suffix="release-indeterminate",
        maximum="0.0050",
    )

    with pytest.raises(RuntimeError, match="release outage"):
        await manager.release_v2(
            held.reservation_id,
            reason="pre-invocation cancellation",
            idempotency_key="release-fails",
        )

    stored = store.get_payment_reservation_v2(held.reservation_id)
    assert stored is not None
    assert stored.state is PaymentReservationState.INDETERMINATE
    assert stored.maximum_amount == money("0.0050")
    assert store.payment_reservation_operation_intent(held.reservation_id) == (
        "release:release-fails"
    )
    operation = store.get_payment_operation("release", "release-fails")
    assert operation is not None
    assert operation["state"] == "indeterminate"


@pytest.mark.asyncio
async def test_identical_retry_recovers_indeterminate_settlement_and_release(
    tmp_path: Path,
):
    store = ReceiptStore(tmp_path / "payment-recovery.db")
    seed_payment_evidence(store, suffix="recover-settle", maximum="0.0050")
    seed_payment_evidence(store, suffix="recover-release", maximum="0.0050")

    settle_adapter = FailOnceSettlementAdapter()
    settle_manager = budget_manager(store, settle_adapter, limit="0.0100")
    settle_hold = await reserve_with_manager(
        settle_manager,
        suffix="recover-settle",
        maximum="0.0050",
    )
    advance_prepared(
        store,
        suffix="recover-settle",
        states=(PreparedDecisionState.INVOKING, PreparedDecisionState.SETTLING),
    )
    with pytest.raises(RuntimeError, match="lost settlement"):
        await settle_manager.settle_v2(
            settle_hold.reservation_id,
            actual_amount=money("0.0038"),
            evidence=evidence(settle_hold, "0.0038"),
            idempotency_key="recover-settlement",
        )
    settled = await settle_manager.settle_v2(
        settle_hold.reservation_id,
        actual_amount=money("0.0038"),
        evidence=evidence(settle_hold, "0.0038"),
        idempotency_key="recover-settlement",
    )
    assert settled.captured_amount == money("0.0038")
    assert settled.released_amount == money("0.0012")
    assert settle_adapter.external_captures == 1

    release_adapter = FailOnceReleaseAdapter()
    release_manager = budget_manager(store, release_adapter, limit="0.0100")
    release_hold = await reserve_with_manager(
        release_manager,
        suffix="recover-release",
        maximum="0.0050",
    )
    with pytest.raises(RuntimeError, match="lost release"):
        await release_manager.release_v2(
            release_hold.reservation_id,
            reason="cancelled before invocation",
            idempotency_key="recover-release",
        )
    released = await release_manager.release_v2(
        release_hold.reservation_id,
        reason="cancelled before invocation",
        idempotency_key="recover-release",
    )
    assert released.captured_amount == money("0")
    assert released.released_amount == money("0.0050")
    assert release_adapter.external_releases == 1


@pytest.mark.asyncio
async def test_concurrent_refunds_are_authorized_before_the_rail_call(tmp_path: Path):
    database = tmp_path / "refund-race.db"
    first_store = ReceiptStore(database)
    seed_payment_evidence(first_store, suffix="refund-race", maximum="0.0050")
    first_adapter = RecordingRefundAdapter()
    first_manager = budget_manager(first_store, first_adapter, limit="0.0100")
    held = await reserve_with_manager(
        first_manager,
        suffix="refund-race",
        maximum="0.0050",
    )
    advance_prepared(
        first_store,
        suffix="refund-race",
        states=(PreparedDecisionState.INVOKING, PreparedDecisionState.SETTLING),
    )
    captured = await first_manager.capture_v2(
        held.reservation_id,
        evidence=evidence(held, "0.0050"),
        idempotency_key="capture-refund-race",
    )

    second_store = ReceiptStore(database)
    second_adapter = RecordingRefundAdapter()
    second_manager = budget_manager(second_store, second_adapter, limit="0.0100")
    outcomes = await asyncio.gather(
        first_manager.refund_v2(
            captured.settlement_id,
            amount=money("0.0040"),
            reason="first correction",
            idempotency_key="refund-race-a",
        ),
        second_manager.refund_v2(
            captured.settlement_id,
            amount=money("0.0040"),
            reason="second correction",
            idempotency_key="refund-race-b",
        ),
        return_exceptions=True,
    )

    assert sum(isinstance(item, ConfigurationError) for item in outcomes) == 1
    assert sum(isinstance(item, RefundReceiptV2) for item in outcomes) == 1
    assert first_adapter.refund_calls + second_adapter.refund_calls == 1
    refunds = first_store.list_refund_receipts_v2(
        settlement_id=captured.settlement_id
    )
    assert [item.amount for item in refunds] == [money("0.0040")]


@pytest.mark.asyncio
async def test_settlement_binding_and_callback_metadata_fail_closed() -> None:
    adapter = PrepaidBalanceAdapterV2(money("1"), clock=lambda: NOW)
    held = await adapter.reserve(reservation=reservation(suffix="binding"))

    with pytest.raises(ConfigurationError, match="currency"):
        await adapter.settle(
            reservation=held,
            actual_amount=money("0.001", "EUR"),
            evidence=evidence(held),
            idempotency_key="wrong-settlement-currency",
        )
    wrong_charge = evidence(held).model_copy(update={"charge_id": "charge-other"})
    with pytest.raises(ConfigurationError, match="charge"):
        await adapter.settle(
            reservation=held,
            actual_amount=money("0.001"),
            evidence=wrong_charge,
            idempotency_key="wrong-evidence-charge",
        )
    wrong_provider_currency = evidence(held).model_copy(
        update={"provider_calculated_amount": money("0.001", "EUR")}
    )
    with pytest.raises(ConfigurationError, match="provider amount currency"):
        await adapter.settle(
            reservation=held,
            actual_amount=money("0.001"),
            evidence=wrong_provider_currency,
            idempotency_key="wrong-provider-currency",
        )
    wrong_provider_amount = evidence(held).model_copy(
        update={"provider_calculated_amount": money("0.002")}
    )
    with pytest.raises(ConfigurationError, match="provider amount does not match"):
        await adapter.settle(
            reservation=held,
            actual_amount=money("0.001"),
            evidence=wrong_provider_amount,
            idempotency_key="wrong-provider-amount",
        )

    async def capture_reference(*_args: object) -> str:
        return "capture-reference"

    callback = CallbackPaymentAdapterV2(
        "callback-reference",
        reserve=lambda _reservation: None,
        settle=capture_reference,
        release=lambda *_args: {},
        refund=lambda *_args: None,
        reconcile=lambda _reference: None,
        clock=lambda: NOW,
    )
    callback_hold = await callback.reserve(
        reservation=reservation(adapter="callback-reference", suffix="callback-reference")
    )
    receipt = await callback.settle(
        reservation=callback_hold,
        actual_amount=money("0.001"),
        evidence=evidence(callback_hold, "0.001"),
        idempotency_key="callback-reference-settle",
    )
    assert receipt.external_reference == "capture-reference"

    for suffix, result, message in (
        ("missing", {}, None),
        ("wrong-type", {"external_reference": 7}, "must be a string"),
        ("wrong-shape", object(), "must return metadata"),
    ):
        invalid = CallbackPaymentAdapterV2(
            f"callback-{suffix}",
            reserve=lambda _reservation: None,
            settle=lambda *_args, value=result: value,
            release=lambda *_args: None,
            refund=lambda *_args: None,
            reconcile=lambda _reference: None,
            clock=lambda: NOW,
        )
        invalid_hold = await invalid.reserve(
            reservation=reservation(adapter=f"callback-{suffix}", suffix=suffix)
        )
        if message is None:
            no_reference = await invalid.settle(
                reservation=invalid_hold,
                actual_amount=money("0.001"),
                evidence=evidence(invalid_hold, "0.001"),
                idempotency_key=f"callback-{suffix}-settle",
            )
            assert no_reference.external_reference is None
        else:
            with pytest.raises(ConfigurationError, match=message):
                await invalid.settle(
                    reservation=invalid_hold,
                    actual_amount=money("0.001"),
                    evidence=evidence(invalid_hold, "0.001"),
                    idempotency_key=f"callback-{suffix}-settle",
                )


@pytest.mark.asyncio
async def test_local_ledger_rejects_conflicting_holds_and_unsafe_refunds() -> None:
    with pytest.raises(ConfigurationError, match="balance currency"):
        LocalLedgerPaymentAdapter(
            settlement_currency="USD",
            balance=money("1", "EUR"),
        )
    with pytest.raises(ConfigurationError, match="unlimited payment rail"):
        LocalLedgerPaymentAdapter(balance=money("1"), unlimited_budget=True)

    adapter = PrepaidBalanceAdapterV2(money("0.0050"), clock=lambda: NOW)
    with pytest.raises(ConfigurationError, match="adapter does not match"):
        await adapter.reserve(reservation=reservation(adapter="invoice", suffix="wrong-rail"))
    with pytest.raises(ConfigurationError, match="must be RESERVED"):
        await adapter.reserve(
            reservation=reservation(suffix="wrong-state").model_copy(
                update={"state": PaymentReservationState.SETTLING}
            )
        )
    with pytest.raises(ConfigurationError, match="insufficient"):
        await adapter.reserve(reservation=reservation(maximum="0.006", suffix="too-large"))

    held = await adapter.reserve(reservation=reservation(suffix="first-charge"))
    conflicting_identity = held.model_copy(
        update={"idempotency_key": "different-reserve-key", "attempt_id": "attempt-other"}
    )
    with pytest.raises(ConfigurationError, match="ID collision"):
        await adapter.reserve(reservation=conflicting_identity)
    duplicate_charge = reservation(maximum="0", suffix="second-charge").model_copy(
        update={"charge_id": held.charge_id}
    )
    with pytest.raises(ConfigurationError, match="already has a reservation"):
        await adapter.reserve(reservation=duplicate_charge)
    with pytest.raises(ConfigurationError, match="requires a reason"):
        await adapter.release(
            reservation=held,
            reason="",
            idempotency_key="blank-release-reason",
        )

    recovery_adapter = PrepaidBalanceAdapterV2(money("1"), clock=lambda: NOW)
    recovered = reservation(suffix="durable-recovery")
    settlement = await recovery_adapter.settle(
        reservation=recovered,
        actual_amount=money("0.001"),
        evidence=evidence(recovered, "0.001"),
        idempotency_key="durable-recovery-settle",
    )
    with pytest.raises(ConfigurationError, match="requires a reason"):
        await recovery_adapter.refund(
            settlement=settlement,
            amount=money("0.001"),
            reason="",
            idempotency_key="blank-refund-reason",
        )
    with pytest.raises(ConfigurationError, match="refund currency"):
        await recovery_adapter.refund(
            settlement=settlement,
            amount=money("0.001", "EUR"),
            reason="currency mismatch",
            idempotency_key="wrong-refund-currency",
        )
    with pytest.raises(ConfigurationError, match="requires a reference"):
        await recovery_adapter.reconcile("")

    changed_identity = recovered.model_copy(update={"attempt_id": "attempt-changed"})
    with pytest.raises(ConfigurationError, match="identity changed"):
        await recovery_adapter.settle(
            reservation=changed_identity,
            actual_amount=money("0.001"),
            evidence=evidence(changed_identity, "0.001"),
            idempotency_key="changed-reservation-identity",
        )

    restarted = PrepaidBalanceAdapterV2(money("1"), clock=lambda: NOW)
    recovered_refund = await restarted.refund(
        settlement=settlement,
        amount=money("0.0005"),
        reason="recovered external settlement",
        idempotency_key="recovered-refund",
    )
    assert recovered_refund.amount == money("0.0005")
    changed_settlement = settlement.model_copy(
        update={"external_reference": "changed-reference"}
    )
    with pytest.raises(ConfigurationError, match="settlement identity changed"):
        await restarted.refund(
            settlement=changed_settlement,
            amount=money("0.0001"),
            reason="unsafe changed settlement",
            idempotency_key="changed-settlement-refund",
        )


@pytest.mark.asyncio
async def test_callback_adapter_exercises_release_and_refund_rails() -> None:
    calls: list[tuple[str, str]] = []

    async def release_callback(
        value: PaymentReservationV2,
        _reason: str,
        _idempotency_key: str,
    ) -> str:
        calls.append(("release", value.reservation_id))
        return "release-reference"

    async def refund_callback(
        value: SettlementReceipt,
        _amount: CurrencyAmount,
        _reason: str,
        _idempotency_key: str,
    ) -> str:
        calls.append(("refund", value.settlement_id))
        return "refund-reference"

    adapter = CallbackPaymentAdapterV2(
        "callback-all-rails",
        reserve=lambda _reservation: None,
        settle=lambda *_args: "settlement-reference",
        release=release_callback,
        refund=refund_callback,
        reconcile=lambda _reference: None,
        clock=lambda: NOW,
    )
    release_hold = await adapter.reserve(
        reservation=reservation(adapter=adapter.name, suffix="callback-release")
    )
    released = await adapter.release(
        reservation=release_hold,
        reason="pre-invocation failure",
        idempotency_key="callback-release",
    )
    assert released.external_reference == "release-reference"
    assert released.captured_amount == money("0")
    assert released.released_amount == money("0.0050")

    capture_hold = await adapter.reserve(
        reservation=reservation(adapter=adapter.name, suffix="callback-refund")
    )
    captured = await adapter.capture(
        reservation=capture_hold,
        evidence=evidence(capture_hold, "0.0050"),
        idempotency_key="callback-capture",
    )
    refund = await adapter.refund(
        settlement=captured,
        amount=money("0.0010"),
        reason="external correction",
        idempotency_key="callback-refund",
    )
    assert captured.external_reference == "settlement-reference"
    assert refund.external_reference == "refund-reference"
    assert calls == [
        ("release", release_hold.reservation_id),
        ("refund", captured.settlement_id),
    ]


def test_billing_policy_covers_retry_trigger_and_bound_guards() -> None:
    quote = bounded_quote()
    with pytest.raises(ValueError, match="attempt_number"):
        billable_amount_for_execution(
            quote,
            execution_status=ProviderExecutionStatus.SUCCESS,
            provider_started=True,
            result_accepted=True,
            actual_usage_amount=money("0.001"),
            attempt_number=0,
        )
    for amount, message in (
        (money("0.001", "EUR"), "currency"),
        (money("0.006"), "exceeds"),
    ):
        with pytest.raises(ConfigurationError, match=message):
            billable_amount_for_execution(
                quote,
                execution_status=ProviderExecutionStatus.SUCCESS,
                provider_started=True,
                result_accepted=True,
                actual_usage_amount=amount,
            )

    first_only = bounded_quote(retry_policy=RetryChargePolicy.FIRST_ATTEMPT_ONLY)
    assert billable_amount_for_execution(
        first_only,
        execution_status=ProviderExecutionStatus.SUCCESS,
        provider_started=True,
        result_accepted=True,
        actual_usage_amount=money("0.001"),
        attempt_number=2,
    ) == money("0")
    successful_only = bounded_quote(
        retry_policy=RetryChargePolicy.SUCCESSFUL_ATTEMPT_ONLY
    )
    assert billable_amount_for_execution(
        successful_only,
        execution_status=ProviderExecutionStatus.FAILED,
        provider_started=True,
        result_accepted=False,
        actual_usage_amount=money("0.001"),
    ) == money("0")
    manual_trigger = bounded_quote(billing_trigger=BillingTrigger.MANUAL_RECONCILIATION)
    assert (
        billable_amount_for_execution(
            manual_trigger,
            execution_status=ProviderExecutionStatus.SUCCESS,
            provider_started=True,
            result_accepted=True,
            actual_usage_amount=money("0.001"),
        )
        is None
    )
    provider_start = bounded_quote(billing_trigger=BillingTrigger.ON_PROVIDER_START)
    assert billable_amount_for_execution(
        provider_start,
        execution_status=ProviderExecutionStatus.FAILED,
        provider_started=False,
        result_accepted=False,
        actual_usage_amount=None,
    ) == money("0")
    assert billable_amount_for_execution(
        quote,
        execution_status=ProviderExecutionStatus.SUCCESS,
        provider_started=True,
        result_accepted=True,
        actual_usage_amount=money("0.0017"),
    ) == money("0.0017")
    free_quote = bounded_quote(maximum="0")
    assert billable_amount_for_execution(
        free_quote,
        execution_status=ProviderExecutionStatus.SUCCESS,
        provider_started=True,
        result_accepted=True,
        actual_usage_amount=None,
    ) == money("0")


def test_fixed_signed_terms_determine_charge_without_a_fake_quote() -> None:
    terms = {
        "billing_trigger": BillingTrigger.ON_SUCCESS,
        "failure_charge_policy": FailureChargePolicy.NO_CHARGE,
        "retry_charge_policy": RetryChargePolicy.EACH_ATTEMPT,
        "maximum_amount": money("0.0040"),
        "fixed_authorized_amount": money("0.0040"),
    }
    assert billable_amount_for_terms(
        **terms,
        execution_status=ProviderExecutionStatus.SUCCESS,
        provider_started=True,
        result_accepted=True,
        actual_usage_amount=money("0.0030"),
    ) == money("0.0040")
    assert billable_amount_for_terms(
        **terms,
        execution_status=ProviderExecutionStatus.FAILED,
        provider_started=True,
        result_accepted=False,
        actual_usage_amount=None,
    ) == money("0")
    assert (
        billable_amount_for_terms(
            **terms,
            execution_status=ProviderExecutionStatus.INDETERMINATE,
            provider_started=True,
            result_accepted=None,
            actual_usage_amount=None,
        )
        is None
    )

    attempt_terms = {
        **terms,
        "billing_trigger": BillingTrigger.ON_ATTEMPT,
        "failure_charge_policy": FailureChargePolicy.CHARGE_FIXED_ATTEMPT_FEE,
        "fixed_attempt_fee": money("0.0004"),
    }
    assert billable_amount_for_terms(
        **attempt_terms,
        execution_status=ProviderExecutionStatus.FAILED,
        provider_started=False,
        result_accepted=False,
        actual_usage_amount=None,
    ) == money("0.0004")

    maximum_attempt_terms = {
        **terms,
        "billing_trigger": BillingTrigger.ON_ATTEMPT,
        "failure_charge_policy": FailureChargePolicy.CHARGE_MAXIMUM,
    }
    assert billable_amount_for_terms(
        **maximum_attempt_terms,
        execution_status=ProviderExecutionStatus.FAILED,
        provider_started=False,
        result_accepted=False,
        actual_usage_amount=None,
    ) == money("0.0040")


@pytest.mark.asyncio
async def test_manager_reserve_is_durably_idempotent_and_recovers_lost_response(
    tmp_path: Path,
) -> None:
    store = ReceiptStore(tmp_path / "reserve-recovery.db")
    seed_payment_evidence(store, suffix="reserve-retry", maximum="0.0050")
    manager = budget_manager(
        store,
        PrepaidBalanceAdapterV2(money("1"), clock=lambda: NOW),
        limit="0.0100",
    )
    first = await reserve_with_manager(
        manager,
        suffix="reserve-retry",
        maximum="0.0050",
    )
    retry_arguments = {
        "prepared_id": "prepared-reserve-retry",
        "quote_id": "quote-reserve-retry",
        "authorization_kind": AuthorizationKind.SIGNED_QUOTE,
        "authorization_id": "quote-reserve-retry",
        "action_id": "action-reserve-retry",
        "attempt_id": "attempt-reserve-retry",
        "charge_id": "charge-reserve-retry",
        "maximum_amount": money("0.0050"),
        "idempotency_key": "reserve-key-reserve-retry",
        "claim_token": "claim-reserve-retry",
        "payment_approved": True,
        "executor_id": "executor.test",
    }
    assert await manager.reserve_v2(**retry_arguments) == first
    assert len(store.list_payment_reservations_v2(action_id=first.action_id)) == 1
    with pytest.raises(ConfigurationError, match="idempotency"):
        await manager.reserve_v2(
            **{**retry_arguments, "attempt_id": "attempt-conflict"}
        )

    seed_payment_evidence(store, suffix="reserve-lost", maximum="0.0050")
    fail_once = FailOnceReserveAdapter()
    recovering = budget_manager(store, fail_once, limit="0.0100")
    claim_token = "claim-reserve-lost"
    store.claim_prepared_decision(
        "prepared-reserve-lost",
        claim_token=claim_token,
        claimed_at=NOW,
    )
    lost_arguments = {
        "prepared_id": "prepared-reserve-lost",
        "quote_id": "quote-reserve-lost",
        "authorization_kind": AuthorizationKind.SIGNED_QUOTE,
        "authorization_id": "quote-reserve-lost",
        "action_id": "action-reserve-lost",
        "attempt_id": "attempt-reserve-lost",
        "charge_id": "charge-reserve-lost",
        "maximum_amount": money("0.0050"),
        "idempotency_key": "reserve-key-reserve-lost",
        "claim_token": claim_token,
        "payment_approved": True,
        "executor_id": "executor.test",
    }
    with pytest.raises(RuntimeError, match="lost reservation"):
        await recovering.reserve_v2(**lost_arguments)
    uncertain = store.list_payment_reservations_v2(action_id="action-reserve-lost")
    assert len(uncertain) == 1
    assert uncertain[0].state is PaymentReservationState.INDETERMINATE

    recovered = await recovering.reserve_v2(**lost_arguments)
    assert recovered.reservation_id == uncertain[0].reservation_id
    assert recovered.state is PaymentReservationState.RESERVED
    assert fail_once.external_holds == 1


@pytest.mark.asyncio
async def test_manager_refund_retry_conflict_and_failure_are_durable(
    tmp_path: Path,
) -> None:
    store = ReceiptStore(tmp_path / "refund-manager-edges.db")
    seed_payment_evidence(store, suffix="refund-edges", maximum="0.0050")
    manager = budget_manager(
        store,
        PrepaidBalanceAdapterV2(money("1"), clock=lambda: NOW),
        limit="0.0100",
    )
    held = await reserve_with_manager(manager, suffix="refund-edges", maximum="0.0050")
    advance_prepared(
        store,
        suffix="refund-edges",
        states=(PreparedDecisionState.INVOKING, PreparedDecisionState.SETTLING),
    )
    captured = await manager.capture_v2(
        held.reservation_id,
        evidence=evidence(held, "0.0050"),
        idempotency_key="capture-refund-edges",
    )
    refunded = await manager.refund_v2(
        captured.settlement_id,
        amount=money("0.0010"),
        reason="billing correction",
        idempotency_key="refund-edges",
    )
    assert (
        await manager.refund_v2(
            captured.settlement_id,
            amount=money("0.0010"),
            reason="billing correction",
            idempotency_key="refund-edges",
        )
        == refunded
    )
    with pytest.raises(ConfigurationError, match="idempotency"):
        await manager.refund_v2(
            captured.settlement_id,
            amount=money("0.0010"),
            reason="changed correction",
            idempotency_key="refund-edges",
        )
    with pytest.raises(ConfigurationError, match="requires a reason"):
        await manager.refund_v2(
            captured.settlement_id,
            amount=money("0.0010"),
            reason="",
            idempotency_key="refund-blank",
        )
    with pytest.raises(ConfigurationError, match="unavailable"):
        await manager.refund_v2(
            "settlement-missing",
            amount=money("0.0010"),
            reason="missing",
            idempotency_key="refund-missing",
        )
    with pytest.raises(ConfigurationError, match="currency"):
        await manager.refund_v2(
            captured.settlement_id,
            amount=money("0.0010", "EUR"),
            reason="wrong currency",
            idempotency_key="refund-currency",
        )

    seed_payment_evidence(store, suffix="refund-fails", maximum="0.0050")
    failing = budget_manager(
        store,
        FailingRefundAdapter(money("1"), clock=lambda: NOW),
        limit="0.0100",
    )
    failing_hold = await reserve_with_manager(
        failing,
        suffix="refund-fails",
        maximum="0.0050",
    )
    advance_prepared(
        store,
        suffix="refund-fails",
        states=(PreparedDecisionState.INVOKING, PreparedDecisionState.SETTLING),
    )
    failing_capture = await failing.capture_v2(
        failing_hold.reservation_id,
        evidence=evidence(failing_hold, "0.0050"),
        idempotency_key="capture-refund-fails",
    )
    with pytest.raises(RuntimeError, match="refund outage"):
        await failing.refund_v2(
            failing_capture.settlement_id,
            amount=money("0.0010"),
            reason="rail outage",
            idempotency_key="refund-fails",
        )
    pending = store.pending_refund_authorizations_v2()
    authorization = next(
        item for item in pending if item["idempotency_key"] == "refund-fails"
    )
    assert authorization["state"] == "INDETERMINATE"
    operation = store.get_payment_operation("refund", "refund-fails")
    assert operation is not None
    assert operation["state"] == "indeterminate"


@pytest.mark.asyncio
async def test_manager_reconciliation_requires_independent_matching_evidence(
    tmp_path: Path,
) -> None:
    store = ReceiptStore(tmp_path / "reconciliation-edges.db")
    seed_payment_evidence(store, suffix="reconcile", maximum="0.0050")
    response: dict[str, object] = {}

    def reconciliation_adapter(
        *,
        name: str = "callback",
        provider_id: str = "provider.callback",
    ) -> CallbackPaymentAdapterV2:
        return CallbackPaymentAdapterV2(
            name,
            reserve=lambda _reservation: None,
            settle=lambda *_args: {"external_reference": "capture-reference"},
            release=lambda *_args: None,
            refund=lambda *_args: None,
            reconcile=lambda _reference: response["value"],
            provider_id=provider_id,
            clock=lambda: NOW,
        )

    adapter = reconciliation_adapter()
    manager = budget_manager(store, adapter, limit="0.0100")
    held = await reserve_with_manager(manager, suffix="reconcile", maximum="0.0050")
    advance_prepared(
        store,
        suffix="reconcile",
        states=(PreparedDecisionState.INVOKING, PreparedDecisionState.SETTLING),
    )
    captured = await manager.capture_v2(
        held.reservation_id,
        evidence=evidence(held, "0.0050"),
        idempotency_key="capture-reconcile",
    )

    def record(
        suffix: str,
        *,
        settlement_id: str = captured.settlement_id,
        expected: str = "0.0050",
        provider_id: str = "provider.callback",
        with_evidence: bool = True,
    ) -> BillingReconciliation:
        return BillingReconciliation(
            reconciliation_id=f"reconciliation-{suffix}",
            settlement_id=settlement_id,
            provider_id=provider_id,
            billing_record_reference=(f"billing-{suffix}" if with_evidence else None),
            expected_amount=money(expected),
            billed_amount=money(expected),
            discrepancy=money("0"),
            status=ReconciliationStatus.MATCHED,
            reconciled_at=NOW,
        )

    response["value"] = record("valid")
    valid = await manager.reconcile_v2(
        captured.settlement_id,
        idempotency_key="reconcile-valid",
    )
    assert store.get_billing_reconciliation(valid.reconciliation_id) == valid
    assert (
        await manager.reconcile_v2(
            captured.settlement_id,
            idempotency_key="reconcile-valid",
        )
        == valid
    )

    response["value"] = "not-a-reconciliation"
    invalid_type = reconciliation_adapter()
    with pytest.raises(ConfigurationError, match="must return BillingReconciliation"):
        await invalid_type.reconcile("invalid-type")
    response["value"] = record("wrong-provider", provider_id="provider.other")
    invalid_provider = reconciliation_adapter()
    with pytest.raises(ConfigurationError, match="wrong provider"):
        await invalid_provider.reconcile("wrong-provider")

    cases = (
        (
            "missing-settlement",
            reconciliation_adapter(),
            record("missing-settlement", settlement_id="settlement-missing"),
            "settlement is unavailable",
        ),
        (
            "wrong-rail",
            reconciliation_adapter(name="other-rail"),
            record("wrong-rail"),
            "does not match settlement rail",
        ),
        (
            "wrong-amount",
            reconciliation_adapter(),
            record("wrong-amount", expected="0.0040"),
            "expected amount does not match",
        ),
        (
            "no-evidence",
            reconciliation_adapter(),
            record("no-evidence", with_evidence=False),
            "independent billing evidence",
        ),
    )
    for suffix, case_adapter, case_record, message in cases:
        response["value"] = case_record
        case_manager = budget_manager(store, case_adapter, limit="0.0100")
        with pytest.raises(ConfigurationError, match=message):
            await case_manager.reconcile_v2(
                captured.settlement_id,
                idempotency_key=f"reconcile-{suffix}",
            )
        operation = store.get_payment_operation("reconcile", f"reconcile-{suffix}")
        assert operation is not None
        assert operation["state"] == "indeterminate"


def test_manager_configuration_human_approval_and_authorization_guards(
    tmp_path: Path,
) -> None:
    budget = AgentBudget(
        daily_marketplace_limit_usd=1,
        max_per_action_usd=Decimal("0.005"),
        prepaid_balance_usd=1,
        authorization=AuthorizationPolicy(
            auto_approve_under_usd=Decimal("0.001"),
            financial_actions_require_human=True,
        ),
    )
    store = ReceiptStore(tmp_path / "payment-configuration.db")
    without_v2 = BudgetManager(budget, store, FreePaymentAdapter(), clock=lambda: NOW)
    with pytest.raises(ConfigurationError, match="V2 payment adapter"):
        without_v2.authorize_v2(
            money("0"),
            executor_id="executor.test",
            payment_approved=True,
        )

    currency_mismatch = BudgetManager(
        budget,
        store,
        FreePaymentAdapter(),
        adapter_v2=PrepaidBalanceAdapterV2(money("1", "EUR"), clock=lambda: NOW),
        settlement_currency="USD",
        clock=lambda: NOW,
    )
    with pytest.raises(ConfigurationError, match="adapter currency"):
        currency_mismatch.authorize_v2(
            money("0.001"),
            executor_id="executor.test",
            payment_approved=True,
            human_approved=True,
        )

    manager = BudgetManager(
        budget,
        store,
        FreePaymentAdapter(),
        adapter_v2=PrepaidBalanceAdapterV2(money("1"), clock=lambda: NOW),
        clock=lambda: NOW,
    )
    with pytest.raises(ConfigurationError, match="max_per_action"):
        manager.authorize_v2(
            money("0.006"),
            executor_id="executor.test",
            payment_approved=True,
            human_approved=True,
        )
    with pytest.raises(ApprovalRequired, match="human approval"):
        manager.authorize_v2(
            money("0.001"),
            executor_id="executor.test",
            payment_approved=True,
        )
    manager.authorize_v2(
        money("0.001"),
        executor_id="executor.test",
        payment_approved=True,
        human_approved=True,
    )


@pytest.mark.asyncio
async def test_manager_rejects_unbound_authorization_before_reservation(
    tmp_path: Path,
) -> None:
    store = ReceiptStore(tmp_path / "authorization-guards.db")
    manager = budget_manager(
        store,
        PrepaidBalanceAdapterV2(money("1"), clock=lambda: NOW),
        limit="0.0100",
    )
    base = {
        "prepared_id": "prepared-unbound",
        "quote_id": "quote-unbound",
        "authorization_kind": AuthorizationKind.SIGNED_QUOTE,
        "authorization_id": "quote-unbound",
        "action_id": "action-unbound",
        "attempt_id": "attempt-unbound",
        "charge_id": "charge-unbound",
        "maximum_amount": money("0.0050"),
        "idempotency_key": "reserve-unbound",
        "claim_token": "claim-unbound",
        "payment_approved": True,
    }
    invalid_cases = (
        ({"claim_token": ""}, "claim token"),
        ({"claim_token": "x" * 257}, "claim token"),
        ({"authorization_id": ""}, "authorization ID"),
        ({"quote_id": "quote-other"}, "must match quote ID"),
        (
            {
                "authorization_kind": AuthorizationKind.PUBLISHED_OFFER,
                "authorization_id": "offer-unbound",
            },
            "cannot carry a quote ID",
        ),
    )
    for changed, message in invalid_cases:
        with pytest.raises(ConfigurationError, match=message):
            await manager.reserve_v2(**{**base, **changed})
    assert store.list_payment_reservations_v2(action_id="action-unbound") == []


@pytest.mark.asyncio
async def test_manager_rejects_corrupt_rail_receipts_and_preserves_recovery_state(
    tmp_path: Path,
) -> None:
    settlement_store = ReceiptStore(tmp_path / "corrupt-settlement.db")
    seed_payment_evidence(
        settlement_store,
        suffix="corrupt-settlement",
        maximum="0.0050",
    )
    settlement_manager = budget_manager(
        settlement_store,
        CorruptSettlementAdapter(money("1"), clock=lambda: NOW),
        limit="0.0100",
    )
    settlement_hold = await reserve_with_manager(
        settlement_manager,
        suffix="corrupt-settlement",
        maximum="0.0050",
    )
    advance_prepared(
        settlement_store,
        suffix="corrupt-settlement",
        states=(PreparedDecisionState.INVOKING, PreparedDecisionState.SETTLING),
    )
    with pytest.raises(ConfigurationError, match="unexpected settlement ID"):
        await settlement_manager.settle_v2(
            settlement_hold.reservation_id,
            actual_amount=money("0.0038"),
            evidence=evidence(settlement_hold, "0.0038"),
            idempotency_key="corrupt-settlement",
        )
    uncertain_settlement = settlement_store.get_payment_reservation_v2(
        settlement_hold.reservation_id
    )
    assert uncertain_settlement is not None
    assert uncertain_settlement.state is PaymentReservationState.INDETERMINATE
    assert settlement_store.list_settlement_receipts(
        prepared_id=settlement_hold.prepared_id
    ) == []

    release_store = ReceiptStore(tmp_path / "corrupt-release.db")
    seed_payment_evidence(release_store, suffix="corrupt-release", maximum="0.0050")
    release_manager = budget_manager(
        release_store,
        CorruptReleaseAdapter(money("1"), clock=lambda: NOW),
        limit="0.0100",
    )
    release_hold = await reserve_with_manager(
        release_manager,
        suffix="corrupt-release",
        maximum="0.0050",
    )
    with pytest.raises(ConfigurationError, match="invalid release"):
        await release_manager.release_v2(
            release_hold.reservation_id,
            reason="failure before provider invocation",
            idempotency_key="corrupt-release",
        )
    uncertain_release = release_store.get_payment_reservation_v2(
        release_hold.reservation_id
    )
    assert uncertain_release is not None
    assert uncertain_release.state is PaymentReservationState.INDETERMINATE

    refund_store = ReceiptStore(tmp_path / "corrupt-refund.db")
    seed_payment_evidence(refund_store, suffix="corrupt-refund", maximum="0.0050")
    refund_manager = budget_manager(
        refund_store,
        CorruptRefundAdapter(money("1"), clock=lambda: NOW),
        limit="0.0100",
    )
    refund_hold = await reserve_with_manager(
        refund_manager,
        suffix="corrupt-refund",
        maximum="0.0050",
    )
    advance_prepared(
        refund_store,
        suffix="corrupt-refund",
        states=(PreparedDecisionState.INVOKING, PreparedDecisionState.SETTLING),
    )
    captured = await refund_manager.capture_v2(
        refund_hold.reservation_id,
        evidence=evidence(refund_hold, "0.0050"),
        idempotency_key="capture-before-corrupt-refund",
    )
    with pytest.raises(ConfigurationError, match="unexpected refund ID"):
        await refund_manager.refund_v2(
            captured.settlement_id,
            amount=money("0.0010"),
            reason="corrupt rail response",
            idempotency_key="corrupt-refund",
        )
    refund_operation = refund_store.get_payment_operation("refund", "corrupt-refund")
    assert refund_operation is not None
    assert refund_operation["state"] == "indeterminate"
    pending = refund_store.pending_refund_authorizations_v2()
    assert any(item["idempotency_key"] == "corrupt-refund" for item in pending)


@pytest.mark.asyncio
async def test_legacy_budget_and_full_capture_guards_remain_compatible(
    tmp_path: Path,
) -> None:
    def legacy_quote(amount: float, suffix: str) -> Quote:
        return Quote(
            quote_id=f"legacy-quote-{suffix}",
            quote_request_id=f"legacy-request-{suffix}",
            provider_id="legacy.provider",
            executor_id="legacy.executor",
            capability="demo.action@1",
            monetary_usd=amount,
            estimate={},
            expires_at=NOW + timedelta(minutes=5),
        )

    def legacy_manager(
        suffix: str,
        *,
        daily: float,
        per_action: float,
        prepaid: float,
        human_required: bool = False,
    ) -> BudgetManager:
        return BudgetManager(
            AgentBudget(
                daily_marketplace_limit_usd=daily,
                max_per_action_usd=per_action,
                prepaid_balance_usd=prepaid,
                authorization=AuthorizationPolicy(
                    auto_approve_under_usd=0.001,
                    financial_actions_require_human=human_required,
                ),
            ),
            ReceiptStore(tmp_path / f"legacy-{suffix}.db"),
            PrepaidBalanceAdapter(1),
            clock=lambda: NOW,
        )

    with pytest.raises(ConfigurationError, match="max_per_action"):
        await legacy_manager(
            "per-action",
            daily=1,
            per_action=0.001,
            prepaid=1,
        ).reserve(
            legacy_quote(0.002, "per-action"),
            action_id="action-per-action",
            approved_side_effect=SideEffect.FINANCIAL,
        )
    with pytest.raises(ConfigurationError, match="daily marketplace"):
        await legacy_manager(
            "daily",
            daily=0.001,
            per_action=1,
            prepaid=1,
        ).reserve(
            legacy_quote(0.002, "daily"),
            action_id="action-daily",
            approved_side_effect=SideEffect.FINANCIAL,
        )
    with pytest.raises(ConfigurationError, match="prepaid balance"):
        await legacy_manager(
            "prepaid",
            daily=1,
            per_action=1,
            prepaid=0.001,
        ).reserve(
            legacy_quote(0.002, "prepaid"),
            action_id="action-prepaid",
            approved_side_effect=SideEffect.FINANCIAL,
        )
    human_manager = legacy_manager(
        "human",
        daily=1,
        per_action=1,
        prepaid=1,
        human_required=True,
    )
    with pytest.raises(ApprovalRequired, match="human approval"):
        await human_manager.reserve(
            legacy_quote(0.001, "human"),
            action_id="action-human",
            approved_side_effect=SideEffect.FINANCIAL,
        )
    held = await human_manager.reserve(
        legacy_quote(0.001, "approved"),
        action_id="action-approved",
        approved_side_effect=SideEffect.FINANCIAL,
        human_approved=True,
    )
    captured = await human_manager.capture(held.reservation_id)
    refunded = await human_manager.refund(captured.capture_id, 0.0005)
    assert captured.amount_usd == 0.001
    assert refunded.amount_usd == 0.0005
    with pytest.raises(ConfigurationError, match="reservation is unavailable"):
        await human_manager.capture("reservation-missing")
    with pytest.raises(ConfigurationError, match="capture is unavailable"):
        await human_manager.refund("capture-missing", 0)

    legacy_adapter = PrepaidBalanceAdapter(0)
    with pytest.raises(ConfigurationError, match="insufficient prepaid balance"):
        await legacy_adapter.capture(
            PaymentReservation(
                quote_id="legacy-quote-defensive",
                action_id="legacy-action-defensive",
                adapter="prepaid",
                amount_usd=0.001,
            )
        )
