from __future__ import annotations

from decimal import Decimal

import pytest
from test_v08_assessment import setup_assessment

from aeep.assessment.recipes import shipped_recipe
from aeep.assessment.reporting import fit_report, native_measurements
from aeep.benchmarking import (
    AssessmentBenchmarkCondition,
    BenchmarkCampaignReport,
    BenchmarkPhase,
    BenchmarkTrial,
)
from aeep.models import (
    EvidenceStatus,
    MeasurementEvidence,
    ModelTokenUsage,
    ResourceAccounting,
    SubscriptionUsage,
)

pytestmark = pytest.mark.assessment_contract


def trial(case, route, wall=1):
    return BenchmarkTrial(
        trial_id=f"{case}-{route}",
        run_id="run",
        suite_id="suite",
        case_id=case,
        route_id=route,
        condition=AssessmentBenchmarkCondition.ROUTER_FRESH,
        repetition=0,
        phase=BenchmarkPhase.HOLDOUT,
        state="complete",
        ok=True,
        valid=True,
        wall_time_ms=wall,
    )


def test_missing_native_measurements_are_not_zero_or_mixed_between_models():
    value = trial("case", "candidate")
    assert native_measurements(value)["local.cpu_ms"] is None
    evidence = MeasurementEvidence(
        status=EvidenceStatus.COMPLETE, source="local_meter", trust="observed"
    )
    value.accounting = ResourceAccounting(
        model_usage=[
            ModelTokenUsage(
                provider="provider", model="m1", input_tokens=5, output_tokens=2, evidence=evidence
            )
        ],
        subscription_usage=[
            SubscriptionUsage(
                provider="provider",
                resource_pool="self",
                unit="turn",
                consumed=Decimal(1),
                source=evidence,
            )
        ],
    )
    measured = native_measurements(value)
    assert measured["model.provider.m1.unknown.input_tokens"] == 5
    assert measured["subscription.provider.self.turn"] == 1
    value.accounting.model_usage[0].evidence.status = EvidenceStatus.PARTIAL
    assert native_measurements(value)["model.provider.m1.unknown.input_tokens"] is None


async def test_reports_handle_losses_missing_pairs_failures_and_assessment_cost(tmp_path):
    router, _service, plan, _ = setup_assessment(tmp_path)
    try:
        cases = [case for case in plan.suite.cases if case.split.value == "holdout"]
        trials = [
            trial(case.case_id, route, 1 if route == "candidate" else 2)
            for case in cases
            for route in ("candidate", "baseline")
        ]
        campaign = BenchmarkCampaignReport(
            run_id="run",
            suite_id=plan.suite.suite_id,
            domain=plan.suite.domain,
            trials=trials,
            deterministic_tools_available=True,
            pricing_snapshot_ids=[],
            frozen_holdout_decisions={},
            summaries=[],
            baseline_deltas=[],
            oracles=[],
            subscription_conservation=[],
        )
        recipe = shipped_recipe("csv")
        report = fit_report(plan, recipe, campaign)
        assert report.outcome == "useful_within_scope" and report.distinct_paired_cases == 105
        assert report.break_even_uses["wall_time_ms"] == 315
        assert report.estimated_production_savings == {}
        assert report.paired_savings["local.cpu_ms"] is None
        reference_plan = plan.model_copy(update={"reference_id": "reference"})
        reference_campaign = campaign.model_copy(update={"trials": [*campaign.trials, *(trial(case.case_id, "reference", 0.1) for case in cases)]})
        reference_report = fit_report(reference_plan, recipe, reference_campaign)
        assert reference_report.outcome == "no_measured_benefit"
        assert reference_report.deterministic_reference_comparison["reference_saves_wall_time_ms_vs_candidate"] > 0
        for item in campaign.trials:
            if item.route_id == "candidate":
                item.wall_time_ms = 3
        assert fit_report(plan, recipe, campaign).outcome == "no_measured_benefit"
        campaign.trials[0].valid = False
        assert fit_report(plan, recipe, campaign).outcome == "unsuitable"
        campaign.trials[0].ok = False
        campaign.trials[0].correctness_failed = False
        campaign.trials[0].execution_failure_codes = ["protocol_frame_limit"]
        unavailable = fit_report(plan, recipe, campaign)
        assert unavailable.outcome == "insufficient_evidence"
        assert unavailable.correctness_failures == 0 and unavailable.execution_failures == 1
        assert any("protocol_frame_limit" in reason for reason in unavailable.explanations)
        campaign.trials = trials[:38]
        report = fit_report(plan, recipe, campaign)
        assert not report.qualification_passed
        assert report.paired_savings["wall_time_ms"] is None
        assert report.break_even_uses["wall_time_ms"] is None
    finally:
        await router.close()


