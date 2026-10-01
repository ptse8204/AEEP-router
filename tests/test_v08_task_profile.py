from __future__ import annotations

import asyncio
import hashlib
import json
import os
import runpy
import subprocess
import sys
import tempfile
import tomllib
from datetime import timedelta
from pathlib import Path

import pytest
from jsonschema import validate
from typer.testing import CliRunner

from aeep.assessment.models import content_digest
from aeep.assessment.onboarding import reference_spec
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.tools import declarations
from aeep.assessment.workbook import workbook_recipe
from aeep.assessment.workbook_native import implementation_digest
from aeep.attempts import ExecutionAttempt, ExecutionAttemptState
from aeep.cli import app
from aeep.economic.prepared import executor_fingerprint
from aeep.errors import ConfigurationError
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.hosts.codex_sandbox import NativeSandboxConfig, native_backend_digest
from aeep.mcp.server import AEEPToolService, MCPProtocolApp
from aeep.models import (
    ActionConstraints,
    ActionRequest,
    ExecutionStatus,
    ExecutorKind,
    Manifest,
    PolicyConfig,
    SideEffect,
    TaskScope,
    ValidationKind,
    ValidationSpec,
    utc_now,
)
from aeep.router import Router
from aeep.store import ReceiptStore

pytestmark = pytest.mark.assessment_lifecycle


def test_task_cli_definition_review_pause_export_and_text_fallback(tmp_path):
    runner = CliRunner()
    root = tmp_path.resolve()
    spec = reference_spec('csv')
    manifest = root / 'aeep.json'
    manifest.write_text(Manifest(database=str(root / '.aeep' / 'state.db'), executors=[spec]).model_dump_json())
    scope = TaskScope(scope_id='cli-scope', project_root=str(root),
        executor_fingerprints={spec.id: executor_fingerprint(spec)}, max_attempts=2,
        max_attempt_seconds=10, expires_at=utc_now() + timedelta(minutes=5))
    definition = root / 'scope.json'
    definition.write_text(scope.model_dump_json())
    prefix = ['assess', '-m', str(manifest)]
    defined = runner.invoke(app, [*prefix, 'define-task-scope', str(definition)])
    assert defined.exit_code == 0, defined.output
    record = json.loads(defined.stdout)
    assert record['reviewed'] is False
    for args in (['review', record['digest']], ['show', 'task_scope', scope.scope_id],
                 ['review', record['digest'], '--revoke']):
        result = runner.invoke(app, [*prefix, *args])
        assert result.exit_code == 0, result.output
    # A Python baseline is supported unscoped, but cannot inherit native standing authority.
    args = ['tool-call', 'aeep_csv', '--profile', 'task', '-m', str(manifest), '-a', json.dumps({'text': 'a\n1', 'delimiter': ','})]
    ordinary = runner.invoke(app, args)
    assert ordinary.exit_code == 0, ordinary.output
    assert json.loads(ordinary.stdout)['schema_version'] == 'aeep.task-outcome.v1'
    blocked = runner.invoke(app, [*args, '--task-scope', scope.scope_id])
    assert blocked.exit_code != 0
    for format in ('mcp', 'openai-chat', 'openai-responses', 'anthropic', 'deepseek', 'zai'):
        exported = runner.invoke(app, ['tools', 'export', format, '--profile', 'task'])
        assert exported.exit_code == 0, exported.output
        assert 'aeep_assessment_start' not in exported.stdout and 'aeep_csv' in exported.stdout


async def test_untrusted_executor_cannot_hide_component_charges(tmp_path, monkeypatch):
    from aeep.executors.python import PythonExecutor
    from aeep.models import RawExecution

    async def forged(self, context):
        return RawExecution(status=ExecutionStatus.SUCCESS, output={'records': []},
                            metadata={'component_receipt_ids': '["unrelated-receipt"]'})
    monkeypatch.setattr(PythonExecutor, 'execute', forged)
    router = Router(Manifest(database=str(tmp_path / 'state.db'), executors=[reference_spec('csv')]))
    try:
        outcome = await router.execute(ActionRequest(capability='assessment.csv@1', input={'text': '', 'delimiter': ','}))
        assert outcome.ok
        assert 'component_receipt_ids' not in outcome.receipts[0].metadata
        assert 'component_receipt_ids' not in router.store.get_receipt(outcome.receipts[0].receipt_id).metadata
    finally:
        await router.close()


