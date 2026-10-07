"""Operator controls over connection filters and explicitly adopted host settings."""
from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

from .connections import AgentConnection, config_root, connection_path, file_lock, write_json
from .economic.prepared import executor_fingerprint
from .errors import ConfigurationError
from .hosts.codex_project import _read, _replace_codex_bytes


def change_access(identity: str, resource: str, allow: bool) -> AgentConnection:
    import asyncio

    from .integrations import export_tools
    from .router import Router
    path = connection_path(identity)
    with file_lock(path):
        before = _read(path)
        value = AgentConnection.model_validate_json(before or b'{}')
        router = Router.from_manifest(value.manifest)
        try:
            if router.registry.contains(resource):
                if allow:
                    # The filter cannot enable the underlying executor or change its approval ceiling.
                    value.executor_fingerprints[resource] = executor_fingerprint(router.registry.get(resource))
                    value.allowed_tools = sorted(set(value.allowed_tools) | {'aeep_execute_action', 'aeep_record_outcome'})
                else:
                    value.executor_fingerprints.pop(resource, None)
            elif resource in {t['name'] for t in export_tools('mcp')}:
                value.allowed_tools = sorted((set(value.allowed_tools) | {resource}) if allow else (set(value.allowed_tools) - {resource}))
            else:
                raise ConfigurationError('unknown executor or AEEP tool; use aeep access show')
            value.pending_reload = True
            write_json(path, value.model_dump(mode='json'), before=before)
            return value
        finally:
            asyncio.run(router.close())


def matrix(identity: str) -> dict[str, Any]:
    import asyncio

    from .integrations import export_tools
    from .router import Router
    value = AgentConnection.model_validate_json(_read(connection_path(identity)) or b'{}')
    router = Router.from_manifest(value.manifest)
    try:
        adopted = [json.loads(_read(p) or b'{}') for p in sorted((config_root() / 'adoptions').glob(f'{identity}-*.json'))]
        return {'connection': identity, 'host': value.host, 'project': value.project,
                'connection_state': 'configured' if value.enabled else 'disconnected',
                'native_controls': [{k: row.get(k) for k in ('path', 'rule', 'active')} for row in adopted],
                'tools': [{'name': t['name'], 'visible_in_aeep': value.enabled and t['name'] in value.allowed_tools,
                           'call_allowed_by_connection': value.enabled and t['name'] in value.allowed_tools}
                          for t in export_tools('mcp')],
                'executors': [{'name': s.id, 'registered': True,
                               'allowed_by_connection': value.enabled and value.executor_fingerprints.get(s.id) == executor_fingerprint(s),
                               'execution_authority': 'subject to existing policy, reviews, scope and runtime approval'} for s in router.registry.all()],
                'host_exposure': 'pending reload; unverified' if value.pending_reload else 'unverified',
                'unmanaged_alternative_access': 'unknown; use aeep agents inspect',
                'skills_and_hooks': 'host controls; loaded instructions require a new session'}
    finally:
        asyncio.run(router.close())


def _codex_filter(raw: bytes, server: str, replacement: list[str] | None) -> bytes:
    """Change one scalar list without reserializing unrelated TOML or secrets."""
    text = raw.decode()
    lines = text.splitlines(keepends=True)
    start, end = None, len(lines)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('['):
            if start is not None:
                end = index
                break
            try:
                if tomllib.loads(stripped) == {'mcp_servers': {server: {}}}:
                    start = index
            except tomllib.TOMLDecodeError:
                continue
    if start is None:
        raise ConfigurationError('server needs an explicit MCP table before adopting its tool filter')
    body = ''.join(lines[start + 1:end])
    matches = list(re.finditer(r'(?m)^[ \t]*disabled_tools[ \t]*=.*(?:\n|$)', body))
    if matches:
        match = matches[0]
        try:
            tomllib.loads(match.group())
        except tomllib.TOMLDecodeError as exc:
            raise ConfigurationError('multiline disabled_tools needs conversion to a single line before adoption') from exc
        body = body[:match.start()] + body[match.end():]
    field = '' if replacement is None else f'disabled_tools = {json.dumps(replacement)}\n'
    output = ''.join(lines[:start + 1]) + field + body + ''.join(lines[end:])
    tomllib.loads(output)
    return output.encode()


