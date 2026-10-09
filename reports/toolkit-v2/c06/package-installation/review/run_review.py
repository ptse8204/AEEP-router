"""Exact pending private-installation test. Default is a read-only review.

Execution requires the operator's response to the recorded review; passing the
flag is not itself permission. Never replace the pinned wheel with a newer build.
"""
import argparse
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from aeep_toolkit.install_runtime import RuntimeInstallation, apply, digest, file_digest, remove

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
EXPECTED = '092e19571b5471a01cc14983096ea67b9074ad963486e6423915e04f563d96cf'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute-reviewed-digest')
    args = parser.parse_args()
    plan = RuntimeInstallation.model_validate_json((HERE / 'installation.json').read_text())
    assert digest(plan) == EXPECTED
    for wheel in plan.wheels:
        assert file_digest(Path(plan.wheelhouse) / wheel.filename) == wheel.sha256
    if args.execute_reviewed_digest is None:
        print(json.dumps({'review_sha256': EXPECTED, 'wheel_count': len(plan.wheels),
                          'destination': plan.destination, 'execution': False,
                          'status': 'Exact operator response still required.'}))
        return
    if args.execute_reviewed_digest != EXPECTED:
        raise ValueError('wrong review')
    output = HERE.parent / 'execution'
    output.mkdir(mode=0o700)  # Existing results must be reviewed, never overwritten/replayed.
    checks = []
    def save():
        (output / 'checks.json').write_text(json.dumps(checks, indent=2) + '\n')
    started = time.monotonic()
    state = apply(plan, EXPECTED)
    checks.append({'operation': 'existing installer apply', 'elapsed_seconds': time.monotonic() - started,
                   'state': state})
    save()
    assert state['status'] == 'installed' and state['enabled'] is False
    private_home = Path(tempfile.mkdtemp(prefix='aeep-core-cli-', dir=plan.wheelhouse))
    env = {'PATH': os.defpath, 'HOME': str(private_home), 'PYTHONNOUSERSITE': '1',
           'PYTHONDONTWRITEBYTECODE': '1', 'PIP_CONFIG_FILE': os.devnull, 'LC_ALL': 'C'}
    python = str(Path(plan.destination) / 'bin/python')
    evidence = ROOT / 'reports/toolkit-v2/c06/verified-journey/result/toolkit-evidence.json'
    candidate = ROOT / 'examples/toolkit_offline/format-json'
    commands = [
        ('help', ['--help'], 0),
        ('list', ['list', 'essentials'], 0),
        ('candidate', ['candidate', str(candidate)], 0),
        ('plan', ['plan', 'essentials', '--registry', str(HERE / 'registry.json'),
                  '--policy', str(HERE / 'policy.json'), '--select', 'aeep-agent-router'], 0),
        *[(f'report-{fmt}', ['report', '--evidence', str(evidence), '--format', fmt], 0)
          for fmt in ('json', 'markdown', 'html')],
        ('scripted-unavailable', ['eval', 'scripted', '--help'], 2),
    ]
    for label, arguments, expected in commands:
        argv = [python, '-I', '-B', '-m', 'aeep_toolkit', *arguments]
        start = time.monotonic()
        completed = subprocess.run(argv, cwd=private_home, env=env, stdin=subprocess.DEVNULL,
                                   capture_output=True, text=True, timeout=60)
        (output / f'{label}.stdout').write_text(completed.stdout)
        (output / f'{label}.stderr').write_text(completed.stderr)
        checks.append({'argv': argv, 'expected_returncode': expected, 'returncode': completed.returncode,
                       'elapsed_seconds': time.monotonic() - start, 'private_home': str(private_home)})
        save()
        assert completed.returncode == expected
        if label == 'report-json':
            summary = json.loads(completed.stdout)
            assert summary['outcome'] == 'NOT_ASSESSED'
            assert all(c['binding']['evidence_kind'] == 'synthetic' for c in summary['cohorts'])
        if label == 'plan':
            assert json.loads(completed.stdout)['execution_authorized'] is False
        if label == 'scripted-unavailable':
            assert 'requires the reviewed repository checkout' in completed.stderr
    assert list(private_home.iterdir()) == []
    private_home.rmdir()  # Remove only the verified empty directory created above.
    state = remove(plan, EXPECTED)  # Existing snapshot conflict protection preserves changed contents.
    checks.append({'operation': 'existing installer remove', 'state': state})
    save()
    assert state['status'] == 'removed' and not Path(plan.destination).exists()
    print(json.dumps({'status': 'installed CLI checks and unchanged removal passed',
                      'source_commit': '538606417ea93be6e82c431011c4f209a68ceb81',
                      'model_calls': 0, 'qualification': False}))


if __name__ == '__main__':
    main()
