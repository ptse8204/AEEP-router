"""Grade one Invoice Fraud artifact with the pinned protected upstream verifier."""

import base64
import binascii
import contextlib
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def reply(valid, failure=None):
    return {'valid': [valid], 'failure_codes': [failure]}


def grade(request, binding):
    if set(request) != {'examples'} or len(request['examples']) != 1:
        raise ValueError('expected one protected example')
    example, = request['examples']
    value = example['input']
    archive = value['task_archive_b64']
    digest = binding['archive_sha256']
    if (value['task_id'] != binding['task_id'] or len(archive) > 400000
            or hashlib.sha256(base64.b64decode(archive, validate=True)).hexdigest() != digest
            or example['expected'] != {'task_archive_sha256': digest}):
        raise ValueError('task input binding changed')
    ground_truth = ROOT / 'ground_truth.json'
    if hashlib.sha256(ground_truth.read_bytes()).hexdigest() != binding['ground_truth_sha256']:
        raise ValueError('protected answer binding changed')
    field = binding['output_field']
    output = example['output']
    if not isinstance(output, dict) or set(output) != {field} or not isinstance(output[field], str):
        return reply(False, 'output_contract')
    if len(output[field]) > 4 * ((binding['max_output_bytes']+2)//3):
        return reply(False, 'output_contract')
    try:
        raw = base64.b64decode(output[field], validate=True)
        if not 0 < len(raw) <= binding['max_output_bytes']:
            return reply(False, 'output_contract')
        if not isinstance(json.loads(raw), list):
            return reply(False, 'output_contract')
    except (binascii.Error, ValueError, UnicodeError):
        return reply(False, 'output_contract')
    scratch = Path('/tmp/aeep-invoice')
    scratch.mkdir(mode=0o700)
    (scratch / 'fraud_report.json').write_bytes(raw)
    os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
    sys.path[:0] = [str(ROOT), str(ROOT / 'native'), *sorted(str(p) for p in (ROOT / 'wheels').glob('*.whl'))]
    import pytest
    import rapidfuzz
    from repository_suite_native_capture import NativeCapture

    assert rapidfuzz.__version__ == '3.14.3' and str(ROOT / 'native') in rapidfuzz.__file__
    assert pytest.__version__ == '8.4.1'
    capture = NativeCapture()
    with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        code = int(pytest.main(['-p', 'no:cacheprovider', '--rootdir='+str(ROOT),
                               str(ROOT/'test_outputs.py'), '-q'], plugins=[capture]))
    statuses = capture.export()['statuses']
    if capture.selected_ids != binding['collected_test_identities'] or set(statuses) != set(binding['collected_test_identities']):
        raise ValueError('protected verifier collection changed')
    if set(statuses.values()) - {'PASSED', 'FAILED'}:
        raise ValueError('protected verifier infrastructure failure')
    failed = 'FAILED' in statuses.values()
    if code != int(failed):
        raise ValueError('protected verifier exit disagrees with assertions')
    return reply(not failed, 'upstream_rejected' if failed else None)


if __name__ == '__main__':
    request = json.loads(sys.stdin.buffer.read(1000001))
    print(json.dumps(grade(request, json.loads((ROOT/'binding.json').read_bytes()))))
