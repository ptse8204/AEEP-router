from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from aeep.assessment.boundary import (
    BoundaryProbeDefinition,
    prepare_model_probe,
    run_boundary_probe,
)
from aeep.assessment.models import AssessmentScopeAmendment, ConformanceProbeRequest, content_digest
from aeep.errors import ConfigurationError
from aeep.execution import EventJournal, ExecutionEvidence
from aeep.hosts.codex_app_server import CodexRequestError
from aeep.hosts.codex_inspection import COMMAND, collect, execute, policy_observations, prepare
from aeep.models import ExecutorSpec

pytestmark = pytest.mark.assessment_lifecycle


@pytest.mark.parametrize('stage,error,expected', [
    ('creation', PermissionError, 'denied'), ('connect', PermissionError, 'denied'),
    ('connect', TimeoutError, 'unreachable'), ('connect', None, 'permitted'),
])
def test_fixed_program_retains_observations_when_socket_creation_is_denied(monkeypatch, capsys, stage, error, expected):
    import errno
    import io
    import pathlib
    import socket

    closed = []
    class SyntheticPath:
        def __init__(self, name):
            self.name = name
        def open(self, mode):
            assert mode == 'x'
            if self.name.startswith('/opt/'):
                if stage == 'creation':
                    raise OSError(errno.EROFS, 'synthetic read-only image')
                raise PermissionError('synthetic denied path')
            return io.StringIO()
        def read_text(self):
            return 'synthetic'
        def unlink(self):
            pass
    def create_socket():
        if stage == 'creation':
            raise error('synthetic socket creation denial')
        def connect(endpoint):
            if error is not None:
                raise error('synthetic connection failure')
        return SimpleNamespace(settimeout=lambda value: None, connect=connect, close=lambda: closed.append(True))
    with monkeypatch.context() as patch:
        patch.setattr(pathlib, 'Path', SyntheticPath)
        patch.setattr(socket, 'socket', create_socket)
        exec(compile(COMMAND, '<fixed-inspection>', 'exec'), {'PROXY_HOST':'127.0.0.1','PROXY_PORT':3128})
    assert json.loads(capsys.readouterr().out) == {
        'workspace_write':True,'configuration_write':'read_only' if stage == 'creation' else 'denied',
        'proxy':expected,'direct':expected}
    assert len(closed) == (0 if stage == 'creation' else 2)


@pytest.mark.real_container
@pytest.mark.assessment_boundary
@pytest.mark.skipif(not os.environ.get('AEEP_INSPECTION_FIXTURE_SPECS'), reason='requires explicit offline Codex worker specs')
async def test_real_offline_codex_inspection_uses_sandbox_without_credentials():
    import asyncio

    from aeep.hosts.codex_app_server import CodexAppServerAdapter
    from aeep.hosts.workers import binding_from_config

    data = await asyncio.to_thread(Path(os.environ['AEEP_INSPECTION_FIXTURE_SPECS']).read_bytes)
    assert len(data) < 262144
    specs = json.loads(data)
    assert isinstance(specs, list) and 1 <= len(specs) <= 2
    for value in specs:
        spec = ExecutorSpec.model_validate(value)
        config = spec.managed_host_config()
        worker = binding_from_config(config.managed_worker)
        assert worker is not None
        assert worker.credential_volume is worker.network_id is worker.model_proxy_url is None
        assert config.argv == (worker.binary, 'app-server')
        adapter = CodexAppServerAdapter.from_executor(spec, principal_salt=b'offline-fixture')
        try:
            result = await adapter.transport.request('command/exec', {
                'command':['python3','-c',COMMAND.replace('PROXY_HOST',repr('127.0.0.1')).replace('PROXY_PORT','3128')],
                'cwd':'/workspace','timeoutMs':10000,'outputBytesCap':4096}, timeout=20)
            assert result['exitCode'] == 0, result
            # The deny-by-default profile hides this path. Absence is not a
            # claim that a filesystem permission error was observed.
            assert json.loads(result['stdout']) == {
                'workspace_write':True,'configuration_write':'absent','proxy':'denied','direct':'denied'}
        finally:
            try:
                await adapter.transport.close()
            finally:
                assert await worker.cleanup(adapter._worker_process_id)
                if adapter._worker_security:
                    adapter._worker_security.cleanup()


