from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import re
import subprocess
import sys
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from aeep.assessment.extensions import structural_features
from aeep.assessment.workbook import workbook_recipe

pytestmark = pytest.mark.assessment_contract
ASSETS = Path(__file__).resolve().parents[1] / 'integrations' / 'assessment-runtime'


def test_workbook_semantics_literal_truth_faults_and_structural_bounds():
    recipe = workbook_recipe()
    assert recipe.extension is not None and recipe.extension.truth_schema is not None
    fixtures = json.loads((ASSETS / 'workbook-grader-fixtures.json').read_text())
    faults = json.loads((ASSETS / 'workbook-faults.json').read_text())
    examples = [*fixtures, *[{**fixtures[1], 'output': output} for output in faults.values()],
                {**fixtures[0], 'output': {'workbook_b64': 'invalid'}}]
    process = subprocess.run([sys.executable, str(ASSETS / 'workbook_grader.py')],
        input=json.dumps({'examples': examples}), text=True, capture_output=True, check=True, timeout=10)
    assert json.loads(process.stdout)['valid'] == [True] * len(fixtures) + [False] * 7
    value = fixtures[1]['input']
    features = structural_features(recipe, value)
    assert features and features['sheets'] == 1 and features['formulas'] == 0
    assert structural_features(recipe, {**value, 'row_bound': 1}) == features  # Declared dimensions aren't evidence.
    assert structural_features(recipe, {**value, 'workbook_b64': 'invalid'}) is None
    assert structural_features(recipe, {**value, 'workbook_b64': 'a'*200001}) is None
    def edited_sheet(text):
        source = zipfile.ZipFile(io.BytesIO(base64.b64decode(value['workbook_b64'])))
        target = io.BytesIO()
        with source, zipfile.ZipFile(target, 'w') as archive:
            for item in source.infolist():
                raw = source.read(item)
                if item.filename == 'xl/worksheets/sheet1.xml':
                    raw = text(raw.decode()).encode()
                archive.writestr(item, raw)
        return {**value, 'workbook_b64': base64.b64encode(target.getvalue()).decode()}
    for number, flag in [('0.5', 'fractional_numbers'), ('-1', 'negative_numbers'), ('1001', 'outside_numeric_bound')]:
        changed = structural_features(recipe, edited_sheet(lambda xml, number=number: re.sub(r'<c r="C3"[^>]*>.*?</c>', '<c r="C3"><v>' + number + '</v></c>', xml)))
        assert changed and changed[flag] is True
    assert structural_features(recipe, edited_sheet(lambda xml: xml.replace('</sheetData>', '<row r="30"><c r="A30"><f>SUM(A1:A2)</f></c></row></sheetData>'))) is None
    assert 'truth_schema' not in recipe.extension.model_copy(update={'schema_version': 'assessment.recipe-extension.v1', 'truth_schema': None}).model_dump()


def test_artifact_validation_batches_obey_existing_input_bounds():
    from aeep.assessment.extensions import bounded_batches
    from aeep.errors import ConfigurationError

    values = [{'value': 'x'*400000}, {'value': 'y'*400000}]
    assert bounded_batches(values) == [[values[0]], [values[1]]]
    assert bounded_batches([]) == []
    with pytest.raises(ConfigurationError, match='input bound'):
        bounded_batches([{'value': 'x'*750000}])


async def test_reviewed_code_is_literal_and_cannot_interpolate_task_fields():
    from aeep.errors import ConfigurationError
    from aeep.executors.base import ExecutionContext
    from aeep.executors.command import CommandExecutor
    from aeep.models import ActionRequest, ExecutorSpec

    spec = ExecutorSpec(id='literal', capability='fixture', description='literal program fixture', kind='command', config={
        'argv': [sys.executable, '-c', "import json; print(json.dumps({'text':'{input.secret}'}))"],
        'argv_literal': True, 'output': {'type': 'json'}})
    context = ExecutionContext(request=ActionRequest(capability='fixture', input={'secret': 'changed'}), spec=spec, estimate=spec.estimate, attempt=1)
    assert (await CommandExecutor().execute(context)).output == {'text': '{input.secret}'}
    spec.config['argv_literal'] = 'true'
    with pytest.raises(ConfigurationError, match='boolean'):
        await CommandExecutor().execute(context)


