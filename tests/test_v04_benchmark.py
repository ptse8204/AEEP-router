from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from aeep.benchmarking import (
    BenchmarkCondition,
    BenchmarkSplit,
    EconomicBenchmarkRouteType,
    EconomicBenchmarkTrial,
    EconomicProofCampaignReport,
    EconomicWorkflowProofTrial,
    economic_settlement_oracles,
    evaluate_economic_proof,
    finalize_economic_proof,
    format_economic_proof_report,
)
from aeep.models import CurrencyAmount, EconomicEvidenceLevel

ROOT = Path(__file__).resolve().parents[1]


def money(value: str) -> CurrencyAmount:
    return CurrencyAmount(amount=Decimal(value), currency="USD")


def trial(
    route_id: str,
    *,
    captured: str | None,
    maximum: str | None = None,
    released: str | None = None,
    selected: bool = False,
    confirmed_free: bool = False,
    route_type: EconomicBenchmarkRouteType = EconomicBenchmarkRouteType.USAGE_PRICED_PROVIDER,
) -> EconomicBenchmarkTrial:
    settled = captured is not None
    maximum = maximum if maximum is not None else captured
    released = released if released is not None else "0" if settled else None
    prior = money("0") if confirmed_free else None
    return EconomicBenchmarkTrial(
        trial_id=f"trial-{route_id}",
        case_id="case-1",
        route_id=route_id,
        route_type=route_type,
        condition=BenchmarkCondition.PROCESS_COLD,
        split=BenchmarkSplit.HOLDOUT,
        repetition=0,
        task_valid=True,
        selected_by_aeep=selected,
        prepared_id=f"prepared-{route_id}" if settled else None,
        quote_id=f"quote-{route_id}" if settled else None,
        settlement_id=f"settlement-{route_id}" if settled else None,
        charge_id=f"charge-{route_id}" if settled else None,
        expected_cash=money(captured) if captured is not None else prior,
        maximum_cash=money(maximum) if maximum is not None else prior,
        reserved_cash=money(maximum) if maximum is not None else None,
        captured_cash=money(captured) if captured is not None else None,
        released_cash=money(released) if released is not None else None,
        cash_evidence_level=(
            EconomicEvidenceLevel.PAYMENT_SETTLEMENT
            if settled
            else EconomicEvidenceLevel.OPERATOR_ATTESTED
            if confirmed_free
            else EconomicEvidenceLevel.UNKNOWN
        ),
        preparation_latency_ms=Decimal("1.0"),
        quote_latency_ms=Decimal("2.0" if settled else "0"),
        execution_latency_ms=Decimal("3.0"),
        settlement_latency_ms=Decimal("1.0" if settled else "0"),
        total_wall_time_ms=Decimal("7.1" if settled else "4.1"),
    )


def workflow_proof() -> EconomicWorkflowProofTrial:
    return EconomicWorkflowProofTrial(
        workflow_id="prepared-hybrid-workflow",
        condition=BenchmarkCondition.PROCESS_COLD,
        split=BenchmarkSplit.HOLDOUT,
        repetition=0,
        task_valid=True,
        dependency_binding_verified=True,
        step_count=2,
        prepared_step_count=2,
        quoted_step_count=1,
        settled_step_count=1,
        dependency_input_bytes=14347,
        expected_cash=money("0.0040"),
        maximum_cash=money("0.0050"),
        reserved_cash=money("0.0050"),
        captured_cash=money("0.0038"),
        released_cash=money("0.0012"),
        cash_evidence_level=EconomicEvidenceLevel.PAYMENT_SETTLEMENT,
        preparation_latency_ms=Decimal("1"),
        quote_latency_ms=Decimal("1"),
        execution_latency_ms=Decimal("1"),
        settlement_latency_ms=Decimal("1"),
        total_wall_time_ms=Decimal("5"),
    )


def report(
    *trials: EconomicBenchmarkTrial,
    workflow_trials: tuple[EconomicWorkflowProofTrial, ...] = (),
) -> EconomicProofCampaignReport:
    return EconomicProofCampaignReport(
        campaign_id="deterministic-economic-evidence",
        domain="text-statistics",
        settlement_currency="USD",
        repetitions=1,
        generated_at=datetime(2026, 8, 14, tzinfo=UTC),
        trials=trials,
        workflow_trials=workflow_trials,
    )


