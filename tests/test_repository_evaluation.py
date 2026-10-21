"""Fixed first-party engineering examples, never live comparative evidence."""
import asyncio
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from aeep.assessment.extensions import callbacks, grader_name, validate_grader
from aeep.assessment.models import content_digest
from aeep.assessment.repository_tasks import (
    REPOSITORY_PROBE,
    RepositoryCase,
    RepositoryInput,
    grade_repository_output,
    repository_recipe,
)
from aeep.errors import ConfigurationError
from aeep.validators import ValidationContext

pytestmark = pytest.mark.assessment_contract
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cases():
    return [RepositoryCase.model_validate(case) for case in json.loads(
        (ROOT / 'examples/repository_evaluation/development-cases.json').read_text())]


async def trusted_fixture_probe(payload):
    # Only fixed reviewed first-party patches are run here. Production uses
    # extensions.invoke and fresh offline containers, never this test helper.
    result = await asyncio.to_thread(subprocess.run, [sys.executable, '-I', '-c', REPOSITORY_PROBE],
        input=json.dumps(payload).encode(), capture_output=True, timeout=10, check=True)
    return json.loads(result.stdout)


@pytest.mark.asyncio
async def test_contract_repairs_and_no_change_control(cases):
    baseline_valid = []
    for case in cases:
        value, truth = case.input.model_dump(mode='json'), case.truth.model_dump(mode='json')
        assert (await grade_repository_output(value, truth,
            case.reference_patch.model_dump(mode='json'), trusted_fixture_probe)).valid
        for fault in case.fault_patches:
            assert not (await grade_repository_output(value, truth,
                fault.model_dump(mode='json'), trusted_fixture_probe)).valid
        baseline_valid.append((await grade_repository_output(value, truth,
            {'base_sha256': content_digest(value), 'files': {}}, trusted_fixture_probe)).valid)
    assert baseline_valid == [False, False, True]


@pytest.mark.asyncio
async def test_patch_boundaries_prevent_execution(cases):
    case = cases[0]
    value, truth = case.input.model_dump(mode='json'), case.truth.model_dump(mode='json')

    async def forbidden(_payload):
        pytest.fail('invalid patch reached an executor')

    for output in [None, {}, {'base_sha256': '0' * 64, 'files': {}},
        {'base_sha256': content_digest(value), 'files': {'../escape.py': 'raise SystemExit'}},
        {'base_sha256': content_digest(value), 'files': {'README.txt': 'changed'}},
        {'base_sha256': content_digest(value), 'files': {'launch.py': '\x00'}},
        {'base_sha256': content_digest(value), 'files': {}, 'valid': True}]:
        assert not (await grade_repository_output(value, truth, output, forbidden)).valid


@pytest.mark.parametrize('files', [{'/abs.py': ''}, {'a/../b.py': ''}, {'a//b.py': ''},
    {'a\\b.py': ''}, {'.git/config': ''}, {'a.py': '', 'a.py/child': ''}, {'a.py': 'x' * 500001},
    {'a.py': 'x' * 100001}])
def test_snapshot_bounds(files):
    with pytest.raises(ValueError):
        RepositoryInput(task_id='x', task='x', family='x', files=files, editable_paths=list(files))


@pytest.mark.asyncio
async def test_answers_stay_outside_probe_and_binding_is_checked(cases):
    case = cases[0]
    value, truth = case.input.model_dump(mode='json'), case.truth.model_dump(mode='json')
    received = []

    async def observe(payload):
        assert set(payload) == {'files', 'probe'} and 'expected' not in payload['probe']
        received.append(payload)
        return {'status': 'ok', 'result': case.truth.checks[len(received) - 1].expected}

    assert (await grade_repository_output(value, truth, case.reference_patch.model_dump(mode='json'), observe)).valid
    assert len(received) == len(case.truth.checks)
    with pytest.raises(ConfigurationError, match='binding changed'):
        await grade_repository_output({**value, 'task': 'changed'}, truth, {}, observe)


@pytest.mark.asyncio
async def test_protocol_errors_block_and_json_types_remain_distinct(cases):
    case = cases[0]
    value, truth = case.input.model_dump(mode='json'), case.truth.model_dump(mode='json')

    async def invalid(_payload):
        return {'valid': True}

    with pytest.raises(ConfigurationError, match='protocol failed'):
        await grade_repository_output(value, truth, case.reference_patch.model_dump(mode='json'), invalid)

    async def number(_payload):
        return {'status': 'ok', 'result': 1}

    truth['checks'] = [{'name': 'typed', 'probe': case.truth.checks[0].probe, 'expected': True}]
    assert not (await grade_repository_output(value, truth, case.reference_patch.model_dump(mode='json'), number)).valid


