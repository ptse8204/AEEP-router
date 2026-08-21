from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from aeep.accounting import (
    cash_accounting_for_reporting,
    cash_accounting_from_reconciliation,
    cash_accounting_from_settlement,
    cash_accounting_from_usage_statement,
    cash_estimate_from_market_aggregate,
    cash_estimate_from_offer,
    cash_estimate_from_quote,
    subscription_model_accounting,
)
from aeep.economics import QuoteService
from aeep.estimator import HistoricalEstimator
from aeep.instrumentation import TraceIngestor
from aeep.models import (
    ActionContext,
    ActionRequest,
    BillingReconciliation,
    BillingTrigger,
    BoundedQuote,
    CapabilityOffer,
    CashAccounting,
    CashClassification,
    CashEstimate,
    CashEvidence,
    CurrencyAmount,
    EconomicEvidenceLevel,
    EvidenceSource,
    EvidenceStatus,
    ExecutionReceipt,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    FailureChargePolicy,
    Manifest,
    MarketAggregate,
    MeasurementEvidence,
    MetricWeights,
    ModelAccessChannel,
    ModelTokenUsage,
    PolicyConfig,
    PricingRule,
    ProviderExecutionStatus,
    QuoteRequest,
    ReconciliationStatus,
    RefundReceiptV2,
    ResourceAccounting,
    ResourceVector,
    RetryChargePolicy,
    RouteEstimate,
    SettlementReceipt,
    SettlementStatus,
    SideEffect,
    SignatureAlgorithm,
    SignatureEnvelopeV2,
    SubscriptionCharge,
    TrustLevel,
    UsageStatement,
)
from aeep.profiler import ActionProfiler
from aeep.registry import Registry
from aeep.router import Router
from aeep.scoring import score_candidate
from aeep.store import ReceiptStore

NOW = datetime(2026, 1, 1, tzinfo=UTC)
FINGERPRINT = f"sha256:{'a' * 64}"


def signature() -> SignatureEnvelopeV2:
    return SignatureEnvelopeV2(
        algorithm=SignatureAlgorithm.ED25519,
        key_id="test-key",
        value="AA",
    )


def amount(value: str) -> CurrencyAmount:
    return CurrencyAmount(amount=value, currency="USD")


def offer() -> CapabilityOffer:
    return CapabilityOffer(
        offer_id="offer-1",
        provider_id="provider.test",
        capability="text.statistics@1",
        executor_id="provider.statistics",
        executor_fingerprint=FINGERPRINT,
        pricing_rules=(
            PricingRule(
                rule_id="request",
                fixed_amount=amount("0.0010"),
            ),
            PricingRule(
                rule_id="bytes",
                meter="bytes",
                unit="byte",
                per_unit_amount=amount("0.0001"),
                maximum_amount=amount("0.0100"),
            ),
        ),
        billing_trigger=BillingTrigger.ON_SUCCESS,
        failure_charge_policy=FailureChargePolicy.NO_CHARGE,
        retry_charge_policy=RetryChargePolicy.EACH_ATTEMPT,
        settlement_currency="USD",
        valid_from=NOW,
        valid_until=NOW + timedelta(hours=1),
        terms_digest=FINGERPRINT,
        issued_at=NOW,
        signature=signature(),
    )


def quote(*, expected: str | None = "0.0038", maximum: str = "0.0050") -> BoundedQuote:
    return BoundedQuote(
        quote_id="quote-1",
        quote_request_id="request-1",
        provider_id="provider.test",
        capability="text.statistics@1",
        executor_id="provider.statistics",
        executor_fingerprint=FINGERPRINT,
        action_digest=FINGERPRINT,
        nonce="nonce-123",
        expected_amount=amount(expected) if expected is not None else None,
        maximum_amount=amount(maximum),
        billing_trigger=BillingTrigger.ON_SUCCESS,
        failure_charge_policy=FailureChargePolicy.NO_CHARGE,
        retry_charge_policy=RetryChargePolicy.EACH_ATTEMPT,
        terms_digest=FINGERPRINT,
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
        signature=signature(),
    )


