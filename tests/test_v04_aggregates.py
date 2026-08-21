from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

import aeep.economic as economic_api
from aeep.economic.aggregates import MarketAggregatePrior, MarketAggregateSelector
from aeep.economic.canonical import canonical_payload
from aeep.economic.signing import Ed25519Signer
from aeep.economic.trust import TrustedProviderKey, TrustStore, TrustStoreVerifier
from aeep.errors import ConfigurationError
from aeep.models import (
    CurrencyAmount,
    EconomicEvidenceLevel,
    MarketAggregate,
    MarketAggregatesConfig,
    SignatureAlgorithm,
    SignatureEnvelopeV2,
)
from aeep.store import ReceiptStore

NOW = datetime(2026, 8, 14, 12, tzinfo=UTC)
CAPABILITY = "text.statistics@1"
PROVIDER = "local.reference-provider"
EXECUTOR = "reference.http.statistics"
FINGERPRINT = f"sha256:{'a' * 64}"
BUCKET = "2^14"
REGION = "us-west"
TIER = "standard"


def signer(*, key_id: str = "aggregate-key") -> Ed25519Signer:
    return Ed25519Signer.from_private_bytes(bytes(range(32)), key_id=key_id)


def verifier(value: Ed25519Signer) -> TrustStoreVerifier:
    key = TrustedProviderKey(
        provider_id=PROVIDER,
        key_id=value.key_id,
        public_key=value.public_key_base64url(),
        valid_from=NOW - timedelta(days=1),
        valid_until=NOW + timedelta(days=1),
        allowed_capabilities=(CAPABILITY,),
    )
    return TrustStoreVerifier(TrustStore([key]), clock=lambda: NOW)


def aggregate(value: Ed25519Signer, **updates: object) -> MarketAggregate:
    data: dict[str, object] = {
        "aggregate_id": "aggregate-1",
        "capability": CAPABILITY,
        "provider_id": PROVIDER,
        "executor_id": EXECUTOR,
        "executor_fingerprint": FINGERPRINT,
        "region": REGION,
        "account_tier": TIER,
        "input_bucket": BUCKET,
        "sample_size": 40,
        "window_start": NOW - timedelta(hours=2),
        "window_end": NOW - timedelta(hours=1),
        "actual_cost_p50": {"amount": "0.0038", "currency": "USD"},
        "actual_cost_p95": {"amount": "0.0047", "currency": "USD"},
        "latency_ms_p50": "12.5",
        "latency_ms_p95": "25",
        "valid_success_rate": "0.95",
        "valid_success_lower_bound": "0.86",
        "settlement_verified_fraction": "0.90",
        "billing_reconciled_fraction": "0.75",
        "generated_at": NOW - timedelta(minutes=30),
        "expires_at": NOW + timedelta(hours=1),
        "signature": SignatureEnvelopeV2(
            algorithm=SignatureAlgorithm.ED25519,
            key_id=value.key_id,
            value="AA",
        ),
    }
    data.update(updates)
    unsigned = MarketAggregate.model_validate(data)
    return unsigned.model_copy(update={"signature": value.sign(canonical_payload(unsigned))})


def config(**updates: object) -> MarketAggregatesConfig:
    values: dict[str, object] = {
        "enabled": True,
        "maximum_age_seconds": 86_400,
        "minimum_sample_size": 20,
        "minimum_settlement_verified_fraction": "0.80",
    }
    values.update(updates)
    return MarketAggregatesConfig.model_validate(values)


@dataclass
class FakeStore:
    records: list[MarketAggregate]
    calls: list[tuple[str | None, int]] = field(default_factory=list)

    def list_market_aggregates(
        self,
        *,
        capability: str | None = None,
        limit: int = 1_000,
    ) -> list[MarketAggregate]:
        self.calls.append((capability, limit))
        return self.records[:limit]


def select(selector: MarketAggregateSelector) -> MarketAggregatePrior | None:
    return selector.select(
        capability=CAPABILITY,
        provider_id=PROVIDER,
        executor_id=EXECUTOR,
        executor_fingerprint=FINGERPRINT,
        input_bucket=BUCKET,
        region=REGION,
        account_tier=TIER,
    )


def test_aggregate_prior_api_is_exported() -> None:
    assert economic_api.MarketAggregateSelector is MarketAggregateSelector
    assert economic_api.MarketAggregatePrior is MarketAggregatePrior


def test_selector_uses_store_and_returns_signed_scoring_only_provenance(tmp_path: Path) -> None:
    signing_key = signer()
    older = aggregate(
        signing_key,
        aggregate_id="aggregate-older",
        generated_at=NOW - timedelta(hours=1),
    )
    newest = aggregate(signing_key, aggregate_id="aggregate-newest")
    with ReceiptStore(tmp_path / "aggregates.db") as store:
        store.save_market_aggregate(older)
        store.save_market_aggregate(newest)
        selector = MarketAggregateSelector(
            store,
            verifier(signing_key),
            config=config(),
            settlement_currency="USD",
            clock=lambda: NOW,
        )
        prior = select(selector)

    assert prior is not None
    assert prior.aggregate == newest
    assert prior.source_aggregate_id == "aggregate-newest"
    assert prior.expected_cash == CurrencyAmount(amount="0.0038", currency="USD")
    assert prior.cash_p95_prior == CurrencyAmount(amount="0.0047", currency="USD")
    assert prior.latency_ms_p50 == Decimal("12.5")
    assert prior.latency_ms_p95 == Decimal("25")
    assert prior.valid_success_rate == Decimal("0.95")
    assert prior.valid_success_lower_bound == Decimal("0.86")
    assert prior.evidence_level is EconomicEvidenceLevel.STATIC_PRIOR
    assert not prior.binding
    assert not prior.qualification_evidence
    assert not prior.activation_evidence


