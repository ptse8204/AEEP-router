from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from aeep.accounting import (
    aggregate_accounting,
    price_model_usage,
    subscription_model_accounting,
    subscription_usage_from_tokens,
)
from aeep.economics import HMACSigner, _legacy_receipt_payload
from aeep.models import (
    ActionConstraints,
    ActionContext,
    CashAccounting,
    CashClassification,
    CashEvidence,
    EvidenceSource,
    EvidenceStatus,
    ExecutionReceipt,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    MeasurementEvidence,
    MetricWeights,
    ModelAccessChannel,
    ModelTokenUsage,
    PolicyConfig,
    RateCardRate,
    RateCardSnapshot,
    RateType,
    ResourceVector,
    RouteEstimate,
    SideEffect,
    SignedExecutionReceipt,
    SubscriptionCharge,
    SubscriptionPolicyRule,
    SubscriptionQuota,
    TrustLevel,
)
from aeep.scoring import score_candidate
from aeep.store import ReceiptStore


def evidence(source: EvidenceSource, trust: TrustLevel = TrustLevel.VERIFIED):
    return MeasurementEvidence(
        status=EvidenceStatus.COMPLETE,
        source=source,
        trust=trust,
    )


def price_snapshot(*, input_rate: str = "0.01") -> RateCardSnapshot:
    return RateCardSnapshot(
        provider="openai",
        product="api",
        model="model-x",
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        retrieved_at=datetime(2026, 1, 2, tzinfo=UTC),
        source_uri="https://example.test/pricing",
        source_content_sha256="a" * 64,
        currency="USD",
        rates=[
            RateCardRate(
                rate_id="input",
                rate_type=RateType.INPUT_TOKEN,
                meter="input_tokens",
                input_unit="token",
                output_unit="USD",
                unit_quantity=1000,
                rate_amount=input_rate,
            ),
            RateCardRate(
                rate_id="cached",
                rate_type=RateType.CACHED_INPUT_TOKEN,
                meter="cached_input_tokens",
                input_unit="token",
                output_unit="USD",
                unit_quantity=1000,
                rate_amount="0.002",
            ),
            RateCardRate(
                rate_id="output",
                rate_type=RateType.OUTPUT_TOKEN,
                meter="output_tokens",
                input_unit="token",
                output_unit="USD",
                unit_quantity=1000,
                rate_amount="0.03",
            ),
        ],
    )


def usage(channel: ModelAccessChannel, *, cache_write: int = 0) -> ModelTokenUsage:
    return ModelTokenUsage(
        provider="openai",
        model="model-x",
        access_channel=channel,
        input_tokens=1000,
        cached_input_tokens=400,
        cache_write_input_tokens=cache_write,
        output_tokens=100,
        reasoning_output_tokens=20,
        evidence=evidence(EvidenceSource.LOCAL_METER, TrustLevel.OBSERVED),
    )


def test_api_tariff_is_actual_only_for_billable_api_usage():
    snapshot = price_snapshot()
    actual = price_model_usage(usage(ModelAccessChannel.API), snapshot, actual_billable=True)
    assert isinstance(actual, CashEvidence)
    assert actual.amount == Decimal("0.0098")
    assert actual.classification == CashClassification.PINNED_RATE_BILLABLE_USAGE
    assert actual.applied_meter_quantities == {
        "input": Decimal(600),
        "cached": Decimal(400),
        "output": Decimal(100),
    }

    counterfactual = price_model_usage(usage(ModelAccessChannel.SUBSCRIPTION), snapshot)
    assert counterfactual.amount == actual.amount
    accounting = subscription_model_accounting(
        usage(ModelAccessChannel.SUBSCRIPTION),
        resource_pool="openai:chatgpt:agentic",
        unit="codex_credit",
        consumed=Decimal("18.7"),
        usage_evidence=evidence(EvidenceSource.PROVIDER_REPORT, TrustLevel.SELF_ASSERTED),
        included_or_paid=SubscriptionCharge.UNKNOWN,
    )
    assert accounting.cash.actual_cash_cost() is None
    assert accounting.subscription_usage[0].consumed == Decimal("18.7")


