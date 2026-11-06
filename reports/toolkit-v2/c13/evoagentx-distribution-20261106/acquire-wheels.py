"""Retain hash-pinned EvoAgentX dependencies for static review and later offline build."""

import argparse
import hashlib
import json
import shutil
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile

from packaging.utils import canonicalize_name

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PRIVATE = ROOT / '.aeep' / HERE.name / 'wheelhouse'
AUTHORITY = HERE.parent / 'pipeline-standing-authority-20261104.json'
CANDIDATES = HERE / 'verified-candidates.json'
GIB = 1024**3


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(name, value):
    with (HERE / name).open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')


def prepare():
    lock = read(CANDIDATES)
    rows = lock['artifacts']
    assert len(rows) == lock['artifact_count'] == 87
    assert sum(row['bytes'] for row in rows) == lock['artifact_bytes'] < 128 * 1024**2
    assert shutil.disk_usage(ROOT).free >= 52 * GIB
    assert not PRIVATE.exists()
    cache = ROOT / '.aeep' / 'proposal-optimizer-preparation-20261105' / 'aflow-wheelhouse'
    reused = {}
    for row in rows:
        filename = row['filename']
        url = urlsplit(row['url'])
        assert Path(filename).name == filename and filename.endswith('.whl')
        assert url.scheme == 'https' and url.netloc == 'files.pythonhosted.org' and url.path.endswith('/' + filename)
        candidate = cache / filename
        if candidate.is_file() and not candidate.is_symlink() and digest(candidate) == row['sha256']:
            reused[filename] = str(candidate)
    review = {
        'purpose': 'Acquire and inspect only the verified EvoAgentX Linux ARM64 dependency wheels.',
        'target': lock['target'], 'source_revision': lock['source_revision'],
        'files': {str(path): digest(path) for path in (CANDIDATES, AUTHORITY, Path(__file__))},
        'cache_hits': reused, 'max_bytes': lock['artifact_bytes'], 'artifact_count': len(rows),
        'max_seconds': 240, 'parallel_fetches': 4, 'automatic_retries': False, 'minimum_free_gib': 50,
        'install': False, 'upstream_execution': False, 'model_turns': 0, 'cash_usd': '0',
    }
    write('acquisition-review.json', review)
    identity = digest(HERE / 'acquisition-review.json')
    write('acquisition-authority.json', {'review_sha256': identity, 'first_attempt': True,
                                         'standing_authority_sha256': digest(AUTHORITY)})
    return identity


def acquire_one(row, review, deadline):
    filename = row['filename']
    target = PRIVATE / filename
    assert target.parent == PRIVATE and shutil.disk_usage(ROOT).free >= review['minimum_free_gib'] * GIB
    assert time.monotonic() < deadline
    cache = review['cache_hits'].get(filename)
    if cache:
        source = Path(cache)
        assert not source.is_symlink() and digest(source) == row['sha256']
        with source.open('rb') as inp, target.open('xb') as out:
            shutil.copyfileobj(inp, out)
    else:
        with urllib.request.urlopen(row['url'], timeout=12) as inp, target.open('xb') as out:
            assert inp.geturl() == row['url']
            remaining = row['bytes']
            while chunk := inp.read(min(262_144, remaining + 1)):
                assert time.monotonic() < deadline
                remaining -= len(chunk)
                assert remaining >= 0
                out.write(chunk)
            assert remaining == 0
    assert target.stat().st_size == row['bytes'] and digest(target) == row['sha256']
    target.chmod(0o400)
    with ZipFile(target) as archive:
        entries = archive.infolist()
        assert len(entries) == len(set(archive.namelist())) <= 20_000
        assert sum(item.file_size for item in entries) < 1024**3
        metadata, = [item for item in entries if item.filename.endswith('.dist-info/METADATA')]
        assert metadata.file_size < 1024**2
        data = archive.read(metadata)
        parsed = BytesParser().parsebytes(data)
        assert canonicalize_name(parsed['Name']) == canonicalize_name(row['name'])
        assert parsed['Version'] == row['version']
        assert sorted(parsed.get_all('Requires-Dist', [])) == sorted(row['requires_dist'])
        notices, hooks = {}, []
        for item in entries:
            path = Path(item.filename)
            assert not path.is_absolute() and '..' not in path.parts
            basename = path.name.casefold()
            if basename.endswith('.pth'):
                hooks.append(item.filename)
            if '.dist-info/' in item.filename and not item.is_dir() and basename.startswith(
                ('license', 'copying', 'notice')
            ):
                assert item.file_size <= 2 * 1024**2
                notices[item.filename] = hashlib.sha256(archive.read(item)).hexdigest()
    return {
        'filename': filename, 'name': row['name'], 'version': row['version'], 'bytes': row['bytes'],
        'sha256': row['sha256'], 'metadata_sha256': hashlib.sha256(data).hexdigest(),
        'license_expression': parsed.get('License-Expression'), 'notice_sha256': notices,
        'startup_hooks': sorted(hooks), 'cache_hit': cache is not None,
    }


def execute(identity):
    path = HERE / 'acquisition-review.json'
    review = read(path)
    authority = read(HERE / 'acquisition-authority.json')
    assert identity == digest(path) == authority['review_sha256'] and authority['first_attempt']
    assert all(digest(file) == expected for file, expected in review['files'].items())
    assert shutil.disk_usage(ROOT).free >= 52 * GIB
    PRIVATE.mkdir(mode=0o700)
    write('acquisition-started.json', {'review_sha256': identity})
    clock = time.monotonic()
    result = {'review_sha256': identity, 'passed': False, 'artifacts': [], 'models': 0, 'installed': False}
    rows = read(CANDIDATES)['artifacts']
    try:
        with ThreadPoolExecutor(max_workers=review['parallel_fetches']) as pool:
            futures = {row['filename']: pool.submit(acquire_one, row, review, clock + review['max_seconds'])
                       for row in rows}
            for name, pending in futures.items():
                try:
                    result['artifacts'].append(pending.result())
                except Exception as failure:
                    result.setdefault('failures', []).append({'filename': name, 'type': type(failure).__name__})
        result['passed'] = len(result['artifacts']) == review['artifact_count'] and 'failures' not in result
    finally:
        result['wall_seconds'] = time.monotonic() - clock
        write('acquisition-result.json', result)
    print(json.dumps({**{key: value for key, value in result.items() if key != 'artifacts'},
                      'verified_count': len(result['artifacts'])}))
    raise SystemExit(not result['passed'])


parser = argparse.ArgumentParser()
args = parser.add_mutually_exclusive_group(required=True)
args.add_argument('--prepare', action='store_true')
args.add_argument('--execute')
selected = parser.parse_args()
if selected.prepare:
    print(prepare())
else:
    execute(selected.execute)
