"""Pin two new negative inputs for the already verified React verifier."""

import argparse
import asyncio
import copy
import importlib.util
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from aeep.models import utc_now

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
PRIOR = HERE.parent / 'browser-id-continuation'
WORK = ROOT / '.aeep/skillsbench-react-reference-20261106'
ORIGINAL = WORK / 'browser-id-continuation/protected'
ORIGINAL_CHECKOUT = 'src/app/api/checkout/route.ts'
ADVANCED_COMPONENT = 'src/components/AdvancedAnalysis.tsx'
CASES = {
    'incomplete': 'test_outputs.py::TestAPIPerformance::test_checkout_fast',
    'destructive': 'test_outputs.py::TestFunctionality::test_compare_page_works[chromium]',
}


def load_case():
    spec = importlib.util.spec_from_file_location('reviewed_react_control', HERE / 'run-case.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


case_driver = load_case()


def freeze():
    positive = case_driver.read(PRIOR / 'result.json')
    assert positive['passed'] and positive['observed']['upstream_binary_reward'] == 1
    assert positive['cleanup_verified'] and len(positive['observed']['test_statuses']) == 11
    old = case_driver.read(PRIOR / 'operation-review.json')
    assert all(case_driver.sha(path) == value for path, value in old['assets'].items())
    assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
    inherited = {str(path): case_driver.sha(path) for path in
                 (Path(__file__), HERE / 'run-case.py', PRIOR / 'operation-review.json', PRIOR / 'result.json')}
    shared = {**old['assets'], **inherited}
    review = {'positive_review_sha256': case_driver.sha(PRIOR / 'operation-review.json'),
              'scope': 'Two new offline React controls, retaining the original verifier and all eleven assertions.',
              'maximum_operations': 2, 'maximum_reserved_seconds': 720, 'models': 0, 'cash_usd': '0',
              'automatic_retries': False, 'comparisons': 'PAUSED', 'cases': {}}
    expires = (utc_now() + timedelta(hours=8)).isoformat()
    review['expires_at'] = expires
    for role, expected in CASES.items():
        protected = WORK / 'negative-controls' / role / 'protected'
        shutil.copytree(ORIGINAL, protected)
        manifest = copy.deepcopy(case_driver.read(ORIGINAL / 'pins.json'))
        if role == 'incomplete':
            # The image's pinned original implementation remains in the private checkout.
            manifest['patches'].pop(ORIGINAL_CHECKOUT)
            (protected / 'patches' / ORIGINAL_CHECKOUT).unlink()
        else:
            path = protected / 'patches' / ADVANCED_COMPONENT
            data = path.read_bytes()
            marker = b'data-testid="advanced-content"'
            assert data.count(marker) == 1
            path.chmod(0o644)
            path.write_bytes(data.replace(marker, b'data-testid="broken-advanced-content"'))
            path.chmod(0o444)
            manifest['patches'][ADVANCED_COMPONENT] = case_driver.sha(path)
        pins = protected / 'pins.json'
        pins.chmod(0o644)
        pins.write_text(json.dumps(manifest, indent=2)+'\n')
        pins.chmod(0o444)
        name = 'aeep-react-negative-20261107-' + role
        assets = {**shared, **{str(path): case_driver.sha(path) for path in protected.rglob('*') if path.is_file()}}
        argv = [arg.replace(str(ORIGINAL), str(protected)) if arg.startswith('type=bind,') else arg
                for arg in old['argv']]
        argv[argv.index('--name') + 1] = name
        review['cases'][role] = old | {
            'assets': assets, 'argv': argv, 'container_name': name, 'expires_at': expires,
            'grant_id': 'skillsbench-react-negative-20261107-' + role, 'expected_failure': expected,
        }
    case_driver.write(HERE / 'operation-review.json', review)


def validate_controls(review, digest):
    assert case_driver.sha(HERE / 'operation-review.json') == digest
    assert datetime.fromisoformat(review['expires_at']) > utc_now()
    assert tuple(review['cases']) == tuple(CASES)
    for role, item in review['cases'].items():
        assert item['expected_failure'] == CASES[role]
        assert not (HERE / role).exists()
        assert all(case_driver.sha(path) == sha for path, sha in item['assets'].items())


def preflight(review):
    positive = case_driver.read(PRIOR / 'result.json')['observed']
    for role, item in review['cases'].items():
        expected = item['expected_failure']
        guest = positive | {'verifier_exit_code': 1, 'upstream_binary_reward': 0, 'passed': False,
                            'test_statuses': positive['test_statuses'] | {expected: 'FAILED'}}
        case_driver.validate_negative(1, guest, expected)
        for exit_code, record in ((0, positive), (4, guest), (1, guest | {'test_statuses':
                                    guest['test_statuses'] | {expected: 'SKIPPED'}})):
            try:
                case_driver.validate_negative(exit_code, record, expected)
            except AssertionError:
                pass
            else:
                raise AssertionError(f'{role}: invalid synthetic outcome passed')
    print(json.dumps({'passed': True, 'controls': list(CASES), 'models': 0, 'synthetic': True}))


async def execute(review, digest):
    for role, item in review['cases'].items():
        case_driver.HERE = HERE / role
        case_driver.HERE.mkdir(mode=0o700)
        result = await case_driver.run(item, digest)
        if not result['passed'] or not result['cleanup_verified']:
            return False
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze', action='store_true')
    mode.add_argument('--preflight')
    mode.add_argument('--execute-approved')
    args = parser.parse_args()
    path = HERE / 'operation-review.json'
    if args.freeze:
        freeze()
        print(case_driver.sha(path))
    else:
        review = case_driver.read(path)
        digest = args.preflight or args.execute_approved
        validate_controls(review, digest)
        if args.preflight:
            preflight(review)
        else:
            assert case_driver.read(HERE / 'operator-approval.json') == {'approved': True, 'review_sha256': digest}
            raise SystemExit(not asyncio.run(execute(review, digest)))