def usage(*, value: str | None = "0.0038") -> UsageStatement:
    return UsageStatement(
        usage_statement_id="usage-1",
        quote_id="quote-1",
        prepared_id="prepared-1",
        action_id="action-1",
        attempt_id="attempt-1",
        provider_id="provider.test",
        executor_id="provider.statistics",
        executor_fingerprint=FINGERPRINT,
        execution_status=ProviderExecutionStatus.SUCCESS,
        provider_calculated_amount=amount(value) if value is not None else None,
        started_at=NOW,
        completed_at=NOW + timedelta(seconds=1),
        issued_at=NOW + timedelta(seconds=2),
        signature=signature(),
    )


def settlement(*, captured: str = "0.0038", released: str = "0.0012") -> SettlementReceipt:
    return SettlementReceipt(
        settlement_id="settlement-1",
        charge_id="charge-1",
        prepared_id="prepared-1",
        quote_id="quote-1",
        reservation_id="reservation-1",
        attempt_id="attempt-1",
        reserved_amount=amount("0.0050"),
        captured_amount=amount(captured),
        released_amount=amount(released),
        payment_rail="local-ledger",
        status=SettlementStatus.SETTLED,
        evidence_level=EconomicEvidenceLevel.PAYMENT_SETTLEMENT,
        settled_at=NOW + timedelta(seconds=3),
    )


def test_operator_attestation_is_not_payment_settlement_proof() -> None:
    assert (
        EconomicEvidenceLevel.OPERATOR_ATTESTED.rank
        < EconomicEvidenceLevel.PAYMENT_SETTLEMENT.rank
    )
    assert not EconomicEvidenceLevel.OPERATOR_ATTESTED.is_payment_evidence
    assert EconomicEvidenceLevel.PAYMENT_SETTLEMENT.is_payment_evidence
    assert EconomicEvidenceLevel.BILLING_RECONCILED.is_payment_evidence

    payload = settlement().model_dump(mode="python")
    payload["evidence_level"] = EconomicEvidenceLevel.OPERATOR_ATTESTED
    with pytest.raises(ValueError, match="payment-settlement evidence"):
        SettlementReceipt.model_validate(payload)


def reconciliation(
    *,
    billed: str = "0.0038",
    reconciliation_id: str = "reconciliation-1",
    status: ReconciliationStatus | None = None,
    reconciled_at: datetime | None = None,
) -> BillingReconciliation:
    billed_amount = Decimal(billed)
    expected_amount = Decimal("0.0038")
    resolved_status = status or (
        ReconciliationStatus.MATCHED
        if billed_amount == expected_amount
        else (
            ReconciliationStatus.OVERCHARGED
            if billed_amount > expected_amount
            else ReconciliationStatus.UNDERCHARGED
        )
    )
    return BillingReconciliation(
        reconciliation_id=reconciliation_id,
        settlement_id="settlement-1",
        provider_id="provider.test",
        billing_record_reference="bill-1",
        expected_amount=amount("0.0038"),
        billed_amount=amount(billed),
        discrepancy=amount(str(abs(billed_amount - expected_amount))),
        status=resolved_status,
        reconciled_at=reconciled_at or NOW + timedelta(days=1),
    )


def refund(
    refund_id: str,
    value: str,
    *,
    refunded_at: datetime | None = None,
) -> RefundReceiptV2:
    return RefundReceiptV2(
        refund_id=refund_id,
        settlement_id="settlement-1",
        charge_id="charge-1",
        amount=amount(value),
        reason="billing correction",
        idempotency_key=f"idempotency-{refund_id}",
        refunded_at=refunded_at or NOW + timedelta(days=2),
    )


def spec(estimate: RouteEstimate | None = None) -> ExecutorSpec:
    return ExecutorSpec(
        id="local.tool",
        capability="text.statistics@1",
        kind=ExecutorKind.PYTHON,
        description="local",
        estimate=estimate or RouteEstimate(resources=ResourceVector(latency_ms=10)),
        side_effect=SideEffect.NONE,
        config={"callable": "aeep.examples.tools:text_stats"},
    )


