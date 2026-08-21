from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

import pytest

from aeep import EconomicProvider as PublicEconomicProvider
from aeep.economic.canonical import canonical_payload
from aeep.economic.signing import HMACSignerV1
from aeep.errors import ConfigurationError
from aeep.models import BoundedQuote, QuoteRequestV2, UsageStatement
from aeep.sdk import EconomicProvider, import_mcp, import_mcp_server

PROVIDER_ID = "provider.example"
CAPABILITY = "text.statistics@1"
EXECUTOR_ID = "provider.statistics"
FINGERPRINT = f"sha256:{'a' * 64}"
ACTION_DIGEST = f"sha256:{'b' * 64}"
TERMS_DIGEST = f"sha256:{'c' * 64}"
NOW = datetime(2026, 8, 14, 12, tzinfo=UTC)


def _provider() -> tuple[EconomicProvider, HMACSignerV1]:
    signer = HMACSignerV1(b"s" * 32, key_id="provider-key")
    return EconomicProvider(PROVIDER_ID, signer), signer


def test_economic_provider_is_exported_from_package_root() -> None:
    assert PublicEconomicProvider is EconomicProvider


def _offer(**updates: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "offer_id": "offer-1",
        "provider_id": PROVIDER_ID,
        "capability": CAPABILITY,
        "executor_id": EXECUTOR_ID,
        "executor_fingerprint": FINGERPRINT,
        "pricing_rules": [
            {
                "rule_id": "request-fee",
                "fixed_amount": {"amount": "0.001", "currency": "USD"},
            }
        ],
        "billing_trigger": "ON_SUCCESS",
        "failure_charge_policy": "NO_CHARGE",
        "retry_charge_policy": "EACH_ATTEMPT",
        "settlement_currency": "USD",
        "valid_from": NOW - timedelta(hours=1),
        "valid_until": NOW + timedelta(days=1),
        "terms_digest": TERMS_DIGEST,
        "issued_at": NOW - timedelta(hours=1),
    }
    value.update(updates)
    return value


def _request(**updates: Any) -> QuoteRequestV2:
    value: dict[str, Any] = {
        "quote_request_id": "request-1",
        "action_id": "action-1",
        "capability": CAPABILITY,
        "executor_id": EXECUTOR_ID,
        "executor_fingerprint": FINGERPRINT,
        "action_digest": ACTION_DIGEST,
        "input_features": {
            "input_bytes": 1024,
            "input_items": 1,
            "text_characters": 1000,
            "max_depth": 1,
            "size_bucket": "2^10",
        },
        "disclosed_quote_features": {"input_bytes": 1024},
        "desired_currency": "USD",
        "maximum_acceptable_amount": {"amount": "0.006", "currency": "USD"},
        "nonce": "nonce-123456",
        "created_at": NOW,
        "expires_at": NOW + timedelta(minutes=2),
    }
    value.update(updates)
    return QuoteRequestV2.model_validate(value)


def _quote(request: QuoteRequestV2, **updates: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "quote_id": f"quote-{request.quote_request_id}",
        "quote_request_id": request.quote_request_id,
        "offer_id": "offer-1",
        "provider_id": PROVIDER_ID,
        "capability": request.capability,
        "executor_id": request.executor_id,
        "executor_fingerprint": request.executor_fingerprint,
        "action_digest": request.action_digest,
        "nonce": request.nonce,
        "expected_amount": {"amount": "0.0038", "currency": "USD"},
        "maximum_amount": {"amount": "0.0050", "currency": "USD"},
        "estimated_meters": [
            {"meter": "input_tokens", "unit": "token", "quantity": "1000"}
        ],
        "billing_trigger": "ON_SUCCESS",
        "failure_charge_policy": "NO_CHARGE",
        "retry_charge_policy": "EACH_ATTEMPT",
        "terms_digest": TERMS_DIGEST,
        "issued_at": NOW,
        "expires_at": NOW + timedelta(minutes=1),
    }
    value.update(updates)
    return value


def _usage(
    request: QuoteRequestV2,
    quote: BoundedQuote,
    bound_prepared_id: str,
    bound_attempt_id: str,
    **updates: Any,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "usage_statement_id": f"usage-{bound_attempt_id}",
        "quote_id": quote.quote_id,
        "prepared_id": bound_prepared_id,
        "action_id": request.action_id,
        "attempt_id": bound_attempt_id,
        "provider_id": PROVIDER_ID,
        "executor_id": quote.executor_id,
        "executor_fingerprint": quote.executor_fingerprint,
        "execution_status": "SUCCESS",
        "meters": [{"meter": "input_tokens", "unit": "token", "quantity": "950"}],
        "provider_calculated_amount": {"amount": "0.0038", "currency": "USD"},
        "started_at": NOW,
        "completed_at": NOW + timedelta(seconds=1),
        "issued_at": NOW + timedelta(seconds=1),
    }
    value.update(updates)
    return value