def fake_adapter(*, failure=None, bad_output=None, unknown_policy=False):
    async def request(method, params, **kwargs):
        assert method in {'config/read', 'configRequirements/read', 'command/exec'}
        if method == failure:
            raise CodexRequestError(method, {'code': -32601})
        if method == 'config/read':
            return {'config': {'default_permissions': 'aeep', 'approval_policy': 'never',
                'web_search': 'disabled', 'mcp_servers': {} if not unknown_policy else {'unreviewed': {}},
                'features': {'apps': False}, 'secret': 'do-not-persist'}}
        if method == 'configRequirements/read':
            return {'requirements': None}
        assert 'sandboxPolicy' not in params and 'permissionProfile' not in params
        assert params['command'][:2] == ['python3','-c'] and params['timeoutMs'] == 10000
        assert '/worker/auth' not in params['command'][2]
        return {'exitCode': 0, 'stdout': bad_output if bad_output is not None else json.dumps({
            'workspace_write': True, 'configuration_write': 'denied', 'proxy': 'denied', 'direct': 'unreachable'})}
    return SimpleNamespace(transport=SimpleNamespace(request=AsyncMock(side_effect=request),
            protocol_version='fixture',close=AsyncMock()),
        resolve_identity=AsyncMock(return_value='a'*64), list_models=AsyncMock(return_value=[]),
        inventory=AsyncMock(return_value={'skills': [], 'apps': [], 'servers': []}),
        _worker_process_id='fixture', _worker_security=None)


def config():
    from test_v08_managed_workers import binding
    worker = binding().model_copy(update={'network_id':'b'*64,'model_proxy_url':'http://172.22.0.2:3128'})
    spec = ExecutorSpec(id='inspection',capability='aeep.conformance.connectivity@1',kind='host_managed',
        resource_pool='pool',description='Offline inspection fixture',config={
        'adapter_id':'codex-app-server:fixture','argv':[worker.binary], 'instructions':'Unused by inspection',
        'managed_worker':worker.model_dump(mode='json'), 'timeout_seconds':60})
    return worker, spec


@pytest.mark.parametrize('failure,bad_output,unknown_policy', [
    (None,None,False), ('config/read',None,False), ('command/exec',None,False),
    (None,'not-json',False), (None,'{}',False), (None,'x'*4097,False), (None,None,True),
])
async def test_turn_free_inspection_does_not_retain_raw_policy_or_expand_access(failure,bad_output,unknown_policy):
    _, spec = config()
    adapter = fake_adapter(failure=failure,bad_output=bad_output,unknown_policy=unknown_policy)
    facts = await collect(adapter,spec.managed_host_config(),EventJournal('fixture'),lambda: None)
    assert not facts['full_conformance'] and facts['model_turns'] == 0
    assert 'do-not-persist' not in json.dumps(facts)
    assert facts['inspection_complete'] == (failure != 'command/exec' and bad_output is None)
    if failure == 'config/read' or unknown_policy:
        adapter.inventory.assert_not_awaited()
    assert not any(call.args[0] == 'turn/start' for call in adapter.transport.request.await_args_list)
    assert policy_observations({}, {'config/secret':False})['config/secret'] == {
        'present':False,'matches':False,'expected':False}
    assert not policy_observations({'config':{'feature':0}}, {'config/feature':False})['config/feature']['matches']


