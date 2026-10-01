"""Executor interface and shared context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path

from ..errors import ConfigurationError
from ..execution import (
    EventJournal,
    ExecutionEvent,
    ExecutionEvidence,
    ExecutionHandle,
    ExecutorCapabilities,
    cancel_execution,
    execution_events,
    start_execution,
)
from ..models import ActionRequest, ExecutorSpec, RawExecution, RouteEstimate, SideEffect, TaskScope


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
    invocation_check: Callable[[], str | None] | None = None


class BaseExecutor(ABC):
    def require_task_scope(self, scope: TaskScope, spec: ExecutorSpec, control_paths: list[Path], *, activating: bool = False) -> None:
        raise ConfigurationError('executor does not support bounded task delegation')

    def capabilities(self) -> ExecutorCapabilities:
        return ExecutorCapabilities(adapter=type(self).__name__)

    async def start(self, context: ExecutionContext) -> ExecutionHandle:
        async def run(journal: EventJournal) -> RawExecution:
            raw = await self.execute(context)
            existing = raw.metadata.get("execution_evidence")
            if existing is not None:
                evidence = ExecutionEvidence.model_validate(existing)
                if evidence.attempt_id != journal.attempt_id:
                    raise ValueError("adapter evidence belongs to another attempt")
                for event in evidence.events:
                    if event.kind not in {"execution.started", "execution.completed", "execution.failed"}:
                        journal.append(event.kind, "adapter:" + event.source_id,
                                       action_digest=event.action_digest, accounting=event.accounting,
                                       evidence_ref=event.evidence_ref, accounting_mode=event.accounting_mode)
            elif raw.accounting.model_usage or raw.accounting.subscription_usage or raw.accounting.cash.components:
                journal.append("usage.reported", "usage", accounting=raw.accounting)
            return raw
        return start_execution(context.attempt_id or context.request.action_id, self.capabilities().adapter, run)

    def events(self, handle: ExecutionHandle) -> AsyncIterator[ExecutionEvent]:
        return execution_events(handle)

    async def cancel(self, handle: ExecutionHandle) -> None:
        await cancel_execution(handle)

    @abstractmethod
    async def execute(self, context: ExecutionContext) -> RawExecution:
        raise NotImplementedError

    async def close(self) -> None:
        return None
