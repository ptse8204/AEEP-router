"""Compare stock and operator envelopes using first-party logs and no child execution."""
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def main():
    stock = (ROOT / 'integrations/assessment-runtime/swe_rebench_pytest_parser.py').read_text() + '\n' + (ROOT / 'integrations/assessment-runtime/repository_suite_plugins_program.py').read_text()
    program = (HERE / 'operator-observer.py').read_text()
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w:gz') as out:
        body = b'raise AssertionError("The synthetic subject must never run")\n'
        info = tarfile.TarInfo('tests/test_fake.py'); info.size = len(body)
        out.addfile(info, io.BytesIO(body))
    payload = {'archive': base64.b64encode(archive.getvalue()).decode(),
        'archive_sha256': hashlib.sha256(archive.getvalue()).hexdigest(), 'python': '3.13',
        'pytest': '8.3.5', 'wheels': [], 'pytest_plugins': [], 'source_modules': [], 'test_paths': ['tests/test_fake.py']}
    samples = [(0, b'PASSED tests/test_fake.py::test_ok\n'),
               (1, b'ModuleNotFoundError: No module named synthetic_dependency\nFAILED tests/test_fake.py::test_ok\n'),
               (2, b'PytestRemovedIn9Warning: synthetic collection error\nERROR tests/test_fake.py\n'),
               (1, b'x' * 10_000 + b'\xff\x00\nFAILED tests/test_fake.py::test_ok\n')]
    original_stdin = sys.stdin
    checked = 0
    try:
        for exit_code, log in samples:
            results = []
            for source in (stock, program):
                namespace = {'__name__': 'first_party_observer_fixture'}
                exec(compile(source, 'operator-observer-fixture', 'exec'), namespace)
                def fake_run(argv, **kwargs):
                    assert argv[:3] == [sys.executable, '-B', '-c']
                    assert kwargs['env']['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] == '1'
                    kwargs['stdout'].write(log)
                    return SimpleNamespace(returncode=exit_code)
                namespace['subprocess'] = SimpleNamespace(run=fake_run, STDOUT=subprocess.STDOUT)
                sys.stdin = io.StringIO(json.dumps(payload))
                results.append(namespace['main']())
            expected, wrapped = results
            assert wrapped['evaluation'] == expected
            assert set(wrapped) == {'evaluation', 'failure_log_tail_b64'}
            assert base64.b64decode(wrapped['failure_log_tail_b64'], validate=True) == (log[-8192:] if exit_code else b'')
            assert len(base64.b64decode(wrapped['failure_log_tail_b64'])) <= 8192
            checked += 1
    finally:
        sys.stdin = original_stdin
    result = {'passed': True, 'synthetic_cases': checked, 'evaluation_identical_to_stock_observer': True,
              'failure_tail_bytes_at_most': 8192, 'child_or_third_party_code_executed': False,
              'fixture_is_not_benchmark_evidence': True, 'new_models': 0}
    (HERE / 'operator-observer-check.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
