"""Evidence-aware resource aggregation and immutable rate-card arithmetic."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime
from decimal import Decimal

from .models import (
    BillingReconciliation,
    BoundedQuote,
    CapabilityOffer,
    CashAccounting,
    CashClassification,
    CashEstimate,
    CashEvidence,
    CounterfactualCashCost,
    EconomicEvidenceLevel,
    EvidenceSource,
    EvidenceStatus,
    ExecutionReceipt,
    MarketAggregate,
    MeasurementEvidence,
    ModelAccessChannel,
    ModelTokenUsage,
    RateCardRate,
    RateCardSnapshot,
    RateType,
    RefundReceiptV2,
    ResourceAccounting,
    SettlementReceipt,
    SettlementStatus,
    SubscriptionCharge,
    SubscriptionUsage,
    TrustLevel,
    UsageStatement,
)


def _economic_evidence(
    level: EconomicEvidenceLevel,
    record_id: str,
    *,
    source: EvidenceSource,
    observed_at: datetime,
    status: EvidenceStatus = EvidenceStatus.COMPLETE,
    trust: TrustLevel = TrustLevel.VERIFIED,
) -> MeasurementEvidence:
    """Map v0.4 evidence onto the legacy accounting envelope without inflating trust."""

    return MeasurementEvidence(
        status=status,
        source=source,
        trust=trust,
        evidence_id=record_id,
        source_reference=f"economic-evidence:{level.value}",
        observed_at=observed_at,
    )


def cash_estimate_from_offer(
    offer: CapabilityOffer,
    meter_quantities: Mapping[str, Decimal | int | str] | None = None,
) -> CashEstimate:
    """Convert a verified published offer into a USD prior, never a binding quote."""

    if offer.settlement_currency != "USD":
        raise ValueError("legacy cash estimates only support USD")
    quantities = meter_quantities or {}
    expected = Decimal(0)
    maximum = Decimal(0)
    expected_known = True
    maximum_known = True
    for rule in offer.pricing_rules:
        if rule.per_unit_amount is None:
            amount = rule.evaluate().amount
            expected += amount
            maximum += amount
            continue
        quantity = quantities.get(rule.meter or "")
        if quantity is None:
            expected_known = False
            if rule.maximum_amount is None:
                maximum_known = False
            else:
                maximum += rule.maximum_amount.amount
            continue
        amount = rule.evaluate(quantity).amount
        expected += amount
        maximum += amount
    if maximum_known and offer.fixed_attempt_fee is not None:
        # A failed attempt is an alternative billing outcome, not an amount to
        # add to the successful-use rules.  The reusable offer therefore binds
        # the larger of its request charge and fixed failure fee.
        maximum = max(maximum, offer.fixed_attempt_fee.amount)
    return CashEstimate(
        amount_usd=expected if expected_known else None,
        upper_bound_usd=maximum if maximum_known else None,
        evidence=_economic_evidence(
            EconomicEvidenceLevel.PUBLISHED_OFFER,
            offer.offer_id,
            source=EvidenceSource.PROVIDER_REPORT,
            observed_at=offer.issued_at,
        ),
    )


def cash_estimate_from_quote(quote: BoundedQuote) -> CashEstimate:
    """Convert a verified request-bound quote into expected and maximum USD cash."""

    if quote.maximum_amount.currency != "USD":
        raise ValueError("legacy cash estimates only support USD")
    return CashEstimate(
        amount_usd=(quote.expected_amount.amount if quote.expected_amount is not None else None),
        upper_bound_usd=quote.maximum_amount.amount,
        evidence=_economic_evidence(
            EconomicEvidenceLevel.SIGNED_QUOTE,
            quote.quote_id,
            source=EvidenceSource.PROVIDER_REPORT,
            observed_at=quote.issued_at,
        ),
    )


def cash_estimate_from_market_aggregate(aggregate: MarketAggregate) -> CashEstimate:
    """Use a verified aggregate as a prior; p95 is not a contractual upper bound."""

    amount = aggregate.actual_cost_p50
    if any(
        value is not None and value.currency != "USD"
        for value in (aggregate.actual_cost_p50, aggregate.actual_cost_p95)
    ):
        raise ValueError("legacy cash estimates only support USD")
    return CashEstimate(
        amount_usd=amount.amount if amount is not None else None,
        upper_bound_usd=None,
        evidence=_economic_evidence(
            EconomicEvidenceLevel.STATIC_PRIOR,
            aggregate.aggregate_id,
            source=EvidenceSource.PROVIDER_REPORT,
            observed_at=aggregate.generated_at,
        ),
    )


def _cash_status(components: list[CashEvidence]) -> EvidenceStatus:
    if not components:
        return EvidenceStatus.UNAVAILABLE
    authoritative = {CashClassification.VERIFIED, CashClassification.BILLING_RECONCILED}
    groups = {
        charge_id: [item for item in components if item.charge_id == charge_id]
        for charge_id in {item.charge_id for item in components}
    }
    if all(
        any(item.amount is not None and item.classification in authoritative for item in group)
        for group in groups.values()
    ):
        return EvidenceStatus.COMPLETE
    return EvidenceStatus.PARTIAL


def _merge_cash(prior: CashAccounting | None, component: CashEvidence) -> CashAccounting:
    existing = list(prior.components) if prior is not None else []
    evidence_id = component.evidence.evidence_id
    for item in existing:
        if evidence_id is not None and item.evidence.evidence_id == evidence_id:
            if item != component:
                raise ValueError(f"conflicting economic evidence ID {evidence_id!r}")
            return CashAccounting(status=_cash_status(existing), components=existing)
    # Newer evidence comes first so the legacy resolver returns the strongest
    # matching stage while retaining earlier stages for audit.
    components = [component, *existing]
    return CashAccounting(status=_cash_status(components), components=components)


def cash_accounting_from_usage_statement(
    statement: UsageStatement,
    *,
    charge_id: str,
    prior: CashAccounting | None = None,
) -> CashAccounting:
    """Record a signed provider assertion without treating it as payment evidence."""

    claimed = statement.provider_calculated_amount
    component = CashEvidence(
        charge_id=charge_id,
        amount=claimed.amount if claimed is not None else None,
        currency=claimed.currency if claimed is not None else "USD",
        classification=(
            CashClassification.ESTIMATED
            if claimed is not None
            else CashClassification.UNAVAILABLE
        ),
        evidence=_economic_evidence(
            EconomicEvidenceLevel.SIGNED_USAGE_STATEMENT,
            statement.usage_statement_id,
            source=EvidenceSource.PROVIDER_REPORT,
            observed_at=statement.issued_at,
            status=EvidenceStatus.PARTIAL,
        ),
    )
    return _merge_cash(prior, component)


def cash_accounting_from_settlement(
    settlement: SettlementReceipt,
    *,
    prior: CashAccounting | None = None,
) -> CashAccounting:
    """Record captured cash; incomplete settlements remain partial and non-authoritative."""

    final = settlement.status in {
        SettlementStatus.COMPLETED,
        SettlementStatus.SETTLED,
        SettlementStatus.RELEASED,
    }
    verified = final and settlement.evidence_level.is_payment_evidence
    component = CashEvidence(
        charge_id=settlement.charge_id,
        amount=settlement.captured_amount.amount,
        currency=settlement.captured_amount.currency,
        classification=(
            CashClassification.VERIFIED if verified else CashClassification.ESTIMATED
        ),
        evidence=_economic_evidence(
            settlement.evidence_level,
            settlement.settlement_id,
            source=(
                EvidenceSource.BILLING_RECORD if verified else EvidenceSource.OPERATOR_REPORT
            ),
            observed_at=settlement.settled_at,
            status=EvidenceStatus.COMPLETE if verified else EvidenceStatus.PARTIAL,
            trust=TrustLevel.VERIFIED if verified else TrustLevel.OBSERVED,
        ),
        billing_record_id=settlement.settlement_id,
    )
    return _merge_cash(prior, component)


def cash_accounting_from_reconciliation(
    reconciliation: BillingReconciliation,
    *,
    charge_id: str,
    prior: CashAccounting | None = None,
) -> CashAccounting:
    """Upgrade matching payment evidence; unresolved discrepancies stay non-authoritative."""

    reconciled = reconciliation.status.is_billing_reconciled
    component = CashEvidence(
        charge_id=charge_id,
        amount=reconciliation.billed_amount.amount,
        currency=reconciliation.billed_amount.currency,
        classification=(
            CashClassification.BILLING_RECONCILED
            if reconciled
            else CashClassification.ESTIMATED
        ),
        evidence=_economic_evidence(
            (
                EconomicEvidenceLevel.BILLING_RECONCILED
                if reconciled
                else EconomicEvidenceLevel.UNKNOWN
            ),
            reconciliation.reconciliation_id,
            source=(
                EvidenceSource.BILLING_RECORD
                if reconciled
                else EvidenceSource.OPERATOR_REPORT
            ),
            observed_at=reconciliation.reconciled_at,
            status=EvidenceStatus.COMPLETE if reconciled else EvidenceStatus.PARTIAL,
            trust=TrustLevel.VERIFIED if reconciled else TrustLevel.OBSERVED,
        ),
        billing_record_id=reconciliation.reconciliation_id,
    )
    return _merge_cash(prior, component)


def _conflicting_report_cash(
    settlement: SettlementReceipt,
    *,
    reason: str,
) -> CashAccounting:
    """Fail closed when supposedly linked immutable payment records disagree."""

    return CashAccounting(
        status=EvidenceStatus.CONFLICT,
        components=[
            CashEvidence(
                charge_id=settlement.charge_id,
                amount=None,
                currency=settlement.captured_amount.currency,
                classification=CashClassification.UNAVAILABLE,
                evidence=MeasurementEvidence(
                    status=EvidenceStatus.CONFLICT,
                    source=EvidenceSource.BILLING_RECORD,
                    trust=TrustLevel.VERIFIED,
                    evidence_id=settlement.settlement_id,
                    source_reference=reason,
                    observed_at=settlement.settled_at,
                ),
            )
        ],
    )


def cash_accounting_for_reporting(
    settlement: SettlementReceipt,
    *,
    reconciliations: Iterable[BillingReconciliation] = (),
    refunds: Iterable[RefundReceiptV2] = (),
) -> CashAccounting:
    """Resolve immutable paid-cash evidence into one non-persisted net charge.

    Settlement is the payment baseline.  The latest eligible reconciliation may
    replace that baseline, and completed V2 refunds are then deducted exactly
    once by immutable refund ID.  Historical receipts and evidence records stay
    untouched; this view exists only for totals and other operator reporting.
    """

    settled = cash_accounting_from_settlement(settlement)
    if settled.actual_cash_cost(settlement.captured_amount.currency) is None:
        return settled

    eligible = [
        item
        for item in reconciliations
        if item.settlement_id == settlement.settlement_id
        and item.status.is_billing_reconciled
        and item.expected_amount == settlement.captured_amount
        and (
            item.invoice_reference is not None
            or item.billing_record_reference is not None
            or item.evidence_digest is not None
        )
    ]
    reconciliation = max(
        eligible,
        key=lambda item: (item.reconciled_at, item.reconciliation_id),
        default=None,
    )
    amount = (
        reconciliation.billed_amount.amount
        if reconciliation is not None
        else settlement.captured_amount.amount
    )
    currency = (
        reconciliation.billed_amount.currency
        if reconciliation is not None
        else settlement.captured_amount.currency
    )
    if currency != settlement.captured_amount.currency:
        return _conflicting_report_cash(
            settlement,
            reason="reconciliation currency conflicts with settlement",
        )

    unique_refunds: dict[str, RefundReceiptV2] = {}
    for refund in refunds:
        previous = unique_refunds.get(refund.refund_id)
        if previous is not None:
            if previous != refund:
                return _conflicting_report_cash(
                    settlement,
                    reason="refund ID conflicts with immutable refund evidence",
                )
            continue
        if (
            refund.settlement_id != settlement.settlement_id
            or refund.charge_id != settlement.charge_id
            or refund.amount.currency != currency
        ):
            return _conflicting_report_cash(
                settlement,
                reason="refund binding conflicts with settlement",
            )
        unique_refunds[refund.refund_id] = refund

    refunded = sum(
        (item.amount.amount for item in unique_refunds.values()),
        Decimal(0),
    )
    if refunded > amount:
        return _conflicting_report_cash(
            settlement,
            reason="refund evidence exceeds the authoritative charge",
        )
    if reconciliation is None and not unique_refunds:
        return settled
    if reconciliation is not None and not unique_refunds:
        return cash_accounting_from_reconciliation(
            reconciliation,
            charge_id=settlement.charge_id,
            prior=settled,
        )

    refund_payload = [
        {
            "refund_id": item.refund_id,
            "amount": str(item.amount.amount),
            "currency": item.amount.currency,
        }
        for item in sorted(unique_refunds.values(), key=lambda item: item.refund_id)
    ]
    digest = hashlib.sha256(
        json.dumps(refund_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    evidence_level = (
        reconciliation.status.economic_evidence_level
        if reconciliation is not None
        else settlement.evidence_level
    )
    observed_at = max(
        [
            settlement.settled_at,
            *(item.refunded_at for item in unique_refunds.values()),
            *(
                [reconciliation.reconciled_at]
                if reconciliation is not None
                else []
            ),
        ]
    )
    return CashAccounting(
        status=EvidenceStatus.COMPLETE,
        components=[
            CashEvidence(
                charge_id=settlement.charge_id,
                amount=amount - refunded,
                currency=currency,
                classification=(
                    CashClassification.BILLING_RECONCILED
                    if reconciliation is not None
                    else CashClassification.VERIFIED
                ),
                evidence=_economic_evidence(
                    evidence_level,
                    f"net_{digest}",
                    source=EvidenceSource.BILLING_RECORD,
                    observed_at=observed_at,
                ),
                billing_record_id=(
                    reconciliation.reconciliation_id
                    if reconciliation is not None
                    else settlement.settlement_id
                ),
            )
        ],
    )


def usage_fingerprint(usage: ModelTokenUsage) -> str:
    payload = usage.model_dump(mode="json", exclude={"evidence"})
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _rate_for(
    snapshot: RateCardSnapshot,
    kind: RateType,
    service_tier: str | None,
    context_tokens: int,
    *,
    region: str | None = None,
    tool_name: str | None = None,
    meter: str | None = None,
) -> RateCardRate | None:
    matches = [
        rate
        for rate in snapshot.rates
        if rate.rate_type == kind
        and rate.service_tier == service_tier
        and (meter is None or rate.meter == meter)
        and (rate.region is None if region is None else rate.region in {None, region})
        and (rate.tool_name is None if tool_name is None else rate.tool_name in {None, tool_name})
        and (rate.long_context_min is None or context_tokens >= rate.long_context_min)
        and (rate.long_context_max is None or context_tokens <= rate.long_context_max)
    ]
    bounded = [
        rate
        for rate in matches
        if rate.long_context_min is not None or rate.long_context_max is not None
    ]
    if bounded:
        matches = bounded
    if matches:
        specificity = max(
            int(rate.region is not None) + int(rate.tool_name is not None) for rate in matches
        )
        matches = [
            rate
            for rate in matches
            if int(rate.region is not None) + int(rate.tool_name is not None) == specificity
        ]
    if len(matches) > 1:
        raise ValueError(f"ambiguous {kind.value} rate")
    return matches[0] if matches else None


def _charge(rate: RateCardRate, quantity: int | Decimal) -> Decimal:
    multiplier = rate.multiplier or Decimal(1)
    return Decimal(quantity) / rate.unit_quantity * rate.rate_amount * multiplier


def price_model_usage(
    usage: ModelTokenUsage,
    snapshot: RateCardSnapshot,
    *,
    actual_billable: bool = False,
    charge_id: str = "model-usage",
    service_tier: str | None = None,
    region: str | None = None,
    tool_name: str | None = None,
    meter_quantities: dict[str, int | Decimal] | None = None,
) -> CashEvidence | CounterfactualCashCost:
    """Price measured tokens without treating cached/reasoning subsets as extra tokens.

    `actual_billable` is deliberately explicit: the same arithmetic is attributable
    cash only when the caller has established that this tariff governed the route.
    """

    if usage.provider != snapshot.provider or usage.model != snapshot.model:
        raise ValueError("usage does not match rate-card provider/model")
    if snapshot.currency is None:
        raise ValueError("model cash pricing requires a monetary rate-card currency")
    if actual_billable and (
        usage.evidence.status != EvidenceStatus.COMPLETE
        or usage.evidence.trust
        not in {TrustLevel.OBSERVED, TrustLevel.VERIFIED, TrustLevel.ATTESTED}
    ):
        raise ValueError("attributable tariff cash requires complete measured usage evidence")
    context_tokens = usage.input_tokens
    selection = {
        "region": region,
        "tool_name": tool_name,
    }
    input_rate = _rate_for(
        snapshot, RateType.INPUT_TOKEN, service_tier, context_tokens, **selection
    )
    output_rate = _rate_for(
        snapshot, RateType.OUTPUT_TOKEN, service_tier, context_tokens, **selection
    )
    cached_rate = _rate_for(
        snapshot, RateType.CACHED_INPUT_TOKEN, service_tier, context_tokens, **selection
    )
    extra_types = {RateType.CACHE_WRITE_TOKEN, RateType.TOOL_CALL, RateType.OTHER}
    extra_keys = {
        (rate.rate_type, rate.meter)
        for rate in snapshot.rates
        if rate.rate_type in extra_types
        and rate.service_tier == service_tier
        and (rate.region is None if region is None else rate.region in {None, region})
        and (rate.tool_name is None if tool_name is None else rate.tool_name in {None, tool_name})
    }
    selected_extras = [
        _rate_for(
            snapshot,
            kind,
            service_tier,
            context_tokens,
            region=region,
            tool_name=tool_name,
            meter=meter,
        )
        for kind, meter in sorted(extra_keys, key=lambda item: (item[0].value, item[1]))
    ]
    extras = [rate for rate in selected_extras if rate is not None]
    known_meter_quantities = dict(meter_quantities or {})
    if "cache_write_input_tokens" in usage.model_fields_set:
        known_meter_quantities["cache_write_input_tokens"] = usage.cache_write_input_tokens
    required = [input_rate, output_rate]
    if usage.cached_input_tokens and cached_rate is None:
        required.append(None)
    if any(rate is None for rate in selected_extras):
        required.append(None)
    if usage.cache_write_input_tokens and not any(
        rate.rate_type == RateType.CACHE_WRITE_TOKEN for rate in extras
    ):
        required.append(None)
    if any(rate.meter not in known_meter_quantities for rate in extras):
        required.append(None)
    complete = all(rate is not None for rate in required)
    applied: list[str] = []
    quantities: dict[str, Decimal] = {}
    amount: Decimal | None = None
    if complete:
        assert input_rate is not None and output_rate is not None
        uncached = usage.input_tokens - usage.cached_input_tokens - usage.cache_write_input_tokens
        amount = _charge(input_rate, uncached) + _charge(output_rate, usage.output_tokens)
        applied.extend([input_rate.rate_id, output_rate.rate_id])
        quantities[input_rate.rate_id] = Decimal(uncached)
        quantities[output_rate.rate_id] = Decimal(usage.output_tokens)
        if cached_rate is not None and usage.cached_input_tokens:
            amount += _charge(cached_rate, usage.cached_input_tokens)
            applied.append(cached_rate.rate_id)
            quantities[cached_rate.rate_id] = Decimal(usage.cached_input_tokens)
        for rate in extras:
            quantity = Decimal(known_meter_quantities[rate.meter])
            amount += _charge(rate, quantity)
            applied.append(rate.rate_id)
            quantities[rate.rate_id] = quantity
    fingerprint = usage_fingerprint(usage)
    status = EvidenceStatus.COMPLETE if complete else EvidenceStatus.PARTIAL
    if actual_billable:
        if usage.access_channel != ModelAccessChannel.API:
            raise ValueError("only an API access channel can create tariff-derived actual cash")
        return CashEvidence(
            charge_id=charge_id,
            amount=amount,
            currency=snapshot.currency,
            classification=(
                CashClassification.PINNED_RATE_BILLABLE_USAGE
                if amount is not None
                else CashClassification.UNAVAILABLE
            ),
            evidence=MeasurementEvidence(
                status=status if amount is not None else EvidenceStatus.UNAVAILABLE,
                source=(
                    EvidenceSource.PRICED_MEASURED_BILLABLE_USAGE
                    if amount is not None
                    else EvidenceSource.UNAVAILABLE
                ),
                trust=TrustLevel.VERIFIED if amount is not None else TrustLevel.UNTRUSTED,
            ),
            rate_snapshot_id=snapshot.snapshot_id if amount is not None else None,
            usage_fingerprint=fingerprint,
            applied_rate_ids=applied,
            applied_meter_quantities=quantities,
        )
    return CounterfactualCashCost(
        amount=amount,
        currency=snapshot.currency,
        rate_snapshot_id=snapshot.snapshot_id or "",
        provider=usage.provider,
        model=usage.model,
        usage_fingerprint=fingerprint,
        applied_rate_ids=applied,
        applied_meter_quantities=quantities,
        status=status,
    )


def subscription_usage_from_tokens(
    usage: ModelTokenUsage,
    snapshot: RateCardSnapshot,
    *,
    resource_pool: str,
    unit: str,
    included_or_paid: SubscriptionCharge = SubscriptionCharge.UNKNOWN,
) -> SubscriptionUsage:
    if usage.evidence.status != EvidenceStatus.COMPLETE:
        return SubscriptionUsage(
            provider=usage.provider,
            resource_pool=resource_pool,
            unit=unit,
            source=MeasurementEvidence(),
            included_or_paid=included_or_paid,
        )
    rates = [rate for rate in snapshot.rates if rate.rate_type == RateType.SUBSCRIPTION_UNIT]
    meters = {
        "input_tokens": usage.input_tokens,
        "cached_input_tokens": usage.cached_input_tokens,
        "cache_write_input_tokens": usage.cache_write_input_tokens,
        "output_tokens": usage.output_tokens,
    }
    if not rates or any(rate.meter not in meters for rate in rates):
        return SubscriptionUsage(
            provider=usage.provider,
            resource_pool=resource_pool,
            unit=unit,
            source=MeasurementEvidence(),
            included_or_paid=included_or_paid,
        )
    consumed = sum((_charge(rate, meters[rate.meter]) for rate in rates), Decimal(0))
    return SubscriptionUsage(
        provider=usage.provider,
        resource_pool=resource_pool,
        unit=unit,
        consumed=consumed,
        source=MeasurementEvidence(
            status=EvidenceStatus.COMPLETE,
            source=EvidenceSource.PINNED_RATE_TABLE,
            trust=TrustLevel.VERIFIED,
        ),
        included_or_paid=included_or_paid,
        rate_snapshot_id=snapshot.snapshot_id,
        usage_fingerprint=usage_fingerprint(usage),
    )


def subscription_model_accounting(
    usage: ModelTokenUsage,
    *,
    resource_pool: str,
    unit: str = "provider_unit",
    consumed: Decimal | None = None,
    usage_evidence: MeasurementEvidence | None = None,
    included_or_paid: SubscriptionCharge = SubscriptionCharge.UNKNOWN,
    confirmed_zero_incremental_cash: bool = False,
) -> ResourceAccounting:
    """Build the subscription ledger without inferring billing state from tokens."""

    subscription = SubscriptionUsage(
        provider=usage.provider,
        resource_pool=resource_pool,
        unit=unit,
        consumed=consumed,
        source=usage_evidence or MeasurementEvidence(),
        included_or_paid=included_or_paid,
        usage_fingerprint=usage_fingerprint(usage),
    )
    cash = CashAccounting()
    if confirmed_zero_incremental_cash:
        cash = CashAccounting(
            status=EvidenceStatus.COMPLETE,
            components=[
                CashEvidence(
                    charge_id=f"included:{resource_pool}:{usage_fingerprint(usage)}",
                    amount=Decimal(0),
                    classification=CashClassification.VERIFIED,
                    evidence=MeasurementEvidence(
                        status=EvidenceStatus.COMPLETE,
                        source=EvidenceSource.CONFIRMED_NO_INCREMENTAL_CHARGE,
                        trust=TrustLevel.VERIFIED,
                    ),
                    usage_fingerprint=usage_fingerprint(usage),
                )
            ],
        )
    return ResourceAccounting(cash=cash, subscription_usage=[subscription], model_usage=[usage])


def aggregate_accounting(
    receipts: Iterable[ExecutionReceipt],
) -> ResourceAccounting:
    """Aggregate every attempt while keeping provider-local pools isolated."""

    items = list(receipts)
    cash_components = [
        component for receipt in items for component in receipt.accounting.cash.components
    ]
    cash_status = EvidenceStatus.COMPLETE
    if not items or any(
        receipt.accounting.cash.status == EvidenceStatus.CONFLICT for receipt in items
    ):
        cash_status = EvidenceStatus.CONFLICT if items else EvidenceStatus.UNAVAILABLE
    elif any(receipt.accounting.cash.status != EvidenceStatus.COMPLETE for receipt in items):
        cash_status = EvidenceStatus.PARTIAL if cash_components else EvidenceStatus.UNAVAILABLE

    grouped: dict[tuple[str, str, str], list[SubscriptionUsage]] = defaultdict(list)
    for receipt in items:
        for usage in receipt.accounting.subscription_usage:
            grouped[(usage.provider, usage.resource_pool, usage.unit)].append(usage)
    subscription: list[SubscriptionUsage] = []
    for (provider, pool, unit), group in sorted(grouped.items()):
        known = [entry.consumed for entry in group if entry.consumed is not None]
        consumed = sum(known, Decimal(0)) if len(known) == len(group) else None
        charges = {entry.included_or_paid for entry in group}
        charge = charges.pop() if len(charges) == 1 else SubscriptionCharge.MIXED
        subscription.append(
            SubscriptionUsage(
                provider=provider,
                resource_pool=pool,
                unit=unit,
                consumed=consumed,
                source=(
                    group[0].source
                    if all(entry.source == group[0].source for entry in group)
                    else MeasurementEvidence(
                        status=EvidenceStatus.PARTIAL,
                        source=EvidenceSource.OPERATOR_REPORT,
                        trust=TrustLevel.OBSERVED,
                    )
                ),
                included_or_paid=charge,
            )
        )

    model_groups: dict[tuple[str, str, ModelAccessChannel], list[ModelTokenUsage]] = defaultdict(
        list
    )
    for receipt in items:
        for model_entry in receipt.accounting.model_usage:
            model_groups[
                (model_entry.provider, model_entry.model, model_entry.access_channel)
            ].append(model_entry)
    model_usage: list[ModelTokenUsage] = []
    for (provider, model, channel), model_group in sorted(model_groups.items()):
        sources = {entry.evidence.model_dump_json() for entry in model_group}
        model_usage.append(
            ModelTokenUsage(
                provider=provider,
                model=model,
                access_channel=channel,
                input_tokens=sum(entry.input_tokens for entry in model_group),
                cached_input_tokens=sum(entry.cached_input_tokens for entry in model_group),
                cache_write_input_tokens=sum(
                    entry.cache_write_input_tokens for entry in model_group
                ),
                output_tokens=sum(entry.output_tokens for entry in model_group),
                reasoning_output_tokens=sum(entry.reasoning_output_tokens for entry in model_group),
                evidence=(
                    model_group[0].evidence
                    if len(sources) == 1
                    else MeasurementEvidence(
                        status=EvidenceStatus.PARTIAL,
                        source=EvidenceSource.OPERATOR_REPORT,
                        trust=TrustLevel.OBSERVED,
                    )
                ),
            )
        )
    footprints = [
        receipt.accounting.tool_footprint
        for receipt in items
        if receipt.accounting.tool_footprint is not None
    ]
    tool_footprint = None
    if footprints:
        from .models import ToolFootprint

        tool_footprint = ToolFootprint(
            schema_bytes=sum(item.schema_bytes for item in footprints),
            schema_approx_tokens=sum(item.schema_approx_tokens for item in footprints),
            raw_result_bytes=sum(item.raw_result_bytes for item in footprints),
            raw_result_approx_tokens=sum(item.raw_result_approx_tokens for item in footprints),
            filtered_result_bytes=sum(item.filtered_result_bytes for item in footprints),
            filtered_result_approx_tokens=sum(
                item.filtered_result_approx_tokens for item in footprints
            ),
            exposed_to_model=any(item.exposed_to_model for item in footprints),
        )
    return ResourceAccounting(
        cash=CashAccounting(status=cash_status, components=cash_components),
        subscription_usage=subscription,
        model_usage=model_usage,
        tool_footprint=tool_footprint,
    )


def mirror_actual_cash(accounting: ResourceAccounting) -> float:
    """Return the legacy numeric mirror; never use it for routing or savings claims."""

    actual = accounting.cash.actual_cash_cost("USD")
    return float(actual) if actual is not None else 0.0
