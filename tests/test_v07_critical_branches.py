from __future__ import annotations

import hashlib
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import aeep.hosts.codex_app_server as app_server
import aeep.x402.conformance as x402_conformance
from aeep.attempts import AttemptService, ExecutionAttempt, ExecutionAttemptState
from aeep.capacity import (
    CapacityAuthorizationEvidence,
    CapacityObservation,
    CapacitySignature,
    CapacityTransferability,
    CapacityWindow,
    observation_quota,
    require_entitlement_authority,
)
from aeep.errors import ConfigurationError
from aeep.hosts import CodexAppServerAdapter, CodexAppServerTransport, CodexProtocolError
from aeep.models import ExecutorKind, ExecutorSpec, SideEffect
from aeep.store import ReceiptStore

NOW = datetime(2030, 1, 1, tzinfo=UTC)
DIGEST = f"sha256:{'a' * 64}"
OTHER_DIGEST = f"sha256:{'b' * 64}"


def _attempt(**updates: object) -> ExecutionAttempt:
    values: dict[str, object] = {
        "attempt_id": "attempt-critical",
        "decision_id": "decision-critical",
        "action_digest": DIGEST,
        "executor_id": "executor-critical",
        "executor_fingerprint": DIGEST,
        "side_effect": SideEffect.READ,
        "idempotent": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(updates)
    return ExecutionAttempt.model_validate(values)


@pytest.mark.parametrize(
    "updates, message",
    [
        ({"created_at": datetime(2030, 1, 1)}, "timezone-aware"),
        ({"updated_at": NOW - timedelta(seconds=1)}, "before creation"),
        ({"state": ExecutionAttemptState.CLAIMED}, "require an owner"),
        (
            {"state": ExecutionAttemptState.INVOKING, "owner_id": "worker"},
            "invocation-start",
        ),
        ({"retry_eligible": True, "idempotent": False}, "retry eligible"),
        (
            {"retry_eligible": True, "side_effect": SideEffect.WRITE},
            "retry eligible",
        ),
        ({"cash_reservation_ids": ("cash", "cash")}, "must be unique"),
        (
            {"capacity_reservation_ids": ("capacity", "capacity")},
            "must be unique",
        ),
    ],
)
def test_attempt_contract_rejects_unsafe_recovery_states(
    updates: dict[str, object], message: str
):
    with pytest.raises(ValueError, match=message):
        _attempt(**updates)


def test_attempt_recovery_rejects_uninspectable_states():
    store = ReceiptStore(":memory:")
    try:
        service = AttemptService(store)
        with pytest.raises(ValueError, match="does not exist"):
            service.recover_after_lease("missing", inspected_external_status=None, now=NOW)

        created = store.create_execution_attempt(
            _attempt(
                created_at=NOW - timedelta(minutes=2),
                updated_at=NOW - timedelta(minutes=2),
            )
        )
        with pytest.raises(ValueError, match="still active"):
            service.recover_after_lease(
                created.attempt_id, inspected_external_status=None, now=NOW
            )

        claimed = store.claim_execution_attempt(
            created.attempt_id,
            owner_id="worker",
            claimed_at=NOW - timedelta(minutes=1),
            lease_expires_at=NOW - timedelta(seconds=1),
        )
        with pytest.raises(ValueError, match="only an expired INVOKING"):
            service.recover_after_lease(
                claimed.attempt_id, inspected_external_status=None, now=NOW
            )

        reserved = store.transition_execution_attempt(
            claimed.attempt_id,
            expected_state=claimed.state,
            expected_version=claimed.version,
            target_state=ExecutionAttemptState.RESERVED,
            updated_at=NOW,
        )
        invoking = store.transition_execution_attempt(
            reserved.attempt_id,
            expected_state=reserved.state,
            expected_version=reserved.version,
            target_state=ExecutionAttemptState.INVOKING,
            updated_at=NOW,
            invocation_start_digest=DIGEST,
        )
        recovered = service.recover_after_lease(
            invoking.attempt_id, inspected_external_status="running", now=NOW
        )
        assert recovered.recovery_reason == "external status inspected: running"
    finally:
        store.close()


def _observation(*windows: CapacityWindow) -> CapacityObservation:
    return CapacityObservation(
        resource_id="capacity-critical",
        source="fixture",
        observed_at=NOW,
        windows=windows,
    )


@pytest.mark.parametrize(
    "window, expected",
    [
        (CapacityWindow(window_id="abundant", used_percent=25), "abundant"),
        (CapacityWindow(window_id="tight", used_percent=70), "tight"),
        (CapacityWindow(window_id="critical", used_percent=90), "critical"),
        (CapacityWindow(window_id="exhausted", used_percent=100), "exhausted"),
        (CapacityWindow(window_id="unknown"), "unknown"),
        (
            CapacityWindow(window_id="hard", used_percent=1, exhausted=True),
            "exhausted",
        ),
    ],
)
def test_capacity_quota_boundaries(window: CapacityWindow, expected: str):
    assert observation_quota(_observation(window), unit="provider_unit", now=NOW).state == expected


def test_capacity_quota_preserves_unknown_and_expired_reset():
    observation = _observation(
        CapacityWindow(
            window_id="other-unit",
            unit="turn",
            remaining=1,
            allowance=2,
            reset_at=NOW - timedelta(seconds=1),
        )
    )
    assert observation_quota(observation, unit="provider_unit", now=NOW).state == "unknown"
    assert observation_quota(observation, unit="turn", now=NOW).reset_at is None


def _authority(beneficiary: str | None = OTHER_DIGEST) -> CapacityAuthorizationEvidence:
    return CapacityAuthorizationEvidence(
        provider_id="fixture",
        resource_id="capacity-critical",
        resource_fingerprint=DIGEST,
        issuer_principal_digest=DIGEST,
        authorized_beneficiary_digest=beneficiary,
        transferability=CapacityTransferability.PROVIDER_AUTHORIZED,
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        signature=CapacitySignature(algorithm="fixture", key_id="key", value="signed"),
    )


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"requested": Decimal(0)}, "positive"),
        ({"known_available": None}, "unknown capacity"),
        ({"requested": Decimal(2)}, "exceeds"),
        (
            {"authorization": _authority(), "issuer_principal_digest": OTHER_DIGEST},
            "issuer does not match",
        ),
        (
            {"authorization": _authority(DIGEST)},
            "beneficiary does not match",
        ),
    ],
)
def test_transferability_authority_fails_closed(kwargs: dict[str, object], message: str):
    values: dict[str, object] = {
        "transferability": CapacityTransferability.PROVIDER_AUTHORIZED,
        "issuer_principal_digest": DIGEST,
        "beneficiary_principal_digest": OTHER_DIGEST,
        "known_available": Decimal(1),
        "requested": Decimal(1),
        "authorization": _authority(),
    }
    values.update(kwargs)
    with pytest.raises(ValueError, match=message):
        require_entitlement_authority(**values)  # type: ignore[arg-type]


