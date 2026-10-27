"""Prepare source-bound references and counterexamples as inert data only."""
import ast
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase, SuiteAsset, SuiteInput, SuiteTruth, SuiteTruthV2, SuiteTruthV4, archive_files, grade_suite_output, pack_files, compressed_patch_artifact
from aeep.assessment.repository_tasks import RepositoryPatch

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUT = ROOT / '.aeep/repository-test-root-cases-20261027'
ENTRIES = [
    ('MindscapeHQ__raygun4py-119', False, []),
    ('carsdotcom__skelebot-280', True, []),
    ('cdent__gabbi-342', False, []),
    ('collective__icalendar-878', True, []),
    ('collective__icalendar-880', False, []),
    ('collective__icalendar-921', True, []),
    ('macbre__sql-metadata-552', True, []),
    ('macbre__sql-metadata-553', False, []),
    ('macbre__sql-metadata-583', False, []),
    ('researchobject__ro-crate-py-248', False, []),
    ('sopel-irc__sopel-2653', True, []),
    ('twisted__towncrier-687', True, []),
]



def sha(data):
    return hashlib.sha256(data).hexdigest()


def asset(path):
    return SuiteAsset(path=str(path.resolve()), sha256=sha(path.read_bytes()), size_bytes=path.stat().st_size)


def executable(data):
    class Strip(ast.NodeTransformer):
        def visit_Expr(self, node):
            return None if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str) else self.generic_visit(node)
    return ast.dump(Strip().visit(ast.parse(data)), include_attributes=False)


def select_nodes(existing, required):
    tree = ast.parse(existing)
    previous = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'pytest_collection_modifyitems'), None)
    if previous:
        assert [x.arg for x in previous.args.args] == ['config', 'items'] and not previous.decorator_list
    hook = ('\n\n# AEEP declared-test scope; upstream assertions and prior collection hook retained.\n'
            + '_AEEP_REQUIRED_NODES = frozenset(' + repr(required) + ')\n'
            + '_AEEP_PREVIOUS_COLLECTION = globals().get("pytest_collection_modifyitems")\n'
            + 'def pytest_collection_modifyitems(config, items):\n'
            + '    if _AEEP_PREVIOUS_COLLECTION is not None:\n        _AEEP_PREVIOUS_COLLECTION(config, items)\n'
            + '    selected = [item for item in items if item.nodeid in _AEEP_REQUIRED_NODES]\n'
            + '    deselected = [item for item in items if item.nodeid not in _AEEP_REQUIRED_NODES]\n'
            + '    items[:] = selected\n'
            + '    if deselected:\n        config.hook.pytest_deselected(items=deselected)\n')
    called, removed = [], []
    namespace = {'pytest_collection_modifyitems': lambda config, items: called.append(True)} if previous else {}
    exec(compile(hook, 'aeep-first-party-selector', 'exec'), namespace)
    items = [SimpleNamespace(nodeid=n) for n in [*required, 'tests/unselected.py::outside']]
    config = SimpleNamespace(hook=SimpleNamespace(pytest_deselected=lambda **kw: removed.extend(kw['items'])))
    namespace['pytest_collection_modifyitems'](config, items)
    assert [x.nodeid for x in items] == required and len(removed) == 1
    assert bool(called) == bool(previous)
    return (existing + hook).encode()


