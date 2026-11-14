"""Build and verify the Prefix Cache grader using the existing local assessment ledger."""

import argparse
import asyncio
import base64
import hashlib
import json
import runpy
import shutil
import subprocess
import time
from datetime import timedelta
from pathlib import Path

from aeep.assessment.containment import ContainerExecutor, container_name
from aeep.assessment.extensions import grader_results, require_environment
from aeep.assessment.models import (
    AssessmentAuthorization, AssessmentEnvironment, AssessmentLimits, RecipeDefinition,
    RecipeMaterializationRequest, content_digest,
)
from aeep.assessment.recipes import faulty_outputs
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutorSpec, StrictModel, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.benchmarks import BenchmarkPack, task_input

HERE = Path(__file__).resolve().parent
stage = runpy.run_path(str(HERE / 'prepare.py'))
ROOT, WORK, IMAGE, TASK, read, sha = (stage[key] for key in ('ROOT', 'WORK', 'IMAGE', 'TASK', 'read', 'sha'))
worker = runpy.run_path(str(IMAGE / 'worker-runtime.py'))
receipt = runpy.run_path(str(IMAGE / 'continue-worker-runtime.py'))['make_receipt']
DOCKER, ENV = worker['DOCKER'], worker['ENV']
GIB = 1024**3
GRANT = 'skillsbench-prefix-cache-sealed-20261113'
OUT = HERE / 'carrier-verification'
REVIEW = OUT / 'operation-review.json'
AUTHORITY = HERE.parents[1] / 'pipeline-standing-authority-20261104.json'
TAG = 'aeep-skillsbench-prefix-cache:sealed-amd64-20261112'
DOCKER_CONFIG = Path(DOCKER[2]) / 'config.json'
BUILDX = Path(DOCKER[0]).parent.parent / 'cli-plugins/docker-buildx'
DOCKER_TEAM = '9BNSXJN65R'


class Scope(StrictModel):
    review_sha256: str


def inputs():
    draft = read(HERE / 'result.json')
    parent = read(HERE / 'carrier-preflight.json')
    context = Path(draft['context'])
    assert context == WORK / 'build'
    files = sorted(context.rglob('*'))
    assert not any(item.is_symlink() for item in files)
    hashes = {str(item.relative_to(context)): sha(item) for item in files if item.is_file()}
    assert hashes == draft['context_files'] and content_digest(hashes) == parent['context_sha256']
    assert all(item.stat().st_nlink == 1 and item.stat().st_mode & 0o777 == 0o444
               for item in files if item.is_file())
    assert all(item.stat().st_mode & 0o777 == 0o755 for item in files if item.is_dir())
    assert sha(HERE / 'result.json') == parent['preparation_result_sha256']
    assert parent['proposed_image_tag'] == TAG
    image = worker['image'](parent['parent_tag'])
    assert image and image['id'] == parent['parent_image_id'] and image['layers'] == parent['parent_layers']
    assert image['platform'] == 'linux/amd64' and image['user'] == '65534:65534' and not image['volumes']
    recipe = RecipeDefinition.model_validate(read(Path(draft['recipe'])))
    assert recipe.extension is not None and content_digest(recipe) == draft['recipe_digest']
    transport = read(HERE.parent / 'task-pack-transport.json')
    value = task_input(BenchmarkPack.model_validate(read(HERE.parent / 'task-pack.json')),
                       Path(transport['pack_root']), TASK)
    assert value['task_archive_sha256'] == draft['public_archive_sha256']
    build = ExecutorSpec(
        id='skillsbench.prefix-cache.carrier-build', capability='toolkit.upstream-engineering@1',
        description='Local offline COPY build of the protected Prefix Cache grader',
        side_effect='write', kind='command', config={
            'argv': [*DOCKER, 'build', *parent['build_flags'], '--tag', TAG, str(context)],
            'argv_literal': True, 'inherit_env': False, 'env': ENV, 'cwd': str(WORK),
            'timeout_seconds': 125, 'max_output_bytes': 65536, 'output': {'type': 'text'},
        },
    )
    return draft, parent, image, recipe, value, build


def save(path, data):
    worker['save'](path, data)


def verify_docker_signature(path, identifier):
    requirement = (f'=identifier "{identifier}" and anchor apple generic '
                   f'and certificate leaf[subject.OU] = "{DOCKER_TEAM}"')
    subprocess.run(['/usr/bin/codesign', '--verify', '--strict', '-R', requirement, str(path)],
                   timeout=15, check=True)


