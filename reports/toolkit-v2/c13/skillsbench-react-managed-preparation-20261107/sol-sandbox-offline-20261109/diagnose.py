"""Diagnose the refreshed managed default without a proxy, auth volume or model."""

import argparse
import asyncio
import hashlib
import json
import re
import secrets
import shutil
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from aeep.assessment.containment import container_name
from aeep.assessment.models import AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_app_server import CodexAppServerAdapter, CodexRequestError
from aeep.hosts.codex_inspection import COMMAND, policy_observations
from aeep.hosts.workers import ManagedWorkerBinding
from aeep.models import ExecutionReceipt, ExecutorSpec, ResourceVector, StrictModel, utc_now
from aeep.store import ReceiptStore

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
LIVE = HERE.parent / 'sol-01591-live-20261109'
REVIEW = HERE / 'operation-review.json'
BLOCKER = LIVE / 'sol-managed-sandbox-blocker.json'
GRANT = 'skillsbench-react-sol-offline-sandbox-20261109'
CANARY = 'print("aeep-offline-sandbox-control")'
ERROR_MARKERS = {
    'bubblewrap': r'\bbwrap\b|\bbubblewrap\b',
    'namespace': r'\bnamespace',
    'operation_not_permitted': r'operation not permitted|\bEPERM\b',
    'permission_denied': r'permission denied|\bEACCES\b',
    'missing_program_or_path': r'not found|no such file',
    'no_writable_root': r'no writable|read-only file system',
    'managed_requirements': r'managed requirements|permission profile',
    'python_traceback': r'Traceback \(most recent call last\)',
}
EXPECTED_POLICY = {
    'config/read': {'config/default_permissions': 'aeep', 'config/approval_policy': 'never'},
    'configRequirements/read': {'requirements/allowedPermissionProfiles': {'aeep': True},
                                'requirements/allowedApprovalPolicies': ['never']},
}
RESERVED_SECONDS = 100


class DiagnosticScope(StrictModel):
    review_sha256: str


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def offline_inputs():
    live = read(LIVE / 'operation-review.json')
    blocker = read(BLOCKER)
    assert blocker['review_sha256'] == sha(LIVE / 'operation-review.json')
    assert blocker['workers']['control']['failed_stage'] == 'sandbox_command'
    pair = Path(live['cases'][0]['pair'])
    assert sha(pair) == live['pins'][str(pair)]
    control = read(pair)['control']
    original = ManagedWorkerBinding.model_validate(control['config']['managed_worker'])
    assert original.image == live['worker_image_ids']['control']
    assert original.digest() == blocker['workers']['control']['worker_digest']
    assert original.model_proxy_url and original.credential_volume and original.seccomp_profile
    assert original.permissions_profile == 'aeep'
    config = control['config']
    assert config['argv'] == [original.binary, 'app-server'] and not config['environment_allowlist']
    worker = ManagedWorkerBinding.model_validate(original.model_dump() | {
        'credential_volume': None, 'network_id': None, 'model_proxy_url': None,
    })
    config['managed_worker'] = worker.model_dump(mode='json')
    endpoint = urlsplit(original.model_proxy_url)
    command = COMMAND.replace('PROXY_HOST', repr(endpoint.hostname)).replace('PROXY_PORT', repr(endpoint.port))
    return live, pair, ExecutorSpec.model_validate(control), worker, command


def docker(worker, *args):
    return subprocess.run([worker.runtime, '--host', f'unix://{worker.socket}', *args],
                          env={}, cwd=ROOT, text=True, capture_output=True, timeout=8, check=True).stdout.strip()


def preflight(review=None):
    live, pair, spec, worker, command = offline_inputs()
    assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
    assert verification_source_digest(ROOT) == live['source_sha256']
    image = docker(worker, 'image', 'inspect', '--format',
                   '{{.Id}} {{.Os}}/{{.Architecture}} {{.Config.User}} {{json (index .Config "Volumes")}}', worker.image)
    assert image == f'{worker.image} linux/arm64 65534:65534 null'
    if review:
        assert utc_now() < datetime.fromisoformat(review['expires_at'])
        assert all(sha(path) == digest for path, digest in review['pins'].items())
        assert worker.digest() == review['worker_digest'] and content_digest(spec) == review['executor_digest']
        assert review['programs_sha256'] == [content_digest(x) for x in ({'program': CANARY}, {'program': command})]
    return live, pair, spec, worker, command


def markers(stderr):
    if not isinstance(stderr, str):
        return []
    return sorted(name for name, pattern in ERROR_MARKERS.items()
                  if re.search(pattern, stderr[:4096], re.IGNORECASE))


