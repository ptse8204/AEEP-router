"""Build two retained client overlays under the existing sandbox read root."""

import argparse
import asyncio
import json
import runpy
import secrets
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

from aeep.assessment.containment import container_name
from aeep.assessment.models import AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.hosts.codex_app_server import CodexAppServerAdapter
from aeep.hosts.workers import ManagedWorkerBinding
from aeep.models import ActionRequest, ExecutorSpec, StrictModel, utc_now
from aeep.store import ReceiptStore

HERE = Path(__file__).resolve().parent
TOP = HERE.parent
DIAGNOSTIC = TOP / 'sol-sandbox-offline-20261109'
diag = runpy.run_path(str(DIAGNOSTIC / 'diagnose.py'))
build = runpy.run_path(str(TOP / 'worker-runtime.py'))
receipt_fn = runpy.run_path(str(TOP / 'continue-worker-runtime.py'))['make_receipt']
ROOT, WORK, image, docker, inventory = (build[key] for key in ('ROOT', 'WORK', 'image', 'docker', 'inventory'))
read, save, inspect_container = (diag[key] for key in ('read', 'save', 'inspect_container'))
sha = build['sha']
CONTEXT = WORK / 'sol-client-context'
REVIEW = HERE / 'operation-review.json'
GRANT = 'skillsbench-react-sol-permitted-path-20261109'
PREFIX = '/opt/codex/0.159.1'
BINARY = PREFIX + '/bin/codex'
ROLES = {'control': 'control', 'candidate': 'treatment'}
LIMITS = {'build': 150, 'sandbox': 100}
diag['markers'].__globals__['ERROR_MARKERS'].update({
    'versioned_client_path': r'/opt/codex/(?:0\.159\.1)/',
    'codex_helper_alias': r'codex-linux-sandbox',
    'python_program': r'\bpython3\b',
    'failed_exec': r'execvp|failed to execute',
    'failed_bind': r'can.t find source path|bind mount',
})


class Scope(StrictModel):
    review_sha256: str


def verify_artifacts():
    live, pair, _, _, command = diag['offline_inputs']()
    previous = read(DIAGNOSTIC / 'result.json')
    assert previous['review_sha256'] == sha(DIAGNOSTIC / 'operation-review.json')
    assert previous['accounting_settled'] and previous['cleanup_confirmed'] and previous['models'] == 0
    for label in ('canary', 'original_probe'):
        assert previous[label]['exit_code'] == 1
        assert set(previous[label]['stderr_categories']) == {'bubblewrap', 'missing_program_or_path'}
    assert diag['verification_source_digest'](ROOT) == live['source_sha256']
    assert shutil.disk_usage(ROOT).free >= 52 * 1024**3
    assert inventory(CONTEXT) == read(WORK / 'sol-client-context-inventory.json')
    source = read(TOP / 'sol-client-context.json')
    assert sha(CONTEXT / 'runtime/bin/codex') == source['binary_sha256']
    return source, pair, command


def dockerfile(base):
    return (f'FROM {base}\nCOPY runtime/ {PREFIX}/\n'
            f'ENV PATH={PREFIX}/codex-path:{PREFIX}/bin:/opt/codex:/usr/local/bin:/usr/bin:/bin\n')


def get_spec(pair, role, built):
    spec = read(pair)[ROLES[role]]
    config = spec['config']
    original = ManagedWorkerBinding.model_validate(config['managed_worker'])
    assert original.permissions_profile == 'aeep' and original.seccomp_profile
    config['argv'][0] = BINARY
    worker = ManagedWorkerBinding.model_validate(original.model_dump() | {
        'credential_volume': None, 'network_id': None, 'model_proxy_url': None, 'image': built,
        'binary': BINARY, 'worker_id': 'react-sol-permitted-' + role,
    })
    config['managed_worker'] = worker.model_dump(mode='json')
    return ExecutorSpec.model_validate(spec), worker


def scoped(repo, digest, expiry):
    scope = Scope(review_sha256=digest)
    ref = content_digest(scope)
    assert repo.put('toolkit_sol_worker_path_scope', ref, scope) == ref
    repo.approve_bundle(AssessmentAuthorization(authorization_id=GRANT, subject_digests=[ref], recipe_digests=[ref],
        environment_digests=[ref], allowed_destinations=['local'], remote_disclosure=False, expires_at=expiry,
        limits=AssessmentLimits(max_operations=4, max_model_turns=0, max_elapsed_seconds=500)),
        {ref: scope.model_dump(mode='json')})
    return RecipeMaterializationRequest(plan_id=GRANT, subject_digest=ref, recipe_digest=ref, environment_digest=ref,
        mapping_digest=ref, authorization_id=GRANT, definition_digests=[ref], seed=0)


def validate(review, *, starting):
    source, pair, command = verify_artifacts()
    assert utc_now() < datetime.fromisoformat(review['expires_at'])
    assert all(sha(Path(path)) == digest for path, digest in review['pins'].items())
    for role, row in review['roles'].items():
        assert row['parent'] == image(row['base']) == source['roles'][role]['parent']
        assert Path(row['dockerfile']).read_text() == dockerfile(row['base'])
        if starting:
            assert image(row['tag']) is None
    return pair, command


