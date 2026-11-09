"""Reuse the React carrier's pinned Python support for the Prefix Cache grader."""

import argparse
import asyncio
import json
import runpy
from datetime import datetime, timedelta
from pathlib import Path

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import AssessmentEnvironment, content_digest
from aeep.models import utc_now

HERE = Path(__file__).resolve().parent
old = runpy.run_path(str(HERE / 'continue-calibration.py'))
read, save, sha, runner = (old[k] for k in ('read', 'save', 'sha', 'runner'))
ROOT = runner['ROOT']
PARENT = HERE.parent / 'skillsbench-react-readonly-grader-20261108'
PARENT_WORK = ROOT / '.aeep' / PARENT.name
PREVIOUS = HERE / 'continuation'
BOOT = HERE / 'bootstrap'
OUT = HERE / 'runtime-support'
REVIEW = OUT / 'operation-review.json'
PRIVATE = runner['PRIVATE'] / 'runtime-support'
GRANT = 'skillsbench-prefix-cache-with-carrier-support-20261109'


def support():
    observed = read(BOOT / 'result.json')
    assert observed['review_sha256'] == sha(BOOT / 'operation-review.json')
    assert observed['accounting_settled'] and observed['cleanup_confirmed']
    assert not observed['upstream_task_executed'] and observed['models'] == 0 and observed['exit_code'] == 1
    assert observed['stderr_categories'] == ['pydantic_import', 'python_import']
    retry = read(PREVIOUS / 'result.json')
    assert retry['review_sha256'] == sha(PREVIOUS / 'operation-review.json')
    assert not retry['passed'] and retry['operations'] == 1 and retry['accounting_settled'] and not retry['cases']
    prior = read(PREVIOUS / 'operation-review.json')
    valid = prior | {'expires_at': (utc_now() + timedelta(minutes=5)).isoformat()}
    env = old['preflight'](valid)
    carrier = read(PARENT / 'result.json')
    reviewed = read(PARENT / 'operation-review.json')
    assert carrier['review_sha256'] == sha(PARENT / 'operation-review.json') and carrier['passed']
    parent_env = AssessmentEnvironment.model_validate(read(PARENT / 'environment.json'))
    assert parent_env.container_image == env.container_image == reviewed['image']
    assert len(parent_env.read_only_roots) == 3
    path = Path(parent_env.read_only_roots[0])
    assert path.name == 'python' and path.resolve(strict=True) == path
    assert (path / 'pydantic/__init__.py').is_file()
    inventory = read(PARENT_WORK / 'mount-inventory.json')
    assert content_digest(inventory) == reviewed['mount_inventory_sha256']
    selected = {name: fact for name, fact in inventory.items() if Path(name).is_relative_to(path)}
    tree = {str(item) for item in (path, *path.rglob('*'))}
    assert tree == set(selected)
    for name, fact in selected.items():
        item = Path(name)
        assert not item.is_symlink() and item.stat().st_mode & 0o777 == fact['mode']
        if 'sha256' in fact:
            assert sha(item) == fact['sha256']
    environment = AssessmentEnvironment.model_validate(env.model_dump() | {
        'environment_id': GRANT, 'read_only_roots': [*env.read_only_roots, str(path)],
        'identity': {'scope': 'protected prefix cache reference', 'python_support_sha256': content_digest(selected)},
    })
    runner['context'].__globals__.update(GRANT=GRANT)
    for case in runner['CASES']:
        argv, _ = ContainerExecutor(environment).command(runner['context'](case))
        assert argv[argv.index('--network')+1] == 'none' and '--pull=never' in argv and '--read-only' in argv
        assert len([item for item in argv if item.startswith('type=bind,') and item.endswith(',readonly')]) == 4
        assert f'type=bind,src={path},dst={path},readonly' in argv
    return environment, prior, path, selected


def preflight(review):
    assert utc_now() < datetime.fromisoformat(review['expires_at'])
    assert all(sha(name) == digest for name, digest in review['runtime_support_pins'].items())
    environment, _, path, entries = support()
    assert review['python_support'] == str(path)
    assert review['python_support_entries'] == len(entries)
    assert review['environment_sha256'] == content_digest(environment)
    return environment


def freeze():
    environment, prior, path, entries = support()
    OUT.mkdir()
    PRIVATE.mkdir(mode=0o700)
    pins = [Path(__file__).resolve(), HERE / 'continue-calibration.py', PREVIOUS / 'operation-review.json',
            PREVIOUS / 'result.json', BOOT / 'operation-review.json', BOOT / 'result.json',
            PARENT / 'operation-review.json', PARENT / 'result.json', PARENT / 'environment.json',
            PARENT_WORK / 'mount-inventory.json']
    review = prior | {'purpose': 'Retry the protected reference with the known-good Python support, then run unstarted controls.',
        'runtime_support_pins': {str(p): sha(p) for p in pins}, 'python_support': str(path),
        'python_support_entries': len(entries), 'python_support_sha256': content_digest(entries),
        'environment_sha256': content_digest(environment), 'maximum_operations': 5, 'maximum_reserved_seconds': 275,
        'previous_charges_preserved': True, 'solver_verifier_inputs_unchanged': True,
        'expires_at': (utc_now() + timedelta(hours=18)).isoformat()}
    save(REVIEW, review)
    preflight(review)
    print(sha(REVIEW))


async def execute(digest):
    review = read(REVIEW)
    assert sha(REVIEW) == digest and read(OUT / 'approval.json') == {'approved': True, 'review_sha256': digest}
    preflight(review)
    entry = old['execute']
    entry.__globals__.update(OUT=OUT, REVIEW=REVIEW, PRIVATE=PRIVATE, GRANT=GRANT, preflight=preflight)
    return await entry(digest)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze', action='store_true')
    mode.add_argument('--preflight', action='store_true')
    mode.add_argument('--execute-approved')
    args = parser.parse_args()
    if args.freeze:
        freeze()
    elif args.preflight:
        preflight(read(REVIEW))
        print(json.dumps({'review_sha256': sha(REVIEW), 'preflight_passed': True, 'executed': False}))
    else:
        raise SystemExit(not asyncio.run(execute(args.execute_approved)))
