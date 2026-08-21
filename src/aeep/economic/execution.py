"""Verify provider usage and resolve signed quote billing without overcapture."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ..errors import ConfigurationError
from ..models import (
    AuthorizationKind,
    BillingTrigger,
    BoundedQuote,
    CurrencyAmount,
    EconomicEvidenceLevel,
    PreparedRouteDecision,
    PricingDispute,
    SettlementEvidence,
    UsageStatement,
)
from .canonical import canonical_digest, canonical_payload
from .trust import TrustStoreVerifier


@dataclass(frozen=True, slots=True)
class EconomicExecutionResolution:
    """Verified provider assertion plus its safe local billing resolution."""

    usage_statement: UsageStatement
    settlement_evidence: SettlementEvidence
    billable_amount: CurrencyAmount | None
    dispute: PricingDispute | None = None


def resolve_usage_statement(
    statement: UsageStatement,
    *,
    quote: BoundedQuote,
    prepared: PreparedRouteDecision,
    action_id: str,
    attempt_id: str,
    charge_id: str,
    verifier: TrustStoreVerifier,
    result_accepted: bool | None,
    attempt_number: int = 1,
) -> EconomicExecutionResolution:
    """Verify exact bindings, then apply only the quote's structured billing policy."""

    if prepared.authorization_kind is not AuthorizationKind.SIGNED_QUOTE:
        raise ConfigurationError("provider usage requires a signed-quote authorization")
    expected = {
        "quote_id": quote.quote_id,
        "prepared_id": prepared.prepared_id,
        "action_id": action_id,
        "attempt_id": attempt_id,
        "provider_id": quote.provider_id,
        "executor_id": quote.executor_id,
        "executor_fingerprint": quote.executor_fingerprint,
    }
    for field, value in expected.items():
        if getattr(statement, field) != value:
            raise ConfigurationError(f"usage statement {field} does not match execution")
    if prepared.authorization_id != quote.quote_id or prepared.selected_quote_id != quote.quote_id:
        raise ConfigurationError("prepared decision does not authorize this quote")
    if prepared.action_id != action_id or prepared.action_digest != quote.action_digest:
        raise ConfigurationError("prepared action does not match usage statement and quote")
    if (
        prepared.selected_executor_id != quote.executor_id
        or prepared.selected_executor_fingerprint != quote.executor_fingerprint
    ):
        raise ConfigurationError("prepared executor does not match usage statement")
    if prepared.maximum_cash_authorization != quote.maximum_amount:
        raise ConfigurationError("prepared maximum authorization does not match quote")

    verification = verifier.verify(
        canonical_payload(statement),
        statement.signature,
        expected_provider_id=quote.provider_id,
        capability=quote.capability,
        signed_at=statement.issued_at,
        allow_historical=True,
    )
    if not verification.valid:
        raise ConfigurationError(f"usage statement verification failed: {verification.reason}")

    provider_amount = statement.provider_calculated_amount
    if provider_amount is not None and provider_amount.currency != quote.maximum_amount.currency:
        raise ConfigurationError("provider usage amount currency does not match quote")
    digest = canonical_digest(statement)
    if provider_amount is not None and provider_amount.amount > quote.maximum_amount.amount:
        evidence = SettlementEvidence(
            charge_id=charge_id,
            evidence_level=EconomicEvidenceLevel.SIGNED_USAGE_STATEMENT,
            usage_statement_id=statement.usage_statement_id,
            evidence_digest=digest,
            provider_calculated_amount=provider_amount,
        )
        identity = hashlib.sha256(
            f"{quote.quote_id}\0{statement.usage_statement_id}".encode()
        ).hexdigest()
        dispute = PricingDispute(
            dispute_id=f"dispute_{identity}",
            prepared_id=prepared.prepared_id,
            quote_id=quote.quote_id,
            usage_statement_id=statement.usage_statement_id,
            provider_id=quote.provider_id,
            quoted_maximum=quote.maximum_amount,
            provider_claimed_amount=provider_amount,
            reason="provider usage statement exceeds the signed quote maximum",
            created_at=statement.issued_at,
        )
        return EconomicExecutionResolution(statement, evidence, None, dispute)

    # Imported lazily because payments persists through the store, while the store
    # imports canonical economic JSON.  Keeping the dependency at the operation
    # boundary avoids making ``aeep.economic`` participate in that import cycle.
    from ..payments import billable_amount_for_execution

    provider_started = statement.started_at is not None
    billable = (
        None
        if quote.billing_trigger is BillingTrigger.ON_PROVIDER_START
        and not provider_started
        else billable_amount_for_execution(
            quote,
            execution_status=statement.execution_status,
            provider_started=provider_started,
            result_accepted=result_accepted,
            actual_usage_amount=provider_amount,
            attempt_number=attempt_number,
        )
    )
    evidence = SettlementEvidence(
        charge_id=charge_id,
        evidence_level=EconomicEvidenceLevel.SIGNED_USAGE_STATEMENT,
        usage_statement_id=statement.usage_statement_id,
        evidence_digest=digest,
        provider_calculated_amount=(provider_amount if provider_amount == billable else None),
    )
    return EconomicExecutionResolution(statement, evidence, billable)
