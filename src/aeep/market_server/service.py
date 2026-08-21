"""Deterministic local reference market for AEEP 0.4 economic evidence."""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal
from threading import RLock
from typing import TYPE_CHECKING, Any, TypeVar, cast
from urllib.parse import urlparse

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from ..economic.canonical import canonical_digest, canonical_payload
from ..economic.signing import Ed25519Signer
from ..economic.trust import TrustedProviderKey
from ..executors.base import BaseExecutor, ExecutionContext
from ..models import (
    ActionFeatures,
    BillingReconciliation,
    BillingTrigger,
    BoundedQuote,
    CapabilityOffer,
    CurrencyAmount,
    EconomicEvidenceLevel,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    FailureChargePolicy,
    Locality,
    MarketAggregate,
    MeterQuantity,
    PricingRoundingMode,
    PricingRule,
    ProviderExecutionStatus,
    QuoteRequestV2,
    RawExecution,
    ReconciliationStatus,
    ResourceVector,
    RetryChargePolicy,
    RouteEstimate,
    SideEffect,
    StrictModel,
    UsageStatement,
)
from ..qualification import behavior_fingerprint

if TYPE_CHECKING:
    from fastapi import FastAPI
    from fastapi import Request as _FastAPIRequest


PROVIDER_ID = "local.reference-provider"
CAPABILITY = "text.statistics@1"
EXECUTOR_ID = "reference.http.statistics"
KEY_ID = "local-reference-ed25519-1"
SETTLEMENT_CURRENCY = "USD"
REFERENCE_BASE_URL = "http://127.0.0.1:8787"
TERMS_DIGEST = (
    "sha256:"
    + hashlib.sha256(
        b"fixed USD 0.0010 plus USD 0.0002 per started KiB; no charge on clear failure"
    ).hexdigest()
)

_REFERENCE_PRIVATE_KEY = hashlib.sha256(
    b"AEEP 0.4 deterministic reference key; tests and local examples only"
).digest()
_FIXED_FEE = Decimal("0.0010")
_PER_KIB = Decimal("0.0002")
_MAXIMUM_INCREMENT = Decimal("0.0010")
_MAXIMUM_MARGIN = Decimal("0.0010")
_IDENTIFIER_PATTERN = r"^[A-Za-z0-9_.:-]+$"
_ENVIRONMENT_NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"

_TEXT_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}
_TEXT_STATISTICS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "characters": {"type": "integer"},
        "words": {"type": "integer"},
        "lines": {"type": "integer"},
    },
    "required": ["characters", "words", "lines"],
    "additionalProperties": False,
}


