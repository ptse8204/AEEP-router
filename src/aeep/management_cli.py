"""Human-friendly entry points over the existing router and operator controls."""
from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any

import typer

from .access import adopt_filter, change_access, matrix
from .catalogs import read_catalogs, save_source, search_catalogs, source_status
from .connections import config_root
from .discovery_service import DiscoverySourceConfig
from .errors import AEEPError
from .marketplaces import marketplace_location
from .onboarding import (
    check_setup,
    connect,
    detect_agents,
    disconnect,
    initialize,
    inventory,
    list_connections,
)

agents = typer.Typer(help='Connect agents and inspect or adopt native tool controls.')
access = typer.Typer(help='Restrict tool exposure and calls without enlarging execution authority.')
catalogs = typer.Typer(help='Manage searchable metadata sources; never install their plugins automatically.')


def friendly(function: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(function)
    def run(*args: Any, **kwargs: Any) -> Any:
        try:
            return function(*args, **kwargs)
        except (AEEPError, ValueError, OSError) as exc:
            if kwargs.get('json_output'):
                typer.echo(json.dumps({'error': str(exc), 'error_type': type(exc).__name__}))
                raise typer.Exit(4) from exc
            raise typer.BadParameter(str(exc)) from exc
    return run


def show(value: Any, json_output: bool = False) -> None:
    if hasattr(value, 'model_dump'):
        value = value.model_dump(mode='json')
    if json_output:
        typer.echo(json.dumps(value, indent=2))
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, list):
                typer.echo(key.replace('_', ' ').capitalize() + ':')
                for row in item:
                    typer.echo('  ' + (' | '.join(f'{k}: {v}' for k, v in row.items()) if isinstance(row, dict) else str(row)))
            else:
                typer.echo(f'{key.replace("_", " ").capitalize()}: {item}')
    else:
        typer.echo(json.dumps(value, indent=2))


def confirm(summary: Any, yes: bool) -> None:
    if not yes:
        typer.echo(json.dumps(summary, indent=2), err=True)
    if not yes and not typer.confirm('Apply these changes?', default=False):
        raise typer.Abort()


@agents.command('list')
@friendly
def agents_list(json_output: bool = typer.Option(False, '--json')) -> None:
    show({'detected': detect_agents(), 'connections': [{'name': c.connection_id, 'host': c.host,
          'project': c.project, 'enabled': c.enabled} for c in list_connections()]}, json_output)


@agents.command('connect')
@friendly
def agents_connect(name: str, host: str = typer.Option(...), project: Path = typer.Option(Path('.')),
                   yes: bool = typer.Option(False, '--yes', '-y'), json_output: bool = typer.Option(False, '--json')) -> None:
    confirm({'connection': name, 'host': host, 'project': str(project.resolve()),
             'access': 'Discovery and planning only. Existing credentials and grants remain host-owned.'}, yes)
    initialize()
    result = connect(name, host, project)
    show({'connection': result.connection_id, 'status': 'configured; restart the host', 'manifest': result.manifest}, json_output)


@agents.command('launch')
@friendly
def agents_launch(name: str) -> None:
    """Start an installed agent with its configured project and DSH overlay."""
    import shutil
    import subprocess

    from .connections import connection_path, load_connection
    value = load_connection(connection_path(name))
    binary = shutil.which(value.host)
    if not binary:
        raise typer.BadParameter('Install the selected agent CLI first; AEEP does not install or authenticate it.')
    argv = [binary]
    if value.host == 'dsh':
        argv += ['--profile', 'web', '--patch', str(value.host_configuration)]
    elif value.host == 'deepseek-api':
        raise typer.BadParameter('Use the ConnectedTools application bridge for an API connection.')
    subprocess.run(argv, cwd=value.project, check=True)


@agents.command('inspect')
@friendly
def agents_inspect(name: str, json_output: bool = typer.Option(False, '--json')) -> None:
    values = [c for c in list_connections() if c.connection_id == name]
    if not values:
        raise typer.BadParameter('unknown connection')
    value = values[0]
    show({'connection': name, 'native_connections': inventory(value.host, Path(value.project)),
          'access': matrix(name)}, json_output)


@agents.command('disconnect')
@friendly
def agents_disconnect(name: str, yes: bool = typer.Option(False, '--yes', '-y'), json_output: bool = typer.Option(False, '--json')) -> None:
    confirm({'disconnect': name, 'effect': 'Revoke calls and remove unchanged AEEP-owned host entries.'}, yes)
    show(disconnect(name), json_output)


@agents.command('adopt')
@friendly
def agents_adopt(name: str, server: str, tool: str, restore: bool = False,
                 yes: bool = typer.Option(False, '--yes', '-y'), json_output: bool = typer.Option(False, '--json')) -> None:
    confirm({'connection': name, 'server': server, 'tool': tool, 'action': 'restore previous rule' if restore else 'deny in native host',
             'boundary': 'Native configuration; no whole-agent isolation or tool qualification.'}, yes)
    show(adopt_filter(name, server, tool, deny=not restore), json_output)