def _register_offer(provider: EconomicProvider) -> None:
    provider.register_offer(_offer())


def test_signed_offer_registration_is_idempotent_and_conflict_safe() -> None:
    provider, signer = _provider()
    signed = provider.sign_offer(_offer())

    assert signer.verify(canonical_payload(signed), signed.signature)
    assert provider.register_offer(signed) is signed
    assert provider.register_offer(signed) is signed
    assert provider.get_offers(CAPABILITY, [EXECUTOR_ID]) == (signed,)
    assert provider.get_offers("other.capability@1") == ()

    with pytest.raises(ConfigurationError, match="different content"):
        provider.register_offer(_offer(terms_digest=f"sha256:{'d' * 64}"))

    foreign = EconomicProvider(
        PROVIDER_ID,
        HMACSignerV1(b"x" * 32, key_id="other-key"),
    ).sign_offer(_offer(offer_id="offer-foreign"))
    with pytest.raises(ConfigurationError, match="configured signer"):
        provider.register_offer(foreign)


@pytest.mark.asyncio
async def test_sync_quote_and_async_usage_handlers_are_bound_signed_and_idempotent() -> None:
    provider, signer = _provider()
    _register_offer(provider)
    quote_calls = 0
    usage_calls = 0

    def quote_handler(request: QuoteRequestV2) -> dict[str, Any]:
        nonlocal quote_calls
        quote_calls += 1
        return _quote(request)

    async def usage_handler(
        request: QuoteRequestV2,
        quote: BoundedQuote,
        prepared_id: str,
        attempt_id: str,
    ) -> dict[str, Any]:
        nonlocal usage_calls
        usage_calls += 1
        return _usage(request, quote, prepared_id, attempt_id)

    provider.register_quote_handler(CAPABILITY, EXECUTOR_ID, FINGERPRINT, quote_handler)
    provider.register_quote_handler(CAPABILITY, EXECUTOR_ID, FINGERPRINT, quote_handler)
    provider.register_usage_handler(CAPABILITY, EXECUTOR_ID, FINGERPRINT, usage_handler)
    provider.register_usage_handler(CAPABILITY, EXECUTOR_ID, FINGERPRINT, usage_handler)

    request = _request()
    quote = await provider.process_quote(request)
    assert await provider.process_quote(request) is quote
    assert quote_calls == 1
    assert quote.action_digest == request.action_digest
    assert quote.nonce == request.nonce
    assert signer.verify(canonical_payload(quote), quote.signature)

    usage = await provider.process_usage(
        quote.quote_id,
        prepared_id="prepared-1",
        attempt_id="attempt-1",
    )
    assert (
        await provider.process_usage(
            quote.quote_id,
            prepared_id="prepared-1",
            attempt_id="attempt-1",
        )
        is usage
    )
    assert usage_calls == 1
    assert usage.action_id == request.action_id
    assert usage.prepared_id == "prepared-1"
    assert usage.attempt_id == "attempt-1"
    assert signer.verify(canonical_payload(usage), usage.signature)


@pytest.mark.asyncio
async def test_async_quote_and_sync_usage_handlers_are_supported() -> None:
    provider, _ = _provider()
    _register_offer(provider)

    async def quote_handler(request: QuoteRequestV2) -> dict[str, Any]:
        return _quote(request)

    def usage_handler(
        request: QuoteRequestV2,
        quote: BoundedQuote,
        prepared_id: str,
        attempt_id: str,
    ) -> dict[str, Any]:
        return _usage(request, quote, prepared_id, attempt_id)

    provider.register_quote_handler(CAPABILITY, EXECUTOR_ID, FINGERPRINT, quote_handler)
    provider.register_usage_handler(CAPABILITY, EXECUTOR_ID, FINGERPRINT, usage_handler)
    quote = await provider.process_quote(_request())

    assert isinstance(
        await provider.process_usage(
            quote.quote_id,
            prepared_id="prepared-1",
            attempt_id="attempt-1",
        ),
        UsageStatement,
    )


