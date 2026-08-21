"""Isolated repeated benchmark campaigns and bounded Codex JSONL usage capture."""

from __future__ import annotations

import hashlib
import json
import math
import random
import sqlite3
import time
from collections.abc import Callable, Iterable
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from statistics import median
from typing import Any, Literal, cast

from pydantic import Field, model_validator

from .accounting import (
    aggregate_accounting,
    price_model_usage,
    subscription_usage_from_tokens,
)
from .codex_capture import parse_codex_jsonl as parse_codex_jsonl
from .errors import ConfigurationError
from .models import (
    ActionRequest,
    CandidateScore,
    CashAccounting,
    CashEstimate,
    CounterfactualCashCost,
    CurrencyAmount,
    EconomicEvidenceLevel,
    EconomicStrictModel,
    EstimateSource,
    EvidenceSource,
    EvidenceStatus,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    Locality,
    MeasurementEvidence,
    ModelAccessChannel,
    NonNegativeDecimal,
    RateCardSnapshot,
    RateType,
    ResourceAccounting,
    ResourceVector,
    RouteEstimate,
    SideEffect,
    StrictModel,
    SubscriptionUsage,
    TrustLevel,
    UtcDateTime,
    ValidationSpec,
    new_id,
    utc_now,
)
from .policy import merge_constraints
from .qualification import RouteLifecycle, behavior_fingerprint
from .router import Router
from .scoring import add_subscription_vector, score_candidate
from .templates import extract_path
from .validators import ValidationContext, run_validators
from .workflow import WorkflowRequest, WorkflowStatus, pointer_get, pointer_replace


class BenchmarkCondition(StrEnum):
    PROCESS_COLD = "process-cold"
    ROUTER_WARM = "router-warm"


class BenchmarkSplit(StrEnum):
    QUALIFICATION = "qualification"
    TRAINING = "training"
    HOLDOUT = "holdout"


class BenchmarkPhase(StrEnum):
    SETUP = "setup"
    QUALIFICATION = "qualification"
    MEASUREMENT = "measurement"
    HOLDOUT = "holdout"


class BenchmarkCase(StrictModel):
    case_id: str = Field(min_length=1, max_length=200)
    split: BenchmarkSplit
    action: ActionRequest
    validators: list[ValidationSpec] = Field(default_factory=list)


class BenchmarkRoute(StrictModel):
    route_id: str = Field(min_length=1, max_length=200)
    executor_id: str | None = None
    workflow: WorkflowRequest | None = None
    provider: str | None = None
    model: str | None = None
    access_channel: ModelAccessChannel = ModelAccessChannel.UNKNOWN
    actual_rate_snapshot_id: str | None = None
    counterfactual_rate_snapshot_id: str | None = None
    subscription_rate_snapshot_id: str | None = None
    subscription_resource_pool: str | None = None
    subscription_unit: str = "provider_unit"
    validation_output_path: str | None = None

    @model_validator(mode="after")
    def valid_accounting_bindings(self) -> BenchmarkRoute:
        if (self.executor_id is None) == (self.workflow is None):
            raise ValueError("benchmark routes require exactly one executor_id or workflow")
        if self.actual_rate_snapshot_id and self.access_channel != ModelAccessChannel.API:
            raise ValueError("actual rate snapshots require API access_channel")
        if self.subscription_rate_snapshot_id and not self.subscription_resource_pool:
            raise ValueError("subscription rate snapshots require a resource pool")
        return self


