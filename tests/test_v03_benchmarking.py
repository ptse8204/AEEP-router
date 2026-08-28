from __future__ import annotations

import sqlite3
import sys
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from conftest import manifest_with, python_spec

from aeep.benchmarking import (
    BenchmarkCampaignReport,
    BenchmarkCase,
    BenchmarkCondition,
    BenchmarkOracle,
    BenchmarkPhase,
    BenchmarkRevaluationReport,
    BenchmarkRoute,
    BenchmarkRunner,
    BenchmarkSplit,
    BenchmarkSuite,
    BenchmarkTrial,
    _summaries,
    evaluate_release_proof,
    format_campaign_report,
    parse_codex_jsonl,
    revalue_campaign,
)
from aeep.errors import ConfigurationError
from aeep.executors.parsing import parse_output
from aeep.models import (
    ActionRequest,
    CashEstimate,
    EvidenceSource,
    EvidenceStatus,
    ExecutorKind,
    ExecutorSpec,
    Locality,
    MeasurementEvidence,
    ModelAccessChannel,
    ModelTokenUsage,
    RateCardRate,
    RateCardSnapshot,
    RateType,
    ResourceAccounting,
    ResourceVector,
    RouteEstimate,
    TrustLevel,
)
from aeep.router import Router
from aeep.workflow import WorkflowOutputProjection, WorkflowRequest, WorkflowStep


def test_codex_jsonl_capture_is_terminal_bounded_and_deduplicated():
    event = (
        '{"type":"turn.completed","usage":{"input_tokens":100,'
        '"cached_input_tokens":40,"cache_write_input_tokens":10,'
        '"output_tokens":20,"reasoning_output_tokens":5}}'
    )
    usage = parse_codex_jsonl(
        ['{"type":"item.completed","item":{"text":"secret output"}}', event, event],
        model="codex-model",
    )
    assert usage.access_channel == ModelAccessChannel.SUBSCRIPTION
    assert usage.input_tokens == 100
    assert usage.cached_input_tokens == 40
    assert usage.cache_write_input_tokens == 10
    assert usage.output_tokens == 20
    assert usage.reasoning_output_tokens == 5
    with pytest.raises(ConfigurationError, match="malformed"):
        parse_codex_jsonl(["{"], model="codex-model")
    with pytest.raises(ConfigurationError, match="conflicting"):
        parse_codex_jsonl(
            [event, event.replace('"input_tokens":100', '"input_tokens":101')],
            model="codex-model",
        )
    with pytest.raises(ConfigurationError, match="size"):
        parse_codex_jsonl([event], model="codex-model", max_bytes=1)


def test_codex_jsonl_precedence_fills_missing_without_double_counting():
    terminal = '{"type":"turn.completed","usage":{"input_tokens":100,"output_tokens":20}}'
    telemetry = ModelTokenUsage(
        provider="openai",
        model="codex-model",
        access_channel=ModelAccessChannel.SUBSCRIPTION,
        input_tokens=100,
        cached_input_tokens=40,
        output_tokens=20,
        reasoning_output_tokens=5,
        evidence=MeasurementEvidence(
            status=EvidenceStatus.COMPLETE,
            source=EvidenceSource.PROVIDER_REPORT,
            trust=TrustLevel.OBSERVED,
        ),
    )
    resolved = parse_codex_jsonl([terminal], model="codex-model", fallback_usage=[telemetry])
    assert resolved.input_tokens == 100
    assert resolved.cached_input_tokens == 40
    assert resolved.output_tokens == 20
    assert resolved.reasoning_output_tokens == 5
    assert resolved.evidence.status == EvidenceStatus.COMPLETE

    conflicting = telemetry.model_copy(update={"input_tokens": 101})
    resolved = parse_codex_jsonl([terminal], model="codex-model", fallback_usage=[conflicting])
    assert resolved.evidence.status == EvidenceStatus.CONFLICT
    with pytest.raises(ConfigurationError, match="failed"):
        parse_codex_jsonl(['{"type":"turn.failed"}'], model="codex-model")


