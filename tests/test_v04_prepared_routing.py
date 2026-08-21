from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from aeep.economic.aggregates import MarketAggregateSelector
from aeep.economic.canonical import canonical_payload
from aeep.economic.prepared import action_digest, executor_fingerprint
from aeep.economic.quotes import QuoteErrorCode, QuoteProviderError
from aeep.economic.signing import Ed25519Signer
from aeep.economic.trust import TrustedProviderKey, TrustStore, TrustStoreVerifier
from aeep.errors import ConfigurationError
from aeep.estimator import action_features
from aeep.models import (
    ActionConstraints,
    ActionContext,
    ActionRequest,
    BillingTrigger,
    BoundedQuote,
    CapabilityOffer,
    CashEstimate,
    CurrencyAmount,
    DataSensitivity,
    EvidenceSource,
    EvidenceStatus,
    ExecutorKind,
    ExecutorSpec,
    FailureChargePolicy,
    Locality,
    Manifest,
    MarketAggregate,
    MarketAggregatesConfig,
    MeasurementEvidence,
    PreparedDecisionState,
    PricingRule,
    QuoteFailurePolicy,
    QuoteRequestV2,
    ResourceVector,
    RetryChargePolicy,
    RouteEstimate,
    SideEffect,
    SignatureAlgorithm,
    SignatureEnvelopeV2,
    TrustLevel,
)
from aeep.router import Router
from aeep.store import ReceiptStore

NOW = datetime(2026, 8, 14, 12, tzinfo=UTC)
CAPABILITY = "text.statistics@1"
PROVIDER = "provider.example"
QUOTE_HOST = "quotes.example"
TERMS_DIGEST = f"sha256:{'7' * 64}"
INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "page_count": {"type": "integer"},
        "access_token": {"type": "string"},
    },
    "required": ["text"],
    "additionalProperties": True,
}
UNSIGNED = SignatureEnvelopeV2(
    algorithm=SignatureAlgorithm.ED25519,
    key_id="provider-key",
    value="AA",
)


@dataclass
class MutableClock:
    now: datetime = NOW

    def __call__(self) -> datetime:
        return self.now


class SignedQuoteProvider:
    """Deterministic provider double; its evidence is signed by a real Ed25519 key."""

    def __init__(
        self,
        signer: Ed25519Signer,
        clock: MutableClock,
        *,
        amounts: dict[str, tuple[str | None, str]] | None = None,
        failing: set[str] | None = None,
        tamper: dict[str, dict[str, object]] | None = None,
    ) -> None:
        self.signer = signer
        self.clock = clock
        self.amounts = amounts or {}
        self.failing = failing or set()
        self.tamper = tamper or {}
        self.calls: list[str] = []
        self.offer_requests: list[str] = []
        self.requests: list[QuoteRequestV2] = []

    async def get_offers(
        self,
        capability: str,
        executor_ids: Sequence[str],
    ) -> tuple[()]:
        assert capability == CAPABILITY
        self.offer_requests.extend(executor_ids)
        return ()

    async def request_quote(self, request: QuoteRequestV2) -> BoundedQuote:
        self.calls.append(request.executor_id)
        self.requests.append(request)
        if request.executor_id in self.failing:
            raise QuoteProviderError(
                QuoteErrorCode.UNAVAILABLE,
                "binding quote is unavailable",
                provider_id=PROVIDER,
            )
        expected, maximum = self.amounts.get(request.executor_id, ("0.0010", "0.0020"))
        quote = BoundedQuote(
            quote_id=f"quote-{request.executor_id}-{len(self.calls)}",
            quote_request_id=request.quote_request_id,
            provider_id=PROVIDER,
            capability=request.capability,
            executor_id=request.executor_id,
            executor_fingerprint=request.executor_fingerprint,
            action_digest=request.action_digest,
            nonce=request.nonce,
            expected_amount=(
                CurrencyAmount(amount=expected, currency="USD")
                if expected is not None
                else None
            ),
            maximum_amount=CurrencyAmount(amount=maximum, currency="USD"),
            billing_trigger=BillingTrigger.ON_SUCCESS,
            failure_charge_policy=FailureChargePolicy.NO_CHARGE,
            retry_charge_policy=RetryChargePolicy.EACH_ATTEMPT,
            terms_digest=TERMS_DIGEST,
            issued_at=self.clock(),
            expires_at=self.clock() + timedelta(minutes=2),
            signature=UNSIGNED,
        )
        signed = quote.model_copy(update={"signature": self.signer.sign(canonical_payload(quote))})
        return signed.model_copy(update=self.tamper.get(request.executor_id, {}))