def test_structure_choices_preserve_controlled_comparison_and_legacy_contracts(tmp_path):
    from aeep.assessment.comparison import choices
    from aeep.assessment.models import AssessmentSubject, content_digest
    from aeep.assessment.onboarding import host_spec
    from aeep.benchmarking import BenchmarkCase, BenchmarkSplit
    from aeep.models import ActionRequest, ExecutorSpec, ManagedHostInvocation

    subject = AssessmentSubject(kind="skill", location=str(tmp_path), dependency_digests={})
    baseline = host_spec("csv", tmp_path / "codex", tmp_path)
    candidate = baseline.model_copy(deep=True)
    candidate.id = "skill"
    candidate.config["invocation"] = {"mode": "skill", "skill_name": "example", "skill_path": str(tmp_path / "SKILL.md"), "skill_sha256": "0" * 64}
    candidate = ExecutorSpec.model_validate(candidate.model_dump())
    result = choices(subject, candidate, baseline)
    assert result["recommended"] == "controlled_agent"
    assert [entry["available"] for entry in result["choices"]] == [False, True, True]
    candidate.config["instructions"] = "Different task instructions"
    assert not choices(subject, candidate, baseline)["choices"][1]["available"]
    subject.declarations = {"missing": ["Skill runtime dependency requires a reviewed mapping: artifact tool"]}
    assert not choices(subject, candidate, baseline)["choices"][2]["available"]
    original = {"mode": "turn", "skill_name": None, "skill_path": None, "skill_sha256": None, "server": None, "tool": None, "tool_sha256": None}
    assert ManagedHostInvocation.model_validate(original).model_dump(mode="json") == original
    case = BenchmarkCase(case_id="old", split=BenchmarkSplit.HOLDOUT, action=ActionRequest(capability="test", input={}))
    assert "variation" not in case.model_dump()
    assert content_digest(case) == content_digest(case.model_dump(mode="json"))


async def test_selected_structure_is_reviewed_and_does_not_reset_budget(tmp_path):
    import pytest
    from test_v08_assessment import setup_assessment

    from aeep.assessment.models import AssessmentLimits, content_digest
    from aeep.errors import ConfigurationError

    router, service, plan, _grant = setup_assessment(tmp_path)
    try:
        service.repository.reserve(plan, "used", AssessmentLimits(max_operations=1, max_elapsed_seconds=1))
        service.repository.finish_operation("used", elapsed_seconds=0.1)
        before = tuple(router.store._connection.execute("SELECT * FROM assessment_grants").fetchone())
        replacement = service.select_structure(plan.plan_id, "workflow")
        assert replacement.plan_id != plan.plan_id
        assert replacement.suite.seed != plan.suite.seed
        assert replacement.comparison.structure == "workflow"
        assert content_digest(replacement.comparison) in replacement.definition_digests
        with pytest.raises(ConfigurationError, match="review"):
            service.enqueue(replacement.plan_id)
        after = tuple(router.store._connection.execute("SELECT * FROM assessment_grants").fetchone())
        assert after[2] == before[2] + 1
        assert after[3] == before[3]
        assert after[4] >= before[4]
        assert after[5] == before[5]
        assert service.budget_preview(plan.plan_id)["minimum_trial_model_turns"] == 0
        assert service.comparison_choices(replacement.plan_id)["selected"] == "workflow"
    finally:
        await router.close()


