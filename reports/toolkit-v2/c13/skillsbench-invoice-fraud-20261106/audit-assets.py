"""Confirm exact source and fixture patterns without retaining input contents."""

import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
SOURCE = json.loads((HERE / 'source-inventory.json').read_bytes())
PRIVATE = Path(SOURCE['private_root'])
LICENSE_URL = SOURCE['files']['LICENSE']['source_url']
CONTRIBUTION = 'https://github.com/benchflow-ai/skillsbench/pull/105'


def verify_sources():
    for name, info in SOURCE['files'].items():
        path = PRIVATE / info['role'] / Path(name).name
        raw = path.read_bytes()
        assert len(raw) == info['bytes']
        assert hashlib.sha256(raw).hexdigest() == info['sha256']


def review_pdf(path):
    extractor = Path('/usr/local/bin/pdftotext').resolve(strict=True)
    text = subprocess.check_output([str(extractor), '-layout', str(path), '-'],
                                   text=True, timeout=10)
    names = re.findall(r'From:[ \t]+([^\n]+)', text)
    accounts = re.findall(r'Payment IBAN:[ \t]+([^\n]+)', text)
    assert len(names) == len(accounts) == 53
    assert all(re.fullmatch(r'Vendor \d+|Fraudulent Corp|Safe Vendor Ltd|'
                            r'Fuzzy Match Systems Inc\.|Boundary Corp', v.strip()) for v in names)
    assert all(re.fullmatch(r'IBAN\d{9}|FRADULENT_IBAN|IBAN(?:SAFE|FUZZ|BOUND)\d{3}', v.strip())
               for v in accounts)
    return {'invoice_records': len(names), 'extractor_sha256': hashlib.sha256(extractor.read_bytes()).hexdigest()}


def review_workbook(path):
    with ZipFile(path) as archive:
        name = 'xl/worksheets/sheet1.xml'
        assert archive.getinfo(name).file_size <= 250_000
        worksheet = ElementTree.fromstring(archive.read(name))
    records = [[cell.text for cell in row.findall('.//{*}t')] for row in worksheet.findall('.//{*}row')]
    header, *vendors = records
    assert header == ['id', 'name', 'iban'] and len(vendors) == 503
    assert all(re.fullmatch(r'V\d{3}|V_NF\d', vendor_id)
               and re.fullmatch(r'Vendor \d+|Safe Vendor Ltd|Fuzzy Match Systems|Boundary Corp', name)
               and re.fullmatch(r'IBAN\d{9}|IBAN(?:SAFE|FUZZ|BOUND)\d{3}', iban)
               for vendor_id, name, iban in vendors)
    return {'vendor_records': len(vendors)}


def review_csv(path):
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == ['po_number', 'vendor_id', 'amount']
        rows = list(reader)
    assert len(rows) == 2503
    assert all(re.fullmatch(r'PO-\d{4}', row['po_number'])
               and re.fullmatch(r'V\d{3}|V_NF\d', row['vendor_id'])
               and re.fullmatch(r'\d+\.\d{1,2}', row['amount']) for row in rows)
    return {'purchase_order_records': len(rows)}


verify_sources()
report = {
    'task_id': SOURCE['task_id'], 'revision': SOURCE['revision'],
    'contribution': CONTRIBUTION, 'repository_notice': LICENSE_URL,
    'notice': 'Apache-2.0', 'verified_source_files': len(SOURCE['files']),
    **review_pdf(PRIVATE / 'public/invoices.pdf'),
    **review_workbook(PRIVATE / 'public/vendors.xlsx'),
    **review_csv(PRIVATE / 'public/purchase_orders.csv'),
    'local_engineering_use': 'CLEARED_FOR_PINNED_CONTRIBUTION_FILES',
    'basis': 'Direct upstream contribution with a retained repository notice. '
             'The contributor describes adding deliberately clean cases and correcting placeholder account fields. '
             'All reviewed vendor and account fields match fixture patterns.',
    'provider_disclosure': 'SEPARATE_AUTHORITY_REQUIRED',
    'excluded': ['bundled skills', 'publication', 'redistribution', 'provider disclosure'],
    'oracle_or_verifier_executed': False,
}
with (HERE / 'asset-use.json').open('x') as stream:
    stream.write(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