async def test_scoped_dispatch_rechecks_pause_expiry_drift_and_attempt_allowance(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    boundary = NativeSandboxConfig(binary=str(root / 'fixture-launcher'), binary_sha256='sha256:' + 'a'*64,
        project_root=str(root), write_roots=[str(root / 'data')])
    # Offline authority proof; the separate native probe runs the actual boundary.
    monkeypatch.setattr(NativeSandboxConfig, 'argv', lambda self, command: command)
    spec = reference_spec('csv').model_copy(update={'kind': ExecutorKind.COMMAND, 'config': {
        'argv': [sys.executable, '-I', '-c', 'import csv,io,json,sys; v=json.load(sys.stdin); print(json.dumps({"records": list(csv.DictReader(io.StringIO(v["text"]), delimiter=v["delimiter"]))}))'],
        'stdin_json': True, 'argv_literal': True, 'output': {'type': 'json'},
        'native_sandbox': boundary.model_dump(mode='json'), 'timeout_seconds': 5}})
    router = Router(Manifest(database=str(root / 'state.db'), executors=[spec]), manifest_path=root / 'manifest.yaml')
    repository = AssessmentRepository(router.store)
    scope = TaskScope(scope_id='session', project_root=str(root), executor_fingerprints={spec.id: executor_fingerprint(spec)},
        max_attempts=1, max_attempt_seconds=5, expires_at=utc_now() + timedelta(minutes=5))
    digest = repository.put('task_scope', scope.scope_id, scope)
    service = AEEPToolService(router, profile='task', task_scope=scope.scope_id)
    arguments = {'text': 'name\nAda\n', 'delimiter': ','}
    try:
        assert (await service.call('aeep_csv', arguments))['isError']
        repository.review(digest)
        successful = (await service.call('aeep_csv', arguments))['structuredContent']
        assert successful['ok'] and successful['output']['records'] == [{'name': 'Ada'}]
        assert successful['task_scope_digest'] == digest and successful['receipts'][0]['approval_id']
        repository.review(digest, revoke=True)
        assert (await service.call('aeep_csv', arguments))['isError']
        repository.review(digest)
        assert (await service.call('aeep_csv', arguments))['isError']  # No reset on resume.
        changed = spec.model_copy(deep=True)
        changed.config['native_sandbox']['write_roots'] = [str(root / 'different')]
        assert executor_fingerprint(changed) != executor_fingerprint(spec)
        with pytest.raises(Exception, match='exact reviewed scope'):
            router._require_task_scope(changed)
        with pytest.raises(ConfigurationError, match='task-only'):
            AEEPToolService(router, profile='legacy', task_scope=scope.scope_id)
    finally:
        await router.close()


@pytest.mark.parametrize('change,reason', [
    ({'expires_at': utc_now() - timedelta(seconds=1)}, 'expired'),
    ({'approval_ceiling': SideEffect.NONE}, 'permission'),
    ({'max_attempt_seconds': 1}, 'resource'),
])
async def test_task_scope_limits_cannot_be_raised_by_operator_service_ceiling(tmp_path, monkeypatch, change, reason):
    root = tmp_path.resolve()
    monkeypatch.setattr(NativeSandboxConfig, 'argv', lambda self, command: command)
    config = NativeSandboxConfig(binary=str(root / 'fixture'), binary_sha256='sha256:' + 'a'*64, project_root=str(root))
    spec = reference_spec('csv').model_copy(update={'kind': ExecutorKind.COMMAND,
        'config': {'native_sandbox': config.model_dump(mode='json'), 'timeout_seconds': 5}})
    router = Router(Manifest(database=str(root / 'state.db'), executors=[spec]), manifest_path=root / 'manifest.yaml')
    scope = TaskScope.model_validate(dict(scope_id='limited', project_root=str(root), executor_fingerprints={spec.id: executor_fingerprint(spec)},
        max_attempts=2, max_attempt_seconds=10, expires_at=utc_now() + timedelta(minutes=2)) | change)
    repository = AssessmentRepository(router.store)
    digest = repository.put('task_scope', scope.scope_id, scope)
    repository.review(digest)
    router.bind_task_scope(scope.scope_id)
    try:
        with pytest.raises(Exception, match=reason):
            router._require_task_scope(spec)
    finally:
        await router.close()


async def test_task_profile_returns_receipt_evidence_and_cannot_start_assessment(tmp_path):
    router = Router(Manifest(database=str(tmp_path / 'state.db'), executors=[reference_spec('csv')]))
    service = AEEPToolService(router, profile='task')
    try:
        assert all(not item['name'].startswith('aeep_assessment_') for item in service.list_tools())
        result = await service.call('aeep_csv', {'text': 'a,b\n1,2\n', 'delimiter': ','})
        payload = result['structuredContent']
        assert payload['ok'] and payload['output'] == {'records': [{'a': '1', 'b': '2'}]}
        validate(payload, next(item for item in declarations(tasks_only=True) if item['name'] == 'aeep_csv')['outputSchema'])
        assert payload['schema_version'] == 'aeep.task-outcome.v1'
        assert payload['verification_limits'] and payload['changes_verified'] is None
        assert 'incomplete' in payload['summary']
        assert router.store.get_receipt(payload['receipts'][0]['receipt_id']) is not None
        assert (await service.call('aeep_assessment_start', {'plan_id': 'anything'}))['isError']
        assert (await service.call('aeep_csv', {'text': 'a\n1', 'delimiter': ',', 'approve': 'write'}))['isError']
        assert not service.assessment_workers
        legacy = await AEEPToolService(router, profile='assessment').call('aeep_csv', {'text': 'a\n1', 'delimiter': ','})
        assert legacy['structuredContent'] == {'records': [{'a': '1'}]}
        protocol = await MCPProtocolApp(service).handle({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}})
        assert protocol and 'aeep_route_action' not in protocol['result']['instructions']
    finally:
        await router.close()


