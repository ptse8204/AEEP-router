"""Run AEEP's deterministic local economic-evidence proof campaign."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import httpx

from aeep.benchmarking import (
    BenchmarkCondition,
    BenchmarkSplit,
    EconomicBenchmarkRouteType,
    EconomicBenchmarkTrial,
    EconomicProofCampaignReport,
    EconomicWorkflowProofTrial,
    finalize_economic_proof,
    format_economic_proof_report,
)
from aeep.economic.prepared import action_digest
from aeep.economic.trust import TrustStore, TrustStoreVerifier
from aeep.estimator import action_features
from aeep.market_server import (
    CAPABILITY,
    ReferenceEconomicExecutor,
    ReferenceMarket,
    ReferenceQuoteProvider,
    reference_executor_spec,
    text_statistics,
)
from aeep.models import (
    ActionRequest,
    AgentBudget,
    AuthorizationPolicy,
    CashEstimate,
    CurrencyAmount,
    EconomicEvidenceConfig,
    EconomicEvidenceLevel,
    EvidenceSource,
    EvidenceStatus,
    ExecutorKind,
    ExecutorSpec,
    Locality,
    Manifest,
    MeasurementEvidence,
    PaymentReservationV2,
    ResourceVector,
    RouteEstimate,
    SettlementEvidence,
    SettlementReceipt,
    SideEffect,
    TrustLevel,
)
from aeep.payments import PrepaidBalanceAdapterV2
from aeep.policy import builtin_policies, merge_constraints
from aeep.router import Router
from aeep.workflow import (
    WorkflowBudget,
    WorkflowInputBinding,
    WorkflowOutputProjection,
    WorkflowRequest,
    WorkflowStatus,
    WorkflowStep,
)

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CLI_ROUTE = HERE / "text_statistics_cli.py"
MCP_ROUTE = ROOT / "examples" / "mcp" / "text_stats_server.py"
GENERATED_AT = datetime(2026, 8, 14, 12, tzinfo=UTC)
SETTLEMENT_CURRENCY = "USD"
WORKFLOW_CAPABILITY = "text.identity@1"
_TIMING_QUANTUM = Decimal("0.000001")
_INPUT_BYTES = 14_336
_REQUIRED_ECONOMIC_GATES = {"settlement-oracle"}


def _clock() -> datetime:
    return GENERATED_AT


def _money(value: Decimal | str | int) -> CurrencyAmount:
    return CurrencyAmount(amount=Decimal(value), currency=SETTLEMENT_CURRENCY)


def _milliseconds(started_ns: int) -> Decimal:
    value = Decimal(time.perf_counter_ns() - started_ns) / Decimal(1_000_000)
    rounded = value.quantize(_TIMING_QUANTUM, rounding=ROUND_HALF_UP)
    return Decimal(0) if rounded == 0 else rounded


def _rounded(value: Decimal) -> Decimal:
    rounded = value.quantize(_TIMING_QUANTUM, rounding=ROUND_HALF_UP)
    return Decimal(0) if rounded == 0 else rounded


def _text() -> str:
    unit = "AEEP economic evidence "
    return (unit * ((_INPUT_BYTES // len(unit)) + 1))[:_INPUT_BYTES]


def _split(repetition: int, repetitions: int) -> BenchmarkSplit:
    if repetition == repetitions - 1:
        return BenchmarkSplit.HOLDOUT
    qualification_end = max(1, repetitions // 3)
    training_end = max(qualification_end + 1, (repetitions * 2) // 3)
    if repetition < qualification_end:
        return BenchmarkSplit.QUALIFICATION
    if repetition < training_end:
        return BenchmarkSplit.TRAINING
    return BenchmarkSplit.HOLDOUT


def _identity(
    route_id: str,
    condition: BenchmarkCondition,
    split: BenchmarkSplit,
    repetition: int,
) -> str:
    return f"{condition.value}-{split.value}-{repetition:02d}-{route_id}"


def _baseline_trial(
    *,
    route_id: str,
    route_type: EconomicBenchmarkRouteType,
    condition: BenchmarkCondition,
    split: BenchmarkSplit,
    repetition: int,
    elapsed_ms: Decimal,
    task_valid: bool,
    confirmed_free: bool,
    network_bytes: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    model_usage_complete: bool = True,
    synthetic_usage: bool = False,
) -> EconomicBenchmarkTrial:
    amount = _money(0) if confirmed_free else None
    return EconomicBenchmarkTrial(
        trial_id=_identity(route_id, condition, split, repetition),
        case_id=f"text-statistics-{split.value}",
        route_id=route_id,
        route_type=route_type,
        condition=condition,
        split=split,
        repetition=repetition,
        task_valid=task_valid,
        expected_cash=amount,
        maximum_cash=amount,
        cash_evidence_level=(
            EconomicEvidenceLevel.OPERATOR_ATTESTED
            if confirmed_free
            else EconomicEvidenceLevel.UNKNOWN
        ),
        preparation_latency_ms=Decimal(0),
        quote_latency_ms=Decimal(0),
        execution_latency_ms=elapsed_ms,
        settlement_latency_ms=Decimal(0),
        total_wall_time_ms=elapsed_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model_usage_complete=model_usage_complete,
        local_resources_complete=False,
        synthetic_usage=synthetic_usage,
        network_bytes=network_bytes,
    )


def _run_local_python(
    text: str,
    *,
    condition: BenchmarkCondition,
    split: BenchmarkSplit,
    repetition: int,
) -> EconomicBenchmarkTrial:
    started = time.perf_counter_ns()
    output = text_statistics(text)
    elapsed = _milliseconds(started)
    return _baseline_trial(
        route_id="local-python",
        route_type=EconomicBenchmarkRouteType.LOCAL_PYTHON,
        condition=condition,
        split=split,
        repetition=repetition,
        elapsed_ms=elapsed,
        task_valid=output == text_statistics(text),
        confirmed_free=True,
    )


def _run_local_cli(
    text: str,
    *,
    condition: BenchmarkCondition,
    split: BenchmarkSplit,
    repetition: int,
) -> EconomicBenchmarkTrial:
    encoded = json.dumps({"text": text}, separators=(",", ":"))
    started = time.perf_counter_ns()
    process = subprocess.run(
        [sys.executable, str(CLI_ROUTE)],
        input=encoded,
        capture_output=True,
        check=True,
        text=True,
        timeout=5,
        cwd=ROOT,
    )
    elapsed = _milliseconds(started)
    output = json.loads(process.stdout)
    return _baseline_trial(
        route_id="local-cli",
        route_type=EconomicBenchmarkRouteType.LOCAL_CLI,
        condition=condition,
        split=split,
        repetition=repetition,
        elapsed_ms=elapsed,
        task_valid=output == text_statistics(text),
        confirmed_free=True,
    )


def _http_handler(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content)
    text = payload.get("text") if isinstance(payload, dict) else None
    if not isinstance(text, str):
        return httpx.Response(400, json={"error": "text must be a string"})
    return httpx.Response(200, json={"output": text_statistics(text)})


def _run_direct_http(
    text: str,
    *,
    condition: BenchmarkCondition,
    split: BenchmarkSplit,
    repetition: int,
    client: httpx.Client | None = None,
) -> EconomicBenchmarkTrial:
    owned = client is None
    active = client or httpx.Client(
        transport=httpx.MockTransport(_http_handler),
        base_url="https://local.reference.invalid",
        trust_env=False,
    )
    request_bytes = len(json.dumps({"text": text}, separators=(",", ":")).encode())
    started = time.perf_counter_ns()
    response = active.post("/statistics", json={"text": text})
    response.raise_for_status()
    elapsed = _milliseconds(started)
    output = response.json()["output"]
    network_bytes = request_bytes + len(response.content)
    if owned:
        active.close()
    return _baseline_trial(
        route_id="direct-http-mock",
        route_type=EconomicBenchmarkRouteType.DIRECT_HTTP,
        condition=condition,
        split=split,
        repetition=repetition,
        elapsed_ms=elapsed,
        task_valid=output == text_statistics(text),
        confirmed_free=False,
        network_bytes=network_bytes,
    )


def _run_local_mcp(
    text: str,
    *,
    condition: BenchmarkCondition,
    split: BenchmarkSplit,
    repetition: int,
) -> EconomicBenchmarkTrial:
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2026-07-28"},
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "text_stats", "arguments": {"text": text}},
        },
    ]
    payload = "".join(json.dumps(message, separators=(",", ":")) + "\n" for message in messages)
    started = time.perf_counter_ns()
    process = subprocess.run(
        [sys.executable, str(MCP_ROUTE)],
        input=payload,
        capture_output=True,
        check=True,
        text=True,
        timeout=5,
        cwd=ROOT,
    )
    elapsed = _milliseconds(started)
    responses = [json.loads(line) for line in process.stdout.splitlines() if line]
    result = responses[-1]["result"]
    output = result["structuredContent"]
    return _baseline_trial(
        route_id="local-mcp-stdio",
        route_type=EconomicBenchmarkRouteType.LOCAL_MCP,
        condition=condition,
        split=split,
        repetition=repetition,
        elapsed_ms=elapsed,
        task_valid=output == text_statistics(text),
        confirmed_free=False,
        network_bytes=len(payload.encode()) + len(process.stdout.encode()),
    )


def _run_subscription_baseline(
    text: str,
    *,
    condition: BenchmarkCondition,
    split: BenchmarkSplit,
    repetition: int,
) -> EconomicBenchmarkTrial:
    started = time.perf_counter_ns()
    output = text_statistics(text)
    elapsed = _milliseconds(started)
    output_bytes = len(json.dumps(output, separators=(",", ":")).encode())
    return _baseline_trial(
        route_id="subscription-baseline-unknown-cash",
        route_type=EconomicBenchmarkRouteType.SUBSCRIPTION_BASELINE,
        condition=condition,
        split=split,
        repetition=repetition,
        elapsed_ms=elapsed,
        task_valid=output == text_statistics(text),
        confirmed_free=False,
        input_tokens=(len(text.encode()) + 3) // 4,
        output_tokens=(output_bytes + 3) // 4,
        model_usage_complete=False,
        synthetic_usage=True,
    )


class _TimedPrepaidAdapter(PrepaidBalanceAdapterV2):
    def __init__(self) -> None:
        super().__init__(_money("1.00"), clock=_clock)
        self.last_settlement_latency_ms = Decimal(0)

    async def settle(
        self,
        *,
        reservation: PaymentReservationV2,
        actual_amount: CurrencyAmount,
        evidence: SettlementEvidence,
        idempotency_key: str,
    ) -> SettlementReceipt:
        started = time.perf_counter_ns()
        try:
            return await super().settle(
                reservation=reservation,
                actual_amount=actual_amount,
                evidence=evidence,
                idempotency_key=idempotency_key,
            )
        finally:
            self.last_settlement_latency_ms = _milliseconds(started)


@dataclass(slots=True)
class _PreparedSession:
    router: Router
    adapter: _TimedPrepaidAdapter

    async def close(self) -> None:
        await self.router.close()


def _confirmed_free_local_spec(provider_spec: ExecutorSpec) -> ExecutorSpec:
    evidence = MeasurementEvidence(
        status=EvidenceStatus.COMPLETE,
        source=EvidenceSource.CONFIRMED_NO_INCREMENTAL_CHARGE,
        trust=TrustLevel.ATTESTED,
    )
    return ExecutorSpec(
        id="local.python.statistics",
        capability=CAPABILITY,
        kind=ExecutorKind.PYTHON,
        description="Slower confirmed-free local comparator for prepared route scoring.",
        input_schema=provider_spec.input_schema,
        output_schema=provider_spec.output_schema,
        estimate=RouteEstimate(
            resources=ResourceVector(latency_ms=1_000, cpu_ms=500),
            cash=CashEstimate(
                amount_usd=Decimal(0),
                upper_bound_usd=Decimal(0),
                evidence=evidence,
            ),
            success_probability=1,
            quality_score=1,
            risk_score=0,
            confidence=1,
        ),
        side_effect=SideEffect.NONE,
        locality=Locality.IN_PROCESS,
        requires_network=False,
        config={
            "callable": "aeep.examples.tools:text_stats",
            "argument_mode": "kwargs",
        },
    )


def _workflow_local_spec() -> ExecutorSpec:
    evidence = MeasurementEvidence(
        status=EvidenceStatus.COMPLETE,
        source=EvidenceSource.CONFIRMED_NO_INCREMENTAL_CHARGE,
        trust=TrustLevel.ATTESTED,
    )
    return ExecutorSpec(
        id="local.python.identity",
        capability=WORKFLOW_CAPABILITY,
        kind=ExecutorKind.PYTHON,
        description="Confirmed-free local dependency step for the workflow proof.",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
        estimate=RouteEstimate(
            resources=ResourceVector(latency_ms=1, cpu_ms=1),
            cash=CashEstimate(
                amount_usd=Decimal(0),
                upper_bound_usd=Decimal(0),
                evidence=evidence,
            ),
            success_probability=1,
            quality_score=1,
            risk_score=0,
            confidence=1,
        ),
        side_effect=SideEffect.NONE,
        locality=Locality.IN_PROCESS,
        requires_network=False,
        config={
            "callable": "workflow_tools:identity_text",
            "argument_mode": "kwargs",
        },
    )


def _prepared_session(
    *,
    hybrid: bool,
    workflow: bool = False,
    database: str = ":memory:",
) -> _PreparedSession:
    if hybrid and workflow:
        raise ValueError("single-action hybrid and workflow sessions are distinct")
    provider_kind = ExecutorKind.HTTP if hybrid or workflow else ExecutorKind.PYTHON
    provider_spec = reference_executor_spec(kind=provider_kind)
    market = ReferenceMarket(executor_spec=provider_spec, clock=_clock)
    executors = [provider_spec]
    if hybrid:
        executors.append(_confirmed_free_local_spec(provider_spec))
    if workflow:
        executors.insert(0, _workflow_local_spec())
    manifest = Manifest(
        version="0.4",
        database=database,
        executors=executors,
        budget=AgentBudget(
            budget_id="economic-proof",
            daily_marketplace_limit_usd=1,
            max_per_action_usd=1,
            prepaid_balance_usd=1,
            authorization=AuthorizationPolicy(
                auto_approve_under_usd=1,
                financial_actions_require_human=False,
            ),
        ),
        economic_evidence=EconomicEvidenceConfig.model_validate(
            {
                "enabled": True,
                "settlement_currency": SETTLEMENT_CURRENCY,
                "live_quotes": {"enabled": True, "top_k": 1},
                "network": {
                    "allowed_quote_hosts": ["127.0.0.1"],
                    "allow_private_addresses": True,
                    "allow_redirects": False,
                    "trust_environment_proxy": False,
                },
                "payment": {"adapter": "prepaid"},
            }
        ),
        policies=(
            {
                "balanced": builtin_policies()["balanced"].model_copy(
                    update={"history_weight": 1.0, "history_prior_samples": 1}
                )
            }
            if hybrid
            else {}
        ),
    )
    adapter = _TimedPrepaidAdapter()
    router = Router(
        manifest,
        quote_provider=ReferenceQuoteProvider(market),
        economic_verifier=TrustStoreVerifier(TrustStore((market.trusted_key,)), clock=_clock),
        payment_adapter_v2=adapter,
        clock=_clock,
        executor_overrides={provider_kind: ReferenceEconomicExecutor(market)},
    )
    return _PreparedSession(router=router, adapter=adapter)


async def _record_hybrid_training_observations(
    session: _PreparedSession,
    text: str,
    *,
    condition: BenchmarkCondition,
    split: BenchmarkSplit,
    repetition: int,
    count: int,
) -> int:
    if split is BenchmarkSplit.HOLDOUT:
        return 0
    recorded = 0
    for index in range(count):
        request = ActionRequest(
            action_id=(
                f"calibration-{condition.value}-{split.value}-{repetition:02d}-{index:02d}"
            ),
            capability=CAPABILITY,
            input={"text": text},
        )
        request.constraints.allowed_executor_ids = ["local.python.statistics"]
        prepared = await session.router.prepare_route(request)
        if (
            not prepared.feasible
            or prepared.selected_executor_id != "local.python.statistics"
        ):
            raise RuntimeError("hybrid calibration did not bind the confirmed-free local route")
        outcome = await session.router.execute_prepared(
            prepared.prepared_id,
            approved_side_effect=SideEffect.NONE,
        )
        if not outcome.ok or outcome.output != text_statistics(text):
            raise RuntimeError("hybrid calibration did not produce a task-valid observation")
        recorded += 1
    return recorded


async def _run_prepared_trial(
    session: _PreparedSession,
    text: str,
    *,
    hybrid: bool,
    condition: BenchmarkCondition,
    split: BenchmarkSplit,
    repetition: int,
) -> EconomicBenchmarkTrial:
    route_id = "aeep-hybrid" if hybrid else "usage-priced-reference"
    route_type = (
        EconomicBenchmarkRouteType.HYBRID
        if hybrid
        else EconomicBenchmarkRouteType.USAGE_PRICED_PROVIDER
    )
    identity = _identity(route_id, condition, split, repetition)
    request = ActionRequest(
        action_id=f"action-{identity}",
        capability=CAPABILITY,
        input={"text": text},
    )
    total_started = time.perf_counter_ns()
    prepared = await session.router.prepare_route(request)
    if not prepared.feasible or prepared.selected_executor_id is None:
        raise RuntimeError("proof campaign did not produce a feasible exact route")
    selected_provider = prepared.selected_executor_id == "reference.http.statistics"
    if not hybrid and not selected_provider:
        raise RuntimeError("provider proof did not select the exact reference route")
    if hybrid and prepared.selected_executor_id not in {
        "local.python.statistics",
        "reference.http.statistics",
    }:
        raise RuntimeError("hybrid proof selected an unexpected executor")
    if hybrid and {item.executor_id for item in prepared.candidate_rankings} != {
        "local.python.statistics",
        "reference.http.statistics",
    }:
        raise RuntimeError("hybrid proof did not score both feasible exact routes")
    session.adapter.last_settlement_latency_ms = Decimal(0)
    execute_started = time.perf_counter_ns()
    outcome = await session.router.execute_prepared(
        prepared.prepared_id,
        approved_side_effect=SideEffect.NONE,
        payment_approved=True,
    )
    execute_wall = _milliseconds(execute_started)
    total_wall = _milliseconds(total_started)
    settlements = session.router.store.list_settlement_receipts(
        prepared_id=prepared.prepared_id
    )
    receipt = outcome.receipts[0]
    footprint = receipt.accounting.tool_footprint
    quote_latency = _rounded(prepared.quote_latency_ms or Decimal(0))
    prepared_total = _rounded(prepared.preparation_latency_ms or Decimal(0))
    preparation_latency = max(Decimal(0), prepared_total - quote_latency)
    settlement_latency = session.adapter.last_settlement_latency_ms
    execution_latency = max(Decimal(0), execute_wall - settlement_latency)
    measured_stages = (
        preparation_latency + quote_latency + execution_latency + settlement_latency
    )
    selected_ranking = next(
        item
        for item in prepared.candidate_rankings
        if item.executor_id == prepared.selected_executor_id
    )
    quote_id: str | None = None
    settlement_id: str | None = None
    charge_id: str | None = None
    reserved_cash: CurrencyAmount | None = None
    captured_cash: CurrencyAmount | None = None
    released_cash: CurrencyAmount | None = None
    if selected_provider:
        if len(settlements) != 1 or prepared.selected_quote_id is None:
            raise RuntimeError("paid proof execution did not create exactly one settlement")
        settlement = settlements[0]
        quote = session.router.store.get_bounded_quote(prepared.selected_quote_id)
        if quote is None:
            raise RuntimeError("paid proof settlement lost its immutable bounded quote")
        expected_cash = quote.expected_amount or quote.maximum_amount
        maximum_cash = quote.maximum_amount
        reserved_cash = settlement.reserved_amount
        captured_cash = settlement.captured_amount
        released_cash = settlement.released_amount
        evidence_level = settlement.evidence_level
        quote_id = quote.quote_id
        settlement_id = settlement.settlement_id
        charge_id = settlement.charge_id
    else:
        if settlements or prepared.selected_quote_id is not None:
            raise RuntimeError("confirmed-free hybrid route unexpectedly created a settlement")
        expected_cash = selected_ranking.expected_amount
        maximum_cash = prepared.maximum_cash_authorization
        if (
            expected_cash is None
            or maximum_cash is None
            or expected_cash.amount != 0
            or maximum_cash.amount != 0
        ):
            raise RuntimeError("confirmed-free hybrid selection lost its explicit zero evidence")
        evidence_level = EconomicEvidenceLevel.OPERATOR_ATTESTED
    return EconomicBenchmarkTrial(
        trial_id=identity,
        case_id=f"text-statistics-{split.value}",
        route_id=route_id,
        route_type=route_type,
        condition=condition,
        split=split,
        repetition=repetition,
        task_valid=outcome.ok and outcome.output == text_statistics(text),
        selected_by_aeep=hybrid,
        prepared_id=prepared.prepared_id,
        quote_id=quote_id,
        settlement_id=settlement_id,
        charge_id=charge_id,
        expected_cash=expected_cash,
        maximum_cash=maximum_cash,
        reserved_cash=reserved_cash,
        captured_cash=captured_cash,
        released_cash=released_cash,
        cash_evidence_level=evidence_level,
        preparation_latency_ms=preparation_latency,
        quote_latency_ms=quote_latency,
        execution_latency_ms=execution_latency,
        settlement_latency_ms=settlement_latency,
        total_wall_time_ms=max(total_wall, measured_stages),
        input_tokens=receipt.actual_resources.input_tokens,
        output_tokens=receipt.actual_resources.output_tokens,
        cached_tokens=receipt.actual_resources.cached_input_tokens,
        tool_schema_tokens=(footprint.schema_approx_tokens if footprint is not None else 0),
        tool_result_tokens=(
            footprint.filtered_result_approx_tokens if footprint is not None else 0
        ),
        model_usage_complete=bool(receipt.accounting.model_usage),
        local_resources_complete=False,
        cpu_ms=Decimal(str(receipt.actual_resources.cpu_ms)),
        peak_memory_mb=Decimal(str(receipt.actual_resources.peak_memory_mb)),
        network_bytes=receipt.actual_resources.network_bytes,
        retry_count=max(0, receipt.attempt - 1),
        fallback_count=0,
        quote_failure_codes=tuple(failure.code for failure in prepared.quote_failures),
    )


async def _run_workflow_proof(
    session: _PreparedSession,
    text: str,
    *,
    repetition: int,
) -> EconomicWorkflowProofTrial:
    workflow_id = f"prepared-hybrid-workflow-{repetition:02d}"
    second_action = ActionRequest(
        action_id=f"action-{workflow_id}-statistics",
        capability=CAPABILITY,
        input={"text": "future input is unavailable until the local step completes"},
    )
    workflow = WorkflowRequest(
        workflow_id=workflow_id,
        budget=WorkflowBudget(max_cash_usd=Decimal("0.0100")),
        steps=[
            WorkflowStep(
                step_id="local-identity",
                action=ActionRequest(
                    action_id=f"action-{workflow_id}-identity",
                    capability=WORKFLOW_CAPABILITY,
                    input={"text": text},
                ),
            ),
            WorkflowStep(
                step_id="paid-statistics",
                action=second_action,
                depends_on=["local-identity"],
                bindings=[
                    WorkflowInputBinding(
                        target_path="/text",
                        source_step_id="local-identity",
                        source_path="/text",
                    )
                ],
            ),
        ],
        outputs=[
            WorkflowOutputProjection(
                name="characters",
                step_id="paid-statistics",
                path="/characters",
            )
        ],
    )
    total_started = time.perf_counter_ns()
    outcome = await session.router.execute_workflow(workflow, payment_approved=True)
    total_wall = _milliseconds(total_started)

    prepared = session.router.store.list_prepared_decisions()
    quotes = session.router.store.list_bounded_quotes()
    settlements = session.router.store.list_settlement_receipts()
    if len(prepared) != 2 or len(quotes) != 1 or len(settlements) != 1:
        raise RuntimeError("hybrid workflow did not produce its exact prepared evidence chain")
    prepared_by_action = {item.action_id: item for item in prepared}
    expected_action_ids = {
        f"action-{workflow_id}-identity",
        f"action-{workflow_id}-statistics",
    }
    if set(prepared_by_action) != expected_action_ids:
        raise RuntimeError("hybrid workflow prepared an unexpected action")
    if any(item.state.value != "SETTLED" for item in prepared):
        raise RuntimeError("hybrid workflow did not settle every prepared step")

    quote = quotes[0]
    quote_request = session.router.store.get_quote_request_v2(quote.quote_request_id)
    if quote_request is None:
        raise RuntimeError("hybrid workflow lost its request-bound quote request")
    resolved_second = second_action.model_copy(deep=True)
    resolved_second.input["text"] = text
    resolved_second.constraints = merge_constraints(
        workflow.constraints, resolved_second.constraints
    )
    resolved_second.constraints.max_cost_usd = float(workflow.budget.max_cash_usd or 0)
    disclosed_bytes = quote_request.disclosed_quote_features.get("input_bytes")
    dependency_binding_verified = (
        quote_request.action_id == second_action.action_id
        and quote_request.action_digest == action_digest(resolved_second)
        and disclosed_bytes == action_features(resolved_second.input).input_bytes
    )
    if not dependency_binding_verified or not isinstance(disclosed_bytes, int):
        raise RuntimeError("hybrid workflow quote was not bound to the resolved dependency input")

    settlement = settlements[0]
    quote_latency = sum(
        (item.quote_latency_ms or Decimal(0) for item in prepared),
        Decimal(0),
    )
    preparation_latency = sum(
        (
            max(
                Decimal(0),
                (item.preparation_latency_ms or Decimal(0))
                - (item.quote_latency_ms or Decimal(0)),
            )
            for item in prepared
        ),
        Decimal(0),
    )
    settlement_latency = session.adapter.last_settlement_latency_ms
    execution_latency = sum(
        (Decimal(str(receipt.duration_ms)) for receipt in outcome.receipts),
        Decimal(0),
    )
    measured_stages = (
        preparation_latency + quote_latency + execution_latency + settlement_latency
    )
    task_valid = (
        outcome.status is WorkflowStatus.SUCCESS
        and outcome.outputs.get("characters") == len(text)
        and len(outcome.receipts) == 2
    )
    return EconomicWorkflowProofTrial(
        workflow_id=workflow_id,
        condition=BenchmarkCondition.PROCESS_COLD,
        split=BenchmarkSplit.HOLDOUT,
        repetition=repetition,
        task_valid=task_valid,
        dependency_binding_verified=dependency_binding_verified,
        step_count=2,
        prepared_step_count=len(prepared),
        quoted_step_count=len(quotes),
        settled_step_count=len(settlements),
        dependency_input_bytes=disclosed_bytes,
        expected_cash=quote.expected_amount or quote.maximum_amount,
        maximum_cash=quote.maximum_amount,
        reserved_cash=settlement.reserved_amount,
        captured_cash=settlement.captured_amount,
        released_cash=settlement.released_amount,
        cash_evidence_level=settlement.evidence_level,
        preparation_latency_ms=_rounded(preparation_latency),
        quote_latency_ms=_rounded(quote_latency),
        execution_latency_ms=_rounded(execution_latency),
        settlement_latency_ms=_rounded(settlement_latency),
        total_wall_time_ms=max(total_wall, _rounded(measured_stages)),
    )


async def run_campaign(*, repetitions: int = 30) -> EconomicProofCampaignReport:
    """Measure deterministic local transports and the real prepared settlement path."""

    if not 1 <= repetitions <= 1_000:
        raise ValueError("repetitions must be between 1 and 1000")
    text = _text()
    trials: list[EconomicBenchmarkTrial] = []
    training_repetitions = sum(
        _split(repetition, repetitions) is not BenchmarkSplit.HOLDOUT
        for repetition in range(repetitions)
    )
    observations_per_training_repetition = (
        max(1, math.ceil(10 / training_repetitions))
        if training_repetitions
        else 0
    )
    hybrid_training_observations = 0
    with tempfile.TemporaryDirectory(prefix="aeep-economic-proof-") as temporary:
        cold_hybrid_database = str(Path(temporary) / "cold-hybrid.db")
        warm_provider = _prepared_session(hybrid=False)
        warm_hybrid = _prepared_session(hybrid=True)
        warm_http = httpx.Client(
            transport=httpx.MockTransport(_http_handler),
            base_url="https://local.reference.invalid",
            trust_env=False,
        )
        try:
            for condition in BenchmarkCondition:
                for repetition in range(repetitions):
                    split = _split(repetition, repetitions)
                    trials.extend(
                        (
                            _run_local_python(
                                text,
                                condition=condition,
                                split=split,
                                repetition=repetition,
                            ),
                            _run_local_cli(
                                text,
                                condition=condition,
                                split=split,
                                repetition=repetition,
                            ),
                            _run_direct_http(
                                text,
                                condition=condition,
                                split=split,
                                repetition=repetition,
                                client=(
                                    warm_http
                                    if condition is BenchmarkCondition.ROUTER_WARM
                                    else None
                                ),
                            ),
                            _run_local_mcp(
                                text,
                                condition=condition,
                                split=split,
                                repetition=repetition,
                            ),
                            _run_subscription_baseline(
                                text,
                                condition=condition,
                                split=split,
                                repetition=repetition,
                            ),
                        )
                    )
                    if condition is BenchmarkCondition.PROCESS_COLD:
                        provider_session = _prepared_session(hybrid=False)
                        hybrid_session = _prepared_session(
                            hybrid=True,
                            database=cold_hybrid_database,
                        )
                    else:
                        provider_session = warm_provider
                        hybrid_session = warm_hybrid
                    try:
                        hybrid_training_observations += (
                            await _record_hybrid_training_observations(
                                hybrid_session,
                                text,
                                condition=condition,
                                split=split,
                                repetition=repetition,
                                count=observations_per_training_repetition,
                            )
                        )
                        trials.append(
                            await _run_prepared_trial(
                                provider_session,
                                text,
                                hybrid=False,
                                condition=condition,
                                split=split,
                                repetition=repetition,
                            )
                        )
                        trials.append(
                            await _run_prepared_trial(
                                hybrid_session,
                                text,
                                hybrid=True,
                                condition=condition,
                                split=split,
                                repetition=repetition,
                            )
                        )
                    finally:
                        if condition is BenchmarkCondition.PROCESS_COLD:
                            await provider_session.close()
                            await hybrid_session.close()
        finally:
            await asyncio.to_thread(warm_http.close)
            await warm_provider.close()
            await warm_hybrid.close()
    workflow_session = _prepared_session(hybrid=False, workflow=True)
    try:
        workflow_trial = await _run_workflow_proof(
            workflow_session,
            text,
            repetition=repetitions - 1,
        )
    finally:
        await workflow_session.close()
    report = EconomicProofCampaignReport(
        campaign_id="deterministic-local-economic-evidence",
        domain="text-statistics",
        settlement_currency=SETTLEMENT_CURRENCY,
        repetitions=repetitions,
        generated_at=GENERATED_AT,
        trials=tuple(trials),
        workflow_trials=(workflow_trial,),
        hybrid_training_observations=hybrid_training_observations,
    )
    return finalize_economic_proof(report)


def write_report(report: EconomicProofCampaignReport, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "report.json").write_text(
        report.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    (destination / "report.md").write_text(
        format_economic_proof_report(report),
        encoding="utf-8",
    )


def check_report(destination: Path, *, repetitions: int) -> EconomicProofCampaignReport:
    report = EconomicProofCampaignReport.model_validate_json(
        (destination / "report.json").read_bytes()
    )
    if report.repetitions != repetitions:
        raise ValueError(
            f"checked report has {report.repetitions} repetitions; expected {repetitions}"
        )
    expected_markdown = format_economic_proof_report(report)
    if (destination / "report.md").read_text(encoding="utf-8") != expected_markdown:
        raise ValueError("report.md is stale relative to report.json")
    recalculated = finalize_economic_proof(report.model_copy(update={"oracles": (), "gates": ()}))
    if recalculated.oracles != report.oracles or recalculated.gates != report.gates:
        raise ValueError("checked report contains stale oracle or gate calculations")
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=30)
    parser.add_argument("--output-dir", type=Path, default=HERE)
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate checked artifacts without rerunning measured transports",
    )
    parser.add_argument(
        "--require-gates",
        action="store_true",
        help="return nonzero when an engineering gate is not met",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.check:
        report = check_report(arguments.output_dir, repetitions=arguments.repetitions)
    else:
        report = asyncio.run(run_campaign(repetitions=arguments.repetitions))
        write_report(report, arguments.output_dir)
    failed = [gate.name for gate in report.gates if not gate.passed]
    safety_failures = [name for name in failed if name not in _REQUIRED_ECONOMIC_GATES]
    required_gate_failures = [
        name for name in failed if name in _REQUIRED_ECONOMIC_GATES
    ]
    print(
        json.dumps(
            {
                "campaign_id": report.campaign_id,
                "repetitions": report.repetitions,
                "trials": len(report.trials),
                "safety_invariants_passed": not safety_failures,
                "failed_safety_invariants": safety_failures,
                "failed_required_economic_gates": required_gate_failures,
                "output_dir": str(arguments.output_dir),
            },
            sort_keys=True,
        )
    )
    return 1 if safety_failures or (failed and arguments.require_gates) else 0


if __name__ == "__main__":
    raise SystemExit(main())
