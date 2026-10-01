from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import json
import os
import stat
import sys
import threading
import tomllib
from datetime import timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aeep.assessment.models import content_digest
from aeep.assessment.onboarding import reference_spec
from aeep.assessment.repository import AssessmentRepository
from aeep.cli import app
from aeep.economic.prepared import executor_fingerprint
from aeep.errors import ConfigurationError
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.hosts.codex_app_server import CodexAppServerTransport
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from aeep.mcp.server import AEEPToolService
from aeep.models import (
    ActionConstraints,
    ActionRequest,
    ExecutionStatus,
    ExecutorKind,
    Manifest,
    PolicyConfig,
    SideEffect,
    TaskScope,
    utc_now,
)
from aeep.router import Router
from aeep.tasks import TaskActivation, activate, change_state, inspect, require_activation

pytestmark = pytest.mark.assessment_lifecycle


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    monkeypatch.setattr(NativeSandboxConfig, 'argv', lambda self, command: command)
    native = NativeSandboxConfig(binary=str(root/'fixture'), binary_sha256='sha256:'+'a'*64,
        project_root=str(root))
    spec = reference_spec('csv').model_copy(update={'kind': ExecutorKind.COMMAND, 'config': {
        'argv':[sys.executable,'-I','-c','import json; print(json.dumps({"records":[]}))'],
        'argv_literal':True,'output':{'type':'json'},'native_sandbox':native.model_dump(mode='json'),'timeout_seconds':1}})
    manifest = root/'aeep.json'
    manifest.write_text(Manifest(database=str(root/'.aeep'/'state.db'), executors=[spec]).model_dump_json())
    router = Router.from_manifest(manifest)
    repo = AssessmentRepository(router.store)
    scope = TaskScope(scope_id='journey', project_root=str(root), executor_fingerprints={spec.id:executor_fingerprint(spec)},
        max_attempts=5,max_attempt_seconds=1,expires_at=utc_now()+timedelta(minutes=5))
    repo.review(repo.put('task_scope',scope.scope_id,scope))
    router.store.close()
    return manifest, scope


async def test_project_activation_pause_resume_user_edit_and_uninstall_preserve_evidence(project):
    manifest, scope = project
    router = Router.from_manifest(manifest)
    peer = Router.from_manifest(manifest)
    try:
        first = activate(router,scope.scope_id)
        second = activate(peer,scope.scope_id)
        service = AEEPToolService(router,profile='task',task_activation=first.activation_id)
        other = AEEPToolService(peer,profile='task',task_activation=second.activation_id)
        args = {'text':'a\n1','delimiter':','}
        result = await service.call('aeep_csv',args)
        receipt_id = result['structuredContent']['receipts'][0]['receipt_id']
        change_state(router,first.activation_id,'pause')
        assert (await service.call('aeep_csv',args))['isError']
        assert not (await other.call('aeep_csv',args))['isError']
        change_state(router,first.activation_id,'resume')
        assert not (await service.call('aeep_csv',args))['isError']
        status = inspect(router,first.activation_id)
        assert status['attempts_used']==3 and status['attempts_remaining']==2
        path = Path(status['owned_files'][0])
        await asyncio.to_thread(path.write_text, 'user edit')
        with pytest.raises(ConfigurationError,match='conflict'):
            change_state(router,first.activation_id,'rollback')
        assert await asyncio.to_thread(path.read_text)=='user edit' and not inspect(router,first.activation_id)['reviewed']
        # An operator can restore the exact applied overlay and retry cleanup.
        await asyncio.to_thread(path.write_text, first.model_dump_json(indent=2)+'\n')
        assert change_state(router,first.activation_id,'uninstall')['overlay']=='absent'
        assert router.store.get_receipt(receipt_id) is not None
        assert require_activation(peer,second.activation_id)==second
        assert manifest.exists()
    finally:
        await router.close()
        await peer.close()


