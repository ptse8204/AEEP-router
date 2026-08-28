from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from aeep.models import (
    CurrencyAmount,
    EconomicEvidenceConfig,
    EconomicEvidenceLevel,
    EconomicLiveQuotesConfig,
    EconomicNetworkConfig,
    EconomicRequirementsConfig,
    Manifest,
    MarketAggregatesConfig,
    MeterQuantity,
    PricingRoundingMode,
    PricingRule,
    Quote,
    QuoteFailurePolicy,
    QuoteRequest,
)


def _assert_no_floats(value: object) -> None:
    if isinstance(value, dict):
        for item in value.values():
            _assert_no_floats(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_floats(item)
    else:
        assert not isinstance(value, float)


def test_currency_amount_exact_json_round_trip_and_normalization() -> None:
    value = CurrencyAmount(amount=Decimal("0.003800"), currency="usd")
    assert value.amount == Decimal("0.003800")
    assert value.currency == "USD"
    assert value.model_dump_json() == '{"amount":"0.003800","currency":"USD"}'
    assert CurrencyAmount.model_validate_json(value.model_dump_json()) == value
    _assert_no_floats(json.loads(value.model_dump_json()))


@pytest.mark.parametrize("value", [-1, "-0.1", float("nan"), float("inf"), float("-inf")])
def test_currency_amount_rejects_negative_nonfinite_and_float(value: object) -> None:
    with pytest.raises(ValidationError):
        CurrencyAmount(amount=value, currency="USD")


def test_currency_amount_normalizes_negative_zero_without_losing_scale() -> None:
    value = CurrencyAmount(amount=Decimal("-0.0000"), currency="USD")
    assert value.amount == Decimal("0.0000")
    assert value.model_dump(mode="json")["amount"] == "0.0000"


@pytest.mark.parametrize("currency", ["US", "USDD", "U1D", " USD", "USD "])
def test_currency_rejects_invalid_codes(currency: str) -> None:
    with pytest.raises(ValidationError):
        CurrencyAmount(amount="1", currency=currency)


def test_currency_mismatch_is_explicit() -> None:
    with pytest.raises(ValueError, match="currency mismatch"):
        CurrencyAmount(amount="1", currency="EUR").require_currency("USD")


def test_fixed_and_linear_pricing_are_exact() -> None:
    fixed = PricingRule(
        rule_id="fixed",
        fixed_amount=CurrencyAmount(amount="0.0010", currency="USD"),
    )
    assert fixed.evaluate().amount == Decimal("0.0010")

    linear = PricingRule(
        rule_id="pages",
        meter="pages",
        unit="page",
        per_unit_amount=CurrencyAmount(amount="0.0002", currency="USD"),
    )
    assert linear.evaluate("14").amount == Decimal("0.0028")


def test_pricing_free_allowance_minimum_maximum_and_increment() -> None:
    rule = PricingRule(
        rule_id="bounded",
        meter="bytes",
        unit="byte",
        fixed_amount={"amount": "0.001", "currency": "USD"},
        per_unit_amount={"amount": "0.0001", "currency": "USD"},
        free_quantity="100",
        minimum_amount={"amount": "0.002", "currency": "USD"},
        maximum_amount={"amount": "0.005", "currency": "USD"},
        quantity_increment="10",
        rounding_mode=PricingRoundingMode.CEILING,
    )
    assert rule.evaluate("50").amount == Decimal("0.002")
    assert rule.evaluate("101").amount == Decimal("0.002")
    assert rule.evaluate("121").amount == Decimal("0.004")
    assert rule.evaluate("1000").amount == Decimal("0.005")


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (PricingRoundingMode.UP, "1"),
        (PricingRoundingMode.DOWN, "0"),
        (PricingRoundingMode.CEILING, "1"),
        (PricingRoundingMode.FLOOR, "0"),
        (PricingRoundingMode.HALF_UP, "1"),
        (PricingRoundingMode.HALF_EVEN, "0"),
    ],
)
def test_all_pricing_rounding_modes(mode: PricingRoundingMode, expected: str) -> None:
    rule = PricingRule(
        rule_id="round",
        meter="seconds",
        unit="second",
        per_unit_amount={"amount": "1", "currency": "USD"},
        quantity_increment="1",
        rounding_mode=mode,
    )
    assert rule.evaluate("0.5").amount == Decimal(expected)


