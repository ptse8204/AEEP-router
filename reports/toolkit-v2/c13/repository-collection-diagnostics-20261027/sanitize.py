"""Allowlisted facts from an untrusted public test log; never return log text."""
import re

SCHEMA = 'aeep.repository-collection-diagnostic.v1'
IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*', re.ASCII)
CATEGORIES = ('ModuleNotFoundError', 'ImportError', 'AttributeError', 'TypeError',
              'NameError', 'SyntaxError', 'ValueError', 'RuntimeError', 'AssertionError',
              'FileNotFoundError', 'PermissionError', 'OSError', 'KeyError',
              'LookupError', 'NotImplementedError', 'TimeoutError')
ERROR = re.compile(r'\b(' + '|'.join(CATEGORIES) + r'):([^\n]*)')


def summarize_log(text, allowed):
    assert isinstance(text, str) and len(text) <= 500_000
    assert len(allowed) <= 20_000
    assert all(isinstance(n, str) and len(n) <= 128 and IDENTIFIER.fullmatch(n) for n in allowed)
    allowed = set(allowed)
    records, seen, redacted = [], set(), 0
    truncated = False

    def retain(record, key, name):
        nonlocal redacted
        if name in allowed:
            record[key] = name
        else:
            redacted += 1

    for match in ERROR.finditer(text):
        category, message = match.groups()
        record = {'category': category}
        if category == 'ModuleNotFoundError':
            missing = re.search(r"No module named ['\"]([A-Za-z_][A-Za-z_0-9.]*)['\"]", message)
            if missing:
                retain(record, 'missing_module', missing[1])
        if category == 'ImportError':
            imported = re.search(r"cannot import name ['\"]([A-Za-z_][A-Za-z_0-9]*)['\"] from ['\"]([A-Za-z_][A-Za-z_0-9.]*)['\"]", message)
            if imported:
                retain(record, 'imported_name', imported[1])
                retain(record, 'from_module', imported[2])
        if category == 'AttributeError':
            attribute = re.search(r"module ['\"]([A-Za-z_][A-Za-z_0-9.]*)['\"] has no attribute ['\"]([A-Za-z_][A-Za-z_0-9]*)['\"]", message)
            if attribute:
                retain(record, 'from_module', attribute[1])
                retain(record, 'attribute', attribute[2])
        key = tuple(sorted(record.items()))
        if key not in seen:
            if len(records) >= 16:
                truncated = True
                break
            seen.add(key)
            records.append(record)
    return {'errors': records, 'errors_truncated': truncated,
            'redacted_identifiers': min(redacted, 100_000),
            'unrecognized_pytest_arguments': 'unrecognized arguments:' in text}


def validate_reply(value, payload):
    assert isinstance(value, dict) and set(value) == {
        'schema_version', 'archive_sha256', 'python', 'pytest', 'exit_code', 'timed_out',
        'log_limit_exceeded', 'diagnostics'}
    assert value['schema_version'] == SCHEMA
    assert all(value[n] == payload[n] for n in ('archive_sha256', 'python', 'pytest'))
    assert value['exit_code'] is None or type(value['exit_code']) is int and -128 <= value['exit_code'] <= 255
    assert type(value['timed_out']) is bool and type(value['log_limit_exceeded']) is bool
    assert (value['exit_code'] is None) == value['timed_out']
    facts = value['diagnostics']
    assert isinstance(facts, dict) and set(facts) == {
        'errors', 'errors_truncated', 'redacted_identifiers', 'unrecognized_pytest_arguments'}
    assert type(facts['errors_truncated']) is bool and type(facts['unrecognized_pytest_arguments']) is bool
    assert type(facts['redacted_identifiers']) is int and 0 <= facts['redacted_identifiers'] <= 100_000
    assert isinstance(facts['errors'], list) and len(facts['errors']) <= 16
    for item in facts['errors']:
        assert isinstance(item, dict) and item.get('category') in CATEGORIES
        fields = {'ModuleNotFoundError': {'missing_module'}, 'ImportError': {'imported_name', 'from_module'},
                  'AttributeError': {'from_module', 'attribute'}}.get(item['category'], set())
        assert set(item) <= {'category', *fields}
        assert all(v in payload['reviewed_identifiers'] for k, v in item.items() if k != 'category')


def self_check():
    import copy
    import json
    allowed = ['known', 'known.api', 'Widget']
    text = ("private-path/secret.txt:42: ModuleNotFoundError: No module named 'known.api'\n"
            "E ImportError: cannot import name 'Widget' from 'known' (/private/secret/token)\n"
            "E AttributeError: module 'known.api' has no attribute 'Widget'\n"
            "E ModuleNotFoundError: No module named 'DO_NOT_RETAIN_SECRET'\n"
            "TypeError: credential=DO_NOT_RETAIN_SECRET arbitrary details\n"
            "ERROR: unrecognized arguments: --token=DO_NOT_RETAIN_SECRET\n")
    facts = summarize_log(text, allowed)
    encoded = json.dumps(facts)
    assert 'DO_NOT_RETAIN_SECRET' not in encoded and 'private' not in encoded and 'token' not in encoded
    assert facts['errors'][0] == {'category': 'ModuleNotFoundError', 'missing_module': 'known.api'}
    assert facts['errors'][1] == {'category': 'ImportError', 'imported_name': 'Widget', 'from_module': 'known'}
    assert facts['redacted_identifiers'] == 1 and facts['unrecognized_pytest_arguments']
    assert summarize_log('', allowed)['errors'] == []
    assert summarize_log("ModuleNotFoundError: No module named 'known.api'\n" * 100, allowed)['errors'] == [facts['errors'][0]]
    assert summarize_log('\n'.join(c + ': x' for c in CATEGORIES) + "\nModuleNotFoundError: No module named 'known'", allowed)['errors_truncated']
    payload = {'archive_sha256': 'a' * 64, 'python': '3.13', 'pytest': '8.3.5', 'reviewed_identifiers': allowed}
    reply = {'schema_version': SCHEMA, **{k: payload[k] for k in ('archive_sha256', 'python', 'pytest')},
             'exit_code': 2, 'timed_out': False, 'log_limit_exceeded': False, 'diagnostics': facts}
    validate_reply(reply, payload)
    count = 7
    for key, value in [('raw_log', text), ('exit_code', True), ('archive_sha256', 'b' * 64),
                       ('timed_out', True), ('diagnostics', {'errors': []})]:
        bad = copy.deepcopy(reply); bad[key] = value
        try:
            validate_reply(bad, payload)
        except AssertionError:
            count += 1
        else:
            raise AssertionError('Diagnostic validator accepted malformed output')
    bad = copy.deepcopy(reply); bad['diagnostics']['errors'][0]['missing_module'] = 'DO_NOT_RETAIN_SECRET'
    try:
        validate_reply(bad, payload)
    except AssertionError:
        count += 1
    else:
        raise AssertionError('Diagnostic validator accepted an unreviewed identifier')
    return count


if __name__ == '__main__':
    print(self_check())
