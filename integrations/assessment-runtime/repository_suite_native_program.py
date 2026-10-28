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

CAPTURE_SOURCE = '__AEEP_NATIVE_CAPTURE_SOURCE__'
# Only an exact operator-reviewed program may enable collection and failure logs.
OPERATOR_REVIEW = False


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
        repo = Path('/tmp/aeep-repository-native-v6')
        repo.mkdir(mode=0o700)
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
