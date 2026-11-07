"""Reuse the reviewed offline native build and verify the longer callback envelope."""

import argparse
import asyncio
import functools
import importlib.util
import json
import shutil
from datetime import timedelta
from pathlib import Path

from aeep.models import utc_now

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'skillrank-native-carrier-20261105'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load('reviewed_native_carrier', PRIOR / 'run.py')
ROOT = builder.ROOT
OLD_WORK = builder.WORK
WORK = ROOT / '.aeep' / HERE.name
OLD_REVIEW = PRIOR / 'execution-review.json'
REVIEW = HERE / 'operation-review.json'
VERIFY = WORK / 'verification/checks.json'
CHECK = PRIOR / 'check-native-coordinator.py'


def bindings():
    return {str(path): builder.sha(path) for path in (
        Path(__file__), PRIOR / 'run.py', OLD_REVIEW, PRIOR / 'result.json', CHECK,
        ROOT / 'tests/test_toolkit_ase_scheduler.py',
        ROOT / 'schemas/assessment-scheduler.schema.json', HERE / 'verify-source.py',
    )}


def configure():
    builder.HERE = HERE
    builder.WORK = WORK
    builder.PROFILE = HERE / 'build.sb'
    builder.BINARY = WORK / builder.BINARY.relative_to(OLD_WORK)


def freeze(old):
    assert builder.read(PRIOR / 'result.json')['passed']
    assert builder.tree(OLD_WORK / 'source') == old['input_bindings']['source_tree']
    assert shutil.disk_usage(ROOT).free >= builder.RESERVE + 2 * 1024**3
    configure()
    for name in ('home', 'cargo', 'tmp', 'target'):
        (WORK / name).mkdir(mode=0o700)
    source = WORK / 'source'
    shutil.copytree(OLD_WORK / 'source', source, symlinks=True)
    entry = source / 'crates/skillrank/src/bin/aeep-skillrank-bridge.rs'
    entry_mode = entry.stat().st_mode & 0o777
    entry.chmod(entry_mode | 0o200)
    entry.write_bytes(builder.BRIDGE.read_bytes())
    entry.chmod(entry_mode)

    def replace(value):
        return value.replace(str(OLD_WORK), str(WORK)).replace(str(PRIOR), str(HERE))

    builder.PROFILE.write_text(replace((PRIOR / 'build.sb').read_text()))
    recorded = builder.inputs()
    assert builder.sha(source / 'Cargo.lock') == old['cargo_lock_sha256']
    for field in ('vendor_tree', 'rust_library_tree', 'apple_sdk_tree'):
        assert recorded[field] == old['input_bindings'][field], field
    old_artifacts = old['input_bindings']['artifacts']
    for path, digest in recorded['artifacts'].items():
        if path not in {str(builder.BRIDGE), str(builder.PROFILE)}:
            assert old_artifacts[path] == digest, path
    review = {
        **old, 'scope': 'One offline native rebuild and one actual SkillRank scheduler check on two synthetic grade certificates.',
        'predecessor_review_sha256': builder.sha(OLD_REVIEW),
        'expires_at': (utc_now() + timedelta(hours=8)).isoformat(),
        'implementation_source': builder.verification_source_digest(ROOT),
        'input_bindings': recorded, 'review_artifacts': bindings(),
        'cwd': str(source), 'argv': [replace(arg) for arg in old['argv']],
        'env': {key: replace(value) for key, value in old['env'].items()},
        'maximum_operations': 2, 'maximum_reserved_seconds': 900,
        'scheduler_check': {'certificate_timeout_seconds': 120, 'command_timeout_seconds': 260,
                            'evidence': 'Synthetic binary grades through the actual retained upstream implementation'},
        'comparisons': 'PAUSED',
    }
    builder.write(REVIEW, review)


def validate(review, identity):
    from datetime import datetime

    assert builder.sha(REVIEW) == identity
    assert datetime.fromisoformat(review['expires_at']) > utc_now()
    assert review['review_artifacts'] == bindings()
    assert review['input_bindings'] == builder.inputs()
    assert review['implementation_source'] == builder.verification_source_digest(ROOT)
    assert not (HERE / 'dispatch-intent.json').exists()
    assert not builder.BINARY.exists()
    assert review['model_turns'] == 0 and review['cash_usd'] == '0' and not review['automatic_retries']


def check_runtime(review, identity, build):
    check = load('existing_native_coordinator_check', CHECK)
    check.HERE = HERE / 'native-check'
    check.HERE.mkdir(mode=0o700)
    check.external_plan = functools.partial(check.external_plan, certificate_timeout=120)
    binary = build['binary']
    check_record = {'source_sha256': review['implementation_source'],
                    'assets': {binary: build['binary_sha256']},
                    'maximum_actual_upstream_processes': 1,
                    'models': 0, 'cash_usd': '0',
                    'owned_work': str(WORK / 'native-coordinator-check'), 'binary': binary}
    observation = check.run(check_record, identity)
    assert observation['passed'] and observation['accounting_settled']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze', action='store_true')
    mode.add_argument('--preflight')
    mode.add_argument('--execute-approved')
    args = parser.parse_args()
    if args.freeze:
        freeze(builder.read(OLD_REVIEW))
        print(builder.sha(REVIEW))
    else:
        configure()
        review = builder.read(REVIEW)
        identity = args.preflight or args.execute_approved
        validate(review, identity)
        if args.preflight:
            print(json.dumps({'passed': True, 'review_sha256': identity, 'models': 0, 'dispatch': False}))
        else:
            assert builder.read(HERE / 'operator-approval.json') == {'approved': True, 'review_sha256': identity}
            source_checks = builder.read(VERIFY)
            assert source_checks['source_before'] == source_checks['source_after'] == review['implementation_source']
            assert len(source_checks['checks']) == 13
            assert all(item['exit_code'] == 0 for item in source_checks['checks'])
            build = asyncio.run(builder.execute(review, identity))
            if not build['passed']:
                raise SystemExit(1)
            check_runtime(review, identity, build)
