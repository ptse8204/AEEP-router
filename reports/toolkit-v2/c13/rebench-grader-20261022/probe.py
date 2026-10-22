"""Reviewed offline development probe; run only inside the approved container."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import socket
import subprocess
import sys
import tarfile
import tempfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def unpack(data, root):
    """Treat archive names and sizes as untrusted even in a disposable worker."""
    total, seen = 0, set()
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        for member in archive.getmembers():
            name = PurePosixPath(member.name)
            if (not member.isfile() or name.is_absolute() or '..' in name.parts
                    or str(name) != member.name or member.name in seen):
                raise ValueError('invalid_archive_member')
            total += member.size
            if total > 4_000_000 or len(seen) >= 1000:
                raise ValueError('archive_limit')
            seen.add(member.name)
            target = root / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.extractfile(member).read())


def boundary(request):
    def readable(path):
        try:
            Path(path).read_bytes()
            return True
        except OSError:
            return False
    try:
        Path('/etc/aeep-rebench-canary').write_text('fixture')
        root_write = True
    except OSError:
        root_write = False
    try:
        with socket.create_connection(('192.0.2.1', 9), timeout=.2):
            network = True
    except OSError:
        network = False
    return dict(uid=os.getuid(), host_visible=readable(request['canary']),
                root_write=root_write, network=network)


def evaluate(request):
    if request['mode'] == 'boundary':
        return boundary(request)
    if request['mode'] in ('fresh_write', 'fresh_read'):
        path = Path('/tmp/aeep-rebench-freshness')
        before = path.exists()
        if request['mode'] == 'fresh_write':
            path.write_text('fixture')
        return {'previous_state': before}
    if request['mode'] != 'repository' or sys.version_info[:2] != (3, 13):
        raise ValueError('unreviewed_mode_or_python')
    with tempfile.TemporaryDirectory(prefix='rebench-') as directory:
        root = Path(directory)
        repo = root / 'repo'
        repo.mkdir()
        data = base64.b64decode(request['archive'], validate=True)
        assert sha(data) == request['archive_sha256']
        unpack(data, repo)
        wheels = []
        for wheel in request['wheels']:
            name = wheel['filename']
            assert name.endswith('.whl') and PurePosixPath(name).name == name
            content = base64.b64decode(wheel['data'], validate=True)
            assert sha(content) == wheel['sha256']
            target = root / name
            target.write_bytes(content)
            wheels.append(str(target))
        # No installer or entrypoint discovery: only reviewed wheels and this repo.
        boot = ('import sys, os; sys.path[:0] = ' + repr([str(repo), *wheels])
                + '; os.chdir(' + repr(str(repo)) + '); import pytest; '
                + 'assert pytest.__version__ == "8.3.5"; '
                + 'raise SystemExit(pytest.main(' + repr(request['test_argv']) + '))')
        env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': str(root),
               'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'}
        log = root / 'pytest.log'
        with log.open('wb') as stream:
            child = subprocess.run([sys.executable, '-B', '-c', boot], cwd=repo,
                                   env=env, stdout=stream, stderr=subprocess.STDOUT,
                                   timeout=22, check=False)
        if log.stat().st_size > 500_000:
            raise ValueError('test_log_limit')
        output = log.read_bytes()
        source = request['upstream_grading']
        assert sha(source.encode()) == request['upstream_grading_sha256']
        namespace = {}
        exec(compile(source, '<pinned-upstream-grading>', 'exec'), namespace)
        statuses = namespace['parse_log_pytest'](output.decode('utf-8', 'replace'), None)
        report = namespace['get_eval_tests_report'](statuses, request['expected'])
        resolved = namespace['get_resolution_status'](report)
        required = set(request['expected']['FAIL_TO_PASS'] + request['expected']['PASS_TO_PASS'])
        return {'exit_code': child.returncode, 'python': list(sys.version_info[:3]),
                'pytest': '8.3.5', 'statuses': statuses, 'resolved': resolved,
                'upstream_report': report, 'required_nodes': len(required),
                'missing_nodes': sorted(required - statuses.keys()),
                'log_sha256': sha(output), 'log_bytes': len(output),
                'archive_sha256': sha(data), 'upstream_grading_sha256': sha(source.encode())}


if __name__ == '__main__':
    payload = json.loads(sys.stdin.buffer.read(1_800_001))
    print(json.dumps(evaluate(payload), separators=(',', ':'), allow_nan=False))
