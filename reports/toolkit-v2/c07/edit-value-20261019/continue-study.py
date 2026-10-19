"""Continue the approved study through existing one-shot drivers, without retries."""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).parent
ENV = {**os.environ, 'PYTHONPATH': str(ROOT / 'src')}


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(folder, driver, *arguments):
    print(json.dumps({'step': folder.name + '/' + driver, 'state': 'starting'}), flush=True)
    with (folder / (driver.removesuffix('.py') + '-execution.log')).open('x') as log:
        subprocess.run([sys.executable, str(folder / driver), *arguments], cwd=ROOT,
                       env=ENV, stdout=log, stderr=subprocess.STDOUT, check=True)
    print(json.dumps({'step': folder.name + '/' + driver, 'state': 'returned'}), flush=True)


def main():
    assert sys.version_info[:2] == (3, 13)
    with (OUT / 'continuation-started.json').open('x') as marker:
        json.dump({'pid': os.getpid(), 'driver_sha256': sha(Path(__file__)),
                   'replay_allowed': False, 'task': 'Qualification then frozen four-arm value'}, marker)
    qualified_path = OUT.parent / 'edit-study-prompt-20261019/qualification-result.json'
    deadline = time.monotonic() + 3600
    while not qualified_path.exists():
        assert time.monotonic() < deadline
        time.sleep(5)
    qualified = read(qualified_path)
    assert qualified['qualification_passed'] and qualified['proxy_restored'] and qualified['source_unchanged']
    print(json.dumps({'qualification_report_id': qualified['report_id'], 'qualification_passed': True}), flush=True)
    for name in ('edit-value-20261019', 'edit-higher-20261019', 'edit-reusable-pair-20261019'):
        folder = OUT.parent / name
        assert not (folder / 'pair-started.json').exists()
        run(folder, 'run-pair.py', sha(folder / 'pair-execution-review.json'))
        result = read(folder / 'pair-result.json')
        assert result['paired_checks_passed'] and result['source_unchanged'] and result['proxy_restored_stopped']
        run(folder, 'assemble-boundary.py')
        boundary = read(folder / 'boundary-result.json')
        assert all(value['verified_probe_count'] == 11 for value in boundary['boundaries'].values())
    run(OUT, 'prepare-value.py')
    proposal = read(OUT / 'value-review.json')
    assert not proposal['blocked_reasons']
    run(OUT, 'prepare-value-execution.py')
    review_sha = sha(OUT / 'value-execution-review.json')
    print(json.dumps({'value_plan_id': proposal['plan_id'], 'execution_review_sha256': review_sha}), flush=True)
    run(OUT, 'run-value.py', review_sha)
    result = read(OUT / 'value-result.json')
    assert result.get('report_id') and result['source_unchanged'] and result['proxy_restored']
    (OUT / 'continuation-result.json').write_text(json.dumps({
        'qualification_report_id': qualified['report_id'], 'value_plan_id': proposal['plan_id'],
        'value_report_id': result['report_id'], 'outcome': result['outcome'],
        'replay_allowed': False, 'admission': False, 'publication': False,
    }, indent=2) + '\n')
    print(json.dumps({'value_report_id': result['report_id'], 'outcome': result['outcome']}), flush=True)


main()
