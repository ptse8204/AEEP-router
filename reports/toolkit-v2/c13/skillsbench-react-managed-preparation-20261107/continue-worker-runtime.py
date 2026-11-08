"""Resume the three unstarted operations while preserving the first build reservation."""

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
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, ResourceVector, StrictModel, utc_now
from aeep.store import ReceiptStore

HERE = Path(__file__).resolve().parent
old = runpy.run_path(str(HERE / 'worker-runtime.py'))
ROOT, WORK, CONTEXT, DOCKER, ENV, FREE = (old[k] for k in ('ROOT', 'WORK', 'CONTEXT', 'DOCKER', 'ENV', 'FREE'))
sha, read, save, docker, image = (old[k] for k in ('sha', 'read', 'save', 'docker', 'image'))
FIRST = HERE / 'worker-runtime-review.json'
REVIEW = HERE / 'worker-continuation-review.json'
GRANT = old['GRANT'] + '-continuation'
BUILD_HISTORY = 'ww1n31ph69qvrux5a8w54mcic'
ORDER = [('control', 'smoke', 75), ('candidate', 'build', 150), ('candidate', 'smoke', 75)]


class Scope(StrictModel):
    review_sha256: str


def original():
    review = read(FIRST)
    failed = read(HERE / 'worker-runtime-result.json')
    assert failed['review_sha256'] == sha(FIRST) and failed['error_type'] == 'ValidationError'
    assert not failed['accounting_settled'] and failed['operations'] == 1
    assert all(sha(Path(path)) == digest for path, digest in review['pins'].items())
    assert old['inventory'](CONTEXT) == read(WORK / 'worker-context-inventory.json')
    assert verification_source_digest(ROOT) == review['source_sha256']
    assert shutil.disk_usage(ROOT).free >= FREE
    ledger = read(HERE / 'worker-runtime-ledger.json')['operations']
    operation, = ledger
    assert operation['operation_id'] == old['GRANT'] + ':control:build'
    assert operation['elapsed_seconds'] is None and operation['reserved']['max_elapsed_seconds'] == 150
    control, candidate = (review['roles'][role] for role in ('control', 'candidate'))
    built = image(control['tag'])
    assert built and built['layers'][:-1] == control['parent']['layers'] and not built['volumes']
    assert built['user'] == '65534:65534' and built['platform'] == 'linux/arm64'
    assert image(candidate['base']) == candidate['parent'] and image(candidate['tag']) is None
    record = docker('buildx', 'history', 'inspect', '--builder=default', '--format', 'json', BUILD_HISTORY)
    assert record.returncode == 0
    history = json.loads(record.stdout)
    assert history['Status'] == 'completed' and history['Platform'] == ['linux/arm64']
    assert history['Materials'][0]['Digests'] == [control['parent']['id']]
    logs = docker('buildx', 'history', 'logs', '--builder=default', BUILD_HISTORY)
    assert logs.returncode == 0 and built['id'] in logs.stdout + logs.stderr
    return review, built, history['Duration']


def spec_for(stage, args, *, stdin_json=False):
    return ExecutorSpec(
        id='skillsbench.react.' + stage, capability='toolkit.upstream-engineering@1', kind='command',
        description='Reviewed managed React worker ' + stage, side_effect='write',
        config={'argv': [*DOCKER, *args], 'argv_literal': True, 'inherit_env': False, 'env': ENV,
                'cwd': str(WORK), 'timeout_seconds': 60 if stdin_json else 125, 'max_output_bytes': 65536,
                'stdin_json': stdin_json, 'output': {'type': 'json' if stdin_json else 'text'}},
    )


def make_receipt(operation, spec, started, elapsed, identity, observation, error_type):
    return ExecutionReceipt(
        decision_id=operation, action_id=operation, capability=spec.capability, executor_id=spec.id,
        executor_kind=spec.kind, status='success' if observation is not None else 'failed',
        started_at=started, ended_at=utc_now(), estimated=spec.estimate,
        actual_resources=ResourceVector(latency_ms=elapsed * 1000), execution_success=observation is not None,
        error_type=error_type, metadata={'review_sha256': identity, 'observation': observation,
                                         'observed_resource_dimensions': ['latency_ms']},
    )


