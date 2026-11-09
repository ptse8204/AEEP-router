"""Recover the completed React evidence using only read-only canonical records."""

import hashlib
import json
import sqlite3
from pathlib import Path

from aeep.benchmarking import BenchmarkTrial
from aeep_toolkit.models import EvaluationRun

HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    review = read(HERE / 'operation-review.json')
    result = read(HERE / 'sol-managed-result.json')
    ready = read(HERE / 'sol-managed-dispatch-ready.json')
    cli = read(HERE / 'sol-sol-managed-run-cli.json')
    identity = sha(HERE / 'operation-review.json')
    assert result['review_sha256'] == ready['review_sha256'] == identity
    assert cli['exit_code'] == 0 and ready['worker_boundary_verified']
    assert not result['passed'] and result['error_type'] == 'AttributeError'
    assert result['model_turns_reserved'] == 1 and result['historical_reservations_preserved']
    assert result['proxy_restored_stopped'] and not result['new_unresolved_reservations']
    assert result['grant_after'][3] == review['grant']['counters'][3]
    work = Path(review['work'])
    target = work / 'react-result'
    evidence = read(work / 'skillsbench-react-sol-permitted.treatment-trial-evidence.json')
    plan = ready['plan_id']
    with sqlite3.connect(Path(review['database']).as_uri() + '?mode=ro', uri=True) as connection:
        job, = connection.execute(
            'SELECT id,state,report_id,error_code FROM assessment_jobs WHERE plan_id=?', (plan,))
    job_id, state, report_id, code = job
    assert state == 'complete' and report_id and code is None
    ledger = work / 'campaigns' / plan / 'campaign.sqlite3'
    with sqlite3.connect(ledger.as_uri() + '?mode=ro', uri=True) as connection:
        row, = connection.execute('SELECT payload_json FROM trials')
    trial = BenchmarkTrial.model_validate_json(row[0])
    assert trial.trial_id == evidence['trial_id'] and trial.valid and trial.model_usage_complete
    assert list(trial.host_models.values()) == ['gpt-6.1-sol']
    grade, = [item for item in trial.case_validation if item.kind.value == 'callback' and item.trust.value == 'verified']
    assert grade.valid and grade.quality_score == 1.0

    run = EvaluationRun.model_validate(read(target / 'toolkit-evidence.json')['runs'][0])
    assert run.status == 'completed' and run.verification == 'pass' and run.retries == 0
    assert run.model == 'gpt-6.1-sol' and run.effort == 'medium' and run.mode == 'forced_diagnostic'
    ref, = run.receipt_refs
    receipt = read(target / 'accounting-records.json')[ref]
    assert receipt['receipt_id'] in trial.receipt_ids
    assert receipt['task_valid'] and receipt['quality_score'] == grade.quality_score
    assert evidence['canonical_trial_complete'] and evidence['worker_cleanup_confirmed']
    assert evidence['independent_grader_observed'] and evidence['task_prompt_bound'] and evidence['task_grade']
    assert evidence['candidate_loading']['instructions_loaded'] is True
    capture = evidence['token_capture']
    assert capture['status'] == 'verified' and capture['receipt_ref'] == ref
    assert capture['source'] == 'provider_report' and not capture['provider_usage_independently_verified']
    tokens = run.tokens.model_dump(mode='json')
    raw = receipt['actual_resources']
    assert all(raw[key] == tokens[key] for key in
               ('input_tokens', 'output_tokens', 'cached_input_tokens', 'reasoning_output_tokens'))
    summary = read(target / 'summary.json')
    assert summary['outcome'] == 'NOT_ASSESSED' and summary['managed_analysis']['distinct_paired_cases'] == 0
    assert trial.retry_fallback_count == 0
    report_hashes = {name: sha(target / name) for name in ('report.html', 'report.md', 'summary.json', 'toolkit-evidence.json')}
    for name in ('report.html', 'report.md'):
        with (HERE / name).open('xb') as stream:
            stream.write((target / name).read_bytes())

    before, after = review['grant']['counters'], result['grant_after']
    save(HERE / 'completed-run-audit.json', {
        'review_sha256': identity, 'scope': 'One required-use stack engineering trial',
        'task_id': trial.case_id, 'plan_id': plan, 'job_id': job_id, 'report_id': report_id,
        'trial_id': trial.trial_id, 'receipt_id': receipt['receipt_id'], 'receipt_ref': ref,
        'score': grade.quality_score, 'scale': 1, 'model': run.model, 'reasoning_effort': run.effort,
        'model_turns': 1, 'retries': 0, 'tokens': tokens, 'cache_write_input_tokens': raw['cache_write_input_tokens'],
        'token_capture': capture, 'agent_wall_seconds': run.agent_wall_seconds,
        'verification_wall_seconds': run.verification_wall_seconds, 'matched_token_delta': None,
        'candidate_instructions_loaded': True, 'candidate_invocation': run.candidate_invoked,
        'worker_cleanup_confirmed': True, 'proxy_restored_stopped': True,
        'operations': after[0] - before[0], 'charged_elapsed_seconds': after[2] - before[2],
        'new_unresolved_reservations': [], 'cash_usd': '0', 'comparisons': 'PAUSED',
        'cli_exit_code': cli['exit_code'], 'canonical_job_state': state,
        'outer_driver_error': result['error_type'],
        'outer_driver_defect': 'Read receipt_ids and wall_time_ms from EvaluationRun. Its fields are receipt_refs and agent_wall_seconds.',
        'original_report_hashes': report_hashes, 'model_replayed': False, 'purpose_outcome': summary['outcome'],
    })


if __name__ == '__main__':
    main()
