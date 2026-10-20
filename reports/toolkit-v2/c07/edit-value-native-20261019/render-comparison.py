"""Render verified comparison data; no models, new statistics or admission."""
from collections import Counter, defaultdict
import html
import json
from pathlib import Path
from statistics import median
import sys

OUT = Path(__file__).parent
LABELS = {'ordinary': 'Ordinary agent', 'optional_candidate': 'Optional Ponytail',
          'higher_compute': 'Higher effort', 'reusable_tool': 'Optional generated tool'}


def number(value):
    return 'unknown' if value is None else f'{value:,.2f}'


def percent(value):
    return 'unknown' if value is None else f'{value * 100:.2f}%'


def middle(values):
    known = [v for v in values if v is not None]
    return median(known) if known else None


def table(headers, rows):
    escaped = lambda row: ''.join('<td>' + html.escape(str(x)) + '</td>' for x in row)
    markup = '<div class="table"><table><thead><tr>' + ''.join('<th scope="col">' + html.escape(x) + '</th>' for x in headers) + '</tr></thead><tbody>'
    markup += ''.join('<tr>' + escaped(row) + '</tr>' for row in rows) + '</tbody></table></div>'
    text = '| ' + ' | '.join(headers) + ' |\n| ' + ' | '.join('---' for _ in headers) + ' |\n'
    text += ''.join('| ' + ' | '.join(str(x).replace('|', '\\|') for x in row) + ' |\n' for row in rows)
    return markup, text


