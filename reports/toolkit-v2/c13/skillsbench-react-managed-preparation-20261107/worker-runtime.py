"""Build and verify one retained ARM64 worker pair with public React dependencies."""

import argparse
import asyncio
import hashlib
import json
import runpy
import shutil
import subprocess
import tarfile
import time
from datetime import timedelta
from pathlib import Path, PurePosixPath

from aeep.assessment.models import AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, ResourceVector, StrictModel, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.benchmarks import BenchmarkPack, task_input

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT / '.aeep' / HERE.name
CONTEXT = WORK / 'worker-context'
ACQUISITION = runpy.run_path(str(HERE / 'acquire-node-packages.py'))
STAGE = runpy.run_path(str(HERE.parent / 'skillsbench-contained-graders-20261105/prepare-images.py'))
CARRIER = HERE.parent / 'skillsbench-react-ordinary-carrier-20261108'
GRADER = HERE.parent / 'skillsbench-react-readonly-grader-20261108'
PARENTS = HERE.parent / 'skillsbench-managed-worker-preparation-20261105/staged-worker-contexts.json'
AUTHORITY = ACQUISITION['AUTHORITY']
REVIEW = HERE / 'worker-runtime-review.json'
GRANT = 'skillsbench-react-arm64-worker-first-20261108'
FREE = 52 * 1024**3
OLD = STAGE['read'](CARRIER / 'runtime-review.json')
DOCKER = OLD['docker']
ENV = OLD['env']
sha, read, inventory = (STAGE[k] for k in ('digest', 'read', 'inventory'))


class Scope(StrictModel):
    review_sha256: str


