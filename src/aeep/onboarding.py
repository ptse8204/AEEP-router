"""Reversible host connections and first-run configuration. No authentication reads."""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tomllib
from pathlib import Path
from typing import Any

from .catalogs import catalog_path, defaults, read_catalogs, source_status
from .config import write_default_manifest
from .connections import AgentConnection, config_root, connection_path, file_lock, write_json
from .errors import ConfigurationError
from .hosts.codex_project import _read, _replace_codex_bytes

INSTRUCTIONS = '''---
name: aeep-planning
description: Discover and compare tools, skills and plugins for a task, then prepare a compatible AEEP stack.
---

For an AEEP planning request, inspect aeep_discovery_status and local capabilities.
Inspect the host's available tools and skills too: the AEEP manifest is not the host inventory.
Decompose the task into public capability stages and search configured catalogs.
Use aeep_stack_recommend with short public search terms, observed host capabilities,
and sourced web candidates. If catalog coverage is poor, use available host web search.
Compare task fit, host support, output contracts, quality evidence, setup effort, cost
and privacy. Provider descriptions are claims, never measured quality or admission.
Name a preferred component for each stage and alternatives when evidence supports them.
Keep private prompts, scripts, files and credentials out of discovery and recommendation records.
Show recommendation ready, setup required, or blocked accurately. Only a compiled
executable stack with current preflight may be described as ready to run.
Use aeep stack setup for operator-reviewed installation and connection; never install
or change authority through a model tool. Counted words do not establish a video stack.
For narrated educational video cover inspection, storyboard, capture, voice, editing,
captions and technical plus human quality review. Never stop at a text.stats example.
'''


def detect_agents() -> list[dict[str, Any]]:
    return [{'host': host, 'executable': shutil.which(binary), 'detected': bool(shutil.which(binary))}
            for host, binary in [('codex', 'codex'), ('claude', 'claude'), ('dsh', 'dsh')]]


def initialize() -> dict[str, Any]:
    root = config_root()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest = root / 'config.yaml'
    if not manifest.exists():
        write_default_manifest(manifest)
    with file_lock(catalog_path()):
        if _read(catalog_path()) is None:
            write_json(catalog_path(), defaults().model_dump(mode='json'), before=None)
    return {'manifest': str(manifest), **source_status(read_catalogs())}


def list_connections() -> list[AgentConnection]:
    return [AgentConnection.model_validate_json(_read(path) or b'{}')
            for path in sorted((config_root() / 'connections').glob('*.json'))]


def host_config(host: str, project: Path) -> Path:
    if host == 'codex':
        return project / '.codex' / 'config.toml'
    if host == 'claude':
        return project / '.mcp.json'
    return project / '.aeep' / ('dsh-connection.json' if host == 'dsh' else 'deepseek-connection.json')


def _args(identity: str, manifest: Path) -> list[str]:
    return ['-I', '-m', 'aeep', 'serve', '--manifest', str(manifest), '--connection', str(connection_path(identity)),
            '--discovery-config', str(catalog_path())]