def test_unsaved_in_process_manifest_does_not_advertise_broken_host_entry(project):
    manifest, scope = project
    loaded = Manifest.model_validate_json(manifest.read_text())
    manifest.unlink()
    router = Router(loaded, manifest_path=manifest)
    try:
        activation = activate(router, scope.scope_id)
        status = inspect(router, activation.activation_id)
        assert status['codex_mcp_entry'] == 'in_process_only'
        assert status['project_host_config'] is None
        assert len(status['owned_files']) == 1
        assert not (manifest.parent / '.codex' / 'config.toml').exists()
        assert require_activation(router, activation.activation_id) == activation
        assert change_state(router, activation.activation_id, 'uninstall')['overlay'] == 'absent'
    finally:
        router.store.close()


async def test_project_codex_mcp_entries_preserve_existing_config_and_other_sessions(project):
    manifest, scope = project
    config = manifest.parent / '.codex' / 'config.toml'
    config.parent.mkdir()
    original = '[mcp_servers.other]\ncommand = "other"\n'
    config.write_text(original)
    config.chmod(0o640)
    router = Router.from_manifest(manifest)
    try:
        first = activate(router, scope.scope_id)
        second = activate(router, scope.scope_id)
        parsed = tomllib.loads(config.read_text())['mcp_servers']
        first_name, second_name = 'aeep_' + first.activation_id, 'aeep_' + second.activation_id
        assert set(parsed) == {'other', first_name, second_name}
        assert parsed[first_name]['args'][:3] == ['-I', '-m', 'aeep']
        assert parsed[first_name]['args'][-4:] == ['--task-activation', first.activation_id,
            '--manifest', str(manifest)]
        assert stat.S_IMODE(config.stat().st_mode) == 0o640
        config.write_text(config.read_text() + '\n[unrelated]\nchanged = true\n')
        assert require_activation(router, second.activation_id) == second
        change_state(router, first.activation_id, 'uninstall')
        assert first_name not in tomllib.loads(config.read_text())['mcp_servers']
        assert second_name in tomllib.loads(config.read_text())['mcp_servers']
        assert require_activation(router, second.activation_id) == second
        change_state(router, second.activation_id, 'uninstall')
        assert config.read_text() == original + '\n[unrelated]\nchanged = true\n'
        assert stat.S_IMODE(config.stat().st_mode) == 0o640
        status = inspect(router, second.activation_id)
        assert status['retained_artifacts'] == [str(manifest.parent / '.aeep' / 'task-profiles' / 'codex-config.lock')]
        assert await asyncio.to_thread(Path(status['retained_artifacts'][0]).exists)
    finally:
        await router.close()


async def test_project_codex_mcp_entry_accepts_unicode_manifest_path(tmp_path, monkeypatch):
    root = (tmp_path / 'project-😀').resolve()
    root.mkdir()
    monkeypatch.setattr(NativeSandboxConfig, 'argv', lambda self, command: command)
    native = NativeSandboxConfig(binary=str(root / 'fixture'), binary_sha256='sha256:' + 'a' * 64,
        project_root=str(root))
    spec = reference_spec('csv').model_copy(update={'kind': ExecutorKind.COMMAND, 'config': {
        'argv': [sys.executable, '-I', '-c', 'import json; print(json.dumps({"records":[]}))'],
        'argv_literal': True, 'output': {'type': 'json'}, 'native_sandbox': native.model_dump(mode='json'),
        'timeout_seconds': 1}})
    manifest = root / 'aeep.json'
    manifest.write_text(Manifest(database=str(root / '.aeep' / 'state.db'), executors=[spec]).model_dump_json())
    router = Router.from_manifest(manifest)
    try:
        repo = AssessmentRepository(router.store)
        scope = TaskScope(scope_id='unicode', project_root=str(root),
            executor_fingerprints={spec.id: executor_fingerprint(spec)}, max_attempts=1,
            max_attempt_seconds=1, expires_at=utc_now() + timedelta(minutes=5))
        repo.review(repo.put('task_scope', scope.scope_id, scope))
        activation = activate(router, scope.scope_id)
        config = root / '.codex' / 'config.toml'
        parsed = tomllib.loads(config.read_text())
        assert parsed['mcp_servers']['aeep_' + activation.activation_id]['args'][-1] == str(manifest)
        assert require_activation(router, activation.activation_id) == activation
        change_state(router, activation.activation_id, 'uninstall')
    finally:
        await router.close()