def reference_executor_spec(
    *,
    kind: ExecutorKind = ExecutorKind.HTTP,
    base_url: str = REFERENCE_BASE_URL,
    auth_token_env: str | None = None,
) -> ExecutorSpec:
    """Return the exact operator-authored executor described by reference offers."""

    parsed = urlparse(base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("reference base_url must be a credential-free loopback HTTP(S) origin")
    origin = base_url.rstrip("/")
    if auth_token_env is not None and not re.fullmatch(
        _ENVIRONMENT_NAME_PATTERN, auth_token_env
    ):
        raise ValueError("reference auth_token_env must be an environment identifier")
    economic = {
        "dynamic_pricing": True,
        "requires_binding_quote": True,
        "paid_marketplace": True,
        "quote_endpoint": f"{origin}/v1/quotes",
        "offers_endpoint": f"{origin}/v1/offers",
        "execute_endpoint": f"{origin}/v1/execute",
        "usage_statement_endpoint": f"{origin}/v1/usage-statements",
        "reconciliation_endpoint": f"{origin}/v1/reconciliations",
        "quote_disclosure": {
            "fields": [
                {
                    "source": "action_features.input_bytes",
                    "name": "input_bytes",
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100_000_000,
                    "required": True,
                }
            ],
            "maximum_encoded_bytes": 256,
        },
    }
    if auth_token_env is not None:
        economic["auth_token_env"] = auth_token_env
    resolved_kind = ExecutorKind(kind)
    if resolved_kind is ExecutorKind.HTTP:
        headers = {"Content-Type": "application/json"}
        if auth_token_env is not None:
            headers["Authorization"] = f"Bearer ${{ENV:{auth_token_env}}}"
        config: dict[str, Any] = {
            "url": f"{origin}/v1/execute",
            "method": "POST",
            "headers": headers,
            "json": {
                "quote_id": "{quote_id}",
                "prepared_id": "{prepared_id}",
                "action_id": "{action.action_id}",
                "attempt_id": "{attempt_id}",
                "text": "{input.text}",
            },
            "timeout_seconds": 5,
            "max_request_bytes": 262_144,
            "max_response_bytes": 262_144,
            "follow_redirects": False,
            "trust_proxy_env": False,
            "allowed_hosts": [parsed.hostname],
            "allow_private_networks": True,
            "allow_insecure_http": parsed.scheme == "http",
            "output": {"type": "json", "path": "output"},
            "economic": economic,
        }
        locality = Locality.LAN
        requires_network = True
    elif resolved_kind is ExecutorKind.PYTHON:
        config = {
            "callable": "aeep.market_server.service:text_statistics",
            "argument_mode": "kwargs",
            "timeout_seconds": 5,
            "economic": economic,
        }
        locality = Locality.IN_PROCESS
        requires_network = False
    else:
        raise ValueError("reference executor supports only HTTP or Python")
    return ExecutorSpec(
        id=EXECUTOR_ID,
        capability=CAPABILITY,
        kind=resolved_kind,
        description="Deterministic AEEP 0.4 text-statistics reference provider.",
        input_schema=_TEXT_INPUT_SCHEMA,
        output_schema=_TEXT_STATISTICS_SCHEMA,
        estimate=RouteEstimate(
            resources=ResourceVector(latency_ms=10, network_bytes=1024),
            success_probability=1,
            quality_score=1,
            risk_score=0,
            confidence=0.9,
        ),
        side_effect=SideEffect.NONE,
        locality=locality,
        requires_network=requires_network,
        data_residency=["local"],
        idempotent=True,
        safe_to_auto_execute=True,
        enabled=True,
        tags=["economic-reference"],
        provider_id=PROVIDER_ID,
        config=config,
    )


EXECUTOR_FINGERPRINT = f"sha256:{behavior_fingerprint(reference_executor_spec())}"


def deterministic_reference_signer() -> Ed25519Signer:
    """Return the public, deterministic key used only by the local reference service."""

    return Ed25519Signer.from_private_bytes(_REFERENCE_PRIVATE_KEY, key_id=KEY_ID)


class ReferenceMarketError(ValueError):
    """A bounded, safe-to-return reference service error."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class UsageStatementRequest(StrictModel):
    """Identifiers and locally measured usage needed to issue a provider statement."""

    quote_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    prepared_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    action_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    attempt_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    execution_status: ProviderExecutionStatus
    actual_input_bytes: int | None = Field(default=None, ge=0, le=100_000_000)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @field_validator("started_at", "completed_at")
    @classmethod
    def aware_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("usage timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def ordered_times(self) -> UsageStatementRequest:
        if (
            self.started_at is not None
            and self.completed_at is not None
            and self.completed_at < self.started_at
        ):
            raise ValueError("completed_at cannot precede started_at")
        return self


class ReconciliationRequest(StrictModel):
    """Sanitized external billing evidence for one provider usage statement."""

    settlement_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    usage_statement_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    billed_amount: CurrencyAmount
    task_valid: bool
    invoice_reference: str | None = Field(default=None, max_length=500)
    billing_record_reference: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def external_reference_required(self) -> ReconciliationRequest:
        if self.invoice_reference is None and self.billing_record_reference is None:
            raise ValueError("reconciliation requires an external billing reference")
        return self


class TextStatisticsExecutionRequest(StrictModel):
    """Ephemeral input for the reference tool; its text is never retained."""

    quote_id: str | None = Field(
        default=None, min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN
    )
    prepared_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        pattern=_IDENTIFIER_PATTERN,
    )
    action_id: str | None = Field(
        default=None, min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN
    )
    attempt_id: str | None = Field(
        default=None, min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN
    )
    text: str = Field(max_length=200_000)

    @model_validator(mode="after")
    def complete_economic_binding(self) -> TextStatisticsExecutionRequest:
        execution_bindings = (self.quote_id, self.prepared_id, self.attempt_id)
        if any(value is not None for value in execution_bindings) and (
            any(value is None for value in execution_bindings) or self.action_id is None
        ):
            raise ValueError("economic execution identifiers must be supplied together")
        return self


def text_statistics(text: str) -> dict[str, int]:
    """Execute the one deterministic reference capability."""

    return {
        "characters": len(text),
        "words": len(text.split()),
        "lines": text.count("\n") + int(bool(text)),
    }


@dataclass(frozen=True, slots=True)
class _UsageRecord:
    statement: UsageStatement
    input_bytes: int
    request_digest: str


@dataclass(frozen=True, slots=True)
class _AggregateObservation:
    observation_id: str
    input_bucket: str
    actual_cost: Decimal
    latency_ms: Decimal
    completed_at: datetime


RecordT = TypeVar("RecordT", CapabilityOffer, BoundedQuote, UsageStatement, MarketAggregate)


def _record_id(prefix: str, *values: str) -> str:
    digest = hashlib.sha256("\x1f".join(values).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:32]}"


def _aware_now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("reference market clock must return a timezone-aware datetime")
    return value.astimezone(UTC)


def _price(input_bytes: int) -> Decimal:
    kibibytes = Decimal((input_bytes + 1023) // 1024)
    return _FIXED_FEE + (_PER_KIB * kibibytes)


def _quoted_maximum(expected: Decimal) -> Decimal:
    return ((expected + _MAXIMUM_MARGIN) / _MAXIMUM_INCREMENT).to_integral_value(
        rounding=ROUND_CEILING
    ) * _MAXIMUM_INCREMENT


def _input_bucket(input_bytes: int) -> str:
    if input_bytes == 0:
        return "empty"
    if input_bytes <= 4 * 1024:
        return "0-4KiB"
    if input_bytes <= 64 * 1024:
        return "4-64KiB"
    if input_bytes <= 1024 * 1024:
        return "64KiB-1MiB"
    return "1MiB+"


def _duration_ms(started_at: datetime | None, completed_at: datetime | None) -> Decimal:
    if started_at is None or completed_at is None:
        return Decimal(0)
    elapsed = completed_at - started_at
    microseconds = (elapsed.days * 86_400 + elapsed.seconds) * 1_000_000 + elapsed.microseconds
    return Decimal(microseconds) / Decimal(1000)


def _percentile(values: list[Decimal], numerator: int, denominator: int = 100) -> Decimal:
    ordered = sorted(values)
    rank = max(1, (len(ordered) * numerator + denominator - 1) // denominator)
    return ordered[rank - 1]


class ReferenceMarket:
    """In-memory deterministic provider and privacy-bounded aggregate service."""

    def __init__(
        self,
        *,
        signer: Ed25519Signer | None = None,
        clock: Callable[[], datetime] | None = None,
        executor_spec: ExecutorSpec | None = None,
        minimum_aggregate_samples: int = 20,
        quote_ttl_seconds: int = 600,
        aggregate_ttl_seconds: int = 86_400,
    ) -> None:
        if minimum_aggregate_samples < 1:
            raise ValueError("minimum_aggregate_samples must be positive")
        if quote_ttl_seconds < 1 or aggregate_ttl_seconds < 1:
            raise ValueError("economic evidence TTLs must be positive")
        self.signer = signer or deterministic_reference_signer()
        self.clock = clock or (lambda: datetime.now(UTC))
        self.executor_spec = (executor_spec or reference_executor_spec()).model_copy(deep=True)
        if (
            self.executor_spec.id != EXECUTOR_ID
            or self.executor_spec.capability != CAPABILITY
            or self.executor_spec.provider_id != PROVIDER_ID
        ):
            raise ValueError("reference executor identity, capability, and provider must match")
        self.executor_fingerprint = f"sha256:{behavior_fingerprint(self.executor_spec)}"
        self.minimum_aggregate_samples = minimum_aggregate_samples
        self.quote_ttl_seconds = quote_ttl_seconds
        self.aggregate_ttl_seconds = aggregate_ttl_seconds
        self._lock = RLock()
        self._quote_requests: dict[str, QuoteRequestV2] = {}
        self._quote_request_digests: dict[str, str] = {}
        self._nonce_digests: dict[str, str] = {}
        self._quotes: dict[str, BoundedQuote] = {}
        self._usage: dict[str, _UsageRecord] = {}
        self._usage_by_attempt: dict[tuple[str, str], str] = {}
        self._reconciliations: dict[str, BillingReconciliation] = {}
        self._reconciliation_by_usage: dict[str, tuple[str, str]] = {}
        self._observations: list[_AggregateObservation] = []
        self.offer = self._build_offer()

    @property
    def trusted_key(self) -> TrustedProviderKey:
        return TrustedProviderKey(
            provider_id=PROVIDER_ID,
            key_id=self.signer.key_id,
            algorithm=self.signer.algorithm,
            public_key=self.signer.public_key_base64url(),
            valid_from=datetime(2024, 1, 1, tzinfo=UTC),
            valid_until=datetime(2100, 1, 1, tzinfo=UTC),
            allowed_capabilities=(CAPABILITY,),
            allowed_quote_hosts=("localhost", "127.0.0.1"),
        )

    def _signed_record(
        self,
        model_type: type[RecordT],
        fields: dict[str, Any],
    ) -> RecordT:
        unsigned = model_type.model_construct(**fields)
        return model_type.model_validate(
            {
                **fields,
                "signature": self.signer.sign(canonical_payload(unsigned)),
            }
        )

    def _build_offer(self) -> CapabilityOffer:
        fields: dict[str, Any] = {
            "schema_version": "0.4",
            "offer_id": "offer_reference_text_statistics_v1",
            "provider_id": PROVIDER_ID,
            "capability": CAPABILITY,
            "executor_id": EXECUTOR_ID,
            "executor_fingerprint": self.executor_fingerprint,
            "pricing_rules": (
                PricingRule(
                    rule_id="fixed-request",
                    fixed_amount=CurrencyAmount(amount=_FIXED_FEE, currency=SETTLEMENT_CURRENCY),
                ),
                PricingRule(
                    rule_id="input-kibibytes",
                    meter=f"{PROVIDER_ID}.input_kibibytes",
                    unit="kibibyte",
                    per_unit_amount=CurrencyAmount(
                        amount=_PER_KIB,
                        currency=SETTLEMENT_CURRENCY,
                    ),
                    quantity_increment=Decimal(1),
                    rounding_mode=PricingRoundingMode.CEILING,
                ),
            ),
            "billing_trigger": BillingTrigger.ON_SUCCESS,
            "failure_charge_policy": FailureChargePolicy.NO_CHARGE,
            "retry_charge_policy": RetryChargePolicy.EACH_ATTEMPT,
            "region": "local",
            "account_tier": "reference",
            "settlement_currency": SETTLEMENT_CURRENCY,
            "valid_from": datetime(2024, 1, 1, tzinfo=UTC),
            "valid_until": datetime(2100, 1, 1, tzinfo=UTC),
            "terms_digest": TERMS_DIGEST,
            "issued_at": datetime(2024, 1, 1, tzinfo=UTC),
        }
        return self._signed_record(CapabilityOffer, fields)

    def list_offers(
        self,
        *,
        capability: str | None = None,
        executor_id: str | None = None,
    ) -> tuple[CapabilityOffer, ...]:
        if capability is not None and capability != CAPABILITY:
            return ()
        if executor_id is not None and executor_id != EXECUTOR_ID:
            return ()
        return (self.offer,)

    def request_quote(self, request: QuoteRequestV2) -> BoundedQuote:
        now = _aware_now(self.clock)
        if request.capability != CAPABILITY:
            raise ReferenceMarketError(404, "unsupported_capability", "capability is not offered")
        if request.executor_id != EXECUTOR_ID:
            raise ReferenceMarketError(404, "unsupported_executor", "executor is not offered")
        if request.executor_fingerprint != self.executor_fingerprint:
            raise ReferenceMarketError(409, "executor_drift", "executor fingerprint does not match")
        if request.desired_currency != SETTLEMENT_CURRENCY:
            raise ReferenceMarketError(
                409, "currency_mismatch", "settlement currency does not match"
            )
        if request.created_at > now + timedelta(seconds=30):
            raise ReferenceMarketError(
                400, "future_request", "quote request is too far in the future"
            )
        if request.expires_at <= now:
            raise ReferenceMarketError(410, "expired_request", "quote request has expired")
        unknown_disclosures = set(request.disclosed_quote_features) - {"input_bytes"}
        if unknown_disclosures:
            raise ReferenceMarketError(
                400,
                "unapproved_disclosure",
                "reference provider accepts only the input_bytes disclosure",
            )
        disclosed_bytes = request.disclosed_quote_features.get("input_bytes")
        if disclosed_bytes is None or (
            isinstance(disclosed_bytes, bool)
            or not isinstance(disclosed_bytes, int)
            or disclosed_bytes < 0
            or disclosed_bytes > 100_000_000
            or disclosed_bytes != request.input_features.input_bytes
        ):
            raise ReferenceMarketError(
                400,
                "invalid_disclosure",
                "input_bytes disclosure must match the bounded action features",
            )

        request_digest = canonical_digest(request)
        with self._lock:
            prior_digest = self._quote_request_digests.get(request.quote_request_id)
            if prior_digest is not None and prior_digest != request_digest:
                raise ReferenceMarketError(
                    409,
                    "quote_request_conflict",
                    "quote request ID was already used with different content",
                )
            nonce_digest = self._nonce_digests.get(request.nonce)
            if nonce_digest is not None and nonce_digest != request_digest:
                raise ReferenceMarketError(
                    409,
                    "nonce_reuse",
                    "quote nonce was already used for a different request",
                )
            existing = next(
                (
                    quote
                    for quote in self._quotes.values()
                    if quote.quote_request_id == request.quote_request_id
                ),
                None,
            )
            if existing is not None:
                return existing

            expected = _price(request.input_features.input_bytes)
            maximum = _quoted_maximum(expected)
            requested_maximum = request.maximum_acceptable_amount
            if requested_maximum is not None and maximum > requested_maximum.amount:
                raise ReferenceMarketError(
                    409,
                    "maximum_exceeded",
                    "binding maximum exceeds maximum acceptable amount",
                )
            expires_at = min(
                request.expires_at,
                now + timedelta(seconds=self.quote_ttl_seconds),
            )
            if expires_at <= now:
                raise ReferenceMarketError(410, "expired_request", "quote request has expired")
            quote = self._signed_record(
                BoundedQuote,
                {
                    "schema_version": "0.4",
                    "quote_id": _record_id("quote", request_digest),
                    "quote_request_id": request.quote_request_id,
                    "offer_id": self.offer.offer_id,
                    "provider_id": PROVIDER_ID,
                    "capability": CAPABILITY,
                    "executor_id": EXECUTOR_ID,
                    "executor_fingerprint": self.executor_fingerprint,
                    "action_digest": request.action_digest,
                    "nonce": request.nonce,
                    "expected_amount": CurrencyAmount(
                        amount=expected,
                        currency=SETTLEMENT_CURRENCY,
                    ),
                    "maximum_amount": CurrencyAmount(
                        amount=maximum,
                        currency=SETTLEMENT_CURRENCY,
                    ),
                    "estimated_meters": (
                        MeterQuantity(
                            meter=f"{PROVIDER_ID}.input_bytes",
                            unit="byte",
                            quantity=Decimal(request.input_features.input_bytes),
                        ),
                    ),
                    "billing_trigger": BillingTrigger.ON_SUCCESS,
                    "failure_charge_policy": FailureChargePolicy.NO_CHARGE,
                    "retry_charge_policy": RetryChargePolicy.EACH_ATTEMPT,
                    "terms_digest": TERMS_DIGEST,
                    "issued_at": now,
                    "expires_at": expires_at,
                    "evidence_level": EconomicEvidenceLevel.SIGNED_QUOTE,
                },
            )
            self._quote_requests[request.quote_request_id] = request
            self._quote_request_digests[request.quote_request_id] = request_digest
            self._nonce_digests[request.nonce] = request_digest
            self._quotes[quote.quote_id] = quote
            return quote

    def issue_usage_statement(self, request: UsageStatementRequest) -> UsageStatement:
        now = _aware_now(self.clock)
        with self._lock:
            quote = self._quotes.get(request.quote_id)
            if quote is None:
                raise ReferenceMarketError(404, "unknown_quote", "quote was not issued here")
            quote_request = self._quote_requests[quote.quote_request_id]
            if quote_request.action_id != request.action_id:
                raise ReferenceMarketError(409, "action_mismatch", "action ID does not match quote")
            started_at = request.started_at or now
            completed_at = request.completed_at or now
            if started_at > now or completed_at > now:
                raise ReferenceMarketError(400, "future_usage", "usage timestamps cannot be future")
            if started_at >= quote.expires_at:
                raise ReferenceMarketError(410, "expired_quote", "quote expired before invocation")
            quoted_bytes = quote_request.input_features.input_bytes
            actual_bytes = (
                quoted_bytes if request.actual_input_bytes is None else request.actual_input_bytes
            )
            if actual_bytes > quoted_bytes:
                raise ReferenceMarketError(
                    409,
                    "usage_above_bound",
                    "actual input bytes exceed the request-bound quote input",
                )
            amount = (
                None
                if request.execution_status
                in {ProviderExecutionStatus.TIMEOUT, ProviderExecutionStatus.INDETERMINATE}
                else CurrencyAmount(
                    amount=(
                        _price(actual_bytes)
                        if request.execution_status is ProviderExecutionStatus.SUCCESS
                        else Decimal(0)
                    ),
                    currency=SETTLEMENT_CURRENCY,
                )
            )
            request_digest = canonical_digest(request)
            attempt_key = (request.prepared_id, request.attempt_id)
            existing_id = self._usage_by_attempt.get(attempt_key)
            if existing_id is not None:
                existing = self._usage[existing_id]
                if existing.request_digest != request_digest:
                    raise ReferenceMarketError(
                        409,
                        "attempt_conflict",
                        "attempt identity was already used with different content",
                    )
                return existing.statement
            statement = self._signed_record(
                UsageStatement,
                {
                    "schema_version": "0.4",
                    "usage_statement_id": _record_id(
                        "usage",
                        request.quote_id,
                        request.prepared_id,
                        request.action_id,
                        request.attempt_id,
                    ),
                    "quote_id": request.quote_id,
                    "prepared_id": request.prepared_id,
                    "action_id": request.action_id,
                    "attempt_id": request.attempt_id,
                    "provider_id": PROVIDER_ID,
                    "executor_id": EXECUTOR_ID,
                    "executor_fingerprint": self.executor_fingerprint,
                    "execution_status": request.execution_status,
                    "meters": (
                        MeterQuantity(
                            meter=f"{PROVIDER_ID}.input_bytes",
                            unit="byte",
                            quantity=Decimal(actual_bytes),
                        ),
                        MeterQuantity(
                            meter="requests",
                            unit="request",
                            quantity=Decimal(1),
                        ),
                    ),
                    "provider_calculated_amount": amount,
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "issued_at": now,
                    "evidence_level": EconomicEvidenceLevel.SIGNED_USAGE_STATEMENT,
                },
            )
            self._usage[statement.usage_statement_id] = _UsageRecord(
                statement=statement,
                input_bytes=actual_bytes,
                request_digest=request_digest,
            )
            self._usage_by_attempt[attempt_key] = statement.usage_statement_id
            return statement

    def reconcile(self, request: ReconciliationRequest) -> BillingReconciliation:
        now = _aware_now(self.clock)
        if request.billed_amount.currency != SETTLEMENT_CURRENCY:
            raise ReferenceMarketError(
                409, "currency_mismatch", "settlement currency does not match"
            )
        request_digest = canonical_digest(request)
        with self._lock:
            usage = self._usage.get(request.usage_statement_id)
            if usage is None:
                raise ReferenceMarketError(
                    404,
                    "unknown_usage",
                    "usage statement was not issued here",
                )
            expected = usage.statement.provider_calculated_amount
            if expected is None:
                raise ReferenceMarketError(
                    409,
                    "indeterminate_charge",
                    "indeterminate usage cannot be reconciled automatically",
                )
            if (
                request.task_valid
                and usage.statement.execution_status is not ProviderExecutionStatus.SUCCESS
            ):
                raise ReferenceMarketError(
                    409,
                    "invalid_success_evidence",
                    "only successful execution may be marked task-valid",
                )
            prior = self._reconciliation_by_usage.get(request.usage_statement_id)
            if prior is not None:
                reconciliation_id, prior_digest = prior
                if prior_digest != request_digest:
                    raise ReferenceMarketError(
                        409,
                        "reconciliation_conflict",
                        "usage statement was already reconciled with different evidence",
                    )
                return self._reconciliations[reconciliation_id]

            billed = request.billed_amount.amount
            expected_value = expected.amount
            status = (
                ReconciliationStatus.MATCHED
                if billed == expected_value
                else ReconciliationStatus.UNDERCHARGED
                if billed < expected_value
                else ReconciliationStatus.OVERCHARGED
            )
            evidence_digest = canonical_digest(
                {
                    "settlement_id": request.settlement_id,
                    "usage_statement_id": request.usage_statement_id,
                    "invoice_reference": request.invoice_reference,
                    "billing_record_reference": request.billing_record_reference,
                    "billed_amount": request.billed_amount,
                }
            )
            record = BillingReconciliation(
                reconciliation_id=_record_id(
                    "reconciliation",
                    request.settlement_id,
                    request.usage_statement_id,
                    evidence_digest,
                ),
                settlement_id=request.settlement_id,
                provider_id=PROVIDER_ID,
                invoice_reference=request.invoice_reference,
                billing_record_reference=request.billing_record_reference,
                expected_amount=expected,
                billed_amount=request.billed_amount,
                discrepancy=CurrencyAmount(
                    amount=abs(billed - expected_value),
                    currency=SETTLEMENT_CURRENCY,
                ),
                status=status,
                evidence_digest=evidence_digest,
                reconciled_at=now,
            )
            self._reconciliations[record.reconciliation_id] = record
            self._reconciliation_by_usage[request.usage_statement_id] = (
                record.reconciliation_id,
                request_digest,
            )
            if request.task_valid:
                completed_at = usage.statement.completed_at or usage.statement.issued_at
                self._observations.append(
                    _AggregateObservation(
                        observation_id=record.reconciliation_id,
                        input_bucket=_input_bucket(usage.input_bytes),
                        actual_cost=billed,
                        latency_ms=_duration_ms(
                            usage.statement.started_at,
                            usage.statement.completed_at,
                        ),
                        completed_at=completed_at,
                    )
                )
            return record

    def list_aggregates(self, *, input_bucket: str | None = None) -> tuple[MarketAggregate, ...]:
        now = _aware_now(self.clock)
        with self._lock:
            buckets: dict[str, list[_AggregateObservation]] = {}
            for observation in self._observations:
                if input_bucket is None or observation.input_bucket == input_bucket:
                    buckets.setdefault(observation.input_bucket, []).append(observation)

            aggregates: list[MarketAggregate] = []
            for bucket in sorted(buckets):
                observations = buckets[bucket]
                if len(observations) < self.minimum_aggregate_samples:
                    continue
                costs = [item.actual_cost for item in observations]
                latencies = [item.latency_ms for item in observations]
                window_start = min(item.completed_at for item in observations)
                window_end = max(item.completed_at for item in observations)
                if window_end == window_start:
                    window_start -= timedelta(microseconds=1)
                observation_ids = ",".join(sorted(item.observation_id for item in observations))
                aggregate = self._signed_record(
                    MarketAggregate,
                    {
                        "schema_version": "0.4",
                        "aggregate_id": _record_id(
                            "aggregate",
                            self.executor_fingerprint,
                            bucket,
                            observation_ids,
                        ),
                        "capability": CAPABILITY,
                        "provider_id": PROVIDER_ID,
                        "executor_id": EXECUTOR_ID,
                        "executor_fingerprint": self.executor_fingerprint,
                        "region": "local",
                        "account_tier": "reference",
                        "input_bucket": bucket,
                        "sample_size": len(observations),
                        "window_start": window_start,
                        "window_end": window_end,
                        "actual_cost_p50": CurrencyAmount(
                            amount=_percentile(costs, 50),
                            currency=SETTLEMENT_CURRENCY,
                        ),
                        "actual_cost_p95": CurrencyAmount(
                            amount=_percentile(costs, 95),
                            currency=SETTLEMENT_CURRENCY,
                        ),
                        "latency_ms_p50": _percentile(latencies, 50),
                        "latency_ms_p95": _percentile(latencies, 95),
                        "valid_success_rate": Decimal(1),
                        "valid_success_lower_bound": (
                            Decimal(len(observations)) / Decimal(len(observations) + 2)
                        ),
                        "settlement_verified_fraction": Decimal(0),
                        "billing_reconciled_fraction": Decimal(1),
                        "generated_at": now,
                        "expires_at": now + timedelta(seconds=self.aggregate_ttl_seconds),
                    },
                )
                aggregates.append(aggregate)
            return tuple(aggregates)


class ReferenceQuoteProvider:
    """In-process quote-provider adapter for deterministic campaigns and tests."""

    def __init__(self, market: ReferenceMarket | None = None) -> None:
        self.market = market or ReferenceMarket()

    async def get_offers(
        self,
        capability: str,
        executor_ids: Sequence[str],
    ) -> Sequence[CapabilityOffer]:
        if executor_ids and EXECUTOR_ID not in executor_ids:
            return ()
        return self.market.list_offers(capability=capability, executor_id=EXECUTOR_ID)

    async def request_quote(self, request: QuoteRequestV2) -> BoundedQuote:
        return self.market.request_quote(request)


class ReferenceEconomicExecutor(BaseExecutor):
    """In-process executor that returns signed usage evidence without retaining input."""

    def __init__(self, market: ReferenceMarket) -> None:
        self.market = market

    async def execute(self, context: ExecutionContext) -> RawExecution:
        if f"sha256:{behavior_fingerprint(context.spec)}" != self.market.executor_fingerprint:
            return RawExecution(
                status=ExecutionStatus.REJECTED,
                error_type="ConfigurationError",
                error_message="reference executor fingerprint does not match its market",
            )
        text = context.request.input.get("text")
        if not isinstance(text, str):
            return RawExecution(
                status=ExecutionStatus.REJECTED,
                error_type="ValidationError",
                error_message="reference executor requires string input.text",
            )
        execution_bindings = (context.prepared_id, context.quote_id, context.attempt_id)
        if any(value is not None for value in execution_bindings) and any(
            value is None for value in execution_bindings
        ):
            return RawExecution(
                status=ExecutionStatus.REJECTED,
                error_type="ConfigurationError",
                error_message="prepared reference execution requires quote and attempt bindings",
            )
        metadata: dict[str, Any] = {"provider_id": PROVIDER_ID}
        if all(value is not None for value in execution_bindings):
            now = _aware_now(self.market.clock)
            statement = self.market.issue_usage_statement(
                UsageStatementRequest(
                    quote_id=cast(str, context.quote_id),
                    prepared_id=cast(str, context.prepared_id),
                    action_id=context.request.action_id,
                    attempt_id=cast(str, context.attempt_id),
                    execution_status=ProviderExecutionStatus.SUCCESS,
                    actual_input_bytes=len(text.encode("utf-8")),
                    started_at=now,
                    completed_at=now,
                )
            )
            metadata["_economic_usage_statement"] = statement.model_dump(mode="json")
        return RawExecution(
            status=ExecutionStatus.SUCCESS,
            output=text_statistics(text),
            metadata=metadata,
        )


def _model_json(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


def create_app(
    market: ReferenceMarket | None = None,
    *,
    bearer_token: str | None = None,
    authorize: Callable[[str | None], bool] | None = None,
    maximum_request_bytes: int = 262_144,
    allow_unauthenticated_evidence: bool = False,
) -> FastAPI:
    """Create the optional FastAPI reference service without a base dependency."""

    if maximum_request_bytes < 1:
        raise ValueError("maximum_request_bytes must be positive")
    if bearer_token == "":
        raise ValueError("bearer_token must not be empty")
    if bearer_token is not None and authorize is not None:
        raise ValueError("configure bearer_token or authorize, not both")
    try:
        from fastapi import FastAPI, HTTPException, Request
        from fastapi.responses import JSONResponse
    except ImportError as exc:  # pragma: no cover - optional extra
        raise RuntimeError(
            "Reference market serving requires `pip install 'aeep-agent-router[http-server]'`"
        ) from exc

    globals()["_FastAPIRequest"] = Request
    service = market or ReferenceMarket()
    app = FastAPI(title="AEEP Local Economic Evidence Market", version="0.4")

    def require_authorization(request: _FastAPIRequest) -> None:
        if bearer_token is None and authorize is None:
            return
        header = request.headers.get("authorization")
        token = None
        if header is not None and header[:7].lower() == "bearer ":
            token = header[7:]
        valid = (
            token is not None and hmac.compare_digest(token, bearer_token)
            if bearer_token is not None
            else bool(authorize and authorize(token))
        )
        if not valid:
            raise HTTPException(status_code=401, detail="invalid bearer authorization")

    def require_evidence_authorization(request: _FastAPIRequest) -> None:
        if bearer_token is None and authorize is None:
            if allow_unauthenticated_evidence:
                return
            raise HTTPException(
                status_code=403,
                detail="economic evidence ingestion requires authentication",
            )
        require_authorization(request)

    async def parse_body(request: _FastAPIRequest, model_type: type[BaseModel]) -> BaseModel:
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise HTTPException(status_code=415, detail="application/json is required")
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                parsed_length = int(content_length)
                if parsed_length < 0:
                    raise ValueError
                if parsed_length > maximum_request_bytes:
                    raise HTTPException(status_code=413, detail="request body too large")
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="invalid content length") from exc
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > maximum_request_bytes:
                raise HTTPException(status_code=413, detail="request body too large")
            body.extend(chunk)
        try:
            return model_type.model_validate_json(bytes(body))
        except (ValidationError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="invalid request body") from exc

    @app.exception_handler(ReferenceMarketError)
    async def reference_error(
        _request: _FastAPIRequest,
        exc: ReferenceMarketError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": str(exc)}},
        )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "ok": True,
            "service": "aeep-reference-market",
            "schema_version": "0.4",
            "reference_only": True,
            "unauthenticated_evidence_ingestion": allow_unauthenticated_evidence,
        }

    @app.get("/.well-known/aeep-keys.json")
    async def keys() -> dict[str, Any]:
        return {"schema_version": "0.4", "keys": [_model_json(service.trusted_key)]}

    @app.get("/v1/offers")
    async def offers(
        request: _FastAPIRequest,
        capability: str | None = None,
        executor_id: str | None = None,
    ) -> dict[str, Any]:
        require_authorization(request)
        return {
            "offers": [
                _model_json(offer)
                for offer in service.list_offers(
                    capability=capability,
                    executor_id=executor_id,
                )
            ]
        }

    @app.post("/v1/quotes")
    async def quotes(request: _FastAPIRequest) -> dict[str, Any]:
        require_authorization(request)
        parsed = cast(QuoteRequestV2, await parse_body(request, QuoteRequestV2))
        return _model_json(service.request_quote(parsed))

    @app.post("/v1/usage-statements")
    async def usage_statements(request: _FastAPIRequest) -> dict[str, Any]:
        require_evidence_authorization(request)
        parsed = cast(
            UsageStatementRequest,
            await parse_body(request, UsageStatementRequest),
        )
        return _model_json(service.issue_usage_statement(parsed))

    @app.post("/v1/execute")
    async def execute(request: _FastAPIRequest) -> dict[str, Any]:
        require_authorization(request)
        parsed = cast(
            TextStatisticsExecutionRequest,
            await parse_body(request, TextStatisticsExecutionRequest),
        )
        result: dict[str, Any] = {"output": text_statistics(parsed.text)}
        if (
            parsed.quote_id is not None
            and parsed.prepared_id is not None
            and parsed.action_id is not None
            and parsed.attempt_id is not None
        ):
            now = _aware_now(service.clock)
            statement = service.issue_usage_statement(
                UsageStatementRequest(
                    quote_id=parsed.quote_id,
                    prepared_id=parsed.prepared_id,
                    action_id=parsed.action_id,
                    attempt_id=parsed.attempt_id,
                    execution_status=ProviderExecutionStatus.SUCCESS,
                    actual_input_bytes=len(parsed.text.encode("utf-8")),
                    started_at=now,
                    completed_at=now,
                )
            )
            result["usage_statement"] = _model_json(statement)
        return result

    @app.post("/v1/reconciliations")
    async def reconciliations(request: _FastAPIRequest) -> dict[str, Any]:
        require_evidence_authorization(request)
        parsed = cast(
            ReconciliationRequest,
            await parse_body(request, ReconciliationRequest),
        )
        return _model_json(service.reconcile(parsed))

    @app.get("/v1/aggregates")
    async def aggregates(
        request: _FastAPIRequest,
        input_bucket: str | None = None,
    ) -> dict[str, Any]:
        require_authorization(request)
        return {
            "aggregates": [
                _model_json(aggregate)
                for aggregate in service.list_aggregates(input_bucket=input_bucket)
            ]
        }

    return app


def example_quote_request(
    *,
    now: datetime | None = None,
    input_bytes: int = 14_336,
    executor_spec: ExecutorSpec | None = None,
) -> QuoteRequestV2:
    """Build the sanitized request used by the runnable local example."""

    created_at = now or datetime.now(UTC)
    fingerprint = f"sha256:{behavior_fingerprint(executor_spec or reference_executor_spec())}"
    digest = "sha256:" + hashlib.sha256(b"local reference action").hexdigest()
    return QuoteRequestV2(
        quote_request_id="request-reference-1",
        action_id="action-reference-1",
        capability=CAPABILITY,
        executor_id=EXECUTOR_ID,
        executor_fingerprint=fingerprint,
        action_digest=digest,
        input_features=ActionFeatures(
            input_bytes=input_bytes,
            input_items=1,
            text_characters=input_bytes,
            max_depth=1,
            size_bucket="2^14",
        ),
        disclosed_quote_features={"input_bytes": input_bytes},
        desired_currency=SETTLEMENT_CURRENCY,
        nonce="reference-nonce-0001",
        created_at=created_at,
        expires_at=created_at + timedelta(minutes=5),
    )
