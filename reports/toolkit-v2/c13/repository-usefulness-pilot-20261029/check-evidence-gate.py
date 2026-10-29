"""Replay six existing canonical trials read-only, then challenge the stop gate."""
import copy
import importlib.util
import json
from pathlib import Path
import sqlite3

from aeep.benchmarking import BenchmarkTrial
from aeep.hosts.codex_pair_inspection import WorkerPairInspection

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'repository-task-delivery-20261023'
BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/.aeep/assessments')
spec = importlib.util.spec_from_file_location('pilot_trial_evidence', HERE / 'trial-evidence.py')
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)
proposal = json.loads((PRIOR / 'collector-definitions.json').read_text())
pair = WorkerPairInspection.model_validate(proposal['definitions'][proposal['pair_definition_digest']])
result = json.loads((PRIOR / 'model-result.json').read_text())
expected = {(item['case'], item['role']): item['instruction_sha256']
            for item in json.loads((PRIOR / 'task-delivery-check.json').read_text())['checks']}
directory = BASE / result['plan_id']
with sqlite3.connect((directory / 'campaign.sqlite3').as_uri() + '?mode=ro', uri=True) as connection:
    trials = [BenchmarkTrial.model_validate_json(row[0]) for row in connection.execute('SELECT payload_json FROM trials')]
    assert len(trials) == 6
    for trial in trials:
        record = evidence.read_trial(connection, trial, pair, expected, directory / 'attempts')
        evidence.require_complete(record)
        assert record['task_grade'] is True

negative_checks = 0
for field in ('canonical_trial_complete', 'worker_cleanup_confirmed', 'independent_grader_observed', 'task_prompt_bound'):
    broken = copy.deepcopy(record)
    broken[field] = False
    try:
        evidence.require_complete(broken)
    except RuntimeError:
        negative_checks += 1
    else:
        raise AssertionError('An incomplete trial was accepted')
for value in (None, {'status': 'unknown'}, {'status': 'partial'}):
    broken = copy.deepcopy(record)
    broken['token_capture'] = value
    try:
        evidence.require_complete(broken)
    except RuntimeError:
        negative_checks += 1
    else:
        raise AssertionError('An unverified token capture was accepted')
failed_candidate = copy.deepcopy(record)
failed_candidate['task_grade'] = False
failed_candidate['candidate_loading'] = None
evidence.require_complete(failed_candidate)
audit = {'passed': True, 'existing_canonical_trials_reopened_read_only': 6,
         'negative_stop_checks': negative_checks, 'verified_candidate_failure_is_retained': True,
         'optional_use_unknown_is_not_forced': True, 'new_execution_or_model_calls': 0,
         'new_benchmark_or_selection_evidence': False}
(HERE / 'evidence-gate-check.json').write_text(json.dumps(audit, indent=2) + '\n')
print(json.dumps(audit))
