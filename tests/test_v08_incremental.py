from __future__ import annotations

import pytest
from pydantic import ValidationError
from test_v08_assessment import setup_assessment
from test_v08_comparisons import trial

from aeep.assessment.comparison import arm
from aeep.assessment.models import (
    AssessmentComparison,
    DifferentialEnvironment,
    IncrementalExperiment,
    UtilityPolicy,
    content_digest,
)
from aeep.assessment.recipes import shipped_recipe
from aeep.assessment.reporting import fit_report, incremental_utility
from aeep.benchmarking import BenchmarkCampaignReport

pytestmark = pytest.mark.assessment_contract


def test_catalog_verification_uses_candidate_receipts_without_inventing_control_discovery():
    from aeep.assessment.verification import _candidate_discovery_verified
    from aeep.models import ExecutionReceipt, RouteEstimate

    candidate=trial('case','candidate')
    baseline=trial('case','baseline')
    facts={'exposed':True,'retrieved':False,'invoked':False}
    candidate.capability_discovery=facts.copy()
    receipts={}
    for item in (candidate,baseline):
        receipt=ExecutionReceipt(decision_id='decision-'+item.route_id,action_id='action-'+item.route_id,
            capability='assessment.csv@1',executor_id=item.route_id,executor_kind='host_managed',
            status='success',estimated=RouteEstimate(),metadata={'capability_discovery':facts.copy()} if item is candidate else {})
        receipts[receipt.receipt_id]=receipt
        item.receipt_ids=[receipt.receipt_id]
    campaign=BenchmarkCampaignReport(run_id='run',suite_id='suite',domain='csv',trials=[candidate,baseline],
        deterministic_tools_available=True,pricing_snapshot_ids=[],frozen_holdout_decisions={},
        summaries=[],baseline_deltas=[],oracles=[],subscription_conservation=[])
    assert _candidate_discovery_verified(campaign,'candidate',receipts)
    assert not _candidate_discovery_verified(campaign,'baseline',receipts)
    observed=receipts[candidate.receipt_ids[0]].metadata['capability_discovery']
    for value in (None,1,True):
        observed['retrieved']=value
        assert not _candidate_discovery_verified(campaign,'candidate',receipts)
    observed['retrieved']=False
    candidate.receipt_ids.append(baseline.receipt_ids[0])
    assert not _candidate_discovery_verified(campaign,'candidate',receipts)
    candidate.receipt_ids=['missing']
    assert not _candidate_discovery_verified(campaign,'candidate',receipts)
    assert not _candidate_discovery_verified(campaign,'absent',receipts)


def environment():
    return DifferentialEnvironment(shared_definition_digest='a' * 64,
        control_inventory={'python': 'b' * 64},
        treatment_inventory={'python': 'b' * 64, 'plugin': 'c' * 64},
        candidate_inventory={'plugin': 'c' * 64}, candidate_paths=['/opt/plugin'])


def test_differential_inventory_and_historical_contracts():
    value = environment()
    assert value.control_inventory['python'] == value.treatment_inventory['python']
    for update in ({'control_inventory': value.treatment_inventory},
                   {'treatment_inventory': {'plugin': 'c' * 64}},
                   {'candidate_aliases': ['python']}, {'candidate_paths': ['/opt/../worker/auth']}):
        with pytest.raises(ValidationError):
            DifferentialEnvironment.model_validate({**value.model_dump(), **update})
    with pytest.raises(ValidationError, match='only qualification'):
        IncrementalExperiment(stage='qualification', exposure='optional', environment=value,
            utility=UtilityPolicy(benefit_dimensions=['wall_time_ms'], guardrail_dimensions=['wall_time_ms']))
    old = AssessmentComparison(structure='direct', candidate={'executor_id':'a', 'fingerprint':'a'*64, 'dependencies':{}},
                               baseline={'executor_id':'b', 'fingerprint':'b'*64, 'dependencies':{}})
    assert 'experiment' not in old.model_dump()
    assert content_digest(old) == content_digest(old.model_dump())


