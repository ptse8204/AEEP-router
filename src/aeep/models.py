"""Protocol and runtime models.

The models intentionally preserve raw resource dimensions rather than converting
all usage into a synthetic token or currency. A policy can assign local shadow
prices or weights without losing the original measurements.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class CashAccounting(StrictModel):
    status: EvidenceStatus = EvidenceStatus.UNAVAILABLE
    components: list[CashEvidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def detect_conflicts(self) -> CashAccounting:
        if self.status == EvidenceStatus.COMPLETE and not self.components:
            raise ValueError("complete cash accounting requires at least one charge component")
        for charge_id in {item.charge_id for item in self.components}:
            known = [
                item
                for item in self.components
                if item.charge_id == charge_id and item.amount is not None
            ]
            billed = [
                item
                for item in known
                if item.classification
                in {CashClassification.VERIFIED, CashClassification.BILLING_RECONCILED}
            ]
            choices = billed or known
            if len({(item.amount, item.currency) for item in choices}) > 1:
                object.__setattr__(self, "status", EvidenceStatus.CONFLICT)
        return self

    def resolved_components(self) -> list[CashEvidence]:
        """Return one non-conflicting component per charge without double counting."""
        resolved: list[CashEvidence] = []
        for charge_id in dict.fromkeys(item.charge_id for item in self.components):
            group = [item for item in self.components if item.charge_id == charge_id]
            known = [item for item in group if item.amount is not None]
            if not known:
                continue
            billed = [
                item
                for item in known
                if item.classification
                in {CashClassification.VERIFIED, CashClassification.BILLING_RECONCILED}
            ]
            choices = billed or known
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


class Manifest(StrictModel):
    version: Literal["0.1", "0.15", "0.2", "0.3"] = "0.3"
    database: str = ".aeep/aeep.db"
    default_policy: str = "balanced"
    persistence: PersistenceConfig = Field(default_factory=PersistenceConfig)
    signing: SigningConfig | None = None
    budget: AgentBudget | None = None
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
    estimated_cash_saving_usd: float = Field(default=0.0, ge=0.0)
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
    api_money_spent_usd: float = 0.0
    wall_clock_time_saved_ms: float = 0.0
    browser_actions_avoided: int = 0
    mcp_calls_avoided: int = 0
    cli_substitutions: int = 0
    total_money_spent_usd: float = 0.0
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
    estimated_cash_saving_usd: float = 0.0
    estimated_latency_saving_ms: float = 0.0
    conserves_subscription_units: float = 0.0


class CounterfactualReport(StrictModel):
    receipt_id: str
    decision_id: str
    selected_executor_id: str
    actual_resources: ResourceVector
    alternatives: list[CounterfactualAlternative] = Field(default_factory=list)
    best_alternative_executor_id: str | None = None
    potential_cash_saving_usd: float = 0.0
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
