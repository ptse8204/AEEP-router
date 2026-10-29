"""Analyze actual canonical development evidence and exercise admission restraint."""
from collections import defaultdict
import html
import json
from pathlib import Path

from aeep.assessment.reporting import paired_interval
from aeep.assessment.service import AssessmentService
from aeep.errors import ConfigurationError
from aeep.router import Router

HERE = Path(__file__).resolve().parent
BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')


def summarize(rows, cases):
    pairs = defaultdict(dict)
    for row in rows:
        assert row['arm'] not in pairs[row['case']]
        pairs[row['case']][row['arm']] = row
    arms = {}
    for arm in ('control', 'treatment'):
        selected = [row for row in rows if row['arm'] == arm]
        arms[arm] = {'trials': len(selected), 'verified_successes': sum(row['independent_grade'] is True for row in selected),
            'by_family': {family: {'trials': sum(cases[row['case']]['family'] == family for row in selected),
                'successes': sum(cases[row['case']]['family'] == family and row['independent_grade'] is True for row in selected)}
                for family in ('single-file-repair', 'multi-file-repair', 'contract-audit')},
            'agent_wall_seconds': sum(row['agent_wall_seconds'] for row in selected),
            'grading_wall_seconds': sum(row['verification_wall_seconds'] for row in selected),
            'provider_reported_input_plus_output_tokens': sum(usage['input_tokens'] + usage['output_tokens'] for row in selected for usage in row['raw_model_usage'])}
    complete = {identity: values for identity, values in pairs.items() if set(values) == {'control', 'treatment'}}
    differences = {identity: [float(values['treatment']['independent_grade']) - float(values['control']['independent_grade'])]
                   for identity, values in complete.items()}
    repositories = {identity: cases[identity]['repository'].casefold() for identity in complete}
    # Existing repository-grouped interval is exploratory. Degenerate success data cannot establish equivalence.
    success, interval = paired_interval(differences, 20, 71, repositories, alpha=0.05/3, success_rate=True)
    resources = {}
    for dimension in ('agent_wall_seconds', 'provider_reported_input_plus_output_tokens'):
        measured = {}
        for identity, values in complete.items():
            if not all(row['independent_grade'] is True and row['token_capture']['status'] == 'verified' for row in values.values()):
                continue
            if dimension == 'agent_wall_seconds':
                baseline, candidate = (values[arm]['agent_wall_seconds'] for arm in ('control', 'treatment'))
            else:
                baseline, candidate = (sum(usage['input_tokens'] + usage['output_tokens'] for usage in values[arm]['raw_model_usage'])
                                       for arm in ('control', 'treatment'))
            if baseline > 0:
                measured[identity] = [(baseline - candidate) / baseline]
        estimate, bounds = paired_interval(measured, 20, 71, repositories, alpha=0.05/3)
        resources[dimension] = {'both_successful_measured_pairs': len(measured),
            'median_paired_relative_reduction': estimate, 'exploratory_corrected_interval': bounds}
    return {'complete_pairs': len(complete), 'arms': arms,
        'paired_success_difference': success, 'exploratory_repository_grouped_success_interval': interval,
        'resource_comparisons': resources, 'exploratory_interval_alpha_per_dimension': 0.05/3,
        'candidate_instruction_loads': sum(row['arm'] == 'treatment' and row['candidate_loading']['instructions_loaded'] is True for row in rows),
        'candidate_use_unknown': sum(row['arm'] == 'treatment' and row['candidate_loading']['instructions_loaded'] is None for row in rows),
        'qualification': False, 'formal_admission_verdict': None, 'positive_selection_value': None,
        'provider_internal_meter_verified': False, 'cash_savings': None,
        'limits': ['Development evidence; no formal qualification or powered efficacy verdict.',
            'Seven cases per family and public-task contamination limit generalization.',
            'A degenerate bootstrap interval does not prove equivalence or absence of value.',
            'If21 independent repositories show no discordance,the one-sided95% bound on discordance is about13.3%;five percentage points is unresolved.',
            'Instruction loading does not establish semantic contribution. No historical missing data are backfilled.']}


def main():
    audit = json.loads((HERE / 'completion-audit.json').read_text())
    assert audit['passed'] and audit['engineering_journey_completed']
    cohort = json.loads((HERE / 'cohort.json').read_text())
    cases = {case['task_id']: case for case in cohort['cases']}
    summary = summarize(audit['rows'], cases)
    assert summary['complete_pairs'] == 21
    model = json.loads((HERE / 'model-result.json').read_text())
    router = Router.from_manifest(BASE / 'aeep.json')
    try:
        service = AssessmentService(router, BASE / '.aeep/assessments')
        canonical = service.repository.get('report', model['report_id'])
        assert canonical['qualification_passed'] is False
        before = list(router.store._connection.execute('SELECT * FROM assessment_admissions'))
        counters = list(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
        try:
            service.admit(model['report_id'])
        except ConfigurationError as exc:
            assert str(exc) == 'admission requires passed qualification and a measured benefit'
            refusal = str(exc)
        else:
            raise AssertionError('Unqualified development evidence was admitted')
        assert before == list(router.store._connection.execute('SELECT * FROM assessment_admissions'))
        assert counters == list(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
        summary['actual_admission_restraint'] = {'report_id': model['report_id'], 'refused': True,
            'reason': refusal, 'admissions_and_counters_unchanged': True,
            'positive_live_selection_or_general_correct_abstention_claim': False}
    finally:
        router.store.close()
    (HERE / 'analysis.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
    lines = ['# Repository usefulness development experiment', '',
        'Ordinary capable Codex versus the same environment plus optional Ponytail 4.10.0.', '',
        '| Arm | Verified successes | Agent seconds | Provider-reported input + output tokens |',
        '| --- | --- | --- | --- |']
    for arm, value in summary['arms'].items():
        lines.append(f"| {arm} | {value['verified_successes']}/{value['trials']} | {value['agent_wall_seconds']:.2f} | {value['provider_reported_input_plus_output_tokens']} |")
    lines += ['', f"Complete pairs: {summary['complete_pairs']}; paired success difference: {summary['paired_success_difference']}; positive instruction loads: {summary['candidate_instruction_loads']}.", '',
        'The actual admission API rejected this development report because qualification and measured benefit are required. No admission, activation or allowance changed. This establishes one restraint check; positive live selection benefit remains unproven.', '',
        *summary['limits'], '',
        'Production resource acceptance is separate. Task tokens and wall time above describe this experiment; they are not proposed infrastructure SLOs or monetary savings.', '',
        '[Canonical completion audit](completion-audit.json) · [Per-family analysis](analysis.json) · [Frozen plan](PLAN.md)']
    markdown = '\n'.join(lines) + '\n'
    (HERE / 'comparison.md').write_text(markdown)
    (HERE / 'comparison.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>AEEP usefulness development comparison</title><style>body{max-width:70rem;margin:2rem auto;padding:1rem;font:16px/1.6 system-ui}pre{white-space:pre-wrap}</style><main><pre>' + html.escape(markdown) + '</pre></main></html>')
    print(json.dumps({key: value for key, value in summary.items() if key not in ('arms', 'limits')}))


if __name__ == '__main__':
    main()
