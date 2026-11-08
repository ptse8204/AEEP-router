"""Check the public React project without starting Codex or the protected grader."""

import base64
import hashlib
import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

assert os.getuid() == os.getgid() == 65534
assert not Path('/var/run/docker.sock').exists()
assert not any(Path(path).exists() for path in (
    '/app', '/tests', '/solution', '/services/api-simulator', '/opt/aeep-react-reference',
))
assert not os.access('/opt/aeep-task-tools/react', os.W_OK)
assert Path('/proc/net/route').read_text().splitlines()[1:] == []
incoming = json.load(sys.stdin)
data = base64.b64decode(incoming['archive'], validate=True)
assert hashlib.sha256(data).hexdigest() == incoming['archive_sha256']
project = Path('/tmp/react-website')
prefix = 'tasks/react-performance-debugging/environment/website/'
with zipfile.ZipFile(io.BytesIO(data)) as archive:
    assert len(archive.namelist()) == len(set(archive.namelist())) == len(incoming['files'])
    assert set(archive.namelist()) == set(incoming['files'])
    for name, expected in incoming['files'].items():
        content = archive.read(name)
        assert hashlib.sha256(content).hexdigest() == expected
        if name.startswith(prefix):
            relative = Path(name.removeprefix(prefix))
            assert not relative.is_absolute() and '..' not in relative.parts
            target = project / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
tools = Path('/opt/aeep-task-tools/react/node_modules')
(project / 'node_modules').symlink_to(tools)
next_cli = tools / 'next/dist/bin/next'
compiler = tools / '@next/swc-linux-arm64-gnu'
env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/tmp', 'TMPDIR': '/tmp',
       'NEXT_TELEMETRY_DISABLED': '1', 'CI': '1', 'UV_THREADPOOL_SIZE': '2'}
subprocess.run(['node', '-e', 'require(process.argv[1])', str(compiler)],
               check=True, cwd=project, env=env, capture_output=True, timeout=15)
version = subprocess.check_output(['node', str(next_cli), '--version'],
                                  cwd=project, env=env, text=True, timeout=15).strip()
assert version == 'Next.js v14.2.0'
try:
    check = subprocess.run(['node', str(tools / 'typescript/bin/tsc'), '--noEmit', '--incremental', 'false'],
                           cwd=project, env=env, capture_output=True, timeout=35)
    result = {'typecheck_exit': check.returncode, 'typecheck_error_codes': sorted({
        int(token[2:-1]) for token in (check.stdout + check.stderr).decode(errors='replace').split()
        if token.startswith('TS') and token.endswith(':') and token[2:-1].isdigit()
    })}
except subprocess.TimeoutExpired:
    result = {'typecheck_exit': None, 'typecheck_timeout': True}
print(json.dumps(result | {'next_version': version, 'native_compiler_loaded': True,
                          'private_public_project': True, 'protected_paths_absent': True,
                          'read_only_tools': True, 'network_denied': True}))