@pytest.mark.parametrize(
    ("field_name", "wrong_value"),
    [
        ("capability", "text.statistics@2"),
        ("provider_id", "other.provider"),
        ("executor_id", "other.executor"),
        ("executor_fingerprint", f"sha256:{'b' * 64}"),
        ("input_bucket", "2^15"),
        ("region", "eu-west"),
        ("account_tier", "enterprise"),
    ],
)
def test_selector_requires_exact_route_and_cohort_binding(
    field_name: str,
    wrong_value: object,
) -> None:
    signing_key = signer()
    store = FakeStore([aggregate(signing_key, **{field_name: wrong_value})])
    selector = MarketAggregateSelector(
        store,
        verifier(signing_key),
        config=config(),
        settlement_currency="USD",
        clock=lambda: NOW,
    )
    assert select(selector) is None


def test_selector_rejects_untrusted_stale_weak_or_currency_mismatched_records() -> None:
    signing_key = signer()
    untrusted_key = signer(key_id="unknown-key")
    tampered = aggregate(signing_key).model_copy(
        update={"actual_cost_p50": CurrencyAmount(amount="0.0001", currency="USD")}
    )
    rejected = (
        aggregate(signing_key, aggregate_id="low-sample", sample_size=19),
        aggregate(
            signing_key,
            aggregate_id="low-coverage",
            settlement_verified_fraction="0.79",
        ),
        aggregate(
            signing_key,
            aggregate_id="expired",
            expires_at=NOW - timedelta(minutes=1),
        ),
        aggregate(
            signing_key,
            aggregate_id="too-old",
            window_start=NOW - timedelta(days=4),
            window_end=NOW - timedelta(days=3),
            generated_at=NOW - timedelta(days=2),
            expires_at=NOW + timedelta(days=1),
        ),
        aggregate(
            signing_key,
            aggregate_id="future-window",
            window_end=NOW + timedelta(minutes=1),
        ),
        aggregate(
            signing_key,
            aggregate_id="wrong-currency",
            actual_cost_p50={"amount": "0.0038", "currency": "EUR"},
            actual_cost_p95={"amount": "0.0047", "currency": "EUR"},
        ),
        aggregate(untrusted_key, aggregate_id="untrusted-key"),
        tampered,
    )
    for candidate in rejected:
        selector = MarketAggregateSelector(
            FakeStore([candidate]),
            verifier(signing_key),
            config=config(),
            settlement_currency="USD",
            clock=lambda: NOW,
        )
        assert select(selector) is None, candidate.aggregate_id


def test_disabled_selector_does_not_query_and_unknown_cash_stays_unknown() -> None:
    signing_key = signer()
    unknown_cash = aggregate(
        signing_key,
        actual_cost_p50=None,
        actual_cost_p95=None,
    )
    store = FakeStore([unknown_cash])
    disabled = MarketAggregateSelector(
        store,
        verifier(signing_key),
        config=config(enabled=False),
        settlement_currency="USD",
        clock=lambda: NOW,
    )
    assert select(disabled) is None
    assert store.calls == []

    enabled = MarketAggregateSelector(
        store,
        verifier(signing_key),
        config=config(),
        settlement_currency="USD",
        clock=lambda: NOW,
    )
    prior = select(enabled)
    assert prior is not None
    assert prior.expected_cash is None
    assert prior.cash_p95_prior is None


def test_selector_rejects_naive_clock() -> None:
    signing_key = signer()
    selector = MarketAggregateSelector(
        FakeStore([aggregate(signing_key)]),
        verifier(signing_key),
        config=config(),
        settlement_currency="USD",
        clock=lambda: datetime(2026, 8, 14, 12),
    )
    with pytest.raises(ConfigurationError, match="timezone-aware"):
        select(selector)


def test_selector_rejects_aggregate_backdated_before_key_validity() -> None:
    signing_key = signer()
    key = TrustedProviderKey(
        provider_id=PROVIDER,
        key_id=signing_key.key_id,
        public_key=signing_key.public_key_base64url(),
        valid_from=NOW - timedelta(minutes=15),
        valid_until=NOW + timedelta(days=1),
        allowed_capabilities=(CAPABILITY,),
    )
    selector = MarketAggregateSelector(
        FakeStore([aggregate(signing_key)]),
        TrustStoreVerifier(TrustStore([key]), clock=lambda: NOW),
        config=config(),
        settlement_currency="USD",
        clock=lambda: NOW,
    )
    assert select(selector) is None
