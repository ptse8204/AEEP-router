"""Static and remote quote sources with bounded acquisition."""

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError

from ..errors import ConfigurationError, ExecutorError, ProtocolError
from ..executors.network import is_local_hostname, validate_http_url
from ..models import (
    BoundedQuote,
    CapabilityOffer,
    CurrencyAmount,
    EconomicEvidenceLevel,
    ExecutorSpec,
    QuoteRequestV2,
)
from .canonical import canonical_payload
from .disclosure import (
    QuoteDisclosureError,
    QuoteDisclosurePolicy,
    validate_disclosed_quote_features,
)
from .trust import TrustStoreVerifier


class QuoteErrorCode(StrEnum):
    CONFIGURATION = "CONFIGURATION"
    NETWORK_POLICY = "NETWORK_POLICY"
    NETWORK = "NETWORK"
    TIMEOUT = "TIMEOUT"
    TOTAL_TIMEOUT = "TOTAL_TIMEOUT"
    HTTP_STATUS = "HTTP_STATUS"
    REQUEST_TOO_LARGE = "REQUEST_TOO_LARGE"
    RESPONSE_TOO_LARGE = "RESPONSE_TOO_LARGE"
    CONTENT_TYPE = "CONTENT_TYPE"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    SIGNATURE = "SIGNATURE"
    BINDING = "BINDING"
    REPLAY = "REPLAY"
    UNAVAILABLE = "UNAVAILABLE"
    INTERNAL = "INTERNAL"


class QuoteProviderError(ProtocolError):
    """Sanitized, structured quote-provider failure."""

    def __init__(
        self,
        code: QuoteErrorCode,
        message: str,
        *,
        provider_id: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            data={
                "code": code.value,
                **({"provider_id": provider_id} if provider_id is not None else {}),
            },
        )
        self.quote_code = code
        self.provider_id = provider_id


class QuoteProvider(Protocol):
    async def get_offers(
        self,
        capability: str,
        executor_ids: Sequence[str],
    ) -> Sequence[CapabilityOffer]: ...

    async def request_quote(self, request: QuoteRequestV2) -> BoundedQuote: ...


@dataclass(frozen=True, slots=True)
class StaticQuoteEstimate:
    executor_id: str
    capability: str
    expected_amount: CurrencyAmount | None
    maximum_amount: CurrencyAmount | None
    evidence_level: EconomicEvidenceLevel = EconomicEvidenceLevel.STATIC_PRIOR
    binding: bool = False


class StaticQuoteProvider:
    """Expose existing static evidence without pretending it is a live quote."""

    def __init__(
        self,
        executors: Sequence[ExecutorSpec] = (),
        *,
        offers: Sequence[CapabilityOffer] = (),
    ) -> None:
        self._executors = {executor.id: executor for executor in executors}
        if len(self._executors) != len(executors):
            raise ConfigurationError("duplicate executor ID in static quote provider")
        self._offers = tuple(offers)

    async def get_offers(
        self,
        capability: str,
        executor_ids: Sequence[str],
    ) -> Sequence[CapabilityOffer]:
        requested = set(executor_ids)
        return tuple(
            offer
            for offer in self._offers
            if offer.capability == capability
            and (not requested or offer.executor_id in requested)
        )

    def estimate(
        self,
        executor_id: str,
        *,
        desired_currency: str = "USD",
    ) -> StaticQuoteEstimate:
        executor = self._executors.get(executor_id)
        if executor is None:
            raise QuoteProviderError(
                QuoteErrorCode.UNAVAILABLE,
                "static estimate is unavailable for this executor",
            )
        if desired_currency != "USD":
            raise QuoteProviderError(
                QuoteErrorCode.BINDING,
                "static estimate currency does not match requested currency",
                provider_id=executor.provider_id,
            )
        cash = executor.estimate.cash
        if cash.amount_usd is None and cash.upper_bound_usd is None:
            raise QuoteProviderError(
                QuoteErrorCode.UNAVAILABLE,
                "cash cost is unknown; no static estimate was produced",
                provider_id=executor.provider_id,
            )
        expected = (
            CurrencyAmount(amount=cash.amount_usd, currency="USD")
            if cash.amount_usd is not None
            else None
        )
        maximum = (
            CurrencyAmount(amount=cash.upper_bound_usd, currency="USD")
            if cash.upper_bound_usd is not None
            else None
        )
        return StaticQuoteEstimate(
            executor_id=executor.id,
            capability=executor.capability,
            expected_amount=expected,
            maximum_amount=maximum,
        )

    async def request_quote(self, request: QuoteRequestV2) -> BoundedQuote:
        raise QuoteProviderError(
            QuoteErrorCode.UNAVAILABLE,
            "a static prior is not a binding quote",
        )