def _trust_verifier(signer: Ed25519Signer, clock: MutableClock) -> TrustStoreVerifier:
    key = TrustedProviderKey(
        provider_id=PROVIDER,
        key_id=signer.key_id,
        public_key=signer.public_key_base64url(),
        valid_from=NOW - timedelta(days=1),
        valid_until=NOW + timedelta(days=1),
        allowed_capabilities=(CAPABILITY,),
        allowed_quote_hosts=(QUOTE_HOST,),
    )
    return TrustStoreVerifier(TrustStore((key,)), clock=clock)


def _cash(value: str | None) -> CashEstimate:
    if value is None:
        return CashEstimate()
    return CashEstimate(
        amount_usd=Decimal(value),
        upper_bound_usd=Decimal(value),
        evidence=MeasurementEvidence(
            status=EvidenceStatus.COMPLETE,
            source=EvidenceSource.STATIC_ESTIMATE,
            trust=TrustLevel.SELF_ASSERTED,
        ),
    )


def _route(
    executor_id: str,
    *,
    latency_ms: float,
    cash: str | None,
    provider: bool = False,
    enabled: bool = True,
    disclosure: list[dict[str, object]] | None = None,
) -> ExecutorSpec:
    economic: dict[str, object] = {"requires_live_quote": True} if provider else {}
    if disclosure is not None:
        economic["quote_disclosure"] = {"fields": disclosure}
    return ExecutorSpec(
        id=executor_id,
        capability=CAPABILITY,
        kind=ExecutorKind.PYTHON,
        description=executor_id,
        input_schema=INPUT_SCHEMA,
        estimate=RouteEstimate(
            resources=ResourceVector(
                latency_ms=latency_ms,
                cpu_ms=latency_ms / 2,
                peak_memory_mb=8,
            ),
            cash=_cash(cash),
            success_probability=Decimal("0.99"),
            quality_score=Decimal("0.99"),
            risk_score=Decimal("0.01"),
            confidence=Decimal("0.90"),
        ),
        side_effect=SideEffect.READ,
        locality=Locality.INTERNET if provider else Locality.IN_PROCESS,
        requires_network=provider,
        provider_id=PROVIDER if provider else None,
        enabled=enabled,
        config={
            "callable": "aeep.examples.tools:text_stats",
            **({"economic": economic} if economic else {}),
        },
    )


def _manifest(
    *routes: ExecutorSpec,
    top_k: int = 3,
    requirements: dict[str, object] | None = None,
) -> Manifest:
    return Manifest(
        version="0.4",
        database=":memory:",
        executors=list(routes),
        economic_evidence={
            "enabled": True,
            "live_quotes": {"enabled": True, "top_k": top_k},
            "network": {"allowed_quote_hosts": [QUOTE_HOST]},
            "payment": {"adapter": "prepaid"},
            **({"requirements": requirements} if requirements is not None else {}),
        },
    )


def _router(
    manifest: Manifest,
    provider: SignedQuoteProvider,
    signer: Ed25519Signer,
    clock: MutableClock,
) -> Router:
    return Router(
        manifest,
        quote_provider=provider,
        economic_verifier=_trust_verifier(signer, clock),
        clock=clock,
    )


def _request(**updates: object) -> ActionRequest:
    values: dict[str, object] = {
        "action_id": "action-1",
        "capability": CAPABILITY,
        "input": {"text": "hello"},
    }
    values.update(updates)
    return ActionRequest.model_validate(values)


