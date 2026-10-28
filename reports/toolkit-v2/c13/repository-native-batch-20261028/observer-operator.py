"""Native pytest identities for explicit v6 recipes; no raw log retention by default."""
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

CAPTURE_SOURCE = '"""First-party glue for pytest\'s public collection and runtest-report hooks.\n\nNo subject imports, stdout parsing, identity rewriting or successful collection\ngrades. A PASS requires all three native runtest phases to have passed.\n"""\n\n\nclass NativeCapture:\n    def __init__(self, collect_only=False):\n        self.collect_only = collect_only\n        self.native_ids = []\n        self.selected_ids = []\n        self.phases = {}\n        self.problems = set()\n\n    def _identity(self, value):\n        if not isinstance(value, str) or not value or not value.isprintable() or len(value.encode(\'utf-8\')) > 8192:\n            self.problems.add(\'invalid_identity\')\n            return False\n        return True\n\n    def pytest_itemcollected(self, item):\n        if self.collect_only and self._identity(item.nodeid):\n            if len(self.native_ids) >= 10000:\n                self.problems.add(\'collection_limit\')\n            else:\n                self.native_ids.append(item.nodeid)\n\n    def pytest_collection_finish(self, session):\n        for item in session.items:\n            if self._identity(item.nodeid):\n                if len(self.selected_ids) >= 10000:\n                    self.problems.add(\'selected_limit\')\n                    break\n                self.selected_ids.append(item.nodeid)\n\n    def pytest_runtest_logreport(self, report):\n        if not self._identity(report.nodeid):\n            return\n        if report.when not in (\'setup\', \'call\', \'teardown\') or report.outcome not in (\'passed\', \'failed\', \'skipped\'):\n            self.problems.add(\'invalid_phase_or_outcome\')\n            return\n        if report.nodeid not in self.phases and len(self.phases) >= 10000:\n            self.problems.add(\'report_limit\')\n            return\n        phases = self.phases.setdefault(report.nodeid, {})\n        if report.when in phases:\n            self.problems.add(\'duplicate_phase\')\n            return\n        phases[report.when] = (report.outcome, hasattr(report, \'wasxfail\'))\n\n    def export(self):\n        if len(set(self.selected_ids)) != len(self.selected_ids):\n            self.problems.add(\'duplicate_selected_identity\')\n        if self.collect_only:\n            if len(set(self.native_ids)) != len(self.native_ids):\n                self.problems.add(\'duplicate_collected_identity\')\n            if not set(self.selected_ids) <= set(self.native_ids) or self.phases:\n                self.problems.add(\'collection_scope_mismatch\')\n            if self.problems:\n                raise ValueError(\'native_collection_protocol:\' + \',\'.join(sorted(self.problems)))\n            return {\'native_ids\': self.native_ids, \'selected_ids\': self.selected_ids}\n        if not set(self.phases) <= set(self.selected_ids):\n            self.problems.add(\'unselected_report_identity\')\n        statuses = {}\n        for node, phases in self.phases.items():\n            if any(outcome == \'failed\' for when, (outcome, _) in phases.items() if when != \'call\'):\n                statuses[node] = \'ERROR\'\n            elif any(outcome == \'skipped\' for outcome, _ in phases.values()):\n                statuses[node] = \'XFAIL\' if any(xfail for _, xfail in phases.values()) else \'SKIPPED\'\n            elif \'call\' in phases:\n                outcome, xfail = phases[\'call\']\n                if xfail:\n                    statuses[node] = \'XFAIL\'  # Unexpected passes never satisfy a required PASS.\n                elif outcome == \'failed\':\n                    statuses[node] = \'FAILED\'\n                elif set(phases) == {\'setup\', \'call\', \'teardown\'} and all(v == (\'passed\', False) for v in phases.values()):\n                    statuses[node] = \'PASSED\'\n                else:\n                    self.problems.add(\'incomplete_pass_phases\')\n        if self.problems:\n            raise ValueError(\'native_report_protocol:\' + \',\'.join(sorted(self.problems)))\n        # Missing reports stay absent; the protected coordinator rejects missing IDs.\n        return {\'statuses\': statuses}\n'
# Only an exact operator-reviewed program may enable collection and failure logs.
OPERATOR_REVIEW = True


