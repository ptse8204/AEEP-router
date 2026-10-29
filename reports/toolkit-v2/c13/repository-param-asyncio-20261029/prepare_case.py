"""Enable one pinned cached test plugin as inert data; retain every assertion."""
import ast
import asyncio
import base64
import hashlib
import json
from pathlib import Path
import zipfile

from packaging.requirements import Requirement
from packaging.version import Version
from aeep.assessment.repository_suites import RepositorySuiteCase, SuiteAssetV5, grade_suite_output, pack_files

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def asset(path):
    return SuiteAssetV5(path=str(path.resolve()), sha256=sha(path.read_bytes()), size_bytes=path.stat().st_size)


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


async def main():
    old = HERE.parent / 'repository-cached-audits-20261029'
    prepared = json.loads((old / 'prepared-cases.json').read_text())
    seed = next(c for c in json.loads((ROOT / prepared['cases_file']).read_text()) if c['input']['task_id'].startswith('holoviz__param-1073'))
    wheel = ROOT / '.aeep/repository-corpus-expansion-20261022-wheels/pytest_asyncio-1.2.0-py3-none-any.whl'
    assert wheel.stat().st_size == 15095 and sha(wheel.read_bytes()) == '8e17ae5e46d8e7efe51ab6494dd2010f4ca8dae51652aa3c8d55acf50bfb2e99'
    with zipfile.ZipFile(wheel) as archive:
        metadata = archive.read(next(n for n in archive.namelist() if n.endswith('/METADATA'))).decode()
        entry = archive.read(next(n for n in archive.namelist() if n.endswith('/entry_points.txt'))).decode()
        assert 'asyncio = pytest_asyncio.plugin' in entry
        assert 'Version: 1.2.0' in metadata and 'License-Expression: Apache-2.0' in metadata
        assert 'Tag: py3-none-any' in archive.read(next(n for n in archive.namelist() if n.endswith('/WHEEL'))).decode()
        notices = []
        for name in archive.namelist():
            if name.endswith(('LICENSE', 'LICENSE.txt', 'NOTICE')):
                target = HERE / 'licenses' / Path(name).name
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(archive.read(name))
                notices.append({'path': str(target.relative_to(ROOT)), 'sha256': sha(target.read_bytes())})
    assert notices
    requirements = []
    for line in metadata.splitlines():
        if line.startswith('Requires-Dist: '):
            requirement = Requirement(line.removeprefix('Requires-Dist: '))
            applies = requirement.marker is None or requirement.marker.evaluate({'python_version': '3.13', 'python_full_version': '3.13.0', 'extra': ''})
            requirements.append({'requirement': str(requirement), 'applies': applies})
            if applies:
                assert requirement.name == 'pytest' and Version('8.3.5') in requirement.specifier
    current = json.loads(json.dumps(seed))
    current['truth']['wheels'].append(asset(wheel).model_dump(mode='json'))
    current['truth']['pytest_plugins'] = ['pytest_asyncio.plugin']
    current['provenance'] += ' Fresh optional runtime:exact cached pytest-asyncio1.2.0 registered explicitly;all original30identities/source/reference/negative bytes remain. Prior unregistered-option failure retained.'
    case = RepositorySuiteCase.model_validate(current)
    assert case.input.model_dump(mode='json') == seed['input'] and case.reference.model_dump(mode='json') == seed['reference']
    assert case.truth.source.model_dump(mode='json') == seed['truth']['source'] and case.truth.tests.model_dump(mode='json') == seed['truth']['tests']
    assert case.fault_outputs == seed['fault_outputs'] and len(case.truth.pass_to_pass) == 30
    private = ROOT / '.aeep/repository-param-asyncio-20261029'
    private.mkdir(mode=0o700, exist_ok=False)
    save(private / 'cases.json', [case.model_dump(mode='json')])
    old_record = next(r for r in json.loads((ROOT / json.loads((old / 'operation-review.json').read_text())['records_file']).read_text()) if r['case_id'] == case.input.task_id)
    save(private / 'records.json', [old_record])
    captures = []
    for label in ('reference', 'counterexample'):
        class Captured(Exception):
            pass
        seen = []
        async def capture(payload):
            seen.append(payload)
            raise Captured()
        try:
            await grade_suite_output(case.input.model_dump(mode='json'), case.truth.model_dump(mode='json'), old_record[label], capture)
        except Captured:
            pass
        assert len(seen) == 1
        path = private / (label + '-payload.json')
        path.write_text(json.dumps(seen[0], separators=(',', ':')))
        assert sha(path.read_bytes()) == sha(json.dumps(json.loads(path.read_text()), separators=(',', ':')).encode())
        captures.append({'variant': label, 'payload': str(path.relative_to(ROOT)), 'sha256': sha(path.read_bytes())})
        if label == 'reference':
            collected = {**seen[0], 'collect_only': True}
            collection = private / 'collection-payload.json'
            collection.write_text(json.dumps(collected, separators=(',', ':')))
    code = '''import asyncio
import importlib.metadata
import pytest
import pytest_asyncio

def test_registration_and_origin(pytestconfig):
    assert importlib.metadata.version('pytest-asyncio') == '1.2.0'
    assert 'pytest_asyncio-1.2.0-py3-none-any.whl/pytest_asyncio/' in pytest_asyncio.__file__
    assert pytestconfig.getini('asyncio_default_fixture_loop_scope') == 'function'

@pytest.mark.asyncio
async def test_event_loop():
    await asyncio.sleep(0)
    assert asyncio.get_running_loop().is_running()
'''
    ast.parse(code)
    archive = pack_files({'tests/test_asyncio_support.py': code.encode(),
        'pytest.ini': b'[pytest]\nasyncio_default_fixture_loop_scope = function\nasyncio_mode = strict\nfilterwarnings = error\n'})
    payload = {'archive': base64.b64encode(archive).decode(), 'archive_sha256': sha(archive),
        'python': '3.13', 'pytest': '8.3.5', 'test_paths': ['tests/test_asyncio_support.py'],
        'pytest_plugins': ['pytest_asyncio.plugin'], 'source_modules': [],
        'wheels': [{'filename': Path(w.path).name, 'sha256': w.sha256, 'data': base64.b64encode(w.read()).decode()} for w in case.truth.wheels]}
    support = {'payload': payload, 'payload_sha256': sha(json.dumps(payload, separators=(',', ':')).encode()),
        'archive_sha256': payload['archive_sha256'], 'required_nodes': ['tests/test_asyncio_support.py::test_registration_and_origin', 'tests/test_asyncio_support.py::test_event_loop']}
    save(HERE / 'support-probe.json', support)
    save(HERE / 'prepared-case.json', {'cases_file': str((private / 'cases.json').relative_to(ROOT)),
        'records_file': str((private / 'records.json').relative_to(ROOT)),
        'collection': {'case_id': case.input.task_id, 'payload': str(collection.relative_to(ROOT)),
            'sha256': sha(collection.read_bytes()), 'payload_file_sha256': sha(collection.read_bytes()), 'archive_sha256': collected['archive_sha256']},
        'variants': captures, 'extra_wheel': asset(wheel).model_dump(mode='json'),
        'license': 'Apache-2.0', 'notices': notices, 'requirements': requirements,
        'original30identities_source_tests_reference_and_negative_unchanged': True,
        'all_wire_and_file_digests_match': True, 'new_source_or_plugin_executions': 0,
        'no_download_install_or_build': True})
    print(json.dumps({'prepared': True, 'source_cases': 1, 'required_ids': 30, 'extra_wheel_bytes': 15095,
        'plugin': 'pytest_asyncio.plugin', 'actual_executions': 0}))


if __name__ == '__main__':
    asyncio.run(main())
