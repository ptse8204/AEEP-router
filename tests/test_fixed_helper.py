from __future__ import annotations

import asyncio
import sys
from datetime import timedelta

import pytest

from aeep.assessment.onboarding import reference_spec
from aeep.assessment.repository import AssessmentRepository
from aeep.economic.prepared import executor_fingerprint
from aeep.errors import ConfigurationError, NoRouteError
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from aeep.models import ActionRequest, ExecutorKind, Manifest, TaskScope, utc_now
from aeep.router import Router


def forbidden(*args, **kwargs):
    raise AssertionError("control used capability selection")


@pytest.fixture
def fixed(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    monkeypatch.setattr(NativeSandboxConfig, "argv", lambda self, command: command)
    monkeypatch.setattr(Router, "route", forbidden)
    monkeypatch.setattr(Router, "route_with_discovery", forbidden)
    monkeypatch.setattr("aeep.router.score_candidate", forbidden)
    boundary = NativeSandboxConfig(binary=str(root / "launcher"), binary_sha256="sha256:" + "a"*64,
                                   project_root=str(root), write_roots=[str(root / "data")])
    spec = reference_spec("csv").model_copy(update={"kind": ExecutorKind.COMMAND, "config": {
        "argv": [sys.executable, "-I", "-c", 'import json; print(json.dumps({"records": []}))'],
        "argv_literal": True, "output": {"type": "json"}, "timeout_seconds": 1,
        "native_sandbox": boundary.model_dump(mode="json")}})
    router = Router(Manifest(database=str(root / "state.db"), executors=[spec]), manifest_path=root / "manifest.json")
    repo = AssessmentRepository(router.store)
    scope = TaskScope(scope_id="fixed", project_root=str(root), executor_fingerprints={spec.id: executor_fingerprint(spec)},
                      max_attempts=1, max_attempt_seconds=2, expires_at=utc_now()+timedelta(minutes=5))
    digest = repo.put("task_scope", scope.scope_id, scope)
    repo.review(digest)
    router.bind_task_scope(scope.scope_id)
    return router, repo, scope, digest, spec


async def test_fixed_no_selection_and_atomic_allowance(fixed):
    router, _repo, _scope, _digest, spec = fixed
    request = ActionRequest(capability=spec.capability, input={"text": "", "delimiter": ","})
    try:
        results = await asyncio.gather(*(router.execute_fixed(request, spec.id) for _ in range(2)), return_exceptions=True)
        assert sum(not isinstance(item, BaseException) and item.ok for item in results) == 1
        assert sum(isinstance(item, ConfigurationError) for item in results) == 1
        assert not router._fixed_dispatches
    finally:
        await router.close()


@pytest.mark.parametrize("invalid", ["revoked", "expired"])
async def test_fixed_current_authority(fixed, invalid, monkeypatch):
    router, repo, scope, digest, spec = fixed
    if invalid == "revoked":
        repo.review(digest, revoke=True)
    else:
        monkeypatch.setattr("aeep.router.utc_now", lambda: scope.expires_at + timedelta(seconds=1))
    try:
        with pytest.raises(NoRouteError):
            await router.execute_fixed(ActionRequest(capability=spec.capability, input={"text": "", "delimiter": ","}), spec.id)
        assert not router._fixed_dispatches
    finally:
        await router.close()

