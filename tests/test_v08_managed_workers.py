from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest

from aeep.errors import ConfigurationError
from aeep.hosts.codex_exec import CodexExecAdapter
from aeep.hosts.workers import ManagedWorkerBinding, validate_worker_pair
from aeep.models import ExecutorSpec

pytestmark = pytest.mark.assessment_boundary


def binding(**changes):
    return ManagedWorkerBinding(worker_id="candidate", runtime="/usr/local/bin/docker", socket=changes.pop("socket", "/tmp/docker.sock"),
        image="sha256:" + "1" * 64, platform="linux/arm64", binary="/opt/codex",
        binary_sha256="2" * 64, configuration_digest="3" * 64, dependencies_digest="4" * 64,
        **changes)


def test_worker_process_arguments_have_no_host_mounts_or_shared_state():
    worker = binding()
    argv = worker.argv(("exec", "--json"), execution_id="candidate-case", output_schema={"type": "object"})
    assert "type=bind" not in " ".join(argv)
    assert argv[argv.index("--network") + 1] == "none"
    assert argv[argv.index("--user") + 1] == "65534:65534"
    assert "--read-only" in argv and "--cap-drop=ALL" in argv
    other = worker.model_copy(update={"worker_id": "baseline"})
    validate_worker_pair(worker, other)
    with pytest.raises(ConfigurationError, match="independent"):
        validate_worker_pair(worker, worker)
    with pytest.raises(ConfigurationError, match="differ"):
        validate_worker_pair(worker, other.model_copy(update={"memory_mb": 512}))
    with pytest.raises(ConfigurationError, match="NUL"):
        worker.argv(("bad\x00arg",), execution_id="test")
    with pytest.raises(ValueError, match="explicit"):
        binding(socket="relative")


def test_reviewed_security_profile_is_private_bounded_and_shared_by_arms(tmp_path):
    profile = {"defaultAction": "SCMP_ACT_ERRNO", "syscalls": []}
    with pytest.raises(ValueError, match="contract v2"):
        binding(seccomp_profile=profile)
    with pytest.raises(ValueError, match="deny by default"):
        binding(schema_version="execution.worker.v2", seccomp_profile={"defaultAction": "SCMP_ACT_ALLOW"})
    worker = binding(schema_version="execution.worker.v2", seccomp_profile=profile, permissions_profile="aeep")
    with pytest.raises(ConfigurationError, match="snapshot"):
        worker.argv(("exec",), execution_id="case")
    snapshot = worker.prepare_security(tmp_path)
    assert snapshot is not None and not snapshot.stat().st_mode & 0o200
    if os.name == "posix":
        assert snapshot.stat().st_mode & 0o777 == 0o400
    argv = worker.argv(("exec",), execution_id="case", security_path=snapshot)
    assert "seccomp=" + str(snapshot) in argv
    assert "type=bind" not in " ".join(argv)
    other = worker.model_copy(update={"worker_id":"baseline"})
    validate_worker_pair(worker, other)
    with pytest.raises(ConfigurationError, match="differ"):
        validate_worker_pair(worker, other.model_copy(update={"seccomp_profile":None}))
    snapshot.chmod(0o600)
    snapshot.write_text('{}')
    with pytest.raises(ConfigurationError, match="snapshot"):
        worker.argv(("exec",), execution_id="case", security_path=snapshot)
    assert "seccomp_profile" not in binding().model_dump()


async def test_worker_binary_not_host_dependency_and_environment_cannot_leak():
    worker = binding()
    spec = ExecutorSpec(id="worker", capability="fixture", kind="host_managed", resource_pool="pool",
                        description="controlled worker", config={"adapter_id": "codex-exec", "argv": [worker.binary],
                        "instructions": "fixture", "exec_model": "fixture", "managed_worker": worker.model_dump(mode="json")})
    host = CodexExecAdapter(spec)
    assert host.worker == worker
    wrong = spec.model_copy(deep=True)
    wrong.config["environment_allowlist"] = ["HOME"]
    with pytest.raises(ConfigurationError, match="inherited"):
        CodexExecAdapter(wrong)
    wrong.config["environment_allowlist"] = []
    wrong.config["argv"] = [sys.executable]
    with pytest.raises(ConfigurationError, match="exact binary"):
        CodexExecAdapter(wrong)
    await host.close()


