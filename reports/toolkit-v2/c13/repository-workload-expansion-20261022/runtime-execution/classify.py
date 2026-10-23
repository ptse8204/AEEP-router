"""Compare a provisional case with its frozen reference/counterexample expectation."""


def discrepancies(raw, grade, expected):
    if not isinstance(raw, dict) or not isinstance(raw.get('statuses'), dict):
        return ['missing_observation']
    failures = []
    if type(raw.get('exit_code')) is not int or raw['exit_code'] != expected['exit_code']:
        failures.append('unexpected_exit')
    if grade.get('valid') is not expected['valid'] or grade.get('detail') != expected['detail']:
        failures.append('unexpected_grade')
    if any(raw['statuses'].get(key) != status for key, status in expected['statuses'].items()):
        failures.append('required_test_status_mismatch')
    return failures


def self_check():
    good = {'exit_code': 0, 'statuses': {'bug': 'PASSED', 'preserve': 'PASSED'}}
    yes = {'valid': True, 'detail': ''}
    expected = {**good, **yes}
    assert not discrepancies(good, yes, expected)
    for status in ('FAILED', 'ERROR', 'SKIPPED', 'XFAIL', None):
        assert discrepancies({**good, 'statuses': {'bug': status, 'preserve': 'PASSED'}}, yes, expected)
    assert discrepancies({**good, 'exit_code': 1}, yes, expected)
    assert discrepancies({**good, 'exit_code': False}, yes, expected)
    assert discrepancies(good, {'valid': False, 'detail': 'missing_test'}, expected)
    assert discrepancies(None, yes, expected)
    negative = {'exit_code': 1, 'statuses': {'bug': 'FAILED', 'preserve': 'PASSED'}}
    no = {'valid': False, 'detail': 'test_failure'}
    assert not discrepancies(negative, no, {**negative, **no})
    assert discrepancies(good, yes, {**negative, **no})
    return 12
