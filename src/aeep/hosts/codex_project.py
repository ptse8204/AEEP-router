"""Codex project MCP configuration for an AEEP task activation."""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

from ..assessment.repository import AssessmentRepository
from ..errors import ConfigurationError
from ..models import StrictModel

if TYPE_CHECKING:
    from ..router import Router
    from ..tasks import TaskActivation

fcntl: ModuleType | None
try:
    import fcntl as _fcntl
    fcntl = _fcntl
except ImportError:  # Ordinary CLI imports remain portable on Windows.
    fcntl = None


def _read(path: Path) -> bytes | None:
    if not hasattr(os, "O_NOFOLLOW"):
        raise ConfigurationError("project configuration requires macOS or Linux/WSL")
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ConfigurationError('project Codex configuration is inaccessible or a symlink') from exc
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 65536:
            raise ConfigurationError('project Codex configuration must be a small regular file without hard links')
        return stream.read(65537)


def lock_path(record: TaskActivation) -> Path:
    root = Path(record.manifest_path).parent
    directory = root / '.aeep' / 'task-profiles'
    if not root.is_absolute() or directory.resolve() != directory:
        raise ConfigurationError('task profile directory must be canonical and symlink-free')
    return directory / 'codex-config.lock'


class TaskCodexBinding(StrictModel):
    activation_id: str
    config_path: str
    block: str


_CODEX_CREATED = b'# AEEP-created project configuration\n'


def get_binding(router: Router, record: TaskActivation) -> TaskCodexBinding | None:
    with router.store._lock:
        row = router.store._connection.execute(
            "SELECT payload_json FROM assessment_records WHERE kind='task_codex_binding' AND id=?",
            (record.activation_id,)).fetchone()
    return TaskCodexBinding.model_validate_json(row[0]) if row else None


def config_path(record: TaskActivation) -> Path:
    root = Path(record.manifest_path).parent
    directory = root / '.codex'
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise ConfigurationError('project Codex configuration directory is not a regular directory')
    return directory / 'config.toml'


@contextmanager
def _codex_lock(record: TaskActivation) -> Iterator[None]:
    # A stable project lock also serializes activations backed by different databases.
    if fcntl is None or not hasattr(os, "O_NOFOLLOW"):
        raise ConfigurationError('project Codex binding requires a POSIX host')
    path = lock_path(record)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ConfigurationError('project Codex lock is not a regular file')
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def read_config(path: Path) -> bytes | None:
    contents = _read(path)
    if contents is not None:
        try:
            tomllib.loads(contents.decode('utf-8'))
        except (UnicodeError, tomllib.TOMLDecodeError) as exc:
            raise ConfigurationError('project Codex configuration is invalid TOML') from exc
    return contents


def entry_state(binding: TaskCodexBinding, contents: bytes | None) -> str:
    if contents is None:
        return 'absent'
    name = 'aeep_' + binding.activation_id
    servers = tomllib.loads(contents.decode('utf-8')).get('mcp_servers', {})
    if not isinstance(servers, dict):
        return 'conflict'
    configured = servers.get(name)
    if configured is None:
        return 'absent'
    expected = tomllib.loads(binding.block.lstrip()).get('mcp_servers', {}).get(name)
    return 'applied' if configured == expected and contents.count(binding.block.encode()) == 1 else 'conflict'


def _replace_codex_bytes(path: Path, before: bytes | None, after: bytes | None) -> None:
    if not hasattr(os, "fchmod") or not hasattr(os, "O_NOFOLLOW"):
        raise ConfigurationError("project configuration requires macOS or Linux/WSL")
    if after is None:
        if _read(path) != before:
            raise ConfigurationError('project Codex configuration changed during cleanup')
        path.unlink()
        return
    descriptor, temporary = tempfile.mkstemp(prefix='.aeep-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            if before is not None:
                os.fchmod(stream.fileno(), stat.S_IMODE(path.stat().st_mode))
            stream.write(after)
            stream.flush()
            os.fsync(stream.fileno())
        if _read(path) != before:
            raise ConfigurationError('project Codex configuration changed during update')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def install_binding(router: Router, record: TaskActivation) -> None:
    with _codex_lock(record):
        path = config_path(record)
        existing = read_config(path)
        base = existing if existing is not None else _CODEX_CREATED
        # Activation already validated the exact reviewed operator-owned scope.
        approval_ceiling = router.bind_task_scope(record.scope_digest)
        name = 'aeep_' + record.activation_id
        if existing is not None:
            servers = tomllib.loads(existing.decode('utf-8')).get('mcp_servers', {})
            if not isinstance(servers, dict):
                raise ConfigurationError('project Codex MCP configuration is not a table')
            if name in servers:
                raise ConfigurationError('project Codex MCP entry already exists')
        block = (('' if base.endswith(b'\n') else '\n')
            + f'# AEEP task {record.activation_id}\n[mcp_servers.{name}]\n'
            + f'command = {json.dumps(sys.executable, ensure_ascii=False)}\n'
            + 'args = ' + json.dumps(['-I', '-m', 'aeep', 'serve', '--transport', 'stdio', '--profile', 'task', '--approve', approval_ceiling.value,
                '--task-activation', record.activation_id, '--manifest', record.manifest_path], ensure_ascii=False) + '\n')
        # Match the task-only service's exact scope/fingerprint declaration filter.
        # Codex still restricts these rules to this owned server and named tools;
        # the service independently enforces the reviewed approval ceiling.
        from ..mcp.server import AEEPToolService
        tools = AEEPToolService(router, profile='task', task_scope=record.scope_digest).list_tools()
        for tool in tools:
            block += (f'\n[mcp_servers.{name}.tools.{json.dumps(tool["name"], ensure_ascii=False)}]\n'
                      + 'approval_mode = "approve"\n')
        binding = TaskCodexBinding(activation_id=record.activation_id, config_path=str(path), block=block)
        try:
            tomllib.loads((base + block.encode()).decode('utf-8'))
        except (UnicodeError, tomllib.TOMLDecodeError) as exc:
            raise ConfigurationError('generated project Codex configuration is invalid TOML') from exc
        AssessmentRepository(router.store).put('task_codex_binding', record.activation_id, binding)
        path.parent.mkdir(mode=0o700, exist_ok=True)
        _replace_codex_bytes(path, existing, base + block.encode())


def remove_binding(router: Router, record: TaskActivation) -> None:
    binding = get_binding(router, record)
    if binding is None:
        return  # Activations created before project Codex integration have no host entry.
    with _codex_lock(record):
        path = config_path(record)
        if str(path) != binding.config_path:
            raise ConfigurationError('project Codex configuration path changed')
        current = read_config(path)
        block = binding.block.encode()
        state = entry_state(binding, current)
        if state == 'absent':
            return  # The entry was never installed or was already removed.
        if state != 'applied':
            raise ConfigurationError('project Codex MCP entry changed; activation paused and user configuration preserved')
        assert current is not None
        remaining = current.replace(block, b'', 1)
        created = remaining.startswith(_CODEX_CREATED) and b'# AEEP task ' not in remaining
        if created:
            remaining = remaining[len(_CODEX_CREATED):]
        try:
            tomllib.loads(remaining.decode('utf-8'))
        except (UnicodeError, tomllib.TOMLDecodeError) as exc:
            raise ConfigurationError('project Codex configuration would be invalid after cleanup') from exc
        _replace_codex_bytes(path, current, remaining if remaining or not created else None)

