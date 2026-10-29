"""Execute only the exact approved changed-wheel/docs bundle, once per component."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from aeep.assessment.verification import verification_source_digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


assert len(sys.argv) == 2
assert sha(HERE / 'approval-bundle.json') == sys.argv[1]
bundle = json.loads((HERE / 'approval-bundle.json').read_text())
assert sha(Path(__file__)) == bundle['runner_sha256']
approval = json.loads((HERE / 'operator-approval.json').read_text())
assert approval['approved'] and approval['review_sha256'] == sys.argv[1]
assert verification_source_digest(ROOT) == bundle['source_digest']
for item in bundle['components'].values():
    assert sha(ROOT / item['review']) == item['review_file_sha256']
    assert sha(ROOT / item['driver']) == item['driver_sha256']
    directory = (ROOT / item['review']).parent
    assert not (directory / 'execution-started.json').exists()
    assert not (directory / 'operator-approval.json').exists()
assert shutil.disk_usage(ROOT).free > 51 * 1024**3
with (HERE / 'bundle-execution-started.json').open('x') as output:
    json.dump({'review_sha256': sys.argv[1], 'automatic_retry': False}, output)
results = {'review_sha256': sys.argv[1], 'phases': [], 'models': 0, 'cash_usd': 0}
for name, item in bundle['components'].items():
    assert verification_source_digest(ROOT) == bundle['source_digest']
    assert shutil.disk_usage(ROOT).free > 51 * 1024**3
    directory = (ROOT / item['review']).parent
    with (directory / 'operator-approval.json').open('x') as output:
        json.dump({'approved': True, 'review_sha256': item['review_file_sha256'],
            'source': 'Exact human-approved parent bundle explicitly includes this component.',
            'parent_review_sha256': sys.argv[1], 'parent_approval_file': str(HERE / 'operator-approval.json')}, output, indent=2)
    arguments = ['--execute-reviewed-digest', item['argument_policy_digest']] if name == 'package' else [item['review_file_sha256']]
    started = time.monotonic()
    try:
        with (HERE / (name + '-execution.log')).open('x') as log:
            process = subprocess.run([sys.executable, str(ROOT / item['driver']), *arguments],
                cwd=ROOT, env=dict(os.environ, PYTHONPATH='src'), stdout=log, stderr=subprocess.STDOUT,
                timeout=bundle['limits']['maximum_' + name + '_seconds'])
    except BaseException as exc:
        results['phases'].append({'component': name, 'error_type': type(exc).__name__,
            'wall_seconds': time.monotonic() - started,
            'effects_and_cleanup': 'Inspect component durable markers and runtime before any dependent work.'})
        results['all_components_passed'] = False
        (HERE / 'bundle-execution-result.json').write_text(json.dumps(results, indent=2) + '\n')
        raise
    results['phases'].append({'component': name, 'returncode': process.returncode,
        'wall_seconds': time.monotonic() - started})
    (HERE / 'bundle-execution-result.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results['phases'][-1]), flush=True)
results['all_components_passed'] = all(p['returncode'] == 0 for p in results['phases'])
(HERE / 'bundle-execution-result.json').write_text(json.dumps(results, indent=2) + '\n')
