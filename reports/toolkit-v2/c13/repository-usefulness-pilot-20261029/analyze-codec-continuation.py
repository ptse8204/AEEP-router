"""Report completed task pairs and actual admission refusal; no execution replay."""
from collections import defaultdict
import html
import importlib.util
import json
from pathlib import Path

from aeep.assessment.service import AssessmentService
from aeep.errors import ConfigurationError
from aeep.router import Router

HERE = Path(__file__).resolve().parent
BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')


def main():
    continuation = json.loads((HERE / 'codec-continuation-result.json').read_text())
    assert continuation['all_completed']
    amendment = json.loads((HERE / 'codec-definition-amendment.json').read_text())
    cohort = json.loads((HERE / 'cohort.json').read_text())
    cases = {case['task_id']: case for case in cohort['cases']}
    spec = importlib.util.spec_from_file_location('frozen_development_analysis', HERE / 'analyze-and-check-admission.py')
    analyzer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(analyzer)
    groups, rows, reports = {}, [], []
    for part in amendment['components']:
        target = Path(part['directory'])
        audit = json.loads((target / 'completion-audit.json').read_text())
        assert audit['passed'] and audit['engineering_journey_completed']
        summary = analyzer.summarize(audit['rows'], cases)
        assert summary['complete_pairs'] == len(part['case_ids'])
        groups[part['mode']] = summary
        rows.extend([{**row, 'codec_condition': part['mode']} for row in audit['rows']])
        reports.append(json.loads((target / 'model-result.json').read_text())['report_id'])
    pairs = defaultdict(dict)
    for row in rows:
        assert row['arm'] not in pairs[row['case']]
        pairs[row['case']][row['arm']] = row
        assert row['receipt_ref'] and row['token_capture']['status'] == 'verified'
        assert {usage['model'] for usage in row['raw_model_usage']} == {'gpt-6-astra'}
    assert len(pairs) == 19 and len(rows) == 38
    assert all(set(pair) == {'control', 'treatment'} for pair in pairs.values())
    result = {'status': 'DEVELOPMENT_ONLY', 'intended_case_slots': 21, 'complete_pairs': 19,
        'engineering_censored_cases': amendment['engineering_censored_started_cases'],
        'earlier_turns_charged_without_value_observations': 3,
        'verified_successes': {arm: sum(pair[arm]['independent_grade'] is True for pair in pairs.values()) for arm in ('control', 'treatment')},
        'candidate_only_successes': sum(pair['treatment']['independent_grade'] is True and pair['control']['independent_grade'] is False for pair in pairs.values()),
        'baseline_only_successes': sum(pair['control']['independent_grade'] is True and pair['treatment']['independent_grade'] is False for pair in pairs.values()),
        'by_family': {family: {arm: {'cases': sum(cases[identity]['family'] == family for identity in pairs),
            'verified_successes': sum(cases[identity]['family'] == family and pair[arm]['independent_grade'] is True for identity, pair in pairs.items())}
            for arm in ('control', 'treatment')} for family in ('single-file-repair', 'multi-file-repair', 'contract-audit')},
        'resource_results_by_codec_condition': groups,
        'resource_conditions_pooled': False, 'confidence_supported_resource_savings': None,
        'monetary_savings': None, 'qualification': False, 'positive_live_selection_benefit': None,
        'candidate_semantic_contribution_proven': False, 'rows': rows}
    router = Router.from_manifest(BASE / 'aeep.json')
    try:
        service = AssessmentService(router, BASE / '.aeep/assessments')
        before = list(router.store._connection.execute('SELECT * FROM assessment_admissions'))
        counters = list(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
        refusals = []
        for report in reports:
            assert service.repository.get('report', report)['qualification_passed'] is False
            try:
                service.admit(report)
            except ConfigurationError as exc:
                assert str(exc) == 'admission requires passed qualification and a measured benefit'
                refusals.append({'report_id': report, 'reason': str(exc), 'admitted': False})
            else:
                raise AssertionError('Development report was admitted')
        assert before == list(router.store._connection.execute('SELECT * FROM assessment_admissions'))
        assert counters == list(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
        result['actual_admission_restraint'] = refusals
        result['admissions_and_counters_unchanged_by_check'] = True
        result['final_grant_counters'] = counters
    finally:
        router.store.close()
    with (HERE / 'comparison-analysis.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    wins, losses = result['candidate_only_successes'], result['baseline_only_successes']
    successes = result['verified_successes']
    lines = ['# Repository usefulness development comparison', '',
        f"Ordinary Codex: **{successes['control']}/19** verified successes. Optional Ponytail4.10.0: **{successes['treatment']}/19**.", '',
        f'Candidate-only successes: {wins}. Baseline-only successes: {losses}. Both arms used the same task and output contract within each pair.', '',
        'There were21intended slots. Two were censored for my controller artifact-format error;their three model turns remain charged and are excluded from capability performance. The remaining19original tasks were not replacements. Canonical records of the stopped attempt remain unchanged.', '',
        '## Task outcomes', '', '| Task | Family | Format | Ordinary | Optional Ponytail |', '| --- | --- | --- | --- | --- |']
    for record in cohort['cases']:
        identity = record['task_id']
        if identity not in pairs:
            lines.append(f'| {identity} | {record["family"]} | — | Engineering-censored | Engineering-censored |')
        else:
            pair = pairs[identity]
            grade = lambda arm: 'PASS' if pair[arm]['independent_grade'] else 'FAIL'
            lines.append(f'| {identity} | {record["family"]} | {pair["control"]["codec_condition"]} | {grade("control")} | {grade("treatment")} |')
    lines += ['', '## Resource observations by format', '',
        'These are descriptive task observations. Format conditions stay separate. Each has fewer than20pairs, so no confidence-supported resource savings claim is available. Provider-reported token captures are bound to canonical turns/receipts;the provider meter and monetary savings are not independently verified.', '',
        '| Format | Arm | Task successes | Agent seconds | Input + output tokens | Positive Ponytail instruction loads |',
        '| --- | --- | --- | --- | --- | --- |']
    for mode, summary in groups.items():
        for arm, value in summary['arms'].items():
            loads = summary['candidate_instruction_loads'] if arm == 'treatment' else 'not applicable'
            lines.append(f'| {mode} | {arm} | {value["verified_successes"]}/{value["trials"]} | {value["agent_wall_seconds"]:.2f} | {value["provider_reported_input_plus_output_tokens"]} | {loads} |')
    lines += ['', '## What the evidence supports', '',
        'The counts above describe performance and instruction loading on these selected public maintenance tasks. Loading does not prove semantic contribution. Public-task contamination is unknown;the sample is small and the controller correction introduced explicit attrition. No formal qualification or broad usefulness verdict follows.', '',
        'The actual synchronous AEEP admission API rejected both canonical development reports because passed qualification and measured benefit are required. Admissions and allowances stayed unchanged. That establishes this evidence-bound restraint check;positive live selection benefit and correct abstention on every task remain unproven.', '',
        'The frozen8/28/105campaign and all thresholds remain. Resource acceptance and concrete human controls are separate open gates. No candidate was admitted or activated;release remains unauthorized.', '',
        '## Evidence', '',
        '- [Full comparison analysis](comparison-analysis.json)',
        '- [Stopped-attempt canonical reconciliation](stopped-accounting-audit.json)',
        '- [Plain-profile canonical audit](../repository-usefulness-plain-20261029/completion-audit.json)',
        '- [Gzip-profile canonical audit](../repository-usefulness-gzip-20261029/completion-audit.json)',
        '- [Exact controller correction](codec-control-review.json)',
        '- [Original frozen plan and authority](PLAN.md)', '']
    markdown = '\n'.join(lines)
    (HERE / 'comparison.md').write_text(markdown)
    # Keep the portable report self-contained and escaped, using the existing report presentation.
    (HERE / 'comparison.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AEEP repository usefulness development evidence</title><style>body{max-width:90rem;margin:2rem auto;padding:1rem;font:16px/1.6 system-ui}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><main><h1>AEEP repository usefulness development evidence</h1><pre>' + html.escape(markdown) + '</pre></main></html>')
    print(json.dumps({key: value for key, value in result.items() if key not in ('rows', 'resource_results_by_codec_condition', 'by_family')}))


if __name__ == '__main__':
    main()
