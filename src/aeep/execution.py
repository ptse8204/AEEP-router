"""AEEP execution contracts, independent of any provider protocol or transport."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Literal
from uuid import uuid4

from pydantic import Field, SerializerFunctionWrapHandler, model_serializer, model_validator

from .errors import ConfigurationError
from .models import ExecutionStatus, RawExecution, ResourceAccounting, StrictModel

Support = Literal["supported", "unsupported", "unknown"]
EventKind = Literal[
    "execution.started", "action.started", "action.completed", "message.received",
    "permission.requested", "permission.granted", "permission.denied",
    "artifact.created", "usage.reported", "execution.failed", "execution.completed",
    "cancellation.requested", "cancellation.confirmed",
]


class ExecutorCapabilities(StrictModel):
    schema_version: Literal["execution.capabilities.v1"] = "execution.capabilities.v1"
    adapter: str
    version: str = "1"
    support_status: Literal["supported", "experimental", "unknown"] = "unknown"
    features: dict[str, Support] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)

    def require(self, required: list[str]) -> None:
        missing = [name for name in required if self.features.get(name, "unknown") != "supported"]
        if missing:
            raise ConfigurationError("executor capabilities unavailable: " + ", ".join(missing))


class ExecutionEvent(StrictModel):
    schema_version: Literal["execution.event.v1", "execution.event.v2"] = "execution.event.v1"
    journal_id: str | None = Field(default=None, min_length=1, max_length=200)
    attempt_id: str = Field(min_length=1, max_length=200)
    sequence: int = Field(ge=0)
    kind: EventKind
    source_id: str = Field(min_length=1, max_length=200)
    action_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    evidence_ref: str | None = Field(default=None, max_length=200)
    accounting: ResourceAccounting | None = None
    accounting_mode: Literal["incremental", "cumulative"] = "incremental"

    @model_validator(mode="after")
    def journal_binding(self) -> ExecutionEvent:
        if (self.schema_version == "execution.event.v2") != (self.journal_id is not None):
            raise ValueError("version-2 execution events require a journal identity")
        return self

    @model_serializer(mode="wrap")
    def preserve_legacy(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        result: dict[str, object] = handler(self)
        if self.journal_id is None:
            result.pop("journal_id", None)
        return result


class ExecutionEvidence(StrictModel):
    schema_version: Literal["execution.evidence.v1"] = "execution.evidence.v1"
    attempt_id: str
    adapter: str
    events: list[ExecutionEvent] = Field(max_length=10000)
    complete: bool
    cancellation_confirmed: bool = False
    identity_digest: str | None = None
    boundary_digest: str | None = None
    journal_id: str | None = None

    @model_validator(mode="after")
    def coherent_stream(self) -> ExecutionEvidence:
        sources: set[str] = set()
        terminal = False
        for sequence, event in enumerate(self.events):
            if (event.attempt_id != self.attempt_id or event.sequence != sequence
                    or event.source_id in sources or terminal
                    or (event.journal_id is not None and event.journal_id != self.journal_id)):
                raise ValueError("execution evidence contains a conflicting or misbound event")
            sources.add(event.source_id)
            terminal = event.kind in {"execution.completed", "execution.failed"}
        if self.complete and not terminal:
            raise ValueError("complete execution evidence requires a terminal event")
        if self.cancellation_confirmed != any(event.kind == "cancellation.confirmed" for event in self.events):
            raise ValueError("cancellation confirmation requires observed evidence")
        return self

    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


_event_sink: ContextVar[Callable[[str, ExecutionEvent], object] | None] = ContextVar("aeep_execution_event_sink", default=None)


@contextmanager
def persist_execution_events(sink: Callable[[str, ExecutionEvent], object]) -> Iterator[None]:
    """Bind synchronous durable writes to this invocation and its adapter tasks."""
    token = _event_sink.set(sink)
    try:
        yield
    finally:
        _event_sink.reset(token)


class EventJournal:
    """Bounded, payload-free event stream with source-event replay detection."""

    def __init__(self, attempt_id: str, *, limit: int = 10000) -> None:
        self.attempt_id = attempt_id
        self.journal_id = uuid4().hex
        self._sink = _event_sink.get()
        self.limit = limit
        self.items: list[ExecutionEvent] = []
        self._sources: dict[str, ExecutionEvent] = {}
        self._terminal: EventKind | None = None
        self.changed = asyncio.Event()

    def append(self, kind: EventKind, source_id: str, *, action_digest: str | None = None,
               accounting: ResourceAccounting | None = None, evidence_ref: str | None = None,
               accounting_mode: Literal["incremental", "cumulative"] = "incremental") -> None:
        event = ExecutionEvent(schema_version="execution.event.v2", journal_id=self.journal_id,
                               attempt_id=self.attempt_id, sequence=len(self.items), kind=kind,
                               source_id=source_id, action_digest=action_digest,
                               accounting=accounting, evidence_ref=evidence_ref, accounting_mode=accounting_mode)
        previous = self._sources.get(source_id)
        if previous is not None:
            if previous.model_dump(exclude={"sequence"}) != event.model_dump(exclude={"sequence"}):
                raise ConfigurationError("conflicting execution event replay")
            return
        if self._terminal is not None:
            raise ConfigurationError("execution event after terminal outcome")
        if len(self.items) >= self.limit:
            raise ConfigurationError("execution event limit exceeded")
        # Commit before publishing; storage failure must stop further execution.
        if self._sink is not None:
            self._sink(self.journal_id, event)
        if kind in {"execution.failed", "execution.completed"}:
            self._terminal = kind
        self._sources[source_id] = event
        self.items.append(event)
        self.changed.set()

    def evidence(self, adapter: str, raw: RawExecution) -> ExecutionEvidence:
        return ExecutionEvidence(
            attempt_id=self.attempt_id, adapter=adapter, events=[item.model_copy(deep=True) for item in self.items],
            complete=self._terminal is not None and raw.status not in {ExecutionStatus.TIMEOUT} and raw.metadata.get("execution_stream_complete") is not False,
            cancellation_confirmed=any(item.kind == "cancellation.confirmed" for item in self.items),
            identity_digest=raw.metadata.get("host_runtime_digest"),
            boundary_digest=raw.metadata.get("boundary_digest"),
            journal_id=self.journal_id,
        )


@dataclass(slots=True)
class ExecutionHandle:
    attempt_id: str
    journal: EventJournal
    task: asyncio.Task[RawExecution]
    cancellation: Callable[[], Awaitable[None]] | None = None
    cancellation_requested: bool = field(default=False)
    schema_version: Literal["execution.handle.v1"] = field(default="execution.handle.v1", init=False)


def start_execution(attempt_id: str, adapter: str, run: Callable[[EventJournal], Awaitable[RawExecution]],
                    cancel: Callable[[], Awaitable[None]] | None = None) -> ExecutionHandle:
    journal = EventJournal(attempt_id)

    async def invoke() -> RawExecution:
        journal.append("execution.started", "start")
        try:
            raw = await run(journal)
        except asyncio.CancelledError:
            if journal._terminal is None:
                journal.append("execution.failed", "terminal")
            raise
        except Exception:
            if journal._terminal is None:
                journal.append("execution.failed", "terminal")
            raise
        if journal._terminal is None:
            journal.append("execution.completed" if raw.status == ExecutionStatus.SUCCESS else "execution.failed", "terminal")
        evidence = journal.evidence(adapter, raw)
        raw.metadata["execution_evidence"] = evidence.model_dump(mode="json")
        raw.metadata["execution_evidence_digest"] = evidence.digest()
        return raw

    task = asyncio.create_task(invoke())
    task.add_done_callback(lambda _: journal.changed.set())
    return ExecutionHandle(attempt_id, journal, task, cancel)


async def execution_events(handle: ExecutionHandle) -> AsyncIterator[ExecutionEvent]:
    position = 0
    while True:
        handle.journal.changed.clear()
        while position < len(handle.journal.items):
            yield handle.journal.items[position]
            position += 1
        if handle.task.done():
            return
        await handle.journal.changed.wait()


async def cancel_execution(handle: ExecutionHandle) -> None:
    if handle.task.done() or handle.cancellation_requested:
        return
    handle.cancellation_requested = True
    handle.journal.append("cancellation.requested", "cancel")
    if handle.cancellation is not None:
        await handle.cancellation()
    handle.task.cancel()


def opaque_digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
