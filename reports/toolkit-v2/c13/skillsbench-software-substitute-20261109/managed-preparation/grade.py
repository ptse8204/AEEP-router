"""Grade the Prefix Cache artifact with the pinned upstream tests."""

import base64
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRATCH = Path('/tmp/aeep-prefix')


def read_binding():
    return json.loads((ROOT / 'binding.json').read_bytes())


def reply(valid, failure=None):
    return {'valid': [valid], 'failure_codes': [failure]}


def check_input(value, binding):
    archive = value['task_archive_b64']
    if (value['task_id'] != binding['task_id'] or len(archive) > 400_000
            or hashlib.sha256(base64.b64decode(archive, validate=True)).hexdigest() != binding['archive_sha256']):
        raise ValueError('protected grader input binding changed')


def decode_report(output, binding):
    field = binding['output_field']
    if not isinstance(output, dict) or set(output) != {field} or not isinstance(output[field], str):
        return None
    limit = binding['max_output_bytes']
    if len(output[field]) > 4 * ((limit + 2) // 3):
        return None
    try:
        raw = base64.b64decode(output[field], validate=True)
        if 0 < len(raw) <= limit and isinstance(json.loads(raw), dict):
            return raw
    except ValueError:
        pass
    return None


def stage_inputs():
    if os.getuid() != 65534:
        raise ValueError('unexpected protected grader uid')
    SCRATCH.mkdir(mode=0o700)
    for name in ('trace.jsonl', 'config.json'):
        shutil.copyfile(ROOT / name, SCRATCH / name)


def reference(request, binding):
    if set(request) != {'inputs'} or len(request['inputs']) != 1:
        raise ValueError('expected one reviewed reference input')
    check_input(request['inputs'][0], binding)
    stage_inputs()
    solved = subprocess.run(['/bin/bash', str(ROOT / 'solve.sh')], cwd=SCRATCH, env={
        'PATH': '/usr/bin:/bin:/usr/local/bin', 'HOME': str(SCRATCH), 'LC_ALL': 'C',
    }, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    report = SCRATCH / 'report.json'
    if solved.returncode or not 0 < report.stat().st_size <= binding['max_output_bytes']:
        raise ValueError('protected solver failed')
    encoded = base64.b64encode(report.read_bytes()).decode('ascii')
    return {'outputs': [{binding['output_field']: encoded}]}


def classify(exit_code, selected, statuses, identities):
    if sorted(selected) != identities or sorted(statuses) != identities:
        raise ValueError('protected verifier collection changed')
    if set(statuses.values()) - {'PASSED', 'FAILED'}:
        raise ValueError('protected verifier infrastructure failure')
    failed = 'FAILED' in statuses.values()
    if exit_code != int(failed):
        raise ValueError('protected verifier exit disagrees with assertions')
    return reply(not failed, 'upstream_rejected' if failed else None)


def grade(request, binding):
    if set(request) != {'examples'} or len(request['examples']) != 1:
        raise ValueError('expected one protected example')
    example, = request['examples']
    check_input(example['input'], binding)
    if example['expected'] != {'task_archive_sha256': binding['archive_sha256']}:
        raise ValueError('protected grader truth binding changed')
    raw = decode_report(example['output'], binding)
    if raw is None:
        return reply(False, 'output_contract')

    stage_inputs()
    (SCRATCH / 'report.json').write_bytes(raw)
    os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
    sys.path[:0] = [str(ROOT), *sorted(str(path) for path in (ROOT / 'wheels').glob('*.whl'))]
    import pytest
    from repository_suite_native_capture import NativeCapture

    if pytest.__version__ != '8.4.1' or str(ROOT / 'wheels') not in pytest.__file__:
        raise ValueError('protected Pytest binding changed')
    capture = NativeCapture()
    with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        code = int(pytest.main(['-p', 'no:cacheprovider', '--rootdir=' + str(ROOT),
                                str(ROOT / 'test_outputs.py'), '-q'], plugins=[capture]))
    return classify(code, capture.selected_ids, capture.export()['statuses'], binding['test_identities'])


if __name__ == '__main__':
    action, = sys.argv[1:]
    request = json.loads(sys.stdin.buffer.read(1_000_001))
    entry = {'reference': reference, 'grade': grade}[action]
    print(json.dumps(entry(request, read_binding())))
