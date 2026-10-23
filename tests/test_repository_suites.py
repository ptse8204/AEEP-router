"""First-party contract fixtures; fabricated sources are never benchmark evidence."""
import asyncio
import base64
import copy
import hashlib
import io
import json
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import (
    RepositorySuiteCase,
    SuiteAsset,
    SuiteInput,
    SuiteTruth,
    SuiteTruthV2,
    archive_files,
    curated_cases,
    curated_payload,
    decode_patch,
    grade_suite_output,
    pack_files,
    patch_artifact,
    public_archive,
    reference_outputs,
    repository_suite_recipe,
)
from aeep.assessment.repository_tasks import RepositoryPatch
from aeep.errors import ConfigurationError

pytestmark = pytest.mark.assessment_contract
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def suite_cases(tmp_path):
    root = tmp_path.resolve()
    public = root / 'public'
    private = root / 'protected'
    public.mkdir()
    private.mkdir()

    def asset(data, name):
        path = private / name
        path.write_bytes(data)
        return SuiteAsset(path=str(path), sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))

    wheel = asset(b'not executed: first-party fake wheel', 'fixture-1-py3-none-any.whl')
    cases = []
    for index in range(3):
        source = pack_files({'library/core.py': f'def value():\n    return {index}\n'.encode(),
                             'README.md': b'public fixture'})
        digest = hashlib.sha256(source).hexdigest()
        path = public / (digest + '.tar.gz')
        path.write_bytes(source)
        task = SuiteInput(task_id='fixture-' + str(index), task='Repair the first-party fixture.',
                          family='fixture', source_sha256=digest, editable_paths=['library/core.py'])
        expected = content_digest(task)
        reference = patch_artifact(RepositoryPatch(base_sha256=expected, files={'library/core.py': 'def value():\n    return 42\n'}))
        truth = SuiteTruth(input_sha256=expected,
            source=SuiteAsset(path=str(path), sha256=digest, size_bytes=len(source)),
            tests=asset(pack_files({'tests/test_core.py': b'protected oracle; never imported in these tests'}), f'tests-{index}.tar.gz'),
            wheels=[wheel], python='3.13', pytest='8.3.5', test_paths=['tests/test_core.py'],
            fail_to_pass=['tests/test_core.py::test_repair'], pass_to_pass=['tests/test_core.py::test_preserved'])
        cases.append(RepositorySuiteCase(input=task, truth=truth,
            reference=asset(json.dumps(reference).encode(), f'reference-{index}.json'), fault_outputs=[patch_artifact(
                RepositoryPatch(base_sha256=expected, files={'library/core.py': 'def value():\n    return -1\n'}))],
            source_repository='https://example.test/fixture-' + str(index), source_revision=f'{index:040x}',
            independent_case_id='fake-origin-' + str(index), license='Apache-2.0',
            provenance='Fabricated first-party contract fixture. Not an independent real task.'))
    return cases


def success(payload, truth):
    return {'exit_code': 0, 'statuses': {name: 'PASSED' for name in truth.fail_to_pass + truth.pass_to_pass},
            'archive_sha256': payload['archive_sha256'], 'python': truth.python, 'pytest': truth.pytest}


def test_public_projection_excludes_oracles_and_checks_content(suite_cases):
    case = suite_cases[0]
    value = case.input.model_dump(mode='json')
    root = Path(case.truth.source.path).parent
    projected = public_archive(value, [str(root)])
    assert projected['base_sha256'] == content_digest(value)
    assert hashlib.sha256(base64.b64decode(projected['source_b64'])).hexdigest() == case.input.source_sha256
    assert 'truth' not in projected and 'reference' not in projected
    assert b'protected oracle' not in base64.b64decode(projected['source_b64'])
    with pytest.raises(ConfigurationError):
        public_archive(value, [])
    changed = copy.deepcopy(value)
    changed['source_sha256'] = suite_cases[1].input.source_sha256
    # An available reviewed public archive can be selected by hash, but cannot
    # smuggle an arbitrary path or claim different bytes under that hash.
    assert public_archive(changed, [str(root)])['source_b64']
    Path(case.truth.source.path).write_bytes(b'changed')
    with pytest.raises(ConfigurationError, match='source changed'):
        public_archive(value, [str(root)])


