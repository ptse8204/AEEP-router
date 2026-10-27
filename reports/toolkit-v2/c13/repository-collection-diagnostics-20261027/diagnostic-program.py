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



# Explicit-plugin observer for reviewed v2 cases; the legacy observer stays unchanged.
import base64
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from swe_rebench_pytest_parser import parse_log_pytest


def main():
    request = json.load(sys.stdin)
    python = '.'.join(map(str, sys.version_info[:2]))
    assert python == request['python']
    plugins = request.get('pytest_plugins', [])
    assert isinstance(plugins, list) and len(plugins) <= 8 and len(set(plugins)) == len(plugins)
    assert all(isinstance(name, str) and len(name) <= 128 and re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', name, flags=re.ASCII) for name in plugins)
    source_modules = request.get('source_modules', [])
    assert isinstance(source_modules, list) and all(isinstance(name, str) and name.isidentifier() for name in source_modules)
    with tempfile.TemporaryDirectory(prefix='repository-suite-') as directory:
        root = Path(directory)
        repo = root / 'repository'
        repo.mkdir()
        archive_bytes = base64.b64decode(request['archive'], validate=True)
        assert hashlib.sha256(archive_bytes).hexdigest() == request['archive_sha256']
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:gz') as archive:
            for member in archive:
                # The coordinator already bounded and canonicalized this archive.
                assert member.isfile() and not member.name.startswith('/') and '..' not in Path(member.name).parts
                path = repo / member.name
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as stream:
                    path.write_bytes(stream.read())
        wheels = []
        for item in request['wheels']:
            name = item['filename']
            assert Path(name).name == name and name.endswith('-none-any.whl')
            data = base64.b64decode(item['data'], validate=True)
            assert hashlib.sha256(data).hexdigest() == item['sha256']
            path = root / name
            path.write_bytes(data)
            wheels.append(str(path))
        argv = ['--no-header', '-rA', '--tb=line', '--color=no', '-p', 'no:cacheprovider', *request['test_paths']]
        # Import reviewed runtime/plugins before exposing candidate source paths.
        boot = ('import sys, os, importlib; sys.path[:] = ' + repr(wheels)
                + ' + [p for p in sys.path if p and os.path.abspath(p) != ' + repr(str(repo))
                + ' and not os.path.abspath(p).startswith(' + repr(str(repo) + '/') + ')]'
                + '; import pytest; assert pytest.__version__ == ' + repr(request['pytest'])
                + '; plugins = [importlib.import_module(n) for n in ' + repr(plugins) + ']'
                + '; assert all(getattr(p, "__file__", None) and not os.path.abspath(p.__file__).startswith('
                + repr(str(repo) + '/') + ') for p in plugins)'
                + '; assert not set(' + repr(source_modules) + ') & {n.split(".")[0] for n in sys.modules}, "source module already loaded by runtime/plugin"'
                + '; sys.path[:0] = ' + repr([str(repo / 'src'), str(repo)])
                + '; os.chdir(' + repr(str(repo)) + '); raise SystemExit(pytest.main(' + repr(argv) + ', plugins=plugins))')
        log = root / 'tests.log'
        timed_out = False
        exit_code = None
        with log.open('wb') as stream:
            try:
                child = subprocess.run([sys.executable, '-B', '-c', boot], cwd=repo,
                    env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': str(root),
                         'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'},
                    stdout=stream, stderr=subprocess.STDOUT, timeout=22, check=False)
                exit_code = child.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
        over_limit = log.stat().st_size > 500_000
        with log.open('rb') as stream:
            text = stream.read(500_000).decode(errors='replace')
        # No test statuses or grade are exported by this separate diagnostic.
        return {'schema_version': SCHEMA, 'archive_sha256': request['archive_sha256'],
                'python': python, 'pytest': request['pytest'], 'exit_code': exit_code,
                'timed_out': timed_out, 'log_limit_exceeded': over_limit,
                'diagnostics': summarize_log(text, request['reviewed_identifiers'])}



if __name__ == '__main__':
    print(json.dumps(main(), separators=(',', ':'), allow_nan=False))
