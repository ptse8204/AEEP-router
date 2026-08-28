"""Blend static route estimates with observed execution receipts."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from decimal import Decimal
from statistics import fmean, pstdev
from typing import Any

from .economic.canonical import canonical_action_digest
from .models import (
    ActionFeatures,
    CashEstimate,
    EstimateSource,
    EstimateUncertainty,
    EvidenceCohortKey,
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
from .provider_package import EvidenceAcceptanceStatus
from .qualification import behavior_fingerprint
from .store import ReceiptStore


def evidence_cohort(spec: ExecutorSpec, features: ActionFeatures | None) -> EvidenceCohortKey:
    """Build the exact, non-payload cohort allowed to influence this route."""

    cache = spec.config.get("cache_affinity")
    cache_config = cache if isinstance(cache, Mapping) else {}
    economic = spec.config.get("economic")
    economic_config = economic if isinstance(economic, Mapping) else {}
    return EvidenceCohortKey(
        capability=spec.capability,
        executor_id=spec.id,
        executor_fingerprint=f"sha256:{behavior_fingerprint(spec)}",
        provider=spec.provider_id or "local",
        provider_version=_optional_text(spec.config.get("provider_version")),
        model=_optional_text(spec.config.get("model")),
        model_version=_optional_text(spec.config.get("model_version")),
        integration_adapter=(
            _optional_text(spec.config.get("integration_adapter")) or spec.kind.value
        ),
        integration_adapter_version=_optional_text(
            spec.config.get("integration_adapter_version")
        ),
        region=_optional_text(spec.config.get("region")),
        account_tier=_optional_text(spec.config.get("account_tier")),
        action_size_bucket=features.size_bucket if features is not None else "unknown",
        validator_digest=canonical_action_digest(
            {
                "purpose": "aeep-validator-set-v1",
                "validators": [item.model_dump(mode="json") for item in spec.validators],
            }
        ),
        cache_namespace=_optional_text(cache_config.get("namespace")),
        cache_profile=_optional_text(cache_config.get("profile")),
        evidence_period=_optional_text(economic_config.get("evidence_period")),
        economic_evidence_level=_optional_text(economic_config.get("evidence_level")),
    )


def evidence_cohort_digest(
    spec: ExecutorSpec,
    features: ActionFeatures | None,
) -> tuple[str, str]:
    key = evidence_cohort(spec, features)
    return key.executor_fingerprint, canonical_action_digest(
        {"purpose": key.profile, "cohort": key.model_dump(mode="json")}
    )


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return (
        value
        if len(value) <= 100
        else canonical_action_digest({"purpose": "aeep-cohort-label-v1", "value": value})
    )


class HistoricalEstimator:
    def __init__(self, store: ReceiptStore) -> None:
        self.store = store

    def estimate(
        self,
        spec: ExecutorSpec,
        policy: PolicyConfig,
        features: ActionFeatures | None = None,
    ) -> RouteEstimate:
        base = _shared_prior(self.store, spec, policy)
        fingerprint, cohort = evidence_cohort_digest(spec, features)
        receipts = [
            receipt
            for receipt in self.store.receipts_for_cohort(
                spec.id,
                executor_fingerprint=fingerprint,
                cohort_digest=cohort,
                limit=200,
            )
            if receipt.status
            not in {
                ExecutionStatus.DELEGATED,
                ExecutionStatus.HOST_SELECTED,
                ExecutionStatus.UNKNOWN,
            }
        ]
        if not receipts:
            return base
        historical = _historical(receipts, base)
        uncertainty = _empirical_uncertainty(receipts, cohort)
        sample_factor = len(receipts) / (len(receipts) + policy.history_prior_samples)
        blend = policy.history_weight * sample_factor
        return RouteEstimate(
            resources=_blend_resources(base.resources, historical.resources, blend),
            cash=_blend_cash(base.cash, historical.cash, blend),
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
            confidence=min(1.0, _blend(base.confidence, historical.confidence, blend)),
            source=EstimateSource.BLENDED,
            sample_size=len(receipts),
            uncertainty=uncertainty,
        )


def _shared_prior(store: ReceiptStore, spec: ExecutorSpec, policy: PolicyConfig) -> RouteEstimate:
    base = spec.estimate.model_copy(deep=True)
    if not policy.evidence_reuse.enabled:
        return base
    evidence = {item.evidence_id: item for item in store.list_evidence_records(spec.id)}
    accepted = [
        item
        for item in store.list_evidence_acceptances(spec.id)
        if item.status
        in {
            EvidenceAcceptanceStatus.ACCEPTED,
            EvidenceAcceptanceStatus.ACCEPTED_AS_PRIOR,
        }
    ]
    latest = {item.metric: item for item in accepted}
    maximum_sample = 0
    for metric, acceptance in latest.items():
        record = evidence.get(acceptance.evidence_id)
        if record is None or record.summary is None:
            continue
        summary = record.summary
        sample_size = _integer_value(summary.get("sample_size")) or _summary_trials(summary)
        maximum_sample = max(maximum_sample, sample_size)
        weight = min(
            policy.evidence_reuse.max_shared_weight,
            float(acceptance.confidence)
            * sample_size
            / (sample_size + policy.evidence_reuse.shared_prior_samples),
        )
        if weight <= 0:
            continue
        if metric == "latency":
            latency = _summary_median(summary.get("latency"), "median_ms", "end_to_end_ms")
            if latency is not None:
                base.resources.latency_ms = _blend(
                    base.resources.latency_ms,
                    latency,
                    weight,
                )
        elif metric == "tokens":
            tokens = summary.get("tokens")
            if isinstance(tokens, dict):
                for field in (
                    "input_tokens",
                    "cached_input_tokens",
                    "cache_write_input_tokens",
                    "output_tokens",
                    "reasoning_output_tokens",
                ):
                    value = _summary_median(tokens.get(field), "median")
                    if value is not None:
                        setattr(
                            base.resources,
                            field,
                            round(_blend(float(getattr(base.resources, field)), value, weight)),
                        )
        elif metric == "correctness":
            success = summary.get("success")
            if isinstance(success, dict):
                rate = _number_value(success.get("success_rate"))
                trials = _integer_value(success.get("trials"))
                successes = _integer_value(success.get("successes"))
                if rate is None and trials and successes is not None:
                    rate = successes / trials
                if rate is not None:
                    base.success_probability = min(
                        1.0,
                        max(0.001, _blend(base.success_probability, rate, weight)),
                    )
                quality = _number_value(success.get("quality_median"))
                if quality is not None:
                    base.quality_score = min(
                        1.0,
                        max(0.0, _blend(base.quality_score, quality, weight)),
                    )
        elif metric == "cost":
            cost = summary.get("cost")
            if isinstance(cost, dict):
                amount = _summary_median(
                    cost.get("actual_cash"),
                    "median",
                    "actual_cash_usd",
                )
                if amount is None:
                    amount = _number_value(cost.get("actual_cash_usd"))
                if amount is not None and amount >= 0:
                    base.cash = CashEstimate(
                        amount_usd=Decimal(str(_blend(
                            float(base.cash.amount_usd or Decimal(0)),
                            amount,
                            weight,
                        ))),
                        upper_bound_usd=base.cash.upper_bound_usd,
                        evidence=MeasurementEvidence(
                            status=EvidenceStatus.COMPLETE,
                            source=EvidenceSource.STATIC_ESTIMATE,
                            trust=acceptance.effective_trust,
                            evidence_id=acceptance.evidence_id,
                            observed_at=acceptance.evaluated_at,
                        ),
                    )
        base.confidence = min(1.0, _blend(base.confidence, float(acceptance.confidence), weight))
    if latest:
        base.source = EstimateSource.BLENDED
        base.sample_size = maximum_sample
    return base


def _number_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _integer_value(value: Any) -> int:
    parsed = _number_value(value)
    return int(parsed) if parsed is not None and parsed >= 0 else 0


def _summary_trials(summary: dict[str, Any]) -> int:
    success = summary.get("success")
    return _integer_value(success.get("trials")) if isinstance(success, dict) else 0


def _summary_median(value: Any, *keys: str) -> float | None:
    direct = _number_value(value)
    if direct is not None:
        return direct
    if not isinstance(value, dict):
        return None
    for key in keys:
        parsed = _number_value(value.get(key))
        if parsed is not None:
            return parsed
    for nested in value.values():
        parsed = _summary_median(nested, *keys)
        if parsed is not None:
            return parsed
    return None


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


def _empirical_uncertainty(
    receipts: list[ExecutionReceipt],
    cohort_digest: str,
) -> EstimateUncertainty | None:
    if len(receipts) < 5:
        return None

    resources = [receipt.actual_resources for receipt in receipts]

    def resource_percentile(probability: float) -> ResourceVector:
        values: dict[str, float | int] = {}
        integer_fields = {
            "network_bytes",
            "context_tokens",
            "input_tokens",
            "cached_input_tokens",
            "cache_write_input_tokens",
            "output_tokens",
            "reasoning_output_tokens",
        }
        for field in ResourceVector.model_fields:
            observed = [float(getattr(item, field)) for item in resources]
            value = _nearest_rank(observed, probability)
            values[field] = round(value) if field in integer_fields else value
        return ResourceVector.model_validate(values)

    succeeded = [
        receipt.status is ExecutionStatus.SUCCESS
        and receipt.output_valid is not False
        and receipt.task_valid is not False
        for receipt in receipts
    ]
    quality = [
        receipt.quality_score
        if receipt.quality_score is not None
        else 1.0
        if receipt.task_valid
        else 0.0
        for receipt in receipts
        if receipt.quality_score is not None or receipt.task_valid is not None
    ]
    cash = [receipt.accounting.cash.actual_cash_cost("USD") for receipt in receipts]
    cash_p95 = (
        sorted(item for item in cash if item is not None)[math.ceil(0.95 * len(cash)) - 1]
        if all(item is not None for item in cash)
        else None
    )
    quality_lower_bound = None
    if len(quality) >= 5:
        quality_mean = fmean(quality)
        quality_margin = 1.96 * pstdev(quality) / math.sqrt(len(quality))
        quality_lower_bound = max(0.0, min(1.0, quality_mean - quality_margin))
    return EstimateUncertainty(
        sample_size=len(receipts),
        cohort_digest=cohort_digest,
        resources_p50=resource_percentile(0.50),
        resources_p95=resource_percentile(0.95),
        cash_p95_usd=cash_p95,
        success_lower_bound=_wilson_lower_bound(sum(succeeded), len(succeeded)),
        quality_sample_size=len(quality),
        quality_lower_bound=quality_lower_bound,
    )


def _nearest_rank(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(probability * len(ordered)) - 1)]


def _wilson_lower_bound(successes: int, trials: int) -> float:
    z = 1.96
    proportion = successes / trials
    denominator = 1 + z * z / trials
    centre = proportion + z * z / (2 * trials)
    margin = z * math.sqrt(
        proportion * (1 - proportion) / trials + z * z / (4 * trials * trials)
    )
    return max(0.0, (centre - margin) / denominator)


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
        "cache_write_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
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
