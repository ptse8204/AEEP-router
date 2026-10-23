"""Collect pinned Git blobs, excluding unrelated docs and unselected test suites."""
import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import shutil
import urllib.request

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
CACHE = ROOT / '.aeep/repository-corpus-tree-scopes-20261022'
IDENTITIES = ['tobymao__sqlglot-4643', 'tobymao__sqlglot-5256']


def read(url, ceiling):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(urllib.request.Request(url, headers={'User-Agent': 'AEEP-source-review/2', 'Accept': 'application/vnd.github+json'}), timeout=30) as stream:
        data = stream.read(ceiling + 1)
    assert len(data) <= ceiling
    return data


def main():
    assert shutil.disk_usage(ROOT).free > 50 * 1024**3 + 100 * 1024**2
    CACHE.mkdir(exist_ok=False)
    spec = importlib.util.spec_from_file_location('aeep_packer', HERE.parent / 'repository-suite-integration-20261022/prepare-development-assets.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    results = []
    for identity in IDENTITIES:
        row = json.loads((ROOT / '.aeep/repository-corpus-expansion-20261022-sources' / identity / 'row.json').read_text())
        directory = CACHE / identity
        directory.mkdir()
        (directory / 'row.json').write_text(json.dumps(row, indent=2) + '\n')
        record = {'instance_id': identity, 'repository': row['repo'], 'revision': row['base_commit'], 'private_cache': str(directory.relative_to(ROOT)), 'external_code_executed': False}
        results.append(record)
        try:
            url = f"https://api.github.com/repos/{row['repo']}/git/trees/{row['base_commit']}?recursive=1"
            prior = ROOT / '.aeep/repository-corpus-tree-review-20261022' / (identity + '-tree.json')
            tree_bytes = prior.read_bytes() if prior.exists() else read(url, 2_000_000)
            tree = json.loads(tree_bytes)
            assert not tree['truncated']
            (directory / 'git-tree.json').write_bytes(tree_bytes)
            entries = {e['path']: e for e in tree['tree'] if e['type'] == 'blob'}
            assert len(entries) < 10_000
            files = {}
            selected_tests = {n.split('::')[0] for n in row['FAIL_TO_PASS'] + row['PASS_TO_PASS']}
            names = {n for n in entries if n.startswith('sqlglot/')}
            names |= {n for n in entries if '/' not in n and (n in ('pyproject.toml', 'setup.cfg', 'setup.py', 'README.md', 'README.rst', 'tox.ini', 'pytest.ini', 'conftest.py') or n.upper().startswith(('LICENSE', 'NOTICE', 'COPYING')))}
            names |= selected_tests
            def fetch(name):
                entry = entries[name]
                assert entry['mode'] == '100644' or entry['mode'] == '100755'
                assert entry['size'] <= 650_000
                data = read(f"https://raw.githubusercontent.com/{row['repo']}/{row['base_commit']}/{name}", 650_000)
                assert len(data) == entry['size']
                assert hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == entry['sha']
                return name, data
            while names - files.keys():
                with ThreadPoolExecutor(max_workers=5) as pool:
                    files.update(pool.map(fetch, sorted(names - files.keys())))
                for name, data in list(files.items()):
                    if not name.startswith('tests/') or not name.endswith('.py'):
                        continue
                    path = PurePosixPath(name)
                    for parent in path.parents:
                        init = (parent / '__init__.py').as_posix()
                        if init in entries:
                            names.add(init)
                        conftest = (parent / 'conftest.py').as_posix()
                        if conftest in entries:
                            names.add(conftest)
                    for node in ast.walk(ast.parse(data)):
                        mods = [node.module] if isinstance(node, ast.ImportFrom) and node.module and not node.level else [a.name for a in node.names] if isinstance(node, ast.Import) else []
                        for mod in mods:
                            if mod.startswith('tests.'):
                                candidate = mod.replace('.', '/') + '.py'
                                if candidate in entries:
                                    names.add(candidate)
                assert sum(map(len, files.values())) < 4_000_000
            fixture_calls = []
            for name in selected_tests:
                for node in ast.walk(ast.parse(files[name])):
                    if isinstance(node, ast.Call) and ((isinstance(node.func, ast.Name) and ('fixture' in node.func.id or node.func.id == 'open')) or (isinstance(node.func, ast.Attribute) and node.func.attr in ('open', 'read_text', 'read_bytes'))):
                        fixture_calls.append({'file': name, 'line': node.lineno, 'function': ast.unparse(node.func)})
            assert not fixture_calls, 'Selected module needs explicit fixture-file review'
            packed = helper.pack_files(files)
            (directory / 'source-only.tar.gz').write_bytes(packed)
            retained = [{'path': name, 'git_blob': entries[name]['sha'], 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)} for name, data in sorted(files.items())]
            omitted = [{'path': n, 'git_blob': e['sha'], 'bytes': e['size'], 'mode': e['mode']} for n, e in entries.items() if n not in files]
            record.update(status='STATIC_SCOPE_REVIEW_REQUIRED', tree_url=url, tree_sha=tree['sha'], tree_json_sha256=hashlib.sha256(tree_bytes).hexdigest(),
                          retained=retained, omitted=omitted, normalized_archive_bytes=len(packed), normalized_archive_sha256=hashlib.sha256(packed).hexdigest(),
                          selected_test_modules=sorted(selected_tests), selected_module_fixture_calls=fixture_calls,
                          scope='Full sqlglot package, root license/configuration and selected test modules plus their static tests.* helper imports. Other upstream test suites/fixtures/docs/CI are outside this declared task scope. Git blob hashes verified for every retained byte. No official full-checkout/runtime equivalence claimed.')
        except Exception as exc:
            record.update(status='UNRESOLVED', error_type=type(exc).__name__, error=str(exc)[:200])
    (HERE / 'git-tree-source-scopes.json').write_text(json.dumps({'sources': results, 'external_code_executed': False, 'cases_adopted': 0, 'stages_frozen': False}, indent=2) + '\n')
    print(json.dumps([{k: x.get(k) for k in ('instance_id', 'status', 'normalized_archive_bytes', 'error')} for x in results]))


if __name__ == '__main__':
    main()
