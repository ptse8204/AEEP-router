"""Read-only regression against the actual minimized receipt; no worker execution."""
import copy
import importlib.util
import json
import sqlite3
from pathlib import Path

from aeep.models import ExecutionReceipt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
spec = importlib.util.spec_from_file_location('review_driver', HERE / 'run-grader-review.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
prior = ROOT / 'reports/toolkit-v2/c13/repository-value-20261021'
review = json.loads((prior / 'grader-operation-review.json').read_text())
plan = review['request']['plan_id']
database = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/.aeep/assessments') / plan / 'recipe-operations' / (plan + '-probe-1.sqlite3')
with sqlite3.connect('file:' + str(database) + '?mode=ro', uri=True) as connection:
    raw = json.loads(connection.execute('SELECT payload_json FROM receipts').fetchone()[0])
    attempt = json.loads(connection.execute('SELECT payload_json FROM execution_attempts WHERE attempt_id=?', (raw['metadata']['attempt_id'],)).fetchone()[0])
assert 'container_name' not in raw['metadata'] and 'container_image' not in raw['metadata']
records = []
for fault in (None, 'missing_attempt', 'fingerprint', 'state', 'terminal_receipt', 'executor'):
    candidate, row = copy.deepcopy(raw), copy.deepcopy(attempt)
    if fault == 'missing_attempt':
        candidate['metadata']['attempt_id'] = 'missing'
    elif fault == 'fingerprint':
        candidate['executor_fingerprint'] = 'sha256:' + 'f' * 64
    elif fault == 'state':
        row['state'] = 'UNKNOWN'
    elif fault == 'terminal_receipt':
        row['terminal_receipt_ids'] = []
    elif fault == 'executor':
        row['executor_id'] = 'wrong-executor'
    with sqlite3.connect(':memory:') as database_copy:
        database_copy.execute('CREATE TABLE execution_attempts(attempt_id TEXT, payload_json TEXT)')
        database_copy.execute('INSERT INTO execution_attempts VALUES (?,?)', (row['attempt_id'], json.dumps(row)))
        try:
            name = module.audit_attempt(database_copy, ExecutionReceipt.model_validate(candidate), raw['executor_id'])
        except (AssertionError, ValueError):
            assert fault is not None
            records.append({'fault': fault, 'rejected': True})
        else:
            assert fault is None
            assert name == json.loads((prior / 'failed-attempt-reconciliation.json').read_text())['container_name']
            records.append({'fault': None, 'canonical_attempt_bound': True, 'derived_container_name': name})
(HERE / 'receipt-audit-regression.json').write_text(json.dumps({'passed': True, 'cases': records,
    'canonical_database_modified': False, 'containers_started': 0, 'scope': 'Audit logic only; no new conformance or grader execution.'}, indent=2) + '\n')
print('All six receipt-audit checks passed; canonical database unchanged.')