async def test_project_codex_mcp_entry_edits_conflict_and_repeat_uninstall_is_safe(project):
    manifest, scope = project
    router = Router.from_manifest(manifest)
    try:
        activation = activate(router, scope.scope_id)
        config = manifest.parent / '.codex' / 'config.toml'
        changed = config.read_text() + f'\n[mcp_servers.aeep_{activation.activation_id}.env]\nEXTRA = "user"\n'
        config.write_text(changed)
        with pytest.raises(ConfigurationError, match='entry changed'):
            change_state(router, activation.activation_id, 'uninstall')
        assert config.read_text() == changed
        assert not inspect(router, activation.activation_id)['reviewed']
        config.write_text(config.read_text().split('\n[mcp_servers.aeep_')[0] + '\n')
        assert change_state(router, activation.activation_id, 'uninstall')['codex_mcp_entry'] == 'absent'
        assert change_state(router, activation.activation_id, 'uninstall')['overlay'] == 'absent'
    finally:
        await router.close()


def test_concurrent_project_codex_activations_keep_every_entry(project):
    manifest, scope = project
    def start(_):
        router = Router.from_manifest(manifest)
        try:
            return activate(router, scope.scope_id).activation_id
        finally:
            router.store.close()
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        ids = list(pool.map(start, range(12)))
    config = manifest.parent / '.codex' / 'config.toml'
    names = tomllib.loads(config.read_text())['mcp_servers']
    assert set(names) == {'aeep_' + identity for identity in ids}
    router = Router.from_manifest(manifest)
    try:
        for identity in ids:
            assert require_activation(router, identity).activation_id == identity
            change_state(router, identity, 'uninstall')
        assert not config.exists()
    finally:
        router.store.close()


def test_project_codex_install_and_uninstall_do_not_invert_locks(project, monkeypatch):
    manifest, scope = project
    router = Router.from_manifest(manifest)
    first = activate(router, scope.scope_id)
    entered, release = threading.Event(), threading.Event()
    from aeep.hosts import codex_project
    replace = codex_project._replace_codex_bytes
    def held_replace(path, before, after):
        entered.set()
        assert release.wait(5)
        return replace(path, before, after)
    monkeypatch.setattr(codex_project, '_replace_codex_bytes', held_replace)
    def install():
        peer = Router.from_manifest(manifest)
        try:
            return activate(peer, scope.scope_id).activation_id
        finally:
            peer.store.close()
    def uninstall():
        peer = Router.from_manifest(manifest)
        try:
            return change_state(peer, first.activation_id, 'uninstall')
        finally:
            peer.store.close()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            added = pool.submit(install)
            assert entered.wait(5)
            removed = pool.submit(uninstall)
            release.set()
            second = added.result(timeout=5)
            assert removed.result(timeout=5)['codex_mcp_entry'] == 'absent'
        assert require_activation(router, second).activation_id == second
    finally:
        release.set()
        router.store.close()


def test_project_codex_non_table_mcp_config_fails_cleanly(project):
    manifest, scope = project
    config = manifest.parent / '.codex' / 'config.toml'
    config.parent.mkdir()
    config.write_text('mcp_servers = "user value"\n')
    router = Router.from_manifest(manifest)
    try:
        with pytest.raises(ConfigurationError, match='not a table'):
            activate(router, scope.scope_id)
        assert config.read_text() == 'mcp_servers = "user value"\n'
    finally:
        router.store.close()