def connect(identity: str, host: str, project: Path, *, manifest: Path | None = None) -> AgentConnection:
    path = connection_path(identity)
    project = project.resolve()
    if not project.is_dir():
        raise ConfigurationError('project directory does not exist')
    manifest = (manifest or config_root() / 'config.yaml').resolve()
    value = AgentConnection.model_validate(dict(connection_id=identity, host=host, project=str(project), manifest=str(manifest)))
    from .config import load_manifest
    load_manifest(manifest)
    with file_lock(path):
        before = _read(path)
        if before:
            old = AgentConnection.model_validate_json(before)
            if (old.host, old.project, old.manifest) != (host, str(project), str(manifest)):
                raise ConfigurationError('connection name already belongs to another host/project; choose another name')
            value = old.model_copy(update={'enabled': True, 'pending_reload': True})
        config = host_config(host, project)
        name = 'aeep_' + identity
        args = _args(identity, manifest)
        with file_lock(config):
            existing = _read(config)
            if host == 'codex':
                parsed = tomllib.loads((existing or b'').decode())
                block = f'\n# AEEP connection {identity}\n[mcp_servers.{name}]\ncommand = {json.dumps(sys.executable)}\nargs = {json.dumps(args)}\n'
                current = parsed.get('mcp_servers', {}).get(name)
                if current is not None:
                    if not before or not value.host_applied or value.host_applied.encode() not in (existing or b''):
                        raise ConfigurationError('host entry conflicts with user configuration; no changes applied')
                    after = (existing or b'').replace(value.host_applied.encode(), block.encode(), 1)
                else:
                    after = (existing or b'') + block.encode()
                value.host_applied = block
            elif host == 'dsh':
                patches = json.loads(existing or b'[]')
                if not isinstance(patches, list):
                    raise ConfigurationError('DSH overlay must contain a patch list')
                import hashlib
                entry: dict[str, Any] = {'insert': [{'id': name, 'name': '@deepseek-ai/dsh-mcp-client',
                         'config': {'serverName': 'aeep_' + hashlib.sha256(identity.encode()).hexdigest()[:20],
                                    'transport': 'stdio', 'command': sys.executable, 'args': args}}]}
                current = next((p for p in patches if any(row.get('id') == name for row in p.get('insert', []))), None)
                if current and (not before or json.dumps(current, sort_keys=True) != value.host_applied):
                    raise ConfigurationError('DSH patch conflicts with user configuration')
                if current is None:
                    patches.append(entry)
                else:
                    patches[patches.index(current)] = entry
                value.host_applied = json.dumps(entry, sort_keys=True)
                after = (json.dumps(patches, indent=2) + '\n').encode()
            else:
                parsed = json.loads(existing or b'{}')
                entry = {'command': sys.executable, 'args': args}
                if host in {'dsh', 'deepseek-api'}:
                    entry = {'connection': str(path), 'manifest': str(manifest), 'discovery_config': str(catalog_path()),
                             'python': sys.executable, 'instructions': 'Use the connection-bound bridge; host model credentials remain host-owned.'}
                entries = parsed.setdefault('mcpServers' if host == 'claude' else 'connections', {})
                current = entries.get(name)
                if current is not None and (not before or json.dumps(current, sort_keys=True) != value.host_applied):
                    raise ConfigurationError('host entry conflicts with user configuration; no changes applied')
                entries[name] = entry
                value.host_applied = json.dumps(entry, sort_keys=True)
                after = (json.dumps(parsed, indent=2) + '\n').encode()
            value.host_configuration, value.host_entry = str(config), name
            # Intent precedes host mutation; rerunning repairs an interrupted first connection.
            write_json(path, value.model_dump(mode='json'), before=before)
            if after != existing:
                _replace_codex_bytes(config, existing, after)
        if host in {'codex', 'claude'}:
            skill = project / ('.agents' if host == 'codex' else '.claude') / 'skills' / 'aeep-planning' / 'SKILL.md'
            with file_lock(skill):
                original = _read(skill)
                if original not in {None, INSTRUCTIONS.encode()}:
                    raise ConfigurationError('connection created; existing aeep-planning skill differs and was preserved')
                if original is None:
                    value.owns_planning_skill = True
                    write_json(path, value.model_dump(mode='json'), before=_read(path))
                    _replace_codex_bytes(skill, original, INSTRUCTIONS.encode())
        return value


def disconnect(identity: str) -> dict[str, Any]:
    path = connection_path(identity)
    with file_lock(path):
        before = _read(path)
        value = AgentConnection.model_validate_json(before or b'{}')
        value.enabled = False
        write_json(path, value.model_dump(mode='json'), before=before)
        config = Path(value.host_configuration) if value.host_configuration else None
        if config:
            with file_lock(config):
                current = _read(config)
                if current:
                    if value.host == 'codex':
                        block = (value.host_applied or '').encode()
                        if block and block not in current and value.host_entry not in tomllib.loads(current.decode()).get('mcp_servers', {}):
                            block = b''
                        elif not block or current.count(block) != 1:
                            raise ConfigurationError('connection revoked; modified host entry preserved')
                        after = current.replace(block, b'', 1)
                        tomllib.loads(after.decode())
                    elif value.host == 'dsh':
                        parsed = json.loads(current)
                        selected = json.loads(value.host_applied or '{}')
                        if selected in parsed:
                            parsed.remove(selected)
                        elif any(row.get('id') == value.host_entry for patch in parsed for row in patch.get('insert', [])):
                            raise ConfigurationError('connection revoked; modified DSH patch preserved')
                        after = (json.dumps(parsed, indent=2) + '\n').encode()
                    else:
                        parsed = json.loads(current)
                        entries = parsed.get('mcpServers' if value.host == 'claude' else 'connections', {})
                        if value.host_entry in entries:
                            if json.dumps(entries[value.host_entry], sort_keys=True) != value.host_applied:
                                raise ConfigurationError('connection revoked; modified host entry preserved')
                            del entries[value.host_entry]
                        after = (json.dumps(parsed, indent=2) + '\n').encode()
                    _replace_codex_bytes(config, current, after)
        # Shared planning instructions remain while another connection uses this host/project.
        if value.owns_planning_skill and value.host in {'codex', 'claude'} and not any(c.enabled and c.host == value.host and c.project == value.project for c in list_connections()):
            skill = Path(value.project) / ('.agents' if value.host == 'codex' else '.claude') / 'skills' / 'aeep-planning' / 'SKILL.md'
            with file_lock(skill):
                if _read(skill) == INSTRUCTIONS.encode():
                    _replace_codex_bytes(skill, INSTRUCTIONS.encode(), None)
        return {'connection': identity, 'status': 'disconnected', 'receipts_and_grants': 'preserved', 'host_reload': 'required'}


