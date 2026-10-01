"""One reviewed, turn-free workbook pair inspection; never replay a started request."""

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_pair_inspection import execute_pair
from aeep.router import Router


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / 'reports/v08'
BASE = ROOT / '.aeep/live-review-v3'
SOURCE = '288e082274cf22631398ca404180f6b58cb27ed7d5654fec0420d1ee6a0a2782'
START = REPORTS / 'sol-workbook-current-source-pair-start-288e.json'
RESULT = REPORTS / 'sol-workbook-current-source-pair-result-288e.json'
FAILURE = REPORTS / 'sol-workbook-current-source-pair-failure-288e.json'


def save_exclusive(path: Path, value: dict) -> None:
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


async def main() -> None:
    start = json.loads(START.read_text())
    review_path = REPORTS / 'sol-workbook-current-source-review-288e.json'
    review_bytes = review_path.read_bytes()
    review = json.loads(review_bytes)
    assert verification_source_digest(ROOT) == SOURCE == start['source_digest'] == review['source_digest']
    assert hashlib.sha256(review_bytes).hexdigest() == start['review_sha256']
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == start['driver_sha256']
    request_ids = review['request_ids']
    assert len(request_ids) == 2 and request_ids == start['request_ids']
    assert not RESULT.exists() and not FAILURE.exists()
    router = Router.from_manifest(BASE / 'aeep.json')
    try:
        service = AssessmentService(router, BASE / '.aeep/assessments')
        try:
            async with asyncio.timeout(600):
                pair = await execute_pair(service, *request_ids)
            workers = {}
            for role in ('control', 'treatment'):
                record = service.repository.get('worker_pair_inspection', pair['workers'][role]['record_digest'])
                inspection = record['observations']['inspection']
                sol = [item for item in inspection['models'] if item['id'] == 'gpt-6-sol']
                workers[role] = {
                    'cleanup_confirmed': record['observations'].get('cleanup_confirmed'),
                    'sol_present': len(sol) == 1,
                    'sol_medium_high_available': len(sol) == 1 and
                        {'medium', 'high'}.issubset(sol[0]['reasoning_efforts']),
                    'identity_digest': inspection['identity_digest'],
                }
            grant = router.store._connection.execute(
                'SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',
                (start['grant_id'],),
            ).fetchone()
            result = {
                'recorded_at': datetime.now(timezone.utc).isoformat(),
                'source_digest': SOURCE,
                'request_ids': request_ids,
                'pair': pair,
                'workers_summary': workers,
                'grant_after': dict(zip(('operations', 'model_turns', 'elapsed_seconds', 'cash_usd'), grant)),
                'source_unchanged': verification_source_digest(ROOT) == SOURCE,
                'model_task_calls': 0,
                'release_ready': False,
            }
            save_exclusive(RESULT, result)
            if not pair.get('probes_match') or not all(item['cleanup_confirmed'] for item in workers.values()):
                raise RuntimeError('paired inspection incomplete; preserve result and do not replay')
            print(json.dumps({'passed': True, 'request_ids': request_ids,
                              'sol_available': all(item['sol_medium_high_available'] for item in workers.values()),
                              'grant_operations': grant[0]}))
        except BaseException as exc:
            if not RESULT.exists():
                grant = router.store._connection.execute(
                    'SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',
                    (start['grant_id'],),
                ).fetchone()
                save_exclusive(FAILURE, {
                    'recorded_at': datetime.now(timezone.utc).isoformat(),
                    'source_digest': SOURCE,
                    'request_ids': request_ids,
                    'error_type': type(exc).__name__,
                    'grant_after': dict(zip(('operations', 'model_turns', 'elapsed_seconds', 'cash_usd'), grant)),
                    'replay_allowed': False,
                })
            raise
    finally:
        await router.close()


asyncio.run(main())
