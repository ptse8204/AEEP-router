"""Capture the exact upstream pytest result and independent native statuses."""
import contextlib
import hashlib
import io
import json
import os
import sys
from pathlib import Path

sys.path[:0] = ['/aeep/tools', '/aeep/native']
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'

import pytest
from repository_suite_native_capture import NativeCapture

capture = NativeCapture()
ctrf = Path('/tmp/ctrf.json')
output = io.StringIO()
with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
    code = int(pytest.main([
        '-p', 'ctrf.main', '-p', 'no:cacheprovider',
        '--rootdir=/aeep', '--ctrf', str(ctrf), '/aeep/test_outputs.py', '-rA', '-v',
    ], plugins=[capture]))
data = ctrf.read_bytes()
assert len(data) <= 512 * 1024
document = json.loads(data)
print(json.dumps({
    'pytest_exit_code': code, 'upstream_binary_reward': int(code == 0),
    'native': capture.export(), 'selected_ids': capture.selected_ids,
    'ctrf_sha256': hashlib.sha256(data).hexdigest(),
    'ctrf_summary': document['results']['summary'],
    'stdout_sha256': hashlib.sha256(output.getvalue().encode()).hexdigest(),
}))