@pytest.mark.asyncio
async def test_usage_handler_must_explicitly_report_execution_evidence() -> None:
    provider, _ = _provider()
    _register_offer(provider)

    def quote_handler(request: QuoteRequestV2) -> dict[str, Any]:
        return _quote(request)

    def incomplete_usage_handler(
        request: QuoteRequestV2,
        quote: BoundedQuote,
        prepared_id: str,
        attempt_id: str,
    ) -> dict[str, Any]:
        value = _usage(request, quote, prepared_id, attempt_id)
        value.pop("meters")
        return value

    provider.register_quote_handler(CAPABILITY, EXECUTOR_ID, FINGERPRINT, quote_handler)
    provider.register_usage_handler(
        CAPABILITY,
        EXECUTOR_ID,
        FINGERPRINT,
        incomplete_usage_handler,
    )
    quote = await provider.process_quote(_request())

    with pytest.raises(ConfigurationError, match="explicitly provide"):
        await provider.process_usage(
            quote.quote_id,
            prepared_id="prepared-1",
            attempt_id="attempt-1",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("provider_id", "provider.other"),
        ("quote_request_id", "request-other"),
        ("capability", "other.statistics@1"),
        ("executor_id", "provider.other"),
        ("executor_fingerprint", f"sha256:{'d' * 64}"),
        ("action_digest", f"sha256:{'e' * 64}"),
        ("nonce", "nonce-other"),
    ],
)
async def test_quote_binding_mismatches_fail_closed(field: str, replacement: str) -> None:
    provider, _ = _provider()
    _register_offer(provider)

    def handler(request: QuoteRequestV2) -> dict[str, Any]:
        return _quote(request, **{field: replacement})

    provider.register_quote_handler(CAPABILITY, EXECUTOR_ID, FINGERPRINT, handler)
    with pytest.raises(ConfigurationError):
        await provider.process_quote(_request())


@pytest.mark.asyncio
async def test_quote_fixed_attempt_fee_must_match_referenced_offer() -> None:
    provider, _ = _provider()
    provider.register_offer(
        _offer(
            failure_charge_policy="CHARGE_FIXED_ATTEMPT_FEE",
            fixed_attempt_fee={"amount": "0.0004", "currency": "USD"},
        )
    )

    def handler(request: QuoteRequestV2) -> dict[str, Any]:
        return _quote(
            request,
            failure_charge_policy="CHARGE_FIXED_ATTEMPT_FEE",
            fixed_attempt_fee={"amount": "0.0005", "currency": "USD"},
        )

    provider.register_quote_handler(CAPABILITY, EXECUTOR_ID, FINGERPRINT, handler)
    with pytest.raises(ConfigurationError, match="fixed attempt fee"):
        await provider.process_quote(_request())


@pytest.mark.asyncio
async def test_request_action_binding_and_unknown_routes_fail_closed() -> None:
    provider, _ = _provider()
    _register_offer(provider)

    def handler(request: QuoteRequestV2) -> dict[str, Any]:
        return _quote(request)

    provider.register_quote_handler(CAPABILITY, EXECUTOR_ID, FINGERPRINT, handler)
    request = _request()
    await provider.process_quote(request)

    with pytest.raises(ConfigurationError, match="request ID"):
        await provider.process_quote(request.model_copy(update={"action_id": "action-other"}))
    with pytest.raises(ConfigurationError, match="exact route"):
        await provider.process_quote(
            _request(
                quote_request_id="request-other",
                executor_id="provider.unknown",
            )
        )
    with pytest.raises(ConfigurationError, match="registered offer"):
        provider.register_usage_handler(
            CAPABILITY,
            "provider.unknown",
            FINGERPRINT,
            lambda *_args: {},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("provider_id", "provider.other"),
        ("quote_id", "quote-other"),
        ("prepared_id", "prepared-other"),
        ("action_id", "action-other"),
        ("attempt_id", "attempt-other"),
        ("executor_id", "provider.other"),
        ("executor_fingerprint", f"sha256:{'d' * 64}"),
    ],
)
async def test_usage_binding_mismatches_fail_closed(field: str, replacement: str) -> None:
    provider, _ = _provider()
    _register_offer(provider)

    def quote_handler(request: QuoteRequestV2) -> dict[str, Any]:
        return _quote(request)

    def usage_handler(
        request: QuoteRequestV2,
        quote: BoundedQuote,
        prepared_id: str,
        attempt_id: str,
    ) -> dict[str, Any]:
        return _usage(request, quote, prepared_id, attempt_id, **{field: replacement})

    provider.register_quote_handler(CAPABILITY, EXECUTOR_ID, FINGERPRINT, quote_handler)
    provider.register_usage_handler(CAPABILITY, EXECUTOR_ID, FINGERPRINT, usage_handler)
    quote = await provider.process_quote(_request())

    with pytest.raises(ConfigurationError):
        await provider.process_usage(
            quote.quote_id,
            prepared_id="prepared-1",
            attempt_id="attempt-1",
        )


