from __future__ import annotations

import asyncio
import os
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_codex_subscription_adapter import RESOURCE_ID, adapter, context, managed_config

from aeep.assessment.conformance import probe_workers
from aeep.models import (
    ExecutorKind,
    ExecutorSpec,
    ManagedHostExecutorConfig,
    ManagedHostInvocation,
    Manifest,
    SubscriptionResource,
)
from aeep.router import Router

pytestmark = pytest.mark.assessment_boundary


def worker(role):
    return ExecutorSpec(id=role, capability="text.length@1", kind=ExecutorKind.MANAGED_HOST, description="Offline worker fixture", resource_pool=RESOURCE_ID, config={**managed_config(), "adapter_id": f"codex-app-server:{role}"})


async def test_workers_use_independent_processes_and_candidate_stays_inactive():
    baseline, candidate = worker("baseline"), worker("candidate")
    candidate.enabled = False
    router = Router(Manifest(database=":memory:", executors=[baseline], resources=[SubscriptionResource(id=RESOURCE_ID, provider="openai", product="codex")]))
    trial = router._campaign_router([candidate, baseline], plan_digest="a" * 64)
    try:
        assert router.managed_hosts.ids() == ("codex-app-server:baseline",)
        assert not router.registry.contains(candidate.id) and candidate.enabled is False
        left = trial.managed_hosts.get("codex-app-server:baseline")
        right = trial.managed_hosts.get("codex-app-server:candidate")
        await left.probe()
        await right.probe()
        assert left.transport._process.pid != right.transport._process.pid
        assert left.principal_salt == right.principal_salt
    finally:
        await trial.close()
        await router.close()
    assert not left.transport.running and not right.transport.running


@pytest.mark.parametrize("rejected", [None, "permissions", "scoped"])
async def test_fresh_worker_directories_and_permission_acknowledgement(tmp_path, monkeypatch, rejected):
    host = adapter()
    host.transport.max_message_bytes = 16384
    original = host.transport.request
    directories = []
    model_calls = []

    async def request(method, params=None, **kwargs):
        params = params or {}
        if method == "skills/list":
            return {"data": []}
        if method == "app/installed":
            return {"apps": []}
        if method == "mcpServerStatus/list":
            return {"data": []}
        if method == "thread/start":
            cwd = Path(params["cwd"])
            assert cwd not in directories and await asyncio.to_thread(lambda: list(cwd.iterdir())) == []
            directories.append(cwd)
            (cwd / "leftover").write_text("must not reach the next trial")
            assert params["permissions"] == "aeep_assessment" and "sandbox" not in params
            assert params["config"]["permissions.aeep_assessment.filesystem"] == {":minimal": "read", ":workspace_roots": {".": "read"}}
            result = await original(method, params, **kwargs)
            result.update(cwd=str(cwd), approvalPolicy="never", approvalsReviewer="user", activePermissionProfile={"id": "aeep_assessment", "extends": None})
            if rejected == "permissions":
                result["approvalPolicy"] = "on-request"
            return result
        if method == "turn/start":
            model_calls.append(method)
        return await original(method, params, **kwargs)

    monkeypatch.setattr(host.transport, "request", request)
    ctx = context()
    config = ctx.config.model_copy(update={"worker_workspace": "temporary", "invocation": ManagedHostInvocation()})
    expected = await host.resolve_identity(config) if rejected == "scoped" else None
    ctx = replace(ctx, config=config, expected_runtime_digest=expected)
    try:
        for _ in range(2):
            result = await host.execute(ctx)
            assert all(not path.exists() for path in directories)
            if rejected:
                assert result.metadata["model_turn_count"] == 0
                assert result.metadata["host_failure_code"] == "environment_verification_unavailable"
            else:
                assert result.output == {"characters": 3}
        assert len(model_calls) == (0 if rejected else 2)
    finally:
        await host.close()


def test_worker_config_preserves_legacy_and_requires_explicit_inventory():
    assert "worker_workspace" not in ManagedHostExecutorConfig.model_validate(managed_config()).model_dump()
    with pytest.raises(ValidationError, match="reviewed invocation"):
        ManagedHostExecutorConfig.model_validate({**managed_config(), "worker_workspace": "temporary"})