def freeze():
    source, pair, _ = verify_artifacts()
    assert diag['markers']('bwrap: execvp /opt/codex/0.159.1/bin/codex: No such file or directory') == [
        'bubblewrap', 'failed_exec', 'missing_program_or_path', 'versioned_client_path']
    builder = docker('buildx', 'inspect', 'default')
    assert builder.returncode == 0 and 'Driver:        docker' in builder.stdout and 'linux/arm64' in builder.stdout
    assert docker('system', 'df', '--format', '{{.Type}} {{.Size}}').returncode == 0
    roles = {}
    for role in ROLES:
        original = source['roles'][role]
        tag = 'aeep-skillsbench-worker:react-sol-path-20261109-' + role
        assert image(tag) is None and image(original['base']) == original['parent']
        path = HERE / f'Dockerfile.{role}'
        if path.exists():
            assert path.read_text() == dockerfile(original['base'])
        else:
            with path.open('x') as stream:
                stream.write(dockerfile(original['base']))
        roles[role] = {'base': original['base'], 'parent': original['parent'], 'tag': tag, 'dockerfile': str(path)}
        spec, worker = get_spec(pair, role, original['parent']['id'])
        adapter = CodexAppServerAdapter.from_executor(spec, principal_salt=secrets.token_bytes(32))
        try:
            argv = adapter.transport.argv
            assert argv[argv.index('--network') + 1] == 'none' and '--mount' not in argv
            assert BINARY in argv and not adapter.transport.running and worker.permissions_profile == 'aeep'
        finally:
            adapter._worker_security.cleanup()
        with ReceiptStore(':memory:') as store:
            repo = AssessmentRepository(store)
            assert build_spec(roles[role]).config['argv'][-1] == str(CONTEXT)
            req = scoped(repo, 'synthetic', utc_now() + timedelta(seconds=30))
            repo.reserve(req, GRANT, AssessmentLimits(max_operations=1, max_elapsed_seconds=1), stage='sandbox')
            receipt = receipt_fn(GRANT, spec, utc_now(), .01, 'synthetic', None, 'synthetic_failure')
            store.save_receipt(receipt)
            repo.finish_operation(GRANT, elapsed_seconds=.01, resources=receipt.actual_resources)
            assert not receipt.execution_success
    pins = [Path(__file__).resolve(), DIAGNOSTIC / 'diagnose.py', DIAGNOSTIC / 'operation-review.json',
            DIAGNOSTIC / 'result.json', TOP / 'sol-client-context.json', TOP / 'worker-runtime.py',
            TOP / 'continue-worker-runtime.py', TOP / 'acquire-node-packages.py',
            TOP.parent / 'skillsbench-contained-graders-20261105/prepare-images.py',
            build['CARRIER'] / 'runtime-review.json',
            WORK / 'sol-client-context-inventory.json',
            Path(build['DOCKER'][0]).resolve(), Path(build['DOCKER'][2]) / 'config.json',
            pair, *[Path(row['dockerfile']) for row in roles.values()]]
    save(REVIEW, {
        'purpose': 'Check whether placing the unchanged client within the existing managed read root restores sandbox startup.',
        'hypothesis': 'Codex re-executes its current binary after bubblewrap mounts the restricted filesystem.',
        'client_version': source['source_version'], 'binary_sha256': source['binary_sha256'], 'client_root': PREFIX,
        'upstream_source': 'https://github.com/openai/codex/blob/rust-v0.159.1/codex-rs/linux-sandbox/src/linux_run_main.rs#L1539',
        'pins': {str(path): sha(path) for path in pins}, 'roles': roles, 'existing_policy_changes': False,
        'builds': 2, 'offline_workers': 2, 'maximum_sandbox_commands': 4, 'maximum_operations': 4,
        'maximum_reserved_seconds': 500, 'minimum_usable_gib_before_builds': 52, 'models': 0, 'cash_usd': '0',
        'network': False, 'credential_volume': False, 'downloads': False, 'pulls': False, 'proxy_start': False,
        'cleanup': 'Only new owned diagnostic containers; retain all images and volumes.',
        'automatic_retries': False, 'comparisons': 'PAUSED', 'preflight_only': True,
        'expires_at': (utc_now() + timedelta(hours=18)).isoformat(),
    })
    validate(read(REVIEW), starting=True)
    print(sha(REVIEW))


