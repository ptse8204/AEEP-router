"""Verify candidate dependencies against Linux markers and the official wheel index."""

import hashlib
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version

HERE = Path(__file__).resolve().parent
ENVIRONMENT = default_environment() | {
    'implementation_name': 'cpython', 'implementation_version': '3.12.16',
    'os_name': 'posix', 'platform_python_implementation': 'CPython',
    'sys_platform': 'linux', 'platform_system': 'Linux', 'platform_machine': 'aarch64',
    'python_version': '3.12', 'python_full_version': '3.12.16',
}


def read(name):
    return json.loads((HERE / name).read_bytes())


def digest(name):
    return hashlib.sha256((HERE / name).read_bytes()).hexdigest()


def closure(roots, candidates):
    pending = [(value, '') for value in roots]
    checked, reached = set(), set()
    while pending:
        key = pending.pop()
        if key in checked:
            continue
        checked.add(key)
        value, extra = key
        requirement = Requirement(value)
        if requirement.marker:
            marker = str(requirement.marker)
            assert 'platform_release' not in marker and 'platform_version' not in marker
            if not requirement.marker.evaluate(ENVIRONMENT | {'extra': extra}):
                continue
        name = canonicalize_name(requirement.name)
        row = candidates[name]
        assert not requirement.url and requirement.specifier.contains(row['version'])
        reached.add(name)
        pending.extend((dep, selected) for dep in row['requires_dist']
                       for selected in {'', *requirement.extras})
    assert reached == candidates.keys()
    return len(checked)


def publisher_row(row):
    key = canonicalize_name(row['name'])
    name, version, _, tags = parse_wheel_filename(row['filename'])
    assert name == key and version == Version(row['version'])
    assert row['requires_python'] is None or SpecifierSet(row['requires_python']).contains('3.12.16')
    url = f"https://pypi.org/pypi/{quote(key)}/{quote(str(version))}/json"
    with urllib.request.urlopen(url, timeout=10) as response:
        assert response.geturl() == url
        raw = response.read(2 * 1024**2 + 1)
    assert len(raw) <= 2 * 1024**2
    data = json.loads(raw)
    assert canonicalize_name(data['info']['name']) == key and Version(data['info']['version']) == version
    artifact, = [item for item in data['urls'] if item['filename'] == row['filename']]
    assert artifact['url'] == row['url'] and artifact['digests']['sha256'] == row['sha256']
    assert not artifact['yanked'] and 0 < artifact['size'] < 200 * 1024**2
    return {
        **row, 'bytes': artifact['size'], 'pypi_metadata_sha256': hashlib.sha256(raw).hexdigest(),
        'license_expression': data['info'].get('license_expression'),
        'license_classifiers': [name for name in data['info']['classifiers'] if name.startswith('License ::')],
        'tags': sorted(str(tag) for tag in tags),
    }


review, resolution = read('resolution-review.json'), read('resolution-result.json')
assert resolution['review_sha256'] == digest('resolution-review.json') and resolution['exit_code'] == 0
candidates = {canonicalize_name(row['name']): row for row in resolution['candidates']}
assert len(candidates) == resolution['count'] == len(resolution['candidates'])
assert {name for name, row in candidates.items() if row['requested']} == {
    canonicalize_name(Requirement(value).name) for value in review['requirements']
}
checked = closure(review['requirements'], candidates)
with ThreadPoolExecutor(max_workers=8) as pool:
    rows = list(pool.map(publisher_row, candidates.values()))
report = {
    'source_revision': review['source_revision'], 'resolution_sha256': digest('resolution-result.json'),
    'artifacts': rows, 'artifact_count': len(rows), 'artifact_bytes': sum(row['bytes'] for row in rows),
    'root_requirements': len(review['requirements']), 'requirement_marker_checks': checked,
    'target': 'CPython 3.12.16 Linux ARM64', 'wheel_content_review': 'pending',
    'dependencies_installed': False, 'upstream_executed': False, 'model_turns': 0,
}
with (HERE / 'verified-candidates.json').open('x') as stream:
    stream.write(json.dumps(report, indent=2) + '\n')
print(json.dumps({key: value for key, value in report.items() if key != 'artifacts'}))
