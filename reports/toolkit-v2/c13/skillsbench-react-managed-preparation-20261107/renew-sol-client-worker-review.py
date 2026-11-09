"""Renew only the window for the approved, unstarted, offline Sol client refresh."""

import argparse
import asyncio
import runpy
from datetime import datetime, timedelta
from pathlib import Path

from aeep.models import utc_now

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE / 'sol-client-worker-review.json'
REVIEW = HERE / 'sol-client-worker-renewal.json'
DELEGATION = HERE.parent / 'pipeline-standing-authority-20261104.json'
OPERATOR_REPLY = HERE / 'sol-client-worker-operator-reply.json'
LOCAL_APPROVAL = HERE / 'sol-client-worker-approval.json'
STARTED = HERE / 'sol-client-worker-started.json'
ORIGINAL_SHA256 = '05ee81184c353230e66aa0b4f8373b41eb5d2d44bdcac988a8d3caf3fe17f806'

runner = runpy.run_path(str(HERE / 'review-sol-workers.py'))
read, sha, save = (runner[key] for key in ('read', 'sha', 'save'))


def original_review():
    assert sha(ORIGINAL) == ORIGINAL_SHA256
    assert read(OPERATOR_REPLY) == {'approved': True, 'review_sha256': ORIGINAL_SHA256}
    review = read(ORIGINAL)
    assert datetime.fromisoformat(review['expires_at']) < utc_now()
    assert review['models'] == 0 and review['cash_usd'] == '0'
    assert not any(review[key] for key in ('proxy_start', 'account_methods', 'network', 'downloads',
                                           'pulls', 'automatic_retries', 'existing_resource_deletion'))
    assert not STARTED.exists()
    return review


def additional_pins():
    return {str(path): sha(path) for path in (Path(__file__).resolve(), ORIGINAL, DELEGATION, OPERATOR_REPLY)}


def freeze():
    original = original_review()
    runner['check'](original)
    save(REVIEW, original | {
        'pins': original['pins'] | additional_pins(),
        'expires_at': (utc_now() + timedelta(hours=2)).isoformat(),
    })
    print(sha(REVIEW))


def execute(identity):
    assert sha(REVIEW) == identity
    original = original_review()
    renewal = read(REVIEW)
    assert renewal == original | {'pins': original['pins'] | additional_pins(),
                                  'expires_at': renewal['expires_at']}
    assert utc_now() < datetime.fromisoformat(renewal['expires_at']) <= utc_now() + timedelta(hours=2)
    runner['check'](renewal)
    save(HERE / 'sol-client-worker-renewal-authority.json', {
        'review_sha256': identity, 'operator_approved_review_sha256': ORIGINAL_SHA256,
        'delegation_sha256': sha(DELEGATION), 'first_attempt': True, 'change': 'expiry_only',
        'prior_operations': 0, 'prior_model_turns': 0,
    })
    save(LOCAL_APPROVAL, {'approved': True, 'review_sha256': identity})
    entry = runner['execute']
    entry.__globals__['REVIEW'] = REVIEW
    return asyncio.run(entry(identity))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument('--freeze', action='store_true')
    flags.add_argument('--execute-delegated')
    options = parser.parse_args()
    if options.freeze:
        freeze()
    else:
        raise SystemExit(not execute(options.execute_delegated))
