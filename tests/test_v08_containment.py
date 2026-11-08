from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from conftest import python_spec

from aeep.assessment.container_worker import run
from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import AssessmentEnvironment, content_digest
from aeep.errors import ConfigurationError
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutionStatus, ExecutorKind, ExecutorSpec

pytestmark = pytest.mark.assessment_boundary


def controlled_context():
    spec = python_spec("csv", "aeep.assessment.recipes:reference_csv")
    return ExecutionContext(
        request=ActionRequest(
            capability=spec.capability,
            input={"text": "id,name,note\n1,A,hello\n", "delimiter": ","},
        ),
        spec=spec,
        estimate=spec.estimate,
        attempt=1,
        attempt_id="attempt",
    )


def test_stable_reader_rejects_replaced_parent_and_fifo(tmp_path):
    import os

    from aeep.artifact_store import _read_stable_file, _safe_local_path

    if os.open not in os.supports_dir_fd or not hasattr(os, "mkfifo"):
        pytest.skip("requires POSIX directory descriptors and FIFO support")
    root = tmp_path.resolve()
    parent = root / "tree"
    parent.mkdir()
    (parent / "data.txt").write_text("approved")
    selected = _safe_local_path(root, "tree/data.txt")
    parent.rename(root / "old")
    parent.symlink_to(root / "old", target_is_directory=True)
    with pytest.raises(ConfigurationError):
        _read_stable_file(selected, 100)
    fifo = root / "pipe"
    os.mkfifo(fifo)
    with pytest.raises(ConfigurationError, match="regular file"):
        _read_stable_file(fifo, 100)


def environment(tmp_path, runtime):
    return AssessmentEnvironment(
        environment_id="test",
        kind="container",
        identity={"test": "offline"},
        container_image="local/aeep@sha256:" + "a" * 64,
        container_runtime=str(runtime),
        container_socket=str(tmp_path / "docker.sock"),
        read_only_roots=[str(tmp_path)],
    )


def test_container_scratch_changes_only_the_reviewed_mount_limit(tmp_path):
    old = environment(tmp_path, tmp_path / "docker")
    legacy = old.model_dump(mode="json")
    assert "container_tmpfs_mb" not in legacy
    assert content_digest(AssessmentEnvironment.model_validate(legacy)) == content_digest(old)

    larger = AssessmentEnvironment.model_validate(legacy | {"container_tmpfs_mb": 160})
    assert content_digest(larger) != content_digest(old)
    argv, name = ContainerExecutor(AssessmentEnvironment.model_validate(legacy)).command(controlled_context())
    mount = argv.index("--tmpfs") + 1
    assert argv[mount] == "/tmp:rw,noexec,nosuid,nodev,size=32m"
    argv[mount] = "/tmp:rw,noexec,nosuid,nodev,size=160m"
    assert ContainerExecutor(larger).command(controlled_context()) == (argv, name)

    for updates in (
        {"container_tmpfs_mb": 31},
        {"container_tmpfs_mb": 1025, "memory_mb": 2048},
        {"container_tmpfs_mb": "160"},
        {"container_tmpfs_mb": 257},
        {"container_tmpfs_mb": 160, "kind": "trusted_local"},
    ):
        with pytest.raises(ValueError):
            AssessmentEnvironment.model_validate(legacy | updates)


