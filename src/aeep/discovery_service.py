"""Explicit discovery preparation using existing candidate and immutable records."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from time import monotonic
from typing import Literal

import httpx
from pydantic import Field, model_validator

from .assessment.repository import AssessmentRepository
from .discovery import (
    ARDRegistryAdapter,
    DiscoveryRequest,
    DiscoveryResult,
    DiscoverySourceRecord,
    DockerCatalogAdapter,
    FixtureRegistryAdapter,
    MCPCommunityRegistryAdapter,
    PackageRegistryAdapter,
    RegistryCandidate,
    RegistryQuery,
    SmitheryRegistryAdapter,
    _metadata_digest,
    candidate_artifact_type,
    external_resource_identity,
)
from .errors import AEEPError, ConfigurationError
from .models import StrictModel, new_id, utc_now
from .store import ReceiptStore


class DiscoverySourceConfig(StrictModel):
    source_id: str = Field(min_length=1, max_length=100)
    kind: Literal['ard', 'fixture', 'mcp', 'docker', 'smithery', 'package']
    catalog: str | None = Field(default=None, max_length=2048)
    command: str | None = Field(default=None, max_length=4096)
    token_env: str | None = Field(default=None, pattern=r'^[A-Za-z_][A-Za-z0-9_]*$', max_length=200)
    base_url: str | None = Field(default=None, max_length=2048)
    path: str | None = Field(default=None, max_length=4096)
    fallback_path: str | None = Field(default=None, max_length=4096)
    allow_remote: bool = False
    artifact_types: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode='after')
    def source_shape(self) -> DiscoverySourceConfig:
        if self.kind in {'fixture', 'package'}:
            if not self.path or self.base_url is not None or self.fallback_path is not None or self.allow_remote:
                raise ValueError('local discovery requires only a local path')
        elif self.kind in {'ard', 'mcp'}:
            if not self.base_url or self.path is not None:
                raise ValueError('remote discovery requires an explicit base URL')
            url = httpx.URL(self.base_url)
            if url.scheme != 'https' or not url.host or url.userinfo or url.query or url.fragment:
                raise ValueError('discovery requires a credential-free HTTPS base URL')
            if self.kind == 'mcp' and self.fallback_path:
                raise ValueError('MCP fallback is not supported')
        elif self.kind == 'docker':
            if not self.catalog or self.base_url or self.path or self.fallback_path:
                raise ValueError('Docker discovery requires a catalog')
        elif not self.token_env or self.base_url or self.path or self.fallback_path:
            raise ValueError('Smithery discovery requires an operator secret reference')
        if self.kind != 'docker' and (self.catalog or self.command):
            raise ValueError('catalog and command belong to Docker sources only')
        if self.kind != 'smithery' and self.token_env:
            raise ValueError('token_env belongs to Smithery sources only')
        return self


class DiscoveryConfig(StrictModel):
    schema_version: Literal['discovery.config.v1'] = 'discovery.config.v1'
    sources: list[DiscoverySourceConfig] = Field(default_factory=list, max_length=8)
    max_results: int = Field(default=20, ge=1, le=100)
    timeout_seconds: float = Field(default=10, gt=0, le=30)

    @model_validator(mode='after')
    def unique_sources(self) -> DiscoveryConfig:
        if len({source.source_id for source in self.sources}) != len(self.sources):
            raise ValueError('discovery source IDs must be unique')
        return self


class DiscoveryQueryRecord(StrictModel):
    """Persist only the public phrase's digest, never task content or cursor text."""

    schema_version: Literal['discovery.query.v1'] = 'discovery.query.v1'
    discovery_id: str
    created_at: datetime
    query_digest: str = Field(pattern=r'^sha256:[a-f0-9]{64}$')
    source_ids: list[str]
    limit: int
    cursor_digest: str | None = None
    artifact_types: list[str]
    timeout_seconds: float