def bounded_reply(reply, *, canary):
    code = reply.get('exitCode')
    result = {'exit_code': code if type(code) is int and -255 <= code <= 255 else None,
              'stderr_categories': markers(reply.get('stderr')), 'observation': None}
    out = reply.get('stdout')
    if code != 0 or not isinstance(out, str) or len(out.encode()) > 4096:
        return result
    if canary:
        result['observation'] = {'canary_matched': out.strip() == 'aeep-offline-sandbox-control'}
        return result
    try:
        observation = json.loads(out)
    except ValueError:
        return result
    if (isinstance(observation, dict) and set(observation) == {'workspace_write', 'configuration_write', 'proxy', 'direct'}
            and type(observation['workspace_write']) is bool
            and observation['configuration_write'] in ('permitted', 'denied', 'read_only', 'absent', 'unavailable')
            and all(observation[k] in ('permitted', 'denied', 'unreachable') for k in ('proxy', 'direct'))):
        result['observation'] = observation
    return result


def freeze():
    live, pair, spec, worker, command = preflight()
    assert markers('bwrap: Creating new namespace failed: Operation not permitted\nsensitive text') == [
        'bubblewrap', 'namespace', 'operation_not_permitted']
    assert bounded_reply({'exitCode': 1, 'stderr': 'unknown sensitive text', 'stdout': 'unknown sensitive text'},
                         canary=False) == {'exit_code': 1, 'stderr_categories': [], 'observation': None}
    healthy = {'workspace_write': True, 'configuration_write': 'denied', 'proxy': 'unreachable', 'direct': 'denied'}
    assert bounded_reply({'exitCode': 0, 'stdout': json.dumps(healthy)}, canary=False)['observation'] == healthy
    assert bounded_reply({'exitCode': 0, 'stdout': json.dumps(healthy | {'secret': 'example'})},
                         canary=False)['observation'] is None
    assert bounded_reply({'exitCode': 0, 'stdout': 'aeep-offline-sandbox-control\n'},
                         canary=True)['observation'] == {'canary_matched': True}
    adapter = CodexAppServerAdapter.from_executor(spec, principal_salt=secrets.token_bytes(32))
    try:
        argv = adapter.transport.argv
        assert argv[argv.index('--network') + 1] == 'none' and '--mount' not in argv
        assert any(arg.startswith('/worker/auth:rw,') for arg in argv)
        assert any(arg.startswith('seccomp=') for arg in argv)
        assert not any('PROXY=' in arg for arg in argv)
        assert argv[-1] == 'app-server' and not adapter.transport.running
    finally:
        if adapter._worker_security:
            adapter._worker_security.cleanup()
    scope_fixture(spec)
    pins = [Path(__file__).resolve(), LIVE / 'operation-review.json', BLOCKER, pair, Path(worker.runtime).resolve()]
    save(REVIEW, {
        'purpose': 'Observe why the unchanged Codex sandbox command stopped on the refreshed React control image.',
        'parent_review_sha256': sha(LIVE / 'operation-review.json'), 'source_sha256': live['source_sha256'],
        'pins': {str(path): sha(path) for path in pins}, 'image': worker.image,
        'worker_digest': worker.digest(), 'executor_digest': content_digest(spec),
        'programs_sha256': [content_digest({'program': program}) for program in (CANARY, command)],
        'maximum_new_operations': 1, 'maximum_reserved_seconds': RESERVED_SECONDS, 'maximum_sandbox_commands': 2,
        'network': 'none', 'credential_volume': False, 'account_methods': False, 'proxy_start': False,
        'models': 0, 'cash_usd': '0', 'downloads': False, 'image_changes': False,
        'cleanup': 'Only the new owned diagnostic container, if still present and verified.',
        'policy_overrides': False, 'automatic_retries': False, 'comparisons': 'PAUSED',
        'synthetic_preflight_passed': True,
        'expires_at': (utc_now() + timedelta(hours=18)).isoformat(),
    })
    print(sha(REVIEW))


async def observe(transport, command, result):
    await transport.start()
    result['protocol'] = transport.protocol_version
    for method, expected in EXPECTED_POLICY.items():
        params = {'includeLayers': False, 'cwd': '/workspace'} if method == 'config/read' else {}
        try:
            reply = await transport.request(method, params, timeout=8)
            result[method] = policy_observations(reply, expected)
        except CodexRequestError:
            result[method] = {'available': False}
    for label, program in (('canary', CANARY), ('original_probe', command)):
        try:
            reply = await transport.request('command/exec', {
                'command': ['python3', '-c', program], 'cwd': '/workspace',
                'timeoutMs': 10000, 'outputBytesCap': 4096,
            }, timeout=15)
            result[label] = bounded_reply(reply, canary=label == 'canary')
        except CodexRequestError as error:
            payload = error.error if isinstance(error.error, dict) else {}
            code = payload.get('code')
            result[label] = {'rpc_error_code': code if type(code) is int and -40000 <= code <= -32000 else None,
                             'rpc_error_categories': markers(payload.get('message'))}


def inspect_container(worker, name):
    listing = docker(worker, 'container', 'ls', '--all', '--no-trunc', '--filter', f'name=^/{name}$',
                     '--format', '{{.ID}} {{.Names}}')
    if not listing:
        return None
    container_id, actual_name = listing.split(' ')
    assert actual_name == name and re.fullmatch('[a-f0-9]{64}', container_id)
    return container_id


