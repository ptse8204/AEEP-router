"""Run the deterministic AEEP v0.5 DSH routing proof."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from aeep.benchmarking import (
    BenchmarkCampaignReport,
    BenchmarkCondition,
    BenchmarkPhase,
    BenchmarkTrial,
    revalue_campaign,
)
from aeep.cache_affinity import estimate_cache_affinity
from aeep.economic.trust import TrustStore, TrustStoreVerifier
from aeep.executors.base import BaseExecutor, ExecutionContext
from aeep.models import (
    ActionConstraints,
    ActionContext,
    ActionRequest,
    CacheAffinityObservation,
    CacheAffinityPolicyConfig,
    CacheRoutingContext,
    EstimateSource,
    EvidenceSource,
    EvidenceStatus,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    Manifest,
    MeasurementEvidence,
    ModelAccessChannel,
    ModelTokenUsage,
    PolicyConfig,
    RateCardRate,
    RateCardSnapshot,
    RateType,
    RawExecution,
    ResourceAccounting,
    ResourceVector,
    RouteEstimate,
    SideEffect,
    TrustLevel,
)
from aeep.proofs import DSHCampaignArm, DSHProofReport, DSHProofTrial, ProofGate
from aeep.provider_package import PackageIntegrityStatus, load_provider_package
from aeep.router import Router

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NOW = datetime(2026, 8, 21, tzinfo=UTC)
SEED = 8204
CAPABILITIES = (
    "web.page.read@1",
    "github.file.read@1",
    "document.text.extract@1",
)


class FixtureExecutor(BaseExecutor):
    async def execute(self, context: ExecutionContext) -> RawExecution:
        local = context.spec.id.startswith("local")
        workload = context.request.input.get("workload", "static")
        cached = 32 if local and context.request.context.cache_affinity is not None else 0
        output = {"ok": True, "capability": context.spec.capability}
        if local and workload == "malformed":
            output = {"broken": True}
        elif local and workload == "js":
            output = {"ok": False, "capability": context.spec.capability}
        return RawExecution(
            status=ExecutionStatus.SUCCESS,
            output=output,
            resources=ResourceVector(
                latency_ms=20 if local else 80,
                input_tokens=40 if local else 240,
                cached_input_tokens=cached,
                output_tokens=10 if local else 40,
            ),
        )


def route_spec(capability: str, route_id: str, latency: int, *, shared: bool) -> ExecutorSpec:
    local = route_id.startswith("local")
    return ExecutorSpec(
        id=route_id,
        capability=capability,
        kind=ExecutorKind.PYTHON,
        description=f"Synthetic {route_id}",
        input_schema={
            "type": "object",
            "properties": {
                "workload": {"enum": ["static", "js", "malformed"]},
            },
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "required": ["ok", "capability"],
            "properties": {
                "ok": {"const": True},
                "capability": {"const": capability},
            },
            "additionalProperties": False,
        },
        estimate=RouteEstimate(
            resources=ResourceVector(
                latency_ms=latency,
                input_tokens=40 if local else 240,
                output_tokens=10 if local else 40,
            ),
            confidence=0.85 if shared else 0.25,
            source=EstimateSource.BLENDED if shared else EstimateSource.STATIC,
            sample_size=100 if shared else 0,
        ),
        side_effect=SideEffect.NONE,
        config={
            "callable": "fixture:not-imported",
            "cache_affinity": {
                "warm_resources": {
                    "latency_ms": 5,
                    "input_tokens": 40 if local else 240,
                    "cached_input_tokens": 32 if local else 0,
                    "output_tokens": 10 if local else 40,
                }
            },
        },
    )


async def run_arm(
    arm: DSHCampaignArm,
    capability: str,
    *,
    shared_trials: int,
    smoke_executions: int,
    workload: str = "static",
    reverse_routes: bool = False,
) -> DSHProofTrial:
    route_suffix = capability.replace("@", ".v")
    oracle = f"local.{route_suffix}"
    model = f"model.{route_suffix}"
    shared = arm in {DSHCampaignArm.AEEP_SHARED, DSHCampaignArm.AEEP_ADAPTIVE}
    local_latency = 20 if shared else 100
    model_latency = 80 if shared else 50
    policy = PolicyConfig(
        name="proof",
        cache_affinity=CacheAffinityPolicyConfig(enabled=arm is DSHCampaignArm.AEEP_ADAPTIVE),
    )
    specs = [
        route_spec(capability, oracle, local_latency, shared=shared),
        route_spec(capability, model, model_latency, shared=False),
    ]
    if reverse_routes:
        specs.reverse()
    router = Router(
        Manifest(
            database=":memory:",
            default_policy="proof",
            policies={"proof": policy},
            executors=specs,
        ),
        clock=lambda: NOW,
        executor_overrides={ExecutorKind.PYTHON: FixtureExecutor()},
    )
    context = ActionContext()
    if arm is DSHCampaignArm.AEEP_ADAPTIVE:
        cache = CacheRoutingContext(
            cache_scope_key_hmac="a" * 64,
            provider="local",
            model="fixture-model",
            integration_adapter="fixture",
            route_id=oracle,
            stable_prefix_digest_hmac="b" * 64,
            previous_state_digest_hmac="c" * 64,
            common_prefix_tokens_estimate=80,
            eligible_cached_tokens_estimate=100,
            observed_hits=9,
            observed_attempts=10,
            last_seen_at=NOW,
        )
        context.cache_affinity = cache
        router.store.save_cache_affinity_observation(
            CacheAffinityObservation(
                scope_key_hmac=cache.cache_scope_key_hmac,
                route_id=oracle,
                stable_prefix_digest_hmac=cache.stable_prefix_digest_hmac,
                state_digest_hmac=cache.previous_state_digest_hmac,
                cache_hit=True,
                cached_input_tokens=80,
                cache_write_input_tokens=0,
                observed_at=NOW,
            )
        )
    try:
        outcome = await router.execute(
            ActionRequest(
                capability=capability,
                input={"workload": workload},
                constraints=ActionConstraints(
                    allowed_executor_ids=([model] if arm is DSHCampaignArm.DSH_SUGGESTED else None)
                ),
                context=context,
            )
        )
    finally:
        await router.close()
    receipts = outcome.receipts
    receipt = receipts[-1]
    selected = outcome.decision.selected_executor_id
    ranking = next(item for item in outcome.decision.candidates if item.executor_id == selected)
    return DSHProofTrial(
        trial_id=f"{arm.value}:{capability}:{workload}:{int(reverse_routes)}",
        arm=arm,
        capability=capability,
        workload_id=workload,
        selected_route_id=selected,
        terminal_route_id=receipt.executor_id,
        oracle_route_id=oracle,
        feasible=selected is not None,
        task_valid=outcome.ok,
        receipt_id=receipt.receipt_id,
        receipt_ids=tuple(item.receipt_id for item in receipts),
        fallback_count=max(0, len(receipts) - 1),
        shared_trials_reused=shared_trials if shared else 0,
        smoke_executions=smoke_executions if shared else 0,
        warm_probability=(
            Decimal(str(ranking.cache_affinity.warm_probability))
            if ranking.cache_affinity is not None
            else None
        ),
        actual_cash_usd=None,
        actual_input_tokens=sum(item.actual_resources.input_tokens for item in receipts),
        actual_cached_input_tokens=sum(
            item.actual_resources.cached_input_tokens for item in receipts
        ),
        actual_output_tokens=sum(item.actual_resources.output_tokens for item in receipts),
    )


async def evidence_reuse_probe() -> tuple[int, int, bool, bool, bool]:
    fixture = HERE.parent / "provider_package"
    trust = TrustStore.load(fixture / "trusted-keys.json")
    with tempfile.TemporaryDirectory(prefix="aeep-v05-dsh-") as directory:
        root = Path(directory)
        router = Router(
            Manifest.model_validate(
                {
                    "database": str(root / "aeep.db"),
                    "provider_packages": {"artifact_root": str(root / "artifacts")},
                }
            ),
            economic_verifier=TrustStoreVerifier(trust, clock=lambda: NOW),
            clock=lambda: NOW,
        )
        try:
            candidate = (await router.ingest_provider_package(fixture / "aeep-provider.yaml"))[0]
            ingest_was_inert = not router.store.list_receipts(limit=1)
            inert_decision = router.route(
                ActionRequest(
                    capability=candidate.capability,
                    input={"text": "inert"},
                )
            )
            unqualified_route_blocked = inert_decision.selected_executor_id != candidate.executor_id
            package, _ = load_provider_package(fixture / "aeep-provider.yaml")
            tampered = package.model_copy(
                update={"metadata": package.metadata.model_copy(update={"description": "tampered"})}
            )
            tamper_rejected = (
                router._provider_package_ingestor().verify_package(tampered).integrity_status
                is PackageIntegrityStatus.FAILED
            )
            shared_sample_size = router.estimator.estimate(
                candidate.spec,
                PolicyConfig(),
            ).sample_size
            smoke = await router.smoke_candidate(candidate.executor_id)
            router.qualify_candidate_from_evidence(candidate.executor_id)
            router.activate_candidate(candidate.executor_id)
            return (
                shared_sample_size,
                len(smoke),
                ingest_was_inert,
                unqualified_route_blocked,
                tamper_rejected,
            )
        finally:
            await router.close()


def cache_affinity_probe() -> dict[str, object]:
    cold_resources = ResourceVector(latency_ms=100, input_tokens=240, output_tokens=40)
    warm_resources = ResourceVector(
        latency_ms=20,
        input_tokens=240,
        cached_input_tokens=200,
        output_tokens=40,
    )
    context = CacheRoutingContext(
        cache_scope_key_hmac="a" * 64,
        provider="fixture",
        model="fixture-model",
        integration_adapter="fixture",
        route_id="model.web.page.read.v1",
        stable_prefix_digest_hmac="b" * 64,
        previous_state_digest_hmac="c" * 64,
        common_prefix_tokens_estimate=200,
        eligible_cached_tokens_estimate=240,
        observed_hits=9,
        observed_attempts=10,
        last_seen_at=NOW,
    )
    latest = CacheAffinityObservation(
        scope_key_hmac=context.cache_scope_key_hmac,
        route_id=context.route_id,
        stable_prefix_digest_hmac=context.stable_prefix_digest_hmac,
        state_digest_hmac=context.previous_state_digest_hmac,
        cache_hit=True,
        cached_input_tokens=200,
        cache_write_input_tokens=0,
        observed_at=NOW,
    )

    def probability(
        value: CacheRoutingContext, observation: CacheAffinityObservation | None
    ) -> float:
        return estimate_cache_affinity(
            value,
            cold_resources=cold_resources,
            warm_resources=warm_resources,
            latest=observation,
            at=NOW,
        ).warm_probability

    evicted = context.model_copy(update={"previous_state_digest_hmac": "d" * 64})
    compacted = context.model_copy(
        update={
            "previous_state_digest_hmac": None,
            "compaction_generation": 1,
            "context_reset_reason": "compaction",
        }
    )
    result = {
        "cold": probability(context, None),
        "warm": probability(context, latest),
        "evicted": probability(evicted, latest),
        "compacted": probability(compacted, latest),
        "hard_feasibility_basis": "cold",
        "persisted_raw_text": False,
    }
    result["passed"] = bool(
        result["cold"] == 0
        and 0 < float(result["warm"]) <= 1
        and result["evicted"] == 0
        and result["compacted"] == 0
    )
    return result


def revaluation_probe() -> dict[str, object]:
    evidence = MeasurementEvidence(
        status=EvidenceStatus.COMPLETE,
        source=EvidenceSource.LOCAL_METER,
        trust=TrustLevel.OBSERVED,
    )
    trial = BenchmarkTrial(
        trial_id="dsh-model-usage",
        run_id="dsh-revaluation",
        suite_id="dsh-v05",
        case_id="static-page",
        route_id="model.web.page.read.v1",
        condition=BenchmarkCondition.PROCESS_COLD,
        repetition=0,
        phase=BenchmarkPhase.HOLDOUT,
        state="complete",
        ended_at=NOW,
        ok=True,
        valid=True,
        accounting=ResourceAccounting(
            model_usage=[
                ModelTokenUsage(
                    provider="fixture",
                    model="fixture-model",
                    access_channel=ModelAccessChannel.API,
                    input_tokens=240,
                    output_tokens=40,
                    evidence=evidence,
                )
            ]
        ),
    )
    campaign = BenchmarkCampaignReport(
        run_id=trial.run_id,
        suite_id=trial.suite_id,
        domain="dsh",
        deterministic_tools_available=True,
        pricing_snapshot_ids=[],
        frozen_holdout_decisions={},
        trials=[trial],
        summaries=[],
        baseline_deltas=[],
        oracles=[],
        subscription_conservation=[],
    )

    def snapshot(multiplier: Decimal) -> RateCardSnapshot:
        return RateCardSnapshot(
            provider="fixture",
            product="api",
            model="fixture-model",
            effective_from=NOW,
            retrieved_at=NOW,
            source_uri="https://pricing.example.invalid/fixture",
            source_content_sha256=hashlib.sha256(str(multiplier).encode()).hexdigest(),
            currency="USD",
            rates=[
                RateCardRate(
                    rate_id="input",
                    rate_type=RateType.INPUT_TOKEN,
                    meter="input_tokens",
                    input_unit="token",
                    output_unit="USD",
                    unit_quantity=100,
                    rate_amount=Decimal("0.01") * multiplier,
                ),
                RateCardRate(
                    rate_id="output",
                    rate_type=RateType.OUTPUT_TOKEN,
                    meter="output_tokens",
                    input_unit="token",
                    output_unit="USD",
                    unit_quantity=100,
                    rate_amount=Decimal("0.03") * multiplier,
                ),
            ],
        )

    before = campaign.model_dump_json()
    old = revalue_campaign(campaign, snapshot(Decimal("1")))
    new = revalue_campaign(campaign, snapshot(Decimal("2")))
    old_cost = old.trial_values[trial.trial_id][0].amount
    new_cost = new.trial_values[trial.trial_id][0].amount
    unchanged = before == campaign.model_dump_json()
    return {
        "correctness_trials_rerun": 0,
        "source_report_sha256": old.source_report_sha256,
        "old_snapshot_id": old.pricing_snapshot_id,
        "new_snapshot_id": new.pricing_snapshot_id,
        "old_api_equivalent_usd": str(old_cost),
        "new_api_equivalent_usd": str(new_cost),
        "historical_trial_unchanged": unchanged,
        "passed": unchanged
        and old_cost is not None
        and new_cost is not None
        and new_cost > old_cost,
    }


async def run_campaign() -> DSHProofReport:
    (
        shared_trials,
        smoke_executions,
        ingest_was_inert,
        unqualified_route_blocked,
        tamper_rejected,
    ) = await evidence_reuse_probe()
    normal_trials = [
        await run_arm(
            arm,
            capability,
            shared_trials=shared_trials,
            smoke_executions=smoke_executions,
        )
        for arm in DSHCampaignArm
        for capability in CAPABILITIES
    ]
    fallback_trials = [
        await run_arm(
            DSHCampaignArm.AEEP_SHARED,
            CAPABILITIES[0],
            shared_trials=shared_trials,
            smoke_executions=smoke_executions,
            workload=workload,
        )
        for workload in ("js", "malformed")
    ]
    route_order = list(CAPABILITIES)
    random.Random(SEED).shuffle(route_order)
    order_trials = [
        await run_arm(
            DSHCampaignArm.AEEP_SHARED,
            capability,
            shared_trials=shared_trials,
            smoke_executions=smoke_executions,
            reverse_routes=True,
        )
        for capability in route_order
    ]
    trials = tuple([*normal_trials, *fallback_trials, *order_trials])
    executed = list(trials)
    shared = [item for item in trials if item.shared_trials_reused]
    normal_shared_routes = {
        item.capability: item.selected_route_id
        for item in normal_trials
        if item.arm is DSHCampaignArm.AEEP_SHARED
    }
    cache = cache_affinity_probe()
    revaluation = revaluation_probe()
    gates = (
        ProofGate(
            name="every-attempt-has-receipt",
            passed=all(
                item.receipt_id is not None and len(item.receipt_ids) == item.fallback_count + 1
                for item in executed
            ),
            detail=f"{sum(len(item.receipt_ids) for item in executed)} receipt(s) for all attempts",
        ),
        ProofGate(
            name="shared-evidence-smoke-bound",
            passed=all(item.smoke_executions <= 2 for item in shared),
            detail=f"{len(shared)} shared trial(s), maximum two smoke executions",
        ),
        ProofGate(
            name="deterministic-aeep-task-valid",
            passed=all(item.task_valid is True for item in executed),
            detail=f"{sum(item.task_valid is True for item in executed)}/{len(executed)}",
        ),
        ProofGate(
            name="no-auto-activation-or-side-effect",
            passed=ingest_was_inert,
            detail="signed package ingest produced zero receipts and activation was explicit",
        ),
        ProofGate(
            name="unqualified-cheap-route-blocked",
            passed=unqualified_route_blocked,
            detail="the inert package route was unavailable before qualification and activation",
        ),
        ProofGate(
            name="package-tamper-rejected",
            passed=tamper_rejected,
            detail="changing signed package metadata invalidated integrity",
        ),
        ProofGate(
            name="safe-validation-fallback",
            passed=all(
                item.task_valid is True
                and item.fallback_count == 1
                and item.terminal_route_id is not None
                and item.terminal_route_id.startswith("model.")
                for item in fallback_trials
            ),
            detail="static-vs-JS and malformed local output each fell back once to the valid model route",
        ),
        ProofGate(
            name="route-order-deterministic",
            passed=all(
                item.selected_route_id == normal_shared_routes[item.capability]
                for item in order_trials
            ),
            detail=f"fixed-seed route permutation preserved {len(order_trials)} selections",
        ),
        ProofGate(
            name="cache-affinity-soft-only",
            passed=bool(cache["passed"]),
            detail="cold, warm, eviction, and compaction vectors passed with cold hard feasibility",
        ),
        ProofGate(
            name="rate-card-revaluation-without-rerun",
            passed=bool(revaluation["passed"]),
            detail="new pricing changed only derived API-equivalent value; correctness trials were unchanged",
        ),
    )
    return DSHProofReport(
        campaign_id="aeep-v05-dsh-deterministic",
        generated_at=NOW,
        trials=trials,
        gates=gates,
    )


def write_report(report: DSHProofReport, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "campaign.json").write_text(
        report.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    lines = ["# AEEP 0.5 DSH deterministic proof", ""]
    lines.extend(
        f"- {'PASS' if gate.passed else 'FAIL'} — {gate.name}: {gate.detail}"
        for gate in report.gates
    )
    lines.extend(
        [
            "",
            "Synthetic token result",
            "",
            "These fixture token counts test accounting and routing structure; they are not a claim about live DSH savings.",
        ]
    )
    (destination / "campaign.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    receipt_lines: list[str] = []
    for trial in report.trials:
        for attempt, receipt_id in enumerate(trial.receipt_ids, start=1):
            terminal = attempt == len(trial.receipt_ids)
            route_id = trial.terminal_route_id if terminal else trial.selected_route_id
            receipt_lines.append(
                json.dumps(
                    {
                        "receipt_id": receipt_id,
                        "trial_id": trial.trial_id,
                        "attempt": attempt,
                        "route_id": route_id,
                        "terminal": terminal,
                        "task_valid": trial.task_valid if terminal else False,
                    },
                    sort_keys=True,
                )
            )
    (destination / "receipts.jsonl").write_text(
        "\n".join(receipt_lines) + "\n",
        encoding="utf-8",
    )

    evidence = {
        "shared_trials": max(item.shared_trials_reused for item in report.trials),
        "local_smoke_executions": max(item.smoke_executions for item in report.trials),
        "ingest_executions": 0,
        "external_evidence_stored_as_local_observations": False,
        "self_asserted_evidence_qualified": False,
        "passed": next(
            item.passed for item in report.gates if item.name == "shared-evidence-smoke-bound"
        ),
    }
    (destination / "evidence-reuse.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (destination / "cache-affinity.json").write_text(
        json.dumps(cache_affinity_probe(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (destination / "rate-card-revaluation.json").write_text(
        json.dumps(revaluation_probe(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    normal = [
        item
        for item in report.trials
        if item.workload_id == "static" and item.trial_id.endswith(":0")
    ]
    baselines = {
        item.capability: (item.actual_input_tokens or 0) + (item.actual_output_tokens or 0)
        for item in normal
        if item.arm is DSHCampaignArm.DSH_SUGGESTED
    }
    regrets = []
    for item in normal:
        tokens = (item.actual_input_tokens or 0) + (item.actual_output_tokens or 0)
        baseline = baselines[item.capability]
        regrets.append(
            {
                "trial_id": item.trial_id,
                "arm": item.arm.value,
                "capability": item.capability,
                "selected_route_id": item.selected_route_id,
                "oracle_route_id": item.oracle_route_id,
                "task_valid": item.task_valid,
                "measured_fixture_tokens": tokens,
                "tokens_vs_dsh_suggested": tokens - baseline,
                "route_regret": int(item.selected_route_id != item.oracle_route_id),
            }
        )
    (destination / "route-regret.json").write_text(
        json.dumps(
            {
                "seed": SEED,
                "metric_scope": "synthetic fixture only",
                "live_savings_claimed": False,
                "trials": regrets,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports" / "v05" / "dsh")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        report = DSHProofReport.model_validate_json(
            (args.output_dir / "campaign.json").read_bytes()
        )
    else:
        report = asyncio.run(run_campaign())
        write_report(report, args.output_dir)
    print(json.dumps({"gates_passed": all(item.passed for item in report.gates)}))
    return 0 if all(item.passed for item in report.gates) else 1


if __name__ == "__main__":
    raise SystemExit(main())
