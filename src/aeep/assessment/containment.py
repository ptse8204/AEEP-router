"""Local Docker containment around existing adapters; no daemon or image provisioning."""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import replace
from pathlib import Path

from pydantic import ValidationError

from ..errors import ConfigurationError
from ..execution import ExecutorCapabilities
from ..executors.base import BaseExecutor, ExecutionContext
from ..executors.command import CommandExecutor
from ..models import ExecutorKind, ExecutorSpec, RawExecution, ResourceVector
from ..store import ReceiptStore
from .identity import protected_directory
from .models import AssessmentEnvironment

NATIVE_KINDS = {ExecutorKind.COMMAND, ExecutorKind.PYTHON, ExecutorKind.MCP}


def container_name(attempt_id: str) -> str:
    return "aeep-" + hashlib.sha256(attempt_id.encode()).hexdigest()[:32]


class ContainerExecutor(BaseExecutor):
    def capabilities(self) -> ExecutorCapabilities:
        return ExecutorCapabilities(adapter=type(self).__name__, features={"fresh_worker":"supported", "reused_worker":"unsupported"})

    def __init__(
        self, environment: AssessmentEnvironment, extra_roots: tuple[Path, ...] = (), *, fixture_root: Path | None = None
    ) -> None:
        self.environment = environment
        self.roots = tuple(Path(root) for root in environment.read_only_roots) + extra_roots
        self.fixture_root = fixture_root

    def command(self, context: ExecutionContext) -> tuple[list[str], str]:
        environment = self.environment
        runtime, socket = environment.container_runtime, environment.container_socket
        if environment.kind != "container" or runtime is None or socket is None:
            raise ConfigurationError("an explicit local container runtime and socket are required")
        if not re.fullmatch(
            r"(?:[A-Za-z0-9._/:+-]+@)?sha256:[a-f0-9]{64}", environment.container_image or ""
        ):
            raise ConfigurationError("container image must be pinned to an exact SHA256 digest")
        if context.spec.kind not in NATIVE_KINDS or (
            context.spec.kind == ExecutorKind.MCP
            and context.spec.config.get("transport", "stdio") != "stdio"
        ):
            raise ConfigurationError(
                "container adapter supports local Python, command and stdio MCP routes"
            )
        if context.spec.config.get("inherit_env") or context.spec.config.get("env"):
            raise ConfigurationError(
                "contained candidates cannot inherit or inject host environment"
            )
        identity = context.attempt_id or context.request.action_id
        name = container_name(identity)
        argv = [
            runtime,
            "--host",
            f"unix://{socket}",
            "run",
            "--pull=never",
            "--rm",
            "--name",
            name,
            "--read-only",
            "--user",
            "65534:65534",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--cpus",
            str(environment.cpu_count),
            "--memory",
            f"{environment.memory_mb}m",
            "--memory-swap",
            f"{environment.memory_mb}m",
            "--pids-limit",
            str(environment.process_limit),
            "--network",
            "bridge" if environment.network else "none",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=32m",
            "--workdir",
            "/tmp",
            "-i",
        ]
        runtime_root = Path(__file__).resolve().parents[2]
        roots = {runtime_root, *self.roots}
        if self.fixture_root is not None and "root" in context.request.input:
            trial_root = Path(context.request.input["root"])
            if trial_root.parent != self.fixture_root / "trial-inputs" or not re.fullmatch(r"[a-f0-9]{64}", trial_root.name):
                raise ConfigurationError("trial fixture must be the current private case directory")
            roots.add(trial_root)
        for root in sorted(roots):
            if (
                not root.is_absolute()
                or root.is_symlink()
                or root.resolve() != root
                or not root.is_dir()
                or any(char in str(root) for char in (",", "\n", "\x00"))
            ):
                raise ConfigurationError(
                    "container mounts require explicit existing directories without symlinks"
                )
            if (
                protected_directory(root)
            ):
                raise ConfigurationError("container mounts cannot expose home, root or Codex state")
            argv.extend(["--mount", f"type=bind,src={root},dst={root},readonly"])
        argv.extend(
            [
                "--env",
                "PYTHONPATH=" + ":".join(str(root) for root in (runtime_root, *self.roots)),
                "--entrypoint",
                "python3",
                str(environment.container_image),
                "-m",
                "aeep.assessment.container_worker",
            ]
        )
        return argv, name

    async def execute(self, context: ExecutionContext) -> RawExecution:
        argv, name = self.command(context)
        payload = {
            "request": context.request.model_dump(mode="json"),
            "spec": context.spec.model_dump(mode="json"),
            "attempt": context.attempt,
            "attempt_id": context.attempt_id,
            "approved_side_effect": context.approved_side_effect.value,
        }
        output_limit = int(context.spec.config.get('max_output_bytes', 1_000_000))
        if not 0 < output_limit <= 16_000_000:
            raise ConfigurationError('contained output exceeds the reviewed transport ceiling')
        wrapper = ExecutorSpec(
            id=context.spec.id,
            capability=context.spec.capability,
            kind=ExecutorKind.COMMAND,
            description="Local controlled adapter subprocess",
            config={
                "argv": argv,
                "stdin_json": True,
                "max_stdin_bytes": 2_000_000,
                "max_output_bytes": 2 * output_limit + 65536 if output_limit > 1_000_000 else 1_000_000,
                "timeout_seconds": float(context.spec.config.get("timeout_seconds", 60)) + 1,
                "output": {"type": "json"},
            },
        )
        try:
            raw = await CommandExecutor().execute(
                replace(
                    context,
                    spec=wrapper,
                    request=context.request.model_copy(update={"input": payload}),
                )
            )
            # Docker CLI CPU/RSS are not the container's CPU/RSS; do not mislabel them.
            raw.resources = ResourceVector(latency_ms=raw.resources.latency_ms)
            raw.metadata = {
                "container_image": self.environment.container_image,
                "container_name": name,
                "container_resource_usage": "unavailable",
            }
            if raw.status.value == "success":
                try:
                    child = RawExecution.model_validate(raw.output)
                except ValidationError:
                    from ..models import ExecutionStatus
                    raw.status = ExecutionStatus.FAILED
                    raw.output = None
                    raw.error_type = "CONTAINER_PROTOCOL_ERROR"
                    return raw
                raw.status, raw.output, raw.error_type = (
                    child.status,
                    child.output,
                    child.error_type,
                )
                raw.error_message = "contained adapter failed" if child.error_type else None
            raw.stdout = raw.stderr = None
            return raw
        finally:
            await self.cleanup(context.attempt_id or context.request.action_id)

    async def cleanup(self, attempt_id: str) -> bool:
        # A killed Docker client does not stop its daemon-owned container.
        try:
            process = await asyncio.create_subprocess_exec(
                str(self.environment.container_runtime),
                "--host",
                f"unix://{self.environment.container_socket}",
                "rm",
                "--force",
                container_name(attempt_id),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                env={},
            )
        except OSError:
            return False
        try:
            return await asyncio.wait_for(process.wait(), timeout=5) == 0
        except TimeoutError:
            process.kill()
            await process.wait()
            return False


def admitted_container(store: ReceiptStore, spec: ExecutorSpec) -> ContainerExecutor | None:
    """Invocation adapter follows the already-checked admission's reviewed environment."""
    from .repository import AssessmentRepository

    with store._lock:
        row = store._connection.execute(
            "SELECT admission_id FROM assessment_admissions WHERE executor_id=?", (spec.id,)
        ).fetchone()
    if row is None:
        return None
    repository = AssessmentRepository(store)
    admission = repository.get("admission", row[0])
    environment = AssessmentEnvironment.model_validate(
        repository.get("environment", admission["environment_digest"])
    )
    return ContainerExecutor(environment) if environment.kind == "container" and spec.kind in NATIVE_KINDS and (spec.kind != ExecutorKind.MCP or spec.config.get("transport", "stdio") == "stdio") else None
