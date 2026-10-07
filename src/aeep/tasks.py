"""Project task lifecycle using existing definitions, reviews and durable attempts."""

from __future__ import annotations

import asyncio
import os
import stat
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import Field, SerializerFunctionWrapHandler, model_serializer

from .assessment.identity import file_digest
from .assessment.models import Digest, content_digest
from .assessment.repository import AssessmentRepository
from .attempts import ExecutionAttempt, ExecutionAttemptState
from .errors import ConfigurationError
from .hosts.codex_project import (
    config_path,
    entry_state,
    get_binding,
    install_binding,
    lock_path,
    read_config,
    remove_binding,
)
from .models import StrictModel, TaskScope, new_id, utc_now

if TYPE_CHECKING:
    from .router import Router


class TaskActivation(StrictModel):
    schema_version: Literal['aeep.task-activation.v1'] = 'aeep.task-activation.v1'
    activation_id: str = Field(default_factory=lambda: new_id('task'), pattern=r'^task_[a-zA-Z0-9_-]{1,100}$')
    scope_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    manifest_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    manifest_file_digest: Digest | None = None
    manifest_path: str
    # Only an AEEP-owned, newly created overlay is supported. User host config is never copied.
    original_value: None = None
    capability_profile_digest: Digest | None = None
    host_binding: bool = True

    @model_serializer(mode='wrap')
    def preserve_legacy_profile(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        result: dict[str, object] = handler(self)
        if self.capability_profile_digest is None:
            result.pop('capability_profile_digest', None)
        if self.host_binding:
            result.pop('host_binding', None)
        return result


class TaskLifecycleEvent(StrictModel):
    event_id: str = Field(default_factory=lambda: new_id('task_event'))
    activation_digest: str
    operation: Literal['activate', 'pause', 'stop', 'resume', 'rollback', 'uninstall', 'replace']


class TaskReconciliation(StrictModel):
    schema_version: Literal['aeep.task-reconciliation.v1'] = 'aeep.task-reconciliation.v1'
    attempt_id: str
    attempt_version: int = Field(ge=0)
    scope_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    resolution: Literal['effects_verified', 'effects_reverted']
    evidence_digests: list[Digest] = Field(min_length=1, max_length=16)


def _record(router: Router, identity: str) -> TaskActivation:
    record = TaskActivation.model_validate(AssessmentRepository(router.store).get('task_activation', identity))
    if router.manifest_path is None or str(router.manifest_path) != record.manifest_path:
        raise ConfigurationError('task activation belongs to another project manifest')
    return record


def _path(record: TaskActivation) -> Path:
    root = Path(record.manifest_path).parent
    directory = root / '.aeep' / 'task-profiles'
    if not root.is_absolute() or directory.resolve() != directory:
        raise ConfigurationError('task profile directory must be canonical and symlink-free')
    return directory / (record.activation_id + '.json')


def _read(path: Path) -> bytes | None:
    if not hasattr(os, "O_NOFOLLOW"):
        raise ConfigurationError("task overlays require macOS or Linux/WSL")
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ConfigurationError('task overlay is inaccessible or is a symlink') from exc
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 65536:
            raise ConfigurationError('task overlay must be a small regular file without hard links')
        return stream.read(65537)


def _applied(record: TaskActivation) -> bytes:
    return (record.model_dump_json(indent=2) + '\n').encode()


def _manifest_file_digest(path: Path) -> str | None:
    return file_digest(path) if path.exists() or path.is_symlink() else None


def _configuration_matches(router: Router, record: TaskActivation) -> bool:
    return (content_digest(router.manifest) == record.manifest_digest
            and _manifest_file_digest(Path(record.manifest_path)) == record.manifest_file_digest)


def require_activation(router: Router, identity: str) -> TaskActivation:
    record = _record(router, identity)
    with router.store._lock:
        row = router.store._connection.execute('SELECT revoked FROM assessment_reviews WHERE digest=?',
            (content_digest(record),)).fetchone()
    if row is None or row[0]:
        raise ConfigurationError('task activation is paused or incomplete')
    if _read(_path(record)) != _applied(record):
        raise ConfigurationError('task overlay changed or is absent; inspect before resuming')
    binding = get_binding(router, record)
    if binding is not None and (str(config_path(record)) != binding.config_path
            or entry_state(binding, read_config(Path(binding.config_path))) != 'applied'):
        raise ConfigurationError('project Codex MCP entry changed or is absent')
    if not _configuration_matches(router, record):
        raise ConfigurationError('task manifest changed; activate its reviewed configuration again')
    if record.capability_profile_digest is not None:
        from .profiles import require_profile
        profile = require_profile(router, record.capability_profile_digest, record.scope_digest)
        if record.host_binding != (profile.host == 'codex-project'):
            raise ConfigurationError('task activation host binding differs from its reviewed profile')
    return record


def _scope_ready(router: Router, digest: str) -> None:
    router.bind_task_scope(digest)
    scope = TaskScope.model_validate(AssessmentRepository(router.store).get('task_scope', digest))
    for executor_id in scope.executor_fingerprints:
        if not router.registry.contains(executor_id):
            raise ConfigurationError('task scope names an unavailable executor')
        spec = router.registry.get(executor_id)
        router._require_active_spec(spec, check_activation=False, configuration_only=True)
        router._require_task_scope(spec, activating=True)


def activate(router: Router, scope_id: str, *, replace: str | None = None,
             capability_profile_digest: str | None = None, host_binding: bool = True) -> TaskActivation:
    repo = AssessmentRepository(router.store)
    scope = TaskScope.model_validate(repo.get('task_scope', scope_id))
    if capability_profile_digest is not None:
        from .profiles import require_profile
        profile = require_profile(router, capability_profile_digest, content_digest(scope))
        if host_binding != (profile.host == 'codex-project'):
            raise ConfigurationError('task activation host binding differs from its reviewed profile')
    _scope_ready(router, content_digest(scope))
    assert router.manifest_path is not None
    previous = _record(router, replace) if replace else None
    if previous and _read(_path(previous)) != _applied(previous):
        raise ConfigurationError('previous task overlay changed; replacement requires conflict resolution')
    record = TaskActivation(scope_digest=content_digest(scope), manifest_digest=content_digest(router.manifest),
        manifest_path=str(router.manifest_path), manifest_file_digest=_manifest_file_digest(router.manifest_path),
        capability_profile_digest=capability_profile_digest, host_binding=host_binding)
    repo.put('task_activation', record.activation_id, record)  # Durable intent before touching disk.
    path = _path(record)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if record.host_binding and record.manifest_file_digest is not None:
        install_binding(router, record)
    with router.store._immediate_transaction() as connection:
        if previous and _read(_path(previous)) != _applied(previous):
            raise ConfigurationError('previous task overlay changed during replacement')
        with path.open('xb') as stream:
            os.chmod(path, 0o600)
            stream.write(_applied(record))
            stream.flush()
            os.fsync(stream.fileno())
        if previous:
            connection.execute('UPDATE assessment_reviews SET revoked=1 WHERE digest=?', (content_digest(previous),))
        connection.execute('INSERT INTO assessment_reviews VALUES (?, ?, 0)', (content_digest(record), utc_now().isoformat()))
        event = TaskLifecycleEvent(activation_digest=content_digest(record), operation='replace' if previous else 'activate')
        repo._put(connection, 'task_lifecycle', event.event_id, event)
    return record


def change_state(router: Router, identity: str, operation: Literal['pause', 'stop', 'resume', 'rollback', 'uninstall']) -> dict[str, object]:
    record = _record(router, identity)
    repo = AssessmentRepository(router.store)
    digest = content_digest(record)
    if operation == 'resume':
        if record.capability_profile_digest is not None:
            from .profiles import require_profile
            require_profile(router, record.capability_profile_digest, record.scope_digest)
        _scope_ready(router, record.scope_digest)
        if not _configuration_matches(router, record) or _read(_path(record)) != _applied(record):
            raise ConfigurationError('task configuration changed or is absent; resume rejected')
        binding = get_binding(router, record)
        if binding is not None and entry_state(binding, read_config(Path(binding.config_path))) != 'applied':
            raise ConfigurationError('project Codex MCP entry changed or is absent; resume rejected')
    # Revoke first, durably. A restore conflict or crash must not leave dispatch permitted.
    event = TaskLifecycleEvent(activation_digest=digest, operation=operation)
    with router.store._immediate_transaction() as connection:
        connection.execute(
            'INSERT INTO assessment_reviews VALUES (?, ?, ?) ON CONFLICT(digest) DO UPDATE SET revoked=excluded.revoked, approved_at=excluded.approved_at',
            (digest, utc_now().isoformat(), int(operation != 'resume')))
        repo._put(connection, 'task_lifecycle', event.event_id, event)
    if operation in {'rollback', 'uninstall'}:
        remove_binding(router, record)
        path = _path(record)
        current = _read(path)
        if current is not None:
            if current != _applied(record):
                raise ConfigurationError('restoration conflict: user-edited overlay preserved; activation paused')
            path.unlink()
    return inspect(router, identity)


async def watch_stop(router: Router, activation_digest: str, cancel: Callable[[], Awaitable[None]], after: int) -> None:
    """Session-owned cancellation; never signal PIDs belonging to another session."""
    try:
        while True:
            with router.store._lock:
                row = router.store._connection.execute(
                    "SELECT 1 FROM assessment_records WHERE rowid>? AND kind='task_lifecycle' AND json_extract(payload_json,'$.activation_digest')=? AND json_extract(payload_json,'$.operation')='stop' LIMIT 1",
                    (after, activation_digest)).fetchone()
            if row:
                await cancel()
                return
            await asyncio.sleep(0.1)
    except Exception:
        await cancel()
        raise


def inspect(router: Router, identity: str) -> dict[str, object]:
    record = _record(router, identity)
    repo = AssessmentRepository(router.store)
    scope = TaskScope.model_validate(repo.get('task_scope', record.scope_digest))
    with router.store._lock:
        row = router.store._connection.execute('SELECT revoked FROM assessment_reviews WHERE digest=?',
            (content_digest(record),)).fetchone()
        scope_review = router.store._connection.execute('SELECT revoked FROM assessment_reviews WHERE digest=?',
            (record.scope_digest,)).fetchone()
        attempts = router.store._connection.execute(
            "SELECT attempt_id,state FROM execution_attempts WHERE json_extract(payload_json,'$.task_scope_digest')=?",
            (record.scope_digest,)).fetchall()
    try:
        contents = _read(_path(record))
        overlay = 'absent' if contents is None else 'applied' if contents == _applied(record) else 'conflict'
    except ConfigurationError:
        overlay = 'conflict'
    binding = get_binding(router, record)
    try:
        host_contents = read_config(Path(binding.config_path)) if binding else None
        codex_entry = ('in_process_only' if binding is None and (not record.host_binding or record.manifest_file_digest is None)
                       else 'none' if binding is None else entry_state(binding, host_contents))
    except ConfigurationError:
        codex_entry = 'conflict'
    return dict(activation_id=record.activation_id, activation_digest=content_digest(record),
        scope_digest=record.scope_digest, reviewed=row is not None and not bool(row[0]),
        scope_reviewed=scope_review is not None and not bool(scope_review[0]),
        overlay=overlay, owned_files=[str(_path(record)), *([str(lock_path(record))] if binding else [])],
        codex_mcp_entry=codex_entry, project_host_config=str(config_path(record)) if binding else None,
        retained_artifacts=[str(lock_path(record))] if binding else [],
        persistent_host_changes=[binding.config_path] if binding and codex_entry != 'absent' else [],
        scope_expired=utc_now() >= scope.expires_at, attempts_used=len(attempts),
        attempts_remaining=max(0, scope.max_attempts-len(attempts)),
        recovery_attempts=[r[0] for r in attempts if r[1] not in {'COMPLETED','FAILED','REJECTED','CANCELLED'}],
        lifecycle='session-scoped', accounting_retained=True)


def reconcile(router: Router, identity: str) -> dict[str, object]:
    """Close a reviewed local attempt only after explicit operator effect inspection."""
    repo = AssessmentRepository(router.store)
    record = TaskReconciliation.model_validate(repo.get('task_reconciliation', identity))
    with router.store._immediate_transaction() as connection:
        reviewed = connection.execute('SELECT revoked FROM assessment_reviews WHERE digest=?', (content_digest(record),)).fetchone()
        if reviewed is None or reviewed[0]:
            raise ConfigurationError('task reconciliation requires exact operator review')
        for evidence in record.evidence_digests:
            if not connection.execute('SELECT 1 FROM assessment_records WHERE digest=?', (evidence,)).fetchone():
                raise ConfigurationError('reconciliation evidence is not present in the existing store')
        attempt = router.store.get_execution_attempt(record.attempt_id)
        if (attempt is None or attempt.task_scope_digest != record.scope_digest or attempt.version != record.attempt_version
                or attempt.state not in {ExecutionAttemptState.INDETERMINATE, ExecutionAttemptState.DISPUTED}
                or attempt.cash_reservation_ids or attempt.capacity_reservation_ids or not attempt.terminal_receipt_ids):
            raise ConfigurationError('reconciliation requires the exact unresolved local attempt with recorded accounting')
        scope = TaskScope.model_validate(repo.get('task_scope', record.scope_digest))
        if router.manifest_path is None or router.manifest_path.parent != Path(scope.project_root):
            raise ConfigurationError('reconciliation belongs to another project')
        if any(router.store.get_receipt(receipt_id) is None for receipt_id in attempt.terminal_receipt_ids):
            raise ConfigurationError('reconciliation accounting receipts are unavailable')
        # Reuse the store's compare-and-set journal under one transaction, so a
        # crash cannot leave a half-reconciled SETTLING attempt or lose revocation.
        final = attempt
        for state in (ExecutionAttemptState.SETTLING, ExecutionAttemptState.COMPLETED if record.resolution == 'effects_verified'
                      else ExecutionAttemptState.FAILED):
            if not final.can_transition_to(state):
                raise ConfigurationError('illegal reconciliation state transition')
            updated = ExecutionAttempt.model_validate({**final.model_dump(mode='python'), 'state': state,
                'version': final.version+1, 'updated_at': max(final.updated_at, utc_now())})
            router.store._save_attempt_update_locked(connection, final, updated,
                reason='operator effect reconciliation: ' + content_digest(record))
            final = updated
    return dict(attempt_id=final.attempt_id, state=final.state.value, reconciliation_digest=content_digest(record),
        evidence_origin='operator-reviewed inspection', automated_verification=False, allowance_reset=False)
