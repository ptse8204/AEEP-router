"""Run only the unstarted candidate smoke check on the audited retained image."""

import argparse
import asyncio
import json
import runpy
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

from aeep.assessment.models import AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, StrictModel, utc_now
from aeep.store import ReceiptStore

HERE = Path(__file__).resolve().parent
helper = runpy.run_path(str(HERE / 'continue-worker-runtime.py'))
old = helper['old']
sha, read, save, image = (helper[key] for key in ('sha', 'read', 'save', 'image'))
GRANT = 'skillsbench-react-candidate-smoke-20261108'
NAME = 'aeep-react-worker-smoke-candidate-20261108'
REVIEW = HERE / 'candidate-smoke-review.json'
FIRST = HERE / 'worker-runtime-review.json'


class Scope(StrictModel):
    review_sha256: str


def validate():
    prior = read(FIRST)
    outcome = read(HERE / 'worker-continuation-result.json')
    proof = read(HERE / 'worker-image-parity.json')
    assert outcome['new_accounting_settled'] and outcome['new_operations'] == 2
    assert list(outcome['smokes']) == ['control'] and outcome['smokes']['control']['typecheck_exit'] == 0
    assert proof['identical_dependency_bytes_modes_and_ownership'] and proof['matches_frozen_context']
    for role, row in prior['roles'].items():
        assert image(row['tag']) == proof['images'][role]
    assert all(sha(Path(path)) == pin for path, pin in prior['pins'].items())
    assert verification_source_digest(old['ROOT']) == prior['source_sha256']
    assert shutil.disk_usage(old['ROOT']).free >= old['FREE'] and old['absent'](NAME)
    payload = old['public_input']()
    assert content_digest(payload) == prior['public_input_sha256']
    return prior, proof['images']['candidate']['id'], payload


def specification(identity):
    return helper['spec_for']('smoke', [
        'run', '--rm', '--pull=never', '--network=none', '--read-only', '--user', '65534:65534',
        '--cap-drop=ALL', '--security-opt=no-new-privileges', '--memory=1024m', '--memory-swap=1024m',
        '--cpus=2', '--pids-limit=192', '--log-driver=none', '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=128m',
        '--workdir', '/tmp', '--name', NAME, '--label', 'aeep.react-smoke=' + old['GRANT'], '-i',
        '--entrypoint', 'python3', identity, '-I', '-B', '-c', (HERE / 'worker-smoke.py').read_text(),
    ], stdin_json=True)


def freeze():
    prior, image_id, payload = validate()
    spec = specification(image_id)
    pins = [Path(__file__).resolve(), FIRST, HERE / 'worker-image-parity.json', HERE / 'audit-worker-files.py',
            HERE / 'continue-worker-runtime.py', HERE / 'worker-continuation-review.json',
            HERE / 'worker-continuation-result.json', HERE / 'worker-continuation-ledger.json']
    save(REVIEW, {
        'scope': 'One unstarted offline candidate smoke check using the retained ARM64 worker.',
        'pins': {str(path): sha(path) for path in pins}, 'image': image_id,
        'spec_digest': content_digest(spec), 'public_input_sha256': content_digest(payload),
        'source_sha256': prior['source_sha256'], 'maximum_operations': 1, 'maximum_reserved_seconds': 75,
        'preserve_original_150_second_reservation': True, 'builds': 0, 'models': 0, 'cash_usd': '0',
        'network': False, 'provider_transfer': False, 'automatic_retries': False,
        'existing_resource_deletion': False, 'comparisons': 'PAUSED',
        'expires_at': (utc_now() + timedelta(hours=12)).isoformat(),
    })
    print(sha(REVIEW))