def test_rate_card_rejects_overlap_currency_mismatch_and_scoped_mismatch():
    base = price_snapshot()
    payload = base.model_dump(exclude={"snapshot_id"})
    payload["rates"].extend(
        [
            RateCardRate(
                rate_id="long-a",
                rate_type=RateType.INPUT_TOKEN,
                meter="input_tokens",
                input_unit="token",
                output_unit="USD",
                unit_quantity=1000,
                rate_amount="0.02",
                long_context_min=1000,
                long_context_max=2000,
            ),
            RateCardRate(
                rate_id="long-b",
                rate_type=RateType.INPUT_TOKEN,
                meter="input_tokens",
                input_unit="token",
                output_unit="USD",
                unit_quantity=1000,
                rate_amount="0.03",
                long_context_min=1500,
            ),
        ]
    )
    with pytest.raises(ValueError, match="overlapping"):
        RateCardSnapshot.model_validate(payload)

    wrong_currency = base.model_dump(exclude={"snapshot_id"})
    wrong_currency["rates"][0]["output_unit"] = "EUR"
    with pytest.raises(ValueError, match="output_unit"):
        RateCardSnapshot.model_validate(wrong_currency)

    scoped = base.model_dump(exclude={"snapshot_id"})
    for rate in scoped["rates"]:
        rate["region"] = "us-east"
        rate["service_tier"] = "priority"
    scoped_snapshot = RateCardSnapshot.model_validate(scoped)
    mismatched = price_model_usage(
        usage(ModelAccessChannel.SUBSCRIPTION),
        scoped_snapshot,
        service_tier="priority",
        region="eu-west",
    )
    assert mismatched.amount is None
    assert mismatched.status == EvidenceStatus.PARTIAL


def test_rate_arithmetic_covers_long_context_cache_write_and_tool_calls_once():
    base = price_snapshot()
    payload = base.model_dump(exclude={"snapshot_id"})
    payload["rates"].extend(
        [
            RateCardRate(
                rate_id="long-input",
                rate_type=RateType.INPUT_TOKEN,
                meter="input_tokens",
                input_unit="token",
                output_unit="USD",
                unit_quantity=1000,
                rate_amount="0.02",
                long_context_min=1000,
                multiplier="1.5",
                rule="long context multiplier",
            ),
            RateCardRate(
                rate_id="cache-write",
                rate_type=RateType.CACHE_WRITE_TOKEN,
                meter="cache_write_input_tokens",
                input_unit="token",
                output_unit="USD",
                unit_quantity=1000,
                rate_amount="0.004",
            ),
            RateCardRate(
                rate_id="tool",
                rate_type=RateType.TOOL_CALL,
                meter="tool_calls",
                input_unit="call",
                output_unit="USD",
                unit_quantity=1,
                rate_amount="0.005",
                tool_name="search",
            ),
        ]
    )
    snapshot = RateCardSnapshot.model_validate(payload)
    priced = price_model_usage(
        usage(ModelAccessChannel.API, cache_write=50),
        snapshot,
        actual_billable=True,
        tool_name="search",
        meter_quantities={"tool_calls": 2},
    )
    assert isinstance(priced, CashEvidence)
    assert priced.amount == Decimal("0.0305")
    assert priced.applied_meter_quantities == {
        "long-input": Decimal(550),
        "cached": Decimal(400),
        "output": Decimal(100),
        "cache-write": Decimal(50),
        "tool": Decimal(2),
    }
    assert "reasoning_output_tokens" not in priced.applied_meter_quantities


def test_official_sol_snapshot_prices_measured_codex_usage_without_double_counting():
    snapshot = RateCardSnapshot.model_validate_json(
        (
            Path(__file__).parents[1] / "examples/proof/openai-gpt-5.6-sol-standard-rate-card.json"
        ).read_text()
    )
    measured = ModelTokenUsage(
        provider="openai",
        model="gpt-5.6-sol",
        access_channel=ModelAccessChannel.SUBSCRIPTION,
        input_tokens=17_897,
        cached_input_tokens=9_984,
        cache_write_input_tokens=0,
        output_tokens=9,
        evidence=evidence(EvidenceSource.LOCAL_METER, TrustLevel.OBSERVED),
    )
    priced = price_model_usage(measured, snapshot)
    assert priced.amount == Decimal("0.0448270")
    assert priced.applied_meter_quantities == {
        "standard-short-input": Decimal(7_913),
        "standard-short-output": Decimal(9),
        "standard-short-cached-input": Decimal(9_984),
        "standard-short-cache-write": Decimal(0),
    }


