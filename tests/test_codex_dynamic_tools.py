from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from aeep.errors import ConfigurationError, InputValidationError
from aeep.hosts.codex_app_server import AppServerOptions, CodexAppServerTransport
from aeep.hosts.codex_dynamic_tools import CodexDynamicTools, DynamicToolSession
from aeep.models import ManagedHostExecutorConfig, ManagedHostInvocation, SideEffect

TOOL = {'name': 'fixed', 'description': 'Fixed synthetic value operation.',
        'inputSchema': {'type': 'object', 'properties': {'value': {'type': 'integer'}},
                        'required': ['value'], 'additionalProperties': False},
        'outputSchema': {'type': 'object', 'properties': {'value': {'type': 'integer'}},
                         'required': ['value'], 'additionalProperties': False}}


def binding(handler=None, *, ceiling='read', timeout=1, max_calls=1):
    calls = []
    async def call(name, arguments):
        calls.append((name, arguments))
        return {'isError': False, 'structuredContent': arguments}
    holder = {}
    value = CodexDynamicTools(namespace='task', tools=[TOOL], identity={
        'worker_digest': 'a' * 64, 'native_backend_digest': 'b' * 64,
        'implementation_digest': 'c' * 64, 'approval_ceiling': ceiling},
        max_calls=max_calls, timeout_seconds=timeout, call=handler or call,
        check=lambda: holder['value'].digest)
    holder['value'] = value
    return value, calls


def session(value, *, ceiling=SideEffect.READ):
    return DynamicToolSession(value, worker_digest='a' * 64, expected_digest=value.digest,
        approved_side_effect=ceiling, max_bytes=4096,
        deadline=asyncio.get_running_loop().time() + 2)


def params(**changes):
    return {'threadId': 'thread', 'turnId': 'turn', 'callId': 'call',
            'namespace': 'task', 'tool': 'fixed', 'arguments': {'value': 1}, **changes}


@pytest.mark.asyncio
async def test_turn_response_race_waits_for_exact_identity_then_dispatches_once():
    value, calls = binding()
    active = session(value)
    active.bind_thread('thread')
    task = asyncio.create_task(active.call(params()))
    await asyncio.sleep(0)
    assert not calls
    active.bind_turn('turn')
    assert (await task)['success'] is True
    assert calls == [('fixed', {'value': 1})]
    with pytest.raises(ConfigurationError):
        await active.call(params())


@pytest.mark.asyncio
@pytest.mark.parametrize('changes', [
    {'threadId': 'other'}, {'turnId': 'other'}, {'namespace': 'other'},
    {'tool': 'approval'}, {'arguments': {'value': 1, 'approval_ceiling': 'write'}},
    {'callId': True}, {'unreviewed': True}, {'arguments': []},
])
async def test_invalid_identity_schema_or_authority_never_dispatches(changes):
    value, calls = binding()
    active = session(value)
    active.bind_thread('thread')
    active.bind_turn('turn')
    with pytest.raises((ConfigurationError, InputValidationError)):
        await active.call(params(**changes))
    assert calls == []


@pytest.mark.asyncio
async def test_outer_read_cannot_launder_write_and_mutation_rejects():
    value, _ = binding(ceiling='write')
    with pytest.raises(ConfigurationError, match='outer approval'):
        session(value)
    value, _ = binding()
    value.identity['native_backend_digest'] = 'd' * 64
    with pytest.raises(ConfigurationError, match='binding differs'):
        session(value)


@pytest.mark.parametrize('timeout', [float('nan'), float('inf'), True, 0])
def test_limits_are_finite_and_schema_valid_before_declaration(timeout):
    with pytest.raises(ConfigurationError):
        binding(timeout=timeout)