def adopt_filter(identity: str, server: str, tool: str, *, deny: bool) -> dict[str, Any]:
    """Manage one native deny rule. This does not proxy or qualify the server."""
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', server) or not re.fullmatch(r'[A-Za-z0-9_.*-]{1,100}', tool):
        raise ConfigurationError('server/tool names contain unsupported characters')
    value = AgentConnection.model_validate_json(_read(connection_path(identity)) or b'{}')
    if value.host not in {'codex', 'claude'}:
        raise ConfigurationError('native adoption supports Codex and Claude; use AEEP connection filters for other hosts')
    if value.host == 'codex' and '*' in tool:
        raise ConfigurationError('Codex tool filters require an exact tool name')
    project = Path(value.project)
    path = project / '.codex/config.toml' if value.host == 'codex' else project / '.claude/settings.json'
    journal = config_root() / 'adoptions' / f'{identity}-{server}-{tool.replace("*", "all")}.json'
    with file_lock(journal), file_lock(path):
        raw = _read(path) or b''
        if value.host == 'codex':
            parsed = tomllib.loads(raw.decode())
            entry = parsed.get('mcp_servers', {}).get(server)
            if not isinstance(entry, dict):
                raise ConfigurationError('unknown native server')
            old = entry.get('disabled_tools')
            rule = tool
        else:
            from .onboarding import inventory
            if server not in {item['name'] for item in inventory('claude', project)}:
                raise ConfigurationError('unknown native server')
            parsed = json.loads(raw or b'{}')
            old = parsed.get('permissions', {}).get('deny')
            rule = f'mcp__{server}__{tool}'
        if old is not None and (not isinstance(old, list) or not all(isinstance(x, str) for x in old)):
            raise ConfigurationError('native tool filter has an unsupported format')
        retained = _read(journal)
        previous = json.loads(retained) if retained else None
        if deny:
            updated = list(dict.fromkeys([*(old or []), rule]))
            # Carry the absent-field origin across rules so either restore order works.
            siblings = [json.loads(_read(p) or b'{}') for p in journal.parent.glob('*.json')]
            originally_absent = old is None or any(
                row.get('active') and row.get('path') == str(path) and row.get('server') == server
                and row.get('filter_was_absent') for row in siblings)
            record = {'path': str(path), 'server': server, 'rule': rule,
                      'previously_present': rule in (old or []), 'filter_was_absent': originally_absent, 'active': True}
            if previous and previous['active']:
                record = previous
            write_json(journal, record, before=retained)
        else:
            if not previous or not previous['active']:
                raise ConfigurationError('this rule was not adopted by AEEP')
            updated = list(old or []) if previous['previously_present'] else [x for x in (old or []) if x != rule]
        if value.host == 'codex':
            replacement: list[str] | None = updated
            if not deny and not updated and previous and previous.get('filter_was_absent') and rule in (old or []):
                replacement = None
            after = raw if updated == old or (not deny and rule not in (old or [])) else _codex_filter(raw, server, replacement)
        else:
            parsed.setdefault('permissions', {})['deny'] = updated
            after = (json.dumps(parsed, indent=2) + '\n').encode()
        _replace_codex_bytes(path, raw if raw else None, after)
        if not deny:
            assert previous is not None
            write_json(journal, {**previous, 'active': False}, before=retained)
    return {'connection': identity, 'server': server, 'tool': tool,
            'native_rule': 'deny' if deny else 'restored', 'reload_required': True,
            'scope': 'native host configuration only; other access paths and live enforcement unverified'}
