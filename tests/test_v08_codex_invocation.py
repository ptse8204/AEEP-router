from __future__ import annotations

import copy
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_codex_subscription_adapter import adapter, context

from aeep.errors import ConfigurationError
from aeep.hosts.codex_invocation import (
    contract_digest,
    inventory,
    isolated_config,
    resolve_skill_name,
    verify_thread_inventory,
)
from aeep.models import ExecutionStatus, ManagedHostInvocation

pytestmark = pytest.mark.assessment_contract

TOOL = {
    "name": "parse",
    "description": "untrusted description",
    "inputSchema": {"type": "object"},
    "outputSchema": {"type": "object"},
}


def catalog(path):
    return {
        "skills": [{"name": "parse", "path": str(path), "enabled": True, "dependencies": None}],
        "apps": [{"id": "external", "callable": True}],
        "servers": [{"name": "parser", "tools": {"parse": TOOL}}],
    }


@pytest.mark.parametrize('supporting', [False, True])
def test_skill_recursion_uses_identity_not_ancestor_name(tmp_path, supporting):
    from aeep.models import ReviewedHostSkill

    path = tmp_path / 'aeep-parent' / 'parse' / 'SKILL.md'
    path.parent.mkdir(parents=True)
    path.write_text('A separate reviewed parser skill.')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    target = (ManagedHostInvocation(mode='turn', supporting_skills=[
        ReviewedHostSkill(name='parse', path=str(path), sha256=digest)]) if supporting else
        ManagedHostInvocation(mode='skill', skill_name='parse', skill_path=str(path), skill_sha256=digest))
    assert isolated_config(catalog(path), target)['skills.config'][0]['enabled'] is True

    bundled = Path(__file__).resolve().parents[1] / 'integrations/aeep/skills/assess-plugin/SKILL.md'
    path.write_bytes(bundled.read_bytes())
    renamed_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    renamed = (ManagedHostInvocation(mode='turn', supporting_skills=[
        ReviewedHostSkill(name='parse', path=str(path), sha256=renamed_digest)]) if supporting else
        ManagedHostInvocation(mode='skill', skill_name='parse', skill_path=str(path), skill_sha256=renamed_digest))
    with pytest.raises(ConfigurationError, match='recursive'):
        isolated_config(catalog(path), renamed)