def freeze():
    prior, control, engine_ns = original()
    payload = old['public_input']()
    assert content_digest(payload) == prior['public_input_sha256']
    receipt = make_receipt('synthetic_receipt_check', spec_for('smoke', ['--version'], stdin_json=True),
                           utc_now(), 0, 'fixture', {}, None)
    assert receipt.execution_success and receipt.model_dump(mode='json')['estimated']['resources']
    pins = [Path(__file__).resolve(), FIRST, HERE / 'worker-runtime-ledger.json', HERE / 'worker-runtime-result.json']
    save(REVIEW, {
        'scope': 'One unstarted candidate COPY-only build and two unstarted offline smoke checks.',
        'pins': {str(path): sha(path) for path in pins}, 'original_review_sha256': sha(FIRST),
        'preserve_prior_reservation_seconds': 150, 'prior_coordinator_elapsed_seconds': None,
        'retained_control': control, 'docker_build_history_ref': BUILD_HISTORY,
        'docker_engine_build_elapsed_ns': engine_ns, 'order': [list(op) for op in ORDER],
        'maximum_new_operations': 3, 'maximum_new_reserved_seconds': 300,
        'control_rebuild': False, 'downloads': False, 'network': False, 'models': 0,
        'cash_usd': '0', 'provider_transfer': False, 'automatic_retries': False,
        'existing_resource_deletion': False, 'comparisons': 'PAUSED',
        'receipt_constructor_fixture_passed': True,
        'expires_at': (utc_now() + timedelta(hours=10)).isoformat(),
    })
    print(sha(REVIEW))