def test_evidenced_zero_is_not_unknown_or_economically_free():
    accounting = subscription_model_accounting(
        usage(ModelAccessChannel.SUBSCRIPTION),
        resource_pool="openai:chatgpt:agentic",
        unit="codex_credit",
        consumed=Decimal("2"),
        usage_evidence=evidence(EvidenceSource.PROVIDER_REPORT, TrustLevel.SELF_ASSERTED),
        included_or_paid=SubscriptionCharge.INCLUDED,
        confirmed_zero_incremental_cash=True,
    )
    assert accounting.cash.actual_cash_cost() == 0

    spec = ExecutorSpec(
        id="subscription",
        capability="x",
        kind=ExecutorKind.HOST,
        description="subscription",
        resource_pool="openai:chatgpt:agentic",
        side_effect=SideEffect.NONE,
        estimate=RouteEstimate(resources=ResourceVector(subscription_units=2, monetary_usd=0)),
        config={"instructions": "x"},
    )
    scored = score_candidate(
        spec,
        spec.estimate,
        PolicyConfig(weights=MetricWeights(monetary=1, subscription=1)),
        ActionContext(),
        SubscriptionQuota(remaining_units=10, allowance_units=100, confidence=1),
    )
    assert scored.score is not None and scored.score.subscription > 0


def test_unknown_cash_fails_finite_cap_and_never_becomes_zero():
    spec = ExecutorSpec(
        id="unknown",
        capability="x",
        kind=ExecutorKind.HTTP,
        description="unknown",
        side_effect=SideEffect.NONE,
        config={"url": "https://example.test"},
    )
    result = score_candidate(
        spec,
        RouteEstimate(),
        PolicyConfig(constraints=ActionConstraints(max_cost_usd=1)),
        ActionContext(),
    )
    assert not result.feasible
    assert "unavailable" in " ".join(result.rejection_reasons)


def test_cash_deduplicates_alternatives_and_detects_conflict():
    billed = CashEvidence(
        charge_id="charge-1",
        amount=Decimal("0.08"),
        classification=CashClassification.BILLING_RECONCILED,
        evidence=evidence(EvidenceSource.BILLING_RECORD),
    )
    calculated = CashEvidence(
        charge_id="charge-1",
        amount=Decimal("0.08"),
        classification=CashClassification.PINNED_RATE_BILLABLE_USAGE,
        evidence=evidence(EvidenceSource.PRICED_MEASURED_BILLABLE_USAGE),
        rate_snapshot_id="rate_x",
    )
    cash = CashAccounting(status=EvidenceStatus.COMPLETE, components=[billed, calculated])
    assert cash.actual_cash_cost() == Decimal("0.08")
    assert cash.known_subtotal() == Decimal("0.08")

    conflicting = CashAccounting(
        status=EvidenceStatus.COMPLETE,
        components=[billed, billed.model_copy(update={"amount": Decimal("0.09")})],
    )
    assert conflicting.status == EvidenceStatus.CONFLICT
    assert conflicting.actual_cash_cost() is None


def test_snapshot_is_immutable_and_historical_rows_do_not_reprice(tmp_path):
    original = price_snapshot()
    same = price_snapshot()
    changed = price_snapshot(input_rate="0.02")
    assert original.snapshot_id == same.snapshot_id
    assert original.snapshot_id != changed.snapshot_id
    store = ReceiptStore(tmp_path / "accounting.db")
    store.save_rate_card_snapshot(original)
    store.save_rate_card_snapshot(changed)
    assert store.get_rate_card_snapshot(original.snapshot_id or "") == original
    assert store.get_rate_card_snapshot(changed.snapshot_id or "") == changed


def test_credit_rate_card_produces_pool_usage_but_never_cash():
    base = price_snapshot()
    payload = base.model_dump(exclude={"snapshot_id"})
    payload["rates"].append(
        RateCardRate(
            rate_id="credits",
            rate_type=RateType.SUBSCRIPTION_UNIT,
            meter="input_tokens",
            input_unit="token",
            output_unit="codex_credit",
            unit_quantity=1000,
            rate_amount="2",
        )
    )
    credit_snapshot = RateCardSnapshot.model_validate(payload)
    consumed = subscription_usage_from_tokens(
        usage(ModelAccessChannel.SUBSCRIPTION),
        credit_snapshot,
        resource_pool="openai:chatgpt:agentic",
        unit="codex_credit",
        included_or_paid=SubscriptionCharge.UNKNOWN,
    )
    assert consumed.consumed == Decimal("2")
    assert consumed.rate_snapshot_id == credit_snapshot.snapshot_id
    assert consumed.source.source == EvidenceSource.PINNED_RATE_TABLE

    unavailable = subscription_usage_from_tokens(
        usage(ModelAccessChannel.SUBSCRIPTION),
        base,
        resource_pool="openai:chatgpt:agentic",
        unit="codex_credit",
    )
    assert unavailable.consumed is None
    assert unavailable.source.status == EvidenceStatus.UNAVAILABLE


