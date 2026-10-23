"""Read complete bounded archives as inert data, then review source-only scopes."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import urllib.request
import urllib.parse

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
CACHE = ROOT / '.aeep/repository-corpus-source-scopes-20261022'
IDENTITIES = ['tobymao__sqlglot-4618', 'tobymao__sqlglot-4643', 'tobymao__sqlglot-5256',
              'tobymao__sqlglot-6374', 'tobymao__sqlglot-7479',
              'facelessuser__pymdown-extensions-2576', 'package-url__packageurl-python-178',
              'nhairs__python-json-logger-39']
ROOTS = {'tobymao/sqlglot': ['sqlglot', 'tests'], 'facelessuser/pymdown-extensions': ['pymdownx', 'tests'],
         'package-url/packageurl-python': ['src', 'packageurl', 'tests'], 'nhairs/python-json-logger': ['src', 'pythonjsonlogger', 'tests']}


def main():
    assert shutil.disk_usage(ROOT).free > 50 * 1024**3 + 100 * 1024**2
    CACHE.mkdir(exist_ok=False)
    spec = importlib.util.spec_from_file_location('aeep_packer', HERE.parent / 'repository-suite-integration-20261022/prepare-development-assets.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    previous = json.loads((HERE / 'source-review.json').read_text())
    rows = {x['instance_id']: x for x in previous['sources']}
    def collect(identity):
        old = rows[identity]
        row = json.loads((ROOT / old['private_cache'] / 'row.json').read_text())
        directory = CACHE / identity
        directory.mkdir()
        (directory / 'row.json').write_text(json.dumps(row, indent=2) + '\n')
        record = {'instance_id': identity, 'repository': row['repo'], 'revision': row['base_commit'], 'private_cache': str(directory.relative_to(ROOT)),
                  'previous_source_record': old['private_cache'], 'allowed_task_roots': ROOTS[row['repo']], 'external_code_executed': False}
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(urllib.request.Request(old['url'], headers={'User-Agent': 'AEEP-source-review/2'}), timeout=30) as stream:
                assert urllib.parse.urlparse(stream.geturl()).hostname == 'codeload.github.com'
                data = stream.read(3_000_001)
            (directory / 'full-upstream.tar.gz').write_bytes(data)
            record.update(downloaded_bytes=len(data), full_archive_sha256=hashlib.sha256(data).hexdigest())
            assert len(data) <= 3_000_000, 'Full source review read bound exceeded; partial data not parsed'
            selected, omitted, full_total = {}, [], 0
            with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
                prefix = None
                for member in archive:
                    path = PurePosixPath(member.name)
                    assert not path.is_absolute() and '..' not in path.parts
                    prefix = prefix or path.parts[0]
                    assert path.parts[0] == prefix
                    if member.isdir():
                        continue
                    name = PurePosixPath(*path.parts[1:]).as_posix()
                    full_total += member.size
                    assert full_total <= 30_000_000, 'Inert full source review decompression bound'
                    root = PurePosixPath(name).parts[0]
                    include = root in ROOTS[row['repo']] or (len(PurePosixPath(name).parts) == 1 and (name in ('pyproject.toml', 'setup.cfg', 'setup.py', 'README.md', 'README.rst', 'tox.ini', 'pytest.ini', 'conftest.py') or name.upper().startswith(('LICENSE', 'COPYING', 'NOTICE'))))
                    if not member.isfile():
                        assert not include, 'Nonregular member inside selected task scope'
                        omitted.append({'path': name, 'kind': 'nonregular', 'size': member.size})
                        continue
                    content = archive.extractfile(member).read()
                    entry = {'path': name, 'size': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
                    if include:
                        assert not set(PurePosixPath(name).parts) & {'.git', '.codex', '.agents', 'AGENTS.md', 'auth.json', '.env', 'credentials.json'}
                        assert name not in selected
                        selected[name] = content
                    else:
                        omitted.append(entry)
            record.update(full_unpacked_bytes=full_total, retained_regular_files=len(selected), retained_bytes=sum(map(len, selected.values())), omitted=omitted)
            normalized = helper.pack_files(selected)
            (directory / 'source-only.tar.gz').write_bytes(normalized)
            record.update(status='SOURCE_SCOPE_REVIEW_REQUIRED', normalized_archive_sha256=hashlib.sha256(normalized).hexdigest(), normalized_archive_bytes=len(normalized),
                          scope='Complete declared source and tests trees plus root build/test configuration and licenses. Unrelated documentation/examples/CI omitted. This is not a full upstream checkout.')
        except Exception as exc:
            record.update(status='EXCLUDED_SCOPE_UNRESOLVED', error_type=type(exc).__name__, error=str(exc)[:200])
        return record
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(collect, IDENTITIES))
    output = {'sources': results, 'maximum_total_read_bytes': len(IDENTITIES) * 3_000_001, 'cases_adopted': 0, 'models': 0,
              'external_code_executed': False, 'runtime_bounds_changed': False}
    (HERE / 'source-scope-review.json').write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps({'results': [{k: x.get(k) for k in ('instance_id', 'status', 'normalized_archive_bytes', 'retained_bytes', 'error')} for x in results],
                      'downloaded_bytes': sum(x.get('downloaded_bytes', 0) for x in results)}))


if __name__ == '__main__':
    main()