async def test_incremental_compiler_and_multimetric_dominance(tmp_path):
    router, service, original, _grant = setup_assessment(tmp_path)
    try:
        baseline = router.registry.get(original.baseline_id)
        high = baseline.model_copy(update={'id': 'high'})
        reusable = baseline.model_copy(update={'id': 'reusable'})
        router.registry.register(high)
        router.registry.register(reusable)
        experiment = IncrementalExperiment(stage='marginal_value', exposure='optional', environment=environment(),
            utility=UtilityPolicy(benefit_dimensions=['wall_time_ms'], guardrail_dimensions=['wall_time_ms']),
            higher_compute=arm(high, []), reusable_tool=arm(reusable, []), reusable_artifact_digest='d'*64,
            reusable_build_operation_ids=['build'], qualification_report_digest='e'*64,
            feasible_challengers=['high', 'reusable'])
        from aeep.assessment.models import AssessmentEnvironment
        plan = service.propose(subject_id=original.subject_digest, family='csv', candidate_id=original.candidate_id,
            baseline_id=original.baseline_id, authorization_id=original.authorization_id,
            environment=AssessmentEnvironment.model_validate(service.repository.get('environment', original.environment_digest)),
            experiment=experiment)
        assert plan.schema_version == 'assessment.plan.v4'
        assert {route.route_id for route in plan.suite.routes} == {'candidate', 'baseline', 'high', 'reusable'}
        assert service.budget_preview(plan.plan_id)['minimum_trial_model_turns'] == 0
        cases = [case for case in plan.suite.cases if case.split.value == 'holdout']
        trials = [trial(case.case_id, route, wall) for case in cases
                  for route, wall in [('candidate', 50), ('baseline', 100), ('high', 80), ('reusable', 75)]]
        campaign = BenchmarkCampaignReport(run_id='run', suite_id=plan.plan_id, domain=plan.suite.domain,
            trials=trials, deterministic_tools_available=True, pricing_snapshot_ids=[], frozen_holdout_decisions={},
            summaries=[], baseline_deltas=[], oracles=[], subscription_conservation=[])
        report = fit_report(plan, shipped_recipe('csv'), campaign)
        assert report.schema_version == 'assessment.report.v3'
        assert report.outcome == 'useful_within_scope'
        assert report.utility_evidence['metrics']['wall_time_ms']['relative_saving'] == .5
        for item in campaign.trials:
            if item.route_id == 'high':
                item.wall_time_ms = 20
        assert fit_report(plan, shipped_recipe('csv'), campaign).outcome == 'no_measured_benefit'
        campaign.trials[-1].wall_time_ms = None
        # One missing measurement need not erase 104 complete independent pairs.
        assert fit_report(plan, shipped_recipe('csv'), campaign).utility_evidence['challengers']['reusable']['metrics']['wall_time_ms']['distinct_pairs'] == 104
        campaign.trials[-1].ok = False
        campaign.trials[-1].valid = None
        assert fit_report(plan, shipped_recipe('csv'), campaign).outcome == 'insufficient_evidence'
        campaign.trials[-1].ok, campaign.trials[-1].valid = True, True
        campaign.trials[-1].wall_time_ms = 75
        # Unknown metrics never become free resources; zero denominators never produce infinity.
        for item in campaign.trials:
            if item.route_id == 'baseline':
                item.wall_time_ms = 0
        assert not incremental_utility(plan, shipped_recipe('csv'), campaign, 'router-fresh')['guardrails_passed']
        for item in campaign.trials:
            item.wall_time_ms = 0
        assert incremental_utility(plan, shipped_recipe('csv'), campaign, 'router-fresh')['complete']
        campaign.trials.append(campaign.trials[0])
        assert not incremental_utility(plan, shipped_recipe('csv'), campaign, 'router-fresh')['complete']
        campaign.trials.pop()
        from aeep.benchmarking import BenchmarkPhase
        excluded = campaign.trials[0].model_copy(update={'phase': BenchmarkPhase.SETUP})
        campaign.trials.append(excluded)
        assert incremental_utility(plan, shipped_recipe('csv'), campaign, 'router-fresh')['complete']
        campaign.trials.pop()
        original_utility = experiment.utility
        plan.comparison.experiment.utility = UtilityPolicy(benefit_dimensions=['task_success'], guardrail_dimensions=['wall_time_ms'])
        assert incremental_utility(plan, shipped_recipe('csv'), campaign, 'router-fresh')['metrics']['task_success']['success_gain'] == 0
        campaign.trials[1].correctness_failed, campaign.trials[1].valid = True, False
        incremental_utility(plan, shipped_recipe('csv'), campaign, 'router-fresh')
        plan.comparison.experiment.utility = original_utility
        plan.comparison.experiment = plan.comparison.experiment.model_copy(update={'stage': 'native_catalog', 'catalog_definition_digest': 'a'*64, 'marginal_report_digest': 'b'*64})
        assert not incremental_utility(plan, shipped_recipe('csv'), campaign, 'router-fresh')['discovery_complete']
        for item in campaign.trials:
            item.capability_discovery = {'exposed': True, 'retrieved': False, 'invoked': False}
        assert incremental_utility(plan, shipped_recipe('csv'), campaign, 'router-fresh')['discovery_complete']
        plan.comparison.experiment = IncrementalExperiment(stage='qualification', exposure='required', environment=environment(), utility=original_utility)
        assert not incremental_utility(plan, shipped_recipe('csv'), campaign, 'router-fresh')['benefit']
        # Qualification schedules one required-invocation arm, without comparative authority.
        qualification = IncrementalExperiment(stage='qualification', exposure='required', environment=environment(), utility=original_utility)
        qualified_plan = service.propose(subject_id=original.subject_digest, family='csv', candidate_id=original.candidate_id,
            baseline_id=original.baseline_id, authorization_id=original.authorization_id,
            environment=AssessmentEnvironment.model_validate(service.repository.get('environment', original.environment_digest)),
            experiment=qualification)
        assert [route.route_id for route in qualified_plan.suite.routes] == ['candidate']
    finally:
        await router.close()