def freeze():
    draft, parent, _, recipe, value, build = inputs()
    docker = Path(DOCKER[0])
    assert read(DOCKER_CONFIG) == {'cliPluginsExtraDirs': [str(BUILDX.parent)]}
    assert not (DOCKER_CONFIG.parent / 'cli-plugins/docker-buildx').exists()
    verify_docker_signature(docker, 'docker')
    verify_docker_signature(BUILDX, 'docker-buildx')
    assert worker['image'](TAG) is None
    files = [Path(__file__), HERE / 'prepare.py', HERE / 'grade.py', HERE / 'result.json',
             HERE / 'carrier-preflight.json', HERE.parent / 'task-pack.json',
             HERE.parent / 'task-pack-transport.json', Path(draft['recipe']),
             IMAGE / 'self-contained-environment.json', IMAGE / 'worker-runtime.py',
             IMAGE / 'continue-worker-runtime.py', worker['CARRIER'] / 'runtime-review.json',
             worker['CARRIER'].parent / 'skillsbench-contained-graders-20261105/prepare-images.py',
             IMAGE / 'acquire-node-packages.py', AUTHORITY, docker, DOCKER_CONFIG, BUILDX]
    limits = AssessmentLimits(max_operations=9, max_elapsed_seconds=640)
    OUT.mkdir(exist_ok=True)
    save(REVIEW, {
        'scope': 'First build of the protected grader image and eight offline checks on that image.',
        'pins': {str(path): sha(path) for path in files}, 'source_sha256': verification_source_digest(ROOT),
        'recipe_digest': content_digest(recipe), 'input_digest': content_digest(value),
        'build_digest': content_digest(build), 'context_digest': draft['context_digest'],
        'docker_identity': {'previous_sha256': parent['docker_client_sha256'], 'sha256': sha(docker),
                            'buildx_sha256': sha(BUILDX), 'signer_team': DOCKER_TEAM},
        'limits': limits.model_dump(mode='json'), 'minimum_start_free_gib': 52, 'minimum_free_gib': 50,
        'models': 0, 'downloads': False, 'provider_transfer': False, 'network': False,
        'automatic_retries': False, 'comparisons': 'PAUSED',
    })
    print(sha(REVIEW))


def preflight(identity):
    review = read(REVIEW)
    assert sha(REVIEW) == identity
    assert all(sha(Path(path)) == digest for path, digest in review['pins'].items())
    assert not (DOCKER_CONFIG.parent / 'cli-plugins/docker-buildx').exists()
    assert verification_source_digest(ROOT) == review['source_sha256']
    draft, _, image, recipe, value, build = inputs()
    assert content_digest(recipe) == review['recipe_digest'] and content_digest(value) == review['input_digest']
    assert content_digest(build) == review['build_digest'] and draft['context_digest'] == review['context_digest']
    assert not (OUT / 'started.json').exists()
    assert worker['image'](TAG) is None
    return review, image, recipe, value, build