@pytest.mark.asyncio
async def test_post_effect_output_failure_keeps_effect_and_cannot_retry():
    effects = []
    async def call(name, args):
        effects.append('durable receipt remains owned by task service')
        return {'isError': False, 'structuredContent': {'value': 'wrong'}}
    value, _ = binding(call)
    active = session(value)
    active.bind_thread('thread')
    active.bind_turn('turn')
    with pytest.raises(InputValidationError):
        await active.call(params())
    assert effects and not active.tools_succeeded
    with pytest.raises(ConfigurationError):
        await active.call(params(callId='second'))


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['success', 'eof', 'early-terminal'])
async def test_protocol_reader_keeps_running_and_owned_callback_cancels(mode):
    entered, cancelled, terminal = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async def call(name, arguments):
        entered.set()
        if mode != 'success':
            try:
                await transport.request('fixture/entered', {})
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        return {'isError': False, 'structuredContent': arguments}
    value, _ = binding(call)
    active = session(value)
    fixture = Path(__file__).parent / 'fixtures/fake_codex_dynamic_tools.py'
    transport = CodexAppServerTransport((sys.executable, '-u', str(fixture), mode),
        request_timeout=1, options=AppServerOptions(experimental_api=True))
    transport.dynamic_tool_handler = active.call
    transport.subscribe(lambda method, data: terminal.set() if method in {'turn/completed', 'callback/replied'} else None)
    try:
        thread = await transport.request('thread/start', {'dynamicTools': value.declarations()})
        active.bind_thread(thread['thread']['id'])
        turn = await transport.request('turn/start', {'threadId': 'thread'})
        active.bind_turn(turn['turn']['id'])
        if mode == 'eof':
            await asyncio.wait_for(transport._failure_event.wait(), 1)
        else:
            await asyncio.wait_for(terminal.wait(), 1)
        if mode == 'success':
            assert active.tools_succeeded == {'fixed'}
        else:
            active.close()
            await transport.cancel_dynamic_tools()
            assert not active.tools_succeeded
    finally:
        await transport.close()
    assert not transport._dynamic_tasks
    assert entered.is_set()
    if mode != 'success':
        assert cancelled.is_set()


def test_optional_binding_changes_process_identity_without_changing_legacy_dump():
    base = ManagedHostExecutorConfig(adapter_id='codex-app-server', argv=(sys.executable,),
                                    instructions='fixed', invocation=ManagedHostInvocation())
    assert 'dynamic_tools_digest' not in base.invocation.model_dump()
    old = base.process_binding()
    scoped = base.model_copy(update={'invocation': ManagedHostInvocation(dynamic_tools_digest='a' * 64)})
    assert scoped.process_binding() != old
    with pytest.raises(ValueError):
        ManagedHostInvocation(mode='dynamic_tool', server='task', tool='fixed', tool_sha256='a' * 64)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['success', 'eof', 'early-terminal'])
async def test_adapter_requires_completed_callback_and_cancels_partial_effects(monkeypatch, mode):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from aeep.hosts.base import HostModel, HostProbe, HostProbeStatus, ManagedHostExecutionContext
    from aeep.hosts.codex_app_server import CodexAppServerAdapter
    from aeep.models import ActionRequest, ExecutionStatus
    effects, cancelled = [], []
    async def call(name, args):
        effects.append('task service owns durable receipt/recovery')
        if mode != 'success':
            try:
                await host.transport.request('fixture/entered', {})
                await asyncio.Event().wait()
            finally:
                cancelled.append(True)
        return {'isError': False, 'structuredContent': args}
    value, _ = binding(call)
    fixture = Path(__file__).parent / 'fixtures/fake_codex_dynamic_tools.py'
    argv = (sys.executable, '-u', str(fixture), mode)
    invocation = ManagedHostInvocation(mode='dynamic_tool', server='task', tool='fixed',
        tool_sha256=value.inventory()['dynamic:task:fixed'], dynamic_tools_digest=value.digest,
        exposure='required')
    config = ManagedHostExecutorConfig(adapter_id='codex-app-server', argv=argv,
        instructions='fixed', invocation=invocation, timeout_seconds=1)
    host = CodexAppServerAdapter(argv=argv, resource_id='fixture', principal_salt=b'fixture',
        options=AppServerOptions(experimental_api=True), dynamic_tools_factory=lambda ctx, adapter: value)
    host._worker = SimpleNamespace(digest=lambda: 'a' * 64, reviewed_files={})
    host.probe = AsyncMock(return_value=HostProbe(adapter_id='codex-app-server', status=HostProbeStatus.READY))
    host.list_models = AsyncMock(return_value=[HostModel(id='fixture')])
    monkeypatch.setattr('aeep.hosts.codex_app_server.inventory', AsyncMock(return_value={'skills': [], 'apps': [], 'servers': []}))
    monkeypatch.setattr('aeep.hosts.codex_app_server.verify_thread_inventory', AsyncMock(return_value=None))
    ctx = ManagedHostExecutionContext(request=ActionRequest(capability='fixed', input={}),
        instruction='fixed', config=config, attempt=1, attempt_id='case')
    try:
        raw = await host._execute(ctx)
        assert raw.status is (ExecutionStatus.SUCCESS if mode == 'success' else ExecutionStatus.FAILED)
        if mode == 'success':
            assert raw.output == {'completed': True} and raw.metadata['dynamic_tool_calls'] == 1
        assert not host.transport._dynamic_tasks
        assert effects
        if mode != 'success':
            assert cancelled
            assert raw.metadata['dynamic_cleanup_confirmed']
    finally:
        await host.transport.close()


