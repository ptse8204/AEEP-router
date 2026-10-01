"""Pinned external task adaptation; local exploratory checks, not qualification."""

from __future__ import annotations

import base64
import io
import json
import re
import warnings
import zipfile
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from conftest import python_spec

from aeep.assessment.skillsbench_offer_letter import exploratory_case, grade_artifact
from aeep.benchmarking import (
    AssessmentBenchmarkCondition,
    BenchmarkRoute,
    BenchmarkRunner,
    BenchmarkSuite,
)
from aeep.errors import ConfigurationError
from aeep.models import Manifest
from aeep.router import Router
from aeep.validators import ValidationContext, run_validators

ASSETS = Path(__file__).resolve().parents[1] / 'reports/v08/skillsbench-offer-letter-pinned'
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
pytestmark = pytest.mark.assessment_contract


def _filled(template: bytes, data: dict[str, str], *, remove_paragraph: bool = False) -> str:
    """Independent fixture builder using OOXML, not the grader's text walk."""
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(template)) as original, zipfile.ZipFile(output, 'w') as filled:
        for member in original.infolist():
            raw = original.read(member)
            if member.filename.startswith('word/') and member.filename.endswith('.xml'):
                root = ET.fromstring(raw)
                for paragraph in root.iter(W + 'p'):
                    texts = list(paragraph.iter(W + 't'))
                    if not texts:
                        continue
                    joined = ''.join(node.text or '' for node in texts)
                    if data['RELOCATION_PACKAGE'] != 'Yes':
                        joined = re.sub(r'\{\{IF_RELOCATION\}\}.*?\{\{END_IF_RELOCATION\}\}', '', joined)
                    else:
                        joined = joined.replace('{{IF_RELOCATION}}', '').replace('{{END_IF_RELOCATION}}', '')
                    joined = re.sub(r'\{\{([A-Z_]+)\}\}', lambda match: data[match.group(1)], joined)
                    texts[0].text = joined
                    for node in texts[1:]:
                        node.text = ''
                if member.filename == 'word/document.xml' and remove_paragraph:
                    body = root.find('.//' + W + 'body')
                    assert body is not None
                    paragraph = next(child for child in body if child.tag == W + 'p')
                    body.remove(paragraph)
                raw = ET.tostring(root, encoding='utf-8', xml_declaration=True)
            filled.writestr(member, raw)
    return base64.b64encode(output.getvalue()).decode('ascii')


def _fixture_executor(template_b64: str, employee_data: dict[str, str]) -> dict[str, str]:
    return {'document_b64': _filled(base64.b64decode(template_b64), employee_data)}


def _faulty_executor(template_b64: str, employee_data: dict[str, str]) -> dict[str, str]:
    return {'document_b64': _filled(base64.b64decode(template_b64), employee_data,
        remove_paragraph=True)}


def test_offer_letter_rejects_deep_xml_before_grading():
    case, _ = exploratory_case(ASSETS)
    template = base64.b64decode(case.action.input['template_b64'])
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(template)) as source, zipfile.ZipFile(output, 'w') as target:
        for member in source.infolist():
            raw = source.read(member)
            if member.filename == 'word/document.xml':
                root = ET.fromstring(raw)
                cursor = root
                for _ in range(70):
                    cursor = ET.SubElement(cursor, 'deep')
                raw = ET.tostring(root, encoding='utf-8')
            target.writestr(member, raw)
    with pytest.raises(ConfigurationError, match='node or depth bound'):
        grade_artifact(base64.b64encode(output.getvalue()).decode(),
            case.action.input['template_b64'], case.action.input['employee_data'])


@pytest.mark.parametrize('faulty', [False, True])
async def test_exploratory_case_uses_existing_router_and_benchmark_validation(tmp_path, faulty):
    case, callback = exploratory_case(ASSETS)
    identity = 'faulty' if faulty else 'fixture'
    spec = python_spec(identity, f'test_v08_skillsbench_offer_letter:_{identity}_executor',
        capability=case.action.capability)
    suite = BenchmarkSuite(suite_id='skillsbench-local-exploratory', repetitions=1,
        routes=[BenchmarkRoute(route_id=identity, executor_id=identity)],
        conditions=[AssessmentBenchmarkCondition.ROUTER_FRESH],
        max_total_cash_usd=Decimal(0), cases=[case])
    runner = BenchmarkRunner(lambda: Router(Manifest(database=':memory:', executors=[spec]),
        validator_callbacks={'skillsbench_offer_letter_pinned': callback}), tmp_path / 'campaign.sqlite3')
    try:
        report = await runner.run(suite)
        assert report.trials[0].valid is (not faulty)
        assert len(runner.connection.execute('SELECT 1 FROM trial_receipts').fetchall()) == 1
    finally:
        runner.connection.close()


