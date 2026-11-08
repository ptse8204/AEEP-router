"""Acquire the pinned public website dependencies without running npm or package code."""

import argparse
import base64
import hashlib
import json
import re
import shutil
import tarfile
import time
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT / '.aeep' / HERE.name
AUTHORITY = HERE.parent / 'pipeline-standing-authority-20261104.json'
AUDIT = HERE / 'managed-toolchain-audit.json'
LOCK = ROOT / '.aeep/skillsbench-stack-9a1f4dd5/tasks/react-performance-debugging/environment/website/package-lock.json'
REVIEW = HERE / 'node-acquisition-review.json'
MIB = 1024**2
RESERVE = 50 * 1024**3
MAX_DOWNLOAD = 128 * MIB
MAX_EXPANDED = 512 * MIB
PACKAGE = r'(?:@[a-z0-9_.-]+/)?[a-z0-9_.-]+'
LOCATION = re.compile(rf'(?:node_modules/{PACKAGE}/)*node_modules/{PACKAGE}\Z')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(name, data):
    with (HERE / name).open('x') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')


def artifacts():
    audit = read(AUDIT)
    lock = read(LOCK)
    assert sha(LOCK) == audit['public_lockfile_sha256'] and lock['lockfileVersion'] == 3
    selected = {}
    for location, entry in sorted(lock['packages'].items()):
        if not location or 'linux' not in entry.get('os', ['linux']) or 'arm64' not in entry.get('cpu', ['arm64']):
            continue
        name = location.split('node_modules/')[-1]
        if name == '@next/swc-linux-arm64-musl':
            continue
        assert LOCATION.fullmatch(location) and '..' not in PurePosixPath(location).parts
        assert not any(entry.get(key) for key in ('hasInstallScript', 'link', 'inBundle'))
        url = urlsplit(entry['resolved'])
        assert url.scheme == 'https' and url.netloc == 'registry.npmjs.org'
        assert not url.query and not url.fragment and url.path.endswith('.tgz')
        algorithm, sri = entry['integrity'].split('-', 1)
        digest = base64.b64decode(sri, validate=True)
        assert algorithm == 'sha512' and len(digest) == 64
        row = dict(name=name, version=entry['version'], url=entry['resolved'], sha512=digest.hex())
        artifact = selected.setdefault(row['sha512'], {**row, 'locations': []})
        assert all(artifact[key] == value for key, value in row.items())
        artifact['locations'].append(location)
    assert sum(len(row['locations']) for row in selected.values()) == audit['linux_arm64_glibc_package_count']
    assert any(row['url'] == audit['gnu_next_compiler']['resolved'] for row in selected.values())
    return list(selected.values())


class DenyRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('unexpected registry redirect')


def inspect(path, row):
    members, notices, metadata, size, root = set(), {}, None, 0, None
    with tarfile.open(path, 'r|gz') as archive:
        for entry in archive:
            parts = PurePosixPath(entry.name)
            assert parts.parts and '..' not in parts.parts
            if root is None:
                root = parts.parts[0]
                assert re.fullmatch(r'[A-Za-z0-9_.-]+', root) and root not in {'.', '..'}
            assert parts.parts[0] == root
            assert str(parts) == entry.name.rstrip('/') and '\\' not in entry.name
            assert entry.isdir() or entry.isfile()
            assert parts not in members and len(members) < 25_000
            members.add(parts)
            size += entry.size
            assert size <= 256 * MIB
            if parts.parts == (root, 'package.json'):
                assert entry.isfile() and entry.size <= MIB
                metadata = json.load(archive.extractfile(entry))
            if len(parts.parts) == 2 and entry.isfile() and parts.name.lower().startswith(('license', 'licence', 'copying', 'notice')):
                assert entry.size <= MIB
                notices[entry.name] = hashlib.sha256(archive.extractfile(entry).read()).hexdigest()
    assert metadata and metadata['name'] == row['name'] and metadata['version'] == row['version']
    return dict(archive_root=root, license=metadata.get('license'), notices=notices,
                member_count=len(members), expanded_bytes=size)