def test_transferability_allows_self_and_unrestricted_provider_authority():
    require_entitlement_authority(
        transferability=CapacityTransferability.SAME_PRINCIPAL,
        issuer_principal_digest=DIGEST,
        beneficiary_principal_digest=DIGEST,
        known_available=Decimal(1),
        requested=Decimal(1),
        authorization=None,
    )
    require_entitlement_authority(
        transferability=CapacityTransferability.PROVIDER_AUTHORIZED,
        issuer_principal_digest=DIGEST,
        beneficiary_principal_digest=OTHER_DIGEST,
        known_available=Decimal(1),
        requested=Decimal(1),
        authorization=_authority(None),
    )


def test_transport_constructor_and_write_boundaries():
    with pytest.raises(ConfigurationError, match="absolute argv"):
        CodexAppServerTransport(())
    with pytest.raises(ConfigurationError, match="NUL-free"):
        CodexAppServerTransport((sys.executable, "bad\0argument"))
    with pytest.raises(ConfigurationError, match="lowercase hex"):
        CodexAppServerTransport((sys.executable,), executable_sha256="sha256:BAD")

    digest = hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()
    assert CodexAppServerTransport(
        (sys.executable,), executable_sha256=f"sha256:{digest}"
    ).executable_sha256 == f"sha256:{digest}"


