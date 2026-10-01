from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import replace

import pytest
from conftest import python_spec

from aeep.errors import ConfigurationError
from aeep.execution import (
    EventJournal,
    ExecutionEvent,
    ExecutionEvidence,
    ExecutorCapabilities,
    cancel_execution,
    execution_events,
    persist_execution_events,
    start_execution,
)
from aeep.hosts.codex_exec import CodexExecAdapter, normalize_exec_events
from aeep.hosts.registry import ManagedHostRegistry
from aeep.models import (
    ActionRequest,
    ExecutionStatus,
    ExecutorSpec,
    Manifest,
    RawExecution,
    ResourceAccounting,
)
from aeep.router import Router

pytestmark = pytest.mark.assessment_contract


def test_event_journal_identity_preserves_nested_streams_and_legacy_bytes(tmp_path):
    from aeep.assessment.repository import AssessmentRepository
    from aeep.store import ReceiptStore

    legacy = ExecutionEvent(attempt_id='legacy', sequence=0, kind='execution.started', source_id='start')
    encoded = legacy.model_dump_json()
    assert 'journal_id' not in encoded
    assert ExecutionEvent.model_validate_json(encoded).model_dump_json() == encoded
    with pytest.raises(ValueError, match='journal identity'):
        ExecutionEvent.model_validate({**legacy.model_dump(), 'schema_version':'execution.event.v2'})
    path = tmp_path / 'nested.sqlite3'
    store = ReceiptStore(path)
    repo = AssessmentRepository(store)
    with persist_execution_events(lambda identity, event: repo.put('execution_event', f'{identity}:{event.sequence}', event)):
        journals = [EventJournal('same-attempt'), EventJournal('same-attempt')]
        for journal in journals:
            journal.append('execution.started', 'start')
    store.close()
    reopened = ReceiptStore(path)
    try:
        for journal in journals:
            saved = AssessmentRepository(reopened).get('execution_event', journal.journal_id + ':0')
            assert saved == journal.items[0].model_dump(mode='json')
        with pytest.raises(ValueError, match='misbound'):
            ExecutionEvidence(attempt_id='same-attempt', adapter='fixture', events=journals[0].items,
                complete=False, journal_id=journals[1].journal_id)
    finally:
        reopened.close()


@pytest.mark.parametrize("scenario,decision", [("approval-read", "permission.granted"), ("approval-write", "permission.denied")])
async def test_canonical_approval_events_preserve_the_operator_ceiling(scenario, decision):
    from test_codex_subscription_adapter import adapter, context

    host = adapter(scenario, approval_handler=lambda *_args: True)
    try:
        handle = await host.start(context(scenario))
        await handle.task
        events = [event async for event in host.events(handle)]
        assert "permission.requested" in [event.kind for event in events]
        assert decision in [event.kind for event in events]
        assert all(event.action_digest for event in events if event.kind.startswith("permission."))
    finally:
        await host.close()


def test_journal_replay_terminal_bounds_and_payload_rejection():
    journal = EventJournal("attempt", limit=2)
    journal.append("usage.reported", "usage", accounting=ResourceAccounting())
    journal.append("usage.reported", "usage", accounting=ResourceAccounting())
    assert len(journal.items) == 1
    with pytest.raises(ConfigurationError, match="conflicting"):
        journal.append("action.started", "usage")
    journal.append("execution.completed", "terminal")
    journal.append("execution.completed", "terminal")
    with pytest.raises(ConfigurationError, match="terminal"):
        journal.append("execution.failed", "different-terminal")
    bounded = EventJournal("attempt", limit=0)
    with pytest.raises(ConfigurationError, match="limit"):
        bounded.append("action.started", "a")
    with pytest.raises(ValueError):
        ExecutionEvidence.model_validate({"attempt_id": "a", "adapter": "a", "events": [],
                                          "complete": True, "prompt": "secret"})


async def test_canonical_execution_stream_and_cancellation_are_distinct():
    started = asyncio.Event()

    async def run(journal):
        journal.append("action.started", "action")
        started.set()
        await asyncio.Event().wait()
        return RawExecution(status=ExecutionStatus.SUCCESS)

    handle = start_execution("attempt", "fixture", run)
    await started.wait()
    await cancel_execution(handle)
    with pytest.raises(asyncio.CancelledError):
        await handle.task
    raw = RawExecution(status=ExecutionStatus.TIMEOUT)
    events = [event async for event in execution_events(handle)]
    assert [event.sequence for event in events] == list(range(len(events)))
    evidence = handle.journal.evidence("fixture", raw)
    assert raw.status is ExecutionStatus.TIMEOUT
    assert not evidence.complete and not evidence.cancellation_confirmed
    assert "cancellation.requested" in [event.kind for event in events]
    await cancel_execution(handle)


def exec_lines():
    return [json.dumps(event) for event in [
        {"type": "thread.started", "thread_id": "transient"},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "item", "type": "agent_message", "text": '{"ok":true}'}},
        {"type": "turn.completed", "usage": {"input_tokens": 7, "cached_input_tokens": 0, "output_tokens": 3}},
    ]]


