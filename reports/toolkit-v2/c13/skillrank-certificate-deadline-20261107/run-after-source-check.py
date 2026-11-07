"""Resume the unstarted native build after repairing only a source-test fixture."""

import argparse
import asyncio
import importlib.util
import json
from datetime import datetime
from pathlib import Path

from aeep.models import utc_now

HERE = Path(__file__).resolve().parent
REVIEW = HERE / 'source-continuation-review.json'
spec = importlib.util.spec_from_file_location('approved_deadline_build', HERE / 'build-and-check.py')
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)
builder = original.builder
FIXTURE = original.ROOT / 'tests/test_toolkit_prompt_binding.py'


def freeze():
    old = builder.read(original.REVIEW)
    previous = builder.sha(original.REVIEW)
    assert builder.read(HERE / 'operator-approval.json') == {'approved': True, 'review_sha256': previous}
    failure = builder.read(original.WORK / 'verification-prompt-fixture-failure/checks.json')
    assert failure['source_before'] == failure['source_after'] == old['implementation_source']
    assert failure['checks'][-1]['name'] == 'pytest' and failure['checks'][-1]['exit_code'] == 1
    source = builder.verification_source_digest(original.ROOT)
    assert source != old['implementation_source']
    builder.write(REVIEW, {
        'scope': 'Continue the approved, unstarted offline native build and scheduler check after one test-only correction.',
        'parent_review_sha256': previous,
        'expires_at': old['expires_at'],
        'implementation_source': source,
        'previous_source': old['implementation_source'],
        'changed_test_fixture': str(FIXTURE),
        'failure_reason': 'A short sample payload matched a substring inside a permitted hexadecimal digest.',
        'files': {str(path): builder.sha(path) for path in
                  (FIXTURE, Path(__file__), original.WORK / 'verification-prompt-fixture-failure/checks.json')},
        'limits_unchanged': {key: old[key] for key in ('maximum_operations', 'maximum_reserved_seconds', 'model_turns', 'cash_usd')},
        'native_inputs_unchanged': True,
        'automatic_retries': False,
        'comparisons': 'PAUSED',
    })


def validate(review, digest):
    old = builder.read(original.REVIEW)
    assert builder.sha(REVIEW) == digest
    assert review['parent_review_sha256'] == builder.sha(original.REVIEW)
    assert builder.read(HERE / 'operator-approval.json') == {'approved': True, 'review_sha256': review['parent_review_sha256']}
    assert datetime.fromisoformat(review['expires_at']) > utc_now()
    assert all(builder.sha(Path(path)) == expected for path, expected in review['files'].items())
    assert builder.verification_source_digest(original.ROOT) == review['implementation_source']
    assert old['implementation_source'] == review['previous_source']
    assert old['review_artifacts'] == original.bindings()
    assert not (HERE / 'dispatch-intent.json').exists()
    original.configure()
    assert old['input_bindings'] == builder.inputs()
    assert not builder.BINARY.exists()
    return old | {'implementation_source': review['implementation_source']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze', action='store_true')
    mode.add_argument('--preflight')
    mode.add_argument('--execute-approved')
    args = parser.parse_args()
    if args.freeze:
        freeze()
        print(builder.sha(REVIEW))
    else:
        review = builder.read(REVIEW)
        digest = args.preflight or args.execute_approved
        effective = validate(review, digest)
        if args.preflight:
            print(json.dumps({'passed': True, 'review_sha256': digest, 'models': 0, 'dispatch': False}))
        else:
            assert builder.read(HERE / 'source-continuation-approval.json') == {'approved': True, 'review_sha256': digest}
            checks = builder.read(original.VERIFY)
            assert checks['source_before'] == checks['source_after'] == effective['implementation_source']
            assert len(checks['checks']) == 13 and all(item['exit_code'] == 0 for item in checks['checks'])
            build = asyncio.run(builder.execute(effective, digest))
            if not build['passed']:
                raise SystemExit(1)
            original.check_runtime(effective, digest, build)
