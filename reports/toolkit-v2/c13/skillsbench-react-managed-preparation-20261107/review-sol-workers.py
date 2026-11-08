"""Stage and optionally build two reviewed Sol-capable worker images, with zero model turns."""

import argparse
import asyncio
import json
import mmap
import runpy
import shutil
import tarfile
import time
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath

from aeep.assessment.models import AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutorSpec, StrictModel, utc_now
from aeep.store import ReceiptStore

HERE = Path(__file__).resolve().parent
helper = runpy.run_path(str(HERE / 'worker-runtime.py'))
receipt_helper = runpy.run_path(str(HERE / 'continue-worker-runtime.py'))
acquisition = runpy.run_path(str(HERE / 'acquire-sol-client.py'))
ROOT, WORK, read, save, sha, image, docker, inventory = (
    helper[k] for k in ('ROOT', 'WORK', 'read', 'save', 'sha', 'image', 'docker', 'inventory')
)
PREFIX = '/opt/codex-0.159.1'
CONTEXT = WORK / 'sol-client-context'
STAGING = HERE / 'sol-client-context.json'
REVIEW = HERE / 'sol-client-worker-review.json'
ARCHIVE = acquisition['ARCHIVE']
VENDOR = 'package/vendor/aarch64-unknown-linux-musl/'
GRANT = 'skillsbench-react-sol-client-20261108'
RESERVE = 50 * 1024**3


class Scope(StrictModel):
    review_sha256: str


def stage():
    source = read(HERE / 'sol-client-acquisition-result.json')
    assert source['passed'] and not source['executed'] and sha(ARCHIVE) == source['archive_sha256']
    assert shutil.disk_usage(ROOT).free >= RESERVE + 3 * 1024**3
    previous = read(helper['REVIEW'])
    parity = read(HERE / 'worker-image-parity.json')
    roots = CONTEXT / 'runtime'
    roots.mkdir(mode=0o700, parents=True)
    expected = {name: row for name, row in source['files'].items() if name.startswith(VENDOR)}
    with tarfile.open(ARCHIVE, 'r|gz') as archive:
        for entry in archive:
            if not entry.isfile() or entry.name not in expected:
                continue
            relative = PurePosixPath(entry.name.removeprefix(VENDOR))
            assert not relative.is_absolute() and '..' not in relative.parts
            destination = roots.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(entry) as body, destination.open('xb') as output:
                shutil.copyfileobj(body, output)
            row = expected[entry.name]
            assert destination.stat().st_size == row['bytes'] and sha(destination) == row['sha256']
            destination.chmod(0o555 if row['executable'] else 0o444)
    roots.chmod(0o755)
    assert len(inventory(roots)) == len(expected)
    layout = read(roots / 'codex-package.json')
    assert layout == {'layoutVersion': 1, 'version': '0.159.1', 'target': 'aarch64-unknown-linux-musl',
                      'variant': 'codex', 'entrypoint': 'bin/codex', 'resourcesDir': 'codex-resources',
                      'pathDir': 'codex-path'}
    with (roots / 'bin/codex').open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as binary:
        assert binary[:6] == b'\x7fELF\x02\x01' and binary[18:20] == b'\xb7\x00'
        assert binary.find(b'gpt-6.1-sol') >= 0
    roles = {}
    for role, row in previous['roles'].items():
        parent = image(row['tag'])
        assert parent == parity['images'][role] and parent['user'] == '65534:65534' and not parent['volumes']
        tag = 'aeep-skillsbench-worker:react-sol-01591-' + role + '-20261108'
        assert image(tag) is None
        dockerfile = CONTEXT / ('Dockerfile.' + role)
        dockerfile.write_text(f"FROM {row['tag']}\nCOPY runtime/ {PREFIX}/\nENV PATH={PREFIX}/codex-path:{PREFIX}/bin:/usr/local/bin:/usr/bin:/bin\n")
        roles[role] = {'base': row['tag'], 'parent': parent, 'tag': tag, 'dockerfile': str(dockerfile)}
    save(WORK / 'sol-client-context-inventory.json', inventory(CONTEXT))
    save(STAGING, {'roles': roles, 'vendor_files': len(expected),
                   'binary_sha256': sha(roots / 'bin/codex'), 'new_binary': PREFIX + '/bin/codex',
                   'binary_contains_sol_identifier': True, 'archive_sha256': source['archive_sha256'],
                   'source_version': layout['version'], 'models': 0, 'builds': 0})


