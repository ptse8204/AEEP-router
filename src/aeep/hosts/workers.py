"""Pinned container process profiles shared by managed-host protocol adapters."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import Field, SerializerFunctionWrapHandler, model_serializer, model_validator

from ..errors import ConfigurationError
from ..models import ActionRequest, ExecutionStatus, ExecutorKind, ExecutorSpec, StrictModel

# Runs in the existing worker, with no shell, mounts or arbitrary path arguments.
ARTIFACT_PROGRAM = r"""
import base64, hashlib, json, os, re, stat, sys
request = json.load(sys.stdin)
name, limit = request['name'], request['limit']
if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', name):
    raise ValueError('invalid artifact name')
if type(limit) is not int or not 1 <= limit <= 4000000:
    raise ValueError('invalid artifact limit')
root = os.open('/workspace', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
try:
    if request['operation'] == 'tree':
        files = request['files']
        if name != 'case-tree' or limit != 100000 or not isinstance(files, list) or len(files) > 1000:
            raise ValueError('invalid tree bounds')
        entries, directories, total = {}, set(), 0
        for item in files:
            if not isinstance(item, dict) or set(item) != {'path', 'text'}:
                raise ValueError('invalid tree entry')
            path, text = item['path'], item['text']
            if not isinstance(path, str) or not isinstance(text, str):
                raise ValueError('invalid tree entry')
            parts = path.split('/')
            if (not path or len(path.encode('utf-8')) > 4096 or len(parts) > 32 or '\\' in path
                    or any(not p or p in {'.', '..', 'auth.json', '.env', 'credentials.json'} or '\x00' in p for p in parts)
                    or path in entries):
                raise ValueError('unsafe tree path')
            content = text.encode('utf-8')
            total += len(content)
            if total > limit:
                raise ValueError('tree exceeds byte limit')
            entries[path] = content
            directories.update('/'.join(parts[:i]) for i in range(1, len(parts)))
        if set(entries) & directories or len(entries) + len(directories) > 1000:
            raise ValueError('conflicting or oversized tree')
        # Validate the whole manifest before creating anything. A fresh root and
        # descriptor-relative exclusive writes prevent overwrites and symlink traversal.
        os.mkdir(name, mode=0o700, dir_fd=root)
        tree = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
        try:
            for path in sorted(directories, key=lambda p: (p.count('/'), p)):
                fd = os.dup(tree)
                try:
                    parts = path.split('/')
                    for part in parts[:-1]:
                        child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                        os.close(fd)
                        fd = child
                    os.mkdir(parts[-1], mode=0o700, dir_fd=fd)
                finally:
                    os.close(fd)
            for path, content in entries.items():
                fd = os.dup(tree)
                try:
                    parts = path.split('/')
                    for part in parts[:-1]:
                        child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                        os.close(fd)
                        fd = child
                    output = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
                    with os.fdopen(output, 'wb') as stream:
                        stream.write(content)
                finally:
                    os.close(fd)
        finally:
            os.close(tree)
        result = {'size': total, 'files': len(entries)}
    elif request['operation'] == 'write':
        encoded = request['data']
        if not isinstance(encoded, str) or len(encoded) > 4 * ((limit + 2) // 3):
            raise ValueError('artifact exceeds limit')
        data = base64.b64decode(encoded, validate=True)
        if len(data) > limit:
            raise ValueError('artifact exceeds limit')
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=root)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        result = {}
    elif request['operation'] == 'read':
        fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=root)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
                raise ValueError('unsafe artifact')
            data = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
        if len(data) > limit or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('artifact changed during read')
        result = {'data': base64.b64encode(data).decode('ascii')}
    else:
        raise ValueError('invalid artifact operation')
    if request['operation'] != 'tree':
        result.update(size=len(data), sha256=hashlib.sha256(data).hexdigest())
    print(json.dumps(result))
finally:
    os.close(root)