@pytest.mark.parametrize(
    "payload",
    [
        {"rule_id": "empty"},
        {
            "rule_id": "missing-meter",
            "per_unit_amount": {"amount": "1", "currency": "USD"},
        },
        {
            "rule_id": "fixed-meter",
            "fixed_amount": {"amount": "1", "currency": "USD"},
            "meter": "requests",
            "unit": "request",
        },
        {
            "rule_id": "free-fixed",
            "fixed_amount": {"amount": "1", "currency": "USD"},
            "free_quantity": "1",
        },
        {
            "rule_id": "currency",
            "fixed_amount": {"amount": "1", "currency": "USD"},
            "minimum_amount": {"amount": "1", "currency": "EUR"},
        },
        {
            "rule_id": "bounds",
            "fixed_amount": {"amount": "1", "currency": "USD"},
            "minimum_amount": {"amount": "2", "currency": "USD"},
            "maximum_amount": {"amount": "1", "currency": "USD"},
        },
    ],
)
def test_pricing_rejects_inconsistent_combinations(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PricingRule.model_validate(payload)


def test_native_and_namespaced_meters() -> None:
    assert MeterQuantity(meter="pages", unit="page", quantity="14").quantity == 14
    assert (
        MeterQuantity(
            meter="provider-x.document_pages",
            unit="page",
            quantity="14.5",
        ).quantity
        == Decimal("14.5")
    )
    with pytest.raises(ValidationError, match="namespaced"):
        MeterQuantity(meter="custom_pages", unit="page", quantity="1")
    with pytest.raises(ValidationError):
        MeterQuantity(meter="pages", unit="page", quantity=0.5)


def test_legacy_quote_models_and_all_manifest_versions_remain_readable() -> None:
    for version in ("0.1", "0.15", "0.2", "0.3", "0.4"):
        assert Manifest(version=version).version == version

    request = QuoteRequest(action={"capability": "demo.echo@1"})
    quote = Quote(
        quote_request_id=request.quote_request_id,
        provider_id="legacy",
        executor_id="legacy.echo",
        capability="demo.echo@1",
        monetary_usd=0.01,
        estimate={},
        expires_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert Quote.model_validate_json(quote.model_dump_json()) == quote


def test_economic_config_is_offline_and_fail_closed_by_default() -> None:
    config = EconomicEvidenceConfig()
    assert not config.enabled
    assert not config.live_quotes.enabled
    assert not config.market_aggregates.enabled
    assert config.live_quotes.top_k == 3
    assert config.live_quotes.per_provider_timeout_seconds == 2
    assert config.live_quotes.total_timeout_seconds == 4
    assert config.live_quotes.maximum_response_bytes == 262_144
    assert config.live_quotes.maximum_clock_skew_seconds == 30
    assert config.live_quotes.maximum_quote_ttl_seconds == 600
    assert config.settlement_currency == "USD"
    assert config.network.allowed_quote_hosts == ()
    assert not config.network.allow_private_addresses
    assert not config.network.allow_redirects
    assert not config.network.trust_environment_proxy
    assert config.payment.adapter == "free"
    assert config.requirements.minimum_evidence_level is EconomicEvidenceLevel.SIGNED_QUOTE
    assert config.trust_store.path == "~/.config/aeep/provider-keys.json"
    assert EconomicEvidenceConfig.model_validate_json(config.model_dump_json()) == config


def test_manifest_defaults_to_v06_with_economic_networking_disabled() -> None:
    manifest = Manifest()
    assert manifest.version == "0.6"
    assert manifest.economic_evidence == EconomicEvidenceConfig()


def test_live_quotes_require_parent_enablement_and_exact_host_allowlist() -> None:
    with pytest.raises(ValidationError, match="USD-denominated"):
        EconomicEvidenceConfig(enabled=True, settlement_currency="EUR")
    with pytest.raises(ValidationError, match="economic evidence"):
        EconomicEvidenceConfig(live_quotes={"enabled": True})
    with pytest.raises(ValidationError, match="allowed quote host"):
        EconomicEvidenceConfig(enabled=True, live_quotes={"enabled": True})

    config = EconomicEvidenceConfig(
        enabled=True,
        settlement_currency="usd",
        live_quotes={"enabled": True},
        network={"allowed_quote_hosts": ["Quotes.Example.COM."]},
    )
    assert config.settlement_currency == "USD"
    assert config.network.allowed_quote_hosts == ("quotes.example.com",)


@pytest.mark.parametrize("unsafe_flag", ["allow_redirects", "trust_environment_proxy"])
def test_live_quotes_reject_unsupported_network_relaxations(unsafe_flag: str) -> None:
    with pytest.raises(ValidationError, match="live quotes do not permit"):
        EconomicEvidenceConfig.model_validate(
            {
                "enabled": True,
                "live_quotes": {"enabled": True},
                "network": {
                    "allowed_quote_hosts": ["quotes.example.com"],
                    unsafe_flag: True,
                },
            }
        )


@pytest.mark.parametrize(
    "host",
    [
        "https://quotes.example.com",
        "*.example.com",
        "quotes.example.com/path",
        "user@quotes.example.com",
        "bad..example.com",
        " quotes.example.com",
    ],
)
def test_quote_host_allowlist_rejects_non_exact_entries(host: str) -> None:
    with pytest.raises(ValidationError):
        EconomicNetworkConfig(allowed_quote_hosts=(host,))
    with pytest.raises(ValidationError, match="duplicates"):
        EconomicNetworkConfig(allowed_quote_hosts=("EXAMPLE.com", "example.com"))


@pytest.mark.parametrize(
    "updates",
    [
        {"top_k": 0},
        {"top_k": 21},
        {"per_provider_timeout_seconds": 0},
        {"per_provider_timeout_seconds": float("inf")},
        {"per_provider_timeout_seconds": 5, "total_timeout_seconds": 4},
        {"maximum_response_bytes": 100},
        {"maximum_clock_skew_seconds": -1},
        {"maximum_quote_ttl_seconds": 0},
    ],
)
def test_live_quote_limits_are_validated(updates: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        EconomicLiveQuotesConfig.model_validate(updates)


def test_market_aggregate_config_uses_decimal_coverage_and_parent_gate() -> None:
    config = MarketAggregatesConfig()
    assert config.minimum_sample_size == 20
    assert config.minimum_settlement_verified_fraction == Decimal("0.80")
    assert config.model_dump(mode="json")["minimum_settlement_verified_fraction"] == "0.80"
    with pytest.raises(ValidationError):
        MarketAggregatesConfig(minimum_settlement_verified_fraction=0.8)
    with pytest.raises(ValidationError):
        MarketAggregatesConfig(minimum_settlement_verified_fraction="1.01")
    with pytest.raises(ValidationError, match="economic evidence"):
        EconomicEvidenceConfig(market_aggregates={"enabled": True})


def test_quote_requirement_fallback_combinations_fail_closed() -> None:
    with pytest.raises(ValidationError, match="verified-offer"):
        EconomicRequirementsConfig(
            require_binding_quote_for_paid_routes=False,
            allow_verified_static_offer=False,
            quote_failure_policy=QuoteFailurePolicy.ALLOW_VERIFIED_OFFER,
        )
    with pytest.raises(ValidationError, match="static-prior"):
        EconomicRequirementsConfig(
            require_binding_quote_for_paid_routes=False,
            allow_static_prior=False,
            quote_failure_policy=QuoteFailurePolicy.ALLOW_STATIC_PRIOR,
        )
    with pytest.raises(ValidationError, match="binding quotes"):
        EconomicRequirementsConfig(
            require_binding_quote_for_paid_routes=True,
            allow_static_prior=True,
            quote_failure_policy=QuoteFailurePolicy.ALLOW_STATIC_PRIOR,
        )
    with pytest.raises(ValidationError, match="cannot exceed"):
        EconomicRequirementsConfig(
            minimum_evidence_level=EconomicEvidenceLevel.PAYMENT_SETTLEMENT
        )


def test_economic_config_rejects_inline_secret_fields() -> None:
    with pytest.raises(ValidationError):
        EconomicEvidenceConfig.model_validate(
            {"payment": {"adapter": "prepaid", "api_key": "secret"}}
        )