@pytest.mark.native_boundary
@pytest.mark.skipif(not os.getenv('AEEP_NATIVE_CODEX'), reason='explicit native launcher required')
async def test_actual_codex_project_mcp_discovery_call_pause_and_uninstall(tmp_path, monkeypatch):
    root = await asyncio.to_thread(tmp_path.resolve)
    git = await asyncio.create_subprocess_exec('git', 'init', '-q', str(root))
    assert await git.wait() == 0
    await asyncio.to_thread((root / 'aeep.py').write_text, 'raise RuntimeError("project shadow imported")\n')
    binary = await asyncio.to_thread(Path(os.environ['AEEP_NATIVE_CODEX']).resolve)
    binary_bytes = await asyncio.to_thread(binary.read_bytes)
    native = NativeSandboxConfig(binary=str(binary), binary_sha256='sha256:' + hashlib.sha256(binary_bytes).hexdigest(),
        project_root=str(root), read_roots=[str(await asyncio.to_thread(Path(sys.prefix).resolve))])
    program = 'import json,sys; json.load(sys.stdin); print(json.dumps({"records":[{"name":"Ada"}]}))'
    spec = reference_spec('csv').model_copy(update={'kind': ExecutorKind.COMMAND, 'config': {
        'argv': [sys.executable, '-I', '-c', program], 'stdin_json': True, 'argv_literal': True,
        'output': {'type': 'json'}, 'native_sandbox': native.model_dump(mode='json'), 'timeout_seconds': 5}})
    manifest = root / 'aeep.json'
    manifest.write_text(Manifest(database=str(root / '.aeep' / 'state.db'), executors=[spec]).model_dump_json())
    router = Router.from_manifest(manifest)
    scope = TaskScope(scope_id='host-check', project_root=str(root), executor_fingerprints={spec.id: executor_fingerprint(spec)},
        max_attempts=1, max_attempt_seconds=5, expires_at=utc_now() + timedelta(minutes=5))
    repo = AssessmentRepository(router.store)
    repo.review(repo.put('task_scope', scope.scope_id, scope))
    activation = activate(router, scope.scope_id)
    host_home = root / 'codex-home'
    host_home.mkdir()
    (host_home / 'config.toml').write_text('[projects.' + json.dumps(str(root)) + ']\ntrust_level = "trusted"\n')
    monkeypatch.setenv('CODEX_HOME', str(host_home))
    transport = CodexAppServerTransport((str(binary), 'app-server'), environment_allowlist=('CODEX_HOME', 'PATH', 'HOME'),
        cwd=str(root), request_timeout=20)
    try:
        server = 'aeep_' + activation.activation_id
        status = await transport.request('mcpServerStatus/list', {'limit': 20, 'detail': 'toolsAndAuthOnly'})
        assert [item['name'] for item in status['data']] == [server]
        assert set(status['data'][0]['tools']) == {'aeep_csv'}
        thread = await transport.request('thread/start', {'ephemeral': True, 'cwd': str(root),
            'approvalPolicy': 'never', 'sandbox': 'read-only'})
        call = {'threadId': thread['thread']['id'], 'server': server, 'tool': 'aeep_csv',
            'arguments': {'text': 'name\nAda\n', 'delimiter': ','}}
        first = (await transport.request('mcpServer/tool/call', call))['structuredContent']
        assert first['ok'] and first['output'] == {'records': [{'name': 'Ada'}]}
        assert len(first['receipts']) == 1 and router.store.get_receipt(first['receipts'][0]['receipt_id'])
        assert first['changes_verified'] is None
        change_state(router, activation.activation_id, 'pause')
        paused = await transport.request('mcpServer/tool/call', call)
        assert paused['isError'] and 'paused' in paused['structuredContent']['error']
        change_state(router, activation.activation_id, 'resume')
        exhausted = await transport.request('mcpServer/tool/call', call)
        assert exhausted['isError'] and 'allowance exhausted' in exhausted['structuredContent']['error']
    finally:
        await transport.close()
        result = change_state(router, activation.activation_id, 'uninstall')
        assert result['attempts_used'] == 1 and result['codex_mcp_entry'] == 'absent'
        assert not (root / '.codex' / 'config.toml').exists()
        await router.close()