def test_offer_quote_and_market_aggregate_preserve_evidence_semantics() -> None:
    published = cash_estimate_from_offer(offer())
    assert published.amount_usd is None
    assert published.upper_bound_usd == Decimal("0.0110")
    assert published.evidence.source_reference == "economic-evidence:PUBLISHED_OFFER"

    bounded = cash_estimate_from_quote(quote(expected=None))
    assert bounded.amount_usd is None
    assert bounded.upper_bound_usd == Decimal("0.0050")
    assert bounded.evidence.source_reference == "economic-evidence:SIGNED_QUOTE"

    aggregate = MarketAggregate(
        aggregate_id="aggregate-1",
        capability="text.statistics@1",
        provider_id="provider.test",
        executor_id="provider.statistics",
        executor_fingerprint=FINGERPRINT,
        input_bucket="small",
        sample_size=20,
        window_start=NOW - timedelta(days=1),
        window_end=NOW,
        actual_cost_p50=amount("0.0040"),
        actual_cost_p95=amount("0.0090"),
        settlement_verified_fraction="0.80",
        billing_reconciled_fraction="0.50",
        generated_at=NOW,
        expires_at=NOW + timedelta(days=1),
        signature=signature(),
    )
    prior = cash_estimate_from_market_aggregate(aggregate)
    assert prior.amount_usd == Decimal("0.0040")
    assert prior.upper_bound_usd is None
    assert prior.evidence.source_reference == "economic-evidence:STATIC_PRIOR"


def test_offer_bound_includes_signed_fixed_attempt_fee() -> None:
    payload = offer().model_dump(mode="python")
    payload.update(
        failure_charge_policy=FailureChargePolicy.CHARGE_FIXED_ATTEMPT_FEE,
        fixed_attempt_fee=amount("0.0200"),
    )
    estimate = cash_estimate_from_offer(
        CapabilityOffer.model_validate(payload),
        {"bytes": "1"},
    )

    assert estimate.amount_usd == Decimal("0.0011")
    assert estimate.upper_bound_usd == Decimal("0.0200")


def test_legacy_quote_service_does_not_turn_unknown_cash_into_zero() -> None:
    request = QuoteRequest(
        action=ActionRequest(capability="text.statistics@1", input={})
    )
    assert QuoteService(Registry([spec()])).quote(request) == []

    confirmed_free = RouteEstimate(
        cash=CashEstimate(
            amount_usd=Decimal(0),
            upper_bound_usd=Decimal(0),
            evidence=MeasurementEvidence(
                status=EvidenceStatus.COMPLETE,
                source=EvidenceSource.STATIC_ESTIMATE,
                trust=TrustLevel.VERIFIED,
            ),
        )
    )
    quotes = QuoteService(Registry([spec(confirmed_free)])).quote(request)
    assert len(quotes) == 1
    assert quotes[0].monetary_usd == 0


def test_usage_settlement_and_reconciliation_are_one_charge() -> None:
    provider_report = cash_accounting_from_usage_statement(usage(), charge_id="charge-1")
    assert provider_report.actual_cash_cost() is None
    assert provider_report.components[0].classification is CashClassification.ESTIMATED
    assert provider_report.components[0].evidence.source is EvidenceSource.PROVIDER_REPORT

    paid = cash_accounting_from_settlement(settlement(), prior=provider_report)
    assert paid.actual_cash_cost() == Decimal("0.0038")
    assert len(paid.components) == 2
    assert len(paid.resolved_components()) == 1

    reconciled = cash_accounting_from_reconciliation(
        reconciliation(), charge_id="charge-1", prior=paid
    )
    assert reconciled.actual_cash_cost() == Decimal("0.0038")
    assert len(reconciled.components) == 3
    assert len(reconciled.resolved_components()) == 1
    assert reconciled.resolved_components()[0].classification is CashClassification.BILLING_RECONCILED

    duplicate = cash_accounting_from_reconciliation(
        reconciliation(), charge_id="charge-1", prior=reconciled
    )
    assert duplicate == reconciled


