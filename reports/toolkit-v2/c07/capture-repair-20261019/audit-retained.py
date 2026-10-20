"""Read-only retrospective capture audit. Never dispatch or refit the old assessment."""
import hashlib
import html
import json
import sqlite3
from collections import Counter
from pathlib import Path
from statistics import mean, median

from aeep.assessment.models import content_digest
from aeep.models import ExecutionReceipt
from aeep_toolkit.telemetry import bound_journal, candidate_loading, capture_summary, token_capture

OUT = Path(__file__).parent
ROOT = OUT.parents[3]
ORIGIN = OUT.parent / 'edit-value-native-20261019'
PLAN = 'plan_017bce61874c437296c66276e91876d6'
ATTEMPTS = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/.aeep/assessments') / PLAN


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    origin_path = ORIGIN / 'all-four-evidence.json'
    old = json.loads(origin_path.read_text())
    assert old['plan_id'] == PLAN and len(old['records']) == 564
    report_files = [ORIGIN / name for name in ('comparison.html', 'comparison.md', 'all-four-evidence.json')]
    before = {str(p.relative_to(ROOT)): sha(p) for p in report_files}
    checks, journals, receipts = {}, {}, {}
    with sqlite3.connect((ATTEMPTS / 'campaign.sqlite3').as_uri() + '?mode=ro', uri=True) as campaign:
        rows = {tid: (rid, raw) for rid, tid, raw in campaign.execute('SELECT receipt_id,trial_id,payload_json FROM trial_receipts')}
        stores = dict(campaign.execute('SELECT trial_id,database_path FROM trial_stores'))
    assert len(rows) == len(old['records'])
    for record in old['records']:
        tid = record['trial_id']
        rid, raw = rows[tid]
        receipt = ExecutionReceipt.model_validate_json(raw)
        assert receipt.receipt_id == rid and content_digest(receipt) == record['receipt_ref']
        path = Path(stores[tid]).resolve(strict=True)
        assert path.parent == ATTEMPTS / 'attempts'
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as original:
            raw_original = original.execute('SELECT payload_json FROM receipts WHERE receipt_id=?', (rid,)).fetchone()[0]
            assert content_digest(ExecutionReceipt.model_validate_json(raw_original)) == content_digest(receipt)
            journal_raw = original.execute("SELECT payload_json FROM assessment_records WHERE kind='execution_evidence' AND digest=?",
                (receipt.metadata['execution_evidence_digest'],)).fetchone()[0]
        journal = bound_journal(receipt, json.loads(journal_raw))
        checks[tid] = {'tokens': token_capture(receipt, journal), 'candidate': candidate_loading(receipt, journal),
                       'arm': record['arm'], 'phase': record['phase']}
        journals[receipt.metadata['execution_evidence_digest']] = journal.model_dump(mode='json')
        receipts[content_digest(receipt)] = receipt.model_dump(mode='json')
    assert len(checks) == 564 and len(journals) == 564 and len(receipts) == 564
    summary = capture_summary(checks)
    assert summary['verified'] == 564 and summary['instructions_loaded'] == 0
    holdouts = [r for r in old['records'] if r['phase'] == 'holdout']
    groups = {arm: [r for r in holdouts if r['arm'] == arm] for arm in sorted({r['arm'] for r in holdouts})}
    paired = {}
    control = {r['case_id']: r for r in groups['ordinary']}
    assert len(control) == 105
    for arm, group in groups.items():
        assert len(group) == 105 and {r['case_id'] for r in group} == set(control)
        paired[arm] = {}
        for field in ('input_tokens', 'output_tokens', 'cached_input_tokens', 'reasoning_output_tokens'):
            values = [r['reported_tokens'][field] for r in group]
            differences = [control[r['case_id']]['reported_tokens'][field] - r['reported_tokens'][field] for r in group]
            assert all(type(value) is int and value >= 0 for value in values)
            paired[arm][field] = {'pairs': len(group), 'median_reported': median(values),
                'mean_control_minus_arm': mean(differences), 'median_control_minus_arm': median(differences)}
    assert before == {str(p.relative_to(ROOT)): sha(p) for p in report_files}
    result = {'schema_version': 'aeep.retrospective-capture-audit.v1', 'plan_id': PLAN,
        'report_id': old['report_id'], 'original_source_digest': old['source_digest'],
        'original_inputs': before, 'summary': summary, 'records': checks,
        'paired_provider_reported_counts': paired, 'new_model_turns': 0,
        'original_report_unchanged': True, 'canonical_outcome_unchanged': old['canonical_outcome'],
        'journal_manifest_ref': content_digest(journals), 'receipt_manifest_ref': content_digest(receipts),
        'by_phase_and_arm': dict(Counter(r['phase'] + ':' + r['arm'] for r in old['records'])),
        'limits': ['Retrospective consistency audit, not new source qualification or a rerun.',
            'Token quantities remain provider_report/self_asserted. Strict utility and admission are unchanged.',
            'Paired token differences are descriptive, exploratory counts, not confidence-supported savings.',
            'The old run did not enable the native metrics collector. Candidate loading and semantic use cannot be reconstructed from these receipts.']}
    (OUT / 'capture-audit.json').write_text(json.dumps(result, indent=2) + '\n')
    (OUT / 'execution-journals.json').write_text(json.dumps(journals, indent=2) + '\n')
    (OUT / 'receipt-records.json').write_text(json.dumps(receipts, indent=2) + '\n')
    lines = ['# Token capture and candidate-use correction', '',
        'All 564 token captures match their original terminal execution journals and receipts. No model was rerun.', '',
        'This verifies capture consistency. OpenAI’s reported token quantities remain independently unverified; the original inconclusive verdict is unchanged.', '',
        '| Holdout arm | Captures verified | Median reported input | Median reported output | Mean reported input difference, ordinary minus arm |',
        '|---|---:|---:|---:|---:|']
    for arm, fields in paired.items():
        lines.append(f"| {arm} | 105/105 | {fields['input_tokens']['median_reported']} | {fields['output_tokens']['median_reported']} | {fields['input_tokens']['mean_control_minus_arm']:.4f} |")
    lines += ['', 'Cached input is included in input; reasoning is included in output. Do not add them to the parent totals.', '',
        'The higher reported input count does not prove full skill instruction loading or explain its cause.', '',
        'Candidate use was not collected in this completed study. The collector was disabled, and the router previously discarded its snapshot. The corrected implementation retains bounded snapshots and can verify a positive instruction-loading event against the exact skill and execution journal. Missing events stay unknown; instruction loading does not prove semantic use or causal benefit.', '',
        'The paired counts above are descriptive. They do not replace the frozen strict-token utility gate or establish savings.', '',
        'Source evidence: capture-audit.json, execution-journals.json and receipt-records.json in this directory. Original comparison files are unchanged.', '']
    text = '\n'.join(lines)
    (OUT / 'capture-audit.md').write_text(text)
    (OUT / 'capture-audit.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AEEP capture correction</title><style>body{max-width:76rem;margin:2rem auto;padding:0 1rem;font:16px/1.6 system-ui}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><main><h1>Capture correction</h1><pre>' + html.escape(text) + '</pre></main></html>\n')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
