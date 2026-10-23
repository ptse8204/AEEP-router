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
    if 'at_least_one_failed' in expected:
        bug=expected['at_least_one_failed']
        if (not bug or not any(raw['statuses'].get(key)=='FAILED' for key in bug)
                or any(raw['statuses'].get(key) not in ('PASSED','FAILED') for key in bug)):
            failures.append('partial_repair_not_detected_with_complete_bug_observations')
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
    partial={'exit_code':1,'valid':False,'detail':'test_failure','statuses':{'preserve':'PASSED'},'at_least_one_failed':['bug','other']}
    assert not discrepancies({'exit_code':1,'statuses':{'bug':'FAILED','other':'PASSED','preserve':'PASSED'}},no,partial)
    for status in (None,'ERROR','SKIPPED','XFAIL'):
        assert discrepancies({'exit_code':1,'statuses':{'bug':'FAILED','other':status,'preserve':'PASSED'}},no,partial)
    assert discrepancies({'exit_code':1,'statuses':{'bug':'PASSED','other':'PASSED','preserve':'PASSED'}},no,partial)
    assert discrepancies({'exit_code':1,'statuses':{'bug':'FAILED','other':'PASSED','preserve':'FAILED'}},no,partial)
    return 19