async def test_worker_inspection_review_budget_partial_evidence_cleanup_and_no_replay(tmp_path,monkeypatch):
    from test_v08_assessment import setup_assessment

    from aeep.executors.command import CommandExecutor
    from aeep.hosts.codex_signin import signin_worker

    router,service,plan,grant = setup_assessment(tmp_path)
    worker,spec = config()
    try:
        source = prepare_model_probe(service,source_plan_id=plan.plan_id,
            definition=BoundaryProbeDefinition(name='model_connectivity',executor=spec,expected={'connected':True}))
        assert 'operation' not in source.model_dump(mode='json')
        with pytest.raises(ConfigurationError,match='own reviewed request'):
            await execute(service,source.plan_id)
        request = prepare(service,source.plan_id)
        assert request.operation == 'worker_inspection'
        assert request.schema_version.endswith('.v2')
        with pytest.raises(ValueError,match='v2'):
            ConformanceProbeRequest.model_validate({**source.model_dump(),'operation':'worker_inspection'})
        with pytest.raises(ConfigurationError,match=r'scope|review'):
            await execute(service,request.plan_id)
        digests={*request.definition_digests,request.subject_digest}
        definitions={d:json.loads(service.repository.store._connection.execute(
            'SELECT payload_json FROM assessment_records WHERE digest=?',(d,)).fetchone()[0]) for d in digests}
        service.repository.approve_bundle(AssessmentScopeAmendment(authorization_id=grant.authorization_id,
            authorization_digest=content_digest(grant),subject_digests=[request.subject_digest],
            recipe_digests=[request.recipe_digest],environment_digests=[request.environment_digest],
            reviewed_digests=request.definition_digests),definitions)
        with pytest.raises(ConfigurationError,match='cannot start'):
            await run_boundary_probe(service.repository,request.mapping_digest,worker_digest=worker.digest(),
                executor=CommandExecutor(),plan=request)
        with monkeypatch.context() as patch:
            import sys
            patch.setattr(sys.stdin,'isatty',lambda:True)
            patch.setattr(sys.stdout,'isatty',lambda:True)
            with pytest.raises(ConfigurationError,match='another sign-in'):
                await signin_worker(service,request.plan_id)
        original_get = service.repository.get
        def drift(kind, identity):
            payload = original_get(kind, identity)
            if kind == 'conformance_request' and identity == request.plan_id:
                return {**payload, 'worker_digest': 'f'*64}
            return payload
        with monkeypatch.context() as patch:
            patch.setattr(service.repository,'get',drift)
            with pytest.raises(ConfigurationError,match='differs'):
                await execute(service,request.plan_id)
        clean=AsyncMock(return_value=True)
        monkeypatch.setattr(type(worker),'cleanup',clean)
        adapter=fake_adapter()
        monkeypatch.setattr('aeep.hosts.codex_inspection.CodexAppServerAdapter.from_executor',lambda *a,**k:adapter)
        result=await execute(service,request.plan_id)
        assert result.observations['inspection_complete'] and result.observations['cleanup_confirmed']
        evidence=ExecutionEvidence.model_validate(service.repository.get('execution_evidence',result.execution_evidence_digest))
        assert evidence.complete and evidence.boundary_digest==worker.digest() and evidence.identity_digest=='a'*64
        assert evidence.events[-1].kind=='execution.completed'
        assert any(event.evidence_ref==content_digest(result.observations) for event in evidence.events)
        operations=service.repository.operation_ledger(request.plan_id).operations
        assert len(operations)==1 and operations[0].reserved.max_model_turns==0 and operations[0].elapsed_seconds is not None
        with pytest.raises(ConfigurationError,match='blind retry'):
            await execute(service,request.plan_id)
        for broken, cleanup in ((fake_adapter(bad_output='{}'),True),(fake_adapter(),False)):
            followup=prepare(service,source.plan_id)
            monkeypatch.setattr('aeep.hosts.codex_inspection.CodexAppServerAdapter.from_executor',lambda *a, broken=broken, **k:broken)
            clean.return_value=cleanup
            observed=await execute(service,followup.plan_id)
            assert not observed.observations['inspection_complete']
            assert service.repository.operation_ledger(followup.plan_id).operations[0].elapsed_seconds is not None
            failure=ExecutionEvidence.model_validate(service.repository.get('execution_evidence',observed.execution_evidence_digest))
            assert failure.events[-1].kind=='execution.failed'
        def broken_factory(*args, **kwargs):
            raise OSError('synthetic constructor failure')
        monkeypatch.setattr('aeep.hosts.codex_inspection.CodexAppServerAdapter.from_executor',broken_factory)
        failed = await execute(service,prepare(service,source.plan_id).plan_id)
        assert not failed.observations['inspection_complete'] and not failed.observations['cleanup_confirmed']
        closing = fake_adapter()
        closing._worker_security = SimpleNamespace(cleanup=lambda: None)
        closing.transport.close.side_effect = OSError('synthetic close failure')
        clean.return_value = True
        monkeypatch.setattr('aeep.hosts.codex_inspection.CodexAppServerAdapter.from_executor',lambda *a,**k:closing)
        failed = await execute(service,prepare(service,source.plan_id).plan_id)
        assert failed.observations['cleanup_confirmed'] and not failed.observations['inspection_complete']
        assert failed.observations['cleanup_error_type']=='OSError'
        unidentified = fake_adapter()
        unidentified._worker_process_id = None
        monkeypatch.setattr('aeep.hosts.codex_inspection.CodexAppServerAdapter.from_executor',lambda *a,**k:unidentified)
        failed = await execute(service,prepare(service,source.plan_id).plan_id)
        assert not failed.observations['cleanup_confirmed'] and not failed.observations['inspection_complete']
        assert router.store._connection.execute('SELECT COUNT(*) FROM assessment_admissions').fetchone()[0]==0
        service.repository.revoke(grant.authorization_id)
        with pytest.raises(ConfigurationError,match='revoked'):
            await execute(service,prepare(service,source.plan_id).plan_id)
    finally:
        await router.close()
