from __future__ import annotations

import asyncio
import ipaddress
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

import aeep.economic as economic_api
from aeep.economic.canonical import canonical_payload
from aeep.economic.disclosure import (
    DisclosureValueType,
    QuoteDisclosureField,
    QuoteDisclosurePolicy,
)
from aeep.economic.quotes import (
    CompositeQuoteProvider,
    QuoteCandidate,
    QuoteErrorCode,
    QuoteProviderError,
    RemoteQuoteProvider,
    RemoteQuoteProviderConfig,
    StaticQuoteProvider,
    acquire_top_k_quotes,
)
from aeep.economic.signing import Ed25519Signer
from aeep.economic.trust import TrustedProviderKey, TrustStore, TrustStoreVerifier
from aeep.errors import ConfigurationError
from aeep.executors import network
from aeep.models import (
    ActionFeatures,
    BillingTrigger,
    BoundedQuote,
    CapabilityOffer,
    CashEstimate,
    CurrencyAmount,
    EconomicEvidenceLevel,
    EvidenceSource,
    EvidenceStatus,
    ExecutorKind,
    ExecutorSpec,
    FailureChargePolicy,
    MeasurementEvidence,
    PricingRule,
    QuoteRequestV2,
    RetryChargePolicy,
    RouteEstimate,
    SignatureAlgorithm,
    SignatureEnvelopeV2,
    TrustLevel,
)

NOW = datetime(2026, 8, 14, 12, tzinfo=UTC)
PROVIDER = "provider.example"
CAPABILITY = "text.statistics@1"
EXECUTOR = "provider.example.statistics"
FINGERPRINT = f"sha256:{'1' * 64}"
ACTION_DIGEST = f"sha256:{'2' * 64}"
TERMS_DIGEST = f"sha256:{'3' * 64}"
HOST = "quotes.example"
ENDPOINT = f"https://{HOST}/v1/quotes"
OFFERS_ENDPOINT = f"https://{HOST}/v1/offers"
DUMMY_SIGNATURE = SignatureEnvelopeV2(
    algorithm=SignatureAlgorithm.ED25519,
    key_id="key-1",
    value="AA",
)
INPUT_BYTES_DISCLOSURE = QuoteDisclosurePolicy(
    fields=(
        QuoteDisclosureField(
            source="action_features.input_bytes",
            name="input_bytes",
        ),
    )
)
DISCLOSURE_POLICIES = {EXECUTOR: INPUT_BYTES_DISCLOSURE}


def test_quote_and_disclosure_api_is_exported() -> None:
    assert economic_api.RemoteQuoteProvider is RemoteQuoteProvider
    assert economic_api.StaticQuoteProvider is StaticQuoteProvider
    assert economic_api.disclose_quote_features is not None


def request(*, executor_id: str = EXECUTOR, nonce: str = "nonce-12345678") -> QuoteRequestV2:
    return QuoteRequestV2(
        quote_request_id=f"request-{executor_id.replace('.', '-')}",
        action_id="action-1",
        capability=CAPABILITY,
        executor_id=executor_id,
        executor_fingerprint=FINGERPRINT,
        action_digest=ACTION_DIGEST,
        input_features=ActionFeatures(
            input_bytes=14_336,
            input_items=1,
            text_characters=14_000,
            max_depth=2,
            size_bucket="2^14",
        ),
        disclosed_quote_features={"input_bytes": 14_336},
        desired_currency="USD",
        maximum_acceptable_amount=CurrencyAmount(amount="0.0100", currency="USD"),
        nonce=nonce,
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=1),
    )


def signed_quote(
    signer: Ed25519Signer,
    quote_request: QuoteRequestV2,
    **updates: object,
) -> BoundedQuote:
    quote = BoundedQuote(
        quote_id=(
            f"quote-{quote_request.executor_id.replace('.', '-')}-{quote_request.nonce}"
        ),
        quote_request_id=quote_request.quote_request_id,
        provider_id=PROVIDER,
        capability=quote_request.capability,
        executor_id=quote_request.executor_id,
        executor_fingerprint=quote_request.executor_fingerprint,
        action_digest=quote_request.action_digest,
        nonce=quote_request.nonce,
        expected_amount=CurrencyAmount(amount="0.0038", currency="USD"),
        maximum_amount=CurrencyAmount(amount="0.0050", currency="USD"),
        billing_trigger=BillingTrigger.ON_SUCCESS,
        failure_charge_policy=FailureChargePolicy.NO_CHARGE,
        retry_charge_policy=RetryChargePolicy.EACH_ATTEMPT,
        terms_digest=TERMS_DIGEST,
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=2),
        signature=DUMMY_SIGNATURE,
    ).model_copy(update=updates)
    return quote.model_copy(update={"signature": signer.sign(canonical_payload(quote))})