def test_reconciliation_supersedes_settlement_but_peer_discrepancies_conflict() -> None:
    provider_report = cash_accounting_from_usage_statement(usage(), charge_id="charge-1")
    paid = cash_accounting_from_settlement(settlement(), prior=provider_report)

    reconciled = cash_accounting_from_reconciliation(
        reconciliation(billed="0.0040"), charge_id="charge-1", prior=paid
    )
    assert reconciled.status is EvidenceStatus.COMPLETE
    assert reconciled.actual_cash_cost() == Decimal("0.0040")
    assert len(reconciled.components) == 3
    assert {
        item.classification for item in reconciled.components
    } == {
        CashClassification.ESTIMATED,
        CashClassification.VERIFIED,
        CashClassification.BILLING_RECONCILED,
    }
    assert reconciled.resolved_components()[0].classification is (
        CashClassification.BILLING_RECONCILED
    )

    conflicting = cash_accounting_from_reconciliation(
        reconciliation(billed="0.0041", reconciliation_id="reconciliation-2"),
        charge_id="charge-1",
        prior=reconciled,
    )
    assert conflicting.status is EvidenceStatus.CONFLICT
    assert conflicting.actual_cash_cost() is None
    assert len(conflicting.components) == 4
    assert conflicting.resolved_components() == []


def test_unresolved_reconciliation_does_not_supersede_settlement() -> None:
    paid = cash_accounting_from_settlement(settlement())
    disputed = cash_accounting_from_reconciliation(
        reconciliation(
            billed="0.0040",
            status=ReconciliationStatus.DISPUTED,
        ),
        charge_id="charge-1",
        prior=paid,
    )

    assert disputed.actual_cash_cost() == Decimal("0.0038")
    assert disputed.resolved_components()[0].classification is CashClassification.VERIFIED


def test_reporting_cash_uses_reconciliation_then_deduplicates_refunds() -> None:
    matched_discrepancy = reconciliation(
        billed="0.0040",
        status=ReconciliationStatus.MATCHED,
    )
    partial = refund("refund-partial", "0.0010")
    resolved = cash_accounting_for_reporting(
        settlement(),
        reconciliations=[
            reconciliation(
                billed="0.0050",
                reconciliation_id="reconciliation-disputed",
                status=ReconciliationStatus.DISPUTED,
                reconciled_at=NOW + timedelta(days=3),
            ),
            matched_discrepancy,
        ],
        refunds=[partial, partial, refund("refund-second", "0.0005")],
    )

    assert resolved.status is EvidenceStatus.COMPLETE
    assert resolved.actual_cash_cost() == Decimal("0.0025")
    assert resolved.resolved_components()[0].classification is (
        CashClassification.BILLING_RECONCILED
    )

    fully_refunded = cash_accounting_for_reporting(
        settlement(),
        refunds=[refund("refund-full", "0.0038")],
    )
    assert fully_refunded.status is EvidenceStatus.COMPLETE
    assert fully_refunded.actual_cash_cost() == Decimal(0)


@pytest.mark.asyncio
async def test_metrics_resolves_reconciliation_and_refunds_without_mutating_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = Router(Manifest(database=":memory:", executors=[spec()]))
    payment = settlement()
    receipt = ExecutionReceipt(
        receipt_id="receipt-metrics",
        decision_id="decision-metrics",
        action_id="action-metrics",
        capability="text.statistics@1",
        executor_id="local.tool",
        executor_kind=ExecutorKind.PYTHON,
        status=ExecutionStatus.SUCCESS,
        estimated=RouteEstimate(),
        accounting=ResourceAccounting(),
        metadata={
            "prepared_id": "prepared-1",
            "authorization_id": "quote-1",
            "settlement_id": payment.settlement_id,
            "charge_id": payment.charge_id,
        },
    )
    router.store.save_receipt(receipt)
    reconciliations = [
        reconciliation(billed="0.0040", status=ReconciliationStatus.MATCHED)
    ]
    refunds: list[RefundReceiptV2] = []
    monkeypatch.setattr(
        router.store,
        "list_settlement_receipts",
        lambda *, prepared_id=None, limit=1_000: [payment],
    )
    monkeypatch.setattr(
        router.store,
        "list_billing_reconciliations",
        lambda *, settlement_id=None, limit=1_000: list(reconciliations),
    )
    monkeypatch.setattr(
        router.store,
        "list_refund_receipts_v2",
        lambda *, settlement_id=None, limit=1_000: list(refunds),
    )

    reconciled = router.metrics()
    assert reconciled.cash_status is EvidenceStatus.COMPLETE
    assert reconciled.actual_cash_total_usd == Decimal("0.0040")
    assert reconciled.actual_cash_known_subtotal_usd == Decimal("0.0040")

    first = refund("refund-metrics-1", "0.0010")
    refunds.extend([first, first, refund("refund-metrics-2", "0.0005")])
    partially_refunded = router.metrics()
    assert partially_refunded.cash_status is EvidenceStatus.COMPLETE
    assert partially_refunded.actual_cash_total_usd == Decimal("0.0025")
    assert partially_refunded.total_money_spent_usd == pytest.approx(0.0025)

    reconciliations.clear()
    refunds[:] = [refund("refund-metrics-full", "0.0038")]
    fully_refunded = router.metrics()
    assert fully_refunded.cash_status is EvidenceStatus.COMPLETE
    assert fully_refunded.actual_cash_total_usd == Decimal(0)
    assert fully_refunded.total_money_spent_usd == 0
    stored = router.store.get_receipt(receipt.receipt_id)
    assert stored is not None
    assert stored.accounting.cash.status is EvidenceStatus.UNAVAILABLE
    await router.close()