def check(review=None):
    context = read(STAGING)
    assert shutil.disk_usage(ROOT).free >= RESERVE + 3 * 1024**3
    assert verification_source_digest(ROOT) == helper['OLD']['source_sha256']
    assert docker('system', 'df', '--format', '{{.Type}} {{.Size}}').returncode == 0
    builder = docker('buildx', 'inspect', 'default')
    assert builder.returncode == 0 and 'Driver:        docker' in builder.stdout and 'linux/arm64' in builder.stdout
    assert inventory(CONTEXT) == read(WORK / 'sol-client-context-inventory.json')
    for role, row in context['roles'].items():
        assert image(row['base']) == row['parent'] and image(row['tag']) is None
        assert helper['absent']('aeep-react-sol-client-' + role)
    if review is not None:
        assert all(sha(Path(path)) == value for path, value in review['pins'].items())
    return context


def freeze():
    stage()
    check()
    paths = [Path(__file__).resolve(), HERE / 'sol-client-catalogue.py', STAGING,
             HERE / 'sol-client-acquisition-result.json', HERE / 'sol-managed-model-blocker.json',
             HERE / 'worker-runtime.py', HERE / 'continue-worker-runtime.py', HERE / 'worker-image-parity.json',
             WORK / 'sol-client-context-inventory.json', Path(helper['DOCKER'][0]),
             Path(helper['DOCKER'][2]) / 'config.json']
    save(REVIEW, {'scope': 'Two local Sol client COPY builds and two offline bundled-catalogue checks.',
        'pins': {str(path): sha(path) for path in paths}, 'source_version': '0.159.1',
        'source_sha256': helper['OLD']['source_sha256'], 'maximum_operations': 4,
        'maximum_reserved_seconds': 400, 'builds': 2, 'offline_catalogue_checks': 2, 'models': 0, 'cash_usd': '0',
        'proxy_start': False, 'account_methods': False, 'network': False, 'downloads': False, 'pulls': False,
        'automatic_retries': False, 'existing_resource_deletion': False, 'comparisons': 'PAUSED',
        'expires_at': (utc_now() + timedelta(hours=12)).isoformat()})
    print(sha(REVIEW))