def test_four_arm_workbook_setup_pins_model_and_uses_actual_files():
    from test_v08_managed_workers import binding

    from aeep.assessment.onboarding import incremental_host_routes
    from aeep.assessment.workbook import workbook_recipe
    from aeep.errors import ConfigurationError
    from aeep.hosts.base import HostModel
    from aeep.models import ManagedHostInvocation

    control = binding()
    params = dict(recipe=workbook_recipe(),control_worker=control,
        treatment_worker=control.model_copy(update={'worker_id':'treatment'}),
        higher_worker=control.model_copy(update={'worker_id':'higher'}),
        reusable_worker=control.model_copy(update={'worker_id':'reusable'}),
        candidate_invocation=ManagedHostInvocation(mode='skill',skill_name='sheets',skill_path='/opt/plugin/SKILL.md',skill_sha256='a'*64),
        model=HostModel(id='observed-model',reasoning_efforts=('low','medium','high')),
        normal_effort='low',effort_order=('low','medium','high'),timeout_seconds=30,protocol_user_agent='observed-version')
    routes = incremental_host_routes(**params)
    configs = [route.managed_host_config() for route in routes]
    assert len(routes) == 4 and not routes[1].enabled
    assert {config.model_constraints.allowed_model_ids for config in configs} == {('observed-model',)}
    assert configs[0].artifact.input_name == 'input.xlsx'
    assert configs[0].instructions == configs[1].instructions == configs[2].instructions
    assert configs[1].invocation.exposure == 'optional'
    assert configs[2].reasoning_efforts == ('medium',) and configs[2].timeout_seconds == 60
    with pytest.raises(ConfigurationError,match='successor'):
        incremental_host_routes(**{**params,'normal_effort':'high'})
    with pytest.raises(ConfigurationError,match='observed'):
        incremental_host_routes(**{**params,'effort_order':('low','higher')})


def test_four_arm_search_requires_reviewed_roots(tmp_path):
    from test_v08_managed_workers import binding

    from aeep.assessment.onboarding import incremental_host_routes
    from aeep.hosts.base import HostModel
    from aeep.models import ManagedHostInvocation

    control = binding()
    params = dict(recipe=shipped_recipe('search'), control_worker=control,
        treatment_worker=control.model_copy(update={'worker_id':'treatment'}),
        higher_worker=control.model_copy(update={'worker_id':'higher'}),
        reusable_worker=control.model_copy(update={'worker_id':'reusable'}),
        candidate_invocation=ManagedHostInvocation(mode='skill',skill_name='search',skill_path='/opt/plugin/SKILL.md',skill_sha256='a'*64),
        model=HostModel(id='observed-model',reasoning_efforts=('low','medium')),
        normal_effort='low',effort_order=('low','medium'),timeout_seconds=30,protocol_user_agent='observed-version')
    with pytest.raises(ValueError, match='explicit roots'):
        incremental_host_routes(**params)
    routes = incremental_host_routes(**params, search_roots=(str(tmp_path),))
    assert len(routes) == 4
    assert all(route.required_capabilities == ('input_tree',) for route in routes)
    configs = [route.managed_host_config() for route in routes]
    assert all(config.input_tree == 'local_search_tree:1' for config in configs)
    assert all(config.assessment_adapter['read_only_roots'] == [str(tmp_path)] for config in configs)
    assert len({config.instructions for config in configs}) == 1