@pytest.mark.parametrize('finish', ['timeout', 'success'])
async def test_native_command_cleans_observed_detached_children(project, finish):
    manifest, _ = project
    router = Router.from_manifest(manifest)
    effect = manifest.parent / 'detached-effect'
    child = 'import pathlib,sys,time; time.sleep(0.8); pathlib.Path(sys.argv[1]).write_text("effect")'
    parent = ('import subprocess,sys,time; subprocess.Popen([sys.executable,"-I","-c",sys.argv[1],sys.argv[2]],'
              'start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); '
              'time.sleep('+('2' if finish == 'timeout' else '0.2')+'); print("{}")')
    spec = router.registry.all()[0].model_copy(deep=True)
    spec.config['argv'] = [sys.executable, '-I', '-c', parent, child, str(effect)]
    spec.config['timeout_seconds'] = 0.3 if finish == 'timeout' else 2
    try:
        raw = await CommandExecutor().execute(ExecutionContext(ActionRequest(capability=spec.capability), spec, spec.estimate, 1))
        assert raw.status == (ExecutionStatus.TIMEOUT if finish == 'timeout' else ExecutionStatus.FAILED)
        if finish == 'success':
            assert raw.error_type == 'BACKGROUND_PROCESS_REJECTED'
        assert not raw.metadata['process_cleanup']['cleanup_incomplete']
        await asyncio.sleep(1)
        assert not await asyncio.to_thread(effect.exists)
    finally:
        await router.close()


async def test_activation_crash_intent_missing_overlay_and_changed_manifest_fail_closed(project, monkeypatch):
    manifest, scope = project
    router = Router.from_manifest(manifest)
    repo = AssessmentRepository(router.store)
    try:
        record = TaskActivation(scope_digest=content_digest(scope),manifest_digest=content_digest(router.manifest),manifest_path=str(manifest))
        repo.put('task_activation',record.activation_id,record)
        with pytest.raises(ConfigurationError,match='incomplete'):
            require_activation(router,record.activation_id)
        assert change_state(router,record.activation_id,'rollback')['overlay']=='absent'
        active = activate(router,scope.scope_id)
        original_bytes = await asyncio.to_thread(manifest.read_bytes)
        await asyncio.to_thread(manifest.write_bytes, original_bytes+b'\n')
        with pytest.raises(ConfigurationError,match='manifest changed'):
            require_activation(router,active.activation_id)
        await asyncio.to_thread(manifest.write_bytes, original_bytes)
        router.manifest.default_policy='local'
        with pytest.raises(ConfigurationError,match='manifest changed'):
            require_activation(router,active.activation_id)
        assert change_state(router,active.activation_id,'uninstall')['overlay']=='absent'
    finally:
        await router.close()


async def test_activation_storage_failure_retains_unreviewed_intent_for_cleanup(project, monkeypatch):
    manifest, scope = project
    router = Router.from_manifest(manifest)

    def full_disk(_descriptor):
        raise OSError('fixture storage full')

    try:
        with monkeypatch.context() as patch:
            patch.setattr('aeep.tasks.os.fsync', full_disk)
            with pytest.raises(OSError, match='storage full'):
                activate(router, scope.scope_id)
        row = router.store._connection.execute("SELECT id FROM assessment_records WHERE kind='task_activation'").fetchone()
        assert row is not None
        with pytest.raises(ConfigurationError, match='incomplete'):
            require_activation(router, row[0])
        assert change_state(router, row[0], 'uninstall')['overlay'] == 'absent'
        assert AssessmentRepository(router.store).get('task_scope', scope.scope_id)
    finally:
        await router.close()


def test_lifecycle_cli_and_replacement_are_operator_only(project):
    manifest, scope = project
    runner = CliRunner()
    base=['task','-m',str(manifest)]
    first=runner.invoke(app,[*base,'activate',scope.scope_id])
    assert first.exit_code==0,first.output
    original=json.loads(first.stdout)
    replaced=runner.invoke(app,[*base,'activate',scope.scope_id,'--replace',original['activation_id']])
    assert replaced.exit_code==0,replaced.output
    current=json.loads(replaced.stdout)
    inspected=runner.invoke(app,[*base,'control','inspect',original['activation_id']])
    assert not json.loads(inspected.stdout)['reviewed']
    for operation in ('pause','resume','rollback','uninstall'):
        result=runner.invoke(app,[*base,'control',operation,current['activation_id']])
        assert result.exit_code==0,result.output
    assert json.loads(result.stdout)['accounting_retained']
    rejected = runner.invoke(app, [*base, 'control', 'resume', current['activation_id']])
    assert rejected.exit_code != 0 and 'configuration changed or is absent' in rejected.output
    assert 'Traceback' not in rejected.output