class BenchmarkSuite(StrictModel):
    schema_version: Literal["0.3"] = "0.3"
    suite_id: str = Field(default_factory=lambda: new_id("suite"))
    domain: str = Field(default="unspecified", min_length=1, max_length=200)
    deterministic_tools_available: bool = False
    seed: int = 0
    repetitions: int = Field(default=30, ge=1, le=1000)
    routes: list[BenchmarkRoute] = Field(min_length=1)
    conditions: list[BenchmarkCondition] = Field(
        default_factory=lambda: [BenchmarkCondition.PROCESS_COLD, BenchmarkCondition.ROUTER_WARM]
    )
    pricing_snapshots: list[RateCardSnapshot] = Field(default_factory=list)
    cases: list[BenchmarkCase] = Field(min_length=1)
    baseline_route_id: str | None = None
    acknowledge_cash_risk: bool = False
    max_total_cash_usd: Decimal | None = Field(default=None, ge=0)
    allow_zero_subscription_weight: bool = False

    @model_validator(mode="after")
    def unique_ids(self) -> BenchmarkSuite:
        for values, label in (
            ([route.route_id for route in self.routes], "route"),
            ([case.case_id for case in self.cases], "case"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate benchmark {label} id")
        route_ids = {route.route_id for route in self.routes}
        if self.baseline_route_id is not None and self.baseline_route_id not in route_ids:
            raise ValueError("baseline_route_id is not a benchmark route")
        return self


class BenchmarkTrial(StrictModel):
    trial_id: str
    run_id: str
    suite_id: str
    case_id: str
    route_id: str
    route_fingerprint: str | None = None
    condition: BenchmarkCondition
    repetition: int = Field(ge=0)
    phase: BenchmarkPhase
    state: str = Field(pattern=r"^(running|complete|failed|skipped)$")
    started_at: datetime = Field(default_factory=utc_now)
    ended_at: datetime | None = None
    ok: bool = False
    valid: bool | None = None
    status: ExecutionStatus | None = None
    wall_time_ms: float | None = Field(default=None, ge=0)
    actual_resources: ResourceVector = Field(default_factory=ResourceVector)
    accounting: ResourceAccounting = Field(default_factory=ResourceAccounting)
    model_usage_complete: bool = False
    counterfactual_costs: list[CounterfactualCashCost] = Field(default_factory=list)
    receipt_ids: list[str] = Field(default_factory=list)
    operation_count: int = Field(default=0, ge=0)
    retry_fallback_count: int = Field(default=0, ge=0)
    intervention_count: int = Field(default=0, ge=0)
    cache_hit_verified: bool | None = None
    policy_score: float | None = None
    error_type: str | None = None
    error_message: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def infer_measured_model_usage(self) -> BenchmarkTrial:
        if self.accounting.model_usage and all(
            usage.evidence.status == EvidenceStatus.COMPLETE
            for usage in self.accounting.model_usage
        ):
            object.__setattr__(self, "model_usage_complete", True)
        return self


class BenchmarkSummary(StrictModel):
    route_id: str
    condition: BenchmarkCondition
    trials: int
    attempted: int
    completed: int
    valid: int
    success_rate: float
    success_wilson_low: float
    success_wilson_high: float
    median_wall_time_ms: float | None
    p95_wall_time_ms: float | None
    mad_wall_time_ms: float | None
    operation_count: int
    retry_fallback_count: int
    intervention_count: int
    warm_cache_evidence_coverage: str
    cash_evidence_coverage: str
    subscription_evidence_coverage: str


class BenchmarkDelta(StrictModel):
    route_id: str
    baseline_route_id: str
    condition: BenchmarkCondition
    paired_trials: int
    median_wall_time_delta_ms: float | None
    bootstrap_low_ms: float | None
    bootstrap_high_ms: float | None


class BenchmarkOracle(StrictModel):
    case_id: str
    condition: BenchmarkCondition
    repetition: int
    selected_route_id: str | None = None
    policy_route_id: str | None = None
    cash_route_id: str | None = None
    token_route_id: str | None = None
    latency_route_id: str | None = None
    selected_within_10_percent: bool | None = None


class SubscriptionConservation(StrictModel):
    route_id: str
    condition: BenchmarkCondition
    resource_pool: str
    unit: str
    measured_trials: int
    total_trials: int
    median_consumed: Decimal | None


class BenchmarkCampaignReport(StrictModel):
    run_id: str
    suite_id: str
    domain: str
    deterministic_tools_available: bool
    pricing_snapshot_ids: list[str]
    frozen_holdout_decisions: dict[str, str | None]
    trials: list[BenchmarkTrial]
    summaries: list[BenchmarkSummary]
    baseline_deltas: list[BenchmarkDelta]
    oracles: list[BenchmarkOracle]
    subscription_conservation: list[SubscriptionConservation]


class BenchmarkRevaluationReport(StrictModel):
    schema_version: Literal["0.3"] = "0.3"
    revaluation_id: str
    source_run_id: str
    source_report_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    pricing_snapshot_id: str = Field(pattern=r"^rate_[a-f0-9]{64}$")
    created_at: datetime = Field(default_factory=utc_now)
    trial_values: dict[str, list[CounterfactualCashCost]]


class ReleaseGate(StrictModel):
    name: str
    passed: bool
    detail: str


class ReleaseProofReport(StrictModel):
    passed: bool
    gates: list[ReleaseGate]


class EconomicBenchmarkRouteType(StrEnum):
    """Transport or funding shape measured by an AEEP 0.4 proof trial."""

    LOCAL_PYTHON = "local-python"
    LOCAL_CLI = "local-cli"
    DIRECT_HTTP = "direct-http"
    LOCAL_MCP = "local-mcp"
    USAGE_PRICED_PROVIDER = "usage-priced-provider"
    SUBSCRIPTION_BASELINE = "subscription-baseline"
    HYBRID = "aeep-hybrid"


class EconomicBenchmarkTrial(EconomicStrictModel):
    """Sanitized measured economics for one existing benchmark trial."""

    schema_version: Literal["0.4"] = "0.4"
    trial_id: str = Field(min_length=1, max_length=300)
    case_id: str = Field(min_length=1, max_length=200)
    route_id: str = Field(min_length=1, max_length=200)
    route_type: EconomicBenchmarkRouteType
    condition: BenchmarkCondition
    split: BenchmarkSplit
    repetition: int = Field(ge=0)
    task_valid: bool
    selected_by_aeep: bool = False
    prepared_id: str | None = Field(default=None, max_length=200)
    quote_id: str | None = Field(default=None, max_length=200)
    settlement_id: str | None = Field(default=None, max_length=200)
    charge_id: str | None = Field(default=None, max_length=200)
    expected_cash: CurrencyAmount | None = None
    maximum_cash: CurrencyAmount | None = None
    reserved_cash: CurrencyAmount | None = None
    captured_cash: CurrencyAmount | None = None
    released_cash: CurrencyAmount | None = None
    cash_evidence_level: EconomicEvidenceLevel = EconomicEvidenceLevel.UNKNOWN
    preparation_latency_ms: NonNegativeDecimal
    quote_latency_ms: NonNegativeDecimal
    execution_latency_ms: NonNegativeDecimal
    settlement_latency_ms: NonNegativeDecimal
    total_wall_time_ms: NonNegativeDecimal
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cached_tokens: int = Field(default=0, ge=0)
    tool_schema_tokens: int = Field(default=0, ge=0)
    tool_result_tokens: int = Field(default=0, ge=0)
    model_usage_complete: bool = False
    local_resources_complete: bool = False
    synthetic_usage: bool = False
    cpu_ms: NonNegativeDecimal = Decimal(0)
    peak_memory_mb: NonNegativeDecimal = Decimal(0)
    network_bytes: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)
    fallback_count: int = Field(default=0, ge=0)
    quote_failure_codes: tuple[str, ...] = ()
    settlement_failure_code: str | None = Field(default=None, max_length=100)
    indeterminate: bool = False

    @model_validator(mode="after")
    def valid_economic_chain(self) -> EconomicBenchmarkTrial:
        amounts = [
            amount
            for amount in (
                self.expected_cash,
                self.maximum_cash,
                self.reserved_cash,
                self.captured_cash,
                self.released_cash,
            )
            if amount is not None
        ]
        if len({amount.currency for amount in amounts}) > 1:
            raise ValueError("benchmark economic amounts must use one currency")
        if (
            self.expected_cash is not None
            and self.maximum_cash is not None
            and self.expected_cash.amount > self.maximum_cash.amount
        ):
            raise ValueError("benchmark expected cash cannot exceed maximum cash")
        if (
            self.reserved_cash is not None
            and self.maximum_cash is not None
            and self.reserved_cash.amount > self.maximum_cash.amount
        ):
            raise ValueError("benchmark reservation cannot exceed the signed maximum")
        if (
            any(
                amount is not None
                for amount in (self.reserved_cash, self.captured_cash, self.released_cash)
            )
            and self.maximum_cash is None
        ):
            raise ValueError("benchmark settlement evidence requires a signed maximum")
        if self.captured_cash is not None:
            if self.reserved_cash is None:
                raise ValueError("benchmark captured cash requires a reservation")
            if (
                self.maximum_cash is not None
                and self.captured_cash.amount > self.maximum_cash.amount
            ):
                raise ValueError("benchmark captured cash cannot exceed the signed maximum")
            if self.captured_cash.amount > self.reserved_cash.amount:
                raise ValueError("benchmark captured cash cannot exceed its reservation")
        if self.released_cash is not None and self.reserved_cash is None:
            raise ValueError("benchmark released cash requires a reservation")
        if self.captured_cash is not None and self.released_cash is not None:
            assert self.reserved_cash is not None
            accounted = self.captured_cash.amount + self.released_cash.amount
            if accounted > self.reserved_cash.amount:
                raise ValueError("benchmark capture plus release exceeds its reservation")
            if (
                self.settlement_id is not None
                and not self.indeterminate
                and accounted != self.reserved_cash.amount
            ):
                raise ValueError("completed benchmark settlement must release its remainder")
        if self.captured_cash is not None:
            if self.settlement_id is None:
                raise ValueError("captured benchmark cash requires a settlement receipt")
            if not self.cash_evidence_level.is_payment_evidence:
                raise ValueError("captured benchmark cash requires settlement evidence")
        if self.cash_evidence_level is EconomicEvidenceLevel.UNKNOWN and amounts:
            raise ValueError("unknown benchmark cash cannot carry an amount")
        if self.indeterminate and self.settlement_failure_code is None:
            raise ValueError("indeterminate benchmark trials require a settlement failure code")
        measured = (
            self.preparation_latency_ms
            + self.quote_latency_ms
            + self.execution_latency_ms
            + self.settlement_latency_ms
        )
        if self.total_wall_time_ms < measured:
            raise ValueError("benchmark total time cannot be shorter than its measured stages")
        return self


class EconomicWorkflowProofTrial(EconomicStrictModel):
    """Measured proof for one caller-authored prepared economic workflow.

    Workflow trials are kept outside the single-action route oracle because a
    multi-step DAG is not an interchangeable route for one bounded action.
    """

    schema_version: Literal["0.4"] = "0.4"
    workflow_id: str = Field(min_length=1, max_length=200)
    condition: BenchmarkCondition
    split: BenchmarkSplit
    repetition: int = Field(ge=0)
    task_valid: bool
    dependency_binding_verified: bool
    step_count: int = Field(ge=2, le=64)
    prepared_step_count: int = Field(ge=0, le=64)
    quoted_step_count: int = Field(ge=0, le=64)
    settled_step_count: int = Field(ge=0, le=64)
    dependency_input_bytes: int = Field(ge=0)
    expected_cash: CurrencyAmount
    maximum_cash: CurrencyAmount
    reserved_cash: CurrencyAmount
    captured_cash: CurrencyAmount
    released_cash: CurrencyAmount
    cash_evidence_level: EconomicEvidenceLevel
    preparation_latency_ms: NonNegativeDecimal
    quote_latency_ms: NonNegativeDecimal
    execution_latency_ms: NonNegativeDecimal
    settlement_latency_ms: NonNegativeDecimal
    total_wall_time_ms: NonNegativeDecimal

    @model_validator(mode="after")
    def valid_workflow_evidence(self) -> EconomicWorkflowProofTrial:
        if self.prepared_step_count != self.step_count:
            raise ValueError("workflow proof must prepare every executed step")
        if self.quoted_step_count > self.prepared_step_count:
            raise ValueError("workflow proof cannot quote more steps than it prepares")
        if self.settled_step_count > self.quoted_step_count:
            raise ValueError("workflow proof cannot settle more steps than it quotes")
        amounts = (
            self.expected_cash,
            self.maximum_cash,
            self.reserved_cash,
            self.captured_cash,
            self.released_cash,
        )
        if len({amount.currency for amount in amounts}) != 1:
            raise ValueError("workflow proof amounts must use one currency")
        if self.expected_cash.amount > self.maximum_cash.amount:
            raise ValueError("workflow expected cash cannot exceed its maximum")
        if self.reserved_cash.amount > self.maximum_cash.amount:
            raise ValueError("workflow reservation cannot exceed its maximum")
        if self.captured_cash.amount > self.reserved_cash.amount:
            raise ValueError("workflow capture cannot exceed its reservation")
        if self.captured_cash.amount + self.released_cash.amount != self.reserved_cash.amount:
            raise ValueError("workflow settlement must release the reservation remainder")
        if self.settled_step_count and not self.cash_evidence_level.is_payment_evidence:
            raise ValueError("settled workflow proof requires payment evidence")
        measured = (
            self.preparation_latency_ms
            + self.quote_latency_ms
            + self.execution_latency_ms
            + self.settlement_latency_ms
        )
        if self.total_wall_time_ms < measured:
            raise ValueError("workflow total time cannot be shorter than its measured stages")
        return self


class EconomicBenchmarkOracle(EconomicStrictModel):
    """Cheapest task-valid route with authoritative actual-cash evidence."""

    case_id: str
    condition: BenchmarkCondition
    repetition: int = Field(ge=0)
    selected_route_id: str | None = None
    oracle_route_id: str | None = None
    selected_captured_cash: CurrencyAmount | None = None
    oracle_captured_cash: CurrencyAmount | None = None
    distance_from_oracle_percent: NonNegativeDecimal | None = None
    selected_within_10_percent: bool | None = None
    eligible_route_ids: tuple[str, ...] = ()


class EconomicProofCampaignReport(EconomicStrictModel):
    """AEEP 0.4 proof report that leaves the frozen 0.3 campaign schema intact."""

    schema_version: Literal["0.4"] = "0.4"
    campaign_id: str = Field(min_length=1, max_length=200)
    domain: str = Field(min_length=1, max_length=200)
    settlement_currency: str = Field(pattern=r"^[A-Z]{3}$")
    repetitions: int = Field(ge=1)
    generated_at: UtcDateTime
    trials: tuple[EconomicBenchmarkTrial, ...]
    workflow_trials: tuple[EconomicWorkflowProofTrial, ...] = ()
    hybrid_training_observations: int = Field(default=0, ge=0)
    oracles: tuple[EconomicBenchmarkOracle, ...] = ()
    gates: tuple[ReleaseGate, ...] = ()

    @model_validator(mode="after")
    def valid_report(self) -> EconomicProofCampaignReport:
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("economic proof generated_at must be timezone-aware")
        trial_ids = [trial.trial_id for trial in self.trials]
        if len(trial_ids) != len(set(trial_ids)):
            raise ValueError("economic proof trial IDs must be unique")
        for trial in self.trials:
            for amount in (
                trial.expected_cash,
                trial.maximum_cash,
                trial.reserved_cash,
                trial.captured_cash,
                trial.released_cash,
            ):
                if amount is not None and amount.currency != self.settlement_currency:
                    raise ValueError("economic proof amount uses another settlement currency")
        workflow_ids = [workflow_trial.workflow_id for workflow_trial in self.workflow_trials]
        if len(workflow_ids) != len(set(workflow_ids)):
            raise ValueError("economic workflow proof IDs must be unique")
        for workflow_trial in self.workflow_trials:
            for amount in (
                workflow_trial.expected_cash,
                workflow_trial.maximum_cash,
                workflow_trial.reserved_cash,
                workflow_trial.captured_cash,
                workflow_trial.released_cash,
            ):
                if amount.currency != self.settlement_currency:
                    raise ValueError("economic workflow proof uses another settlement currency")
        return self


def economic_settlement_oracles(
    trials: Iterable[EconomicBenchmarkTrial],
) -> tuple[EconomicBenchmarkOracle, ...]:
    """Compare AEEP with settled paid or authoritatively confirmed-free routes."""

    groups: dict[
        tuple[str, BenchmarkCondition, int], list[EconomicBenchmarkTrial]
    ] = {}
    for trial in trials:
        if trial.split is not BenchmarkSplit.HOLDOUT:
            continue
        groups.setdefault((trial.case_id, trial.condition, trial.repetition), []).append(trial)
    oracles: list[EconomicBenchmarkOracle] = []
    for (case_id, condition, repetition), items in sorted(groups.items()):
        selected_items = [item for item in items if item.selected_by_aeep]
        if len(selected_items) > 1:
            raise ConfigurationError("economic proof group has multiple AEEP selections")
        selected = selected_items[0] if selected_items else None
        eligible = [item for item in items if _authoritative_actual_cash(item) is not None]
        oracle = (
            min(
                eligible,
                key=lambda item: (
                    cast(CurrencyAmount, _authoritative_actual_cash(item)).amount,
                    item.route_id,
                ),
            )
            if eligible
            else None
        )
        selected_amount = (
            _authoritative_actual_cash(selected)
            if selected is not None
            else None
        )
        oracle_amount = _authoritative_actual_cash(oracle) if oracle is not None else None
        distance: Decimal | None = None
        within: bool | None = None
        if selected_amount is not None and oracle_amount is not None:
            if selected_amount.currency != oracle_amount.currency:
                raise ConfigurationError("economic oracle routes use different currencies")
            if oracle_amount.amount == 0:
                within = selected_amount.amount == 0
                distance = Decimal(0) if within else None
            else:
                distance = (
                    (selected_amount.amount - oracle_amount.amount)
                    / oracle_amount.amount
                    * Decimal(100)
                )
                within = distance <= Decimal(10)
        oracles.append(
            EconomicBenchmarkOracle(
                case_id=case_id,
                condition=condition,
                repetition=repetition,
                selected_route_id=selected.route_id if selected is not None else None,
                oracle_route_id=oracle.route_id if oracle is not None else None,
                selected_captured_cash=selected_amount,
                oracle_captured_cash=oracle_amount,
                distance_from_oracle_percent=distance,
                selected_within_10_percent=within,
                eligible_route_ids=tuple(sorted(item.route_id for item in eligible)),
            )
        )
    return tuple(oracles)


def _authoritative_actual_cash(
    trial: EconomicBenchmarkTrial,
) -> CurrencyAmount | None:
    if not trial.task_valid or trial.indeterminate:
        return None
    if (
        trial.settlement_id is not None
        and trial.captured_cash is not None
        and trial.cash_evidence_level.is_payment_evidence
    ):
        return trial.captured_cash
    if (
        trial.cash_evidence_level is EconomicEvidenceLevel.OPERATOR_ATTESTED
        and trial.expected_cash is not None
        and trial.maximum_cash is not None
        and trial.expected_cash.amount == 0
        and trial.maximum_cash.amount == 0
        and trial.expected_cash.currency == trial.maximum_cash.currency
        and trial.reserved_cash is None
        and trial.captured_cash is None
        and trial.released_cash is None
    ):
        return trial.maximum_cash
    return None


def evaluate_economic_proof(report: EconomicProofCampaignReport) -> ReleaseProofReport:
    """Evaluate economic gates using settlement records only."""

    completed_paid = [
        trial
        for trial in report.trials
        if trial.task_valid
        and not trial.indeterminate
        and any(
            amount is not None and amount.amount > 0
            for amount in (trial.expected_cash, trial.maximum_cash, trial.captured_cash)
        )
    ]
    paid_with_evidence = [
        trial
        for trial in completed_paid
        if trial.prepared_id is not None
        and trial.quote_id is not None
        and trial.settlement_id is not None
        and trial.maximum_cash is not None
        and trial.reserved_cash is not None
        and trial.captured_cash is not None
        and trial.released_cash is not None
        and trial.cash_evidence_level.is_payment_evidence
    ]
    overcaptures = [
        trial
        for trial in report.trials
        if trial.captured_cash is not None
        and trial.maximum_cash is not None
        and trial.captured_cash.amount > trial.maximum_cash.amount
    ]
    partial_releases = [
        trial
        for trial in report.trials
        if trial.reserved_cash is not None
        and trial.captured_cash is not None
        and trial.released_cash is not None
        and trial.captured_cash.amount < trial.reserved_cash.amount
        and trial.captured_cash.amount + trial.released_cash.amount
        == trial.reserved_cash.amount
    ]
    unknown = [
        trial
        for trial in report.trials
        if trial.cash_evidence_level is EconomicEvidenceLevel.UNKNOWN
    ]
    unknown_clean = [
        trial
        for trial in unknown
        if all(
            amount is None
            for amount in (
                trial.expected_cash,
                trial.maximum_cash,
                trial.reserved_cash,
                trial.captured_cash,
                trial.released_cash,
            )
        )
    ]
    oracle_values = [
        oracle.selected_within_10_percent
        for oracle in report.oracles
        if oracle.selected_within_10_percent is not None
    ]
    oracle_fraction = (
        sum(oracle_values) / len(oracle_values) if oracle_values else 0.0
    )
    gates = [
        ReleaseGate(
            name="zero-overcapture",
            passed=not overcaptures and bool(report.trials),
            detail=f"{len(overcaptures)} overcapture incident(s)",
        ),
        ReleaseGate(
            name="paid-settlement-evidence",
            passed=bool(completed_paid) and len(paid_with_evidence) == len(completed_paid),
            detail=(
                f"{len(paid_with_evidence)}/{len(completed_paid)} paid completed trial(s) "
                "have quote, reservation, capture, and release evidence"
            ),
        ),
        ReleaseGate(
            name="partial-capture-release",
            passed=bool(partial_releases),
            detail=f"{len(partial_releases)} partial settlement(s) released the remainder",
        ),
        ReleaseGate(
            name="unknown-remains-unknown",
            passed=bool(unknown) and len(unknown_clean) == len(unknown),
            detail=f"{len(unknown_clean)}/{len(unknown)} unknown-cash trial(s) retained no amount",
        ),
        ReleaseGate(
            name="settlement-oracle",
            passed=bool(oracle_values) and oracle_fraction >= 0.80,
            detail=(
                f"{sum(oracle_values)}/{len(oracle_values)} measured AEEP selection(s) "
                "were within 10% of the cheapest successful authoritatively costed route"
            ),
        ),
    ]
    valid_workflows = [
        trial
        for trial in report.workflow_trials
        if trial.task_valid
        and trial.dependency_binding_verified
        and trial.prepared_step_count == trial.step_count
        and trial.settled_step_count > 0
        and trial.cash_evidence_level.is_payment_evidence
    ]
    gates.append(
        ReleaseGate(
            name="prepared-hybrid-workflow",
            passed=bool(report.workflow_trials)
            and len(valid_workflows) == len(report.workflow_trials),
            detail=(
                f"{len(valid_workflows)}/{len(report.workflow_trials)} hybrid workflow "
                "trial(s) bound real dependency inputs and carried settlement evidence"
            ),
        )
    )
    return ReleaseProofReport(passed=all(gate.passed for gate in gates), gates=gates)


def finalize_economic_proof(
    report: EconomicProofCampaignReport,
) -> EconomicProofCampaignReport:
    """Derive oracles and gates without changing measured trial evidence."""

    oracles = economic_settlement_oracles(report.trials)
    with_oracles = report.model_copy(update={"oracles": oracles})
    proof = evaluate_economic_proof(with_oracles)
    return with_oracles.model_copy(update={"gates": tuple(proof.gates)})


def format_economic_proof_report(report: EconomicProofCampaignReport) -> str:
    """Render a compact report without turning unknown cash into zero."""

    conditions = ", ".join(sorted({trial.condition.value for trial in report.trials}))
    splits = ", ".join(sorted({trial.split.value for trial in report.trials}))
    route_types = ", ".join(sorted({trial.route_type.value for trial in report.trials}))
    lines = [
        f"# AEEP 0.4 economic evidence proof: {report.campaign_id}",
        "",
        f"Domain: {report.domain}",
        f"Repetitions: {report.repetitions}",
        f"Conditions: {conditions}",
        f"Splits: {splits}",
        f"Route types: {route_types}",
        f"Hybrid qualification/training observations: {report.hybrid_training_observations}",
        "",
        "The JSON artifact is authoritative for per-trial token, resource, failure, "
        "and timing dimensions. `unknown` is never rendered as zero.",
        "",
        "## Route summary",
        "",
        "| Route | Type | Trials | Valid | Median total ms | Median actual cash | "
        "Settlement evidence | Quote failures | Settlement failures | Indeterminate |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    grouped: dict[str, list[EconomicBenchmarkTrial]] = {}
    for trial in report.trials:
        grouped.setdefault(trial.route_id, []).append(trial)
    for route_id, trials in sorted(grouped.items()):
        actual_cash = [
            amount
            for trial in trials
            if (amount := _authoritative_actual_cash(trial)) is not None
        ]
        settled = [
            trial
            for trial in trials
            if trial.settlement_id is not None
            and trial.cash_evidence_level.is_payment_evidence
        ]
        quote_failures = sum(len(trial.quote_failure_codes) for trial in trials)
        settlement_failures = sum(
            trial.settlement_failure_code is not None for trial in trials
        )
        lines.append(
            "| "
            + " | ".join(
                (
                    route_id,
                    trials[0].route_type.value,
                    str(len(trials)),
                    str(sum(trial.task_valid for trial in trials)),
                    _median_decimal_text(trial.total_wall_time_ms for trial in trials),
                    _median_currency_text(actual_cash),
                    f"{len(settled)}/{len(trials)}",
                    str(quote_failures),
                    str(settlement_failures),
                    str(sum(trial.indeterminate for trial in trials)),
                )
            )
            + " |"
        )
    lines.extend(
        (
            "",
            "## Measured trials",
            "",
            "| Route | Split / condition / repetition | Valid | Expected | Maximum | "
            "Reserved | Captured | Released | Evidence | "
            "Prep / quote / execute / settle / total ms |",
            "|---|---|---:|---:|---:|---:|---:|---:|---|---:|",
        )
    )
    for trial in sorted(report.trials, key=lambda item: item.trial_id):
        timing = " / ".join(
            format(value, "f")
            for value in (
                trial.preparation_latency_ms,
                trial.quote_latency_ms,
                trial.execution_latency_ms,
                trial.settlement_latency_ms,
                trial.total_wall_time_ms,
            )
        )
        lines.append(
            "| "
            + " | ".join(
                (
                    trial.route_id,
                    f"{trial.split.value} / {trial.condition.value} / {trial.repetition}",
                    "yes" if trial.task_valid else "no",
                    _economic_amount_text(trial.expected_cash),
                    _economic_amount_text(trial.maximum_cash),
                    _economic_amount_text(trial.reserved_cash),
                    _economic_amount_text(trial.captured_cash),
                    _economic_amount_text(trial.released_cash),
                    trial.cash_evidence_level.value,
                    timing,
                )
            )
            + " |"
        )
    if report.workflow_trials:
        lines.extend(
            (
                "",
                "## Prepared hybrid workflow proof",
                "",
                "These multi-step DAG measurements are not included in the single-action "
                "route oracle.",
                "",
                "| Workflow | Split / condition / repetition | Steps prepared | Quotes | "
                "Settlements | Dependency bytes | Valid | Expected | Maximum | Reserved | "
                "Captured | Released | Evidence | Prep / quote / execute / settle / total ms |",
                "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|",
            )
        )
        for workflow_trial in sorted(
            report.workflow_trials, key=lambda item: item.workflow_id
        ):
            timing = " / ".join(
                format(value, "f")
                for value in (
                    workflow_trial.preparation_latency_ms,
                    workflow_trial.quote_latency_ms,
                    workflow_trial.execution_latency_ms,
                    workflow_trial.settlement_latency_ms,
                    workflow_trial.total_wall_time_ms,
                )
            )
            lines.append(
                "| "
                + " | ".join(
                    (
                        workflow_trial.workflow_id,
                        f"{workflow_trial.split.value} / {workflow_trial.condition.value} / "
                        f"{workflow_trial.repetition}",
                        f"{workflow_trial.prepared_step_count}/{workflow_trial.step_count}",
                        str(workflow_trial.quoted_step_count),
                        str(workflow_trial.settled_step_count),
                        str(workflow_trial.dependency_input_bytes),
                        "yes" if workflow_trial.task_valid else "no",
                        _economic_amount_text(workflow_trial.expected_cash),
                        _economic_amount_text(workflow_trial.maximum_cash),
                        _economic_amount_text(workflow_trial.reserved_cash),
                        _economic_amount_text(workflow_trial.captured_cash),
                        _economic_amount_text(workflow_trial.released_cash),
                        workflow_trial.cash_evidence_level.value,
                        timing,
                    )
                )
                + " |"
            )
    lines.extend(("", "## Authoritatively costed oracle", ""))
    for oracle in report.oracles:
        distance = (
            f"{oracle.distance_from_oracle_percent:f}%"
            if oracle.distance_from_oracle_percent is not None
            else "not within 10% (the oracle actual cash is zero)"
            if oracle.selected_within_10_percent is False
            and oracle.oracle_captured_cash is not None
            and oracle.oracle_captured_cash.amount == 0
            else "unavailable"
        )
        lines.append(
            f"- {oracle.case_id} {oracle.condition} repetition {oracle.repetition}: "
            f"AEEP {oracle.selected_route_id or 'unavailable'}; cheapest successful "
            f"{oracle.oracle_route_id or 'unavailable'}; distance {distance}."
        )
    lines.extend(("", "## Economic gates", ""))
    for gate in report.gates:
        lines.append(f"- {'PASS' if gate.passed else 'FAIL'} — {gate.name}: {gate.detail}")
    hybrid = [trial for trial in report.trials if trial.selected_by_aeep]
    valid_baselines = [
        trial
        for trial in report.trials
        if not trial.selected_by_aeep and trial.task_valid and not trial.indeterminate
    ]
    lines.extend(("", "## Initial engineering targets", ""))
    if hybrid and valid_baselines:
        hybrid_success = Decimal(sum(trial.task_valid for trial in hybrid)) / Decimal(len(hybrid))
        baseline_groups: dict[str, list[EconomicBenchmarkTrial]] = {}
        for trial in valid_baselines:
            baseline_groups.setdefault(trial.route_id, []).append(trial)
        strongest_success = max(
            Decimal(sum(item.task_valid for item in values)) / Decimal(len(values))
            for values in baseline_groups.values()
        )
        lines.append(
            f"- {'PASS' if hybrid_success >= strongest_success else 'FAIL'} — task-valid "
            f"success: AEEP {hybrid_success * 100:f}% versus strongest measured baseline "
            f"{strongest_success * 100:f}%."
        )
        hybrid_time = median(trial.total_wall_time_ms for trial in hybrid)
        fastest_baseline = min(
            median(item.total_wall_time_ms for item in values)
            for values in baseline_groups.values()
        )
        reduction = (
            (fastest_baseline - hybrid_time) / fastest_baseline * Decimal(100)
            if fastest_baseline > 0
            else None
        )
        if reduction is not None:
            reduction = reduction.quantize(Decimal("0.000001"))
        lines.append(
            "- "
            + (
                f"{'PASS' if reduction is not None and reduction >= 15 else 'FAIL'} — "
                f"deterministic-domain total-time target: AEEP median {hybrid_time:f} ms, "
                f"fastest measured baseline {fastest_baseline:f} ms, "
                f"reduction {reduction:f}%."
                if reduction is not None
                else "NOT EVALUATED — deterministic-domain total-time target has a zero-time "
                "baseline."
            )
        )
    else:
        lines.append("- NOT EVALUATED — task-valid success and time targets lack paired routes.")
    complete_model_trials = [trial for trial in report.trials if trial.model_usage_complete]
    lines.append(
        "- NOT EVALUATED — two-domain 20% model-token target: this local campaign covers "
        f"one domain and {len(complete_model_trials)} trial(s) with complete model-usage "
        "measurement; synthetic subscription usage is excluded from claims."
    )
    return "\n".join(lines) + "\n"


def _economic_amount_text(amount: CurrencyAmount | None) -> str:
    return "unknown" if amount is None else f"{amount.currency} {amount.amount:f}"


def _median_decimal_text(values: Iterable[Decimal]) -> str:
    measured = list(values)
    return "unknown" if not measured else f"{median(measured):f}"


def _median_currency_text(values: Iterable[CurrencyAmount]) -> str:
    measured = list(values)
    if not measured:
        return "unknown"
    currencies = {item.currency for item in measured}
    if len(currencies) != 1:
        raise ConfigurationError("economic proof summary cannot combine currencies")
    amount = median(item.amount for item in measured)
    return f"{measured[0].currency} {amount:f}"


def _benchmark_route_candidates(
    router: Router, route: BenchmarkRoute
) -> list[tuple[ExecutorSpec, CandidateScore]]:
    if route.executor_id is not None:
        spec = router.registry.get(route.executor_id)
        action = ActionRequest(capability=spec.capability)
        action.constraints.allowed_executor_ids = [spec.id]
        decision = router.route(action)
        candidate = next(item for item in decision.candidates if item.executor_id == spec.id)
        return [(spec, candidate)]
    assert route.workflow is not None
    candidates: list[tuple[ExecutorSpec, CandidateScore]] = []
    for step in route.workflow.steps:
        action = step.action.model_copy(deep=True)
        action.constraints = merge_constraints(route.workflow.constraints, action.constraints)
        for binding in step.bindings:
            if binding.source_step_id is None:
                pointer_replace(
                    action.input,
                    binding.target_path,
                    pointer_get(route.workflow.input, binding.source_path),
                )
        decision = router.route(action)
        if decision.selected_executor_id is None:
            raise ConfigurationError(decision.explanation)
        spec = router.registry.get(decision.selected_executor_id)
        candidate = next(
            item
            for item in decision.candidates
            if item.executor_id == decision.selected_executor_id
        )
        candidates.append((spec, candidate))
    return candidates


def _benchmark_route_specs(router: Router, route: BenchmarkRoute) -> list[ExecutorSpec]:
    return [spec for spec, _candidate in _benchmark_route_candidates(router, route)]


def _workflow_plan_score(router: Router, case: BenchmarkCase, route: BenchmarkRoute) -> float:
    if route.executor_id is not None:
        action = case.action.model_copy(deep=True)
        action.constraints.allowed_executor_ids = [route.executor_id]
        decision = router.route(action)
        candidate = next(
            item for item in decision.candidates if item.executor_id == route.executor_id
        )
        return candidate.score.total if candidate.feasible and candidate.score else math.inf

    planned = _benchmark_route_candidates(router, route)
    resources = ResourceVector()
    cash_amounts: list[Decimal] = []
    cash_bounds: list[Decimal] = []
    usage_by_pool: dict[tuple[str, str], Decimal] = {}
    quotas: dict[tuple[str, str], Any] = {}
    for spec, candidate in planned:
        estimate = candidate.estimate
        resources = resources.plus(estimate.resources)
        if estimate.cash.amount_usd is not None:
            cash_amounts.append(estimate.cash.amount_usd)
        if estimate.cash.upper_bound_usd is not None:
            cash_bounds.append(estimate.cash.upper_bound_usd)
        entries = estimate.subscription_usage
        if not entries and spec.resource_pool and estimate.resources.subscription_units:
            resource = router.resources.get(spec.resource_pool)
            entries = [
                SubscriptionUsage(
                    provider=resource.provider if resource else spec.provider_id or "unknown",
                    resource_pool=spec.resource_pool,
                    unit=resource.unit if resource else "provider_unit",
                    consumed=Decimal(str(estimate.resources.subscription_units)),
                    source=MeasurementEvidence(
                        status=EvidenceStatus.COMPLETE,
                        source=EvidenceSource.STATIC_ESTIMATE,
                        trust=TrustLevel.SELF_ASSERTED,
                    ),
                )
            ]
        for entry in entries:
            if entry.consumed is None:
                continue
            key = (entry.resource_pool, entry.unit)
            usage_by_pool[key] = usage_by_pool.get(key, Decimal(0)) + entry.consumed
            quotas[key] = router._subscription_quota(spec, case.action.context)
    resources.peak_memory_mb = max(
        (candidate.estimate.resources.peak_memory_mb for _spec, candidate in planned),
        default=0.0,
    )
    resources.subscription_units = 0.0
    evidence = MeasurementEvidence(
        status=EvidenceStatus.COMPLETE,
        source=EvidenceSource.STATIC_ESTIMATE,
        trust=TrustLevel.SELF_ASSERTED,
    )
    estimates = [candidate.estimate for _spec, candidate in planned]
    estimate = RouteEstimate(
        resources=resources,
        cash=CashEstimate(
            amount_usd=sum(cash_amounts, Decimal(0)) if len(cash_amounts) == len(planned) else None,
            upper_bound_usd=(
                sum(cash_bounds, Decimal(0)) if len(cash_bounds) == len(planned) else None
            ),
            evidence=evidence
            if len(cash_amounts) == len(cash_bounds) == len(planned)
            else MeasurementEvidence(),
        ),
        subscription_usage=[
            SubscriptionUsage(
                provider="aggregate",
                resource_pool=pool,
                unit=unit,
                consumed=consumed,
                source=evidence,
            )
            for (pool, unit), consumed in sorted(usage_by_pool.items())
        ],
        success_probability=math.prod(item.success_probability for item in estimates),
        quality_score=min(item.quality_score for item in estimates),
        risk_score=max(item.risk_score for item in estimates),
        confidence=min(item.confidence for item in estimates),
        source=EstimateSource.BLENDED,
        sample_size=sum(item.sample_size for item in estimates),
    )
    for key, consumed in usage_by_pool.items():
        quota = quotas.get(key)
        if (
            quota is not None
            and quota.remaining_units is not None
            and consumed > quota.remaining_units
        ):
            return math.inf
    synthetic = case.action.model_copy(deep=True)
    assert route.workflow is not None
    synthetic.constraints = merge_constraints(route.workflow.constraints, synthetic.constraints)
    policy = router._policy_for(synthetic)
    policy.constraints.allowed_executor_ids = None
    policy.constraints.allowed_executor_kinds = None
    policy.constraints.denied_executor_ids = []
    specs = [spec for spec, _candidate in planned]
    pseudo = ExecutorSpec(
        id=f"workflow.{hashlib.sha256(route.route_id.encode()).hexdigest()[:16]}",
        capability=case.action.capability,
        kind=ExecutorKind.PYTHON,
        description="Caller-authored workflow plan",
        side_effect=max(specs, key=lambda item: item.side_effect.rank).side_effect,
        locality=(
            Locality.INTERNET if any(item.requires_network for item in specs) else Locality.LOCAL
        ),
        requires_network=any(item.requires_network for item in specs),
        config={"callable": "benchmark-plan-only"},
    )
    scored = score_candidate(pseudo, estimate, policy, case.action.context)
    if not scored.feasible or scored.score is None:
        return math.inf
    scored.score = add_subscription_vector(
        scored.score,
        estimate,
        policy,
        estimate.subscription_usage,
        quotas,
    )
    return scored.score.total


class BenchmarkRunner:
    """Small hermetic runner; production receipt/history stores are never used."""

    def __init__(self, router_factory: Callable[[], Router], database: str | Path) -> None:
        self.router_factory = router_factory
        self.database = str(database)
        target = Path(self.database)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database)
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS trials (
                trial_id TEXT PRIMARY KEY,
                suite_id TEXT NOT NULL,
                state TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS suites (
                suite_id TEXT PRIMARY KEY,
                content_sha256 TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                snapshot_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL
            )
            """
        )

    def _save_trial(self, trial: BenchmarkTrial) -> None:
        self.connection.execute(
            """
            INSERT INTO trials (trial_id, suite_id, state, payload_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(trial_id) DO UPDATE SET state=excluded.state, payload_json=excluded.payload_json
            """,
            (trial.trial_id, trial.suite_id, trial.state, trial.model_dump_json()),
        )
        self.connection.commit()

    def _freeze_suite(self, suite: BenchmarkSuite) -> str:
        canonical = json.dumps(
            suite.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode()
        digest = hashlib.sha256(canonical).hexdigest()
        row = self.connection.execute(
            "SELECT content_sha256 FROM suites WHERE suite_id = ?", (suite.suite_id,)
        ).fetchone()
        if row is not None and row[0] != digest:
            raise ConfigurationError("benchmark suite id is already bound to different content")
        self.connection.execute(
            "INSERT OR IGNORE INTO suites (suite_id, content_sha256) VALUES (?, ?)",
            (suite.suite_id, digest),
        )
        self.connection.commit()
        return digest

    def _freeze_snapshots(self, suite: BenchmarkSuite) -> None:
        for snapshot in suite.pricing_snapshots:
            assert snapshot.snapshot_id is not None
            payload = snapshot.model_dump_json()
            row = self.connection.execute(
                "SELECT payload_json FROM snapshots WHERE snapshot_id = ?",
                (snapshot.snapshot_id,),
            ).fetchone()
            if row is not None and row[0] != payload:
                raise ConfigurationError("benchmark pricing snapshot digest mismatch")
            self.connection.execute(
                "INSERT OR IGNORE INTO snapshots (snapshot_id, payload_json) VALUES (?, ?)",
                (snapshot.snapshot_id, payload),
            )
        self.connection.commit()

    async def _execute_trial(
        self,
        router: Router,
        suite: BenchmarkSuite,
        case: BenchmarkCase,
        route: BenchmarkRoute,
        trial: BenchmarkTrial,
    ) -> BenchmarkTrial:
        action = case.action.model_copy(deep=True)
        if action.idempotency_key is not None:
            raise ConfigurationError("benchmark route variants cannot share idempotency keys")
        started = time.perf_counter()
        try:
            if route.executor_id is not None:
                action.constraints.allowed_executor_ids = [route.executor_id]
                decision = router.route(action)
                if decision.selected_executor_id is None:
                    raise ConfigurationError(decision.explanation)
                spec = router.registry.get(route.executor_id)
                specs = [spec]
                trial.route_fingerprint = behavior_fingerprint(spec)
                outcome = await router.execute(decision)
                receipts = outcome.receipts
                output = outcome.output
                ok = outcome.ok
                status = outcome.status
                policy = decision.policy
                quota = next(
                    item.subscription_quota
                    for item in decision.candidates
                    if item.executor_id == route.executor_id
                )
            else:
                assert route.workflow is not None
                workflow = route.workflow.model_copy(
                    update={"workflow_id": f"{route.workflow.workflow_id}.{trial.trial_id}"},
                    deep=True,
                )
                workflow_outcome = await router.execute_workflow(workflow)
                receipts = workflow_outcome.receipts
                output = workflow_outcome.outputs
                ok = workflow_outcome.status == WorkflowStatus.SUCCESS
                status = ExecutionStatus.SUCCESS if ok else ExecutionStatus.FAILED
                specs = [router.registry.get(receipt.executor_id) for receipt in receipts]
                if not specs:
                    raise ConfigurationError("workflow benchmark produced no route receipts")
                fingerprint_payload = {
                    "workflow": route.workflow.workflow_hash,
                    "routes": [(item.id, behavior_fingerprint(item)) for item in specs],
                }
                trial.route_fingerprint = hashlib.sha256(
                    json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                spec = ExecutorSpec(
                    id=f"workflow.{hashlib.sha256(route.route_id.encode()).hexdigest()[:16]}",
                    capability=case.action.capability,
                    kind=ExecutorKind.PYTHON,
                    description="Observed caller-authored workflow",
                    side_effect=max(specs, key=lambda item: item.side_effect.rank).side_effect,
                    locality=(
                        Locality.INTERNET
                        if any(item.requires_network for item in specs)
                        else Locality.LOCAL
                    ),
                    requires_network=any(item.requires_network for item in specs),
                    config={"callable": "benchmark-only"},
                )
                scoped_action = action.model_copy(deep=True)
                scoped_action.constraints = merge_constraints(
                    route.workflow.constraints, scoped_action.constraints
                )
                policy = router._policy_for(scoped_action)
                policy.constraints.allowed_executor_ids = None
                policy.constraints.allowed_executor_kinds = None
                policy.constraints.denied_executor_ids = []
                quota = None
            if any(
                item.side_effect.rank > SideEffect.READ.rank or not item.idempotent
                for item in specs
            ):
                raise ConfigurationError("v1 benchmark routes must be read-only and idempotent")
            valid = ok and all(
                receipt.output_valid is not False and receipt.task_valid is not False
                for receipt in receipts
            )
            if valid and case.validators:
                results = await run_validators(
                    case.validators,
                    ValidationContext(
                        input=action.input,
                        output=extract_path(output, route.validation_output_path),
                    ),
                    router.validator_callbacks,
                )
                valid = all(result.valid is True for result in results)
            trial.ok = ok
            trial.valid = valid
            trial.status = status
            trial.accounting = aggregate_accounting(receipts)
            snapshots = {snapshot.snapshot_id: snapshot for snapshot in suite.pricing_snapshots}
            for usage in trial.accounting.model_usage:
                if route.actual_rate_snapshot_id:
                    cash = price_model_usage(
                        usage,
                        snapshots[route.actual_rate_snapshot_id],
                        actual_billable=True,
                        charge_id=f"{trial.trial_id}:model",
                    )
                    assert not isinstance(cash, CounterfactualCashCost)
                    trial.accounting.cash = CashAccounting(
                        status=(
                            cash.evidence.status
                            if not trial.accounting.cash.components
                            else EvidenceStatus.COMPLETE
                            if trial.accounting.cash.status == EvidenceStatus.COMPLETE
                            and cash.evidence.status == EvidenceStatus.COMPLETE
                            else EvidenceStatus.PARTIAL
                        ),
                        components=[*trial.accounting.cash.components, cash],
                    )
                if route.subscription_rate_snapshot_id:
                    assert route.subscription_resource_pool is not None
                    trial.accounting.subscription_usage.append(
                        subscription_usage_from_tokens(
                            usage,
                            snapshots[route.subscription_rate_snapshot_id],
                            resource_pool=route.subscription_resource_pool,
                            unit=route.subscription_unit,
                        )
                    )
                if route.counterfactual_rate_snapshot_id:
                    valued = price_model_usage(
                        usage,
                        snapshots[route.counterfactual_rate_snapshot_id],
                    )
                    assert isinstance(valued, CounterfactualCashCost)
                    trial.counterfactual_costs.append(valued)
            trial.model_usage_complete = (
                bool(trial.accounting.model_usage)
                and all(
                    usage.evidence.status == EvidenceStatus.COMPLETE
                    for usage in trial.accounting.model_usage
                )
            ) or (
                route.provider is None
                and route.model is None
                and route.access_channel == ModelAccessChannel.UNKNOWN
            )
            trial.receipt_ids = [receipt.receipt_id for receipt in receipts]
            trial.operation_count = len(receipts)
            trial.retry_fallback_count = sum(receipt.attempt > 1 for receipt in receipts)
            cache_values = [
                receipt.metadata.get("schema_cache_hit")
                for receipt in receipts
                if "schema_cache_hit" in receipt.metadata
            ]
            trial.cache_hit_verified = (
                any(value is True for value in cache_values) if cache_values else None
            )
            elapsed = (time.perf_counter() - started) * 1000.0
            trial.actual_resources = _aggregate_resources(receipts, elapsed)
            actual_cash = trial.accounting.cash.actual_cash_cost()
            estimate = RouteEstimate(
                resources=trial.actual_resources,
                cash=(
                    CashEstimate(
                        amount_usd=actual_cash,
                        upper_bound_usd=actual_cash,
                        evidence=MeasurementEvidence(
                            status=EvidenceStatus.COMPLETE,
                            source=EvidenceSource.LOCAL_METER,
                            trust=TrustLevel.OBSERVED,
                        ),
                    )
                    if actual_cash is not None
                    else CashEstimate()
                ),
                subscription_usage=trial.accounting.subscription_usage,
                success_probability=1.0 if valid else 0.001,
                quality_score=1.0 if valid else 0.0,
                risk_score=max(item.estimate.risk_score for item in specs),
                confidence=1.0,
                source=EstimateSource.OBSERVED,
                sample_size=1,
            )
            observed = score_candidate(
                spec,
                estimate,
                policy,
                action.context,
                quota,
            )
            if route.workflow is not None and observed.score is not None:
                quotas: dict[tuple[str, str], Any] = {}
                expected_pools = {item.resource_pool for item in specs if item.resource_pool}
                observed_pools = {
                    item.resource_pool for item in trial.accounting.subscription_usage
                }
                for item in trial.accounting.subscription_usage:
                    matching = next(
                        (spec for spec in specs if spec.resource_pool == item.resource_pool), None
                    )
                    quotas[(item.resource_pool, item.unit)] = (
                        router._subscription_quota(matching, action.context)
                        if matching is not None
                        else None
                    )
                observed.score = add_subscription_vector(
                    observed.score,
                    estimate,
                    policy,
                    trial.accounting.subscription_usage,
                    quotas,
                )
                if expected_pools - observed_pools:
                    observed.score = None
            trial.policy_score = observed.score.total if observed.score is not None else None
            trial.state = "complete"
        except Exception as exc:
            trial.state = "failed"
            trial.error_type = type(exc).__name__
            if isinstance(exc, ConfigurationError):
                trial.error_message = str(exc)[:1000]
        trial.wall_time_ms = (time.perf_counter() - started) * 1000.0
        trial.actual_resources.latency_ms = trial.wall_time_ms
        trial.ended_at = utc_now()
        self._save_trial(trial)
        return trial

    async def _preflight(self, suite: BenchmarkSuite) -> dict[str, str | None]:
        router = self.router_factory()
        try:
            planned_upper = Decimal(0)
            risky = False
            snapshots = {snapshot.snapshot_id: snapshot for snapshot in suite.pricing_snapshots}
            multiplier = suite.repetitions * len(suite.cases) * len(suite.conditions)
            if BenchmarkCondition.ROUTER_WARM in suite.conditions:
                multiplier += 1
            for route in suite.routes:
                snapshot_ids = [
                    item
                    for item in (
                        route.actual_rate_snapshot_id,
                        route.counterfactual_rate_snapshot_id,
                        route.subscription_rate_snapshot_id,
                    )
                    if item is not None
                ]
                if any(item not in snapshots for item in snapshot_ids):
                    raise ConfigurationError(
                        f"benchmark route {route.route_id!r} references an unknown rate snapshot"
                    )
                if any(
                    (route.provider is not None and snapshots[item].provider != route.provider)
                    or (route.model is not None and snapshots[item].model != route.model)
                    for item in snapshot_ids
                ):
                    raise ConfigurationError(
                        f"benchmark route {route.route_id!r} rate snapshot does not match provider/model"
                    )
                for spec in _benchmark_route_specs(router, route):
                    if not spec.enabled:
                        raise ConfigurationError(f"benchmark route {spec.id!r} is not active")
                    candidate = router.store.get_route_candidate(spec.id)
                    if candidate is not None:
                        report = router.store.get_qualification_report(
                            candidate.qualification_report_id or ""
                        )
                        if (
                            candidate.status != RouteLifecycle.ACTIVE
                            or report is None
                            or not report.passed
                            or report.behavior_fingerprint != candidate.behavior_fingerprint
                            or behavior_fingerprint(spec) != candidate.behavior_fingerprint
                        ):
                            raise ConfigurationError(
                                f"benchmark route {spec.id!r} lacks exact activation evidence"
                            )
                    if spec.side_effect.rank > SideEffect.READ.rank or not spec.idempotent:
                        raise ConfigurationError(
                            "v1 benchmark routes must be read-only and idempotent"
                        )
                    upper = spec.estimate.cash.upper_bound_usd
                    priced_api = route.actual_rate_snapshot_id is not None and any(
                        rate.rate_amount > 0
                        for rate in snapshots[route.actual_rate_snapshot_id].rates
                        if rate.rate_type != RateType.SUBSCRIPTION_UNIT
                    )
                    risky |= upper is None or upper > 0 or priced_api
                    if priced_api and (upper is None or upper <= 0):
                        raise ConfigurationError(
                            f"paid API benchmark route {spec.id!r} requires a positive "
                            "cash upper bound"
                        )
                    if upper is None:
                        if suite.max_total_cash_usd is not None:
                            raise ConfigurationError(
                                f"benchmark route {spec.id!r} has no enforceable cash upper bound"
                            )
                    else:
                        planned_upper += upper * multiplier
            if risky and (not suite.acknowledge_cash_risk or suite.max_total_cash_usd is None):
                raise ConfigurationError(
                    "paid or unknown-cash campaigns require acknowledgement and a total cash ceiling"
                )
            if suite.max_total_cash_usd is not None and planned_upper > suite.max_total_cash_usd:
                raise ConfigurationError(
                    "planned benchmark cash upper bound exceeds campaign ceiling"
                )
            decisions = {case.case_id: router.route(case.action) for case in suite.cases}
            if (
                any(
                    spec.resource_pool
                    for route in suite.routes
                    for spec in _benchmark_route_specs(router, route)
                )
                and not suite.allow_zero_subscription_weight
                and any(
                    decision.policy.weights.subscription == 0 for decision in decisions.values()
                )
            ):
                raise ConfigurationError(
                    "proof campaigns with subscription routes require a non-zero subscription weight"
                )
            return {
                case.case_id: min(
                    suite.routes,
                    key=lambda route: (_workflow_plan_score(router, case, route), route.route_id),
                ).route_id
                for case in suite.cases
                if case.split == BenchmarkSplit.HOLDOUT
            }
        finally:
            await router.close()

    async def run(self, suite: BenchmarkSuite) -> BenchmarkCampaignReport:
        self._freeze_snapshots(suite)
        suite_digest = self._freeze_suite(suite)
        frozen = await self._preflight(suite)
        run_id = f"run_{suite_digest}"
        rng = random.Random(suite.seed)
        planned = [
            (case, route, condition, repetition)
            for case in suite.cases
            for condition in suite.conditions
            for repetition in range(suite.repetitions)
            for route in suite.routes
        ]
        rng.shuffle(planned)
        warm: dict[str, Router] = {}
        warmed: set[str] = set()
        trials: list[BenchmarkTrial] = []
        try:
            for case, route, condition, repetition in planned:
                trial_id = f"trial_{suite.suite_id}_{case.case_id}_{route.route_id}_{condition}_{repetition}"
                existing = self.connection.execute(
                    "SELECT payload_json, state FROM trials WHERE trial_id = ?", (trial_id,)
                ).fetchone()
                if existing is not None:
                    if existing[1] == "running":
                        raise ConfigurationError(f"ambiguous running benchmark trial {trial_id}")
                    trials.append(BenchmarkTrial.model_validate_json(existing[0]))
                    continue
                phase = {
                    BenchmarkSplit.QUALIFICATION: BenchmarkPhase.QUALIFICATION,
                    BenchmarkSplit.TRAINING: BenchmarkPhase.MEASUREMENT,
                    BenchmarkSplit.HOLDOUT: BenchmarkPhase.HOLDOUT,
                }[case.split]
                trial = BenchmarkTrial(
                    trial_id=trial_id,
                    run_id=run_id,
                    suite_id=suite.suite_id,
                    case_id=case.case_id,
                    route_id=route.route_id,
                    condition=condition,
                    repetition=repetition,
                    phase=phase,
                    state="running",
                )
                self._save_trial(trial)
                if condition == BenchmarkCondition.PROCESS_COLD:
                    router = self.router_factory()
                else:
                    warm_router = warm.get(route.route_id)
                    if warm_router is None:
                        warm_router = self.router_factory()
                        warm[route.route_id] = warm_router
                    router = warm_router
                    if route.route_id not in warmed:
                        setup = BenchmarkTrial(
                            trial_id=f"setup_{run_id}_{route.route_id}_{time.time_ns()}",
                            run_id=run_id,
                            suite_id=suite.suite_id,
                            case_id=case.case_id,
                            route_id=route.route_id,
                            condition=condition,
                            repetition=0,
                            phase=BenchmarkPhase.SETUP,
                            state="running",
                        )
                        self._save_trial(setup)
                        trials.append(await self._execute_trial(router, suite, case, route, setup))
                        warmed.add(route.route_id)
                trials.append(await self._execute_trial(router, suite, case, route, trial))
                if condition == BenchmarkCondition.PROCESS_COLD:
                    await router.close()
        finally:
            for router in warm.values():
                await router.close()
        setup_rows = self.connection.execute(
            "SELECT payload_json FROM trials WHERE suite_id = ?", (suite.suite_id,)
        ).fetchall()
        by_id = {trial.trial_id: trial for trial in trials}
        for row in setup_rows:
            stored = BenchmarkTrial.model_validate_json(row[0])
            if stored.phase == BenchmarkPhase.SETUP:
                by_id[stored.trial_id] = stored
        trials = list(by_id.values())
        return BenchmarkCampaignReport(
            run_id=run_id,
            suite_id=suite.suite_id,
            domain=suite.domain,
            deterministic_tools_available=suite.deterministic_tools_available,
            pricing_snapshot_ids=[
                snapshot.snapshot_id or "" for snapshot in suite.pricing_snapshots
            ],
            frozen_holdout_decisions=frozen,
            trials=trials,
            summaries=_summaries(trials),
            baseline_deltas=_baseline_deltas(trials, suite),
            oracles=_oracles(trials, suite, frozen),
            subscription_conservation=_subscription_conservation(trials),
        )


def _summaries(trials: list[BenchmarkTrial]) -> list[BenchmarkSummary]:
    groups: dict[tuple[str, BenchmarkCondition], list[BenchmarkTrial]] = {}
    for trial in trials:
        if trial.phase == BenchmarkPhase.SETUP:
            continue
        groups.setdefault((trial.route_id, trial.condition), []).append(trial)
    summaries: list[BenchmarkSummary] = []
    for (route, condition), items in sorted(groups.items()):
        cache_evidence = [
            item.cache_hit_verified for item in items if item.cache_hit_verified is not None
        ]
        measured = (
            [item for item in items if item.cache_hit_verified is True]
            if condition == BenchmarkCondition.ROUTER_WARM and cache_evidence
            else items
        )
        valid = sum(item.valid is True for item in measured)
        low, high = _wilson(valid, len(measured))
        durations = [item.wall_time_ms for item in measured if item.wall_time_ms is not None]
        center = median(durations) if durations else None
        summaries.append(
            BenchmarkSummary(
                route_id=route,
                condition=condition,
                trials=len(measured),
                attempted=len(items),
                completed=sum(item.state == "complete" for item in measured),
                valid=valid,
                success_rate=valid / len(measured) if measured else 0.0,
                success_wilson_low=low,
                success_wilson_high=high,
                median_wall_time_ms=center,
                p95_wall_time_ms=_nearest_rank(durations, 0.95),
                mad_wall_time_ms=(
                    median(abs(value - center) for value in durations)
                    if durations and center is not None
                    else None
                ),
                operation_count=sum(item.operation_count for item in measured),
                retry_fallback_count=sum(item.retry_fallback_count for item in measured),
                intervention_count=sum(item.intervention_count for item in measured),
                warm_cache_evidence_coverage=(
                    f"{sum(value is True for value in cache_evidence)}/{len(items)}"
                    if condition == BenchmarkCondition.ROUTER_WARM and cache_evidence
                    else "not-applicable"
                ),
                cash_evidence_coverage=f"{sum(item.accounting.cash.actual_cash_cost() is not None for item in measured)}/{len(measured)}",
                subscription_evidence_coverage=f"{sum(bool(item.accounting.subscription_usage) and all(usage.consumed is not None for usage in item.accounting.subscription_usage) for item in measured)}/{len(measured)}",
            )
        )
    return summaries


def _aggregate_resources(receipts: Iterable[Any], wall_time_ms: float) -> ResourceVector:
    vectors = [receipt.actual_resources for receipt in receipts]
    if not vectors:
        return ResourceVector(latency_ms=wall_time_ms)
    summed = ResourceVector()
    for vector in vectors:
        summed = summed.plus(vector)
    summed.latency_ms = wall_time_ms
    summed.peak_memory_mb = max(vector.peak_memory_mb for vector in vectors)
    return summed


def _wilson(successes: int, total: int) -> tuple[float, float]:
    if total == 0:
        return 0.0, 0.0
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total))
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def _nearest_rank(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


def _baseline_deltas(trials: list[BenchmarkTrial], suite: BenchmarkSuite) -> list[BenchmarkDelta]:
    baseline = suite.baseline_route_id or suite.routes[0].route_id
    measured = _eligible_measurements(trials)
    keyed = {
        (trial.route_id, trial.case_id, trial.condition, trial.repetition): trial
        for trial in measured
    }
    deltas: list[BenchmarkDelta] = []
    for route in suite.routes:
        if route.route_id == baseline:
            continue
        for condition in suite.conditions:
            paired = [
                trial.wall_time_ms - base.wall_time_ms
                for trial in measured
                if trial.route_id == route.route_id
                and trial.condition == condition
                and trial.wall_time_ms is not None
                and (base := keyed.get((baseline, trial.case_id, condition, trial.repetition)))
                is not None
                and base.wall_time_ms is not None
            ]
            low, high = _bootstrap_interval(paired, suite.seed, f"{route.route_id}:{condition}")
            deltas.append(
                BenchmarkDelta(
                    route_id=route.route_id,
                    baseline_route_id=baseline,
                    condition=condition,
                    paired_trials=len(paired),
                    median_wall_time_delta_ms=median(paired) if paired else None,
                    bootstrap_low_ms=low,
                    bootstrap_high_ms=high,
                )
            )
    return deltas


def _bootstrap_interval(
    values: list[float], seed: int, label: str
) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    label_seed = int.from_bytes(hashlib.sha256(label.encode()).digest()[:8], "big")
    rng = random.Random(seed ^ label_seed)
    samples = [median(rng.choice(values) for _ in values) for _ in range(2000)]
    return _nearest_rank(samples, 0.025), _nearest_rank(samples, 0.975)


def _oracles(
    trials: list[BenchmarkTrial],
    suite: BenchmarkSuite,
    frozen: dict[str, str | None],
) -> list[BenchmarkOracle]:
    measured = [trial for trial in _eligible_measurements(trials) if trial.valid is True]
    groups: dict[tuple[str, BenchmarkCondition, int], list[BenchmarkTrial]] = {}
    for trial in measured:
        groups.setdefault((trial.case_id, trial.condition, trial.repetition), []).append(trial)
    route_by_executor = {
        route.executor_id: route.route_id for route in suite.routes if route.executor_id is not None
    }
    route_ids = {route.route_id for route in suite.routes}
    values: list[BenchmarkOracle] = []
    for (case_id, condition, repetition), items in sorted(groups.items()):
        policy_items = [item for item in items if item.policy_score is not None]
        policy = (
            min(policy_items, key=lambda item: item.policy_score or math.inf)
            if policy_items
            else None
        )
        cash_items = [item for item in items if item.accounting.cash.actual_cash_cost() is not None]
        cash = (
            min(
                cash_items,
                key=lambda item: item.accounting.cash.actual_cash_cost() or Decimal(0),
            )
            if cash_items
            else None
        )
        token = min(items, key=_model_tokens)
        latency = min(items, key=lambda item: item.wall_time_ms or math.inf)
        frozen_route = frozen.get(case_id)
        selected_route = (
            frozen_route if frozen_route in route_ids else route_by_executor.get(frozen_route or "")
        )
        selected = next((item for item in items if item.route_id == selected_route), None)
        within: bool | None = None
        if selected is not None and selected.policy_score is not None and policy is not None:
            oracle_score = policy.policy_score or 0.0
            within = (
                selected.policy_score == 0
                if oracle_score == 0
                else selected.policy_score <= 1.10 * oracle_score
            )
        values.append(
            BenchmarkOracle(
                case_id=case_id,
                condition=condition,
                repetition=repetition,
                selected_route_id=selected_route,
                policy_route_id=policy.route_id if policy else None,
                cash_route_id=cash.route_id if cash else None,
                token_route_id=token.route_id,
                latency_route_id=latency.route_id,
                selected_within_10_percent=within,
            )
        )
    return values


def _model_tokens(trial: BenchmarkTrial) -> int:
    return sum(usage.input_tokens + usage.output_tokens for usage in trial.accounting.model_usage)


def _subscription_conservation(
    trials: list[BenchmarkTrial],
) -> list[SubscriptionConservation]:
    measured = _eligible_measurements(trials)
    groups: dict[tuple[str, BenchmarkCondition, str, str], list[Decimal | None]] = {}
    totals: dict[tuple[str, BenchmarkCondition], int] = {}
    for trial in measured:
        totals[(trial.route_id, trial.condition)] = (
            totals.get((trial.route_id, trial.condition), 0) + 1
        )
        for usage in trial.accounting.subscription_usage:
            groups.setdefault(
                (trial.route_id, trial.condition, usage.resource_pool, usage.unit), []
            ).append(usage.consumed)
    return [
        SubscriptionConservation(
            route_id=route,
            condition=condition,
            resource_pool=pool,
            unit=unit,
            measured_trials=sum(value is not None for value in consumed),
            total_trials=totals[(route, condition)],
            median_consumed=(
                median(value for value in consumed if value is not None)
                if any(value is not None for value in consumed)
                else None
            ),
        )
        for (route, condition, pool, unit), consumed in sorted(groups.items())
    ]


def format_campaign_report(report: BenchmarkCampaignReport) -> str:
    """Render separate ledgers; intentionally no synthetic total-cost column."""

    measured = _eligible_measurements(report.trials)
    lines = ["Correctness and wall time"]
    for summary in report.summaries:
        wall = (
            f"{summary.median_wall_time_ms:.3f} ms"
            if summary.median_wall_time_ms is not None
            else "unavailable"
        )
        lines.append(
            f"  {summary.route_id} [{summary.condition} requested]: "
            f"{summary.valid}/{summary.trials} eligible valid; median {wall}; "
            f"attempted {summary.attempted}; cache evidence "
            f"{summary.warm_cache_evidence_coverage}"
        )
    lines.append("\nRaw model resources")
    for route, condition, items in _trial_groups(measured):
        totals = [_model_tokens(item) for item in items]
        cached = [
            sum(usage.cached_input_tokens for usage in item.accounting.model_usage)
            for item in items
        ]
        cache_writes = [
            sum(usage.cache_write_input_tokens for usage in item.accounting.model_usage)
            for item in items
        ]
        lines.append(
            f"  {route} [{condition}]: median input+output {median(totals):g}; "
            f"cached-input subset {median(cached):g}; "
            f"cache-write subset {median(cache_writes):g}"
        )
    lines.append("\nActual cash")
    for route, condition, items in _trial_groups(measured):
        values = [
            value
            for item in items
            if (value := item.accounting.cash.actual_cash_cost()) is not None
        ]
        display = f"${median(values):f}" if len(values) == len(items) else "unavailable"
        lines.append(f"  {route} [{condition}]: {display}; evidence {len(values)}/{len(items)}")
    lines.append("\nSubscription usage (provider-local; never summed across pools)")
    if report.subscription_conservation:
        for item in report.subscription_conservation:
            subscription_value = (
                f"{item.median_consumed:f}" if item.median_consumed is not None else "unavailable"
            )
            lines.append(
                f"  {item.route_id} [{item.condition}] {item.resource_pool} "
                f"{subscription_value} {item.unit}; evidence "
                f"{item.measured_trials}/{item.total_trials}"
            )
    else:
        lines.append("  none reported")
    lines.append("\nAPI-equivalent counterfactual (not actual cash)")
    for route, condition, items in _trial_groups(measured):
        values = [
            cost.amount
            for item in items
            for cost in item.counterfactual_costs
            if cost.amount is not None
        ]
        snapshots = sorted(
            {cost.rate_snapshot_id for item in items for cost in item.counterfactual_costs}
        )
        display = f"${median(values):f}" if values else "unavailable"
        lines.append(
            f"  {route} [{condition}]: {display}; snapshots {','.join(snapshots) or 'none'}"
        )
    lines.append("\nPrivate policy score")
    for route, condition, items in _trial_groups(measured):
        policy_scores = [item.policy_score for item in items if item.policy_score is not None]
        display = f"{median(policy_scores):.6f}" if policy_scores else "unavailable"
        lines.append(f"  {route} [{condition}]: {display}")
    setup = [trial for trial in report.trials if trial.phase == BenchmarkPhase.SETUP]
    lines.append("\nSetup and qualification")
    lines.append(f"  setup trials: {len(setup)}; resources are excluded from measured summaries")
    return "\n".join(lines)


def revalue_campaign(
    report: BenchmarkCampaignReport, snapshot: RateCardSnapshot
) -> BenchmarkRevaluationReport:
    """Create a separate API-equivalent view without mutating historical trials."""

    source = json.dumps(
        report.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    source_digest = hashlib.sha256(source).hexdigest()
    values: dict[str, list[CounterfactualCashCost]] = {}
    for trial in report.trials:
        priced: list[CounterfactualCashCost] = []
        for usage in trial.accounting.model_usage:
            if usage.provider != snapshot.provider or usage.model != snapshot.model:
                continue
            value = price_model_usage(usage, snapshot)
            assert isinstance(value, CounterfactualCashCost)
            priced.append(value)
        if priced:
            values[trial.trial_id] = priced
    assert snapshot.snapshot_id is not None
    identity = hashlib.sha256(f"{source_digest}:{snapshot.snapshot_id}".encode()).hexdigest()
    return BenchmarkRevaluationReport(
        revaluation_id=f"revalue_{identity}",
        source_run_id=report.run_id,
        source_report_sha256=source_digest,
        pricing_snapshot_id=snapshot.snapshot_id,
        trial_values=values,
    )


def _trial_groups(
    trials: list[BenchmarkTrial],
) -> list[tuple[str, BenchmarkCondition, list[BenchmarkTrial]]]:
    groups: dict[tuple[str, BenchmarkCondition], list[BenchmarkTrial]] = {}
    for trial in trials:
        groups.setdefault((trial.route_id, trial.condition), []).append(trial)
    return [(route, condition, items) for (route, condition), items in sorted(groups.items())]


def _eligible_measurements(trials: list[BenchmarkTrial]) -> list[BenchmarkTrial]:
    """Exclude router-reused cache misses from statistics labeled warm."""

    measured = [trial for trial in trials if trial.phase != BenchmarkPhase.SETUP]
    evidenced = {
        (trial.route_id, trial.condition)
        for trial in measured
        if trial.condition == BenchmarkCondition.ROUTER_WARM
        and trial.cache_hit_verified is not None
    }
    return [
        trial
        for trial in measured
        if (trial.route_id, trial.condition) not in evidenced or trial.cache_hit_verified is True
    ]


def _heldout_policy_oracle_values(report: BenchmarkCampaignReport) -> list[bool]:
    groups: dict[tuple[str, BenchmarkCondition, int], list[BenchmarkTrial]] = {}
    for trial in _eligible_measurements(report.trials):
        if trial.phase == BenchmarkPhase.HOLDOUT:
            groups.setdefault((trial.case_id, trial.condition, trial.repetition), []).append(trial)

    values: list[bool] = []
    for (case_id, _condition, _repetition), trials in groups.items():
        selected_route = report.frozen_holdout_decisions.get(case_id)
        selected = [trial for trial in trials if trial.route_id == selected_route]
        policy = [trial for trial in trials if trial.valid is True and trial.policy_score is not None]
        if len(selected) != 1 or selected[0].valid is not True or not policy:
            values.append(False)
            continue
        oracle_score = min(trial.policy_score for trial in policy if trial.policy_score is not None)
        selected_score = selected[0].policy_score
        values.append(
            selected_score is not None
            and (selected_score == 0 if oracle_score == 0 else selected_score <= 1.10 * oracle_score)
        )
    return values


def evaluate_release_proof(
    reports: list[BenchmarkCampaignReport],
    *,
    baseline_route_ids: list[str],
    hybrid_route_id: str,
) -> ReleaseProofReport:
    """Evaluate the locked numeric gates without manufacturing missing evidence."""

    success_ok = True
    token_domains: set[str] = set()
    latency_results: list[bool] = []
    exact_activation = True
    for report in reports:
        measured = _eligible_measurements(report.trials)
        hybrid = [trial for trial in measured if trial.route_id == hybrid_route_id]
        baselines = {
            route_id: [trial for trial in measured if trial.route_id == route_id]
            for route_id in baseline_route_ids
        }
        baselines = {key: value for key, value in baselines.items() if value}
        if not hybrid or not baselines:
            success_ok = False
            continue
        baseline_id, baseline = max(
            baselines.items(),
            key=lambda item: sum(trial.valid is True for trial in item[1]) / len(item[1]),
        )
        del baseline_id
        hybrid_success = sum(trial.valid is True for trial in hybrid) / len(hybrid)
        baseline_success = sum(trial.valid is True for trial in baseline) / len(baseline)
        success_ok &= hybrid_success >= baseline_success - 0.01
        if all(trial.model_usage_complete for trial in [*baseline, *hybrid]):
            baseline_tokens = median(_model_tokens(trial) for trial in baseline)
            hybrid_tokens = median(_model_tokens(trial) for trial in hybrid)
            if baseline_tokens > 0 and hybrid_tokens <= 0.80 * baseline_tokens:
                token_domains.add(report.domain)
        if report.deterministic_tools_available:
            baseline_times = [
                trial.wall_time_ms for trial in baseline if trial.wall_time_ms is not None
            ]
            hybrid_times = [
                trial.wall_time_ms for trial in hybrid if trial.wall_time_ms is not None
            ]
            latency_results.append(
                bool(baseline_times)
                and bool(hybrid_times)
                and median(hybrid_times) <= 0.85 * median(baseline_times)
            )
        exact_activation &= all(trial.route_fingerprint for trial in measured)
    heldout = [value for report in reports for value in _heldout_policy_oracle_values(report)]
    oracle_ok = bool(heldout) and sum(heldout) / len(heldout) >= 0.80
    gates = [
        ReleaseGate(
            name="task-success",
            passed=success_ok and bool(reports),
            detail="hybrid success is no more than one percentage point below the strongest baseline",
        ),
        ReleaseGate(
            name="model-token-reduction",
            passed=len(token_domains) >= 2,
            detail=f"20% median reduction demonstrated in {len(token_domains)} domain(s)",
        ),
        ReleaseGate(
            name="completion-time-reduction",
            passed=bool(latency_results) and all(latency_results),
            detail="15% median reduction wherever deterministic tools were declared available",
        ),
        ReleaseGate(
            name="policy-oracle",
            passed=oracle_ok,
            detail="at least 80% of held-out selections are within 10% of the frozen policy oracle",
        ),
        ReleaseGate(
            name="activation-evidence",
            passed=exact_activation and bool(reports),
            detail="every measured trial retains its exact route fingerprint",
        ),
        ReleaseGate(
            name="economic-ledger-separation",
            passed=bool(reports),
            detail="actual cash, subscription usage, counterfactuals, and policy values remain separate",
        ),
    ]
    return ReleaseProofReport(passed=all(gate.passed for gate in gates), gates=gates)
