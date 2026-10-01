"""Pinned SkillsBench offer-letter case for local exploratory artifact tests.

This adapts one external task to the existing case/callback contract. It does
not materialize a qualifying recipe or run the upstream verifier.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import re
import zipfile
from collections.abc import Callable
from pathlib import Path
from xml.etree import ElementTree as ET

from ..benchmarking import BenchmarkCase, BenchmarkSplit
from ..errors import ConfigurationError
from ..models import ActionRequest, TrustLevel, ValidationKind, ValidationResult, ValidationSpec
from ..validators import ValidationContext

TEMPLATE_SHA256 = '34a2fe42f5799f35b9543af63d712b9e28cc93f97847528c3fbfe76071f60d15'
DATA_SHA256 = '64dcb6aad2423051a638efefc85d1b47d306718e462342281553bf00082870c0'
_W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
_SPLIT_FIELDS = ('DATE', 'CANDIDATE_FULL_NAME', 'CITY', 'STATE', 'ZIP_CODE',
    'POSITION', 'DEPARTMENT', 'RESPONSE_DEADLINE', 'HR_NAME', 'PTO_DAYS')
_NESTED_FIELDS = ('POSITION', 'DEPARTMENT', 'BASE_SALARY', 'SIGNING_BONUS',
    'EQUITY_SHARES', 'MANAGER_NAME')


def _pinned_bytes(path: Path, digest: str, limit: int) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ConfigurationError('pinned offer-letter input is missing or unsafe')
    contents = path.read_bytes()
    if hashlib.sha256(contents).hexdigest() != digest:
        raise ConfigurationError('pinned offer-letter input digest changed')
    return contents


def _document(encoded: str) -> tuple[bytes, dict[str, ET.Element], list[str], list[str]]:
    if not isinstance(encoded, str) or len(encoded) > 200000:
        raise ConfigurationError('offer-letter artifact exceeds its encoded bound')
    try:
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > 150000:
            raise ConfigurationError('offer-letter artifact exceeds its byte bound')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            if (len(members) > 100 or len(names) != len(set(names))
                    or sum(member.file_size for member in members) > 2_000_000
                    or any(name.startswith('/') or '\\' in name or '..' in name.split('/')
                           or any(bad in name.lower() for bad in ('vba', 'externallink', 'embeddings'))
                           for name in names)
                    or 'word/document.xml' not in names):
                raise ConfigurationError('offer-letter artifact has an unsafe package structure')
            roots: dict[str, ET.Element] = {}
            for name in names:
                if not name.endswith(('.xml', '.rels')):
                    continue
                xml = archive.read(name)
                decoded = xml.decode('utf-8-sig')
                declaration = re.match(r'<\?xml[^>]*encoding=[\'\"]([^\'\"]+)', decoded, re.IGNORECASE)
                if declaration and declaration.group(1).lower() != 'utf-8':
                    raise ConfigurationError('offer-letter artifact has an unsupported XML encoding')
                if '\x00' in decoded or '<!DOCTYPE' in decoded.upper() or '<!ENTITY' in decoded.upper():
                    raise ConfigurationError('offer-letter artifact contains an XML declaration')
                root = ET.fromstring(decoded)
                stack = [(root, 1)]
                count = 0
                while stack:
                    node, depth = stack.pop()
                    count += 1
                    if count > 50000 or depth > 64:
                        raise ConfigurationError('offer-letter XML exceeds its node or depth bound')
                    stack.extend((child, depth + 1) for child in node)
                if any(node.get('TargetMode') == 'External' for node in root.iter()):
                    raise ConfigurationError('offer-letter artifact contains an external relationship')
                roots[name] = root
    except (ValueError, UnicodeError, zipfile.BadZipFile, ET.ParseError, RuntimeError, OSError) as exc:
        raise ConfigurationError('offer-letter artifact is not valid bounded DOCX') from exc
    all_text: list[str] = []
    nested_text: list[str] = []
    for name in sorted(roots):
        root = roots[name]
        if name != 'word/document.xml' and not re.fullmatch(r'word/(?:header|footer)\d+\.xml', name):
            continue
        parents = {child: parent for parent in root.iter() for child in parent}
        for paragraph in root.iter(_W + 'p'):
            text = ''.join(node.text or '' for node in paragraph.iter(_W + 't'))
            all_text.append(text)
            depth = 0
            cursor = parents.get(paragraph)
            while cursor is not None:
                depth += cursor.tag == _W + 'tbl'
                cursor = parents.get(cursor)
            if name == 'word/document.xml' and depth >= 2:
                nested_text.append(text)
    return raw, roots, all_text, nested_text


def grade_artifact(encoded: str, template_encoded: str, data: dict[str, str]) -> dict[str, bool]:
    """Return pinned upstream checks and separate adapted text/structure checks."""
    _raw, roots, all_parts, nested_parts = _document(encoded)
    _template_raw, template_roots, template_parts, _ = _document(template_encoded)
    all_text = '\n'.join(all_parts)
    nested_text = '\n'.join(nested_parts)
    markers_absent = '{{IF_RELOCATION}}' not in all_text and '{{END_IF_RELOCATION}}' not in all_text
    upstream = (data['RELOCATION_PACKAGE'] == 'Yes'
        and not re.search(r'\{\{[A-Z_]+\}\}', all_text)
        and all(data[field] in all_text for field in _SPLIT_FIELDS)
        and all(data[field] in nested_text for field in _NESTED_FIELDS)
        and markers_absent
        and all(data[field] in all_text for field in ('RELOCATION_AMOUNT', 'RELOCATION_DAYS')))
    def expected_text(part: str) -> str:
        if data['RELOCATION_PACKAGE'] == 'Yes':
            part = part.replace('{{IF_RELOCATION}}', '').replace('{{END_IF_RELOCATION}}', '')
        else:
            part = re.sub(r'\{\{IF_RELOCATION\}\}.*?\{\{END_IF_RELOCATION\}\}', '', part)
        return re.sub(r'\{\{([A-Z_]+)\}\}', lambda match: data[match.group(1)], part)
    expected_parts = [expected_text(part) for part in template_parts]
    text_preserved = all_parts == expected_parts
    body = roots['word/document.xml']
    template_body = template_roots['word/document.xml']
    structure = (set(roots) == set(template_roots)
        and len(list(body.iter(_W + 'tbl'))) == len(list(template_body.iter(_W + 'tbl')))
        and len(list(body.iter(_W + 'p'))) == len(list(template_body.iter(_W + 'p'))))
    result = {'upstream_equivalent': bool(upstream), 'text_preserved': bool(text_preserved),
        'structure_counts_match': bool(structure)}
    if data['RELOCATION_PACKAGE'] != 'Yes':
        markers = [index for index, part in enumerate(template_parts) if '{{IF_RELOCATION}}' in part]
        result['no_relocation_block'] = (len(markers) == 1 and len(all_parts) == len(expected_parts)
            and all_parts[markers[0]] == expected_parts[markers[0]] and markers_absent)
    return result


def exploratory_case(asset_root: Path, *, capability: str = 'assessment.offer_letter@1') -> tuple[BenchmarkCase, Callable[[ValidationContext], ValidationResult]]:
    """Expose only pinned task inputs to the action; keep grading in a callback."""
    template = _pinned_bytes(asset_root / 'offer_letter_template.docx', TEMPLATE_SHA256, 150000)
    data_bytes = _pinned_bytes(asset_root / 'employee_data.json', DATA_SHA256, 10000)
    data = json.loads(data_bytes)
    if not isinstance(data, dict) or any(not isinstance(key, str) or not isinstance(value, str)
                                         for key, value in data.items()):
        raise ConfigurationError('pinned offer-letter data must be a string map')
    required = {*_SPLIT_FIELDS, *_NESTED_FIELDS, 'RELOCATION_PACKAGE', 'RELOCATION_AMOUNT', 'RELOCATION_DAYS'}
    if not required <= data.keys():
        raise ConfigurationError('pinned offer-letter data lacks required fields')
    template_encoded = base64.b64encode(template).decode('ascii')
    trusted_data = copy.deepcopy(data)
    expected_input = {'template_b64': template_encoded, 'employee_data': copy.deepcopy(data)}
    case = BenchmarkCase(case_id='skillsbench-offer-letter-pinned-exploratory',
        split=BenchmarkSplit.QUALIFICATION,
        action=ActionRequest(capability=capability, input=copy.deepcopy(expected_input)),
        validators=[ValidationSpec(kind=ValidationKind.CALLBACK, config={'name': 'skillsbench_offer_letter_pinned'})])

    def callback(context: ValidationContext) -> ValidationResult:
        try:
            if context.input != expected_input:
                raise ConfigurationError('offer-letter task input changed')
            output = context.output
            if not isinstance(output, dict) or set(output) != {'document_b64'}:
                raise ConfigurationError('offer-letter output contract changed')
            result = grade_artifact(output['document_b64'], template_encoded, trusted_data)
            valid = all(result.values())
            detail = 'passed' if valid else ','.join(key for key, value in result.items() if not value)
        except (ConfigurationError, KeyError, TypeError):
            valid, detail = False, 'invalid_artifact'
        return ValidationResult(kind=ValidationKind.CALLBACK, valid=valid,
            quality_score=1.0 if valid else 0.0, detail=detail, trust=TrustLevel.VERIFIED)

    return case, callback
