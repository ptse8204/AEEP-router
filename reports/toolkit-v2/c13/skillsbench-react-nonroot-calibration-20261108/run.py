"""Prepare and run one exact offline nonroot calibration."""

import argparse
import asyncio
import importlib.util
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from aeep.assessment.verification import verification_source_digest
from aeep.models import utc_now

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT / '.aeep' / HERE.name
PRIOR = HERE.parent / 'skillsbench-react-reference-20261106'
REFERENCE = PRIOR / 'verifier-continuation/reference.py'
POSITIVE = PRIOR / 'browser-id-continuation'
CONTROL = PRIOR / 'negative-controls'
CASE_DRIVER = CONTROL / 'run-case.py'
spec = importlib.util.spec_from_file_location('retained_react_receipt_driver', CASE_DRIVER)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
runner.HERE = HERE


def browser_manifest(path):
    assert path.is_dir() and not path.is_symlink()
    files = {}
    for entry in sorted(path.rglob('*')):
        assert not entry.is_symlink()
        assert entry.is_file() or entry.is_dir()
        mode = entry.stat().st_mode & 0o777
        assert mode in ({0o555} if entry.is_dir() else {0o444, 0o555})
        if entry.is_file():
            files[str(entry.relative_to(path))] = {'sha256': runner.sha(entry), 'mode': oct(mode)}
    return files


def require_calibration(exit_code, guest, _role):
    statuses = guest['test_statuses']
    assert exit_code == guest['verifier_exit_code'] == 0
    assert guest['passed'] is True and guest['upstream_binary_reward'] == 1
    assert guest['phase'] == 'complete' and guest['solver_replayed'] is False
    assert not guest['missing_collected'] and guest['unexpected_collected_count'] == 0
    expected = runner.read(POSITIVE / 'result.json')['observed']['test_statuses']
    assert statuses == expected and len(statuses) == 11
    assert (guest['uid'], guest['gid']) == (65534, 65534)
    peak = guest['peak_used_bytes_above_start']
    assert set(peak) == {'/tmp', '/dev/shm'} and all(type(value) is int and value >= 0 for value in peak.values())
    assert 0 < peak['/tmp'] <= 1024 * 1024**2 and peak['/dev/shm'] <= 256 * 1024**2


def freeze():
    old = runner.read(POSITIVE / 'operation-review.json')
    observed = runner.read(POSITIVE / 'result.json')
    assert observed['passed'] and observed['cleanup_verified']
    assert observed['observed']['upstream_binary_reward'] == 1
    assert all(runner.sha(path) == digest for path, digest in old['assets'].items())
    assert shutil.disk_usage(ROOT).free >= 52 * 1024**3
    extraction = WORK / 'browser-extraction.json'
    chromium = runner.read(extraction)
    browser = Path(chromium['browser_path'])
    assert chromium['image_id'] == old['image'] and chromium['container_remained_created']
    assert browser_manifest(browser) == chromium['files']

    program = REFERENCE.read_text()
    changes = {
        "assert os.geteuid()==0 and not os.access": "assert os.geteuid()==os.getegid()==65534 and not os.access",
        "'PLAYWRIGHT_BROWSERS_PATH':'/root/.cache/ms-playwright'":
            "'PLAYWRIGHT_BROWSERS_PATH':'/opt/aeep-react-browser'",
    }
    for before, after in changes.items():
        assert program.count(before) == 1
        program = program.replace(before, after)
    adapted = WORK / 'nonroot-reference.py'
    with adapted.open('x') as stream:
        stream.write(program)
    adapted.chmod(0o444)
    compile(program, str(adapted), 'exec')

    argv = old['argv'][:]
    assert argv[argv.index('--user') + 1] == '0:0'
    argv[argv.index('--user') + 1] = '65534:65534'
    name = 'aeep-react-nonroot-calibration-20261108'
    argv[argv.index('--name') + 1] = name
    original_mount = f'type=bind,src={REFERENCE},dst=/opt/aeep-react-reference.py,readonly'
    argv[argv.index(original_mount)] = f'type=bind,src={adapted},dst=/opt/aeep-react-reference.py,readonly'
    entry = HERE / 'observe.py'
    argv[argv.index('--entrypoint'):argv.index('--entrypoint')] = [
        '--mount', f'type=bind,src={browser},dst=/opt/aeep-react-browser,readonly',
        '--mount', f'type=bind,src={entry},dst=/opt/aeep-react-observe.py,readonly',
    ]
    assert argv[-1] == '/opt/aeep-react-reference.py'
    argv[-1] = '/opt/aeep-react-observe.py'
    assets = old['assets'] | {
        str(path): runner.sha(path) for path in
        (Path(__file__), entry, adapted, extraction, CASE_DRIVER, POSITIVE / 'result.json',
         POSITIVE / 'operation-review.json', HERE.parent / 'skillsbench-react-managed-preparation-20261107/result.json')
    }
    review = old | {
        'scope': 'One existing React reference under UID/GID 65534 with read-only browser files and measured scratch.',
        'argv': argv, 'container_name': name, 'grant_id': 'skillsbench-react-nonroot-calibration-20261108',
        'expected_failure': 'calibration', 'assets': assets, 'source_sha256': verification_source_digest(ROOT),
        'browser_extraction': str(extraction), 'browser_files': len(chromium['files']),
        'expires_at': (utc_now()+timedelta(hours=8)).isoformat(),
        'maximum_operations': 1, 'maximum_reserved_seconds': 360,
        'reference_reused': True, 'solver_replay': False,
        'automatic_retries': False, 'comparisons': 'PAUSED',
    }
    runner.write(HERE / 'operation-review.json', review)


def preflight(review, digest):
    assert runner.sha(HERE / 'operation-review.json') == digest
    assert not (HERE / 'started.json').exists()
    assert datetime.fromisoformat(review['expires_at']) > utc_now()
    assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
    assert verification_source_digest(ROOT) == review['source_sha256']
    assert all(runner.sha(path) == expected for path, expected in review['assets'].items())
    chromium = runner.read(Path(review['browser_extraction']))
    assert browser_manifest(Path(chromium['browser_path'])) == chromium['files']
    assert review['maximum_operations'] == 1 and review['models'] == 0 and not review['automatic_retries']
    fixture = runner.read(POSITIVE/'result.json')['observed'] | {
        'uid': 65534, 'gid': 65534, 'peak_used_bytes_above_start': {'/tmp': 1024, '/dev/shm': 0},
    }
    require_calibration(0, fixture, 'calibration')
    try:
        require_calibration(0, fixture | {'uid': 0}, 'calibration')
    except AssertionError:
        pass
    else:
        raise AssertionError('Calibration accepted an unreviewed root process')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze', action='store_true')
    mode.add_argument('--preflight')
    mode.add_argument('--execute-approved')
    args = parser.parse_args()
    if args.freeze:
        freeze()
    path = HERE / 'operation-review.json'
    digest = runner.sha(path) if args.freeze else args.preflight or args.execute_approved
    review = runner.read(path)
    preflight(review, digest)
    if args.execute_approved:
        assert runner.read(HERE / 'operator-approval.json') == {'approved': True, 'review_sha256': digest}
        runner.validate_negative = require_calibration
        result = asyncio.run(runner.run(review, digest))
        raise SystemExit(not result['passed'])
    print(json.dumps({'passed': True, 'review_sha256': digest, 'models': 0, 'guest_executed': False}))
