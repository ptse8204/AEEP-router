from __future__ import annotations

import json

import pytest
from conftest import manifest_with

from aeep.models import ExecutionReceipt, ExecutionStatus, ExecutorKind, RouteEstimate
from aeep.router import Router


@pytest.mark.asyncio
async def test_host_progress_survives_receipt_database_reopen(tmp_path):
    manifest = manifest_with()
    manifest.database = str(tmp_path / "receipts.sqlite3")
    progress = {
        "stage": "awaiting_turn_completion",
        "callback_counts": {"requested": 1, "handler_completed": 1, "response_written": 1, "rejected": 0},
        "turn_completion_received": False,
        "elapsed_seconds": 180.0,
    }
    receipt = ExecutionReceipt(
        decision_id="decision-progress", action_id="action-progress", capability="test.progress",
        executor_id="managed-host", executor_kind=ExecutorKind.MANAGED_HOST,
        status=ExecutionStatus.FAILED, estimated=RouteEstimate(),
        metadata={"host_progress": json.dumps(progress, separators=(",", ":")),
                  "task_payload": "private task content"},
    )
    router = Router(manifest)
    router._save_receipt(receipt)
    await router.close()

    reopened = Router(manifest)
    try:
        saved = reopened.store.get_receipt(receipt.receipt_id)
        assert saved is not None
        assert json.loads(saved.metadata["host_progress"]) == progress
        assert "task_payload" not in saved.metadata
        assert saved.status is ExecutionStatus.FAILED
    finally:
        await reopened.close()
