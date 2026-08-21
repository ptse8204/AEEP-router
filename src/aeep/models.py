"""Protocol and runtime models.

The models intentionally preserve raw resource dimensions rather than converting
all usage into a synthetic token or currency. A policy can assign local shadow
prices or weights without losing the original measurements.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import re
from datetime import UTC, datetime
from decimal import (
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_FLOOR,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    ROUND_UP,
    Decimal,
    InvalidOperation,
)
from enum import StrEnum
from typing import Annotated, Any, ClassVar, Literal, TypeAlias
from uuid import uuid4

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    WithJsonSchema,
    field_validator,
    model_validator,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        allow_inf_nan=False,
    )


class EconomicStrictModel(StrictModel):
    """Immutable base for canonical AEEP 0.4 economic records."""

    model_config = ConfigDict(frozen=True, validate_default=True)


class ExecutorKind(StrEnum):
    COMMAND = "command"
    PYTHON = "python"
    HTTP = "http"
    MCP = "mcp"
    HOST = "host"
    DELEGATE = "delegate"


class SideEffect(StrEnum):
    NONE = "none"
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"
    FINANCIAL = "financial"

    @property
    def rank(self) -> int:
        return {
            SideEffect.NONE: 0,
            SideEffect.READ: 1,
            SideEffect.WRITE: 2,
            SideEffect.DESTRUCTIVE: 3,
            SideEffect.FINANCIAL: 4,
        }[self]


class Locality(StrEnum):
    IN_PROCESS = "in_process"
    LOCAL = "local"
    LAN = "lan"
    INTERNET = "internet"


class DataSensitivity(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class ExecutionStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    REJECTED = "rejected"
    HOST_SELECTED = "host_selected"
    DELEGATED = "delegated"
    UNKNOWN = "unknown"


class EstimateSource(StrEnum):
    STATIC = "static"
    HISTORICAL = "historical"
    BLENDED = "blended"
    QUOTE = "quote"
    OBSERVED = "observed"


class QuotaState(StrEnum):
    """Private opportunity-cost signal for a non-transferable subscription."""

    ABUNDANT = "abundant"
    NORMAL = "normal"
    TIGHT = "tight"
    CRITICAL = "critical"
    EXHAUSTED = "exhausted"
    UNKNOWN = "unknown"

    @property
    def pressure(self) -> float:
        return {
            QuotaState.ABUNDANT: 0.10,
            QuotaState.NORMAL: 0.50,
            QuotaState.TIGHT: 2.0,
            QuotaState.CRITICAL: 8.0,
            QuotaState.EXHAUSTED: float("inf"),
            QuotaState.UNKNOWN: 1.0,
        }[self]


class QuotaSource(StrEnum):
    USER = "user"
    HOST = "host"
    OFFICIAL_CLI = "official_cli"
    RATE_LIMIT = "rate_limit"
    HEURISTIC = "heuristic"
    OBSERVED = "observed"


class TrustLevel(StrEnum):
    UNTRUSTED = "untrusted"
    SELF_ASSERTED = "self_asserted"
    OBSERVED = "observed"
    VERIFIED = "verified"
    ATTESTED = "attested"


class EvidenceStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    CONFLICT = "conflict"
    UNAVAILABLE = "unavailable"


class EvidenceSource(StrEnum):
    BILLING_RECORD = "billing_record"
    LOCAL_METER = "local_meter"
    PRICED_MEASURED_BILLABLE_USAGE = "priced_measured_billable_usage"
    CONFIRMED_NO_INCREMENTAL_CHARGE = "confirmed_no_incremental_charge"
    PROVIDER_REPORT = "provider_report"
    PINNED_RATE_TABLE = "pinned_rate_table"
    OPERATOR_REPORT = "operator_report"
    STATIC_ESTIMATE = "static_estimate"
    LEGACY_UNSPECIFIED = "legacy_unspecified"
    UNAVAILABLE = "unavailable"


class CashClassification(StrEnum):
    VERIFIED = "verified"
    BILLING_RECONCILED = "billing_reconciled"
    PINNED_RATE_BILLABLE_USAGE = "pinned_rate_billable_usage"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"


class SubscriptionCharge(StrEnum):
    INCLUDED = "included"
    PAID = "paid"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class ModelAccessChannel(StrEnum):
    API = "api"
    SUBSCRIPTION = "subscription"
    PURCHASED_CREDIT = "purchased_credit"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class MeasurementEvidence(StrictModel):
    status: EvidenceStatus = EvidenceStatus.UNAVAILABLE
    source: EvidenceSource = EvidenceSource.UNAVAILABLE
    trust: TrustLevel = TrustLevel.UNTRUSTED
    evidence_id: str | None = Field(default=None, max_length=200)
    source_reference: str | None = Field(default=None, max_length=500)
    digest: str | None = Field(default=None, pattern=r"^[A-Fa-f0-9]{64}$")
    observed_at: datetime | None = None

    @model_validator(mode="after")
    def consistent_availability(self) -> MeasurementEvidence:
        if self.status == EvidenceStatus.UNAVAILABLE and self.source != EvidenceSource.UNAVAILABLE:
            raise ValueError("unavailable evidence must use source=unavailable")
        if self.status != EvidenceStatus.UNAVAILABLE and self.source == EvidenceSource.UNAVAILABLE:
            raise ValueError("available evidence requires a source")
        return self


def unavailable_evidence() -> MeasurementEvidence:
    return MeasurementEvidence()


class CashEstimate(StrictModel):
    amount_usd: Decimal | None = Field(default=None, ge=0)
    upper_bound_usd: Decimal | None = Field(default=None, ge=0)
    evidence: MeasurementEvidence = Field(default_factory=unavailable_evidence)

    @model_validator(mode="after")
    def valid_bounds(self) -> CashEstimate:
        if self.amount_usd is not None and self.evidence.status == EvidenceStatus.UNAVAILABLE:
            raise ValueError("a cash amount requires evidence")
        if self.upper_bound_usd is not None and self.evidence.status == EvidenceStatus.UNAVAILABLE:
            raise ValueError("a cash upper bound requires evidence")
        if (
            self.amount_usd is not None
            and self.upper_bound_usd is not None
            and self.upper_bound_usd < self.amount_usd
        ):
            raise ValueError("upper_bound_usd must be >= amount_usd")
        return self


class CashEvidence(StrictModel):
    charge_id: str = Field(min_length=1, max_length=200)
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    classification: CashClassification = CashClassification.UNAVAILABLE
    evidence: MeasurementEvidence = Field(default_factory=unavailable_evidence)
    rate_snapshot_id: str | None = Field(default=None, max_length=100)
    billing_record_id: str | None = Field(default=None, max_length=200)
    usage_fingerprint: str | None = Field(default=None, max_length=128)
    applied_rate_ids: list[str] = Field(default_factory=list)
    applied_meter_quantities: dict[str, Decimal] = Field(default_factory=dict)

    @model_validator(mode="after")
    def consistent_amount(self) -> CashEvidence:
        unavailable = self.classification == CashClassification.UNAVAILABLE
        if unavailable != (self.amount is None):
            raise ValueError("unavailable cash must omit amount; known cash must include amount")
        if self.amount is not None and self.evidence.status == EvidenceStatus.UNAVAILABLE:
            raise ValueError("known cash requires evidence")
        if (
            self.classification == CashClassification.PINNED_RATE_BILLABLE_USAGE
            and not self.rate_snapshot_id
        ):
            raise ValueError("priced billable usage requires rate_snapshot_id")
        return self


_CASH_CLASSIFICATION_STRENGTH = {
    CashClassification.ESTIMATED: 1,
    CashClassification.PINNED_RATE_BILLABLE_USAGE: 2,
    CashClassification.VERIFIED: 3,
    CashClassification.BILLING_RECONCILED: 4,
}


def _strongest_cash_evidence(group: list[CashEvidence]) -> list[CashEvidence]:
    known = [
        item
        for item in group
        if item.amount is not None and item.classification != CashClassification.UNAVAILABLE
    ]
    if not known:
        return []
    strongest = max(_CASH_CLASSIFICATION_STRENGTH[item.classification] for item in known)
    return [
        item
        for item in known
        if _CASH_CLASSIFICATION_STRENGTH[item.classification] == strongest
    ]


class CashAccounting(StrictModel):
    status: EvidenceStatus = EvidenceStatus.UNAVAILABLE
    components: list[CashEvidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def detect_conflicts(self) -> CashAccounting:
        if self.status == EvidenceStatus.COMPLETE and not self.components:
            raise ValueError("complete cash accounting requires at least one charge component")
        for charge_id in {item.charge_id for item in self.components}:
            choices = _strongest_cash_evidence(
                [
                    item
                    for item in self.components
                    if item.charge_id == charge_id
                ]
            )
            if len({(item.amount, item.currency) for item in choices}) > 1:
                object.__setattr__(self, "status", EvidenceStatus.CONFLICT)
        return self

    def resolved_components(self) -> list[CashEvidence]:
        """Return the strongest non-conflicting evidence for each charge."""
        resolved: list[CashEvidence] = []
        for charge_id in dict.fromkeys(item.charge_id for item in self.components):
            choices = _strongest_cash_evidence(
                [
                    item
                    for item in self.components
                    if item.charge_id == charge_id
                ]
            )
            if len({(item.amount, item.currency) for item in choices}) == 1:
                resolved.append(choices[0])
        return resolved

    def known_subtotal(self, currency: str = "USD") -> Decimal:
        return sum(
            (
                item.amount or Decimal(0)
                for item in self.resolved_components()
                if item.currency == currency
            ),
            Decimal(0),
        )

    def actual_cash_cost(self, currency: str = "USD") -> Decimal | None:
        if self.status != EvidenceStatus.COMPLETE or not self.components:
            return None
        resolved = self.resolved_components()
        if len(resolved) != len({item.charge_id for item in self.components}):
            return None
        eligible = {
            CashClassification.VERIFIED,
            CashClassification.BILLING_RECONCILED,
            CashClassification.PINNED_RATE_BILLABLE_USAGE,
        }
        if any(
            item.classification not in eligible or item.currency != currency for item in resolved
        ):
            return None
        if (not resolved or all(item.amount == 0 for item in resolved)) and (
            not resolved
            or any(
                item.classification
                not in {CashClassification.VERIFIED, CashClassification.BILLING_RECONCILED}
                for item in resolved
            )
        ):
            return None
        return sum((item.amount or Decimal(0) for item in resolved), Decimal(0))


class SubscriptionUsage(StrictModel):
    provider: str = Field(min_length=1, max_length=100)
    resource_pool: str = Field(min_length=1, max_length=200)
    unit: str = Field(default="provider_unit", min_length=1, max_length=100)
    consumed: Decimal | None = Field(default=None, ge=0)
    source: MeasurementEvidence = Field(default_factory=unavailable_evidence)
    included_or_paid: SubscriptionCharge = SubscriptionCharge.UNKNOWN
    rate_snapshot_id: str | None = Field(default=None, max_length=100)
    usage_fingerprint: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def known_usage_has_source(self) -> SubscriptionUsage:
        if self.consumed is not None and self.source.status == EvidenceStatus.UNAVAILABLE:
            raise ValueError("known subscription usage requires evidence")
        return self


class ModelTokenUsage(StrictModel):
    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=200)
    access_channel: ModelAccessChannel = ModelAccessChannel.UNKNOWN
    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    cache_write_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    reasoning_output_tokens: int = Field(default=0, ge=0)
    evidence: MeasurementEvidence = Field(default_factory=unavailable_evidence)

    @model_validator(mode="after")
    def valid_subsets(self) -> ModelTokenUsage:
        if self.cached_input_tokens + self.cache_write_input_tokens > self.input_tokens:
            raise ValueError("cached and cache-write input tokens cannot exceed input_tokens")
        if self.reasoning_output_tokens > self.output_tokens:
            raise ValueError("reasoning_output_tokens cannot exceed output_tokens")
        return self


class ToolFootprint(StrictModel):
    schema_bytes: int = Field(default=0, ge=0)
    schema_approx_tokens: int = Field(default=0, ge=0)
    raw_result_bytes: int = Field(default=0, ge=0)
    raw_result_approx_tokens: int = Field(default=0, ge=0)
    filtered_result_bytes: int = Field(default=0, ge=0)
    filtered_result_approx_tokens: int = Field(default=0, ge=0)
    exposed_to_model: bool = False


class ResourceAccounting(StrictModel):
    cash: CashAccounting = Field(default_factory=CashAccounting)
    subscription_usage: list[SubscriptionUsage] = Field(default_factory=list)
    model_usage: list[ModelTokenUsage] = Field(default_factory=list)
    tool_footprint: ToolFootprint | None = None


class CounterfactualCashCost(StrictModel):
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    basis: Literal["api_equivalent"] = "api_equivalent"
    rate_snapshot_id: str
    provider: str
    model: str
    usage_fingerprint: str
    applied_rate_ids: list[str] = Field(default_factory=list)
    applied_meter_quantities: dict[str, Decimal] = Field(default_factory=dict)
    status: EvidenceStatus = EvidenceStatus.UNAVAILABLE


class PolicyValuation(StrictModel):
    amount: Decimal = Field(ge=0)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    policy_id: str = Field(min_length=1, max_length=200)
    resource_pool: str | None = Field(default=None, max_length=200)
    unit: str | None = Field(default=None, max_length=100)
    explanation: str = Field(default="", max_length=1000)


class ValidationKind(StrEnum):
    SCHEMA = "schema"
    EXACT_MATCH = "exact_match"
    RANGE = "range"
    STATE_TRANSITION = "state_transition"
    CALLBACK = "callback"
    DOWNSTREAM = "downstream"
    LLM = "llm"
    HUMAN = "human"


class SubscriptionQuota(StrictModel):
    state: QuotaState = QuotaState.UNKNOWN
    reset_at: datetime | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: QuotaSource = QuotaSource.USER
    unit: str = Field(default="provider_unit", min_length=1, max_length=100)
    allowance_units: Decimal | None = Field(default=None, ge=0)
    remaining_units: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def valid_allowance(self) -> SubscriptionQuota:
        if (
            self.allowance_units is not None
            and self.remaining_units is not None
            and self.remaining_units > self.allowance_units
        ):
            raise ValueError("remaining_units cannot exceed allowance_units")
        return self


class SubscriptionAccess(StrictModel):
    mode: Literal["host", "cli", "mcp"] = "host"


class SubscriptionCapabilities(StrictModel):
    reasoning: bool = False
    coding: bool = False
    browser: bool = False
    computer_use: bool = False
    custom: list[str] = Field(default_factory=list)


class SubscriptionResource(StrictModel):
    """A resource the user already owns; it is never represented as money."""

    id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:-]+$")
    kind: Literal["subscription"] = "subscription"
    provider: str = Field(min_length=1, max_length=100)
    product: str = Field(min_length=1, max_length=100)
    unit: str = Field(default="provider_unit", min_length=1, max_length=100)
    access: SubscriptionAccess = Field(default_factory=SubscriptionAccess)
    quota: SubscriptionQuota = Field(default_factory=SubscriptionQuota)
    capabilities: SubscriptionCapabilities = Field(default_factory=SubscriptionCapabilities)

    @model_validator(mode="after")
    def align_quota_unit(self) -> SubscriptionResource:
        if self.quota.unit == "provider_unit":
            self.quota.unit = self.unit
        elif self.quota.unit != self.unit:
            raise ValueError("subscription quota unit must match resource unit")
        return self


class QuotaObservation(StrictModel):
    observation_id: str = Field(default_factory=lambda: new_id("quota"))
    resource_id: str = Field(min_length=1, max_length=200)
    quota: SubscriptionQuota
    observed_at: datetime = Field(default_factory=utc_now)
    note: str | None = Field(default=None, max_length=1000)


class CapabilityDefinition(StrictModel):
    namespace: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    version: str = Field(default="1", pattern=r"^[0-9]+(?:\.[0-9]+){0,2}$")
    authority: str | None = Field(
        default=None,
        max_length=500,
        description="Domain, URI, or organization responsible for the canonical contract.",
    )
    owner: str | None = Field(default=None, max_length=200)
    status: Literal["active", "deprecated"] = "active"
    replaced_by: str | None = Field(default=None, max_length=200)
    compatible_versions: list[str] = Field(default_factory=list)
    description: str = Field(min_length=1, max_length=4000)
    input_schema: dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "additionalProperties": True}
    )
    output_schema: dict[str, Any] | None = None
    side_effect: SideEffect = SideEffect.READ

    @property
    def capability(self) -> str:
        return f"{self.namespace}.{self.name}@{self.version}"

    @model_validator(mode="after")
    def valid_lifecycle(self) -> CapabilityDefinition:
        if self.status == "active" and self.replaced_by is not None:
            raise ValueError("only deprecated capabilities can declare replaced_by")
        if self.replaced_by == self.capability:
            raise ValueError("capability cannot replace itself")
        return self


class ValidationSpec(StrictModel):
    kind: ValidationKind
    config: dict[str, Any] = Field(default_factory=dict)
    required: bool = True


class ValidationResult(StrictModel):
    kind: ValidationKind
    valid: bool | None = None
    quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    detail: str = Field(default="", max_length=4096)
    trust: TrustLevel = TrustLevel.OBSERVED


class SignatureEnvelope(StrictModel):
    algorithm: Literal["hmac-sha256"] = "hmac-sha256"
    key_id: str = Field(min_length=1, max_length=200)
    value: str = Field(pattern=r"^[A-Za-z0-9_-]+$")


class ResourceVector(StrictModel):
    """Raw resource dimensions for one attempt.

    `memory_mb_seconds` is the integral of route-attributable resident memory
    over time. `peak_memory_mb` is retained separately because it is useful as a
    hard capacity constraint rather than only a consumable-resource signal.
    """

    monetary_usd: float = Field(default=0.0, ge=0.0)
    latency_ms: float = Field(default=0.0, ge=0.0)
    cpu_ms: float = Field(default=0.0, ge=0.0)
    memory_mb_seconds: float = Field(default=0.0, ge=0.0)
    peak_memory_mb: float = Field(default=0.0, ge=0.0)
    gpu_ms: float = Field(default=0.0, ge=0.0)
    network_bytes: int = Field(default=0, ge=0)
    context_tokens: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    subscription_units: float = Field(
        default=0.0,
        ge=0.0,
        description="Provider-local capacity units; not cash and not transferable.",
    )

    def plus(self, other: ResourceVector) -> ResourceVector:
        return ResourceVector(
            **{
                field: getattr(self, field) + getattr(other, field)
                for field in type(self).model_fields
            }
        )

    def scale(self, factor: float) -> ResourceVector:
        values: dict[str, float | int] = {}
        integer_fields = {
            "network_bytes",
            "context_tokens",
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
        }
        for field in type(self).model_fields:
            value = getattr(self, field) * factor
            values[field] = round(value) if field in integer_fields else float(value)
        return ResourceVector.model_validate(values)


class RouteEstimate(StrictModel):
    resources: ResourceVector = Field(default_factory=ResourceVector)
    cash: CashEstimate = Field(default_factory=CashEstimate)
    subscription_usage: list[SubscriptionUsage] = Field(default_factory=list)
    success_probability: float = Field(default=0.95, ge=0.001, le=1.0)
    quality_score: float = Field(default=0.95, ge=0.0, le=1.0)
    risk_score: float = Field(default=0.05, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: EstimateSource = EstimateSource.STATIC
    sample_size: int = Field(default=0, ge=0)

    @model_validator(mode="before")
    @classmethod
    def migrate_explicit_legacy_cost(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "cash" in value:
            return value
        resources = value.get("resources")
        explicit: Decimal | None = None
        if isinstance(resources, dict) and "monetary_usd" in resources:
            explicit = Decimal(str(resources["monetary_usd"]))
        elif isinstance(resources, ResourceVector) and "monetary_usd" in resources.model_fields_set:
            explicit = Decimal(str(resources.monetary_usd))
        if explicit is not None:
            amount = explicit
            value = dict(value)
            value["cash"] = {
                "amount_usd": amount,
                "upper_bound_usd": amount,
                "evidence": {
                    "status": "complete",
                    "source": "static_estimate",
                    "trust": "self_asserted",
                },
            }
        return value


class ComputeAvailability(StrictModel):
    """Resources available to the caller at routing time.

    These values are optional because agents often know context-window or quota
    headroom that the local process cannot detect.
    """

    available_memory_mb: float | None = Field(default=None, gt=0)
    available_cpu_fraction: float | None = Field(default=None, gt=0.0, le=1.0)
    available_gpu_ms: float | None = Field(default=None, ge=0.0)
    context_tokens_remaining: int | None = Field(default=None, ge=0)
    monetary_budget_remaining_usd: float | None = Field(default=None, ge=0.0)
    network_metered: bool = False


class ActionContext(StrictModel):
    data_sensitivity: DataSensitivity = DataSensitivity.INTERNAL
    state_locality: Locality | None = None
    preferred_region: str | None = None
    compute: ComputeAvailability = Field(default_factory=ComputeAvailability)
    labels: dict[str, str] = Field(default_factory=dict)
    traceparent: str | None = None
    subscription_quotas: dict[str, SubscriptionQuota] = Field(default_factory=dict)


class ActionConstraints(StrictModel):
    max_cost_usd: float | None = Field(default=None, ge=0.0)
    max_latency_ms: float | None = Field(default=None, ge=0.0)
    max_cpu_ms: float | None = Field(default=None, ge=0.0)
    max_memory_mb_seconds: float | None = Field(default=None, ge=0.0)
    max_peak_memory_mb: float | None = Field(default=None, ge=0.0)
    max_gpu_ms: float | None = Field(default=None, ge=0.0)
    max_network_bytes: int | None = Field(default=None, ge=0)
    max_context_tokens: int | None = Field(default=None, ge=0)
    min_success_probability: float = Field(default=0.70, ge=0.0, le=1.0)
    min_quality_score: float = Field(default=0.50, ge=0.0, le=1.0)
    max_risk_score: float = Field(default=0.50, ge=0.0, le=1.0)
    max_side_effect: SideEffect = SideEffect.READ
    allow_network: bool = True
    require_local: bool = False
    allowed_executor_kinds: list[ExecutorKind] | None = None
    allowed_executor_ids: list[str] | None = None
    denied_executor_ids: list[str] = Field(default_factory=list)
    allowed_data_residency: list[str] | None = None


class ActionRequest(StrictModel):
    action_id: str = Field(default_factory=lambda: new_id("act"))
    capability: str = Field(min_length=1, max_length=200)
    input: dict[str, Any] = Field(default_factory=dict)
    policy: str = "balanced"
    constraints: ActionConstraints = Field(default_factory=ActionConstraints)
    context: ActionContext = Field(default_factory=ActionContext)
    idempotency_key: str | None = Field(default=None, max_length=256)


class ActionFeatures(StrictModel):
    """Non-payload characteristics used to condition historical estimates."""

    input_bytes: int = Field(ge=0)
    input_items: int = Field(ge=0)
    text_characters: int = Field(ge=0)
    max_depth: int = Field(ge=0)
    size_bucket: str = Field(pattern=r"^(empty|2\^[0-9]+)$")


_IDENTIFIER_PATTERN = r"^[A-Za-z0-9_.:-]+$"
_CAPABILITY_PATTERN = r"^[a-z0-9][a-z0-9_.-]*@[0-9]+(?:\.[0-9]+){0,2}$"
_FINGERPRINT_PATTERN = r"^sha256:[a-f0-9]{64}$"
_DECIMAL_JSON_SCHEMA = {
    "type": "string",
    "pattern": r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$",
}
_STANDARD_METERS = frozenset(
    {
        "browser_minutes",
        "bytes",
        "compute_seconds",
        "input_tokens",
        "output_tokens",
        "pages",
        "records",
        "requests",
        "seconds",
    }
)


def _nonnegative_decimal(value: Any) -> Decimal:
    if isinstance(value, bool | float):
        raise ValueError("economic decimals do not accept binary floating-point values")
    if isinstance(value, str) and (not value or value != value.strip()):
        raise ValueError("economic decimal strings must be canonical tokens")
    if not isinstance(value, Decimal | int | str):
        raise ValueError("economic decimals require a Decimal, integer, or decimal string")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid economic decimal") from exc
    if not parsed.is_finite():
        raise ValueError("economic decimals must be finite")
    if parsed < 0:
        raise ValueError("economic decimals cannot be negative")
    return parsed.copy_abs() if parsed.is_zero() else parsed


def _finite_decimal(value: Any) -> Decimal:
    if isinstance(value, bool | float):
        raise ValueError("economic decimals do not accept binary floating-point values")
    if isinstance(value, str) and (not value or value != value.strip()):
        raise ValueError("economic decimal strings must be canonical tokens")
    if not isinstance(value, Decimal | int | str):
        raise ValueError("economic decimals require a Decimal, integer, or decimal string")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid economic decimal") from exc
    if not parsed.is_finite():
        raise ValueError("economic decimals must be finite")
    return parsed.copy_abs() if parsed.is_zero() else parsed


def _positive_decimal(value: Any) -> Decimal:
    parsed = _nonnegative_decimal(value)
    if parsed == 0:
        raise ValueError("value must be greater than zero")
    return parsed


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("economic timestamps must be timezone-aware")
    return value.astimezone(UTC)


NonNegativeDecimal = Annotated[
    Decimal,
    BeforeValidator(_nonnegative_decimal),
    PlainSerializer(_decimal_text, return_type=str, when_used="json"),
    WithJsonSchema(_DECIMAL_JSON_SCHEMA),
]
FiniteDecimal = Annotated[
    Decimal,
    BeforeValidator(_finite_decimal),
    PlainSerializer(_decimal_text, return_type=str, when_used="json"),
    WithJsonSchema(
        {
            "type": "string",
            "pattern": r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$",
        }
    ),
]
PositiveDecimal = Annotated[
    Decimal,
    BeforeValidator(_positive_decimal),
    PlainSerializer(_decimal_text, return_type=str, when_used="json"),
    WithJsonSchema({**_DECIMAL_JSON_SCHEMA, "pattern": r"^(?:0\.[0-9]*[1-9][0-9]*|[1-9][0-9]*(?:\.[0-9]+)?)$"}),
]
UtcDateTime = Annotated[datetime, AfterValidator(_aware_utc)]
JsonPrimitive: TypeAlias = str | int | bool | None


class SignatureAlgorithm(StrEnum):
    HMAC_SHA256 = "hmac-sha256"
    ED25519 = "ed25519"


class SignatureEnvelopeV2(EconomicStrictModel):
    algorithm: SignatureAlgorithm
    key_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    value: str = Field(min_length=1, max_length=4096, pattern=r"^[A-Za-z0-9_-]+$")
    canonicalization_version: Literal["aeep-canonical-json-v1"] = "aeep-canonical-json-v1"


class EconomicEvidenceLevel(StrEnum):
    UNKNOWN = "UNKNOWN"
    STATIC_PRIOR = "STATIC_PRIOR"
    PUBLISHED_OFFER = "PUBLISHED_OFFER"
    SIGNED_QUOTE = "SIGNED_QUOTE"
    SIGNED_USAGE_STATEMENT = "SIGNED_USAGE_STATEMENT"
    PAYMENT_SETTLEMENT = "PAYMENT_SETTLEMENT"
    BILLING_RECONCILED = "BILLING_RECONCILED"
    OPERATOR_ATTESTED = "OPERATOR_ATTESTED"

    @property
    def rank(self) -> int:
        # Operator attestation is useful actual-cost evidence, but it is not
        # payment-rail or billing proof. Keep the ordering explicit so enum
        # declaration order can never promote it above verified settlement.
        return {
            EconomicEvidenceLevel.UNKNOWN: 0,
            EconomicEvidenceLevel.STATIC_PRIOR: 10,
            EconomicEvidenceLevel.PUBLISHED_OFFER: 20,
            EconomicEvidenceLevel.SIGNED_QUOTE: 30,
            EconomicEvidenceLevel.SIGNED_USAGE_STATEMENT: 40,
            EconomicEvidenceLevel.OPERATOR_ATTESTED: 45,
            EconomicEvidenceLevel.PAYMENT_SETTLEMENT: 50,
            EconomicEvidenceLevel.BILLING_RECONCILED: 60,
        }[self]

    @property
    def is_payment_evidence(self) -> bool:
        """Whether this level proves settlement or external billing evidence."""

        return self in {
            EconomicEvidenceLevel.PAYMENT_SETTLEMENT,
            EconomicEvidenceLevel.BILLING_RECONCILED,
        }


class AuthorizationKind(StrEnum):
    """Immutable economic basis for a maximum cash authorization."""

    SIGNED_QUOTE = "SIGNED_QUOTE"
    PUBLISHED_OFFER = "PUBLISHED_OFFER"
    PINNED_RATE_CARD = "PINNED_RATE_CARD"


def _migrate_quote_authorization(value: Any, quote_field: str) -> Any:
    """Make legacy quote-bound 0.4 records explicit without weakening their binding."""

    if not isinstance(value, dict):
        return value
    if value.get("authorization_kind") is not None or value.get("authorization_id") is not None:
        return value
    quote_id = value.get(quote_field)
    if quote_id is None:
        return value
    migrated = dict(value)
    migrated["authorization_kind"] = AuthorizationKind.SIGNED_QUOTE
    migrated["authorization_id"] = quote_id
    return migrated


class BillingTrigger(StrEnum):
    ON_SUCCESS = "ON_SUCCESS"
    ON_ATTEMPT = "ON_ATTEMPT"
    ON_ACCEPTED_RESULT = "ON_ACCEPTED_RESULT"
    ON_PROVIDER_START = "ON_PROVIDER_START"
    MANUAL_RECONCILIATION = "MANUAL_RECONCILIATION"


class FailureChargePolicy(StrEnum):
    NO_CHARGE = "NO_CHARGE"
    CHARGE_ACTUAL_USAGE = "CHARGE_ACTUAL_USAGE"
    CHARGE_FIXED_ATTEMPT_FEE = "CHARGE_FIXED_ATTEMPT_FEE"
    CHARGE_MAXIMUM = "CHARGE_MAXIMUM"
    MANUAL_RECONCILIATION = "MANUAL_RECONCILIATION"


class RetryChargePolicy(StrEnum):
    EACH_ATTEMPT = "EACH_ATTEMPT"
    FIRST_ATTEMPT_ONLY = "FIRST_ATTEMPT_ONLY"
    SUCCESSFUL_ATTEMPT_ONLY = "SUCCESSFUL_ATTEMPT_ONLY"
    MANUAL_RECONCILIATION = "MANUAL_RECONCILIATION"


class PricingRoundingMode(StrEnum):
    UP = "ROUND_UP"
    DOWN = "ROUND_DOWN"
    CEILING = "ROUND_CEILING"
    FLOOR = "ROUND_FLOOR"
    HALF_UP = "ROUND_HALF_UP"
    HALF_EVEN = "ROUND_HALF_EVEN"

    @property
    def decimal_mode(self) -> str:
        return {
            PricingRoundingMode.UP: ROUND_UP,
            PricingRoundingMode.DOWN: ROUND_DOWN,
            PricingRoundingMode.CEILING: ROUND_CEILING,
            PricingRoundingMode.FLOOR: ROUND_FLOOR,
            PricingRoundingMode.HALF_UP: ROUND_HALF_UP,
            PricingRoundingMode.HALF_EVEN: ROUND_HALF_EVEN,
        }[self]


class CurrencyAmount(EconomicStrictModel):
    amount: NonNegativeDecimal
    currency: str = Field(pattern=r"^[A-Z]{3}$")

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: Any) -> str:
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z]{3}", value):
            raise ValueError("currency must be a three-letter code")
        return value.upper()

    def require_currency(self, currency: str) -> None:
        if self.currency != currency:
            raise ValueError(f"currency mismatch: expected {currency}, got {self.currency}")


class MeterQuantity(EconomicStrictModel):
    meter: str = Field(min_length=1, max_length=200, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    unit: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_.-]*$")
    quantity: NonNegativeDecimal

    @field_validator("meter")
    @classmethod
    def namespace_custom_meter(cls, value: str) -> str:
        if value not in _STANDARD_METERS and "." not in value:
            raise ValueError("provider-defined meters must be namespaced")
        return value


class AuthorizationMeterQuantity(MeterQuantity):
    """One pinned rate-card rate and the bounded native quantity it prices."""

    rate_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)


class PricingRule(EconomicStrictModel):
    rule_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    meter: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
    )
    unit: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_.-]*$",
    )
    fixed_amount: CurrencyAmount | None = None
    per_unit_amount: CurrencyAmount | None = None
    free_quantity: NonNegativeDecimal | None = None
    minimum_amount: CurrencyAmount | None = None
    maximum_amount: CurrencyAmount | None = None
    rounding_mode: PricingRoundingMode = PricingRoundingMode.CEILING
    quantity_increment: PositiveDecimal | None = None

    _ROUNDING: ClassVar[dict[PricingRoundingMode, str]] = {
        mode: mode.decimal_mode for mode in PricingRoundingMode
    }

    @model_validator(mode="after")
    def valid_rule(self) -> PricingRule:
        if self.fixed_amount is None and self.per_unit_amount is None:
            raise ValueError("pricing rule requires a fixed or per-unit amount")
        metered = self.per_unit_amount is not None
        if metered != (self.meter is not None and self.unit is not None):
            raise ValueError("per-unit pricing requires both meter and unit")
        if not metered and (self.free_quantity is not None or self.quantity_increment is not None):
            raise ValueError("free quantity and quantity increment require per-unit pricing")
        amounts = [
            amount
            for amount in (
                self.fixed_amount,
                self.per_unit_amount,
                self.minimum_amount,
                self.maximum_amount,
            )
            if amount is not None
        ]
        currencies = {amount.currency for amount in amounts}
        if len(currencies) != 1:
            raise ValueError("all pricing-rule amounts must use one currency")
        if (
            self.minimum_amount is not None
            and self.maximum_amount is not None
            and self.minimum_amount.amount > self.maximum_amount.amount
        ):
            raise ValueError("minimum amount cannot exceed maximum amount")
        return self

    @property
    def currency(self) -> str:
        for amount in (self.fixed_amount, self.per_unit_amount):
            if amount is not None:
                return amount.currency
        raise AssertionError("validated pricing rule has no amount")

    def evaluate(self, quantity: Decimal | int | str = 0) -> CurrencyAmount:
        measured = _nonnegative_decimal(quantity)
        total = self.fixed_amount.amount if self.fixed_amount is not None else Decimal(0)
        if self.per_unit_amount is not None:
            billable = max(Decimal(0), measured - (self.free_quantity or Decimal(0)))
            if self.quantity_increment is not None:
                increments = (billable / self.quantity_increment).to_integral_value(
                    rounding=self._ROUNDING[self.rounding_mode]
                )
                billable = increments * self.quantity_increment
            total += billable * self.per_unit_amount.amount
        if self.minimum_amount is not None:
            total = max(total, self.minimum_amount.amount)
        if self.maximum_amount is not None:
            total = min(total, self.maximum_amount.amount)
        return CurrencyAmount(amount=total, currency=self.currency)


def _unique_meters(values: tuple[MeterQuantity, ...]) -> tuple[MeterQuantity, ...]:
    keys = [(item.meter, item.unit) for item in values]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate meter-and-unit pair")
    return values


class CapabilityOffer(EconomicStrictModel):
    schema_version: Literal["0.4"] = "0.4"
    offer_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    provider_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    capability: str = Field(min_length=3, max_length=200, pattern=_CAPABILITY_PATTERN)
    executor_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    executor_fingerprint: str = Field(pattern=_FINGERPRINT_PATTERN)
    pricing_rules: tuple[PricingRule, ...] = Field(min_length=1)
    billing_trigger: BillingTrigger
    failure_charge_policy: FailureChargePolicy
    retry_charge_policy: RetryChargePolicy
    fixed_attempt_fee: CurrencyAmount | None = None
    region: str | None = Field(default=None, max_length=100)
    account_tier: str | None = Field(default=None, max_length=100)
    settlement_currency: str = Field(pattern=r"^[A-Z]{3}$")
    valid_from: UtcDateTime
    valid_until: UtcDateTime
    terms_digest: str = Field(pattern=_FINGERPRINT_PATTERN)
    issued_at: UtcDateTime
    signature: SignatureEnvelopeV2

    @field_validator("settlement_currency", mode="before")
    @classmethod
    def normalize_settlement_currency(cls, value: Any) -> str:
        return CurrencyAmount.normalize_currency(value)

    @model_validator(mode="after")
    def valid_offer(self) -> CapabilityOffer:
        if self.valid_until <= self.valid_from:
            raise ValueError("offer valid_until must be later than valid_from")
        if self.issued_at > self.valid_until:
            raise ValueError("offer cannot be issued after it expires")
        rule_ids = [rule.rule_id for rule in self.pricing_rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("duplicate pricing rule ID")
        if any(rule.currency != self.settlement_currency for rule in self.pricing_rules):
            raise ValueError("pricing-rule currency must match settlement currency")
        requires_attempt_fee = (
            self.failure_charge_policy is FailureChargePolicy.CHARGE_FIXED_ATTEMPT_FEE
        )
        if requires_attempt_fee != (self.fixed_attempt_fee is not None):
            raise ValueError(
                "fixed attempt fee is required only for CHARGE_FIXED_ATTEMPT_FEE"
            )
        if (
            self.fixed_attempt_fee is not None
            and self.fixed_attempt_fee.currency != self.settlement_currency
        ):
            raise ValueError("fixed attempt fee currency must match settlement currency")
        return self

    def valid_at(self, at: datetime) -> bool:
        instant = _aware_utc(at)
        return self.valid_from <= instant < self.valid_until


class QuoteRequestV2(EconomicStrictModel):
    schema_version: Literal["0.4"] = "0.4"
    quote_request_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    action_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    capability: str = Field(min_length=3, max_length=200, pattern=_CAPABILITY_PATTERN)
    executor_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    executor_fingerprint: str = Field(pattern=_FINGERPRINT_PATTERN)
    action_digest: str = Field(pattern=_FINGERPRINT_PATTERN)
    input_features: ActionFeatures
    disclosed_quote_features: dict[str, JsonPrimitive] = Field(default_factory=dict)
    desired_currency: str = Field(pattern=r"^[A-Z]{3}$")
    maximum_acceptable_amount: CurrencyAmount | None = None
    nonce: str = Field(min_length=8, max_length=256, pattern=r"^[A-Za-z0-9_-]+$")
    created_at: UtcDateTime
    expires_at: UtcDateTime

    @field_validator("desired_currency", mode="before")
    @classmethod
    def normalize_desired_currency(cls, value: Any) -> str:
        return CurrencyAmount.normalize_currency(value)

    @field_validator("disclosed_quote_features", mode="before")
    @classmethod
    def bounded_disclosure(cls, value: Any) -> Any:
        if not isinstance(value, dict) or len(value) > 64:
            raise ValueError("quote disclosure must be an object with at most 64 fields")
        for key, item in value.items():
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", key):
                raise ValueError("quote disclosure names must be bounded identifiers")
            if isinstance(item, float | list | dict) or not isinstance(
                item, str | int | bool | type(None)
            ):
                raise ValueError("quote disclosure values must be JSON primitives without floats")
            if isinstance(item, str) and len(item) > 128:
                raise ValueError("quote disclosure string values must be bounded")
        return value

    @model_validator(mode="after")
    def valid_request(self) -> QuoteRequestV2:
        if self.expires_at <= self.created_at:
            raise ValueError("quote request must expire after creation")
        if (
            self.maximum_acceptable_amount is not None
            and self.maximum_acceptable_amount.currency != self.desired_currency
        ):
            raise ValueError("maximum acceptable amount currency does not match desired currency")
        return self


class BoundedQuote(EconomicStrictModel):
    schema_version: Literal["0.4"] = "0.4"
    quote_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    quote_request_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    offer_id: str | None = Field(default=None, max_length=200, pattern=_IDENTIFIER_PATTERN)
    provider_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    capability: str = Field(min_length=3, max_length=200, pattern=_CAPABILITY_PATTERN)
    executor_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    executor_fingerprint: str = Field(pattern=_FINGERPRINT_PATTERN)
    action_digest: str = Field(pattern=_FINGERPRINT_PATTERN)
    nonce: str = Field(min_length=8, max_length=256, pattern=r"^[A-Za-z0-9_-]+$")
    expected_amount: CurrencyAmount | None = None
    maximum_amount: CurrencyAmount
    estimated_meters: tuple[MeterQuantity, ...] = ()
    billing_trigger: BillingTrigger
    failure_charge_policy: FailureChargePolicy
    retry_charge_policy: RetryChargePolicy
    fixed_attempt_fee: CurrencyAmount | None = None
    terms_digest: str = Field(pattern=_FINGERPRINT_PATTERN)
    issued_at: UtcDateTime
    expires_at: UtcDateTime
    signature: SignatureEnvelopeV2
    evidence_level: Literal[EconomicEvidenceLevel.SIGNED_QUOTE] = (
        EconomicEvidenceLevel.SIGNED_QUOTE
    )

    @field_validator("estimated_meters")
    @classmethod
    def unique_estimated_meters(
        cls, values: tuple[MeterQuantity, ...]
    ) -> tuple[MeterQuantity, ...]:
        return _unique_meters(values)

    @model_validator(mode="after")
    def valid_quote(self) -> BoundedQuote:
        if self.expires_at <= self.issued_at:
            raise ValueError("quote must expire after it is issued")
        if self.expected_amount is not None:
            if self.expected_amount.currency != self.maximum_amount.currency:
                raise ValueError("expected and maximum quote currencies must match")
            if self.expected_amount.amount > self.maximum_amount.amount:
                raise ValueError("expected amount cannot exceed maximum amount")
        requires_attempt_fee = (
            self.failure_charge_policy is FailureChargePolicy.CHARGE_FIXED_ATTEMPT_FEE
        )
        if requires_attempt_fee != (self.fixed_attempt_fee is not None):
            raise ValueError(
                "fixed attempt fee is required only for CHARGE_FIXED_ATTEMPT_FEE"
            )
        if self.fixed_attempt_fee is not None:
            if self.fixed_attempt_fee.currency != self.maximum_amount.currency:
                raise ValueError("fixed attempt fee currency must match quote currency")
            if self.fixed_attempt_fee.amount > self.maximum_amount.amount:
                raise ValueError("fixed attempt fee cannot exceed maximum amount")
        return self

    def validate_binding(
        self,
        request: QuoteRequestV2,
        *,
        at: datetime,
        maximum_ttl_seconds: int,
    ) -> None:
        if maximum_ttl_seconds <= 0:
            raise ValueError("maximum quote TTL must be positive")
        bindings = (
            (self.quote_request_id, request.quote_request_id, "quote request"),
            (self.capability, request.capability, "capability"),
            (self.executor_id, request.executor_id, "executor"),
            (self.executor_fingerprint, request.executor_fingerprint, "executor fingerprint"),
            (self.action_digest, request.action_digest, "action digest"),
            (self.nonce, request.nonce, "nonce"),
            (self.maximum_amount.currency, request.desired_currency, "currency"),
        )
        for actual, expected, label in bindings:
            if actual != expected:
                raise ValueError(f"quote {label} does not match request")
        instant = _aware_utc(at)
        if instant < self.issued_at or instant >= self.expires_at:
            raise ValueError("quote is not currently valid")
        if (self.expires_at - self.issued_at).total_seconds() > maximum_ttl_seconds:
            raise ValueError("quote TTL exceeds configured maximum")
        maximum = request.maximum_acceptable_amount
        if maximum is not None and self.maximum_amount.amount > maximum.amount:
            raise ValueError("quote exceeds requested maximum acceptable amount")


class QuoteFailurePolicy(StrEnum):
    REQUIRE_BINDING_QUOTE = "REQUIRE_BINDING_QUOTE"
    ALLOW_VERIFIED_OFFER = "ALLOW_VERIFIED_OFFER"
    ALLOW_STATIC_PRIOR = "ALLOW_STATIC_PRIOR"
    TREAT_AS_UNAVAILABLE = "TREAT_AS_UNAVAILABLE"


class PreparedDecisionState(StrEnum):
    PREPARED = "PREPARED"
    RESERVED = "RESERVED"
    INVOKING = "INVOKING"
    AWAITING_USAGE = "AWAITING_USAGE"
    SETTLING = "SETTLING"
    SETTLED = "SETTLED"
    RELEASED = "RELEASED"
    INDETERMINATE = "INDETERMINATE"
    DISPUTED = "DISPUTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


_PREPARED_TRANSITIONS: dict[PreparedDecisionState, frozenset[PreparedDecisionState]] = {
    PreparedDecisionState.PREPARED: frozenset(
        {
            PreparedDecisionState.RESERVED,
            PreparedDecisionState.INVOKING,
            PreparedDecisionState.EXPIRED,
            PreparedDecisionState.CANCELLED,
        }
    ),
    PreparedDecisionState.RESERVED: frozenset(
        {
            PreparedDecisionState.INVOKING,
            PreparedDecisionState.RELEASED,
            PreparedDecisionState.CANCELLED,
            PreparedDecisionState.INDETERMINATE,
        }
    ),
    PreparedDecisionState.INVOKING: frozenset(
        {
            PreparedDecisionState.AWAITING_USAGE,
            PreparedDecisionState.SETTLING,
            PreparedDecisionState.INDETERMINATE,
            PreparedDecisionState.DISPUTED,
        }
    ),
    PreparedDecisionState.AWAITING_USAGE: frozenset(
        {
            PreparedDecisionState.SETTLING,
            PreparedDecisionState.INDETERMINATE,
            PreparedDecisionState.DISPUTED,
        }
    ),
    PreparedDecisionState.SETTLING: frozenset(
        {
            PreparedDecisionState.SETTLED,
            PreparedDecisionState.INDETERMINATE,
            PreparedDecisionState.DISPUTED,
        }
    ),
    PreparedDecisionState.INDETERMINATE: frozenset(
        {
            PreparedDecisionState.SETTLING,
            PreparedDecisionState.SETTLED,
            PreparedDecisionState.DISPUTED,
        }
    ),
    PreparedDecisionState.DISPUTED: frozenset({PreparedDecisionState.SETTLED}),
    PreparedDecisionState.SETTLED: frozenset(),
    PreparedDecisionState.RELEASED: frozenset(),
    PreparedDecisionState.EXPIRED: frozenset(),
    PreparedDecisionState.CANCELLED: frozenset(),
}


class CandidateRanking(EconomicStrictModel):
    executor_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    executor_fingerprint: str = Field(pattern=_FINGERPRINT_PATTERN)
    rank: int = Field(ge=1)
    score: FiniteDecimal | None = None
    quote_id: str | None = Field(default=None, max_length=200, pattern=_IDENTIFIER_PATTERN)
    expected_amount: CurrencyAmount | None = None
    maximum_amount: CurrencyAmount | None = None
    evidence_level: EconomicEvidenceLevel = EconomicEvidenceLevel.UNKNOWN
    explanation: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def valid_amounts(self) -> CandidateRanking:
        if self.expected_amount is not None and self.maximum_amount is not None:
            if self.expected_amount.currency != self.maximum_amount.currency:
                raise ValueError("candidate expected and maximum currencies must match")
            if self.expected_amount.amount > self.maximum_amount.amount:
                raise ValueError("candidate expected amount cannot exceed maximum amount")
        return self


class RejectedCandidate(EconomicStrictModel):
    executor_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    executor_fingerprint: str | None = Field(default=None, pattern=_FINGERPRINT_PATTERN)
    reasons: tuple[str, ...] = Field(min_length=1)
    quote_id: str | None = Field(default=None, max_length=200, pattern=_IDENTIFIER_PATTERN)

    @field_validator("reasons")
    @classmethod
    def bounded_reasons(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value or len(value) > 2000 for value in values):
            raise ValueError("rejection reasons must be non-empty and bounded")
        return values


class QuoteFailure(EconomicStrictModel):
    executor_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    provider_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        pattern=_IDENTIFIER_PATTERN,
    )
    code: str = Field(min_length=1, max_length=100, pattern=r"^[A-Z0-9_]+$")
    reason: str = Field(min_length=1, max_length=2000)
    retryable: bool = False


class PreparedRouteDecision(EconomicStrictModel):
    schema_version: Literal["0.4"] = "0.4"
    prepared_id: str = Field(
        default_factory=lambda: new_id("prepared"),
        min_length=1,
        max_length=200,
        pattern=_IDENTIFIER_PATTERN,
    )
    action_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    action_digest: str = Field(pattern=_FINGERPRINT_PATTERN)
    effective_policy_digest: str = Field(pattern=_FINGERPRINT_PATTERN)
    selected_executor_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        pattern=_IDENTIFIER_PATTERN,
    )
    selected_executor_fingerprint: str | None = Field(
        default=None,
        pattern=_FINGERPRINT_PATTERN,
    )
    selected_quote_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        pattern=_IDENTIFIER_PATTERN,
    )
    selected_offer_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        pattern=_IDENTIFIER_PATTERN,
    )
    selected_rate_card_id: str | None = Field(
        default=None,
        pattern=r"^rate_[a-f0-9]{64}$",
    )
    authorization_kind: AuthorizationKind | None = None
    authorization_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        pattern=_IDENTIFIER_PATTERN,
    )
    authorization_rate_ids: tuple[str, ...] = ()
    authorization_meter_quantities: tuple[AuthorizationMeterQuantity, ...] = ()
    quote_ids: tuple[str, ...] = ()
    candidate_rankings: tuple[CandidateRanking, ...] = ()
    rejected_candidates: tuple[RejectedCandidate, ...] = ()
    quote_failures: tuple[QuoteFailure, ...] = ()
    disclosed_quote_features: dict[str, JsonPrimitive] = Field(default_factory=dict)
    expected_accounting: ResourceAccounting = Field(default_factory=ResourceAccounting)
    maximum_cash_authorization: CurrencyAmount | None = None
    quote_failure_policy: QuoteFailurePolicy = QuoteFailurePolicy.REQUIRE_BINDING_QUOTE
    preparation_latency_ms: NonNegativeDecimal | None = None
    quote_latency_ms: NonNegativeDecimal | None = None
    quote_request_count: int = Field(default=0, ge=0)
    state: PreparedDecisionState = PreparedDecisionState.PREPARED
    created_at: UtcDateTime = Field(default_factory=utc_now)
    expires_at: UtcDateTime

    @property
    def id(self) -> str:
        return self.prepared_id

    @property
    def feasible(self) -> bool:
        return self.selected_executor_id is not None

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_quote_authorization(cls, value: Any) -> Any:
        return _migrate_quote_authorization(value, "selected_quote_id")

    @field_validator("quote_ids")
    @classmethod
    def unique_quote_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not re.fullmatch(_IDENTIFIER_PATTERN, value) for value in values):
            raise ValueError("quote IDs must be bounded identifiers")
        if len(values) != len(set(values)):
            raise ValueError("prepared decision cannot contain duplicate quote IDs")
        return values

    @field_validator("authorization_rate_ids")
    @classmethod
    def unique_authorization_rate_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not re.fullmatch(_IDENTIFIER_PATTERN, value) for value in values):
            raise ValueError("authorization rate IDs must be bounded identifiers")
        if len(values) != len(set(values)):
            raise ValueError("authorization rate IDs must be unique")
        return values

    @field_validator("disclosed_quote_features", mode="before")
    @classmethod
    def bounded_disclosure(cls, value: Any) -> Any:
        return QuoteRequestV2.bounded_disclosure(value)

    @model_validator(mode="after")
    def valid_decision(self) -> PreparedRouteDecision:
        if self.expires_at <= self.created_at:
            raise ValueError("prepared decision must expire after creation")
        selected = self.selected_executor_id is not None
        if selected != (self.selected_executor_fingerprint is not None):
            raise ValueError("selected executor ID and fingerprint must appear together")
        selected_basis_ids = (
            self.selected_quote_id,
            self.selected_offer_id,
            self.selected_rate_card_id,
        )
        if not selected and (
            any(value is not None for value in selected_basis_ids)
            or self.authorization_kind is not None
            or self.authorization_id is not None
            or self.authorization_rate_ids
            or self.authorization_meter_quantities
            or self.maximum_cash_authorization is not None
        ):
            raise ValueError("infeasible decision cannot select an authorization or authorize cash")
        if self.selected_quote_id is not None and self.selected_quote_id not in self.quote_ids:
            raise ValueError("selected quote must appear in quote_ids")
        if (self.authorization_kind is None) != (self.authorization_id is None):
            raise ValueError("authorization kind and ID must appear together")
        if self.authorization_kind is not None and self.maximum_cash_authorization is None:
            raise ValueError("authorization basis requires a maximum cash authorization")
        if (
            self.maximum_cash_authorization is not None
            and self.maximum_cash_authorization.amount > 0
            and self.authorization_kind is None
        ):
            raise ValueError("nonzero maximum cash authorization requires an immutable basis")
        if self.authorization_kind is AuthorizationKind.SIGNED_QUOTE:
            if self.selected_quote_id != self.authorization_id:
                raise ValueError("signed-quote authorization must match selected quote")
            if self.selected_offer_id is not None or self.selected_rate_card_id is not None:
                raise ValueError("signed-quote authorization cannot select another basis")
        elif self.authorization_kind is AuthorizationKind.PUBLISHED_OFFER:
            if self.selected_offer_id != self.authorization_id:
                raise ValueError("published-offer authorization must match selected offer")
            if self.selected_quote_id is not None or self.selected_rate_card_id is not None:
                raise ValueError("published-offer authorization cannot select another basis")
        elif self.authorization_kind is AuthorizationKind.PINNED_RATE_CARD:
            if self.selected_rate_card_id != self.authorization_id:
                raise ValueError("pinned-rate-card authorization must match selected rate card")
            if self.selected_quote_id is not None or self.selected_offer_id is not None:
                raise ValueError("pinned-rate-card authorization cannot select another basis")
            quantity_rate_ids = tuple(item.rate_id for item in self.authorization_meter_quantities)
            if not self.authorization_rate_ids or not quantity_rate_ids:
                raise ValueError("pinned-rate-card authorization requires rates and quantities")
            if len(quantity_rate_ids) != len(set(quantity_rate_ids)):
                raise ValueError("authorization meter quantities require unique rate IDs")
            if quantity_rate_ids != self.authorization_rate_ids:
                raise ValueError("authorization rates and meter quantities must match in order")
        else:
            if any(value is not None for value in selected_basis_ids):
                raise ValueError("selected authorization basis requires authorization kind and ID")
        if self.authorization_kind is not AuthorizationKind.PINNED_RATE_CARD and (
            self.authorization_rate_ids or self.authorization_meter_quantities
        ):
            raise ValueError("only pinned-rate-card authorization may include rate quantities")
        executor_ids = [item.executor_id for item in self.candidate_rankings]
        ranks = [item.rank for item in self.candidate_rankings]
        if len(executor_ids) != len(set(executor_ids)) or len(ranks) != len(set(ranks)):
            raise ValueError("candidate rankings require unique executors and ranks")
        if selected and executor_ids and self.selected_executor_id not in executor_ids:
            raise ValueError("selected executor must appear in candidate rankings")
        return self

    def can_transition_to(self, state: PreparedDecisionState) -> bool:
        return state in _PREPARED_TRANSITIONS[self.state]

    def transitioned(self, state: PreparedDecisionState) -> PreparedRouteDecision:
        target = PreparedDecisionState(state)
        if not self.can_transition_to(target):
            raise ValueError(f"illegal prepared decision transition: {self.state} -> {target}")
        return self.model_copy(update={"state": target})


class PreparedRouteTransition(EconomicStrictModel):
    schema_version: Literal["0.4"] = "0.4"
    transition_id: str = Field(
        default_factory=lambda: new_id("transition"),
        min_length=1,
        max_length=200,
        pattern=_IDENTIFIER_PATTERN,
    )
    prepared_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    from_state: PreparedDecisionState
    to_state: PreparedDecisionState
    occurred_at: UtcDateTime = Field(default_factory=utc_now)
    reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def legal_transition(self) -> PreparedRouteTransition:
        if self.to_state not in _PREPARED_TRANSITIONS[self.from_state]:
            raise ValueError(
                f"illegal prepared decision transition: {self.from_state} -> {self.to_state}"
            )
        return self


class ProviderExecutionStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    REJECTED = "REJECTED"
    INDETERMINATE = "INDETERMINATE"


class PaymentReservationState(StrEnum):
    RESERVED = "RESERVED"
    SETTLING = "SETTLING"
    SETTLED = "SETTLED"
    RELEASED = "RELEASED"
    INDETERMINATE = "INDETERMINATE"
    DISPUTED = "DISPUTED"


class PaymentReservationV2(EconomicStrictModel):
    schema_version: Literal["0.4"] = "0.4"
    reservation_id: str = Field(
        default_factory=lambda: new_id("reserve"),
        min_length=1,
        max_length=200,
        pattern=_IDENTIFIER_PATTERN,
    )
    charge_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    prepared_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    quote_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        pattern=_IDENTIFIER_PATTERN,
    )
    authorization_kind: AuthorizationKind | None = None
    authorization_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        pattern=_IDENTIFIER_PATTERN,
    )
    action_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    attempt_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    maximum_amount: CurrencyAmount
    adapter: str = Field(min_length=1, max_length=100, pattern=_IDENTIFIER_PATTERN)
    idempotency_key: str = Field(min_length=1, max_length=256)
    state: PaymentReservationState = PaymentReservationState.RESERVED
    created_at: UtcDateTime = Field(default_factory=utc_now)
    updated_at: UtcDateTime = Field(default_factory=utc_now)
    indeterminate_reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_quote_authorization(cls, value: Any) -> Any:
        return _migrate_quote_authorization(value, "quote_id")

    @model_validator(mode="after")
    def valid_reservation(self) -> PaymentReservationV2:
        if self.updated_at < self.created_at:
            raise ValueError("reservation updated_at cannot precede created_at")
        if self.state is PaymentReservationState.INDETERMINATE and not self.indeterminate_reason:
            raise ValueError("indeterminate reservation requires a reason")
        if self.state is not PaymentReservationState.INDETERMINATE and self.indeterminate_reason:
            raise ValueError("only an indeterminate reservation may carry an indeterminate reason")
        if self.authorization_kind is None or self.authorization_id is None:
            raise ValueError("payment reservation requires an immutable authorization basis")
        if self.authorization_kind is AuthorizationKind.SIGNED_QUOTE:
            if self.quote_id != self.authorization_id:
                raise ValueError("signed-quote reservation must match quote ID")
        elif self.quote_id is not None:
            raise ValueError("offer and rate-card reservations cannot carry a quote ID")
        return self


class SettlementEvidence(EconomicStrictModel):
    schema_version: Literal["0.4"] = "0.4"
    charge_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    evidence_level: EconomicEvidenceLevel = EconomicEvidenceLevel.UNKNOWN
    usage_statement_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        pattern=_IDENTIFIER_PATTERN,
    )
    evidence_digest: str | None = Field(default=None, pattern=_FINGERPRINT_PATTERN)
    external_reference: str | None = Field(default=None, max_length=500)
    provider_calculated_amount: CurrencyAmount | None = None


class UsageStatement(EconomicStrictModel):
    schema_version: Literal["0.4"] = "0.4"
    usage_statement_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    quote_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    prepared_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    action_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    attempt_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    provider_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    executor_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    executor_fingerprint: str = Field(pattern=_FINGERPRINT_PATTERN)
    execution_status: ProviderExecutionStatus
    meters: tuple[MeterQuantity, ...] = ()
    provider_calculated_amount: CurrencyAmount | None = None
    started_at: UtcDateTime | None = None
    completed_at: UtcDateTime | None = None
    issued_at: UtcDateTime
    signature: SignatureEnvelopeV2
    evidence_level: Literal[EconomicEvidenceLevel.SIGNED_USAGE_STATEMENT] = (
        EconomicEvidenceLevel.SIGNED_USAGE_STATEMENT
    )

    @field_validator("meters")
    @classmethod
    def unique_usage_meters(cls, values: tuple[MeterQuantity, ...]) -> tuple[MeterQuantity, ...]:
        return _unique_meters(values)

    @model_validator(mode="after")
    def valid_usage(self) -> UsageStatement:
        if (
            self.started_at is not None
            and self.completed_at is not None
            and self.completed_at < self.started_at
        ):
            raise ValueError("usage completed_at cannot precede started_at")
        if self.completed_at is not None and self.issued_at < self.completed_at:
            raise ValueError("usage statement cannot be issued before completion")
        return self


class SettlementStatus(StrEnum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    SETTLED = "SETTLED"
    RELEASED = "RELEASED"
    INDETERMINATE = "INDETERMINATE"
    DISPUTED = "DISPUTED"
    REFUNDED = "REFUNDED"
    FAILED = "FAILED"


class SettlementReceipt(EconomicStrictModel):
    schema_version: Literal["0.4"] = "0.4"
    settlement_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    charge_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    prepared_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    quote_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        pattern=_IDENTIFIER_PATTERN,
    )
    authorization_kind: AuthorizationKind | None = None
    authorization_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        pattern=_IDENTIFIER_PATTERN,
    )
    reservation_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    attempt_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    reserved_amount: CurrencyAmount
    captured_amount: CurrencyAmount
    released_amount: CurrencyAmount
    payment_rail: str = Field(min_length=1, max_length=100, pattern=_IDENTIFIER_PATTERN)
    external_reference: str | None = Field(default=None, max_length=500)
    status: SettlementStatus
    evidence_level: EconomicEvidenceLevel
    settled_at: UtcDateTime
    signature: SignatureEnvelopeV2 | None = None

    @property
    def id(self) -> str:
        return self.settlement_id

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_quote_authorization(cls, value: Any) -> Any:
        return _migrate_quote_authorization(value, "quote_id")

    @model_validator(mode="after")
    def valid_settlement(self) -> SettlementReceipt:
        currencies = {
            self.reserved_amount.currency,
            self.captured_amount.currency,
            self.released_amount.currency,
        }
        if len(currencies) != 1:
            raise ValueError("settlement amounts must use one currency")
        accounted = self.captured_amount.amount + self.released_amount.amount
        if self.captured_amount.amount > self.reserved_amount.amount:
            raise ValueError("captured amount cannot exceed reserved amount")
        if accounted > self.reserved_amount.amount:
            raise ValueError("captured plus released cannot exceed reserved amount")
        final = {
            SettlementStatus.COMPLETED,
            SettlementStatus.SETTLED,
            SettlementStatus.RELEASED,
        }
        if self.status in final and accounted != self.reserved_amount.amount:
            raise ValueError("completed settlement must account for the full reservation")
        if self.status in final and not self.evidence_level.is_payment_evidence:
            raise ValueError("completed settlement requires payment-settlement evidence")
        if self.authorization_kind is None or self.authorization_id is None:
            raise ValueError("settlement receipt requires an immutable authorization basis")
        if self.authorization_kind is AuthorizationKind.SIGNED_QUOTE:
            if self.quote_id != self.authorization_id:
                raise ValueError("signed-quote settlement must match quote ID")
        elif self.quote_id is not None:
            raise ValueError("offer and rate-card settlements cannot carry a quote ID")
        return self


class RefundReceiptV2(EconomicStrictModel):
    schema_version: Literal["0.4"] = "0.4"
    refund_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    settlement_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    charge_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    amount: CurrencyAmount
    reason: str = Field(min_length=1, max_length=2000)
    idempotency_key: str = Field(min_length=1, max_length=256)
    refunded_at: UtcDateTime
    external_reference: str | None = Field(default=None, max_length=500)
    signature: SignatureEnvelopeV2 | None = None


class ReconciliationStatus(StrEnum):
    MATCHED = "MATCHED"
    UNDERCHARGED = "UNDERCHARGED"
    OVERCHARGED = "OVERCHARGED"
    MISSING_BILLING_RECORD = "MISSING_BILLING_RECORD"
    PENDING = "PENDING"
    DISPUTED = "DISPUTED"
    RESOLVED = "RESOLVED"

    @property
    def economic_evidence_level(self) -> EconomicEvidenceLevel:
        """Return authoritative billing evidence only for resolved comparisons."""

        if self in {
            ReconciliationStatus.MATCHED,
            ReconciliationStatus.UNDERCHARGED,
            ReconciliationStatus.OVERCHARGED,
            ReconciliationStatus.RESOLVED,
        }:
            return EconomicEvidenceLevel.BILLING_RECONCILED
        return EconomicEvidenceLevel.UNKNOWN

    @property
    def is_billing_reconciled(self) -> bool:
        return self.economic_evidence_level is EconomicEvidenceLevel.BILLING_RECONCILED


class BillingReconciliation(EconomicStrictModel):
    schema_version: Literal["0.4"] = "0.4"
    reconciliation_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    settlement_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    provider_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    invoice_reference: str | None = Field(default=None, max_length=500)
    billing_record_reference: str | None = Field(default=None, max_length=500)
    expected_amount: CurrencyAmount
    billed_amount: CurrencyAmount
    discrepancy: CurrencyAmount
    status: ReconciliationStatus
    evidence_digest: str | None = Field(default=None, pattern=_FINGERPRINT_PATTERN)
    reconciled_at: UtcDateTime

    @model_validator(mode="after")
    def valid_reconciliation(self) -> BillingReconciliation:
        currencies = {
            self.expected_amount.currency,
            self.billed_amount.currency,
            self.discrepancy.currency,
        }
        if len(currencies) != 1:
            raise ValueError("reconciliation amounts must use one currency")
        expected_discrepancy = abs(self.billed_amount.amount - self.expected_amount.amount)
        if self.discrepancy.amount != expected_discrepancy:
            raise ValueError("reconciliation discrepancy does not match billed difference")
        return self


class MarketAggregate(EconomicStrictModel):
    schema_version: Literal["0.4"] = "0.4"
    aggregate_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    capability: str = Field(min_length=3, max_length=200, pattern=_CAPABILITY_PATTERN)
    provider_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    executor_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    executor_fingerprint: str = Field(pattern=_FINGERPRINT_PATTERN)
    region: str | None = Field(default=None, max_length=100)
    account_tier: str | None = Field(default=None, max_length=100)
    input_bucket: str = Field(min_length=1, max_length=100)
    sample_size: int = Field(ge=1)
    window_start: UtcDateTime
    window_end: UtcDateTime
    actual_cost_p50: CurrencyAmount | None = None
    actual_cost_p95: CurrencyAmount | None = None
    latency_ms_p50: NonNegativeDecimal | None = None
    latency_ms_p95: NonNegativeDecimal | None = None
    valid_success_rate: NonNegativeDecimal | None = None
    valid_success_lower_bound: NonNegativeDecimal | None = None
    settlement_verified_fraction: NonNegativeDecimal
    billing_reconciled_fraction: NonNegativeDecimal
    generated_at: UtcDateTime
    expires_at: UtcDateTime
    signature: SignatureEnvelopeV2

    @model_validator(mode="after")
    def valid_aggregate(self) -> MarketAggregate:
        if self.window_end <= self.window_start:
            raise ValueError("aggregate window_end must be later than window_start")
        if self.expires_at <= self.generated_at:
            raise ValueError("aggregate must expire after generation")
        for value, label in (
            (self.valid_success_rate, "valid_success_rate"),
            (self.valid_success_lower_bound, "valid_success_lower_bound"),
            (self.settlement_verified_fraction, "settlement_verified_fraction"),
            (self.billing_reconciled_fraction, "billing_reconciled_fraction"),
        ):
            if value is not None and value > 1:
                raise ValueError(f"{label} cannot exceed one")
        if (
            self.valid_success_rate is not None
            and self.valid_success_lower_bound is not None
            and self.valid_success_lower_bound > self.valid_success_rate
        ):
            raise ValueError("success lower bound cannot exceed success rate")
        if (
            self.latency_ms_p50 is not None
            and self.latency_ms_p95 is not None
            and self.latency_ms_p50 > self.latency_ms_p95
        ):
            raise ValueError("latency p50 cannot exceed p95")
        if self.actual_cost_p50 is not None and self.actual_cost_p95 is not None:
            if self.actual_cost_p50.currency != self.actual_cost_p95.currency:
                raise ValueError("aggregate cost percentiles must use one currency")
            if self.actual_cost_p50.amount > self.actual_cost_p95.amount:
                raise ValueError("actual cost p50 cannot exceed p95")
        return self

    def fresh_at(self, at: datetime) -> bool:
        instant = _aware_utc(at)
        return self.generated_at <= instant < self.expires_at


class PricingDisputeStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"


class PricingDispute(EconomicStrictModel):
    schema_version: Literal["0.4"] = "0.4"
    dispute_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    prepared_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    quote_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    usage_statement_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        pattern=_IDENTIFIER_PATTERN,
    )
    provider_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    quoted_maximum: CurrencyAmount
    provider_claimed_amount: CurrencyAmount
    status: PricingDisputeStatus = PricingDisputeStatus.OPEN
    reason: str = Field(min_length=1, max_length=2000)
    created_at: UtcDateTime = Field(default_factory=utc_now)
    resolved_at: UtcDateTime | None = None

    @model_validator(mode="after")
    def valid_dispute(self) -> PricingDispute:
        if self.quoted_maximum.currency != self.provider_claimed_amount.currency:
            raise ValueError("dispute amounts must use one currency")
        if self.provider_claimed_amount.amount <= self.quoted_maximum.amount:
            raise ValueError("pricing dispute requires a provider claim above quoted maximum")
        if (self.status is PricingDisputeStatus.OPEN) == (self.resolved_at is not None):
            raise ValueError("open disputes cannot be resolved; closed disputes require resolved_at")
        if self.resolved_at is not None and self.resolved_at < self.created_at:
            raise ValueError("dispute resolved_at cannot precede created_at")
        return self


class EconomicEvidenceLink(EconomicStrictModel):
    schema_version: Literal["0.4"] = "0.4"
    link_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    charge_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    evidence_level: EconomicEvidenceLevel
    evidence_type: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_.-]+$")
    evidence_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    payload_digest: str = Field(pattern=_FINGERPRINT_PATTERN)
    authoritative: bool = False
    supersedes_link_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        pattern=_IDENTIFIER_PATTERN,
    )
    created_at: UtcDateTime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def valid_link(self) -> EconomicEvidenceLink:
        if self.supersedes_link_id == self.link_id:
            raise ValueError("evidence link cannot supersede itself")
        return self


class QuoteRequest(StrictModel):
    quote_request_id: str = Field(default_factory=lambda: new_id("qreq"))
    action: ActionRequest
    executor_ids: list[str] | None = None
    created_at: datetime = Field(default_factory=utc_now)


class Quote(StrictModel):
    quote_id: str = Field(default_factory=lambda: new_id("quote"))
    quote_request_id: str
    provider_id: str
    executor_id: str
    capability: str
    monetary_usd: float = Field(ge=0.0)
    estimate: RouteEstimate
    expires_at: datetime
    terms: dict[str, Any] = Field(default_factory=dict)
    signature: SignatureEnvelope | None = None


class QuoteAcceptance(StrictModel):
    acceptance_id: str = Field(default_factory=lambda: new_id("accept"))
    quote_id: str
    action_id: str
    accepted_amount_usd: float = Field(ge=0.0)
    accepted_at: datetime = Field(default_factory=utc_now)
    signature: SignatureEnvelope | None = None


class PaymentState(StrEnum):
    RESERVED = "reserved"
    CAPTURED = "captured"
    RELEASED = "released"
    REFUNDED = "refunded"
    FAILED = "failed"


class AuthorizationPolicy(StrictModel):
    auto_approve_under_usd: float = Field(default=0.0, ge=0.0)
    financial_actions_require_human: bool = True
    preserve_subscriptions: list[str] = Field(default_factory=list)
    prefer_local_within_percent: float = Field(default=0.0, ge=0.0, le=100.0)


class AgentBudget(StrictModel):
    budget_id: str = "default"
    daily_marketplace_limit_usd: float = Field(default=0.0, ge=0.0)
    max_per_action_usd: float = Field(default=0.0, ge=0.0)
    prepaid_balance_usd: float = Field(default=0.0, ge=0.0)
    authorization: AuthorizationPolicy = Field(default_factory=AuthorizationPolicy)


class PaymentReservation(StrictModel):
    reservation_id: str = Field(default_factory=lambda: new_id("reserve"))
    quote_id: str
    action_id: str
    adapter: str
    amount_usd: float = Field(ge=0.0)
    state: PaymentState = PaymentState.RESERVED
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PaymentCapture(StrictModel):
    capture_id: str = Field(default_factory=lambda: new_id("capture"))
    reservation_id: str
    amount_usd: float = Field(ge=0.0)
    captured_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PaymentRefund(StrictModel):
    refund_id: str = Field(default_factory=lambda: new_id("refund"))
    capture_id: str
    amount_usd: float = Field(ge=0.0)
    refunded_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LedgerEvent(StrictModel):
    event_id: str = Field(default_factory=lambda: new_id("ledger"))
    event_type: Literal["reserve", "capture", "release", "refund"]
    amount_usd: float = Field(ge=0.0)
    action_id: str
    reference_id: str
    occurred_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutorSpec(StrictModel):
    id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:-]+$")
    capability: str = Field(min_length=1, max_length=200)
    kind: ExecutorKind
    description: str = Field(min_length=1, max_length=4000)
    input_schema: dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "additionalProperties": True}
    )
    output_schema: dict[str, Any] | None = None
    estimate: RouteEstimate = Field(default_factory=RouteEstimate)
    side_effect: SideEffect = SideEffect.READ
    locality: Locality = Locality.LOCAL
    requires_network: bool = False
    data_residency: list[str] = Field(default_factory=list)
    idempotent: bool = True
    safe_to_auto_execute: bool = True
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)
    resource_pool: str | None = Field(default=None, max_length=200)
    provider_id: str | None = Field(default=None, max_length=200)
    validators: list[ValidationSpec] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_network_locality(self) -> ExecutorSpec:
        if self.locality == Locality.INTERNET and not self.requires_network:
            self.requires_network = True
        if self.kind in {ExecutorKind.DELEGATE, ExecutorKind.HOST} and self.safe_to_auto_execute:
            # Host/delegate routes are plans; AEEP cannot enforce their execution.
            self.safe_to_auto_execute = False
        if self.kind == ExecutorKind.HOST and not self.resource_pool:
            raise ValueError("host executors require resource_pool")
        if self.kind == ExecutorKind.HOST and self.estimate.resources.subscription_units == 0:
            self.estimate.resources.subscription_units = 1.0
        return self


class MetricWeights(StrictModel):
    monetary: float = Field(default=0.30, ge=0.0)
    latency: float = Field(default=0.25, ge=0.0)
    compute: float = Field(default=0.25, ge=0.0)
    subscription: float = Field(default=0.0, ge=0.0)
    reliability: float = Field(default=0.10, ge=0.0)
    quality: float = Field(default=0.05, ge=0.0)
    risk: float = Field(default=0.05, ge=0.0)

    @model_validator(mode="after")
    def nonzero(self) -> MetricWeights:
        if sum(getattr(self, field) for field in type(self).model_fields) <= 0:
            raise ValueError("at least one policy weight must be positive")
        return self

    def normalized(self) -> dict[str, float]:
        values = {field: float(getattr(self, field)) for field in type(self).model_fields}
        total = sum(values.values())
        return {field: value / total for field, value in values.items()}


class ReferenceScales(StrictModel):
    """A score of roughly one means one reference unit of burden."""

    monetary_usd: float = Field(default=0.05, gt=0.0)
    latency_ms: float = Field(default=2_000.0, gt=0.0)
    cpu_ms: float = Field(default=1_000.0, gt=0.0)
    memory_mb_seconds: float = Field(default=256.0, gt=0.0)
    peak_memory_mb: float = Field(default=512.0, gt=0.0)
    gpu_ms: float = Field(default=1_000.0, gt=0.0)
    network_bytes: int = Field(default=1_000_000, gt=0)
    context_tokens: int = Field(default=8_000, gt=0)


class ShadowPrices(StrictModel):
    """Optional local economic values for scarce non-cash resources.

    Values are USD per unit. They are additive to reported monetary cost and are
    useful for subscription quotas or expensive local compute. Defaults are zero
    so AEEP does not pretend different providers' tokens are fungible.
    """

    cpu_ms_usd: float = Field(default=0.0, ge=0.0)
    memory_mb_second_usd: float = Field(default=0.0, ge=0.0)
    gpu_ms_usd: float = Field(default=0.0, ge=0.0)
    network_byte_usd: float = Field(default=0.0, ge=0.0)
    context_token_usd: float = Field(default=0.0, ge=0.0)
    input_token_usd: float = Field(default=0.0, ge=0.0)
    output_token_usd: float = Field(default=0.0, ge=0.0)


class SubscriptionPolicyRule(StrictModel):
    resource_pool: str = Field(min_length=1, max_length=200)
    unit: str = Field(default="provider_unit", min_length=1, max_length=100)
    pressure_weight: float = Field(default=1.0, ge=0.0, le=100.0)
    policy_value_usd_per_unit: Decimal | None = Field(default=None, ge=0)


class FallbackConfig(StrictModel):
    enabled: bool = True
    max_attempts: int = Field(default=3, ge=1, le=10)
    retry_timeouts: bool = True
    retry_validation_failures: bool = True
    allow_non_idempotent: bool = False


class PolicyConfig(StrictModel):
    name: str = "balanced"
    description: str = "Balance expected cash cost, latency, and compute pressure."
    weights: MetricWeights = Field(default_factory=MetricWeights)
    references: ReferenceScales = Field(default_factory=ReferenceScales)
    shadow_prices: ShadowPrices = Field(default_factory=ShadowPrices)
    constraints: ActionConstraints = Field(default_factory=ActionConstraints)
    fallback: FallbackConfig = Field(default_factory=FallbackConfig)
    history_weight: float = Field(default=0.70, ge=0.0, le=1.0)
    history_prior_samples: int = Field(default=5, ge=1, le=1000)
    resource_scarcity_multiplier: float = Field(default=2.0, ge=0.0, le=100.0)
    subscription_scarcity_multiplier: float = Field(default=1.0, ge=0.0, le=100.0)
    subscription_rules: list[SubscriptionPolicyRule] = Field(default_factory=list)
    uncertainty_penalty: float = Field(
        default=0.10,
        ge=0.0,
        le=10.0,
        description="Added score burden at zero estimate confidence.",
    )
    prefer_local_bonus: float = Field(default=0.05, ge=0.0, le=1.0)
    deterministic_tie_break: bool = True

    @field_validator("subscription_rules")
    @classmethod
    def unique_subscription_rules(
        cls, rules: list[SubscriptionPolicyRule]
    ) -> list[SubscriptionPolicyRule]:
        keys = [(rule.resource_pool, rule.unit) for rule in rules]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate subscription policy rule")
        return rules


class RateType(StrEnum):
    INPUT_TOKEN = "input_token"
    CACHED_INPUT_TOKEN = "cached_input_token"
    OUTPUT_TOKEN = "output_token"
    CACHE_WRITE_TOKEN = "cache_write_token"
    TOOL_CALL = "tool_call"
    SUBSCRIPTION_UNIT = "subscription_unit"
    OTHER = "other"


class RateCardRate(StrictModel):
    rate_id: str = Field(min_length=1, max_length=200)
    rate_type: RateType
    meter: str = Field(min_length=1, max_length=200)
    input_unit: str = Field(min_length=1, max_length=100)
    output_unit: str = Field(min_length=1, max_length=100)
    unit_quantity: Decimal = Field(gt=0)
    rate_amount: Decimal = Field(ge=0)
    service_tier: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    tool_name: str | None = Field(default=None, max_length=200)
    long_context_min: int | None = Field(default=None, ge=0)
    long_context_max: int | None = Field(default=None, ge=0)
    multiplier: Decimal | None = Field(default=None, gt=0)
    rule: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def valid_range(self) -> RateCardRate:
        if (
            self.long_context_min is not None
            and self.long_context_max is not None
            and self.long_context_max < self.long_context_min
        ):
            raise ValueError("long_context_max must be >= long_context_min")
        return self


class RateCardSnapshot(StrictModel):
    schema_version: Literal["1"] = "1"
    snapshot_id: str | None = Field(default=None, pattern=r"^rate_[A-Fa-f0-9]{64}$")
    provider: str = Field(min_length=1, max_length=100)
    product: str = Field(min_length=1, max_length=200)
    model: str = Field(min_length=1, max_length=200)
    effective_from: datetime
    effective_until: datetime | None = None
    retrieved_at: datetime = Field(default_factory=utc_now)
    source_uri: str = Field(min_length=1, max_length=2000)
    source_published_at: datetime | None = None
    source_content_sha256: str = Field(pattern=r"^[A-Fa-f0-9]{64}$")
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    rates: list[RateCardRate] = Field(min_length=1)

    def canonical_payload(self) -> bytes:
        payload = self.model_dump(mode="json", exclude={"snapshot_id"})
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

    @model_validator(mode="after")
    def validate_snapshot(self) -> RateCardSnapshot:
        if self.effective_until is not None and self.effective_until <= self.effective_from:
            raise ValueError("effective_until must be after effective_from")
        ids = [rate.rate_id for rate in self.rates]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate rate_id")
        semantic_keys = [
            (
                rate.rate_type,
                rate.meter,
                rate.service_tier,
                rate.region,
                rate.tool_name,
                rate.long_context_min,
                rate.long_context_max,
            )
            for rate in self.rates
        ]
        if len(semantic_keys) != len(set(semantic_keys)):
            raise ValueError("ambiguous duplicate rate")
        monetary_rates = [
            rate for rate in self.rates if rate.rate_type != RateType.SUBSCRIPTION_UNIT
        ]
        if monetary_rates and not self.currency:
            raise ValueError("monetary rate cards require currency")
        if self.currency and any(rate.output_unit != self.currency for rate in monetary_rates):
            raise ValueError("monetary rate output_unit must match snapshot currency")
        grouped: dict[
            tuple[RateType, str, str | None, str | None, str | None],
            list[RateCardRate],
        ] = {}
        for rate in self.rates:
            grouped.setdefault(
                (
                    rate.rate_type,
                    rate.meter,
                    rate.service_tier,
                    rate.region,
                    rate.tool_name,
                ),
                [],
            ).append(rate)
        for rates in grouped.values():
            bounded = [
                rate
                for rate in rates
                if rate.long_context_min is not None or rate.long_context_max is not None
            ]
            for index, left in enumerate(bounded):
                left_min = left.long_context_min or 0
                left_max = left.long_context_max if left.long_context_max is not None else math.inf
                for right in bounded[index + 1 :]:
                    right_min = right.long_context_min or 0
                    right_max = (
                        right.long_context_max if right.long_context_max is not None else math.inf
                    )
                    if max(left_min, right_min) <= min(left_max, right_max):
                        raise ValueError("ambiguous overlapping long-context rates")
        expected = f"rate_{hashlib.sha256(self.canonical_payload()).hexdigest()}"
        if self.snapshot_id is not None and self.snapshot_id != expected:
            raise ValueError("snapshot_id does not match canonical content")
        object.__setattr__(self, "snapshot_id", expected)
        return self


class PinnedRateCardAuthorizationConfig(StrictModel):
    """Operator-pinned, unconditional rate selection for one exact executor."""

    rate_card_snapshot_id: str = Field(pattern=r"^rate_[a-f0-9]{64}$")
    meter_quantities: tuple[AuthorizationMeterQuantity, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_rate_ids(self) -> PinnedRateCardAuthorizationConfig:
        rate_ids = self.rate_ids
        if len(rate_ids) != len(set(rate_ids)):
            raise ValueError("pinned rate-card quantities require unique rate IDs")
        return self

    @property
    def rate_ids(self) -> tuple[str, ...]:
        return tuple(item.rate_id for item in self.meter_quantities)

    def authorized_maximum(
        self,
        snapshot: RateCardSnapshot,
        *,
        at: datetime,
    ) -> CurrencyAmount:
        """Validate immutable, unconditional rates and calculate their exact bound."""

        if snapshot.snapshot_id != self.rate_card_snapshot_id:
            raise ValueError("pinned rate-card snapshot does not match operator configuration")
        if snapshot.currency is None:
            raise ValueError("subscription-only rate card cannot authorize cash")
        instant = _aware_utc(at)
        effective_from = _aware_utc(snapshot.effective_from)
        effective_until = (
            _aware_utc(snapshot.effective_until)
            if snapshot.effective_until is not None
            else None
        )
        if instant < effective_from or (
            effective_until is not None and instant >= effective_until
        ):
            raise ValueError("pinned rate-card snapshot is not currently effective")
        rates = {rate.rate_id: rate for rate in snapshot.rates}
        total = Decimal(0)
        for quantity in self.meter_quantities:
            rate = rates.get(quantity.rate_id)
            if rate is None:
                raise ValueError("pinned rate-card authorization names an unknown rate")
            if rate.rate_type is RateType.SUBSCRIPTION_UNIT:
                raise ValueError("subscription-unit rates cannot authorize cash")
            if any(
                value is not None
                for value in (
                    rate.service_tier,
                    rate.region,
                    rate.tool_name,
                    rate.long_context_min,
                    rate.long_context_max,
                    rate.rule,
                )
            ):
                raise ValueError("conditional pinned rates cannot authorize cash")
            if rate.meter != quantity.meter or rate.input_unit != quantity.unit:
                raise ValueError("pinned authorization quantity does not match its rate")
            total += (
                quantity.quantity
                / rate.unit_quantity
                * rate.rate_amount
                * (rate.multiplier or Decimal(1))
            )
        return CurrencyAmount(amount=total, currency=snapshot.currency)


class PersistenceConfig(StrictModel):
    """Local persistence controls.

    Decisions are useful for delegated outcome reporting and auditability, but
    action inputs and caller context can contain secrets or personal data. They
    are redacted from SQLite by default while the in-memory/returned decision
    remains complete.
    """

    store_action_inputs: bool = False
    store_action_context: bool = False


class SigningConfig(StrictModel):
    key_id: str = Field(min_length=1, max_length=200)
    secret_env: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")


class EconomicLiveQuotesConfig(StrictModel):
    enabled: bool = False
    top_k: int = Field(default=3, ge=1, le=20)
    per_provider_timeout_seconds: float = Field(default=2.0, gt=0.0, le=60.0)
    total_timeout_seconds: float = Field(default=4.0, gt=0.0, le=120.0)
    maximum_response_bytes: int = Field(default=262_144, ge=1_024, le=10_000_000)
    maximum_clock_skew_seconds: int = Field(default=30, ge=0, le=300)
    maximum_quote_ttl_seconds: int = Field(default=600, ge=1, le=86_400)

    @model_validator(mode="after")
    def valid_deadlines(self) -> EconomicLiveQuotesConfig:
        if self.total_timeout_seconds < self.per_provider_timeout_seconds:
            raise ValueError("total quote timeout cannot be shorter than provider timeout")
        return self


class EconomicRequirementsConfig(StrictModel):
    require_binding_quote_for_paid_routes: bool = True
    allow_verified_static_offer: bool = True
    allow_static_prior: bool = False
    minimum_evidence_level: EconomicEvidenceLevel = EconomicEvidenceLevel.SIGNED_QUOTE
    quote_failure_policy: QuoteFailurePolicy = QuoteFailurePolicy.REQUIRE_BINDING_QUOTE
    pinned_rate_cards: dict[str, PinnedRateCardAuthorizationConfig] = Field(
        default_factory=dict
    )

    @field_validator("pinned_rate_cards")
    @classmethod
    def valid_pinned_rate_card_executors(
        cls,
        values: dict[str, PinnedRateCardAuthorizationConfig],
    ) -> dict[str, PinnedRateCardAuthorizationConfig]:
        if any(not re.fullmatch(_IDENTIFIER_PATTERN, executor_id) for executor_id in values):
            raise ValueError("pinned rate-card executor IDs must be bounded identifiers")
        return values

    @model_validator(mode="after")
    def valid_fallback(self) -> EconomicRequirementsConfig:
        if self.minimum_evidence_level.rank > EconomicEvidenceLevel.SIGNED_QUOTE.rank:
            raise ValueError("pre-execution minimum evidence cannot exceed SIGNED_QUOTE")
        if (
            self.quote_failure_policy is QuoteFailurePolicy.ALLOW_VERIFIED_OFFER
            and not self.allow_verified_static_offer
        ):
            raise ValueError("verified-offer fallback is disabled")
        if (
            self.quote_failure_policy is QuoteFailurePolicy.ALLOW_STATIC_PRIOR
            and not self.allow_static_prior
        ):
            raise ValueError("static-prior fallback is disabled")
        if self.require_binding_quote_for_paid_routes and self.quote_failure_policy not in {
            QuoteFailurePolicy.REQUIRE_BINDING_QUOTE,
            QuoteFailurePolicy.TREAT_AS_UNAVAILABLE,
        }:
            raise ValueError("paid routes requiring binding quotes cannot use estimate fallback")
        return self


class MarketAggregatesConfig(StrictModel):
    enabled: bool = False
    maximum_age_seconds: int = Field(default=86_400, ge=1, le=2_592_000)
    minimum_sample_size: int = Field(default=20, ge=1, le=1_000_000)
    minimum_settlement_verified_fraction: NonNegativeDecimal = Decimal("0.80")

    @field_validator("minimum_settlement_verified_fraction")
    @classmethod
    def valid_fraction(cls, value: Decimal) -> Decimal:
        if value > 1:
            raise ValueError("minimum settlement-verified fraction cannot exceed one")
        return value


def _exact_quote_host(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("allowed quote hosts must be strings")
    host = value.rstrip(".").lower()
    if not host or host != value.strip().rstrip(".").lower():
        raise ValueError("allowed quote hosts must not contain surrounding whitespace")
    if any(token in host for token in ("://", "/", "@", "*")) or ".." in host:
        raise ValueError("allowed quote hosts must be exact hosts, not URLs or wildcards")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        labels = host.split(".")
        if any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in labels
        ):
            raise ValueError("allowed quote host is invalid") from None
    return host


class EconomicNetworkConfig(StrictModel):
    allowed_quote_hosts: tuple[str, ...] = ()
    allow_private_addresses: bool = False
    allow_redirects: bool = False
    trust_environment_proxy: bool = False

    @field_validator("allowed_quote_hosts")
    @classmethod
    def exact_unique_hosts(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_exact_quote_host(value) for value in values)
        if len(normalized) != len(set(normalized)):
            raise ValueError("allowed quote hosts cannot contain duplicates")
        return normalized


class EconomicTrustStoreConfig(StrictModel):
    path: str = Field(default="~/.config/aeep/provider-keys.json", min_length=1, max_length=2000)


class EconomicPaymentConfig(StrictModel):
    adapter: str = Field(default="free", min_length=1, max_length=100, pattern=_IDENTIFIER_PATTERN)
    unlimited_budget: bool = False

    @model_validator(mode="after")
    def valid_unlimited_budget(self) -> EconomicPaymentConfig:
        if self.adapter == "invoice" and not self.unlimited_budget:
            raise ValueError("invoice payment adapter requires explicit unlimited_budget")
        if self.adapter != "invoice" and self.unlimited_budget:
            raise ValueError("unlimited_budget is restricted to the invoice payment adapter")
        return self


class EconomicEvidenceConfig(StrictModel):
    enabled: bool = False
    settlement_currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    live_quotes: EconomicLiveQuotesConfig = Field(default_factory=EconomicLiveQuotesConfig)
    requirements: EconomicRequirementsConfig = Field(default_factory=EconomicRequirementsConfig)
    market_aggregates: MarketAggregatesConfig = Field(default_factory=MarketAggregatesConfig)
    network: EconomicNetworkConfig = Field(default_factory=EconomicNetworkConfig)
    trust_store: EconomicTrustStoreConfig = Field(default_factory=EconomicTrustStoreConfig)
    payment: EconomicPaymentConfig = Field(default_factory=EconomicPaymentConfig)

    @field_validator("settlement_currency", mode="before")
    @classmethod
    def normalize_settlement_currency(cls, value: Any) -> str:
        return CurrencyAmount.normalize_currency(value)

    @model_validator(mode="after")
    def valid_activation(self) -> EconomicEvidenceConfig:
        if self.enabled and self.settlement_currency != "USD":
            raise ValueError(
                "AEEP 0.4 routing budgets are USD-denominated; non-USD economic routing "
                "requires explicit currency-tagged policy support"
            )
        if not self.enabled and (self.live_quotes.enabled or self.market_aggregates.enabled):
            raise ValueError("economic evidence must be enabled before network sources")
        if self.live_quotes.enabled and not self.network.allowed_quote_hosts:
            raise ValueError("live quotes require at least one allowed quote host")
        if self.live_quotes.enabled and self.network.allow_redirects:
            raise ValueError("live quotes do not permit HTTP redirects")
        if self.live_quotes.enabled and self.network.trust_environment_proxy:
            raise ValueError("live quotes do not permit ambient proxy trust")
        return self


class Manifest(StrictModel):
    version: Literal["0.1", "0.15", "0.2", "0.3", "0.4"] = "0.4"
    database: str = ".aeep/aeep.db"
    default_policy: str = "balanced"
    persistence: PersistenceConfig = Field(default_factory=PersistenceConfig)
    signing: SigningConfig | None = None
    budget: AgentBudget | None = None
    economic_evidence: EconomicEvidenceConfig = Field(default_factory=EconomicEvidenceConfig)
    policies: dict[str, PolicyConfig] = Field(default_factory=dict)
    capabilities: list[CapabilityDefinition] = Field(default_factory=list)
    resources: list[SubscriptionResource] = Field(default_factory=list)
    registries: list[RegistryConfig] = Field(default_factory=list)
    executors: list[ExecutorSpec] = Field(default_factory=list)

    @field_validator("executors")
    @classmethod
    def unique_executor_ids(cls, executors: list[ExecutorSpec]) -> list[ExecutorSpec]:
        ids = [executor.id for executor in executors]
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        if duplicates:
            raise ValueError(f"duplicate executor ids: {', '.join(duplicates)}")
        return executors

    @field_validator("resources")
    @classmethod
    def unique_resource_ids(
        cls, resources: list[SubscriptionResource]
    ) -> list[SubscriptionResource]:
        ids = [resource.id for resource in resources]
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        if duplicates:
            raise ValueError(f"duplicate resource ids: {', '.join(duplicates)}")
        return resources

    @field_validator("capabilities")
    @classmethod
    def unique_capability_ids(
        cls, capabilities: list[CapabilityDefinition]
    ) -> list[CapabilityDefinition]:
        ids = [definition.capability for definition in capabilities]
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        if duplicates:
            raise ValueError(f"duplicate capability definitions: {', '.join(duplicates)}")
        return capabilities

    @model_validator(mode="after")
    def ensure_policy_names(self) -> Manifest:
        for key, policy in self.policies.items():
            if policy.name != key:
                policy.name = key
        # Built-in policies are merged by the config loader/Router after model
        # validation, so a manifest may define only its custom policies here.
        resource_ids = {resource.id for resource in self.resources}
        for executor in self.executors:
            if executor.resource_pool and executor.resource_pool not in resource_ids:
                raise ValueError(
                    f"executor {executor.id!r} references unknown resource_pool "
                    f"{executor.resource_pool!r}"
                )
        return self


class ScoreBreakdown(StrictModel):
    monetary: float = 0.0
    cash: float = 0.0
    policy_valuation: float = 0.0
    latency: float = 0.0
    compute: float = 0.0
    subscription: float = 0.0
    reliability: float = 0.0
    quality: float = 0.0
    risk: float = 0.0
    uncertainty: float = 0.0
    cash_uncertainty: float = 0.0
    locality_adjustment: float = 0.0
    total: float = 0.0


class CandidateScore(StrictModel):
    executor_id: str
    feasible: bool
    rejection_reasons: list[str] = Field(default_factory=list)
    estimate: RouteEstimate
    resource_pool: str | None = None
    subscription_quota: SubscriptionQuota | None = None
    score: ScoreBreakdown | None = None
    rank: int | None = None


class RouteDecision(StrictModel):
    decision_id: str = Field(default_factory=lambda: new_id("dec"))
    action: ActionRequest
    policy: PolicyConfig
    selected_executor_id: str | None = None
    candidates: list[CandidateScore] = Field(default_factory=list)
    action_features: ActionFeatures | None = None
    created_at: datetime = Field(default_factory=utc_now)
    explanation: str = ""


class ExecutionReceipt(StrictModel):
    receipt_id: str = Field(default_factory=lambda: new_id("rcpt"))
    decision_id: str
    action_id: str
    capability: str
    executor_id: str
    executor_kind: ExecutorKind
    status: ExecutionStatus
    attempt: int = Field(default=1, ge=1)
    started_at: datetime = Field(default_factory=utc_now)
    ended_at: datetime = Field(default_factory=utc_now)
    estimated: RouteEstimate
    action_features: ActionFeatures | None = None
    actual_resources: ResourceVector = Field(default_factory=ResourceVector)
    accounting: ResourceAccounting = Field(default_factory=ResourceAccounting)
    transport_success: bool | None = None
    execution_success: bool | None = None
    schema_valid: bool | None = None
    task_valid: bool | None = None
    quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    validation_results: list[ValidationResult] = Field(default_factory=list)
    output_valid: bool | None = None
    error_type: str | None = None
    error_message: str | None = None
    trace_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        return max(0.0, (self.ended_at - self.started_at).total_seconds() * 1000.0)


class ExecutionOutcome(StrictModel):
    ok: bool
    status: ExecutionStatus
    output: Any = None
    decision: RouteDecision
    receipts: list[ExecutionReceipt] = Field(default_factory=list)
    delegated_instructions: str | None = None


class CompactAlternative(StrictModel):
    executor_id: str
    kind: ExecutorKind
    score: float
    delta: float = Field(ge=0.0)


class CompactRouteDecision(StrictModel):
    decision_id: str
    action_id: str
    capability: str
    selected: str | None = None
    reason: str
    alternatives: list[CompactAlternative] = Field(default_factory=list)
    rejected: int = 0


class CompactReceipt(StrictModel):
    receipt_id: str
    executor_id: str
    status: ExecutionStatus
    resources: ResourceVector
    valid: bool | None = None
    error: str | None = None


class CompactExecutionOutcome(StrictModel):
    ok: bool
    status: ExecutionStatus
    output: Any = None
    decision: CompactRouteDecision
    receipts: list[CompactReceipt] = Field(default_factory=list)
    instructions: str | None = None


class ExternalOutcomeReport(StrictModel):
    decision_id: str
    executor_id: str
    status: ExecutionStatus
    actual_resources: ResourceVector = Field(default_factory=ResourceVector)
    output_valid: bool | None = None
    task_valid: bool | None = None
    quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    validation_results: list[ValidationResult] = Field(default_factory=list)
    quota_observation: SubscriptionQuota | None = None
    error_message: str | None = Field(default=None, max_length=16_384)
    metadata: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    ended_at: datetime | None = None

    @field_validator("status")
    @classmethod
    def terminal_status(cls, value: ExecutionStatus) -> ExecutionStatus:
        if value in {
            ExecutionStatus.DELEGATED,
            ExecutionStatus.HOST_SELECTED,
            ExecutionStatus.UNKNOWN,
        }:
            raise ValueError("external outcome status must be final")
        return value

    @model_validator(mode="after")
    def consistent_validity(self) -> ExternalOutcomeReport:
        if self.status != ExecutionStatus.SUCCESS and self.output_valid is True:
            raise ValueError("a non-success external outcome cannot declare output_valid=true")
        if self.status != ExecutionStatus.SUCCESS and self.task_valid is True:
            raise ValueError("a non-success external outcome cannot declare task_valid=true")
        return self


class SignedExecutionReceipt(StrictModel):
    receipt: ExecutionReceipt
    signature: SignatureEnvelope
    canonical_version: Literal[1, 2] = 1


class Observation(StrictModel):
    observation_id: str = Field(default_factory=lambda: new_id("obs"))
    provider_id: str | None = None
    executor_id: str
    capability: str
    receipt_id: str | None = None
    resources: ResourceVector = Field(default_factory=ResourceVector)
    accounting: ResourceAccounting = Field(default_factory=ResourceAccounting)
    transport_success: bool | None = None
    execution_success: bool | None = None
    schema_valid: bool | None = None
    task_valid: bool | None = None
    quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    trust: TrustLevel = TrustLevel.UNTRUSTED
    observed_at: datetime = Field(default_factory=utc_now)
    attestation: SignatureEnvelope | None = None


class TraceCallKind(StrEnum):
    MODEL = "model"
    TOOL = "tool"
    BROWSER = "browser"
    COMMAND = "command"
    MCP = "mcp"
    HTTP = "http"
    UNKNOWN = "unknown"


class TraceCall(StrictModel):
    trace_id: str | None = None
    span_id: str | None = None
    name: str
    capability: str | None = None
    executor_id: str | None = None
    kind: TraceCallKind = TraceCallKind.UNKNOWN
    provider: str | None = None
    model: str | None = None
    status: Literal["success", "failed", "unknown"] = "unknown"
    retries: int = Field(default=0, ge=0)
    resources: ResourceVector = Field(default_factory=ResourceVector)


class PassiveRecommendation(StrictModel):
    capability: str
    observed_kind: TraceCallKind
    recommended_executor_id: str
    estimated_cash_saving_usd: float | None = Field(default=None, ge=0.0)
    estimated_latency_saving_ms: float = Field(default=0.0, ge=0.0)
    reason: str


class TraceProfileReport(StrictModel):
    calls: list[TraceCall] = Field(default_factory=list)
    total_resources: ResourceVector = Field(default_factory=ResourceVector)
    retries: int = Field(default=0, ge=0)
    failures: int = Field(default=0, ge=0)
    unmapped_calls: int = Field(default=0, ge=0)
    recommendations: list[PassiveRecommendation] = Field(default_factory=list)
    recorded_receipt_ids: list[str] = Field(default_factory=list)


class ProviderReputation(StrictModel):
    provider_id: str
    capability: str
    executions: int = 0
    success_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    task_valid_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    latency_p50_ms: float | None = Field(default=None, ge=0.0)
    latency_p95_ms: float | None = Field(default=None, ge=0.0)
    actual_cost_mean_usd: float | None = Field(default=None, ge=0.0)
    trust_floor: TrustLevel = TrustLevel.OBSERVED


class ProviderDescriptor(StrictModel):
    provider_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:-]+$")
    name: str = Field(min_length=1, max_length=200)
    capabilities: list[CapabilityDefinition] = Field(default_factory=list)
    executors: list[ExecutorSpec] = Field(default_factory=list)
    quote_endpoint: str | None = None
    health_endpoint: str | None = None
    signing_key_id: str | None = None
    trust: TrustLevel = TrustLevel.SELF_ASSERTED
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def bind_provider(self) -> ProviderDescriptor:
        for executor in self.executors:
            if executor.provider_id is None:
                executor.provider_id = self.provider_id
            elif executor.provider_id != self.provider_id:
                raise ValueError(f"executor {executor.id!r} provider_id does not match descriptor")
        return self


class RegistryConfig(StrictModel):
    id: str = Field(min_length=1, max_length=200)
    kind: Literal["local", "remote"]
    path: str | None = None
    url: str | None = None
    enabled: bool = True
    allowed_hosts: list[str] | None = None
    allow_private_networks: bool = False
    allow_insecure_http: bool = False
    timeout_seconds: float = Field(default=10.0, gt=0.0, le=120.0)
    max_response_bytes: int = Field(default=1_000_000, ge=1024, le=10_000_000)

    @model_validator(mode="after")
    def required_location(self) -> RegistryConfig:
        if self.kind == "local" and not self.path:
            raise ValueError("local registry requires path")
        if self.kind == "remote" and not self.url:
            raise ValueError("remote registry requires url")
        return self


class BenchmarkEntry(StrictModel):
    executor_id: str
    executor_kind: ExecutorKind
    decision_id: str | None = None
    receipt_id: str | None = None
    ok: bool = False
    status: ExecutionStatus | None = None
    estimated: RouteEstimate | None = None
    actual_resources: ResourceVector | None = None
    accounting: ResourceAccounting | None = None
    counterfactual_costs: list[CounterfactualCashCost] = Field(default_factory=list)
    policy_valuations: list[PolicyValuation] = Field(default_factory=list)
    output_valid: bool | None = None
    actual_score: ScoreBreakdown | None = None
    actual_rank: int | None = None
    skipped_reason: str | None = None
    error_message: str | None = None


class BenchmarkResult(StrictModel):
    benchmark_id: str = Field(default_factory=lambda: new_id("bench"))
    action_id: str
    capability: str
    policy: str
    route_decision_id: str
    entries: list[BenchmarkEntry] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class EconomicMetrics(StrictModel):
    decisions: int = 0
    successful_actions: int = 0
    failed_actions: int = 0
    model_actions_avoided: int = 0
    model_turns_avoided: int = 0
    context_tokens_avoided: int = 0
    subscription_capacity_conserved: float = 0.0
    local_cpu_ms_consumed: float = 0.0
    api_money_spent_usd: float | None = None
    wall_clock_time_saved_ms: float = 0.0
    browser_actions_avoided: int = 0
    mcp_calls_avoided: int = 0
    cli_substitutions: int = 0
    total_money_spent_usd: float | None = None
    cost_per_successful_action_usd: float | None = None
    actual_cash_known_subtotal_usd: Decimal = Decimal(0)
    actual_cash_total_usd: Decimal | None = None
    cash_status: EvidenceStatus = EvidenceStatus.UNAVAILABLE
    subscription_usage: list[SubscriptionUsage] = Field(default_factory=list)


class CounterfactualAlternative(StrictModel):
    executor_id: str
    executor_kind: ExecutorKind
    estimated_resources: ResourceVector
    estimated_score: float | None = None
    estimated_cash_saving_usd: float | None = None
    estimated_latency_saving_ms: float = 0.0
    conserves_subscription_units: float = 0.0


class CounterfactualReport(StrictModel):
    receipt_id: str
    decision_id: str
    selected_executor_id: str
    actual_resources: ResourceVector
    alternatives: list[CounterfactualAlternative] = Field(default_factory=list)
    best_alternative_executor_id: str | None = None
    potential_cash_saving_usd: float | None = None
    potential_cash_saving_percent: float | None = None
    avoidable_subscription_units: float = 0.0
    subscription_pressure: QuotaState | None = None
    actual_cash_comparison: EvidenceStatus = EvidenceStatus.UNAVAILABLE
    actual_cash_saving_usd: Decimal | None = None
    explanation: str = ""


class RawExecution(StrictModel):
    status: ExecutionStatus
    output: Any = None
    resources: ResourceVector = Field(default_factory=ResourceVector)
    accounting: ResourceAccounting = Field(default_factory=ResourceAccounting)
    stdout: str | None = None
    stderr: str | None = None
    exit_code: int | None = None
    error_type: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
