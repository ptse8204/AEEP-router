"""Budget previews count existing reservation paths; they authorize no execution."""
from __future__ import annotations

from decimal import Decimal

import pytest
from test_v08_assessment import setup_assessment

from aeep.assessment.budget import campaign_allowances
from aeep.assessment.models import AssessmentLimits
from aeep.benchmarking import AssessmentBenchmarkCondition, BenchmarkCondition

pytestmark = pytest.mark.assessment_lifecycle


async def test_preview_matches_fresh_campaign_ledger_without_double_charging(tmp_path):
    router, service, plan, _ = setup_assessment(tmp_path)
    try:
        before = service.budget_preview(plan.plan_id)
        allowance = before['campaign_allowance']
        assert allowance['fits_remaining'] is False  # Worst-case reservations exceed this fixture grant.
        assert before['minimum_trial_model_turns'] == 0
        assert allowance['upper_allowance']['operations'] == 569  # 282 trials + 283 routers + grader/report + two setup costs.
        assert not service.repository.operation_ledger(plan.plan_id).operations
        report = await service.run(service.enqueue(plan.plan_id))
        actual = service.repository.operation_ledger(plan.plan_id)
        assert sum(item.reserved.max_operations for item in actual.operations) == allowance['upper_allowance']['operations']
        assert sum(item.reserved.max_elapsed_seconds for item in actual.operations) == pytest.approx(allowance['upper_allowance']['elapsed_seconds'])
        after = service.budget_preview(plan.plan_id)
        assert after['campaign_allowance']['fits_remaining'] is None
        assert 'already started' in ' '.join(after['campaign_allowance']['gaps'])
        assert len(after['campaign_allowance']['prior_operations']) == len(actual.operations)
        assert after['remaining']['operations'] == before['remaining']['operations'] - len(actual.operations)
        assert report.operation_ledger_digest
    finally:
        await router.close()


async def test_warmups_and_workflow_members_count_each_stage_and_condition(tmp_path):
    router, service, original, _ = setup_assessment(tmp_path)
    try:
        plan = original.model_copy(deep=True)
        plan.suite.warmup_cases = [plan.suite.cases[0].model_copy(update={'case_id': 'separate'})]
        plan.suite.conditions = [BenchmarkCondition.ROUTER_WARM, AssessmentBenchmarkCondition.REUSED_WORKER,
                                 AssessmentBenchmarkCondition.FRESH_WORKER]
        plan.suite.repetitions = 2
        plan.suite.warmup_cases = [plan.suite.cases[0].model_copy(update={'case_id': 'separate'})]
        result = campaign_allowances(service, plan, operations_per_case=3, turns_per_case=2,
            seconds_per_case=35, cash_per_case=None, remaining=None)
        stages = {item['stage']: item for item in result['stages']}
        assert stages['warmup']['calls_upper'] == 12  # Two arms, two warm conditions, three stages.
        assert stages['warmup']['operations_upper'] == 18
        assert stages['warmup']['model_turns'] == 12
        assert stages['router_setup']['calls_upper'] == 577  # 1 preflight + 564 fresh + 12 reused.
        assert result['upper_allowance']['cash_usd'] is None and result['fits_remaining'] is None
        assert 'cash upper bound' in ' '.join(result['gaps'])
        plan.suite.sequential_stages = False
        fewer = campaign_allowances(service, plan, operations_per_case=3, turns_per_case=2,
            seconds_per_case=35, cash_per_case=None, remaining=None)
        assert next(item for item in fewer['stages'] if item['stage'] == 'warmup')['calls_upper'] == 4
    finally:
        await router.close()


