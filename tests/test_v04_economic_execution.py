from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from aeep.economic import canonical_payload
from aeep.economic.execution import EconomicExecutionResolution, resolve_usage_statement
from aeep.economic.trust import (
    TrustedKeyStatus,
    TrustStore,
    TrustStoreVerifier,
)
from aeep.errors import ConfigurationError
from aeep.market_server import (
    CAPABILITY,
    EXECUTOR_ID,
    ReferenceMarket,
    UsageStatementRequest,
    reference_executor_spec,
)
from aeep.models import (
    ActionFeatures,
    AuthorizationKind,
    BillingTrigger,
    CurrencyAmount,
    EconomicEvidenceLevel,
    ExecutorKind,
    FailureChargePolicy,
    PreparedRouteDecision,
    ProviderExecutionStatus,
    QuoteRequestV2,
    UsageStatement,
)

NOW = datetime(2026, 8, 14, 12, tzinfo=UTC)


def _evidence_chain() -> tuple[
    ReferenceMarket,
    QuoteRequestV2,
    PreparedRouteDecision,
    UsageStatement,
]:
    spec = reference_executor_spec(kind=ExecutorKind.PYTHON)
    market = ReferenceMarket(executor_spec=spec, clock=lambda: NOW)
    request = QuoteRequestV2(
        quote_request_id="request-execution-1",
        action_id="action-execution-1",
        capability=CAPABILITY,
        executor_id=EXECUTOR_ID,
        executor_fingerprint=market.executor_fingerprint,
        action_digest="sha256:" + hashlib.sha256(b"economic execution test").hexdigest(),
        input_features=ActionFeatures(
            input_bytes=14_336,
            input_items=1,
            text_characters=14_336,
            max_depth=1,
            size_bucket="2^14",
        ),
        disclosed_quote_features={"input_bytes": 14_336},
        desired_currency="USD",
        nonce="execution-nonce-0001",
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    quote = market.request_quote(request)
    prepared = PreparedRouteDecision(
        prepared_id="prepared-execution-1",
        action_id=request.action_id,
        action_digest=request.action_digest,
        effective_policy_digest="sha256:" + ("b" * 64),
        selected_executor_id=quote.executor_id,
        selected_executor_fingerprint=quote.executor_fingerprint,
        selected_quote_id=quote.quote_id,
        authorization_kind=AuthorizationKind.SIGNED_QUOTE,
        authorization_id=quote.quote_id,
        quote_ids=(quote.quote_id,),
        maximum_cash_authorization=quote.maximum_amount,
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    statement = market.issue_usage_statement(
        UsageStatementRequest(
            quote_id=quote.quote_id,
            prepared_id=prepared.prepared_id,
            action_id=request.action_id,
            attempt_id="attempt-execution-1",
            execution_status=ProviderExecutionStatus.SUCCESS,
            actual_input_bytes=14_336,
            started_at=NOW - timedelta(milliseconds=10),
            completed_at=NOW,
        )
    )
    return market, request, prepared, statement


def _resign(
    market: ReferenceMarket,
    statement: UsageStatement,
    **updates: Any,
) -> UsageStatement:
    fields = statement.model_dump(mode="python", exclude={"signature"})
    fields.update(updates)
    fields["signature"] = market.signer.sign(canonical_payload(fields))
    return UsageStatement.model_validate(fields)


def _verifier(market: ReferenceMarket) -> TrustStoreVerifier:
    return TrustStoreVerifier(TrustStore((market.trusted_key,)), clock=lambda: NOW)


def _resolve(
    market: ReferenceMarket,
    request: QuoteRequestV2,
    prepared: PreparedRouteDecision,
    statement: UsageStatement,
    *,
    verifier: TrustStoreVerifier | None = None,
) -> EconomicExecutionResolution:
    quote = market.request_quote(request)
    return resolve_usage_statement(
        statement,
        quote=quote,
        prepared=prepared,
        action_id=request.action_id,
        attempt_id="attempt-execution-1",
        charge_id="charge-execution-1",
        verifier=verifier or _verifier(market),
        result_accepted=True,
    )


def test_verified_usage_resolves_structured_billable_amount() -> None:
    market, request, prepared, statement = _evidence_chain()

    result = _resolve(market, request, prepared, statement)

    assert result.usage_statement == statement
    assert result.billable_amount == CurrencyAmount(amount=Decimal("0.0038"), currency="USD")
    assert result.dispute is None
    assert result.settlement_evidence.evidence_level is EconomicEvidenceLevel.SIGNED_USAGE_STATEMENT
    assert result.settlement_evidence.usage_statement_id == statement.usage_statement_id
    assert result.settlement_evidence.provider_calculated_amount == result.billable_amount


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("quote_id", "quote-wrong", "quote_id"),
        ("prepared_id", "prepared-wrong", "prepared_id"),
        ("action_id", "action-wrong", "action_id"),
        ("attempt_id", "attempt-wrong", "attempt_id"),
        ("provider_id", "provider.wrong", "provider_id"),
        ("executor_id", "executor-wrong", "executor_id"),
        ("executor_fingerprint", "sha256:" + ("c" * 64), "executor_fingerprint"),
    ],
)
def test_usage_statement_exact_bindings_are_enforced(
    field: str,
    value: str,
    message: str,
) -> None:
    market, request, prepared, statement = _evidence_chain()
    altered = _resign(market, statement, **{field: value})

    with pytest.raises(ConfigurationError, match=message):
        _resolve(market, request, prepared, altered)


