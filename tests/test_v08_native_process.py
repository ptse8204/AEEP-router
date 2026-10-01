"""The stronger native boundary is opt-in, source-bound and never retries."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from aeep.assessment.onboarding import reference_spec
from aeep.errors import ConfigurationError
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.hosts.codex_native_process import SINGLE_PROCESS_GUARD, execute_single_process
from aeep.hosts.codex_sandbox import NativeSandboxConfig, native_backend_digest
from aeep.models import ActionRequest, ExecutionStatus, ExecutorKind

pytestmark = pytest.mark.assessment_lifecycle
BINARY = Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')


def boundary(root: Path) -> NativeSandboxConfig:
    data = root / 'data'
    data.mkdir(exist_ok=True)
    python = Path(sys.executable).resolve()
    return NativeSandboxConfig(binary=str(BINARY), binary_sha256='sha256:' + hashlib.sha256(BINARY.read_bytes()).hexdigest(),
        project_root=str(root), read_roots=[str(Path(sys.prefix).resolve())], write_roots=[str(data)],
        single_process=True, python_binary=str(python), python_sha256='sha256:' + hashlib.sha256(python.read_bytes()).hexdigest())


@pytest.mark.skipif(sys.platform != 'darwin' or not BINARY.exists(), reason='installed native Mac runtime required')
@pytest.mark.parametrize('program,stdin,expected', [
    ('import json,sys; print(json.dumps(json.load(sys.stdin)))', b'{"name":"\xe9\x98\xbf"}', {'name': '阿'}),
    ('import json,sys; print(json.dumps({"empty":sys.stdin.read()==""}))', None, {'empty': True}),
    ('import os,resource,json; r={};\ntry:\n os.fork(); r["fork"]=False\nexcept OSError: r["fork"]=True\ntry:\n os.posix_spawn("/usr/bin/true",["/usr/bin/true"],{});r["spawn"]=False\nexcept OSError:r["spawn"]=True\ntry:\n resource.setrlimit(resource.RLIMIT_NPROC,(1,1));r["raise"]=False\nexcept (OSError,ValueError):r["raise"]=True\nprint(json.dumps(r))', None, {'fork': True, 'spawn': True, 'raise': True}),
])
async def test_native_single_process_io_and_no_fork(tmp_path, program, stdin, expected):
    raw = await execute_single_process(boundary(tmp_path.resolve()), [sys.executable, '-I', '-c', program], {}, stdin, 5, 10000)
    assert not raw.timed_out and not raw.stream_error, raw
    assert raw.exit_code == 0, raw.stderr
    assert json.loads(raw.stdout) == expected


@pytest.mark.skipif(sys.platform != 'darwin' or not BINARY.exists(), reason='installed native Mac runtime required')
async def test_native_single_process_timeout_and_normal_error(tmp_path):
    b = boundary(tmp_path.resolve())
    effect = Path(b.write_roots[0]) / 'effect'
    program = 'import os,time,pathlib,sys;\ntry:os.setsid()\nexcept OSError:pass\ntime.sleep(1);pathlib.Path(sys.argv[1]).write_text("bad")'
    raw = await execute_single_process(b, [sys.executable, '-I', '-c', program, str(effect)], {}, None, .4, 10000)
    assert raw.timed_out
    await asyncio.sleep(1.1)
    assert not effect.exists()
    raw = await execute_single_process(b, [sys.executable, '-I', '-c', 'raise SystemExit(7)'], {}, None, 5, 10000)
    assert raw.exit_code == 7 and not raw.stream_error


def test_single_process_missing_runtime_and_drift_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr('aeep.hosts.codex_sandbox.sys.platform', 'darwin')
    b = NativeSandboxConfig(binary=str(tmp_path / 'codex'), binary_sha256='sha256:'+'a'*64,
                           project_root=str(tmp_path), single_process=True)
    with pytest.raises(ConfigurationError, match='pinned Python'):
        b.validate_single_process()
    ordinary = b.model_copy(update={'single_process': False})
    assert native_backend_digest(ordinary) != native_backend_digest(b)


@pytest.mark.skipif(sys.platform != 'darwin' or not BINARY.exists(), reason='installed native Mac runtime required')
async def test_command_single_process_reuses_output_and_rejects_payload_limit(tmp_path):
    b = boundary(tmp_path.resolve())
    spec = reference_spec('csv').model_copy(update={'kind': ExecutorKind.COMMAND, 'config': {
        'argv': [sys.executable, '-I', '-c', 'import json,sys; print(json.dumps(json.load(sys.stdin)))'],
        'argv_literal': True, 'stdin_json': True, 'native_sandbox': b.model_dump(mode='json'), 'output': {'type': 'json'}}})
    context = ExecutionContext(request=ActionRequest(capability=spec.capability,input={'text':'阿','delimiter':','}),spec=spec,estimate=spec.estimate,attempt=1)
    raw = await CommandExecutor().execute(context)
    assert raw.status == ExecutionStatus.SUCCESS and raw.output == context.request.input
    assert raw.metadata['enforcement_backend_digest'] == native_backend_digest(b)
    context.request.input['text'] = 'x' * 1_048_577
    with pytest.raises(ConfigurationError, match='1 MiB'):
        await CommandExecutor().execute(context)


@pytest.mark.skipif(sys.platform != 'darwin' or not BINARY.exists(), reason='installed native Mac runtime required')
async def test_native_single_process_cancellation_and_output_limit(tmp_path):
    b = boundary(tmp_path.resolve())
    effect = Path(b.write_roots[0]) / 'effect'
    task = asyncio.create_task(execute_single_process(b, [sys.executable, '-I', '-c',
        'import pathlib,sys,time;time.sleep(1);pathlib.Path(sys.argv[1]).write_text("bad")', str(effect)], {}, None, 5, 1000))
    await asyncio.sleep(.4)
    task.cancel()
    raw = await task
    assert raw.timed_out
    await asyncio.sleep(1.1)
    assert not effect.exists()
    raw = await execute_single_process(b, [sys.executable, '-I', '-c', 'print("x"*10000)'], {}, None, 5, 100)
    assert raw.output_truncated and raw.error_type == 'NATIVE_OUTPUT_LIMIT'
    assert len(raw.stdout) <= 100


@pytest.mark.skipif(sys.platform != 'darwin' or not BINARY.exists(), reason='installed native Mac runtime required')
async def test_native_guard_early_eof_and_runtime_drift(tmp_path):
    from aeep.hosts.codex_app_server import AppServerOptions, CodexAppServerTransport
    b = boundary(tmp_path.resolve())
    transport = CodexAppServerTransport((str(BINARY), 'app-server', '--stdio', *b.permission_overrides()),
        cwd=b.project_root, options=AppServerOptions(experimental_api=True), executable_sha256=b.binary_sha256)
    try:
        result = await transport.request('command/exec', {'command': [sys.executable, '-I', '-c', SINGLE_PROCESS_GUARD, '{}', '/usr/bin/true'],
            'permissionProfile': 'aeep-native-task', 'cwd': b.project_root, 'timeoutMs': 1000})
        assert result['exitCode'] != 0 and 'incomplete native command handshake' in result['stderr']
    finally:
        await transport.close()
    changed = b.model_copy(update={'python_sha256': 'sha256:'+'0'*64})
    with pytest.raises(ConfigurationError, match='Python changed'):
        await execute_single_process(changed, [sys.executable, '-I', '-c', 'print(1)'], {}, None, 5, 100)


@pytest.mark.skipif(not os.environ.get('AEEP_NATIVE_WORKBOOK_PYTHON'), reason='explicit installed workbook Python required')
def test_native_single_process_workbook_reference(tmp_path):
    import runpy
    import subprocess
    workbook_python = Path(os.environ['AEEP_NATIVE_WORKBOOK_PYTHON']).resolve()
    prefix = subprocess.check_output([str(workbook_python), '-I', '-c', 'import sys;print(sys.prefix)'], text=True).strip()
    b = boundary(tmp_path.resolve()).model_copy(update={'python_binary': str(workbook_python),
        'python_sha256': 'sha256:' + hashlib.sha256(workbook_python.read_bytes()).hexdigest(), 'read_roots': [str(Path(prefix).resolve())]})
    assets = Path(__file__).resolve().parents[1] / 'integrations' / 'assessment-runtime'
    source = (assets / 'workbook_program.py').read_text()
    program = "import json,sys;ns={'__name__':'reference'};exec("+repr(source)+",ns);print(json.dumps(ns['reference'](json.load(sys.stdin))))"
    fixture = json.loads((assets / 'workbook-grader-fixtures.json').read_text())[0]
    raw = asyncio.run(execute_single_process(b, [str(workbook_python), '-I', '-c', program],
        {'TMPDIR': b.write_roots[0]}, json.dumps(fixture['input']).encode(), 10, 200000))
    assert raw.exit_code == 0 and not raw.stream_error, raw
    output = json.loads(raw.stdout)
    grade = runpy.run_path(str(assets / 'workbook_grader.py'))['grade']
    assert grade({'input':fixture['input'],'output':output,'expected':fixture['expected']})


@pytest.mark.skipif(sys.platform != 'darwin' or not BINARY.exists(), reason='installed native Mac runtime required')
@pytest.mark.parametrize('death', ['coordinator', 'native_server'])
def test_native_owned_connection_death_and_native_server_failure(tmp_path, death):
    import subprocess
    import time

    import psutil
    root = tmp_path.resolve()
    b = boundary(root)
    marker, effect = root/'data'/'started', root/'data'/'effect'
    code = r'''import asyncio,json,sys
from pathlib import Path
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from datetime import timedelta
from aeep.assessment.onboarding import reference_spec
from aeep.assessment.repository import AssessmentRepository
from aeep.economic.prepared import executor_fingerprint
from aeep.models import Manifest,TaskScope,ActionRequest,ActionConstraints,PolicyConfig,SideEffect,ExecutorKind,utc_now
from aeep.router import Router
b=NativeSandboxConfig.model_validate(json.loads(sys.argv[1]))
program="import os,pathlib,sys,time;pathlib.Path(sys.argv[1]).write_text(str(os.getpid()));time.sleep(1);pathlib.Path(sys.argv[2]).write_text('synthetic');time.sleep(2)"
async def run():
 root=Path(b.project_root)
 spec=reference_spec('csv').model_copy(update={'kind':ExecutorKind.COMMAND,'side_effect':SideEffect.WRITE,'idempotent':False,'config':{'argv':[sys.executable,'-I','-c',program,sys.argv[2],sys.argv[3]],'argv_literal':True,'native_sandbox':b.model_dump(mode='json'),'timeout_seconds':5}})
 manifest=Manifest(database=str(root/'.aeep'/'state.db'),executors=[spec],policies={'write':PolicyConfig(name='write',constraints=ActionConstraints(max_side_effect=SideEffect.WRITE))})
 router=Router(manifest,manifest_path=root/'aeep.json')
 repo=AssessmentRepository(router.store)
 scope=TaskScope(scope_id='crash',project_root=str(root),executor_fingerprints={spec.id:executor_fingerprint(spec)},approval_ceiling=SideEffect.WRITE,max_attempts=1,max_attempt_seconds=5,expires_at=utc_now()+timedelta(minutes=2))
 repo.review(repo.put('task_scope',scope.scope_id,scope));router.bind_task_scope(scope.scope_id)
 outcome=await router.execute(ActionRequest(capability=spec.capability,policy='write',input={'text':'a\n1','delimiter':','},constraints=ActionConstraints(max_side_effect=SideEffect.WRITE)),approved_side_effect=SideEffect.WRITE)
 receipt=outcome.receipts[-1]
 print(json.dumps({'stream_error':receipt.error_type=='NATIVE_COMMAND_PROTOCOL_FAILED','cleanup_incomplete':receipt.metadata['process_cleanup']['cleanup_incomplete']}))
 await router.close()
asyncio.run(run())
'''
    repo = Path(__file__).resolve().parents[1]
    process = subprocess.Popen([sys.executable,'-c',code,b.model_dump_json(),str(marker),str(effect)],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={'PATH':os.environ.get('PATH',''),'PYTHONPATH':str(repo/'src')})
    owner = psutil.Process(process.pid)
    handles = [owner]
    try:
        deadline = time.monotonic()+6
        while not marker.exists() and process.poll() is None and time.monotonic()<deadline:
            time.sleep(.02)
        assert marker.exists(), process.communicate(timeout=2)
        handles.extend(owner.children(recursive=True))
        command_pid = int(marker.read_text())
        assert any(h.pid==command_pid for h in handles)
        if death=='coordinator':
            owner.kill()
        else:
            servers = [h for h in handles if 'app-server' in h.cmdline()]
            assert len(servers)==1
            servers[0].kill()
        stdout, stderr = process.communicate(timeout=4)
        import sqlite3
        db = sqlite3.connect(root/'.aeep'/'state.db')
        states = db.execute('select state,count(*) from execution_attempts group by state').fetchall()
        db.close()
        assert states == [('INVOKING' if death=='coordinator' else 'INDETERMINATE', 1)]
        time.sleep(1.2)
        if death=='coordinator':
            assert not effect.exists()
        else:
            # The retained handshake identity repairs native-server SIGKILL cleanup.
            assert not effect.exists()
            assert json.loads(stdout)=={'stream_error':True,'cleanup_incomplete':False}, stderr
    finally:
        for handle in reversed(handles):
            try:
                if handle.is_running() and handle.status()!=psutil.STATUS_ZOMBIE:
                    handle.kill()
            except psutil.NoSuchProcess:
                pass
        psutil.wait_procs(handles,timeout=2)
        assert not any(h.is_running() and h.status()!=psutil.STATUS_ZOMBIE for h in handles)


@pytest.mark.skipif(sys.platform != 'darwin' or not BINARY.exists(), reason='installed native Mac runtime required')
async def test_native_single_process_read_only_profile_needs_no_scratch(tmp_path):
    b = boundary(tmp_path.resolve()).model_copy(update={'write_roots': []})
    program = 'import pathlib,sys,json;\ntry:pathlib.Path(sys.argv[1]).write_text("bad");denied=False\nexcept PermissionError:denied=True\nprint(json.dumps({"write_denied":denied}))'
    raw = await execute_single_process(b, [sys.executable, '-I', '-c', program, str(tmp_path/'data'/'denied')], {}, None, 5, 1000)
    assert raw.exit_code == 0 and json.loads(raw.stdout) == {'write_denied': True}


@pytest.mark.skipif(sys.platform != 'darwin' or not BINARY.exists(), reason='installed native Mac runtime required')
async def test_native_single_process_effective_filesystem_and_network(tmp_path):
    root = tmp_path.resolve()
    b = boundary(root)
    allowed, denied = root/'data'/'allowed', root/'denied'
    allowed.write_text('synthetic')
    denied.write_text('synthetic')
    program = ('import pathlib,socket,sys,json; r={"allowed":pathlib.Path(sys.argv[1]).read_text()=="synthetic"};\n'
        'try:pathlib.Path(sys.argv[2]).read_text();r["read_denied"]=False\n'
        'except PermissionError:r["read_denied"]=True\n'
        'try:s=socket.socket();s.bind(("127.0.0.1",0));r["network_denied"]=False\n'
        'except PermissionError:r["network_denied"]=True\n'
        'print(json.dumps(r))')
    raw = await execute_single_process(b, [sys.executable, '-I', '-c', program, str(allowed), str(denied)], {}, None, 5, 1000)
    assert raw.exit_code == 0 and json.loads(raw.stdout) == {'allowed':True,'read_denied':True,'network_denied':True}
