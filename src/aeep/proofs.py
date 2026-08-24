"""Typed AEEP v0.5 DSH and job-sandbox proof reports."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from .models import EconomicStrictModel, ExecutionStatus, UtcDateTime


class ProofGate(EconomicStrictModel):
    name: str = Field(min_length=1, max_length=200)
    passed: bool
    detail: str = Field(max_length=2000)


class DSHCampaignArm(StrEnum):
    DSH_SUGGESTED = "DSH_SUGGESTED"
    AEEP_STATIC = "AEEP_STATIC"
    AEEP_SHARED = "AEEP_SHARED"
    AEEP_ADAPTIVE = "AEEP_ADAPTIVE"


class DSHProofTrial(EconomicStrictModel):
    schema_version: Literal["0.5"] = "0.5"
    trial_id: str
    arm: DSHCampaignArm
    capability: str
    workload_id: str = "default"
    selected_route_id: str | None
    terminal_route_id: str | None = None
    oracle_route_id: str
    feasible: bool
    task_valid: bool | None
    receipt_id: str | None = None
    receipt_ids: tuple[str, ...] = ()
    fallback_count: int = Field(default=0, ge=0)
    shared_trials_reused: int = Field(default=0, ge=0)
    smoke_executions: int = Field(default=0, ge=0, le=2)
    warm_probability: Decimal | None = Field(default=None, ge=0, le=1)
    actual_cash_usd: Decimal | None = Field(default=None, ge=0)
    actual_input_tokens: int | None = Field(default=None, ge=0)
    actual_cached_input_tokens: int | None = Field(default=None, ge=0)
    actual_output_tokens: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def receipt_consistency(self) -> DSHProofTrial:
        if (
            self.receipt_id is not None
            and self.receipt_ids
            and self.receipt_id != self.receipt_ids[-1]
        ):
            raise ValueError("receipt_id must identify the terminal receipt")
        if self.fallback_count != max(0, len(self.receipt_ids) - 1):
            raise ValueError("fallback_count must match receipt_ids")
        return self


class DSHProofReport(EconomicStrictModel):
    schema_version: Literal["0.5"] = "0.5"
    campaign_id: str
    generated_at: UtcDateTime
    synthetic: bool = True
    trials: tuple[DSHProofTrial, ...]
    gates: tuple[ProofGate, ...]

    @model_validator(mode="after")
    def all_hard_gates(self) -> DSHProofReport:
        if not self.gates:
            raise ValueError("DSH proof requires hard gates")
        return self


class DSHLiveTurn(EconomicStrictModel):
    turn: int = Field(ge=1, le=6)
    session: Literal["primary", "fresh"]
    expected_tool: str = Field(min_length=1, max_length=100)
    observed_tool: str = Field(min_length=1, max_length=100)
    tool_calls: int = Field(ge=0)
    tool_succeeded: int = Field(ge=0)
    tool_failed: int = Field(ge=0)
    tool_unresolved: int = Field(ge=0)
    expected_aeep_receipts: int = Field(ge=0, le=1)
    aeep_receipt_ids: tuple[str, ...] = ()
    verification_receipt_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    assertion_code: Literal[
        "capabilities_discovered",
        "text_stats_correct",
        "read_route_selected",
        "read_output_digest_matched",
        "repeat_read_output_digest_matched",
        "inactive_route_blocked",
    ]
    assertion_passed: bool
    result_digest: str | None = Field(
        default=None,
        pattern=r"^sha256:[a-f0-9]{64}$",
    )

    @model_validator(mode="after")
    def consistent_counts(self) -> DSHLiveTurn:
        if self.tool_calls != self.tool_succeeded + self.tool_failed + self.tool_unresolved:
            raise ValueError("tool status counts must sum to tool_calls")
        if len(self.aeep_receipt_ids) != self.expected_aeep_receipts:
            raise ValueError("AEEP receipt count does not match the turn plan")
        return self


class DSHLiveUsage(EconomicStrictModel):
    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=200)
    model_calls: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_read_tokens: int = Field(ge=0)
    cache_write_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)

    @model_validator(mode="after")
    def consistent_total(self) -> DSHLiveUsage:
        total = (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )
        if self.total_tokens != total:
            raise ValueError("DSH token buckets must sum to total_tokens")
        return self


class DSHLiveProofReport(EconomicStrictModel):
    schema_version: Literal["0.5"] = "0.5"
    campaign_id: str = Field(min_length=1, max_length=200)
    generated_at: UtcDateTime
    synthetic: Literal[True] = True
    harness_version: str = Field(min_length=1, max_length=100)
    fixture_digest_before: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    fixture_digest_after: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    qualification_executions: int = Field(ge=0, le=2)
    active_community_routes_during: int = Field(ge=0)
    active_community_routes_after: int = Field(ge=0)
    persisted_sensitive_matches: int = Field(ge=0)
    dsh_usage_imported_into_aeep: Literal[False] = False
    turns: tuple[DSHLiveTurn, ...]
    usage: DSHLiveUsage
    gates: tuple[ProofGate, ...]

    @model_validator(mode="after")
    def six_distinct_turns(self) -> DSHLiveProofReport:
        if [item.turn for item in self.turns] != list(range(1, 7)):
            raise ValueError("live DSH proof requires ordered turns 1 through 6")
        hashes = [item.verification_receipt_hash for item in self.turns]
        if len(set(hashes)) != 6:
            raise ValueError("live DSH proof requires one distinct verification receipt per turn")
        if not self.gates:
            raise ValueError("live DSH proof requires hard gates")
        return self


class DSHLiveComparisonArm(StrEnum):
    DIRECT_MODEL = "DIRECT_MODEL"
    AEEP_ROUTED = "AEEP_ROUTED"


class DSHLiveComparisonTrial(EconomicStrictModel):
    schema_version: Literal["0.5"] = "0.5"
    trial_id: str = Field(min_length=1, max_length=200)
    task_id: str = Field(min_length=1, max_length=200)
    arm: DSHLiveComparisonArm
    correct: bool
    model_calls: int = Field(ge=1)
    tool_calls: int = Field(ge=0)
    receipt_id: str | None = None
    usage: DSHLiveUsage

    @model_validator(mode="after")
    def routed_trial_has_one_receipt(self) -> DSHLiveComparisonTrial:
        if self.arm is DSHLiveComparisonArm.AEEP_ROUTED:
            if self.tool_calls != 1 or self.receipt_id is None:
                raise ValueError("AEEP-routed comparison trials require one tool and receipt")
        elif self.tool_calls or self.receipt_id is not None:
            raise ValueError("direct-model comparison trials cannot have a tool or receipt")
        return self


class DSHLiveComparisonReport(EconomicStrictModel):
    schema_version: Literal["0.5"] = "0.5"
    campaign_id: str = Field(min_length=1, max_length=200)
    generated_at: UtcDateTime
    synthetic: Literal[True] = True
    harness_version: str = Field(min_length=1, max_length=100)
    mcp_client_version: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=200)
    reasoning_effort: Literal["low"]
    read_only: Literal[True] = True
    pilot_sessions_excluded: int = Field(default=0, ge=0)
    imported_plugin_candidates: int = Field(ge=0)
    active_plugin_candidates_after: int = Field(ge=0)
    plugin_capability_discovered: bool
    plugin_route_selected: bool
    plugin_route_estimate_available: bool
    plugin_token_estimate_status: Literal["measured", "estimated", "unavailable"]
    trials: tuple[DSHLiveComparisonTrial, ...]
    direct_total_tokens: int = Field(ge=0)
    aeep_total_tokens: int = Field(ge=0)
    tokens_saved_by_aeep: int
    savings_percent: Decimal
    direct_correct: int = Field(ge=0)
    aeep_correct: int = Field(ge=0)
    gates: tuple[ProofGate, ...]

    @model_validator(mode="after")
    def consistent_comparison(self) -> DSHLiveComparisonReport:
        direct = [item for item in self.trials if item.arm is DSHLiveComparisonArm.DIRECT_MODEL]
        routed = [item for item in self.trials if item.arm is DSHLiveComparisonArm.AEEP_ROUTED]
        if len(direct) != 3 or len(routed) != 3:
            raise ValueError("live comparison requires three trials per arm")
        direct_tokens = sum(item.usage.total_tokens for item in direct)
        routed_tokens = sum(item.usage.total_tokens for item in routed)
        if (self.direct_total_tokens, self.aeep_total_tokens) != (
            direct_tokens,
            routed_tokens,
        ):
            raise ValueError("comparison totals must equal trial usage")
        if self.tokens_saved_by_aeep != direct_tokens - routed_tokens:
            raise ValueError("tokens_saved_by_aeep must be direct minus AEEP usage")
        if self.direct_correct != sum(item.correct for item in direct):
            raise ValueError("direct_correct does not match trials")
        if self.aeep_correct != sum(item.correct for item in routed):
            raise ValueError("aeep_correct does not match trials")
        if not self.gates:
            raise ValueError("live comparison requires hard gates")
        return self


class ApplicationAttemptState(StrEnum):
    DISCOVERED = "DISCOVERED"
    SHORTLISTED = "SHORTLISTED"
    RESUME_PREPARED = "RESUME_PREPARED"
    FORM_INSPECTED = "FORM_INSPECTED"
    DRAFT_FILLED = "DRAFT_FILLED"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    SUBMITTING = "SUBMITTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    INDETERMINATE = "INDETERMINATE"
    RECONCILED = "RECONCILED"


class ResumeRewriteRequest(EconomicStrictModel):
    fact_id: str
    focus: str = Field(max_length=500)
    max_words: int = Field(ge=1, le=100)


class ResumePlan(EconomicStrictModel):
    schema_version: Literal["0.5"] = "0.5"
    job_id: str
    source_commit: str
    emphasize_fact_ids: tuple[str, ...] = ()
    omit_fact_ids: tuple[str, ...] = ()
    rewrite_requests: tuple[ResumeRewriteRequest, ...] = ()

    @model_validator(mode="after")
    def valid_facts(self) -> ResumePlan:
        referenced = [*self.emphasize_fact_ids, *self.omit_fact_ids]
        referenced.extend(item.fact_id for item in self.rewrite_requests)
        if len(referenced) != len(set(referenced)):
            raise ValueError("resume plan cannot reference one fact more than once")
        return self


class JobApplicationAttempt(EconomicStrictModel):
    schema_version: Literal["0.5"] = "0.5"
    attempt_id: str
    job_id_hmac: str = Field(pattern=r"^[a-f0-9]{64}$")
    resume_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    idempotency_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    state: ApplicationAttemptState
    approval_id: str | None = None
    receipt_ids: tuple[str, ...] = ()
    reconciled_at: datetime | None = None


class JobProofReport(EconomicStrictModel):
    schema_version: Literal["0.5"] = "0.5"
    campaign_id: str
    generated_at: UtcDateTime
    synthetic: bool = True
    postings: int = Field(ge=1)
    unique_canonical_jobs: int = Field(ge=1)
    duplicate_postings: int = Field(ge=0)
    form_families: int = Field(ge=1)
    form_family_ids: tuple[str, ...]
    attempts: tuple[JobApplicationAttempt, ...]
    supported_fact_ids: tuple[str, ...]
    gates: tuple[ProofGate, ...]
    execution_statuses: tuple[ExecutionStatus, ...] = ()

    @model_validator(mode="after")
    def consistent_fixture_counts(self) -> JobProofReport:
        if self.unique_canonical_jobs + self.duplicate_postings != self.postings:
            raise ValueError("canonical and duplicate posting counts must sum to postings")
        if len(set(self.form_family_ids)) != self.form_families:
            raise ValueError("form_family_ids must match form_families")
        return self
