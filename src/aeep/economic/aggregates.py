"""Trusted, scoring-only market aggregate priors.

Market aggregates summarize observed qualified executions.  This module only
selects inputs for initial economic ranking; it has no registry mutation or
qualification surface and its output is explicitly non-binding.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal, Protocol

from pydantic import Field, ValidationError

from ..errors import ConfigurationError
from ..models import (
    CurrencyAmount,
    EconomicEvidenceLevel,
    EconomicStrictModel,
    MarketAggregate,
    MarketAggregatesConfig,
)
from .canonical import canonical_payload
from .trust import TrustStoreVerifier


class MarketAggregateStore(Protocol):
    """Read-only subset of :class:`ReceiptStore` used by aggregate selection."""

    def list_market_aggregates(
        self,
        *,
        capability: str | None = None,
        limit: int = 1_000,
    ) -> list[MarketAggregate]: ...


class MarketAggregateWriteStore(MarketAggregateStore, Protocol):
    """Immutable store subset needed by the bounded aggregate importer."""

    def get_market_aggregate(self, aggregate_id: str) -> MarketAggregate | None: ...

    def save_market_aggregate(self, aggregate: MarketAggregate) -> MarketAggregate: ...


class _MarketAggregateEnvelope(EconomicStrictModel):
    aggregates: tuple[MarketAggregate, ...] = Field(max_length=1_000)


class MarketAggregateImporter:
    """Verify a bounded JSON aggregate response before persisting buyer priors.

    Network acquisition remains the caller's responsibility and must use the
    normal allowlist/SSRF controls.  This boundary accepts only an already
    bounded HTTP/file payload and never mutates qualification or activation.
    """

    def __init__(
        self,
        store: MarketAggregateWriteStore,
        verifier: TrustStoreVerifier,
        *,
        maximum_response_bytes: int = 262_144,
        maximum_records: int = 1_000,
    ) -> None:
        if maximum_response_bytes < 1:
            raise ConfigurationError("aggregate response limit must be positive")
        if not 1 <= maximum_records <= 1_000:
            raise ConfigurationError("aggregate record limit must be between 1 and 1000")
        self.store = store
        self.verifier = verifier
        self.maximum_response_bytes = maximum_response_bytes
        self.maximum_records = maximum_records

    def import_response(
        self,
        payload: bytes,
        *,
        content_type: str = "application/json",
    ) -> tuple[MarketAggregate, ...]:
        """Verify and immutably store one provider aggregate response."""

        if not isinstance(payload, bytes):
            raise ConfigurationError("aggregate response must be bytes")
        if len(payload) > self.maximum_response_bytes:
            raise ConfigurationError("aggregate response exceeds its configured size limit")
        parts = [part.strip() for part in content_type.split(";")]
        if not parts or parts[0].lower() != "application/json":
            raise ConfigurationError("aggregate response must use application/json")
        charsets = [
            part.partition("=")[2].strip().strip('"').lower()
            for part in parts[1:]
            if part.partition("=")[0].strip().lower() == "charset"
        ]
        if any(charset not in {"utf-8", "utf8"} for charset in charsets):
            raise ConfigurationError("aggregate response must use UTF-8")
        try:
            envelope = _MarketAggregateEnvelope.model_validate_json(payload)
        except (ValidationError, ValueError) as exc:
            raise ConfigurationError("aggregate response is not a valid 0.4 envelope") from exc
        if len(envelope.aggregates) > self.maximum_records:
            raise ConfigurationError("aggregate response contains too many records")

        verified: dict[str, MarketAggregate] = {}
        for aggregate in envelope.aggregates:
            existing_in_response = verified.get(aggregate.aggregate_id)
            if existing_in_response is not None:
                if existing_in_response != aggregate:
                    raise ConfigurationError(
                        "aggregate response reuses an ID with different content"
                    )
                continue
            current = self.verifier.verify(
                canonical_payload(aggregate),
                aggregate.signature,
                aggregate.provider_id,
                capability=aggregate.capability,
            )
            historical = self.verifier.verify(
                canonical_payload(aggregate),
                aggregate.signature,
                aggregate.provider_id,
                capability=aggregate.capability,
                signed_at=aggregate.generated_at,
                allow_historical=True,
            )
            if not current.valid or not historical.valid:
                raise ConfigurationError("aggregate signature is not trusted for import")
            stored = self.store.get_market_aggregate(aggregate.aggregate_id)
            if stored is not None and stored != aggregate:
                raise ConfigurationError("aggregate ID already has different immutable content")
            verified[aggregate.aggregate_id] = aggregate
        return tuple(
            self.store.save_market_aggregate(aggregate)
            for aggregate in verified.values()
        )


@dataclass(frozen=True, slots=True)
class MarketAggregatePrior:
    """Signed aggregate provenance and the scoring inputs derived from it."""

    aggregate: MarketAggregate
    evidence_level: EconomicEvidenceLevel = field(
        default=EconomicEvidenceLevel.STATIC_PRIOR,
        init=False,
    )
    binding: Literal[False] = field(default=False, init=False)
    qualification_evidence: Literal[False] = field(default=False, init=False)
    activation_evidence: Literal[False] = field(default=False, init=False)

    @property
    def source_aggregate_id(self) -> str:
        return self.aggregate.aggregate_id

    @property
    def expected_cash(self) -> CurrencyAmount | None:
        """Return p50 actual cash as a prior, never as a guaranteed amount."""

        return self.aggregate.actual_cost_p50

    @property
    def cash_p95_prior(self) -> CurrencyAmount | None:
        """Return p95 actual cash as uncertainty evidence, not a hard maximum."""

        return self.aggregate.actual_cost_p95

    @property
    def latency_ms_p50(self) -> Decimal | None:
        return self.aggregate.latency_ms_p50

    @property
    def latency_ms_p95(self) -> Decimal | None:
        return self.aggregate.latency_ms_p95

    @property
    def valid_success_rate(self) -> Decimal | None:
        return self.aggregate.valid_success_rate

    @property
    def valid_success_lower_bound(self) -> Decimal | None:
        return self.aggregate.valid_success_lower_bound


class MarketAggregateSelector:
    """Select the freshest exact, trusted aggregate admitted by local policy."""

    def __init__(
        self,
        store: MarketAggregateStore,
        verifier: TrustStoreVerifier,
        *,
        config: MarketAggregatesConfig,
        settlement_currency: str,
        clock: Callable[[], datetime] | None = None,
        limit: int = 1_000,
    ) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ConfigurationError("market aggregate query limit must be positive")
        try:
            currency = CurrencyAmount(amount=Decimal(0), currency=settlement_currency).currency
        except ValueError as exc:
            raise ConfigurationError("market aggregate settlement currency is invalid") from exc
        self.store = store
        self.verifier = verifier
        self.config = config
        self.settlement_currency = currency
        self.clock = clock or (lambda: datetime.now(UTC))
        self.limit = limit

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ConfigurationError("market aggregate clock must be timezone-aware")
        return value.astimezone(UTC)

    def _eligible(
        self,
        aggregate: MarketAggregate,
        *,
        capability: str,
        provider_id: str,
        executor_id: str,
        executor_fingerprint: str,
        input_bucket: str,
        region: str | None,
        account_tier: str | None,
        at: datetime,
    ) -> bool:
        if (
            aggregate.capability != capability
            or aggregate.provider_id != provider_id
            or aggregate.executor_id != executor_id
            or aggregate.executor_fingerprint != executor_fingerprint
            or aggregate.input_bucket != input_bucket
            or aggregate.region != region
            or aggregate.account_tier != account_tier
        ):
            return False
        if (
            not aggregate.fresh_at(at)
            or aggregate.window_end > at
            or at - aggregate.generated_at
            > timedelta(seconds=self.config.maximum_age_seconds)
            or aggregate.sample_size < self.config.minimum_sample_size
            or aggregate.settlement_verified_fraction
            < self.config.minimum_settlement_verified_fraction
        ):
            return False
        if any(
            amount is not None and amount.currency != self.settlement_currency
            for amount in (aggregate.actual_cost_p50, aggregate.actual_cost_p95)
        ):
            return False
        current_verification = self.verifier.verify(
            canonical_payload(aggregate),
            aggregate.signature,
            provider_id,
            capability=capability,
        )
        if not current_verification.valid:
            return False
        historical_verification = self.verifier.verify(
            canonical_payload(aggregate),
            aggregate.signature,
            provider_id,
            capability=capability,
            signed_at=aggregate.generated_at,
            allow_historical=True,
        )
        return historical_verification.valid

    def select(
        self,
        *,
        capability: str,
        provider_id: str,
        executor_id: str,
        executor_fingerprint: str,
        input_bucket: str,
        region: str | None = None,
        account_tier: str | None = None,
    ) -> MarketAggregatePrior | None:
        """Return one scoring prior, or ``None`` when no aggregate is admissible."""

        if not self.config.enabled:
            return None
        at = self._now()
        eligible = [
            aggregate
            for aggregate in self.store.list_market_aggregates(
                capability=capability,
                limit=self.limit,
            )
            if self._eligible(
                aggregate,
                capability=capability,
                provider_id=provider_id,
                executor_id=executor_id,
                executor_fingerprint=executor_fingerprint,
                input_bucket=input_bucket,
                region=region,
                account_tier=account_tier,
                at=at,
            )
        ]
        if not eligible:
            return None
        selected = max(
            eligible,
            key=lambda aggregate: (
                aggregate.generated_at,
                aggregate.settlement_verified_fraction,
                aggregate.sample_size,
                aggregate.aggregate_id,
            ),
        )
        return MarketAggregatePrior(selected)
