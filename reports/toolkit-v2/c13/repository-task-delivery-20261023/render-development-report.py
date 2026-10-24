"""Describe audited development observations; do not manufacture a value verdict."""
import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def number(value):
    return 'unknown' if value is None else f'{value:,.2f}'


def main():
    audit = json.loads((HERE / 'completion-audit.json').read_text())
    assert audit['passed']
    rows = audit['rows']
    pairs = {}
    for row in rows:
        assert row['arm'] not in pairs.setdefault(row['case'], {})
        pairs[row['case']][row['arm']] = row
    complete = [pair for pair in pairs.values() if set(pair) == {'control', 'treatment'}]
    lines = [
        '# Real repository development comparison', '',
        f"{audit['verified_successes']}/{len(rows)} task repairs passed protected upstream grading. "
        f"{audit['verified_token_capture_chains']}/{len(rows)} retained token capture chains verified. "
        f"There are {len(complete)} complete task pairs. These are development observations; "
        'comparative usefulness and selection remain unqualified.', '',
        'The ordinary Codex agent and the same agent with optional Ponytail 4.10.0 used '
        'gpt-6-astra at medium effort, the same public tasks and the reviewed isolated '
        'worker environments. The existing AEEP AssessmentService, BenchmarkRunner, '
        'ContainerExecutor, Codex collector and protected upstream pytest suites ran '
        'the journey. No new evaluation engine was introduced.', '',
        '| Task | Arm | Independent grade | Agent wall seconds | Grading seconds | Input tokens | Cached input | Output tokens | Reasoning output | Ponytail instructions loaded |',
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |',
    ]
    for row in rows:
        usage = row['raw_model_usage'][0] if len(row['raw_model_usage']) == 1 else {}
        grade = {True: 'pass', False: 'fail', None: 'unknown'}[row['independent_grade']]
        loaded = 'yes' if row['candidate_loading']['instructions_loaded'] is True else 'unknown' if row['arm'] == 'treatment' else 'outside control'
        fields = [row['case'], row['arm'], grade, number(row['agent_wall_seconds']), number(row['verification_wall_seconds']), *[str(usage.get(key, 'unknown')) for key in ('input_tokens', 'cached_input_tokens', 'output_tokens', 'reasoning_output_tokens')], loaded]
        lines.append('| ' + ' | '.join(fields) + ' |')
    lines += ['',
        'Input includes cached input; output includes reasoning output. Do not add '
        'those subsets again. Counts remain provider reports with self-asserted trust. '
        'Capture verification checks the canonical journal, receipt and model usage '
        'agree; it does not independently verify the provider’s meter.', '',
        'Agent wall time is the canonical trial’s execution time, with protected '
        'grading reported separately. Worker setup and inspection are assessment '
        'overhead. Positive native skill-loading events establish instruction '
        'delivery, not semantic contribution. Missing events never prove non-use.', '',
        '## Interpretation', '',
        'The completed repairs establish that actual task delivery, returned patches, '
        'independent upstream grading, token capture and cleanup can work together '
        'on these three public repository tasks. A failed task, if present, remains '
        'a failed grade rather than an infrastructure pass.', '',
        'One observation per task and arm cannot establish a reliable performance '
        'benefit or a selection rule. These repositories were used for development '
        'and remain excluded from future holdouts. No candidate was admitted or '
        'activated. This run does not complete the required qualification, '
        'four-arm usefulness or native selection evaluations.', '',
        '## Separate accounting and operational evidence', '',
        f"The model component charged {audit['canonical_operations']} operations, "
        f"{audit['model_turns_charged']} model turns and "
        f"{number(audit['charged_operation_seconds'])} operation-seconds. "
        'Operation-seconds sum separately timed assessment operations, including '
        'overhead; overlapping wrappers are not unique elapsed host time. '
        'No cash charge was added to the grant. Actual provider-billed cash, '
        'cost per verified success and monetary savings remain unavailable.', '',
        f"Owned grader and model workers are absent: {audit['all_owned_graders_absent'] and audit['all_reviewed_model_workers_absent']}. "
        f"The existing proxy is restored stopped: {audit['proxy_restored_stopped']}.", '',
        'The 11 worker containment groups per role and three offline grader probes '
        'are infrastructure evidence. They do not validate comparative usefulness. '
        'Production resource acceptance remains separate and needs workload-derived '
        'thresholds. Placeholder zero CPU, memory and network resource fields are '
        'not measurements of zero consumption.', '',
        'Earlier failed attempts remain charged and unchanged: the first review '
        'used 15 operations / 65.09651541616768 seconds / zero turns; the next '
        'used 29 operations / 313.0355685814284 seconds / five ungraded turns. '
        'Those outcomes are not pooled into the corrected task pairs.', '',
        '## Evidence', '',
        '- [Canonical receipt, trial, journal, attempt and cleanup audit](completion-audit.json)',
        '- [Terminal integrated bundle result](bundle-execution-result.json)',
        '- [Original exact approved review](approval-bundle.json)',
        '- [Full model result](model-result.json)',
        '- [Fresh offline grader probes](grader-probes-result.json)',
        '- [Fresh worker and collector checks](collector-result.json)', '',
        f"Product source: `{audit['source_digest']}`. Results describe only these "
        'pinned versions and observations; no retrospective budget or criterion changes.', '',
    ]
    markdown = '\n'.join(lines)
    with (HERE / 'comparison.md').open('x') as stream:
        stream.write(markdown)
    # Use the same plain, escaped report presentation as the existing toolkit renderer.
    document = ('<!doctype html><html lang="en"><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>AEEP repository development evidence</title>'
                '<style>body{max-width:86rem;margin:2rem auto;padding:0 1rem;font:16px/1.6 system-ui}'
                'pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
                '<main><h1>AEEP repository development evidence</h1><pre>'
                + html.escape(markdown) + '</pre></main></html>\n')
    with (HERE / 'comparison.html').open('x') as stream:
        stream.write(document)
    print(json.dumps({'rows': len(rows), 'complete_pairs': len(complete), 'formal_value_or_selection_verdict': None}))


if __name__ == '__main__':
    main()