@pytest.mark.asyncio
async def test_route_remains_network_free() -> None:
    clock = MutableClock()
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="provider-key")
    provider = SignedQuoteProvider(signer, clock)
    router = _router(
        _manifest(_route("remote.dynamic", latency_ms=1, cash="0.001", provider=True)),
        provider,
        signer,
        clock,
    )
    try:
        decision = router.route(_request())
        assert decision.selected_executor_id == "remote.dynamic"
        assert provider.calls == []
        assert provider.offer_requests == []
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_trusted_market_prior_changes_only_the_live_quote_shortlist() -> None:
    clock = MutableClock()
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="provider-key")
    provider = SignedQuoteProvider(signer, clock)
    cheap_static = _route("remote.static-cheap", latency_ms=1, cash="0.001", provider=True)
    market_candidate = _route(
        "remote.market-cheap",
        latency_ms=1,
        cash="0.010",
        provider=True,
    )
    manifest = _manifest(cheap_static, market_candidate, top_k=1)
    manifest.economic_evidence.market_aggregates = MarketAggregatesConfig(
        enabled=True,
        minimum_sample_size=20,
        minimum_settlement_verified_fraction=Decimal("0.80"),
    )
    store = ReceiptStore(":memory:")
    unsigned = MarketAggregate(
        aggregate_id="aggregate-market-shortlist",
        capability=CAPABILITY,
        provider_id=PROVIDER,
        executor_id=market_candidate.id,
        executor_fingerprint=executor_fingerprint(market_candidate),
        input_bucket=action_features(_request().input).size_bucket,
        sample_size=40,
        window_start=clock() - timedelta(hours=2),
        window_end=clock() - timedelta(hours=1),
        actual_cost_p50=CurrencyAmount(amount="0.0001", currency="USD"),
        actual_cost_p95=CurrencyAmount(amount="0.0002", currency="USD"),
        settlement_verified_fraction=Decimal("0.95"),
        billing_reconciled_fraction=Decimal("0.90"),
        generated_at=clock() - timedelta(minutes=30),
        expires_at=clock() + timedelta(hours=1),
        signature=UNSIGNED,
    )
    signed = unsigned.model_copy(
        update={"signature": signer.sign(canonical_payload(unsigned))}
    )
    store.save_market_aggregate(signed)
    verifier = _trust_verifier(signer, clock)
    selector = MarketAggregateSelector(
        store,
        verifier,
        config=manifest.economic_evidence.market_aggregates,
        settlement_currency="USD",
        clock=clock,
    )
    router = Router(
        manifest,
        store=store,
        quote_provider=provider,
        economic_verifier=verifier,
        market_aggregate_selector=selector,
        clock=clock,
    )
    try:
        prepared = await router.prepare_route(_request())
        assert provider.calls == [market_candidate.id]
        assert prepared.selected_executor_id == market_candidate.id
        ranking = next(
            item
            for item in prepared.candidate_rankings
            if item.executor_id == market_candidate.id
        )
        assert ranking.evidence_level.name == "SIGNED_QUOTE"
        assert not router.store.get_route_candidate(market_candidate.id)
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_legacy_execute_cannot_bypass_required_economic_preparation() -> None:
    clock = MutableClock()
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="provider-key")
    provider = SignedQuoteProvider(signer, clock)
    router = _router(
        _manifest(_route("remote.dynamic", latency_ms=1, cash="0.001", provider=True)),
        provider,
        signer,
        clock,
    )
    try:
        decision = router.route(_request())
        with pytest.raises(ConfigurationError, match="requires prepared economic execution"):
            await router.execute(decision)
        assert provider.calls == []
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_live_maximum_budget_selects_confirmed_free_route() -> None:
    clock = MutableClock()
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="provider-key")
    provider = SignedQuoteProvider(
        signer,
        clock,
        amounts={"remote.dynamic": ("0.0038", "0.0100")},
    )
    router = _router(
        _manifest(
            _route("local.free", latency_ms=500, cash="0"),
            _route("remote.dynamic", latency_ms=1, cash="0.001", provider=True),
        ),
        provider,
        signer,
        clock,
    )
    try:
        prepared = await router.prepare_route(
            _request(constraints=ActionConstraints(max_cost_usd=0.005))
        )
        assert prepared.feasible
        assert prepared.selected_executor_id == "local.free"
        rejected = next(
            item for item in prepared.rejected_candidates if item.executor_id == "remote.dynamic"
        )
        reason = " ".join(rejected.reasons).lower()
        assert "maximum" in reason or "quote" in reason
        quote_failure = next(
            item for item in prepared.quote_failures if item.executor_id == "remote.dynamic"
        )
        assert "maximum acceptable" in quote_failure.reason
        assert provider.calls == ["remote.dynamic"]
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_unknown_provider_cost_requires_quote_and_never_becomes_free() -> None:
    clock = MutableClock()
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="provider-key")
    provider = SignedQuoteProvider(signer, clock, failing={"remote.unknown"})
    router = _router(
        _manifest(_route("remote.unknown", latency_ms=1, cash=None, provider=True)),
        provider,
        signer,
        clock,
    )
    try:
        prepared = await router.prepare_route(
            _request(constraints=ActionConstraints(max_cost_usd=1))
        )
        assert not prepared.feasible
        assert prepared.maximum_cash_authorization is None
        assert prepared.candidate_rankings == ()
        assert prepared.expected_accounting.cash.actual_cash_cost() is None
        assert provider.calls == ["remote.unknown"]
        assert any(item.executor_id == "remote.unknown" for item in prepared.quote_failures)
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_only_top_k_policy_feasible_active_routes_are_contacted() -> None:
    clock = MutableClock()
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="provider-key")
    provider = SignedQuoteProvider(signer, clock)
    router = _router(
        _manifest(
            _route("paid.0", latency_ms=1, cash="0.001", provider=True),
            _route("paid.1", latency_ms=2, cash="0.001", provider=True),
            _route("paid.2", latency_ms=3, cash="0.001", provider=True),
            _route("paid.denied", latency_ms=0.1, cash="0.001", provider=True),
            _route(
                "paid.inactive",
                latency_ms=0.1,
                cash="0.001",
                provider=True,
                enabled=False,
            ),
            top_k=2,
        ),
        provider,
        signer,
        clock,
    )
    try:
        prepared = await router.prepare_route(
            _request(
                constraints=ActionConstraints(
                    denied_executor_ids=["paid.denied"],
                )
            )
        )
        assert prepared.feasible
        assert set(provider.calls) == {"paid.0", "paid.1"}
        assert set(provider.offer_requests) == {"paid.0", "paid.1"}
        assert "paid.2" not in provider.calls
        assert "paid.denied" not in provider.calls
        assert "paid.inactive" not in provider.calls
        assert prepared.quote_request_count == 2
    finally:
        await router.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["action_digest", "executor_fingerprint"])
