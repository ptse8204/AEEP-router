from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from test_v04_prepared_routing import (
    CAPABILITY,
    PROVIDER,
    QUOTE_HOST,
    UNSIGNED,
    MutableClock,
    SignedQuoteProvider,
    _manifest,
    _request,
    _route,
    _router,
)

from aeep.economic.canonical import canonical_payload
from aeep.economic.prepared import executor_fingerprint
from aeep.economic.signing import Ed25519Signer
from aeep.economic.trust import TrustedProviderKey, TrustStore, TrustStoreVerifier
from aeep.errors import ApprovalRequired, ConfigurationError, NoRouteError
from aeep.executors.base import BaseExecutor, ExecutionContext
from aeep.models import (
    ActionConstraints,
    AgentBudget,
    AuthorizationPolicy,
    CurrencyAmount,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    MeterQuantity,
    PaymentReservationState,
    PaymentReservationV2,
    PolicyConfig,
    PreparedDecisionState,
    ProviderExecutionStatus,
    RawExecution,
    ResourceVector,
    SettlementEvidence,
    SideEffect,
    UsageStatement,
)
from aeep.payments import PrepaidBalanceAdapterV2
from aeep.router import Router


class SignedUsageExecutor(BaseExecutor):
    def __init__(
        self,
        signer: Ed25519Signer,
        clock: MutableClock,
        *,
        amount: str = "0.0038",
        status: ExecutionStatus = ExecutionStatus.SUCCESS,
    ) -> None:
        self.signer = signer
        self.clock = clock
        self.amount = amount
        self.status = status
        self.calls: list[ExecutionContext] = []

    async def execute(self, context: ExecutionContext) -> RawExecution:
        self.calls.append(context)
        if self.status is not ExecutionStatus.SUCCESS:
            return RawExecution(
                status=self.status,
                error_type="TimeoutError",
                error_message="provider outcome is unknown",
                resources=ResourceVector(latency_ms=1),
            )
        assert context.prepared_id is not None
        assert context.quote_id is not None
        assert context.attempt_id is not None
        text = str(context.request.input["text"])
        statement = UsageStatement(
            usage_statement_id=f"usage-{context.attempt_id}",
            quote_id=context.quote_id,
            prepared_id=context.prepared_id,
            action_id=context.request.action_id,
            attempt_id=context.attempt_id,
            provider_id=PROVIDER,
            executor_id=context.spec.id,
            executor_fingerprint=executor_fingerprint(context.spec),
            execution_status=ProviderExecutionStatus.SUCCESS,
            meters=(
                MeterQuantity(
                    meter=f"{PROVIDER}.input_bytes",
                    unit="byte",
                    quantity=len(text.encode()),
                ),
            ),
            provider_calculated_amount=CurrencyAmount(amount=self.amount, currency="USD"),
            started_at=self.clock(),
            completed_at=self.clock(),
            issued_at=self.clock(),
            signature=UNSIGNED,
        )
        statement = statement.model_copy(
            update={"signature": self.signer.sign(canonical_payload(statement))}
        )
        return RawExecution(
            status=ExecutionStatus.SUCCESS,
            output={
                "output": {
                    "characters": len(text),
                    "words": len(text.split()),
                    "lines": text.count("\n") + int(bool(text)),
                },
                "usage_statement": statement.model_dump(mode="json"),
            },
            resources=ResourceVector(latency_ms=1),
        )


class FailOncePrepaidAdapter(PrepaidBalanceAdapterV2):
    def __init__(self, clock: MutableClock) -> None:
        super().__init__(CurrencyAmount(amount="1", currency="USD"), clock=clock)
        self.settlement_attempts = 0

    async def _settle_external(
        self,
        reservation: PaymentReservationV2,
        actual_amount: CurrencyAmount,
        evidence: SettlementEvidence,
        idempotency_key: str,
    ) -> Any:
        del reservation, actual_amount, evidence, idempotency_key
        self.settlement_attempts += 1
        if self.settlement_attempts == 1:
            raise RuntimeError("simulated crash window")
        return None


class AnyCapabilityQuoteProvider(SignedQuoteProvider):
    async def get_offers(
        self,
        capability: str,
        executor_ids: Sequence[str],
    ) -> tuple[()]:
        del capability
        self.offer_requests.extend(executor_ids)
        return ()


