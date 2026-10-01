"""Read-only allowances for the existing campaign's reservation stages."""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from ..benchmarking import AssessmentBenchmarkCondition, BenchmarkCondition
from ..errors import ConfigurationError
from .models import AssessmentPlan, AssessmentSetupCost, RecipeDefinition

if TYPE_CHECKING:
    from .service import AssessmentService


def campaign_allowances(service: AssessmentService, plan: AssessmentPlan, *,
                        operations_per_case: int, turns_per_case: int,
                        seconds_per_case: float, cash_per_case: Decimal | None,
                        remaining: dict[str, Any] | None) -> dict[str, Any]:
    """Full fresh schedule, not a prediction of actual use or permission to resume."""
    suite = plan.suite
    stages: list[dict[str, Any]] = []
    gaps: list[str] = []

    def add(stage: str, calls: int, seconds: float, *, upper_calls: int | None = None,
            operations: int | None = None, turns: int = 0, cash: Decimal | None = Decimal(0)) -> None:
        ceiling = calls if upper_calls is None else upper_calls
        stages.append(dict(stage=stage, calls_minimum=calls, calls_upper=ceiling,
            operations_upper=ceiling if operations is None else operations,
            model_turns=turns, elapsed_reservation_upper_seconds=seconds,
            cash_reservation_upper_usd=None if cash is None else str(cash)))

    repeats = len(suite.cases) * suite.repetitions
    fresh = sum(condition in {BenchmarkCondition.PROCESS_COLD,
        AssessmentBenchmarkCondition.ROUTER_FRESH, AssessmentBenchmarkCondition.FRESH_WORKER}
        for condition in suite.conditions)
    warm = len(suite.conditions) - fresh
    splits = len({case.split for case in suite.cases}) if suite.sequential_stages else 1
    assigned = repeats * len(suite.conditions)
    warmups = warm * splits
    route_count = len(suite.routes)
    add('trial', assigned * route_count, assigned * seconds_per_case,
        operations=assigned * operations_per_case, turns=assigned * turns_per_case,
        cash=None if cash_per_case is None else assigned * cash_per_case)
    add('warmup', warmups * route_count, warmups * seconds_per_case,
        operations=warmups * operations_per_case, turns=warmups * turns_per_case,
        cash=None if cash_per_case is None else warmups * cash_per_case)
    routers = 1 + (repeats * fresh + warmups) * route_count  # Includes preflight.
    add('router_setup', routers, routers * 30)
    add('grader_validation', 1, 30)
    add('report_generation', 1, 30)  # Reserved before the campaign, released last.
    recipe = RecipeDefinition.model_validate(service.repository.get('recipe', plan.recipe_digest))
    if recipe.extension is not None:
        from .extensions import bounded_batches
        extension = recipe.extension
        literals = [*extension.independent_fixtures, *extension.transformed_fixtures]
        reference_inputs = [fixture.input for fixture in literals] + [case.action.input for case in [*suite.cases, *suite.warmup_cases]]
        reference_calls = len(bounded_batches(reference_inputs)) if extension.truth_schema is not None else 1
        add('grader_reference', reference_calls,
            reference_calls * (float(extension.reference.config['timeout_seconds']) + 5))
        # Artifact output sizes and generated faults are unknown until reference execution.
        # At most ten built-in faults accompany each literal/screening answer.
        challenged = min(len(reference_inputs), len(literals) + 8)
        upper_calls = (len(reference_inputs) + challenged * (10 + len(extension.fault_outputs))
                       + sum(fixture.grader_output is not None for fixture in literals)
                       if extension.truth_schema is not None else 1)
        add('grader_probe', 1, upper_calls * (float(extension.grader.config['timeout_seconds']) + 5),
            upper_calls=upper_calls)
        grading_calls = (assigned + warmups) * route_count
        add('recipe_grading', 0, grading_calls * (float(extension.grader.config['timeout_seconds']) + 5),
            upper_calls=grading_calls)
    with service.router.store._lock:
        for identity in plan.setup_cost_ids:
            state = service.router.store._connection.execute(
                'SELECT state FROM assessment_operations WHERE id=?', (identity,)).fetchone()
            if state is None:
                cost = AssessmentSetupCost.model_validate(service.repository.get('setup_cost', identity))
                add(cost.stage, 1, max(cost.elapsed_seconds, .000001))
            elif state[0] != 'complete':
                gaps.append('setup accounting is indeterminate')
    try:
        ids, sources = service._cost_sources(plan, require_complete=False)
        ledger = service.repository.operation_ledger(plan.plan_id, ids, sources)
        prior = [dict(operation_id=item.operation_id, stage=item.stage,
                      state='complete' if item.elapsed_seconds is not None else 'reserved',
                      elapsed_seconds=item.elapsed_seconds,
                      reserved=item.reserved.model_dump(mode='json')) for item in ledger.operations]
        if any(item.plan_id == plan.plan_id and item.operation_id not in plan.setup_cost_ids
               for item in ledger.operations):
            gaps.append('campaign already started; this is a fresh-schedule bound, not a resume allowance')
        if any(item.elapsed_seconds is None for item in ledger.operations):
            gaps.append('linked operations remain uncertain; their reservations are retained')
    except ConfigurationError:
        prior = []
        gaps.append('preparation cost lineage is incomplete or belongs to another grant')
    if cash_per_case is None:
        gaps.append('trial cash upper bound is unavailable')
    total = dict(operations=sum(item['operations_upper'] for item in stages),
                 model_turns=sum(item['model_turns'] for item in stages),
                 elapsed_seconds=sum(item['elapsed_reservation_upper_seconds'] for item in stages),
                 cash_usd=None if cash_per_case is None else str(sum(
                     (Decimal(item['cash_reservation_upper_usd']) for item in stages), Decimal(0))))
    fits = None if remaining is None or gaps else all(
        Decimal(str(total[key])) <= Decimal(str(remaining[key])) for key in total)
    return dict(scope='fresh_campaign_reservations', stages=stages, upper_allowance=total,
        prior_operations=prior, gaps=gaps, fits_remaining=fits,
        authorization_changed=False, automatic_retries=0,
        explanation='Bounds cover the frozen campaign including setup, warm-ups, grading and reporting. '
        'They are reservation ceilings, not measured consumption or execution approval. Early failures '
        'can use less. Prior operations are already charged and are not added again. Preparation '
        'must finish before a plan is reviewed; unplanned future planning, conformance, reusable-tool '
        'construction and interventions require their own reviewed allowances. Production monitoring '
        'uses receipts and launches no comparison calls.')