async def execute(identity):
    review = read(REVIEW)
    assert sha(REVIEW) == identity
    assert read(HERE / 'candidate-smoke-approval.json') == {'approved': True, 'review_sha256': identity}
    assert not (HERE / 'candidate-smoke-started.json').exists()
    expiry = datetime.fromisoformat(review['expires_at'])
    assert utc_now() < expiry
    assert all(sha(Path(path)) == digest for path, digest in review['pins'].items())
    _, image_id, payload = validate()
    spec = specification(image_id)
    assert image_id == review['image'] and content_digest(spec) == review['spec_digest']
    assert content_digest(payload) == review['public_input_sha256']
    scope = Scope(review_sha256=identity)
    digest = content_digest(scope)
    limits = AssessmentLimits(max_operations=1, max_model_turns=0, max_elapsed_seconds=75)
    grant = AssessmentAuthorization(
        authorization_id=GRANT, subject_digests=[digest], recipe_digests=[digest], environment_digests=[digest],
        limits=limits, allowed_destinations=['local'], remote_disclosure=False, expires_at=expiry,
    )
    request = RecipeMaterializationRequest(
        plan_id=GRANT, subject_digest=digest, recipe_digest=digest, environment_digest=digest,
        mapping_digest=digest, definition_digests=[digest], authorization_id=GRANT, seed=0,
    )
    save(HERE / 'candidate-smoke-started.json', {'review_sha256': identity})
    observation, failure = None, None
    with ReceiptStore(old['OLD']['ledger']) as store:
        repo = AssessmentRepository(store)
        assert repo.put('toolkit_react_candidate_smoke_scope', digest, scope) == digest
        repo.approve_bundle(grant, {digest: scope.model_dump(mode='json')})
        operation = GRANT + ':smoke'
        repo.reserve(request, operation, limits, stage='smoke')
        clock, started = time.perf_counter(), utc_now()
        runner = CommandExecutor()

        def authorize():
            repo.authorize(request)
            assert utc_now() < expiry
            assert all(sha(Path(path)) == digest for path, digest in review['pins'].items())
            validate()
            return identity

        try:
            raw = await runner.execute(ExecutionContext(
                request=ActionRequest(action_id=operation, capability=spec.capability, input=payload),
                spec=spec, estimate=spec.estimate, attempt=1, attempt_id=operation,
                approved_side_effect=spec.side_effect, invocation_check=authorize,
            ))
            if raw.status.value != 'success':
                failure = raw.error_type or 'command_failed'
                raise RuntimeError(failure)
            result = raw.output
            assert result['next_version'] == 'Next.js v14.2.0'
            assert all(result[key] is True for key in (
                'native_compiler_loaded', 'private_public_project', 'protected_paths_absent',
                'read_only_tools', 'network_denied',
            ))
            observation = result
        except Exception as error:
            failure = failure or type(error).__name__
        finally:
            try:
                old['cleanup'](NAME)
            except Exception:
                observation, failure = None, 'owned_container_cleanup_unverified'
            await runner.close()
            elapsed = time.perf_counter() - clock
            receipt = helper['make_receipt'](operation, spec, started, elapsed, identity, observation, failure)
            store.save_receipt(receipt)
            repo.finish_operation(operation, elapsed_seconds=elapsed, resources=receipt.actual_resources)
            save(HERE / 'candidate-smoke-receipt.json', receipt.model_dump(mode='json'))
            ledger = repo.operation_ledger(GRANT)
            save(HERE / 'candidate-smoke-ledger.json', ledger.model_dump(mode='json'))
    result = {'review_sha256': identity, 'observation': observation, 'error_type': failure,
              'passed': observation is not None and observation['typecheck_exit'] == 0,
              'models': 0, 'comparisons': 'PAUSED'}
    save(HERE / 'candidate-smoke-result.json', result)
    print(json.dumps(result))
    return result['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument('--freeze', action='store_true')
    flags.add_argument('--execute-approved')
    args = parser.parse_args()
    if args.freeze:
        freeze()
    else:
        raise SystemExit(not asyncio.run(execute(args.execute_approved)))
