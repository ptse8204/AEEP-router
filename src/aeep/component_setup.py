"""Operator-reviewed component installation; no discovery-supplied commands."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from .assessment.models import content_digest
from .assessment.repository import AssessmentRepository
from .connections import AgentConnection, config_root, connection_path, file_lock, write_json
from .errors import ConfigurationError
from .hosts.codex_project import _read, _replace_codex_bytes
from .marketplaces import public_url
from .models import StrictModel
from .router import Router


def require_space(path: Path, additional_bytes: int = 0) -> None:
    target = path
    while not target.exists():
        target = target.parent
    if shutil.disk_usage(target).free - additional_bytes < 50 * 1024**3:
        raise ConfigurationError('installation would cross the 50 GiB free-space reserve; inspect obsolete AEEP staging directories before continuing')


class ComponentSetup(StrictModel):
    schema_version: Literal['aeep.component-setup.v1'] = 'aeep.component-setup.v1'
    connection_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    candidate_id: str = Field(min_length=1, max_length=300)
    candidate_digest: str = Field(pattern=r'^sha256:[a-f0-9]{64}$')
    kind: Literal['npm', 'python', 'https-mcp', 'marketplace']
    package: str = Field(min_length=1, max_length=2048)
    version: str | None = None
    executable: str | None = Field(default=None, pattern=r'^[A-Za-z0-9_-]{1,100}$')
    plugin: str | None = Field(default=None, pattern=r'^[A-Za-z0-9_-]{1,100}$')
    marketplace: str | None = Field(default=None, pattern=r'^[A-Za-z0-9_-]{1,100}$')
    lifecycle_scripts: bool = False

    @model_validator(mode='after')
    def pinned(self) -> ComponentSetup:
        if self.kind in {'https-mcp', 'marketplace'}:
            public_url(self.package)
        elif not re.fullmatch(r'(?:@[a-zA-Z0-9_.-]+/)?[a-zA-Z0-9][a-zA-Z0-9_.-]*', self.package):
            raise ValueError('package must be an exact registry name')
        if self.kind == 'marketplace':
            if not self.version or not re.fullmatch(r'[a-f0-9]{40}', self.version) or not self.plugin or not self.marketplace:
                raise ValueError('marketplace setup requires an exact Git commit, plugin and marketplace name')
        elif self.kind in {'npm', 'python'} and (not self.version or not re.fullmatch(r'[0-9]+(?:\.[0-9]+)+(?:[A-Za-z0-9.+-]*)', self.version) or not self.executable):
            raise ValueError('stdio package setup requires an exact version and executable name')
        return self


def preview(router: Router, plan: ComponentSetup) -> dict[str, Any]:
    candidate = router.store.get_registry_candidate(plan.candidate_id)
    if candidate is None or candidate.raw_metadata_digest != plan.candidate_digest:
        raise ConfigurationError('candidate metadata changed or is absent; rediscover and review')
    connection = AgentConnection.model_validate_json(_read(connection_path(plan.connection_id)) or b'{}')
    if not connection.enabled or connection.manifest != str(router.manifest_path):
        raise ConfigurationError('setup connection is disabled or belongs to another manifest')
    if plan.kind == 'marketplace' and connection.host not in {'codex', 'claude'}:
        raise ConfigurationError('native plugin setup requires a Codex or Claude connection')
    digest = content_digest(plan)
    directory = config_root() / 'packages' / digest
    return {'digest': digest, 'candidate': candidate.name, 'source': plan.package, 'version': plan.version,
            'destination': str(directory), 'connection': plan.connection_id,
            'metadata_review': candidate.model_dump(mode='json'),
            'command_policy': 'Exact package/version and executable above; argv only, no catalog-supplied commands.',
            'effects': ['Download pinned package and dependencies',
                        ('Native Codex user-scope plugin registration can affect other projects' if connection.host == 'codex' else 'Native Claude plugin and marketplace registration in the selected project') if plan.kind == 'marketplace' else 'Write owned host connection',
                        'Plugin hooks may execute when the host loads a native plugin' if plan.kind == 'marketplace' else
                        'Package lifecycle scripts enabled' if plan.lifecycle_scripts else 'Package lifecycle/build scripts disabled'],
            'readiness': 'Installation does not qualify a route, establish output compatibility, sign in, or authorize paid execution.'}


def define(router: Router, plan: ComponentSetup) -> dict[str, Any]:
    result = preview(router, plan)
    AssessmentRepository(router.store).put('component_setup', result['digest'], plan)
    return result


def _run(argv: list[str], cwd: Path) -> None:
    # Output can contain provider secrets; retain only bounded command status.
    try:
        subprocess.run(argv, cwd=cwd, check=True, timeout=300, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (subprocess.SubprocessError, OSError) as exc:
        raise ConfigurationError('component setup command failed; inspect package state before explicitly retrying') from exc


def _connect_mcp(connection: AgentConnection, identity: str, entry: dict[str, Any]) -> None:
    from .onboarding import host_config
    if connection.host == 'dsh':
        path = host_config('dsh', Path(connection.project))
        config = {'serverName': identity, 'transport': 'streamable-http' if 'url' in entry else 'stdio', **entry}
        patch = {'insert': [{'id': identity, 'name': '@deepseek-ai/dsh-mcp-client', 'config': config}]}
        with file_lock(path):
            before = _read(path)
            patches = json.loads(before or b'[]')
            old = next((p for p in patches if any(row.get('id') == identity for row in p.get('insert', []))), None)
            if old is not None and old != patch:
                raise ConfigurationError('component DSH patch was edited; preserved')
            if old is None:
                patches.append(patch)
                write_json(path, patches, before=before)
        return
    if connection.host not in {'codex', 'claude'}:
        path = Path(connection.project) / '.aeep' / f'{identity}.json'
        with file_lock(path):
            before = _read(path)
            if before and json.loads(before) != entry:
                raise ConfigurationError('component connection was edited; preserved')
            write_json(path, entry, before=before)
        return
    if connection.host == 'claude':
        entry = {'type': 'http' if 'url' in entry else 'stdio', **entry}
    path = host_config(connection.host, Path(connection.project))
    with file_lock(path):
        before = _read(path)
        if connection.host == 'codex':
            import tomllib
            current = tomllib.loads((before or b'').decode()).get('mcp_servers', {}).get(identity)
            if current is not None:
                if current != entry:
                    raise ConfigurationError('component host entry already exists with different settings')
                return
            block = f'\n[mcp_servers.{identity}]\n' + ''.join(f'{key} = {json.dumps(value)}\n' for key, value in entry.items())
            after = (before or b'') + block.encode()
            tomllib.loads(after.decode())
        else:
            parsed = json.loads(before or b'{}')
            entries = parsed.setdefault('mcpServers', {})
            if identity in entries and entries[identity] != entry:
                raise ConfigurationError('component host entry already exists with different settings')
            entries[identity] = entry
            after = (json.dumps(parsed, indent=2) + '\n').encode()
        _replace_codex_bytes(path, before, after)


def inspect_native_catalog(checkout: Path, plan: ComponentSetup) -> None:
    from .discovery import _metadata_digest
    from .marketplaces import MarketplaceAdapter, _relative
    catalog, _origin, _host = MarketplaceAdapter(str(checkout), local=True).local_metadata()
    if catalog.get('name') != plan.marketplace:
        raise ConfigurationError('pinned catalog name differs from the reviewed marketplace')
    entries = catalog.get('plugins', [])
    if not isinstance(entries, list):
        raise ConfigurationError('pinned catalog plugin list is malformed')
    if any(isinstance(e, dict) and isinstance(e.get('source'), dict) and
           (e['source'].get('source') == 'command' or e['source'].get('headersHelper')) for e in entries):
        raise ConfigurationError('command-based catalog sources require an unsupported manual handoff; no host installer ran')
    selected = [e for e in entries if isinstance(e, dict) and e.get('name') == plan.plugin]
    if len(selected) != 1 or _metadata_digest(selected[0]) != plan.candidate_digest:
        raise ConfigurationError('pinned plugin metadata differs from the reviewed candidate')
    entry = selected[0]
    source = entry.get('source')
    relative = source if isinstance(source, str) else source.get('path') if isinstance(source, dict) and source.get('source') == 'local' else None
    if not isinstance(relative, str) or relative.startswith('https:'):
        raise ConfigurationError('native setup currently requires a plugin contained in the pinned catalog; remote sources need separate reviewed setup')
    directory = (checkout / _relative(relative)).resolve()
    if not directory.is_relative_to(checkout.resolve()) or not directory.is_dir():
        raise ConfigurationError('selected plugin is absent or escapes the pinned checkout')
    manifests = [entry]
    for name in ('.claude-plugin/plugin.json', '.codex-plugin/plugin.json'):
        path = directory / name
        if path.resolve() != path:
            raise ConfigurationError('plugin manifest must not contain symlinks')
        raw = _read(path)
        if raw:
            manifests.append(json.loads(raw))
    if any(not isinstance(m, dict) or m.get('dependencies') for m in manifests):
        raise ConfigurationError('native plugin dependencies need separate reviewed setup before installation')


def apply(router: Router, digest: str, *, retry_failed: bool = False) -> dict[str, Any]:
    repository = AssessmentRepository(router.store)
    plan = ComponentSetup.model_validate(repository.get('component_setup', digest))
    actual = content_digest(plan)
    with router.store._lock:
        reviewed = router.store._connection.execute('SELECT 1 FROM assessment_reviews WHERE digest=? AND revoked=0', (actual,)).fetchone()
    if digest != actual or not reviewed:
        raise ConfigurationError('component setup requires its exact operator review')
    result = preview(router, plan)
    connection = AgentConnection.model_validate_json(_read(connection_path(plan.connection_id)) or b'{}')
    root = Path(result['destination'])
    require_space(root, 1024**3)
    journal = config_root() / 'installations' / f'{digest}.json'
    with file_lock(journal):
        before = _read(journal)
        previous = json.loads(before) if before else {}
        if previous.get('status') == 'installed':
            return previous
        if previous and not retry_failed:
            raise ConfigurationError('previous setup interrupted or failed; inspect it, then use --retry-failed explicitly')
        write_json(journal, {'digest': digest, 'status': 'installing', 'destination': str(root)}, before=before)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if root.resolve() != root:
            raise ConfigurationError('package directory must not contain symlinks')
        try:
            if plan.kind == 'https-mcp':
                import asyncio

                import httpx

                from .executors.network import validate_http_url
                asyncio.run(validate_http_url(plan.package, {'allowed_hosts': [httpx.URL(plan.package).host]}, label='MCP setup'))
                _connect_mcp(connection, 'aeep_component_' + digest[:16], {'url': plan.package})
            elif plan.kind == 'npm':
                npm = shutil.which('npm')
                if not npm:
                    raise ConfigurationError('npm is required for this selected package; install Node.js then retry')
                _run([npm, 'install', '--prefix', str(root), '--no-audit', '--no-fund',
                      *([] if plan.lifecycle_scripts else ['--ignore-scripts']), f'{plan.package}@{plan.version}'], root)
                executable = root / 'node_modules' / '.bin' / str(plan.executable)
                if not executable.is_file() or not executable.resolve().is_relative_to(root):
                    raise ConfigurationError('package did not supply the selected executable')
                _connect_mcp(connection, 'aeep_component_' + digest[:16], {'command': str(executable), 'args': []})
            elif plan.kind == 'python':
                _run([sys.executable, '-m', 'venv', str(root / 'venv')], root)
                python = root / 'venv/bin/python'
                _run([str(python), '-m', 'pip', 'install', '--only-binary=:all:', f'{plan.package}=={plan.version}'], root)
                executable = root / 'venv/bin' / str(plan.executable)
                if not executable.is_file() or not executable.resolve().is_relative_to(root):
                    raise ConfigurationError('package did not supply the selected executable')
                _connect_mcp(connection, 'aeep_component_' + digest[:16], {'command': str(executable), 'args': []})
            else:
                git, host = shutil.which('git'), shutil.which(connection.host)
                if not git or not host:
                    raise ConfigurationError('Git and the selected agent CLI must be installed')
                checkout = root / 'repository'
                if not checkout.exists():
                    _run([git, '-c', 'core.hooksPath=/dev/null', 'clone', '--no-checkout', '--', plan.package, str(checkout)], root)
                _run([git, '-c', 'core.hooksPath=/dev/null', 'checkout', '--detach', str(plan.version)], checkout)
                inspect_native_catalog(checkout, plan)
                scope = ['--scope', 'project'] if connection.host == 'claude' else []
                native_source = str(checkout)
                if connection.host == 'claude' and plan.package.removesuffix('.git') == 'https://github.com/anthropics/claude-plugins-official':
                    native_source = f'anthropics/claude-plugins-official#{plan.version}'
                _run([host, 'plugin', 'marketplace', 'add', native_source, *scope], Path(connection.project))
                _run([host, 'plugin', 'add' if connection.host == 'codex' else 'install', f'{plan.plugin}@{plan.marketplace}', *scope], Path(connection.project))
            result = {'digest': digest, 'status': 'installed', 'destination': str(root),
                      'execution': 'not admitted; host connection only',
                      'connection_state': 'application handoff required; inspect the owned MCP descriptor' if connection.host == 'deepseek-api' else 'native connection configured; reload and verify',
                      'access_boundary': 'Native component connection is separate from AEEP routing; use explicit adoption for native filters.', 'next_step': 'Restart host, inspect exposed tools, then intake/map and preflight before AEEP execution.'}
        except Exception:
            write_json(journal, {'digest': digest, 'status': 'failed', 'destination': str(root)}, before=_read(journal))
            raise
        write_json(journal, result, before=_read(journal))
        return result