@pytest.mark.parametrize('name', ['../escape', '/absolute', 'a//b', 'a\\b', '.git/config',
                                 '.codex/config.toml', 'AGENTS.md', '.env'])
def test_archives_reject_unsafe_members(name):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz') as archive:
        member = tarfile.TarInfo(name)
        archive.addfile(member)
    with pytest.raises(ConfigurationError):
        archive_files(stream.getvalue())


def test_archive_links_duplicates_conflicts_and_bombs():
    for kind in ('link', 'duplicate', 'conflict', 'expanded'):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w:gz') as archive:
            member = tarfile.TarInfo('file')
            if kind == 'link':
                member.type, member.linkname = tarfile.SYMTYPE, '/etc/passwd'
            if kind == 'expanded':
                member.size = 4_000_001
                archive.addfile(member, io.BytesIO(b'0'*member.size))
            else:
                archive.addfile(member)
                if kind in ('duplicate', 'conflict'):
                    archive.addfile(tarfile.TarInfo('file' if kind == 'duplicate' else 'file/child'))
        with pytest.raises(ConfigurationError):
            archive_files(stream.getvalue())
    with pytest.raises(ConfigurationError):
        archive_files(b'not gzip')


def test_asset_symlinks_and_drift(suite_cases, tmp_path):
    original = suite_cases[0].truth.tests
    link = tmp_path / 'linked'
    link.symlink_to(original.path)
    with pytest.raises(ValueError):
        SuiteAsset(path=str(link), sha256=original.sha256, size_bytes=original.size_bytes)
    Path(original.path).write_bytes(b'changed')
    with pytest.raises(ConfigurationError):
        original.read()
    with pytest.raises(ValueError):
        SuiteAsset(path=str(tmp_path / 'auth.json'), sha256='a'*64, size_bytes=1)
    link.unlink()
    link.symlink_to(Path(suite_cases[0].truth.source.path).parent, target_is_directory=True)
    with pytest.raises(ConfigurationError, match='root'):
        public_archive(suite_cases[0].input.model_dump(mode='json'), [str(link)])


@pytest.mark.parametrize('name', ['tests/test_core.py', 'library/conftest.py', 'pyproject.toml', '../escape.py'])
def test_editable_scope_cannot_include_tests_or_configuration(suite_cases, name):
    data = suite_cases[0].input.model_dump(mode='json')
    with pytest.raises(ValueError):
        SuiteInput.model_validate({**data, 'editable_paths': [name]})


@pytest.mark.asyncio
async def test_protected_grading_uses_observations_not_child_verdict(suite_cases):
    case = suite_cases[0]
    observed = []

    async def probe(payload):
        assert 'expected' not in payload and 'fail_to_pass' not in payload and 'reference' not in payload
        files = archive_files(base64.b64decode(payload['archive']))
        assert b'return 42' in files['library/core.py'] and b'protected oracle' in files['tests/test_core.py']
        observed.append(payload)
        return success(payload, case.truth)

    result = await grade_suite_output(case.input.model_dump(mode='json'), case.truth.model_dump(mode='json'),
        json.loads(case.reference.read()), probe)
    assert result.valid and len(observed) == 1