def test_explicit_revaluation_creates_derived_report_without_mutating_trials():
    measured = MeasurementEvidence(
        status=EvidenceStatus.COMPLETE,
        source=EvidenceSource.LOCAL_METER,
        trust=TrustLevel.OBSERVED,
    )
    trial = BenchmarkTrial(
        trial_id="trial",
        run_id="run",
        suite_id="suite",
        case_id="case",
        route_id="codex",
        route_fingerprint="a" * 64,
        condition=BenchmarkCondition.PROCESS_COLD,
        repetition=0,
        phase=BenchmarkPhase.HOLDOUT,
        state="complete",
        ok=True,
        valid=True,
        accounting=ResourceAccounting(
            model_usage=[
                ModelTokenUsage(
                    provider="openai",
                    model="model-x",
                    access_channel=ModelAccessChannel.SUBSCRIPTION,
                    input_tokens=100,
                    output_tokens=20,
                    evidence=measured,
                )
            ]
        ),
    )
    report = BenchmarkCampaignReport(
        run_id="run",
        suite_id="suite",
        domain="domain",
        deterministic_tools_available=False,
        pricing_snapshot_ids=[],
        frozen_holdout_decisions={},
        trials=[trial],
        summaries=[],
        baseline_deltas=[],
        oracles=[],
        subscription_conservation=[],
    )
    snapshot = RateCardSnapshot(
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
                unit_quantity=100,
                rate_amount=Decimal("0.01"),
            ),
            RateCardRate(
                rate_id="output",
                rate_type=RateType.OUTPUT_TOKEN,
                meter="output_tokens",
                input_unit="token",
                output_unit="USD",
                unit_quantity=100,
                rate_amount=Decimal("0.03"),
            ),
        ],
    )
    original = report.model_dump_json()
    derived = revalue_campaign(report, snapshot)
    assert isinstance(derived, BenchmarkRevaluationReport)
    assert derived.pricing_snapshot_id == snapshot.snapshot_id
    assert derived.trial_values["trial"][0].amount == Decimal("0.016")
    assert report.model_dump_json() == original
    assert report.trials[0].counterfactual_costs == []


def test_jsonl_output_parser_selects_the_final_structured_message():
    output = parse_output(
        "\n".join(
            [
                '{"type":"item.completed","item":{"type":"analysis","text":"secret"}}',
                '{"type":"item.completed","item":{"type":"agent_message","text":"{\\"words\\":2}"}}',
                '{"type":"turn.completed","usage":{"input_tokens":10}}',
            ]
        ),
        {
            "type": "jsonl",
            "match": {"type": "item.completed", "item.type": "agent_message"},
            "path": "item.text",
            "decode_json": True,
        },
    )
    assert output == {"words": 2}