"""


class ManagedWorkerBinding(StrictModel):
    schema_version: Literal["execution.worker.v1", "execution.worker.v2"] = "execution.worker.v1"
    worker_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,50}$")
    runtime: str
    socket: str
    image: str = Field(pattern=r"^(?:[A-Za-z0-9._/:+-]+@)?sha256:[a-f0-9]{64}$")
    platform: Literal["linux/amd64", "linux/arm64"]
    binary: str
    binary_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    configuration_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    dependencies_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    cpu_count: float = Field(default=1, gt=0, le=64)
    memory_mb: int = Field(default=1024, ge=128, le=65536)
    process_limit: int = Field(default=64, ge=1, le=1024)
    # Exact Docker network ID, never host/bridge or a mutable network name.
    network_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    model_proxy_url: str | None = Field(default=None, pattern=r"^http://(?:[0-9]{1,3}\.){3}[0-9]{1,3}:[0-9]{1,5}$")
    credential_volume: str | None = Field(default=None, pattern=r"^aeep-auth-[a-z0-9-]{1,64}$")
    seccomp_profile: dict[str, object] | None = None
    permissions_profile: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    reviewed_files: dict[str, str] | None = None

    @model_serializer(mode="wrap")
    def preserve_historical_binding(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        result: dict[str, object] = handler(self)
        for name in ("seccomp_profile", "permissions_profile", "reviewed_files", "model_proxy_url"):
            if getattr(self, name) is None:
                result.pop(name, None)
        return result

    @model_validator(mode="after")
    def paths_are_explicit(self) -> ManagedWorkerBinding:
        if self.model_proxy_url is not None:
            from ipaddress import IPv4Address
            from urllib.parse import urlsplit
            endpoint = urlsplit(self.model_proxy_url)
            IPv4Address(endpoint.hostname or "")
            if self.network_id is None or not endpoint.port:
                raise ValueError("model proxy requires a pinned private network and valid port")
        if (self.seccomp_profile is not None or self.permissions_profile is not None) and self.schema_version != "execution.worker.v2":
            raise ValueError("reviewed security profiles require worker contract v2")
        if self.seccomp_profile is not None:
            if self.seccomp_profile.get("defaultAction") not in {"SCMP_ACT_ERRNO", "SCMP_ACT_KILL", "SCMP_ACT_KILL_PROCESS", "SCMP_ACT_TRAP"}:
                raise ValueError("worker seccomp profile must deny by default")
            if len(self.security_bytes()) > 131072:
                raise ValueError("worker seccomp profile is too large")
        for value in (self.runtime, self.socket, self.binary):
            if not PurePosixPath(value).is_absolute() or ".." in PurePosixPath(value).parts or any(c in value for c in "\x00\n,"):
                raise ValueError("worker paths must be explicit absolute paths")
        if self.reviewed_files is not None:
            if not self.reviewed_files or len(self.reviewed_files) > 2000:
                raise ValueError("worker reviewed files must be bounded")
            for name, digest in self.reviewed_files.items():
                path = PurePosixPath(name)
                if (not path.is_relative_to('/opt') or '..' in path.parts
                        or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest)):
                    raise ValueError("reviewed files require immutable /opt paths and SHA256 digests")
        return self

    def security_bytes(self) -> bytes:
        return json.dumps(self.seccomp_profile, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()

    def prepare_security(self, directory: Path) -> Path | None:
        """Docker reads a private snapshot; no policy file is mounted in the worker."""
        if self.seccomp_profile is None:
            return None
        path = directory / "seccomp.json"
        with path.open("xb") as stream:
            stream.write(self.security_bytes())
        path.chmod(0o400)
        return path

    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()

    def argv(self, arguments: tuple[str, ...], *, execution_id: str, output_schema: dict[str, object] | None = None, security_path: Path | None = None) -> tuple[str, ...]:
        if any("\x00" in item for item in arguments):
            raise ConfigurationError("worker arguments contain NUL")
        name = "aeep-" + hashlib.sha256(execution_id.encode()).hexdigest()[:32]
        command = [self.runtime, "--host", f"unix://{self.socket}", "run", "--pull=never", "--rm",
                   "--name", name, "--platform", self.platform, "--read-only", "--user", "65534:65534",
                   "--cap-drop=ALL", "--security-opt=no-new-privileges", "--cpus", str(self.cpu_count),
                   "--memory", f"{self.memory_mb}m", "--memory-swap", f"{self.memory_mb}m",
                   "--pids-limit", str(self.process_limit), "--network", self.network_id or "none",
                   "--tmpfs", "/workspace:rw,nosuid,nodev,size=128m,uid=65534,gid=65534,mode=700",
                   "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=64m,uid=65534,gid=65534,mode=700",
                   "--tmpfs", "/worker/home:rw,nosuid,nodev,noexec,size=32m,uid=65534,gid=65534,mode=700",
                   "--env", "HOME=/worker/home", "--env", "CODEX_HOME=/worker/auth",
                   "--workdir", "/workspace", "-i"]
        if self.model_proxy_url is not None:
            command += ["--env", "HTTPS_PROXY=" + self.model_proxy_url, "--env", "HTTP_PROXY=" + self.model_proxy_url,
                        "--env", "ALL_PROXY=" + self.model_proxy_url, "--env", "NO_PROXY="]
        if self.credential_volume:
            command += ["--mount", f"type=volume,src={self.credential_volume},dst=/worker/auth"]
        else:
            command += ["--tmpfs", "/worker/auth:rw,nosuid,nodev,noexec,size=32m,uid=65534,gid=65534,mode=700"]
        if self.reviewed_files is not None:
            command += ["--env", "AEEP_REVIEWED_FILES=" + json.dumps(self.reviewed_files, separators=(",", ":"))]
        if self.seccomp_profile is not None:
            if security_path is None or security_path.is_symlink() or security_path.read_bytes() != self.security_bytes():
                raise ConfigurationError("worker security snapshot differs from the reviewed profile")
            command += ["--security-opt", "seccomp=" + str(security_path)]
        elif security_path is not None:
            raise ConfigurationError("unreviewed worker security snapshot")
        if output_schema is not None:
            schema = json.dumps(output_schema, separators=(",", ":"))
            if len(schema.encode()) > 65536:
                raise ConfigurationError("worker output schema is too large")
            command += ["--env", "AEEP_OUTPUT_SCHEMA=" + schema]
        command += ["--entrypoint", "/opt/aeep/worker-launch", self.image,
                    self.binary_sha256, self.configuration_digest, self.binary, *arguments]
        return tuple(command)


    async def artifact(self, execution_id: str, *, name: str, limit: int,
                       data: str | None = None, files: list[dict[str, str]] | None = None,
                       timeout: float = 10) -> dict[str, object]:
        from ..executors.base import ExecutionContext
        from ..executors.command import CommandExecutor
        command = [self.runtime, "--host", f"unix://{self.socket}", "exec", "-i",
                   "--user", "65534:65534", "aeep-" + hashlib.sha256(execution_id.encode()).hexdigest()[:32],
                   "python3", "-I", "-c", ARTIFACT_PROGRAM]
        spec = ExecutorSpec(id="worker-artifact", capability="worker.artifact", kind=ExecutorKind.COMMAND,
                            description="Bounded private worker artifact transfer", config={
                                "argv": command, "argv_literal": True, "stdin_json": True,
                                "max_stdin_bytes": 6_000_000, "max_output_bytes": 6_000_000,
                                "timeout_seconds": timeout, "output": {"type": "json"}})
        request = ActionRequest(capability=spec.capability, input={"name": name, "limit": limit,
                                "operation": "tree" if files is not None else "read" if data is None else "write",
                                "data": data, "files": files})
        raw = await CommandExecutor().execute(ExecutionContext(request=request, spec=spec,
                                                              estimate=spec.estimate, attempt=1))
        if raw.status is not ExecutionStatus.SUCCESS or not isinstance(raw.output, dict):
            # No child stderr, file contents or paths escape in the diagnostic.
            raise ConfigurationError("worker artifact transfer failed")
        return raw.output

    async def cleanup(self, execution_id: str) -> bool:
        from ..assessment.containment import ContainerExecutor
        from ..assessment.models import AssessmentEnvironment
        environment = AssessmentEnvironment(environment_id=self.worker_id, kind="container", identity={},
                                            container_image=self.image, container_runtime=self.runtime,
                                            container_socket=self.socket)
        return await ContainerExecutor(environment).cleanup(execution_id)


def validate_worker_pair(candidate: ManagedWorkerBinding, baseline: ManagedWorkerBinding) -> None:
    if candidate.worker_id == baseline.worker_id or (candidate.credential_volume and candidate.credential_volume == baseline.credential_volume):
        raise ConfigurationError("comparison workers must have independent identities and credential storage")
    for field in ("platform", "binary_sha256", "cpu_count", "memory_mb", "process_limit", "network_id", "model_proxy_url", "seccomp_profile", "permissions_profile"):
        if getattr(candidate, field) != getattr(baseline, field):
            raise ConfigurationError(f"comparison worker settings differ: {field}")
    # Different reviewed plugin dependencies/configuration are legitimate only in a
    # whole-workflow comparison. The reviewed plan still binds both exact digests.


def binding_from_config(value: object) -> ManagedWorkerBinding | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ConfigurationError("managed worker binding must be a reviewed object")
    return ManagedWorkerBinding.model_validate(value)