@pytest.mark.asyncio
async def test_invalid_patch_does_not_execute(suite_cases):
    case = suite_cases[0]

    async def forbidden(_payload):
        pytest.fail('invalid patch executed')

    bad = [None, {}, {'patch_b64': 'invalid'}, patch_artifact(RepositoryPatch(base_sha256='0'*64, files={})),
           patch_artifact(RepositoryPatch(base_sha256=content_digest(case.input), files={'tests/test_core.py': 'forged'})),
           {'patch_b64': base64.b64encode(b'{"base_sha256":"x","base_sha256":"y","files":{}}').decode()}]
    for output in bad:
        assert not (await grade_suite_output(case.input.model_dump(mode='json'), case.truth.model_dump(mode='json'), output, forbidden)).valid


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['FAILED', 'SKIPPED', 'XFAIL', 'ERROR', None])
async def test_missing_or_nonpassing_tests_never_pass(suite_cases, status):
    case = suite_cases[0]

    async def probe(payload):
        reply = success(payload, case.truth)
        name = case.truth.fail_to_pass[0]
        if status is None:
            reply['statuses'].pop(name)
        else:
            reply['statuses'][name] = status
        return reply

    result = await grade_suite_output(case.input.model_dump(mode='json'), case.truth.model_dump(mode='json'), json.loads(case.reference.read()), probe)
    assert not result.valid and result.detail == ('missing_test' if status is None else 'test_failure')


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['forged_verdict', 'wrong_archive', 'nonzero', 'invalid_status'])
async def test_probe_protocol_and_exit_status(suite_cases, kind):
    case = suite_cases[0]

    async def probe(payload):
        reply = success(payload, case.truth)
        if kind == 'forged_verdict':
            reply['valid'] = True
        elif kind == 'wrong_archive':
            reply['archive_sha256'] = '0'*64
        elif kind == 'nonzero':
            reply['exit_code'] = 1
        else:
            reply['statuses'][case.truth.fail_to_pass[0]] = []
        return reply

    call = grade_suite_output(case.input.model_dump(mode='json'), case.truth.model_dump(mode='json'), json.loads(case.reference.read()), probe)
    if kind == 'nonzero':
        assert not (await call).valid
    else:
        with pytest.raises(ConfigurationError, match='protocol'):
            await call


def test_factory_and_reference_are_inert_and_hash_bound(suite_cases, capsys, tmp_path):
    recipe = repository_suite_recipe(suite_cases)
    assert recipe.extension.schema_version.endswith('.v5') and recipe.generator == 'curated_repository:1'
    assert recipe.generator_config['real_repository_workload'] is False
    assert reference_outputs(recipe, [suite_cases[0].input.model_dump(mode='json')]) == [json.loads(suite_cases[0].reference.read())]
    assert len(curated_cases(recipe)) == 3
    compile(recipe.extension.grader.config['argv'][3], '<observer>', 'exec')
    with pytest.raises(ConfigurationError, match='8/28/105'):
        curated_payload(recipe)
    with pytest.raises(ConfigurationError, match='repeated'):
        repository_suite_recipe([suite_cases[0], suite_cases[0], suite_cases[1]])
    with pytest.raises(ConfigurationError, match='three'):
        repository_suite_recipe(suite_cases[:2])
    from aeep_toolkit.cli import main

    path = tmp_path / 'cases.json'
    path.write_text(json.dumps([case.model_dump(mode='json') for case in suite_cases]))
    assert main(['repository-suite-recipe', '--cases', str(path)]) == 0
    assert json.loads(capsys.readouterr().out)['extension']['schema_version'].endswith('.v5')


def test_truth_and_fault_contracts(suite_cases):
    case = suite_cases[0]
    for update in ({'fail_to_pass': case.truth.pass_to_pass}, {'test_paths': ['../escape.py']},
                   {'pass_to_pass': []}, {'fail_to_pass': ['tests/elsewhere.py::test_x']},
                   {'fail_to_pass': ['tests/test_core.py::test_with spaces']}):
        with pytest.raises(ValueError):
            SuiteTruth.model_validate({**case.truth.model_dump(mode='json'), **update})
    with pytest.raises(ValueError, match='faults'):
        RepositorySuiteCase.model_validate({**case.model_dump(mode='json'), 'fault_outputs': [patch_artifact(
            RepositoryPatch(base_sha256=case.truth.input_sha256, files={}))]})
    with pytest.raises(ValueError):
        decode_patch({'patch_b64': base64.b64encode(b'{"files":{},"files":{}}').decode()})


