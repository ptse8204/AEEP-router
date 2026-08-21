from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

import aeep
from aeep.models import (
    AuthorizationKind,
    AuthorizationMeterQuantity,
    CurrencyAmount,
    EconomicEvidenceLevel,
    EconomicPaymentConfig,
    EconomicRequirementsConfig,
    PaymentReservationV2,
    PinnedRateCardAuthorizationConfig,
    PreparedRouteDecision,
    RateCardRate,
    RateCardSnapshot,
    RateType,
    SettlementReceipt,
    SettlementStatus,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
DIGEST = "sha256:" + ("a" * 64)
FINGERPRINT = "sha256:" + ("b" * 64)
RATE_CARD_ID = "rate_" + ("c" * 64)


def _prepared(**updates: object) -> PreparedRouteDecision:
    values: dict[str, object] = {
        "prepared_id": "prepared-1",
        "action_id": "action-1",
        "action_digest": DIGEST,
        "effective_policy_digest": DIGEST,
        "selected_executor_id": "executor-1",
        "selected_executor_fingerprint": FINGERPRINT,
        "created_at": NOW,
        "expires_at": NOW + timedelta(minutes=5),
    }
    values.update(updates)
    return PreparedRouteDecision.model_validate(values)


def _reservation(**updates: object) -> PaymentReservationV2:
    values: dict[str, object] = {
        "reservation_id": "reservation-1",
        "charge_id": "charge-1",
        "prepared_id": "prepared-1",
        "action_id": "action-1",
        "attempt_id": "attempt-1",
        "maximum_amount": {"amount": "0.0050", "currency": "USD"},
        "adapter": "prepaid",
        "idempotency_key": "reservation-key-1",
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(updates)
    return PaymentReservationV2.model_validate(values)


def _settlement(**updates: object) -> SettlementReceipt:
    values: dict[str, object] = {
        "settlement_id": "settlement-1",
        "charge_id": "charge-1",
        "prepared_id": "prepared-1",
        "reservation_id": "reservation-1",
        "attempt_id": "attempt-1",
        "reserved_amount": {"amount": "0.0050", "currency": "USD"},
        "captured_amount": {"amount": "0.0038", "currency": "USD"},
        "released_amount": {"amount": "0.0012", "currency": "USD"},
        "payment_rail": "prepaid",
        "status": SettlementStatus.SETTLED,
        "evidence_level": EconomicEvidenceLevel.PAYMENT_SETTLEMENT,
        "settled_at": NOW,
    }
    values.update(updates)
    return SettlementReceipt.model_validate(values)


def test_legacy_quote_records_migrate_to_explicit_authorization() -> None:
    prepared = _prepared(
        selected_quote_id="quote-1",
        quote_ids=("quote-1",),
        maximum_cash_authorization={"amount": "0.0050", "currency": "USD"},
    )
    reservation = _reservation(quote_id="quote-1")
    settlement = _settlement(quote_id="quote-1")

    for record in (prepared, reservation, settlement):
        assert record.authorization_kind is AuthorizationKind.SIGNED_QUOTE
        assert record.authorization_id == "quote-1"


def test_nonzero_static_prior_cannot_authorize_cash() -> None:
    with pytest.raises(ValidationError, match="immutable basis"):
        _prepared(maximum_cash_authorization={"amount": "0.0050", "currency": "USD"})

    confirmed_free = _prepared(
        maximum_cash_authorization=CurrencyAmount(amount=Decimal(0), currency="USD")
    )
    assert confirmed_free.authorization_kind is None


def test_offer_authorization_is_exactly_one_basis() -> None:
    prepared = _prepared(
        selected_offer_id="offer-1",
        authorization_kind=AuthorizationKind.PUBLISHED_OFFER,
        authorization_id="offer-1",
        maximum_cash_authorization={"amount": "0.0050", "currency": "USD"},
    )
    assert prepared.selected_quote_id is None

    with pytest.raises(ValidationError, match="cannot select another basis"):
        _prepared(
            selected_quote_id="quote-1",
            quote_ids=("quote-1",),
            selected_offer_id="offer-1",
            authorization_kind=AuthorizationKind.PUBLISHED_OFFER,
            authorization_id="offer-1",
            maximum_cash_authorization={"amount": "0.0050", "currency": "USD"},
        )


def test_pinned_rate_card_requires_exact_rate_quantity_mapping() -> None:
    quantity = AuthorizationMeterQuantity(
        rate_id="input-rate",
        meter="input_tokens",
        unit="token",
        quantity=Decimal(1000),
    )
    prepared = _prepared(
        selected_rate_card_id=RATE_CARD_ID,
        authorization_kind=AuthorizationKind.PINNED_RATE_CARD,
        authorization_id=RATE_CARD_ID,
        authorization_rate_ids=("input-rate",),
        authorization_meter_quantities=(quantity,),
        maximum_cash_authorization={"amount": "0.0050", "currency": "USD"},
    )
    assert prepared.authorization_meter_quantities == (quantity,)

    with pytest.raises(ValidationError, match="must match in order"):
        _prepared(
            selected_rate_card_id=RATE_CARD_ID,
            authorization_kind=AuthorizationKind.PINNED_RATE_CARD,
            authorization_id=RATE_CARD_ID,
            authorization_rate_ids=("other-rate",),
            authorization_meter_quantities=(quantity,),
            maximum_cash_authorization={"amount": "0.0050", "currency": "USD"},
        )
    with pytest.raises(ValidationError, match="requires rates and quantities"):
        _prepared(
            selected_rate_card_id=RATE_CARD_ID,
            authorization_kind=AuthorizationKind.PINNED_RATE_CARD,
            authorization_id=RATE_CARD_ID,
            maximum_cash_authorization={"amount": "0.0050", "currency": "USD"},
        )
    with pytest.raises(ValidationError, match="binary floating-point"):
        AuthorizationMeterQuantity(
            rate_id="input-rate",
            meter="input_tokens",
            unit="token",
            quantity=1.0,  # type: ignore[arg-type]
        )


def test_offer_reservation_and_settlement_do_not_require_quote_id() -> None:
    reservation = _reservation(
        authorization_kind=AuthorizationKind.PUBLISHED_OFFER,
        authorization_id="offer-1",
    )
    settlement = _settlement(
        authorization_kind=AuthorizationKind.PUBLISHED_OFFER,
        authorization_id="offer-1",
    )
    assert reservation.quote_id is None
    assert settlement.quote_id is None

    with pytest.raises(ValidationError, match="immutable authorization basis"):
        _reservation()
    with pytest.raises(ValidationError, match="cannot carry a quote ID"):
        _settlement(
            quote_id="quote-1",
            authorization_kind=AuthorizationKind.PUBLISHED_OFFER,
            authorization_id="offer-1",
        )


def test_invoice_requires_explicit_unlimited_budget() -> None:
    with pytest.raises(ValidationError, match="requires explicit unlimited_budget"):
        EconomicPaymentConfig(adapter="invoice")
    assert EconomicPaymentConfig(adapter="invoice", unlimited_budget=True).unlimited_budget
    with pytest.raises(ValidationError, match="restricted to the invoice"):
        EconomicPaymentConfig(adapter="prepaid", unlimited_budget=True)


def test_pinned_rate_card_operator_config_accepts_only_unconditional_rates() -> None:
    snapshot = RateCardSnapshot(
        provider="operator.pinned",
        product="reference",
        model="fixed-v1",
        effective_from=NOW - timedelta(days=1),
        effective_until=NOW + timedelta(days=1),
        retrieved_at=NOW,
        source_uri="https://operator.example/rates.json",
        source_content_sha256="d" * 64,
        currency="USD",
        rates=[
            RateCardRate(
                rate_id="request-rate",
                rate_type=RateType.OTHER,
                meter="requests",
                input_unit="request",
                output_unit="USD",
                unit_quantity=Decimal(1),
                rate_amount=Decimal("0.002"),
            )
        ],
    )
    assert snapshot.snapshot_id is not None
    config = PinnedRateCardAuthorizationConfig(
        rate_card_snapshot_id=snapshot.snapshot_id,
        meter_quantities=(
            AuthorizationMeterQuantity(
                rate_id="request-rate",
                meter="requests",
                unit="request",
                quantity=Decimal(2),
            ),
        ),
    )

    assert config.rate_ids == ("request-rate",)
    assert config.authorized_maximum(snapshot, at=NOW) == CurrencyAmount(
        amount=Decimal("0.004"), currency="USD"
    )
    requirements = EconomicRequirementsConfig(
        pinned_rate_cards={"executor.fixed": config}
    )
    assert requirements.pinned_rate_cards["executor.fixed"] == config

    conditional = RateCardSnapshot(
        **snapshot.model_dump(exclude={"snapshot_id", "rates", "source_content_sha256"}),
        source_content_sha256="e" * 64,
        rates=[snapshot.rates[0].model_copy(update={"region": "private-tier"})],
    )
    conditional_config = config.model_copy(
        update={"rate_card_snapshot_id": conditional.snapshot_id}
    )
    with pytest.raises(ValueError, match="conditional pinned rates"):
        conditional_config.authorized_maximum(conditional, at=NOW)


def test_pinned_rate_card_operator_config_rejects_ambiguous_selection() -> None:
    quantity = AuthorizationMeterQuantity(
        rate_id="request-rate",
        meter="requests",
        unit="request",
        quantity=Decimal(1),
    )
    with pytest.raises(ValidationError, match="unique rate IDs"):
        PinnedRateCardAuthorizationConfig(
            rate_card_snapshot_id=RATE_CARD_ID,
            meter_quantities=(quantity, quantity),
        )
    with pytest.raises(ValidationError, match="executor IDs"):
        EconomicRequirementsConfig(
            pinned_rate_cards={
                "not an executor": PinnedRateCardAuthorizationConfig(
                    rate_card_snapshot_id=RATE_CARD_ID,
                    meter_quantities=(quantity,),
                )
            }
        )


def test_authorization_and_v2_payment_surface_is_public() -> None:
    expected = {
        "AuthorizationKind",
        "AuthorizationMeterQuantity",
        "CallbackPaymentAdapterV2",
        "FreePaymentAdapterV2",
        "InvoicePaymentAdapterV2",
        "LocalLedgerPaymentAdapter",
        "PaymentAdapterV2",
        "PinnedRateCardAuthorizationConfig",
        "PrepaidBalanceAdapterV2",
        "billable_amount_for_execution",
    }
    assert expected <= set(aeep.__all__)
    assert all(hasattr(aeep, name) for name in expected)
