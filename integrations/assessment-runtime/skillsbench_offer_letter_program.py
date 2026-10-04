"""Contained stdlib generator/reference for the AEEP SkillsBench adaptation.

The exporter prefixes the pinned ASSETS, VARIATIONS and TASK constants. This
file is read as source, never imported by the assessment coordinator.
"""
import base64
import datetime
import hashlib
import io
import json
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

# These names are supplied by the exporter's frozen prefix, never by task input.
ASSETS: dict = globals()['ASSETS']
VARIATIONS: list[str] = globals()['VARIATIONS']
TASK: str = globals()['TASK']
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def truth(value):
    return {'input_sha256': hashlib.sha256(json.dumps(value, sort_keys=True,
        ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()}


def generate(payload):
    stages = [{'split': 'qualification', 'count': 8}, {'split': 'training', 'count': 28},
              {'split': 'holdout', 'count': 105}]
    if (set(payload) != {'seed', 'stages', 'variations'} or type(payload['seed']) is not int
            or not 0 <= payload['seed'] < 2**63 or payload['stages'] != stages
            or payload['variations'] != VARIATIONS):
        raise ValueError('unsupported offer-letter generation contract')
    cases = []
    for stage in stages:
        for index in range(stage['count']):
            variation = VARIATIONS[index % len(VARIATIONS)]
            key = f"{payload['seed']}:{stage['split']}:{index}"
            number = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], 'big')
            data = dict(ASSETS['employee_data'])
            data.update(DOC_ID='AEEP-' + key, CANDIDATE_FULL_NAME=f'Candidate {number:020d}',
                COMPANY_NAME='Example Research Company', MANAGER_NAME=f'Manager {index}',
                HR_NAME=f'Contact {index}', BASE_SALARY=f'{60000 + number % 180001:,}',
                SIGNING_BONUS=f'{number % 30001:,}', EQUITY_SHARES=f'{number % 10001:,}',
                RELOCATION_AMOUNT=f'{1000 + number % 19001:,}',
                RELOCATION_DAYS=str(14 + number % 47), PTO_DAYS=str(10 + number % 21))
            day = datetime.date(2024, 1, 1) + datetime.timedelta(days=number % 1461)
            data.update(DATE=day.isoformat(), START_DATE=(day + datetime.timedelta(days=30)).isoformat(),
                        RESPONSE_DEADLINE=(day + datetime.timedelta(days=7)).isoformat())
            if variation == 'relocation_no':
                data['RELOCATION_PACKAGE'] = 'No'
            elif variation == 'unicode_names':
                data.update(CANDIDATE_FULL_NAME='Zoë 李 ' + str(number), CITY='Montréal',
                            MANAGER_NAME='André Núñez', DEPARTMENT='研究開発')
            elif variation == 'xml_escaping':
                data.update(COMPANY_NAME='Research & Development <Example>',
                            POSITION='Engineer "A&B"', DEPARTMENT='Tools <Platform>')
            elif variation == 'long_fields':
                data.update(POSITION='Senior Research Engineer, Distributed Systems and Reliability',
                            STREET_ADDRESS='123 Example Avenue, Building 12, Suite 345, North Campus',
                            DEPARTMENT='Infrastructure, Developer Experience and Quality Engineering')
            elif variation == 'numeric_boundaries':
                data.update(SIGNING_BONUS='0', EQUITY_SHARES='0', BASE_SALARY='1,000,000', PTO_DAYS='1')
            elif variation == 'date_boundaries':
                data.update(DATE='2024-02-29', START_DATE='2024-03-01', RESPONSE_DEADLINE='2024-03-07')
            value = {'template_b64': ASSETS['template_b64'], 'employee_data': data,
                     'task': TASK, 'variation': variation}
            cases.append({'input': value, 'output': truth(value), 'variation': variation,
                          'template_family': 'skillsbench-offer-letter:pinned-template'})
    return {'cases': cases}


def reference(value):
    if (value['template_b64'] != ASSETS['template_b64'] or value['task'] != TASK
            or value['variation'] not in VARIATIONS):
        raise ValueError('unsupported offer-letter input')
    data = value['employee_data']
    if (set(data) != set(ASSETS['employee_data']) or data['RELOCATION_PACKAGE'] not in {'Yes', 'No'}
            or any(not isinstance(item, str) or not 1 <= len(item) <= 256
                   or any(ord(char) < 32 for char in item) for item in data.values())):
        raise ValueError('unsupported employee data')
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(value['template_b64']))) as original, \
            zipfile.ZipFile(output, 'w') as filled:
        for member in original.infolist():
            raw = original.read(member)
            if re.fullmatch(r'word/(?:document|header\d+|footer\d+)\.xml', member.filename):
                root = ET.fromstring(raw)
                for paragraph in root.iter(W + 'p'):
                    nodes = list(paragraph.iter(W + 't'))
                    text = ''.join(node.text or '' for node in nodes)
                    edits = []
                    for match in re.finditer(r'\{\{IF_RELOCATION\}\}.*?\{\{END_IF_RELOCATION\}\}', text):
                        if data['RELOCATION_PACKAGE'] == 'No':
                            edits.append((match.start(), match.end(), ''))
                    for match in re.finditer(r'\{\{([A-Z_]+)\}\}', text):
                        if any(start <= match.start() < end for start, end, _ in edits):
                            continue
                        replacement = '' if match.group(1) in {'IF_RELOCATION', 'END_IF_RELOCATION'} else data[match.group(1)]
                        edits.append((match.start(), match.end(), replacement))
                    # Reverse edits leave earlier offsets intact, including split-run tokens.
                    for start, end, replacement in sorted(edits, reverse=True):
                        offset = 0
                        inserted = False
                        for node in nodes:
                            current = node.text or ''
                            stop = offset + len(current)
                            if offset < end and stop > start:
                                left, right = max(0, start-offset), min(len(current), end-offset)
                                node.text = current[:left] + (replacement if not inserted else '') + current[right:]
                                inserted = True
                            offset = stop
                    for node in nodes:
                        if node.text and (node.text[0].isspace() or node.text[-1].isspace()):
                            node.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
                raw = ET.tostring(root, encoding='utf-8', xml_declaration=True)
            filled.writestr(member, raw)
    return {'document_b64': base64.b64encode(output.getvalue()).decode('ascii')}


if __name__ == '__main__':
    raw = sys.stdin.buffer.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError('offer-letter request too large')
    payload = json.loads(raw)
    if sys.argv[1:] == ['generate']:
        result = generate(payload)
    elif sys.argv[1:] == ['reference'] and set(payload) == {'inputs'} and isinstance(payload['inputs'], list) and len(payload['inputs']) <= 141:
        result = {'outputs': [reference(value) for value in payload['inputs']]}
    else:
        raise ValueError('unsupported offer-letter operation')
    print(json.dumps(result, ensure_ascii=False))