@pytest.mark.asyncio
async def test_transport_dispatch_and_io_boundaries():
    tiny = CodexAppServerTransport((sys.executable,), max_message_bytes=1)
    with pytest.raises(CodexProtocolError, match="outbound"):
        await tiny._write({})

    transport = CodexAppServerTransport((sys.executable,))
    with pytest.raises(CodexProtocolError, match="not running"):
        await transport._write({})
    await transport._read_stdout()
    await transport._read_stderr()
    await transport._watch_process()

    seen: list[tuple[str, dict[str, object]]] = []
    unsubscribe = transport.subscribe(lambda method, params: seen.append((method, params)))
    await transport._dispatch({"method": "notice", "params": []})
    unsubscribe()
    assert seen == [("notice", {})]

    with pytest.raises(CodexProtocolError, match="invalid request ID"):
        await transport._dispatch({"id": True, "result": {}})
    with pytest.raises(CodexProtocolError, match="no pending"):
        await transport._dispatch({"id": 9, "result": {}})
    transport._expired_ids.add(10)
    await transport._dispatch({"id": 10, "result": {}})
    assert not transport._expired_ids

    error_future = asyncio_future()
    transport._pending[11] = error_future
    await transport._dispatch({"id": 11, "error": {"code": 1}})
    with pytest.raises(app_server.CodexRequestError):
        await error_future

    result_future = asyncio_future()
    transport._pending[12] = result_future
    await transport._dispatch({"id": 12, "result": []})
    with pytest.raises(CodexProtocolError, match="result must be an object"):
        await result_future

    transport._write = AsyncMock()  # type: ignore[method-assign]
    with pytest.raises(CodexProtocolError, match="invalid ID"):
        await transport._handle_server_request(True, "unknown", {})
    await transport._handle_server_request("server-1", "unknown", {})
    with pytest.raises(CodexProtocolError, match="duplicate"):
        await transport._handle_server_request("server-1", "unknown", {})

    class AwaitableDecision:
        def __await__(self):
            yield
            return True

    transport.approval_ceiling = SideEffect.DESTRUCTIVE
    transport.approval_handler = lambda *_args: AwaitableDecision()  # type: ignore[assignment]
    with pytest.raises(CodexProtocolError, match="synchronous"):
        await transport._handle_server_request(
            "server-2", "item/commandExecution/requestApproval", {}
        )


def asyncio_future():
    import asyncio

    return asyncio.get_running_loop().create_future()


@pytest.mark.asyncio
async def test_transport_stderr_bounds_and_failure_fanout():
    class Reader:
        def __init__(self) -> None:
            self.chunks = [b"abcd", b"ef", b""]

        async def read(self, _size: int) -> bytes:
            return self.chunks.pop(0)

    transport = CodexAppServerTransport((sys.executable,), max_stderr_bytes=2)
    transport._process = SimpleNamespace(stderr=Reader())  # type: ignore[assignment]
    await transport._read_stderr()
    assert bytes(transport.stderr) == b"ab"
    assert transport.stderr_truncated

    pending = asyncio_future()
    done = asyncio_future()
    done.set_result({})
    transport._process = None
    transport._pending = {1: pending, 2: done}
    first = RuntimeError("first")
    transport._fail(first)
    transport._fail(RuntimeError("second"))
    with pytest.raises(RuntimeError, match="first"):
        await pending
    with pytest.raises(CodexProtocolError, match="transport failed"):
        transport._raise_if_failed()


def test_adapter_constructor_and_executor_boundaries():
    with pytest.raises(ConfigurationError, match="HMAC salt"):
        CodexAppServerAdapter(
            argv=(sys.executable,), resource_id="resource", principal_salt=b""
        )

    command = ExecutorSpec(
        id="command",
        capability="fixture@1",
        kind=ExecutorKind.COMMAND,
        description="fixture",
        config={"argv": [sys.executable, "-V"]},
    )
    with pytest.raises(ConfigurationError, match="managed-host resource"):
        CodexAppServerAdapter.from_executor(command, principal_salt=b"salt")

    managed = ExecutorSpec(
        id="managed",
        capability="fixture@1",
        kind=ExecutorKind.MANAGED_HOST,
        description="fixture",
        resource_pool="resource",
        config={
            "adapter_id": "other-adapter",
            "argv": [sys.executable],
            "instructions": "fixture",
        },
    )
    with pytest.raises(ConfigurationError, match="does not select"):
        CodexAppServerAdapter.from_executor(managed, principal_salt=b"salt")


@pytest.mark.asyncio
async def test_model_catalog_rejects_malformed_and_repeated_pages():
    class Pages:
        protocol_version = "fixture"

        def __init__(self, pages: list[dict[str, object]]) -> None:
            self.pages = pages

        async def request(self, _method: str, _params: dict[str, object]):
            return self.pages.pop(0)

    host = CodexAppServerAdapter(
        argv=(sys.executable,), resource_id="resource", principal_salt=b"salt"
    )
    host.transport = Pages([{"data": None}])  # type: ignore[assignment]
    with pytest.raises(CodexProtocolError, match="data page"):
        await host.list_models()

    host.transport = Pages(  # type: ignore[assignment]
        [
            {
                "data": [None, {}, {"model": "repeat"}, {"model": "repeat"}],
                "nextCursor": "repeat",
            }
        ]
    )
    with pytest.raises(CodexProtocolError, match="cursor repeated"):
        await host.list_models()

    host.transport = Pages(  # type: ignore[assignment]
        [
            {"data": [{"model": "first"}], "nextCursor": "page-2"},
            {"data": [{"id": "second", "inputModalities": ["text", 1]}]},
        ]
    )
    assert [model.id for model in await host.list_models()] == ["first", "second"]