def test_cash_resolution_uses_pinned_rate_before_estimate_and_verified_after() -> None:
    evidence = MeasurementEvidence(
        status=EvidenceStatus.COMPLETE,
        source=EvidenceSource.STATIC_ESTIMATE,
        trust=TrustLevel.VERIFIED,
    )
    estimated = CashEvidence(
        charge_id="charge-1",
        amount="0.0050",
        classification=CashClassification.ESTIMATED,
        evidence=evidence,
    )
    pinned = CashEvidence(
        charge_id="charge-1",
        amount="0.0045",
        classification=CashClassification.PINNED_RATE_BILLABLE_USAGE,
        evidence=evidence.model_copy(
            update={"source": EvidenceSource.PRICED_MEASURED_BILLABLE_USAGE}
        ),
        rate_snapshot_id="rate-1",
    )
    pinned_accounting = CashAccounting(
        status=EvidenceStatus.COMPLETE,
        components=[estimated, pinned],
    )
    assert pinned_accounting.resolved_components() == [pinned]
    assert pinned_accounting.actual_cash_cost() == Decimal("0.0045")

    verified = CashEvidence(
        charge_id="charge-1",
        amount="0.0040",
        classification=CashClassification.VERIFIED,
        evidence=evidence.model_copy(update={"source": EvidenceSource.BILLING_RECORD}),
    )
    verified_accounting = CashAccounting(
        status=EvidenceStatus.COMPLETE,
        components=[estimated, pinned, verified],
    )
    assert verified_accounting.resolved_components() == [verified]
    assert verified_accounting.actual_cash_cost() == Decimal("0.0040")


def test_provider_zero_is_unknown_until_payment_confirms_free() -> None:
    reported = cash_accounting_from_usage_statement(usage(value="0"), charge_id="charge-1")
    assert reported.actual_cash_cost() is None

    free = cash_accounting_from_settlement(
        settlement(captured="0", released="0.0050"), prior=reported
    )
    assert free.actual_cash_cost() == Decimal(0)


def test_scoring_uses_maximum_when_expected_is_absent() -> None:
    policy = PolicyConfig(
        weights=MetricWeights(
            monetary=1,
            latency=0,
            compute=0,
            subscription=0,
            reliability=0,
            quality=0,
            risk=0,
        )
    )
    bounded = score_candidate(
        spec(RouteEstimate(cash=cash_estimate_from_quote(quote(expected=None)))),
        RouteEstimate(cash=cash_estimate_from_quote(quote(expected=None))),
        policy,
        ActionContext(),
    )
    unknown_estimate = RouteEstimate()
    unknown = score_candidate(spec(unknown_estimate), unknown_estimate, policy, ActionContext())
    free_estimate = RouteEstimate(
        cash=CashEstimate(
            amount_usd=Decimal(0),
            upper_bound_usd=Decimal(0),
            evidence=MeasurementEvidence(
                status=EvidenceStatus.COMPLETE,
                source=EvidenceSource.STATIC_ESTIMATE,
                trust=TrustLevel.VERIFIED,
            ),
        )
    )
    free = score_candidate(spec(free_estimate), free_estimate, policy, ActionContext())

    assert bounded.score is not None and bounded.score.cash > 0
    assert bounded.score.cash_uncertainty == 0
    assert unknown.score is not None and unknown.score.cash_uncertainty > 0
    assert free.score is not None and free.score.cash == 0
    assert free.score.cash_uncertainty == 0