def test_provider_claim_above_signed_maximum_opens_dispute_without_billable_amount() -> None:
    market, request, prepared, statement = _evidence_chain()
    quote = market.request_quote(request)
    claimed = CurrencyAmount(
        amount=quote.maximum_amount.amount + Decimal("0.0001"),
        currency=quote.maximum_amount.currency,
    )
    altered = _resign(market, statement, provider_calculated_amount=claimed)

    result = _resolve(market, request, prepared, altered)

    assert result.billable_amount is None
    assert result.dispute is not None
    assert result.dispute.quoted_maximum == quote.maximum_amount
    assert result.dispute.provider_claimed_amount == claimed
    assert result.settlement_evidence.provider_calculated_amount == claimed


@pytest.mark.parametrize(
    "prepared_update",
    [
        {"action_id": "another-action"},
        {"action_digest": "sha256:" + ("d" * 64)},
        {"maximum_cash_authorization": CurrencyAmount(amount=Decimal("0.0049"), currency="USD")},
    ],
)
def test_prepared_action_and_maximum_must_match_quote(
    prepared_update: dict[str, object],
) -> None:
    market, request, prepared, statement = _evidence_chain()
    altered = prepared.model_copy(update=prepared_update)

    with pytest.raises(ConfigurationError, match=r"prepared (action|maximum authorization)"):
        _resolve(market, request, altered, statement)


def test_indeterminate_usage_remains_unknown_instead_of_becoming_zero() -> None:
    market, request, prepared, statement = _evidence_chain()
    altered = _resign(
        market,
        statement,
        execution_status=ProviderExecutionStatus.INDETERMINATE,
        provider_calculated_amount=None,
    )

    result = _resolve(market, request, prepared, altered)

    assert result.billable_amount is None
    assert result.dispute is None
    assert result.settlement_evidence.provider_calculated_amount is None


@pytest.mark.parametrize(
    ("failure_policy", "expected"),
    [
        (FailureChargePolicy.NO_CHARGE, Decimal("0")),
        (FailureChargePolicy.CHARGE_MAXIMUM, Decimal("0.0050")),
    ],
)
def test_provider_claim_is_not_mislabeled_as_policy_derived_failure_charge(
    failure_policy: FailureChargePolicy,
    expected: Decimal,
) -> None:
    market, request, prepared, statement = _evidence_chain()
    quote = market.request_quote(request).model_copy(
        update={"failure_charge_policy": failure_policy}
    )
    failed = _resign(
        market,
        statement,
        execution_status=ProviderExecutionStatus.FAILED,
    )

    result = resolve_usage_statement(
        failed,
        quote=quote,
        prepared=prepared,
        action_id=request.action_id,
        attempt_id="attempt-execution-1",
        charge_id="charge-execution-1",
        verifier=_verifier(market),
        result_accepted=False,
    )

    assert result.billable_amount == CurrencyAmount(amount=expected, currency="USD")
    assert result.settlement_evidence.provider_calculated_amount is None


def test_provider_start_without_explicit_start_time_remains_unknown() -> None:
    market, request, prepared, statement = _evidence_chain()
    quote = market.request_quote(request).model_copy(
        update={"billing_trigger": BillingTrigger.ON_PROVIDER_START}
    )
    without_start = _resign(market, statement, started_at=None)

    result = resolve_usage_statement(
        without_start,
        quote=quote,
        prepared=prepared,
        action_id=request.action_id,
        attempt_id="attempt-execution-1",
        charge_id="charge-execution-1",
        verifier=_verifier(market),
        result_accepted=True,
    )

    assert result.billable_amount is None
    assert result.settlement_evidence.provider_calculated_amount is None


def test_usage_signature_tampering_is_rejected() -> None:
    market, request, prepared, statement = _evidence_chain()
    tampered = statement.model_copy(
        update={
            "provider_calculated_amount": CurrencyAmount(amount=Decimal(0), currency="USD")
        }
    )

    with pytest.raises(ConfigurationError, match="signature verification failed"):
        _resolve(market, request, prepared, tampered)


def test_historical_usage_signed_before_key_revocation_remains_verifiable() -> None:
    market, request, prepared, statement = _evidence_chain()
    revoked_key = market.trusted_key.model_copy(
        update={
            "status": TrustedKeyStatus.REVOKED,
            "revoked_at": NOW + timedelta(seconds=1),
        }
    )
    verifier = TrustStoreVerifier(
        TrustStore((revoked_key,)),
        clock=lambda: NOW + timedelta(days=1),
    )

    result = _resolve(market, request, prepared, statement, verifier=verifier)

    assert result.billable_amount == statement.provider_calculated_amount


def test_provider_usage_currency_must_match_quote() -> None:
    market, request, prepared, statement = _evidence_chain()
    altered = _resign(
        market,
        statement,
        provider_calculated_amount=CurrencyAmount(amount=Decimal("0.0038"), currency="EUR"),
    )

    with pytest.raises(ConfigurationError, match="currency does not match quote"):
        _resolve(market, request, prepared, altered)