def signed_offer(signer: Ed25519Signer) -> CapabilityOffer:
    offer = CapabilityOffer(
        offer_id="offer-1",
        provider_id=PROVIDER,
        capability=CAPABILITY,
        executor_id=EXECUTOR,
        executor_fingerprint=FINGERPRINT,
        pricing_rules=(
            PricingRule(
                rule_id="fixed",
                fixed_amount=CurrencyAmount(amount="0.0010", currency="USD"),
            ),
        ),
        billing_trigger=BillingTrigger.ON_SUCCESS,
        failure_charge_policy=FailureChargePolicy.NO_CHARGE,
        retry_charge_policy=RetryChargePolicy.EACH_ATTEMPT,
        settlement_currency="USD",
        valid_from=NOW - timedelta(minutes=1),
        valid_until=NOW + timedelta(hours=1),
        terms_digest=TERMS_DIGEST,
        issued_at=NOW,
        signature=DUMMY_SIGNATURE,
    )
    return offer.model_copy(update={"signature": signer.sign(canonical_payload(offer))})


def verifier(signer: Ed25519Signer) -> TrustStoreVerifier:
    key = TrustedProviderKey(
        provider_id=PROVIDER,
        key_id=signer.key_id,
        public_key=signer.public_key_base64url(),
        valid_from=NOW - timedelta(days=1),
        valid_until=NOW + timedelta(days=1),
        allowed_capabilities=(CAPABILITY,),
        allowed_quote_hosts=(HOST,),
    )
    return TrustStoreVerifier(TrustStore([key]), clock=lambda: NOW)


@pytest.fixture
def public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    async def resolve(_hostname: str) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        return {ipaddress.ip_address("93.184.216.34")}

    monkeypatch.setattr(network, "resolved_addresses", resolve)