@pytest.mark.asyncio
async def test_turn_collector_rejects_unbound_or_oversized_events():
    collector = app_server._TurnCollector(max_output_bytes=3)
    collector.thread_id = "thread"
    collector.turn_id = "turn"
    collector.handle("model/rerouted", {"threadId": "other", "toModel": "ignored"})
    collector.handle("model/rerouted", {"turnId": "other", "toModel": "ignored"})
    collector.handle("thread/tokenUsage/updated", {"tokenUsage": {"total": "bad"}})
    collector.handle("item/completed", {"item": None})
    collector.handle("item/completed", {"item": {"type": "agentMessage", "text": 1}})
    assert collector.actual_model is None and collector.output_parts == []

    invalid = app_server._TurnCollector(max_output_bytes=3)
    invalid.handle("turn/completed", {"turn": {}})
    with pytest.raises(CodexProtocolError, match="terminal state"):
        await invalid.future

    oversized = app_server._TurnCollector(max_output_bytes=3)
    oversized.handle("item/completed", {"item": {"type": "agentMessage", "text": "long"}})
    oversized.handle("turn/completed", {"turn": {"status": "completed"}})
    with pytest.raises(CodexProtocolError, match="exceeds"):
        await oversized.future

    completed = app_server._TurnCollector(max_output_bytes=3)
    completed.future.set_result(None)  # type: ignore[arg-type]
    completed.handle("turn/completed", {"turn": {"status": "completed"}})
    completed._reject("already complete")
    assert completed.error is not None

    assert app_server._token_usage(None) is None
    assert app_server._token_usage({"inputTokens": True}) is None
    assert app_server._approval_side_effect("item/fileChange/requestApproval", {}) is SideEffect.WRITE
    assert app_server._approval_side_effect(
        "item/commandExecution/requestApproval", {"commandActions": [{"type": "read"}]}
    ) is SideEffect.READ
    assert app_server._approval_side_effect(
        "item/commandExecution/requestApproval", {"commandActions": []}
    ) is SideEffect.DESTRUCTIVE


@pytest.mark.parametrize(
    "scenario, message",
    [
        ("canonical", "canonical serialization"),
        ("binding", "entitlement-bound"),
        ("maximum", "maximum or unit"),
        ("beneficiary", "beneficiary or action"),
        ("release", "partial use"),
        ("dispute", "overclaim"),
    ],
)
def test_x402_conformance_detects_corrupt_local_evidence(
    monkeypatch: pytest.MonkeyPatch, scenario: str, message: str
):
    real_commit = x402_conformance.commit
    real_reconcile = x402_conformance.reconcile

    if scenario == "canonical":
        calls = 0

        def unstable_bytes(_commitment: object) -> bytes:
            nonlocal calls
            calls += 1
            return str(calls).encode()

        monkeypatch.setattr(x402_conformance, "canonical_commitment_bytes", unstable_bytes)
    elif scenario in {"binding", "maximum", "beneficiary"}:

        def corrupt_commit(entitlement: object, *, enabled: bool = False):
            batch = real_commit(entitlement, enabled=enabled)  # type: ignore[arg-type]
            field = {
                "binding": {"entitlement_digest": OTHER_DIGEST},
                "maximum": {"maximum_quantity": Decimal(9)},
                "beneficiary": {"beneficiary_principal_digest": DIGEST},
            }[scenario]
            return batch.model_copy(
                update={"commitment": batch.commitment.model_copy(update=field)}
            )

        monkeypatch.setattr(x402_conformance, "commit", corrupt_commit)
    else:

        def corrupt_reconcile(
            record: object, *, claimed_quantity: Decimal, release_remaining: bool = False
        ):
            if scenario == "release" and release_remaining:
                return record
            if scenario == "dispute" and claimed_quantity == 11:
                return record
            return real_reconcile(  # type: ignore[arg-type]
                record,
                claimed_quantity=claimed_quantity,
                release_remaining=release_remaining,
            )

        monkeypatch.setattr(x402_conformance, "reconcile", corrupt_reconcile)

    with pytest.raises(AssertionError, match=message):
        x402_conformance.run_local_conformance()
