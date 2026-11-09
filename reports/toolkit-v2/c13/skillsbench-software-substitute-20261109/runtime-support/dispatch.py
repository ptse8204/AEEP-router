"""Bind the approved dispatch separately from its pinned preflight."""

import argparse
import asyncio
import json
import runpy
from pathlib import Path

OUT = Path(__file__).resolve().parent
runtime = runpy.run_path(str(OUT.parent / 'with-runtime-support.py'))
read, sha = runtime['read'], runtime['sha']
REVIEW, PRIVATE, GRANT = (runtime[key] for key in ('REVIEW', 'PRIVATE', 'GRANT'))


class BeforeStart(Exception):
    pass


def bind(digest):
    assert sha(REVIEW) == digest
    assert read(OUT / 'approval.json') == {'approved': True, 'review_sha256': digest}
    assert not (OUT / 'started.json').exists()
    assert not (PRIVATE / 'calibration-continuation.sqlite3').exists()
    # A fresh namespace keeps the prior preflight's grant and fingerprint intact.
    entry = runpy.run_path(str(OUT.parent / 'continue-calibration.py'))['execute']
    entry.__globals__.update(
        OUT=OUT, REVIEW=REVIEW, PRIVATE=PRIVATE, GRANT=GRANT,
        preflight=runtime['preflight'], context=runtime['runner']['context'],
    )
    return entry


async def check(digest):
    entry = bind(digest)

    def stop(path, value):
        assert path == OUT / 'started.json'
        assert value == {'review_sha256': digest, 'models': 0}
        assert all(
            entry.__globals__['context'](case).attempt_id == f'{GRANT}:{case}'
            for case in read(REVIEW)['cases']
        )
        raise BeforeStart

    entry.__globals__['save'] = stop
    try:
        await entry(digest)
    except BeforeStart:
        return
    raise AssertionError('dispatch did not reach the start-record boundary')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preflight')
    mode.add_argument('--execute-approved')
    args = parser.parse_args()
    digest = args.preflight or args.execute_approved
    asyncio.run(check(digest))
    if args.preflight:
        print(json.dumps({'review_sha256': digest, 'checked_through_start_record_boundary': True,
                          'execution_started': False, 'operations': 0, 'models': 0}))
    else:
        raise SystemExit(not asyncio.run(bind(digest)(digest)))