@pytest.mark.asyncio
async def test_callback_identity_link_is_retained_before_output_rejection():
    from aeep.execution import EventJournal
    from aeep.hosts.codex_dynamic_tools import current_dynamic_call
    observed = []
    async def call(name, args):
        context = current_dynamic_call()
        assert context is not None and context.action_id == 'dynamic_' + context.call_digest
        observed.append(context.outer_attempt_digest)
        context.record_link('f' * 64)
        return {'isError': False, 'structuredContent': {'value': 'invalid'}}
    value, _ = binding(call)
    journal = EventJournal('outer')
    active = DynamicToolSession(value, worker_digest='a' * 64, expected_digest=value.digest,
        approved_side_effect=SideEffect.READ, max_bytes=4096,
        deadline=asyncio.get_running_loop().time() + 2, outer_attempt_id='outer', journal=journal)
    active.bind_thread('thread')
    active.bind_turn('turn')
    with pytest.raises(InputValidationError):
        await active.call(params())
    assert observed and active.evidence[0]['evidence_ref'] == 'f' * 64
    assert any(event.evidence_ref == 'f' * 64 for event in journal.items)
    assert current_dynamic_call() is None


@pytest.mark.asyncio
async def test_transport_teardown_runs_when_callback_cleanup_is_unconfirmed(monkeypatch):
    from aeep.hosts.codex_app_server import CodexProtocolError
    fixture = Path(__file__).parent / 'fixtures/fake_codex_dynamic_tools.py'
    transport = CodexAppServerTransport((sys.executable, '-u', str(fixture), 'success'))
    await transport.start()
    process = transport._process
    async def unconfirmed():
        raise CodexProtocolError('dynamic task cleanup unconfirmed')
    monkeypatch.setattr(transport, 'cancel_dynamic_tools', unconfirmed)
    with pytest.raises(CodexProtocolError, match='cleanup unconfirmed'):
        await transport.close()
    assert process.returncode is not None and not transport._tasks and transport._process is None


@pytest.mark.asyncio
async def test_exec_explicitly_rejects_turn_with_dynamic_binding():
    from aeep.hosts.base import ManagedHostExecutionContext
    from aeep.hosts.codex_exec import CodexExecAdapter
    from aeep.models import ActionRequest, ExecutionStatus, ExecutorSpec
    spec = ExecutorSpec(id='exec', capability='fixed', kind='host_managed', resource_pool='fixture',
        description='offline unsupported dynamic host', config={'adapter_id': 'codex-exec',
        'argv': [sys.executable], 'instructions': 'fixed',
        'invocation': {'mode': 'turn', 'dynamic_tools_digest': 'a' * 64}})
    host = CodexExecAdapter(spec)
    ctx = ManagedHostExecutionContext(request=ActionRequest(capability='fixed', input={}),
        instruction='fixed', config=host.config, attempt=1, attempt_id='case')
    assert (await host.execute(ctx)).status is ExecutionStatus.REJECTED


def test_old_pair_inspection_cannot_attest_dynamic_exposure():
    from test_v08_pair_inspection import definition

    from aeep.hosts.codex_pair_inspection import WorkerPairInspection
    value = definition(task_profile=True).model_dump(mode='json')
    value['control']['config']['invocation']['dynamic_tools_digest'] = 'a' * 64
    with pytest.raises(ValueError):
        WorkerPairInspection.model_validate(value)