@pytest.mark.parametrize('max_attempts', [1, 3])
def test_task_scope_attempt_limit_is_durable_atomic_and_pause_keeps_usage(tmp_path, max_attempts):
    store = ReceiptStore(tmp_path / 'state.db')
    other = ReceiptStore(tmp_path / 'state.db')
    repo = AssessmentRepository(store)
    scope = TaskScope(scope_id='bounded', project_root=str(tmp_path.resolve()),
        executor_fingerprints={'tool': 'sha256:' + 'a' * 64}, max_attempts=max_attempts,
        max_attempt_seconds=10, expires_at=utc_now() + timedelta(minutes=5))
    digest = repo.put('task_scope', scope.scope_id, scope)
    attempt = ExecutionAttempt(decision_id='d', action_digest='a' * 64, executor_id='tool',
        executor_fingerprint='sha256:' + 'a' * 64, side_effect=SideEffect.READ,
        idempotent=True, task_scope_digest=digest)
    try:
        with pytest.raises(ConfigurationError, match='paused'):
            store.create_execution_attempt(attempt)
        repo.review(digest)
        store.create_execution_attempt(attempt)
        assert other.create_execution_attempt(attempt).attempt_id == attempt.attempt_id
        with pytest.raises(ConfigurationError, match='allowance'):
            other.create_execution_attempt(attempt.model_copy(update={'attempt_id': 'second'}))
        repo.review(digest, revoke=True)
        repo.review(digest)
        with pytest.raises(ConfigurationError, match='allowance'):
            other.create_execution_attempt(attempt.model_copy(update={'attempt_id': 'third'}))
        with pytest.raises(ConfigurationError, match='authority'):
            other.create_execution_attempt(attempt.model_copy(update={'task_scope_digest': None}))
    finally:
        store.close()
        other.close()


def test_native_sandbox_pins_launcher_and_keeps_argv_and_config_local(tmp_path):
    binary = tmp_path / 'codex'
    binary.write_bytes(b'fixture')
    config = NativeSandboxConfig(binary=str(binary.resolve()),
        binary_sha256='sha256:' + hashlib.sha256(b'fixture').hexdigest(),
        project_root=str(tmp_path.resolve()), write_roots=[str(tmp_path.resolve() / 'data')])
    if sys.platform == 'darwin':
        argv = config.argv(['printf', '$(touch never)'])
        assert argv[-3:] == ['--', 'printf', '$(touch never)']
        assert '--include-managed-config' in argv
        binary.write_bytes(b'changed')
        with pytest.raises(ConfigurationError, match='changed'):
            config.argv([])
    with pytest.raises(ValueError, match='subdirectories'):
        NativeSandboxConfig.model_validate({**config.model_dump(), 'write_roots': [str(tmp_path.resolve())]})