@pytest.mark.real_container
@pytest.mark.assessment_boundary
@pytest.mark.skipif(not os.environ.get('AEEP_WORKBOOK_IMAGE'), reason='requires a pinned offline workbook recipe runtime')
async def test_contained_workbook_materialization_grader_and_honest_rejection(tmp_path, monkeypatch):
    from test_v08_executable_recipes import setup

    from aeep.assessment.extensions import materialize

    # Deliberately wrong native fixtures prove the shared campaign reports a loss;
    # this is not a plugin or live-Codex comparison.
    router, service, recipe, request, environment = setup(tmp_path, monkeypatch, recipe=workbook_recipe(), real=True)
    try:
        for name in ('candidate', 'baseline'):
            spec = router.registry.get(name).model_copy(update={'capability': recipe.capability})
            spec.config = {**spec.config, 'argv': ['python3', '-c', "print('{}')"]}
            router.registry.replace(spec)
        for digest in request.definition_digests:
            service.repository.review(digest)
        cases = await materialize(service, request.plan_id)
        assert len(cases.cases) == 141
        assert all(len(case.validators) == 1 for case in cases.cases)  # Semantic callback, not byte equality.
        plan = service.propose(subject_id=request.subject_digest, family=recipe.recipe_id, candidate_id='candidate', baseline_id='baseline',
            authorization_id=request.authorization_id, environment=environment, seed=request.seed, case_set_id=request.plan_id)
        for digest in plan.definition_digests:
            service.repository.review(digest)
        report = await service.run(service.enqueue(plan.plan_id))
        assert report.grader_validation_digest, report.explanations
        assert not report.qualification_passed
        assert report.outcome == 'unsuitable'
        ledger = service.repository.operation_ledger(plan.plan_id, source_plan_ids=[request.plan_id])
        assert {'recipe_generation', 'grader_reference', 'grader_probe', 'trial'} <= {item.stage for item in ledger.operations}
        assert all(item.elapsed_seconds is not None for item in ledger.operations)
    finally:
        await router.close()


@pytest.mark.real_container
@pytest.mark.assessment_boundary
@pytest.mark.skipif(not os.environ.get('AEEP_WORKBOOK_IMAGE'), reason='requires a pinned offline image with openpyxl 3.1.5')
def test_workbook_real_generator_reference_and_independent_grader():
    image = os.environ['AEEP_WORKBOOK_IMAGE']
    assert image.startswith('sha256:') and len(image) == 71
    program = (ASSETS / 'workbook_program.py').read_text().split("if __name__ == '__main__':")[0]
    grader = (ASSETS / 'workbook_grader.py').read_text().split("if __name__ == '__main__':")[0]
    check = '''
payload={'seed':21,'stages':[{'split':'screening','count':8},{'split':'training','count':28},{'split':'holdout','count':105}]}
cases=generate(payload)['cases']
assert generate(payload)['cases']==cases
assert all(grade({'input':case['input'],'output':reference(case['input']),'expected':case['output']}) for case in cases)
print(json.dumps({'count':len(cases),'holdout_variations':[case['variation'] for case in cases[36:]]}))
'''
    result = subprocess.run([os.environ['AEEP_CONTAINER_RUNTIME'], '--host', 'unix://' + os.environ['AEEP_CONTAINER_SOCKET'],
        'run', '--rm', '--network=none', '--read-only', '--user', '65534:65534', '--cap-drop=ALL',
        '--security-opt=no-new-privileges', '--memory=256m', '--pids-limit=64', '--cpus=1',
        '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=32m', '--entrypoint', 'python3', image,
        '-c', program + '\n' + grader + '\n' + check], capture_output=True, text=True, timeout=60, check=True)
    observed = json.loads(result.stdout)
    assert observed['count'] == 141
    assert set(Counter(observed['holdout_variations']).values()) == {15}


