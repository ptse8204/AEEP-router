"""Fail-closed transferability checks."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from .models import CapacityAuthorizationEvidence, CapacityObservation, CapacityTransferability

if TYPE_CHECKING:
    from ..models import QuotaState, SubscriptionQuota


def observation_quota(
    observation: CapacityObservation,
    *,
    unit: str,
    now: datetime | None = None,
) -> SubscriptionQuota:
    """Reduce multiple raw windows to their most constraining routing signal."""

    from ..models import QuotaSource, QuotaState, SubscriptionQuota

    current = (now or datetime.now(UTC)).astimezone(UTC)
    windows = [item for item in observation.windows if item.unit == unit]
    if not windows:
        return SubscriptionQuota(
            state=QuotaState.UNKNOWN,
            confidence=0,
            source=QuotaSource.RATE_LIMIT,
            unit=unit,
            window_count=len(observation.windows),
            evidence_digest=observation.canonical_digest,
        )
    if any(item.hard_limit and item.exhausted for item in windows):
        state = QuotaState.EXHAUSTED
    else:
        used_values = [item.used_percent for item in windows if item.used_percent is not None]
        maximum_used = max(used_values) if used_values else None
        state = _quota_state(maximum_used)
    ranked = sorted(
        windows,
        key=lambda item: (
            item.used_percent if item.used_percent is not None else Decimal(-1),
            -(item.remaining if item.remaining is not None else Decimal("Infinity")),
            item.window_id,
        ),
        reverse=True,
    )
    controlling = ranked[0]
    remaining = [item.remaining for item in windows if item.remaining is not None]
    allowances = [item.allowance for item in windows if item.allowance is not None]
    return SubscriptionQuota(
        state=state,
        reset_at=controlling.reset_at if controlling.reset_at and controlling.reset_at > current else None,
        observed_at=observation.observed_at,
        confidence=min(item.confidence for item in windows),
        source=QuotaSource.RATE_LIMIT,
        unit=unit,
        allowance_units=min(allowances) if allowances else None,
        remaining_units=min(remaining) if remaining else None,
        used_percent=controlling.used_percent,
        window_duration_seconds=controlling.duration_seconds,
        window_count=len(windows),
        evidence_digest=observation.canonical_digest,
    )


def _quota_state(used_percent: Decimal | None) -> QuotaState:
    from ..models import QuotaState

    if used_percent is None:
        return QuotaState.UNKNOWN
    if used_percent <= 25:
        return QuotaState.ABUNDANT
    if used_percent <= 60:
        return QuotaState.NORMAL
    if used_percent <= 80:
        return QuotaState.TIGHT
    if used_percent < 100:
        return QuotaState.CRITICAL
    return QuotaState.EXHAUSTED


def require_entitlement_authority(
    *,
    transferability: CapacityTransferability,
    issuer_principal_digest: str,
    beneficiary_principal_digest: str,
    known_available: Decimal | None,
    requested: Decimal,
    authorization: CapacityAuthorizationEvidence | None,
) -> None:
    if requested <= 0:
        raise ValueError("entitlement quantity must be positive")
    if known_available is None:
        raise ValueError("unknown capacity cannot authorize an entitlement")
    if requested > known_available:
        raise ValueError("entitlement exceeds known available capacity")
    same_principal = issuer_principal_digest == beneficiary_principal_digest
    if transferability in {
        CapacityTransferability.SELF_ONLY,
        CapacityTransferability.SAME_PRINCIPAL,
    }:
        if not same_principal:
            raise ValueError("self-only capacity cannot name an external beneficiary")
        return
    if authorization is None:
        raise ValueError("external entitlement requires provider authorization evidence")
    if authorization.issuer_principal_digest != issuer_principal_digest:
        raise ValueError("authorization issuer does not match entitlement issuer")
    if (
        authorization.authorized_beneficiary_digest is not None
        and authorization.authorized_beneficiary_digest != beneficiary_principal_digest
    ):
        raise ValueError("authorization beneficiary does not match entitlement beneficiary")