def test_development_export_cannot_generate_holdouts(cases):
    recipe = repository_recipe(cases)
    changed = cases[0].model_copy(update={'provenance': cases[0].provenance + ' Updated metadata.'})
    assert repository_recipe([changed, *cases[1:]]).recipe_id != recipe.recipe_id
    assert recipe.extension.schema_version.endswith('.v4')
    assert 'expected' not in recipe.extension.grader.config['argv'][3]
    with pytest.raises(ValueError, match='8/28/105'):
        repository_recipe(cases, assessment=True)
    process = subprocess.run([sys.executable, *recipe.extension.generator.config['argv'][1:]],
        input=b'{}', capture_output=True, timeout=10)
    assert process.returncode != 0 and b'not campaign holdouts' in process.stderr


def test_assessment_export_formats_frozen_cases_and_rejects_relabelled_origins(cases):
    # Fabricated pins/cases exercise serialization only; they are never retained
    # as benchmark evidence, passed to a model, or called independent real tasks.
    expanded = list(cases)
    for split, count in [('qualification', 8), ('training', 28), ('holdout', 105)]:
        for index in range(count):
            data = cases[index % 3].model_dump(mode='json')
            tag = split + '-' + str(index)
            data['input']['task_id'] = tag
            data['input']['files']['case.txt'] = tag
            digest = content_digest(data['input'])
            data['truth']['input_sha256'] = data['reference_patch']['base_sha256'] = digest
            for fault in data['fault_patches']:
                fault['base_sha256'] = digest
            data.update(split=split, independent_case_id=tag, source_path='synthetic/' + tag,
                used_for_development=False,
                provenance='Software fixture only; fabricated source pins for contract testing.')
            expanded.append(RepositoryCase.model_validate(data))
    recipe = repository_recipe(expanded, assessment=True)
    request = dict(seed=29, variations=recipe.variations,
        stages=[{'split': s, 'count': n} for s, n in [('qualification', 8), ('training', 28), ('holdout', 105)]])
    result = subprocess.run([sys.executable, *recipe.extension.generator.config['argv'][1:]],
        input=json.dumps(request).encode(), capture_output=True, timeout=10, check=True)
    generated = json.loads(result.stdout)['cases']
    assert len(generated) == 141 and generated[-1]['input']['task_id'] == 'holdout-104'
    expanded[-1] = expanded[-1].model_copy(update={'independent_case_id': expanded[0].independent_case_id})
    with pytest.raises(ValueError, match='relabelled or repeated'):
        repository_recipe(expanded, assessment=True)


@pytest.mark.asyncio
async def test_existing_callback_and_independent_validation(cases, monkeypatch):
    recipe = repository_recipe(cases)
    case = cases[0]
    value, truth = case.input.model_dump(mode='json'), case.truth.model_dump(mode='json')
    plan = SimpleNamespace(suite=SimpleNamespace(cases=[], warmup_cases=[]))

    async def invoke(_service, _plan, spec, payload, **kwargs):
        if spec == recipe.extension.reference:
            outputs = [next(item.reference_patch.model_dump(mode='json') for item in cases
                            if item.input.model_dump(mode='json') == value) for value in payload['inputs']]
            return {'outputs': outputs}, 0.0
        return await trusted_fixture_probe(payload), 0.0

    monkeypatch.setattr('aeep.assessment.extensions.invoke', invoke)
    literals, faults = await validate_grader(None, plan, recipe, [])
    assert len(literals) == 3 and faults >= 3
    plan.suite.cases = [SimpleNamespace(action=SimpleNamespace(input=value),
        validators=[SimpleNamespace(config={'expected': truth})])]
    result = await callbacks(None, plan, recipe)[grader_name(value, truth)](
        ValidationContext(input=value, output=case.reference_patch.model_dump(mode='json')))
    assert result.valid


def test_reproducible_source_pins_and_inert_cli(cases, capsys):
    from aeep_toolkit.cli import main

    result = subprocess.run([sys.executable, 'scripts/prepare_repository_development_cases.py'],
        cwd=ROOT, capture_output=True, check=True, timeout=10)
    assert json.loads(result.stdout) == [case.model_dump(mode='json') for case in cases]
    assert main(['repository-recipe', '--cases', str(ROOT / 'examples/repository_evaluation/development-cases.json')]) == 0
    assert json.loads(capsys.readouterr().out)['extension']['schema_version'].endswith('.v4')


@pytest.mark.asyncio
async def test_repository_budget_includes_every_fresh_behavior_probe(cases, tmp_path, monkeypatch):
    from test_v08_assessment import setup_assessment

    router, service, plan, _ = setup_assessment(tmp_path)
    try:
        recipe = repository_recipe(cases)
        read = service.repository.get
        monkeypatch.setattr(service.repository, 'get', lambda kind, identity:
            recipe.model_dump(mode='json') if kind == 'recipe' else read(kind, identity))
        allowance = service.budget_preview(plan.plan_id)['campaign_allowance']
        grading = next(item for item in allowance['stages'] if item['stage'] == 'recipe_grading')
        assert grading['calls_upper'] == 282 * 32
        assert grading['elapsed_reservation_upper_seconds'] == 282 * 32 * 35
        assert allowance['fits_remaining'] is False
    finally:
        await router.close()
