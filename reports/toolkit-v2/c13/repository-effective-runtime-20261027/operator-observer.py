# MIT source: SWE-rebench/SWE-bench-fork, 980d0cca8aa4e73f1d9f894e906370bef8c4de8a
# Exact class/function bodies; see LICENSE.swe-rebench.
from __future__ import annotations

from enum import Enum
from typing import Any as TestSpec


class TestStatus(Enum):
    FAILED = "FAILED"
    PASSED = "PASSED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"
    XFAIL = "XFAIL"

def parse_log_pytest(log: str, test_spec: TestSpec) -> dict[str, str]:
    """
    Parser for test logs generated with PyTest framework

    Args:
        log (str): log content
    Returns:
        dict: test case to test status mapping
    """
    test_status_map = {}
    for line in log.split("\n"):
        if any([line.startswith(x.value) for x in TestStatus]):
            # Additional parsing for FAILED status
            if line.startswith(TestStatus.FAILED.value):
                line = line.replace(" - ", " ")
            test_case = line.split()
            if len(test_case) <= 1:
                continue
            test_status_map[test_case[1]] = test_case[0]
    return test_status_map

# Explicit-plugin observer for reviewed v2 cases; the legacy observer stays unchanged.
import base64
import hashlib
import io
import json
import re
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
    plugins = request.get('pytest_plugins', [])
    assert isinstance(plugins, list) and len(plugins) <= 8 and len(set(plugins)) == len(plugins)
    assert all(isinstance(name, str) and len(name) <= 128 and re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', name, flags=re.ASCII) for name in plugins)
    source_modules = request.get('source_modules', [])
    assert isinstance(source_modules, list) and all(isinstance(name, str) and name.isidentifier() for name in source_modules)
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
        # Import reviewed runtime/plugins before exposing candidate source paths.
        boot = ('import sys, os, importlib; sys.path[:] = ' + repr(wheels)
                + ' + [p for p in sys.path if p and os.path.abspath(p) != ' + repr(str(repo))
                + ' and not os.path.abspath(p).startswith(' + repr(str(repo) + '/') + ')]'
                + '; import pytest; assert pytest.__version__ == ' + repr(request['pytest'])
                + '; plugins = [importlib.import_module(n) for n in ' + repr(plugins) + ']'
                + '; assert all(getattr(p, "__file__", None) and not os.path.abspath(p.__file__).startswith('
                + repr(str(repo) + '/') + ') for p in plugins)'
                + '; assert not set(' + repr(source_modules) + ') & {n.split(".")[0] for n in sys.modules}, "source module already loaded by runtime/plugin"'
                + '; sys.path[:0] = ' + repr([str(repo / 'src'), str(repo)])
                + '; os.chdir(' + repr(str(repo)) + '); raise SystemExit(pytest.main(' + repr(argv) + ', plugins=plugins))')
        log = root / 'tests.log'
        with log.open('wb') as stream:
            child = subprocess.run([sys.executable, '-B', '-c', boot], cwd=repo,
                env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': str(root),
                     'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'},
                stdout=stream, stderr=subprocess.STDOUT, timeout=22, check=False)
        assert log.stat().st_size <= 500_000
        # Frame pytest result rows before the pinned upstream parser. Application
        # logging prefixes are not test statuses; preserve real module errors too.
        lines = log.read_text(errors='replace').splitlines()
        framed = [line for line in lines if re.match(
            r'^(?:PASSED|FAILED|ERROR|SKIPPED|XFAIL)\s+[^\s]+\.py(?:::|\s|$)', line)]
        statuses = parse_log_pytest('\n'.join(framed), None)
        evaluation = {'statuses': statuses, 'exit_code': child.returncode,
                      'archive_sha256': request['archive_sha256'], 'python': python, 'pytest': request['pytest']}
        # This operator-only review may retain at most 8 KiB of public failure output.
        tail = log.read_bytes()[-8192:] if child.returncode else b''
        return {'evaluation': evaluation, 'failure_log_tail_b64': base64.b64encode(tail).decode('ascii')}



if __name__ == '__main__':
    print(json.dumps(main(), separators=(',', ':'), allow_nan=False))