async def test_tampered_quote_binding_is_rejected(field: str) -> None:
    clock = MutableClock()
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="provider-key")
    provider = SignedQuoteProvider(
        signer,
        clock,
        tamper={"remote.dynamic": {field: f"sha256:{'9' * 64}"}},
    )
    router = _router(
        _manifest(_route("remote.dynamic", latency_ms=1, cash="0.001", provider=True)),
        provider,
        signer,
        clock,
    )
    try:
        prepared = await router.prepare_route(_request())
        assert not prepared.feasible
        assert prepared.quote_ids == ()
        assert router.store.list_bounded_quotes() == []
        assert any(
            failure.executor_id == "remote.dynamic"
            and failure.code in {"BINDING", "SIGNATURE", "INVALID_RESPONSE"}
            for failure in prepared.quote_failures
        )
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_quote_cannot_change_its_signed_offer_fixed_attempt_fee() -> None:
    clock = MutableClock()
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="provider-key")
    route = _route("remote.dynamic", latency_ms=1, cash="0.001", provider=True)
    unsigned_offer = CapabilityOffer(
        offer_id="offer-fixed-attempt-fee",
        provider_id=PROVIDER,
        capability=route.capability,
        executor_id=route.id,
        executor_fingerprint=executor_fingerprint(route),
        pricing_rules=(
            PricingRule(
                rule_id="fixed",
                fixed_amount=CurrencyAmount(amount="0.001", currency="USD"),
            ),
        ),
        billing_trigger=BillingTrigger.ON_ATTEMPT,
        failure_charge_policy=FailureChargePolicy.CHARGE_FIXED_ATTEMPT_FEE,
        retry_charge_policy=RetryChargePolicy.EACH_ATTEMPT,
        fixed_attempt_fee=CurrencyAmount(amount="0.0004", currency="USD"),
        settlement_currency="USD",
        valid_from=clock() - timedelta(minutes=1),
        valid_until=clock() + timedelta(hours=1),
        terms_digest=TERMS_DIGEST,
        issued_at=clock(),
        signature=UNSIGNED,
    )
    signed_offer = unsigned_offer.model_copy(
        update={"signature": signer.sign(canonical_payload(unsigned_offer))}
    )

    class FeeTamperingProvider(SignedQuoteProvider):
        async def get_offers(
            self,
            capability: str,
            executor_ids: Sequence[str],
        ) -> tuple[CapabilityOffer, ...]:
            self.offer_requests.extend(executor_ids)
            assert capability == signed_offer.capability
            return (signed_offer,)

        async def request_quote(self, request: QuoteRequestV2) -> BoundedQuote:
            base = await super().request_quote(request)
            changed = base.model_copy(
                update={
                    "offer_id": signed_offer.offer_id,
                    "billing_trigger": signed_offer.billing_trigger,
                    "failure_charge_policy": signed_offer.failure_charge_policy,
                    "retry_charge_policy": signed_offer.retry_charge_policy,
                    "fixed_attempt_fee": CurrencyAmount(
                        amount="0.0005", currency="USD"
                    ),
                    "signature": UNSIGNED,
                }
            )
            return changed.model_copy(
                update={"signature": signer.sign(canonical_payload(changed))}
            )

    provider = FeeTamperingProvider(signer, clock)
    router = _router(_manifest(route), provider, signer, clock)
    try:
        prepared = await router.prepare_route(_request())
        assert not prepared.feasible
        assert prepared.quote_ids == ()
        assert router.store.list_bounded_quotes() == []
        assert any(
            failure.executor_id == route.id and failure.code == "BINDING"
            for failure in prepared.quote_failures
        )
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_persisted_quote_input_contains_only_approved_disclosure() -> None:
    clock = MutableClock()
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="provider-key")
    provider = SignedQuoteProvider(signer, clock)
    disclosure: list[dict[str, object]] = [
        {"source": "action_features.input_bytes", "name": "input_bytes"},
        {
            "source": "action_input.page_count",
            "name": "page_count",
            "type": "integer",
            "maximum": 100,
        },
    ]
    router = _router(
        _manifest(
            _route(
                "remote.dynamic",
                latency_ms=1,
                cash="0.001",
                provider=True,
                disclosure=disclosure,
            )
        ),
        provider,
        signer,
        clock,
    )
    secret_text = "PRIVATE RESUME BODY 4de4e755"
    secret_token = "access-token-e55c1d"
    try:
        prepared = await router.prepare_route(
            _request(
                input={
                    "text": secret_text,
                    "page_count": 7,
                    "access_token": secret_token,
                }
            )
        )
        assert prepared.feasible
        assert len(provider.requests) == 1
        disclosed = provider.requests[0].disclosed_quote_features
        assert disclosed["page_count"] == 7
        assert isinstance(disclosed["input_bytes"], int)
        assert set(disclosed) == {"input_bytes", "page_count"}
        stored = router.store.list_quote_requests_v2(action_id="action-1")
        assert len(stored) == 1
        assert stored[0].disclosed_quote_features == disclosed
        payloads = " ".join(
            row[0]
            for table in ("quote_requests_v2", "prepared_route_decisions")
            for row in router.store._connection.execute(f"SELECT payload_json FROM {table}")
        )
        assert secret_text not in payloads
        assert secret_token not in payloads
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_prepared_decision_expires_and_can_be_cancelled() -> None:
    clock = MutableClock()
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="provider-key")
    provider = SignedQuoteProvider(signer, clock)
    router = _router(
        _manifest(_route("local.free", latency_ms=1, cash="0")),
        provider,
        signer,
        clock,
    )
    try:
        expiring = await router.prepare_route(_request(action_id="action-expiring"))
        assert expiring.can_transition_to(PreparedDecisionState.INVOKING)
        clock.now = expiring.expires_at + timedelta(microseconds=1)
        assert router.get_prepared_decision(expiring.prepared_id).state is PreparedDecisionState.EXPIRED

        clock.now = NOW
        cancellable = await router.prepare_route(_request(action_id="action-cancellable"))
        cancelled = await router.cancel_prepared(cancellable.prepared_id)
        assert cancelled.state is PreparedDecisionState.CANCELLED
        assert router.get_prepared_decision(cancellable.prepared_id).state is PreparedDecisionState.CANCELLED
    finally:
        await router.close()


def test_action_digest_binds_relevant_data_context() -> None:
    internal = _request(
        context=ActionContext(
            data_sensitivity=DataSensitivity.INTERNAL,
            preferred_region="CA",
        )
    )
    restricted = internal.model_copy(
        update={
            "context": ActionContext(
                data_sensitivity=DataSensitivity.RESTRICTED,
                preferred_region="CA",
            )
        }
    )
    assert action_digest(internal) != action_digest(restricted)


@pytest.mark.asyncio
async def test_caller_cannot_enable_static_prior_fallback() -> None:
    clock = MutableClock()
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="provider-key")
    provider = SignedQuoteProvider(signer, clock, failing={"remote.dynamic"})
    router = _router(
        _manifest(_route("remote.dynamic", latency_ms=1, cash="0.001", provider=True)),
        provider,
        signer,
        clock,
    )
    try:
        with pytest.raises(ConfigurationError, match="cannot weaken"):
            await router.prepare_route(
                _request(),
                quote_policy=QuoteFailurePolicy.ALLOW_STATIC_PRIOR,
            )
        assert provider.calls == []
    finally:
        await router.close()
