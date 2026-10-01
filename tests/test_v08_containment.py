from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from conftest import python_spec

from aeep.assessment.container_worker import run
from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import AssessmentEnvironment
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