def main():
    request = json.load(sys.stdin)
    python = '.'.join(map(str, sys.version_info[:2]))
    assert python == request['python']
    collect_only = request.get('collect_only', False)
    assert type(collect_only) is bool
    assert OPERATOR_REVIEW or 'collect_only' not in request
    plugins = request.get('pytest_plugins', [])
    assert isinstance(plugins, list) and len(plugins) <= 8 and len(set(plugins)) == len(plugins)
    assert all(isinstance(n, str) and len(n) <= 128 and re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', n, flags=re.ASCII) for n in plugins)
    source_modules = request.get('source_modules', [])
    assert isinstance(source_modules, list) and all(isinstance(n, str) and n.isidentifier() for n in source_modules)
    with tempfile.TemporaryDirectory(prefix='repository-native-pytest-') as directory:
        root = Path(directory)
        repo = root / 'repository'
        repo.mkdir()
        archive_bytes = base64.b64decode(request['archive'], validate=True)
        assert hashlib.sha256(archive_bytes).hexdigest() == request['archive_sha256']
        expanded = 0
        seen = set()
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:gz') as archive:
            for member in archive:
                name = Path(member.name)
                assert member.isfile() and not name.is_absolute() and '..' not in name.parts and member.name not in seen
                expanded += member.size
                assert expanded <= 24_000_000 and len(seen) < 10000
                seen.add(member.name)
                path = repo / name
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
            with path.open('xb') as stream:
                stream.write(data)
            wheels.append(str(path))
        argv = ['--no-header', '-rA', '--tb=line', '--color=no', '-p', 'no:cacheprovider', *request['test_paths']]
        if collect_only:
            argv[:0] = ['--collect-only']
        if '_hypothesis_pytestplugin' in plugins:
            argv[:0] = ['--hypothesis-seed=29']
        events = root / 'native-events.json'
        boot = ('import sys,os,importlib,json;from pathlib import Path;sys.path[:] = ' + repr(wheels)
            + ' + [p for p in sys.path if p and os.path.abspath(p) != ' + repr(str(repo))
            + ' and not os.path.abspath(p).startswith(' + repr(str(repo) + '/') + ')]'
            + ';import pytest;assert pytest.__version__ == ' + repr(request['pytest'])
            + ';plugins=[importlib.import_module(n) for n in ' + repr(plugins) + ']'
            + ';assert all(getattr(p,"__file__",None) and not os.path.abspath(p.__file__).startswith(' + repr(str(repo) + '/') + ') for p in plugins)'
            + ';assert not set(' + repr(source_modules) + ') & {n.split(".")[0] for n in sys.modules},"source module already loaded by runtime/plugin"'
            + ';scope={"__name__":"aeep_native_capture"};exec(' + repr(CAPTURE_SOURCE) + ',scope)'
            + ';capture=scope["NativeCapture"](' + repr(collect_only) + ')'
            + ';export=capture.export;sys.path[:0]=' + repr([str(repo / 'src'), str(repo)])
            + ';os.chdir(' + repr(str(repo)) + ');code=pytest.main(' + repr(argv) + ',plugins=[*plugins,capture])'
            + ';Path(' + repr(str(events)) + ').write_text(json.dumps(export(),separators=(",",":"),allow_nan=False))'
            + ';raise SystemExit(code)')
        log = root / 'tests.log'
        with log.open('wb') as stream:
            # Bootstrap outside candidate cwd before adding reviewed source paths.
            child = subprocess.run([sys.executable, '-B', '-c', boot], cwd=root,
                env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': str(root),
                     'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'},
                stdout=stream, stderr=subprocess.STDOUT, timeout=22, check=False)
        assert log.stat().st_size <= 500_000 and events.is_file() and not events.is_symlink() and events.stat().st_size <= 500_000
        native = json.loads(events.read_text())
        header = {'exit_code': child.returncode, 'archive_sha256': request['archive_sha256'], 'python': python, 'pytest': request['pytest']}
        if not OPERATOR_REVIEW:
            assert set(native) == {'statuses'}
            return {**header, **native}
        tail = base64.b64encode(log.read_bytes()[-8192:] if child.returncode else b'').decode('ascii')
        if collect_only:
            assert set(native) == {'native_ids', 'selected_ids'}
            return {'collection': {**header, **native}, 'failure_log_tail_b64': tail}
        assert set(native) == {'statuses'}
        return {'evaluation': {**header, **native}, 'failure_log_tail_b64': tail}


if __name__ == '__main__':
    print(json.dumps(main(), separators=(',', ':'), allow_nan=False))
