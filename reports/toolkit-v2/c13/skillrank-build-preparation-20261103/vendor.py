"""Verify reviewed Cargo archives and stage an offline source directory.

No installer, Cargo, compiler, package script or downloaded code runs here.
Downloads/extraction are called only by the separately approved runtime driver.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import tarfile
import time
import tomllib
import urllib.request
from pathlib import Path, PurePosixPath

MAX_ARCHIVE = 8 * 1024**2
MAX_COMPRESSED = 64 * 1024**2
MAX_EXPANDED = 512 * 1024**2
MAX_FILES = 50000


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        raise ValueError('Cargo source redirects are not permitted')


def unpack(raw: bytes, *, name: str, version: str, expected: str, destination: Path) -> dict:
    if len(raw) > MAX_ARCHIVE or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Cargo archive size or checksum differs from the frozen lock')
    prefix = name + '-' + version
    files = {}
    total = 0
    # Validate every entry before writing any archive content.
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        members = []
        for entry in archive:
            path = PurePosixPath(entry.name)
            if (path.is_absolute() or '..' in path.parts or '\\' in entry.name
                    or not path.parts or path.parts[0] != prefix
                    or not (entry.isdir() or entry.isfile())):
                raise ValueError('Cargo archive contains an unsafe path or entry type')
            if not entry.isfile():
                continue
            relative = PurePosixPath(*path.parts[1:]).as_posix()
            if (relative in files or relative in {'', '.', '.cargo-checksum.json'}
                    or not 0 <= entry.size <= MAX_EXPANDED):
                raise ValueError('Cargo archive has a duplicate/reserved name or oversized file')
            total += entry.size
            if total > MAX_EXPANDED or len(members) >= MAX_FILES:
                raise ValueError('Cargo archive expansion exceeds its bound')
            content = archive.extractfile(entry).read(entry.size + 1)
            if len(content) != entry.size:
                raise ValueError('Cargo archive entry is incomplete')
            files[relative] = hashlib.sha256(content).hexdigest()
            members.append((relative, content))
    if not members or 'Cargo.toml' not in files or destination.exists():
        raise ValueError('Cargo source is missing its manifest or destination is not fresh')
    if any(parent.as_posix() in files for name in files for parent in PurePosixPath(name).parents):
        raise ValueError('Cargo archive file shadows a parent directory')
    destination.mkdir(mode=0o755)
    for relative, content in members:
        target = destination / relative
        target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(content)
        target.chmod(0o444)
    checksum = {'files': files, 'package': expected}
    (destination / '.cargo-checksum.json').write_text(json.dumps(checksum, sort_keys=True) + '\n')
    licenses = sorted(path for path in files if 'license' in path.lower() or 'copying' in path.lower())
    package = tomllib.loads((destination / 'Cargo.toml').read_text())['package']
    license_expression = package.get('license', '')
    license_tokens = set(re.findall(r'[A-Za-z0-9.-]+', license_expression))
    if not license_tokens or not license_tokens <= {
        'MIT', 'Apache-2.0', 'ISC', 'BSD-2-Clause', 'BSD-3-Clause', 'OpenSSL',
        'Unicode-3.0', 'Unicode-DFS-2016', 'MPL-2.0', 'Zlib', 'AND', 'OR',
    }:
        raise ValueError('Cargo source license requires a separate review')
    return {'name': name, 'version': version, 'archive_sha256': expected,
            'compressed_bytes': len(raw), 'expanded_bytes': total,
            'file_count': len(files), 'license_paths': licenses,
            'license_expression': license_expression, 'rust_version': package.get('rust-version')}


def prepare(lock: dict, destination: Path, archives: Path) -> list[dict]:
    if lock['count'] != 86 or len(lock['files']) != 86 or destination.exists() or archives.exists():
        raise ValueError('Expected a fresh exact 86-crate offline closure')
    destination.mkdir(mode=0o755)
    archives.mkdir(mode=0o700)
    total_compressed, total_expanded = 0, 0
    results = []
    deadline = time.monotonic() + 600
    transport = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    for item in lock['files']:
        if (re.fullmatch(r'[A-Za-z0-9_-]+', item['name']) is None
                or re.fullmatch(r'[0-9][A-Za-z0-9.+-]*', item['version']) is None):
            raise ValueError('Cargo source name or version is not a portable basename')
        expected_url = ('https://static.crates.io/crates/' + item['name'] + '/'
                        + item['name'] + '-' + item['version'] + '.crate')
        if item['url'] != expected_url:
            raise ValueError('Cargo download is not its exact public static URL')
        raw = None
        for attempt in range(2):
            if time.monotonic() >= deadline:
                raise TimeoutError('Finite Cargo source download time exhausted')
            try:
                with transport.open(expected_url, timeout=20) as response:
                    if response.geturl() != expected_url:
                        raise ValueError('Cargo source redirect is not permitted')
                    raw = response.read(MAX_ARCHIVE + 1)
                break
            except (TimeoutError, OSError):
                if attempt == 1:
                    raise
        if raw is None:
            raise ValueError('Cargo source transport returned no archive')
        total_compressed += len(raw)
        if total_compressed > MAX_COMPRESSED:
            raise ValueError('Aggregate Cargo archive ceiling exceeded')
        path = archives / (item['name'] + '-' + item['version'] + '.crate')
        path.write_bytes(raw)
        result = unpack(raw, name=item['name'], version=item['version'], expected=item['sha256'],
                        destination=destination / (item['name'] + '-' + item['version']))
        total_expanded += result['expanded_bytes']
        if total_expanded > MAX_EXPANDED:
            raise ValueError('Aggregate Cargo expansion ceiling exceeded')
        results.append(result)
    return results
