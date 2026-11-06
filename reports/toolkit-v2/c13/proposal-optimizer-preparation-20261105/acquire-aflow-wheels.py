"""Acquire only the reviewed AFlow wheel closure, without installing or importing it."""

from __future__ import annotations

import argparse
import email
import hashlib
import json
import shutil
import sys
import time
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PRIVATE = ROOT / '.aeep' / HERE.name / 'aflow-wheelhouse'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


parser = argparse.ArgumentParser()
parser.add_argument('--execute-delegated', required=True)
args = parser.parse_args()
scope = HERE / 'aflow-wheel-acquisition-review.json'
identity = digest(scope)
review = read(scope)
authority = read(HERE / 'aflow-wheel-acquisition-authority.json')
assert identity == args.execute_delegated == authority['review_sha256'] and authority['first_attempt']
assert datetime.now(UTC) < datetime.fromisoformat(review['expires_at'])
for path, expected in review['assets'].items():
    assert digest(Path(path)) == expected, path
selection = read(HERE / 'aflow-wheel-selection.json')
rows = selection['artifacts']
assert len(rows) == review['maximum_files'] == selection['compatible_wheel_count']
assert sum(row['bytes'] for row in rows) <= review['maximum_download_bytes']
assert shutil.disk_usage(ROOT).free >= 51 * 1024**3 and not PRIVATE.exists()
PRIVATE.mkdir(mode=0o700)
write(HERE / 'aflow-wheel-acquisition-started.json', {'review_sha256': identity})
result = {'review_sha256': identity, 'passed': False, 'installed': False,
          'upstream_code_executed': False, 'models': 0, 'artifacts': [], 'unresolved_requirements': []}
start = time.monotonic()
try:
    for row in rows:
        path = PRIVATE / row['filename']
        assert path.parent == PRIVATE and row['url'].startswith('https://files.pythonhosted.org/')
        assert time.monotonic() - start < review['maximum_wall_seconds']
        assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
        cache = review['cache_hits'].get(row['filename'])
        if cache:
            source = Path(cache)
            assert source.is_file() and not source.is_symlink() and digest(source) == row['sha256']
            with source.open('rb') as inp, path.open('xb') as out:
                shutil.copyfileobj(inp, out)
        else:
            request = urllib.request.Request(row['url'], headers={'User-Agent': 'AEEP reviewed public wheel acquisition'})
            with urllib.request.urlopen(request, timeout=30) as inp, path.open('xb') as out:
                assert inp.geturl().startswith('https://files.pythonhosted.org/')
                remaining = row['bytes']
                while chunk := inp.read(min(262144, remaining + 1)):
                    remaining -= len(chunk)
                    assert remaining >= 0
                    out.write(chunk)
            assert remaining == 0
        assert path.stat().st_size == row['bytes'] and digest(path) == row['sha256']
        path.chmod(0o444)
        with zipfile.ZipFile(path) as wheel:
            metadata, = [item for item in wheel.infolist() if item.filename.endswith('.dist-info/METADATA')]
            assert metadata.file_size <= 1024**2
            content = wheel.read(metadata)
            parsed = email.message_from_bytes(content)
            assert canonicalize_name(parsed['Name']) == canonicalize_name(row['name'])
            assert parsed['Version'] == row['version']
            notice = []
            for item in wheel.infolist():
                name = Path(item.filename).name.casefold()
                if '.dist-info/' in item.filename and not item.is_dir() and name.startswith(('license','copying','notice')):
                    assert item.file_size < 2 * 1024**2
                    notice.append({'path':item.filename,'sha256':hashlib.sha256(wheel.read(item)).hexdigest()})
        result['artifacts'].append({
            'name':row['name'],'version':row['version'],'filename':path.name,'sha256':row['sha256'],
            'bytes':row['bytes'],'acquisition':'reviewed_cache' if cache else 'public_index',
            'metadata_sha256':hashlib.sha256(content).hexdigest(),
            'license_expression':parsed.get('License-Expression'),'license_notices':notice,
            'requires_dist':parsed.get_all('Requires-Dist', []),
        })
    versions = {canonicalize_name(row['name']):row['version'] for row in result['artifacts']}
    marker_env = {'python_version':'3.12','python_full_version':'3.12.16','platform_system':'Linux',
                  'sys_platform':'linux','platform_machine':'aarch64','extra':''}
    for row in result['artifacts']:
        for item in row['requires_dist']:
            requirement = Requirement(item)
            if requirement.marker and not requirement.marker.evaluate(marker_env):
                continue
            installed = versions.get(canonicalize_name(requirement.name))
            if installed is None or installed not in requirement.specifier or requirement.url:
                result['unresolved_requirements'].append({'dependency_of':row['name'],'requirement':item})
    result['passed'] = not result['unresolved_requirements']
finally:
    result['elapsed_seconds'] = time.monotonic() - start
    write(HERE / 'aflow-wheel-acquisition-result.json', result)
print({k:result[k] for k in ('passed','elapsed_seconds','unresolved_requirements')})
sys.exit(not result['passed'])
