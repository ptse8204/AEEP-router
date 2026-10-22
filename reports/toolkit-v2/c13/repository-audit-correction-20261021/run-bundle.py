"""Execute each exact approved component once; continue independent safe checks."""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from aeep.assessment.verification import verification_source_digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert len(sys.argv) == 2 and sha(HERE / 'approval-bundle.json') == sys.argv[1]
    bundle = json.loads((HERE / 'approval-bundle.json').read_text())
    approval = json.loads((HERE / 'bundle-operator-approval.json').read_text())
    assert approval['approved'] and approval['review_sha256'] == sys.argv[1]
    assert sha(Path(__file__)) == bundle['runner_sha256']
    assert verification_source_digest(ROOT) == bundle['source_digest']
    assert json.loads((HERE / 'validation-v2/source-stability.json').read_text())['all_passed']
    for action in bundle['actions']:
        assert sha(ROOT / action['review']) == action['review_sha256']
        assert sha(ROOT / action['runner']) == action['runner_sha256']
        assert not (ROOT / action['started_marker']).exists()
        assert not (ROOT / action['approval_record']).exists()
    with (HERE / 'bundle-execution-started.json').open('x') as marker:
        json.dump({'review_sha256': sys.argv[1], 'automatic_replay': False}, marker)
    results = []
    for action in bundle['actions']:
        assert verification_source_digest(ROOT) == bundle['source_digest']
        record = {'approved': True, 'review_sha256': action['review_sha256'],
            'bundle_sha256': sys.argv[1], 'operator_text': approval['operator_text'],
            'authority': 'Exact human approval of this bundle and its listed component digests.'}
        with (ROOT / action['approval_record']).open('x') as output:
            json.dump(record, output, indent=2)
        started = time.perf_counter()
        try:
            with (HERE / (action['name'] + '-execution.log')).open('x') as log:
                process = subprocess.run(action['argv'], cwd=ROOT, env={**os.environ, 'PYTHONPATH': 'src'},
                    stdout=log, stderr=subprocess.STDOUT, timeout=action['maximum_seconds'])
            terminal = ROOT / action['terminal_result']
            evidence = json.loads(terminal.read_text()) if terminal.is_file() else {}
            passed = process.returncode == 0 and all(evidence.get(key) == value
                for key, value in action['pass_conditions'].items())
            result = {'action': action['name'], 'returncode': process.returncode, 'passed': passed}
        except BaseException as exc:
            result = {'action': action['name'], 'passed': False, 'error_type': type(exc).__name__}
            if not isinstance(exc, Exception):
                results.append(result)
                (HERE / 'bundle-execution-result.json').write_text(json.dumps({'passed': False, 'actions': results}, indent=2) + '\n')
                raise
        result['seconds'] = time.perf_counter() - started
        results.append(result)
        (HERE / 'bundle-execution-result.json').write_text(json.dumps({'passed': len(results) == len(bundle['actions'])
            and all(item['passed'] for item in results), 'source_digest': bundle['source_digest'],
            'model_calls': 0, 'actions': results}, indent=2) + '\n')
    print(json.dumps(results))


if __name__ == '__main__':
    main()