async def test_uncertain_preparation_keeps_reservations_and_unknown_measurements(tmp_path):
    router, service, plan, _ = setup_assessment(tmp_path)
    try:
        service.repository.reserve(plan, 'uncertain', AssessmentLimits(max_operations=2,
            max_model_turns=0, max_elapsed_seconds=20), stage='planning')
        first = service.budget_preview(plan.plan_id)
        second = service.budget_preview(plan.plan_id)
        assert first == second
        assert first['remaining']['operations'] == 1998
        assert first['remaining']['elapsed_seconds'] == 19980
        allowance = first['campaign_allowance']
        assert allowance['fits_remaining'] is None
        assert allowance['prior_operations'][0]['elapsed_seconds'] is None
        assert allowance['prior_operations'][0]['reserved']['max_elapsed_seconds'] == 20
    finally:
        await router.close()


async def test_extension_preview_bounds_output_dependent_batches(tmp_path, monkeypatch):
    from test_v08_executable_recipes import definition

    from aeep.assessment.workbook import workbook_recipe
    router, service, plan, _ = setup_assessment(tmp_path)
    try:
        recipe = workbook_recipe()
        assert recipe.extension
        read = service.repository.get
        monkeypatch.setattr(service.repository, 'get', lambda kind, identity:
            recipe.model_dump(mode='json') if kind == 'recipe' else read(kind, identity))
        result = service.budget_preview(plan.plan_id)['campaign_allowance']
        stages = {item['stage']: item for item in result['stages']}
        assert stages['grader_reference']['calls_upper'] == 1
        assert stages['grader_probe']['calls_minimum'] == 1
        literal_count = len(recipe.extension.independent_fixtures) + len(recipe.extension.transformed_fixtures)
        literal_outputs = sum(f.grader_output is not None for f in [*recipe.extension.independent_fixtures, *recipe.extension.transformed_fixtures])
        assert literal_outputs == 4
        assert stages['grader_probe']['calls_upper'] == 141 + literal_count + literal_outputs + (literal_count + 8) * (10 + len(recipe.extension.fault_outputs))
        assert stages['recipe_grading']['calls_upper'] == 282
        assert stages['recipe_grading']['elapsed_reservation_upper_seconds'] == 282 * (recipe.extension.grader.config['timeout_seconds'] + 5)
        assert result['upper_allowance']['elapsed_seconds'] > 20000
        assert result['fits_remaining'] is False
        recipe = definition()
        exact = service.budget_preview(plan.plan_id)['campaign_allowance']
        assert next(item for item in exact['stages'] if item['stage'] == 'grader_probe')['calls_upper'] == 1
    finally:
        await router.close()


async def test_extension_warmup_uses_reviewed_case_grader(tmp_path, monkeypatch):
    from test_v08_executable_recipes import definition

    from aeep.assessment.extensions import callbacks, grader_name
    from aeep.validators import ValidationContext

    router, service, plan, _ = setup_assessment(tmp_path)
    try:
        warmup = plan.suite.cases[0].model_copy(deep=True)
        warmup.case_id = 'warmup'
        warmup.action.input = {'items': ['warmup-only']}
        warmup.validators[-1].config['expected'] = {'count': 1}
        plan.suite.warmup_cases = [warmup]
        observed = []
        async def invoke(_service, _plan, _spec, value, **options):
            observed.append((value, options))
            return {'valid': [True]}, .01
        monkeypatch.setattr('aeep.assessment.extensions.invoke', invoke)
        callback = callbacks(service, plan, definition())[grader_name(warmup.action.input, {'count': 1})]
        assert await callback(ValidationContext(input=warmup.action.input, output={'count': 1}))
        assert observed[0][1]['stage'] == 'recipe_grading'
        assert observed[0][0]['examples'][0]['expected'] == {'count': 1}
        preview = campaign_allowances(service, plan, operations_per_case=2, turns_per_case=0,
            seconds_per_case=20, cash_per_case=Decimal(0),
            remaining={'operations': 10000, 'model_turns': 10000, 'elapsed_seconds': 100000, 'cash_usd': '0'})
        assert preview['fits_remaining'] is True
    finally:
        await router.close()
