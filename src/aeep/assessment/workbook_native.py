"""Fixed, bounded workbook check for reviewed native task executors."""

from __future__ import annotations

import base64
import hashlib
import io
import posixpath
import re
import zipfile
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from ..models import TrustLevel, ValidationKind, ValidationResult
from ..validators import ValidationContext
from .workbook import workbook_features

TASK = ('Clean Data rows: preserve first occurrence of each ID; discard rows with invalid numeric '
        'quantity/price; missing numbers become zero. Preserve order and ID text. Normalize dates '
        'to YYYY-MM-DD text. Set Amount to a relative Quantity*Price formula on every retained row. '
        'Write Summary!A1="Total" and Summary!B1=SUM(Data!E2:E<last-row>). Preserve other sheets '
        'and their values. Keep all Data header cells bold. Save an XLSX with recalculated formula '
        'caches; return its base64 bytes as workbook_b64. No macros or external links.')
N = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'


def implementation_digest() -> str:
    digest = hashlib.sha256()
    for path in (Path(__file__), Path(__file__).with_name('workbook.py')):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _inspect(encoded: str) -> tuple[dict[str, dict[str, tuple[Any, str | None, int]]], set[int], set[int]]:
    if not isinstance(encoded, str) or len(encoded) > 200000:
        raise ValueError('oversized workbook')
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(encoded, validate=True))) as archive:
        entries = archive.infolist()
        names = [item.filename for item in entries]
        if (len(entries) > 100 or len(names) != len(set(names))
                or sum(item.file_size for item in entries) > 2_000_000
                or any(name.startswith('/') or '\\' in name or '..' in name.split('/')
                       or name.lower().endswith('.bin')
                       or any(bad in name.lower() for bad in
                              ('vba', 'externallink', 'activex', 'embeddings', 'drawings', 'charts'))
                       for name in names)):
            raise ValueError('unsupported workbook archive')

        def xml(name: str) -> ET.Element:
            raw = archive.read(name)
            decoded = raw.decode('utf-8-sig')
            if '\x00' in decoded or '<!DOCTYPE' in decoded.upper() or '<!ENTITY' in decoded.upper():
                raise ValueError('unsafe workbook XML')
            declaration = re.match(r'<\?xml[^>]*encoding=[\'\"]([^\'\"]+)', decoded, re.IGNORECASE)
            if declaration and declaration.group(1).lower() != 'utf-8':
                raise ValueError('unsupported workbook XML encoding')
            root = ET.fromstring(decoded)
            stack = [(root, 1)]
            count = 0
            while stack:
                node, depth = stack.pop()
                count += 1
                if count > 50000 or depth > 64:
                    raise ValueError('workbook XML exceeds its node or depth bound')
                stack.extend((child, depth + 1) for child in node)
            return root

        for name in names:
            if name.endswith('.rels') or name == '[Content_Types].xml':
                metadata = xml(name)
                for node in metadata.iter():
                    if node.get('TargetMode') == 'External':
                        raise ValueError('external workbook relationship')
                    if any(bad in str(attribute).lower() for attribute in node.attrib.values()
                           for bad in ('vba', 'macroenabled', 'activex', 'oleobject',
                                       'embedded', 'chart', 'drawing')):
                        raise ValueError('unreviewed workbook package feature')
        links = xml('xl/_rels/workbook.xml.rels')
        targets: dict[str, str] = {}
        for link in links:
            target = link.get('Target', '')
            resolved = target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join('xl', target))
            if not resolved.startswith('xl/') or resolved not in names:
                raise ValueError('workbook relationship escapes package')
            targets[link.get('Id', '')] = resolved
        strings: list[str] = []
        if 'xl/sharedStrings.xml' in names:
            strings = [''.join(item.itertext()) for item in xml('xl/sharedStrings.xml').findall(N + 'si')]
        sheets: dict[str, dict[str, tuple[Any, str | None, int]]] = {}
        workbook = xml('xl/workbook.xml')
        properties = workbook.find(N + 'workbookPr')
        if properties is not None and properties.get('date1904', 'false').lower() in {'true', '1'}:
            raise ValueError('unreviewed workbook date epoch')
        sheet_list = workbook.find(N + 'sheets')
        if sheet_list is None:
            raise ValueError('workbook has no sheets')
        for sheet in sheet_list:
            cells: dict[str, tuple[Any, str | None, int]] = {}
            for cell in xml(targets[sheet.get(R + 'id', '')]).iter(N + 'c'):
                address = cell.get('r', '')
                if address in cells or not re.fullmatch(r'[A-Z]{1,2}[1-9][0-9]*', address):
                    raise ValueError('invalid workbook cell address')
                value: Any = cell.findtext(N + 'v')
                formula_node = cell.find(N + 'f')
                if formula_node is not None and formula_node.attrib:
                    raise ValueError('unreviewed workbook formula type')
                formula = formula_node.text if formula_node is not None else None
                if cell.get('t') == 'inlineStr':
                    inline = cell.find(N + 'is')
                    value = ''.join(inline.itertext()) if inline is not None else None
                elif cell.get('t') == 's':
                    value = strings[int(value)]
                elif cell.get('t') == 'str':
                    pass
                elif cell.get('t') not in (None, 'n'):
                    raise ValueError('unsupported workbook cell type')
                elif value is not None:
                    value = Decimal(value) if value.strip() else None
                cells[address] = (value, formula, int(cell.get('s', '0')))
            name = sheet.get('name', '')
            if name in sheets:
                raise ValueError('duplicate workbook sheet')
            sheets[name] = cells
        styles = xml('xl/styles.xml')
        fonts_node, cell_formats = styles.find(N + 'fonts'), styles.find(N + 'cellXfs')
        if fonts_node is None or cell_formats is None:
            raise ValueError('workbook styles missing')
        fonts = list(fonts_node)
        bold = set()
        for index, style in enumerate(cell_formats):
            bold_node = fonts[int(style.get('fontId', '0'))].find(N + 'b')
            if bold_node is not None and bold_node.get('val', '1') not in {'0', 'false'}:
                bold.add(index)
        custom_formats = styles.find(N + 'numFmts')
        date_formats = {int(item.get('numFmtId', '-1')) for item in (custom_formats if custom_formats is not None else [])
                        if item.get('formatCode') in {'yyyy-mm-dd h:mm:ss', 'yyyy-mm-dd'}}
        date_styles = {index for index, style in enumerate(cell_formats)
                       if int(style.get('numFmtId', '0')) in date_formats}
        return sheets, bold, date_styles