def test_exec_normalization_deduplicates_and_keeps_partial_usage():
    lines = exec_lines()
    journal = EventJournal("attempt")
    raw = RawExecution(status=ExecutionStatus.SUCCESS)
    normalize_exec_events([*lines, lines[-1]], journal, raw, model="fixture", max_bytes=4096, output_mode="json")
    assert raw.output == {"ok": True}
    assert len(raw.accounting.model_usage) == 1
    assert raw.accounting.model_usage[0].input_tokens == 7
    assert "transient" not in journal.evidence("exec", raw).model_dump_json()
    raw = RawExecution(status=ExecutionStatus.SUCCESS)
    with pytest.raises(ConfigurationError, match="terminal"):
        normalize_exec_events([*lines, json.dumps({"type": "turn.failed"})], EventJournal("a"), raw,
                              model="fixture", max_bytes=4096, output_mode="json")
    assert raw.accounting.model_usage[0].input_tokens == 7


@pytest.mark.parametrize("lines", [["{"], ["[]"], ['{"type":"unknown"}'], exec_lines()[:-1]])
def test_incomplete_exec_stream_is_not_success(lines):
    with pytest.raises((ConfigurationError, ValueError)):
        normalize_exec_events(lines, EventJournal("a"), RawExecution(status="success"),
                              model="fixture", max_bytes=4096, output_mode="json")


async def test_exec_real_process_and_unknown_identity(tmp_path):
    from aeep.hosts.base import ManagedHostExecutionContext

    program = tmp_path / "fixture.py"
    program.write_text("import sys\nsys.stdin.read()\n" + "\n".join(f"print({line!r})" for line in exec_lines()))
    spec = ExecutorSpec(id="exec", capability="fixture", kind="host_managed", description="fixture",
                        resource_pool="pool", config={"adapter_id": "codex-exec", "argv": [sys.executable, str(program)],
                        "instructions": "fixture", "exec_model": "fixture", "timeout_seconds": 2})
    host = CodexExecAdapter(spec)
    context = ManagedHostExecutionContext(ActionRequest(capability="fixture", input={}), "fixture", spec.managed_host_config(), 1, "attempt")
    try:
        raw = await host.execute(context)
        assert raw.status is ExecutionStatus.SUCCESS and raw.output == {"ok": True}
        assert raw.stdout == raw.stderr == ""
        assert await host.resolve_identity(context.config) is None
        assert (await host.snapshot_capacity()).windows[0].confidence == 0
        blocked = await host.execute(replace(context, attempt_id="blocked", expected_runtime_digest="a" * 64))
        assert blocked.status is ExecutionStatus.REJECTED
        assert blocked.error_type == "ENVIRONMENT_VERIFICATION_UNAVAILABLE"
        with pytest.raises(ConfigurationError, match="already started"):
            await host.execute(context)
    finally:
        await host.close()


def test_registry_extensions_are_explicit_and_missing_capabilities_fail():
    registry = ManagedHostRegistry()
    with pytest.raises(ConfigurationError, match="invalid"):
        registry.register_factory("bad:name", lambda *_: None)
    capabilities = ExecutorCapabilities(adapter="unknown")
    with pytest.raises(ConfigurationError, match="isolation"):
        capabilities.require(["isolation"])
    ExecutorCapabilities(adapter="verified", features={"isolation": "supported"}).require(["isolation"])


async def test_router_persists_canonical_evidence_without_payloads():
    from aeep.assessment.repository import AssessmentRepository

    spec = python_spec("fixture", "test_v08_execution_boundary:echo")
    router = Router(Manifest(database=":memory:", executors=[spec]))
    try:
        outcome = await router.execute(ActionRequest(capability=spec.capability, input={"secret": "never-persist"}))
        receipt = outcome.receipts[-1]
        digest = receipt.metadata["execution_evidence_digest"]
        evidence = AssessmentRepository(router.store).get("execution_evidence", digest)
        assert evidence["attempt_id"] == receipt.metadata["attempt_id"]
        assert "never-persist" not in json.dumps(evidence)
        stored = AssessmentRepository(router.store).get("execution_event", evidence["journal_id"] + ":0")
        assert stored["kind"] == "execution.started"
    finally:
        await router.close()


def echo(value):
    return value