def main():
    data = json.loads((OUT / 'all-four-evidence.json').read_text())
    terminal = json.loads((OUT / 'value-result.json').read_text())
    source = json.loads((OUT / 'source-pin.json').read_text())
    records = data['records']
    assert len(records) == data['all_four_trials'] == 564 and data['normalization_gaps'] == 0
    assert terminal['proxy_restored'] and terminal['source_unchanged']
    assert len({r['condition'] for r in records}) == 1
    body, markdown = [], []

    def heading(text):
        body.append('<h2>' + html.escape(text) + '</h2>')
        markdown.append('## ' + text + '\n')

    def paragraph(text):
        body.append('<p>' + html.escape(text) + '</p>')
        markdown.append(text + '\n')

    def grid(headers, rows):
        markup, text = table(headers, rows)
        body.append(markup)
        markdown.append(text)

    verdict = {'insufficient_evidence': 'INCONCLUSIVE', 'no_measured_benefit': 'NO MEASURED BENEFIT',
               'unsuitable': 'UNSUITABLE', 'useful_within_scope': 'USEFUL WITHIN SCOPE'}[data['canonical_outcome']]
    title = 'Four-arm editing comparison'
    paragraph('Canonical verdict: ' + verdict + ' (' + data['canonical_outcome'] + '). No automatic admission or candidate activation occurred.')
    paragraph('This completed study contains 564 real Codex task runs on bounded synthetic recipes: 32 screening, 112 training and 420 held-out arm runs. The holdout contains 105 distinct cases, 35 per family, assigned to all four arms. The separate required-use qualification passed 141/141 tasks including 105 disjoint holdouts.')
    paragraph('Task correctness and runner wall time are measured. Token counts below come from protocol reports with provider_report/self_asserted provenance; their coverage is shown. They are excluded from strict observed/verified utility. The formal verdict retains the original token guardrails; this report cannot establish verified token savings or monetary savings.')
    heading('Held-out results for all four arms')
    holdout = [r for r in records if r['phase'] == 'holdout']
    assert len(holdout) == 420
    rows = []
    for arm, label in LABELS.items():
        group = [r for r in holdout if r['arm'] == arm]
        assert len(group) == 105
        trusted = sum(r['strict_native_measurements'].get('model.openai.gpt-6-astra.subscription.input_tokens') is not None for r in group)
        rows.append([label, str(sum(r['verification'] == 'pass' for r in group)) + '/105',
            number(middle([r['wall_seconds'] for r in group])),
            number(middle([(r['reported_tokens'] or {}).get('input_tokens') for r in group])),
            number(middle([(r['reported_tokens'] or {}).get('output_tokens') for r in group])), str(sum(all((r['reported_tokens'] or {}).get(k) is not None for k in ('input_tokens', 'output_tokens')) for r in group)) + '/105', str(trusted) + '/105'])
    grid(['Arm', 'Verified success', 'Median wall seconds', 'Median reported input tokens', 'Median reported output tokens', 'Reported input/output coverage', 'Trusted input coverage'], rows)
    paragraph('Wall time includes routing and preflight; independent grading is measured separately. Medians in this table describe the assigned runs. They do not replace paired confidence bounds. Cached input is included in input; reasoning is included in output. Unknown categories stay unknown.')
    heading('Task-family results')
    rows = []
    for s in data['family_phase_arm_summaries']:
        if s['phase'] == 'holdout':
            rows.append([s['family'], LABELS[s['arm']], str(s['verification'].get('pass', 0)) + '/' + str(s['assigned']),
                number(s['wall_seconds']['median']), number(s['reported_input_tokens']['median']), number(s['reported_output_tokens']['median'])])
    grid(['Family', 'Arm', 'Verified success', 'Median wall seconds', 'Median reported input tokens', 'Median reported output tokens'], rows)
    paragraph('Easy cases edit one literal while preserving another file. Multi-file cases rename Python NAME tokens across three files while preserving comments, strings, whitespace and notes. Adjacent cases count matching log lines without changing files. Seven template variants per family do not establish arbitrary repository debugging or general programming competence. Returned Python is inert data; its exact artifact is checked without executing it.')
    heading('Frozen paired analysis')
    utility = data['canonical_utility']
    comparisons = [('Optional Ponytail vs ordinary', utility)]
    for route, result in utility['challengers'].items():
        comparisons.append(('Higher effort vs Ponytail' if 'higher' in route else 'Generated tool vs Ponytail', result))
    rows = []
    for label, comparison in comparisons:
        for metric, result in comparison['metrics'].items():
            estimate = result['success_gain'] if metric == 'task_success' else result['relative_saving']
            interval = result['interval']
            rows.append([label, metric.replace('model.openai.gpt-6-astra.subscription.', ''), result['distinct_pairs'],
                percent(estimate), ' to '.join(percent(v) for v in interval) if interval else 'unavailable'])
    grid(['Comparison', 'Dimension', 'Distinct measured pairs', 'Paired estimate', 'Corrected interval'], rows)
    paragraph('Positive resource estimates favor the first arm; negative estimates favor the second. Task success uses percentage-point gain. These are the unchanged canonical hierarchical paired intervals, with correction across dimensions and comparators at family error rate 0.05. Admission needs a confidence-supported 10% resource benefit or five-point success gain, no more than 10% regression on other declared resource guardrails, complete evidence and no dominating feasible challenger. Missing trusted token intervals remain missing. Family tables above add no new admission tests.')
    heading('Optional access, failures and verification')
    candidate = [r for r in holdout if r['arm'] == 'optional_candidate']
    for key in ('exposed', 'retrieved', 'invoked'):
        paragraph('Candidate ' + key + ' fields in held-out receipts: ' + json.dumps(dict(Counter(str((r['discovery'] or {}).get(key)) for r in candidate)), sort_keys=True) + '. These recorded fields are distinct from causal benefit.')
    paragraph('Generated-tool files were verified in the immutable worker image. Its actual invocation is not separately instrumented; candidate-discovery fields on auxiliary arms do not measure generated-tool use. All assigned cases are included regardless of invocation.')
    grid(['Phase', 'Assigned arm runs', 'Verified passes', 'Failed or unknown verification'], [[label,
        len(group := [r for r in records if r['phase'] == phase]), sum(r['verification'] == 'pass' for r in group),
        sum(r['verification'] != 'pass' for r in group)] for phase, label in
        [('qualification', 'Screening'), ('measurement', 'Training'), ('holdout', 'Holdout')]])
    paragraph('All 564 canonical positions matched retained original receipts and source/cohort/conformance bindings. The standard managed export normalizes 282 primary trials; this supplement verifies the 282 auxiliary trials with the same existing receipt verifier and their exact frozen executor definitions. No canonical mapping, evidence trust or verdict is changed.')
    heading('Study costs and limits')
    costs = data['accounting_summary']
    paragraph(str(costs['operations']) + ' unique canonical operations are included in the supplemental editing-study ledger; ' + str(costs['unresolved_operations']) + ' have unresolved duration. Known charged operation seconds: ' + number(costs['charged_operation_seconds']['known_subtotal']) + '. These lifecycle intervals overlap, so their sum is not elapsed study wall time.')
    paragraph('The ledger includes linked preparation, failed readiness/profile predecessors, qualification, builder, training, image operations, the cancelled 46-run pre-holdout value attempt and post-report cleanup. The original grant and incurred counters were retained. This is not the cost of every historical experiment in the repository.')
    paragraph('One initial public nonroot metadata diagnostic lacked advance reservation. Its retained tool wall measurement was 0.112110291 seconds. It is recorded separately, not relabeled as pre-reserved. Engineering time and whole-host CPU, memory and energy are incompletely measured. Subscription consumption and a zero cash ceiling do not establish a dollar saving or verified break-even.')
    heading('Exact stack and study scope')
    paragraph('This study reuses the existing AEEP AssessmentService and BenchmarkRunner fallback selected in D40. agent-skill-eval 0.7.0 remains the tested scripted upstream path; its pinned Codex launch/usage contract remains unqualified. Waza mock and LangGraph fixture conformance are separate engineering evidence and supply no live benefit claim here.')
    paragraph('Candidate: ' + source['repository'] + ' at ' + source['revision'] + '. Ponytail 4.10.0 SKILL.md SHA-256: 1316a2f3f95741d2300b116fe0c2d81ce4a9568656ed0a62643f54aaf09957f2. Source rights are recorded as MIT assertions; developer ownership is not attested.')
    paragraph('Host versions: ' + ', '.join(sorted({r['host_version'] for r in records})) + '; model: ' + ', '.join(sorted({r['model'] for r in records})) + '. Ordinary, candidate and reusable arms use medium effort; higher-compute uses high effort and twice the 203-second task timeout. All four task prompts match. Workers are distinct and fresh; future cases, grader answers and shared writable state remain outside trial workers.')
    paragraph('Generated source SHA-256: 3360c74f1be036ba1e61ceb1ba3cf362d7258c11dbd2cbde5d7672fe4e38e2f6. It was built from the original 28 qualification training inputs and task contract before holdout, never expected outputs or candidate source. Its 28/28 training diagnostic on Python 3.13 does not establish general compatibility with the usage text\'s requested Python 3.11.')
    heading('Permissions, stop and recovery')
    paragraph('The exact reviews authorize the frozen workers/tool and finite model turns on the existing subscription grant, with a cash ceiling of zero and no new destinations. Codex owns authentication; the implementation agent did not inspect, copy or return its contents. No global installation, hosted telemetry, publication or release occurred. The study never admits the candidate automatically.')
    paragraph('The campaign is terminal. Its driver stopped the task-owned proxy and restored its prior stopped state; the approved 512 MiB/no-swap cap remains. No assessment dispatch is active for this completed plan. Generated images and evidence are retained; their deletion needs a separate exact cleanup decision. The current AEEP package, Waza and LangGraph test runtimes were removed by their recorded installation checks.')
    paragraph('For a future active assessment, the existing assess cancel command stops subsequent dispatch; a cancellation does not prove an in-flight effect was absent. Inspect canonical status and retained receipts before the existing assess recover operation. Never rerun a started driver, reset a grant or delete uncertain state. Ordinary routing continues independently of assessment workers. Private installation removal uses its exact installation record and reviewed digest; preserve changed environments and unrelated configuration.')
    heading('Evidence and remaining acceptance')
    paragraph('Plan: ' + data['plan_id'] + '; report: ' + data['report_id'] + '; executable source: ' + data['source_digest'] + '. Hashes bind local evidence; they are not signatures or independent attestation. Human comprehension, broader platform claims and publication require their own evidence or authorization.')
    links = [('Verified managed export', 'report/report.html'), ('All four arms and receipt references', 'all-four-evidence.json'),
             ('Supplemental cost ledger', 'study-accounting-ledger.json'), ('Cost scope and source hashes', 'accounting-scope.json'),
             ('Frozen plan', 'plan.json'), ('Exact execution review', 'value-execution-review.json'),
             ('Analysis plan', 'analysis-plan.json'), ('Terminal cleanup', 'value-result.json')]
    body.append('<ul>' + ''.join('<li><a href="' + html.escape(url, quote=True) + '">' + html.escape(label) + '</a></li>' for label, url in links) + '</ul>')
    markdown.extend('- [' + label + '](' + url + ')' for label, url in links)
    with (OUT / 'comparison.md').open('x') as handle:
        handle.write('# ' + title + '\n\n' + '\n'.join(markdown) + '\n')
    with (OUT / 'comparison.html').open('x') as handle:
        handle.write('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + title + '</title><style>body{font:16px/1.6 system-ui;max-width:78rem;margin:2rem auto;padding:0 1rem;color:#17202a}h1,h2{line-height:1.25}.table{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{border:1px solid #cbd0d6;padding:.5rem;text-align:left}th{background:#eef1f5}p{max-width:85ch;overflow-wrap:anywhere}a{color:#164a91}</style><main><h1>' + title + '</h1>' + ''.join(body) + '</main></html>\n')
    print(json.dumps({'report': str(OUT / 'comparison.html'), 'canonical_verdict': verdict, 'admission': False}))


if __name__ == '__main__':
    if sys.argv[1:] == ['--self-check']:
        markup, text = table(['Name'], [['<script>|unsafe</script>']])
        assert '<script>' not in markup and '&lt;script&gt;' in markup and '\\|' in text
        assert number(None) == percent(None) == 'unknown' and middle([None, 2, 4]) == 3
        print('Report escaping and missing-value self-checks passed; no evidence opened.')
    else:
        assert not sys.argv[1:]
        main()
