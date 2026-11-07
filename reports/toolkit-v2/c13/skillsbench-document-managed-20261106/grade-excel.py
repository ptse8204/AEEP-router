"""Grade one reviewed Excel-in-PowerPoint submission through the upstream tests."""

import base64
import binascii
import contextlib
import hashlib
import io
import json
import os
import stat
import sys
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parent
EMBEDDING = 'ppt/embeddings/Microsoft_Excel_Worksheet.xlsx'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inspect_parts(archive, required):
    entries = archive.infolist()
    names = {entry.filename for entry in entries}
    if (len(entries) != len(names) or len(entries) > 256 or not required <= names
            or sum(entry.file_size for entry in entries) > 8_000_000):
        return False
    for entry in entries:
        name = PurePosixPath(entry.filename)
        if (name.is_absolute() or '..' in name.parts or str(name) != entry.filename
                or entry.flag_bits & 1 or entry.is_dir()
                or stat.S_IFMT(entry.external_attr >> 16) not in (0, stat.S_IFREG)):
            return False
        if entry.filename.endswith('vbaProject.bin') or '/externalLinks/' in entry.filename:
            return False
        if entry.filename.endswith(('.xml', '.rels')):
            xml = archive.read(entry)
            if b'<!DOCTYPE' in xml.upper() or b'TargetMode="External"' in xml:
                return False
    return True


def document(raw):
    with ZipFile(io.BytesIO(raw)) as deck:
        if not inspect_parts(deck, {EMBEDDING, '[Content_Types].xml', 'ppt/presentation.xml'}):
            return False
        with ZipFile(io.BytesIO(deck.read(EMBEDDING))) as workbook:
            return inspect_parts(workbook, {'[Content_Types].xml', 'xl/workbook.xml'})


def reply(valid, failure=None):
    return {'valid': [valid], 'failure_codes': [failure]}


def grade(request, binding):
    if set(request) != {'examples'} or len(request['examples']) != 1:
        raise ValueError('expected one protected example')
    example, = request['examples']
    value = example['input']
    archive = value['task_archive_b64']
    digest = binding['archive_sha256']
    if (value['task_id'] != binding['task_id'] or len(archive) > 400_000
            or sha(base64.b64decode(archive, validate=True)) != digest
            or example['expected'] != {'task_archive_sha256': digest}):
        raise ValueError('task input binding changed')
    output = example['output']
    field = binding['output_field']
    if not isinstance(output, dict) or set(output) != {field} or not isinstance(output[field], str):
        return reply(False, 'output_contract')
    limit = binding['max_output_bytes']
    if len(output[field]) > 4 * ((limit + 2) // 3):
        return reply(False, 'output_contract')
    try:
        raw = base64.b64decode(output[field], validate=True)
        if not 0 < len(raw) <= limit or not document(raw):
            return reply(False, 'output_contract')
    except (BadZipFile, binascii.Error, ValueError, NotImplementedError, RuntimeError):
        return reply(False, 'output_contract')
    source = (ROOT / 'input.pptx').read_bytes()
    if sha(source) != binding['protected_input_sha256']:
        raise ValueError('protected input binding changed')
    scratch = Path('/tmp/aeep-excel')
    scratch.mkdir(mode=0o700)
    (scratch / 'input.pptx').write_bytes(source)
    (scratch / 'results.pptx').write_bytes(raw)
    os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
    sys.path[:0] = [str(ROOT), *sorted(str(p) for p in (ROOT / 'wheels').glob('*.whl')), '/opt/aflow-dependencies']
    import openpyxl
    import pandas
    import pytest
    from repository_suite_native_capture import NativeCapture

    assert (pandas.__version__, openpyxl.__version__, pytest.__version__) == ('2.2.3', '3.1.5', '8.4.1')
    capture = NativeCapture()
    with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        code = int(pytest.main(['-p', 'no:cacheprovider', '--rootdir='+str(ROOT),
                               str(ROOT/'test_outputs.py'), '-q'], plugins=[capture]))
    identities = binding['collected_test_identities']
    statuses = capture.export()['statuses']
    if capture.selected_ids != identities or set(statuses) != set(identities):
        raise ValueError('unexpected protected verifier collection')
    if set(statuses.values()) - {'PASSED', 'FAILED'}:
        raise ValueError('protected verifier infrastructure failure')
    failed = 'FAILED' in statuses.values()
    if code != int(failed):
        raise ValueError('protected verifier exit disagrees with recorded assertions')
    return reply(not failed, 'upstream_rejected' if failed else None)


if __name__ == '__main__':
    request = json.loads(sys.stdin.buffer.read(1_000_001))
    print(json.dumps(grade(request, json.loads((ROOT / 'binding.json').read_bytes()))))