@pytest.mark.parametrize('change', ['limits', 'program', 'missing', 'fresh'])
def test_reviewed_binding_rejects_changed_scope_program_or_missing_executor(tmp_path, monkeypatch, change):
    from datetime import timedelta
    from types import SimpleNamespace

    from aeep.assessment.onboarding import reference_spec
    from aeep.assessment.repository import AssessmentRepository
    from aeep.economic.prepared import executor_fingerprint
    from aeep.models import ExecutorKind, Manifest, TaskScope, utc_now
    from aeep.router import Router
    spec = reference_spec('csv').model_copy(update={'kind': ExecutorKind.COMMAND,
        'config': {'argv': [sys.executable, '-I', '-c', 'print(1)'], 'argv_literal': True}})
    router = Router(Manifest(database=str(tmp_path/'state.db'), executors=[spec]), manifest_path=tmp_path.resolve()/'manifest.json')
    repo = AssessmentRepository(router.store)
    scope = TaskScope(scope_id='bound', project_root=str(tmp_path.resolve()),
        executor_fingerprints={spec.id: executor_fingerprint(spec)}, max_attempts=1,
        max_attempt_seconds=1, expires_at=utc_now()+timedelta(minutes=5))
    digest = repo.put('task_scope', scope.scope_id, scope)
    repo.review(digest)
    router.bind_task_scope(scope.scope_id)
    value, _ = binding()
    value.identity.update(scope_limits={'max_attempts': 1, 'max_attempt_seconds': 1}, executor_fingerprints=scope.executor_fingerprints,
                          implementation_digest=value.implementation_digest())
    value.digest = __import__('aeep.hosts.codex_invocation', fromlist=['contract_digest']).contract_digest(value.definition())
    original_get = repo.get
    monkeypatch.setattr(repo, 'get', lambda kind, key: value.definition() if kind == 'codex_dynamic_tools' else original_get(kind, key))
    router.store._connection.execute('INSERT INTO assessment_reviews(digest, approved_at, revoked) VALUES (?, ?, 0)', (value.digest, utc_now().isoformat()))
    router.store._connection.commit()
    if change == 'limits':
        other = scope.model_copy(update={'scope_id': 'other', 'max_attempts': 2})
        other_digest = repo.put('task_scope', other.scope_id, other)
        repo.review(other_digest)
        router._task_scope_digest = other_digest
    elif change == 'program':
        changed = spec.model_copy(update={'config': {**spec.config, 'argv': [sys.executable, '-I', '-c', 'print(2)']}})
        monkeypatch.setattr(router.registry, 'all', lambda: [changed])
    elif change == 'missing':
        monkeypatch.setattr(router.registry, 'all', lambda: [])
    else:
        from aeep.hosts.codex_invocation import contract_digest
        from aeep.hosts.codex_sandbox import NativeSandboxConfig
        monkeypatch.setattr(NativeSandboxConfig, 'model_validate', lambda value: SimpleNamespace(single_process=True, validate_single_process=lambda: None))
        monkeypatch.setattr('aeep.hosts.codex_sandbox.native_backend_digest', lambda value: 'same-backend')
        monkeypatch.setattr(router, '_require_active_spec', lambda spec: None)
        value.identity['native_backend_digest'] = contract_digest({spec.id: 'same-backend'})
        value.digest = contract_digest(value.definition())
        router.store._connection.execute('INSERT INTO assessment_reviews VALUES (?, ?, 0)', (value.digest, utc_now().isoformat()))
        router.store._connection.commit()
        for index in range(2):
            fresh = scope.model_copy(update={'scope_id': f'fresh-{index}'})
            fresh_digest = repo.put('task_scope', fresh.scope_id, fresh)
            repo.review(fresh_digest)
            router._task_scope_digest = fresh_digest
            assert value.require_reviewed_binding(repo, worker=SimpleNamespace(digest=lambda: 'a'*64), service=SimpleNamespace(router=router)) == value.digest
        router.store.close()
        return
    try:
        with pytest.raises(ConfigurationError, match=r'scope|fingerprint|missing'):
            value.require_reviewed_binding(repo, worker=SimpleNamespace(digest=lambda: 'a'*64),
                service=SimpleNamespace(router=router))
    finally:
        router.store.close()