async def main():
    OUT.mkdir(exist_ok=False)
    spec = importlib.util.spec_from_file_location('aeep_inert_patch_helper', HERE.parent / 'repository-suite-integration-20261022/prepare-development-assets.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    source_records = {x['instance_id']: x for x in json.loads((HERE / 'source-review.json').read_text())['sources']}
    scopes = {x['instance_id']: x for f in ('source-scope-review.json', 'git-tree-source-scopes.json') for x in json.loads((HERE / f).read_text())['sources'] if x['status'] in ('SOURCE_SCOPE_REVIEW_REQUIRED', 'STATIC_SCOPE_REVIEW_REQUIRED')}
    pure = json.loads((HERE / 'pure-wheel-review.json').read_text())
    assert pure['closure_verified']
    extras = {x['project']: asset(ROOT / x['private_cache']) for x in pure['pins']}
    core = [asset(ROOT / x['private_cache']) for x in json.loads((HERE.parent / 'repository-replacement-runtime-20261022/runtime-wheel-review.json').read_text())['pins'] if x['project'] in ('pytest', 'pluggy', 'iniconfig', 'packaging')]
    assert len(core) == 4
    cases, descriptions, variants, errors = [], [], [], []
    for identity, audit, wheel_names in ENTRIES:
        try:
            record = scopes.get(identity, source_records[identity])
            directory = ROOT / record['private_cache']
            row = json.loads((directory / 'row.json').read_text())
            required_nodes = row['FAIL_TO_PASS'] + row['PASS_TO_PASS']
            roots = set()
            for node in required_nodes:
                parts = node.split('::')[0].split('/')
                index = next(i for i, name in enumerate(parts[:-1]) if name in {'test', 'tests', 'testing'})
                roots.add('/'.join(parts[:index + 1]))
            assert len(roots) == 1, 'This authoring helper currently prepares one published test root per case'
            test_root = next(iter(roots))
            if identity in scopes:
                raw = (directory / 'source-only.tar.gz').read_bytes()
                assert sha(raw) == record['normalized_archive_sha256']
                files = archive_files(raw)
            else:
                assert record['status'] == 'STATIC_REVIEW_REQUIRED'
                raw = (directory / 'source.tar.gz').read_bytes()
                assert sha(raw) == record['archive_sha256']
                files, _ = helper.normalize(raw)
            licenses = {n: d for n, d in files.items() if '/' not in n and n.upper().startswith(('LICENSE', 'COPYING', 'NOTICE'))}
            assert licenses
            license_records = []
            for name, data in licenses.items():
                path = HERE / 'licenses' / identity / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                license_records.append({'path': str(path.relative_to(ROOT)), 'sha256': sha(data), 'bytes': len(data)})
            with tempfile.TemporaryDirectory(prefix='aeep-inert-case-', dir='/private/tmp') as temporary:
                work = Path(temporary).resolve()
                for name, data in files.items():
                    p = work / name
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(data)
                helper.apply(work, row['test_patch'], work.parent)
                after_test = {p.relative_to(work).as_posix(): p.read_bytes() for p in work.rglob('*') if p.is_file()}
                assert set(files) <= after_test.keys()
                overlay = {n: d for n, d in after_test.items() if files.get(n) != d}
                assert overlay and all(n.startswith(test_root + '/') for n in overlay)
                gold_sections = []
                omitted_scope_docs = []
                for part in row['patch'].split('diff --git ')[1:]:
                    name = part.splitlines()[0].split()[0].removeprefix('a/')
                    if name not in after_test:
                        assert identity == 'nhairs__python-json-logger-39' and name == 'docs/changelog.md'
                        omitted_scope_docs.append(name)
                    else:
                        gold_sections.append('diff --git ' + part)
                helper.apply(work, ''.join(gold_sections), work.parent)
                fixed = {p.relative_to(work).as_posix(): p.read_bytes() for p in work.rglob('*') if p.is_file()}
                assert set(fixed) == set(after_test)
            changed = sorted(n for n in fixed if fixed[n] != after_test[n])
            source_names = [n for n in changed if n.endswith('.py') and not set(Path(n).parts) & {'tests', 'test', 'testing'} and n not in ('setup.py', 'conftest.py')]
            omitted = [n for n in changed if n not in source_names] + omitted_scope_docs
            assert all(n.endswith(('.md', '.rst', '.txt')) for n in omitted), 'Non-source reference edit needs separate review'
            bodies = [n for n in source_names if executable(after_test[n]) != executable(fixed[n])]
            assert bodies
            changes = {n: fixed[n].decode() for n in source_names}
            prefixes = {n.split('/')[0] + '/' for n in source_names if '/' in n}
            editable = sorted(n for n in files if n.endswith('.py') and (n in source_names or any(n.startswith(prefix) for prefix in prefixes)) and not set(Path(n).parts) & {'tests', 'test', 'testing'} and Path(n).name != 'conftest.py')
            assert editable and len(editable) <= 256
            public = {**files, **{n: s.encode() for n, s in changes.items()}} if audit else files
            source = pack_files(public)
            case_id = identity + ('-aeep-contract-audit' if audit else '-declared-tests')
            contract = row['problem_statement'] + ('\n\n' + row['interface'] if row.get('interface') else '')
            if audit:
                contract = 'Audit this current snapshot against the contract below. Change listed source only if it violates that contract. Otherwise return an empty patch and preserve source bytes.\n\n' + contract
            contract += '\n\nAEEP scope: listed existing Python source and declared issue/preservation tests. New/deleted files, packaging, unrelated suites and external services are outside this task. All declared upstream assertions are retained.'
            value = SuiteInput(task_id=case_id, task=contract, family='contract-audit' if audit else 'multi-file-repair' if len(bodies) > 1 else 'single-file-repair', source_sha256=sha(source), editable_paths=editable)
            binding = content_digest(value)
            reference = compressed_patch_artifact(RepositoryPatch(base_sha256=binding, files={} if audit else changes))
            negative = compressed_patch_artifact(RepositoryPatch(base_sha256=binding, files={n: files[n].decode() for n in changes} if audit else {}))
            faults = [negative if audit else compressed_patch_artifact(RepositoryPatch(base_sha256=binding, files={source_names[0]: files[source_names[0]].decode()}))]
            f2p = [] if audit else row['FAIL_TO_PASS']
            p2p = row['FAIL_TO_PASS'] + row['PASS_TO_PASS'] if audit else row['PASS_TO_PASS']
            upstream_required = list(row['FAIL_TO_PASS'] + row['PASS_TO_PASS'])
            if audit:
                guard = 'import hashlib\nfrom pathlib import Path\n\ndef test_snapshot_preserved():\n    root = Path(__file__).resolve().parents[' + str(len(Path(test_root).parts)) + ']\n    expected = ' + repr({n: sha(public[n]) for n in editable}) + '\n    assert all(hashlib.sha256((root / n).read_bytes()).hexdigest() == digest for n, digest in expected.items())\n'
                ast.parse(guard)
                guard_path = test_root + '/test_aeep_preservation.py'
                assert guard_path not in files and guard_path not in overlay
                overlay[guard_path] = guard.encode()
                p2p = [*p2p, guard_path + '::test_snapshot_preserved']
            required = [*f2p, *p2p]
            original_config = overlay.get(test_root + '/conftest.py', files.get(test_root + '/conftest.py', b'')).decode()
            overlay[test_root + '/conftest.py'] = select_nodes(original_config, required)
            test_paths = sorted({n.split('::')[0] for n in required})
            case_dir = OUT / case_id
            case_dir.mkdir()
            src = case_dir / (sha(source) + '.tar.gz')
            src.write_bytes(source)
            tests = case_dir / 'tests.tar.gz'
            tests.write_bytes(pack_files(overlay))
            ref = case_dir / 'reference.json'
            ref.write_text(json.dumps(reference, separators=(',', ':')))
            kwargs = dict(input_sha256=binding, source=asset(src), tests=asset(tests), wheels=[*core, *(extras[n] for n in wheel_names)], python='3.13', pytest='8.3.5', test_paths=test_paths, fail_to_pass=f2p, pass_to_pass=p2p)
            plugins = ['pytest_asyncio.plugin'] if 'pytest-asyncio' in wheel_names else []
            truth = SuiteTruthV4(**kwargs, pytest_plugins=plugins, patch_encoding='gzip-json', test_roots=[test_root])
            case = RepositorySuiteCase(schema_version='assessment.repository-suite-case.v4', input=value, truth=truth, reference=asset(ref), fault_outputs=faults, source_repository='https://github.com/' + row['repo'], source_revision=row['base_commit'], independent_case_id=case_id, license='Retained upstream license text hashes; issue metadata CC-BY-4.0', origin_kind='authored_control' if audit else 'upstream_issue', split='qualification', used_for_development=False,
                provenance='Unadopted pre-stage source/runtime curation. Source revision and exact retained license hashes are in prepared-cases.json. ' + ('Authored fixed-snapshot audit: published Python repair applied to public source, empty reference, original-source negative and private byte-preservation guard. ' if audit else 'Published Python repair reference and original-source negative. ') + 'All original required assertions retained; protected exact-node collection composes the prior collection hook and selects only declared identities. No whole-checkout, official benchmark/runtime equivalence or arbitrary repository-preservation claim. Scope/omissions reviewed before models; no model outcomes used. Extra wheels are private optional grader supports, not host/core dependencies.')
            outputs = [('reference', reference), ('counterexample', negative)]
            if not audit and len(bodies) > 1:
                for index, name in enumerate(bodies, 1):
                    outputs.append(('partial-' + str(index), compressed_patch_artifact(RepositoryPatch(base_sha256=binding, files={**changes, name: files[name].decode()}))))
            for label, output in outputs:
                class Captured(Exception):
                    pass
                async def capture(payload):
                    path = case_dir / (label + '-payload.json')
                    path.write_text(json.dumps(payload, separators=(',', ':')))
                    variants.append({'case': case_id, 'variant': label, 'artifact': output, 'payload': str(path.relative_to(ROOT)), 'sha256': sha(path.read_bytes()), 'bytes': path.stat().st_size})
                    raise Captured()
                try:
                    await grade_suite_output(value.model_dump(mode='json'), truth.model_dump(mode='json'), output, capture)
                except Captured:
                    pass
                else:
                    raise AssertionError('Inert preparation unexpectedly returned a grade')
            descriptions.append({'id': case_id, 'original_issue_id': identity, 'repository': row['repo'], 'revision': row['base_commit'], 'family': value.family, 'origin_kind': case.origin_kind,
                                 'source_record': record['private_cache'], 'source_sha256': sha(source), 'source_bytes': len(source), 'executable_changed_files': bodies, 'reference_changed_files': source_names,
                                 'omitted_non_source_reference_changes': omitted, 'required_tests': len(required), 'upstream_required_identities': upstream_required,
                                 'authored_preservation_guard': audit, 'license_records': license_records, 'declared_python': row['install_config']['python'], 'adapted_python': '3.13',
                                 'portable_wheels': wheel_names, 'explicit_plugins': plugins, 'test_roots': [test_root], 'adopted': False, 'stage_assignment_frozen': False})
            cases.append(case)
        except Exception as exc:
            errors.append({'id': identity, 'error_type': type(exc).__name__, 'error': str(exc)[:250], 'external_code_executed': False})
    cases_file = OUT / 'cases.json'
    cases_file.write_text(json.dumps([c.model_dump(mode='json') for c in cases], indent=2) + '\n')
    variants_file = OUT / 'variants.json'
    variants_file.write_text(json.dumps(variants, indent=2) + '\n')
    report = {'prepared_cases': len(cases), 'cases_file': str(cases_file.relative_to(ROOT)), 'cases_file_sha256': sha(cases_file.read_bytes()),
              'variants_file': str(variants_file.relative_to(ROOT)), 'cases': descriptions, 'errors': errors,
              'payloads': [{k: v for k, v in x.items() if k != 'artifact'} for x in variants], 'external_code_executed': False, 'models': 0,
              'cases_adopted': 0, 'stages_frozen': False, 'infrastructure_acceptance': False}
    (HERE / 'prepared-cases.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'prepared_cases': len(cases), 'payloads': len(variants), 'errors': errors}))


if __name__ == '__main__':
    asyncio.run(main())
