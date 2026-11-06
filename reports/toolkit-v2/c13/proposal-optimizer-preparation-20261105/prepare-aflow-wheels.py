"""Resolve exact AFlow lock entries to public wheels for the retained Linux guest."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from packaging.tags import compatible_tags, cpython_tags
from packaging.utils import canonicalize_name, parse_wheel_filename

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
RUNTIME = ROOT / '.aeep' / HERE.name
SOURCES = json.loads((HERE / 'source-contracts.json').read_bytes())
LOCK = RUNTIME / 'aflow/requirements.txt'
LOCK_SHA = hashlib.sha256(LOCK.read_bytes()).hexdigest()
assert LOCK_SHA == SOURCES['components']['aflow']['files']['requirements.txt']['sha256']

# Known target is CPython 3.12 on Linux ARM64, with Linux 2.28 glibc
# compatibility. Do not choose sdist or native host artifacts.
platforms = [f'manylinux_2_{n}_aarch64' for n in range(28, 16, -1)] + ['manylinux2014_aarch64']
tags = list(cpython_tags((3, 12), platforms=platforms))
tags += list(compatible_tags((3, 12), interpreter='cp312', platforms=platforms))
tag_rank = {tag: index for index, tag in reversed(list(enumerate(tags)))}
entries = LOCK.read_text().splitlines()
assert all(re.fullmatch(r'[A-Za-z0-9_.-]+==[0-9][A-Za-z0-9_.-]*', line) for line in entries)
assert len(entries) == len(set(entries)) and len(entries) <= 64


def select(entry):
    name, version = entry.split('==')
    url = f'https://pypi.org/pypi/{canonicalize_name(name)}/{version}/json'
    request = urllib.request.Request(url, headers={'User-Agent': 'AEEP pinned wheel metadata review'})
    with urllib.request.urlopen(request, timeout=15) as response:
        raw = response.read(1024**2 + 1)
    assert len(raw) <= 1024**2
    release = json.loads(raw)
    assert canonicalize_name(release['info']['name']) == canonicalize_name(name)
    assert release['info']['version'] == version
    eligible = []
    for artifact in release['urls']:
        if artifact['yanked'] or artifact['packagetype'] != 'bdist_wheel':
            continue
        package, resolved, _, available = parse_wheel_filename(artifact['filename'])
        assert package == canonicalize_name(name) and str(resolved) == version
        matching = set(tag_rank) & available
        if matching:
            assert artifact['url'].startswith('https://files.pythonhosted.org/')
            assert re.fullmatch('[a-f0-9]{64}', artifact['digests']['sha256'])
            eligible.append((min(tag_rank[tag] for tag in matching), artifact['filename'], artifact))
    if not eligible:
        return {'name': name, 'version': version, 'status': 'NO_COMPATIBLE_WHEEL', 'metadata_url': url}
    rank, filename, wheel = min(eligible)
    return {'name': name, 'version': version, 'filename': filename, 'sha256': wheel['digests']['sha256'],
            'bytes': wheel['size'], 'url': wheel['url'], 'metadata_url': url,
            'metadata_sha256': hashlib.sha256(raw).hexdigest(), 'tag_rank': rank,
            'license_expression': release['info'].get('license_expression'),
            'license_classifier': [entry for entry in release['info'].get('classifiers', [])
                                   if entry.startswith('License ::')],
            'requires_dist': release['info'].get('requires_dist') or []}


with ThreadPoolExecutor(max_workers=4) as pool:
    rows = list(pool.map(select, entries))
result = {
    'source_revision': SOURCES['components']['aflow']['revision'], 'lock_sha256': LOCK_SHA,
    'target': 'CPython 3.12, Linux ARM64, manylinux glibc <=2.28 floor',
    'pinned_entries': len(rows), 'compatible_wheel_count': sum('filename' in row for row in rows),
    'total_known_bytes': sum(row.get('bytes', 0) for row in rows), 'artifacts': rows,
    'wheel_files_downloaded': 0, 'installed': False, 'upstream_code_executed': False, 'models': 0,
    'remaining': ['inspect exact wheel METADATA and notices', 'verify dependency closure offline',
                  'review adapted bounded evaluator and generated-code isolation before execution'],
}
with (HERE / 'aflow-wheel-selection.json').open('x') as stream:
    json.dump(result,stream,indent=2)
    stream.write('\n')
print({k:result[k] for k in ('pinned_entries','compatible_wheel_count','total_known_bytes')})
