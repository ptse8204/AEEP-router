"""Run one pinned upstream verifier under AEEP's ordinary contained command contract."""

import base64
import binascii
import contextlib
import hashlib
import io
import json
import os
import stat
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def classify(exit_code, selected, statuses, identities, skips):
    if selected != identities or set(statuses) != set(identities):
        raise ValueError('upstream verifier collected unexpected tests')
    if {node for node, status in statuses.items() if status == 'SKIPPED'} != set(skips):
        raise ValueError('upstream verifier changed the reviewed skip set')
    if set(statuses.values()) - {'PASSED', 'FAILED', 'SKIPPED'}:
        raise ValueError('upstream verifier infrastructure failure')
    failed = any(status == 'FAILED' for status in statuses.values())
    if exit_code != int(failed):
        raise ValueError('upstream verifier returned an inconsistent exit code')
    return not failed


def reply(valid, code=None):
    return {'valid': [valid], 'failure_codes': [code]}


def workspace(raw, destination, members):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        if (len(entries) != len(members) or {entry.filename for entry in entries} != set(members)
                or sum(entry.file_size for entry in entries) > 2_000_000):
            return False
        for entry in entries:
            kind = stat.S_IFMT(entry.external_attr >> 16)
            if entry.is_dir() or kind not in (0, stat.S_IFREG) or entry.flag_bits & 1:
                return False
            name = Path(entry.filename)
            if name.is_absolute() or '..' in name.parts or str(name) != entry.filename:
                return False
        for entry in entries:
            path = destination / entry.filename
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(archive.read(entry))
    return True


def workbook(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        names = {entry.filename for entry in entries}
        return (len(entries) == len(names) <= 256
                and {'[Content_Types].xml', 'xl/workbook.xml'} <= names
                and sum(entry.file_size for entry in entries) <= 16_000_000
                and not any(entry.flag_bits & 1 for entry in entries))


def grade(request, config):
    if not isinstance(request, dict) or set(request) != {'examples'} or len(request['examples']) != 1:
        raise ValueError('protected grader requires one reviewed case')
    example = request['examples'][0]
    value = example['input']
    archive = value['task_archive_b64']
    if (value['task_id'] != config['task_id'] or len(archive) > 400_000
            or hashlib.sha256(base64.b64decode(archive, validate=True)).hexdigest() != config['archive_sha256']
            or example['expected'] != {'task_archive_sha256': config['archive_sha256']}):
        raise ValueError('protected grader input binding changed')
    output, field = example['output'], config['output_field']
    if not isinstance(output, dict) or set(output) != {field} or not isinstance(output[field], str):
        return reply(False, 'output_contract')
    limit = config['max_output_bytes']
    if len(output[field]) > 4 * ((limit + 2) // 3):
        return reply(False, 'output_contract')
    try:
        raw = base64.b64decode(output[field], validate=True)
    except (binascii.Error, ValueError):
        return reply(False, 'output_contract')
    if not 0 < len(raw) <= limit:
        return reply(False, 'output_contract')

    scratch = Path(config['scratch'])
    scratch.mkdir(mode=0o700)
    try:
        if field == 'workbook_b64':
            if not workbook(raw):
                return reply(False, 'output_contract')
            for name in ('income.xlsx', 'population.pdf'):
                (scratch/name).write_bytes((ROOT/'inputs'/name).read_bytes())
            (scratch/'demographic_analysis.xlsx').write_bytes(raw)
        elif not workspace(raw, scratch/'workspace', config['workspace_members']):
            return reply(False, 'output_contract')
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError):
        return reply(False, 'output_contract')

    os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
    if field == 'workspace_b64':
        os.environ.update(
            HOME=str(scratch), JAVA_HOME=str(ROOT/'java'),
            MAVEN_OPTS='-Xmx512m -XX:ActiveProcessorCount=1',
        )
    sys.path[:0] = [str(ROOT/'tools'), str(ROOT)]
    import pytest
    from repository_suite_native_capture import NativeCapture

    capture = NativeCapture()
    with open(os.devnull, 'w', encoding='utf-8') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        code = int(pytest.main(
            ['-p', 'no:cacheprovider', '--rootdir='+str(ROOT), str(ROOT/'test_outputs.py'), '-q'],
            plugins=[capture],
        ))
    valid = classify(code, capture.selected_ids, capture.export()['statuses'],
                     config['collected_test_identities'], config['intentional_skips'])
    return reply(valid, None if valid else 'upstream_rejected')


if __name__ == '__main__':
    request = json.loads(sys.stdin.buffer.read(1_000_001))
    print(json.dumps(grade(request, json.loads((ROOT/'binding.json').read_bytes()))))
