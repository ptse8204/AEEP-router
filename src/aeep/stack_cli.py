"""Stack preparation and operator execution commands."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import typer

from .models import SideEffect
from .provider_setup import ProviderSetupDefinition, ProviderSetupService
from .router import Router
from .stack_models import GoalSpec, StackRecovery
from .stack_planning import StackService
from .stack_runtime import StackRuntime

app = typer.Typer(help='Propose compatible configurations, inspect setup, and execute reviewed stacks.')
setup_app = typer.Typer(help='Operator-owned provider setup definitions and non-charging checks.')
app.add_typer(setup_app, name='setup')


def emit(value: Any) -> None:
    typer.echo(value.model_dump_json(indent=2) if hasattr(value, 'model_dump_json') else json.dumps(value, indent=2))


@app.callback()
def configure(ctx: typer.Context, manifest: Path = typer.Option(..., '--manifest', '-m')) -> None:
    router = Router.from_manifest(manifest)
    ctx.obj = StackService(router)
    ctx.call_on_close(lambda: asyncio.run(router.close()))


@app.command()
def propose(ctx: typer.Context, goal: Path, parent: str | None = None) -> None:
    if parent:
        ctx.obj.inspect(parent)
    emit(ctx.obj.propose(GoalSpec.model_validate_json(goal.read_bytes()), parent_id=parent))


@app.command()
def inspect(ctx: typer.Context, proposal: str) -> None:
    emit(ctx.obj.inspect(proposal))


@app.command()
def optimize(ctx: typer.Context, proposal: str, policy: str = typer.Option(...)) -> None:
    emit(ctx.obj.optimize(proposal, policy))


@app.command()
def preflight(ctx: typer.Context, proposal: str) -> None:
    emit(ctx.obj.preflight(proposal))


@app.command()
def compile(ctx: typer.Context, proposal: str, inputs: Path) -> None:
    """Print a transient workflow containing caller-supplied task values."""
    emit(ctx.obj.compile(proposal, json.loads(inputs.read_bytes())))


@app.command()
def assemble(ctx: typer.Context, proposal: str, profile: str | None = None) -> None:
    emit(StackRuntime(ctx.obj).assemble(proposal, profile_id=profile))


@app.command()
def run(ctx: typer.Context, proposal: str, inputs: Path,
        approved_side_effect: SideEffect = SideEffect.READ,
        profile: str | None = None) -> None:
    runtime = StackRuntime(ctx.obj)
    runtime.assemble(proposal, profile_id=profile)
    emit(asyncio.run(runtime.run(proposal, json.loads(inputs.read_bytes()), approved_side_effect=approved_side_effect)))


@app.command()
def resume(ctx: typer.Context, proposal: str, inputs: Path, artifacts: Path,
           approved_side_effect: SideEffect = SideEffect.READ, delegated: Path | None = None) -> None:
    emit(asyncio.run(StackRuntime(ctx.obj).run(proposal, json.loads(inputs.read_bytes()),
        completed_outputs=json.loads(artifacts.read_bytes()),
        delegated_outputs=json.loads(delegated.read_bytes()) if delegated else None,
        approved_side_effect=approved_side_effect)))


@app.command()
def amend(ctx: typer.Context, previous: str, successor: str) -> None:
    emit(StackRuntime(ctx.obj).amend(previous, successor))


@setup_app.command('define')
def define_setup(ctx: typer.Context, definition: Path) -> None:
    service = ProviderSetupService(ctx.obj.router.store)
    parsed = ProviderSetupDefinition.model_validate_json(definition.read_bytes())
    emit({'setup_id': parsed.setup_id, 'digest': service.define(parsed), 'reviewed': False})


@setup_app.command('inspect')
def inspect_setup(ctx: typer.Context, setup: str) -> None:
    emit(ProviderSetupService(ctx.obj.router.store).inspect(setup))


@setup_app.command('check')
def check_setup(ctx: typer.Context, setup: str) -> None:
    emit(asyncio.run(ProviderSetupService(ctx.obj.router.store).check(setup)))


@app.command('recovery-define')
def define_recovery(ctx: typer.Context, definition: Path) -> None:
    parsed = StackRecovery.model_validate_json(definition.read_bytes())
    emit({'digest': ctx.obj.repository.put('stack_recovery', parsed.recovery_id, parsed), 'reviewed': False})


@app.command()
def reconcile(ctx: typer.Context, recovery: str, artifact: Path) -> None:
    emit(StackRuntime(ctx.obj).reconcile(recovery, json.loads(artifact.read_bytes())))
