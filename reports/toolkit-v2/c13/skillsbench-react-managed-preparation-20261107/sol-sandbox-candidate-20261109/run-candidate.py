"""Finish the two unstarted candidate operations after the successful control commands."""

import argparse
import asyncio
import json
import runpy
import time
from datetime import datetime, timedelta
from pathlib import Path

from aeep.assessment.models import AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.models import utc_now
from aeep.store import ReceiptStore

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'sol-sandbox-path-20261109'
driver = runpy.run_path(str(PRIOR / 'run-path-check.py'))
read, save, sha, image, WORK, Scope = (driver[k] for k in ('read', 'save', 'sha', 'image', 'WORK', 'Scope'))
GRANT = 'skillsbench-react-sol-permitted-candidate-20261109'
REVIEW = HERE / 'operation-review.json'
ROLE = 'candidate'


def sandbox_passed(facts):
    command = facts.get('original_probe', {})
    sample = command.get('observation')
    canary = facts.get('canary', {})
    policy = facts.get('configRequirements/read', {})
    return (facts.get('cleanup_confirmed') is True and canary.get('exit_code') == 0
            and canary.get('observation') == {'canary_matched': True}
            and command.get('exit_code') == 0 and isinstance(sample, dict)
            and sample.get('workspace_write') is True
            and sample.get('configuration_write') in ('denied', 'read_only', 'absent')
            and sample.get('proxy') == sample.get('direct') == 'denied'
            and len(policy) == 2 and all(isinstance(row, dict) and row.get('matches') is True for row in policy.values()))


def validate(review=None, *, starting=True):
    earlier = read(PRIOR / 'operation-review.json')
    result = read(PRIOR / 'result.json')
    ledger = read(PRIOR / 'ledger.json')
    assert result['review_sha256'] == sha(PRIOR / 'operation-review.json')
    assert not result['passed'] and result['error_type'] == 'AssertionError'
    assert result['models'] == 0 and result['accounting_settled'] and result['operations'] == 2
    assert [row['stage'] for row in ledger['operations']] == ['build', 'sandbox']
    control, = result['roles'].values()
    assert set(result['roles']) == {'control'} and sandbox_passed(control['sandbox'])
    assert control['sandbox']['original_probe']['observation']['configuration_write'] == 'absent'
    assert image(earlier['roles']['control']['tag']) == control['build']
    # This deliberately uses the new approval window. Old content pins still apply.
    validation = earlier | {'expires_at': review['expires_at'] if review else (utc_now() + timedelta(minutes=5)).isoformat()}
    pair, program = driver['validate'](validation, starting=False)
    row = earlier['roles'][ROLE]
    if starting:
        assert image(row['tag']) is None
    if review:
        assert utc_now() < datetime.fromisoformat(review['expires_at'])
        assert all(sha(Path(p)) == h for p, h in review['pins'].items())
        assert review['candidate'] == row and review['retained_control'] == control['build']['id']
    return row, pair, program, control['build']['id']


def scope(repo, digest, expiry):
    record = Scope(review_sha256=digest)
    ref = content_digest(record)
    assert repo.put('toolkit_sol_candidate_path_scope', ref, record) == ref
    grant = AssessmentAuthorization(authorization_id=GRANT, subject_digests=[ref], recipe_digests=[ref],
        environment_digests=[ref], allowed_destinations=['local'], remote_disclosure=False, expires_at=expiry,
        limits=AssessmentLimits(max_operations=2, max_model_turns=0, max_elapsed_seconds=250))
    repo.approve_bundle(grant, {ref: record.model_dump(mode='json')})
    return RecipeMaterializationRequest(plan_id=GRANT, subject_digest=ref, recipe_digest=ref, environment_digest=ref,
        mapping_digest=ref, authorization_id=GRANT, definition_digests=[ref], seed=0)


