"""Provider-neutral managed-host adapter boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from pydantic import Field

from ..capacity import CapacityObservation
from ..models import ActionRequest, ManagedHostExecutorConfig, RawExecution, StrictModel


class HostProbeStatus(StrEnum):
    READY = "ready"
    AUTH_REQUIRED = "auth_required"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"


class HostProbe(StrictModel):
    adapter_id: str = Field(min_length=1, max_length=200)
    status: HostProbeStatus
    protocol_version: str | None = Field(default=None, max_length=100)
    supported_features: tuple[str, ...] = ()
    reason: str | None = Field(default=None, max_length=1000)


class HostModel(StrictModel):
    id: str = Field(min_length=1, max_length=200)
    capabilities: tuple[str, ...] = ()
    reasoning_efforts: tuple[str, ...] = ()
    context_tokens: int | None = Field(default=None, ge=1)


@dataclass(frozen=True, slots=True)
class ManagedHostExecutionContext:
    request: ActionRequest
    instruction: str
    config: ManagedHostExecutorConfig
    attempt: int
    attempt_id: str


class ManagedHostAdapter(Protocol):
    async def probe(self) -> HostProbe: ...

    async def snapshot_capacity(self) -> CapacityObservation: ...

    async def list_models(self) -> list[HostModel]: ...

    async def execute(self, context: ManagedHostExecutionContext) -> RawExecution: ...

    async def interrupt(self, attempt_id: str) -> None: ...

    async def close(self) -> None: ...
