"""Operator-only project task controls; never exported to evaluated agents."""

from __future__ import annotations

import asyncio
import json
import shlex
from enum import StrEnum
from pathlib import Path
from typing import Literal, cast

import typer

from . import profiles
from .assessment.models import content_digest
from .assessment.repository import AssessmentRepository
from .errors import AEEPError
from .models import ExecutionOutcome, TaskExecutionOutcome, TaskScope
from .router import Router
from .tasks import TaskReconciliation, activate, change_state, inspect, reconcile

app = typer.Typer(help='Enable, inspect, pause and remove project-local task activations.')


@app.callback()
def configure(ctx: typer.Context, manifest: Path = typer.Option(..., '--manifest', '-m')) -> None:
    router = Router.from_manifest(manifest)
    ctx.obj = router
    ctx.call_on_close(lambda: asyncio.run(router.close()))


@app.command('define')
def define_scope(ctx: typer.Context, file: Path) -> None:
    scope = TaskScope.model_validate_json(file.read_bytes())
    digest = AssessmentRepository(ctx.obj.store).put('task_scope', scope.scope_id, scope)
    typer.echo(json.dumps(dict(scope_id=scope.scope_id, digest=digest, reviewed=False)))


@app.command('profile-from-scope')
def profile_from_scope(ctx: typer.Context, scope: str, profile_id: str = typer.Option(..., '--profile-id')) -> None:
    """Export an inert capability profile from an existing task scope."""
    typer.echo(profiles.from_scope(ctx.obj, scope, profile_id=profile_id).model_dump_json(indent=2))


@app.command('define-profile')
def define_profile(ctx: typer.Context, file: Path) -> None:
    """Store an inert profile; review its exact digest with assess review."""
    profile = profiles.CapabilityProfile.model_validate_json(file.read_bytes())
    digest = profiles.define(ctx.obj, profile)
    typer.echo(json.dumps(dict(profile_id=profile.profile_id, digest=digest, reviewed=False)))


@app.command('profile-compile')
def compile_profile(ctx: typer.Context, profile: str) -> None:
    """Resolve configured components and unsupported controls without activation."""
    typer.echo(json.dumps(profiles.compile_profile(ctx.obj, profile)))


@app.command('profile-preflight')
def preflight_profile(ctx: typer.Context, profile: str) -> None:
    """Inspect profile bindings, required reviews and activation blockers."""
    typer.echo(json.dumps(profiles.preflight(ctx.obj, profile)))


@app.command('profile-diff')
def diff_profiles(ctx: typer.Context, before: str, after: str) -> None:
    """Compare stored declarations; effective host differences require evidence."""
    typer.echo(json.dumps(profiles.diff_profiles(profiles.load(ctx.obj, before), profiles.load(ctx.obj, after))))


@app.command('profile-inspect')
def inspect_profile(ctx: typer.Context, profile: str, activation: str | None = typer.Option(None, '--activation')) -> None:
    """Inspect the profile and optionally its activation and recorded use."""
    typer.echo(json.dumps(profiles.inspect(ctx.obj, profile, activation_id=activation)))


@app.command('activate-profile')
def activate_profile(ctx: typer.Context, profile: str, replace: str | None = None) -> None:
    """Activate an exactly reviewed profile under its existing task authority."""
    try:
        record = profiles.activate(ctx.obj, profile, replace=replace)
        typer.echo(json.dumps(profiles.inspect(ctx.obj, profile, activation_id=record.activation_id)))
    except (AEEPError, ValueError, OSError) as exc:
        from .cli import _fail
        _fail(exc, compact=True)


@app.command('activate')
def activate_scope(ctx: typer.Context, scope: str, replace: str | None = None) -> None:
    try:
        record = activate(ctx.obj, scope, replace=replace)
        typer.echo(json.dumps(inspect(ctx.obj, record.activation_id)))
    except (AEEPError, ValueError, OSError) as exc:
        from .cli import _fail
        _fail(exc, compact=True)


class Operation(StrEnum):
    INSPECT = 'inspect'
    PAUSE = 'pause'
    STOP = 'stop'
    RESUME = 'resume'
    ROLLBACK = 'rollback'
    UNINSTALL = 'uninstall'


@app.command('control')
def control(ctx: typer.Context, operation: Operation, activation: str, text: bool = typer.Option(False, '--text')) -> None:
    try:
        result = inspect(ctx.obj, activation) if operation == Operation.INSPECT else change_state(ctx.obj, activation,
            cast(Literal['pause', 'stop', 'resume', 'rollback', 'uninstall'], operation.value))
        typer.echo((f"Activation: {result['activation_id']}\nReviewed: {result['reviewed']}\nOwned configuration: overlay={result['overlay']}, MCP={result['codex_mcp_entry']}\nAttempts remaining: {result['attempts_remaining']}\nRecovery attempts: {len(cast(list[str], result['recovery_attempts']))}\nUser edits are preserved as conflicts; rollback undoes owned configuration, not task effects.") if text else json.dumps(result))
    except (AEEPError, ValueError, OSError) as exc:
        from .cli import _fail
        _fail(exc, compact=True)