@pytest.mark.skipif(sys.platform == "win32", reason="local Unix container runtime")
async def test_container_uses_bounded_argv_and_existing_adapters(tmp_path):
    # Protocol fixture only: this does not certify Docker's OS isolation.
    runtime = tmp_path / "docker-fixture"
    runtime.write_text(
        f"#!{sys.executable}\n"
        + """import sys, json
if 'run' in sys.argv:
    payload=json.load(sys.stdin)
    assert payload['request']['input']['text'].startswith('id,name')
    assert '--network' in sys.argv and 'none' in sys.argv
    assert '--read-only' in sys.argv and '--pull=never' in sys.argv
    print(json.dumps({'status':'success','output':{'records':[{'id':'1','name':'A','note':'hello'}]},'resources':{'cpu_ms':999},'metadata':{'claimed':'not observed'}}))
"""
    )
    runtime.chmod(0o755)
    ctx = controlled_context()
    contained = ContainerExecutor(environment(tmp_path, runtime))
    argv, name = contained.command(ctx)
    assert name.startswith("aeep-") and name == contained.command(ctx)[1]
    assert argv[argv.index("--pids-limit") + 1] == "64"
    assert argv[argv.index("--memory") + 1] == "256m"
    assert "--cap-drop=ALL" in argv and "--security-opt=no-new-privileges" in argv
    assert not any("docker.sock,dst=" in arg for arg in argv)
    result = await contained.execute(ctx)
    assert result.status == ExecutionStatus.SUCCESS
    assert result.output["records"][0]["name"] == "A"
    assert result.resources.cpu_ms == 0 and result.resources.latency_ms > 0
    assert result.stdout is None and result.stderr is None
    assert "claimed" not in result.metadata
    assert not result.accounting.model_usage
    payload = {
        "spec": ctx.spec.model_dump(mode="json"),
        "request": ctx.request.model_dump(mode="json"),
        "attempt": 1,
        "approved_side_effect": "read",
    }
    assert (await run(payload))["output"] == result.output
    bad = ctx.spec.model_copy(deep=True)
    bad.config["inherit_env"] = True
    with pytest.raises(ConfigurationError, match="environment"):
        contained.command(
            ExecutionContext(request=ctx.request, spec=bad, estimate=bad.estimate, attempt=1)
        )
    unsafe = contained.environment.model_copy(update={"read_only_roots": [str(Path.home())]})
    with pytest.raises(ConfigurationError, match="home"):
        ContainerExecutor(unsafe).command(ctx)
    link = tmp_path / "link"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ConfigurationError, match="symlinks"):
        ContainerExecutor(contained.environment, (link,)).command(ctx)
    with pytest.raises(ConfigurationError, match="SHA256"):
        ContainerExecutor(
            contained.environment.model_copy(update={"container_image": "x@sha256:bad"})
        ).command(ctx)


async def test_command_timeout_covers_blocked_stdin_and_cancellation():
    spec = ExecutorSpec(
        id="blocked",
        capability="test",
        kind=ExecutorKind.COMMAND,
        description="bounded fixture",
        config={
            "argv": [sys.executable, "-c", "import time;time.sleep(30)"],
            "stdin_json": True,
            "timeout_seconds": 0.05,
        },
    )
    ctx = ExecutionContext(
        request=ActionRequest(capability="test", input={"data": "x" * 500000}),
        spec=spec,
        estimate=spec.estimate,
        attempt=1,
    )
    result = await asyncio.wait_for(CommandExecutor().execute(ctx), timeout=3)
    assert result.status == ExecutionStatus.TIMEOUT
    assert result.resources.latency_ms > 0
    spec.config["timeout_seconds"] = 30
    task = asyncio.create_task(CommandExecutor().execute(ctx))
    await asyncio.sleep(0.05)
    task.cancel()
    result = await asyncio.wait_for(task, timeout=3)
    assert result.status == ExecutionStatus.TIMEOUT and result.exit_code is not None


@pytest.mark.parametrize('limit,expected', [(None, 2_000_000), (1_800_000, 2_000_000),
    (7_000_000, 8_000_000), (16_000_000, 17_000_000)])
async def test_contained_input_allowance_is_operator_bound_and_legacy_default_is_stable(tmp_path, monkeypatch, limit, expected):
    from aeep.models import RawExecution

    context = controlled_context()
    if limit is not None:
        context.spec.config['max_stdin_bytes'] = limit
    context.request.input['max_stdin_bytes'] = 16_000_000
    seen = []
    async def capture(self, wrapper):
        assert wrapper.spec.config['max_stdin_bytes'] == expected
        argv = wrapper.spec.config['argv']
        if expected > 2_000_000:
            assert argv[-2:] == ['--input-limit', str(expected)]
        else:
            assert argv[-1] == 'aeep.assessment.container_worker'
            assert '--input-limit' not in argv
        assert wrapper.request.input['spec']['config'].get('max_stdin_bytes') == limit
        seen.append(wrapper)
        return RawExecution(status=ExecutionStatus.SUCCESS,
            output=RawExecution(status=ExecutionStatus.SUCCESS, output={'fixture': True}).model_dump(mode='json'))
    async def cleanup(self, identity):
        assert identity == 'attempt'
        return True
    monkeypatch.setattr(CommandExecutor, 'execute', capture)
    monkeypatch.setattr(ContainerExecutor, 'cleanup', cleanup)
    result = await ContainerExecutor(environment(tmp_path, tmp_path / 'not-executed')).execute(context)
    assert result.status is ExecutionStatus.SUCCESS and result.output == {'fixture': True} and len(seen) == 1


