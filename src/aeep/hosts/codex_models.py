"""Sanitized observations produced by the Codex App Server adapter."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from ..models import StrictModel


class CodexAccountObservation(StrictModel):
    authenticated: bool
    requires_openai_auth: bool
    account_type: str | None = Field(default=None, max_length=50)
    plan_type: str | None = Field(default=None, max_length=100)
    principal_digest: str | None = Field(
        default=None, pattern=r"^sha256:[a-f0-9]{64}$"
    )


class CodexUsageTelemetry(StrictModel):
    """Account activity is telemetry, never exact remaining allowance."""

    lifetime_tokens: int | None = Field(default=None, ge=0)
    peak_daily_tokens: int | None = Field(default=None, ge=0)
    daily_bucket_count: int = Field(default=0, ge=0)


class CodexTurnResult(StrictModel):
    thread_id: str = Field(min_length=1, max_length=200)
    turn_id: str = Field(min_length=1, max_length=200)
    status: str = Field(min_length=1, max_length=50)
    output: Any = None
    actual_model: str | None = Field(default=None, max_length=200)
    token_usage: dict[str, int] | None = None
    tool_count: int = Field(default=0, ge=0)
    approval_digests: tuple[str, ...] = ()
    error: str | None = Field(default=None, max_length=2000)


def sanitize_account(payload: dict[str, Any], *, principal_digest: str | None) -> CodexAccountObservation:
    account = payload.get("account")
    account_data = account if isinstance(account, dict) else {}
    requires_auth = bool(payload.get("requiresOpenaiAuth", True))
    return CodexAccountObservation(
        authenticated=bool(account_data) or not requires_auth,
        requires_openai_auth=requires_auth,
        account_type=_bounded_text(account_data.get("type"), 50),
        plan_type=_bounded_text(account_data.get("planType"), 100),
        principal_digest=principal_digest,
    )


def usage_telemetry(payload: dict[str, Any]) -> CodexUsageTelemetry:
    summary = payload.get("summary")
    summary_data = summary if isinstance(summary, dict) else {}
    buckets = payload.get("dailyUsageBuckets")
    return CodexUsageTelemetry(
        lifetime_tokens=_nonnegative_int(summary_data.get("lifetimeTokens")),
        peak_daily_tokens=_nonnegative_int(summary_data.get("peakDailyTokens")),
        daily_bucket_count=len(buckets) if isinstance(buckets, list) else 0,
    )


def _bounded_text(value: Any, maximum: int) -> str | None:
    return value[:maximum] if isinstance(value, str) and value else None


def _nonnegative_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
