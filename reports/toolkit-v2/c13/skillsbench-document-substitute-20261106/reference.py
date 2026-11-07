"""Create an independent OOXML reference for the pinned workbook update."""

import argparse
import io
import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from zipfile import ZipFile

EMBEDDING = 'ppt/embeddings/Microsoft_Excel_Worksheet.xlsx'
SHEET = 'xl/worksheets/sheet1.xml'


def replace_member(source, member, replacement):
    target = io.BytesIO()
    with ZipFile(source) as original, ZipFile(target, 'w') as output:
        assert original.namelist().count(member) == 1
        for info in original.infolist():
            output.writestr(info, replacement if info.filename == member else original.read(info))
    return target.getvalue()


def value_at(xml, address, number):
    pattern = rb'(<c r="' + address.encode() + rb'"[^>]*>(?:<f>[^<]+</f>)?<v>)([^<]+)(</v></c>)'
    updated, count = re.subn(pattern, lambda m: m[1] + str(number).encode() + m[3], xml)
    assert count == 1
    return updated


def reference(data):
    with ZipFile(io.BytesIO(data)) as source:
        slide = source.read('ppt/slides/slide1.xml')
        rate, = re.findall(rb'<a:t>USD to CNY=([0-9.]+)</a:t>', slide)
        rate = Decimal(rate.decode())
        inverse = (1 / rate).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
        workbook = source.read(EMBEDDING)
    with ZipFile(io.BytesIO(workbook)) as source:
        original = source.read(SHEET)
    assert b'<f>ROUND(1/B3, 3)</f>' in original
    updated = value_at(value_at(original, 'B3', rate), 'C2', inverse)
    updated_workbook = replace_member(io.BytesIO(workbook), SHEET, updated)
    return replace_member(io.BytesIO(data), EMBEDDING, updated_workbook)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    with args.output.open('xb') as stream:
        stream.write(reference(args.source.read_bytes()))
