from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from aeep.capacity import CapacityObservation, CapacityWindow
from aeep.hosts import HostModel, HostProbe, HostProbeStatus, ManagedHostExecutionContext
from aeep.models import (
    ActionRequest,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    Manifest,
    RawExecution,
    SubscriptionResource,
)
from aeep.router import Router

ROOT = Path(__file__).parents[1]


class PrivateManagedHost:
    async def probe(self) -> HostProbe:
        return HostProbe(adapter_id="private", status=HostProbeStatus.READY)

    async def snapshot_capacity(self) -> CapacityObservation:
        return CapacityObservation(
            resource_id="private-plan",
            source="fixture",
            windows=(CapacityWindow(window_id="primary", used_percent=1),),
        )

    async def list_models(self) -> list[HostModel]:
        return [HostModel(id="runtime-model")]

    async def execute(self, context: ManagedHostExecutionContext) -> RawExecution:
        assert "PRIVATE_INPUT_MARKER" in context.instruction
        return RawExecution(
            status=ExecutionStatus.SUCCESS,
            output={"result": "PRIVATE_OUTPUT_MARKER"},
            metadata={"model_turn_count": 1},
        )

    async def interrupt(self, attempt_id: str) -> None:
        return None

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_default_database_omits_managed_prompt_and_output(tmp_path: Path):
    database = tmp_path / "private.sqlite3"
    spec = ExecutorSpec(
        id="private-managed",
        capability="fixture.private@1",
        kind=ExecutorKind.MANAGED_HOST,
        description="privacy fixture",
        resource_pool="private-plan",
        config={
            "adapter_id": "private",
            "argv": [sys.executable, "fixture"],
            "instructions": "Process {input.value}",
            "store_prompt": False,
            "store_output": False,
        },
    )
    router = Router(
        Manifest(
            database=str(database),
            resources=[
                SubscriptionResource(
                    id="private-plan", provider="fixture", product="fixture"
                )
            ],
            executors=[spec],
        ),
        managed_host_adapters={"private": PrivateManagedHost()},
    )
    try:
        outcome = await router.execute(
            ActionRequest(
                capability="fixture.private@1",
                input={"value": "PRIVATE_INPUT_MARKER"},
            )
        )
        assert outcome.output == {"result": "PRIVATE_OUTPUT_MARKER"}
    finally:
        await router.close()
    persisted = database.read_bytes()
    assert b"PRIVATE_INPUT_MARKER" not in persisted
    assert b"PRIVATE_OUTPUT_MARKER" not in persisted


def test_committed_fixture_reports_contain_no_secret_patterns():
    tracked = subprocess.run(
        ["git", "ls-files", "tests/fixtures", "reports/v07"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    patterns = (
        re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
        re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(rb"Authorization:\s*Bearer\s+[A-Za-z0-9._-]{12,}", re.I),
        re.compile(rb'"(?:access|refresh)_token"\s*:\s*"[^"\s]{8,}"', re.I),
    )
    for relative in tracked:
        payload = (ROOT / relative).read_bytes()
        assert not any(pattern.search(payload) for pattern in patterns), relative


def test_verifier_subprocess_enables_offline_guard(monkeypatch):
    from aeep import verification

    observed: dict[str, str] = {}

    def fake_run(*_args: object, **kwargs: object):
        observed.update(kwargs["env"])
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(verification.subprocess, "run", fake_run)
    assert verification._pytest(ROOT, ["tests/test_v07_security.py"])[0]
    assert observed["AEEP_VERIFY_OFFLINE"] == "1"