def test_native_sandbox_unicode_paths_compile_as_toml(tmp_path):
    root = (tmp_path / 'project-😀').resolve()
    root.mkdir()
    config = NativeSandboxConfig(binary=str(root / 'codex'), binary_sha256='sha256:' + 'a' * 64,
        project_root=str(root), read_roots=[str(root / 'inputs-😀')])
    overrides = config.permission_overrides()
    parsed = tomllib.loads(overrides[-1])
    assert parsed['permissions']['aeep-native-task']['filesystem'][str(root / 'inputs-😀')] == 'read'


def test_native_sandbox_denies_implicit_temp_and_declared_subtrees(tmp_path):
    root = tmp_path.resolve()
    denied = root / 'private'
    config = NativeSandboxConfig(binary=str(root / 'codex'), binary_sha256='sha256:' + 'a' * 64,
        project_root=str(root), deny_roots=[str(denied)])
    filesystem = tomllib.loads(config.permission_overrides()[-1])['permissions']['aeep-native-task']['filesystem']
    for path in [denied, root / '.aeep', root / '.codex', Path.home() / '.codex',
                 Path('/tmp').resolve(), Path('/var/tmp').resolve()]:
        assert filesystem[str(path)] == 'deny'
        assert filesystem[str(path / '**')] == 'deny'
        assert filesystem[f'{path}{{,/**}}'] == 'deny'
    with pytest.raises(ConfigurationError, match='temporary'):
        config.model_copy(update={'project_root': str(Path('/tmp').resolve() / 'project')}).permission_overrides()
    with pytest.raises(ConfigurationError, match='temporary'):
        config.model_copy(update={'read_roots': [str(Path('/var/tmp').resolve() / 'input')]}).permission_overrides()
    with pytest.raises(ConfigurationError, match='glob'):
        config.model_copy(update={'deny_roots': [str(root / 'private[1]')]}).permission_overrides()
    with pytest.raises(ConfigurationError, match='glob'):
        config.model_copy(update={'read_roots': [str(root / 'input{old}')]}).permission_overrides()


def test_native_policy_change_invalidates_reviewed_route_and_receipt_identity(tmp_path, monkeypatch):
    import aeep.hosts.codex_sandbox as sandbox

    root = tmp_path.resolve()
    boundary = NativeSandboxConfig(binary=str(root / 'codex'), binary_sha256='sha256:' + 'a' * 64,
        project_root=str(root))
    spec = reference_spec('csv').model_copy(update={'kind': ExecutorKind.COMMAND,
        'config': {'argv': ['python3'], 'native_sandbox': boundary.model_dump(mode='json'),
                   'timeout_seconds': 5}})
    before = executor_fingerprint(spec)
    before_backend = native_backend_digest(boundary)
    router = Router(Manifest(database=str(root / 'state.db'), executors=[spec]), manifest_path=root / 'aeep.json')
    scope = TaskScope(scope_id='policy-pin', project_root=str(root),
        executor_fingerprints={spec.id: before}, max_attempts=1, max_attempt_seconds=5,
        expires_at=utc_now() + timedelta(minutes=5))
    repo = AssessmentRepository(router.store)
    repo.review(repo.put('task_scope', scope.scope_id, scope))
    try:
        router.bind_task_scope(scope.scope_id)
        router._require_task_scope(spec)
        monkeypatch.setattr(sandbox, 'native_policy_digest', lambda: 'changed-adapter-policy')
        assert executor_fingerprint(spec) != before
        assert native_backend_digest(boundary) != before_backend
        with pytest.raises(Exception, match='exact reviewed scope'):
            router._require_task_scope(spec)
    finally:
        asyncio.run(router.close())


def test_native_environment_requires_literal_reviewed_scratch(tmp_path):
    root = tmp_path.resolve()
    scratch = root / 'scratch'
    scratch.mkdir()
    config = NativeSandboxConfig(binary=str(root / 'codex'), binary_sha256='sha256:' + 'a' * 64,
        project_root=str(root), write_roots=[str(scratch)])
    assert config.validate_environment({'TMPDIR': str(scratch)}) == {'TMPDIR': str(scratch)}
    for value in ({'TMPDIR': '${ENV:SECRET}'}, {'TMPDIR': str(root / 'other')},
                  {'HOME': str(scratch)}, {'TMPDIR': str(root / 'missing')}):
        with pytest.raises(ConfigurationError):
            config.validate_environment(value)