def campaign_cases(development, root):
    """Fabricated origins and simple text assets for lifecycle serialization only."""
    result = list(development)
    for split, count in [('qualification', 8), ('training', 28), ('holdout', 105)]:
        for index in range(count):
            tag = split + str(index)
            data = development[0].model_dump(mode='json')
            archive = pack_files({'library/core.py': ('# first-party serialization fixture ' + tag).encode()})
            digest = hashlib.sha256(archive).hexdigest()
            path = root / (digest + '.tar.gz')
            path.write_bytes(archive)
            data['input'].update(task_id=tag, source_sha256=digest)
            binding = content_digest(data['input'])
            data['truth'].update(input_sha256=binding, source=dict(path=str(path), sha256=digest, size_bytes=len(archive)))
            output = patch_artifact(RepositoryPatch(base_sha256=binding, files={'library/core.py': 'return 42'}))
            reference = root / (tag + '.json')
            reference.write_text(json.dumps(output))
            data.update(reference=dict(path=str(reference), sha256=hashlib.sha256(reference.read_bytes()).hexdigest(), size_bytes=reference.stat().st_size),
                split=split, used_for_development=False, independent_case_id=tag,
                source_revision=hashlib.sha1(tag.encode()).hexdigest(),
                fault_outputs=[patch_artifact(RepositoryPatch(base_sha256=binding, files={'library/core.py': 'return -1'}))])
            result.append(RepositorySuiteCase.model_validate(data))
    return result


@pytest.mark.asyncio
async def test_curated_materialization_uses_one_existing_ledger_operation(suite_cases, tmp_path, monkeypatch):
    from test_v08_executable_recipes import setup

    from aeep.assessment.extensions import materialize

    expanded = campaign_cases(suite_cases, tmp_path.resolve())
    recipe = repository_suite_recipe(expanded, assessment=True)
    assert len(curated_payload(recipe)['cases']) == 141
    router, service, _recipe, request, _env = setup(tmp_path, monkeypatch, recipe=recipe)
    try:
        for digest in request.definition_digests:
            service.repository.review(digest)
        cases = await materialize(service, request.plan_id)
        assert len(cases.cases) == 141 and await materialize(service, request.plan_id) == cases
        ledger = service.repository.operation_ledger(request.plan_id)
        assert len(ledger.operations) == 1 and ledger.operations[0].stage == 'curated_case_materialization'
        assert ledger.operations[0].elapsed_seconds is not None
        assert not router.store.list_receipts()  # Pure reviewed data, no child execution.
        broken = recipe.model_copy(deep=True)
        broken.generator_config['cases'][-1]['used_for_development'] = True
        with pytest.raises(ConfigurationError, match='8/28/105'):
            curated_payload(broken)
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_changed_oracle_and_payload_bounds_stop_execution(suite_cases, monkeypatch):
    case = suite_cases[0]

    async def forbidden(_payload):
        pytest.fail('unverified assets executed')

    value, truth = case.input.model_dump(mode='json'), case.truth.model_dump(mode='json')
    with pytest.raises(ConfigurationError, match='binding'):
        await grade_suite_output({**value, 'task': 'different'}, truth, json.loads(case.reference.read()), forbidden)
    monkeypatch.setattr('aeep.assessment.repository_suites.MAX_PAYLOAD', 10)
    with pytest.raises(ConfigurationError, match='transport'):
        await grade_suite_output(value, truth, json.loads(case.reference.read()), forbidden)
    await asyncio.to_thread(Path(case.truth.tests.path).write_bytes, b'changed')
    with pytest.raises(ConfigurationError):
        await grade_suite_output(value, truth, json.loads(case.reference.read()), forbidden)


