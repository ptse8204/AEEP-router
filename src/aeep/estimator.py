"""Blend static route estimates with observed execution receipts."""

from __future__ import annotations

from collections.abc import Iterable

from .models import (
    EstimateSource,
    ExecutionReceipt,
    ExecutionStatus,
    ExecutorSpec,
    PolicyConfig,
    ResourceVector,
    RouteEstimate,
)
from .store import ReceiptStore


class HistoricalEstimator:
    def __init__(self, store: ReceiptStore) -> None:
        self.store = store

    def estimate(self, spec: ExecutorSpec, policy: PolicyConfig) -> RouteEstimate:
        receipts = [
            receipt
            for receipt in self.store.receipts_for_executor(spec.id, limit=200)
            if receipt.status not in {ExecutionStatus.DELEGATED, ExecutionStatus.UNKNOWN}
        ]
        if not receipts:
            return spec.estimate.model_copy(deep=True)
        historical = self._historical(receipts, spec.estimate)
        sample_factor = len(receipts) / (len(receipts) + policy.history_prior_samples)
        blend = policy.history_weight * sample_factor
        return RouteEstimate(
            resources=_blend_resources(spec.estimate.resources, historical.resources, blend),
            success_probability=_blend(
                spec.estimate.success_probability, historical.success_probability, blend
            ),
            quality_score=_blend(spec.estimate.quality_score, historical.quality_score, blend),
            risk_score=_blend(spec.estimate.risk_score, historical.risk_score, blend),
            confidence=min(1.0, _blend(spec.estimate.confidence, historical.confidence, blend)),
            source=EstimateSource.BLENDED,
            sample_size=len(receipts),
        )

    @staticmethod
    def _historical(
        receipts: list[ExecutionReceipt],
        prior: RouteEstimate,
    ) -> RouteEstimate:
        alpha = 0.30
        resource = receipts[0].actual_resources
        success_ewma = (
            1.0
            if receipts[0].status == ExecutionStatus.SUCCESS and receipts[0].output_valid is not False
            else 0.0
        )
        valid_samples: list[bool] = []
        if receipts[0].output_valid is not None:
            valid_samples.append(receipts[0].output_valid)
        for receipt in receipts[1:]:
            resource = _blend_resources(resource, receipt.actual_resources, alpha)
            succeeded = (
                1.0
                if receipt.status == ExecutionStatus.SUCCESS and receipt.output_valid is not False
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
        return RouteEstimate(
            resources=resource,
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
    integer_fields = {"network_bytes", "context_tokens", "input_tokens", "output_tokens"}
    values: dict[str, float | int] = {}
    for field in ResourceVector.model_fields:
        value = _blend(float(getattr(a, field)), float(getattr(b, field)), weight_b)
        values[field] = int(round(value)) if field in integer_fields else value
    return ResourceVector(**values)