def scoped_request(value, expiry):
    ref = content_digest(value)
    limits = AssessmentLimits(max_operations=1, max_model_turns=0, max_elapsed_seconds=RESERVED_SECONDS)
    grant = AssessmentAuthorization(authorization_id=GRANT, subject_digests=[ref], recipe_digests=[ref],
        environment_digests=[ref], limits=limits, allowed_destinations=['local'], remote_disclosure=False, expires_at=expiry)
    request = RecipeMaterializationRequest(plan_id=GRANT, subject_digest=ref, recipe_digest=ref,
        environment_digest=ref, mapping_digest=ref, authorization_id=GRANT, definition_digests=[ref], seed=0)
    return ref, limits, grant, request


def reserve(store, value, expiry):
    ref, limits, grant, request = scoped_request(value, expiry)
    repo = AssessmentRepository(store)
    assert repo.put('toolkit_react_sol_offline_sandbox_scope', ref, value) == ref
    repo.approve_bundle(grant, {ref: value.model_dump(mode='json')})
    repo.reserve(request, GRANT, limits, stage='worker_sandbox_diagnostic')
    repo.authorize(request)
    return repo


def record(store, repo, spec, result, started, elapsed):
    receipt = ExecutionReceipt(decision_id=GRANT, action_id=GRANT, capability=spec.capability,
        executor_id=spec.id, executor_kind=spec.kind, status='success' if result['passed'] else 'failed',
        started_at=started, ended_at=utc_now(), estimated=spec.estimate,
        actual_resources=ResourceVector(latency_ms=elapsed * 1000), execution_success=result['passed'],
        error_type=result['error_type'], metadata={'review_sha256': result['review_sha256'], 'observation': result,
                                                  'observed_resource_dimensions': ['latency_ms']})
    store.save_receipt(receipt)
    repo.finish_operation(GRANT, elapsed_seconds=elapsed, resources=receipt.actual_resources)
    return receipt


def scope_fixture(spec):
    with ReceiptStore(':memory:') as store:
        repo = reserve(store, DiagnosticScope(review_sha256='fixture'), utc_now() + timedelta(seconds=30))
        receipt = record(store, repo, spec, {'passed': False, 'error_type': 'synthetic', 'review_sha256': 'fixture'},
                         utc_now(), .01)
        assert receipt.execution_success is False


async def execute(identity):
    review = read(REVIEW)
    assert sha(REVIEW) == identity and read(HERE / 'approval.json') == {'approved': True, 'review_sha256': identity}
    assert not (HERE / 'started.json').exists()
    _, _, spec, worker, command = preflight(review)
    expiry = datetime.fromisoformat(review['expires_at'])
    ledger = HERE.parents[4] / '.aeep' / HERE.parent.name / 'sol-sandbox-offline-20261109.sqlite3'
    assert not ledger.exists()
    adapter = CodexAppServerAdapter.from_executor(spec, principal_salt=secrets.token_bytes(32))
    name = container_name(adapter._worker_process_id)
    result = {'review_sha256': identity, 'container_name': name, 'models': 0, 'passed': False, 'cleanup_confirmed': False}
    try:
        assert inspect_container(worker, name) is None
        save(HERE / 'started.json', result)
        with ReceiptStore(str(ledger)) as store:
            repo = reserve(store, DiagnosticScope(review_sha256=identity), expiry)
            started, clock = utc_now(), time.monotonic()
            failure = None
            try:
                async with asyncio.timeout(55):
                    await observe(adapter.transport, command, result)
            except Exception as error:
                failure = type(error).__name__
            finally:
                try:
                    await asyncio.wait_for(adapter.transport.close(), timeout=5)
                    container_id = inspect_container(worker, name)
                    if container_id is not None:
                        actual = docker(worker, 'container', 'inspect', '--format', '{{.Image}} {{.Name}}', container_id)
                        assert actual == f'{worker.image} /{name}'
                        assert docker(worker, 'container', 'rm', '--force', container_id) == container_id
                    result['cleanup_confirmed'] = inspect_container(worker, name) is None
                except Exception as error:
                    failure = 'cleanup_' + type(error).__name__
                elapsed = time.monotonic() - clock
                result.update(passed=failure is None and result['cleanup_confirmed'], error_type=failure,
                              elapsed_seconds=elapsed, purpose='diagnostic only; no worker qualification')
                receipt = record(store, repo, spec, result, started, elapsed)
                save(HERE / 'receipt.json', receipt.model_dump(mode='json'))
                save(HERE / 'result.json', result | {'accounting_settled': True})
    finally:
        if adapter._worker_security:
            adapter._worker_security.cleanup()
    return result['passed']


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
        preflight(read(REVIEW))
        print(json.dumps({'review_sha256': sha(REVIEW), 'preflight_passed': True, 'executed': False}))
    else:
        raise SystemExit(not asyncio.run(execute(args.execute_approved)))
