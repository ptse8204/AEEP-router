"""Shared catalog configuration, bounded searches, and labelled cached results."""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import Field

from .assessment.repository import AssessmentRepository
from .connections import config_root, file_lock, write_json
from .discovery import DiscoveryRequest, DiscoveryResult, RegistryCandidate, _metadata_digest
from .discovery_service import DiscoveryConfig, DiscoveryService, DiscoverySourceConfig
from .errors import ConfigurationError
from .hosts.codex_project import _read
from .models import StrictModel, new_id, utc_now
from .store import ReceiptStore


def catalog_path() -> Path:
    return config_root() / 'discovery.json'


def defaults() -> DiscoveryConfig:
    return DiscoveryConfig(sources=[
        DiscoverySourceConfig(source_id='mcp-registry', kind='mcp',
                              base_url='https://registry.modelcontextprotocol.io', allow_remote=True),
        DiscoverySourceConfig(source_id='anthropic-plugins', kind='marketplace',
                              base_url='https://github.com/anthropics/claude-plugins-official', allow_remote=True),
    ])


def read_catalogs(path: Path | None = None) -> DiscoveryConfig:
    raw = _read(path or catalog_path())
    if raw is None:
        return DiscoveryConfig()
    return DiscoveryConfig.model_validate_json(raw)


def save_source(source: DiscoverySourceConfig | None, *, remove: str | None = None) -> DiscoveryConfig:
    path = catalog_path()
    with file_lock(path):
        before = _read(path)
        config = read_catalogs(path)
        identity = source.source_id if source else remove
        sources = [item for item in config.sources if item.source_id != identity]
        if source:
            sources.append(source)
        config = DiscoveryConfig.model_validate({**config.model_dump(), 'sources': sources})
        write_json(path, config.model_dump(mode='json'), before=before)
        return config


class CatalogSearch(StrictModel):
    search_id: str
    created_at: datetime
    configuration_digest: str
    query_digest: str
    candidates: list[RegistryCandidate] = Field(default_factory=list)
    searches: list[DiscoveryResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    stale: bool = False


def source_status(config: DiscoveryConfig) -> dict[str, Any]:
    return {'sources': [{'source_id': s.source_id, 'kind': s.kind,
                        'remote_enabled': s.allow_remote, 'status': 'configured; availability not checked'}
                       for s in config.sources],
            'next_step': 'Search public capability terms; use host web search for coverage gaps.' if config.sources
            else 'Run aeep setup or aeep catalogs add to connect searchable catalogs.'}


async def search_catalogs(store: ReceiptStore, terms: list[str], *, config: DiscoveryConfig | None = None,
                          source_ids: list[str] | None = None, path: Path | None = None) -> CatalogSearch:
    if not 1 <= len(terms) <= 6:
        raise ConfigurationError('provide one to six short public capability terms')
    config = config if config is not None else read_catalogs(path)
    if source_ids is not None:
        if not set(source_ids) <= {source.source_id for source in config.sources}:
            raise ConfigurationError('unknown catalog source')
        config = config.model_copy(update={'sources': [s for s in config.sources if s.source_id in source_ids]})
    terms = [DiscoveryRequest.public_phrase(term) for term in terms]
    result = CatalogSearch(search_id=new_id('catalog_search'), created_at=utc_now(),
                           configuration_digest=_metadata_digest(config.model_dump(mode='json')),
                           query_digest=_metadata_digest(terms))
    if not config.sources:
        result.warnings.append('No catalogs configured. Run aeep setup; host web search remains available independently.')
        return result
    service = DiscoveryService.from_config(store, config, base_directory=(path or catalog_path()).parent)
    candidates: dict[str, RegistryCandidate] = {}
    try:
        async with asyncio.timeout(30):
            for term in terms:
                # Query each source so an early source cannot consume another source's result budget.
                for source in config.sources:
                    found = await service.search(DiscoveryRequest(public_query=term, source_ids=[source.source_id], limit=config.max_results))
                    result.searches.append(found)
                    candidates.update((item.registry_candidate_id, item) for item in found.candidates)
                    if len(candidates) >= 100:
                        result.warnings.append('Search truncated at 100 candidates.')
                        break
                if len(candidates) >= 100:
                    break
    except TimeoutError:
        result.warnings.append('Search stopped at its 30-second deadline; coverage is incomplete.')
    result.candidates = list(candidates.values())[:100]
    failed = any(s.status in {'failed', 'timeout', 'skipped'} for r in result.searches for s in r.source_records)
    if failed or result.warnings:
        with store._lock:
            rows = store._connection.execute("SELECT payload_json FROM assessment_records WHERE kind='catalog_search' ORDER BY rowid DESC LIMIT 50").fetchall()
        for row in rows:
            old = CatalogSearch.model_validate_json(row[0])
            if old.configuration_digest == result.configuration_digest and old.query_digest == result.query_digest and old.candidates and not old.stale:
                missing = [item for item in old.candidates if item.registry_candidate_id not in candidates]
                result.candidates = (result.candidates + missing)[:100]
                if missing:
                    result.stale = True
                    result.warnings.append(f'Includes cached metadata from {old.created_at.isoformat()}; recheck before setup.')
                break
    result.warnings.append('Registry descriptions are claims. No candidate was installed, qualified or enabled.')
    AssessmentRepository(store).put('catalog_search', result.search_id, result)
    return result