def remote_config(**updates: object) -> RemoteQuoteProviderConfig:
    values: dict[str, object] = {
        "provider_id": PROVIDER,
        "quote_endpoint": ENDPOINT,
        "offers_endpoint": OFFERS_ENDPOINT,
        "allowed_hosts": (HOST,),
    }
    values.update(updates)
    return RemoteQuoteProviderConfig(**values)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_remote_quote_is_bounded_signed_bound_and_replay_protected(public_dns: None) -> None:
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    seen: dict[str, object] = {}

    def handle(http_request: httpx.Request) -> httpx.Response:
        payload = json.loads(http_request.content)
        seen.update(payload)
        quote = signed_quote(signer, QuoteRequestV2.model_validate(payload))
        return httpx.Response(200, json=quote.model_dump(mode="json"))

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handle),
        follow_redirects=False,
        trust_env=False,
    )
    provider = RemoteQuoteProvider(
        remote_config(),
        verifier(signer),
        client=client,
        clock=lambda: NOW,
        disclosure_policies=DISCLOSURE_POLICIES,
    )
    try:
        quote = await provider.request_quote(request())
        assert quote.maximum_amount.amount == Decimal("0.0050")
        assert quote.evidence_level is EconomicEvidenceLevel.SIGNED_QUOTE
        assert seen["disclosed_quote_features"] == {"input_bytes": 14_336}
        assert "resume" not in str(seen)

        with pytest.raises(QuoteProviderError) as replay:
            await provider.request_quote(request())
        assert replay.value.quote_code is QuoteErrorCode.REPLAY
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_remote_offer_requires_signature_and_exact_binding(public_dns: None) -> None:
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    offer = signed_offer(signer)

    def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"offers": [offer.model_dump(mode="json")]})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handle),
        follow_redirects=False,
        trust_env=False,
    )
    provider = RemoteQuoteProvider(
        remote_config(),
        verifier(signer),
        client=client,
        clock=lambda: NOW,
        disclosure_policies=DISCLOSURE_POLICIES,
    )
    try:
        assert await provider.get_offers(CAPABILITY, [EXECUTOR]) == (offer,)
        with pytest.raises(QuoteProviderError) as mismatch:
            await provider.get_offers("document.extract@1", [EXECUTOR])
        assert mismatch.value.quote_code is QuoteErrorCode.BINDING
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["maximum_amount", "action_digest", "executor_fingerprint"])
async def test_quote_tampering_is_rejected(public_dns: None, field: str) -> None:
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    quote_request = request()
    signed = signed_quote(signer, quote_request)
    payload = signed.model_dump(mode="json")
    replacements: dict[str, object] = {
        "maximum_amount": {"amount": "0.0060", "currency": "USD"},
        "action_digest": f"sha256:{'a' * 64}",
        "executor_fingerprint": f"sha256:{'b' * 64}",
    }
    payload[field] = replacements[field]

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=payload)),
        follow_redirects=False,
        trust_env=False,
    )
    provider = RemoteQuoteProvider(
        remote_config(),
        verifier(signer),
        client=client,
        clock=lambda: NOW,
        disclosure_policies=DISCLOSURE_POLICIES,
    )
    try:
        with pytest.raises(QuoteProviderError) as rejected:
            await provider.request_quote(quote_request)
        assert rejected.value.quote_code is QuoteErrorCode.SIGNATURE
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_validly_signed_wrong_binding_is_rejected(public_dns: None) -> None:
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    quote_request = request()
    wrong = signed_quote(
        signer,
        quote_request,
        action_digest=f"sha256:{'a' * 64}",
    )
    # model_copy does not revalidate; sign the changed content explicitly.
    wrong = wrong.model_copy(update={"signature": signer.sign(canonical_payload(wrong))})
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json=wrong.model_dump(mode="json"))
        ),
        follow_redirects=False,
        trust_env=False,
    )
    provider = RemoteQuoteProvider(
        remote_config(),
        verifier(signer),
        client=client,
        clock=lambda: NOW,
        disclosure_policies=DISCLOSURE_POLICIES,
    )
    try:
        with pytest.raises(QuoteProviderError) as rejected:
            await provider.request_quote(quote_request)
        assert rejected.value.quote_code is QuoteErrorCode.BINDING
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.Response(200, text="{}", headers={"content-type": "text/plain"}), QuoteErrorCode.CONTENT_TYPE),
        (
            httpx.Response(
                200,
                content=b"{}",
                headers={"content-type": "application/json; charset=iso-8859-1"},
            ),
            QuoteErrorCode.CONTENT_TYPE,
        ),
        (httpx.Response(200, content=b"x" * 2048, headers={"content-type": "application/json"}), QuoteErrorCode.RESPONSE_TOO_LARGE),
        (httpx.Response(503, text="provider secret"), QuoteErrorCode.HTTP_STATUS),
    ],
)
async def test_remote_quote_wire_failures_are_bounded_and_sanitized(
    public_dns: None,
    response: httpx.Response,
    code: QuoteErrorCode,
) -> None:
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: response),
        follow_redirects=False,
        trust_env=False,
    )
    provider = RemoteQuoteProvider(
        remote_config(maximum_response_bytes=1024),
        verifier(signer),
        client=client,
        headers={"Authorization": "Bearer never-print-this"},
        clock=lambda: NOW,
        disclosure_policies=DISCLOSURE_POLICIES,
    )
    try:
        with pytest.raises(QuoteProviderError) as rejected:
            await provider.request_quote(request())
        assert rejected.value.quote_code is code
        assert "never-print-this" not in str(rejected.value)
        assert "provider secret" not in str(rejected.value)
        assert ENDPOINT not in str(rejected.value)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_remote_quote_rejects_unsafe_injected_http_client() -> None:
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: None))
    try:
        with pytest.raises(ConfigurationError, match="redirects and environment proxies"):
            RemoteQuoteProvider(remote_config(), verifier(signer), client=client)
    finally:
        await client.aclose()


def test_remote_quote_config_requires_exact_allowlisted_https_endpoint() -> None:
    with pytest.raises(ConfigurationError, match="allowlisted"):
        remote_config(quote_endpoint="https://evil.example/v1/quotes")
    with pytest.raises(ConfigurationError, match="HTTPS"):
        remote_config(quote_endpoint=f"http://{HOST}/v1/quotes")
    with pytest.raises(ConfigurationError, match="query strings"):
        remote_config(quote_endpoint=f"{ENDPOINT}?token=not-allowed")
    with pytest.raises(ConfigurationError, match="fragments"):
        remote_config(quote_endpoint=f"{ENDPOINT}#credentials")