class DiscoveryService:
    """Registration and remote-query authority are operator configuration only."""

    @classmethod
    def from_config(
        cls, store: ReceiptStore, config: DiscoveryConfig, *, base_directory: Path = Path('.'),
    ) -> DiscoveryService:
        adapters: dict[str, PackageRegistryAdapter] = {}
        for source in config.sources:
            adapters[source.source_id] = discovery_adapter(source, base_directory=base_directory)
        return cls(store, adapters,
                   allowed_remote_sources=tuple(source.source_id for source in config.sources if source.allow_remote),
                   max_results=config.max_results, timeout_seconds=config.timeout_seconds)

    def __init__(
        self,
        store: ReceiptStore,
        adapters: Mapping[str, PackageRegistryAdapter],
        *,
        allowed_remote_sources: tuple[str, ...] = (),
        max_results: int = 20,
        timeout_seconds: float = 10,
    ) -> None:
        if (not 1 <= max_results <= 100 or not math.isfinite(timeout_seconds)
                or not 0 < timeout_seconds <= 30):
            raise ConfigurationError('discovery requires finite bounded operator limits')
        if not set(allowed_remote_sources).issubset(adapters):
            raise ConfigurationError('remote discovery authority names an unconfigured source')
        self.store = store
        self.repository = AssessmentRepository(store)
        self.adapters = dict(adapters)
        self.allowed_remote_sources = frozenset(allowed_remote_sources)
        self.max_results = max_results
        self.timeout_seconds = timeout_seconds
        # Adapter warnings belong to one call; serialize use of shared adapters.
        self._lock = asyncio.Lock()

    async def search(self, request: DiscoveryRequest) -> DiscoveryResult:
        request = DiscoveryRequest.model_validate(request.model_dump())
        if request.limit > self.max_results:
            raise ConfigurationError('discovery request exceeds operator result ceiling')
        for source in request.source_ids:
            adapter = self.adapters.get(source)
            if adapter is None:
                raise ConfigurationError('discovery source is not configured')
            # Only an exact fixture adapter is known to perform no network calls.
            if type(adapter) not in {FixtureRegistryAdapter, LocalPackageAdapter} and source not in self.allowed_remote_sources:
                raise ConfigurationError('discovery source requires operator remote-query authority')
            if (isinstance(adapter, ARDRegistryAdapter) and adapter.fallback is not None
                    and type(adapter.fallback) is not FixtureRegistryAdapter):
                raise ConfigurationError('discovery fallback must be a configured local fixture')
        async with self._lock:
            return await self._search(request)

    async def _search(self, request: DiscoveryRequest) -> DiscoveryResult:
        started = monotonic()
        discovery_id = new_id('discovery')
        query_digest = _metadata_digest({'public_query': request.public_query})
        record = DiscoveryQueryRecord(
            discovery_id=discovery_id, created_at=utc_now(), query_digest=query_digest, source_ids=request.source_ids,
            limit=request.limit, artifact_types=request.artifact_types,
            cursor_digest=_metadata_digest(request.cursor) if request.cursor is not None else None,
            timeout_seconds=self.timeout_seconds,
        )
        self.repository.put('discovery_query', discovery_id, record)
        sources: list[DiscoverySourceRecord] = []
        candidates: dict[str, RegistryCandidate] = {}
        for source in request.source_ids:
            adapter = self.adapters[source]
            source_started = monotonic()
            source_record = DiscoverySourceRecord(
                source_record_id=new_id('discovery_source'), discovery_id=discovery_id,
                source_id=source, adapter_id=adapter.adapter_id, created_at=utc_now(),
                query_digest=query_digest, status='complete', elapsed_ms=0,
            )
            remaining = self.timeout_seconds - (monotonic() - started)
            limit = request.limit - len(candidates)
            if remaining <= 0 or limit <= 0:
                source_record.status = 'skipped'
                source_record.warnings.append('Discovery deadline or result ceiling reached')
                found = []
            else:
                try:
                    async with asyncio.timeout(remaining):
                        query = RegistryQuery(
                            query=request.public_query, limit=limit, cursor=request.cursor,
                        )
                        # Keep part of the total deadline for the configured local fallback.
                        found = (await adapter.search(query, timeout_seconds=min(10, remaining * 0.8))
                                 if isinstance(adapter, ARDRegistryAdapter)
                                 else await adapter.search(query))
                    if len(found) > limit:
                        raise ConfigurationError('registry exceeded requested result ceiling')
                    # Validate all returned metadata before any candidate from this source is stored.
                    found = [RegistryCandidate.model_validate(item.model_dump()) for item in found]
                    for item in found:
                        external_resource_identity(item)
                    if isinstance(adapter, ARDRegistryAdapter):
                        source_record.warnings.extend(adapter.warnings)
                        if 'ARD unavailable or unsupported; returning configured local candidates' in adapter.warnings:
                            source_record.status = 'fallback'
                except TimeoutError:
                    source_record.status = 'timeout'
                    source_record.warnings.append('Discovery source exceeded its deadline')
                    found = []
                except (AEEPError, httpx.HTTPError, ValueError, TypeError, OSError, RecursionError):
                    source_record.status = 'failed'
                    source_record.warnings.append('Discovery source unavailable or unsupported')
                    found = []
            for item in found:
                artifact_type = candidate_artifact_type(item)
                if request.artifact_types and artifact_type not in request.artifact_types:
                    source_record.warnings.append('Candidate omitted by local artifact-type filter')
                    continue
                previous = candidates.get(item.registry_candidate_id)
                if previous is not None and previous.raw_metadata_digest != item.raw_metadata_digest:
                    source_record.warnings.append('Conflicting candidate identity omitted')
                    continue
                identity = external_resource_identity(item)
                if identity is not None:
                    self.repository.put('external_identity', identity.digest(), identity)
                snapshot_digest = _metadata_digest(item.model_dump(mode='json'))
                self.repository.put('discovery_candidate', snapshot_digest, item)
                self.store.save_registry_candidate(item)
                candidates[item.registry_candidate_id] = item
                source_record.candidate_ids.append(item.registry_candidate_id)
                source_record.candidate_digests.append(snapshot_digest)
            source_record.elapsed_ms = (monotonic() - source_started) * 1000
            self.repository.put('discovery_source', source_record.source_record_id, source_record)
            sources.append(source_record)
        result = DiscoveryResult(
            discovery_id=discovery_id, created_at=utc_now(), query_digest=query_digest,
            candidates=list(candidates.values()), candidate_ids=list(candidates),
            source_records=sources, elapsed_ms=(monotonic() - started) * 1000,
        )
        self.repository.put('discovery_result', discovery_id, result)
        return result

    def get(self, discovery_id: str) -> DiscoveryResult:
        return DiscoveryResult.model_validate(self.repository.get('discovery_result', discovery_id))