# Compatibility-friendly name for callers that use this only as an offer source.
StaticOfferService = StaticQuoteProvider


@dataclass(frozen=True, slots=True)
class RemoteQuoteProviderConfig:
    provider_id: str
    quote_endpoint: str
    allowed_hosts: tuple[str, ...]
    offers_endpoint: str | None = None
    allow_private_networks: bool = False
    allow_insecure_http: bool = False
    per_provider_timeout_seconds: float = 2.0
    total_timeout_seconds: float = 4.0
    maximum_request_bytes: int = 262_144
    maximum_response_bytes: int = 262_144
    maximum_clock_skew_seconds: int = 30
    maximum_quote_ttl_seconds: int = 600

    def __post_init__(self) -> None:
        if not self.provider_id:
            raise ConfigurationError("remote quote provider_id is required")
        if not self.allowed_hosts or any(
            not host
            or host != host.strip()
            or any(token in host for token in ("://", "/", "@", "*"))
            for host in self.allowed_hosts
        ):
            raise ConfigurationError("remote quotes require a non-empty exact host allowlist")
        allowed = {host.rstrip(".").lower() for host in self.allowed_hosts}
        for endpoint in (self.quote_endpoint, self.offers_endpoint):
            if endpoint is None:
                continue
            parsed = urlparse(endpoint)
            if (
                parsed.scheme not in {"http", "https"}
                or parsed.hostname is None
                or parsed.username is not None
                or parsed.password is not None
                or bool(parsed.query)
                or bool(parsed.fragment)
            ):
                raise ConfigurationError(
                    "remote quote endpoints must be credential-free absolute HTTP(S) URLs "
                    "without query strings or fragments"
                )
            if parsed.hostname.rstrip(".").lower() not in allowed:
                raise ConfigurationError("remote quote endpoint host is not locally allowlisted")
            if (
                parsed.scheme != "https"
                and not self.allow_insecure_http
                and not (
                    self.allow_private_networks and is_local_hostname(parsed.hostname)
                )
            ):
                raise ConfigurationError("remote quote endpoints require HTTPS by default")
        if any(
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
            or value <= 0
            for value in (
                self.per_provider_timeout_seconds,
                self.total_timeout_seconds,
            )
        ):
            raise ConfigurationError("remote quote timeouts must be positive")
        if self.total_timeout_seconds < self.per_provider_timeout_seconds:
            raise ConfigurationError("total quote timeout cannot be shorter than provider timeout")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1024
            for value in (self.maximum_request_bytes, self.maximum_response_bytes)
        ):
            raise ConfigurationError("remote quote byte limits must be at least 1024")
        if (
            isinstance(self.maximum_clock_skew_seconds, bool)
            or not isinstance(self.maximum_clock_skew_seconds, int)
            or self.maximum_clock_skew_seconds < 0
            or isinstance(self.maximum_quote_ttl_seconds, bool)
            or not isinstance(self.maximum_quote_ttl_seconds, int)
            or self.maximum_quote_ttl_seconds <= 0
        ):
            raise ConfigurationError("remote quote time bounds are invalid")


class QuoteReplayGuard(Protocol):
    async def consume(self, provider_id: str, nonce: str, quote_id: str) -> bool: ...


class InMemoryQuoteReplayGuard:
    """Process-local fallback; production routers should inject the durable store guard."""

    def __init__(self) -> None:
        self._uses: set[tuple[str, str]] = set()
        self._lock = asyncio.Lock()

    async def consume(self, provider_id: str, nonce: str, quote_id: str) -> bool:
        del quote_id
        key = (provider_id, nonce)
        async with self._lock:
            if key in self._uses:
                return False
            self._uses.add(key)
            return True