@pytest.mark.asyncio
async def test_quote_request_size_is_checked_before_network(public_dns: None) -> None:
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    names = tuple(f"metric_{index}_{'x' * 60}" for index in range(16))
    large_disclosure = {name: index for index, name in enumerate(names)}
    large_policy = QuoteDisclosurePolicy(
        fields=tuple(
            QuoteDisclosureField(
                source=f"action_input.count_{index}",
                name=name,
                type=DisclosureValueType.INTEGER,
            )
            for index, name in enumerate(names)
        )
    )
    quote_request = QuoteRequestV2.model_validate(
        {
            **request().model_dump(mode="python"),
            "disclosed_quote_features": large_disclosure,
        }
    )
    called = False

    def handle(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handle),
        follow_redirects=False,
        trust_env=False,
    )
    provider = RemoteQuoteProvider(
        remote_config(maximum_request_bytes=1024),
        verifier(signer),
        client=client,
        clock=lambda: NOW,
        disclosure_policies={EXECUTOR: large_policy},
    )
    try:
        with pytest.raises(QuoteProviderError) as rejected:
            await provider.request_quote(quote_request)
        assert rejected.value.quote_code is QuoteErrorCode.REQUEST_TOO_LARGE
        assert not called
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("features", "policy", "raw_value"),
    [
        ({"page_count": 14}, None, None),
        ({"resume_text": "private resume contents"}, INPUT_BYTES_DISCLOSURE, "private resume contents"),
        ({"input_bytes": "private resume contents"}, INPUT_BYTES_DISCLOSURE, "private resume contents"),
        (
            {"category": "user@example.com"},
            QuoteDisclosurePolicy(
                fields=(
                    QuoteDisclosureField(
                        source="action_input.category",
                        name="category",
                        type=DisclosureValueType.ENUM,
                        allowed_values=("short", "long"),
                    ),
                )
            ),
            "user@example.com",
        ),
    ],
)
async def test_remote_client_revalidates_disclosure_before_network(
    features: dict[str, object],
    policy: QuoteDisclosurePolicy | None,
    raw_value: str | None,
) -> None:
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    quote_request = QuoteRequestV2.model_validate(
        {
            **request().model_dump(mode="python"),
            "disclosed_quote_features": features,
        }
    )
    called = False

    def handle(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handle),
        follow_redirects=False,
        trust_env=False,
    )
    provider = RemoteQuoteProvider(
        remote_config(),
        verifier(signer),
        client=client,
        clock=lambda: NOW,
        disclosure_policies={EXECUTOR: policy} if policy is not None else None,
    )
    try:
        with pytest.raises(QuoteProviderError) as rejected:
            await provider.request_quote(quote_request)
        assert rejected.value.quote_code is QuoteErrorCode.CONFIGURATION
        if raw_value is not None:
            assert raw_value not in str(rejected.value)
        assert not called
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_redirects_are_not_followed(public_dns: None) -> None:
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    calls = 0

    def handle(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest"})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handle),
        follow_redirects=False,
        trust_env=False,
    )
    provider = RemoteQuoteProvider(
        remote_config(),
        verifier(signer),
        client=client,
        clock=lambda: NOW,
        disclosure_policies=DISCLOSURE_POLICIES,
    )
    try:
        with pytest.raises(QuoteProviderError) as rejected:
            await provider.request_quote(request())
        assert rejected.value.quote_code is QuoteErrorCode.HTTP_STATUS
        assert calls == 1
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_dns_policy_is_revalidated_for_each_quote_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolutions = 0

    async def resolve(_hostname: str) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        nonlocal resolutions
        resolutions += 1
        return {ipaddress.ip_address("93.184.216.34")}

    monkeypatch.setattr(network, "resolved_addresses", resolve)
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")

    def handle(http_request: httpx.Request) -> httpx.Response:
        quote_request = QuoteRequestV2.model_validate_json(http_request.content)
        return httpx.Response(
            200,
            json=signed_quote(signer, quote_request).model_dump(mode="json"),
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handle),
        follow_redirects=False,
        trust_env=False,
    )
    provider = RemoteQuoteProvider(
        remote_config(),
        verifier(signer),
        client=client,
        clock=lambda: NOW,
        disclosure_policies=DISCLOSURE_POLICIES,
    )
    try:
        await provider.request_quote(request(nonce="nonce-first-1234"))
        await provider.request_quote(request(nonce="nonce-second-123"))
        assert resolutions == 2
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_total_quote_deadline_includes_dns_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def slow_resolve(
        _hostname: str,
    ) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        await asyncio.sleep(1)
        return {ipaddress.ip_address("93.184.216.34")}

    monkeypatch.setattr(network, "resolved_addresses", slow_resolve)
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(500)),
        follow_redirects=False,
        trust_env=False,
    )
    provider = RemoteQuoteProvider(
        remote_config(
            per_provider_timeout_seconds=0.01,
            total_timeout_seconds=0.01,
        ),
        verifier(signer),
        client=client,
        clock=lambda: NOW,
        disclosure_policies=DISCLOSURE_POLICIES,
    )
    try:
        with pytest.raises(QuoteProviderError) as rejected:
            await provider.request_quote(request())
        assert rejected.value.quote_code is QuoteErrorCode.TIMEOUT
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_network_policy_blocks_non_global_and_requires_explicit_local_opt_in() -> None:
    for url_host, allowed_host in (
        ("10.0.0.1", "10.0.0.1"),
        ("169.254.169.254", "169.254.169.254"),
        ("100.100.100.200", "100.100.100.200"),
        ("[fec0::1]", "fec0::1"),
    ):
        with pytest.raises(ConfigurationError, match="private or non-public"):
            await network.validate_http_url(
                f"https://{url_host}/quote",
                {"allowed_hosts": [allowed_host]},
                label="quote",
            )

    with pytest.raises(ConfigurationError):
        await network.validate_http_url(
            "http://127.0.0.1/quote",
            {"allowed_hosts": ["127.0.0.1"]},
            label="quote",
        )
    await network.validate_http_url(
        "http://127.0.0.1/quote",
        {
            "allowed_hosts": ["127.0.0.1"],
            "allow_private_networks": True,
        },
        label="quote",
    )


