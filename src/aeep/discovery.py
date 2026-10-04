"""Provider discovery from reviewed local catalogs and bounded remote registries."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import shutil
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.parse import urlencode

import httpx
import rfc8785
import yaml
from pydantic import Field, JsonValue, field_validator, model_validator

from .errors import ConfigurationError, ExecutorError, ProtocolError
from .executors.network import validate_http_url
from .models import ProviderDescriptor, RegistryConfig, StrictModel


class ProviderRegistry(Protocol):
    async def discover(self, capability: str) -> list[ProviderDescriptor]: ...


def _descriptors(value: Any) -> list[ProviderDescriptor]:
    if isinstance(value, dict) and "providers" in value:
        value = value["providers"]
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        raise ProtocolError("registry response must be a provider or provider list")
    return [ProviderDescriptor.model_validate(item) for item in value]


class LocalProviderRegistry:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    async def discover(self, capability: str) -> list[ProviderDescriptor]:
        paths = (
            sorted(self.path.glob("*.json")) + sorted(self.path.glob("*.yaml"))
            if self.path.is_dir()
            else [self.path]
        )
        found: list[ProviderDescriptor] = []
        for path in paths:
            try:
                text = path.read_text(encoding="utf-8")
                value = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
            except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
                raise ConfigurationError(f"cannot read provider registry {path}: {exc}") from exc
            for provider in _descriptors(value):
                if any(
                    definition.capability == capability for definition in provider.capabilities
                ) or any(executor.capability == capability for executor in provider.executors):
                    found.append(provider)
        return found


class RemoteProviderRegistry:
    def __init__(self, config: RegistryConfig) -> None:
        self.config = config

    async def discover(self, capability: str) -> list[ProviderDescriptor]:
        assert self.config.url is not None
        separator = "&" if "?" in self.config.url else "?"
        url = f"{self.config.url}{separator}{urlencode({'capability': capability})}"
        network_config = self.config.model_dump(mode="python", exclude_none=True)
        await validate_http_url(url, network_config, label="registry")
        try:
            async with (
                httpx.AsyncClient(
                    timeout=self.config.timeout_seconds,
                    follow_redirects=False,
                    trust_env=False,
                ) as client,
                client.stream("GET", url, headers={"accept": "application/json"}) as response,
            ):
                response.raise_for_status()
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > self.config.max_response_bytes:
                        raise ProtocolError("registry response exceeds configured size limit")
                    chunks.append(chunk)
            return _descriptors(json.loads(b"".join(chunks)))
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise ProtocolError(f"registry discovery failed: {exc}") from exc


class CompositeProviderRegistry:
    def __init__(self, configs: list[RegistryConfig]) -> None:
        self.registries: list[ProviderRegistry] = [
            LocalProviderRegistry(config.path)
            if config.kind == "local" and config.path is not None
            else RemoteProviderRegistry(config)
            for config in configs
            if config.enabled
        ]

    async def discover(self, capability: str) -> list[ProviderDescriptor]:
        providers: dict[str, ProviderDescriptor] = {}
        for registry in self.registries:
            for provider in await registry.discover(capability):
                previous = providers.get(provider.provider_id)
                if previous is not None:
                    raise ProtocolError(f"provider id collision for {provider.provider_id!r}")
                providers[provider.provider_id] = provider
        return [providers[key] for key in sorted(providers)]


class PackageLocatorKind(StrEnum):
    LOCAL = "local"
    HTTPS = "https"
    REPOSITORY = "repository"


class ProviderPackageLocator(StrictModel):
    kind: PackageLocatorKind
    value: str = Field(min_length=1, max_length=2048)
    subdirectory: str | None = Field(default=None, max_length=1024)


class RegistryQuery(StrictModel):
    query: str = Field(default="", max_length=500)
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=1000)


class RegistryCandidate(StrictModel):
    registry_candidate_id: str = Field(min_length=1, max_length=300)
    adapter_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=4096)
    version: str | None = Field(default=None, max_length=200)
    tags: list[str] = Field(default_factory=list, max_length=100)
    source_repository: str | None = Field(default=None, max_length=2048)
    package_locator: ProviderPackageLocator | None = None
    remote_endpoint: str | None = Field(default=None, max_length=2048)
    provenance: dict[str, JsonValue] = Field(default_factory=dict)
    marketplace_labels: dict[str, JsonValue] = Field(default_factory=dict)
    retrieved_at: datetime
    raw_metadata_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")


class ExternalResourceIdentity(StrictModel):
    """Registry identity, never an assertion that artifact bytes were verified."""

    schema_version: Literal['discovery.external_identity.v1'] = 'discovery.external_identity.v1'
    scheme: Literal['ard', 'registry']
    identifier: str = Field(min_length=1, max_length=2048)
    registry_origin: str = Field(min_length=1, max_length=2048)
    version: str | None = Field(default=None, max_length=200)
    content_digest: str | None = Field(default=None, pattern=r'^sha256:[a-f0-9]{64}$')

    @model_validator(mode='after')
    def validate_identity(self) -> ExternalResourceIdentity:
        if any(character.isspace() or ord(character) < 32 for character in self.identifier):
            raise ValueError('external identifier must not contain whitespace or controls')
        if self.scheme == 'ard':
            if not self.identifier.startswith('urn:air:') or self.identifier == 'urn:air:':
                raise ValueError('ARD identity requires its exact urn:air identifier')
            url = httpx.URL(self.registry_origin)
            if url.scheme != 'https' or not url.host or url.userinfo or url.query or url.fragment:
                raise ValueError('ARD registry origin requires a credential-free HTTPS base URL')
            object.__setattr__(self, 'registry_origin', str(url).rstrip('/'))
        return self

    def digest(self) -> str:
        return _metadata_digest(self.model_dump(mode='json'))


def external_resource_identity(candidate: RegistryCandidate) -> ExternalResourceIdentity | None:
    """Legacy candidates stay unbound; do not infer exact identity from their names."""
    value = candidate.provenance.get('external_identity')
    return ExternalResourceIdentity.model_validate(value) if value is not None else None


def candidate_artifact_type(candidate: RegistryCandidate) -> JsonValue:
    entry = candidate.provenance.get('entry')
    return entry.get('type') if isinstance(entry, dict) else candidate.provenance.get('artifact_type')


class DiscoveryRequest(StrictModel):
    schema_version: Literal['discovery.request.v1'] = 'discovery.request.v1'
    public_query: str = Field(min_length=1, max_length=500)
    source_ids: list[str] = Field(min_length=1, max_length=8)
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=1000)
    artifact_types: list[str] = Field(default_factory=list, max_length=32)

    @field_validator('public_query')
    @classmethod
    def public_phrase(cls, value: str) -> str:
        value = value.strip()
        if (not value or any(ord(character) < 32 for character in value)
                or re.search(r'(?i)(?:bearer\s|(?:api[_-]?key|password|token)\s*[:=]|'
                             r'file://|/(?:Users|home)/|[A-Z]:\\|\S+@\S+)', value)):
            raise ValueError('discovery requires public search terms without credentials or private paths')
        return value

    @field_validator('source_ids', 'artifact_types')
    @classmethod
    def bounded_labels(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values) or any(
            not value or len(value) > 100 or any(ord(c) < 32 for c in value) for value in values
        ):
            raise ValueError('discovery labels must be unique, nonempty and bounded')
        return values

    @model_validator(mode='after')
    def single_cursor_source(self) -> DiscoveryRequest:
        if self.cursor is not None and len(self.source_ids) != 1:
            raise ValueError('a page cursor belongs to exactly one source')
        return self


class DiscoverySourceRecord(StrictModel):
    schema_version: Literal['discovery.source.v1'] = 'discovery.source.v1'
    source_record_id: str
    discovery_id: str
    source_id: str
    adapter_id: str
    created_at: datetime
    query_digest: str = Field(pattern=r'^sha256:[a-f0-9]{64}$')
    status: Literal['complete', 'fallback', 'failed', 'timeout', 'skipped']
    candidate_ids: list[str] = Field(default_factory=list)
    candidate_digests: list[str] = Field(default_factory=list)
    elapsed_ms: float = Field(ge=0)
    cash_usd: float | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    warnings: list[str] = Field(default_factory=list)


class DiscoveryResult(StrictModel):
    schema_version: Literal['discovery.result.v1'] = 'discovery.result.v1'
    discovery_id: str
    created_at: datetime
    query_digest: str = Field(pattern=r'^sha256:[a-f0-9]{64}$')
    candidate_ids: list[str] = Field(default_factory=list)
    candidates: list[RegistryCandidate] = Field(default_factory=list)
    source_records: list[DiscoverySourceRecord] = Field(default_factory=list)
    elapsed_ms: float = Field(ge=0)


class PackageRegistryAdapter(Protocol):
    adapter_id: str

    async def search(self, query: RegistryQuery) -> list[RegistryCandidate]: ...


def _metadata_digest(value: Any) -> str:
    try:
        payload = rfc8785.dumps(value)
    except rfc8785.CanonicalizationError as exc:
        raise ProtocolError("registry metadata cannot be canonicalized") from exc
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


class FixtureRegistryAdapter:
    adapter_id = "fixture"

    def __init__(self, path: str | Path, *, clock: Any | None = None,
                 allowed_types: tuple[str, ...] = ()) -> None:
        self.path = Path(path)
        self.clock = clock or (lambda: datetime.now(UTC))
        self.allowed_types = allowed_types

    def _read(self) -> bytes:
        from .artifact_store import _read_stable_file
        from .assessment.identity import protected_directory

        path = self.path.absolute()
        if (protected_directory(path) or path != path.resolve() or path.is_symlink()
                or path.name in {'auth.json', 'credentials.json', '.env'}
                or path.name.startswith('.env.')
                or any(part in {'.ssh', '.aws', '.azure', '.kube'} for part in path.parts)):
            raise ConfigurationError('fixture registry requires an explicit non-secret regular file')
        return _read_stable_file(path, 1_000_000)

    async def search(self, query: RegistryQuery) -> list[RegistryCandidate]:
        try:
            payload = await asyncio.to_thread(self._read)
        except OSError as exc:
            raise ConfigurationError("cannot read fixture registry") from exc
        if len(payload) > 1_000_000:
            raise ConfigurationError("fixture registry exceeds 1 MiB")
        try:
            value = (
                json.loads(payload)
                if self.path.suffix.lower() == ".json"
                else yaml.safe_load(payload)
            )
        except (json.JSONDecodeError, yaml.YAMLError) as exc:
            raise ConfigurationError("fixture registry is invalid") from exc
        items = value.get("candidates") if isinstance(value, dict) else None
        if not isinstance(items, list):
            raise ConfigurationError("fixture registry requires a candidates list")
        terms = query.query.casefold().split()
        matched: list[RegistryCandidate] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            text = f"{item.get('name', '')} {item.get('description', '')}".casefold()
            if terms and not all(term in text for term in terms):
                continue
            normalized = dict(item)
            normalized.setdefault("adapter_id", self.adapter_id)
            normalized.setdefault("retrieved_at", self.clock())
            normalized.setdefault("raw_metadata_digest", _metadata_digest(item))
            candidate = RegistryCandidate.model_validate(normalized)
            if self.allowed_types and candidate_artifact_type(candidate) not in self.allowed_types:
                continue
            matched.append(candidate)
            if len(matched) >= query.limit:
                break
        return matched


class ARDRegistryAdapter:
    """Explicit, single-page ARD v0.91 search; results are inert candidate metadata."""

    adapter_id = 'ard'

    def __init__(self, base_url: str, *, client: httpx.AsyncClient | None = None,
                 fallback: PackageRegistryAdapter | None = None, allowed_types: tuple[str, ...] = ()) -> None:
        self.base_url = base_url.rstrip('/')
        self.client = client
        self.fallback = fallback
        self.allowed_types = allowed_types
        self.warnings: list[str] = []

    async def search(self, query: RegistryQuery, *, timeout_seconds: float = 10) -> list[RegistryCandidate]:
        self.warnings = []
        # Only a caller-supplied public search phrase crosses this preparation
        # boundary. There is no ActionRequest, task payload or filesystem context.
        if not query.query.strip():
            raise ConfigurationError('ARD requires an explicit public search phrase')
        if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 10:
            raise ConfigurationError('ARD remote search deadline must be finite and at most ten seconds')
        try:
            async with asyncio.timeout(timeout_seconds):
                return await self._search(query)
        except (ConfigurationError, ExecutorError, ProtocolError, httpx.HTTPError, ValueError, TimeoutError, RecursionError):
            if self.fallback is None:
                raise ProtocolError('ARD search unavailable or unsupported; no candidates activated') from None
            self.warnings.append('ARD unavailable or unsupported; returning configured local candidates')
            candidates = await self.fallback.search(query)
            return [candidate for candidate in candidates
                    if not self.allowed_types or candidate_artifact_type(candidate) in self.allowed_types]

    async def _search(self, query: RegistryQuery) -> list[RegistryCandidate]:
        parsed = httpx.URL(self.base_url)
        if parsed.query or parsed.fragment:
            raise ConfigurationError('ARD registry base URL cannot contain a query or fragment')
        url = self.base_url + '/search'
        await validate_http_url(url, {'allowed_hosts':[httpx.URL(self.base_url).host]}, label='ARD registry')
        body: dict[str, Any] = {'query':{'text':query.query}, 'pageSize':query.limit, 'federation':'none'}
        if query.cursor is not None:
            body['pageToken'] = query.cursor
        # Filter locally too; a registry's optional filter support is not authority.
        if self.allowed_types:
            body['query']['filter'] = {'type':list(self.allowed_types)}
        client = self.client or httpx.AsyncClient(timeout=10, follow_redirects=False, trust_env=False)
        try:
            async with client.stream('POST', url, json=body, headers={'accept':'application/json'}, follow_redirects=False) as response:
                response.raise_for_status()
                chunks, total = [], 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > 1_000_000:
                        raise ProtocolError('ARD response exceeds 1 MiB')
                    chunks.append(chunk)
            data = json.loads(b''.join(chunks))
        finally:
            if self.client is None:
                await client.aclose()
        if not isinstance(data, dict) or not isinstance(data.get('results'), list):
            raise ProtocolError('ARD response requires results')
        candidates = []
        for entry in data['results'][:query.limit]:
            try:
                candidates.append(self._candidate(entry))
            except (ValueError, TypeError, ConfigurationError, ProtocolError):
                self.warnings.append('Malformed or unsupported ARD entry omitted')
        if data.get('referrals') or data.get('pageToken'):
            self.warnings.append('Additional pages/referrals were not fetched')
        return candidates

    def _candidate(self, entry: Any) -> RegistryCandidate:
        if not isinstance(entry, dict) or not isinstance(entry.get('identifier'), str) or not entry['identifier'].startswith('urn:air:'):
            raise ValueError('invalid ARD identifier')
        context = entry.get('@context')
        if context not in (None, 'https://agenticresourcediscovery.org/context/v1'):
            raise ConfigurationError('ARD context expansion beyond the pinned base context is unsupported')
        if self.allowed_types and entry.get('type') not in self.allowed_types:
            raise ConfigurationError('ARD artifact type is outside the local selection')
        if 'url' in entry and 'data' in entry:
            raise ValueError('ARD entry contains both artifact value and reference')
        digest = _metadata_digest(entry)
        identity = ExternalResourceIdentity(
            scheme='ard', identifier=entry['identifier'], registry_origin=self.base_url,
            version=entry.get('version'),
        )
        # Identical entries served by different registries are separate provenance.
        candidate_digest = _metadata_digest({'origin': identity.registry_origin, 'metadata': digest})
        return RegistryCandidate(registry_candidate_id='ard_'+candidate_digest.removeprefix('sha256:')[:32],
            adapter_id=self.adapter_id, name=entry.get('displayName') or entry['identifier'],
            description=entry.get('description',''), version=entry.get('version'),
            provenance={'specification':'ARD v0.91', 'entry':entry, 'trust_verified':False,
                        'specification_revision':'b76f235a8f461876ad4f1e77abd0eb0eb302b48d',
                        'external_identity':identity.model_dump(mode='json'),
                        'artifact_fetched':False, 'namespace_support':'default namespace only'},
            retrieved_at=datetime.now(UTC), raw_metadata_digest=digest)


class MCPCommunityRegistryAdapter:
    adapter_id = "mcp-community"

    def __init__(
        self,
        *,
        base_url: str = "https://registry.modelcontextprotocol.io",
        client: httpx.AsyncClient | None = None,
        clock: Any | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = client
        self.clock = clock or (lambda: datetime.now(UTC))

    async def search(self, query: RegistryQuery) -> list[RegistryCandidate]:
        parameters: dict[str, str | int] = {
            "search": query.query,
            "limit": query.limit,
            "version": "latest",
        }
        if query.cursor is not None:
            parameters["cursor"] = query.cursor
        url = f"{self.base_url}/v0.1/servers?{urlencode(parameters)}"
        hostname = httpx.URL(self.base_url).host
        await validate_http_url(
            url,
            {"allowed_hosts": [hostname]},
            label="MCP registry",
        )
        owned = self.client is None
        client = self.client or httpx.AsyncClient(
            timeout=10,
            follow_redirects=False,
            trust_env=False,
        )
        try:
            response = await client.get(url, headers={"accept": "application/json"})
            response.raise_for_status()
            if len(response.content) > 1_000_000:
                raise ProtocolError("MCP registry response exceeds 1 MiB")
            value = response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise ProtocolError("MCP registry search failed") from exc
        finally:
            if owned:
                await client.aclose()
        servers = value.get("servers") if isinstance(value, dict) else None
        if not isinstance(servers, list):
            raise ProtocolError("MCP registry response requires servers")
        return [self._candidate(item) for item in servers[: query.limit] if isinstance(item, dict)]

    def _candidate(self, item: dict[str, Any]) -> RegistryCandidate:
        raw_server = item.get("server")
        server: dict[str, Any] = raw_server if isinstance(raw_server, dict) else item
        name = str(server.get("name") or server.get("title") or "unnamed")
        version = str(server.get("version")) if server.get("version") is not None else None
        repository = server.get("repository")
        source_repository = (
            repository.get("url") if isinstance(repository, dict) else None
        )
        raw_metadata = server.get("_meta")
        metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
        manifest_url = metadata.get("org.aeep/providerManifest")
        locator = (
            ProviderPackageLocator(kind=PackageLocatorKind.HTTPS, value=manifest_url)
            if isinstance(manifest_url, str) and manifest_url.startswith("https://")
            else ProviderPackageLocator(
                kind=PackageLocatorKind.REPOSITORY,
                value=source_repository,
            )
            if isinstance(source_repository, str)
            else None
        )
        identifier = hashlib.sha256(f"{name}\x1f{version or ''}".encode()).hexdigest()[:32]
        return RegistryCandidate(
            registry_candidate_id=f"mcp_{identifier}",
            adapter_id=self.adapter_id,
            name=name,
            description=str(server.get("description") or ""),
            version=version,
            source_repository=(str(source_repository) if source_repository else None),
            package_locator=locator,
            provenance={"packages": server.get("packages", [])},
            marketplace_labels=metadata,
            retrieved_at=self.clock(),
            raw_metadata_digest=_metadata_digest(item),
        )


class DockerCatalogAdapter:
    adapter_id = "docker-mcp"

    def __init__(self, catalog: str, *, command: str | None = None) -> None:
        executable = command or shutil.which("docker")
        if executable is None or not os.path.isabs(executable):
            raise ConfigurationError("Docker registry adapter requires an absolute docker argv")
        self.command = executable
        self.catalog = catalog

    async def search(self, query: RegistryQuery) -> list[RegistryCandidate]:
        process = await asyncio.create_subprocess_exec(
            self.command,
            "mcp",
            "catalog",
            "show",
            self.catalog,
            "--format",
            "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=10)
        if process.returncode != 0 or len(stdout) > 1_000_000:
            raise ProtocolError("Docker MCP catalog inspection failed")
        value = json.loads(stdout)
        items = value.get("servers") if isinstance(value, dict) else None
        fixture = {"candidates": items if isinstance(items, list) else []}
        candidates: list[RegistryCandidate] = []
        for item in fixture["candidates"]:
            if not isinstance(item, dict):
                continue
            text = f"{item.get('name', '')} {item.get('description', '')}".casefold()
            if query.query.casefold() not in text:
                continue
            candidate_id = hashlib.sha256(rfc8785.dumps(item)).hexdigest()[:32]
            candidates.append(
                RegistryCandidate(
                    registry_candidate_id=f"docker_{candidate_id}",
                    adapter_id=self.adapter_id,
                    name=str(item.get("name") or "unnamed"),
                    description=str(item.get("description") or ""),
                    version=(str(item["version"]) if item.get("version") else None),
                    provenance=item,
                    marketplace_labels={"catalog": self.catalog},
                    retrieved_at=datetime.now(UTC),
                    raw_metadata_digest=_metadata_digest(item),
                )
            )
            if len(candidates) >= query.limit:
                break
        return candidates


class SmitheryRegistryAdapter:
    adapter_id = "smithery"

    def __init__(self, *, token_env: str, client: httpx.AsyncClient | None = None) -> None:
        token = os.environ.get(token_env)
        if not token:
            raise ConfigurationError("Smithery registry token environment variable is unset")
        self.token = token
        self.client = client

    async def search(self, query: RegistryQuery) -> list[RegistryCandidate]:
        owned = self.client is None
        client = self.client or httpx.AsyncClient(
            timeout=10,
            follow_redirects=False,
            trust_env=False,
        )
        try:
            response = await client.get(
                "https://api.smithery.ai/servers",
                params={"q": query.query, "pageSize": query.limit},
                headers={"authorization": f"Bearer {self.token}"},
            )
            response.raise_for_status()
            if len(response.content) > 1_000_000:
                raise ProtocolError("Smithery response exceeds 1 MiB")
            value = response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise ProtocolError("Smithery registry search failed") from exc
        finally:
            if owned:
                await client.aclose()
        items = value.get("servers") if isinstance(value, dict) else None
        if not isinstance(items, list):
            return []
        results: list[RegistryCandidate] = []
        for item in items[: query.limit]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("qualifiedName") or item.get("displayName") or "unnamed")
            results.append(
                RegistryCandidate(
                    registry_candidate_id="smithery_"
                    + hashlib.sha256(name.encode()).hexdigest()[:32],
                    adapter_id=self.adapter_id,
                    name=name,
                    description=str(item.get("description") or ""),
                    remote_endpoint=(str(item["remoteUrl"]) if item.get("remoteUrl") else None),
                    marketplace_labels={
                        key: item[key]
                        for key in ("verified", "useCount")
                        if key in item
                    },
                    retrieved_at=datetime.now(UTC),
                    raw_metadata_digest=_metadata_digest(item),
                )
            )
        return results