@pytest.mark.asyncio
async def test_command_codex_capture_attaches_usage_without_persisting_jsonl(tmp_path):
    script = (
        "import json;"
        "print(json.dumps({'type':'item.completed','item':{'type':'command_execution',"
        "'command':'python3 -m fixture.tool','status':'completed','exit_code':0}}));"
        "print(json.dumps({'type':'item.completed','item':{'type':'agent_message',"
        "'text':'{\\\"value\\\":1}'}}));"
        "print(json.dumps({'type':'turn.completed','usage':{'input_tokens':100,"
        "'cached_input_tokens':40,'output_tokens':20,'reasoning_output_tokens':5}}))"
    )
    route = ExecutorSpec(
        id="codex-fixture",
        capability="fixture.answer@1",
        kind=ExecutorKind.COMMAND,
        description="Hermetic Codex JSONL fixture",
        input_schema={"type": "object", "additionalProperties": False},
        output_schema={
            "type": "object",
            "properties": {"value": {"type": "integer"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        estimate=RouteEstimate(resources=ResourceVector(monetary_usd=0)),
        side_effect="none",
        locality=Locality.LOCAL,
        config={
            "argv": [sys.executable, "-c", script],
            "output": {
                "type": "jsonl",
                "match": {"type": "item.completed", "item.type": "agent_message"},
                "path": "item.text",
                "decode_json": True,
            },
            "usage_capture": {
                "type": "codex_jsonl",
                "provider": "openai",
                "model": "codex-fixture",
                "access_channel": "subscription",
                "required_command_substring": "python3 -m fixture.tool",
            },
        },
    )
    router = Router(manifest_with(route))
    outcome = await router.execute(router.route(ActionRequest(capability=route.capability)))
    assert outcome.output == {"value": 1}
    assert outcome.receipts[0].accounting.model_usage[0].cached_input_tokens == 40
    assert outcome.receipts[0].metadata["codex_command_executions"] == 1
    assert "agent_message" not in outcome.receipts[0].model_dump_json()
    await router.close()

    rejected = route.model_copy(
        update={
            "id": "codex-fixture-missing-tool",
            "config": {
                **route.config,
                "usage_capture": {
                    **route.config["usage_capture"],
                    "required_command_substring": "python3 -m missing.tool",
                },
            },
        }
    )
    router = Router(manifest_with(rejected))
    outcome = await router.execute(router.route(ActionRequest(capability=rejected.capability)))
    assert not outcome.ok
    await router.close()


@pytest.mark.asyncio
async def test_campaign_keeps_api_cash_subscription_and_counterfactuals_separate(tmp_path):
    script = (
        "import json;"
        "print(json.dumps({'type':'item.completed','item':{'type':'agent_message',"
        "'text':'{\"value\":1}'}}));"
        "print(json.dumps({'type':'turn.completed','usage':{'input_tokens':100,"
        "'cached_input_tokens':40,'output_tokens':20}}))"
    )

    def model_route(identifier: str, channel: str) -> ExecutorSpec:
        return ExecutorSpec(
            id=identifier,
            capability="model.fixture@1",
            kind=ExecutorKind.COMMAND,
            description=identifier,
            input_schema={"type": "object", "additionalProperties": False},
            output_schema={
                "type": "object",
                "properties": {"value": {"const": 1}},
                "required": ["value"],
                "additionalProperties": False,
            },
            estimate=RouteEstimate(
                resources=ResourceVector(monetary_usd=0),
                cash=CashEstimate(
                    amount_usd=Decimal("0.02"),
                    upper_bound_usd=Decimal("0.02"),
                    evidence=MeasurementEvidence(
                        status=EvidenceStatus.COMPLETE,
                        source=EvidenceSource.STATIC_ESTIMATE,
                        trust=TrustLevel.SELF_ASSERTED,
                    ),
                ),
            ),
            side_effect="none",
            locality=Locality.LOCAL,
            config={
                "argv": [sys.executable, "-c", script],
                "output": {
                    "type": "jsonl",
                    "match": {"type": "item.completed", "item.type": "agent_message"},
                    "path": "item.text",
                    "decode_json": True,
                },
                "usage_capture": {
                    "type": "codex_jsonl",
                    "provider": "openai",
                    "model": "model-x",
                    "access_channel": channel,
                },
            },
        )

    rates = RateCardSnapshot(
        provider="openai",
        product="api-and-credit",
        model="model-x",
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        retrieved_at=datetime(2026, 1, 2, tzinfo=UTC),
        source_uri="https://example.test/pricing",
        source_content_sha256="b" * 64,
        currency="USD",
        rates=[
            RateCardRate(
                rate_id="input",
                rate_type=RateType.INPUT_TOKEN,
                meter="input_tokens",
                input_unit="token",
                output_unit="USD",
                unit_quantity=100,
                rate_amount="0.01",
            ),
            RateCardRate(
                rate_id="cached",
                rate_type=RateType.CACHED_INPUT_TOKEN,
                meter="cached_input_tokens",
                input_unit="token",
                output_unit="USD",
                unit_quantity=100,
                rate_amount="0.002",
            ),
            RateCardRate(
                rate_id="output",
                rate_type=RateType.OUTPUT_TOKEN,
                meter="output_tokens",
                input_unit="token",
                output_unit="USD",
                unit_quantity=100,
                rate_amount="0.03",
            ),
            RateCardRate(
                rate_id="credit",
                rate_type=RateType.SUBSCRIPTION_UNIT,
                meter="input_tokens",
                input_unit="token",
                output_unit="codex_credit",
                unit_quantity=100,
                rate_amount="2",
            ),
        ],
    )
    api = model_route("api-model", "api")
    subscription = model_route("subscription-model", "subscription")
    suite = BenchmarkSuite(
        suite_id="economic-separation",
        repetitions=1,
        conditions=[BenchmarkCondition.PROCESS_COLD],
        routes=[
            BenchmarkRoute(
                route_id="api",
                executor_id=api.id,
                provider="openai",
                model="model-x",
                access_channel=ModelAccessChannel.API,
                actual_rate_snapshot_id=rates.snapshot_id,
                counterfactual_rate_snapshot_id=rates.snapshot_id,
            ),
            BenchmarkRoute(
                route_id="subscription",
                executor_id=subscription.id,
                provider="openai",
                model="model-x",
                access_channel=ModelAccessChannel.SUBSCRIPTION,
                counterfactual_rate_snapshot_id=rates.snapshot_id,
                subscription_rate_snapshot_id=rates.snapshot_id,
                subscription_resource_pool="openai:chatgpt:agentic",
                subscription_unit="codex_credit",
            ),
        ],
        pricing_snapshots=[rates],
        cases=[
            BenchmarkCase(
                case_id="case",
                split=BenchmarkSplit.HOLDOUT,
                action=ActionRequest(capability="model.fixture@1"),
            )
        ],
        acknowledge_cash_risk=True,
        max_total_cash_usd=Decimal("0.10"),
    )
    runner = BenchmarkRunner(
        lambda: Router(manifest_with(api, subscription)), tmp_path / "economics.db"
    )
    report = await runner.run(suite)
    by_route = {trial.route_id: trial for trial in report.trials}
    assert by_route["api"].accounting.cash.actual_cash_cost() == Decimal("0.0128")
    assert by_route["api"].counterfactual_costs[0].amount == Decimal("0.0128")
    assert by_route["subscription"].accounting.cash.actual_cash_cost() is None
    assert by_route["subscription"].counterfactual_costs[0].amount == Decimal("0.0128")
    assert by_route["subscription"].accounting.subscription_usage[0].consumed == 2


@pytest.mark.asyncio
async def test_campaign_is_isolated_repeatable_and_stores_no_payload(
    tmp_path, text_schema, stats_schema
):
    route = python_spec(
        "local",
        "aeep.examples.tools:text_stats",
        input_schema=text_schema,
        output_schema=stats_schema,
    )
    route.estimate.resources = ResourceVector(monetary_usd=0, latency_ms=1)
    manifest = manifest_with(route)
    suite = BenchmarkSuite(
        suite_id="suite-test",
        repetitions=2,
        conditions=[BenchmarkCondition.PROCESS_COLD],
        routes=[BenchmarkRoute(route_id="local", executor_id="local")],
        cases=[
            BenchmarkCase(
                case_id="secret-case",
                split=BenchmarkSplit.HOLDOUT,
                action=ActionRequest(
                    capability="text.stats",
                    input={"text": "DO-NOT-PERSIST"},
                ),
            )
        ],
    )
    database = tmp_path / "benchmarks.db"
    runner = BenchmarkRunner(lambda: Router(manifest), database)
    report = await runner.run(suite)
    assert len(report.trials) == 2
    assert all(trial.valid for trial in report.trials)
    assert report.oracles[0].selected_route_id == "local"
    assert report.oracles[0].selected_within_10_percent is True
    assert report.summaries[0].p95_wall_time_ms is not None
    rendered = format_campaign_report(report)
    for panel in (
        "Actual cash",
        "Subscription usage",
        "API-equivalent counterfactual (not actual cash)",
        "Private policy score",
    ):
        assert panel in rendered
    proof = evaluate_release_proof([report], baseline_route_ids=["local"], hybrid_route_id="local")
    assert not proof.passed
    assert (
        next(gate for gate in proof.gates if gate.name == "model-token-reduction").passed is False
    )
    resumed = await runner.run(suite)
    assert {trial.trial_id for trial in resumed.trials} == {
        trial.trial_id for trial in report.trials
    }
    connection = sqlite3.connect(database)
    stored = " ".join(row[0] for row in connection.execute("SELECT payload_json FROM trials"))
    assert "DO-NOT-PERSIST" not in stored


@pytest.mark.asyncio
async def test_warm_setup_is_separate_and_suite_id_is_immutable(
    tmp_path, text_schema, stats_schema
):
    route = python_spec(
        "local",
        "aeep.examples.tools:text_stats",
        input_schema=text_schema,
        output_schema=stats_schema,
    )
    route.estimate.resources = ResourceVector(monetary_usd=0)
    suite = BenchmarkSuite(
        suite_id="immutable-suite",
        repetitions=2,
        conditions=[BenchmarkCondition.ROUTER_WARM],
        routes=[BenchmarkRoute(route_id="local", executor_id="local")],
        cases=[
            BenchmarkCase(
                case_id="one",
                split=BenchmarkSplit.TRAINING,
                action=ActionRequest(capability="text.stats", input={"text": "x"}),
            )
        ],
    )
    runner = BenchmarkRunner(lambda: Router(manifest_with(route)), tmp_path / "bench.db")
    report = await runner.run(suite)
    assert len([trial for trial in report.trials if trial.phase.value == "setup"]) == 1
    assert report.summaries[0].trials == 2
    assert report.summaries[0].warm_cache_evidence_coverage == "not-applicable"
    with pytest.raises(ConfigurationError, match="different content"):
        await runner.run(suite.model_copy(update={"seed": 99}))


def test_router_reuse_cache_miss_is_not_counted_as_warm_measurement():
    trials = [
        BenchmarkTrial(
            trial_id=f"warm-{index}",
            run_id="run",
            suite_id="suite",
            case_id="case",
            route_id="mcp",
            route_fingerprint="a" * 64,
            condition=BenchmarkCondition.ROUTER_WARM,
            repetition=index,
            phase=BenchmarkPhase.HOLDOUT,
            state="complete",
            ok=True,
            valid=True,
            wall_time_ms=wall,
            cache_hit_verified=cache_hit,
        )
        for index, (wall, cache_hit) in enumerate(((100.0, False), (20.0, True)))
    ]
    summary = _summaries(trials)[0]
    assert summary.attempted == 2
    assert summary.trials == 1
    assert summary.median_wall_time_ms == 20
    assert summary.warm_cache_evidence_coverage == "1/2"


@pytest.mark.asyncio
async def test_campaign_executes_and_accounts_for_a_workflow_variant(
    tmp_path, text_schema, stats_schema
):
    route = python_spec(
        "local",
        "aeep.examples.tools:text_stats",
        input_schema=text_schema,
        output_schema=stats_schema,
    )
    route.estimate.resources = ResourceVector(monetary_usd=0)
    workflow = WorkflowRequest(
        workflow_id="bench-workflow",
        steps=[
            WorkflowStep(
                step_id="stats",
                action=ActionRequest(capability="text.stats", input={"text": "workflow input"}),
            )
        ],
        outputs=[WorkflowOutputProjection(name="stats", step_id="stats", path="")],
    )
    suite = BenchmarkSuite(
        suite_id="workflow-suite",
        repetitions=1,
        conditions=[BenchmarkCondition.PROCESS_COLD],
        routes=[
            BenchmarkRoute(route_id="direct", executor_id="local"),
            BenchmarkRoute(route_id="hybrid", workflow=workflow, validation_output_path="/stats"),
        ],
        cases=[
            BenchmarkCase(
                case_id="one",
                split=BenchmarkSplit.HOLDOUT,
                action=ActionRequest(capability="text.stats", input={"text": "unused"}),
            )
        ],
    )
    runner = BenchmarkRunner(lambda: Router(manifest_with(route)), tmp_path / "workflow.db")
    report = await runner.run(suite)
    trial = next(item for item in report.trials if item.route_id == "hybrid")
    assert trial.valid is True
    assert trial.operation_count == 1
    assert trial.retry_fallback_count == 0
    assert trial.route_fingerprint is not None
    assert report.frozen_holdout_decisions == {"one": "direct"}
    assert report.oracles[0].selected_route_id == "direct"


@pytest.mark.asyncio
async def test_unknown_cash_campaign_requires_an_enforceable_ceiling(
    tmp_path, text_schema, stats_schema
):
    route = python_spec(
        "unknown",
        "aeep.examples.tools:text_stats",
        input_schema=text_schema,
        output_schema=stats_schema,
    )
    route.estimate.cash = route.estimate.cash.model_copy(
        update={"amount_usd": None, "upper_bound_usd": None}
    )
    suite = BenchmarkSuite(
        suite_id="unknown-cash",
        repetitions=1,
        conditions=[BenchmarkCondition.PROCESS_COLD],
        routes=[BenchmarkRoute(route_id="unknown", executor_id="unknown")],
        cases=[
            BenchmarkCase(
                case_id="one",
                split=BenchmarkSplit.TRAINING,
                action=ActionRequest(capability="text.stats", input={"text": "x"}),
            )
        ],
    )
    runner = BenchmarkRunner(lambda: Router(manifest_with(route)), tmp_path / "bench.db")
    with pytest.raises(ConfigurationError, match="acknowledgement"):
        await runner.run(suite)


def test_release_proof_enforces_all_locked_numeric_thresholds():
    usage_evidence = MeasurementEvidence(
        status=EvidenceStatus.COMPLETE,
        source=EvidenceSource.LOCAL_METER,
        trust=TrustLevel.OBSERVED,
    )

    def trial(route_id: str, repetition: int, *, tokens: int, wall: float):
        return {
            "trial_id": f"{route_id}-{repetition}",
            "run_id": "run",
            "suite_id": "suite",
            "case_id": "case",
            "route_id": route_id,
            "route_fingerprint": "a" * 64,
            "condition": BenchmarkCondition.PROCESS_COLD,
            "repetition": repetition,
            "phase": BenchmarkPhase.HOLDOUT,
            "state": "complete",
            "ok": True,
            "valid": True,
            "wall_time_ms": wall,
            "policy_score": 1.0 if route_id == "hybrid" else 1.05,
            "accounting": ResourceAccounting(
                model_usage=[
                    ModelTokenUsage(
                        provider="openai",
                        model="model-x",
                        access_channel=ModelAccessChannel.API,
                        input_tokens=tokens - 10,
                        output_tokens=10,
                        evidence=usage_evidence,
                    )
                ]
            ),
        }

    reports = []
    for domain in ("local-data", "github"):
        trials = [
            trial("baseline", repetition, tokens=100, wall=100) for repetition in range(2)
        ] + [trial("hybrid", repetition, tokens=70, wall=80) for repetition in range(2)]
        reports.append(
            BenchmarkCampaignReport.model_validate(
                {
                    "run_id": f"run-{domain}",
                    "suite_id": f"suite-{domain}",
                    "domain": domain,
                    "deterministic_tools_available": True,
                    "pricing_snapshot_ids": [],
                    "frozen_holdout_decisions": {"case": "hybrid"},
                    "trials": trials,
                    "summaries": [],
                    "baseline_deltas": [],
                    "oracles": [
                        BenchmarkOracle(
                            case_id="case",
                            condition=BenchmarkCondition.PROCESS_COLD,
                            repetition=repetition,
                            selected_route_id="hybrid",
                            policy_route_id="hybrid",
                            selected_within_10_percent=True,
                        )
                        for repetition in range(2)
                    ],
                    "subscription_conservation": [],
                }
            )
        )
    proof = evaluate_release_proof(
        reports,
        baseline_route_ids=["baseline"],
        hybrid_route_id="hybrid",
    )
    assert proof.passed
    assert all(gate.passed for gate in proof.gates)

    forged = [
        report.model_copy(update={"frozen_holdout_decisions": {"case": "hybrid-executor"}})
        for report in reports
    ]
    forged_proof = evaluate_release_proof(
        forged,
        baseline_route_ids=["baseline"],
        hybrid_route_id="hybrid",
    )
    assert not next(gate for gate in forged_proof.gates if gate.name == "policy-oracle").passed