class RemoteQuoteProvider:
    """Bounded HTTP quote client for one operator-approved provider endpoint."""

    def __init__(
        self,
        config: RemoteQuoteProviderConfig,
        verifier: TrustStoreVerifier,
        *,
        client: httpx.AsyncClient | None = None,
        headers: Mapping[str, str] | None = None,
        clock: Callable[[], datetime] | None = None,
        replay_guard: QuoteReplayGuard | None = None,
        disclosure_policies: Mapping[str, QuoteDisclosurePolicy] | None = None,
    ) -> None:
        if client is not None and (client.follow_redirects or client.trust_env):
            raise ConfigurationError(
                "injected quote HTTP client must disable redirects and environment proxies"
            )
        self.config = config
        self.verifier = verifier
        self.clock = clock or (lambda: datetime.now(UTC))
        self.replay_guard = replay_guard or InMemoryQuoteReplayGuard()
        self._disclosure_policies = dict(disclosure_policies or {})
        if any(not executor_id for executor_id in self._disclosure_policies):
            raise ConfigurationError("quote disclosure policies require executor IDs")
        self._headers = {str(key): str(value) for key, value in (headers or {}).items()}
        if any(
            "\r" in key or "\n" in key or "\r" in value or "\n" in value
            for key, value in self._headers.items()
        ):
            raise ConfigurationError("quote HTTP headers cannot contain newlines")
        if {key.lower() for key in self._headers} & {
            "accept",
            "content-length",
            "content-type",
            "host",
            "transfer-encoding",
        }:
            raise ConfigurationError("quote HTTP headers cannot override protocol headers")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=config.per_provider_timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        )

    @property
    def provider_id(self) -> str:
        return self.config.provider_id

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise QuoteProviderError(
                QuoteErrorCode.CONFIGURATION,
                "quote clock must return a timezone-aware datetime",
                provider_id=self.provider_id,
            )
        return value.astimezone(UTC)

    def _network_config(self) -> dict[str, object]:
        return {
            "allowed_hosts": list(self.config.allowed_hosts),
            "allow_private_networks": self.config.allow_private_networks,
            "allow_insecure_http": self.config.allow_insecure_http,
        }

    async def _request_object(
        self,
        method: str,
        endpoint: str,
        *,
        body: bytes | None = None,
        params: Mapping[str, str] | None = None,
    ) -> dict[str, object]:
        if body is not None and len(body) > self.config.maximum_request_bytes:
            raise QuoteProviderError(
                QuoteErrorCode.REQUEST_TOO_LARGE,
                "quote request exceeds its configured size limit",
                provider_id=self.provider_id,
            )
        headers = {
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if body is not None else {}),
            **self._headers,
        }
        try:
            async with asyncio.timeout(self.config.total_timeout_seconds):
                try:
                    await validate_http_url(endpoint, self._network_config(), label="quote")
                except (ConfigurationError, ExecutorError) as exc:
                    raise QuoteProviderError(
                        QuoteErrorCode.NETWORK_POLICY,
                        "quote endpoint was rejected by local network policy",
                        provider_id=self.provider_id,
                    ) from exc
                async with self._client.stream(
                    method,
                    endpoint,
                    content=body,
                    params=params,
                    headers=headers,
                    timeout=self.config.per_provider_timeout_seconds,
                    follow_redirects=False,
                ) as response:
                    content_type = response.headers.get("content-type", "")
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > self.config.maximum_response_bytes:
                            raise QuoteProviderError(
                                QuoteErrorCode.RESPONSE_TOO_LARGE,
                                "quote response exceeds its configured size limit",
                                provider_id=self.provider_id,
                            )
                        chunks.append(chunk)
                    raw = b"".join(chunks)
                    status_code = response.status_code
        except QuoteProviderError:
            raise
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise QuoteProviderError(
                QuoteErrorCode.TIMEOUT,
                "quote request timed out",
                provider_id=self.provider_id,
            ) from exc
        except httpx.HTTPError as exc:
            raise QuoteProviderError(
                QuoteErrorCode.NETWORK,
                "quote network request failed",
                provider_id=self.provider_id,
            ) from exc

        if not 200 <= status_code < 300:
            raise QuoteProviderError(
                QuoteErrorCode.HTTP_STATUS,
                f"quote service returned HTTP status {status_code}",
                provider_id=self.provider_id,
                status_code=status_code,
            )
        content_type_parts = [part.strip() for part in content_type.split(";")]
        media_type = content_type_parts[0].lower()
        charsets = [
            part.partition("=")[2].strip().strip('"').lower()
            for part in content_type_parts[1:]
            if part.partition("=")[0].strip().lower() == "charset"
        ]
        if media_type != "application/json" or any(
            charset not in {"utf-8", "utf8"} for charset in charsets
        ):
            raise QuoteProviderError(
                QuoteErrorCode.CONTENT_TYPE,
                "quote service must return UTF-8 application/json",
                provider_id=self.provider_id,
            )
        try:
            decoded = json.loads(raw.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise QuoteProviderError(
                QuoteErrorCode.INVALID_RESPONSE,
                "quote service returned invalid JSON",
                provider_id=self.provider_id,
            ) from exc
        if not isinstance(decoded, dict):
            raise QuoteProviderError(
                QuoteErrorCode.INVALID_RESPONSE,
                "quote service response must be a JSON object",
                provider_id=self.provider_id,
            )
        return decoded

    def _verify_signature(
        self,
        record: CapabilityOffer | BoundedQuote,
        endpoint: str,
    ) -> None:
        host = urlparse(endpoint).hostname
        assert host is not None
        result = self.verifier.verify(
            canonical_payload(record),
            record.signature,
            self.provider_id,
            capability=record.capability,
            quote_host=host,
        )
        if not result.valid:
            raise QuoteProviderError(
                QuoteErrorCode.SIGNATURE,
                result.reason,
                provider_id=self.provider_id,
            )

    async def get_offers(
        self,
        capability: str,
        executor_ids: Sequence[str],
    ) -> Sequence[CapabilityOffer]:
        endpoint = self.config.offers_endpoint
        if endpoint is None:
            return ()
        if len(executor_ids) > 256:
            raise QuoteProviderError(
                QuoteErrorCode.REQUEST_TOO_LARGE,
                "offer request contains too many executor IDs",
                provider_id=self.provider_id,
            )
        response = await self._request_object(
            "GET",
            endpoint,
            params={
                "capability": capability,
                "executor_ids": ",".join(executor_ids),
            },
        )
        raw_offers = response.get("offers")
        if not isinstance(raw_offers, list) or len(raw_offers) > 256:
            raise QuoteProviderError(
                QuoteErrorCode.INVALID_RESPONSE,
                "offer response must contain a bounded offers array",
                provider_id=self.provider_id,
            )
        requested = set(executor_ids)
        now = self._now()
        offers: list[CapabilityOffer] = []
        for raw_offer in raw_offers:
            try:
                offer = CapabilityOffer.model_validate(raw_offer)
            except ValidationError as exc:
                raise QuoteProviderError(
                    QuoteErrorCode.INVALID_RESPONSE,
                    "offer response contains an invalid offer",
                    provider_id=self.provider_id,
                ) from exc
            if (
                offer.provider_id != self.provider_id
                or offer.capability != capability
                or (requested and offer.executor_id not in requested)
                or not offer.valid_at(now)
                or offer.issued_at > now + timedelta(seconds=self.config.maximum_clock_skew_seconds)
            ):
                raise QuoteProviderError(
                    QuoteErrorCode.BINDING,
                    "offer does not match the requested provider, capability, executor, or time",
                    provider_id=self.provider_id,
                )
            self._verify_signature(offer, endpoint)
            offers.append(offer)
        return tuple(offers)

    async def request_quote(self, request: QuoteRequestV2) -> BoundedQuote:
        try:
            validate_disclosed_quote_features(
                request.disclosed_quote_features,
                policy=self._disclosure_policies.get(request.executor_id),
            )
        except QuoteDisclosureError as exc:
            raise QuoteProviderError(
                QuoteErrorCode.CONFIGURATION,
                "quote disclosure was rejected by local policy",
                provider_id=self.provider_id,
            ) from exc
        now = self._now()
        if now >= request.expires_at:
            raise QuoteProviderError(
                QuoteErrorCode.BINDING,
                "quote request has expired",
                provider_id=self.provider_id,
            )
        if request.created_at > now + timedelta(seconds=self.config.maximum_clock_skew_seconds):
            raise QuoteProviderError(
                QuoteErrorCode.BINDING,
                "quote request creation time exceeds allowed clock skew",
                provider_id=self.provider_id,
            )
        body = json.dumps(
            request.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        response = await self._request_object("POST", self.config.quote_endpoint, body=body)
        try:
            quote = BoundedQuote.model_validate(response)
        except ValidationError as exc:
            raise QuoteProviderError(
                QuoteErrorCode.INVALID_RESPONSE,
                "quote service returned an invalid bounded quote",
                provider_id=self.provider_id,
            ) from exc
        if quote.provider_id != self.provider_id:
            raise QuoteProviderError(
                QuoteErrorCode.BINDING,
                "quote provider identity does not match the configured provider",
                provider_id=self.provider_id,
            )
        self._verify_signature(quote, self.config.quote_endpoint)
        now = self._now()
        if quote.issued_at > now + timedelta(seconds=self.config.maximum_clock_skew_seconds):
            raise QuoteProviderError(
                QuoteErrorCode.BINDING,
                "quote issue time exceeds allowed clock skew",
                provider_id=self.provider_id,
            )
        try:
            quote.validate_binding(
                request,
                at=max(now, quote.issued_at),
                maximum_ttl_seconds=self.config.maximum_quote_ttl_seconds,
            )
        except ValueError as exc:
            raise QuoteProviderError(
                QuoteErrorCode.BINDING,
                str(exc),
                provider_id=self.provider_id,
            ) from exc
        if not await self.replay_guard.consume(
            quote.provider_id,
            quote.nonce,
            quote.quote_id,
        ):
            raise QuoteProviderError(
                QuoteErrorCode.REPLAY,
                "quote nonce has already been used",
                provider_id=self.provider_id,
            )
        return quote


class CompositeQuoteProvider:
    """Combine named sources while retaining the source of every record."""

    def __init__(
        self,
        sources: Mapping[str, QuoteProvider],
        *,
        executor_sources: Mapping[str, str] | None = None,
    ) -> None:
        if not sources or any(not name for name in sources):
            raise ConfigurationError("composite quote provider requires named sources")
        self.sources = dict(sources)
        if len(self.sources) > 1 and executor_sources is None:
            raise ConfigurationError(
                "multi-source quote providers require exact executor-to-source routing"
            )
        self._executor_sources = dict(executor_sources or {})
        if any(not executor_id or not source_name for executor_id, source_name in self._executor_sources.items()):
            raise ConfigurationError("executor-to-source quote routes must be non-empty")
        unknown_sources = set(self._executor_sources.values()) - set(self.sources)
        if unknown_sources:
            raise ConfigurationError("executor quote route references an unknown source")
        self._offer_provenance: dict[str, str] = {}
        self._quote_provenance: dict[str, str] = {}

    async def get_offers(
        self,
        capability: str,
        executor_ids: Sequence[str],
    ) -> Sequence[CapabilityOffer]:
        requested = tuple(dict.fromkeys(executor_ids))
        partitions: dict[str, list[str]] = {}
        for executor_id in requested:
            source_name = self._executor_sources.get(executor_id)
            if source_name is None and len(self.sources) == 1:
                source_name = next(iter(self.sources))
            if source_name is not None:
                partitions.setdefault(source_name, []).append(executor_id)
        names = sorted(partitions)
        batches = await asyncio.gather(
            *(
                self.sources[name].get_offers(capability, partitions[name])
                for name in names
            )
        )
        offers: list[CapabilityOffer] = []
        requested_set = set(requested)
        for name, batch in zip(names, batches, strict=True):
            for offer in batch:
                if offer.capability != capability or offer.executor_id not in requested_set:
                    raise QuoteProviderError(
                        QuoteErrorCode.INVALID_RESPONSE,
                        "quote source returned an offer outside the requested binding",
                    )
                previous = self._offer_provenance.get(offer.offer_id)
                if previous is not None and previous != name:
                    raise QuoteProviderError(
                        QuoteErrorCode.INVALID_RESPONSE,
                        "offer ID collision across quote sources",
                    )
                executor_source = self._executor_sources.get(offer.executor_id)
                if executor_source is not None and executor_source != name:
                    raise QuoteProviderError(
                        QuoteErrorCode.INVALID_RESPONSE,
                        "executor is advertised by multiple quote sources",
                    )
                self._offer_provenance[offer.offer_id] = name
                self._executor_sources[offer.executor_id] = name
                offers.append(offer)
        return tuple(offers)

    async def request_quote(self, request: QuoteRequestV2) -> BoundedQuote:
        source_name = self._executor_sources.get(request.executor_id)
        if source_name is None and len(self.sources) == 1:
            source_name = next(iter(self.sources))
        if source_name is None:
            raise QuoteProviderError(
                QuoteErrorCode.UNAVAILABLE,
                "no quote source is configured for this executor",
            )
        quote = await self.sources[source_name].request_quote(request)
        previous = self._quote_provenance.get(quote.quote_id)
        if previous is not None and previous != source_name:
            raise QuoteProviderError(
                QuoteErrorCode.INVALID_RESPONSE,
                "quote ID collision across quote sources",
            )
        self._quote_provenance[quote.quote_id] = source_name
        return quote

    def offer_provenance(self, offer_id: str) -> str | None:
        return self._offer_provenance.get(offer_id)

    def quote_provenance(self, quote_id: str) -> str | None:
        return self._quote_provenance.get(quote_id)


@dataclass(frozen=True, slots=True)
class QuoteCandidate:
    provider_id: str
    request: QuoteRequestV2
    provider: QuoteProvider


@dataclass(frozen=True, slots=True)
class QuoteAcquisitionFailure:
    provider_id: str
    executor_id: str
    code: QuoteErrorCode
    reason: str


@dataclass(frozen=True, slots=True)
class QuoteAcquisitionResult:
    quotes: tuple[BoundedQuote, ...]
    failures: tuple[QuoteAcquisitionFailure, ...]


async def acquire_top_k_quotes(
    candidates: Sequence[QuoteCandidate],
    *,
    top_k: int = 3,
    total_timeout_seconds: float = 4.0,
) -> QuoteAcquisitionResult:
    """Request only the leading K candidates concurrently and return sanitized failures."""

    if top_k <= 0 or total_timeout_seconds <= 0:
        raise ConfigurationError("quote top_k and total timeout must be positive")
    shortlisted = tuple(candidates[:top_k])
    if not shortlisted:
        return QuoteAcquisitionResult((), ())

    async def acquire(
        candidate: QuoteCandidate,
    ) -> tuple[BoundedQuote | None, QuoteAcquisitionFailure | None]:
        try:
            return await candidate.provider.request_quote(candidate.request), None
        except QuoteProviderError as exc:
            return None, QuoteAcquisitionFailure(
                provider_id=candidate.provider_id,
                executor_id=candidate.request.executor_id,
                code=exc.quote_code,
                reason=str(exc),
            )
        except Exception:
            return None, QuoteAcquisitionFailure(
                provider_id=candidate.provider_id,
                executor_id=candidate.request.executor_id,
                code=QuoteErrorCode.INTERNAL,
                reason="quote provider failed",
            )

    tasks = [asyncio.create_task(acquire(candidate)) for candidate in shortlisted]
    done, pending = await asyncio.wait(tasks, timeout=total_timeout_seconds)
    results: dict[int, tuple[BoundedQuote | None, QuoteAcquisitionFailure | None]] = {}
    positions = {task: index for index, task in enumerate(tasks)}
    for task in done:
        results[positions[task]] = task.result()
    for task in pending:
        index = positions[task]
        task.cancel()
        candidate = shortlisted[index]
        results[index] = (
            None,
            QuoteAcquisitionFailure(
                provider_id=candidate.provider_id,
                executor_id=candidate.request.executor_id,
                code=QuoteErrorCode.TOTAL_TIMEOUT,
                reason="total quote acquisition deadline exceeded",
            ),
        )
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    quotes: list[BoundedQuote] = []
    failures: list[QuoteAcquisitionFailure] = []
    for index in range(len(shortlisted)):
        quote, failure = results[index]
        if quote is not None:
            quotes.append(quote)
        if failure is not None:
            failures.append(failure)
    return QuoteAcquisitionResult(tuple(quotes), tuple(failures))