@pytest.mark.parametrize("incomplete", [False, True])
async def test_session_probe_retains_permissions_when_inventory_fails(monkeypatch, incomplete):
    from aeep.assessment import conformance

    transports = []

    class Transport:
        protocol_version = "fixture"

        def __init__(self, argv, *, cwd, **kwargs):
            self.cwd = cwd
            self.closed = False
            transports.append(self)

        async def request(self, method, params=None):
            if method == "skills/list":
                return {"data": []}
            if method == "app/installed":
                return {"apps": []}
            if method == "mcpServerStatus/list":
                return {"data": [{"name": "fixture", "tools": {}, "toolsError": "incomplete"}]} if incomplete and "threadId" in params else {"data": []}
            assert method == "thread/start"  # No model execution or credential requests.
            return {"thread": {"id": "fixture"}, "cwd": self.cwd, "activePermissionProfile": {"id": "aeep_assessment", "extends": None}, "approvalPolicy": "never", "approvalsReviewer": "user"}

        async def close(self):
            self.closed = True

    monkeypatch.setattr(conformance, "CodexAppServerTransport", Transport)
    result = await conformance.probe_sessions(Path("/fixture/codex"))
    assert len(transports) == 2 and transports[0].cwd != transports[1].cwd
    assert await asyncio.to_thread(lambda: all(item.closed and not Path(item.cwd).exists() for item in transports))
    for item in result:
        assert item["profile_acknowledged"] and item["approvals_acknowledged"] and item["cwd_acknowledged"]
        assert item["model_turns_started"] == 0 and item["tool_boundary_verified"] is False
        assert item["stage"] == ("thread_inventory" if incomplete else "complete")
        assert ("error_type" in item) is incomplete


def test_controlled_comparison_allows_worker_names_but_not_different_adapters(tmp_path):
    from aeep.assessment.comparison import choices
    from aeep.assessment.models import AssessmentSubject

    candidate, baseline = worker("candidate"), worker("baseline")
    baseline.config["invocation"] = {"mode": "turn"}
    candidate.config["invocation"] = {"mode": "skill", "skill_name": "fixture", "skill_path": str(tmp_path / "SKILL.md"), "skill_sha256": "0" * 64}
    subject = AssessmentSubject(kind="skill", location=str(tmp_path), dependency_digests={})
    assert choices(subject, candidate, baseline)["choices"][1]["available"]
    candidate.config["adapter_id"] = "different-host"
    assert not choices(subject, candidate, baseline)["choices"][1]["available"]


async def test_onboarding_shows_two_workers_and_282_turns_without_starting_them(tmp_path):
    import json
    import sys

    from aeep.assessment.models import AssessmentLimits
    from aeep.assessment.onboarding import initialize

    skill = tmp_path / "SKILL.md"
    skill.write_text("---\nname: parser\ndescription: Parse CSV records.\n---\nReturn records from CSV.")
    result = await initialize(tmp_path / "assessment", skill, "csv", Path(sys.executable), AssessmentLimits(max_operations=10000, max_model_turns=300, max_elapsed_seconds=3600))
    bundle = json.loads(await asyncio.to_thread(Path(result["review_bundle"]).read_text))
    budget = bundle["budget"]
    assert budget["model_worker_profile_count"] == 2
    assert budget["minimum_trial_model_turns"] == 282
    assert budget["screening_trial_model_turns"] == 16
    assert budget["measurement_concurrency"] == 1
    assert bundle["authorization"]["limits"]["max_model_turns"] == 300


@pytest.mark.parametrize("enforced", [True, False])
def test_boundary_probe_detects_ignored_restrictions(tmp_path, monkeypatch, enforced):
    import sys
    import tomllib

    def run(argv, *, cwd, **kwargs):
        profile = tomllib.loads(argv[argv.index("-c") + 1])
        assert profile["permissions"]["aeep_assessment"]["filesystem"] == {":minimal": "read", ":workspace_roots": {".": "write"}}
        target = Path(argv[-1])
        if enforced and not target.is_relative_to(cwd):
            return subprocess.CompletedProcess(argv, 1, b"", b"Operation not permitted")
        if Path(argv[-2]).name == "touch":
            target.touch()
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        return subprocess.CompletedProcess(argv, 0, target.read_bytes(), b"")

    monkeypatch.setattr(subprocess, "run", run)
    result = probe_workers(Path(sys.executable))
    assert result["filesystem_verified"] is enforced
    assert result["model_turns_started"] == 0 and result["tool_boundary_verified"] is False
    assert len(result["workers"]) == 2


@pytest.mark.codex_conformance
def test_installed_codex_worker_filesystem_boundary():
    executable = os.environ.get("AEEP_CODEX_EXECUTABLE")
    if not executable:
        pytest.skip("set AEEP_CODEX_EXECUTABLE for authorized no-model Codex conformance")
    result = probe_workers(Path(executable))
    assert result["filesystem_verified"], result
    assert result["model_turns_started"] == 0 and result["tool_boundary_verified"] is False
