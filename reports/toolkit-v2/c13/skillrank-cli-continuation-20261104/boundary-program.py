"""Return explicit containment observations, including filesystem denial errno."""
import errno
import hashlib
import json
import os
import socket
import subprocess
import sys
from pathlib import Path


def check(request):
    checks = {}
    diagnostics = {}
    checks['binary_hash_verified'] = hashlib.sha256(Path('/opt/aeep-skillrank').read_bytes()).hexdigest() == request['binary_sha256']
    positive = Path('/tmp/aeep-catalog-positive')
    positive.write_text('owned check')
    checks['owned_tmp_read_write'] = positive.read_text() == 'owned check'
    checks['host_canary_absent'] = not Path(request['host_canary']).exists()
    checks['docker_socket_absent'] = not Path(request['docker_socket']).exists()
    checks['credential_environment_absent'] = not any(name in os.environ for name in (
        'CODEX_HOME', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GH_TOKEN', 'GITHUB_TOKEN'))
    try:
        Path('/etc/aeep-catalog-forbidden-write').write_text('must be denied')
    except OSError as error:
        diagnostics['root_write_errno'] = error.errno
        checks['root_write_denied'] = error.errno in {errno.EACCES, errno.EPERM, errno.EROFS}
    else:
        checks['root_write_denied'] = False
    try:
        connection = socket.create_connection(('1.1.1.1', 443), timeout=.2)
    except OSError as error:
        diagnostics['network_error_type'] = type(error).__name__
        diagnostics['network_errno'] = error.errno
        diagnostics['network_observation'] = ('permission_denied' if error.errno in {errno.EACCES, errno.EPERM}
            else 'namespace_has_no_route' if error.errno == errno.ENETUNREACH else 'unverified_failure')
        checks['external_network_boundary'] = error.errno in {errno.EACCES, errno.EPERM, errno.ENETUNREACH}
    else:
        connection.close()
        checks['external_network_boundary'] = False
    version = subprocess.run(['/opt/aeep-skillrank', '--version'], env={'PATH':'/usr/bin:/bin','HOME':'/tmp'},
        stdin=subprocess.DEVNULL, capture_output=True, timeout=5)
    checks['upstream_cli_version'] = version.returncode == 0 and version.stdout.strip() == b'skillrank 0.1.5'
    diagnostics['version_exit_code'] = version.returncode
    if not checks['upstream_cli_version']:
        diagnostics['version_stderr'] = version.stderr[:1024].decode('utf-8', errors='replace')
    return {'passed': all(checks.values()), 'checks': checks, 'diagnostics': diagnostics}


def main():
    try:
        result = check(json.load(sys.stdin))
    except BaseException as error:
        result = {'passed': False, 'failure_category': type(error).__name__}
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