def _receipt(identifier: str, accounting) -> ExecutionReceipt:
    return ExecutionReceipt(
        receipt_id=identifier,
        decision_id="d",
        action_id="a",
        capability="x",
        executor_id=identifier,
        executor_kind=ExecutorKind.HTTP,
        status=ExecutionStatus.SUCCESS,
        estimated=RouteEstimate(),
        accounting=accounting,
    )


def test_attempt_aggregation_is_pool_local_and_one_unknown_cash_is_incomplete():
    known = subscription_model_accounting(
        usage(ModelAccessChannel.SUBSCRIPTION),
        resource_pool="openai:plan-a",
        unit="credit",
        consumed=Decimal("2"),
        usage_evidence=evidence(EvidenceSource.PROVIDER_REPORT, TrustLevel.SELF_ASSERTED),
        confirmed_zero_incremental_cash=True,
    )
    other = subscription_model_accounting(
        usage(ModelAccessChannel.SUBSCRIPTION),
        resource_pool="anthropic:plan-b",
        unit="message",
        consumed=Decimal("3"),
        usage_evidence=evidence(EvidenceSource.PROVIDER_REPORT, TrustLevel.SELF_ASSERTED),
    )
    aggregated = aggregate_accounting([_receipt("one", known), _receipt("two", other)])
    assert {(item.resource_pool, item.unit) for item in aggregated.subscription_usage} == {
        ("openai:plan-a", "credit"),
        ("anthropic:plan-b", "message"),
    }
    assert aggregated.cash.known_subtotal() == 0
    assert aggregated.cash.actual_cash_cost() is None


def test_policy_value_changes_rank_without_changing_cash():
    policy = PolicyConfig(
        weights=MetricWeights(monetary=1, latency=0, compute=0, subscription=0),
        subscription_rules=[
            SubscriptionPolicyRule(
                resource_pool="openai:plan",
                unit="credit",
                policy_value_usd_per_unit=Decimal("1"),
            )
        ],
    )
    spec = ExecutorSpec(
        id="subscription",
        capability="x",
        kind=ExecutorKind.HOST,
        description="subscription",
        resource_pool="openai:plan",
        side_effect=SideEffect.NONE,
        estimate=RouteEstimate(resources=ResourceVector(monetary_usd=0, subscription_units=1)),
        config={"instructions": "x"},
    )
    scored = score_candidate(
        spec,
        spec.estimate,
        policy,
        ActionContext(),
        SubscriptionQuota(unit="credit", state="abundant", confidence=1),
    )
    assert scored.score is not None
    assert scored.score.cash == 0
    assert scored.score.policy_valuation > 0
    assert spec.estimate.cash.amount_usd == 0


def test_signed_receipt_v1_compatibility_and_v2_accounting_tamper_detection():
    receipt = _receipt(
        "signed",
        subscription_model_accounting(
            usage(ModelAccessChannel.SUBSCRIPTION),
            resource_pool="openai:plan",
            unit="credit",
            consumed=Decimal("1"),
            usage_evidence=evidence(EvidenceSource.PROVIDER_REPORT, TrustLevel.SELF_ASSERTED),
            confirmed_zero_incremental_cash=True,
        ),
    )
    signer = HMACSigner(b"x" * 32, key_id="test")
    legacy = SignedExecutionReceipt(
        receipt=receipt,
        signature=signer.sign(_legacy_receipt_payload(receipt)),
        canonical_version=1,
    )
    assert signer.verify_receipt(legacy)
    signed = signer.sign_receipt(receipt)
    assert signer.verify_receipt(signed)
    signed.receipt.accounting.subscription_usage[0].consumed = Decimal("2")
    assert not signer.verify_receipt(signed)
