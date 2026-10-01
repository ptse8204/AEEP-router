"""Offline definition checks; actual worker/native conformance remains separate."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from aeep.errors import ConfigurationError
from aeep.execution import EventJournal
from aeep.hosts.codex_app_server import AppServerOptions
from aeep.hosts.codex_dynamic_tools import CodexDynamicTools
from aeep.hosts.codex_pair_inspection import inspect_dynamic_declaration
from aeep.models import ManagedHostInvocation


@pytest.mark.asyncio
async def test_zero_turn_declaration_does_not_install_handler_or_claim_exposure(monkeypatch):
    holder = {}
    async def forbidden(*args):
        raise AssertionError('inspection dispatched task')
    binding = CodexDynamicTools(namespace='task', tools=[{'name': 'fixed',
        'description': 'Synthetic fixed task', 'inputSchema': {'type': 'object'}}],
        identity={'worker_digest': 'a'*64, 'native_backend_digest': 'b'*64,
                  'implementation_digest': 'c'*64, 'approval_ceiling': 'read'},
        max_calls=1, timeout_seconds=1, call=forbidden,
        check=lambda: holder['binding'].digest)
    holder['binding'] = binding
    response = {'thread': {'id': 'synthetic'}, 'approvalsReviewer': 'user',
        'activePermissionProfile': {'id': 'aeep', 'extends': None},
        'approvalPolicy': 'never', 'cwd': '/workspace'}
    transport = SimpleNamespace(options=AppServerOptions(experimental_api=True),
        request=AsyncMock(return_value=response), dynamic_tool_handler=None)
    adapter = SimpleNamespace(transport=transport, list_models=AsyncMock(return_value=[]))
    target = ManagedHostInvocation(mode='turn', dynamic_tools_digest=binding.digest)
    config = SimpleNamespace(invocation=target)
    worker = SimpleNamespace(digest=lambda: 'a'*64, permissions_profile='aeep', reviewed_files={})
    monkeypatch.setattr('aeep.hosts.codex_app_server._select_model_config', lambda models, cfg: SimpleNamespace(id='metadata-only'))
    monkeypatch.setattr('aeep.hosts.codex_invocation.inventory', AsyncMock(return_value={}))
    monkeypatch.setattr('aeep.hosts.codex_invocation.isolated_config', lambda *args, **kwargs: {})
    monkeypatch.setattr('aeep.hosts.codex_invocation.verify_thread_inventory', AsyncMock())
    result = await inspect_dynamic_declaration(adapter, config=config, worker=worker,
        binding=binding, journal=EventJournal('synthetic'), recheck=lambda: None)
    assert result['model_tool_exposure'] == 'unknown'
    assert result['model_turns'] == result['task_calls'] == 0
    assert transport.dynamic_tool_handler is None
    assert [call.args[0] for call in transport.request.await_args_list] == ['thread/start']
    transport.options = AppServerOptions(experimental_api=False)
    with pytest.raises(ConfigurationError):
        await inspect_dynamic_declaration(adapter, config=config, worker=worker,
            binding=binding, journal=EventJournal('rejected'), recheck=lambda: None)


@pytest.mark.asyncio
async def test_scripted_callback_uses_transport_but_does_not_claim_native_host_call():
    import sys
    from pathlib import Path

    from aeep.hosts.codex_app_server import CodexAppServerTransport
    from aeep.hosts.codex_pair_inspection import inspect_scripted_callback

    holder = {}
    observed = []
    async def call(name, arguments):
        observed.append((name, arguments))
        return {'isError': False, 'structuredContent': {'ok': True}}
    binding = CodexDynamicTools(namespace='bounded', tools=[{'name': 'fixed',
        'description': 'Operator bound synthetic task',
        'inputSchema': {'type': 'object', 'additionalProperties': False}}],
        identity={'worker_digest': 'a'*64, 'native_backend_digest': 'b'*64,
                  'implementation_digest': 'c'*64, 'approval_ceiling': 'read'},
        max_calls=1, timeout_seconds=1, call=call,
        check=lambda: holder['binding'].digest)
    holder['binding'] = binding
    transport = CodexAppServerTransport(argv=(sys.executable, '-u',
        str(Path(__file__).parent/'fixtures/fake_composed_callback.py')),
        options=AppServerOptions(experimental_api=True))
    try:
        result = await inspect_scripted_callback(transport, binding=binding,
            worker_digest='a'*64, outer_attempt_id='owned-fixture',
            journal=EventJournal('scripted'), recheck=lambda: None, timeout_seconds=2)
        assert result['response_success'] and observed == [('fixed', {})]
        assert result['completed_tools'] == ['fixed']
        assert result['native_host_issued_callback'] == 'unobserved'
        assert result['model_turns'] == 0
    finally:
        await transport.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['guard', 'cancel_after_write'])
async def test_canonical_scripted_callback_executes_protected_csv_native_guard(tmp_path, case):
    """Actual native child + scripted host peer; never full native-host conformance."""
    import errno
    import json
    import sys
    import time
    from datetime import timedelta
    from pathlib import Path
    from types import SimpleNamespace

    from test_v08_assessment import setup_assessment
    from test_v08_native_process import BINARY, boundary

    from aeep.assessment.fixed_helper import AssessmentCallbackAuthority, FixedHelperService
    from aeep.assessment.identity import runtime_dependencies
    from aeep.assessment.models import AssessmentLimits, ConformanceProbeRequest, content_digest
    from aeep.assessment.onboarding import reference_spec
    from aeep.assessment.repository import AssessmentRepository
    from aeep.attempts import ExecutionAttempt
    from aeep.economic.prepared import executor_fingerprint
    from aeep.hosts.codex_app_server import CodexAppServerTransport
    from aeep.hosts.codex_invocation import contract_digest
    from aeep.hosts.codex_pair_inspection import (
        inspect_scripted_callback,
        protected_callback_evidence,
    )
    from aeep.hosts.codex_sandbox import native_backend_digest
    from aeep.models import (
        ActionConstraints,
        ExecutorKind,
        Manifest,
        PolicyConfig,
        SideEffect,
        StrictModel,
        TaskScope,
        utc_now,
    )
    from aeep.router import Router

    if sys.platform != 'darwin' or not BINARY.exists():
        pytest.skip('pinned native Mac runtime required')
    (tmp_path/'assessment').mkdir()
    root, assessment, plan, _grant = setup_assessment(tmp_path/'assessment')
    private = tmp_path/'protected'
    private.mkdir()
    native = boundary(private.resolve())
    canary = private/'private-canary'
    canary.write_text('synthetic-private-witness')
    native = native.model_copy(update={'deny_roots': [str(canary), str(private/'state.db')]})
    text = f'hard_nproc,fork_errno,spawn_errno,marker,private_denied\n0:0,{errno.EAGAIN},{errno.EAGAIN},post_exec,true\n'
    program = ('import os,resource,json; r={"hard_nproc":":".join(map(str,resource.getrlimit(resource.RLIMIT_NPROC))),"marker":"post_exec"};\n'
        'try:os.fork();r["fork_errno"]="unexpected"\nexcept OSError as e:r["fork_errno"]=str(e.errno)\n'
        'try:os.posix_spawn("/usr/bin/true",["/usr/bin/true"],{});r["spawn_errno"]="unexpected"\nexcept OSError as e:r["spawn_errno"]=str(e.errno)\n'
        f'try:open({str(canary)!r}).read();r["private_denied"]="false"\nexcept PermissionError:r["private_denied"]="true"\n'
        'print(json.dumps({"records":[r]}))')
    marker = private/'data'/'owned-callback-effect'
    if case == 'cancel_after_write':
        program = f'import pathlib,time;pathlib.Path({str(marker)!r}).write_text("synthetic");time.sleep(30)'
    ceiling = SideEffect.WRITE if case == 'cancel_after_write' else SideEffect.READ
    spec = reference_spec('csv').model_copy(update={'kind': ExecutorKind.COMMAND,
        'side_effect': ceiling, 'idempotent': case == 'guard',
        'config': {'argv': [native.python_binary, '-I', '-c', program],
            'argv_literal': True, 'output': {'type': 'json'}, 'timeout_seconds': 5,
            'native_sandbox': native.model_dump(mode='json')}})
    task_router = Router(Manifest(database=str(private/'state.db'), executors=[spec],
        policies={'balanced': PolicyConfig(name='balanced', constraints=ActionConstraints(max_side_effect=ceiling))}),
        manifest_path=private.resolve()/'manifest.json')
    task_repo = AssessmentRepository(task_router.store)
    scope = TaskScope(scope_id='native-inspection', project_root=str(private.resolve()),
        executor_fingerprints={spec.id: executor_fingerprint(spec)}, approval_ceiling=ceiling, max_attempts=1,
        max_attempt_seconds=5, expires_at=utc_now()+timedelta(minutes=5))
    task_repo.review(task_repo.put('task_scope', scope.scope_id, scope))
    task_router.bind_task_scope(scope.scope_id)
    descriptor = {'name': 'fixed_csv', 'description': 'Fixed public native CSV enforcement probe',
        'inputSchema': spec.input_schema}
    fixed = FixedHelperService(task_router, spec.id, task_scope=scope.scope_id,
        declaration=descriptor, check=lambda: content_digest(task_repo.get('task_scope', task_router._task_scope_digest)),
        approved_side_effect=ceiling)
    holder = {}
    def resolve():
        return holder['binding'].require_reviewed_binding(assessment.repository,
            worker=SimpleNamespace(digest=lambda: 'a'*64), service=fixed)
    callback_errors = []
    async def authorized(name, arguments):
        try:
            return await holder['authority'].call(fixed, name, arguments)
        except Exception as error:
            import hashlib
            message = str(error)
            callback_errors.append({'type': type(error).__name__, 'message_bytes': len(message.encode()),
                'message_sha256': hashlib.sha256(message.encode()).hexdigest()})
            raise
    binding = CodexDynamicTools.task_service(fixed, namespace='inspection',
        identity={'worker_digest': 'a'*64, 'native_backend_digest': contract_digest({spec.id: native_backend_digest(native)}),
            'implementation_digest': CodexDynamicTools.implementation_digest(), 'approval_ceiling': ceiling.value,
            'executor_fingerprints': scope.executor_fingerprints,
            'scope_limits': {'max_attempts': 1, 'max_attempt_seconds': 5}},
        max_calls=1, timeout_seconds=5.0, check=resolve, authorized_call=authorized)
    holder['binding'] = binding
    class Definition(StrictModel):
        namespace: str
        tools: list[dict]
        identity: dict
        max_calls: int
        timeout_seconds: float
    definition_digest = assessment.repository.put('codex_dynamic_tools', binding.digest,
        Definition.model_validate(binding.definition()))
    assessment.repository.review(definition_digest)
    request = ConformanceProbeRequest(schema_version='assessment.conformance-request.v4',
        subject_digest=plan.subject_digest, recipe_digest=plan.recipe_digest,
        environment_digest=plan.environment_digest, mapping_digest=plan.mapping_digest,
        authorization_id=plan.authorization_id, worker_digest='a'*64,
        definition_digests=[*plan.definition_digests, binding.digest],
        pair_definition_digest=binding.digest, executable_dependencies=runtime_dependencies(),
        operation='composed_pair_inspection', composed_model_turns=0)
    assessment.repository.put('conformance_request', request.plan_id, request)
    operation = 'owned-composed-inspection'
    started = time.perf_counter()
    assessment.repository.reserve(request, operation, AssessmentLimits(max_operations=1,
        max_elapsed_seconds=20, max_model_turns=0), stage='composed_pair_inspection')
    root._callback_conformance_identity = (request.plan_id, operation)
    root._trial_check = lambda: assessment.repository.authorize(request)
    attempt = root.store.create_execution_attempt(ExecutionAttempt(attempt_id='owned-composed-outer',
        decision_id='owned-composed-decision', action_digest='b'*64, executor_id=plan.candidate_id,
        executor_fingerprint='c'*64, side_effect=ceiling, idempotent=case == 'guard',
        owner_id='operator', state='INVOKING', invocation_start_digest='sha256:'+'d'*64))
    holder['authority'] = AssessmentCallbackAuthority.for_conformance(assessment, request, operation,
        outer_router=root, outer_attempt_id=attempt.attempt_id, binding_digest=binding.digest,
        resolve_binding=resolve, max_calls=1)
    task_router._trial_check = holder['authority'].check
    task_router._trial_deadline = root._trial_deadline
    transport = CodexAppServerTransport(argv=(sys.executable, '-u',
        str(Path(__file__).parent/'fixtures/fake_composed_callback.py'),
        json.dumps({'text': text, 'delimiter': ','})), options=AppServerOptions(experimental_api=True))
    try:
        if case == 'cancel_after_write':
            import asyncio
            task = asyncio.create_task(inspect_scripted_callback(transport, binding=binding, worker_digest='a'*64,
                outer_attempt_id=attempt.attempt_id, journal=EventJournal(operation),
                recheck=holder['authority'].check, timeout_seconds=10))
            async with asyncio.timeout(5):
                # The marker is an independent native-process observation.
                while not marker.exists():
                    if task.done():
                        result = await task
                        raise AssertionError({'callback_errors': callback_errors, 'response_success': result['response_success'], 'evidence': result['callback_evidence']})
                    await asyncio.sleep(.02)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert marker.read_text() == 'synthetic'
            with task_router.store._lock:
                states = [json.loads(row[0])['state'] for row in task_router.store._connection.execute('SELECT payload_json FROM execution_attempts')]
            assert 'INDETERMINATE' in states
            assert not transport._dynamic_tasks
            return
        result = await inspect_scripted_callback(transport, binding=binding, worker_digest='a'*64,
            outer_attempt_id=attempt.attempt_id, journal=EventJournal(operation),
            recheck=holder['authority'].check, timeout_seconds=10)
        evidence = protected_callback_evidence(assessment.repository, task_router, result)
        assert result['response_success'] and evidence['child_receipt_count'] == 1
        assert canary.read_text() == 'synthetic-private-witness'
        assert evidence['canonical_link_count'] == 1 and evidence['full_conformance'] is False
        assert evidence['native_host_issued_callback'] == 'unobserved'
        assert assessment.repository.operation_ledger(request.plan_id).operations[0].elapsed_seconds is None
        from aeep.errors import NoRouteError
        task_repo.review(content_digest(scope), revoke=True)
        with pytest.raises((ConfigurationError, NoRouteError)):
            await inspect_scripted_callback(transport, binding=binding, worker_digest='a'*64,
                outer_attempt_id=attempt.attempt_id, journal=EventJournal(operation+'-rejected'),
                recheck=holder['authority'].check, timeout_seconds=1)
        with task_router.store._lock:
            assert task_router.store._connection.execute('SELECT count(*) FROM execution_attempts').fetchone()[0] == 1
    finally:
        await transport.close()
        assessment.repository.finish_operation(operation, elapsed_seconds=time.perf_counter()-started)
        await task_router.close()
        await root.close()
