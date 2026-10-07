"""Reviewed built-in workbook check in the ordinary task-service path."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import subprocess
import sys
import zipfile
from datetime import timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.workbook import workbook_recipe
from aeep.assessment.workbook_native import implementation_digest, validate
from aeep.economic.prepared import executor_fingerprint
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from aeep.mcp.server import AEEPToolService
from aeep.models import Manifest, TaskScope, ValidationKind, ValidationSpec, utc_now
from aeep.router import Router
from aeep.tasks import activate, change_state
from aeep.validators import ValidationContext, run_validators

ASSETS = Path(__file__).resolve().parents[1] / 'integrations/assessment-runtime'
FIXTURES = json.loads((ASSETS / 'workbook-grader-fixtures.json').read_text())
N = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
pytestmark = pytest.mark.assessment_lifecycle


def _mutate_workbook(encoded, member_name, edit):
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(encoded))) as source, zipfile.ZipFile(output, 'w') as target:
        for member in source.infolist():
            raw = source.read(member)
            if member.filename == member_name:
                root = ET.fromstring(raw)
                edit(root)
                raw = ET.tostring(root, encoding='utf-8', xml_declaration=True)
            target.writestr(member, raw)
    return base64.b64encode(output.getvalue()).decode('ascii')


@pytest.mark.parametrize('where,member,edit', [
    ('input', 'xl/worksheets/sheet1.xml', lambda root: ET.SubElement(next(root.iter(N + 'row')), N + 'c', r='F1')),
    ('input', 'xl/workbook.xml', lambda root: root.find(N + 'workbookPr').set('date1904', '1')),
    ('input', 'xl/worksheets/sheet1.xml', lambda root: ET.SubElement(next(node for node in root.iter(N + 'c') if node.get('r') == 'C2'), N + 'f').__setattr__('text', '1+1')),
    ('input', 'xl/_rels/workbook.xml.rels', lambda root: ET.SubElement(root, 'Relationship', Id='renamed', Type='http://schemas.microsoft.com/office/2006/relationships/vbaProject', Target='secret.dat')),
    ('output', 'xl/worksheets/sheet1.xml', lambda root: ET.SubElement(next(node for node in root.iter(N + 'c') if node.get('r') == 'A2'), N + 'f').__setattr__('text', '1+1')),
    ('output', 'xl/worksheets/sheet2.xml', lambda root: ET.SubElement(next(root.iter(N + 'row')), N + 'c', r='C1', t='inlineStr')),
])
def test_unreviewed_input_and_output_mutations_reject(where, member, edit):
    fixture = FIXTURES[0]
    value = dict(fixture[where])
    value['workbook_b64'] = _mutate_workbook(value['workbook_b64'], member, edit)
    context = ValidationContext(value, fixture['output']) if where == 'input' else ValidationContext(fixture['input'], value)
    assert validate(context).valid is False


@pytest.mark.parametrize('faulty', [False, True])
@pytest.mark.skipif(sys.platform == "win32", reason="native task integration requires POSIX; Windows uses WSL")
async def test_fresh_task_service_uses_reviewed_builtin_without_callback_injection(tmp_path, monkeypatch, faulty):
    recipe = workbook_recipe()
    assert recipe.extension is not None
    spec = recipe.extension.reference.model_copy(deep=True)
    spec.id = 'workbook'
    spec.input_schema, spec.output_schema = recipe.input_schema, recipe.output_schema
    output = {'workbook_b64': 'invalid'} if faulty else FIXTURES[0]['output']
    program = 'import json; print(json.dumps(' + repr(output) + '))'
    root = tmp_path.resolve()
    monkeypatch.setattr(NativeSandboxConfig, 'argv', lambda self, command: command)
    boundary = NativeSandboxConfig(binary=str(root / 'fixture-codex'), binary_sha256='sha256:' + 'a' * 64,
        project_root=str(root))
    spec.config = {**spec.config, 'argv': [os.sys.executable, '-I', '-c', program],
        'native_sandbox': boundary.model_dump(mode='json'), 'max_output_bytes': 200000,
        'timeout_seconds': 5}
    spec.validators = [ValidationSpec(kind=ValidationKind.CALLBACK,
        config={'name': 'aeep.workbook.native.v1', 'implementation_digest': implementation_digest()})]
    manifest = tmp_path / 'aeep.json'
    manifest.write_text(Manifest(database=str(tmp_path / '.aeep' / 'state.db'), executors=[spec]).model_dump_json())
    router = Router.from_manifest(manifest)  # No injected validator callbacks, as in CLI/App Server.
    repo = AssessmentRepository(router.store)
    captured = []
    original_outcome = router.task_outcome
    def record_outcome(outcome, *, approved_side_effect):
        captured.append(outcome)
        return original_outcome(outcome, approved_side_effect=approved_side_effect)
    monkeypatch.setattr(router, 'task_outcome', record_outcome)
    try:
        repo.review(repo.put('recipe', recipe.recipe_id, recipe))
        scope = TaskScope(scope_id='workbook', project_root=str(tmp_path.resolve()),
            executor_fingerprints={spec.id: executor_fingerprint(spec)}, max_attempts=1,
            max_attempt_seconds=10, expires_at=utc_now() + timedelta(minutes=5))
        repo.review(repo.put('task_scope', scope.scope_id, scope))
        activation = activate(router, scope.scope_id)
        service = AEEPToolService(router, profile='task', task_activation=activation.activation_id)
        name = 'aeep_recipe_' + hashlib.sha256(recipe.capability.encode()).hexdigest()[:12]
        result = await service.call(name, FIXTURES[0]['input'])
        view = result['structuredContent']
        assert view['ok'] is (not faulty)
        receipt = router.store.get_receipt(view['receipts'][0]['receipt_id'])
        assert receipt is not None
        assert receipt.task_valid is (not faulty)
        assert any(item.kind == ValidationKind.CALLBACK and item.valid is (not faulty)
                   for item in receipt.validation_results)
        assert (receipt.error_type == 'execution_error') is faulty
        if not faulty:
            assert 'retained rows, formulas, totals, and Notes values' in view['summary']
            assert any('Formatting and other OOXML' in limit for limit in view['verification_limits'])
            assert view['changes_verified'] is None
            stale = captured[0].model_copy(deep=True)
            stale.receipts[0].executor_fingerprint = 'sha256:' + '0' * 64
            stale_view = original_outcome(stale, approved_side_effect=scope.approval_ceiling)
            assert stale_view.summary == 'Completed; recorded non-schema task checks passed.'
        change_state(router, activation.activation_id, 'uninstall')
    finally:
        await router.close()


async def test_builtin_name_cannot_be_overridden_and_source_drift_fails_closed():
    fixture = FIXTURES[0]
    valid = ValidationSpec(kind=ValidationKind.CALLBACK,
        config={'name': 'aeep.workbook.native.v1', 'implementation_digest': implementation_digest()})
    results = await run_validators([valid], ValidationContext(fixture['input'], fixture['output']),
        {'aeep.workbook.native.v1': lambda _context: False}, raise_errors=True)
    assert results[0].valid is True
    stale = valid.model_copy(deep=True)
    stale.config['implementation_digest'] = '0' * 64
    from aeep.errors import ValidationExecutionError
    with pytest.raises(ValidationExecutionError):
        await run_validators([stale], ValidationContext(fixture['input'], fixture['output']),
            {'aeep.workbook.native.v1': lambda _context: True}, raise_errors=True)


@pytest.mark.skipif(not os.environ.get('AEEP_NATIVE_WORKBOOK_PYTHON'), reason='installed workbook runtime opt-in')
def test_all_reviewed_workbook_variations_and_original_sol_cases():
    binary = os.environ['AEEP_NATIVE_WORKBOOK_PYTHON']
    generated = subprocess.run([binary, '-I', str(ASSETS / 'workbook_program.py'), 'generate'],
        input=json.dumps({'seed': 20260930, 'stages': [{'split': 'demo', 'count': 11}]}),
        text=True, capture_output=True, check=True, timeout=15)
    cases = json.loads(generated.stdout)['cases']
    reference = subprocess.run([binary, '-I', str(ASSETS / 'workbook_program.py'), 'reference'],
        input=json.dumps({'inputs': [case['input'] for case in cases]}),
        text=True, capture_output=True, check=True, timeout=30)
    outputs = json.loads(reference.stdout)['outputs']
    assert len({case['variation'] for case in cases}) == 7
    assert all(validate(ValidationContext(case['input'], output)).valid is True
               for case, output in zip(cases, outputs, strict=True))
    for fault in json.loads((ASSETS / 'workbook-faults.json').read_text()).values():
        assert validate(ValidationContext(FIXTURES[0]['input'], fault)).valid is False
