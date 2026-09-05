from __future__ import annotations

import json
import shutil
from pathlib import Path

from aeep.models import ActionRequest, ExecutorKind, ExecutorSpec, Manifest, SideEffect
from aeep.router import Router
from aeep.verification import CompletionStatus, verify_router_complete

ROOT = Path(__file__).parents[1]


def test_router_tie_breaks_by_executor_id():
    shared = {
        "capability": "fixture.tie@1",
        "kind": ExecutorKind.COMMAND,
        "description": "tie fixture",
        "side_effect": SideEffect.NONE,
        "config": {"argv": ["true"]},
    }
    router = Router(
        Manifest(
            database=":memory:",
            executors=[
                ExecutorSpec(id="z-route", **shared),
                ExecutorSpec(id="a-route", **shared),
            ],
        )
    )
    try:
        decision = router.route(ActionRequest(capability="fixture.tie@1"))
        assert decision.selected_executor_id == "a-route"
    finally:
        import asyncio

        asyncio.run(router.close())


def test_core_verifier_executes_tests_and_checks_locked_digests():
    report = verify_router_complete(profile="core")
    assert report.profiles["core"] is CompletionStatus.PASS, report.model_dump_json(indent=2)
    assert all(
        item.test_ids and item.artifact_digests
        for item in report.checks
        if item.status is CompletionStatus.PASS
    )


def test_tampered_required_artifact_fails_verification(tmp_path: Path, monkeypatch):
    from aeep import verification

    lock = json.loads(
        (ROOT / "reports" / "v07" / "verification-lock.json").read_text()
    )
    lock_path = tmp_path / "reports" / "v07" / "verification-lock.json"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(json.dumps(lock))
    for relative in lock["artifacts"]:
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    (tmp_path / "reports" / "v07" / "x402-conformance.json").write_text("tampered")
    monkeypatch.setattr(verification, "_pytest", lambda *_args: (True, ""))
    monkeypatch.setattr(verification, "_revision", lambda *_args: "0" * 40)
    report = verify_router_complete(profile="marketplace-contract", root=tmp_path)
    check = next(item for item in report.checks if item.id == "x402-local-batch-conformance")
    assert check.status is CompletionStatus.FAIL
    assert not report.marketplace_contract_ready
