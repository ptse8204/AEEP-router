"""Executor interface and shared context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..models import ActionRequest, ExecutorSpec, RawExecution, RouteEstimate, SideEffect


@dataclass(slots=True)
class ExecutionContext:
    request: ActionRequest
    spec: ExecutorSpec
    estimate: RouteEstimate
    attempt: int
    prepared_id: str | None = None
    quote_id: str | None = None
    attempt_id: str | None = None
    approved_side_effect: SideEffect = SideEffect.READ


class BaseExecutor(ABC):
    @abstractmethod
    async def execute(self, context: ExecutionContext) -> RawExecution:
        raise NotImplementedError

    async def close(self) -> None:
        return None