def test_historical_actuals_do_not_become_contractual_bounds() -> None:
    store = ReceiptStore(":memory:")
    executor = spec()
    paid = cash_accounting_from_settlement(settlement())
    store.save_receipt(
        ExecutionReceipt(
            decision_id="decision-1",
            action_id="action-1",
            capability=executor.capability,
            executor_id=executor.id,
            executor_kind=executor.kind,
            status=ExecutionStatus.SUCCESS,
            estimated=executor.estimate,
            accounting=ResourceAccounting(cash=paid),
        )
    )
    store.save_receipt(
        ExecutionReceipt(
            decision_id="decision-2",
            action_id="action-2",
            capability=executor.capability,
            executor_id=executor.id,
            executor_kind=executor.kind,
            status=ExecutionStatus.SUCCESS,
            estimated=executor.estimate,
        )
    )

    estimate = HistoricalEstimator(store).estimate(executor, PolicyConfig())
    assert estimate.cash.amount_usd == Decimal("0.0038")
    assert estimate.cash.upper_bound_usd is None
    assert estimate.cash.evidence.status is EvidenceStatus.PARTIAL
    store.close()


def test_instrumentation_marks_missing_cash_unavailable() -> None:
    report = TraceIngestor(Registry([spec()])).profile(
        {
            "name": "slow call",
            "attributes": {
                "aeep.capability": "text.statistics@1",
                "aeep.resource.latency_ms": 100,
            },
        }
    )
    assert "monetary_usd" not in report.calls[0].resources.model_fields_set
    assert report.recommendations
    assert report.recommendations[0].estimated_cash_saving_usd is None
    assert "cash comparison unavailable" in report.recommendations[0].reason

    confirmed_free = RouteEstimate(
        resources=ResourceVector(latency_ms=10),
        cash=CashEstimate(
            amount_usd=Decimal(0),
            upper_bound_usd=Decimal(0),
            evidence=MeasurementEvidence(
                status=EvidenceStatus.COMPLETE,
                source=EvidenceSource.STATIC_ESTIMATE,
                trust=TrustLevel.VERIFIED,
            ),
        ),
    )
    free_report = TraceIngestor(Registry([spec(confirmed_free)])).profile(
        {
            "name": "free slow call",
            "attributes": {
                "aeep.capability": "text.statistics@1",
                "aeep.resource.latency_ms": 100,
                "aeep.resource.monetary_usd": 0,
            },
        }
    )
    assert free_report.recommendations[0].estimated_cash_saving_usd == 0


def test_profiler_reported_cash_is_not_settlement_evidence() -> None:
    store = ReceiptStore(":memory:")
    with ActionProfiler(store=store, capability="x@1", executor_id="browser") as profile:
        profile.add_cost(0)
        profile.succeed()
    assert profile.receipt is not None
    assert profile.receipt.actual_resources.monetary_usd == 0
    assert profile.receipt.accounting.cash.actual_cash_cost() is None
    with pytest.raises(ValueError, match="finite and non-negative"):
        ActionProfiler(store=store, capability="x@1", executor_id="browser").add_cost(-1)
    store.close()


def test_subscription_usage_stays_separate_from_cash() -> None:
    tokens = ModelTokenUsage(
        provider="provider.test",
        model="model",
        access_channel=ModelAccessChannel.SUBSCRIPTION,
        input_tokens=10,
        output_tokens=2,
    )
    accounting = subscription_model_accounting(
        tokens,
        resource_pool="provider.plan",
        consumed=Decimal("2"),
        usage_evidence=MeasurementEvidence(
            status=EvidenceStatus.COMPLETE,
            source=EvidenceSource.LOCAL_METER,
            trust=TrustLevel.OBSERVED,
        ),
        included_or_paid=SubscriptionCharge.INCLUDED,
    )
    assert accounting.subscription_usage[0].consumed == Decimal("2")
    assert accounting.cash.actual_cash_cost() is None
