# Only this fixed observer executes repository code, inside the offline grader.
import base64
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from swe_rebench_pytest_parser import parse_log_pytest


def main():
    request = json.load(sys.stdin)
    python = '.'.join(map(str, sys.version_info[:2]))
    assert python == request['python']
    with tempfile.TemporaryDirectory(prefix='repository-suite-') as directory:
        root = Path(directory)
        repo = root / 'repository'
        repo.mkdir()
        archive_bytes = base64.b64decode(request['archive'], validate=True)
        assert hashlib.sha256(archive_bytes).hexdigest() == request['archive_sha256']
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:gz') as archive:
            for member in archive:
                # The coordinator already bounded and canonicalized this archive.
                assert member.isfile() and not member.name.startswith('/') and '..' not in Path(member.name).parts
                path = repo / member.name
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as stream:
                    path.write_bytes(stream.read())
        wheels = []
        for item in request['wheels']:
            name = item['filename']
            assert Path(name).name == name and name.endswith('-none-any.whl')
            data = base64.b64decode(item['data'], validate=True)
            assert hashlib.sha256(data).hexdigest() == item['sha256']
            path = root / name
            path.write_bytes(data)
            wheels.append(str(path))
        argv = ['--no-header', '-rA', '--tb=line', '--color=no', '-p', 'no:cacheprovider', *request['test_paths']]
        boot = ('import sys, os; sys.path[:0] = ' + repr([str(repo / 'src'), str(repo), *wheels])
                + '; os.chdir(' + repr(str(repo)) + '); import pytest; assert pytest.__version__ == '
                + repr(request['pytest']) + '; raise SystemExit(pytest.main(' + repr(argv) + '))')
        log = root / 'tests.log'
        with log.open('wb') as stream:
            child = subprocess.run([sys.executable, '-B', '-c', boot], cwd=repo,
                env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': str(root),
                     'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'},
                stdout=stream, stderr=subprocess.STDOUT, timeout=22, check=False)
        assert log.stat().st_size <= 500_000
        statuses = parse_log_pytest(log.read_text(errors='replace'), None)
        return {'statuses': statuses, 'exit_code': child.returncode,
                'archive_sha256': request['archive_sha256'], 'python': python, 'pytest': request['pytest']}


if __name__ == '__main__':
    print(json.dumps(main(), separators=(',', ':'), allow_nan=False))
