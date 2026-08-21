"""Blend static route estimates with observed execution receipts."""

from __future__ import annotations

import json
import math
from decimal import Decimal
from typing import Any

from .models import (
    ActionFeatures,
    CashEstimate,
    EstimateSource,
    EvidenceSource,
    EvidenceStatus,
    ExecutionReceipt,
    ExecutionStatus,
    ExecutorSpec,
    MeasurementEvidence,
    PolicyConfig,
    ResourceVector,
    RouteEstimate,
    TrustLevel,
)
from .store import ReceiptStore


class HistoricalEstimator:
    def __init__(self, store: ReceiptStore) -> None:
        self.store = store

    def estimate(
        self,
        spec: ExecutorSpec,
        policy: PolicyConfig,
        features: ActionFeatures | None = None,
    ) -> RouteEstimate:
        receipts = [
            receipt
            for receipt in self.store.receipts_for_executor(spec.id, limit=200)
            if receipt.status
            not in {
                ExecutionStatus.DELEGATED,
                ExecutionStatus.HOST_SELECTED,
                ExecutionStatus.UNKNOWN,
            }
            and (
                features is None
                or (
                    receipt.action_features is not None
                    and receipt.action_features.size_bucket == features.size_bucket
                )
            )
        ]
        if not receipts:
            return spec.estimate.model_copy(deep=True)
        historical = _historical(receipts, spec.estimate)
        sample_factor = len(receipts) / (len(receipts) + policy.history_prior_samples)
        blend = policy.history_weight * sample_factor
        return RouteEstimate(
            resources=_blend_resources(spec.estimate.resources, historical.resources, blend),
            cash=_blend_cash(spec.estimate.cash, historical.cash, blend),
            subscription_usage=(
                historical.subscription_usage
                if historical.subscription_usage
                else spec.estimate.subscription_usage
            ),
            success_probability=_blend(
                spec.estimate.success_probability, historical.success_probability, blend
            ),
            quality_score=_blend(spec.estimate.quality_score, historical.quality_score, blend),
            risk_score=_blend(spec.estimate.risk_score, historical.risk_score, blend),
            confidence=min(1.0, _blend(spec.estimate.confidence, historical.confidence, blend)),
            source=EstimateSource.BLENDED,
            sample_size=len(receipts),
        )


def action_features(value: dict[str, Any]) -> ActionFeatures:
    """Extract bounded, non-content features suitable for persisted learning."""

    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    item_count = 0
    text_characters = 0
    max_depth = 0
    stack: list[tuple[Any, int]] = [(value, 0)]
    while stack:
        current, depth = stack.pop()
        max_depth = max(max_depth, depth)
        if isinstance(current, dict):
            item_count += len(current)
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            item_count += len(current)
            stack.extend((item, depth + 1) for item in current)
        elif isinstance(current, str):
            text_characters += len(current)
    byte_count = len(encoded)
    bucket = "empty" if byte_count == 0 else f"2^{int(math.log2(byte_count))}"
    return ActionFeatures(
        input_bytes=byte_count,
        input_items=item_count,
        text_characters=text_characters,
        max_depth=max_depth,
        size_bucket=bucket,
    )