def test_structural_generators_and_independent_metamorphic_fixtures(tmp_path):
    from aeep.assessment.recipes import (
        features,
        generate_case,
        independent_cases,
        reference_csv,
        reference_search,
        reference_text,
    )
    from aeep.benchmarking import BenchmarkSplit

    for family, reference in [("csv", reference_csv), ("text", reference_text), ("search", reference_search)]:
        structural = set()
        for index in range(105):
            case, variation = generate_case(family, index, 42, BenchmarkSplit.HOLDOUT, fixture_root=tmp_path / family)
            assert case.variation == variation and case.template_family
            assert reference(**case.action.input) == case.validators[0].config["expected"]
            observed = features(family, case.action.input)
            if observed:
                structural.add(observed["structure"])
        assert len(structural) >= 4
        fixtures = independent_cases(family, tmp_path / f"independent-{family}")
        for case in fixtures:
            assert reference(**case.action.input) == case.validators[0].config["expected"]
        if family != "search":
            assert reference(**fixtures[0].action.input) == reference(**fixtures[1].action.input)


async def test_conditions_are_reported_separately_and_primary_is_frozen(tmp_path):
    from aeep.benchmarking import BenchmarkCondition

    router, _service, plan, _grant = setup_assessment(tmp_path)
    try:
        plan.suite.conditions.append(BenchmarkCondition.ROUTER_WARM)
        cases = [case for case in plan.suite.cases if case.split.value == "holdout"]
        trials = []
        for case in cases:
            for route in ("candidate", "baseline"):
                trials.append(trial(case.case_id, route, 10 if route == "candidate" else 20))
                warm = trial(case.case_id, route, 1000 if route == "candidate" else 1)
                warm.trial_id += "-warm"
                warm.condition = BenchmarkCondition.ROUTER_WARM
                trials.append(warm)
        campaign = BenchmarkCampaignReport(run_id="conditions", suite_id=plan.plan_id, domain=plan.suite.domain, trials=trials, deterministic_tools_available=True, pricing_snapshot_ids=[], frozen_holdout_decisions={}, summaries=[], baseline_deltas=[], oracles=[], subscription_conservation=[])
        report = fit_report(plan, shipped_recipe("csv"), campaign)
        assert report.paired_savings["wall_time_ms"] == 10
        assert report.condition_comparisons["router-warm"]["paired_savings"]["wall_time_ms"] == -999
        assert report.distinct_holdout_cases == 105
        assert report.distinct_paired_cases == 105
    finally:
        await router.close()


def test_historical_report_keeps_absent_failure_count_and_explicit_zero():
    from aeep.assessment.models import AssessmentReport, content_digest

    current = AssessmentReport(report_id='fixture', plan_digest='a' * 64, outcome='insufficient_evidence',
        qualification_passed=False, distinct_holdout_cases=0, distinct_paired_cases=0,
        correctness_failures=0, execution_failures=0, tested_variations=[], measured_usage={},
        paired_savings={}, break_even_uses={}, campaign_digest='b' * 64, explanations=[])
    explicit = current.model_dump(mode='json')
    assert explicit['execution_failures'] == 0
    assert content_digest(AssessmentReport.model_validate(explicit)) == content_digest(explicit)
    legacy = dict(explicit)
    del legacy['execution_failures']
    restored = AssessmentReport.model_validate(legacy)
    assert restored.execution_failures == 0
    assert content_digest(restored) == content_digest(legacy)
    changed = restored.model_copy(update={'execution_failures': 1})
    assert changed.model_dump(mode='json')['execution_failures'] == 1
    assert content_digest(changed) != content_digest(legacy)
