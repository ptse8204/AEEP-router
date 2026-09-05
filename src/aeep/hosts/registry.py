"""Deterministic local registry for reviewed managed-host adapters."""

from __future__ import annotations

from ..errors import ConfigurationError
from .base import ManagedHostAdapter


class ManagedHostRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, ManagedHostAdapter] = {}

    def register(self, adapter_id: str, adapter: ManagedHostAdapter) -> None:
        if not adapter_id:
            raise ConfigurationError("managed-host adapter ID is required")
        if adapter_id in self._adapters:
            raise ConfigurationError(f"managed-host adapter {adapter_id!r} is already registered")
        self._adapters[adapter_id] = adapter

    def get(self, adapter_id: str) -> ManagedHostAdapter:
        try:
            return self._adapters[adapter_id]
        except KeyError as exc:
            raise ConfigurationError(
                f"managed-host adapter {adapter_id!r} is not registered locally"
            ) from exc

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))

    async def close(self) -> None:
        for adapter_id in self.ids():
            await self._adapters[adapter_id].close()
        self._adapters.clear()