async def execute(identity):
    review, parent, recipe, value, build = preflight(identity)
    delegated = read(AUTHORITY)
    assert delegated['first_attempts'].startswith('Concrete finite installation/service/execution reviews')
    assert shutil.disk_usage(ROOT).free >= review['minimum_start_free_gib'] * GIB
    assert worker['docker']('buildx', 'inspect', 'default').returncode == 0
    assert worker['docker']('system', 'df', '--format', '{{.Type}} {{.Size}}').returncode == 0
    expires = utc_now() + timedelta(hours=1)
    assert not (WORK / 'carrier-verification.sqlite3').exists()
    save(OUT / 'started.json', {'review_sha256': identity, 'authority_sha256': sha(AUTHORITY),
                                'grant_expires_at': expires.isoformat(), 'first_attempt': True})
    scope = Scope(review_sha256=identity)
    digest = content_digest(scope)
    request = RecipeMaterializationRequest(plan_id=GRANT, subject_digest=digest, recipe_digest=digest,
        mapping_digest=digest, environment_digest=digest, authorization_id=GRANT, definition_digests=[digest], seed=0)
    grant = AssessmentAuthorization(authorization_id=GRANT, subject_digests=[digest], recipe_digests=[digest],
        environment_digests=[digest], allowed_destinations=['local'], remote_disclosure=False,
        limits=AssessmentLimits.model_validate(review['limits']), expires_at=expires)
    facts = {'review_sha256': identity, 'models': 0, 'comparisons': 'PAUSED', 'observations': {}, 'passed': False}
    with ReceiptStore(str(WORK / 'carrier-verification.sqlite3')) as store:
        repository = AssessmentRepository(store)
        repository.put('toolkit_prefix_cache_carrier_scope', digest, scope)
        repository.approve_bundle(grant, {digest: scope.model_dump(mode='json')})

        async def operation(name, spec, executor, payload, reservation, observe):
            op = f'{GRANT}:{name}'
            container = container_name(op) if isinstance(executor, ContainerExecutor) else None
            if container:
                assert worker['absent'](container)
            repository.reserve(request, op, AssessmentLimits(max_operations=1, max_elapsed_seconds=reservation), stage=name)
            started, clock = utc_now(), time.perf_counter()
            evidence, failure = None, None

            def authorize():
                repository.authorize(request)
                assert shutil.disk_usage(ROOT).free >= review['minimum_free_gib'] * GIB
                assert verification_source_digest(ROOT) == review['source_sha256']
                assert all(sha(Path(path)) == digest for path, digest in review['pins'].items())
                if container is None:
                    assert inputs()[2] == parent and worker['image'](TAG) is None
                return identity

            try:
                raw = await executor.execute(ExecutionContext(
                    request=ActionRequest(action_id=op, capability=spec.capability, input=payload),
                    spec=spec, estimate=spec.estimate, attempt=1, attempt_id=op,
                    approved_side_effect=spec.side_effect, invocation_check=authorize,
                ))
                if container:
                    assert worker['absent'](container), 'owned container cleanup unverified'
                if raw.status.value != 'success':
                    failure = raw.error_type or 'command_failed'
                    raise RuntimeError(failure)
                evidence = observe(raw.output)
                facts['observations'][name] = evidence
                return raw.output
            except Exception as error:
                failure = failure or type(error).__name__
                raise
            finally:
                await executor.close()
                elapsed = time.perf_counter() - clock
                record = receipt(op, spec, started, elapsed, identity, evidence, failure)
                store.save_receipt(record)
                repository.finish_operation(op, elapsed_seconds=elapsed, resources=record.actual_resources)
                save(OUT / f'{name}-receipt.json', record.model_dump(mode='json'))

        try:
            def built(_):
                image = worker['image'](TAG)
                assert image and image['id'] != parent['id'] and image['platform'] == parent['platform']
                assert image['user'] == parent['user'] and not image['volumes']
                assert image['layers'][:-1] == parent['layers']
                return image

            await operation('build', build, CommandExecutor(), {}, 150, built)
            image = facts['observations']['build']
            env = AssessmentEnvironment.model_validate(read(IMAGE / 'self-contained-environment.json'))
            env = env.model_copy(update={'environment_id': GRANT, 'container_image': image['id'],
                'identity': {'context_sha256': review['context_digest']}, 'cpu_count': 1.0,
                'memory_mb': 512, 'process_limit': 64, 'container_tmpfs_mb': 32})
            require_environment(recipe, env)
            extension = recipe.extension
            assert extension is not None

            def reference(output):
                answer, = output['outputs']
                raw = base64.b64decode(answer['report_b64'], validate=True)
                assert 0 < len(raw) <= stage['LIMIT'] and isinstance(json.loads(raw), dict)
                return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}

            reply = await operation('reference', extension.reference, ContainerExecutor(env),
                                    {'inputs': [value]}, 35, reference)
            answer, = reply['outputs']
            outputs = [answer, *faulty_outputs(answer), *extension.fault_outputs]
            assert len(outputs) == 7
            for index, output in enumerate(outputs):
                def grade(reply):
                    result, = grader_results(reply, extension, 1)
                    expected_code = None if index == 0 else 'upstream_rejected' if index == 6 else 'output_contract'
                    assert result.valid is (index == 0) and (result.detail or None) == expected_code
                    return {'binary_score': int(result.valid), 'failure_code': expected_code}

                payload = {'examples': [{'input': value, 'output': output,
                                         'expected': {'task_archive_sha256': value['task_archive_sha256']}}]}
                await operation(f'probe-{index}', extension.grader, ContainerExecutor(env), payload, 65, grade)
            save(OUT / 'environment.json', env.model_dump(mode='json'))
            facts['passed'] = True
        except Exception as error:
            facts['error_type'] = type(error).__name__
        finally:
            ledger = repository.operation_ledger(GRANT)
            facts['operations'] = len(ledger.operations)
            facts['accounting_settled'] = all(operation.elapsed_seconds is not None for operation in ledger.operations)
            save(OUT / 'ledger.json', ledger.model_dump(mode='json'))
            save(OUT / 'result.json', facts)
    print(json.dumps(facts))
    return facts['passed'] and facts['accounting_settled']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze', action='store_true')
    mode.add_argument('--preflight')
    mode.add_argument('--execute-delegated')
    args = parser.parse_args()
    if args.freeze:
        freeze()
    elif args.preflight:
        review, *_ = preflight(args.preflight)
        free = shutil.disk_usage(ROOT).free
        print(json.dumps({'review_sha256': args.preflight, 'pins_verified': True, 'free_bytes': free,
                          'build_ready': free >= review['minimum_start_free_gib'] * GIB, 'operations': 0, 'models': 0}))
    else:
        raise SystemExit(not asyncio.run(execute(args.execute_delegated)))