async def test_stop_cancels_only_the_activation_owned_command(project):
    manifest, original = project
    router = Router.from_manifest(manifest)
    started = asyncio.Event()
    spec = router.registry.all()[0]
    spec.config['argv']=[sys.executable,'-u','-c','import time; print("ready"); time.sleep(30)']
    spec.config['timeout_seconds']=30
    router.registry.replace(spec)
    scope = original.model_copy(update={'scope_id':'stop', 'max_attempt_seconds':30,
        'executor_fingerprints':{spec.id:executor_fingerprint(spec)}})
    repo = AssessmentRepository(router.store)
    repo.review(repo.put('task_scope',scope.scope_id,scope))
    executor = router._executor_for(ExecutorKind.COMMAND,spec)
    assert isinstance(executor,CommandExecutor)
    executor.stdout_observer=lambda _: started.set()
    activation=activate(router,scope.scope_id)
    service=AEEPToolService(router,profile='task',task_activation=activation.activation_id)
    call=asyncio.create_task(service.call('aeep_csv',{'text':'a\n1','delimiter':','}))
    unrelated = await asyncio.create_subprocess_exec(sys.executable, '-c', 'import time; time.sleep(30)')
    try:
        await asyncio.wait_for(started.wait(),3)
        change_state(router,activation.activation_id,'stop')
        # A rapid resume must not erase a stop already issued for this operation.
        change_state(router,activation.activation_id,'resume')
        result=await asyncio.wait_for(call,3)
        assert result['isError'] and result['structuredContent']['status']=='timeout'
        assert inspect(router,activation.activation_id)['attempts_used']==1
        assert unrelated.returncode is None
    finally:
        call.cancel()
        if unrelated.returncode is None:
            unrelated.terminate()
        await unrelated.wait()
        await router.close()


@pytest.mark.parametrize("ceiling", [SideEffect.READ, SideEffect.WRITE])
async def test_project_mcp_launch_uses_only_reviewed_scope_ceiling(project, ceiling):
    manifest_path, original_scope = project
    manifest = Manifest.model_validate_json(manifest_path.read_text())
    write_root = manifest_path.parent / "task-output"
    write_root.mkdir()
    effect = write_root / "owned-write-effect"
    config = dict(manifest.executors[0].config)
    if ceiling == SideEffect.WRITE:
        config["argv"] = [sys.executable, "-I", "-c",
            "import pathlib,json,sys; pathlib.Path(sys.argv[1]).write_text('written'); print(json.dumps({'records':[]}))",
            str(effect)]
        config["native_sandbox"]["write_roots"] = [str(write_root)]
    spec = manifest.executors[0].model_copy(update={"side_effect": ceiling, "config": config})
    manifest = manifest.model_copy(update={"executors": [spec], "policies": {
        "balanced": PolicyConfig(name="balanced", constraints=ActionConstraints(max_side_effect=ceiling))}})
    manifest_path.write_text(manifest.model_dump_json())
    router = Router.from_manifest(manifest_path)
    scope = original_scope.model_copy(update={"scope_id": "approval-launch", "approval_ceiling": ceiling,
        "executor_fingerprints": {spec.id: executor_fingerprint(spec)}})
    repo = AssessmentRepository(router.store)
    repo.review(repo.put("task_scope", scope.scope_id, scope))
    try:
        activation = activate(router, scope.scope_id)
        entry = tomllib.loads((manifest_path.parent / ".codex/config.toml").read_text())["mcp_servers"]["aeep_" + activation.activation_id]
        args = entry["args"]
        launch_ceiling = SideEffect(args[args.index("--approve") + 1])
        assert launch_ceiling == ceiling
        service = AEEPToolService(router, profile="task", task_activation=activation.activation_id,
            approved_side_effect=launch_ceiling)
        result = await service.call("aeep_csv", {"text": "name\nAda\n", "delimiter": ","})
        assert result["structuredContent"].get("ok"), result
        attempts = router.store._connection.execute("SELECT count(*) FROM execution_attempts").fetchone()[0]
        for argument in ("approve", "approval_ceiling", "approved_side_effect"):
            rejected = await service.call("aeep_csv", {"text": "a\n1", "delimiter": ",", argument: "financial"})
            assert rejected["isError"]
        assert router.store._connection.execute("SELECT count(*) FROM execution_attempts").fetchone()[0] == attempts
        assert service.approved_side_effect == ceiling
        assert effect.exists() == (ceiling == SideEffect.WRITE)
        legacy = AEEPToolService(router, profile="assessment")
        assert legacy.approved_side_effect == SideEffect.READ
        if ceiling == SideEffect.WRITE:
            assert (await legacy.call("aeep_csv", {"text": "a\n1", "delimiter": ","}))["isError"]
        repo.review(activation.scope_digest, revoke=True)
        assert (await service.call("aeep_csv", {"text": "a\n1", "delimiter": ","}))["isError"]
        assert router.store._connection.execute("SELECT count(*) FROM execution_attempts").fetchone()[0] == attempts
    finally:
        await router.close()