def freeze():
    rows = artifacts()
    write(REVIEW.name, {
        'scope': 'First archive-only acquisition for the ordinary ARM64 React worker. No npm, extraction, package code or models.',
        'assets': {str(path): sha(path) for path in (Path(__file__).resolve(), LOCK, AUDIT, AUTHORITY)},
        'registry': 'https://registry.npmjs.org', 'archives': rows, 'maximum_requests': len(rows),
        'maximum_download_bytes': MAX_DOWNLOAD, 'maximum_expanded_bytes': MAX_EXPANDED,
        'maximum_seconds': 600, 'automatic_retries': False, 'provider_transfer': False,
        'model_turns': 0, 'cash_usd': '0', 'minimum_host_free_gib': 50,
    })
    identity = sha(REVIEW)
    write('node-acquisition-authority.json', {'review_sha256': identity, 'first_attempt': True,
                                            'standing_authority_sha256': sha(AUTHORITY)})
    print(identity)


def execute(identity):
    review = read(REVIEW)
    assert sha(REVIEW) == identity
    assert read(HERE / 'node-acquisition-authority.json') == {
        'review_sha256': identity, 'first_attempt': True, 'standing_authority_sha256': sha(AUTHORITY),
    }
    assert all(sha(Path(name)) == digest for name, digest in review['assets'].items())
    assert review['archives'] == artifacts()
    assert not (HERE / 'node-acquisition-started.json').exists()
    assert shutil.disk_usage(ROOT).free >= RESERVE + MAX_DOWNLOAD
    destination = WORK / 'npm-archives'
    destination.mkdir(mode=0o700)
    write('node-acquisition-started.json', {'review_sha256': identity})
    opener = build_opener(ProxyHandler({}), DenyRedirect())
    facts = {'review_sha256': identity, 'archives': [], 'requests': 0, 'bytes_received': 0,
             'passed': False, 'models': 0, 'packages_executed': False}
    start = time.monotonic()
    expanded = 0
    try:
        for row in review['archives']:
            assert time.monotonic() - start < review['maximum_seconds']
            assert shutil.disk_usage(ROOT).free >= RESERVE + MAX_DOWNLOAD - facts['bytes_received']
            assert facts['requests'] < review['maximum_requests']
            facts['requests'] += 1
            with opener.open(row['url'], timeout=15) as response:
                assert response.geturl() == row['url'] and response.status == 200
                length = int(response.headers['Content-Length'])
                assert 0 < length <= MAX_DOWNLOAD - facts['bytes_received']
                data = bytearray()
                while len(data) < length:
                    assert time.monotonic() - start < review['maximum_seconds']
                    chunk = response.read(min(65536, length - len(data)))
                    facts['bytes_received'] += len(chunk)
                    if not chunk:
                        raise ValueError('short archive response')
                    data.extend(chunk)
            assert hashlib.sha512(data).hexdigest() == row['sha512']
            target = destination / (row['sha512'] + '.tgz')
            with target.open('xb') as stream:
                stream.write(data)
            target.chmod(0o400)
            metadata = inspect(target, row)
            expanded += metadata['expanded_bytes']
            assert expanded <= MAX_EXPANDED
            facts['archives'].append({'name': row['name'], 'version': row['version'], 'sha512': row['sha512'],
                                      'bytes': length, **metadata})
        facts['passed'] = True
    except Exception as error:
        facts.update(error_type=type(error).__name__, stopped_package=row['name'])
        raise
    finally:
        facts['wall_seconds'] = time.monotonic() - start
        facts['expanded_bytes'] = expanded
        write('node-acquisition-result.json', facts)
    print(json.dumps({key: value for key, value in facts.items() if key != 'archives'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument('--freeze', action='store_true')
    flags.add_argument('--execute-delegated')
    args = parser.parse_args()
    if args.freeze:
        freeze()
    else:
        execute(args.execute_delegated)
