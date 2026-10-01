"""Independent bounded OOXML grader; supports only the recipe's product/SUM formulas."""
import base64
import io
import json
import posixpath
import sys
import zipfile
from decimal import Decimal
from xml.etree import ElementTree as ET

N = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'


def inspect(encoded):
    if not isinstance(encoded, str) or len(encoded) > 200000:
        raise ValueError('oversized workbook')
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(encoded, validate=True))) as archive:
        entries = archive.infolist()
        if (len(entries) > 100 or len({item.filename for item in entries}) != len(entries)
                or sum(item.file_size for item in entries) > 2000000
                or any('..' in item.filename.split('/') or item.filename.startswith('/')
                       or 'vba' in item.filename.lower() or 'externallink' in item.filename.lower() for item in entries)):
            raise ValueError('unsupported workbook archive')
        def xml(name):
            value = archive.read(name)
            if b'<!DOCTYPE' in value or b'<!ENTITY' in value:
                raise ValueError('XML declarations denied')
            return ET.fromstring(value)
        links = xml('xl/_rels/workbook.xml.rels')
        if any(item.get('TargetMode') == 'External' for item in links):
            raise ValueError('external relationships denied')
        targets = {item.get('Id'): posixpath.normpath(posixpath.join('xl', item.get('Target', '').lstrip('/')))
                   if not item.get('Target', '').startswith('/') else item.get('Target').lstrip('/') for item in links}
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(item.itertext()) for item in xml('xl/sharedStrings.xml').findall(N+'si')]
        sheets = {}
        for sheet in xml('xl/workbook.xml').find(N+'sheets'):
            cells = {}
            for cell in xml(targets[sheet.get(R+'id')]).iter(N+'c'):
                address = cell.get('r')
                if address in cells:
                    raise ValueError('duplicate cell')
                value, formula = cell.findtext(N+'v'), cell.findtext(N+'f')
                if cell.get('t') == 'inlineStr':
                    value = ''.join(cell.find(N+'is').itertext())
                elif cell.get('t') == 's':
                    value = strings[int(value)]
                elif cell.get('t') == 'str':
                    pass  # OOXML string values are text, including numeric-looking IDs.
                elif cell.get('t') not in (None, 'n'):
                    raise ValueError('unsupported cell type')
                elif value is not None:
                    value = Decimal(value)
                cells[address] = (value, formula, int(cell.get('s', '0')))
            if sheet.get('name') in sheets:
                raise ValueError('duplicate sheet')
            sheets[sheet.get('name')] = cells
        styles = xml('xl/styles.xml')
        fonts = list(styles.find(N+'fonts'))
        bold = {index for index, style in enumerate(styles.find(N+'cellXfs'))
                if fonts[int(style.get('fontId', '0'))].find(N+'b') is not None
                and fonts[int(style.get('fontId', '0'))].find(N+'b').get('val', '1') not in {'0', 'false'}}
        return sheets, bold


def failure_code(example):
    try:
        if not isinstance(example['output'], dict) or set(example['output']) != {'workbook_b64'}:
            return 'output_contract'
        sheets, bold = inspect(example['output']['workbook_b64'])
        truth = example['expected']
        if set(sheets) != {'Data', 'Summary', *truth['extras']}:
            return 'sheet_set'
        data = sheets['Data']
        expected_addresses = {f'{col}{row}' for row in range(1, len(truth['rows'])+2) for col in 'ABCDE'}
        if {key for key, item in data.items() if item[0] is not None or item[1] is not None} != expected_addresses:
            return 'data_extent'
        for col, header in zip('ABCDE', ['ID', 'Date', 'Quantity', 'Price', 'Amount'], strict=True):
            if data[col+'1'][0] != header or data[col+'1'][2] not in bold:
                return 'header_format'
        recomputed = Decimal(0)
        for index, expected in enumerate(truth['rows'], 2):
            for col, value in zip('ABCDE', expected, strict=True):
                if data[f'{col}{index}'][0] != value:
                    return 'formula_cache' if col == 'E' else 'cell_value'
            # No eval: the reviewed formula grammar is exactly these references.
            if data[f'E{index}'][1] != f'C{index}*D{index}':
                return 'row_formula'
            product = data[f'C{index}'][0] * data[f'D{index}'][0]
            if data[f'E{index}'][0] != product:
                return 'formula_cache'
            recomputed += product
        summary = sheets['Summary']
        if (summary['A1'][0] != 'Total' or summary['B1'][0] != recomputed
                or summary['B1'][1] != f'SUM(Data!E2:E{len(truth["rows"])+1})'):
            return 'summary'
        return None if all({key: cell[:2] for key, cell in sheets[name].items()} == {'A1': (value, None)} for name, value in truth['extras'].items()) else 'preserved_sheets'
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, ArithmeticError, RuntimeError, NotImplementedError, ET.ParseError, zipfile.BadZipFile):
        return 'invalid_workbook'


def grade(example):
    return failure_code(example) is None


if __name__ == '__main__':
    payload = json.load(sys.stdin)
    codes = [failure_code(example) for example in payload['examples']]
    result = {'valid': [code is None for code in codes]}
    if sys.argv[1:] == ['diagnose']:
        result['failure_codes'] = codes
    print(json.dumps(result))
