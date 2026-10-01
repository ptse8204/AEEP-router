"""Comparisons use distinct paired cases; repetitions never inflate qualification."""

from __future__ import annotations

import random
from collections import defaultdict
from statistics import mean, median
from typing import Any, Literal

from ..benchmarking import BenchmarkCampaignReport, BenchmarkPhase, BenchmarkTrial
from ..models import EvidenceStatus, ResourceAccounting, ResourceVector, TrustLevel
from .models import (
    AssessmentOperationLedger,
    AssessmentPlan,
    AssessmentReport,
    RecipeDefinition,
    content_digest,
)


def fit_report(
    plan: AssessmentPlan, recipe: RecipeDefinition, campaign: BenchmarkCampaignReport,
    *, ledger: AssessmentOperationLedger | None = None,
    _condition: str | None = None,
) -> AssessmentReport:
    condition = _condition or (plan.comparison.primary_condition if plan.comparison else None)
    families = {case.case_id: case.template_family for case in plan.suite.cases}
    selected = [
        trial
        for trial in campaign.trials
        if trial.route_id == plan.candidate_id and trial.phase == BenchmarkPhase.HOLDOUT
    ]
    cases = {trial.case_id for trial in selected}
    expected = {case.case_id for case in plan.suite.cases if case.split.value == "holdout"}
    failures = sum(
        trial.correctness_failed is True or (trial.correctness_failed is None and trial.ok and trial.valid is False)
        for trial in campaign.trials
        if trial.route_id == plan.candidate_id and trial.phase != BenchmarkPhase.SETUP
    )
    covered = [
        variation
        for variation in recipe.variations
        if any(case.case_id in cases and (case.variation == variation if plan.comparison else f"-{variation}-" in case.case_id) for case in plan.suite.cases)
    ]
    required_runs = len(expected) * plan.suite.repetitions * len(plan.suite.conditions)
    complete_positions = (
        {(trial.case_id, trial.condition.value, trial.repetition) for trial in selected}
        == {(case, condition.value, repetition) for case in expected for condition in plan.suite.conditions for repetition in range(plan.suite.repetitions)}
    )
    qualified = (
        not failures
        and len(cases) >= recipe.minimum_holdout_cases
        and cases == expected
        and len(selected) == required_runs
        and (plan.comparison is None or complete_positions)
        and all(trial.valid is True and trial.ok for trial in selected)
        and set(covered) == set(recipe.variations)
    )
    models_match = True
    incremental_managed = (plan.comparison is not None and plan.comparison.experiment is not None
                           and plan.comparison.candidate.host_config is not None)
    if plan.comparison and (plan.comparison.structure == "controlled_agent" or incremental_managed):
        controlled_runs = [trial for trial in campaign.trials if trial.phase == BenchmarkPhase.HOLDOUT and trial.route_id in {plan.candidate_id, plan.baseline_id}]
        models = {model for trial in controlled_runs for model in (trial.host_models or {}).values()}
        models_match = bool(controlled_runs) and all(trial.host_models for trial in controlled_runs) and len(models) == 1
        if incremental_managed and plan.comparison.experiment is not None:
            all_runs = [trial for trial in campaign.trials if trial.phase == BenchmarkPhase.HOLDOUT
                        and trial.route_id in {plan.candidate_id, plan.baseline_id, *(arm.executor_id for arm in plan.comparison.experiment.challengers)}]
            models_match &= all(trial.host_models for trial in all_runs) and len({model for trial in all_runs for model in (trial.host_models or {}).values()}) == 1
        qualified &= models_match
    paired: dict[tuple[str, str, int], dict[str, BenchmarkTrial]] = defaultdict(dict)
    for trial in campaign.trials:
        if (
            trial.phase == BenchmarkPhase.HOLDOUT
            and trial.valid is True
            and trial.ok
            and trial.route_id in {plan.candidate_id, plan.baseline_id}
            and models_match
            and (condition is None or trial.condition.value == condition)
        ):
            paired[(trial.case_id, trial.condition.value, trial.repetition)][trial.route_id] = trial
    differences: dict[str, list[float]] = defaultdict(list)
    for (case, _paired_condition, _rep), runs in paired.items():
        if len(runs) != 2:
            continue
        candidate, baseline = runs[plan.candidate_id], runs[plan.baseline_id]
        if candidate.wall_time_ms is not None and baseline.wall_time_ms is not None:
            differences[case].append(baseline.wall_time_ms - candidate.wall_time_ms)
    savings, interval = paired_interval(differences, recipe.minimum_paired_cases, plan.suite.seed, families if plan.comparison else None)
    reference_comparison: dict[str, float | None] = {}
    reference_preferred = False
    if plan.reference_id:
        by_case = {(trial.case_id, trial.condition, trial.repetition): trial for trial in campaign.trials if trial.route_id == plan.reference_id and trial.phase == BenchmarkPhase.HOLDOUT and trial.ok and trial.valid is True}
        comparison: dict[str, list[float]] = defaultdict(list)
        for trial in selected:
            if condition is not None and trial.condition.value != condition:
                continue
            reference = by_case.get((trial.case_id, trial.condition, trial.repetition))
            if reference is not None and trial.ok and trial.wall_time_ms is not None and reference.wall_time_ms is not None:
                comparison[trial.case_id].append(trial.wall_time_ms - reference.wall_time_ms)
        reference_saving, reference_interval = paired_interval(comparison, recipe.minimum_paired_cases, plan.suite.seed, families if plan.comparison else None)
        reference_comparison["reference_saves_wall_time_ms_vs_candidate"] = reference_saving if reference_interval else None
        reference_preferred = bool(reference_interval and reference_interval[0] > 0)
    useful = (
        qualified
        and len(differences) >= recipe.minimum_paired_cases
        and bool(interval)
        and interval[0] > 0
        and not reference_preferred
    )
    utility = None
    experiment = plan.comparison.experiment if plan.comparison else None
    if experiment is not None:
        utility = incremental_utility(plan, recipe, campaign, condition)
        useful = qualified and utility["benefit"] and utility["guardrails_passed"] and not utility["dominated"] and utility["complete"]
    outcome: Literal[
        "useful_within_scope", "no_measured_benefit", "unsuitable", "insufficient_evidence"
    ] = (
        "useful_within_scope"
        if useful
        else "unsuitable"
        if failures
        else "no_measured_benefit"
        if qualified and (utility["complete"] if utility is not None else interval)
        else "insufficient_evidence"
    )
    measurements = {trial.trial_id: native_measurements(trial) for trial in campaign.trials}
    paired_savings = {"wall_time_ms": savings if interval else None}
    intervals = {"wall_time_ms": interval} if interval else {}
    paired_counts = {"wall_time_ms": len(differences)}
    for key in sorted({key for item in measurements.values() for key in item}):
        metric_pairs: dict[str, list[float]] = defaultdict(list)
        for (case, _paired_condition, _rep), runs in paired.items():
            if len(runs) != 2:
                continue
            left = measurements[runs[plan.candidate_id].trial_id].get(key)
            right = measurements[runs[plan.baseline_id].trial_id].get(key)
            if left is not None and right is not None:
                metric_pairs[case].append(right - left)
        difference, bounds = paired_interval(
            metric_pairs, recipe.minimum_paired_cases, plan.suite.seed, families if plan.comparison else None
        )
        paired_counts[key] = len(metric_pairs)
        paired_savings[key] = difference if bounds else None
        if bounds:
            intervals[key] = bounds
    host_bindings: dict[str, str] = {}
    for executor_id in plan.route_fingerprints:
        route_ids = {route.route_id for route in plan.suite.routes if route.executor_id == executor_id or (route.workflow is not None and any(executor_id in (step.action.constraints.allowed_executor_ids or []) for step in route.workflow.steps))}
        trials = [item for item in campaign.trials if item.route_id in route_ids]
        observed = {item.host_runtime_digests.get(executor_id) for item in trials}
        if len(observed) == 1:
            digest = next(iter(observed))
            if digest is not None:
                host_bindings[executor_id] = digest
    report = AssessmentReport(
        schema_version="assessment.report.v3" if experiment else "assessment.report.v2" if plan.comparison else "assessment.report.v1",
        utility_evidence=utility,
        comparison=plan.comparison,
        feature_combinations=plan.feature_combinations,
        plan_digest=content_digest(plan),
        outcome=outcome,
        qualification_passed=qualified,
        distinct_holdout_cases=len(cases),
        distinct_paired_cases=len(differences),
        correctness_failures=failures,
        execution_failures=sum(not trial.ok for trial in campaign.trials if trial.route_id == plan.candidate_id and trial.phase != BenchmarkPhase.SETUP),
        tested_variations=covered,
        measured_usage={},
        paired_measurement_cases=paired_counts,
        paired_savings=paired_savings,
        savings_interval=intervals,
        break_even_uses={},
        campaign_digest=content_digest(campaign),
        operation_ledger_digest=content_digest(ledger) if ledger else None,
        host_runtime_digests=host_bindings,
        deterministic_reference_comparison=reference_comparison,
        explanations=[
            "Correctness counts distinct held-out cases; repetitions measure variability.",
            "Latency includes routing and grading. The interval resamples template families and cases.",
            "No cash, subscription or production savings are inferred from an unexecuted baseline.",
            "Assessment overhead is charged once; incomplete operations leave the total and break-even unknown."
            if ledger else "Only campaign costs are available; setup and planning costs have not been measured.",
        ],
    )

    if plan.comparison and _condition is None:
        report.condition_comparisons = {}
        for item in plan.suite.conditions:
            separate = fit_report(plan, recipe, campaign, ledger=ledger, _condition=item.value)
            report.condition_comparisons[item.value] = {"paired_savings": separate.paired_savings, "savings_interval": separate.savings_interval, "paired_measurement_cases": separate.paired_measurement_cases, "break_even_uses": separate.break_even_uses}
        report.explanations.append(f"Comparison structure: {plan.comparison.structure}; admission uses {'predeclared utility and guardrails' if experiment else 'wall time'} under {condition}. Conditions are never pooled.")
        if plan.comparison.structure == "workflow":
            report.explanations.append("Benefits apply to the complete reviewed workflow, not to the plugin alone.")
    if report.execution_failures:
        codes = sorted({code for trial in campaign.trials for code in trial.execution_failure_codes})
        report.explanations.append("Execution or environment failures are separate from incorrect output; no correctness conclusion is drawn from a missing result." + (" Host checks: " + ", ".join(codes) + "." if codes else ""))
    if not models_match:
        report.explanations.append("Controlled comparison requires the same resolved model in both arms; identity evidence is missing or differs.")
    if plan.pilot is not None:
        report.outcome = "insufficient_evidence"
        report.qualification_passed = False
        report.explanations.append("Timing pilot only: its cases cannot enter holdout or authorize admission.")
    apply_assessment_costs(report, campaign, ledger)
    return report