def test_host_plugin_namespace_and_server_policy_use_exact_selected_path(tmp_path):
    path = tmp_path / "SKILL.md"
    path.write_text("reviewed parser")
    data = catalog(path)
    data["skills"][0]["name"] = "installed:parse"
    data["servers"][0]["pluginId"] = "parser@local"
    target = ManagedHostInvocation(mode="skill", skill_name="parse", skill_path=str(path), skill_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    resolved = resolve_skill_name(data, target)
    assert resolved.skill_name == "installed:parse"
    overrides = isolated_config(data, resolved)
    assert overrides['plugins."parser@local".mcp_servers.parser.enabled'] is False
    assert "mcp_servers.parser.enabled" not in overrides
    data["servers"].append({"name": "codex_apps", "tools": {"parse": TOOL}, "pluginId": None})
    overrides = isolated_config(data, resolved)
    assert overrides["features.apps"] is False
    assert "mcp_servers.codex_apps.enabled" not in overrides
    with pytest.raises(ConfigurationError, match="host-generated"):
        isolated_config(data, ManagedHostInvocation(mode="mcp_tool", server="codex_apps", tool="parse", tool_sha256=contract_digest(TOOL)))
    data["skills"][0]["path"] = str(tmp_path / "other" / "SKILL.md")
    with pytest.raises(ConfigurationError, match="absent"):
        resolve_skill_name(data, target)
    data["servers"][0]["pluginId"] = 'unsafe".key'
    with pytest.raises(ConfigurationError, match="plugin identity"):
        isolated_config(data, ManagedHostInvocation(mode="turn"))


async def test_preflight_protocol_failure_keeps_usage_and_a_safe_reason(monkeypatch):
    from aeep.hosts.codex_app_server import CodexProtocolError

    host = adapter()
    original = host.transport.request

    async def request(method, params=None, **kwargs):
        if method == "skills/list":
            raise CodexProtocolError("oversized App Server frame")
        return await original(method, params, **kwargs)

    monkeypatch.setattr(host.transport, "request", request)
    ctx = context()
    try:
        raw = await host.execute(replace(ctx, config=ctx.config.model_copy(update={"invocation": ManagedHostInvocation(mode="turn")})))
        assert raw.status == ExecutionStatus.FAILED
        assert raw.metadata["host_failure_code"] == "protocol_frame_limit"
        assert raw.metadata["model_turn_count"] == 0
        assert raw.resources.latency_ms >= 0
    finally:
        await host.close()


@pytest.mark.parametrize("mode", ["turn", "skill", "mcp_tool"])
@pytest.mark.parametrize("optional", [False, True])
async def test_supported_invocation_restricts_inventory_and_keeps_usage(
    tmp_path, monkeypatch, mode, optional
):
    path = tmp_path / "SKILL.md"
    path.write_text("Parse labeled data into JSON.")
    target = ManagedHostInvocation.model_validate(
        {
            "mode": mode,
            **({"exposure": "optional", "local_profile": "capable_local"} if optional and mode == "skill" else {}),
            **(
                {
                    "skill_name": "parse",
                    "skill_path": str(path),
                    "skill_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
                if mode == "skill"
                else {"server": "parser", "tool": "parse", "tool_sha256": contract_digest(TOOL)}
                if mode == "mcp_tool"
                else {}
            ),
        }
    )
    host = adapter()
    original = host.transport.request
    requests = []
    host.transport.max_message_bytes = 16384

    async def request(method, params=None, **kw):
        params = params or {}
        requests.append(method)
        if method == "skills/list":
            return {"data": [{"skills": catalog(path)["skills"], "errors": []}]}
        if method == "app/installed":
            return {"apps": [] if "threadId" in params else catalog(path)["apps"]}
        if method == "mcpServerStatus/list":
            return {
                "data": catalog(path)["servers"]
                if mode == "mcp_tool" or "threadId" not in params
                else []
            }
        if method == "thread/start":
            overrides = params["config"]
            assert overrides["features.multi_agent"] is False
            assert overrides["apps.external.enabled"] is False
            assert overrides["mcp_servers.parser.enabled"] is (mode == "mcp_tool")
        if method == "turn/start":
            assert mode != "mcp_tool"
            if mode == "skill" and optional:
                assert len(params["input"]) == 1
                assert not params["input"][0]["text"].startswith("$parse ")
            if mode == "skill" and not optional:
                assert params["input"][1] == {"type": "skill", "name": "parse", "path": str(path)}
                assert params["input"][0]["text"].startswith("$parse ")
        if method == "mcpServer/tool/call":
            assert params["arguments"] == {"text": "abc"}
            return {"structuredContent": {"characters": 3}}
        return await original(method, params, **kw)

    monkeypatch.setattr(host.transport, "request", request)
    ctx = context()
    ctx = replace(ctx, config=ctx.config.model_copy(update={"invocation": target}))
    try:
        result = await host.execute(ctx)
        assert result.status == ExecutionStatus.SUCCESS
        assert result.output == {"characters": 3}
        assert result.metadata["model_turn_count"] == int(mode != "mcp_tool")
        assert ("turn/start" in requests) is (mode != "mcp_tool")
        assert not {"plugin/list", "plugin/read", "config/read", "config/value/write"}.intersection(
            requests
        )
        assert (await host.inventory())["servers"][0]["tools"]["parse"]["outputSchema"] == {
            "type": "object"
        }
    finally:
        await host.close()


async def test_invocation_drift_recursion_and_unsupported_inventory_fail_closed(tmp_path):
    path = tmp_path / "SKILL.md"
    path.write_text("reviewed")
    original = catalog(path)
    skill = ManagedHostInvocation(
        mode="skill",
        skill_name="parse",
        skill_path=str(path),
        skill_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    target = ManagedHostInvocation(
        mode="mcp_tool", server="parser", tool="parse", tool_sha256=contract_digest(TOOL)
    )
    for mutation in (
        lambda c: c["servers"][0]["tools"]["parse"].update(description="changed"),
        lambda c: c["servers"][0]["tools"].update(aeep_assessment_start=TOOL),
        lambda c: c["servers"].clear(),
        lambda c: c["servers"][0].update(name="unsafe.key"),
        lambda c: c["apps"][0].update(id="unsafe.key"),
        lambda c: c["skills"][0].update(path="relative"),
    ):
        changed = copy.deepcopy(original)
        mutation(changed)
        with pytest.raises(ConfigurationError):
            isolated_config(changed, target)
    path.write_text("changed")
    with pytest.raises(ConfigurationError, match="changed"):
        isolated_config(original, skill)
    with pytest.raises(ValidationError):
        ManagedHostInvocation(
            mode="skill",
            skill_name="parse",
            skill_path=str(tmp_path / "auth.json"),
            skill_sha256="a" * 64,
        )
    with pytest.raises(ValidationError):
        ManagedHostInvocation(mode="turn", server="parser")
    with pytest.raises(ValidationError):
        ManagedHostInvocation(mode="mcp_tool", tool="parse")

    class Broken:
        async def request(self, method, params=None, **kwargs):
            if method == "skills/list":
                return {"data": []}
            if method == "app/installed":
                return {"apps": []}
            return {"data": original["servers"]}

    broken = Broken()
    with pytest.raises(ConfigurationError, match="environment verification unavailable"):
        await verify_thread_inventory(broken, "t", ManagedHostInvocation())
    assert (await inventory(broken, None))["servers"]
    for reply in ({}, {"data": [], "nextCursor": "repeat"}, {"data": [None]}):

        async def request(method, params=None, reply=reply, **kwargs):
            return reply if method == "mcpServerStatus/list" else {"data": [], "apps": []}

        broken.request = request
        with pytest.raises(ConfigurationError):
            await inventory(broken, None)


async def test_paginated_advertisements_support_tools_without_claiming_enforcement():
    from aeep.hosts.codex_invocation import advertised_tools
    from aeep.models import ReviewedHostTool

    target = ManagedHostInvocation(mode="turn", supporting_tools=(ReviewedHostTool(server="parser", tool="parse", sha256=contract_digest(TOOL)),))

    class Pages:
        async def request(self, method, params=None, **kwargs):
            if method == "app/installed":
                return {"apps": []}
            if "cursor" not in params:
                return {"data": [], "nextCursor": "page-2"}
            return {"data": [{"name": "parser", "tools": {"parse": TOOL}}]}

    assert (await advertised_tools(Pages(), "thread"))[("parser", "parse")] == TOOL
    assert await verify_thread_inventory(Pages(), "thread", target) is None
    with pytest.raises(ConfigurationError, match="environment verification unavailable"):
        await verify_thread_inventory(Pages(), "thread", ManagedHostInvocation())


async def test_scoped_model_trial_requires_more_than_an_empty_catalog(monkeypatch):
    host = adapter()
    original = host.transport.request
    methods = []

    async def request(method, params=None, **kwargs):
        methods.append(method)
        if method in {"skills/list", "mcpServerStatus/list"}:
            return {"data": []}
        if method == "app/installed":
            return {"apps": []}
        return await original(method, params, **kwargs)

    monkeypatch.setattr(host.transport, "request", request)
    ctx = context()
    config = ctx.config.model_copy(update={"invocation": ManagedHostInvocation()})
    try:
        identity = await host.resolve_identity(config)
        result = await host.execute(replace(ctx, config=config, expected_runtime_digest=identity))
        assert result.status == ExecutionStatus.FAILED
        assert result.metadata["host_failure_code"] == "environment_verification_unavailable"
        assert result.metadata["model_turn_count"] == 0
        assert result.metadata["host_available_tools"] == "unknown"
        assert "turn/start" not in methods
    finally:
        await host.close()


def test_reviewed_background_skills_keep_native_catalog_bounded(tmp_path):
    from aeep.models import ReviewedHostSkill

    path = tmp_path / 'SKILL.md'
    path.write_text('reviewed background capability')
    reviewed = ReviewedHostSkill(name='parse',path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    target = ManagedHostInvocation(mode='turn',local_profile='capable_local',native_catalog=True,supporting_skills=[reviewed])
    data = catalog(path)
    assert isolated_config(data,target)['skills.config'] == [{'path':str(tmp_path),'enabled':True}]
    with pytest.raises(ConfigurationError,match='changed'):
        isolated_config(data,target,reviewed_worker_files={})
    path.write_text('changed')
    with pytest.raises(ConfigurationError,match='changed'):
        isolated_config(data,target)
    assert isolated_config(data,target,reviewed_worker_files={str(path):reviewed.sha256})['skills.config'][0]['enabled']
    data['skills'] = []
    with pytest.raises(ConfigurationError,match='absent'):
        isolated_config(data,target)
    with pytest.raises(ValidationError,match='distinct'):
        ManagedHostInvocation(mode='turn',supporting_skills=[reviewed,reviewed])
    assert 'supporting_skills' not in ManagedHostInvocation().model_dump()


async def test_protocol_binding_is_explicit_and_probe_does_not_claim_untried_methods():
    from aeep.hosts.codex_app_server import AppServerOptions

    host = adapter()
    try:
        assert not host.transport.options.experimental_api
        probe = await host.probe()
        assert probe.status.value == 'ready'
        assert 'model/list' in probe.supported_features
        assert 'turn/start' not in probe.supported_features
        ctx = context()
        result = await host.execute(replace(ctx,config=ctx.config.model_copy(update={'reasoning_efforts':('unavailable',)})))
        assert result.error_type == 'NO_COMPATIBLE_MODEL'
    finally:
        await host.close()
    host = adapter()
    host.transport.options = AppServerOptions(expected_user_agent='reviewed-different-version')
    try:
        assert (await host.probe()).status.value == 'unsupported'
    finally:
        await host.close()


async def test_registered_process_policy_and_pinned_model_cannot_drift():
    from aeep.models import ManagedHostModelConstraints

    host = adapter()
    ctx = context()
    try:
        host._configured_process = ctx.config.process_binding()
        changed = ctx.config.model_copy(update={'adapter_options':{'experimental_api':True}})
        assert (await host.execute(replace(ctx,config=changed))).error_type == 'CONFIGURATION_REJECTED'
        assert not host.transport._started
        pinned = ctx.config.model_copy(update={'model_constraints':ManagedHostModelConstraints(allowed_model_ids=('absent',))})
        assert (await host.execute(replace(ctx,config=pinned))).error_type == 'NO_COMPATIBLE_MODEL'
    finally:
        await host.close()


def test_worker_candidate_never_falls_back_to_coordinator_skill(tmp_path):
    path = tmp_path / 'SKILL.md'
    path.write_text('coordinator copy')
    target = ManagedHostInvocation(mode='skill',skill_name='parse',skill_path=str(path),skill_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    with pytest.raises(ConfigurationError,match='changed'):
        isolated_config(catalog(path),target,reviewed_worker_files={})


def catalog_payload(scope, *, skill='fixture-skill', value='1'):
    return {'resourceMetrics': [{'resource': {'attributes': [{'key':'account','value':{'stringValue':'PRIVATE_ACCOUNT_CANARY'}}]},
        'scopeMetrics': [{'metrics': [{'name':'codex.skill.injected', 'sum': {'dataPoints':[{
            'asInt':value, 'attributes':[{'key':key,'value':{'stringValue':item}} for key,item in
                {'service_name':scope,'skill':skill,'status':'ok','invoke_type':'implicit','task':'PRIVATE_TASK_CANARY'}.items()]}]}}]}]}]}


def test_catalog_metrics_minimize_bound_and_preserve_unknowns():
    import copy
    import hashlib

    from aeep.hosts.codex_metrics import MAX_BODY, Metrics, snapshot, validate_snapshot

    scope = 'aeep-metrics-' + 'a'*32
    metrics = Metrics(scope)
    body = catalog_payload(scope)
    metrics.accept(json.dumps(body).encode())
    metrics.accept(json.dumps(body).encode())
    assert metrics.value['batches'] == 2 and len(metrics.value['observations']) == 1
    point = metrics.value['observations'][0]
    assert point['skill_digest'] == hashlib.sha256(b'fixture-skill').hexdigest()
    assert point['value'] == 1 and metrics.value['delivery_complete'] is False
    assert 'PRIVATE' not in json.dumps(metrics.value) and 'fixture-skill' not in json.dumps(metrics.value)
    other = Metrics(scope)
    other.accept(json.dumps(catalog_payload('other-attempt')).encode())
    assert other.value['observations'] == []
    for bad in ('NaN', True, -1, 10**1000, 'nan', 1_000_001):
        before = copy.deepcopy(metrics.value)
        with pytest.raises(ValueError):
            metrics.accept(json.dumps(catalog_payload(scope,value=bad)).encode())
        assert metrics.value == before
    for raw in (b'{"resourceMetrics":[],"resourceMetrics":[]}', b'{"resourceMetrics":NaN}'):
        with pytest.raises(ValueError):
            metrics.accept(raw)
    with pytest.raises(ValueError, match='bound'):
        metrics.accept(b'x'*(MAX_BODY+1))
    assert metrics.value['overflow']
    for changes in ({'delivery_complete':True}, {'scope':'wrong'}, {'extra':'data'}, {'observations':[{'name':'unknown'}]}):
        with pytest.raises(ValueError):
            validate_snapshot(dict(snapshot(scope),**changes),scope)
    for name in ('enabled_total','kept_total','truncated'):
        data = {'resourceMetrics':[{'scopeMetrics':[{'metrics':[{'name':'codex.thread.skills.'+name,
            'histogram':{'dataPoints':[{'sum':2,'count':'1','attributes':[
                {'key':'service_name','value':{'stringValue':scope}},
                {'key':'catalog_surface','value':{'stringValue':'thread_context'}}]}]}}]}]}]}
        other.accept(json.dumps(data).encode())
    assert len(other.value['observations']) == 3
    for i in range(256):
        if i < 253:
            other.accept(json.dumps(catalog_payload(scope,skill=f'skill-{i}')).encode())
            # Test the point bound independently of the separate batch ceiling.
            other.value['batches'] = 0
        else:
            with pytest.raises(ValueError,match='observations'):
                other.accept(json.dumps(catalog_payload(scope,skill=f'skill-{i}')).encode())
    assert len(other.value['observations']) == 256


async def test_catalog_metrics_transport_rejects_unconfigured_misbound_and_conflicting_snapshots():
    from test_codex_subscription_adapter import adapter

    from aeep.hosts.codex_app_server import CodexProtocolError
    from aeep.hosts.codex_metrics import NOTIFICATION, Metrics, snapshot

    host = adapter()
    scope = 'aeep-metrics-'+'b'*32
    transport = host.transport
    try:
        with pytest.raises(CodexProtocolError,match='unconfigured'):
            await transport._dispatch({'method':NOTIFICATION,'params':snapshot(scope)})
        transport.metrics_scope = scope
        with pytest.raises(CodexProtocolError,match='invalid'):
            await transport._dispatch({'method':NOTIFICATION,'params':snapshot('wrong')})
        metrics = Metrics(scope)
        metrics.accept(json.dumps(catalog_payload(scope)).encode())
        await transport._dispatch({'method':NOTIFICATION,'params':metrics.value})
        with pytest.raises(CodexProtocolError,match='conflicting'):
            await transport._dispatch({'method':NOTIFICATION,'params':snapshot(scope)})
        assert transport.catalog_metrics['delivery_complete'] is False
    finally:
        await host.close()


async def test_catalog_metrics_worker_binding_is_exact_and_metadata_never_implies_discovery(monkeypatch):
    import asyncio
    import hashlib
    import sys
    from dataclasses import replace
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from test_codex_subscription_adapter import adapter, context
    from test_v08_managed_workers import binding

    from aeep.hosts import codex_metrics
    from aeep.hosts.codex_app_server import CodexAppServerAdapter
    from aeep.models import ExecutionStatus, ExecutorSpec, RawExecution

    worker = binding().model_copy(update={"runtime": sys.executable})
    spec = ExecutorSpec(id='metrics',capability='fixture',kind='host_managed',resource_pool='pool',description='metrics fixture',
        config={'adapter_id':'codex-app-server','argv':[worker.binary,'app-server'],'instructions':'fixture',
                'adapter_options':{'catalog_metrics':True},'managed_worker':worker.model_dump(mode='json')})
    with pytest.raises(ConfigurationError,match='exact reviewed'):
        CodexAppServerAdapter.from_executor(spec,principal_salt=b'fixture')
    worker.reviewed_files = {codex_metrics.WORKER_PATH:hashlib.sha256(await asyncio.to_thread(Path(codex_metrics.__file__).read_bytes)).hexdigest()}
    spec.config['managed_worker'] = worker.model_dump(mode='json')
    configured = CodexAppServerAdapter.from_executor(spec,principal_salt=b'fixture')
    assert any(arg.startswith('--aeep-catalog-metrics=') for arg in configured.transport.argv)
    configured._worker = None  # No container was launched by construction.
    await configured.close()
    spec.config.pop('managed_worker')
    spec.config['argv'] = [sys.executable,'app-server']
    with pytest.raises(ConfigurationError,match='exact reviewed'):
        CodexAppServerAdapter.from_executor(spec,principal_salt=b'fixture')
    host = adapter()
    host._worker = SimpleNamespace(digest=lambda:'a'*64,cleanup=AsyncMock(return_value=True))
    host._worker_process_id = 'fixture'
    host.transport.metrics_scope = 'aeep-metrics-'+'c'*32
    async def execute(ctx):
        metric = codex_metrics.Metrics(host.transport.metrics_scope)
        metric.accept(json.dumps(catalog_payload(host.transport.metrics_scope)).encode())
        await host.transport._dispatch({'method':codex_metrics.NOTIFICATION,'params':metric.value})
        return RawExecution(status=ExecutionStatus.SUCCESS,output={})
    monkeypatch.setattr(host,'_execute',execute)
    host.transport.close = AsyncMock()
    handle = await host.start(replace(context(),attempt_id='metrics-attempt'))
    events = [event async for event in host.events(handle)]
    raw = await handle.task
    assert raw.metadata['capability_discovery'] == {'exposed':None,'retrieved':None,'invoked':None}
    assert raw.metadata['catalog_metrics']['observations'] and not raw.metadata['catalog_metrics']['collector_closed']
    assert any(event.kind=='message.received' for event in events)
    assert raw.resources.latency_ms > 0


@pytest.mark.parametrize('fault', ['none', 'bad_export', 'forged_frame', 'malformed_frame'])
@pytest.mark.skipif(not hasattr(os, 'killpg'), reason='worker relay requires POSIX process groups')
def test_catalog_metrics_real_http_and_stdio_relay(tmp_path, fault):
    import subprocess
    import sys

    from aeep.hosts.codex_metrics import NOTIFICATION, validate_snapshot

    scope = 'aeep-metrics-'+'d'*32
    body = catalog_payload(scope)
    child = tmp_path/'host.py'
    child.write_text('''import http.client,json,re,sys,urllib.parse
option=next(arg for arg in sys.argv if arg.startswith('otel.metrics_exporter='))
endpoint=json.loads(re.search(r'endpoint=("[^"]+")',option).group(1))
url=urllib.parse.urlsplit(endpoint)
connection=http.client.HTTPConnection(url.hostname,url.port,timeout=2)
body=BODY
connection.request('POST','/v1/metrics',body=body,headers={'Content-Type':'application/json'})
response=connection.getresponse(); status=response.status; response.read(); connection.close()
print(FRAME,flush=True)
'''.replace('BODY',repr(b'{"invalid":NaN}' if fault=='bad_export' else json.dumps(body).encode()))
       .replace('FRAME',repr('not json' if fault=='malformed_frame' else json.dumps({'method':NOTIFICATION,'params':{}}) if fault=='forged_frame' else json.dumps({'method':'fixture/status','params':{'ok':True}}))))
    from aeep.hosts import codex_metrics
    # Match worker-launch: import the standalone stdlib relay, not all of AEEP.
    program = 'import faulthandler,socket,sys; faulthandler.dump_traceback_later(5); socket.getfqdn=lambda *a: sys.exit(99); sys.path.insert(0,sys.argv.pop(1)); from codex_metrics import relay; raise SystemExit(relay(sys.argv[1:-1],sys.argv[-1]))'
    relay_directory = str(Path(codex_metrics.__file__).parent)
    result = subprocess.run([sys.executable,'-c',program,relay_directory,sys.executable,str(child),scope],input=b'',capture_output=True,timeout=10)
    frames = [json.loads(line) for line in result.stdout.splitlines()]
    observations = [validate_snapshot(frame['params'],scope) for frame in frames if frame['method']==NOTIFICATION]
    assert observations and observations[-1]['collector_closed'] and not observations[-1]['delivery_complete']
    if fault in {'forged_frame','malformed_frame'}:
        assert result.returncode != 0
    else:
        assert result.returncode == 0
        assert frames[-2]['method']=='fixture/status'
    if fault=='bad_export':
        assert observations[-1]['rejected_batches']==1 and observations[-1]['observations']==[]
    else:
        assert observations[-1]['batches']==1 and observations[-1]['observations']
    assert b'PRIVATE_' not in result.stdout and b'fixture-skill' not in result.stdout


@pytest.mark.skipif(not hasattr(os, 'killpg'), reason='worker relay requires POSIX process groups')
def test_catalog_metrics_relay_termination_cleans_up_child(tmp_path):
    import os
    import subprocess
    import sys

    scope = 'aeep-metrics-'+'e'*32
    child = tmp_path/'host.py'
    child.write_text('import json,os,time\nprint(json.dumps({"method":"ready","params":{"pid":os.getpid()}}),flush=True)\ntime.sleep(60)\n')
    from aeep.hosts import codex_metrics
    # Match worker-launch: import the standalone stdlib relay, not all of AEEP.
    program = 'import faulthandler,socket,sys; faulthandler.dump_traceback_later(5); socket.getfqdn=lambda *a: sys.exit(99); sys.path.insert(0,sys.argv.pop(1)); from codex_metrics import relay; raise SystemExit(relay(sys.argv[1:-1],sys.argv[-1]))'
    relay_directory = str(Path(codex_metrics.__file__).parent)
    process = subprocess.Popen([sys.executable,'-c',program,relay_directory,sys.executable,str(child),scope],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    try:
        ready = json.loads(process.stdout.readline())
        pid = ready['params']['pid']
        process.terminate()
        output,_ = process.communicate(timeout=10)
        assert process.returncode==143
        final = json.loads(output.splitlines()[-1])['params']
        assert final['collector_closed'] and not final['delivery_complete']
        with pytest.raises(ProcessLookupError):
            os.kill(pid,0)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
