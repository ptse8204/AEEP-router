import hashlib

import pytest
from test_codex_subscription_adapter import adapter, context

from aeep.executors.base import ExecutionContext
from aeep.executors.managed_host import ManagedHostExecutor
from aeep.hosts import ManagedHostRegistry
from aeep.models import ExecutorSpec, RouteEstimate
from aeep.router import Router


@pytest.mark.asyncio
async def test_actual_managed_task_instruction_is_hashed_without_content_retention():
    host = adapter()
    current = context()
    registry = ManagedHostRegistry()
    registry.register(current.config.adapter_id, host)
    executor = ManagedHostExecutor(registry)
    spec = ExecutorSpec(
        id="fixture",
        capability=current.request.capability,
        kind="host_managed",
        description="Synthetic App Server prompt binding fixture",
        resource_pool="fixture-subscription",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        config=current.config.model_dump(mode="json"),
    )
    try:
        raw = await executor.execute(
            ExecutionContext(
                request=current.request, spec=spec, estimate=RouteEstimate(), attempt=1
            )
        )
        expected = hashlib.sha256(b"Count characters in abc").hexdigest()
        assert raw.metadata["task_instruction_sha256"] == expected
        retained = Router._safe_receipt_metadata(raw.metadata)
        assert retained["task_instruction_sha256"] == expected
        assert "abc" not in str(retained) and "Count characters" not in str(retained)
    finally:
        await executor.close()


@pytest.mark.parametrize(
    "value,expected",
    [(True, True), (False, False), (None, None), ("private payload", None), (1, None)],
)
def test_discovery_retention_is_limited_to_boolean_observations(value, expected):
    retained = Router._safe_receipt_metadata(
        {
            "capability_discovery": {
                "exposed": value,
                "invoked": False,
                "retrieved": None,
                "private": "secret",
            },
            "task_input": "private",
        }
    )
    assert retained == {
        "capability_discovery": {"exposed": expected, "retrieved": None, "invoked": False}
    }


@pytest.mark.asyncio
async def test_artifact_evidence_survives_receipt_storage_without_contents(tmp_path, monkeypatch):
    from conftest import manifest_with, python_spec

    from aeep.executors.python import PythonExecutor
    from aeep.models import ActionRequest, RawExecution

    async def execute(self, context):
        return RawExecution(status='success', output={}, metadata={
            'worker_cleanup_confirmed': True, 'artifact_sha256': 'a' * 64,
            'artifact_bytes': 17, 'artifact_contents': 'PRIVATE_ARTIFACT',
            'artifact_path': '/private/user/file', 'host_failure_code': 'worker_artifact_failed'})

    monkeypatch.setattr(PythonExecutor, 'execute', execute)
    manifest = manifest_with(python_spec('artifact', 'aeep.builtin.text:stats'))
    manifest.database = str(tmp_path / 'receipts.sqlite3')
    router = Router(manifest)
    try:
        outcome = await router.execute(ActionRequest(capability='text.stats', input={}))
        assert outcome.ok
        retained = router.store.get_receipt(outcome.receipts[0].receipt_id).metadata
        assert retained['worker_cleanup_confirmed'] is True
        assert retained['artifact_sha256'] == 'a' * 64 and retained['artifact_bytes'] == 17
        assert retained['host_failure_code'] == 'worker_artifact_failed'
        assert 'PRIVATE_ARTIFACT' not in str(retained) and '/private/user/file' not in str(retained)
    finally:
        await router.close()


def test_artifact_metadata_rejects_contents_and_unbounded_counts():
    retained = Router._safe_receipt_metadata({
        'worker_cleanup_confirmed': 'PRIVATE', 'artifact_sha256': 'PRIVATE',
        'artifact_bytes': 4_000_001, 'artifact_contents': 'PRIVATE'})
    assert retained == {}
    assert Router._safe_receipt_metadata({'artifact_bytes': True}) == {}
