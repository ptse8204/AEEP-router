"""Protocol and runtime models.

The models intentionally preserve raw resource dimensions rather than converting
all usage into a synthetic token or currency. A policy can assign local shadow
prices or weights without losing the original measurements.
"""

from __future__ import annotations

from datetime import UTC, datetime
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
    DELEGATED = "delegated"
    UNKNOWN = "unknown"


class EstimateSource(StrEnum):
    STATIC = "static"
    HISTORICAL = "historical"
    BLENDED = "blended"
    QUOTE = "quote"
    OBSERVED = "observed"


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
    output_tokens: int = Field(default=0, ge=0)

    def plus(self, other: "ResourceVector") -> "ResourceVector":
        return ResourceVector(
            **{
                field: getattr(self, field) + getattr(other, field)
                for field in type(self).model_fields
            }
        )

    def scale(self, factor: float) -> "ResourceVector":
        values: dict[str, float | int] = {}
        integer_fields = {"network_bytes", "context_tokens", "input_tokens", "output_tokens"}
        for field in type(self).model_fields:
            value = getattr(self, field) * factor
            values[field] = int(round(value)) if field in integer_fields else float(value)
        return ResourceVector(**values)


class RouteEstimate(StrictModel):
    resources: ResourceVector = Field(default_factory=ResourceVector)
    success_probability: float = Field(default=0.95, ge=0.001, le=1.0)
    quality_score: float = Field(default=0.95, ge=0.0, le=1.0)
    risk_score: float = Field(default=0.05, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: EstimateSource = EstimateSource.STATIC
    sample_size: int = Field(default=0, ge=0)


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
    config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_network_locality(self) -> "ExecutorSpec":
        if self.locality == Locality.INTERNET and not self.requires_network:
            self.requires_network = True
        if self.kind == ExecutorKind.DELEGATE and self.safe_to_auto_execute:
            # Delegates are plans for the host agent; AEEP cannot enforce their execution.
            self.safe_to_auto_execute = False
        return self


class MetricWeights(StrictModel):
    monetary: float = Field(default=0.30, ge=0.0)
    latency: float = Field(default=0.25, ge=0.0)
    compute: float = Field(default=0.25, ge=0.0)
    reliability: float = Field(default=0.10, ge=0.0)
    quality: float = Field(default=0.05, ge=0.0)
    risk: float = Field(default=0.05, ge=0.0)

    @model_validator(mode="after")
    def nonzero(self) -> "MetricWeights":
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
    prefer_local_bonus: float = Field(default=0.05, ge=0.0, le=1.0)
    deterministic_tie_break: bool = True


class PersistenceConfig(StrictModel):
    """Local persistence controls.

    Decisions are useful for delegated outcome reporting and auditability, but
    action inputs and caller context can contain secrets or personal data. They
    are redacted from SQLite by default while the in-memory/returned decision
    remains complete.
    """

    store_action_inputs: bool = False
    store_action_context: bool = False


class Manifest(StrictModel):
    version: Literal["0.1"] = "0.1"
    database: str = ".aeep/aeep.db"
    default_policy: str = "balanced"
    persistence: PersistenceConfig = Field(default_factory=PersistenceConfig)
    policies: dict[str, PolicyConfig] = Field(default_factory=dict)
    executors: list[ExecutorSpec] = Field(default_factory=list)

    @field_validator("executors")
    @classmethod
    def unique_executor_ids(cls, executors: list[ExecutorSpec]) -> list[ExecutorSpec]:
        ids = [executor.id for executor in executors]
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        if duplicates:
            raise ValueError(f"duplicate executor ids: {', '.join(duplicates)}")
        return executors

    @model_validator(mode="after")
    def ensure_policy_names(self) -> "Manifest":
        for key, policy in self.policies.items():
            if policy.name != key:
                policy.name = key
        # Built-in policies are merged by the config loader/Router after model
        # validation, so a manifest may define only its custom policies here.
        return self


class ScoreBreakdown(StrictModel):
    monetary: float = 0.0
    latency: float = 0.0
    compute: float = 0.0
    reliability: float = 0.0
    quality: float = 0.0
    risk: float = 0.0
    locality_adjustment: float = 0.0
    total: float = 0.0


class CandidateScore(StrictModel):
    executor_id: str
    feasible: bool
    rejection_reasons: list[str] = Field(default_factory=list)
    estimate: RouteEstimate
    score: ScoreBreakdown | None = None
    rank: int | None = None


class RouteDecision(StrictModel):
    decision_id: str = Field(default_factory=lambda: new_id("dec"))
    action: ActionRequest
    policy: PolicyConfig
    selected_executor_id: str | None = None
    candidates: list[CandidateScore] = Field(default_factory=list)
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
    actual_resources: ResourceVector = Field(default_factory=ResourceVector)
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


class ExternalOutcomeReport(StrictModel):
    decision_id: str
    executor_id: str
    status: ExecutionStatus
    actual_resources: ResourceVector = Field(default_factory=ResourceVector)
    output_valid: bool | None = None
    error_message: str | None = Field(default=None, max_length=16_384)
    metadata: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    ended_at: datetime | None = None

    @field_validator("status")
    @classmethod
    def terminal_status(cls, value: ExecutionStatus) -> ExecutionStatus:
        if value in {ExecutionStatus.DELEGATED, ExecutionStatus.UNKNOWN}:
            raise ValueError("external outcome status must be final")
        return value

    @model_validator(mode="after")
    def consistent_validity(self) -> "ExternalOutcomeReport":
        if self.status != ExecutionStatus.SUCCESS and self.output_valid is True:
            raise ValueError("a non-success external outcome cannot declare output_valid=true")
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


class RawExecution(StrictModel):
    status: ExecutionStatus
    output: Any = None
    resources: ResourceVector = Field(default_factory=ResourceVector)
    stdout: str | None = None
    stderr: str | None = None
    exit_code: int | None = None
    error_type: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
