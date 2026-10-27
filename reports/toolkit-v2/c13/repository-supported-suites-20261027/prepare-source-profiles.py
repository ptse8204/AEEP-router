"""Retain all test assertions while explicitly scoping a non-task CI/config edit."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sections(patch):
    return [(part.splitlines()[0].split()[0].removeprefix('a/'), 'diff --git ' + part) for part in patch.split('diff --git ')[1:]]


def main():
    records = json.loads((HERE / 'source-review.json').read_text())
    original = next(r for r in records['sources'] if r['instance_id'] == 'lincolnloop__goodconf-51')
    path = ROOT / original['private_cache']
    row_bytes = (path / 'row.json').read_bytes()
    row = json.loads(row_bytes)
    specification = importlib.util.spec_from_file_location('existing_inert_patch_helper', HERE.parent / 'repository-suite-integration-20261022/prepare-development-assets.py')
    helper = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(helper)
    data = (path / 'source.tar.gz').read_bytes()
    assert sha(data) == original['archive_sha256']
    files, _ = helper.normalize(data)
    gold = sections(row['patch'])
    tests = sections(row['test_patch'])
    assert {n for n, _ in gold} == {'.gitignore', 'goodconf/__init__.py', 'pyproject.toml'}
    assert {n for n, _ in tests if not n.startswith('tests/')} == {'.github/workflows/test.yml'}
    config_patch = next(text for name, text in gold if name == 'pyproject.toml')
    with tempfile.TemporaryDirectory(prefix='aeep-inert-config-', dir='/private/tmp') as directory:
        work = Path(directory)
        (work / 'pyproject.toml').write_bytes(files['pyproject.toml'])
        helper.apply(work, config_patch, work.parent)
        changed = (work / 'pyproject.toml').read_bytes()
    assert changed == files['pyproject.toml'].replace(b'addopts = "--cov --cov-branch"', b'addopts = "-s --cov --cov-branch"')
    assert changed != files['pyproject.toml']
    files['pyproject.toml'] = changed
    profile = ROOT / '.aeep/repository-supported-goodconf-profile-20261027'
    profile.mkdir(exist_ok=False)
    (profile / 'original-row.json').write_bytes(row_bytes)
    row['patch'] = ''.join(text for name, text in gold if name == 'goodconf/__init__.py')
    row['test_patch'] = ''.join(text for name, text in tests if name.startswith('tests/'))
    assert sections(row['test_patch']) == [(n, t) for n, t in tests if n.startswith('tests/')]
    (profile / 'row.json').write_text(json.dumps(row, indent=2) + '\n')
    archive = helper.pack_files(files)
    (profile / 'source-only.tar.gz').write_bytes(archive)
    entry = {**original, 'private_cache': str(profile.relative_to(ROOT)), 'status': 'SOURCE_SCOPE_REVIEW_REQUIRED', 'normalized_archive_sha256': sha(archive), 'normalized_archive_bytes': len(archive), 'scope': 'Original full bounded source plus the published -s capture flag in pytest configuration. All original coverage flags retained. Source answer remains unmodified until the reference is applied.', 'authored_runtime_configuration': {'file': 'pyproject.toml', 'change': 'Original --cov --cov-branch retained; published -s capture option added equally before grading.', 'sha256': sha(changed)}, 'omitted_non_task_patch_sections': [{'kind': kind, 'path': name, 'sha256': sha(text.encode()), 'reason': 'CI runner/matrix or ignored lockfile metadata, not an executed assertion or source repair.'} for kind, values in [('reference', gold), ('test', tests)] for name, text in values if name == '.gitignore' or name == '.github/workflows/test.yml'], 'original_row_sha256': sha(row_bytes), 'all_upstream_test_assertions_unchanged': True, 'source_subject_execution': False}
    (HERE / 'source-scope-review.json').write_text(json.dumps({'sources': [entry]}, indent=2) + '\n')
    # The successful complete tree scope is distinct from the earlier truncated archive.
    (HERE / 'git-tree-source-scopes.json').write_bytes((HERE.parent / 'repository-workload-batch-20261022/prometheus-git-tree-source-scope.json').read_bytes())
    (HERE / 'source-profile-review.json').write_text(json.dumps(entry, indent=2) + '\n')
    print(json.dumps({'source_profiles': 1, 'assertions_changed': False, 'source_code_changed': False, 'external_execution': False}))


if __name__ == '__main__':
    main()