def test_static_provider_never_turns_unknown_into_zero_or_binding() -> None:
    unknown = ExecutorSpec(
        id="unknown",
        capability=CAPABILITY,
        kind=ExecutorKind.PYTHON,
        description="unknown cost",
        config={"callable": "tests.fake:call"},
    )
    known_zero = unknown.model_copy(
        update={
            "id": "known-zero",
            "estimate": RouteEstimate(
                cash=CashEstimate(
                    amount_usd=Decimal(0),
                    upper_bound_usd=Decimal(0),
                    evidence=MeasurementEvidence(
                        status=EvidenceStatus.COMPLETE,
                        source=EvidenceSource.STATIC_ESTIMATE,
                        trust=TrustLevel.SELF_ASSERTED,
                    ),
                )
            ),
        }
    )
    provider = StaticQuoteProvider([unknown, known_zero])

    with pytest.raises(QuoteProviderError) as unavailable:
        provider.estimate("unknown")
    assert unavailable.value.quote_code is QuoteErrorCode.UNAVAILABLE

    estimate = provider.estimate("known-zero")
    assert estimate.expected_amount == CurrencyAmount(amount="0", currency="USD")
    assert estimate.evidence_level is EconomicEvidenceLevel.STATIC_PRIOR
    assert not estimate.binding


class FakeProvider:
    def __init__(
        self,
        quote: BoundedQuote,
        *,
        offers: tuple[CapabilityOffer, ...] = (),
        gate: asyncio.Event | None = None,
        calls: list[str] | None = None,
        offer_calls: list[tuple[str, ...]] | None = None,
        delay: float = 0,
    ) -> None:
        self.quote = quote
        self.offers = offers
        self.gate = gate
        self.calls = calls if calls is not None else []
        self.offer_calls = offer_calls if offer_calls is not None else []
        self.delay = delay

    async def get_offers(
        self, capability: str, executor_ids: list[str] | tuple[str, ...]
    ) -> tuple[CapabilityOffer, ...]:
        self.offer_calls.append(tuple(executor_ids))
        requested = set(executor_ids)
        return tuple(
            offer
            for offer in self.offers
            if offer.capability == capability and (not requested or offer.executor_id in requested)
        )

    async def request_quote(self, quote_request: QuoteRequestV2) -> BoundedQuote:
        self.calls.append(quote_request.executor_id)
        if self.gate is not None:
            if len(self.calls) >= 2:
                self.gate.set()
            await self.gate.wait()
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.quote


class UnfilteredOfferProvider(FakeProvider):
    async def get_offers(
        self, capability: str, executor_ids: list[str] | tuple[str, ...]
    ) -> tuple[CapabilityOffer, ...]:
        del capability
        self.offer_calls.append(tuple(executor_ids))
        return self.offers


