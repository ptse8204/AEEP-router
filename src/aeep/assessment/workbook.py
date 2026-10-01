"""Reviewable workbook recipe assets; programs execute through contained JSON extensions."""
from __future__ import annotations

import base64
import io
import json
import re
import sysconfig
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from ..errors import ConfigurationError
from ..models import ExecutorKind, ExecutorSpec
from .models import (
    ExecutableRecipeExtension,
    RecipeDefinition,
    RecipeFeatureRule,
    RecipeLiteralFixture,
)

VARIATIONS = ['mixed_types_dates', 'missing_invalid', 'duplicates', 'multiple_sheets',
              'formulas', 'structure_formatting', 'unicode_sparse']


def workbook_features(value: dict[str, Any]) -> dict[str, str | int | bool] | None:
    """Inspect bounded worksheet structure, without cleaning records or computing answers."""
    try:
        encoded = value['workbook_b64']
        if not isinstance(encoded, str) or len(encoded) > 200000 or value['variation'] not in VARIATIONS:
            return None
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(encoded, validate=True))) as archive:
            entries = archive.infolist()
            if (len(entries) > 100 or len({item.filename for item in entries}) != len(entries)
                    or sum(item.file_size for item in entries) > 2000000
                    or any('..' in item.filename.split('/') or item.filename.startswith('/')
                           or 'vba' in item.filename.lower() or 'externallink' in item.filename.lower() for item in entries)):
                return None
            rows = cells = sheets = formulas = 0
            unicode_text = False
            fractional = negative = outside_numeric_bound = False
            ns = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
            for item in entries:
                if not item.filename.endswith('.xml') and not item.filename.endswith('.rels'):
                    continue
                raw = archive.read(item)
                if b'<!DOCTYPE' in raw or b'<!ENTITY' in raw:
                    return None
                root = ET.fromstring(raw)
                if any(element.get('TargetMode') == 'External' for element in root.iter()):
                    return None
                if item.filename.startswith('xl/worksheets/'):
                    sheets += 1
                    rows += len(list(root.iter(ns+'row')))
                    cells += len(list(root.iter(ns+'c')))
                    formulas += len(list(root.iter(ns+'f')))
                    if any(formula.text != '1+1' for formula in root.iter(ns+'f')):
                        return None  # Unreviewed input formula grammar, not a request to evaluate it.
                    addresses = [cell.get('r') for cell in root.iter(ns+'c')]
                    if len(set(addresses)) != len(addresses):
                        return None
                    for cell in root.iter(ns+'c'):
                        if not re.fullmatch(r'[CD](?:[2-9]|[1-9][0-9]+)', cell.get('r', '')):
                            continue
                        text = ''.join(cell.itertext())
                        try:
                            number = Decimal(text)
                        except InvalidOperation:
                            continue  # Invalid numeric strings are an explicitly tested variation.
                        if not number.is_finite():
                            return None
                        fractional |= number != number.to_integral_value()
                        negative |= number < 0
                        outside_numeric_bound |= abs(number) > 1000
                    unicode_text |= any(ord(character) > 127 for character in ''.join(root.itertext()))
            if not 1 <= sheets <= 4 or not 1 <= rows <= 40 or not 1 <= cells <= 200:
                return None
            return {'variation': value['variation'], 'sheets': sheets, 'rows': rows,
                    'cells': cells, 'formulas': formulas, 'unicode': unicode_text,
                    'fractional_numbers': fractional, 'negative_numbers': negative,
                    'outside_numeric_bound': outside_numeric_bound,
                    'shared_strings': 'xl/sharedStrings.xml' in archive.namelist()}
    except (ValueError, TypeError, KeyError, ArithmeticError, RuntimeError, NotImplementedError, ET.ParseError, zipfile.BadZipFile):
        return None


def workbook_recipe() -> RecipeDefinition:
    root = Path(__file__).resolve().parents[3] / 'integrations' / 'assessment-runtime'
    if not root.is_dir():
        root = Path(sysconfig.get_path('data')) / 'share' / 'aeep' / 'integrations' / 'assessment-runtime'
    try:
        program = (root / 'workbook_program.py').read_text()
        grader = (root / 'workbook_grader.py').read_text()
        fixtures = [RecipeLiteralFixture(input=item['input'], output=item['expected'], grader_output=item['output'])
                    for item in json.loads((root / 'workbook-grader-fixtures.json').read_text())]
        faults = list(json.loads((root / 'workbook-faults.json').read_text()).values())
    except (OSError, ValueError) as exc:
        raise ConfigurationError('installed workbook recipe assets are unavailable') from exc

    def executor(name: str, source: str, mode: str) -> ExecutorSpec:
        return ExecutorSpec(id=f'workbook.{name}', capability='assessment.workbook@1', kind=ExecutorKind.COMMAND,
            description='Reviewed offline workbook recipe program', config={
                'argv': ['python3', '-c', source, mode], 'argv_literal': True, 'stdin_json': True,
                'timeout_seconds': 30, 'max_output_bytes': 16000000, 'output': {'type': 'json'}})

    return RecipeDefinition(schema_version='assessment.recipe.v2', recipe_id='workbook',
        capability='assessment.workbook@1', description='Clean bounded workbook records, formulas and summaries while preserving required structure.',
        input_schema={'type': 'object', 'required': ['workbook_b64', 'task', 'variation', 'row_bound'], 'additionalProperties': False,
            'properties': {'workbook_b64': {'type': 'string', 'maxLength': 200000}, 'task': {'const': fixtures[0].input['task']},
                           'variation': {'enum': VARIATIONS}, 'row_bound': {'type': 'integer', 'minimum': 1, 'maximum': 32}}},
        output_schema={'type': 'object', 'required': ['workbook_b64'], 'additionalProperties': False,
                       'properties': {'workbook_b64': {'type': 'string', 'maxLength': 200000}}},
        generator='contained_json:1', grader='contained_json:1', extractor='workbook_structure:1', variations=VARIATIONS,
        exclusions=['macros', 'external links', 'connected Excel', 'formulas other than relative products and SUM ranges',
                    'workbooks larger than the admitted structural bounds', 'fractional or negative quantities/prices',
                    'input formulas other than the reviewed stale constant formula', 'unobserved shared-string input encodings'],
        extension=ExecutableRecipeExtension(schema_version='assessment.recipe-extension.v3',
            failure_codes=['output_contract', 'sheet_set', 'data_extent', 'header_format', 'cell_value',
                           'row_formula', 'formula_cache', 'summary', 'preserved_sheets', 'invalid_workbook'],
            generator=executor('generator', program, 'generate'), reference=executor('reference', program, 'reference'),
            grader=executor('grader', grader, 'diagnose'),
            truth_schema={'type': 'object', 'required': ['rows', 'extras'], 'additionalProperties': False,
                          'properties': {'rows': {'type': 'array', 'maxItems': 32}, 'extras': {'type': 'object'}}},
            independent_fixtures=fixtures[:2], transformed_fixtures=fixtures[2:], fault_outputs=[{'workbook_b64': 'invalid'}, *faults],
            feature_rules={'variation': RecipeFeatureRule(path='/variation', operation='enum', values=list(VARIATIONS)),
                           'encoded_bytes': RecipeFeatureRule(path='/workbook_b64', operation='length')},
            variation_features={value: {'variation': value} for value in VARIATIONS},
            template_families=['workbook:' + value for value in VARIATIONS]))
