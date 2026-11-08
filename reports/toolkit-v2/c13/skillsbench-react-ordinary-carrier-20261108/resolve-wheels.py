"""Resolve exact Linux counterparts to the previously reviewed package closure."""

import concurrent.futures
import email.parser
import hashlib
import json
import zipfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.tags import cpython_tags
from packaging.utils import canonicalize_name, parse_wheel_filename

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
REVIEW = HERE.parent / 'integration-snapshot-correction-20261103/package-installation.json'
CACHE = ROOT / '.aeep/integration-snapshot-correction-20261103/package-wheels'
NATIVE = {'cffi', 'cryptography', 'psutil', 'pydantic-core', 'pyyaml', 'rpds-py'}
ENV = {
    'python_version': '3.12', 'python_full_version': '3.12.3',
    'os_name': 'posix', 'sys_platform': 'linux', 'platform_system': 'Linux',
    'platform_machine': 'x86_64', 'platform_python_implementation': 'CPython',
    'implementation_name': 'cpython', 'implementation_version': '3.12.3', 'extra': '',
}
PLATFORMS = [f'manylinux_2_{minor}_x86_64' for minor in range(39, 4, -1)]
PLATFORMS += ['manylinux2014_x86_64', 'manylinux2010_x86_64', 'manylinux1_x86_64']
TAG_RANK = {tag: index for index, tag in enumerate(cpython_tags((3,12), ['cp312'], PLATFORMS))}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def cached(row):
    path = CACHE / row['filename']
    assert row['filename'].endswith('-none-any.whl') and sha(path) == row['sha256']
    with zipfile.ZipFile(path) as wheel:
        names = [name for name in wheel.namelist() if name.endswith('.dist-info/METADATA')]
        assert len(names) == 1
        meta = email.parser.BytesParser().parsebytes(wheel.read(names[0]))
    assert canonicalize_name(meta['Name']) == canonicalize_name(row['name'])
    assert meta['Version'] == row['version']
    return row | {'origin': 'retained', 'path': str(path), 'bytes': path.stat().st_size,
                  'requires_python': meta['Requires-Python'],
                  'requires_dist': meta.get_all('Requires-Dist') or []}


def linux(row):
    project = canonicalize_name(row['name'])
    version = row['version']
    api = f'https://pypi.org/pypi/{project}/{version}/json'
    with build_opener(ProxyHandler({})).open(api, timeout=15) as response:
        assert response.geturl() == api and response.status == 200
        raw = response.read(2_000_001)
    assert len(raw) <= 2_000_000
    data = json.loads(raw)
    assert canonicalize_name(data['info']['name']) == project and data['info']['version'] == version
    matches = []
    for artifact in data['urls']:
        if artifact['packagetype'] != 'bdist_wheel' or artifact['yanked']:
            continue
        wheel_name, wheel_version, _build, tags = parse_wheel_filename(artifact['filename'])
        assert wheel_name == project and str(wheel_version) == version
        ranks = [TAG_RANK[tag] for tag in tags if tag in TAG_RANK]
        if ranks:
            matches.append((min(ranks), artifact['filename'], artifact))
    _, filename, artifact = min(matches)
    parsed = urlsplit(artifact['url'])
    assert parsed.scheme == 'https' and parsed.hostname == 'files.pythonhosted.org'
    assert not (parsed.query or parsed.fragment or parsed.username) and parsed.path.endswith('/'+filename)
    return {'name':row['name'], 'version':version, 'filename':filename, 'origin':'pypi',
            'artifact_url':artifact['url'], 'release_metadata':api,
            'release_metadata_sha256':hashlib.sha256(raw).hexdigest(),
            'sha256':artifact['digests']['sha256'], 'bytes':artifact['size'],
            'requires_python':artifact['requires_python'] or data['info']['requires_python'],
            'requires_dist':data['info']['requires_dist'] or [],
            'license_expression':data['info'].get('license_expression'),
            'license_classifiers':[text for text in data['info']['classifiers'] if text.startswith('License :: ')]}


def validate_closure(rows, root_requirements):
    by_name = {canonicalize_name(row['name']): row for row in rows}
    for row in rows:
        assert SpecifierSet(row['requires_python'] or '').contains(ENV['python_full_version'])
    for text in [*root_requirements, *(entry for row in rows for entry in row['requires_dist'])]:
        requirement = Requirement(text)
        if requirement.marker and not requirement.marker.evaluate(ENV):
            continue
        assert not requirement.url
        selected = by_name[canonicalize_name(requirement.name)]
        assert requirement.specifier.contains(selected['version']), text


def main():
    packet = json.loads(REVIEW.read_bytes())
    rows = [row for row in packet['wheels'] if canonicalize_name(row['name']) != 'aeep-agent-router']
    assert len(rows) == 32
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(lambda row: linux(row) if canonicalize_name(row['name']) in NATIVE else cached(row), rows))
    wheel = next(path for path in CACHE.glob('aeep_agent_router-*.whl'))
    project = next(row for row in packet['wheels'] if canonicalize_name(row['name']) == 'aeep-agent-router')
    assert sha(wheel) == project['sha256']
    with zipfile.ZipFile(wheel) as archive:
        path = next(name for name in archive.namelist() if name.endswith('.dist-info/METADATA'))
        roots = email.parser.BytesParser().parsebytes(archive.read(path)).get_all('Requires-Dist')
    validate_closure(rows, roots)
    native = [row for row in rows if row['origin'] == 'pypi']
    assert len(native) == 6 and sum(row['bytes'] for row in native) <= 12 * 1024**2
    evidence = {
        'target': 'CPython 3.12 Linux AMD64, manylinux compatible with Ubuntu 24.04',
        'wheels': rows, 'source_review_sha256': sha(REVIEW),
        'existing_versions_preserved': True, 'metadata_closure_verified': True,
        'download_count': len(native), 'download_bytes': sum(row['bytes'] for row in native),
        'wheel_downloads_performed': False, 'installation_verified': False,
    }
    with (HERE / 'wheel-lock.json').open('x') as stream:
        json.dump(evidence, stream, indent=2); stream.write('\n')
    print(json.dumps({key: value for key, value in evidence.items() if key != 'wheels'}))


if __name__ == '__main__':
    main()
