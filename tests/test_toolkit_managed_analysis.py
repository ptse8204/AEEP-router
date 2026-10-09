"""Synthetic canonical analysis checks; no host or efficacy proof."""
import pytest
from test_toolkit_managed import prepared, record

from aeep.errors import ConfigurationError
from aeep_toolkit import managed
from aeep_toolkit.reporting import render


@pytest.mark.asyncio
async def test_managed_analysis_retains_uncertainty_costs_and_expected_positions(tmp_path, monkeypatch):
    router,service,adapter,path,_=prepared(tmp_path,monkeypatch)
    try:
        report=record(service,adapter,path)
        monkeypatch.setattr(managed,'require_conformance',lambda *args,**kwargs:None)
        bundle=adapter.normalize(report.report_id)
        summary=managed.comparison_summary(adapter,bundle)
        analysis=summary['managed_analysis']
        assert analysis['outcome']=='insufficient_evidence'
        assert analysis['expected_trial_positions']>analysis['missing_trial_positions']>0
        assert analysis['expected_trial_positions']-analysis['missing_trial_positions']==3
        assert analysis['duplicate_trial_positions']==analysis['unexpected_trial_positions']==0
        assert analysis['measured_usage']==report.measured_usage
        assert analysis['savings_interval']==report.savings_interval
        assert summary['outcome']=='NOT_ASSESSED'
        assert {r.task_family for r in bundle.runs}=={adapter.plan.suite.cases[0].template_family}
        for fmt in ('markdown','html'):
            text=render(summary,fmt)
            for value in ('insufficient_evidence','Uncertainty intervals','Measurement coverage','Utility, guardrails','unavailable','Assessment resource break-even'):
                assert value in text
            assert report.campaign_digest in text and report.operation_ledger_digest in text
    finally:
        await router.close()

@pytest.mark.asyncio
@pytest.mark.parametrize('field,value',[
    ('paired_savings',{'wall_time_ms':1000000}),
    ('savings_interval',{'wall_time_ms':[100,200]}),
    ('paired_measurement_cases',{'wall_time_ms':999}),
    ('condition_comparisons',{}),
    ('distinct_paired_cases',999),
    ('correctness_failures',999),
    ('utility_evidence',{'benefit':True}),
    ('measurement_coverage',{'tokens':'100/100'}),
])
async def test_modified_statistics_rejected_even_with_same_inconclusive_verdict(tmp_path,monkeypatch,field,value):
    router,service,adapter,path,_=prepared(tmp_path,monkeypatch)
    try:
        report=record(service,adapter,path)
        report=report.model_copy(update={field:value})
        original=service.repository.get
        monkeypatch.setattr(service.repository,'get',lambda kind,key: report.model_dump() if kind=='report' else original(kind,key))
        with pytest.raises(ConfigurationError,match='statistics do not reproduce'):
            adapter.normalize(report.report_id)
    finally:
        await router.close()

@pytest.mark.asyncio
@pytest.mark.parametrize('field,value',[
    ('measured_usage',{'assessment_wall_time_ms':0}),
    ('break_even_uses',{'wall_time_ms':1}),
])
async def test_modified_costs_rejected(tmp_path,monkeypatch,field,value):
    router,service,adapter,path,_=prepared(tmp_path,monkeypatch)
    try:
        report=record(service,adapter,path).model_copy(update={field:value})
        original=service.repository.get
        monkeypatch.setattr(service.repository,'get',lambda kind,key: report.model_dump() if kind=='report' else original(kind,key))
        with pytest.raises(ConfigurationError,match='costs do not reproduce'):
            adapter.normalize(report.report_id)
    finally:
        await router.close()

@pytest.mark.asyncio
async def test_service_cost_lineage_downgrade_is_preserved(tmp_path,monkeypatch):
    router,service,adapter,path,_=prepared(tmp_path,monkeypatch)
    try:
        report=record(service,adapter,path)
        report.explanations.append('Preparation cost lineage is incomplete; known incurred usage is retained.')
        report.measured_usage['assessment_wall_time_ms']=None
        report.break_even_uses={key:None for key in report.break_even_uses}
        original=service.repository.get
        monkeypatch.setattr(service.repository,'get',lambda kind,key: report.model_dump() if kind=='report' else original(kind,key))
        monkeypatch.setattr(managed,'require_conformance',lambda *args,**kwargs:None)
        summary=managed.comparison_summary(adapter,adapter.normalize(report.report_id))
        assert summary['managed_analysis']['measured_usage']['assessment_wall_time_ms'] is None
    finally:
        await router.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('tamper', [False, True])
async def test_condition_costs_preserve_service_report_operation_timing(tmp_path, monkeypatch, tamper):
    from test_v08_comparisons import trial

    from aeep.assessment.models import (
        AssessmentLimits,
        AssessmentOperation,
        AssessmentOperationLedger,
        content_digest,
    )
    from aeep.assessment.reporting import apply_assessment_costs, fit_report
    from aeep.benchmarking import BenchmarkCampaignReport

    router, service, adapter, _path, _ = prepared(tmp_path, monkeypatch)
    try:
        trials = [trial(case.case_id, route, 1 if route == 'candidate' else 2)
                  for case in adapter.plan.suite.cases if case.split.value == 'holdout'
                  for route in ('candidate', 'baseline')]
        for item in trials:
            item.host_models = {item.route_id: 'synthetic-model'}
        campaign = BenchmarkCampaignReport(
            run_id='cost-timing', suite_id=adapter.plan.suite.suite_id,
            domain=adapter.plan.suite.domain, trials=trials,
            deterministic_tools_available=True, pricing_snapshot_ids=[],
            frozen_holdout_decisions={}, summaries=[], baseline_deltas=[],
            oracles=[], subscription_conservation=[])
        ledger = AssessmentOperationLedger(plan_id=adapter.plan.plan_id, operations=[
            AssessmentOperation(operation_id='report', plan_id=adapter.plan.plan_id,
                                stage='report', reserved=AssessmentLimits(max_operations=1, max_elapsed_seconds=1))])
        report = fit_report(adapter.plan, adapter.recipe, campaign, ledger=ledger)
        condition = next(iter(report.condition_comparisons))
        assert report.condition_comparisons[condition]['break_even_uses']['wall_time_ms'] is None
        ledger.operations[0].elapsed_seconds = 0.1
        apply_assessment_costs(report, campaign, ledger)
        fresh = fit_report(adapter.plan, adapter.recipe, campaign, ledger=ledger)
        assert fresh.condition_comparisons[condition]['break_even_uses']['wall_time_ms'] > 0
        if tamper:
            report.condition_comparisons[condition]['break_even_uses']['wall_time_ms'] = 999999
        service.repository.put('campaign', campaign.run_id, campaign)
        service.repository.put('operation_ledger', content_digest(ledger), ledger)
        service.repository.put('report', report.report_id, report)
        if tamper:
            with pytest.raises(ConfigurationError, match='condition costs do not reproduce'):
                adapter.normalize(report.report_id)
        else:
            adapter.normalize(report.report_id)
            assert adapter.details['assessment_analysis']['condition_comparisons'][condition]['break_even_uses']['wall_time_ms'] is None
    finally:
        await router.close()
