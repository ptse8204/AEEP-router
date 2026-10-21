"""Run the three explicitly approved current-source checks, preserving terminal attempts."""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from aeep.assessment.verification import verification_source_digest
from aeep_toolkit.install_runtime import digest

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert len(sys.argv) == 2 and sha(OUT / 'approval-bundle.json') == sys.argv[1]
    bundle = json.loads((OUT / 'approval-bundle.json').read_text())
    approval = json.loads((OUT / 'bundle-operator-approval.json').read_text())
    assert approval['approved'] and approval['bundle_sha256'] == sys.argv[1]
    assert sha(Path(__file__)) == bundle['runner_sha256']
    assert verification_source_digest(ROOT) == bundle['source_digest']
    assert json.loads((OUT / 'validation/source-stability.json').read_text())['all_passed']
    assert shutil.disk_usage(ROOT).free > 51 * 1024**3
    for action in bundle['actions']:
        assert sha(ROOT / action['review']) == action['review_sha256']
    assert not (OUT / 'bundle-execution-started.json').exists()
    with (OUT / 'bundle-execution-started.json').open('x') as stream:
        json.dump({'bundle_sha256': sys.argv[1], 'automatic_retry': False}, stream)
    checks = []
    for action in bundle['actions']:
        review_path = ROOT / action['review']
        review = json.loads(review_path.read_text())
        try:
            assert verification_source_digest(ROOT) == bundle['source_digest']
            assert not (review_path.parent / action['started_marker']).exists(), 'Started operation requires recovery; never replay.'
            record = dict(approval, review_sha256=action['review_sha256'])
            with (review_path.parent / 'operator-approval.json').open('x') as stream:
                json.dump(record, stream, indent=2)
                stream.write('\n')
            runner = ROOT / action['runner']
            argument = digest(review) if action['name'] == 'package' else action['review_sha256']
            arguments = ['--execute-reviewed-digest', argument] if action['name'] == 'package' else [argument]
            with (OUT / (action['name'] + '-bundle.log')).open('x') as log:
                result = subprocess.run([sys.executable, str(runner), *arguments], cwd=ROOT,
                                        stdout=log, stderr=subprocess.STDOUT, timeout=action['maximum_seconds'])
            terminal = ROOT / action['terminal_result']
            payload = json.loads(terminal.read_text()) if terminal.is_file() else {}
            checks.append({'name': action['name'], 'returncode': result.returncode,
                           'terminal_result': action['terminal_result'],
                           'passed': result.returncode == 0 and all(
                               payload.get(key) == value for key, value in action['pass_conditions'].items())})
        except Exception as exc:
            checks.append({'name': action['name'], 'error_type': type(exc).__name__})
        # A failed collector cannot block the independent offline package/docs checks.
        (OUT / 'bundle-execution-results.json').write_text(json.dumps(checks, indent=2) + '\n')
    print(json.dumps(checks))


if __name__ == '__main__':
    main()