async def test_events_commit_before_completion_and_survive_interruption(tmp_path):
    from aeep.assessment.repository import AssessmentRepository
    from aeep.store import ReceiptStore

    path = tmp_path / "events.sqlite3"
    store = ReceiptStore(path)
    repository = AssessmentRepository(store)
    observed = asyncio.Event()

    async def run(journal):
        journal.append("usage.reported", "partial", accounting=ResourceAccounting())
        journal.append("usage.reported", "partial", accounting=ResourceAccounting())
        observed.set()
        await asyncio.Event().wait()
        return RawExecution(status="success")

    try:
        with persist_execution_events(lambda identity, event: repository.put("execution_event", f"{identity}:{event.sequence}", event)):
            handle = start_execution("interrupted", "fixture", run)
        await observed.wait()
        reopened = ReceiptStore(path)
        try:
            saved = AssessmentRepository(reopened).get("execution_event", f"{handle.journal.journal_id}:1")
            assert saved["kind"] == "usage.reported" and saved["attempt_id"] == "interrupted"
            assert not handle.task.done()
        finally:
            reopened.close()
        await cancel_execution(handle)
        with pytest.raises(asyncio.CancelledError):
            await handle.task
        assert len(handle.journal.items) == 4  # start, one usage, requested cancellation, uncertain failure
        # The invocation-local sink cannot leak into unrelated later work.
        EventJournal("other").append("execution.started", "start")
        assert store._connection.execute("SELECT COUNT(*) FROM assessment_records WHERE kind='execution_event'").fetchone()[0] == 4
    finally:
        store.close()


def test_failed_event_storage_stops_publication():
    def fail(*_args):
        raise OSError("storage unavailable")

    with persist_execution_events(fail):
        journal = EventJournal("attempt")
    with pytest.raises(OSError, match="storage unavailable"):
        journal.append("execution.started", "start")
    assert journal.items == []


def test_evidence_rejects_misbound_events_and_unobserved_completion():
    journal = EventJournal("attempt")
    journal.append("execution.started", "start")
    incomplete = journal.evidence("fixture", RawExecution(status="timeout"))
    with pytest.raises(ValueError, match="terminal"):
        ExecutionEvidence.model_validate({**incomplete.model_dump(), "complete": True})
    with pytest.raises(ValueError, match="confirmation"):
        ExecutionEvidence.model_validate({**incomplete.model_dump(), "cancellation_confirmed": True})
    with pytest.raises(ValueError, match="misbound"):
        ExecutionEvidence.model_validate({**incomplete.model_dump(), "attempt_id": "other"})
    journal.append("execution.completed", "done")
    completed = journal.evidence("fixture", RawExecution(status="success"))
    data = completed.model_dump()
    data["events"].append(data["events"][0])
    with pytest.raises(ValueError, match="misbound"):
        ExecutionEvidence.model_validate(data)


def test_required_capability_is_checked_before_ranking():
    spec = python_spec("fixture", "test_v08_execution_boundary:echo")
    historical = spec.model_dump(mode="json")
    assert "required_capabilities" not in historical
    spec.required_capabilities = ("isolation",)
    router = Router(Manifest(database=":memory:", executors=[spec]))
    try:
        decision = router.route(ActionRequest(capability=spec.capability, input={}))
        assert decision.selected_executor_id is None
    finally:
        router.store.close()


async def test_exec_events_are_durable_before_process_completion(tmp_path):
    from aeep.hosts.base import ManagedHostExecutionContext

    release = tmp_path / 'release'
    script = tmp_path / 'stream.py'
    script.write_text('import pathlib,time\n' + '\n'.join(f'print({line!r},flush=True)' for line in exec_lines()) +
        f'\nwhile not pathlib.Path({str(release)!r}).exists(): time.sleep(.01)\n')
    spec = ExecutorSpec(id='stream', capability='fixture', kind='host_managed', resource_pool='pool', description='stream fixture',
        config={'adapter_id':'codex-exec','argv':[sys.executable,str(script)],'instructions':'fixture','exec_model':'fixture','timeout_seconds':5})
    host = CodexExecAdapter(spec)
    persisted = []
    try:
        with persist_execution_events(lambda journal, event: persisted.append((journal,event))):
            handle = await host.start(ManagedHostExecutionContext(ActionRequest(capability='fixture'), 'fixture', spec.managed_host_config(), 1, 'streamed'))
        async with asyncio.timeout(3):
            async for event in host.events(handle):
                if event.kind == 'usage.reported':
                    break
        assert not handle.task.done()
        assert any(event.kind == 'usage.reported' for _,event in persisted)
        assert all('agent_message' not in event.model_dump_json() for _,event in persisted)
        release.touch()
        raw = await handle.task
        assert raw.output == {'ok':True}
        assert len(raw.accounting.model_usage) == 1
        assert host.capabilities().features['streaming'] == 'supported'
    finally:
        release.touch()
        await host.close()


async def test_stream_sink_failure_stops_process_and_retains_measurements():
    from aeep.executors.base import ExecutionContext
    from aeep.executors.command import CommandExecutor

    def broken_sink(_chunk):
        raise OSError('storage unavailable')

    spec = ExecutorSpec(id='sink',capability='fixture',kind='command',description='sink failure fixture',
        config={'argv':[sys.executable,'-c',"import time; print('event',flush=True); time.sleep(30)"],'timeout_seconds':5})
    context = ExecutionContext(ActionRequest(capability='fixture'),spec,spec.estimate,1)
    raw = await asyncio.wait_for(CommandExecutor(stdout_observer=broken_sink).execute(context),3)
    assert raw.status == ExecutionStatus.FAILED and raw.error_type == 'STREAM_OBSERVER_FAILED'
    assert raw.resources.latency_ms > 0 and raw.exit_code is not None