def apply_assessment_costs(report: AssessmentReport, campaign: BenchmarkCampaignReport, ledger: AssessmentOperationLedger | None) -> None:
    """Finalize measured costs after statistical report generation has been measured."""
    trials = [native_measurements(trial) for trial in campaign.trials]
    overhead = [item for item in ledger.operations if item.stage != "trial" or item.plan_id != ledger.plan_id] if ledger else []
    measurements = [resource_measurements(item.accounting or ResourceAccounting(), item.resources or ResourceVector()) for item in overhead]
    uncertain = bool(ledger and any(item.elapsed_seconds is None for item in ledger.operations))
    known_campaign_ms = sum(trial.wall_time_ms for trial in campaign.trials if trial.wall_time_ms is not None)
    complete_campaign = bool(campaign.trials) and all(trial.wall_time_ms is not None for trial in campaign.trials)
    campaign_ms = known_campaign_ms if complete_campaign else None
    uncertain |= not complete_campaign
    known_overhead_ms = sum((item.elapsed_seconds or 0) * 1000 for item in overhead)
    report.measured_usage.update(campaign_wall_time_ms=campaign_ms, known_campaign_wall_time_ms=known_campaign_ms, known_overhead_wall_time_ms=known_overhead_ms, assessment_wall_time_ms=None if uncertain else known_campaign_ms + known_overhead_ms)
    for field in ("routing_overhead_ms", "invocation_guard_ms"):
        values = [getattr(trial, field) for trial in campaign.trials]
        report.measured_usage[f"included_{field}"] = sum(values) if values and all(value is not None for value in values) else None
    savings = report.paired_savings.get("wall_time_ms")
    report.break_even_uses["wall_time_ms"] = (known_campaign_ms + known_overhead_ms) / savings if not uncertain and savings is not None and savings > 0 else None
    for key in sorted({key for item in [*trials, *measurements] for key in item}):
        known = [item[key] for item in trials if item.get(key) is not None]
        known_overhead = [item[key] for item in measurements if item.get(key) is not None]
        subtotal = sum(value for value in known if value is not None) if known else None
        overhead_total = sum(value for value in known_overhead if value is not None)
        complete = subtotal if len(known) == len(trials) else None
        total = complete + overhead_total if complete is not None and len(known_overhead) == len(overhead) and not uncertain else None
        report.measurement_coverage[key] = f"{len(known)}/{len(trials)}"
        report.measured_usage.update({f"known_campaign_subtotal.{key}": subtotal, f"campaign_total.{key}": complete, f"known_overhead_subtotal.{key}": overhead_total if known_overhead else None, f"assessment_total.{key}": total})
        savings = report.paired_savings.get(key)
        report.break_even_uses[key] = total / savings if total is not None and savings is not None and savings > 0 else None
    report.operation_ledger_digest = content_digest(ledger) if ledger else None