def _execution_router(
    route: ExecutorSpec,
    provider: SignedQuoteProvider,
    signer: Ed25519Signer,
    clock: MutableClock,
    *,
    adapter: PrepaidBalanceAdapterV2 | None = None,
    capabilities: tuple[str, ...] = (CAPABILITY,),
    policies: Mapping[str, PolicyConfig] | None = None,
) -> Router:
    manifest = _manifest(route)
    manifest.policies.update(policies or {})
    manifest.budget = AgentBudget(
        daily_marketplace_limit_usd=1,
        max_per_action_usd=1,
        prepaid_balance_usd=1,
        authorization=AuthorizationPolicy(
            auto_approve_under_usd=1,
            financial_actions_require_human=False,
        ),
    )
    manifest.economic_evidence.payment.adapter = "prepaid"
    key = TrustedProviderKey(
        provider_id=PROVIDER,
        key_id=signer.key_id,
        public_key=signer.public_key_base64url(),
        valid_from=clock() - timedelta(days=1),
        valid_until=clock() + timedelta(days=1),
        allowed_capabilities=capabilities,
        allowed_quote_hosts=(QUOTE_HOST,),
    )
    return Router(
        manifest,
        quote_provider=provider,
        economic_verifier=TrustStoreVerifier(TrustStore((key,)), clock=clock),
        payment_adapter_v2=adapter
        or PrepaidBalanceAdapterV2(
            CurrencyAmount(amount="1", currency="USD"),
            clock=clock,
        ),
        clock=clock,
    )