@pytest.mark.asyncio
async def test_cloned_campaign_factory_captures_actual_router_and_reserved_attempt(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from test_v08_assessment import setup_assessment

    from aeep.assessment.fixed_helper import current_assessment_router
    from aeep.assessment.models import AssessmentLimits, content_digest
    from aeep.attempts import ExecutionAttempt
    from aeep.hosts.base import HostModel, HostProbe, HostProbeStatus, ManagedHostExecutionContext
    from aeep.hosts.codex_app_server import CodexAppServerAdapter
    from aeep.models import ActionRequest

    root, assessment, plan, _grant = setup_assessment(tmp_path)
    job = assessment.enqueue(plan.plan_id)
    with root.store._immediate_transaction() as connection:
        connection.execute("UPDATE assessment_jobs SET state='running' WHERE id=?", (job,))
    assessment.repository.reserve(plan, 'factory-trial', AssessmentLimits(max_operations=1, max_elapsed_seconds=20), stage='trial')
    scoped = root._campaign_router([root.registry.get(plan.candidate_id)], plan_digest=content_digest(plan))
    scoped._callback_trial_identity = (job, 'factory-trial')
    scoped._trial_check = lambda: assessment.repository.authorize(plan)
    attempt = scoped.store.create_execution_attempt(ExecutionAttempt(attempt_id='factory-outer',
        decision_id='factory-decision', action_digest='a'*64, executor_id=plan.candidate_id,
        executor_fingerprint='b'*64, side_effect=SideEffect.READ, idempotent=True,
        owner_id='operator', state='INVOKING', invocation_start_digest='sha256:'+'c'*64))
    value, calls = binding()
    captured = []
    def factory(context, adapter):
        actual = current_assessment_router()
        assert actual is scoped and actual is not root
        assert actual._callback_trial_identity == (job, 'factory-trial')
        assert context.attempt_id == attempt.attempt_id
        assert assessment.repository.operation_ledger(plan.plan_id).operations[0].elapsed_seconds is None
        captured.append(actual)
        return value
    argv = (sys.executable, '-u', str(Path(__file__).parent/'fixtures/fake_codex_dynamic_tools.py'), 'success')
    cfg = ManagedHostExecutorConfig(adapter_id='codex-app-server', argv=argv, instructions='fixed',
        invocation=ManagedHostInvocation(mode='dynamic_tool', server='task', tool='fixed',
            tool_sha256=value.inventory()['dynamic:task:fixed'], dynamic_tools_digest=value.digest,
            exposure='required'), timeout_seconds=1)
    host = CodexAppServerAdapter(argv=argv, resource_id='factory', principal_salt=b'fixture',
        options=AppServerOptions(experimental_api=True), dynamic_tools_factory=factory)
    host._worker = SimpleNamespace(digest=lambda: 'a'*64, reviewed_files={})
    host.probe = AsyncMock(return_value=HostProbe(adapter_id='codex-app-server', status=HostProbeStatus.READY))
    host.list_models = AsyncMock(return_value=[HostModel(id='fixture')])
    monkeypatch.setattr('aeep.hosts.codex_app_server.inventory', AsyncMock(return_value={'skills': [], 'apps': [], 'servers': []}))
    monkeypatch.setattr('aeep.hosts.codex_app_server.verify_thread_inventory', AsyncMock(return_value=None))
    context = ManagedHostExecutionContext(request=ActionRequest(capability='fixed', input={}),
        instruction='fixed', config=cfg, attempt=1, attempt_id=attempt.attempt_id)
    # Only protocol/model execution is stubbed; the scoped invocation context is real.
    monkeypatch.setattr(scoped, '_invoke_controlled_authorized', lambda unused: host._execute(context))
    try:
        raw = await scoped._invoke_controlled(None)
        assert raw.status.value == 'success' and captured == [scoped] and calls
        assert current_assessment_router() is None
    finally:
        await host.close()
        await scoped.close()
        await root.close()