@access.command('show')
@access.command('explain')
@friendly
def access_show(name: str, json_output: bool = typer.Option(False, '--json')) -> None:
    show(matrix(name), json_output)


@access.command('allow')
@friendly
def access_allow(name: str, resource: str, yes: bool = typer.Option(False, '--yes', '-y'), json_output: bool = typer.Option(False, '--json')) -> None:
    confirm({'connection': name, 'allow': resource, 'authority': 'Existing policy and approval ceilings still apply.'}, yes)
    change_access(name, resource, True)
    show(matrix(name), json_output)


@access.command('deny')
@friendly
def access_deny(name: str, resource: str, json_output: bool = typer.Option(False, '--json')) -> None:
    change_access(name, resource, False)
    show(matrix(name), json_output)


@catalogs.command('list')
@friendly
def catalogs_list(json_output: bool = typer.Option(False, '--json')) -> None:
    show(source_status(read_catalogs()), json_output)


@catalogs.command('add')
@friendly
def catalogs_add(name: str, location: str, kind: str = 'marketplace', token_env: str | None = None,
                  yes: bool = typer.Option(False, '--yes', '-y'), json_output: bool = typer.Option(False, '--json')) -> None:
    values: dict[str, Any] = {'source_id': name, 'kind': kind}
    if kind == 'marketplace':
        path, url = marketplace_location(location)
        values.update(path=path, base_url=url, allow_remote=bool(url))
    elif kind in {'mcp', 'ard'}:
        values.update(base_url=location, allow_remote=True)
    elif kind == 'docker':
        values.update(catalog=location, allow_remote=True)
    elif kind == 'smithery':
        values.update(token_env=token_env, allow_remote=True)
    else:
        values.update(path=str(Path(location).resolve()))
    source = DiscoverySourceConfig.model_validate(values)
    confirm({'catalog': name, 'location': location, 'kind': kind, 'remote_public_queries': source.allow_remote}, yes)
    save_source(source)
    show({'catalog': name, 'status': 'configured; plugins remain uninstalled'}, json_output)


@catalogs.command('remove')
@friendly
def catalogs_remove(name: str, json_output: bool = typer.Option(False, '--json')) -> None:
    save_source(None, remove=name)
    show({'removed': name, 'installed_plugins': 'unchanged'}, json_output)


@catalogs.command('inspect')
@friendly
def catalogs_inspect(name: str, json_output: bool = typer.Option(False, '--json')) -> None:
    found = [s for s in read_catalogs().sources if s.source_id == name]
    if not found:
        raise typer.BadParameter('unknown source')
    show(found[0], json_output)


@catalogs.command('refresh')
@friendly
def catalogs_refresh(name: str, query: str = 'video', json_output: bool = typer.Option(False, '--json')) -> None:
    discover([query], source=[name], json_output=json_output)


def discover(terms: list[str], source: list[str] | None = None, json_output: bool = False) -> None:
    from .router import Router
    router = Router.from_manifest(config_root() / 'config.yaml')
    try:
        result = asyncio.run(search_catalogs(router.store, terms, source_ids=source or None))
        show(result if json_output else {'candidates': [{'name': c.name, 'id': c.registry_candidate_id, 'source': c.adapter_id,
             'description': c.description} for c in result.candidates], 'warnings': result.warnings,
             'sources': [s.model_dump(mode='json') for r in result.searches for s in r.source_records]}, json_output)
    finally:
        asyncio.run(router.close())


def setup(agent: list[str] | None = None, project: Path = Path('.'), yes: bool = False, json_output: bool = False) -> None:
    detected = detect_agents()
    if not agent and not yes:
        show({'detected': detected})
        choices = typer.prompt('Agents (comma-separated: codex, claude, dsh, deepseek-api; or none)', default=','.join(x['host'] for x in detected if x['detected']) or 'none')
        agent = [x.strip() for x in choices.split(',') if x.strip() != 'none']
    if not agent:
        agent = []
    if any(x not in {'codex', 'claude', 'dsh', 'deepseek-api'} for x in agent):
        raise typer.BadParameter('supported agents: codex, claude, dsh, deepseek-api')
    imports = []
    if not yes:
        from .onboarding import known_marketplaces
        for host in agent:
            for item in known_marketplaces(host):
                if typer.confirm(f"Also search existing {host} catalog {item['name']}?", default=False):
                    imports.append(item)
    additional = None if yes else typer.prompt('Existing marketplace repository, URL or directory (optional)', default='', show_default=False)
    confirm({'agents': agent, 'project': str(project.resolve()),
             'catalogs': ['Official MCP Registry', 'Anthropic official plugins'],
             'changes': 'AEEP runtime configuration, discovery sources, selected agent connections and planning skill. No plugin execution or payments.'}, yes)
    initialize()
    import hashlib
    for item in imports:
        catalogs_add('imported-' + hashlib.sha256(item['location'].encode()).hexdigest()[:12], item['location'], yes=True, json_output=False)
    if additional:
        catalogs_add('imported-' + hashlib.sha256(additional.encode()).hexdigest()[:12], additional, yes=True, json_output=False)
    for host in agent:
        connect(host, host, project)
    show(check_setup(probe=True), json_output)
    if not json_output:
        typer.echo('Restart connected hosts. Try: Use AEEP to recommend a narrated educational-video stack. Search catalogs and compare named tools.')