def paired_interval(
    differences: dict[str, list[float]], minimum: int, seed: int, template_families: dict[str, str | None] | None = None,
    *, alpha: float = 0.05,
    success_rate: bool = False,
) -> tuple[float | None, list[float]]:
    # Resample template families, then independent cases within each family.
    aggregate = mean if success_rate else median
    families: dict[str, list[float]] = defaultdict(list)
    for case, values in differences.items():
        family = template_families.get(case) if template_families is not None else case.rsplit("-", 1)[0]
        if family is None:
            return None, []
        families[family].append(aggregate(values))
    savings = aggregate([aggregate(values) for values in differences.values()]) if differences else None
    if len(differences) < minimum:
        return savings, []
    rng = random.Random(seed)
    groups = list(families.values())
    estimates = sorted(
        aggregate(
            [
                rng.choice(group)
                for group in rng.choices(groups, k=len(groups))
                for _ in range(len(group))
            ]
        )
        for _ in range(2000)
    )
    lower = max(0, int(len(estimates) * alpha / 2) - 1)
    upper = min(len(estimates) - 1, int(len(estimates) * (1 - alpha / 2)) - 1)
    return savings, [estimates[lower], estimates[upper]]


def incremental_utility(plan: AssessmentPlan, recipe: RecipeDefinition, campaign: BenchmarkCampaignReport,
                        condition: str | None) -> dict[str, Any]:
    """Intention-to-treat comparison; selection/invocation does not filter cases."""
    assert plan.comparison is not None and plan.comparison.experiment is not None
    experiment = plan.comparison.experiment
    policy = experiment.utility
    dimensions = sorted(set(policy.benefit_dimensions + policy.guardrail_dimensions))
    families = {case.case_id: case.template_family for case in plan.suite.cases}
    expected = {case.case_id for case in plan.suite.cases if case.split.value == "holdout"}
    runs: dict[str, dict[tuple[str, int], BenchmarkTrial]] = defaultdict(dict)
    duplicate = False
    for trial in campaign.trials:
        if trial.phase != BenchmarkPhase.HOLDOUT or trial.condition.value != condition:
            continue
        position = (trial.case_id, trial.repetition)
        duplicate |= position in runs[trial.route_id]
        runs[trial.route_id][position] = trial
    positions = {(case, rep) for case in expected for rep in range(plan.suite.repetitions)}
    compared_ids = [plan.baseline_id, *experiment.feasible_challengers]
    # Bonferroni bounds cover every declared metric/guardrail and challenger.
    alpha = policy.family_error_rate / max(1, len(dimensions) * (3 if experiment.stage == "aeep_value" else len(compared_ids)) * len(plan.suite.conditions))

    def value(trial: BenchmarkTrial, metric: str) -> float | None:
        if metric == "task_success":
            if trial.ok and trial.valid is True:
                return 1.0
            return 0.0 if trial.correctness_failed is True else None
        if not (trial.ok and trial.valid is True) and trial.correctness_failed is not True:
            return None
        return trial.wall_time_ms if metric == "wall_time_ms" else native_measurements(trial).get(metric)

    def compare(candidate_id: str, base_id: str) -> dict[str, Any]:
        measured: dict[str, Any] = {}
        for metric in dimensions:
            differences: dict[str, list[float]] = defaultdict(list)
            zero_regression = False
            for position in positions:
                candidate, base = runs[candidate_id].get(position), runs[base_id].get(position)
                if candidate is None or base is None:
                    continue
                left, right = value(candidate, metric), value(base, metric)
                if left is None or right is None:
                    continue
                if metric == "task_success":
                    difference = left - right
                elif right == 0:
                    zero_regression |= left > 0
                    if left > 0:
                        continue
                    difference = 0.0
                else:
                    difference = (right - left) / right
                differences[position[0]].append(difference)
            estimate, bounds = paired_interval(differences, recipe.minimum_paired_cases, plan.suite.seed, families, alpha=alpha, success_rate=metric == "task_success")
            measured[metric] = {"relative_saving": estimate if metric != "task_success" else None,
                                "success_gain": estimate if metric == "task_success" else None,
                                "interval": bounds, "distinct_pairs": len(differences),
                                "zero_baseline_regression": zero_regression}
        complete = (not duplicate and set(runs[candidate_id]) == positions and set(runs[base_id]) == positions
                    and all(trial.valid is True or trial.correctness_failed is True
                            for identity in (candidate_id, base_id) for trial in runs[identity].values())
                    and all(item["interval"] or item["zero_baseline_regression"] for item in measured.values()))
        benefit = any(measured[key]["interval"] and measured[key]["interval"][0] >= (
            policy.minimum_success_gain if key == "task_success" else policy.minimum_resource_benefit)
            for key in policy.benefit_dimensions)
        guardrails = all(not measured[key]["zero_baseline_regression"] and measured[key]["interval"]
                         and measured[key]["interval"][0] >= -policy.maximum_resource_regression
                         for key in policy.guardrail_dimensions)
        return {"metrics": measured, "complete": complete, "benefit": bool(benefit), "guardrails_passed": bool(guardrails)}

    primary = compare(plan.candidate_id, plan.baseline_id)
    challengers = {identity: compare(identity, plan.candidate_id) for identity in experiment.feasible_challengers}
    dominated = any(result["complete"] and result["benefit"] and result["guardrails_passed"]
                    and all(trial.ok and trial.valid is True for trial in runs[identity].values())
                    for identity, result in challengers.items())
    primary.update(challengers=challengers, dominated=dominated,
                   complete=primary["complete"] and all(result["complete"] for result in challengers.values()),
                   stage=experiment.stage, family_error_rate=policy.family_error_rate,
                   analysis="all_assigned_cases", candidate_selection_filter=False)
    if experiment.stage == "aeep_value":
        assert experiment.normal_host is not None
        primary["discovery_vs_normal"] = compare(plan.baseline_id, experiment.normal_host.executor_id)
        primary["complete"] &= primary["discovery_vs_normal"]["complete"]
    if experiment.stage == "qualification":
        primary["benefit"] = False  # Qualification is never comparative admission authority.
    if experiment.stage == "native_catalog":
        discovery_complete = all(trial.capability_discovery is not None and all(
            type(trial.capability_discovery.get(key)) is bool for key in ('exposed', 'retrieved', 'invoked'))
            for trial in runs[plan.candidate_id].values()) and bool(runs[plan.candidate_id])
        primary['discovery_complete'] = discovery_complete
        primary['complete'] &= discovery_complete
    return primary


