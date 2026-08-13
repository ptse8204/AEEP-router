"""Provider discovery from reviewed local catalogs and bounded remote registries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx
import yaml

from .errors import ConfigurationError, ProtocolError
from .executors.network import validate_http_url
from .models import ProviderDescriptor, RegistryConfig


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
        paths = sorted(self.path.glob("*.json")) + sorted(self.path.glob("*.yaml")) if self.path.is_dir() else [self.path]
        found: list[ProviderDescriptor] = []
        for path in paths:
            try:
                text = path.read_text(encoding="utf-8")
                value = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
            except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
                raise ConfigurationError(f"cannot read provider registry {path}: {exc}") from exc
            for provider in _descriptors(value):
                if any(definition.capability == capability for definition in provider.capabilities) or any(
                    executor.capability == capability for executor in provider.executors
                ):
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
            async with httpx.AsyncClient(
                timeout=self.config.timeout_seconds,
                follow_redirects=False,
                trust_env=False,
            ) as client, client.stream(
                "GET", url, headers={"accept": "application/json"}
            ) as response:
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
                providers.setdefault(provider.provider_id, provider)
        return [providers[key] for key in sorted(providers)]
