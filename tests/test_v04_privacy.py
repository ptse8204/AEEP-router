from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from conftest import manifest_with, python_spec

from aeep.errors import InputValidationError
from aeep.executors.base import BaseExecutor, ExecutionContext
from aeep.models import (
    ActionRequest,
    ExecutionStatus,
    ExecutorKind,
    RawExecution,
    ResourceVector,
    ValidationKind,
    ValidationResult,
    ValidationSpec,
)
from aeep.registry import validate_json
from aeep.router import Router


def _persisted_payloads(router: Router) -> str:
    connection = router.store._connection
    tables = [
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )
    ]
    payloads: list[str] = []
    for table in tables:
        quoted = '"' + table.replace('"', '""') + '"'
        columns = {
            str(row[1]) for row in connection.execute(f"PRAGMA table_info({quoted})")
        }
        if "payload_json" not in columns:
            continue
        payloads.extend(str(row[0]) for row in connection.execute(f"SELECT payload_json FROM {quoted}"))
    return "\n".join(payloads)


class _SecretOutputExecutor(BaseExecutor):
    def __init__(self, secret: str) -> None:
        self.secret = secret

    async def execute(self, context: ExecutionContext) -> RawExecution:
        del context
        return RawExecution(
            status=ExecutionStatus.SUCCESS,
            output={"result": self.secret},
            resources=ResourceVector(latency_ms=1),
        )


class _StateOutputExecutor(BaseExecutor):
    def __init__(self, state: str) -> None:
        self.state = state

    async def execute(self, context: ExecutionContext) -> RawExecution:
        del context
        return RawExecution(
            status=ExecutionStatus.SUCCESS,
            output={"state": self.state},
            resources=ResourceVector(latency_ms=1),
        )


def test_validation_error_retains_schema_path_and_keyword_without_instance() -> None:
    secret = "private-resume-body-41495e18"
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {"text": {"enum": ["operator-approved-category"]}},
        "required": ["text"],
        "additionalProperties": False,
    }

    with pytest.raises(InputValidationError) as caught:
        validate_json({"text": secret}, schema, label="input")

    message = str(caught.value)
    assert secret not in message
    assert "$.text" in message
    assert "'enum'" in message


def test_validation_error_does_not_reflect_dynamic_secret_key_or_value() -> None:
    secret_key = "access-token-59fe13c2"
    secret_value = "bearer-secret-0bce4f30"
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": {"type": "integer"},
    }

    with pytest.raises(InputValidationError) as caught:
        validate_json({secret_key: secret_value}, schema, label="input")

    message = str(caught.value)
    assert secret_key not in message
    assert secret_value not in message
    assert "$.*" in message
    assert "'type'" in message


@pytest.mark.asyncio
async def test_prepared_rejection_never_persists_invalid_secret_input(tmp_path: Path) -> None:
    secret = "unique-confidential-input-5295c234"
    route = python_spec(
        "local.schema-bound",
        "aeep.examples.tools:text_stats",
        cost=0,
        capability="text.statistics@1",
        input_schema={
            "type": "object",
            "properties": {"text": {"enum": ["operator-approved-category"]}},
            "required": ["text"],
            "additionalProperties": False,
        },
    )
    manifest = manifest_with(route)
    manifest.version = "0.4"
    manifest.database = str(tmp_path / "prepared-privacy.db")
    router = Router(manifest)
    try:
        prepared = await router.prepare_route(
            ActionRequest(
                action_id="privacy-input-action",
                capability="text.statistics@1",
                input={"text": secret},
            )
        )

        assert not prepared.feasible
        reason = prepared.rejected_candidates[0].reasons[0]
        assert secret not in reason
        assert "$.text" in reason
        assert "'enum'" in reason
        assert secret not in _persisted_payloads(router)
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_prepared_output_validation_never_persists_secret_instance(tmp_path: Path) -> None:
    secret = "unique-confidential-output-a794ad86"
    route = python_spec(
        "local.secret-output",
        "aeep.examples.tools:text_stats",
        cost=0,
        capability="text.statistics@1",
        input_schema={"type": "object", "additionalProperties": False},
        output_schema={
            "type": "object",
            "properties": {"result": {"enum": ["operator-approved-result"]}},
            "required": ["result"],
            "additionalProperties": False,
        },
    )
    manifest = manifest_with(route)
    manifest.version = "0.4"
    manifest.database = str(tmp_path / "output-privacy.db")
    router = Router(manifest)
    router._executors[ExecutorKind.PYTHON] = _SecretOutputExecutor(secret)
    try:
        prepared = await router.prepare_route(
            ActionRequest(
                action_id="privacy-output-action",
                capability="text.statistics@1",
                input={},
            )
        )
        outcome = await router.execute_prepared(prepared.prepared_id)

        assert not outcome.ok
        validation = outcome.receipts[0].validation_results[0]
        assert validation.valid is False
        assert secret not in validation.detail
        assert "$.result" in validation.detail
        assert "'enum'" in validation.detail
        assert secret not in _persisted_payloads(router)
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_persisted_validator_details_never_retain_runtime_secrets(tmp_path: Path) -> None:
    input_secret = "unique-private-before-state-6953346a"
    output_secret = "unique-private-after-state-1d186cd0"
    callback_secret = "unique-private-callback-detail-6dd05753"
    route = python_spec(
        "local.secret-validator",
        "aeep.examples.tools:text_stats",
        cost=0,
        capability="text.statistics@1",
        input_schema={
            "type": "object",
            "properties": {"state": {"type": "string"}},
            "required": ["state"],
            "additionalProperties": False,
        },
    )
    route.validators = [
        ValidationSpec(
            kind=ValidationKind.STATE_TRANSITION,
            config={
                "transitions": {input_secret: [output_secret]},
                "before_path": "state",
                "after_path": "state",
            },
        ),
        ValidationSpec(
            kind=ValidationKind.CALLBACK,
            config={"name": "secret-detail"},
        ),
    ]
    manifest = manifest_with(route)
    manifest.version = "0.4"
    manifest.database = str(tmp_path / "validator-detail-privacy.db")

    def validator(_context: Any) -> ValidationResult:
        return ValidationResult(
            kind=ValidationKind.CALLBACK,
            valid=True,
            quality_score=1,
            detail=callback_secret,
        )

    router = Router(manifest, validator_callbacks={"secret-detail": validator})
    router._executors[ExecutorKind.PYTHON] = _StateOutputExecutor(output_secret)
    try:
        prepared = await router.prepare_route(
            ActionRequest(
                action_id="privacy-validator-action",
                capability="text.statistics@1",
                input={"state": input_secret},
            )
        )
        outcome = await router.execute_prepared(prepared.prepared_id)

        assert outcome.ok
        assert callback_secret in {
            result.detail for result in outcome.receipts[0].validation_results
        }
        stored = router.store.get_receipt(outcome.receipts[0].receipt_id)
        assert stored is not None
        assert all(
            result.detail.endswith("validation passed")
            for result in stored.validation_results
        )
        payloads = _persisted_payloads(router)
        assert input_secret not in payloads
        assert output_secret not in payloads
        assert callback_secret not in payloads
    finally:
        await router.close()
