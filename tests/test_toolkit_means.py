import pytest
from test_toolkit_reporting import bundle, family, modify


def observed(controls,treatments):
    base=bundle()
    runs=[]
    for index,(control,treatment) in enumerate(zip(controls,treatments,strict=True)):
        for run,value in zip(base.runs,(control,treatment),strict=True):
            runs.append(run.model_copy(update={'run_id':f'{run.arm}-{index}','task_sha256':f'{index:064x}',
                'agent_wall_seconds':value,'timing_source_ref':'a'*64}))
    return family(modify(base,runs))['metric_differences']['agent_wall_seconds']


def test_mean_and_median_show_different_long_tail_effects():
    stats=observed([10.,10.,1000.],[5.,5.,1000.])
    assert stats['mean_observed_control']==340
    assert stats['mean_observed_treatment']==pytest.approx(1010/3)
    assert stats['mean_control_minus_treatment']==pytest.approx(10/3)
    assert stats['relative_mean_control_minus_treatment']==pytest.approx((10/3)/340)
    assert stats['median_control_minus_treatment']==5
    assert stats['confidence_interval'] is None


def test_means_use_only_same_measured_pairs_and_zero_baseline_has_no_ratio():
    stats=observed([0.,100.,None],[5.,None,3.])
    assert stats['measured_pairs']==1 and stats['observed_pairs']==3
    assert stats['mean_observed_control']==0 and stats['mean_observed_treatment']==5
    assert stats['mean_control_minus_treatment']==-5
    assert stats['relative_mean_control_minus_treatment'] is None
    stats=observed([None],[3.])
    assert stats['mean_control_minus_treatment'] is None


def test_rendered_percentage_does_not_overflow_a_finite_relative_change():
    from aeep_toolkit.reporting import render, summarize
    base = bundle(agent_wall_seconds=1e308, timing_source_ref='a'*64)
    records = modify(base, [base.runs[0].model_copy(update={
        'agent_wall_seconds': 1., 'timing_source_ref': 'a'*64}), base.runs[1]])
    rendered = render(summarize(records), 'markdown')
    assert 'Infinity' not in rendered and 'inf%' not in rendered
    import re
    from decimal import Decimal
    percentage = re.search(r'relative mean difference ([^%]+)%', rendered)
    assert percentage is not None and Decimal(percentage[1]) == Decimal('-1e310')


def test_readable_report_shows_scope_success_difference_and_unknown_invocation():
    from aeep_toolkit.reporting import render, summarize
    records = bundle(verification='fail')
    summary = summarize(records)
    assert summary['candidate'] == records.candidate.model_dump(mode='json')
    assert summary['adapter'] == records.adapter.model_dump(mode='json')
    output = render(summary, 'markdown')
    assert 'https://example.org/fixture' in output
    assert 'Revision: ' + 'b'*40 in output
    assert '-100 percentage points; graded pairs: 1/1' in output
    assert '0 observed, 0 observed absent, 1 unknown' in output
    assert 'Value verdict: NOT_ASSESSED' in output
    assert 'treatment minus control: unknown' in render(summarize(bundle(verification='unknown', verification_ref=None)), 'html')