def test_economic_trial_uses_exact_money_and_enforces_quote_bound() -> None:
    measured = trial(
        "usage-priced",
        captured="0.0038",
        maximum="0.0050",
        released="0.0012",
        selected=True,
    )
    payload = measured.model_dump_json()
    assert '"amount":"0.0038"' in payload
    assert '"amount":"0.0050"' in payload
    assert '"preparation_latency_ms":"1.0"' in payload

    with pytest.raises(ValidationError, match="binary floating-point"):
        EconomicBenchmarkTrial.model_validate(
            {**measured.model_dump(), "quote_latency_ms": 1.5}
        )
    with pytest.raises(ValidationError, match="signed maximum"):
        EconomicBenchmarkTrial.model_validate(
            {
                **measured.model_dump(),
                "captured_cash": money("0.0051"),
                "released_cash": money("0"),
            }
        )
    with pytest.raises(ValidationError, match="requires a signed maximum"):
        EconomicBenchmarkTrial.model_validate(
            {**measured.model_dump(), "maximum_cash": None}
        )


def test_oracle_uses_settlement_or_authoritative_confirmed_free_cost() -> None:
    unknown = trial(
        "subscription-unknown",
        captured=None,
        route_type=EconomicBenchmarkRouteType.SUBSCRIPTION_BASELINE,
    )
    selected = trial("hybrid", captured="0.0038", selected=True)
    expensive = trial("fixed", captured="0.0040")
    confirmed_free = trial(
        "confirmed-free",
        captured=None,
        confirmed_free=True,
        route_type=EconomicBenchmarkRouteType.LOCAL_PYTHON,
    )
    failed = trial("invalid-cheap", captured="0.0001").model_copy(
        update={"task_valid": False}
    )
    oracle = economic_settlement_oracles(
        (unknown, selected, expensive, confirmed_free, failed)
    )[0]
    assert oracle.selected_route_id == "hybrid"
    assert oracle.oracle_route_id == "confirmed-free"
    assert oracle.eligible_route_ids == ("confirmed-free", "fixed", "hybrid")
    assert oracle.distance_from_oracle_percent is None
    assert oracle.selected_within_10_percent is False


def test_economic_oracle_uses_holdout_trials_only() -> None:
    holdout = trial("holdout", captured="0.0040", selected=True)
    training = trial("training", captured="0.0001", selected=True).model_copy(
        update={"split": BenchmarkSplit.TRAINING, "repetition": 1}
    )

    oracles = economic_settlement_oracles((training, holdout))

    assert len(oracles) == 1
    assert oracles[0].selected_route_id == "holdout"


def test_economic_proof_reports_partial_release_and_unknown_without_claiming_zero() -> None:
    selected = trial(
        "hybrid",
        captured="0.0038",
        maximum="0.0050",
        released="0.0012",
        selected=True,
        route_type=EconomicBenchmarkRouteType.HYBRID,
    )
    fixed = trial("fixed", captured="0.0040")
    unknown = trial(
        "subscription-unknown",
        captured=None,
        route_type=EconomicBenchmarkRouteType.SUBSCRIPTION_BASELINE,
    )
    finalized = finalize_economic_proof(
        report(selected, fixed, unknown, workflow_trials=(workflow_proof(),))
    )
    proof = evaluate_economic_proof(finalized)
    assert proof.passed
    assert all(gate.passed for gate in proof.gates)
    rendered = format_economic_proof_report(finalized)
    assert "USD 0.0038" in rendered
    assert "USD 0.0012" in rendered
    unknown_line = next(line for line in rendered.splitlines() if "subscription-unknown" in line)
    assert "unknown" in unknown_line
    assert "USD 0" not in unknown_line


