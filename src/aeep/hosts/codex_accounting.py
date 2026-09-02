"""Map Codex provider telemetry without inventing cash or capacity units."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from ..capacity import CapacityEvidence, CapacityObservation, CapacityWindow
from ..models import (
    EvidenceSource,
    EvidenceStatus,
    MeasurementEvidence,
    ModelAccessChannel,
    ModelTokenUsage,
    ResourceAccounting,
    ResourceVector,
    SubscriptionCharge,
    SubscriptionUsage,
    TrustLevel,
)


def rate_limit_observation(payload: dict[str, Any], *, resource_id: str) -> CapacityObservation:
    snapshots = payload.get("rateLimitsByLimitId")
    if not isinstance(snapshots, dict) or not snapshots:
        snapshots = {"default": payload.get("rateLimits")}
    windows: list[CapacityWindow] = []
    for fallback_id, raw_snapshot in sorted(snapshots.items()):
        if not isinstance(raw_snapshot, dict):
            continue
        limit_id = raw_snapshot.get("limitId")
        bucket = limit_id if isinstance(limit_id, str) and limit_id else str(fallback_id)
        reached = bool(raw_snapshot.get("rateLimitReachedType")) or bool(
            raw_snapshot.get("spendControlReached")
        )
        for name in ("primary", "secondary"):
            raw_window = raw_snapshot.get(name)
            if not isinstance(raw_window, dict):
                continue
            used = _percentage(raw_window.get("usedPercent"))
            reset = _unix_time(raw_window.get("resetsAt"))
            duration = _positive_int(raw_window.get("windowDurationMins"))
            evidence_payload = {
                "bucket": bucket,
                "window": name,
                "used_percent": str(used) if used is not None else None,
                "reset_at": reset.isoformat() if reset else None,
                "duration_seconds": duration * 60 if duration else None,
                "reached": reached,
            }
            digest = hashlib.sha256(
                json.dumps(evidence_payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            windows.append(
                CapacityWindow(
                    window_id=f"{bucket}:{name}",
                    used_percent=used,
                    reset_at=reset,
                    duration_seconds=duration * 60 if duration else None,
                    hard_limit=True,
                    exhausted=reached or used == Decimal(100),
                    confidence=0.95,
                    evidence=(
                        CapacityEvidence(
                            source="codex_app_server_rate_limits",
                            source_digest=f"sha256:{digest}",
                            confidence=0.95,
                        ),
                    ),
                )
            )
    if not windows:
        windows.append(
            CapacityWindow(
                window_id="unknown",
                confidence=0,
                evidence=(
                    CapacityEvidence(
                        source="codex_app_server_rate_limits",
                        source_digest=f"sha256:{hashlib.sha256(b'unknown').hexdigest()}",
                        confidence=0,
                    ),
                ),
            )
        )
    credits = payload.get("rateLimitResetCredits")
    available = credits.get("availableCount") if isinstance(credits, dict) else None
    return CapacityObservation(
        resource_id=resource_id,
        windows=tuple(windows),
        source="codex_app_server",
        redacted_provider_metadata={
            "reset_credits_available": available if isinstance(available, int) else None,
        },
    )


def turn_accounting(
    token_usage: dict[str, int] | None,
    *,
    model: str | None,
    resource_pool: str,
) -> tuple[ResourceVector, ResourceAccounting]:
    subscription = SubscriptionUsage(
        provider="openai",
        resource_pool=resource_pool,
        consumed=None,
        source=MeasurementEvidence(),
        included_or_paid=SubscriptionCharge.UNKNOWN,
    )
    if token_usage is None or model is None:
        return ResourceVector(), ResourceAccounting(subscription_usage=[subscription])
    evidence = MeasurementEvidence(
        status=EvidenceStatus.COMPLETE,
        source=EvidenceSource.PROVIDER_REPORT,
        trust=TrustLevel.SELF_ASSERTED,
        observed_at=datetime.now(UTC),
    )
    usage = ModelTokenUsage(
        provider="openai",
        model=model,
        access_channel=ModelAccessChannel.SUBSCRIPTION,
        input_tokens=token_usage.get("inputTokens", 0),
        cached_input_tokens=token_usage.get("cachedInputTokens", 0),
        cache_write_input_tokens=token_usage.get("cacheWriteInputTokens", 0),
        output_tokens=token_usage.get("outputTokens", 0),
        reasoning_output_tokens=token_usage.get("reasoningOutputTokens", 0),
        evidence=evidence,
    )
    resources = ResourceVector(
        input_tokens=usage.input_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        cache_write_input_tokens=usage.cache_write_input_tokens,
        output_tokens=usage.output_tokens,
        reasoning_output_tokens=usage.reasoning_output_tokens,
    )
    return resources, ResourceAccounting(
        subscription_usage=[subscription],
        model_usage=[usage],
    )


def _percentage(value: Any) -> Decimal | None:
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100:
        return Decimal(value)
    return None


def _positive_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _unix_time(value: Any) -> datetime | None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return None
    try:
        return datetime.fromtimestamp(value, UTC)
    except (OverflowError, OSError, ValueError):
        return None
