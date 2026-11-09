"""Verify the retained Prefix Cache grades without starting another case."""

import ast
import json
import math
import runpy
import sqlite3
from collections import Counter
from pathlib import Path

OUT = Path(__file__).resolve().parent
runtime = runpy.run_path(str(OUT.parent / 'with-runtime-support.py'))
read, sha, save = (runtime[key] for key in ('read', 'sha', 'save'))
runner = runtime['runner']


def main():
    review_path = OUT / 'operation-review.json'
    digest = sha(review_path)
    review = read(review_path)
    result = read(OUT / 'result.json')
    ledger = read(OUT / 'ledger.json')
    assert result['review_sha256'] == digest
    assert result['passed'] is False and result['error_type'] == 'AssertionError'
    assert result['accounting_settled'] and result['operations'] == 5 and result['models'] == 0
    operations = sorted(ledger['operations'], key=lambda row: row['started_at'])
    cases = review['cases']
    assert [row['stage'] for row in operations] == cases
    elapsed = sum(row['elapsed_seconds'] for row in operations)

    # The omitted trace belongs to the expected fixture. Self-consistency
    # reads only the existing report, so its success cannot repair the grade.
    verifier = runtime['old']['STAGED'] / 'test_outputs.py'
    assert sha(verifier) == review['pins'][str(verifier)]
    source = ast.parse(verifier.read_bytes())
    fixtures = {node.name: node for node in source.body if isinstance(node, ast.FunctionDef)}
    assert any(isinstance(node, ast.Name) and node.id == 'TRACE_PATH'
               for node in ast.walk(fixtures['expected']))
    observed = result['unexpected_observation']
    assert observed['case'] == 'infrastructure' and observed['pytest_exit'] == 1
    assert observed['pytest_version'] == '8.4.1'
    tests = observed['tests']
    assert len(tests) == 10 and {test['test_id'] for test in tests} == runner['names']()
    for test in tests:
        fixture_args = {arg.arg for arg in fixtures[test['test_id'].split('[')[0]].args.args}
        assert test['status'] == ('error' if 'expected' in fixture_args else 'passed')
    assert Counter(test['status'] for test in tests) == {'error': 9, 'passed': 1}

    database = runtime['PRIVATE'] / 'calibration-continuation.sqlite3'
    audited = {}
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        assert db.execute(
            'SELECT operations, model_turns, cash_usd FROM assessment_grants WHERE id=?',
            (ledger['plan_id'],),
        ).fetchone() == (5, 0, '0')
        assert math.isclose(db.execute('SELECT elapsed_seconds FROM assessment_grants WHERE id=?',
                                       (ledger['plan_id'],)).fetchone()[0], elapsed)
        for operation in operations:
            case = operation['stage']
            path = OUT / f'{case}-receipt.json'
            receipt = read(path)
            persisted, = db.execute('SELECT payload_json FROM receipts WHERE receipt_id=?',
                                    (receipt['receipt_id'],)).fetchone()
            assert json.loads(persisted) == receipt
            assert receipt['action_id'] == operation['operation_id'] and receipt['attempt'] == 1
            assert receipt['metadata']['review_sha256'] == digest
            assert db.execute('SELECT state FROM assessment_operations WHERE id=?',
                              (operation['operation_id'],)).fetchone() == ('complete',)
            if case == 'infrastructure':
                assert not receipt['execution_success'] and receipt['quality_score'] is None
                assert receipt['metadata']['observation'] is None
                observation = observed
            else:
                observation = result['cases'][case]
                assert receipt['execution_success'] and receipt['metadata']['observation'] == observation
                assert observation['cleanup_confirmed']
                assert runner['classify'](case, observation)['calibration_case_passed']
            audited[case] = {
                'receipt_sha256': sha(path),
                'test_counts': dict(Counter(test['status'] for test in observation['tests'])),
                'pytest_exit': observation['pytest_exit'],
                'upstream_binary_reward': observation.get('verified_upstream_binary_reward'),
            }

    save(OUT / 'audit.json', {
        'review_sha256': digest, 'result_sha256': sha(OUT / 'result.json'),
        'ledger_sha256': sha(OUT / 'ledger.json'), 'cases': audited,
        'original_driver_passed': False, 'infrastructure_blocked_grading': True,
        'original_driver_error': 'Expected all tests to error, including the trace-independent check.',
        'operations': 5, 'elapsed_seconds': elapsed, 'model_turns': 0,
        'cash_usd': '0', 'replayed': False, 'comparisons': 'PAUSED',
    })


if __name__ == '__main__':
    main()
