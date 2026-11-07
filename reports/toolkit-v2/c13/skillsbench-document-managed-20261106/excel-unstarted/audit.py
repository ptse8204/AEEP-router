"""Reconcile one completed managed task from the existing read-only trial evidence."""

import sqlite3
from contextlib import closing, nullcontext
from types import SimpleNamespace

from aeep.assessment.models import content_digest
from aeep_toolkit.models import EvidenceBundle


def audit_document(parent, engine, review, role):
    case = next(item for item in review['cases'] if item['role'] == role)
    pair = parent.WorkerPairInspection.model_validate(parent.read(case['pair']))
    auditor = parent.load('existing_trial_audit', parent.PRIOR / 'audit-trial.py')
    plan = auditor.stored_plan(engine, role)
    output = engine.WORK / f'{role}-result'
    normalized = EvidenceBundle.model_validate_json((output / 'toolkit-evidence.json').read_bytes())
    assert len(normalized.runs) == 1
    run = normalized.runs[0]

    uri = parent.Path(review['database']).as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        store = SimpleNamespace(_connection=connection, _lock=nullcontext())
        service = SimpleNamespace(directory=engine.CAMPAIGNS, router=SimpleNamespace(store=store))
        record = auditor.audit(engine, service, plan, pair)

    assert auditor.passed(record) and record['case_id'] == case['task_id']
    assert run.run_id == record['trial_id'] and run.plan_ref == content_digest(plan)
    assert run.receipt_refs == (record['receipt_ref'],)
    assert run.status == 'completed' and run.retries == record['retries']
    assert run.verification == ('pass' if record['task_grade'] else 'fail')
    assert run.agent_wall_seconds == record['agent_wall_seconds']
    assert run.verification_wall_seconds == record['grading_wall_seconds']
    assert run.tokens is not None and run.tokens.source_ref == record['receipt_ref']
    counts = record['token_counts_provider_reported']
    for category in ('input_tokens', 'output_tokens', 'cached_input_tokens', 'reasoning_output_tokens'):
        assert getattr(run.tokens, category) == counts.get(category)
    summary = parent.read(output / 'summary.json')
    analysis = summary['managed_analysis']
    assert analysis['plan_ref'] == content_digest(plan) and analysis['unresolved_operations'] == 0
    assert summary['evidence_sha256'] == content_digest(normalized.model_dump(mode='json'))
    files = ('report.html', 'report.md', 'summary.json', 'toolkit-evidence.json', 'accounting-records.json')
    return record | {
        'report': str(output / 'report.html'),
        'report_file_sha256': {name: parent.sha(output / name) for name in files},
        'token_semantics': {'cached': run.tokens.cached_semantics, 'reasoning': run.tokens.reasoning_semantics},
        'paired_token_difference': None,
        'comparisons': 'PAUSED',
        'candidate_usefulness': 'NOT_ASSESSED',
        'selection_usefulness': 'NOT_ASSESSED',
    }