async def test_native_dispatch_hashes_once_after_authority_check(tmp_path, monkeypatch):
    binary = tmp_path / 'codex'
    binary.write_bytes(b'fixture')
    config = NativeSandboxConfig(binary=str(binary.resolve()),
        binary_sha256='sha256:' + hashlib.sha256(b'fixture').hexdigest(), project_root=str(tmp_path.resolve()))
    spec = reference_spec('csv').model_copy(update={'kind': ExecutorKind.COMMAND, 'config': {
        'argv': [sys.executable, '-c', 'print(1)'], 'argv_literal': True,
        'native_sandbox': config.model_dump(mode='json'), 'timeout_seconds': 1}})
    scope = TaskScope(scope_id='pin', project_root=config.project_root,
        executor_fingerprints={spec.id: executor_fingerprint(spec)}, max_attempts=1,
        max_attempt_seconds=1, expires_at=utc_now() + timedelta(minutes=1))
    hashes = []
    original = hashlib.file_digest
    def counted(stream, algorithm):
        hashes.append(stream.name)
        return original(stream, algorithm)
    monkeypatch.setattr(hashlib, 'file_digest', counted)
    executor = CommandExecutor()
    for _ in range(4):
        executor.require_task_scope(scope, spec, [])
    assert hashes == []  # Offline eligibility never rereads the executable.
    monkeypatch.setattr('aeep.hosts.codex_sandbox.sys.platform', 'darwin')
    def revoke_binary():
        binary.write_bytes(b'changed')
    context = ExecutionContext(request=ActionRequest(capability=spec.capability), spec=spec,
        estimate=spec.estimate, attempt=1, invocation_check=revoke_binary)
    with pytest.raises(ConfigurationError, match='executable changed'):
        await executor.execute(context)
    assert hashes == [str(binary.resolve())]  # Full hash after the final authority check.


@pytest.mark.parametrize('failure', ['exit', 'timeout'])
async def test_scoped_partial_write_requires_recovery_after_restart(tmp_path, monkeypatch, failure):
    root = tmp_path.resolve()
    data = root / 'data'
    data.mkdir()
    effect = data / 'effect'
    monkeypatch.setattr(NativeSandboxConfig, 'argv', lambda self, command: command)
    boundary = NativeSandboxConfig(binary=str(root / 'fixture'), binary_sha256='sha256:' + 'a'*64,
        project_root=str(root), write_roots=[str(data)])
    program = ('import pathlib,sys,time; p=pathlib.Path(sys.argv[1]); '
               'p.write_text(p.read_text()+"effect\\n" if p.exists() else "effect\\n"); '
               + ('sys.exit(3)' if failure == 'exit' else 'time.sleep(10)'))
    spec = reference_spec('csv').model_copy(update={'kind': ExecutorKind.COMMAND,
        'side_effect': SideEffect.WRITE, 'idempotent': False, 'config': {
        'argv': [sys.executable, '-I', '-c', program, str(effect)], 'argv_literal': True,
        'native_sandbox': boundary.model_dump(mode='json'), 'timeout_seconds': 0.5}})
    manifest = Manifest(database=str(root / '.aeep' / 'state.db'), executors=[spec],
        policies={'write': PolicyConfig(name='write', constraints=ActionConstraints(max_side_effect=SideEffect.WRITE))})
    request = ActionRequest(capability=spec.capability, policy='write', input={'text': 'a\n1', 'delimiter': ','},
        constraints=ActionConstraints(max_side_effect=SideEffect.WRITE))
    router = Router(manifest, manifest_path=root / 'aeep.yaml')
    repo = AssessmentRepository(router.store)
    scope = TaskScope(scope_id='recovery', project_root=str(root),
        executor_fingerprints={spec.id: executor_fingerprint(spec)}, approval_ceiling=SideEffect.WRITE,
        max_attempts=3, max_attempt_seconds=1, expires_at=utc_now() + timedelta(minutes=5))
    digest = repo.put('task_scope', scope.scope_id, scope)
    repo.review(digest)
    router.bind_task_scope(scope.scope_id)
    try:
        outcome = await router.execute(request, approved_side_effect=SideEffect.WRITE)
        assert not outcome.ok and effect.read_text() == 'effect\n'
        attempt = router.store.execution_attempt_for_decision(outcome.decision.decision_id)
        assert attempt is not None and attempt.state is ExecutionAttemptState.INDETERMINATE
        payload = router.task_outcome(outcome, approved_side_effect=SideEffect.WRITE)
        assert payload.recovery_state == 'required' and 'Reconcile' in payload.summary
    finally:
        await router.close()
    restarted = Router(manifest, manifest_path=root / 'aeep.yaml')
    try:
        repo = AssessmentRepository(restarted.store)
        repo.review(digest, revoke=True)
        repo.review(digest)
        restarted.bind_task_scope(scope.scope_id)
        with pytest.raises(ConfigurationError, match='recovery'):
            await restarted.execute(request, approved_side_effect=SideEffect.WRITE)
        assert effect.read_text() == 'effect\n'  # Restart/pause/resume must not duplicate the write.
        assert restarted.store.get_receipt(outcome.receipts[0].receipt_id) is not None
        from aeep.tasks import TaskReconciliation, reconcile
        # Explicit operator inspection/reversal, never an automatic retry.
        effect.unlink()
        recovery = TaskReconciliation(attempt_id=attempt.attempt_id, attempt_version=attempt.version,
            scope_digest=digest, resolution='effects_reverted', evidence_digests=[digest])
        recovery_digest=repo.put('task_reconciliation',content_digest(recovery),recovery)
        with pytest.raises(ConfigurationError,match='review'):
            reconcile(restarted,recovery_digest)
        repo.review(recovery_digest)
        resolved=reconcile(restarted,recovery_digest)
        assert resolved['state']=='FAILED' and resolved['allowance_reset'] is False
        assert restarted.store.get_receipt(outcome.receipts[0].receipt_id) is not None
        with pytest.raises(ConfigurationError,match='exact unresolved'):
            reconcile(restarted,recovery_digest)
        retried = await restarted.execute(request, approved_side_effect=SideEffect.WRITE)
        assert not retried.ok and effect.read_text() == 'effect\n'
        next_attempt = restarted.store.execution_attempt_for_decision(retried.decision.decision_id)
        assert next_attempt is not None and next_attempt.attempt_id != attempt.attempt_id
        assert next_attempt.state is ExecutionAttemptState.INDETERMINATE
        assert restarted.store._connection.execute('SELECT COUNT(*) FROM execution_attempts').fetchone()[0] == 2
    finally:
        await restarted.close()