@pytest.mark.asyncio
async def test_altered_quote_and_usage_statement_id_reuse_is_rejected() -> None:
    provider, _ = _provider()
    _register_offer(provider)

    def quote_handler(request: QuoteRequestV2) -> dict[str, Any]:
        return _quote(request, quote_id="quote-shared")

    def usage_handler(
        request: QuoteRequestV2,
        quote: BoundedQuote,
        prepared_id: str,
        attempt_id: str,
    ) -> dict[str, Any]:
        return _usage(
            request,
            quote,
            prepared_id,
            attempt_id,
            usage_statement_id="usage-shared",
        )

    provider.register_quote_handler(CAPABILITY, EXECUTOR_ID, FINGERPRINT, quote_handler)
    provider.register_usage_handler(CAPABILITY, EXECUTOR_ID, FINGERPRINT, usage_handler)
    first = await provider.process_quote(_request())
    with pytest.raises(ConfigurationError, match="quote ID"):
        await provider.process_quote(
            _request(
                quote_request_id="request-2",
                action_id="action-2",
                action_digest=f"sha256:{'f' * 64}",
                nonce="nonce-654321",
            )
        )

    await provider.process_usage(
        first.quote_id,
        prepared_id="prepared-1",
        attempt_id="attempt-1",
    )
    with pytest.raises(ConfigurationError, match="usage statement ID"):
        await provider.process_usage(
            first.quote_id,
            prepared_id="prepared-1",
            attempt_id="attempt-2",
        )

    with pytest.raises(ConfigurationError, match="unknown issued quote"):
        await provider.process_usage(
            "quote-unknown",
            prepared_id="prepared-1",
            attempt_id="attempt-1",
        )


@pytest.mark.parametrize(
    ("endpoint", "private_allowed"),
    [
        ("http://localhost:8000/mcp", True),
        ("http://127.0.0.1:8000/mcp", True),
        ("http://service.localhost:8000/mcp", True),
        ("https://example.com/mcp", False),
    ],
)
def test_import_mcp_persists_private_opt_in_only_for_reviewed_localhost(
    endpoint: str,
    private_allowed: bool,
) -> None:
    descriptor = import_mcp(
        provider_id="provider-mcp",
        capability_name="demo.echo@1",
        tool="echo",
        transport="http",
        endpoint=endpoint,
    )

    config = descriptor.executors[0].config
    assert config.get("allow_private_networks", False) is private_allowed
    assert config["allowed_hosts"] == [urlparse(endpoint).hostname]


@pytest.mark.parametrize("transport", ["bogus", "streamable_http", "streamable-http"])
def test_import_mcp_rejects_unknown_transport(transport: str) -> None:
    with pytest.raises(ConfigurationError, match="transport"):
        import_mcp(
            provider_id="provider-mcp",
            capability_name="demo.echo@1",
            tool="echo",
            transport=transport,
            endpoint="https://example.com/mcp",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "private_allowed"),
    [
        ("http://localhost:8000/mcp", True),
        ("https://example.com/mcp", False),
    ],
)
async def test_mcp_server_import_opts_in_only_reviewed_localhost_validation(
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
    private_allowed: bool,
) -> None:
    import aeep.sdk as sdk

    validated: list[dict[str, Any]] = []

    async def validate(_url: str, config: dict[str, Any], *, label: str) -> None:
        assert label == "MCP import"
        validated.append(config)

    class FakeClient:
        def __init__(self, **_kwargs: Any) -> None:
            self.kwargs = _kwargs

        async def list_tools(self) -> SimpleNamespace:
            return SimpleNamespace(
                result={"tools": [{"name": "echo", "inputSchema": {"type": "object"}}]}
            )

        async def close(self) -> None:
            return None

    monkeypatch.setattr(sdk, "validate_http_url", validate)
    monkeypatch.setattr(sdk, "MCPHTTPClient", FakeClient)

    descriptor = await import_mcp_server(
        provider_id="provider-mcp",
        transport="http",
        endpoint=endpoint,
        capability_prefix="demo",
    )

    assert validated[0].get("allow_private_networks", False) is private_allowed
    assert (
        descriptor.executors[0].config.get("allow_private_networks", False)
        is private_allowed
    )
