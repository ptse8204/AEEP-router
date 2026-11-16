"""Replay cached patches as data and stage hash-bound inputs for protected reproduction."""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path, PurePosixPath

from aeep.assessment.repository_suites import SuiteInput, pack_files
from aeep.errors import ConfigurationError

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
INTAKE = ROOT / '.aeep/completion-20261116/source-bound-leads.json'
OUT = INTAKE.parent / 'patch-batch-v1'
HELPERS = {
    'patch': HERE.parent / 'repository-suite-integration-20261022/prepare-development-assets.py',
    'archive': HERE.parent / 'repository-large-archives-20261027/prepare-cases.py',
}
ROW_KEYS = ('repo', 'base_commit', 'patch', 'test_patch', 'FAIL_TO_PASS', 'PASS_TO_PASS')
TEST_ROOT_NAMES = {'test', 'tests', 'testing'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_reviewed_helpers():
    loaded = {}
    for name, path in HELPERS.items():
        packed = subprocess.check_output(
            ['git', 'show', '6782f617:' + path.relative_to(ROOT).as_posix()], cwd=ROOT
        )
        if packed != path.read_bytes():
            raise ValueError('inert helper differs from its reviewed historical bytes')
        spec = spec_from_file_location('intake_' + name, path)
        assert spec is not None and spec.loader is not None
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        loaded[name] = module
    return loaded


def stage_file(folder, name, data):
    path = folder / name
    with path.open('xb') as stream:
        stream.write(data)
    return {'file': name, 'sha256': sha(data), 'bytes': len(data)}


def snapshot(root):
    files = {}
    for path in root.rglob('*'):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError('patch introduced a nonregular file')
        if path.is_file():
            files[path.relative_to(root).as_posix()] = path.read_bytes()
    return files


def test_roots(nodes):
    modules, roots = set(), set()
    for node in nodes:
        module, sep, identity = node.partition('::')
        path = PurePosixPath(module)
        if (not sep or not identity or path.is_absolute() or module != path.as_posix()
                or '..' in path.parts or path.suffix != '.py'):
            raise ValueError('published test lacks a canonical Python test identity')
        indices = [i for i, part in enumerate(path.parts[:-1]) if part in TEST_ROOT_NAMES]
        if not indices:
            raise ValueError('published tests need explicit root review')
        modules.add(module)
        roots.add('/'.join(path.parts[:indices[0] + 1]))
    return sorted(modules), sorted(roots)


def python_source(name, roots):
    path = PurePosixPath(name)
    return (path.suffix == '.py' and path.name not in {'setup.py', 'conftest.py'}
            and not path.name.startswith('test_') and not path.name.endswith('_test.py')
            and not set(path.parts) & TEST_ROOT_NAMES
            and not any(path.is_relative_to(root) for root in roots))


def assess(lead, helpers):
    binding = lead['source_bindings'][0]
    archived = ROOT / binding['archive']
    raw = archived.read_bytes()
    if sha(raw) != binding['sha256']:
        raise ValueError('cached archive drifted')
    row_bytes = archived.with_name('row.json').read_bytes()
    row = json.loads(row_bytes)
    semantic = sha(json.dumps({key: row[key] for key in ROW_KEYS}, sort_keys=True).encode())
    if (semantic != lead['metadata_semantic_sha256'] or row['instance_id'] != lead['instance_id']
            or row['repo'].casefold() != lead['repository'].casefold() or row['base_commit'] != lead['base_commit']):
        raise ValueError('cached issue and tests differ from the pinned queue')
    if row['install_config'].get('env_vars'):
        raise ValueError('published runtime declares external environment inputs')

    files = helpers['archive'].normalize_large(raw)
    for notice in binding['license_notices']:
        data = files[notice['file']]
        if sha(data) != notice['sha256'] or len(data) != notice['bytes']:
            raise ValueError('archive license bytes differ from the acquisition record')

    fail, preserve = row['FAIL_TO_PASS'], row['PASS_TO_PASS']
    nodes = [*fail, *preserve]
    if not fail or not preserve or len(nodes) != len(set(nodes)):
        raise ValueError('published issue and preservation identities must be distinct')
    modules, roots = test_roots(nodes)
    with tempfile.TemporaryDirectory(prefix='aeep-inert-corpus-', dir='/private/tmp') as temporary:
        root = Path(temporary)
        for name, data in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        helpers['patch'].apply(root, row['test_patch'], root.parent)
        overlaid = snapshot(root)
        overlay = {name: data for name, data in overlaid.items() if files.get(name) != data}
        if (not overlay or not set(files) <= overlaid.keys() or not set(modules) <= overlaid.keys()
                or any(not any(PurePosixPath(name).is_relative_to(r) for r in roots) for name in overlay)):
            raise ValueError('published test overlay exceeds the declared protected roots')
        helpers['patch'].apply(root, row['patch'], root.parent)
        repaired = snapshot(root)
    if repaired.keys() != overlaid.keys():
        raise ValueError('published repair adds or removes files')
    changed = sorted(name for name in repaired if repaired[name] != overlaid[name])
    edits = [name for name in changed if python_source(name, roots)]
    omissions = sorted(set(changed) - set(edits))
    if any(PurePosixPath(name).suffix not in {'.md', '.rst'} for name in omissions):
        raise ValueError('published repair includes non-editable behavior or configuration')
    bodies = [name for name in edits if helpers['archive'].executable(repaired[name]) !=
              helpers['archive'].executable(overlaid[name])]
    if not bodies:
        raise ValueError('published repair has no observed Python body change')
    public = pack_files(files, large=True)
    protected = pack_files(overlay, large=True)
    repair = {name: repaired[name].decode() for name in edits}
    family = 'multi-file-repair' if len(bodies) > 1 else 'single-file-repair'
    task = row['problem_statement'] + ('\n\n' + row['interface'] if row.get('interface') else '')
    SuiteInput(task_id=row['instance_id'], family=family, source_sha256=sha(public),
               editable_paths=edits, task=task)
    return {
        'repository': row['repo'], 'revision': row['base_commit'],
        'source_archive_sha256': sha(raw), 'dataset_row_sha256': sha(row_bytes),
        'metadata_semantic_sha256': semantic, 'license_notices': binding['license_notices'],
        'published_python': row['install_config']['python'], 'family': family,
        'required_issue_tests': len(fail), 'required_preservation_tests': len(preserve),
        'test_roots': roots, 'test_modules': modules, 'executable_changes': bodies,
        'editable_changes': edits, 'omitted_documentation_changes': omissions,
    }, {
        'source.tar.gz': public,
        'tests.tar.gz': protected,
        'repair.json': json.dumps(repair, sort_keys=True).encode(),
        'required.json': json.dumps({'fail_to_pass': fail, 'pass_to_pass': preserve}).encode(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    output = parser.parse_args().output.resolve()
    if not output.is_relative_to(INTAKE.parent):
        parser.error('output must be a new directory within the private intake workspace')
    if shutil.disk_usage(INTAKE.parent).free < 50 * 1024**3 + 64 * 1024**2:
        raise RuntimeError('source screening needs storage above the 50 GiB reserve')
    helpers = load_reviewed_helpers()
    output.mkdir(mode=0o700)
    source = INTAKE.read_bytes()
    leads = [lead for lead in json.loads(source) if lead['source_status'] == 'matches_acquisition_and_license_record']
    results = []
    for lead in leads:
        record = {'case_id': lead['instance_id']}
        try:
            facts, assets = assess(lead, helpers)
        except (AssertionError, ConfigurationError, KeyError, OSError, subprocess.CalledProcessError,
                SyntaxError, ValueError) as error:
            record.update(status='needs_scope_or_asset_review', reason=type(error).__name__)
            if isinstance(error, ValueError) and not isinstance(error, UnicodeError):
                record['detail'] = str(error).splitlines()[0][:180]
        else:
            folder = output / lead['instance_id']
            folder.mkdir(mode=0o700)
            record.update(facts, status='ready_for_runtime_review',
                          assets=[stage_file(folder, name, data) for name, data in assets.items()])
        results.append(record)
    with (output / 'private-index.json').open('x') as stream:
        json.dump({'source_inventory_sha256': sha(source), 'records': results}, stream, indent=2)
        stream.write('\n')


if __name__ == '__main__':
    main()