def test_reviewed_workbook_failure_codes_preserve_decisions():
    from aeep.assessment.extensions import grader_results
    from aeep.errors import ConfigurationError

    recipe = workbook_recipe()
    extension = recipe.extension
    assert extension is not None and extension.failure_codes
    fixtures = json.loads((ASSETS / 'workbook-grader-fixtures.json').read_text())
    faults = json.loads((ASSETS / 'workbook-faults.json').read_text())
    examples = [*fixtures, *[{**fixtures[1], 'output': output} for output in faults.values()],
                {**fixtures[0], 'output': {'workbook_b64': 'invalid'}}]
    result = subprocess.run([sys.executable, str(ASSETS / 'workbook_grader.py'), 'diagnose'],
        input=json.dumps({'examples': examples}), text=True, capture_output=True, check=True, timeout=10)
    parsed = grader_results(json.loads(result.stdout), extension, len(examples))
    assert [item.valid for item in parsed] == [True] * len(fixtures) + [False] * 7
    assert all(not item.detail if item.valid else item.detail in extension.failure_codes for item in parsed)
    assert parsed[-1].detail == 'invalid_workbook'
    for reply in ({'valid': [False]}, {'valid': [False], 'failure_codes': ['private cell value']},
                  {'valid': [True], 'failure_codes': ['cell_value']},
                  {'valid': [False], 'failure_codes': [None]},
                  {'valid': [False], 'failure_codes': []},
                  {'valid': [False], 'failure_codes': {}},
                  {'valid': [False], 'failure_codes': ['cell_value'], 'raw': 'private'},
                  {'valid': [1], 'failure_codes': [None]}):
        with pytest.raises(ConfigurationError, match='grader returned'):
            grader_results(reply, extension, 1)
    from aeep.assessment.models import ExecutableRecipeExtension
    raw = extension.model_dump()
    for change in ({'schema_version': 'assessment.recipe-extension.v2'},
                   {'failure_codes': None}, {'failure_codes': ['cell_value', 'cell_value']},
                   {'failure_codes': ['private value']}, {'truth_schema': None}):
        with pytest.raises(ValueError):
            ExecutableRecipeExtension.model_validate({**raw, **change})
    for fixture in [*raw['independent_fixtures'], *raw['transformed_fixtures']]:
        fixture.pop('grader_output', None)
    legacy = ExecutableRecipeExtension.model_validate({**raw,
        'schema_version': 'assessment.recipe-extension.v2', 'failure_codes': None})
    assert 'failure_codes' not in legacy.model_dump()
    assert grader_results({'valid': [False, True]}, legacy, 2)[0].detail == ''
    with pytest.raises(ConfigurationError):
        grader_results({'valid': [False], 'failure_codes': ['cell_value']}, legacy, 1)


async def test_independent_literal_artifact_blocks_an_encoding_biased_grader(monkeypatch):
    from types import SimpleNamespace

    from aeep.assessment import extensions
    from aeep.errors import ConfigurationError

    recipe = workbook_recipe()
    assert recipe.extension is not None
    fixtures = [*recipe.extension.independent_fixtures, *recipe.extension.transformed_fixtures]
    assert fixtures[-1].input == fixtures[1].input and fixtures[-1].output == fixtures[1].output
    assert fixtures[-1].grader_output != fixtures[1].grader_output
    assert all(fixture.grader_output is not None for fixture in fixtures)
    plan = SimpleNamespace(suite=SimpleNamespace(cases=[], warmup_cases=[]))

    async def invoke(_service, _plan, spec, payload, **_kwargs):
        if spec.id == recipe.extension.reference.id:
            return {'outputs': [next(f.grader_output for f in fixtures if f.input == value)
                                for value in payload['inputs']]}, 0
        result = await asyncio.to_thread(subprocess.run, [sys.executable, '-c', spec.config['argv'][2], 'diagnose'],
            input=json.dumps(payload), capture_output=True, text=True, check=True, timeout=10)
        return json.loads(result.stdout), 0

    monkeypatch.setattr(extensions, 'invoke', invoke)
    _, faults = await extensions.validate_grader(None, plan, recipe, [])
    assert faults > 0
    source = recipe.extension.grader.config['argv'][2]
    start = source.index("                elif cell.get('t') == 'str':")
    end = source.index('                elif value is not None:', start)
    recipe.extension.grader.config['argv'][2] = source[:start] + source[end:]
    with pytest.raises(ConfigurationError, match='independent correctness/fault validation'):
        await extensions.validate_grader(None, plan, recipe, [])


def test_unknown_cell_type_cannot_masquerade_as_number():
    fixture = json.loads((ASSETS / 'workbook-grader-fixtures.json').read_text())[1]
    target = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(fixture['output']['workbook_b64']))) as source, zipfile.ZipFile(target, 'w') as archive:
        for item in source.infolist():
            data = source.read(item)
            if item.filename == 'xl/worksheets/sheet1.xml':
                root = ET.fromstring(data)
                cell = next(c for c in root.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c') if c.get('r') == 'C2')
                cell.set('t', 'unreviewed')
                data = ET.tostring(root)
            archive.writestr(item, data)
    example = {**fixture, 'output': {'workbook_b64': base64.b64encode(target.getvalue()).decode()}}
    result = subprocess.run([sys.executable, str(ASSETS / 'workbook_grader.py'), 'diagnose'],
        input=json.dumps({'examples': [fixture, example]}), capture_output=True, text=True, check=True, timeout=10)
    assert json.loads(result.stdout) == {'valid': [True, False], 'failure_codes': [None, 'invalid_workbook']}
