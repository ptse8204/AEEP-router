"""Run the pinned verifier and controls with the original assertions."""

import contextlib
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from zipfile import ZipFile

sys.path[:0] = ['/opt', '/opt/aflow-dependencies', *sorted(str(p) for p in Path('/opt/wheels').glob('*.whl'))]
from check_socket_boundary import socket_boundary


class Observation:
    def __init__(self):
        self.identities = []
        self.outcomes = {}
        self.setup_errors = []

    def pytest_collection_modifyitems(self, items):
        self.identities.extend(item.nodeid.split('::', 1)[1] for item in items)

    def pytest_runtest_logreport(self, report):
        identity = report.nodeid.split('::', 1)[1]
        if report.when == 'call':
            self.outcomes[identity] = report.outcome
        elif report.outcome != 'passed':
            self.setup_errors.append(identity)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    assert (os.geteuid(), os.getegid()) == (65534, 65534)
    assert not Path('/var/run/docker.sock').exists() and not os.access('/opt', os.W_OK)
    status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines())
    assert status['NoNewPrivs'].strip() == '1' and int(status['CapEff'], 16) == 0
    assert status['Seccomp'].strip() == '2'
    boundary = socket_boundary()
    import openpyxl
    import pandas
    import pytest

    assert openpyxl.__version__ == '3.1.5' and '/opt/wheels/' in openpyxl.__file__
    assert pandas.__version__ == '2.2.3' and pandas.__file__.startswith('/opt/aflow-dependencies/')
    assert pytest.__version__ == '8.4.1' and '/opt/wheels/' in pytest.__file__
    assert os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] == '1'
    root = Path('/tmp/aeep-excel')
    root.mkdir()
    pins = json.loads(Path('/opt/pins.json').read_bytes())
    source = Path('/opt/test_outputs.py').read_bytes()
    assert sha(source) == pins['verifier_sha256']
    adapted = source.replace(b'/root/input.pptx', b'/tmp/aeep-excel/input.pptx').replace(
        b'/root/results.pptx', b'/tmp/aeep-excel/results.pptx')
    assert adapted.replace(b'/tmp/aeep-excel/', b'/root/') == source and adapted != source
    verifier = root / 'test_outputs.py'
    verifier.write_bytes(adapted)
    input_file, result_file = root / 'input.pptx', root / 'results.pptx'
    initial, reference = Path('/opt/input.pptx'), Path('/opt/reference.pptx')
    assert sha(initial.read_bytes()) == pins['input_sha256']
    assert sha(reference.read_bytes()) == pins['reference_sha256']
    results = {}
    for mode in ('reference', 'unchanged', 'destructive', 'missing_protected_input'):
        if mode == 'missing_protected_input':
            input_file.unlink()
        else:
            shutil.copyfile(initial, input_file)
        if mode == 'destructive':
            member = 'ppt/embeddings/Microsoft_Excel_Worksheet.xlsx'
            with ZipFile(reference) as src, ZipFile(result_file, 'w') as dst:
                assert member in src.namelist()
                for info in src.infolist():
                    if info.filename != member:
                        dst.writestr(info, src.read(info))
        else:
            shutil.copyfile(initial if mode == 'unchanged' else reference, result_file)
        # Missing protected inputs are infrastructure errors regardless of task output.
        protected_input_available = input_file.is_file() and sha(input_file.read_bytes()) == pins['input_sha256']
        if not protected_input_available:
            assert mode == 'missing_protected_input'
            results[mode] = {'infrastructure_error': 'missing_protected_input', 'verifier_started': False}
            continue
        tracker = Observation()
        with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            exit_code = int(pytest.main(['-q', '--disable-warnings', '-p', 'no:cacheprovider', str(verifier)],
                                        plugins=[tracker]))
        assert tracker.identities == pins['tests']
        assert not tracker.setup_errors and set(tracker.outcomes) == set(pins['tests'])
        assert set(tracker.outcomes.values()) <= {'passed', 'failed'}
        assert exit_code == (0 if mode == 'reference' else 1)
        assert (all(v == 'passed' for v in tracker.outcomes.values())) is (mode == 'reference')
        if mode == 'unchanged':
            assert tracker.outcomes['test_exchange_rate_updated'] == 'failed'
        if mode == 'destructive':
            assert tracker.outcomes['test_embedded_excel_preserved'] == 'failed'
        results[mode] = {'exit_code': exit_code, 'upstream_binary_reward': int(exit_code == 0),
                         'observations': tracker.outcomes, 'intentional_skips': 0}
    return {'passed': True, 'models': 0, 'protected_grader': results, 'boundary': boundary,
            'adaptation': 'absolute input/output paths only'}


if __name__ == '__main__':
    try:
        print(json.dumps(main()))
    except Exception as error:
        import traceback

        frames = traceback.extract_tb(error.__traceback__)
        print(json.dumps({'passed': False, 'error_type': type(error).__name__,
                          'locations': [{'file': f.filename, 'line': f.lineno, 'function': f.name}
                                        for f in frames if f.filename in ('/opt/grade.py', '/opt/check_socket_boundary.py')]}))
        raise SystemExit(1)