def _self_check() -> None:
    """Small offline contract check: ``python -m aeep.discovery_service``."""
    from .discovery import ExternalResourceIdentity

    identity = ExternalResourceIdentity(
        scheme='ard', identifier='urn:air:example.org:skill:format',
        registry_origin='https://REGISTRY.example.org/',
    )
    assert identity.registry_origin == 'https://registry.example.org'
    assert identity.content_digest is None
    for phrase in ('', 'token=secret', '/Users/person/private.xlsx'):
        try:
            DiscoveryRequest(public_query=phrase, source_ids=['local'])
        except ValueError:
            continue
        raise AssertionError('private or empty discovery phrase accepted')
    assert DiscoveryConfig().sources == []
    assert DiscoveryRequest(public_query='format worksheets', source_ids=['local']).limit == 20


if __name__ == '__main__':
    _self_check()


class LocalPackageAdapter:
    """Read an explicit local package; never fetch artifacts or activate routes."""
    adapter_id = 'local-package'

    def __init__(self, path: Path) -> None:
        self.path = path

    async def search(self, query: RegistryQuery) -> list[RegistryCandidate]:
        from .provider_package import ProviderPackage, load_provider_package
        def read_package() -> tuple[ProviderPackage, Path]:
            if self.path.stat().st_size > 1048576:
                raise ConfigurationError('local provider package metadata exceeds 1 MiB')
            return load_provider_package(self.path)
        package, _ = await asyncio.to_thread(read_package)
        name = package.spec.provider.provider_id
        if query.query.casefold() not in name.casefold():
            return []
        digest = _metadata_digest(package.model_dump(mode='json'))
        return [RegistryCandidate(registry_candidate_id='package_' + digest.removeprefix('sha256:')[:32],
            adapter_id=self.adapter_id, name=name, description='Operator-selected local provider package',
            retrieved_at=utc_now(), raw_metadata_digest=digest,
            provenance={'package_digest': digest})]


def discovery_adapter(source: DiscoverySourceConfig, *, base_directory: Path = Path('.')) -> PackageRegistryAdapter:
    """Canonical factory. Only operator configuration chooses code and destinations."""
    if source.kind == 'fixture':
        return FixtureRegistryAdapter(base_directory / str(source.path), allowed_types=tuple(source.artifact_types))
    if source.kind == 'package':
        return LocalPackageAdapter(base_directory / str(source.path))
    if source.kind == 'ard':
        return ARDRegistryAdapter(str(source.base_url),
            fallback=FixtureRegistryAdapter(base_directory / source.fallback_path) if source.fallback_path else None,
            allowed_types=tuple(source.artifact_types))
    if source.kind == 'mcp':
        return MCPCommunityRegistryAdapter(base_url=str(source.base_url))
    if source.kind == 'docker':
        return DockerCatalogAdapter(str(source.catalog), command=source.command)
    return SmitheryRegistryAdapter(token_env=str(source.token_env))