@pytest.mark.parametrize('ceiling', [SideEffect.READ, SideEffect.WRITE])
async def test_project_codex_approval_rules_match_scoped_task_tools_and_preserve_user_edits(project, ceiling):
    manifest, original_scope = project
    # An unrelated configured task capability must not receive a rule.
    definition = Manifest.model_validate_json(manifest.read_text())
    definition.executors.append(reference_spec('text'))
    manifest.write_text(definition.model_dump_json())
    router = Router.from_manifest(manifest)
    try:
        scope = original_scope.model_copy(update={'scope_id': 'approval-' + ceiling.value,
                                                  'approval_ceiling': ceiling})
        repo = AssessmentRepository(router.store)
        repo.review(repo.put('task_scope', scope.scope_id, scope))
        config = manifest.parent / '.codex' / 'config.toml'
        config.parent.mkdir()
        config.write_text('model = "user-model"\n[mcp_servers.user]\ncommand = "user-tool"\n')
        activation = activate(router, scope.scope_id)
        service = AEEPToolService(router, profile='task', task_activation=activation.activation_id)
        expected = {tool['name'] for tool in service.list_tools()}
        name = 'aeep_' + activation.activation_id
        entry = tomllib.loads(config.read_text())['mcp_servers'][name]
        assert expected == {'aeep_csv'}
        assert entry['tools'] == {tool: {'approval_mode': 'approve'} for tool in expected}
        assert 'default_tools_approval_mode' not in entry
        assert entry['args'][entry['args'].index('--approve') + 1] == ceiling.value
        assert all(not tool.startswith('aeep_assessment_') for tool in entry['tools'])
        # A user edit outside the exact owned block survives ordinary rollback.
        config.write_text(config.read_text() + '\n[user_preferences]\nkeep = true\n')
        assert change_state(router, activation.activation_id, 'uninstall')['codex_mcp_entry'] == 'absent'
        remaining = tomllib.loads(config.read_text())
        assert remaining['model'] == 'user-model'
        assert remaining['mcp_servers'] == {'user': {'command': 'user-tool'}}
        assert remaining['user_preferences'] == {'keep': True}
    finally:
        await router.close()


async def test_project_codex_tool_approval_user_edit_conflicts_with_rollback(project):
    manifest, scope = project
    router = Router.from_manifest(manifest)
    try:
        activation = activate(router, scope.scope_id)
        config = manifest.parent / '.codex' / 'config.toml'
        changed = config.read_text().replace('approval_mode = "approve"', 'approval_mode = "prompt"')
        config.write_text(changed)
        with pytest.raises(ConfigurationError, match='entry changed'):
            change_state(router, activation.activation_id, 'uninstall')
        assert config.read_text() == changed
        assert not inspect(router, activation.activation_id)['reviewed']
    finally:
        await router.close()