def test_bounded_data_and_reference_errors(suite_cases):
    import os

    with pytest.raises(ConfigurationError, match='transport'):
        pack_files({'large.bin': os.urandom(660_000)})
    with pytest.raises(ValueError, match='byte bound'):
        decode_patch({'patch_b64': base64.b64encode(b' '*500001).decode()})
    with pytest.raises(ValueError, match='duplicate'):
        SuiteInput.model_validate({**suite_cases[0].input.model_dump(mode='json'), 'editable_paths': ['x.py', 'x.py']})
    recipe = repository_suite_recipe(suite_cases)
    with pytest.raises(ConfigurationError, match='absent'):
        reference_outputs(recipe, [{'unknown': True}])
    changed = recipe.model_copy(deep=True)
    asset = changed.generator_config['cases'][0]['reference']
    path = Path(asset['path'])
    path.write_text(json.dumps(patch_artifact(RepositoryPatch(base_sha256='0'*64, files={}))))
    asset.update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), size_bytes=path.stat().st_size)
    with pytest.raises(ConfigurationError, match='binding'):
        reference_outputs(changed, [suite_cases[0].input.model_dump(mode='json')])
    empty = recipe.model_copy(deep=True)
    empty.generator_config['cases'] = []
    with pytest.raises(ConfigurationError, match='count'):
        curated_cases(empty)


@pytest.mark.asyncio
async def test_protected_assets_cannot_expand_source_scope(suite_cases, tmp_path):
    case = suite_cases[0]

    async def forbidden(_payload):
        pytest.fail('conflicting tests or missing source executed')

    value, truth = case.input.model_dump(mode='json'), case.truth.model_dump(mode='json')
    data = pack_files({'library/core.py': b'forged overlay outside tests'})
    path = tmp_path.resolve() / 'wrong-overlay.tar.gz'
    path.write_bytes(data)
    truth['tests'] = dict(path=str(path), sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))
    with pytest.raises(ConfigurationError, match='overlay'):
        await grade_suite_output(value, truth, json.loads(case.reference.read()), forbidden)
    value['editable_paths'].append('library/absent.py')
    truth['input_sha256'] = content_digest(value)
    output = patch_artifact(RepositoryPatch(base_sha256=content_digest(value), files={}))
    with pytest.raises(ConfigurationError, match='absent'):
        await grade_suite_output(value, truth, output, forbidden)


