"""Run the protected upstream verifier and emit only grade and test facts."""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).parent
WORK = pathlib.Path('/tmp/aeep-prefix')
CASES = {'reference', 'incomplete', 'destructive', 'intentional_skip', 'infrastructure'}
PATHS = ('config.json', 'trace.jsonl', 'report.json')


def main():
    case, tools = sys.argv[1:]
    if case not in CASES or os.getuid() != 65534:
        raise SystemExit('unexpected case or uid')
    WORK.mkdir(mode=0o700)
    assert os.stat('/').st_dev != os.stat(WORK).st_dev
    for path in PATHS[:2]:
        shutil.copyfile(ROOT / path, WORK / path)
    report = WORK / 'report.json'
    oracle = subprocess.run(['/bin/bash', str(ROOT / 'solve.sh')], cwd=WORK, env={
        'PATH': '/usr/bin:/bin:/usr/local/bin', 'HOME': str(WORK), 'LC_ALL': 'C',
    }, capture_output=True, timeout=10)
    if oracle.returncode != 0 or report.stat().st_size > 262144:
        raise SystemExit('protected reference preparation failed')
    initial = json.loads(report.read_bytes())
    if case == 'incomplete':
        initial['per_request'].pop()
        report.write_text(json.dumps(initial))
    if case == 'destructive':
        for key in ('total_hit_tokens', 'overall_hit_rate', 'final_cache_blocks'):
            initial[key] = 0
        for row in initial['per_request']:
            row['hit_tokens'] = 0
        report.write_text(json.dumps(initial))
    if case == 'infrastructure':
        (WORK / 'trace.jsonl').unlink()

    sys.path.insert(0, tools)
    os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
    import pytest

    class SkipControl:
        def pytest_collection_modifyitems(self, items):
            marked = [item for item in items if item.name == 'test_total_hit_tokens']
            assert len(marked) == 1
            marked[0].add_marker(pytest.mark.skip(reason='explicit first-party skip control'))

    xml = WORK / 'tests.xml'
    runner = pytest.main(['-q', '-p', 'no:cacheprovider', '--junitxml', str(xml),
                          str(ROOT / 'test_outputs.py')],
                         plugins=[SkipControl()] if case == 'intentional_skip' else [])
    document = ET.parse(xml)
    rows = []
    for item in document.iter('testcase'):
        status = 'passed'
        for state in ('failure', 'error', 'skipped'):
            if item.find(state) is not None:
                status = state
                break
        rows.append({'test_id': item.attrib['name'], 'status': status})
    output = {'case': case, 'pytest_exit': int(runner), 'pytest_version': pytest.__version__, 'tests': rows}
    (WORK / 'result.json').write_text(json.dumps(output))


if __name__ == '__main__':
    # Pytest stdout can contain task data. Run the entire guest in a child
    # and expose only the fixed result, with no raw logs on either channel.
    if len(sys.argv) == 4 and sys.argv[1] == '--protected':
        sys.argv.pop(1)
        main()
    else:
        result = subprocess.run([sys.executable, '-I', '-B', __file__, '--protected', *sys.argv[1:]],
                                capture_output=True, timeout=30)
        if result.returncode or not (WORK / 'result.json').is_file():
            raise SystemExit('protected guest stopped before emitting its grade')
        print((WORK / 'result.json').read_text())
