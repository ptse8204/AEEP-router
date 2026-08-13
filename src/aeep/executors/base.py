"""Executor interface and shared context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..models import ActionRequest, ExecutorSpec, RawExecution, RouteEstimate


@dataclass(slots=True)
class ExecutionContext:
    request: ActionRequest
    spec: ExecutorSpec
    estimate: RouteEstimate
    attempt: int


class BaseExecutor(ABC):
    @abstractmethod
    async def execute(self, context: ExecutionContext) -> RawExecution:
        raise NotImplementedError

    async def close(self) -> None:
        return None
