"""Run the unmodified upstream tests against a bounded ephemeral submission."""
import contextlib
import json
import os
import sys
from pathlib import Path

EXPECTED = ['test_outputs.py::TestOutputs::test_content', 'test_outputs.py::TestOutputs::test_file_exists']


def main():
    sys.path[:0] = ['/aeep', '/aeep/tools']
    from boundary import check
    from repository_suite_native_capture import NativeCapture

    check()
    os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
    import pytest

    request = json.loads(sys.stdin.buffer.read(75_000))
    assert set(request) == {'report'}
    report = request['report']
    if report is not None:
        assert isinstance(report, str) and 0 < len(report.encode()) <= 65_536
        Path('/root/fraud_report.json').write_text(report)
    capture = NativeCapture()
    # A missing protected asset is an infrastructure failure, before scoring.
    if not Path('/aeep/ground_truth.json').is_file():
        print(json.dumps({'status': 'infrastructure_error', 'cause': 'protected_asset_missing'}))
        return
    with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        code = int(pytest.main(['-p', 'no:cacheprovider', '--rootdir=/aeep',
                                '/aeep/test_outputs.py', '-q'], plugins=[capture]))
    statuses = capture.export()['statuses']
    if (sorted(capture.selected_ids) != EXPECTED or sorted(statuses) != EXPECTED
            or set(statuses.values()) - {'PASSED', 'FAILED'}):
        print(json.dumps({'status': 'infrastructure_error', 'cause': 'verifier_protocol',
                          'identities': capture.selected_ids, 'exit_code': code}))
        return
    failed = 'FAILED' in statuses.values()
    assert code == int(failed)
    print(json.dumps({'status': 'rejected' if failed else 'passed', 'tests': statuses,
                      'exit_code': code, 'intentional_skips': []}))


if __name__ == '__main__':
    main()