@pytest.mark.native_boundary
@pytest.mark.skipif(not os.getenv('AEEP_NATIVE_CODEX'), reason='explicit native launcher required')
def test_actual_native_allow_deny_and_network_boundary(tmp_path):
    root = tmp_path.resolve()
    data = root / 'data'
    data.mkdir()
    denied = root / 'private'
    denied.mkdir()
    (denied / 'canary').write_text('synthetic-canary')
    protected = root / '.aeep'
    protected.mkdir()
    (protected / 'canary').write_text('synthetic-control-canary')
    binary = Path(os.environ['AEEP_NATIVE_CODEX']).resolve()
    boundary = NativeSandboxConfig(binary=str(binary), binary_sha256='sha256:' + hashlib.sha256(binary.read_bytes()).hexdigest(),
        project_root=str(root), read_roots=[str(Path(sys.prefix).resolve())], write_roots=[str(data)], deny_roots=[str(denied)])
    program = '''import json, pathlib, socket, subprocess, sys
data, denied, temp_denied, temp_alias, var_temp_denied, protected = map(pathlib.Path, sys.argv[1:])
(data / 'allowed').write_text('ok')
result = {'allowed': (data / 'allowed').read_text() == 'ok'}
for name, operation in [('read_denied', lambda: (denied / 'canary').read_text()), ('write_denied', lambda: (denied / 'written').write_text('bad')),
                        ('read_temp_denied', lambda: (temp_denied / 'canary').read_text()),
                        ('write_temp_denied', lambda: (temp_denied / 'written').write_text('bad')),
                        ('read_temp_alias_denied', lambda: (temp_alias / 'canary').read_text()),
                        ('read_var_temp_denied', lambda: (var_temp_denied / 'canary').read_text()),
                        ('write_var_temp_denied', lambda: (var_temp_denied / 'written').write_text('bad')),
                        ('read_protected', lambda: (protected / 'canary').read_text()),
                        ('list_denied_root', lambda: list(denied.iterdir()))]:
    try: operation(); result[name] = False
    except PermissionError: result[name] = True
(data / 'rename-source').write_text('ok')
try: (data / 'rename-source').replace(temp_denied / 'renamed'); result['rename_temp_denied'] = False
except PermissionError: result['rename_temp_denied'] = True
try:
    s = socket.socket(); s.bind(('127.0.0.1', 0)); result['network_denied'] = False; s.close()
except PermissionError: result['network_denied'] = True
child = subprocess.run([sys.executable, '-I', '-c', 'import pathlib,sys; pathlib.Path(sys.argv[1]).read_text()', str(denied / 'canary')], capture_output=True)
result['child_denied'] = child.returncode != 0
child = subprocess.run([sys.executable, '-I', '-c', 'import pathlib,sys; pathlib.Path(sys.argv[1]).read_text()', str(temp_alias / 'canary')], capture_output=True)
result['child_temp_denied'] = child.returncode != 0
print(json.dumps(result))
'''
    with (tempfile.TemporaryDirectory(prefix='aeep-cross-root-', dir='/private/tmp') as temp_root,
          tempfile.TemporaryDirectory(prefix='aeep-var-cross-root-', dir='/private/var/tmp') as var_temp_root):
        temp_denied = Path(temp_root)
        (temp_denied / 'canary').write_text('synthetic-canary')
        var_temp_denied = Path(var_temp_root)
        (var_temp_denied / 'canary').write_text('synthetic-canary')
        temp_alias = Path('/tmp') / temp_denied.name
        spec = reference_spec('csv').model_copy(update={'kind': 'command', 'config': {
            'argv': [sys.executable, '-I', '-c', program, str(data), str(denied), str(temp_denied),
                     str(temp_alias), str(var_temp_denied), str(protected)], 'argv_literal': True,
            'native_sandbox': boundary.model_dump(mode='json'), 'output': {'type': 'json'}, 'timeout_seconds': 10}})
        raw = asyncio.run(CommandExecutor().execute(ExecutionContext(request=ActionRequest(capability=spec.capability), spec=spec, estimate=spec.estimate, attempt=1)))
        assert raw.status == ExecutionStatus.SUCCESS, (raw.error_message, raw.stderr)
        assert raw.output == {'allowed': True, 'read_denied': True, 'write_denied': True,
                              'read_temp_denied': True, 'write_temp_denied': True,
                              'read_temp_alias_denied': True, 'read_protected': True,
                              'read_var_temp_denied': True, 'write_var_temp_denied': True,
                              'list_denied_root': True, 'rename_temp_denied': True,
                              'network_denied': True, 'child_denied': True, 'child_temp_denied': True}
        assert raw.metadata['enforcement_backend_digest']