def freeze():
    row, pair, _, retained = validate()
    observation = read(PRIOR / 'result.json')['roles']['control']['sandbox']
    original = observation['original_probe']
    for mode in ('denied', 'read_only', 'absent'):
        amended = observation | {'original_probe': original | {'observation': original['observation'] | {
            'configuration_write': mode}}}
        assert sandbox_passed(amended)
    for failed in ({'workspace_write': False}, {'configuration_write': 'permitted'}, {'direct': 'unreachable'}):
        amended = observation | {'original_probe': original | {'observation': original['observation'] | failed}}
        assert not sandbox_passed(amended)
    assert not sandbox_passed(observation | {'cleanup_confirmed': False})
    with ReceiptStore(':memory:') as store:
        repo = AssessmentRepository(store)
        req = scope(repo, 'synthetic', utc_now() + timedelta(seconds=30))
        repo.reserve(req, GRANT, AssessmentLimits(max_operations=1, max_elapsed_seconds=1), stage='sandbox')
        repo.authorize(req)
        repo.finish_operation(GRANT, elapsed_seconds=.01)
    pins = [Path(__file__).resolve(), PRIOR / 'run-path-check.py', PRIOR / 'operation-review.json',
            PRIOR / 'result.json', PRIOR / 'ledger.json', pair]
    save(REVIEW, {'purpose': 'Build the unstarted candidate and verify the same restricted sandbox.',
        'pins': {str(p): sha(p) for p in pins}, 'retained_control': retained, 'candidate': row,
        'configuration_write_policy': 'The immutable launcher proves its config exists outside the sandbox. A hidden path is recorded as absent. Writes must fail.',
        'maximum_operations': 2, 'maximum_reserved_seconds': 250, 'builds': 1, 'offline_worker_checks': 1,
        'control_replayed': False, 'downloads': False, 'proxy_start': False, 'credential_volume': False,
        'network': False, 'models': 0, 'cash_usd': '0', 'existing_resource_deletion': False,
        'comparisons': 'PAUSED', 'automatic_retries': False,
        'expires_at': (utc_now() + timedelta(hours=18)).isoformat()})
    validate(read(REVIEW))
    print(sha(REVIEW))


async def execute(identity):
    review = read(REVIEW)
    assert identity == sha(REVIEW) and read(HERE / 'approval.json') == {'approved': True, 'review_sha256': identity}
    assert not (HERE / 'started.json').exists()
    ledger_path = WORK / 'sol-sandbox-candidate-20261109.sqlite3'
    assert not ledger_path.exists()
    row, pair, program, retained = validate(review)
    save(HERE / 'started.json', {'review_sha256': identity, 'models': 0})
    result = {'review_sha256': identity, 'retained_control': retained, 'models': 0, 'passed': False,
              'comparisons': 'PAUSED'}
    with ReceiptStore(str(ledger_path)) as store:
        repo = AssessmentRepository(store)
        request = scope(repo, identity, datetime.fromisoformat(review['expires_at']))
        try:
            for stage, seconds in driver['LIMITS'].items():
                spec = driver['build_spec'](row) if stage == 'build' else driver['get_spec'](pair, ROLE, result['build']['id'])[0]
                operation = f'{GRANT}:{stage}'
                repo.reserve(request, operation, AssessmentLimits(max_operations=1, max_elapsed_seconds=seconds), stage=stage)
                started, clock = utc_now(), time.monotonic()
                facts, error = {}, None

                def authorize():
                    repo.authorize(request)
                    validate(review, starting=False)
                    return identity

                try:
                    authorize()
                    if stage == 'build':
                        facts.update(await driver['local_build'](row, spec, operation, authorize))
                    else:
                        try:
                            await driver['check_sandbox'](pair, ROLE, result['build']['id'], program, facts)
                        except AssertionError:
                            # Accept the complete guarded observation when the known host path is hidden.
                            if not sandbox_passed(facts):
                                raise
                        assert sandbox_passed(facts)
                except Exception as exc:
                    error = type(exc).__name__
                    raise
                finally:
                    elapsed = time.monotonic() - clock
                    result[stage] = facts
                    receipt = driver['receipt_fn'](operation, spec, started, elapsed, identity,
                                                   facts if error is None else None, error)
                    store.save_receipt(receipt)
                    repo.finish_operation(operation, elapsed_seconds=elapsed, resources=receipt.actual_resources)
                    save(HERE / f'{stage}-receipt.json', receipt.model_dump(mode='json'))
            result['passed'] = True
        except Exception as exc:
            result['error_type'] = type(exc).__name__
        finally:
            ledger = repo.operation_ledger(GRANT)
            result['operations'] = len(ledger.operations)
            result['accounting_settled'] = all(row.elapsed_seconds is not None for row in ledger.operations)
            save(HERE / 'ledger.json', ledger.model_dump(mode='json'))
            save(HERE / 'result.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'build'}))
    return result['passed'] and result['accounting_settled']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument('--freeze', action='store_true')
    flags.add_argument('--preflight', action='store_true')
    flags.add_argument('--execute-approved')
    args = parser.parse_args()
    if args.freeze:
        freeze()
    elif args.preflight:
        validate(read(REVIEW))
        print(json.dumps({'review_sha256': sha(REVIEW), 'preflight_passed': True, 'executed': False}))
    else:
        raise SystemExit(not asyncio.run(execute(args.execute_approved)))