def test_pinned_upstream_bodies_are_unchanged_without_executing_them():
    import ast

    root = Path(__file__).resolve().parents[1] / 'integrations/assessment-runtime'
    source = (root / 'swe_rebench_pytest_parser.py').read_text()
    expected = json.loads((root / 'swe-rebench-provenance.json').read_text())
    bodies = {node.name: hashlib.sha256(ast.get_source_segment(source, node).encode()).hexdigest()
              for node in ast.parse(source).body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    assert bodies == expected['selected_body_sha256']
    assert (root / expected['license_file']).read_text().startswith('MIT License')


@pytest.mark.asyncio
async def test_observer_runs_reviewed_src_layout_with_first_party_shims():
    """Real process regression, using no third-party parser, test runner or source."""
    import subprocess
    import sys
    import zipfile

    wheel = io.BytesIO()
    with zipfile.ZipFile(wheel, 'w') as archive:
        archive.writestr('fixture_target.py', 'value = -1\n')
        archive.writestr('pytest.py', '__version__="8.3.5"\ndef main(argv):\n'
            '    import fixture_target\n    assert fixture_target.value == 42\n'
            '    print("FIRSTPARTY_SOURCE_OK")\n    return 0\n')
    data = wheel.getvalue()
    source = pack_files({'src/fixture_target/__init__.py': b'value = 42\n', 'tests/test_fixture.py': b'# fixture\n'})
    payload = {'archive': base64.b64encode(source).decode(), 'archive_sha256': hashlib.sha256(source).hexdigest(),
        'python': '.'.join(map(str, sys.version_info[:2])), 'pytest': '8.3.5', 'test_paths': ['tests/test_fixture.py'],
        'wheels': [{'filename': 'pytest-fixture-py3-none-any.whl', 'sha256': hashlib.sha256(data).hexdigest(),
                    'data': base64.b64encode(data).decode()}]}
    # Replace the untrusted upstream parser with an explicitly first-party shim.
    observer_source = await asyncio.to_thread((ROOT / 'integrations/assessment-runtime/repository_suite_program.py').read_text)
    program = ('def parse_log_pytest(text, unused):\n'
        '    return {"tests/test_fixture.py::test_source": "PASSED"} if "FIRSTPARTY_SOURCE_OK" in text else {}\n'
        + observer_source)
    result = await asyncio.to_thread(subprocess.run, [sys.executable, '-B', '-c', program],
        input=json.dumps(payload).encode(), capture_output=True, timeout=10, check=True)
    observation = json.loads(result.stdout)
    assert observation['exit_code'] == 0 and observation['statuses'] == {'tests/test_fixture.py::test_source': 'PASSED'}


@pytest.mark.asyncio
async def test_existing_callback_and_grader_validation(suite_cases, monkeypatch):
    from aeep.assessment.extensions import callbacks, grader_name, validate_grader
    from aeep.validators import ValidationContext

    recipe = repository_suite_recipe(suite_cases)
    case = suite_cases[0]
    plan = SimpleNamespace(suite=SimpleNamespace(cases=[], warmup_cases=[]))

    async def invoke(_service, _plan, _spec, payload, **kwargs):
        # First-party observer fixture: metadata verification, not external test execution.
        files = archive_files(base64.b64decode(payload['archive']))
        correct = b'return 42' in files['library/core.py']
        reply = success(payload, case.truth)
        if not correct:
            reply['exit_code'] = 1
            reply['statuses'][case.truth.fail_to_pass[0]] = 'FAILED'
        return reply, 0.0

    monkeypatch.setattr('aeep.assessment.extensions.invoke', invoke)
    literals, faults = await validate_grader(None, plan, recipe, [])
    assert len(literals) == 3 and faults >= 3
    value, truth = case.input.model_dump(mode='json'), case.truth.model_dump(mode='json')
    plan.suite.cases = [SimpleNamespace(action=SimpleNamespace(input=value), validators=[SimpleNamespace(config={'expected': truth})])]
    result = await callbacks(None, plan, recipe)[grader_name(value, truth)](ValidationContext(input=value, output=json.loads(case.reference.read())))
    assert result.valid


def test_explicit_plugins_need_v2_in_models_and_exported_schema(suite_cases):
    from jsonschema import Draft202012Validator, ValidationError

    legacy = suite_cases[0].model_dump(mode='json')
    current = copy.deepcopy(legacy)
    current['schema_version'] = 'assessment.repository-suite-case.v2'
    current['truth']['pytest_plugins'] = ['pytest_mock']
    schema = RepositorySuiteCase.model_json_schema()
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    assert not list(validator.iter_errors(legacy)) and not list(validator.iter_errors(current))
    case = RepositorySuiteCase.model_validate(current)
    assert isinstance(case.truth, SuiteTruthV2) and case.model_dump(mode='json') == current
    assert suite_cases[0].model_dump(mode='json') == legacy and 'pytest_plugins' not in legacy['truth']
    for invalid in ({**legacy, 'truth': current['truth']}, {**current, 'truth': legacy['truth']}):
        with pytest.raises(ValueError, match='require repository suite case v2'):
            RepositorySuiteCase.model_validate(invalid)
        with pytest.raises(ValidationError):
            validator.validate(invalid)
    without_version = {key: value for key, value in current.items() if key != 'schema_version'}
    with pytest.raises(ValidationError):
        validator.validate(without_version)
    with pytest.raises(ValueError):
        SuiteTruth.model_validate(current['truth'])


@pytest.mark.parametrize('plugins', [[], ['pytest_mock'] * 2, ['x'] * 9, ['-p'], ['x/y'], ['x:y'],
                                    ['x;exit'], ['x\ny'], ['x' * 129], ['café'], ['x..y']])
def test_plugin_names_cannot_supply_paths_flags_or_duplicate_imports(suite_cases, plugins):
    with pytest.raises(ValueError):
        SuiteTruthV2.model_validate({**suite_cases[0].truth.model_dump(mode='json'), 'pytest_plugins': plugins})


@pytest.mark.asyncio
async def test_plugins_are_frozen_truth_and_not_patch_or_public_input(suite_cases):
    case = suite_cases[0]
    legacy = repository_suite_recipe(suite_cases)
    truth = {**case.truth.model_dump(mode='json'), 'pytest_plugins': ['pytest_mock']}
    data = {**case.model_dump(mode='json'), 'schema_version': 'assessment.repository-suite-case.v2', 'truth': truth}
    current = RepositorySuiteCase.model_validate(data)
    recipe = repository_suite_recipe([current, *suite_cases[1:]])
    assert recipe.recipe_id != legacy.recipe_id
    assert content_digest(recipe.extension.grader) != content_digest(legacy.extension.grader)
    assert reference_outputs(recipe, [case.input.model_dump(mode='json')]) == [json.loads(case.reference.read())]
    observed = []

    async def probe(payload):
        assert payload['pytest_plugins'] == ['pytest_mock'] and payload['source_modules'] == ['library']
        observed.append(payload)
        return success(payload, case.truth)

    assert (await grade_suite_output(case.input.model_dump(mode='json'), truth, json.loads(case.reference.read()), probe)).valid
    assert len(observed) == 1
    public = public_archive(case.input.model_dump(mode='json'), [str(Path(case.truth.source.path).parent)])
    assert 'pytest_plugins' not in public and 'source_modules' not in public

    async def forbidden(_payload):
        pytest.fail('patch-supplied plugin configuration executed')

    forged = {**json.loads(case.reference.read()), 'pytest_plugins': ['unreviewed']}
    assert not (await grade_suite_output(case.input.model_dump(mode='json'), truth, forged, forbidden)).valid


@pytest.mark.asyncio
@pytest.mark.parametrize('preload_source', [False, True])
async def test_explicit_plugin_real_process_keeps_trusted_imports_and_source_binding(preload_source):
    """Only first-party parser/pytest/plugin shims execute; this is not conformance."""
    import subprocess
    import sys
    import zipfile

    wheel = io.BytesIO()
    with zipfile.ZipFile(wheel, 'w') as archive:
        archive.writestr('fixture_target.py', 'value = -1\n')
        archive.writestr('fixture_plugin.py',
            ('import fixture_target\n' if preload_source else '') + 'marker = "trusted first-party fixture"\n')
        archive.writestr('pytest.py', '__version__="8.3.5"\ndef main(argv, plugins):\n'
            '    import os, fixture_target\n'
            '    assert os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"\n'
            '    assert len(plugins) == 1 and plugins[0].marker == "trusted first-party fixture"\n'
            '    assert fixture_target.value == 42\n'
            '    print("FIRSTPARTY_PLUGIN_AND_SOURCE_OK")\n    return 0\n')
    data = wheel.getvalue()
    source = pack_files({'src/fixture_target/__init__.py': b'value = 42\n',
        'fixture_plugin.py': b'raise RuntimeError("candidate plugin must not load")\n',
        'pytest.py': b'raise RuntimeError("candidate pytest must not load")\n',
        'tests/test_fixture.py': b'# first-party fixture\n'})
    payload = {'archive': base64.b64encode(source).decode(), 'archive_sha256': hashlib.sha256(source).hexdigest(),
        'python': '.'.join(map(str, sys.version_info[:2])), 'pytest': '8.3.5', 'test_paths': ['tests/test_fixture.py'],
        'pytest_plugins': ['fixture_plugin'], 'source_modules': ['fixture_target'],
        'wheels': [{'filename': 'firstparty-fixture-py3-none-any.whl', 'sha256': hashlib.sha256(data).hexdigest(),
                    'data': base64.b64encode(data).decode()}]}
    observer = (ROOT / 'integrations/assessment-runtime/repository_suite_plugins_program.py').read_text()
    program = ('def parse_log_pytest(text, unused):\n'
        '    return {"tests/test_fixture.py::test_source": "PASSED"} if "FIRSTPARTY_PLUGIN_AND_SOURCE_OK" in text else {}\n'
        + observer)
    result = await asyncio.to_thread(subprocess.run, [sys.executable, '-B', '-c', program],
        input=json.dumps(payload).encode(), capture_output=True, timeout=10, check=True)
    observation = json.loads(result.stdout)
    assert (observation['exit_code'] == 0) is not preload_source
    assert bool(observation['statuses']) is not preload_source