@pytest.mark.asyncio
async def test_acceptance_a_dynamic_quote_changes_route_selection() -> None:
    clock = MutableClock()
    signer = _signer()
    provider = SignedQuoteProvider(
        signer,
        clock,
        amounts={"remote.dynamic": ("0.0038", "0.0100")},
    )
    router = _router(
        _manifest(
            _route("local.free", latency_ms=500, cash="0"),
            _route("remote.dynamic", latency_ms=1, cash="0.001", provider=True),
        ),
        provider,
        signer,
        clock,
    )
    secret = "PRIVATE ACTION PAYLOAD 9c07a2"
    request = _request(
        input={"text": secret},
        constraints=ActionConstraints(max_cost_usd=0.005),
    )
    try:
        assert router.route(request).selected_executor_id == "remote.dynamic"

        prepared = await router.prepare_route(request)

        assert prepared.selected_executor_id == "local.free"
        rejection = next(
            item for item in prepared.rejected_candidates if item.executor_id == "remote.dynamic"
        )
        assert "quote" in " ".join(rejection.reasons).lower()
        failure = next(
            item for item in prepared.quote_failures if item.executor_id == "remote.dynamic"
        )
        assert "maximum acceptable" in failure.reason
        assert provider.requests[0].maximum_acceptable_amount == CurrencyAmount(
            amount=Decimal("0.005"), currency="USD"
        )
        assert secret not in provider.requests[0].model_dump_json()
        assert router.store.get_prepared_decision(prepared.prepared_id) == prepared
        assert router.store.list_payment_reservations_v2() == []
        assert all(
            decision.action.input == {"__aeep_redacted__": True}
            for decision in router.store.list_decisions()
        )
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_acceptance_c_unknown_cost_is_not_free() -> None:
    clock = MutableClock()
    signer = _signer()
    provider = SignedQuoteProvider(signer, clock, failing={"remote.unknown"})
    router = _router(
        _manifest(_route("remote.unknown", latency_ms=1, cash=None, provider=True)),
        provider,
        signer,
        clock,
    )
    try:
        prepared = await router.prepare_route(
            _request(constraints=ActionConstraints(max_cost_usd=1))
        )

        assert not prepared.feasible
        assert prepared.maximum_cash_authorization is None
        assert prepared.candidate_rankings == ()
        assert prepared.expected_accounting.cash.actual_cash_cost("USD") is None
        assert "not treated as zero" in " ".join(
            reason
            for candidate in prepared.rejected_candidates
            for reason in candidate.reasons
        )
        assert router.store.list_bounded_quotes() == []
        assert router.store.list_payment_reservations_v2() == []
    finally:
        await router.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("maximum_amount", CurrencyAmount(amount="0.0060", currency="USD")),
        ("action_digest", f"sha256:{'8' * 64}"),
        ("executor_fingerprint", f"sha256:{'9' * 64}"),
    ],
)
async def test_acceptance_d_quote_tampering_creates_no_reservation(
    field: str,
    value: object,
) -> None:
    clock = MutableClock()
    signer = _signer()
    provider = SignedQuoteProvider(
        signer,
        clock,
        amounts={"remote.dynamic": ("0.0038", "0.0050")},
        tamper={"remote.dynamic": {field: value}},
    )
    router = _router(
        _manifest(_route("remote.dynamic", latency_ms=1, cash="0.001", provider=True)),
        provider,
        signer,
        clock,
    )
    try:
        prepared = await router.prepare_route(_request())

        assert not prepared.feasible
        assert prepared.quote_ids == ()
        assert any(
            failure.executor_id == "remote.dynamic"
            and failure.code == "BINDING"
            for failure in prepared.quote_failures
        )
        assert router.store.list_bounded_quotes() == []
        assert router.store.list_payment_reservations_v2() == []
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_acceptance_b_partial_capture_releases_exact_remainder() -> None:
    clock = MutableClock()
    signer = _signer()
    provider = SignedQuoteProvider(
        signer,
        clock,
        amounts={"remote.dynamic": ("0.0038", "0.0050")},
    )
    router = _execution_router(
        _route("remote.dynamic", latency_ms=1, cash="0.001", provider=True),
        provider,
        signer,
        clock,
    )
    executor = SignedUsageExecutor(signer, clock)
    router._executors[ExecutorKind.PYTHON] = executor
    secret = "PRIVATE SETTLEMENT INPUT 5385a4"
    try:
        prepared = await router.prepare_route(_request(input={"text": secret}))
        outcome = await router.execute_prepared(
            prepared.prepared_id,
            approved_side_effect=SideEffect.READ,
            payment_approved=True,
        )

        assert outcome.ok
        assert outcome.output == {"characters": len(secret), "words": 4, "lines": 1}
        assert len(executor.calls) == 1
        usages = router.store.list_usage_statements(prepared_id=prepared.prepared_id)
        reservations = [
            item
            for item in router.store.list_payment_reservations_v2()
            if item.prepared_id == prepared.prepared_id
        ]
        settlements = router.store.list_settlement_receipts(prepared_id=prepared.prepared_id)
        assert len(usages) == len(reservations) == len(settlements) == 1
        usage, reservation, settlement = usages[0], reservations[0], settlements[0]
        assert usage.quote_id == prepared.selected_quote_id
        assert usage.attempt_id == reservation.attempt_id == settlement.attempt_id
        assert settlement.quote_id == reservation.quote_id == prepared.selected_quote_id
        assert settlement.reserved_amount.amount == Decimal("0.0050")
        assert settlement.captured_amount.amount == Decimal("0.0038")
        assert settlement.released_amount.amount == Decimal("0.0012")
        assert settlement.captured_amount.amount <= settlement.reserved_amount.amount
        assert reservation.state is PaymentReservationState.SETTLED
        assert router.store.get_prepared_decision(prepared.prepared_id).state is (
            PreparedDecisionState.SETTLED
        )
        assert {
            (transition.from_state, transition.to_state)
            for transition in router.store.list_prepared_transitions(prepared.prepared_id)
        } == {
            (PreparedDecisionState.PREPARED, PreparedDecisionState.RESERVED),
            (PreparedDecisionState.RESERVED, PreparedDecisionState.INVOKING),
            (PreparedDecisionState.INVOKING, PreparedDecisionState.AWAITING_USAGE),
            (PreparedDecisionState.AWAITING_USAGE, PreparedDecisionState.SETTLING),
            (PreparedDecisionState.SETTLING, PreparedDecisionState.SETTLED),
        }
        assert outcome.receipts[0].accounting.cash.actual_cash_cost("USD") == Decimal(
            "0.0038"
        )
        persisted = " ".join(
            row[0]
            for table in (
                "quote_requests_v2",
                "bounded_quotes",
                "prepared_route_decisions",
                "payment_reservations_v2",
                "usage_statements",
                "settlement_receipts",
            )
            for row in router.store._connection.execute(f"SELECT payload_json FROM {table}")
        )
        assert secret not in persisted
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_acceptance_e_route_drift_rejects_before_reservation() -> None:
    clock = MutableClock()
    signer = _signer()
    provider = SignedQuoteProvider(
        signer,
        clock,
        amounts={"remote.dynamic": ("0.0038", "0.0050")},
    )
    router = _execution_router(
        _route("remote.dynamic", latency_ms=1, cash="0.001", provider=True),
        provider,
        signer,
        clock,
    )
    executor = SignedUsageExecutor(signer, clock)
    router._executors[ExecutorKind.PYTHON] = executor
    try:
        prepared = await router.prepare_route(_request())
        router.registry.get("remote.dynamic").config["callable"] = (
            "aeep.examples.tools:always_fail"
        )

        with pytest.raises((ConfigurationError, NoRouteError), match="fingerprint"):
            await router.execute_prepared(
                prepared.prepared_id,
                payment_approved=True,
            )

        assert executor.calls == []
        assert router.store.list_payment_reservations_v2() == []
        assert router.store.get_prepared_decision(prepared.prepared_id).state is (
            PreparedDecisionState.PREPARED
        )
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_acceptance_f_recovery_settles_without_reexecution() -> None:
    clock = MutableClock()
    signer = _signer()
    provider = SignedQuoteProvider(
        signer,
        clock,
        amounts={"remote.dynamic": ("0.0038", "0.0050")},
    )
    adapter = FailOncePrepaidAdapter(clock)
    router = _execution_router(
        _route("remote.dynamic", latency_ms=1, cash="0.001", provider=True),
        provider,
        signer,
        clock,
        adapter=adapter,
    )
    executor = SignedUsageExecutor(signer, clock)
    router._executors[ExecutorKind.PYTHON] = executor
    try:
        prepared = await router.prepare_route(_request())
        with pytest.raises(RuntimeError, match="crash window"):
            await router.execute_prepared(
                prepared.prepared_id,
                payment_approved=True,
            )

        assert len(executor.calls) == 1
        assert len(router.store.list_usage_statements(prepared_id=prepared.prepared_id)) == 1
        assert router.store.list_settlement_receipts(prepared_id=prepared.prepared_id) == []
        assert router.store.get_prepared_decision(prepared.prepared_id).state is (
            PreparedDecisionState.INDETERMINATE
        )

        recovery = await router.economic_recover()

        assert recovery["settled"] == 1
        assert len(executor.calls) == 1
        assert adapter.settlement_attempts == 2
        assert len(router.store.list_settlement_receipts(prepared_id=prepared.prepared_id)) == 1
        assert router.store.get_prepared_decision(prepared.prepared_id).state is (
            PreparedDecisionState.SETTLED
        )
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_acceptance_g_payment_approval_cannot_grant_write_approval() -> None:
    capability = "job.application.submit@1"
    clock = MutableClock()
    signer = _signer()
    provider = AnyCapabilityQuoteProvider(
        signer,
        clock,
        amounts={"job.submit": ("0.0038", "0.0050")},
    )
    route = _route("job.submit", latency_ms=1, cash="0.001", provider=True)
    route.capability = capability
    route.side_effect = SideEffect.WRITE
    route.idempotent = False
    policy = PolicyConfig(
        name="write",
        constraints=ActionConstraints(max_side_effect=SideEffect.WRITE),
    )
    router = _execution_router(
        route,
        provider,
        signer,
        clock,
        capabilities=(capability,),
        policies={"write": policy},
    )
    executor = SignedUsageExecutor(signer, clock, status=ExecutionStatus.TIMEOUT)
    router._executors[ExecutorKind.PYTHON] = executor
    request = _request(
        capability=capability,
        policy="write",
        constraints=ActionConstraints(max_side_effect=SideEffect.WRITE),
    )
    try:
        prepared = await router.prepare_route(request)
        assert prepared.feasible

        with pytest.raises(ApprovalRequired):
            await router.execute_prepared(
                prepared.prepared_id,
                approved_side_effect=SideEffect.READ,
                payment_approved=True,
                human_approved=True,
            )

        assert executor.calls == []
        assert router.store.list_payment_reservations_v2() == []
        assert router.store.get_prepared_decision(prepared.prepared_id).state is (
            PreparedDecisionState.PREPARED
        )

        outcome = await router.execute_prepared(
            prepared.prepared_id,
            approved_side_effect=SideEffect.WRITE,
            payment_approved=True,
            human_approved=True,
        )

        assert not outcome.ok
        assert outcome.status is ExecutionStatus.TIMEOUT
        assert len(executor.calls) == 1
        assert router.store.list_settlement_receipts(prepared_id=prepared.prepared_id) == []
        assert router.store.get_prepared_decision(prepared.prepared_id).state is (
            PreparedDecisionState.INDETERMINATE
        )
        recovery = await router.economic_recover()
        assert recovery["unresolved"] == 1
        assert len(executor.calls) == 1
    finally:
        await router.close()


def _signer() -> Ed25519Signer:
    return Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="provider-key")