@pytest.mark.asyncio
async def test_composite_retains_offer_and_quote_provenance() -> None:
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    quote_request = request()
    quote = signed_quote(signer, quote_request)
    offer = signed_offer(signer)
    composite = CompositeQuoteProvider({"remote": FakeProvider(quote, offers=(offer,))})

    assert await composite.get_offers(CAPABILITY, [EXECUTOR]) == (offer,)
    assert composite.offer_provenance(offer.offer_id) == "remote"
    assert await composite.request_quote(quote_request) == quote
    assert composite.quote_provenance(quote.quote_id) == "remote"


@pytest.mark.asyncio
async def test_composite_routes_no_offer_quote_to_only_configured_source() -> None:
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    first_request = request(
        executor_id="provider.example.first",
        nonce="nonce-first-12345678",
    )
    second_request = request(
        executor_id="provider.example.second",
        nonce="nonce-second-12345678",
    )
    first = FakeProvider(signed_quote(signer, first_request))
    second = FakeProvider(signed_quote(signer, second_request))
    composite = CompositeQuoteProvider(
        {"first-source": first, "second-source": second},
        executor_sources={
            first_request.executor_id: "first-source",
            second_request.executor_id: "second-source",
        },
    )

    assert await composite.get_offers(CAPABILITY, [first_request.executor_id]) == ()
    assert first.offer_calls == [(first_request.executor_id,)]
    assert second.offer_calls == []
    assert await composite.request_quote(first_request) == first.quote
    assert first.calls == [first_request.executor_id]
    assert second.calls == []


def test_multisource_composite_requires_exact_executor_mapping() -> None:
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    quote_request = request()
    provider = FakeProvider(signed_quote(signer, quote_request))

    with pytest.raises(ConfigurationError, match="exact executor-to-source"):
        CompositeQuoteProvider({"first": provider, "second": provider})


@pytest.mark.asyncio
async def test_composite_rejects_wrong_capability_offer_and_ignores_unmapped_executor() -> None:
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    mapped_request = request()
    unmapped_request = request(
        executor_id="provider.example.unmapped",
        nonce="nonce-unmapped-12345678",
    )
    wrong_capability = signed_offer(signer).model_copy(
        update={"capability": "text.other@1"}
    )
    first = UnfilteredOfferProvider(
        signed_quote(signer, mapped_request),
        offers=(wrong_capability,),
    )
    second = FakeProvider(signed_quote(signer, unmapped_request))
    composite = CompositeQuoteProvider(
        {"first": first, "second": second},
        executor_sources={mapped_request.executor_id: "first"},
    )

    with pytest.raises(QuoteProviderError) as rejected:
        await composite.get_offers(CAPABILITY, [mapped_request.executor_id])
    assert rejected.value.quote_code is QuoteErrorCode.INVALID_RESPONSE

    assert await composite.get_offers(CAPABILITY, [unmapped_request.executor_id]) == ()
    assert second.offer_calls == []
    with pytest.raises(QuoteProviderError) as unavailable:
        await composite.request_quote(unmapped_request)
    assert unavailable.value.quote_code is QuoteErrorCode.UNAVAILABLE
    assert second.calls == []


@pytest.mark.asyncio
async def test_top_k_quote_acquisition_is_concurrent_and_bounded() -> None:
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    gate = asyncio.Event()
    calls: list[str] = []
    candidates: list[QuoteCandidate] = []
    for index in range(3):
        quote_request = request(
            executor_id=f"provider.example.executor-{index}",
            nonce=f"nonce-{index}-12345678",
        )
        provider = FakeProvider(
            signed_quote(signer, quote_request),
            gate=gate,
            calls=calls,
        )
        candidates.append(QuoteCandidate(PROVIDER, quote_request, provider))

    result = await acquire_top_k_quotes(candidates, top_k=2, total_timeout_seconds=1)

    assert len(result.quotes) == 2
    assert not result.failures
    assert calls == [
        "provider.example.executor-0",
        "provider.example.executor-1",
    ]


@pytest.mark.asyncio
async def test_total_quote_deadline_returns_failure_without_zero_cost() -> None:
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    quote_request = request()
    slow = FakeProvider(signed_quote(signer, quote_request), delay=1)

    result = await acquire_top_k_quotes(
        [QuoteCandidate(PROVIDER, quote_request, slow)],
        total_timeout_seconds=0.01,
    )

    assert result.quotes == ()
    assert result.failures[0].code is QuoteErrorCode.TOTAL_TIMEOUT


@pytest.mark.asyncio
async def test_empty_quote_shortlist_does_not_contact_any_provider() -> None:
    result = await acquire_top_k_quotes([])
    assert result.quotes == ()
    assert result.failures == ()
