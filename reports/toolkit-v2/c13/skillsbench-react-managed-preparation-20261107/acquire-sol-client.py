"""Retain the first reviewed Sol-capable Codex CLI archive without installing it."""

import argparse
import base64
import hashlib
import json
import runpy
import shutil
import tarfile
import time
from pathlib import Path, PurePosixPath
from urllib.request import ProxyHandler, build_opener

HERE = Path(__file__).resolve().parent
helper = runpy.run_path(str(HERE / 'acquire-node-packages.py'))
ROOT, WORK, AUTHORITY, REVIEW = helper['ROOT'], helper['WORK'], helper['AUTHORITY'], HERE / 'sol-client-acquisition-review.json'
sha, read, write = helper['sha'], helper['read'], helper['write']
ARCHIVE = WORK / 'codex-0.159.1-linux-arm64.tgz'
SOURCE = 'https://registry.npmjs.org/@openai/codex/-/codex-0.159.1-linux-arm64.tgz'
INTEGRITY = 'SUuxUCTWkvmzrCPIpRHMlivwSsL2STeUv6Dqm/TkUwYFfaqAQqZ8uIq8+d3SnYJsXiz1bkoiIdy8CSuptfEBfQ=='
MAX_BYTES = 192 * 1024**2
RESERVE = 50 * 1024**3


def freeze():
    blocker = HERE / 'sol-managed-model-blocker.json'
    assert read(blocker)['requested_model_visible'] is False
    write(REVIEW.name, {
        'scope': 'First read-only archive acquisition and static inspection of the pinned Sol-capable CLI release.',
        'pins': {str(p): sha(p) for p in (Path(__file__).resolve(), HERE / 'acquire-node-packages.py', blocker, AUTHORITY)},
        'version': '0.159.1-linux-arm64', 'source': SOURCE, 'integrity': 'sha512-' + INTEGRITY,
        'registry_sha1': '828ec97658789c26aae3cc2a1c6ac079455682ba',
        'publisher_attestation_url': 'https://registry.npmjs.org/-/npm/v1/attestations/@openai%2fcodex@0.159.1-linux-arm64',
        'official_release_notes': 'https://learn.chatgpt.com/docs/changelog',
        'license': 'Apache-2.0', 'maximum_requests': 1, 'maximum_download_bytes': MAX_BYTES,
        'maximum_expanded_bytes': 420 * 1024**2, 'destination': str(ARCHIVE),
        'install_or_execution': False, 'model_turns': 0, 'cash_usd': '0',
        'provider_disclosure': False, 'automatic_retries': False, 'minimum_host_free_gib': 50,
    })
    identity = sha(REVIEW)
    write('sol-client-acquisition-authority.json', {'review_sha256': identity, 'first_attempt': True,
                                                  'standing_authority_sha256': sha(AUTHORITY)})
    print(identity)


def inspect(path, review):
    files, metadata, expanded, notices = {}, None, 0, []
    with tarfile.open(path, 'r|gz') as archive:
        for entry in archive:
            name = PurePosixPath(entry.name)
            assert name.parts[0] == 'package' and '..' not in name.parts and not name.is_absolute()
            assert str(name) == entry.name.rstrip('/') and '\\' not in entry.name
            assert entry.isdir() or entry.isfile()
            if not entry.isfile():
                continue
            assert entry.name not in files and len(files) < 100
            expanded += entry.size
            assert expanded <= review['maximum_expanded_bytes']
            with archive.extractfile(entry) as body:
                if entry.name == 'package/package.json':
                    assert entry.size <= 65536
                    data = body.read()
                    metadata = json.loads(data)
                    digest = hashlib.sha256(data).hexdigest()
                else:
                    digest = hashlib.file_digest(body, 'sha256').hexdigest()
            files[entry.name] = {'sha256': digest, 'bytes': entry.size, 'executable': bool(entry.mode & 0o111)}
            if name.name.casefold().startswith(('license', 'notice', 'copying')):
                notices.append(entry.name)
    assert metadata and metadata['name'] == '@openai/codex'
    assert metadata['version'] == review['version'] and metadata['license'] == review['license']
    assert metadata['os'] == ['linux'] and metadata['cpu'] == ['arm64']
    assert not metadata.get('scripts')
    return files, expanded, notices


def execute(identity):
    review = read(REVIEW)
    assert sha(REVIEW) == identity
    assert read(HERE / 'sol-client-acquisition-authority.json') == {
        'review_sha256': identity, 'first_attempt': True, 'standing_authority_sha256': sha(AUTHORITY),
    }
    assert all(sha(Path(p)) == h for p, h in review['pins'].items())
    assert not ARCHIVE.exists() and not (HERE / 'sol-client-acquisition-started.json').exists()
    assert shutil.disk_usage(ROOT).free >= RESERVE + MAX_BYTES + 1024**3
    assert review['source'] == SOURCE and review['integrity'] == 'sha512-' + INTEGRITY
    opener = build_opener(ProxyHandler({}), helper['DenyRedirect']())
    write('sol-client-acquisition-started.json', {'review_sha256': identity})
    facts = {'review_sha256': identity, 'passed': False, 'download_bytes': 0, 'models': 0, 'executed': False}
    started = time.monotonic()
    try:
        h = hashlib.sha512()
        with opener.open(SOURCE, timeout=15) as response, ARCHIVE.open('xb') as output:
            assert response.geturl() == SOURCE and response.status == 200
            while data := response.read(1024**2):
                facts['download_bytes'] += len(data)
                assert facts['download_bytes'] <= MAX_BYTES and time.monotonic() - started < 180
                assert shutil.disk_usage(ROOT).free >= RESERVE
                h.update(data)
                output.write(data)
        assert base64.b64encode(h.digest()).decode() == INTEGRITY
        with ARCHIVE.open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha1').hexdigest() == review['registry_sha1']
        files, expanded, notices = inspect(ARCHIVE, review)
        facts.update(passed=True, archive_sha256=sha(ARCHIVE), files=files, expanded_bytes=expanded,
                     notices=notices, archive=str(ARCHIVE), license=review['license'])
    except Exception as error:
        facts['error_type'] = type(error).__name__
        raise
    finally:
        if ARCHIVE.exists():
            ARCHIVE.chmod(0o400)
        facts['wall_seconds'] = time.monotonic() - started
        write('sol-client-acquisition-result.json', facts)
    print(json.dumps({k: v for k, v in facts.items() if k != 'files'}))


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