def _historical(
    receipts: list[ExecutionReceipt],
    prior: RouteEstimate,
) -> RouteEstimate:
    alpha = 0.30
    resource = _eligible_resources(receipts[0], prior.resources)
    success_ewma = (
        1.0
        if receipts[0].status == ExecutionStatus.SUCCESS
        and receipts[0].output_valid is not False
        and receipts[0].task_valid is not False
        else 0.0
    )
    valid_samples: list[bool] = []
    if receipts[0].output_valid is not None:
        valid_samples.append(receipts[0].output_valid)
    for receipt in receipts[1:]:
        resource = _blend_resources(resource, _eligible_resources(receipt, resource), alpha)
        succeeded = (
            1.0
            if receipt.status == ExecutionStatus.SUCCESS
            and receipt.output_valid is not False
            and receipt.task_valid is not False
            else 0.0
        )
        success_ewma = _blend(success_ewma, succeeded, alpha)
        if receipt.output_valid is not None:
            valid_samples.append(receipt.output_valid)
    quality = (
        sum(1.0 for value in valid_samples if value) / len(valid_samples)
        if valid_samples
        else prior.quality_score
    )
    failure_rate = 1.0 - success_ewma
    actual_cash: list[Decimal] = []
    for receipt in receipts:
        amount = receipt.accounting.cash.actual_cash_cost("USD")
        if amount is not None:
            actual_cash.append(amount)
    historical_cash = prior.cash
    if actual_cash:
        value = actual_cash[0]
        for item in actual_cash[1:]:
            value = value * Decimal(str(1 - alpha)) + item * Decimal(str(alpha))
        historical_cash = CashEstimate(
            amount_usd=value,
            # Historical maxima are priors, not contractual authorization bounds.
            upper_bound_usd=None,
            evidence=MeasurementEvidence(
                status=(
                    EvidenceStatus.COMPLETE
                    if len(actual_cash) == len(receipts)
                    else EvidenceStatus.PARTIAL
                ),
                source=EvidenceSource.LOCAL_METER,
                trust=TrustLevel.OBSERVED,
            ),
        )
    return RouteEstimate(
        resources=resource,
        cash=historical_cash,
        subscription_usage=prior.subscription_usage,
        success_probability=max(0.001, min(1.0, success_ewma)),
        quality_score=max(0.0, min(1.0, quality)),
        risk_score=max(prior.risk_score, min(1.0, failure_rate * 0.5)),
        confidence=min(1.0, len(receipts) / 20.0),
        source=EstimateSource.HISTORICAL,
        sample_size=len(receipts),
    )


def _blend(a: float, b: float, weight_b: float) -> float:
    return float(a * (1.0 - weight_b) + b * weight_b)


def _blend_resources(
    a: ResourceVector,
    b: ResourceVector,
    weight_b: float,
) -> ResourceVector:
    integer_fields = {
        "network_bytes",
        "context_tokens",
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
    }
    values: dict[str, float | int] = {}
    for field in ResourceVector.model_fields:
        value = _blend(float(getattr(a, field)), float(getattr(b, field)), weight_b)
        values[field] = round(value) if field in integer_fields else value
    return ResourceVector.model_validate(values)


def _eligible_resources(receipt: ExecutionReceipt, fallback: ResourceVector) -> ResourceVector:
    """Legacy cash/quota mirrors are not observations without authoritative evidence."""

    values = receipt.actual_resources.model_dump()
    actual_cash = receipt.accounting.cash.actual_cash_cost("USD")
    values["monetary_usd"] = (
        float(actual_cash) if actual_cash is not None else fallback.monetary_usd
    )
    known_usage = [
        item.consumed
        for item in receipt.accounting.subscription_usage
        if item.consumed is not None
        and item.source.trust in {TrustLevel.OBSERVED, TrustLevel.VERIFIED, TrustLevel.ATTESTED}
        and item.source.source != EvidenceSource.PROVIDER_REPORT
    ]
    values["subscription_units"] = (
        float(known_usage[0]) if len(known_usage) == 1 else fallback.subscription_units
    )
    return ResourceVector.model_validate(values)


def _blend_cash(a: CashEstimate, b: CashEstimate, weight_b: float) -> CashEstimate:
    if b.amount_usd is None:
        return a.model_copy(deep=True)
    if a.amount_usd is None:
        return b.model_copy(deep=True)
    amount = Decimal(str(_blend(float(a.amount_usd), float(b.amount_usd), weight_b)))
    bounds = [item for item in (a.upper_bound_usd, b.upper_bound_usd) if item is not None]
    upper = max(bounds) if bounds and max(bounds) >= amount else None
    return CashEstimate(
        amount_usd=amount,
        upper_bound_usd=upper,
        evidence=b.evidence,
    )