@app.command('define-reconciliation')
def define_reconciliation(ctx: typer.Context, file: Path) -> None:
    record = TaskReconciliation.model_validate_json(file.read_bytes())
    digest = AssessmentRepository(ctx.obj.store).put('task_reconciliation', content_digest(record), record)
    typer.echo(json.dumps(dict(digest=digest, reviewed=False)))


@app.command('profile-capture')
def capture_profile(
    ctx: typer.Context, profile: str,
    activation: str | None = typer.Option(None, '--activation'),
    receipt: list[str] = typer.Option([], '--receipt'),
) -> None:
    """Record content-free configuration and selected receipt observations."""
    from .configuration_profile import capture
    try:
        typer.echo(capture(ctx.obj, profile, activation, receipt).model_dump_json())
    except (AEEPError, ValueError, OSError) as exc:
        from .cli import _fail
        _fail(exc, compact=True)


@app.command('reconcile')
def reconcile_attempt(ctx: typer.Context, digest: str) -> None:
    try:
        typer.echo(json.dumps(reconcile(ctx.obj, digest)))
    except (AEEPError, ValueError, OSError) as exc:
        from .cli import _fail
        _fail(exc, compact=True)


def result_text(value: TaskExecutionOutcome, *, controls: list[str] | None = None) -> str:
    """Text view of the same allowlisted result; never expose action/output payloads."""
    decision = value.decision
    lines = [value.summary, f"Route: {decision.selected or 'none'} ({decision.reason}).",
        f"Operator approval ceiling: {value.approval_ceiling.value}; backend scope requires separate evidence.",
        f"Changes verified: {value.changes_verified if value.changes_verified is not None else 'unknown'}.",
        f"Recovery: {value.recovery_state}. Scope: {value.task_scope_digest or 'not recorded'}."]
    for receipt in value.receipts:
        checked = ', '.join(f"{check.kind.value}: {'passed' if check.valid is True else 'failed' if check.valid is False else 'unknown'} ({check.trust.value})" for check in receipt.checks)
        lines.append(f"Receipt {receipt.receipt_id}: {checked or 'no checks recorded'}.")
    lines.extend(value.verification_limits)
    lines.append('Resources and spending: inspect receipt accounting; missing measurements are unknown, not zero.')
    if value.recovery_state == 'required':
        lines.append('Inspect and reconcile the recorded attempt before retrying; reconciliation requires operator review.')
    if controls:
        lines.extend(controls)
    else:
        lines.append('Pause/undo commands unavailable: no currently validated project activation supplied.')
    return '\n'.join(lines)


def control_commands(router: Router, activation: str | None, scope_digest: str | None) -> list[str] | None:
    if activation is None or router.manifest_path is None or not router.manifest_path.is_file():
        return None
    try:
        state = inspect(router, activation)
        if state['scope_digest'] != scope_digest:
            return ['Pause/undo commands unavailable: activation does not match the recorded task scope.']
    except (AEEPError, ValueError, OSError):
        return ['Pause/undo commands unavailable: activation or project binding could not be inspected.']
    prefix = ['aeep', 'task', '--manifest', str(router.manifest_path), 'control']
    return [f"{label}: {shlex.join([*prefix, operation, str(state['activation_id'])])}" for label, operation in
        [('Inspect', 'inspect'), ('Pause', 'pause'), ('Undo owned configuration', 'rollback')]]


@app.command('result')
def show_result(ctx: typer.Context, receipt_id: str, text: bool = typer.Option(False, '--text'),
                activation: str | None = typer.Option(None, '--activation')) -> None:
    """Inspect a task receipt; original output is not reconstructed or persisted."""
    router = ctx.obj
    try:
        receipt = router.store.get_receipt(receipt_id)
        if receipt is None:
            raise ValueError('unknown receipt')
        scope_digest = receipt.metadata.get('task_scope_digest')
        if not isinstance(scope_digest, str):
            raise ValueError('receipt has no recorded task scope')
        scope = TaskScope.model_validate(AssessmentRepository(router.store).get('task_scope', scope_digest))
        decision = router.store.get_decision(receipt.decision_id)
        if decision is None:
            raise ValueError('receipt decision is unavailable')
        value = router.task_outcome(ExecutionOutcome(ok=receipt.status.value == 'success', status=receipt.status,
            decision=decision, receipts=[receipt]), approved_side_effect=scope.approval_ceiling)
        value.task_scope_digest = scope_digest
        value.verification_limits.append('Receipt view: original task output and historical runtime approval are not retained; displayed ceiling is the recorded operator scope ceiling. Current controls do not establish historical permissions.')
        value.verification_limits.append(f'Recorded scope: at most {scope.max_attempts} attempts, each at most {scope.max_attempt_seconds:g}s, expires {scope.expires_at.isoformat()}. Pause/resume does not reset allowance.')
        commands = control_commands(router, activation, scope_digest) if text else None
        typer.echo(result_text(value, controls=commands) if text else value.model_dump_json())
    except (AEEPError, ValueError, OSError) as exc:
        from .cli import _fail
        _fail(exc, compact=True)
