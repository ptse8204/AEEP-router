"""Operator-owned connection filters. These restrict, never grant, authority."""
from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field

from .errors import ConfigurationError
from .hosts.codex_project import _read, _replace_codex_bytes
from .models import ExecutorSpec, StrictModel

if TYPE_CHECKING:
    from .router import Router

PLANNING_TOOLS = frozenset({
    'aeep_list_capabilities', 'aeep_route_action', 'aeep_lookup_capability',
    'aeep_discover_resources', 'aeep_discovery_status', 'aeep_stack_recommend',
    'aeep_stack_propose', 'aeep_stack_inspect', 'aeep_stack_optimize', 'aeep_stack_preflight',
})


def config_root() -> Path:
    return Path(os.environ.get('AEEP_CONFIG_HOME', str(Path.home() / '.config' / 'aeep'))).resolve()


def connection_path(identity: str) -> Path:
    if not identity or len(identity) > 80 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in identity):
        raise ConfigurationError('connection name must contain only letters, digits, hyphens or underscores')
    return config_root() / 'connections' / f'{identity}.json'


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    """Serialize cooperating operator writers; dispatch only reads atomic files."""
    from .hosts.codex_project import fcntl
    if fcntl is None or not hasattr(os, "O_NOFOLLOW"):
        raise ConfigurationError('connection management requires macOS or Linux/WSL')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.resolve() != path.parent:
        raise ConfigurationError('configuration directory must not contain symlinks')
    fd = os.open(str(path) + '.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def write_json(path: Path, value: Any, *, before: bytes | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _replace_codex_bytes(path, before, (json.dumps(value, indent=2) + '\n').encode())


class AgentConnection(StrictModel):
    schema_version: Literal['aeep.agent-connection.v1'] = 'aeep.agent-connection.v1'
    connection_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    host: Literal['codex', 'claude', 'dsh', 'deepseek-api']
    project: str
    manifest: str
    enabled: bool = True
    allowed_tools: list[str] = Field(default_factory=lambda: sorted(PLANNING_TOOLS), max_length=256)
    executor_fingerprints: dict[str, str] = Field(default_factory=dict, max_length=256)
    host_configuration: str | None = None
    host_entry: str | None = None
    host_applied: str | None = None
    pending_reload: bool = True
    owns_planning_skill: bool = False


def load_connection(path: Path) -> AgentConnection:
    raw = _read(path)
    if raw is None:
        raise ConfigurationError('connection is missing; run aeep setup')
    connection = AgentConnection.model_validate_json(raw)
    if not connection.enabled:
        raise ConfigurationError('connection is disconnected')
    return connection


class ConnectionGuard:
    def __init__(self, path: Path, router: Router) -> None:
        self.path = path.absolute()
        if self.path.resolve() != self.path:
            raise ConfigurationError('connection file must not contain symlinks')
        connection = load_connection(self.path)
        self.identity = connection.connection_id
        self.manifest = str(router.manifest_path)
        self.project = connection.project
        self.current()

    def current(self) -> AgentConnection:
        value = load_connection(self.path)
        if (value.connection_id != self.identity or value.manifest != self.manifest
                or value.project != self.project):
            raise ConfigurationError('connection binding changed; reconnect')
        return value

    def require_tool(self, name: str) -> None:
        if name not in self.current().allowed_tools:
            raise ConfigurationError('tool denied for this connection')

    def require_executor(self, spec: ExecutorSpec) -> None:
        from .economic.prepared import executor_fingerprint
        self.require_tool('aeep_execute_action')
        if self.current().executor_fingerprints.get(spec.id) != executor_fingerprint(spec):
            raise ConfigurationError('executor denied or changed for this connection')


def bind_connection(router: Router, path: Path) -> ConnectionGuard:
    if router._connection_guard is not None:
        if router._connection_guard.path != path.resolve():
            raise ConfigurationError('router already belongs to another connection')
        return router._connection_guard
    guard = ConnectionGuard(path, router)
    router._connection_guard = guard
    return guard
