"""Profiling helpers for AEEP-managed and externally executed actions."""

from __future__ import annotations

import json
import time
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Any

import psutil

from .models import (
    EstimateSource,
    ExecutionReceipt,
    ExecutionStatus,
    ExecutorKind,
    ResourceVector,
    RouteEstimate,
    new_id,
)
from .store import ReceiptStore


def approximate_tokens(value: Any) -> int:
    """Cheap tokenizer-independent context estimate.

    This is deliberately labeled an estimate. Integrations should report exact
    provider usage when available through `ActionProfiler.add_tokens`.
    """

    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError):
            text = repr(value)
    return max(1, (len(text.encode("utf-8")) + 3) // 4)


class ActionProfiler(AbstractContextManager["ActionProfiler"]):
    """Record an action performed outside AEEP's built-in executors.

    Useful for browser/computer-use/model routes controlled by a host agent.
    Call `succeed()` or `fail()` before leaving the context; otherwise success is
    inferred when no exception escapes.
    """

    def __init__(
        self,
        *,
        store: ReceiptStore,
        capability: str,
        executor_id: str,
        executor_kind: ExecutorKind = ExecutorKind.DELEGATE,
        decision_id: str | None = None,
        action_id: str | None = None,
        estimated: RouteEstimate | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.store = store
        self.capability = capability
        self.executor_id = executor_id
        self.executor_kind = executor_kind
        self.decision_id = decision_id or new_id("external_dec")
        self.action_id = action_id or new_id("external_act")
        self.estimated = estimated or RouteEstimate(source=EstimateSource.STATIC)
        self.metadata = dict(metadata or {})
        self.resources = ResourceVector()
        self.status: ExecutionStatus | None = None
        self.output_valid: bool | None = None
        self.error_message: str | None = None
        self._started_at: datetime | None = None
        self._start_perf: float | None = None
        self._cpu_start: float | None = None
        self._rss_start: float | None = None
        self.receipt: ExecutionReceipt | None = None

    def __enter__(self) -> "ActionProfiler":
        process = psutil.Process()
        times = process.cpu_times()
        self._started_at = datetime.now(UTC)
        self._start_perf = time.perf_counter()
        self._cpu_start = times.user + times.system
        self._rss_start = process.memory_info().rss / (1024 * 1024)
        return self

    def add_cost(self, usd: float) -> None:
        self.resources.monetary_usd += max(0.0, usd)

    def add_tokens(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        context_tokens: int = 0,
    ) -> None:
        self.resources.input_tokens += max(0, input_tokens)
        self.resources.output_tokens += max(0, output_tokens)
        self.resources.context_tokens += max(0, context_tokens)

    def add_network_bytes(self, count: int) -> None:
        self.resources.network_bytes += max(0, count)

    def succeed(self, *, output_valid: bool | None = True) -> None:
        self.status = ExecutionStatus.SUCCESS
        self.output_valid = output_valid

    def fail(self, message: str, *, status: ExecutionStatus = ExecutionStatus.FAILED) -> None:
        self.status = status
        self.error_message = message
        self.output_valid = False

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        assert self._started_at is not None
        assert self._start_perf is not None
        assert self._cpu_start is not None
        assert self._rss_start is not None
        process = psutil.Process()
        times = process.cpu_times()
        ended_at = datetime.now(UTC)
        elapsed = max(0.0, time.perf_counter() - self._start_perf)
        self.resources.latency_ms = elapsed * 1000.0
        self.resources.cpu_ms = max(0.0, (times.user + times.system - self._cpu_start) * 1000.0)
        rss = process.memory_info().rss / (1024 * 1024)
        incremental_mb = max(0.0, rss - self._rss_start)
        self.resources.peak_memory_mb = incremental_mb
        self.resources.memory_mb_seconds = incremental_mb * elapsed
        if exc is not None:
            self.status = ExecutionStatus.FAILED
            self.error_message = str(exc)
            self.output_valid = False
        elif self.status is None:
            self.status = ExecutionStatus.SUCCESS
        self.receipt = ExecutionReceipt(
            decision_id=self.decision_id,
            action_id=self.action_id,
            capability=self.capability,
            executor_id=self.executor_id,
            executor_kind=self.executor_kind,
            status=self.status,
            started_at=self._started_at,
            ended_at=ended_at,
            estimated=self.estimated,
            actual_resources=self.resources,
            output_valid=self.output_valid,
            error_type=type(exc).__name__ if exc is not None else None,
            error_message=self.error_message,
            metadata=self.metadata,
        )
        self.store.save_receipt(self.receipt)
        return False
