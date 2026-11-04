"""Build the exact upstream CLI and check its real isolated local registry.

Requires the specific grouped review and its recorded operator approval. This
does not implement a substitute registry, invoke an agent or test usefulness.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from aeep.assessment.models import AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, SideEffect, StrictModel, utc_now
from aeep.store import ReceiptStore

DOCKER = ['/usr/local/bin/docker', '--host', 'unix:///Users/edwintse/.docker/run/docker.sock']


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree_hash(root):
    files = {}
    for p in sorted(Path(root).rglob('*')):
        if p.is_symlink():
            raise ValueError('Owned source/runtime tree contains a symlink')
        if p.is_file():
            files[p.relative_to(root).as_posix()] = file_hash(p)
    return content_digest(files)


def validate():
    review = json.loads((HERE / 'operation-review.json').read_bytes())
    for path, target in review.get('executable_links', {}).items():
        if str(Path(path).resolve(strict=True)) != target:
            raise ValueError('Reviewed executable link changed')
    for path, expected in review['assets'].items():
        if file_hash(path) != expected:
            raise ValueError('A reviewed input changed: ' + path)
    if tree_hash(review['build_context']) != review['build_context_sha256']:
        raise ValueError('Pinned build context changed')
    if verification_source_digest(ROOT) != review['source']:
        raise ValueError('Coordinator source changed after review')
    if utc_now() + timedelta(hours=2) >= datetime.fromisoformat(review['expires_at'].replace('Z', '+00:00')):
        raise ValueError('Exact review lacks its full finite execution/cleanup window')
    gates = json.loads(Path(review['source_checks']).read_bytes())
    ready = (gates['source_before'] == gates['source_after'] == review['source']
             and len(gates['checks']) == 13 and all(c['exit_code'] == 0 for c in gates['checks']))
    if not ready:
        raise ValueError('All thirteen source checks must pass before consuming an attempt')
    if shutil.disk_usage(ROOT).free < 58 * 1024**3:
        raise ValueError('Build needs the normal 50 GiB reserve plus eight GiB headroom')
    return review


class Scope(StrictModel):
    role: str
    review_sha256: str
    purpose: str = 'Actual pinned SkillRank build/search/show; bounded evaluation remains open'


async def execute(review, identity):
    wrapper_began = time.monotonic()
    runtime = Path(review['runtime'])
    with (HERE / 'runtime-started.json').open('x') as f:
        json.dump({'review_sha256': identity, 'started_at': utc_now().isoformat()}, f)
    runtime.mkdir(mode=0o700)
    execution = HERE / 'runtime-execution'
    execution.mkdir(mode=0o700)
    for name in ('home', 'tmp', 'docker-config'):
        (execution / name).mkdir(mode=0o700)
    (execution / 'docker-config/config.json').write_text(json.dumps({
        'auths': {'https://index.docker.io/v1/': {}}, 'credsStore': '', 'credHelpers': {}}) + '\n')
    work = runtime / 'work'
    work.mkdir(mode=0o777)
    work.chmod(0o777)
    for name in ('home', 'tmp', 'cargo'):
        (work / name).mkdir(mode=0o777)
        (work / name).chmod(0o777)
    session = runtime / 'session'
    session.mkdir(mode=0o777)
    session.chmod(0o777)
    for name in ('home', 'tmp', 'cargo'):
        (session / name).mkdir(mode=0o777)
        (session / name).chmod(0o777)
    host_canary = runtime / 'host-only-canary'
    host_canary.write_text('First-party public boundary canary, not mounted.\n')
    initial_free = shutil.disk_usage(ROOT).free
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(execution / 'home'),
           'TMPDIR': str(execution / 'tmp'), 'DOCKER_CONFIG': str(execution / 'docker-config'),
           'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1'}
    store = ReceiptStore(execution / 'canonical.sqlite3')
    repo = AssessmentRepository(store)
    refs = []
    for role in ('subject', 'recipe', 'environment', 'mapping'):
        ref = repo.put('toolkit_engineering_scope', role, Scope(role=role, review_sha256=identity))
        repo.review(ref)
        refs.append(ref)
    grant = AssessmentAuthorization(authorization_id='skillrank-engineering-' + identity,
        subject_digests=[refs[0]], recipe_digests=[refs[1]], environment_digests=[refs[2]],
        limits=AssessmentLimits(max_model_turns=0, max_operations=40, max_elapsed_seconds=4500,
                                max_cash_usd=Decimal(0)),
        allowed_destinations=['local', 'static.crates.io', 'DockerHub-public-OCI'],
        expires_at=utc_now() + timedelta(hours=2))
    repo.grant(grant)
    request = RecipeMaterializationRequest(subject_digest=refs[0], recipe_digest=refs[1],
        environment_digest=refs[2], mapping_digest=refs[3], authorization_id=grant.authorization_id,
        definition_digests=refs, seed=0)
    repo.put('recipe_materialization_request', request.plan_id, request)
    overhead_id = 'skillrank:' + identity + ':wrapper-overhead'
    repo.reserve(request, overhead_id, AssessmentLimits(max_operations=1, max_model_turns=0,
                 max_elapsed_seconds=300), stage='skillrank_wrapper_overhead')
    nested_seconds = 0.0
    executor = CommandExecutor()
    owned = []
    result = {'passed': False, 'models': 0, 'candidate_usefulness': 'NOT_ASSESSED',
              'selection_usefulness': 'NOT_ASSESSED', 'all_stack_complete': False,
              'skillrank_bounded_evaluation': 'OPEN', 'comparisons': 'PAUSED'}

    def capacity(*, strict=False):
        free = shutil.disk_usage(ROOT).free
        if free < 50 * 1024**3 or initial_free - free > 6 * 1024**3:
            raise ValueError('Actual host reserve or six-GiB net-capacity bound reached')
        if verification_source_digest(ROOT) != review['source']:
            raise ValueError('Coordinator source drift; stop dependent dispatch')
        if time.monotonic() - wrapper_began > 4300:
            raise TimeoutError('Finite runtime execution window exhausted; preserve cleanup time')
        if not strict:
            return
        for path, target in review.get('executable_links', {}).items():
            if str(Path(path).resolve(strict=True)) != target:
                raise ValueError('Reviewed executable link changed')
        for path, expected in review['assets'].items():
            if file_hash(path) != expected:
                raise ValueError('Reviewed executable/document input drift')
        if tree_hash(review['build_context']) != review['build_context_sha256']:
            raise ValueError('Reviewed build context changed')
        if 'vendor_tree_sha256' in result and tree_hash(runtime / 'vendor') != result['vendor_tree_sha256']:
            raise ValueError('Offline dependency source changed')
        if 'binary_sha256' in result and file_hash(work / 'target/release/skillrank') != result['binary_sha256']:
            raise ValueError('Built executable changed')

    async def run(name, argv, seconds, *, cleanup=False):
        nonlocal nested_seconds
        if not cleanup:
            capacity(strict=True)
        repo.authorize(request)
        key = 'skillrank:' + identity + ':' + name
        spec = ExecutorSpec(id='skillrank-' + name, capability='toolkit.upstream-engineering@1',
            description='Reviewed pinned SkillRank component engineering', kind='command',
            side_effect='write', requires_network=name in {'crate-source', 'compiler-image'},
            config={'argv': argv, 'argv_literal': True, 'stdin_json': False, 'inherit_env': False,
                    'timeout_seconds': seconds, 'max_output_bytes': 1048576,
                    'env': env, 'output': {'type': 'text'}})
        action = ActionRequest(capability=spec.capability, input={})
        repo.reserve(request, key, AssessmentLimits(max_operations=1, max_model_turns=0,
                     max_elapsed_seconds=seconds + 5), stage='skillrank_' + name)
        raw, handle = None, None
        started_at, began = utc_now(), time.monotonic()
        try:
            handle = await executor.start(ExecutionContext(request=action, spec=spec,
                estimate=spec.estimate, attempt=1, attempt_id=key, approved_side_effect=SideEffect.WRITE,
                invocation_check=lambda: (repo.authorize(request), None)[1]))
            while not handle.task.done():
                await asyncio.wait({handle.task}, timeout=1)
                if not cleanup:
                    capacity()
            raw = await handle.task
            receipt = ExecutionReceipt(decision_id=key, action_id=action.action_id,
                capability=spec.capability, executor_id=spec.id, executor_kind=spec.kind,
                status=raw.status, started_at=started_at, ended_at=utc_now(), estimated=spec.estimate,
                actual_resources=raw.resources, accounting=raw.accounting,
                execution_success=raw.status.value == 'success', error_type=raw.error_type,
                metadata={'review_sha256': identity, 'scope': 'isolated_component_engineering',
                          'client_resources_are_not_container_resources': True, **raw.metadata})
            store.save_receipt(receipt)
            (execution / (name + '-receipt.json')).write_text(receipt.model_dump_json(indent=2) + '\n')
            (execution / (name + '-process.json')).write_text(json.dumps({
                'stdout': (raw.stdout or '')[:16384], 'stderr': (raw.stderr or '')[:16384],
                'status': raw.status.value, 'error_type': raw.error_type}, indent=2) + '\n')
            return raw
        finally:
            if handle is not None and not handle.task.done():
                await executor.cancel(handle)
            repo.finish_operation(key, elapsed_seconds=time.monotonic() - began,
                accounting=raw.accounting if raw else None, resources=raw.resources if raw else None)
            nested_seconds += time.monotonic() - began

    def inspect(arguments):
        return subprocess.run([*DOCKER, *arguments], env=env, capture_output=True,
                              text=True, timeout=30, check=True).stdout

    def container(name, image, command, *, serve=False):
        absent = subprocess.run([*DOCKER, 'container', 'inspect', name], env=env,
                                capture_output=True, text=True, timeout=15)
        if absent.returncode == 0 or 'No such' not in absent.stderr:
            raise ValueError('New container name is not proven absent')
        cid = execution / (name + '.cid')
        if cid.exists():
            raise ValueError('Container identity file already exists')
        owned.append({'name': name, 'cid': cid, 'image': image})
        context = review['build_context']
        args = [*DOCKER, 'run', '--detach' if serve else '--rm', '--name', name, '--cidfile', str(cid),
            '--label', 'aeep.review=' + identity, '--network', 'none', '--read-only',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--user', '65534:65534',
            '--pids-limit', '256', '--memory', '2g', '--memory-swap', '2g', '--cpus', '2',
            '--mount', 'type=bind,src=' + context + '/source,dst=/source,readonly',
            '--mount', 'type=bind,src=' + str(runtime / 'vendor') + ',dst=/vendor,readonly',
            '--mount', 'type=bind,src=' + context + '/checks,dst=/checks,readonly',
            '--mount', 'type=bind,src=' + context + '/catalog.json,dst=/catalog.json,readonly',
            '--mount', 'type=bind,src=' + str(session if serve else work) + ',dst=/work',
            '--workdir', '/source', '--env', 'HOME=/work/home', '--env', 'TMPDIR=/work/tmp',
            '--env', 'CARGO_HOME=/work/cargo', '--env', 'RUSTUP_AUTO_INSTALL=0',
            '--env', 'SKILLRANK_NO_UPDATE_CHECK=1', '--env', 'CI=1',
            '--env', 'SKILLRANK_HOME=/work/home/.skillrank',
            '--env', 'SKILLRANK_API_URL=http://127.0.0.1:18899']
        if serve:
            args += ['--mount', 'type=bind,src=' + str(work / 'target/release/skillrank') + ',dst=/opt/skillrank,readonly',
                     '--mount', 'type=bind,src=' + str(work / 'boundary') + ',dst=/opt/aeep-boundary,readonly']
        args += [image, *command]
        return args

    try:
        (execution / 'docker-before.json').write_text(inspect(['system', 'df', '--format', 'json']))
        mirrors = json.loads(inspect(['info', '--format', '{{json .RegistryConfig.Mirrors}}']))
        if mirrors:
            raise ValueError('Unreviewed registry mirror; no image pull')
        download = await run('crate-source', [sys.executable, '-I', '-B', str(HERE / 'vendor-entry.py')], 660)
        if download.status.value != 'success':
            raise ValueError('Exact Cargo source preparation failed')
        vendor_digest = tree_hash(runtime / 'vendor')
        result['vendor_tree_sha256'] = vendor_digest
        pull = await run('compiler-image', [*DOCKER, 'pull', '--platform', 'linux/arm64', review['compiler_image']], 600)
        if pull.status.value != 'success':
            raise ValueError('Exact public compiler image pull failed')
        image = json.loads(inspect(['image', 'inspect', review['compiler_image'], '--format',
            '{"Id":{{json .Id}},"RepoDigests":{{json .RepoDigests}},"Architecture":{{json .Architecture}},"Os":{{json .Os}}}']))
        if image['Architecture'] != 'arm64' or image['Os'] != 'linux':
            raise ValueError('Compiler image platform differs')
        result['compiler_image'] = image
        (execution / 'image-binding.json').write_text(json.dumps(image, indent=2) + '\n')
        cargo = ['cargo', 'build', '--locked', '--offline', '--release', '--jobs', '2',
                 '--package', 'skillrank', '--target-dir', '/work/target',
                 '--config', 'source.crates-io.replace-with="vendored-sources"',
                 '--config', 'source.vendored-sources.directory="/vendor"']
        # One build is dispatched. The review reserves no automatic source repair.
        built = await run('build', container('aeep-skillrank-build-' + identity[:10], image['Id'], cargo), 900)
        if built.status.value != 'success':
            raise ValueError('Offline pinned source build failed; retain partial output')
        probe = await run('compile-boundary', container('aeep-skillrank-probe-' + identity[:10], image['Id'],
            ['rustc', '/checks/boundary.rs', '-o', '/work/boundary']), 60)
        if probe.status.value != 'success':
            raise ValueError('First-party boundary compilation failed')
        binary = work / 'target/release/skillrank'
        result['binary_sha256'] = file_hash(binary)
        name = 'aeep-skillrank-serve-' + identity[:10]
        started = await run('serve', container(name, image['Id'],
            ['/opt/skillrank', 'serve', '--host', '127.0.0.1', '--port', '18899',
             '--catalog', '/catalog.json'], serve=True), 20)
        if started.status.value != 'success':
            raise ValueError('Actual upstream local registry did not start')
        metadata = json.loads(inspect(['container', 'inspect', name, '--format',
            '{"Id":{{json .Id}},"Image":{{json .Image}},"NetworkMode":{{json .HostConfig.NetworkMode}},"ReadonlyRootfs":{{json .HostConfig.ReadonlyRootfs}},"User":{{json .Config.User}},"CapDrop":{{json .HostConfig.CapDrop}},"SecurityOpt":{{json .HostConfig.SecurityOpt}},"Mounts":{{json .Mounts}}}']))
        if (metadata['Image'] != image['Id'] or metadata['NetworkMode'] != 'none'
                or metadata['ReadonlyRootfs'] is not True or metadata['User'] != '65534:65534'
                or metadata['CapDrop'] != ['ALL']
                or not any('no-new-privileges' in s for s in metadata['SecurityOpt'])
                or {m['Destination'] for m in metadata['Mounts']} != {'/source', '/vendor', '/checks', '/catalog.json', '/work', '/opt/skillrank', '/opt/aeep-boundary'}
                or {m['Destination'] for m in metadata['Mounts'] if m['RW']} != {'/work'}):
            raise ValueError('Actual service boundary differs from review')
        (execution / 'service-binding.json').write_text(json.dumps(metadata, indent=2) + '\n')
        compiler = await run('compiler-version', [*DOCKER, 'exec', '--user', '65534:65534',
            metadata['Id'], 'rustc', '--version'], 10)
        if compiler.status.value != 'success' or not (compiler.stdout or '').startswith('rustc 1.94.1 '):
            raise ValueError('Observed compiler version differs from the selected runtime')
        result['compiler_version'] = (compiler.stdout or '').strip()
        def cli(*args):
            return [*DOCKER, 'exec', '--user', '65534:65534', metadata['Id'],
                    '/opt/skillrank', *args]
        version = await run('version', cli('--version'), 10)
        if version.status.value != 'success' or (version.stdout or '').strip() != 'skillrank 0.1.5':
            raise ValueError('Built CLI version differs')
        found = None
        for attempt in range(5):
            found = await run('search-' + str(attempt), cli('search', 'stack-check', '--json'), 10)
            if found.status.value == 'success':
                break
        if found.status.value != 'success':
            raise ValueError('Actual upstream search failed')
        search = json.loads(found.stdout)
        if [x['slug'] for x in search['items']] != ['aeep/stack-check']:
            raise ValueError('Actual search did not preserve catalog filtering')
        shown = await run('show', cli('show', 'aeep/stack-check', '--json'), 10)
        if shown.status.value != 'success':
            raise ValueError('Actual show failed')
        detail = json.loads(shown.stdout)
        if detail['slug'] != 'aeep/stack-check' or not detail['versions']:
            raise ValueError('Actual show lost the selected record')
        missing = await run('missing-record', cli('show', 'aeep/absent', '--json'), 10)
        if missing.status.value == 'success' or 'not found' not in (missing.stderr or ''):
            raise ValueError('Missing catalog record did not fail explicitly')
        boundary = await run('boundary', [*DOCKER, 'exec', '--user', '65534:65534', metadata['Id'],
            '/opt/aeep-boundary', str(host_canary)], 15)
        if boundary.status.value != 'success' or json.loads(boundary.stdout)['passed'] is not True:
            raise ValueError('Actual runtime boundary probe failed')
        if tree_hash(runtime / 'vendor') != vendor_digest or file_hash(binary) != result['binary_sha256']:
            raise ValueError('Runtime inputs or selected binary changed')
        result.update(passed=True, search_show=True, real_upstream_server=True,
                      external_registry_used=False, runtime_retained=True,
                      local_catalog_safe_labels_are_not_scanner_evidence=True)
    except BaseException as error:
        result.update(error_type=type(error).__name__, error=str(error)[:300])
    finally:
        cleanup = []
        for index, owned_item in enumerate(owned):
            name = owned_item['name']
            try:
                cid = owned_item['cid'].read_text().strip() if owned_item['cid'].exists() else None
                if cid is not None and re.fullmatch('[0-9a-f]{64}', cid) is None:
                    raise ValueError('Owned container identity file is invalid')
                check = subprocess.run([*DOCKER, 'container', 'inspect', cid or name, '--format',
                    '{"Id":{{json .Id}},"Image":{{json .Image}},"Running":{{json .State.Running}},"Label":{{json (index .Config.Labels "aeep.review")}}}'],
                    env=env, capture_output=True, text=True, timeout=20)
                if check.returncode != 0:
                    cleanup.append({'name': name, 'id': cid, 'absent': 'No such' in check.stderr})
                    continue
                item = json.loads(check.stdout)
                if item['Label'] != identity or item['Id'] != cid or item['Image'] != owned_item['image']:
                    raise ValueError('Owned container identity/configuration differs; preserve it')
                if item['Running']:
                    await run('stop-owned-' + str(index), [*DOCKER, 'stop', '--time', '5', item['Id']], 15, cleanup=True)
                removed = await run('remove-owned-' + str(index), [*DOCKER, 'rm', item['Id']], 15, cleanup=True)
                cleanup.append({'name': name, 'id': item['Id'], 'removed': removed.status.value == 'success'})
            except BaseException as error:
                cleanup.append({'name': name, 'error_type': type(error).__name__, 'uncertain': True})
        result['cleanup'] = cleanup
        result['cleanup_uncertain'] = not all(c.get('absent') or c.get('removed') for c in cleanup)
        result['passed'] = result['passed'] and not result['cleanup_uncertain']
        result['free_bytes_after'] = shutil.disk_usage(ROOT).free
        exclusive = time.monotonic() - wrapper_began - nested_seconds
        if exclusive < 0:
            raise ValueError('Wrapper accounting intervals overlap')
        repo.finish_operation(overhead_id, elapsed_seconds=exclusive)
        result['wrapper_exclusive_seconds'] = exclusive
        result['nested_operation_seconds'] = nested_seconds
        result['wrapper_timing_scope'] = 'Inspection/preparation/report overhead through ledger finalization; nested operation intervals excluded. Final summary write is outside this interval.'
        ledger = repo.operation_ledger(request.plan_id)
        result['accounting_uncertain'] = any(op.elapsed_seconds is None for op in ledger.operations)
        result['passed'] = result['passed'] and not result['accounting_uncertain']
        (execution / 'operation-ledger.json').write_text(ledger.model_dump_json(indent=2) + '\n')
        (execution / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
        await executor.close()
        store.close()
    print(json.dumps(result, indent=2))
    return result['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-approved', required=True)
    args = parser.parse_args()
    review = validate()
    identity = file_hash(HERE / 'operation-review.json')
    approval = json.loads((HERE / 'operator-approval.json').read_bytes())
    if args.execute_approved != identity or approval['review_sha256'] != identity or approval.get('approved') is not True:
        raise SystemExit('Exact recorded approval required')
    raise SystemExit(0 if asyncio.run(execute(review, identity)) else 1)
