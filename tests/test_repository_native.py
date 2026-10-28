"""Native pytest hook checks use only authored local fixtures, never benchmarks."""
import base64
import hashlib
import importlib.metadata
import json
import os
import runpy
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from aeep.assessment.repository_suites import pack_files

pytestmark = pytest.mark.assessment_contract
RUNTIME = Path(__file__).resolve().parents[1] / 'integrations/assessment-runtime'
NODE = 'tests/test_native.py::test_native[white space café]'


def native_program(repository):
    program = (RUNTIME / 'repository_suite_native_program.py').read_text().replace(
        "'__AEEP_NATIVE_CAPTURE_SOURCE__'", repr((RUNTIME / 'repository_suite_native_capture.py').read_text()))
    literal = "repo = Path('/tmp/aeep-repository-native-v6')"
    assert program.count(literal) == 1
    # Host tests use only their owned scratch; deployed workers use private tmpfs.
    return program.replace(literal, 'repo = Path(' + repr(str(repository)) + ')')


@pytest.fixture
def capture():
    cls = runpy.run_path(str(RUNTIME / 'repository_suite_native_capture.py'))['NativeCapture']
    result = cls()
    result.pytest_collection_finish(SimpleNamespace(items=[SimpleNamespace(nodeid=NODE)]))
    return result


def report(capture, when, outcome, xfail=False):
    fields = {'nodeid': NODE, 'when': when, 'outcome': outcome}
    if xfail:
        fields['wasxfail'] = 'authored fixture'
    capture.pytest_runtest_logreport(SimpleNamespace(**fields))


@pytest.mark.parametrize(('phases', 'expected'), [
    ([('setup', 'passed'), ('call', 'passed'), ('teardown', 'passed')], 'PASSED'),
    ([('setup', 'passed'), ('call', 'failed'), ('teardown', 'passed')], 'FAILED'),
    ([('setup', 'failed'), ('teardown', 'passed')], 'ERROR'),
    ([('setup', 'passed'), ('call', 'passed'), ('teardown', 'failed')], 'ERROR'),
    ([('setup', 'skipped'), ('teardown', 'passed')], 'SKIPPED'),
])
def test_native_event_phases(capture, phases, expected):
    for when, outcome in phases:
        report(capture, when, outcome)
    assert capture.export() == {'statuses': {NODE: expected}}


@pytest.mark.parametrize('outcome', ['passed', 'skipped'])
def test_native_xpass_and_xfail_cannot_satisfy_pass(capture, outcome):
    report(capture, 'setup', 'passed')
    report(capture, 'call', outcome, True)
    report(capture, 'teardown', 'passed')
    assert capture.export() == {'statuses': {NODE: 'XFAIL'}}


@pytest.mark.parametrize('problem', ['duplicate', 'missing_teardown', 'bad_phase', 'bad_outcome',
    'duplicate_selected', 'unselected', 'invalid_identity'])
def test_native_invalid_events_fail_closed(capture, problem):
    report(capture, 'setup', 'passed')
    report(capture, 'call', 'passed')
    if problem == 'duplicate':
        report(capture, 'call', 'passed')
    elif problem == 'bad_phase':
        report(capture, 'unknown', 'passed')
    elif problem == 'bad_outcome':
        report(capture, 'teardown', 'unknown')
    elif problem == 'duplicate_selected':
        capture.selected_ids *= 2
    elif problem == 'unselected':
        capture.selected_ids = []
    elif problem == 'invalid_identity':
        capture.pytest_runtest_logreport(SimpleNamespace(nodeid='bad\nname', when='call', outcome='passed'))
    with pytest.raises(ValueError):
        capture.export()


def test_native_missing_events_stay_missing(capture):
    assert capture.export() == {'statuses': {}}


@pytest.mark.parametrize('problem', ['duplicate', 'uncollected', 'body', 'invalid', 'limit'])
def test_native_collection_does_not_grade_or_ignore_protocol_problems(capture, problem):
    capture.collect_only = True
    capture.pytest_itemcollected(SimpleNamespace(nodeid=NODE))
    assert capture.export() == {'native_ids': [NODE], 'selected_ids': [NODE]}
    if problem == 'duplicate':
        capture.pytest_itemcollected(SimpleNamespace(nodeid=NODE))
    elif problem == 'uncollected':
        capture.native_ids = []
    elif problem == 'body':
        report(capture, 'call', 'passed')
    elif problem == 'invalid':
        capture.pytest_itemcollected(SimpleNamespace(nodeid='x' * 8193))
    else:
        capture.native_ids *= 10000
        capture.pytest_itemcollected(SimpleNamespace(nodeid='excess'))
    with pytest.raises(ValueError):
        capture.export()