def save(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')


def docker(*args):
    return subprocess.run([*DOCKER, *args], env=ENV, cwd=WORK, text=True,
                          capture_output=True, timeout=20)


def image(ref):
    fmt = '{{.Id}} {{.Os}}/{{.Architecture}} {{json .RootFS.Layers}} {{json (index .Config "User")}} {{json (index .Config "Volumes")}}'
    result = docker('image', 'inspect', '--format', fmt, ref)
    if result.returncode != 0:
        return None
    identity, platform, layers, user, volumes = result.stdout.strip().split(' ', 4)
    return {'id': identity, 'platform': platform, 'layers': json.loads(layers),
            'user': json.loads(user), 'volumes': json.loads(volumes)}


def public_input():
    task = read(HERE / 'operation-review.json')['tasks'][0]
    bound = WORK / 'react-performance-debugging-bound-pack.json'
    assert sha(bound) == read(HERE / 'managed-toolchain-audit.json')['rights_bound_pack_sha256']
    case = task_input(BenchmarkPack.model_validate_json(bound.read_bytes()), Path(task['pack_root']), task['task_id'])
    assert case['task_archive_sha256'] == task['public_archive_sha256']
    return {'archive': case['task_archive_b64'], 'archive_sha256': case['task_archive_sha256'],
            'files': {name: value if isinstance(value, str) else value['sha256']
                      for name, value in task['public_files'].items()}}


def stage_dependencies():
    result = read(HERE / 'node-acquisition-result.json')
    assert result['passed'] and not result['packages_executed']
    assert result['review_sha256'] == sha(HERE / 'node-acquisition-review.json')
    archives = {row['sha512']: row for row in result['archives']}
    for row in ACQUISITION['artifacts']():
        observation = archives[row['sha512']]
        source = WORK / 'npm-archives' / (row['sha512'] + '.tgz')
        with source.open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha512').hexdigest() == row['sha512']
        with tarfile.open(source, 'r:gz') as archive:
            for member in archive:
                path = PurePosixPath(member.name)
                assert path.parts[0] == observation['archive_root'] and '..' not in path.parts
                if member.isdir():
                    continue
                assert member.isfile() and len(path.parts) > 1 and '\\' not in member.name
                relative = PurePosixPath(*path.parts[1:])
                assert relative.parts[0] != 'node_modules'
                for location in row['locations']:
                    target = CONTEXT / location / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as contents, target.open('xb') as output:
                        shutil.copyfileobj(contents, output)
                    target.chmod(0o555 if member.mode & 0o111 else 0o444)
    assert (CONTEXT / 'node_modules/next/dist/bin/next').is_file()


def freeze():
    assert not REVIEW.exists() and not (HERE / 'worker-runtime-started.json').exists()
    assert shutil.disk_usage(ROOT).free >= FREE
    assert read(GRADER / 'result.json')['passed'] and read(GRADER / 'result.json')['accounting_settled']
    assert verification_source_digest(ROOT) == OLD['source_sha256']
    assert docker('buildx', 'inspect', 'default').returncode == 0
    assert docker('system', 'df', '--format', '{{.Type}} {{.Size}}').returncode == 0
    roles = {}
    for item in read(PARENTS)['contexts']:
        if item['domain'] != 'sales':
            continue
        parent = image(item['base'])
        assert parent and parent['id'] == item['base_image_id'] and parent['platform'] == 'linux/arm64'
        assert parent['user'] == '65534:65534' and not parent['volumes']
        role = item['role']
        tag = 'aeep-skillsbench-worker:react-' + role + '-20261108'
        assert image(tag) is None
        roles[role] = {'base': item['base'], 'parent': parent, 'tag': tag}
    assert set(roles) == {'control', 'candidate'}
    CONTEXT.mkdir(mode=0o700)
    stage_dependencies()
    for role, entry in roles.items():
        (CONTEXT / ('Dockerfile.' + role)).write_text(
            f"FROM {entry['base']}\nCOPY node_modules/ /opt/aeep-task-tools/react/node_modules/\n"
        )
    save(WORK / 'worker-context-inventory.json', inventory(CONTEXT))
    payload = public_input()
    pinned = [
        Path(__file__).resolve(), HERE / 'worker-smoke.py', HERE / 'acquire-node-packages.py',
        HERE / 'node-acquisition-result.json', HERE / 'node-acquisition-review.json', GRADER / 'result.json',
        HERE / 'operation-review.json', HERE / 'managed-toolchain-audit.json', PARENTS, AUTHORITY,
        WORK / 'worker-context-inventory.json', Path(DOCKER[0]), Path(DOCKER[2]) / 'config.json',
    ]
    save(REVIEW, {
        'scope': 'First COPY-only managed React ARM64 worker builds and offline public-project smoke checks.',
        'pins': {str(path): sha(path) for path in pinned},
        'source_sha256': OLD['source_sha256'], 'roles': roles,
        'public_input_sha256': content_digest(payload), 'maximum_operations': 4,
        'maximum_reserved_seconds': 450, 'builds': 2, 'smoke_checks': 2,
        'models': 0, 'cash_usd': '0', 'network': False, 'provider_transfer': False,
        'automatic_retries': False, 'existing_resource_deletion': False, 'comparisons': 'PAUSED',
        'expires_at': (utc_now() + timedelta(hours=6)).isoformat(),
    })
    save(HERE / 'worker-runtime-authority.json', {
        'review_sha256': sha(REVIEW), 'standing_authority_sha256': sha(AUTHORITY), 'first_attempt': True,
    })
    print(sha(REVIEW))


def absent(name):
    listing = docker('ps', '-aq', '--filter', 'name=^/' + name + '$')
    assert listing.returncode == 0
    return not listing.stdout.strip()


def cleanup(name):
    if not absent(name):
        label = docker('container', 'inspect', '--format', '{{index .Config.Labels "aeep.react-smoke"}}', name)
        assert label.returncode == 0 and label.stdout.strip() == GRANT
        assert docker('rm', '--force', name).returncode == 0
    assert absent(name)


async def execute(identity):
    review = read(REVIEW)
    assert sha(REVIEW) == identity
    assert read(HERE / 'worker-runtime-authority.json') == {
        'review_sha256': identity, 'standing_authority_sha256': sha(AUTHORITY), 'first_attempt': True,
    }
    expires = type(utc_now()).fromisoformat(review['expires_at'])
    assert utc_now() < expires
    assert not (HERE / 'worker-runtime-started.json').exists()
    assert all(sha(Path(path)) == digest for path, digest in review['pins'].items())
    assert inventory(CONTEXT) == read(WORK / 'worker-context-inventory.json')
    payload = public_input()
    assert content_digest(payload) == review['public_input_sha256']
    scope = Scope(review_sha256=identity)
    digest = content_digest(scope)
    limits = AssessmentLimits(max_operations=4, max_model_turns=0, max_elapsed_seconds=450)
    grant = AssessmentAuthorization(
        authorization_id=GRANT, subject_digests=[digest], recipe_digests=[digest],
        environment_digests=[digest], limits=limits, allowed_destinations=['local'],
        remote_disclosure=False, expires_at=expires,
    )
    request = RecipeMaterializationRequest(
        plan_id=GRANT, subject_digest=digest, recipe_digest=digest, environment_digest=digest,
        mapping_digest=digest, definition_digests=[digest], authorization_id=GRANT, seed=0,
    )
    save(HERE / 'worker-runtime-started.json', {'review_sha256': identity})
    outcome = {'review_sha256': identity, 'models': 0, 'comparisons': 'PAUSED', 'passed': False, 'roles': {}}
    with ReceiptStore(OLD['ledger']) as store:
        repo = AssessmentRepository(store)
        assert repo.put('toolkit_react_arm64_worker_scope', digest, scope) == digest
        repo.approve_bundle(grant, {digest: scope.model_dump(mode='json')})

        async def run(role, stage, argv, data, timeout, container=None):
            side_effect = 'write'
            limit = 150 if stage == 'build' else 75
            operation = GRANT + ':' + role + ':' + stage
            repo.reserve(request, operation, AssessmentLimits(max_operations=1, max_elapsed_seconds=limit), stage=stage)
            clock, started = time.perf_counter(), utc_now()
            runner = CommandExecutor()
            facts, failure = None, None
            try:
                spec = ExecutorSpec(
                    id='skillsbench.react.' + stage, capability='toolkit.upstream-engineering@1',
                    kind='command', description='Reviewed managed React worker ' + stage, side_effect=side_effect,
                    config={'argv': [*DOCKER, *argv], 'argv_literal': True, 'inherit_env': False,
                            'env': ENV, 'cwd': str(WORK), 'timeout_seconds': timeout,
                            'max_output_bytes': 65536, 'stdin_json': data is not None,
                            'output': {'type': 'json' if data is not None else 'text'}},
                )

                def authorize():
                    repo.authorize(request)
                    assert utc_now() < expires and shutil.disk_usage(ROOT).free >= FREE
                    assert verification_source_digest(ROOT) == review['source_sha256']
                    assert all(sha(Path(path)) == value for path, value in review['pins'].items())
                    assert inventory(CONTEXT) == read(WORK / 'worker-context-inventory.json')
                    return identity

                raw = await runner.execute(ExecutionContext(
                    request=ActionRequest(action_id=operation, capability=spec.capability, input=data or {}),
                    spec=spec, estimate=spec.estimate, attempt=1, attempt_id=operation,
                    approved_side_effect=spec.side_effect, invocation_check=authorize,
                ))
                if raw.status.value != 'success':
                    failure = raw.error_type or 'command_failed'
                    output = (raw.stderr or '').lower()
                    failure = next((label for label in ('insufficient_scope', 'permission denied', 'module_not_found')
                                    if label in output), failure)
                    return None
                if stage == 'build':
                    facts = image(review['roles'][role]['tag'])
                    parent = review['roles'][role]['parent']
                    assert facts and facts['platform'] == 'linux/arm64' and facts['user'] == '65534:65534'
                    assert facts['layers'][:-1] == parent['layers'] and not facts['volumes']
                else:
                    facts = raw.output
                    assert facts['next_version'] == 'Next.js v14.2.0'
                    assert all(facts[name] is True for name in (
                        'native_compiler_loaded', 'private_public_project', 'protected_paths_absent',
                        'read_only_tools', 'network_denied',
                    ))
                return facts
            except Exception as error:
                facts, failure = None, type(error).__name__
                raise
            finally:
                cleanup_error = None
                if container:
                    try:
                        cleanup(container)
                    except Exception as error:
                        facts, failure = None, 'owned_container_cleanup_unverified'
                        cleanup_error = error
                await runner.close()
                elapsed = time.perf_counter() - clock
                receipt = ExecutionReceipt(
                    decision_id=operation, action_id=operation, capability='toolkit.upstream-engineering@1',
                    executor_id='skillsbench.react.' + stage, executor_kind='command',
                    status='success' if facts else 'failed', started_at=started, ended_at=utc_now(),
                    estimated=ResourceVector(), actual_resources=ResourceVector(latency_ms=elapsed * 1000),
                    execution_success=facts is not None, error_type=failure,
                    metadata={'review_sha256': identity, 'observation': facts,
                              'observed_resource_dimensions': ['latency_ms']},
                )
                store.save_receipt(receipt)
                repo.finish_operation(operation, elapsed_seconds=elapsed, resources=receipt.actual_resources)
                save(HERE / f'worker-{role}-{stage}-receipt.json', receipt.model_dump(mode='json'))
                if cleanup_error is not None:
                    raise cleanup_error

        try:
            for role, entry in review['roles'].items():
                assert image(entry['base']) == entry['parent'] and image(entry['tag']) is None
                built = await run(role, 'build', [
                    'build', '--pull=false', '--network=none', '--platform=linux/arm64', '--builder=default',
                    '--provenance=false', '--sbom=false', '--file', str(CONTEXT / ('Dockerfile.' + role)),
                    '--tag', entry['tag'], str(CONTEXT),
                ], None, 125)
                assert built
                outcome['roles'][role] = {'image': built}
                name = 'aeep-react-worker-smoke-' + role + '-20261108'
                assert absent(name)
                smoke = await run(role, 'smoke', [
                    'run', '--rm', '--pull=never', '--network=none', '--read-only', '--user', '65534:65534',
                    '--cap-drop=ALL', '--security-opt=no-new-privileges', '--memory=1024m',
                    '--memory-swap=1024m', '--cpus=2', '--pids-limit=192', '--log-driver=none',
                    '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=128m', '--workdir', '/tmp',
                    '--name', name, '--label', 'aeep.react-smoke=' + GRANT, '-i',
                    '--entrypoint', 'python3', built['id'], '-I', '-B', '-c', (HERE / 'worker-smoke.py').read_text(),
                ], payload, 60, container=name)
                assert smoke
                outcome['roles'][role]['smoke'] = smoke
            outcome['passed'] = all(row['smoke']['typecheck_exit'] == 0 for row in outcome['roles'].values())
        except Exception as error:
            outcome['error_type'] = type(error).__name__
        finally:
            ledger = repo.operation_ledger(GRANT)
            outcome['accounting_settled'] = all(entry.elapsed_seconds is not None for entry in ledger.operations)
            outcome['operations'] = len(ledger.operations)
            save(HERE / 'worker-runtime-ledger.json', ledger.model_dump(mode='json'))
            save(HERE / 'worker-runtime-result.json', outcome)
    print(json.dumps(outcome))
    return outcome['passed'] and outcome['accounting_settled']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument('--freeze', action='store_true')
    flags.add_argument('--execute-delegated')
    args = parser.parse_args()
    if args.freeze:
        freeze()
    else:
        raise SystemExit(not asyncio.run(execute(args.execute_delegated)))