async def check_sandbox(pair, role, built, command, facts):
    spec, worker = get_spec(pair, role, built)
    adapter = CodexAppServerAdapter.from_executor(spec, principal_salt=secrets.token_bytes(32))
    name = container_name(adapter._worker_process_id)
    owns_name = False
    try:
        assert inspect_container(worker, name) is None
        owns_name = True
        facts['container_name'] = name
        async with asyncio.timeout(55):
            await diag['observe'](adapter.transport, command, facts)
        command_facts = facts['original_probe']['observation']
        assert facts['canary']['observation'] == {'canary_matched': True}
        assert command_facts and command_facts['workspace_write']
        assert command_facts['configuration_write'] in ('denied', 'read_only')
        assert all(command_facts[key] in ('denied', 'unreachable') for key in ('proxy', 'direct'))
        assert all(row['matches'] for row in facts['configRequirements/read'].values())
    finally:
        try:
            try:
                await asyncio.wait_for(adapter.transport.close(), timeout=5)
            finally:
                if owns_name:
                    cid = inspect_container(worker, name)
                    if cid is not None:
                        identity = diag['docker'](worker, 'container', 'inspect', '--format', '{{.Image}} {{.Name}}', cid)
                        assert identity == f'{built} /{name}'
                        assert diag['docker'](worker, 'container', 'rm', '--force', cid) == cid
                    facts['cleanup_confirmed'] = inspect_container(worker, name) is None
                    assert facts['cleanup_confirmed']
        finally:
            adapter._worker_security.cleanup()


def build_spec(row):
    return ExecutorSpec(id='skillsbench.react.sol-path-build', capability='toolkit.upstream-engineering@1',
        kind='command', description='Build reviewed local Sol client overlay', side_effect='write',
        config={'argv': [*build['DOCKER'], 'build', '--pull=false', '--network=none', '--platform=linux/arm64',
                          '--builder=default', '--provenance=false', '--sbom=false', '--file', row['dockerfile'],
                          '--tag', row['tag'], str(CONTEXT)],
                'argv_literal': True, 'inherit_env': False, 'env': build['ENV'], 'cwd': str(WORK),
                'timeout_seconds': 125, 'max_output_bytes': 16384, 'output': {'type': 'text'}})


async def local_build(row, spec, operation, authorize):
    assert image(row['tag']) is None
    runner = CommandExecutor()
    try:
        raw = await runner.execute(ExecutionContext(request=ActionRequest(action_id=operation,
            capability=spec.capability), spec=spec, estimate=spec.estimate, attempt=1, attempt_id=operation,
            approved_side_effect=spec.side_effect, invocation_check=authorize))
        if raw.status.value != 'success':
            raise RuntimeError('offline Docker build stopped')
    finally:
        await runner.close()
    created = image(row['tag'])
    assert created and created['layers'][:-1] == row['parent']['layers']
    assert all(created[key] == row['parent'][key] for key in ('platform', 'user', 'volumes'))
    return created


async def execute(identity):
    review = read(REVIEW)
    assert identity == sha(REVIEW)
    assert read(HERE / 'approval.json') == {'approved': True, 'review_sha256': identity}
    assert not (HERE / 'started.json').exists()
    ledger_path = WORK / 'sol-sandbox-path-20261109.sqlite3'
    assert not ledger_path.exists()
    pair, command = validate(review, starting=True)
    save(HERE / 'started.json', {'review_sha256': identity, 'models': 0})
    result = {'review_sha256': identity, 'passed': False, 'models': 0, 'roles': {}, 'comparisons': 'PAUSED'}
    expiry = datetime.fromisoformat(review['expires_at'])
    with ReceiptStore(str(ledger_path)) as store:
        repo = AssessmentRepository(store)
        request = scoped(repo, identity, expiry)
        try:
            for role, row in review['roles'].items():
                result['roles'][role] = {}
                for stage, seconds in LIMITS.items():
                    validate(review, starting=False)
                    operation = f'{GRANT}:{role}:{stage}'
                    repo.reserve(request, operation, AssessmentLimits(max_operations=1, max_elapsed_seconds=seconds), stage=stage)
                    started, clock = utc_now(), time.monotonic()
                    facts, failure = {}, None
                    spec = build_spec(row) if stage == 'build' else get_spec(pair, role, row['parent']['id'])[0]

                    def authorize():
                        repo.authorize(request)
                        validate(review, starting=False)
                        return identity

                    try:
                        authorize()
                        if stage == 'build':
                            facts.update(await local_build(row, spec, operation, authorize))
                        else:
                            await check_sandbox(pair, role, result['roles'][role]['build']['id'], command, facts)
                    except Exception as error:
                        failure = type(error).__name__
                        raise
                    finally:
                        elapsed = time.monotonic() - clock
                        result['roles'][role][stage] = facts
                        receipt = receipt_fn(operation, spec, started, elapsed, identity,
                                             facts if failure is None else None, failure)
                        store.save_receipt(receipt)
                        repo.finish_operation(operation, elapsed_seconds=elapsed, resources=receipt.actual_resources)
                        save(HERE / f'{role}-{stage}-receipt.json', receipt.model_dump(mode='json'))
            result['passed'] = True
        except Exception as error:
            result['error_type'] = type(error).__name__
        finally:
            ledger = repo.operation_ledger(GRANT)
            result['operations'] = len(ledger.operations)
            result['accounting_settled'] = all(row.elapsed_seconds is not None for row in ledger.operations)
            save(HERE / 'ledger.json', ledger.model_dump(mode='json'))
            save(HERE / 'result.json', result)
    print(json.dumps(result))
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
        validate(read(REVIEW), starting=True)
        print(json.dumps({'review_sha256': sha(REVIEW), 'preflight_passed': True, 'executed': False}))
    else:
        raise SystemExit(not asyncio.run(execute(args.execute_approved)))
