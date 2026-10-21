"""Selection software scoring; these cases are synthetic authority fixtures."""
import json

import pytest

from aeep.assessment.models import content_digest
from aeep.models import ActionRequest, PolicyConfig, RouteDecision
from aeep_toolkit.selection import (
    SelectionCase,
    SelectionEvaluation,
    from_route_decision,
    summarize_selection,
)

pytestmark = pytest.mark.assessment_contract


def evaluation():
    inventory = {'editing': '1' * 64, 'logs': '2' * 64}
    common = dict(inventory_sha256=content_digest(inventory), shared_environment_sha256='3' * 64,
        authority_sha256='4' * 64, model_settings_sha256='5' * 64)
    cases = []
    for name, eligible, useful, known in [('repair', ['editing'], ['editing'], True),
        ('tiny', ['editing'], [], True), ('drifted', [], [], True), ('unknown', ['logs'], [], False)]:
        cases.append(dict(case_id=name, task_sha256=content_digest({'task': name}), family=name,
            eligible=eligible, demonstrated_useful=useful, value_known=known,
            eligibility_ref='6' * 64, prior_value_ref='7' * 64 if known else None))
    decisions = []
    for policy, selections in [('static', ['editing'] * 4), ('aeep', ['editing', None, None, None]),
                                ('always-abstain', [None] * 4)]:
        for case, selected in zip(cases, selections, strict=True):
            decisions.append(dict(policy=policy, case_id=case['case_id'], selected=selected,
                decision_ref=content_digest({'policy': policy, 'case': case['case_id']}),
                task_verified=None, decision_wall_seconds=None))
    return SelectionEvaluation(evidence_kind='synthetic', plan_ref='8' * 64, inventory=inventory,
        **{key: value for key, value in common.items() if key != 'inventory_sha256'},
        policies={name: dict(definition_ref=content_digest({'policy': name}), **common)
            for name in ['static', 'aeep', 'always-abstain']}, cases=cases, decisions=decisions)


def test_selection_scores_safety_usefulness_and_abstention_separately():
    result = summarize_selection(evaluation())
    assert result['outcome'] == 'NOT_ASSESSED' and not result['admission_changed']
    static = result['policies']['static']['counts']
    assert static['useful_selections'] == 1 and static['unnecessary_selections'] == 1
    assert static['ineligible_selections'] == 2
    assert result['policies']['aeep']['counts']['correct_abstentions'] == 2
    assert result['policies']['always-abstain']['counts']['missed_applicable_value'] == 1
    assert result['policies']['aeep']['counts']['ungraded_tasks'] == 4
    assert result['policies']['aeep']['decision_time']['observed_total_seconds'] is None
    assert result['comparisons'][0]['graded_pairs'] == 0
    assert result['comparisons'][0]['success_rate_left_minus_right'] is None


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'different_inventory', 'different_authority',
    'different_model', 'different_environment', 'future_value', 'repeated_task', 'reused_decision', 'ungraded_success'])
def test_incomplete_unmatched_or_outcome_leaking_evaluations_are_rejected(change):
    data = evaluation().model_dump(mode='json')
    if change == 'missing':
        data['decisions'].pop()
    elif change == 'duplicate':
        data['decisions'].append(data['decisions'][0])
    elif change.startswith('different_'):
        field = {'different_inventory': 'inventory_sha256', 'different_authority': 'authority_sha256',
                 'different_model': 'model_settings_sha256', 'different_environment': 'shared_environment_sha256'}[change]
        data['policies']['static'][field] = '0' * 64
    elif change == 'future_value':
        data['cases'][0]['prior_value_ref'] = None
    elif change == 'repeated_task':
        data['cases'][1]['task_sha256'] = data['cases'][0]['task_sha256']
    elif change == 'reused_decision':
        data['decisions'][1]['decision_ref'] = data['decisions'][0]['decision_ref']
    elif change == 'ungraded_success':
        data['decisions'][0]['task_verified'] = True
    with pytest.raises(ValueError):
        SelectionEvaluation.model_validate(data)


def test_unknown_value_and_partial_overhead_are_not_zero():
    data = evaluation().model_dump(mode='json')
    data['decisions'][3]['selected'] = 'logs'
    data['decisions'][0]['decision_wall_seconds'] = 0.0
    data['decisions'][0].update(task_verified=False, verification_ref='9' * 64)
    summary = summarize_selection(SelectionEvaluation.model_validate(data))['policies']['static']
    assert summary['counts']['value_unknown_selections'] == 1
    assert summary['counts']['graded_tasks'] == 1 and summary['counts']['verified_successes'] == 0
    assert summary['decision_time'] == dict(measured=1, missing=3, observed_total_seconds=0.0)


def test_actual_route_decision_lineage_and_cli(tmp_path, capsys):
    from aeep_toolkit.cli import main

    decision = RouteDecision(action=ActionRequest(capability='assessment.text@1', input={'text': 'x'}),
        policy=PolicyConfig(), selected_executor_id='reviewed-edit', routing_overhead_ms=2)
    case = SelectionCase(case_id='repair', task_sha256=content_digest({'text': 'x'}), family='repair',
        eligible=['editing'], demonstrated_useful=['editing'], eligibility_ref='1' * 64,
        prior_value_ref='2' * 64, value_known=True)
    captured = from_route_decision(decision, policy='aeep', case=case,
        baseline_executor_id='native', capability_by_executor={'reviewed-edit': 'editing'})
    assert captured.selected == 'editing' and captured.decision_ref == content_digest(decision)
    assert captured.decision_wall_seconds == .002 and captured.task_verified is None
    decision.selected_executor_id = 'native'
    assert from_route_decision(decision, policy='aeep', case=case, baseline_executor_id='native',
        capability_by_executor={}).selected is None
    with pytest.raises(ValueError, match='frozen task'):
        from_route_decision(decision, policy='aeep', case=case.model_copy(update={'task_sha256': '0' * 64}),
            baseline_executor_id='native', capability_by_executor={})
    path = tmp_path / 'evaluation.json'
    path.write_text(evaluation().model_dump_json())
    assert main(['selection-report', '--evaluation', str(path)]) == 0
    assert json.loads(capsys.readouterr().out)['evidence_kind'] == 'synthetic'
