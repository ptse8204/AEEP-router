"""Verify the real native child in the ordinary coordinator with synthetic grades."""

import argparse
import asyncio
import hashlib
import json
import shutil
import sys
from pathlib import Path

from pytest import MonkeyPatch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]

from aeep.assessment.verification import verification_source_digest
from aeep.benchmarking import BenchmarkTrial
from aeep_toolkit.skillrank_scheduler import SkillRankCoordinator
from test_toolkit_ase_scheduler import external_plan


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


async def dispatch(service, plan, coordinator):
    async def fixture(slot):
        # Actual managed-worker conformance is a separate gate. No model is
        # dispatched here. The protected interface is exercised with one
        # passing and one failing first-party binary grade.
        return BenchmarkTrial(
            trial_id='fixture-' + slot, run_id='offline-native-check',
            suite_id=plan.suite.suite_id, case_id=plan.suite.cases[0].case_id,
            route_id=(plan.baseline_id, plan.candidate_id)[int(slot)],
            condition='fresh-worker', repetition=0, phase='qualification',
            state='complete', valid=slot == '0',
        )

    await coordinator.coordinate(('0', '1'), fixture)
    return service.repository.get('scheduler_observation', plan.plan_id)


def run(review, identity):
    assert review['source_sha256'] == verification_source_digest(ROOT)
    for path, digest in review['assets'].items():
        assert sha(path) == digest, path
    assert review['maximum_actual_upstream_processes'] == 1
    assert review['models'] == 0 and review['cash_usd'] == '0'
    assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
    work = Path(review['owned_work'])
    assert not work.exists() and not work.is_symlink()
    work.mkdir(mode=0o700)
    write(HERE / 'native-check-started.json', {'review_sha256': identity})
    result = {'passed': False, 'models': 0, 'engineering_fixture': True, 'review_sha256': identity}
    try:
        with MonkeyPatch.context() as patch:
            service, plan, definition, _ = external_plan(
                work, patch, engine='skillrank', native_binary=Path(review['binary']),
            )
            try:
                coordinator = SkillRankCoordinator(service.repository, plan)
                result['definition_ref'] = coordinator.definition_digest
                result['plan_schema'] = plan.schema_version
                assert definition.artifact_sha256 == review['assets'][review['binary']]
                record = asyncio.run(dispatch(service, plan, coordinator))
                assert record['grade_summaries']['0']['passed'] == 1
                assert record['grade_summaries']['1']['failed'] == 1
                assert record['upstream_timing_is_compatibility_only'] is True
                assert len(record['trial_refs']) == 2
                result['scheduler_observation'] = record
                result['passed'] = True
            finally:
                ledger = service.repository.operation_ledger(plan.plan_id).model_dump(mode='json')
                result['accounting_settled'] = (
                    len(ledger['operations']) == 1
                    and ledger['operations'][0]['elapsed_seconds'] is not None
                )
                result['passed'] &= result['accounting_settled']
                write(HERE / 'native-check-ledger.json', ledger)
                service.router.store.close()
    except Exception as failure:
        result['error_type'] = type(failure).__name__
        raise
    finally:
        write(HERE / 'native-check-result.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute-delegated', required=True)
    args = parser.parse_args()
    path = HERE / 'native-check-review.json'
    identity = sha(path)
    authority = json.loads((HERE / 'native-check-authority.json').read_bytes())
    assert args.execute_delegated == identity == authority['review_sha256']
    assert authority['first_native_coordinator_check'] is True
    assert sha(HERE.parent / 'pipeline-standing-authority-20261104.json') == authority['standing_authority_sha256']
    outcome = run(json.loads(path.read_bytes()), identity)
    print(json.dumps(outcome))
    raise SystemExit(not outcome['passed'])
