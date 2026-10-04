"""Contained semantic grader; exporter prefixes the existing bounded DOCX reader.

No relocation is an AEEP adaptation, not an upstream verifier success. Literal
fixtures and independent reference outputs must pass existing grader validation
before this definition can supply qualification evidence.
"""
import hashlib
import io
import json
import sys
import zipfile
from collections.abc import Callable
from xml.etree import ElementTree as ET

# The exporter supplies these exact definitions before this fragment. Resolve
# them explicitly and fail if its pinned prefix is missing; there is no fallback.
ASSETS: dict = globals()['ASSETS']
VARIATIONS: list[str] = globals()['VARIATIONS']
TASK: str = globals()['TASK']
_W: str = globals()['_W']
ConfigurationError: type[ValueError] = globals()['ConfigurationError']
_document: Callable[[str], tuple[bytes, dict[str, ET.Element], list[str], list[str]]] = globals()['_document']
grade_artifact: Callable[[str, str, dict[str, str]], dict[str, bool]] = globals()['grade_artifact']


def failure_code(example):
    try:
        value = example['input']
        digest = hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
            separators=(',', ':')).encode()).hexdigest()
        if (example['expected'] != {'input_sha256': digest}
                or value['template_b64'] != ASSETS['template_b64'] or value['task'] != TASK
                or value['variation'] not in VARIATIONS):
            return 'input_binding'
        data = value['employee_data']
        if (set(data) != set(ASSETS['employee_data']) or data['RELOCATION_PACKAGE'] not in {'Yes', 'No'}
                or any(not isinstance(item, str) or not 1 <= len(item) <= 256
                       or any(ord(char) < 32 for char in item) for item in data.values())):
            return 'input_binding'
        output = example['output']
        if not isinstance(output, dict) or set(output) != {'document_b64'}:
            return 'output_contract'
        checks = grade_artifact(output['document_b64'], value['template_b64'], data)
        if not checks['text_preserved']:
            return 'text_preserved'
        if not checks['structure_counts_match']:
            return 'document_structure'
        if data['RELOCATION_PACKAGE'] == 'Yes' and not checks['upstream_equivalent']:
            return 'relocation_yes'
        if data['RELOCATION_PACKAGE'] == 'No' and not checks['no_relocation_block']:
            return 'relocation_no'
        raw, roots, _, _ = _document(output['document_b64'])
        template, originals, _, _ = _document(value['template_b64'])
        # Preserve every non-text property and element. Text runs may redistribute
        # replacement text; visual pagination/typographic fidelity is excluded.
        for name in roots:
            for tree in (roots[name], originals[name]):
                for node in tree.iter(_W + 't'):
                    node.text = ''
                    node.attrib.pop('{http://www.w3.org/XML/1998/namespace}space', None)
            if ET.tostring(roots[name]) != ET.tostring(originals[name]):
                return 'document_structure'
        with zipfile.ZipFile(io.BytesIO(raw)) as actual, zipfile.ZipFile(io.BytesIO(template)) as source:
            if set(actual.namelist()) != set(source.namelist()):
                return 'package_members'
            if any(actual.read(name) != source.read(name) for name in source.namelist() if name not in roots):
                return 'preserved_parts'
        return None
    except (ConfigurationError, ValueError, TypeError, KeyError, IndexError, AttributeError,
            RuntimeError, NotImplementedError, ET.ParseError, zipfile.BadZipFile):
        return 'invalid_document'


if __name__ == '__main__':
    raw = sys.stdin.buffer.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError('offer-letter grading request too large')
    payload = json.loads(raw)
    if set(payload) != {'examples'} or not isinstance(payload['examples'], list) or len(payload['examples']) > 1000:
        raise ValueError('unsupported offer-letter grading contract')
    codes = [failure_code(example) for example in payload['examples']]
    print(json.dumps({'valid': [code is None for code in codes], 'failure_codes': codes}))
