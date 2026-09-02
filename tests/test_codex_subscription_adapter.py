from __future__ import annotations

import builtins
import sys
from pathlib import Path
from typing import Any

import pytest

from aeep.hosts import CodexAppServerAdapter, HostProbeStatus, ManagedHostExecutionContext
from aeep.models import (
    ActionRequest,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    ManagedHostExecutorConfig,
    Manifest,
    SideEffect,
    SubscriptionResource,
)
from aeep.router import Router

FAKE = Path(__file__).parent / "fixtures" / "fake_codex_app_server.py"
RESOURCE_ID = "fixture-subscription"


def argv(scenario: str = "success") -> tuple[str, ...]:
    return (sys.executable, "-u", str(FAKE), "--scenario", scenario)


def adapter(
    scenario: str = "success", *, approval_handler: Any = None
) -> CodexAppServerAdapter:
    return CodexAppServerAdapter(
        argv=argv(scenario),
        resource_id=RESOURCE_ID,
        principal_salt=b"fixture-correlation-salt",
        max_message_bytes=1024,
        request_timeout=2,
        approval_handler=approval_handler,
    )


def managed_config(scenario: str = "success", *, ceiling: str = "read") -> dict[str, Any]:
    return {
        "adapter_id": "codex-app-server",
        "argv": list(argv(scenario)),
        "instructions": "Count characters in {input.text}",
        "model_constraints": {"required_capabilities": ["text"]},
        "reasoning_efforts": ["low"],
        "working_directory_policy": "inherit",
        "sandbox_policy": "read_only",
        "approval_ceiling": ceiling,
        "output_mode": "json",
        "timeout_seconds": 1,
        "max_message_bytes": 1024,
        "environment_allowlist": [],
        "store_prompt": False,
        "store_output": False,
        "redaction_policy": "strict",
    }


def context(scenario: str = "success", *, ceiling: str = "read") -> ManagedHostExecutionContext:
    return ManagedHostExecutionContext(
        request=ActionRequest(capability="text.length@1", input={"text": "abc"}),
        instruction="Count characters in abc",
        config=ManagedHostExecutorConfig.model_validate(managed_config(scenario, ceiling=ceiling)),
        attempt=1,
        attempt_id="fixture-attempt",
        output_schema={"type": "object"},
        approved_side_effect=ceiling,
    )


@pytest.mark.asyncio
async def test_auth_required_is_explicit_and_does_not_fallback():
    host = adapter("unauthenticated")
    try:
        probe = await host.probe()
        assert probe.status is HostProbeStatus.AUTH_REQUIRED
        assert probe.supported_features == ("account/read",)
    finally:
        await host.close()


@pytest.mark.asyncio
async def test_adapter_never_reads_codex_auth_files(monkeypatch):
    real_open = builtins.open

    def guarded_open(file: object, *args: object, **kwargs: object):
        if str(file).endswith("auth.json"):
            raise AssertionError("adapter attempted to read Codex credentials")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    host = adapter()
    try:
        account = await host.account()
        assert account.authenticated
    finally:
        await host.close()


@pytest.mark.asyncio
async def test_runtime_models_and_multi_window_quota_are_preserved():
    host = adapter()
    try:
        models = await host.list_models()
        quota = await host.snapshot_capacity()
        account = await host.account()
        assert [item.id for item in models] == ["fixture-model-a", "fixture-model-b"]
        assert [item.window_id for item in quota.windows] == [
            "fixture:primary",
            "fixture:secondary",
        ]
        assert [item.used_percent for item in quota.windows] == [20, 40]
        assert quota.redacted_provider_metadata["reset_credits_available"] == 0
        assert account.principal_digest is not None
        assert "fixture-principal" not in account.model_dump_json()
    finally:
        await host.close()


@pytest.mark.asyncio
async def test_reset_credit_presence_is_telemetry_only():
    host = adapter("credits-present")
    try:
        quota = await host.snapshot_capacity()
        assert quota.redacted_provider_metadata["reset_credits_available"] == 2
        assert all(window.remaining is None for window in quota.windows)
    finally:
        await host.close()


@pytest.mark.asyncio
async def test_managed_action_records_one_turn_reroute_and_token_accounting():
    host = adapter()
    spec = ExecutorSpec(
        id="codex-managed",
        capability="text.length@1",
        kind=ExecutorKind.MANAGED_HOST,
        description="Offline Codex fixture",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"characters": {"type": "integer"}},
            "required": ["characters"],
            "additionalProperties": False,
        },
        side_effect=SideEffect.NONE,
        resource_pool=RESOURCE_ID,
        config=managed_config(),
    )
    router = Router(
        Manifest(
            database=":memory:",
            resources=[
                SubscriptionResource(
                    id=RESOURCE_ID, provider="openai", product="codex"
                )
            ],
            executors=[spec],
        ),
        managed_host_adapters={"codex-app-server": host},
    )
    try:
        outcome = await router.execute(
            ActionRequest(capability="text.length@1", input={"text": "abc"})
        )
        receipt = outcome.receipts[0]
        assert outcome.ok and outcome.output == {"characters": 3}
        assert receipt.metadata["actual_model"] == "fixture-model-b"
        assert receipt.metadata["model_turn_count"] == 1
        assert receipt.metadata["tool_selection_rounds"] == 0
        assert receipt.metadata["implementation_schema_bytes"] == 0
        assert receipt.metadata["output_schema_bytes"] > 0
        assert receipt.metadata["result_bytes"] == 16
        assert receipt.actual_resources.input_tokens == 7
        assert receipt.actual_resources.output_tokens == 3
        assert receipt.accounting.subscription_usage[0].consumed is None
        assert receipt.accounting.model_usage[0].access_channel.value == "subscription"
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_approval_requires_both_host_decision_and_aeep_ceiling():
    def allow(*_args: object) -> bool:
        return True

    read_host = adapter("approval-read", approval_handler=allow)
    write_host = adapter("approval-write", approval_handler=allow)
    try:
        accepted = await read_host.execute(context("approval-read"))
        blocked = await write_host.execute(context("approval-write"))
        assert accepted.status is ExecutionStatus.SUCCESS
        assert accepted.metadata["approval_evidence_digest"] is not None
        assert blocked.status is ExecutionStatus.FAILED
    finally:
        await read_host.close()
        await write_host.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["failure", "timeout", "disconnect"])
async def test_turn_failure_modes_fail_closed(scenario: str):
    host = adapter(scenario)
    try:
        raw = await host.execute(context(scenario))
        assert raw.status is not ExecutionStatus.SUCCESS
    finally:
        await host.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["duplicate-terminal", "conflicting-usage"])
async def test_duplicate_or_conflicting_terminal_evidence_is_rejected(scenario: str):
    host = adapter(scenario)
    try:
        raw = await host.execute(context(scenario))
        assert raw.status is ExecutionStatus.FAILED
        assert raw.error_type == "ProtocolError"
    finally:
        await host.close()
