"""Deterministic local registry for reviewed managed-host adapters."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from ..errors import ConfigurationError
from ..execution import ExecutorCapabilities
from ..models import ExecutorKind, ExecutorSpec, ManagedHostExecutorConfig
from .base import ManagedHostAdapter


class ManagedHostRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, ManagedHostAdapter] = {}
        self._factories: dict[str, Callable[[ExecutorSpec, bytes, Path | None], ManagedHostAdapter]] = {}

    def register(self, adapter_id: str, adapter: ManagedHostAdapter) -> None:
        if not adapter_id:
            raise ConfigurationError("managed-host adapter ID is required")
        if adapter_id in self._adapters:
            raise ConfigurationError(f"managed-host adapter {adapter_id!r} is already registered")
        self._adapters[adapter_id] = adapter

    def register_factory(
        self, name: str,
        factory: Callable[[ExecutorSpec, bytes, Path | None], ManagedHostAdapter],
    ) -> None:
        """Operator composition only; candidate metadata cannot register Python code."""
        if not name or ":" in name or name in self._factories:
            raise ConfigurationError("invalid or duplicate adapter factory")
        self._factories[name] = factory

    def clone_factories(self) -> ManagedHostRegistry:
        """Fresh campaign adapters retain operator composition, never processes."""
        registry = ManagedHostRegistry()
        registry._factories = dict(self._factories)
        return registry

    def configure(
        self, specs: Iterable[ExecutorSpec], *, principal_salt: bytes | Callable[[], bytes],
        manifest_directory: Path | None = None,
    ) -> None:
        from .codex_app_server import CodexAppServerAdapter
        from .codex_exec import CodexExecAdapter

        factories = dict(self._factories)
        factories.setdefault("codex-app-server", lambda spec, salt, directory:
            CodexAppServerAdapter.from_executor(spec, principal_salt=salt,
                                                manifest_directory=directory))
        factories.setdefault("codex-exec", lambda spec, salt, directory:
            CodexExecAdapter.from_executor(spec, principal_salt=salt, manifest_directory=directory))
        grouped: dict[str, list[ExecutorSpec]] = {}
        for spec in specs:
            if spec.kind is ExecutorKind.MANAGED_HOST:
                grouped.setdefault(spec.managed_host_config().adapter_id, []).append(spec)
        for adapter_id, routes in sorted(grouped.items()):
            if adapter_id in self._adapters:
                continue
            factory = factories.get(adapter_id.split(":", 1)[0])
            if factory is None:
                continue  # Explicitly injected adapters remain supported.
            bindings = {(spec.resource_pool, spec.managed_host_config().process_binding()) for spec in routes}
            if len(bindings) != 1:
                raise ConfigurationError("managed-host routes must share one process, worker, protocol and resource binding")
            self.register(adapter_id, factory(routes[0], principal_salt() if callable(principal_salt) else principal_salt, manifest_directory))

    def capabilities(self, adapter_id: str) -> ExecutorCapabilities:
        adapter = self.get(adapter_id)
        method = getattr(adapter, "capabilities", None)
        if method is None:
            return ExecutorCapabilities(adapter=adapter_id)
        return ExecutorCapabilities.model_validate(method())

    async def resolve_identity(self, config: ManagedHostExecutorConfig) -> str | None:
        method = getattr(self.get(config.adapter_id), "resolve_identity", None)
        if method is None:
            return None
        result = await method(config)
        if result is not None and (not isinstance(result, str) or len(result) != 64
                                   or any(c not in "0123456789abcdef" for c in result)):
            raise ConfigurationError("adapter returned an invalid identity digest")
        return result

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