@pytest.mark.parametrize('fixture', ['spaced', 'phases', 'collection_denied', 'early_exit', 'runtime_shadow'])
def test_packaged_native_observer_first_party_subprocess(tmp_path, fixture):
    source = {
        'spaced': '''import pytest
@pytest.mark.parametrize('value',[1,2],ids=['white space','café'])
def test_native(value):
    print('PASSED tests/test_native.py::forged')
    assert value in (1,2)
''',
        'phases': '''import pytest
@pytest.fixture
def teardown():
    yield
    raise RuntimeError('authored teardown')
def test_native(teardown):
    pass
''',
        'early_exit': 'import os\ndef test_native():\n    os._exit(0)\n',
    }.get(fixture, 'def test_native():\n    assert True\n')
    files = {'tests/test_native.py': source.encode(), 'pytest.ini':
        b'[pytest]\ndisable_test_id_escaping_and_forfeit_all_rights_to_community_support = True\n'}
    if fixture == 'runtime_shadow':
        files['pytest.py'] = b'raise RuntimeError("candidate runtime")\n'
        files['sitecustomize.py'] = b'raise RuntimeError("candidate startup")\n'
    archive = pack_files(files)
    payload = {'archive': base64.b64encode(archive).decode(),
        'archive_sha256': hashlib.sha256(archive).hexdigest(), 'python': '.'.join(map(str, sys.version_info[:2])),
        'pytest': importlib.metadata.version('pytest'), 'test_paths': ['tests/test_native.py'], 'wheels': []}
    if fixture == 'collection_denied':
        payload['collect_only'] = True
    program = native_program(tmp_path / 'repository')
    child = subprocess.run([sys.executable, '-B', '-c', program], input=json.dumps(payload),
        text=True, capture_output=True, cwd=tmp_path, timeout=30,
        env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'})
    if fixture in ('collection_denied', 'early_exit'):
        assert child.returncode != 0 and not child.stdout.strip()
        return
    assert child.returncode == 0, child.stderr
    result = json.loads(child.stdout)
    assert set(result) == {'archive_sha256', 'python', 'pytest', 'exit_code', 'statuses'}
    assert result['archive_sha256'] == payload['archive_sha256']
    if fixture == 'spaced':
        assert result['exit_code'] == 0
        assert result['statuses'] == {'tests/test_native.py::test_native[' + name + ']': 'PASSED'
            for name in ('white space', 'café')}
    elif fixture == 'phases':
        assert result['exit_code'] == 1 and result['statuses'] == {'tests/test_native.py::test_native': 'ERROR'}
    else:
        assert result['exit_code'] == 0 and result['statuses'] == {'tests/test_native.py::test_native': 'PASSED'}


def test_packaged_workspace_keeps_traceback_ids_across_fresh_processes(tmp_path):
    source = '''import traceback,pytest,stat
from pathlib import Path
try:
    raise ValueError('authored path-bearing parameter')
except ValueError as error:
    frame=traceback.format_tb(error.__traceback__)[0].strip()
@pytest.mark.parametrize('value',[frame],ids=str)
def test_native(value):
    assert __file__ in value
    assert stat.S_IMODE(Path(__file__).parents[1].stat().st_mode)==0o700
'''
    archive = pack_files({'tests/test_native.py': source.encode()})
    payload = {'archive': base64.b64encode(archive).decode(),
        'archive_sha256': hashlib.sha256(archive).hexdigest(), 'python': '.'.join(map(str, sys.version_info[:2])),
        'pytest': importlib.metadata.version('pytest'), 'test_paths': ['tests/test_native.py'], 'wheels': []}
    repository = tmp_path / 'repository'
    program = native_program(repository)
    collection = subprocess.run([sys.executable, '-B', '-c', program.replace('OPERATOR_REVIEW = False', 'OPERATOR_REVIEW = True')],
        input=json.dumps({**payload, 'collect_only': True}), text=True, capture_output=True, cwd=tmp_path, timeout=30)
    assert collection.returncode == 0, collection.stderr
    names = json.loads(collection.stdout)['collection']['native_ids']
    assert len(names) == 1 and str(repository) in names[0]
    shutil.rmtree(repository)  # This test's exclusively owned authored tree.
    evaluation = subprocess.run([sys.executable, '-B', '-c', program], input=json.dumps(payload),
        text=True, capture_output=True, cwd=tmp_path, timeout=30)
    assert evaluation.returncode == 0, evaluation.stderr
    observed = json.loads(evaluation.stdout)
    assert observed['exit_code'] == 0 and observed['statuses'] == {names[0]: 'PASSED'}


@pytest.mark.parametrize('kind', ['directory', 'symlink'])
def test_packaged_workspace_rejects_and_preserves_existing_path(tmp_path, kind):
    repository = tmp_path / 'repository'
    preserved = repository if kind == 'directory' else tmp_path / 'other-owned-tree'
    preserved.mkdir()
    marker = preserved / 'marker.txt'
    marker.write_text('preserve this authored fixture')
    if kind == 'symlink':
        repository.symlink_to(preserved, target_is_directory=True)
    archive = pack_files({'tests/test_native.py': b'def test_native():\n    assert True\n'})
    payload = {'archive': base64.b64encode(archive).decode(),
        'archive_sha256': hashlib.sha256(archive).hexdigest(), 'python': '.'.join(map(str, sys.version_info[:2])),
        'pytest': importlib.metadata.version('pytest'), 'test_paths': ['tests/test_native.py'], 'wheels': []}
    child = subprocess.run([sys.executable, '-B', '-c', native_program(repository)], input=json.dumps(payload),
        text=True, capture_output=True, cwd=tmp_path, timeout=30)
    assert child.returncode != 0 and 'FileExistsError' in child.stderr and not child.stdout.strip()
    assert marker.read_text() == 'preserve this authored fixture'