def _number(value: Any) -> int | None:
    if value is None or value == '':
        return 0
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or number != number.to_integral_value() or not 0 <= number <= 1000:
        return None
    return int(number)


def _truth(value: dict[str, Any]) -> dict[str, Any]:
    if (not isinstance(value, dict)
            or set(value) != {'workbook_b64', 'task', 'variation', 'row_bound'}
            or value['task'] != TASK
            or type(value['row_bound']) is not int or not 1 <= value['row_bound'] <= 32):
        raise ValueError('unsupported workbook task input')
    sheets, _bold, date_styles = _inspect(value['workbook_b64'])
    features = workbook_features(value)
    if features is None or any(features[key] for key in ('fractional_numbers', 'negative_numbers',
                                    'outside_numeric_bound', 'shared_strings')):
        raise ValueError('unreviewed workbook numeric or string encoding')
    if set(sheets) not in ({'Data'}, {'Data', 'Notes'}):
        raise ValueError('unreviewed workbook sheet set')
    data = sheets['Data']
    if any(data.get(f'{col}1', (None, None, 0))[0] != header for col, header in
           zip('ABCDE', ('ID', 'Date', 'Quantity', 'Price', 'Amount'), strict=True)):
        raise ValueError('unreviewed workbook headers')
    for address in data:
        match = re.fullmatch(r'([A-E])([1-9][0-9]*)', address)
        if match is None or int(match.group(2)) > value['row_bound'] + 1:
            raise ValueError('unreviewed workbook cell extent')
        formula = data[address][1]
        if formula is not None and not (match.group(1) == 'E' and int(match.group(2)) >= 2
                                        and formula == '1+1'):
            raise ValueError('unreviewed input formula')
    rows = range(2, value['row_bound'] + 2)
    cleaned: list[list[Any]] = []
    seen: set[str] = set()
    for row in rows:
        identity = data.get(f'A{row}', (None, None, 0))[0]
        if identity is None or identity == '' or identity in seen:
            continue
        if not isinstance(identity, str):
            raise ValueError('unreviewed workbook ID type')
        seen.add(identity)
        date_cell = data.get(f'B{row}', (None, None, 0))
        date = date_cell[0]
        quantity = _number(data.get(f'C{row}', (None, None, 0))[0])
        price = _number(data.get(f'D{row}', (None, None, 0))[0])
        if quantity is None or price is None:
            continue
        if (isinstance(date, Decimal) and date_cell[2] in date_styles
                and date == date.to_integral_value() and 61 <= date <= 73000):
            date = (datetime(1899, 12, 30) + timedelta(days=int(date))).strftime('%Y-%m-%d')
        if not isinstance(date, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
            raise ValueError('native workbook check requires reviewed ISO dates')
        try:
            if datetime.strptime(date, '%Y-%m-%d').strftime('%Y-%m-%d') != date:
                raise ValueError('invalid date')
        except ValueError as exc:
            raise ValueError('invalid workbook date') from exc
        cleaned.append([identity, date, quantity, price, quantity * price])
    extras: dict[str, str] = {}
    if 'Notes' in sheets:
        notes = sheets['Notes']
        if (set(notes) != {'A1'} or not isinstance(notes['A1'][0], str)
                or notes['A1'][1] is not None):
            raise ValueError('unreviewed Notes sheet')
        extras['Notes'] = notes['A1'][0]
    return {'rows': cleaned, 'extras': extras}


def _failure(context: ValidationContext) -> str | None:
    if not isinstance(context.output, dict) or set(context.output) != {'workbook_b64'}:
        return 'output_contract'
    truth = _truth(context.input)
    sheets, bold, _date_styles = _inspect(context.output['workbook_b64'])
    if set(sheets) != {'Data', 'Summary', *truth['extras']}:
        return 'sheet_set'
    data = sheets['Data']
    expected_addresses = {f'{col}{row}' for row in range(1, len(truth['rows']) + 2) for col in 'ABCDE'}
    if set(data) != expected_addresses:
        return 'data_extent'
    for col, header in zip('ABCDE', ('ID', 'Date', 'Quantity', 'Price', 'Amount'), strict=True):
        cell = data.get(col + '1')
        if cell is None or cell[0] != header or cell[2] not in bold:
            return 'header_format'
    expected_formulas = {f'E{row}': f'C{row}*D{row}' for row in range(2, len(truth['rows']) + 2)}
    if {address: cell[1] for address, cell in data.items() if cell[1] is not None} != expected_formulas:
        return 'row_formula'
    total = 0
    for row, expected in enumerate(truth['rows'], 2):
        for col, correct in zip('ABCDE', expected, strict=True):
            cell = data.get(f'{col}{row}')
            if cell is None or cell[0] != correct:
                return 'formula_cache' if col == 'E' else 'cell_value'
        formula = data[f'E{row}'][1]
        if formula != f'C{row}*D{row}':
            return 'row_formula'
        total += expected[4]
    summary = sheets['Summary']
    if (set(summary) != {'A1', 'B1'} or summary.get('A1', (None, None, 0))[1] is not None
            or summary.get('A1', (None, None, 0))[0] != 'Total'
            or summary.get('B1', (None, None, 0))[0] != total
            or summary.get('B1', (None, None, 0))[1] != f'SUM(Data!E2:E{len(truth["rows"])+1})'):
        return 'summary'
    if any({address: cell[:2] for address, cell in sheets[name].items()} != {'A1': (text, None)}
           for name, text in truth['extras'].items()):
        return 'preserved_sheets'
    return None


def validate(context: ValidationContext) -> ValidationResult:
    """Use only code-reviewed input/output semantics; never an agent-supplied expected value."""
    try:
        code = _failure(context)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, ArithmeticError,
            InvalidOperation,
            RuntimeError, NotImplementedError, UnicodeError, ET.ParseError, zipfile.BadZipFile):
        code = 'invalid_workbook'
    return ValidationResult(kind=ValidationKind.CALLBACK, valid=code is None,
        quality_score=1.0 if code is None else 0.0, detail=code or '', trust=TrustLevel.VERIFIED)