@pytest.mark.parametrize('limit', [0, -1, 16_000_001, True, '7000000', None])
async def test_invalid_contained_input_limits_never_reach_a_process(tmp_path, monkeypatch, limit):
    context = controlled_context()
    context.spec.config['max_stdin_bytes'] = limit
    async def forbidden(*args, **kwargs):
        pytest.fail('Invalid operator input allowance reached process execution')
    monkeypatch.setattr(CommandExecutor, 'execute', forbidden)
    with pytest.raises(ConfigurationError, match='input exceeds'):
        await ContainerExecutor(environment(tmp_path, tmp_path / 'not-executed')).execute(context)


@pytest.mark.parametrize('arguments', [[], ['--input-limit', '2000000'], ['--input-limit', '8000000']])
def test_worker_entrypoint_enforces_launch_bound_before_dispatch(monkeypatch, capsys, arguments):
    import io
    import json
    from types import SimpleNamespace

    from aeep.assessment import container_worker

    limit = 8_000_000 if arguments[-1:] == ['8000000'] else 2_000_000
    # A model-supplied field cannot raise the default framing limit. Exercise the
    # real main reader, with a synthetic adapter replacing external execution.
    payload = {'input_limit': 17_000_000, 'data': 'x' * (limit - 100)}
    data = json.dumps(payload).encode()
    seen = []
    async def synthetic_run(value):
        seen.append(value)
        return {'fixture_only': True}
    monkeypatch.setattr(container_worker, 'run', synthetic_run)
    monkeypatch.setattr(sys, 'argv', ['container_worker', *arguments])
    monkeypatch.setattr(sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(data)))
    container_worker.main()
    assert seen == [payload] and json.loads(capsys.readouterr().out) == {'fixture_only': True}
    seen.clear()
    monkeypatch.setattr(sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(data + b' ' * (limit + 1 - len(data)))))
    with pytest.raises(ConfigurationError, match='input exceeds its limit'):
        container_worker.main()
    assert not seen


@pytest.mark.parametrize('arguments', [['--unknown', '8000000'], ['--input-limit'],
    ['--input-limit', '1999999'], ['--input-limit', '17000001'],
    ['--input-limit', 'NaN'], ['--input-limit', '\uff18\uff10\uff10\uff10\uff10\uff10\uff10'],
    ['--input-limit', '8000000', 'extra']])
def test_worker_rejects_invalid_launch_limits_before_reading(monkeypatch, arguments):
    from aeep.assessment import container_worker
    monkeypatch.setattr(sys, 'argv', ['container_worker', *arguments])
    # Accessing buffer would fail: arguments must be validated before any input.
    monkeypatch.setattr(sys, 'stdin', object())
    with pytest.raises(ConfigurationError, match='input'):
        container_worker.main()


@pytest.mark.skipif(sys.platform == 'win32', reason='local executable protocol fixture')
async def test_large_input_crosses_both_actual_container_protocol_readers(tmp_path):
    # A local stand-in for Docker forwards into the actual worker entrypoint.
    # It proves framing across both processes, not OS container isolation.
    runtime = tmp_path / 'docker-worker-fixture'
    runtime.write_text(f"#!{sys.executable}\n" + """import os,subprocess,sys
if 'run' in sys.argv:
    i=sys.argv.index('aeep.assessment.container_worker')
    env=dict(os.environ,PYTHONPATH=sys.argv[sys.argv.index('--env')+1].split('=',1)[1])
    p=subprocess.run([sys.executable,'-m',*sys.argv[i:]],input=sys.stdin.buffer.read(),capture_output=True,env=env)
    sys.stdout.buffer.write(p.stdout)
    sys.stderr.buffer.write(p.stderr)
    raise SystemExit(p.returncode)
""")
    runtime.chmod(0o755)
    context = controlled_context()
    context.spec.kind = ExecutorKind.COMMAND
    context.spec.config.update(argv=[sys.executable, '-c',
        'import json,sys;value=json.load(sys.stdin);print(json.dumps({"length":len(value["data"])}))'],
        max_stdin_bytes=7_000_000, stdin_json=True, output={'type': 'json'})
    context.request.input = {'data': 'x' * 2_700_000}
    result = await ContainerExecutor(environment(tmp_path, runtime)).execute(context)
    assert result.status is ExecutionStatus.SUCCESS and result.output == {'length': 2_700_000}
