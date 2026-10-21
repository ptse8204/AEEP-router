"""Render retained capture checks; never dispatch a worker or change evidence."""
import hashlib
import json
from pathlib import Path

from markdown_it import MarkdownIt

from aeep.assessment.models import content_digest
from aeep.models import ExecutionReceipt
from aeep_toolkit.telemetry import bound_journal, candidate_loading, token_capture

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
OLD = OUT.parent / 'capture-local-tag-20261021'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    initial = json.loads((OLD / 'first-control-capture.json').read_text())
    corrected = json.loads((OLD / 'binding-diagnostic-result.json').read_text())
    audit = json.loads((OLD / 'final-diagnostic-audit.json').read_text())
    profile = json.loads((OUT / 'collector-result.json').read_text())
    resources = json.loads((OUT / 'completion-audit.json').read_text())
    positive = json.loads((OUT / 'positive-check-result.json').read_text())
    assert positive['passed'] and resources['passed']
    records = [('Initial control, grader binding failed', initial, 'Unknown: grader callback not found')]
    for trial, record in corrected['records'].items():
        actual = next(item for item in audit['binding-diagnostic-result']['trials'] if item['trial_id'] == trial)
        assert actual['state'] == 'complete' and actual['status'] == 'success' and not actual['correctness_failed']
        role = 'Treatment' if record['receipt']['metadata'].get('candidate_skill_sha256') else 'Control'
        records.append(('Corrected ' + role.lower(), record, 'Passed independent grader'))
    assert resources['trials'][0]['state']=='complete' and not resources['trials'][0]['correctness_failed']
    records.append(('Forced skill loading check',next(iter(positive['records'].values())),'Passed independent grader'))
    rows = []
    for label, record, quality in records:
        receipt = ExecutionReceipt.model_validate(record['receipt'])
        journal = bound_journal(receipt, record['journal'])
        tokens = token_capture(receipt, journal)
        loading = candidate_loading(receipt, journal, skill_sha256=receipt.metadata.get('candidate_skill_sha256'))
        assert tokens == record['tokens'] and loading == record['candidate']
        assert tokens['status'] == 'verified' and not tokens['provider_usage_independently_verified']
        usage = receipt.accounting.model_usage[0]
        rows.append({'label': label, 'receipt_id': receipt.receipt_id, 'receipt_digest': content_digest(receipt),
                     'executor': receipt.executor_id, 'input_tokens': usage.input_tokens,
                     'cached_input_tokens': usage.cached_input_tokens, 'cache_write_input_tokens': usage.cache_write_input_tokens,
                     'output_tokens': usage.output_tokens, 'reasoning_output_tokens': usage.reasoning_output_tokens,
                     'capture': tokens, 'candidate_loading': loading, 'task_verification': quality,
                     'metric_batches': receipt.metadata['catalog_metrics']['batches'],
                     'collector_delivery_complete': receipt.metadata['catalog_metrics']['delivery_complete']})
    assert len(rows)==4 and sum(row['candidate_loading']['instructions_loaded'] is True for row in rows)==1
    pending = sha(OUT / 'positive-operation-review.json')
    summary = {'source_commit': '77077562e1a63d45791c478066affba35dd8d10d',
               'source_digest': profile['source_digest'], 'actual_model_receipts': 4,
               'token_captures_verified': 4, 'charged_diagnostic_turn_reservations': 5,
               'preflight_skipped_reservations_retained': 1, 'required_profile_conformance_passed': profile['passed'],
               'required_profile_probe_groups_each': 11, 'positive_loading_observed': True,
               'instructions_loading_status': 'Verified instructions loaded in the forced positive probe; optional-exposure loading and semantic use remain unknown.',
               'candidate_nonuse_proven': False, 'independent_provider_metering': 'unverified',
               'task_correctness': {'passed': 3, 'ungraded': 1}, 'rows': rows,
               'historical_comparison': 'Unchanged INCONCLUSIVE; no historical replay or trust promotion.',
               'new_qualification_or_admission': False, 'proxy_stopped': not resources['proxy']['running'],
               'grant_after_last_observation': resources['grant_after'], 'completed_positive_review_sha256': pending,
               'pending_additional_task_turns': 0,
               'source_records': {str(p.relative_to(ROOT)): sha(p) for p in (
                   OLD / 'first-control-capture.json', OLD / 'binding-diagnostic-result.json',
                   OLD / 'final-diagnostic-audit.json', OLD / 'explicit-loading-result.json',
                   OUT / 'collector-result.json', OUT / 'boundary-result.json', OUT / 'completion-audit.json', OUT / 'positive-check-result.json', OUT / 'positive-operator-approval.json')}}
    (OUT / 'capture-status.json').write_text(json.dumps(summary, indent=2) + '\n')
    lines = ['# Capture checks after the policy correction', '',
             'Four completed real model turns have token counts matching their original execution journals and receipts. The corrected pair and the additional forced-loading probe passed independent grading. The first control remains ungraded because its diagnostic callback name was stale. A native positive event now verifies Ponytail instructions loaded in the forced probe.', '',
             '| Run | Input | Cached input | Cache-write input | Output | Reasoning output | Capture | Task check |',
             '|---|---:|---:|---:|---:|---:|---|---|']
    for row in rows:
        lines.append('| ' + ' | '.join(str(row[key]) for key in ('label', 'input_tokens', 'cached_input_tokens', 'cache_write_input_tokens', 'output_tokens', 'reasoning_output_tokens')) + ' | Verified | ' + row['task_verification'] + ' |')
    lines += ['', 'Cached input and reasoning output overlap their parent categories. These one-case diagnostic counts are not a savings estimate. Quantities remain provider-reported and self-asserted; matching retained evidence does not independently verify the provider meter.', '',
              '## Candidate loading', '',
              'The collector received real metric batches, and task commands could not access either collector endpoint. No positive candidate injection event was retained from the completed optional-exposure turns. Instruction loading and semantic use therefore remain unknown. Missing events do not prove non-use or complete export.', '',
              'The first typed positive probe was skipped before model dispatch: forcing the skill changed runtime identity, and the boundary check rejected the old identity. Its turn reservation remains charged. A fresh model-free inspection now passes all 11 probe groups in each worker, including collector denial, and binds the required treatment identity 3d13ce70b6385daea011d4432654f3e40c0e54d6f427c4627170e6c5b3833097.', '',
              '## Completed positive loading check', '',
              'The operator explicitly approved the additional one-turn review ' + pending + '. That fresh check passed with the exact required runtime identity and reviewed skill. A native codex.skill.injected event reports status=ok and invoke_type=explicit; the minimized snapshot is bound to this receipt and journal. All five reservations remain charged: four completed model turns and one preflight skip. No new model authorization is pending.', '',
              'The positive injection establishes instructions loaded in this forced diagnostic. It does not establish voluntary selection, semantic contribution or benefit. The optional two-turn pair was not dispatched. The original 564-task comparison and its INCONCLUSIVE verdict remain unchanged. Its disabled collector cannot retrospectively establish loading.', '',
              '## Completed engineering and remaining limits', '',
              'Source7707756 passed all12 integrated checks; both suites1589 passed/21 skipped,82% displayed coverage and both branch gates. Its wheel passed16 offline installed checks with0 downloads and private runtime removal. The pinned offline docs check passed67 files,658 link occurrences,454 unique,591 OK,67 excluded,0 errors; runtime removal passed.', '',
              'The proxy is stopped and no containers reference either new task image. Both images and their parents remain retained. No image, volume, backup or unrelated work was removed. Actual human first and helped follow-up responses are recorded. Report scope and limits are understood after clarification; concrete control discovery remains partial. Whole-host resource acceptance and release authorization remain open.', '',
              'Evidence: capture-status.json binds the original receipts/journals, canonical reports, skipped preflight, fresh required-profile conformance and completion audit. The current CLI resource characterization adds 24 network-denied source commands and shared-host before/during/after counters; it is not a production acceptance verdict. No new framework or dependency was added.', '']
    text = '\n'.join(lines)
    (OUT / 'capture-status.md').write_text(text)
    (OUT / 'capture-status.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AEEP live capture checks</title><style>body{max-width:76rem;margin:2rem auto;padding:0 1rem;font:16px/1.6 system-ui;color:#17242f}table{border-collapse:collapse;display:block;overflow-x:auto}th,td{padding:.6rem .8rem;border:1px solid #cad2d8;text-align:left}th{background:#eef3f5}code{overflow-wrap:anywhere}h2{margin-top:2rem}</style><main>' + MarkdownIt('commonmark', {'html': False}).enable('table').render(text) + '</main></html>\n')
    print(json.dumps({key: summary[key] for key in ('actual_model_receipts', 'token_captures_verified', 'charged_diagnostic_turn_reservations', 'positive_loading_observed', 'pending_additional_task_turns')}))


if __name__ == '__main__':
    main()