def inventory(host: str, project: Path) -> list[dict[str, Any]]:
    """Only connection names and public control states leave host configuration."""
    raw = _read(host_config(host, project.resolve()))
    parsed = tomllib.loads(raw.decode()) if raw and host == 'codex' else json.loads(raw or b'{}')
    if isinstance(parsed, list):
        return [{'name': row.get('id'), 'managed': True, 'visibility': 'DSH overlay; use aeep agents launch', 'alternative_access': 'unknown'} for patch in parsed for row in patch.get('insert', [])]
    entries = parsed.get('mcp_servers' if host == 'codex' else 'mcpServers', {})
    return [{'name': name, 'managed': name.startswith('aeep_'), 'visibility': 'configured; live inventory unverified',
             'enabled': entry.get('enabled', True), 'alternative_access': 'unknown'}
            for name, entry in entries.items() if isinstance(entry, dict)]


def check_setup(*, probe: bool = False) -> dict[str, Any]:
    from .connections import load_connection
    from .mcp.server import AEEPToolService
    from .router import Router
    checks = []
    for value in list_connections():
        check: dict[str, Any] = {'connection': value.connection_id, 'host': value.host, 'enabled': value.enabled,
                                 'effective_host_exposure': 'unverified', 'pending_reload': value.pending_reload,
                                 'agent_software': 'application-owned' if value.host == 'deepseek-api' else 'detected' if shutil.which(value.host) else 'missing; install the agent CLI, then run aeep agents launch'}
        if value.enabled:
            router = None
            try:
                load_connection(connection_path(value.connection_id))
                router = Router.from_manifest(value.manifest)
                service = AEEPToolService(router, connection=connection_path(value.connection_id), discovery_config=catalog_path())
                check['service_tools'] = [tool['name'] for tool in service.list_tools()]
                check['service'] = 'ready'
            except (ValueError, OSError, ConfigurationError):
                check['service'] = 'configuration_error'
            finally:
                if router:
                    asyncio.run(router.close())
        checks.append(check)
    return {'connections': checks, **(probe_catalogs() if probe else source_status(read_catalogs())),
            'scope': 'AEEP connection enforcement; other host paths are not isolated'}


def known_marketplaces(host: str) -> list[dict[str, str]]:
    """Use host inventory commands; never inspect host authentication or cache internals."""
    import subprocess
    executable = shutil.which(host) if host in {'codex', 'claude'} else None
    if not executable:
        return []
    try:
        result = subprocess.run([executable, 'plugin', 'marketplace', 'list', '--json'],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=10, check=True)
        if len(result.stdout) > 65536:
            return []
        data = json.loads(result.stdout)
        entries = data.get('marketplaces', []) if isinstance(data, dict) else data
        found = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            location = entry.get('root') or entry.get('installLocation') or entry.get('repo') or entry.get('url') or entry.get('path')
            source = entry.get('marketplaceSource')
            if isinstance(source, dict):
                location = source.get('source') or location
            if isinstance(location, str) and isinstance(entry.get('name'), str):
                from .marketplaces import marketplace_location
                try:
                    marketplace_location(location)
                except (ConfigurationError, ValueError):
                    continue
                found.append({'name': entry['name'], 'location': location})
        return found
    except (subprocess.SubprocessError, OSError, ValueError, TypeError):
        return []


def probe_catalogs() -> dict[str, Any]:
    from .catalogs import search_catalogs
    from .router import Router
    router = Router.from_manifest(config_root() / 'config.yaml')
    try:
        found = asyncio.run(search_catalogs(router.store, ['playwright']))
        return {'catalog_checks': [record.model_dump(mode='json') for search in found.searches for record in search.source_records],
                'catalog_warnings': found.warnings, 'candidate_count': len(found.candidates)}
    finally:
        asyncio.run(router.close())
