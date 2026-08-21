from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

import aeep
from aeep.models import (
    ActionFeatures,
    BillingReconciliation,
    BillingTrigger,
    BoundedQuote,
    CandidateRanking,
    CapabilityOffer,
    CurrencyAmount,
    EconomicEvidenceLevel,
    EconomicEvidenceLink,
    FailureChargePolicy,
    MarketAggregate,
    MeterQuantity,
    PaymentReservationState,
    PaymentReservationV2,
    PreparedDecisionState,
    PreparedRouteDecision,
    PreparedRouteTransition,
    PricingDispute,
    PricingRule,
    ProviderExecutionStatus,
    QuoteRequestV2,
    ReconciliationStatus,
    RetryChargePolicy,
    SettlementReceipt,
    SettlementStatus,
    SignatureEnvelopeV2,
    UsageStatement,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
ACTION_DIGEST = "sha256:" + ("a" * 64)
POLICY_DIGEST = "sha256:" + ("b" * 64)
FINGERPRINT = "sha256:" + ("c" * 64)
TERMS_DIGEST = "sha256:" + ("d" * 64)


def test_v04_protocol_models_are_public() -> None:
    names = {
        "BillingReconciliation",
        "BoundedQuote",
        "CapabilityOffer",
        "CurrencyAmount",
        "EconomicEvidenceConfig",
        "EconomicEvidenceLevel",
        "EconomicStrictModel",
        "EconomicLiveQuotesConfig",
        "EconomicNetworkConfig",
        "EconomicPaymentConfig",
        "EconomicRequirementsConfig",
        "EconomicTrustStoreConfig",
        "MarketAggregate",
        "MarketAggregatesConfig",
        "MeterQuantity",
        "PaymentReservationV2",
        "PreparedRouteDecision",
        "PricingRule",
        "QuoteRequestV2",
        "SettlementReceipt",
        "SignatureEnvelopeV2",
        "UsageStatement",
    }
    assert names <= set(aeep.__all__)
    assert all(getattr(aeep, name) is not None for name in names)


def signature() -> SignatureEnvelopeV2:
    return SignatureEnvelopeV2(algorithm="ed25519", key_id="reference-key", value="AA")


def pricing_rule(rule_id: str = "request") -> PricingRule:
    return PricingRule(
        rule_id=rule_id,
        fixed_amount={"amount": "0.0010", "currency": "USD"},
    )


def offer(**updates: object) -> CapabilityOffer:
    values: dict[str, object] = {
        "offer_id": "offer-1",
        "provider_id": "local.reference-provider",
        "capability": "text.statistics@1",
        "executor_id": "reference.http.statistics",
        "executor_fingerprint": FINGERPRINT,
        "pricing_rules": (pricing_rule(),),
        "billing_trigger": BillingTrigger.ON_SUCCESS,
        "failure_charge_policy": FailureChargePolicy.NO_CHARGE,
        "retry_charge_policy": RetryChargePolicy.EACH_ATTEMPT,
        "settlement_currency": "USD",
        "valid_from": NOW,
        "valid_until": NOW + timedelta(hours=1),
        "terms_digest": TERMS_DIGEST,
        "issued_at": NOW,
        "signature": signature(),
    }
    values.update(updates)
    return CapabilityOffer.model_validate(values)


def quote_request(**updates: object) -> QuoteRequestV2:
    values: dict[str, object] = {
        "quote_request_id": "request-1",
        "action_id": "action-1",
        "capability": "text.statistics@1",
        "executor_id": "reference.http.statistics",
        "executor_fingerprint": FINGERPRINT,
        "action_digest": ACTION_DIGEST,
        "input_features": ActionFeatures(
            input_bytes=14336,
            input_items=1,
            text_characters=14336,
            max_depth=1,
            size_bucket="2^13",
        ),
        "disclosed_quote_features": {"input_bytes": 14336, "cached": False},
        "desired_currency": "USD",
        "maximum_acceptable_amount": {"amount": "0.0050", "currency": "USD"},
        "nonce": "nonce-12345678",
        "created_at": NOW,
        "expires_at": NOW + timedelta(minutes=1),
    }
    values.update(updates)
    return QuoteRequestV2.model_validate(values)


def bounded_quote(**updates: object) -> BoundedQuote:
    values: dict[str, object] = {
        "quote_id": "quote-1",
        "quote_request_id": "request-1",
        "offer_id": "offer-1",
        "provider_id": "local.reference-provider",
        "capability": "text.statistics@1",
        "executor_id": "reference.http.statistics",
        "executor_fingerprint": FINGERPRINT,
        "action_digest": ACTION_DIGEST,
        "nonce": "nonce-12345678",
        "expected_amount": {"amount": "0.0038", "currency": "USD"},
        "maximum_amount": {"amount": "0.0050", "currency": "USD"},
        "estimated_meters": (
            {"meter": "bytes", "unit": "byte", "quantity": "14336"},
        ),
        "billing_trigger": BillingTrigger.ON_SUCCESS,
        "failure_charge_policy": FailureChargePolicy.NO_CHARGE,
        "retry_charge_policy": RetryChargePolicy.EACH_ATTEMPT,
        "terms_digest": TERMS_DIGEST,
        "issued_at": NOW,
        "expires_at": NOW + timedelta(minutes=1),
        "signature": signature(),
    }
    values.update(updates)
    return BoundedQuote.model_validate(values)


def _assert_no_float(value: object) -> None:
    if isinstance(value, dict):
        for item in value.values():
            _assert_no_float(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_float(item)
    else:
        assert not isinstance(value, float)


def test_offer_is_immutable_exact_versioned_and_round_trips() -> None:
    value = offer()
    assert value.valid_at(NOW)
    assert not value.valid_at(NOW + timedelta(hours=1))
    assert CapabilityOffer.model_validate_json(value.model_dump_json()) == value
    _assert_no_float(json.loads(value.model_dump_json()))
    with pytest.raises(ValidationError):
        value.offer_id = "changed"


@pytest.mark.parametrize(
    "updates",
    [
        {"capability": "text.statistics"},
        {"executor_fingerprint": "c" * 64},
        {"valid_from": datetime(2026, 1, 1)},
        {"valid_until": NOW},
        {"settlement_currency": "EUR"},
        {"pricing_rules": (pricing_rule("same"), pricing_rule("same"))},
    ],
)
def test_offer_rejects_invalid_identity_time_currency_and_duplicate_rules(
    updates: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        offer(**updates)


def test_quote_request_disclosure_is_primitive_bounded_and_currency_safe() -> None:
    request = quote_request()
    assert request.desired_currency == "USD"
    assert "input" not in request.model_dump(mode="json")
    with pytest.raises(ValidationError):
        quote_request(disclosed_quote_features={"raw": {"resume": "secret"}})
    with pytest.raises(ValidationError):
        quote_request(disclosed_quote_features={"ratio": 0.5})
    with pytest.raises(ValidationError):
        quote_request(maximum_acceptable_amount={"amount": "1", "currency": "EUR"})
    with pytest.raises(ValidationError):
        quote_request(created_at=datetime(2026, 1, 1))


def test_bounded_quote_binding_and_amount_validation() -> None:
    quote = bounded_quote()
    quote.validate_binding(quote_request(), at=NOW, maximum_ttl_seconds=60)
    assert BoundedQuote.model_validate_json(quote.model_dump_json()) == quote
    with pytest.raises(ValidationError, match="exceed"):
        bounded_quote(expected_amount={"amount": "0.006", "currency": "USD"})
    with pytest.raises(ValidationError, match="currencies"):
        bounded_quote(expected_amount={"amount": "0.003", "currency": "EUR"})
    with pytest.raises(ValueError, match="action digest"):
        quote.validate_binding(
            quote_request(action_digest="sha256:" + ("e" * 64)),
            at=NOW,
            maximum_ttl_seconds=60,
        )
    with pytest.raises(ValueError, match="TTL"):
        quote.validate_binding(quote_request(), at=NOW, maximum_ttl_seconds=30)


def test_fixed_attempt_fee_is_structured_signed_and_bounded() -> None:
    with pytest.raises(ValidationError, match="fixed attempt fee"):
        offer(
            failure_charge_policy=FailureChargePolicy.CHARGE_FIXED_ATTEMPT_FEE,
        )
    signed_offer = offer(
        failure_charge_policy=FailureChargePolicy.CHARGE_FIXED_ATTEMPT_FEE,
        fixed_attempt_fee={"amount": "0.0004", "currency": "USD"},
    )
    assert signed_offer.fixed_attempt_fee == CurrencyAmount(
        amount=Decimal("0.0004"), currency="USD"
    )

    with pytest.raises(ValidationError, match="fixed attempt fee"):
        bounded_quote(
            failure_charge_policy=FailureChargePolicy.CHARGE_FIXED_ATTEMPT_FEE,
        )
    signed_quote = bounded_quote(
        failure_charge_policy=FailureChargePolicy.CHARGE_FIXED_ATTEMPT_FEE,
        fixed_attempt_fee={"amount": "0.0004", "currency": "USD"},
    )
    assert signed_quote.fixed_attempt_fee == signed_offer.fixed_attempt_fee
    with pytest.raises(ValidationError, match="cannot exceed"):
        bounded_quote(
            failure_charge_policy=FailureChargePolicy.CHARGE_FIXED_ATTEMPT_FEE,
            fixed_attempt_fee={"amount": "0.0051", "currency": "USD"},
        )
    with pytest.raises(ValidationError, match="required only"):
        bounded_quote(fixed_attempt_fee={"amount": "0.0004", "currency": "USD"})


def test_duplicate_meter_pairs_are_rejected() -> None:
    meter = {"meter": "bytes", "unit": "byte", "quantity": "1"}
    with pytest.raises(ValidationError, match="duplicate"):
        bounded_quote(estimated_meters=(meter, meter))


def test_prepared_decision_feasibility_and_legal_transitions() -> None:
    infeasible = PreparedRouteDecision(
        action_id="action-1",
        action_digest=ACTION_DIGEST,
        effective_policy_digest=POLICY_DIGEST,
        expires_at=NOW + timedelta(minutes=1),
        created_at=NOW,
    )
    assert not infeasible.feasible

    prepared = PreparedRouteDecision(
        prepared_id="prepared-1",
        action_id="action-1",
        action_digest=ACTION_DIGEST,
        effective_policy_digest=POLICY_DIGEST,
        selected_executor_id="reference.http.statistics",
        selected_executor_fingerprint=FINGERPRINT,
        selected_quote_id="quote-1",
        quote_ids=("quote-1",),
        candidate_rankings=(
            CandidateRanking(
                executor_id="reference.http.statistics",
                executor_fingerprint=FINGERPRINT,
                rank=1,
                score="-0.05",
                expected_amount={"amount": "0.0038", "currency": "USD"},
                maximum_amount={"amount": "0.0050", "currency": "USD"},
                quote_id="quote-1",
                evidence_level=EconomicEvidenceLevel.SIGNED_QUOTE,
            ),
        ),
        disclosed_quote_features={"input_bytes": 14336},
        maximum_cash_authorization={"amount": "0.0050", "currency": "USD"},
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=1),
    )
    assert prepared.feasible and prepared.id == "prepared-1"
    assert prepared.candidate_rankings[0].score == Decimal("-0.05")
    assert prepared.model_dump(mode="json")["candidate_rankings"][0]["score"] == "-0.05"
    reserved = prepared.transitioned(PreparedDecisionState.RESERVED)
    assert reserved.state is PreparedDecisionState.RESERVED
    with pytest.raises(ValueError, match="illegal"):
        prepared.transitioned(PreparedDecisionState.SETTLED)
    PreparedRouteTransition(
        prepared_id=prepared.id,
        from_state=PreparedDecisionState.PREPARED,
        to_state=PreparedDecisionState.RESERVED,
        occurred_at=NOW,
    )
    with pytest.raises(ValidationError, match="illegal"):
        PreparedRouteTransition(
            prepared_id=prepared.id,
            from_state=PreparedDecisionState.PREPARED,
            to_state=PreparedDecisionState.SETTLED,
            occurred_at=NOW,
        )


def test_reservation_usage_and_partial_settlement_chain() -> None:
    reservation = PaymentReservationV2(
        charge_id="charge-1",
        prepared_id="prepared-1",
        quote_id="quote-1",
        action_id="action-1",
        attempt_id="attempt-1",
        maximum_amount={"amount": "0.0050", "currency": "USD"},
        adapter="prepaid",
        idempotency_key="reserve-1",
        created_at=NOW,
        updated_at=NOW,
    )
    assert reservation.state is PaymentReservationState.RESERVED
    usage = UsageStatement(
        usage_statement_id="usage-1",
        quote_id="quote-1",
        prepared_id="prepared-1",
        action_id="action-1",
        attempt_id="attempt-1",
        provider_id="local.reference-provider",
        executor_id="reference.http.statistics",
        executor_fingerprint=FINGERPRINT,
        execution_status=ProviderExecutionStatus.SUCCESS,
        meters=(MeterQuantity(meter="bytes", unit="byte", quantity="14336"),),
        provider_calculated_amount={"amount": "0.0038", "currency": "USD"},
        started_at=NOW,
        completed_at=NOW + timedelta(seconds=1),
        issued_at=NOW + timedelta(seconds=1),
        signature=signature(),
    )
    assert UsageStatement.model_validate_json(usage.model_dump_json()) == usage
    settlement = SettlementReceipt(
        settlement_id="settlement-1",
        charge_id="charge-1",
        prepared_id="prepared-1",
        quote_id="quote-1",
        reservation_id=reservation.reservation_id,
        attempt_id="attempt-1",
        reserved_amount={"amount": "0.0050", "currency": "USD"},
        captured_amount={"amount": "0.0038", "currency": "USD"},
        released_amount={"amount": "0.0012", "currency": "USD"},
        payment_rail="prepaid",
        status=SettlementStatus.SETTLED,
        evidence_level=EconomicEvidenceLevel.PAYMENT_SETTLEMENT,
        settled_at=NOW + timedelta(seconds=2),
    )
    assert settlement.captured_amount.amount == Decimal("0.0038")
    assert settlement.released_amount.amount == Decimal("0.0012")
    _assert_no_float(json.loads(settlement.model_dump_json()))


def test_usage_and_settlement_reject_duplicates_overcapture_and_unaccounted_final() -> None:
    meter = MeterQuantity(meter="bytes", unit="byte", quantity="1")
    with pytest.raises(ValidationError, match="duplicate"):
        UsageStatement(
            usage_statement_id="usage-1",
            quote_id="quote-1",
            prepared_id="prepared-1",
            action_id="action-1",
            attempt_id="attempt-1",
            provider_id="provider",
            executor_id="executor",
            executor_fingerprint=FINGERPRINT,
            execution_status=ProviderExecutionStatus.SUCCESS,
            meters=(meter, meter),
            issued_at=NOW,
            signature=signature(),
        )
    base = {
        "settlement_id": "settlement-1",
        "charge_id": "charge-1",
        "prepared_id": "prepared-1",
        "quote_id": "quote-1",
        "reservation_id": "reservation-1",
        "attempt_id": "attempt-1",
        "reserved_amount": {"amount": "1", "currency": "USD"},
        "payment_rail": "prepaid",
        "status": SettlementStatus.SETTLED,
        "evidence_level": EconomicEvidenceLevel.PAYMENT_SETTLEMENT,
        "settled_at": NOW,
    }
    with pytest.raises(ValidationError, match="exceed"):
        SettlementReceipt.model_validate(
            {
                **base,
                "captured_amount": {"amount": "1.1", "currency": "USD"},
                "released_amount": {"amount": "0", "currency": "USD"},
            }
        )
    with pytest.raises(ValidationError, match="full reservation"):
        SettlementReceipt.model_validate(
            {
                **base,
                "captured_amount": {"amount": "0.5", "currency": "USD"},
                "released_amount": {"amount": "0.4", "currency": "USD"},
            }
        )


def test_reconciliation_and_market_aggregate_rules() -> None:
    reconciliation = BillingReconciliation(
        reconciliation_id="reconciliation-1",
        settlement_id="settlement-1",
        provider_id="local.reference-provider",
        expected_amount={"amount": "0.0038", "currency": "USD"},
        billed_amount={"amount": "0.0040", "currency": "USD"},
        discrepancy={"amount": "0.0002", "currency": "USD"},
        status=ReconciliationStatus.OVERCHARGED,
        reconciled_at=NOW,
    )
    assert BillingReconciliation.model_validate_json(reconciliation.model_dump_json()) == reconciliation
    with pytest.raises(ValidationError, match="discrepancy"):
        BillingReconciliation.model_validate(
            reconciliation.model_copy(
                update={"discrepancy": CurrencyAmount(amount="0.1", currency="USD")}
            ).model_dump()
        )

    aggregate = MarketAggregate(
        aggregate_id="aggregate-1",
        capability="text.statistics@1",
        provider_id="local.reference-provider",
        executor_id="reference.http.statistics",
        executor_fingerprint=FINGERPRINT,
        input_bucket="2^13",
        sample_size=20,
        window_start=NOW - timedelta(days=1),
        window_end=NOW,
        actual_cost_p50={"amount": "0.0038", "currency": "USD"},
        actual_cost_p95={"amount": "0.0050", "currency": "USD"},
        latency_ms_p50="10",
        latency_ms_p95="20",
        valid_success_rate="0.95",
        valid_success_lower_bound="0.80",
        settlement_verified_fraction="0.90",
        billing_reconciled_fraction="0.80",
        generated_at=NOW,
        expires_at=NOW + timedelta(days=1),
        signature=signature(),
    )
    assert aggregate.fresh_at(NOW)
    assert not aggregate.fresh_at(aggregate.expires_at)
    _assert_no_float(json.loads(aggregate.model_dump_json()))
    with pytest.raises(ValidationError):
        MarketAggregate.model_validate({**aggregate.model_dump(), "valid_success_rate": "1.1"})


def test_dispute_and_evidence_link_keep_one_charge_chain() -> None:
    dispute = PricingDispute(
        dispute_id="dispute-1",
        prepared_id="prepared-1",
        quote_id="quote-1",
        usage_statement_id="usage-1",
        provider_id="local.reference-provider",
        quoted_maximum={"amount": "0.005", "currency": "USD"},
        provider_claimed_amount={"amount": "0.006", "currency": "USD"},
        reason="provider-reported amount exceeds signed maximum",
        created_at=NOW,
    )
    link = EconomicEvidenceLink(
        link_id="link-1",
        charge_id="charge-1",
        evidence_level=EconomicEvidenceLevel.SIGNED_QUOTE,
        evidence_type="bounded_quote",
        evidence_id="quote-1",
        payload_digest=ACTION_DIGEST,
        authoritative=True,
        created_at=NOW,
    )
    assert dispute.quoted_maximum.amount == Decimal("0.005")
    assert link.charge_id == "charge-1"
    with pytest.raises(ValidationError):
        EconomicEvidenceLink.model_validate({**link.model_dump(), "supersedes_link_id": "link-1"})