@pytest.mark.native_boundary
@pytest.mark.skipif(not (os.getenv('AEEP_NATIVE_CODEX') and os.getenv('AEEP_NATIVE_WORKBOOK_PYTHON')),
    reason='explicit native launcher and existing workbook Python required')
def test_native_workbook_scoped_journey_with_independent_preservation_checks(tmp_path):
    """Two predeclared synthetic tasks; this is not a live model experiment."""
    root = tmp_path.resolve()
    scratch = root / 'scratch'
    scratch.mkdir()
    assets = Path(__file__).resolve().parents[1] / 'integrations' / 'assessment-runtime'
    recipe = workbook_recipe()
    workbook_python = Path(os.environ['AEEP_NATIVE_WORKBOOK_PYTHON']).resolve()
    prefix = subprocess.run([str(workbook_python), '-I', '-c', 'import sys; print(sys.prefix)'],
        capture_output=True, text=True, check=True, timeout=5).stdout.strip()
    generated = subprocess.run([str(workbook_python), '-I', str(assets / 'workbook_program.py'), 'generate'],
        input=json.dumps({'seed': 29, 'stages': [{'split': 'demo', 'count': 11}]}),
        text=True, capture_output=True, check=True, timeout=10)
    # Fixed before dispatch: literal small task and 12-row generated task with preserved Notes.
    small = json.loads((assets / 'workbook-grader-fixtures.json').read_text())[0]
    larger = json.loads(generated.stdout)['cases'][10]
    cases = [(small['input'], small['expected']), (larger['input'], larger['output'])]
    grader = runpy.run_path(str(assets / 'workbook_grader.py'))['grade']
    binary = Path(os.environ['AEEP_NATIVE_CODEX']).resolve()
    boundary = NativeSandboxConfig(binary=str(binary), binary_sha256='sha256:' + hashlib.sha256(binary.read_bytes()).hexdigest(),
        project_root=str(root), read_roots=[str(Path(prefix).resolve())], write_roots=[str(scratch)])
    source = (assets / 'workbook_program.py').read_text()
    fault = json.loads((assets / 'workbook-faults.json').read_text())['stale_value']
    fault_input = dict(small['input'], row_bound=small['input']['row_bound'] + 1)
    program = ("import json,sys; ns={'__name__':'reference'}; exec(" + repr(source) +
        ", ns); inp=json.load(sys.stdin); print(json.dumps(" + repr(fault) +
        " if inp['row_bound']==" + str(fault_input['row_bound']) + " else ns['reference'](inp)))")
    assert recipe.extension
    spec = recipe.extension.reference.model_copy(deep=True)
    spec.id = 'native.workbook.reference'
    spec.input_schema, spec.output_schema = recipe.input_schema, recipe.output_schema
    spec.config = {**spec.config, 'argv': [str(workbook_python), '-I', '-c', program],
                   'native_sandbox': boundary.model_dump(mode='json'), 'env': {'TMPDIR': str(scratch)},
                   'max_output_bytes': 200000}
    spec.validators = [ValidationSpec(kind=ValidationKind.CALLBACK,
        config={'name': 'aeep.workbook.native.v1', 'implementation_digest': implementation_digest()})]

    async def journey():
        manifest_path = root / 'aeep.json'
        manifest_path.write_text(Manifest(database=str(root / '.aeep' / 'state.db'),
            executors=[spec]).model_dump_json())
        router = Router.from_manifest(manifest_path)
        repo = AssessmentRepository(router.store)
        repo.review(repo.put('recipe', recipe.recipe_id, recipe))
        scope = TaskScope(scope_id='workbook-demo', project_root=str(root),
            executor_fingerprints={spec.id: executor_fingerprint(spec)}, approval_ceiling=SideEffect.READ,
            max_attempts=3, max_attempt_seconds=30, expires_at=utc_now() + timedelta(minutes=5))
        digest = repo.put('task_scope', scope.scope_id, scope)
        repo.review(digest)
        from aeep.tasks import activate, change_state, inspect
        activation = activate(router, scope.scope_id)
        service = AEEPToolService(router, profile='task', task_activation=activation.activation_id)
        name = 'aeep_recipe_' + hashlib.sha256(recipe.capability.encode()).hexdigest()[:12]
        from aeep.mcp.client import MCPStdioClient
        client = MCPStdioClient(command=os.sys.executable,
            args=['-I', '-m', 'aeep', 'serve', '--transport', 'stdio', '--profile', 'task',
                  '--task-activation', activation.activation_id, '-m', str(manifest_path)])
        try:
            for index, (value, truth) in enumerate(cases):
                called = await service.call(name, value) if index == 0 else (await client.call_tool(name, value)).result
                result = called['structuredContent']
                assert result['ok'], result
                assert grader({'input': value, 'output': result['output'], 'expected': truth})
                assert 'retained rows, formulas, totals, and Notes values' in result['summary']
                assert result['receipts'][0]['enforcement_backend_digest']
                assert result['receipts'][0]['task_valid'] is True
                assert any(check['kind'] == 'callback' and check['valid'] is True
                           and check['trust'] == 'verified' for check in result['receipts'][0]['checks'])
                assert result['receipts'][0]['approval_id'] and result['recovery_state'] == 'none'
                assert result['task_activation_digest'] == content_digest(activation)
                assert result['changes_verified'] is None  # No claim of general OOXML preservation.
            response = await client.call_tool(name, fault_input)
            rejected = response.result['structuredContent']
            assert rejected['ok'] is False and rejected['receipts'][0]['task_valid'] is False
            change_state(router, activation.activation_id, 'pause')
            assert (await service.call(name, cases[0][0]))['isError']
            change_state(router, activation.activation_id, 'resume')
            repo.review(digest, revoke=True)
            assert (await service.call(name, cases[0][0]))['isError']
            repo.review(digest)
            assert (await service.call(name, cases[0][0]))['isError']  # Three attempts remain consumed.
            assert inspect(router, activation.activation_id)['attempts_used'] == 3
            change_state(router, activation.activation_id, 'uninstall')
            assert inspect(router, activation.activation_id)['overlay'] == 'absent'
        finally:
            await client.close()
            await router.close()
    asyncio.run(journey())