async def execute(identity):
    review = read(REVIEW)
    assert sha(REVIEW) == identity
    assert read(HERE / 'worker-continuation-approval.json') == {'approved': True, 'review_sha256': identity}
    assert not (HERE / 'worker-continuation-started.json').exists()
    expires = datetime.fromisoformat(review['expires_at'])
    assert utc_now() < expires
    assert all(sha(Path(path)) == digest for path, digest in review['pins'].items())
    prior, control, engine_ns = original()
    assert control == review['retained_control'] and engine_ns == review['docker_engine_build_elapsed_ns']
    payload = old['public_input']()
    assert content_digest(payload) == prior['public_input_sha256']
    scope = Scope(review_sha256=identity)
    digest = content_digest(scope)
    limits = AssessmentLimits(max_operations=3, max_model_turns=0, max_elapsed_seconds=300)
    request = RecipeMaterializationRequest(
        plan_id=GRANT, subject_digest=digest, recipe_digest=digest, environment_digest=digest,
        mapping_digest=digest, definition_digests=[digest], authorization_id=GRANT, seed=0,
    )
    grant = AssessmentAuthorization(
        authorization_id=GRANT, subject_digests=[digest], recipe_digests=[digest],
        environment_digests=[digest], limits=limits, allowed_destinations=['local'],
        remote_disclosure=False, expires_at=expires,
    )
    images, probes = {'control': control}, {}
    outcome = {'review_sha256': identity, 'images': images, 'smokes': probes, 'passed': False, 'models': 0}
    save(HERE / 'worker-continuation-started.json', {'review_sha256': identity})
    with ReceiptStore(old['OLD']['ledger']) as store:
        repo = AssessmentRepository(store)
        assert repo.put('toolkit_react_arm64_worker_continuation_scope', digest, scope) == digest
        repo.approve_bundle(grant, {digest: scope.model_dump(mode='json')})
        try:
            for role, stage, reserved in ORDER:
                entry = prior['roles'][role]
                name = None
                if stage == 'build':
                    assert image(entry['base']) == entry['parent'] and image(entry['tag']) is None
                    spec = spec_for(stage, [
                        'build', '--pull=false', '--network=none', '--platform=linux/arm64', '--builder=default',
                        '--provenance=false', '--sbom=false', '--file', str(CONTEXT / ('Dockerfile.' + role)),
                        '--tag', entry['tag'], str(CONTEXT),
                    ])
                else:
                    name = 'aeep-react-worker-smoke-' + role + '-20261108'
                    assert old['absent'](name) and image(entry['tag']) == images[role]
                    spec = spec_for(stage, [
                        'run', '--rm', '--pull=never', '--network=none', '--read-only', '--user', '65534:65534',
                        '--cap-drop=ALL', '--security-opt=no-new-privileges', '--memory=1024m',
                        '--memory-swap=1024m', '--cpus=2', '--pids-limit=192', '--log-driver=none',
                        '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=128m', '--workdir', '/tmp',
                        '--name', name, '--label', 'aeep.react-smoke=' + old['GRANT'], '-i',
                        '--entrypoint', 'python3', images[role]['id'], '-I', '-B', '-c',
                        (HERE / 'worker-smoke.py').read_text(),
                    ], stdin_json=True)
                operation = GRANT + ':' + role + ':' + stage
                repo.reserve(request, operation, AssessmentLimits(max_operations=1, max_elapsed_seconds=reserved), stage=stage)
                runner = CommandExecutor()
                clock, started = time.perf_counter(), utc_now()
                observation, failure = None, None

                def authorize():
                    repo.authorize(request)
                    assert utc_now() < expires and shutil.disk_usage(ROOT).free >= FREE
                    assert verification_source_digest(ROOT) == prior['source_sha256']
                    assert old['inventory'](CONTEXT) == read(WORK / 'worker-context-inventory.json')
                    assert all(sha(Path(path)) == digest for path, digest in (review['pins'] | prior['pins']).items())
                    return identity

                try:
                    raw = await runner.execute(ExecutionContext(
                        request=ActionRequest(action_id=operation, capability=spec.capability, input=payload if name else {}),
                        spec=spec, estimate=spec.estimate, attempt=1, attempt_id=operation,
                        approved_side_effect=spec.side_effect, invocation_check=authorize,
                    ))
                    if raw.status.value != 'success':
                        failure = raw.error_type or 'command_failed'
                        raise RuntimeError(failure)
                    if stage == 'build':
                        result = image(entry['tag'])
                        assert result and result['platform'] == 'linux/arm64' and result['user'] == '65534:65534'
                        assert result['layers'][:-1] == entry['parent']['layers'] and not result['volumes']
                        assert result['layers'][-1] == control['layers'][-1]
                        images[role] = observation = result
                    else:
                        result = raw.output
                        assert result['next_version'] == 'Next.js v14.2.0'
                        assert all(result[key] is True for key in (
                            'native_compiler_loaded', 'private_public_project', 'protected_paths_absent',
                            'read_only_tools', 'network_denied',
                        ))
                        probes[role] = observation = result
                except Exception as error:
                    failure = failure or type(error).__name__
                    raise
                finally:
                    cleanup_error = None
                    if name:
                        try:
                            old['cleanup'](name)
                        except Exception as error:
                            observation, failure, cleanup_error = None, 'owned_container_cleanup_unverified', error
                    await runner.close()
                    elapsed = time.perf_counter() - clock
                    receipt = make_receipt(operation, spec, started, elapsed, identity, observation, failure)
                    store.save_receipt(receipt)
                    repo.finish_operation(operation, elapsed_seconds=elapsed, resources=receipt.actual_resources)
                    save(HERE / f'worker-continuation-{role}-{stage}-receipt.json', receipt.model_dump(mode='json'))
                    if cleanup_error:
                        raise cleanup_error
            outcome['passed'] = len(probes) == 2 and all(row['typecheck_exit'] == 0 for row in probes.values())
        except Exception as error:
            outcome['error_type'] = type(error).__name__
        finally:
            ledger = repo.operation_ledger(GRANT)
            outcome['new_accounting_settled'] = all(entry.elapsed_seconds is not None for entry in ledger.operations)
            outcome['new_operations'] = len(ledger.operations)
            save(HERE / 'worker-continuation-ledger.json', ledger.model_dump(mode='json'))
            save(HERE / 'worker-continuation-result.json', outcome)
    print(json.dumps(outcome))
    return outcome['passed'] and outcome['new_accounting_settled']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze', action='store_true')
    mode.add_argument('--execute-approved')
    options = parser.parse_args()
    if options.freeze:
        freeze()
    else:
        raise SystemExit(not asyncio.run(execute(options.execute_approved)))