async def execute(identity):
    review = read(REVIEW)
    assert sha(REVIEW) == identity
    assert read(HERE / 'sol-client-worker-approval.json') == {'approved': True, 'review_sha256': identity}
    assert not (HERE / 'sol-client-worker-started.json').exists()
    expiry = datetime.fromisoformat(review['expires_at'])
    assert utc_now() < expiry
    context = check(review)
    scope = Scope(review_sha256=identity)
    ref = content_digest(scope)
    limits = AssessmentLimits(max_operations=4, max_model_turns=0, max_elapsed_seconds=400)
    grant = AssessmentAuthorization(authorization_id=GRANT, subject_digests=[ref], recipe_digests=[ref],
        environment_digests=[ref], limits=limits, allowed_destinations=['local'], remote_disclosure=False, expires_at=expiry)
    request = RecipeMaterializationRequest(plan_id=GRANT, subject_digest=ref, recipe_digest=ref,
        environment_digest=ref, mapping_digest=ref, authorization_id=GRANT, definition_digests=[ref], seed=0)
    save(HERE / 'sol-client-worker-started.json', {'review_sha256': identity})
    result = {'review_sha256': identity, 'images': {}, 'catalogues': {}, 'passed': False, 'models': 0}
    with ReceiptStore(helper['OLD']['ledger']) as store:
        repo = AssessmentRepository(store)
        assert repo.put('toolkit_react_sol_client_scope', ref, scope) == ref
        repo.approve_bundle(grant, {ref: scope.model_dump(mode='json')})

        async def run(role, kind, argv, reserved, verify, name=None):
            spec = ExecutorSpec(id='skillsbench.react.sol.' + kind, capability='toolkit.upstream-engineering@1',
                kind='command', description='Reviewed Sol worker ' + kind, side_effect='write',
                config={'argv': [*helper['DOCKER'], *argv], 'argv_literal': True, 'inherit_env': False, 'env': helper['ENV'],
                        'cwd': str(WORK), 'timeout_seconds': reserved - 10, 'max_output_bytes': 65536,
                        'output': {'type': 'json' if name else 'text'}})
            op = GRANT + ':' + role + ':' + kind
            repo.reserve(request, op, AssessmentLimits(max_operations=1, max_elapsed_seconds=reserved), stage=kind)
            clock, started = time.perf_counter(), utc_now()
            runner = CommandExecutor()
            facts, failure = None, None

            def authorize():
                repo.authorize(request)
                assert utc_now() < expiry and shutil.disk_usage(ROOT).free >= RESERVE
                assert verification_source_digest(ROOT) == review['source_sha256']
                assert all(sha(Path(path)) == value for path, value in review['pins'].items())
                assert inventory(CONTEXT) == read(WORK / 'sol-client-context-inventory.json')
                return identity

            try:
                raw = await runner.execute(ExecutionContext(
                    request=ActionRequest(action_id=op, capability=spec.capability), spec=spec, estimate=spec.estimate,
                    attempt=1, attempt_id=op, approved_side_effect=spec.side_effect, invocation_check=authorize))
                if raw.status.value != 'success':
                    failure = raw.error_type or 'command_failed'
                    raise RuntimeError(failure)
                facts = verify(raw)
                return facts
            except Exception as error:
                failure = failure or type(error).__name__
                raise
            finally:
                cleanup_error = None
                if name and not helper['absent'](name):
                    tag = docker('container', 'inspect', '--format', '{{index .Config.Labels "aeep.sol-client"}}', name)
                    if tag.returncode == 0 and tag.stdout.strip() == GRANT:
                        docker('rm', '--force', name)
                    if not helper['absent'](name):
                        cleanup_error = RuntimeError('owned probe cleanup unverified')
                        facts, failure = None, 'cleanup_unverified'
                await runner.close()
                elapsed = time.perf_counter() - clock
                receipt = receipt_helper['make_receipt'](op, spec, started, elapsed, identity, facts, failure)
                store.save_receipt(receipt)
                repo.finish_operation(op, elapsed_seconds=elapsed, resources=receipt.actual_resources)
                save(HERE / f'sol-client-{role}-{kind}-receipt.json', receipt.model_dump(mode='json'))
                if cleanup_error:
                    raise cleanup_error

        try:
            for role, entry in context['roles'].items():
                def verify_build(_raw):
                    current = image(entry['tag'])
                    assert current and current['platform'] == 'linux/arm64' and current['user'] == '65534:65534'
                    assert current['layers'][:-1] == entry['parent']['layers'] and not current['volumes']
                    return current

                assert image(entry['base']) == entry['parent'] and image(entry['tag']) is None
                built = await run(role, 'build', ['build', '--pull=false', '--network=none', '--platform=linux/arm64',
                    '--builder=default', '--provenance=false', '--sbom=false', '--file', entry['dockerfile'],
                    '--tag', entry['tag'], str(CONTEXT)], 150, verify_build)
                result['images'][role] = built
                name = 'aeep-react-sol-client-' + role

                def verify_catalogue(raw):
                    facts = raw.output
                    assert facts['catalogue_complete'] and facts['network_denied'] and not facts['account_read']
                    assert facts['model_turns'] == 0 and '0.159.1' in facts['protocol_version']
                    return facts

                assert helper['absent'](name)
                result['catalogues'][role] = await run(role, 'catalogue', ['run', '--rm', '--pull=never', '--network=none',
                    '--read-only', '--user', '65534:65534', '--cap-drop=ALL', '--security-opt=no-new-privileges',
                    '--memory=768m', '--memory-swap=768m', '--cpus=2', '--pids-limit=128', '--log-driver=none',
                    '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=64m', '--workdir', '/tmp',
                    '--name', name, '--label', 'aeep.sol-client=' + GRANT, '--entrypoint', 'python3', built['id'],
                    '-I', '-B', '-c', (HERE / 'sol-client-catalogue.py').read_text()], 50, verify_catalogue, name=name)
            result['passed'] = all(value['medium_supported'] for value in result['catalogues'].values())
        except Exception as error:
            result['error_type'] = type(error).__name__
        finally:
            ledger = repo.operation_ledger(GRANT)
            result['accounting_settled'] = all(row.elapsed_seconds is not None for row in ledger.operations)
            result['operations'] = len(ledger.operations)
            save(HERE / 'sol-client-worker-ledger.json', ledger.model_dump(mode='json'))
            save(HERE / 'sol-client-worker-result.json', result)
    print(json.dumps(result))
    return result['passed'] and result['accounting_settled']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument('--freeze', action='store_true')
    flags.add_argument('--execute-approved')
    options = parser.parse_args()
    if options.freeze:
        freeze()
    else:
        raise SystemExit(not asyncio.run(execute(options.execute_approved)))