def menu() -> None:
    labels = ['Plan a task', 'Search tools and plugins', 'Manage agents', 'Manage tool access',
              'Manage catalogs', 'Check setup', 'Update or remove AEEP', 'Exit']
    while True:
        typer.echo('\nAEEP')
        for index, label in enumerate(labels, 1):
            typer.echo(f'  {index}. {label}')
        choice = typer.prompt('Choose', type=int, default=8)
        try:
            if choice == 8:
                return
            if choice == 1:
                typer.echo('In your connected agent: Use AEEP to plan [your task]. Inspect host tools, search catalogs, compare candidates, and show setup requirements.')
                goal = typer.prompt('Public stage JSON file to compare now (optional)', default='', show_default=False)
                if goal:
                    from .recommendations import RecommendationRequest, recommend
                    from .router import Router
                    router = Router.from_manifest(config_root() / 'config.yaml')
                    try:
                        show(asyncio.run(recommend(router, RecommendationRequest.model_validate_json(Path(goal).read_bytes()))))
                    finally:
                        asyncio.run(router.close())
            elif choice == 2:
                discover([typer.prompt('Public capability terms')])
            elif choice == 3:
                agents_list(False)
                action = typer.prompt('Action', default='inspect')
                name = typer.prompt('Connection name')
                if action == 'connect':
                    agents_connect(name, typer.prompt('Host'), Path(typer.prompt('Project', default=str(Path.cwd()))), False, False)
                elif action == 'disconnect':
                    agents_disconnect(name, False, False)
                else:
                    agents_inspect(name, False)
            elif choice == 4:
                name = typer.prompt('Connection name')
                access_show(name, False)
                action = typer.prompt('Action (allow, deny, back)', default='back')
                if action in {'allow', 'deny'}:
                    resource = typer.prompt('Exact executor or tool name')
                    if action == 'allow':
                        access_allow(name, resource, False, False)
                    else:
                        access_deny(name, resource, False)
            elif choice == 5:
                catalogs_list(False)
                action = typer.prompt('Action (add, remove, refresh, back)', default='back')
                if action == 'add':
                    catalogs_add(typer.prompt('Catalog name'), typer.prompt('Repository, URL or local directory'), yes=False, json_output=False)
                elif action == 'remove':
                    catalogs_remove(typer.prompt('Catalog name'), False)
                elif action == 'refresh':
                    catalogs_refresh(typer.prompt('Catalog name'), typer.prompt('Search term'), False)
            elif choice == 6:
                show(check_setup())
            elif choice == 7:
                from .installation import maintain
                action = typer.prompt('Action (update, uninstall, back)', default='back')
                if action != 'back':
                    confirm({'action': action, 'scope': 'AEEP-owned resources only; receipts retained'}, False)
                    show(maintain(action))
        except (AEEPError, ValueError, OSError, typer.BadParameter) as exc:
            typer.echo(f'Cannot complete: {exc}', err=True)


def register(app: typer.Typer) -> None:
    app.add_typer(agents, name='agents')
    app.add_typer(access, name='access')
    app.add_typer(catalogs, name='catalogs')

    @app.command('update')
    @friendly
    def update_command(yes: bool = typer.Option(False, '--yes', '-y'), json_output: bool = typer.Option(False, '--json')) -> None:
        from .installation import maintain
        confirm({'action': 'Install the latest published checksum-verified AEEP release; preserve configuration and rollback runtime.'}, yes)
        show(maintain('update'), json_output)

    @app.command('uninstall')
    @friendly
    def uninstall_command(yes: bool = typer.Option(False, '--yes', '-y'), json_output: bool = typer.Option(False, '--json')) -> None:
        from .installation import maintain
        confirm({'action': 'Disconnect AEEP-owned host entries and remove its unchanged launcher; retain evidence and runtimes.'}, yes)
        show(maintain('uninstall'), json_output)

    @app.command('setup')
    @friendly
    def setup_command(agent: list[str] = typer.Option([], '--agent'), project: Path = Path('.'),
                      yes: bool = typer.Option(False, '--yes', '-y'), json_output: bool = typer.Option(False, '--json')) -> None:
        setup(agent, project, yes, json_output)

    @app.command('discover')
    @friendly
    def discover_command(terms: list[str], source: list[str] = typer.Option([], '--source'),
                         json_output: bool = typer.Option(False, '--json')) -> None:
        discover(terms, source, json_output)

    @app.callback(invoke_without_command=True)
    def root(ctx: typer.Context) -> None:
        if ctx.invoked_subcommand is None:
            if sys.stdin.isatty():
                menu()
            else:
                typer.echo(ctx.get_help())
