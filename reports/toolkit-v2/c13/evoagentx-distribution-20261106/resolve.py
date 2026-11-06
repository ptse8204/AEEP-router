"""Resolve binary-only candidates for the pinned EvoAgentX source without installing them."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT / '.aeep' / HERE.name / 'resolution'
AUTHORITY = HERE.parent / 'pipeline-standing-authority-20261104.json'
SOURCE = HERE / 'source-result.json'
REQUIREMENTS = HERE.parent / 'proposal-optimizer-preparation-20261105/evoagentx-base-requirements.json'
PLATFORMS = ('manylinux_2_28_aarch64', 'manylinux_2_17_aarch64', 'manylinux2014_aarch64')
GIB = 1024**3


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(name, value):
    with (HERE / name).open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')


def prepare():
    requirements = read(REQUIREMENTS)
    assert read(SOURCE)['revision'] == requirements['source_revision']
    root_requirements = [item['runtime_requirement'] for item in requirements['base_requirements']]
    assert len(root_requirements) == 18 and not requirements['optional_extras_selected']
    path = HERE / 'resolution-review.json'
    review = {
        'purpose': 'Resolve candidate wheel pins for the exact source revision without building or installing anything.',
        'source_revision': requirements['source_revision'], 'requirements': root_requirements,
        'platform_tags': PLATFORMS, 'python': '3.12', 'implementation': 'cp', 'abi': 'cp312',
        'python_executable': str(Path(sys.executable).resolve()), 'maximum_seconds': 150,
        'minimum_free_gib': 52, 'retries': 0, 'cache_enabled': False,
        'index': 'https://pypi.org/simple', 'permitted_artifact_host': 'files.pythonhosted.org',
        'possible_network_artifacts': 'pip may fetch wheels for metadata if the index lacks sidecars',
        'install': False, 'models': 0, 'cash_usd': '0',
    }
    review['files'] = {str(p): sha(p) for p in (
        SOURCE, REQUIREMENTS, AUTHORITY, Path(__file__), Path(sys.executable).resolve(),
    )}
    write(path.name, review)
    identity = sha(path)
    write('resolution-authority.json', {'review_sha256': identity, 'first_attempt': True,
                                        'standing_authority_sha256': sha(AUTHORITY)})
    return identity


def resolve(identity):
    path = HERE / 'resolution-review.json'
    review = read(path)
    authority = read(HERE / 'resolution-authority.json')
    assert authority['first_attempt'] and identity == sha(path) == authority['review_sha256']
    assert shutil.disk_usage(ROOT).free >= review['minimum_free_gib'] * GIB
    assert all(sha(file) == expected for file, expected in review['files'].items())
    WORK.mkdir(mode=0o700)
    write('resolution-started.json', {'review_sha256': identity})
    raw_report = WORK / 'pip-resolution.json'
    args = [review['python_executable'], '-B', '-m', 'pip', '--isolated',
            '--disable-pip-version-check', '--no-cache-dir', 'install', '--dry-run',
            '--ignore-installed', '--only-binary=:all:', '--index-url', review['index'],
            '--timeout', '10', '--retries', str(review['retries']),
            '--python-version', review['python'], '--implementation', review['implementation'],
            '--abi', review['abi'], '--report', str(raw_report)]
    for platform in review['platform_tags']:
        args.extend(('--platform', platform))
    args.extend(review['requirements'])
    env = {'HOME': str(WORK), 'TMPDIR': str(WORK), 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C',
           'PIP_CONFIG_FILE': '/dev/null', 'PYTHONDONTWRITEBYTECODE': '1'}
    log = WORK / 'pip.log'
    started = time.monotonic()
    with log.open('xb') as stream:
        result = subprocess.run(args, env=env, cwd=WORK, stdin=subprocess.DEVNULL, stdout=stream,
                                stderr=subprocess.STDOUT, timeout=review['maximum_seconds'], check=False)
    evidence = {'review_sha256': identity, 'exit_code': result.returncode,
                'log_sha256': sha(log), 'wall_seconds': time.monotonic() - started,
                'target': 'CPython 3.12 Linux arm64', 'installed_packages': 0, 'models': 0,
                'dependency_markers_require_linux_review': True, 'candidate_lock_only': True}
    if result.returncode != 0:
        write('resolution-result.json', evidence)
        raise SystemExit(result.returncode)
    raw = read(raw_report)
    rows = []
    for entry in raw['install']:
        metadata = entry['metadata']
        artifact = entry['download_info']
        url = urlsplit(artifact['url'])
        name = unquote(url.path.rsplit('/', 1)[-1])
        assert url.scheme == 'https' and url.netloc == review['permitted_artifact_host']
        assert name.endswith('.whl') and not url.query and not url.fragment and not entry.get('is_yanked')
        digest = artifact['archive_info']['hashes']['sha256']
        assert len(digest) == 64 and int(digest, 16) >= 0
        rows.append({'name': metadata['name'], 'version': metadata['version'], 'filename': name,
                     'url': artifact['url'], 'sha256': digest, 'requested': entry['requested'],
                     'requires_python': metadata.get('requires_python'),
                     'requires_dist': metadata.get('requires_dist', [])})
    assert 18 <= len(rows) <= 100 and sum(row['requested'] for row in rows) == 18
    assert shutil.disk_usage(ROOT).free >= 50 * GIB
    evidence.update(pip_version=raw['pip_version'], count=len(rows),
                    candidates=sorted(rows, key=lambda row: row['name'].lower()))
    write('resolution-result.json', evidence)
    return {key: value for key, value in evidence.items() if key != 'candidates'}


parser = argparse.ArgumentParser()
commands = parser.add_mutually_exclusive_group(required=True)
commands.add_argument('--prepare', action='store_true')
commands.add_argument('--resolve')
args = parser.parse_args()
print(prepare() if args.prepare else json.dumps(resolve(args.resolve)))