def native_measurements(trial: BenchmarkTrial) -> dict[str, float | None]:
    return resource_measurements(trial.accounting, trial.actual_resources)


def resource_measurements(accounting: ResourceAccounting, resources: ResourceVector) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    currencies = {item.currency for item in accounting.cash.components}
    for currency in currencies:
        value = accounting.cash.actual_cash_cost(currency)
        result[f"cash.{currency}"] = float(value) if value is not None else None
    for usage in accounting.model_usage:
        for field in (
            "input_tokens",
            "cached_input_tokens",
            "cache_write_input_tokens",
            "output_tokens",
            "reasoning_output_tokens",
        ):
            key = f"model.{usage.provider}.{usage.model}.{usage.access_channel.value}.{field}"
            if key not in result:
                result[key] = 0
            if (
                usage.evidence.status != EvidenceStatus.COMPLETE
                or usage.evidence.trust not in {TrustLevel.OBSERVED, TrustLevel.VERIFIED}
                or result[key] is None
            ):
                result[key] = None
            else:
                result[key] = float(result[key] or 0) + getattr(usage, field)
    for subscription in accounting.subscription_usage:
        key = (
            f"subscription.{subscription.provider}.{subscription.resource_pool}.{subscription.unit}"
        )
        if key not in result:
            result[key] = 0
        if (
            subscription.source.status != EvidenceStatus.COMPLETE
            or subscription.source.trust not in {TrustLevel.OBSERVED, TrustLevel.VERIFIED}
            or subscription.consumed is None
            or result[key] is None
        ):
            result[key] = None
        else:
            result[key] = float(result[key] or 0) + float(subscription.consumed)
    # A legacy zero-default vector cannot prove that an uninstrumented dimension was zero.
    for field in ("cpu_ms", "memory_mb_seconds", "gpu_ms", "network_bytes"):
        value = getattr(resources, field)
        result[f"local.{field}"] = float(value) if value > 0 else None
    return result