async def test_pinned_offer_letter_case_passes_trusted_callback_and_rejects_faults(tmp_path):
    case, callback = exploratory_case(ASSETS)
    assert set(case.action.input) == {'template_b64', 'employee_data'}
    assert len(case.validators) == 1
    data = case.action.input['employee_data']
    template = base64.b64decode(case.action.input['template_b64'])
    correct = {'document_b64': _filled(template, data)}
    result = await run_validators(case.validators, ValidationContext(case.action.input, correct),
        {'skillsbench_offer_letter_pinned': callback}, raise_errors=True)
    assert result[0].valid is True
    assert grade_artifact(correct['document_b64'], case.action.input['template_b64'], data) == {
        'upstream_equivalent': True, 'text_preserved': True, 'structure_counts_match': True}
    rearranged = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(correct['document_b64']))) as source, zipfile.ZipFile(rearranged, 'w') as target:
        for member in reversed(source.infolist()):
            target.writestr(member, source.read(member))
    assert all(grade_artifact(base64.b64encode(rearranged.getvalue()).decode(),
        case.action.input['template_b64'], data).values())

    malformed = await run_validators(case.validators,
        ValidationContext(case.action.input, {'document_b64': 'invalid'}),
        {'skillsbench_offer_letter_pinned': callback}, raise_errors=True)
    assert malformed[0].valid is False and malformed[0].detail == 'invalid_artifact'

    missing_structure = {'document_b64': _filled(template, data, remove_paragraph=True)}
    structural = grade_artifact(missing_structure['document_b64'], case.action.input['template_b64'], data)
    assert structural == {'upstream_equivalent': True, 'text_preserved': False, 'structure_counts_match': False}
    rejected = await run_validators(case.validators,
        ValidationContext(case.action.input, missing_structure),
        {'skillsbench_offer_letter_pinned': callback}, raise_errors=True)
    assert rejected[0].valid is False and rejected[0].detail == 'text_preserved,structure_counts_match'

    swapped_input = dict(case.action.input)
    swapped_input['employee_data'] = dict(data, BASE_SALARY='changed')
    tampered = await run_validators(case.validators, ValidationContext(swapped_input, correct),
        {'skillsbench_offer_letter_pinned': callback}, raise_errors=True)
    assert tampered[0].valid is False and tampered[0].detail == 'invalid_artifact'
    case.action.input['employee_data']['BASE_SALARY'] = 'changed'
    mutated_case = await run_validators(case.validators,
        ValidationContext(case.action.input, correct),
        {'skillsbench_offer_letter_pinned': callback}, raise_errors=True)
    assert mutated_case[0].valid is False and mutated_case[0].detail == 'invalid_artifact'

    changed = tmp_path / 'inputs'
    changed.mkdir()
    (changed / 'offer_letter_template.docx').write_bytes(template)
    corrupt_data = dict(data)
    corrupt_data['BASE_SALARY'] = 'wrong'
    (changed / 'employee_data.json').write_text(json.dumps(corrupt_data))
    with pytest.raises(ConfigurationError, match='digest changed'):
        exploratory_case(changed)


def test_no_relocation_conditional_is_a_separate_adapted_check():
    case, _callback = exploratory_case(ASSETS)
    data = dict(case.action.input['employee_data'])
    data['RELOCATION_PACKAGE'] = 'No'
    template = base64.b64decode(case.action.input['template_b64'])
    grade = grade_artifact(_filled(template, data), case.action.input['template_b64'], data)
    assert grade['upstream_equivalent'] is False  # Upstream verifier only covers pinned Yes data.
    assert grade['no_relocation_block'] is True and grade['text_preserved'] is True
    kept = dict(data, RELOCATION_PACKAGE='Yes')
    bad = grade_artifact(_filled(template, kept), case.action.input['template_b64'], data)
    assert bad['no_relocation_block'] is False and bad['text_preserved'] is False


@pytest.mark.parametrize('fault', ['duplicate', 'doctype', 'utf16', 'utf16_without_bom'])
def test_offer_letter_grader_rejects_unsafe_ooxml(fault):
    case, _callback = exploratory_case(ASSETS)
    source = base64.b64decode(case.action.input['template_b64'])
    target = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source)) as original, zipfile.ZipFile(target, 'w') as output:
        for member in original.infolist():
            payload = original.read(member)
            if member.filename == 'word/document.xml':
                if fault == 'doctype':
                    payload = payload.replace(b'<w:document', b'<!DOCTYPE unsafe><w:document', 1)
                elif fault == 'utf16':
                    payload = ET.tostring(ET.fromstring(payload), encoding='utf-16', xml_declaration=True)
                elif fault == 'utf16_without_bom':
                    payload = ET.tostring(ET.fromstring(payload), encoding='utf-16', xml_declaration=True)[2:]
            output.writestr(member, payload)
        if fault == 'duplicate':
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                output.writestr('word/document.xml', original.read('word/document.xml'))
    with pytest.raises(ConfigurationError, match=r'unsafe|invalid|encoding|declaration|not valid'):
        grade_artifact(base64.b64encode(target.getvalue()).decode(),
            case.action.input['template_b64'], case.action.input['employee_data'])