def test_economic_proof_requires_a_real_prepared_hybrid_workflow() -> None:
    selected = trial("hybrid", captured="0.0038", selected=True)
    fixed = trial("fixed", captured="0.0040")
    unknown = trial("subscription-unknown", captured=None)

    finalized = finalize_economic_proof(report(selected, fixed, unknown))

    workflow_gate = next(
        gate for gate in finalized.gates if gate.name == "prepared-hybrid-workflow"
    )
    assert workflow_gate.passed is False


def test_economic_proof_rejects_duplicate_trials_and_naive_time() -> None:
    item = trial("fixed", captured="0.0040")
    with pytest.raises(ValidationError, match="trial IDs"):
        report(item, item)
    with pytest.raises(ValidationError, match="timezone-aware"):
        EconomicProofCampaignReport(
            campaign_id="bad-clock",
            domain="test",
            settlement_currency="USD",
            repetitions=1,
            generated_at=datetime(2026, 8, 14),
            trials=(item,),
        )


def test_local_campaign_uses_real_prepared_execution_and_settlement(tmp_path: Path) -> None:
    environment = dict(os.environ)
    existing_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = str(ROOT / "src") + (
        os.pathsep + existing_path if existing_path else ""
    )
    process = subprocess.run(
        [
            sys.executable,
            str(ROOT / "examples/economic_evidence/campaign.py"),
            "--repetitions",
            "3",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    assert process.returncode == 0, process.stderr
    measured = EconomicProofCampaignReport.model_validate_json(
        (tmp_path / "report.json").read_bytes()
    )

    assert {trial.route_type for trial in measured.trials} == set(EconomicBenchmarkRouteType)
    selected = [trial for trial in measured.trials if trial.selected_by_aeep]
    assert len(selected) == 6
    assert all(trial.prepared_id is not None for trial in selected)
    paid_selected = [trial for trial in selected if trial.captured_cash is not None]
    free_selected = [trial for trial in selected if trial.captured_cash is None]
    assert paid_selected
    assert len(paid_selected) + len(free_selected) == len(selected)
    assert all(trial.quote_id is not None for trial in paid_selected)
    assert all(trial.settlement_id is not None for trial in paid_selected)
    assert all(trial.maximum_cash == money("0.0050") for trial in paid_selected)
    assert all(trial.reserved_cash == money("0.0050") for trial in paid_selected)
    assert all(trial.captured_cash == money("0.0038") for trial in paid_selected)
    assert all(trial.released_cash == money("0.0012") for trial in paid_selected)
    assert all(
        trial.cash_evidence_level is EconomicEvidenceLevel.PAYMENT_SETTLEMENT
        for trial in paid_selected
    )
    assert all(
        trial.quote_id is None
        and trial.settlement_id is None
        and trial.expected_cash == money("0")
        and trial.maximum_cash == money("0")
        and trial.reserved_cash is None
        and trial.released_cash is None
        and trial.cash_evidence_level is EconomicEvidenceLevel.OPERATOR_ATTESTED
        for trial in free_selected
    )
    holdout_selected = [
        trial for trial in selected if trial.split is BenchmarkSplit.HOLDOUT
    ]
    assert len(holdout_selected) == 2
    assert all(trial in free_selected for trial in holdout_selected)
    assert len(measured.workflow_trials) == 1
    workflow_trial = measured.workflow_trials[0]
    assert workflow_trial.task_valid
    assert workflow_trial.dependency_binding_verified
    assert workflow_trial.prepared_step_count == workflow_trial.step_count == 2
    assert workflow_trial.quoted_step_count == workflow_trial.settled_step_count == 1
    assert workflow_trial.maximum_cash == money("0.0050")
    assert workflow_trial.captured_cash == money("0.0038")
    assert workflow_trial.released_cash == money("0.0012")
    assert measured.hybrid_training_observations == 20
    assert len(measured.oracles) == 2
    assert all(oracle.oracle_route_id == "aeep-hybrid" for oracle in measured.oracles)
    assert all(
        oracle.eligible_route_ids
        == (
            "aeep-hybrid",
            "local-cli",
            "local-python",
            "usage-priced-reference",
        )
        for oracle in measured.oracles
    )
    assert all(oracle.selected_within_10_percent is True for oracle in measured.oracles)
    assert all(gate.passed for gate in measured.gates)