async def test_app_server_fresh_worker_cleanup_covers_production_and_failure(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from aeep.hosts.base import ManagedHostExecutionContext
    from aeep.hosts.codex_app_server import CodexAppServerAdapter
    from aeep.models import ActionRequest, ExecutionStatus, ManagedHostExecutorConfig, RawExecution

    adapter = CodexAppServerAdapter(argv=(sys.executable,), resource_id='pool', principal_salt=b'fixture')
    cleanup = AsyncMock(return_value=True)
    adapter._worker = SimpleNamespace(digest=lambda: 'a'*64, cleanup=cleanup)
    adapter._worker_process_id = 'worker-fixture'
    adapter.transport.close = AsyncMock()
    monkeypatch.setattr(adapter, '_execute', AsyncMock(return_value=RawExecution(status=ExecutionStatus.SUCCESS, output={})))
    context = ManagedHostExecutionContext(request=ActionRequest(capability='fixture'), instruction='fixture',
        config=ManagedHostExecutorConfig(adapter_id='codex-app-server', argv=[sys.executable], instructions='fixture'),
        attempt=1, attempt_id='attempt')
    result = await adapter.execute(context)
    assert result.metadata['worker_cleanup_confirmed'] is True
    assert cleanup.await_count == adapter.transport.close.await_count == 1
    cleanup.return_value = False
    result = await adapter.execute(context)
    assert result.status == ExecutionStatus.FAILED and result.error_type == 'WORKER_CLEANUP_UNCONFIRMED'
    monkeypatch.setattr(adapter, '_execute', AsyncMock(side_effect=RuntimeError('interrupted')))
    with pytest.raises(RuntimeError, match='interrupted'):
        await adapter.execute(context)
    assert cleanup.await_count == adapter.transport.close.await_count == 3


async def test_shared_managed_executor_rechecks_revocation_after_probe():
    from aeep.executors.base import ExecutionContext
    from aeep.executors.managed_host import ManagedHostExecutor
    from aeep.hosts import HostProbe, HostProbeStatus, ManagedHostRegistry
    from aeep.models import ActionRequest, RouteEstimate

    revoked = False
    class Fixture:
        async def probe(self):
            nonlocal revoked
            revoked = True
            return HostProbe(adapter_id='fixture',status=HostProbeStatus.READY)
        async def execute(self, context):
            raise AssertionError('revoked work must not reach the adapter')

    def check():
        if revoked:
            raise ConfigurationError('fixture grant revoked during preparation')
        return None

    registry = ManagedHostRegistry()
    registry.register('fixture',Fixture())
    spec = ExecutorSpec(id='fixture',capability='fixture',kind='host_managed',resource_pool='pool',description='authority fixture',
        config={'adapter_id':'fixture','argv':['/fixture/host'],'instructions':'fixture'})
    with pytest.raises(ConfigurationError,match='revoked during preparation'):
        await ManagedHostExecutor(registry).execute(ExecutionContext(request=ActionRequest(capability='fixture'),
            spec=spec,estimate=RouteEstimate(),attempt=1,invocation_check=check))


@pytest.mark.parametrize('cleanup_fails', [False, True])
async def test_app_server_private_policy_snapshot_lifetime(monkeypatch, cleanup_fails):
    from aeep.hosts.codex_app_server import CodexAppServerAdapter

    worker = binding(schema_version='execution.worker.v2', seccomp_profile={'defaultAction':'SCMP_ACT_ERRNO','syscalls':[]})
    # This lifecycle fixture never launches its runtime; use an existing executable on every host.
    worker = worker.model_copy(update={'runtime': sys.executable})
    spec = ExecutorSpec(id='worker', capability='fixture', kind='host_managed', resource_pool='pool', description='policy lifecycle fixture',
        config={'adapter_id':'codex-app-server','argv':[worker.binary,'app-server'],'instructions':'fixture','managed_worker':worker.model_dump(mode='json')})

    async def cleanup(self, execution_id):
        assert execution_id
        if cleanup_fails:
            raise RuntimeError('cleanup unavailable')
        return True

    monkeypatch.setattr(ManagedWorkerBinding,'cleanup',cleanup)
    host = CodexAppServerAdapter.from_executor(spec,principal_salt=b'fixture-only')
    assert host._worker_security is not None
    snapshot = Path(host._worker_security.name)/'seccomp.json'
    assert snapshot.read_bytes() == worker.security_bytes()
    if cleanup_fails:
        with pytest.raises(RuntimeError,match='cleanup unavailable'):
            await host.close()
    else:
        await host.close()
    assert not snapshot.exists()
    wrong = spec.model_copy(deep=True)
    wrong.config['environment_allowlist']=['HOME']
    with pytest.raises(ConfigurationError,match='inherited'):
        CodexAppServerAdapter.from_executor(wrong,principal_salt=b'fixture-only')


@pytest.mark.parametrize('boundary', ['absent', 'verified_fixture', 'revoked'])
async def test_app_server_named_worker_profile_is_acknowledged_but_not_conformance(monkeypatch, boundary):
    from dataclasses import replace

    from test_codex_subscription_adapter import adapter, context

    from aeep.models import ManagedHostInvocation

    host = adapter()
    host._worker = binding(schema_version='execution.worker.v2',permissions_profile='aeep')
    original = host.transport.request
    calls = []

    async def request(method, params=None, **kwargs):
        calls.append(method)
        if method in {'skills/list','mcpServerStatus/list'}:
            return {'data':[]}
        if method == 'app/installed':
            return {'apps':[]}
        result = await original(method,params,**kwargs)
        if method == 'thread/start':
            assert params['permissions'] == 'aeep' and 'sandbox' not in params
            assert not any(key.startswith('permissions.') for key in params.get('config',{}))
            result.update(cwd='/workspace',approvalPolicy='never',approvalsReviewer='user',activePermissionProfile={'id':'aeep','extends':None})
        return result

    monkeypatch.setattr(host.transport,'request',request)
    ctx = context()
    config = ctx.config.model_copy(update={'invocation':ManagedHostInvocation()})
    def check():
        if boundary == 'revoked':
            raise ConfigurationError('environment verification unavailable: fixture review revoked')
        return 'a' * 64
    try:
        await host.probe()
        identity = await host.resolve_identity(config)
        raw = await host.execute(replace(ctx,config=config,expected_runtime_digest=identity,
            invocation_check=check if boundary != 'absent' else None))
        assert 'thread/start' in calls, raw.model_dump_json()
        if boundary == 'verified_fixture':
            # Callback injection tests protocol translation only, not real conformance.
            assert 'turn/start' in calls and raw.metadata['boundary_digest'] == 'a' * 64
            assert raw.metadata['model_turn_count'] == 1
        else:
            assert 'turn/start' not in calls
            assert raw.metadata['host_failure_code'] == 'environment_verification_unavailable'
            assert raw.metadata['model_turn_count'] == 0
    finally:
        await host.close()


@pytest.mark.skipif(not os.environ.get("AEEP_CONTAINER_RUNTIME"), reason="requires explicitly configured local container runtime")
@pytest.mark.real_container
async def test_real_managed_worker_uses_only_frozen_image(tmp_path):
    import asyncio

    from aeep.hosts.base import ManagedHostExecutionContext
    from aeep.models import ActionRequest, ExecutionStatus

    runtime, socket = os.environ["AEEP_CONTAINER_RUNTIME"], os.environ["AEEP_CONTAINER_SOCKET"]
    root = (await asyncio.to_thread(Path(__file__).resolve)).parents[1]
    launch = (root / "integrations/managed-worker/worker-launch").read_bytes()
    (tmp_path / "worker-launch").write_bytes(launch)
    (tmp_path / "worker-config.json").write_text("[]")
    # This local process is explicitly a transport fixture, not a Codex model.
    code = b'''#!/usr/bin/env python3
import json,os,pathlib,sys
sys.stdin.read()
pathlib.Path('/workspace/current.txt').write_text('current case')
result={'uid':os.getuid(),'cwd':os.getcwd(),'home':os.environ['HOME'],'has_repo':pathlib.Path('/repository').exists()}
for event in [{'type':'turn.started'}, {'type':'item.completed','item':{'id':'result','type':'agent_message','text':json.dumps(result)}}, {'type':'turn.completed','usage':{'input_tokens':0,'cached_input_tokens':0,'output_tokens':0}}]:
 print(json.dumps(event),flush=True)
'''
    (tmp_path / "fixture-codex").write_bytes(code)
    (tmp_path / "Dockerfile").write_text('FROM python:3.13-slim@sha256:8d9d0b8bcf6506481eae4907c18f5e3e7902e629f5f6d684f9e7c32e85e3ddf0\nCOPY worker-launch worker-config.json /opt/aeep/\nCOPY fixture-codex /opt/fixture-codex\nRUN chmod 755 /opt/aeep/worker-launch /opt/fixture-codex\n')
    iid = tmp_path / "image-id"
    process = await asyncio.create_subprocess_exec(runtime, "--host", f"unix://{socket}", "build", "--network=none", "--iidfile", str(iid), str(tmp_path), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
    _, error = await asyncio.wait_for(process.communicate(), 60)
    assert process.returncode == 0, error.decode()[-1000:]
    worker = ManagedWorkerBinding(worker_id="fixture", runtime=runtime, socket=socket,
        image=iid.read_text().strip(), platform="linux/arm64" if os.uname().machine == "arm64" else "linux/amd64",
        binary="/opt/fixture-codex", binary_sha256=hashlib.sha256(code).hexdigest(),
        configuration_digest=hashlib.sha256(b"[]").hexdigest(), dependencies_digest=hashlib.sha256(launch).hexdigest())
    spec = ExecutorSpec(id="fixture", capability="fixture", kind="host_managed", resource_pool="pool", description="real container transport fixture",
        config={"adapter_id":"codex-exec", "argv":[worker.binary], "instructions":"fixture", "exec_model":"fixture", "timeout_seconds":15, "managed_worker":worker.model_dump(mode="json")})
    host = CodexExecAdapter(spec)
    try:
        raw = await host.execute(ManagedHostExecutionContext(ActionRequest(capability="fixture"), "fixture", spec.managed_host_config(), 1, "real-worker-fixture", output_schema={"type":"object"}))
        assert raw.status == ExecutionStatus.SUCCESS, raw.model_dump_json()
        assert raw.output == {"uid":65534,"cwd":"/workspace","home":"/worker/home","has_repo":False}
        assert raw.metadata["worker_digest"] == worker.digest()
        assert not raw.stdout and not raw.stderr
    finally:
        await host.close()


async def test_artifact_read_failure_preserves_usage_and_cleans_worker(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from aeep.hosts.base import ManagedHostExecutionContext
    from aeep.hosts.codex_app_server import CodexAppServerAdapter
    from aeep.models import (
        ActionRequest,
        ExecutionStatus,
        ManagedHostExecutorConfig,
        RawExecution,
        ResourceVector,
    )

    host = CodexAppServerAdapter(argv=(sys.executable,), resource_id='pool', principal_salt=b'fixture')
    transfer = AsyncMock(return_value={'data': 'YWJj', 'sha256': 'a'*64, 'size': 3})
    cleanup = AsyncMock(return_value=True)
    host._worker = SimpleNamespace(digest=lambda: 'b'*64, artifact=transfer, cleanup=cleanup)
    host._worker_process_id = 'fixture-worker'
    host.transport.close = AsyncMock()
    raw = RawExecution(status=ExecutionStatus.SUCCESS, output={'completed': True}, resources=ResourceVector(output_tokens=7))
    monkeypatch.setattr(host, '_execute', AsyncMock(side_effect=lambda context: raw.model_copy(deep=True)))
    config = ManagedHostExecutorConfig(adapter_id='fixture', argv=[sys.executable], instructions='fixture', managed_worker={},
        artifact={'input_field':'workbook_b64','output_field':'workbook_b64','input_name':'input.xlsx','output_name':'output.xlsx'})
    ctx = ManagedHostExecutionContext(request=ActionRequest(capability='fixture'), instruction='fixture', config=config, attempt=1, attempt_id='fixture')
    result = await host.execute(ctx)
    assert result.output == {'workbook_b64':'YWJj'}
    assert result.metadata['artifact_bytes'] == 3
    transfer.side_effect = ConfigurationError('worker artifact transfer failed')
    result = await host.execute(ctx)
    assert result.error_type == 'WORKER_ARTIFACT_FAILED' and result.output is None
    assert result.resources.output_tokens == 7
    assert cleanup.await_count == 2


async def test_artifact_prompt_uses_paths_and_exec_start_rejects_transport():
    from aeep.executors.base import ExecutionContext
    from aeep.executors.managed_host import ManagedHostExecutor
    from aeep.hosts import HostProbe, HostProbeStatus, ManagedHostRegistry
    from aeep.hosts.base import ManagedHostExecutionContext
    from aeep.models import ActionRequest, ExecutionStatus, RawExecution

    class Fixture:
        async def probe(self):
            return HostProbe(adapter_id='fixture', status=HostProbeStatus.READY)
        async def execute(self, context):
            assert 'secret-encoded-input' not in context.instruction
            assert '/workspace/input.xlsx' in context.instruction
            assert '/workspace/output.xlsx' in context.instruction
            assert context.request.input['workbook_b64'] == 'secret-encoded-input'
            return RawExecution(status=ExecutionStatus.SUCCESS, output={})

    config = {'adapter_id':'fixture','argv':[binding().binary], 'instructions':'Task {input}; action {action}', 'managed_worker':binding().model_dump(),
        'artifact':{'input_field':'workbook_b64','output_field':'workbook_b64','input_name':'input.xlsx','output_name':'output.xlsx'}}
    spec = ExecutorSpec(id='fixture',capability='fixture',kind='host_managed',resource_pool='pool',description='fixture',config=config)
    registry = ManagedHostRegistry()
    registry.register('fixture', Fixture())
    request = ActionRequest(capability='fixture',input={'workbook_b64':'secret-encoded-input','task':'clean'})
    await ManagedHostExecutor(registry).execute(ExecutionContext(request=request,spec=spec,estimate=spec.estimate,attempt=1))
    spec.config['argv'] = [binding().binary]
    host = CodexExecAdapter(spec)
    handle = await host.start(ManagedHostExecutionContext(request=request,instruction='fixture',config=spec.managed_host_config(),attempt=1,attempt_id='fixture'))
    assert (await handle.task).error_type == 'ARTIFACT_TRANSPORT_UNSUPPORTED'
    await host.close()


def test_proxy_binding_is_explicit_and_registry_cannot_mix_worker_policies():
    from aeep.hosts.registry import ManagedHostRegistry

    with pytest.raises(ValueError,match='proxy requires'):
        binding(model_proxy_url='http://172.20.0.2:3128')
    with pytest.raises(ValueError):
        binding(network_id='a'*64,model_proxy_url='http://999.0.0.1:3128')
    worker = binding(network_id='a'*64,model_proxy_url='http://172.20.0.2:3128')
    assert 'HTTPS_PROXY=http://172.20.0.2:3128' in worker.argv(('app-server',),execution_id='fixture')
    other = worker.model_copy(update={'worker_id':'other','model_proxy_url':'http://172.20.0.3:3128'})
    with pytest.raises(ConfigurationError,match='differ'):
        validate_worker_pair(worker,other)
    route = ExecutorSpec(id='one',capability='fixture',kind='host_managed',resource_pool='pool',description='fixture',
        config={'adapter_id':'codex-app-server','argv':[worker.binary,'app-server'],'instructions':'fixture','managed_worker':worker.model_dump(mode='json')})
    changed = route.model_copy(deep=True)
    changed.id = 'two'
    changed.config['managed_worker'] = other.model_dump(mode='json')
    with pytest.raises(ConfigurationError,match='worker, protocol'):
        ManagedHostRegistry().configure([route,changed],principal_salt=b'fixture')


@pytest.mark.parametrize('input_present,boundary_changes', [(True,False),(False,False),(True,True)])
@pytest.mark.parametrize('tree', [False, True])
async def test_artifact_staging_precedes_turn_and_rechecks_authority(monkeypatch,input_present,boundary_changes,tree):
    from dataclasses import replace

    from test_codex_subscription_adapter import adapter, context

    from aeep.models import ManagedHostArtifact, ManagedHostInvocation

    host = adapter()
    host._worker = binding(schema_version='execution.worker.v2',permissions_profile='aeep')
    host._worker_process_id = 'controlled-fixture'
    transferred = []
    async def transfer(self,execution_id,**kwargs):
        transferred.append(kwargs)
        return {'data':'YWJj','sha256':'a'*64,'size':3}
    async def cleanup(self,execution_id):
        return True
    monkeypatch.setattr(ManagedWorkerBinding,'artifact',transfer)
    monkeypatch.setattr(ManagedWorkerBinding,'cleanup',cleanup)
    original = host.transport.request
    calls = []
    async def request(method,params=None,**kwargs):
        calls.append(method)
        if method in {'skills/list','mcpServerStatus/list'}:
            return {'data':[]}
        if method == 'app/installed':
            return {'apps':[]}
        if method == 'turn/start':
            if tree:
                assert transferred[0]['files'] == [{'path':'nested/current.txt','text':'current'}]
                assert params['outputSchema'] == ctx.output_schema
            else:
                assert transferred[0]['data'] == 'YWJj'
                assert params['outputSchema']['required'] == ['completed']
        result = await original(method,params,**kwargs)
        if method == 'thread/start':
            result.update(cwd='/workspace',approvalPolicy='never',approvalsReviewer='user',activePermissionProfile={'id':'aeep','extends':None})
        return result
    monkeypatch.setattr(host.transport,'request',request)
    ctx = context()
    ctx.request.input = {'workbook_b64':'YWJj'} if input_present else {}
    config = ctx.config.model_copy(update={'invocation':ManagedHostInvocation(),'artifact':ManagedHostArtifact(
        input_field='workbook_b64',output_field='workbook_b64',input_name='input.xlsx',output_name='output.xlsx')})
    if tree:
        ctx.request.input = {'files':[{'path':'nested/current.txt','text':'current'}]} if input_present else {}
        config = config.model_copy(update={'artifact':None, 'input_tree':'local_search_tree:1'})
    checks = 0
    def check():
        nonlocal checks
        checks += 1
        return ('b' if boundary_changes and checks > 1 else 'a')*64
    try:
        raw = await host.execute(replace(ctx,config=config,invocation_check=check))
        if input_present and not boundary_changes:
            assert raw.output == ({'characters':3} if tree else {'workbook_b64':'YWJj'}) and raw.metadata['model_turn_count'] == 1
            assert len(transferred) == (1 if tree else 2)
        else:
            assert 'turn/start' not in calls and raw.metadata['model_turn_count'] == 0
    finally:
        await host.close()


@pytest.mark.real_container
@pytest.mark.parametrize('explicit', [False, True])
def test_native_catalog_relay_in_offline_codex_worker(tmp_path, explicit):
    import json
    import re
    import runpy
    import subprocess
    import uuid

    from aeep.hosts import codex_metrics

    image = os.environ.get('AEEP_CATALOG_METRICS_IMAGE')
    definitions = os.environ.get('AEEP_INSPECTION_FIXTURE_SPECS')
    if not image or not definitions:
        pytest.skip('pinned catalog relay image and offline worker specs required')
    assert re.fullmatch(r'sha256:[a-f0-9]{64}', image)
    spec = ExecutorSpec.model_validate(json.loads(Path(definitions).read_text())[0])
    worker = ManagedWorkerBinding.model_validate(spec.config['managed_worker'])
    assert worker.credential_volume is None and worker.network_id is None and worker.model_proxy_url is None
    security = worker.prepare_security(tmp_path)
    assert security is not None
    # Exercise the real image entrypoint and adapter opt-in, without a thread,
    # authentication observation or model request. The protocol probe below
    # then checks native export and sandbox denial using a synthetic provider.
    import asyncio

    from aeep.hosts.codex_app_server import CodexAppServerAdapter

    collector_hash = hashlib.sha256(Path(codex_metrics.__file__).read_bytes()).hexdigest()
    frozen_worker = worker.model_copy(update={'image':image,
        'reviewed_files':dict(worker.reviewed_files or {}, **{codex_metrics.WORKER_PATH:collector_hash})})
    configured = spec.model_copy(deep=True)
    configured.config['managed_worker'] = frozen_worker.model_dump(mode='json')
    configured.config['adapter_options'] = dict(configured.config.get('adapter_options') or {},catalog_metrics=True)
    async def initialize_only():
        host = CodexAppServerAdapter.from_executor(configured,principal_salt=b'offline-fixture')
        try:
            await host.transport.start()
            assert host.transport.protocol_version
        finally:
            await host.close()
        assert host.transport.catalog_metrics is not None
        assert host.transport.catalog_metrics['collector_closed']
        assert host.transport.catalog_metrics['delivery_complete'] is False
    asyncio.run(initialize_only())
    program = runpy.run_path(str(Path(__file__).parent/'fixtures/codex_catalog_probe.py'))['PROGRAM']
    program = program.replace('ANALYTICS','True').replace('EXPLICIT',repr(explicit)).replace('enabled = True\\n','enabled = true\\n')
    name = 'aeep-catalog-fixture-'+uuid.uuid4().hex
    runtime = [worker.runtime,'--host','unix://'+worker.socket]
    command = [*runtime,'run','--name',name,'--rm','--pull','never','--network','none','--read-only',
        '--cap-drop','ALL','--security-opt','no-new-privileges','--security-opt','seccomp='+str(security),
        '--pids-limit','64','--memory','512m','--cpus','1','--user','65534:65534',
        '--tmpfs','/tmp:rw,nosuid,nodev,size=67108864',
        '--tmpfs','/workspace:rw,nosuid,nodev,size=67108864,uid=65534,gid=65534,mode=0700',
        '--entrypoint','python3',image,'-c',program]
    try:
        result = subprocess.run(command,capture_output=True,text=True,timeout=60)
        assert result.returncode==0, result.stderr
        value = json.loads(result.stdout)
        assert value['collector_sha256']==hashlib.sha256(Path(codex_metrics.__file__).read_bytes()).hexdigest()
        assert value['terminal_status']=='completed' and value['exit_code']==0 and value['stop']=='stdin_eof'
        assert value['model_calls']==0 and value['collector_access_from_sandbox']['outcome']=='denied'
        assert value['requests']['skill_description_in_request'] and value['requests']['full_skill_marker_seen']==explicit
        final = value['relay_snapshots'][-1]
        codex_metrics.validate_snapshot(final,'aeep-metrics-'+'f'*32)
        assert final['collector_closed'] and not final['delivery_complete'] and not final['rejected_batches']
        injections = [p for p in final['observations'] if p['name']=='codex.skill.injected']
        assert bool(injections)==explicit
        if explicit:
            assert injections[0]['skill_digest']==hashlib.sha256(b'synthetic').hexdigest()
            assert injections[0]['status']=='ok' and injections[0]['invoke_type']=='explicit'
    finally:
        subprocess.run([*runtime,'rm','-f',name],capture_output=True,timeout=20)
