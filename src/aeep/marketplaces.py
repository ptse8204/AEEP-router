"""Read marketplace metadata without checking out or executing plugin code."""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

import httpx

from .discovery import RegistryCandidate, RegistryQuery, _metadata_digest
from .errors import ConfigurationError, ProtocolError
from .executors.network import validate_http_url
from .models import utc_now

CATALOG_PATHS = ('.agents/plugins/marketplace.json', '.claude-plugin/marketplace.json')


def public_url(value: str) -> str:
    url = httpx.URL(value)
    if url.scheme != 'https' or not url.host or url.userinfo or url.query or url.fragment:
        raise ConfigurationError('catalog URLs must be credential-free HTTPS without query or fragment')
    return str(url)


def marketplace_location(value: str) -> tuple[str | None, str | None]:
    path = Path(value).expanduser()
    if path.exists():
        return str(path.resolve()), None
    if re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', value):
        value = f'https://github.com/{value}'
    return None, public_url(value)


def _relative(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or '\\' in value or not value:
        raise ConfigurationError('marketplace entry path must remain inside its repository')
    return str(path)


async def fetch_metadata(url: str) -> bytes:
    public_url(url)
    await validate_http_url(url, {'allowed_hosts': [httpx.URL(url).host]}, label='marketplace')
    async with httpx.AsyncClient(timeout=10, follow_redirects=False, trust_env=False) as client, client.stream('GET', url, headers={'accept': 'application/json'}) as response:
        response.raise_for_status()
        chunks = bytearray()
        async for chunk in response.aiter_bytes():
            chunks.extend(chunk)
            if len(chunks) > 1_000_000:
                raise ProtocolError('marketplace exceeds 1 MiB')
        return bytes(chunks)


class MarketplaceAdapter:
    adapter_id = 'plugin-marketplace'

    def __init__(self, location: str, *, local: bool = False) -> None:
        self.location, self.local = location, local
        self.warnings: list[str] = []


    def local_metadata(self) -> tuple[dict[str, Any], str, str]:
        root = Path(self.location)
        paths = [root / part for part in CATALOG_PATHS] if root.is_dir() else [root]
        for path in paths:
            if not path.exists():
                continue
            if path.is_symlink() or (root.is_dir() and not path.resolve().is_relative_to(root.resolve())):
                raise ConfigurationError('catalog path escapes its root')
            with path.open('rb') as stream:
                raw = stream.read(1_000_001)
            if len(raw) > 1_000_000:
                raise ConfigurationError('marketplace exceeds 1 MiB')
            return json.loads(raw), str(path), 'codex' if '.agents' in path.parts else 'claude'
        raise ConfigurationError('no supported marketplace.json found')

    async def metadata(self) -> tuple[dict[str, Any], str, str]:
        if self.local:
            return await asyncio.to_thread(self.local_metadata)
        url = public_url(self.location)
        parsed = urlsplit(url)
        if parsed.hostname == 'github.com':
            parts = parsed.path.strip('/').removesuffix('.git').split('/')
            if len(parts) != 2 or any(not re.fullmatch(r'[A-Za-z0-9_.-]+', part) for part in parts):
                raise ConfigurationError('use a repository URL or an explicit raw catalog URL')
            for item in CATALOG_PATHS:
                endpoint = f'https://raw.githubusercontent.com/{parts[0]}/{parts[1]}/HEAD/{item}'
                try:
                    return json.loads(await fetch_metadata(endpoint)), endpoint, 'codex' if item.startswith('.agents') else 'claude'
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 404:
                        raise
            raise ConfigurationError('repository has no supported marketplace catalog')
        return json.loads(await fetch_metadata(url)), url, 'codex' if '/.agents/' in url else 'claude'

    async def search(self, query: RegistryQuery) -> list[RegistryCandidate]:
        self.warnings = []
        catalog, origin, host = await self.metadata()
        entries = catalog.get('plugins') if isinstance(catalog, dict) else None
        if not isinstance(entries, list) or len(entries) > 10000:
            raise ConfigurationError('invalid marketplace plugin list')
        snapshot = _metadata_digest(catalog)
        results = []
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get('name'), str):
                self.warnings.append('Malformed entry omitted')
                continue
            source = entry.get('source')
            try:
                if isinstance(source, str):
                    if source.startswith('https://'):
                        public_url(source)
                    else:
                        _relative(source)
                elif isinstance(source, dict):
                    if isinstance(source.get('path'), str):
                        _relative(source['path'])
                    if isinstance(source.get('url'), str) and source['url'].startswith('https://'):
                        public_url(source['url'])
                else:
                    raise ConfigurationError('missing source')
            except ConfigurationError:
                self.warnings.append('Unsafe or unsupported entry omitted')
                continue
            interface = entry.get('interface')
            description = str(entry.get('description') or (interface.get('shortDescription', '') if isinstance(interface, dict) else ''))
            keywords = entry.get('keywords', [])
            haystack = f"{entry['name']} {description} {keywords}".casefold()
            if not all(word in haystack for word in query.query.casefold().split()):
                continue
            results.append(RegistryCandidate(
                registry_candidate_id='marketplace_' + _metadata_digest({'origin': origin, 'name': entry['name']})[7:39],
                adapter_id=self.adapter_id, name=entry['name'], description=description[:4096],
                version=str(entry['version']) if entry.get('version') else None,
                retrieved_at=utc_now(), raw_metadata_digest=_metadata_digest(entry),
                provenance={'artifact_type': 'plugin', 'supported_hosts': [host], 'catalog': origin,
                            'catalog_digest': snapshot, 'marketplace': str(catalog.get('name', '')),
                            'source': source, 'revision': None},
            ))
        offset = int(query.cursor or '0')
        if offset < 0 or offset > 10000:
            raise ConfigurationError('invalid marketplace cursor')
        if len(results) > offset + query.limit:
            self.warnings.append(f'Results truncated; next cursor: {offset + query.limit}')
        return results[offset:offset + query.limit]
