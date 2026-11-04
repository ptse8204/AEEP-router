"""Explicit local receipt export through the existing HTTP executor and ledger."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from aeep.assessment.models import AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.assessment.verification import verification_source_digest
from aeep.economic.prepared import executor_fingerprint
from aeep.errors import ConfigurationError
from aeep.execution import ExecutionEvidence, persist_execution_events
from aeep.executors.base import ExecutionContext
from aeep.executors.http import HTTPExecutor
from aeep.models import (
    ActionRequest,
    ExecutionReceipt,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    RawExecution,
    ResourceVector,
    SideEffect,
    StrictModel,
    utc_now,
)
from aeep.telemetry import receipt_otlp_preview

from .models import Digest
from .workflow import StackWorkflow, _read
from .workflow_accounting import account_workflow


class ReceiptExportDefinition(StrictModel):
    schema_version: Literal["aeep.toolkit.receipt-export.v1"] = "aeep.toolkit.receipt-export.v1"
    request: RecipeMaterializationRequest
    port: int = Field(strict=True, ge=1024, le=65535)
    enabled: bool = False
    # References the exact separately reviewed local deployment, not a host name claim.
    deployment_review_ref: Digest
    timeout_seconds: int = Field(default=10, strict=True, ge=1, le=30)


class ReceiptExportRecord(StrictModel):
    schema_version: Literal["aeep.toolkit.receipt-export-record.v1"] = (
        "aeep.toolkit.receipt-export-record.v1"
    )
    definition_ref: Digest
    deployment_review_ref: Digest
    source_receipt_id: str
    source_receipt_sha256: Digest
    trace_id: str
    span_id: str
    operation_id: str
    transport_receipt_ref: Digest
    executor_fingerprint: str
    # Successful transport cannot prove ingestion or trace linkage.
    transport_accepted: bool
    ingestion_verified: Literal[False] = False


def spec_for(definition: ReceiptExportDefinition) -> ExecutorSpec:
    return ExecutorSpec(
        id="toolkit.langfuse-export",
        capability="toolkit.receipt-export@1",
        description="Send only minimized canonical receipt telemetry to reviewed local Langfuse",
        kind=ExecutorKind.HTTP,
        side_effect=SideEffect.WRITE,
        config={
            "url": f"http://127.0.0.1:{definition.port}/api/public/otel/v1/traces",
            "method": "POST",
            "json": "{input}",
            "headers": {
                "Authorization": "${ENV:AEEP_LANGFUSE_LOCAL_AUTH}",
                "Content-Type": "application/json",
                "x-langfuse-ingestion-version": "4",
            },
            "allowed_hosts": ["127.0.0.1"],
            "allow_private_networks": True,
            "follow_redirects": False,
            "trust_proxy_env": False,
            "max_request_bytes": 65536,
            "max_response_bytes": 16384,
            "timeout_seconds": definition.timeout_seconds,
            "accepted_statuses": [200],
            "output": {"type": "json"},
        },
    )


def accepted(raw: Any) -> bool:
    if raw.status != ExecutionStatus.SUCCESS or not isinstance(raw.output, dict):
        return False
    # OTLP can report rejected spans in an HTTP200 response. Preserve the failure.
    partial = raw.output.get("partialSuccess", raw.output.get("partial_success", {}))
    return raw.output == {} or (
        isinstance(partial, dict)
        and partial == {}
        and set(raw.output) <= {"partialSuccess", "partial_success"}
    )


def export_receipt(
    workflow_file: Path,
    configuration: str,
    receipt_id: str,
    *,
    accounting: Path | None,
    operation_key: str | None,
    reviewed_digest: str | None,
) -> dict[str, Any]:
    """No background exporter, batching, retry or caller-supplied trace payload."""
    with account_workflow(
        accounting,
        workflow_file=workflow_file,
        configuration=configuration,
        stage="report",
        operation_key=operation_key,
    ) as meter:
        root = workflow_file.absolute().parent
        workflow = StackWorkflow.model_validate_json(_read_bytes(workflow_file))
        if configuration not in workflow.configurations:
            raise ConfigurationError("unknown workflow configuration")
        selected = workflow.configurations[configuration]
        if selected.telemetry is None or not {"langfuse", "opentelemetry"} <= set(
            selected.components
        ):
            raise ConfigurationError(
                "receipt export requires explicit Langfuse and OpenTelemetry selection"
            )
        binding = selected.telemetry
        _, raw_definition = _read(binding, root)
        definition = ReceiptExportDefinition.model_validate_json(raw_definition)
        ref = content_digest(definition)
        if meter is None or meter.scope is None or meter.repository is None:
            if reviewed_digest is not None:
                raise ConfigurationError("receipt export requires canonical accounting")
            return {
                "definition_ref": ref,
                "enabled": definition.enabled,
                "receipt_resolution": "REQUIRES_CANONICAL_ACCOUNTING",
                "export_performed": False,
            }
        repository = meter.repository
        receipt = repository.store.get_receipt(receipt_id)
        if receipt is None:
            raise ConfigurationError("source receipt is absent from the canonical store")
        preview = receipt_otlp_preview(receipt)
        payload = preview["payload"]
        span = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        for attribute in span["attributes"]:
            if attribute["key"] == "aeep.evidence.trust":
                attribute["value"] = {"stringValue": "canonical_store_receipt"}
        # The old supplied-preview contract retains its semantics.
        facts = {
            "definition_ref": ref,
            "deployment_review_ref": definition.deployment_review_ref,
            "enabled": definition.enabled,
            "source_receipt_id": receipt_id,
            "source_receipt_sha256": preview["receipt_sha256"],
            "payload_sha256": content_digest(payload),
            "trace_id": span["traceId"],
            "span_id": span["spanId"],
            "endpoint": spec_for(definition).config["url"],
            "executor_fingerprint": executor_fingerprint(spec_for(definition)),
            "implementation_source": verification_source_digest(
                Path(__file__).resolve().parents[2]
            ),
            "content_excluded": ["prompts", "artifacts", "paths", "model traces", "credentials"],
            "export_performed": False,
            "ingestion_verified": False,
        }
        digest = content_digest(facts)
        if reviewed_digest is None:
            return {**facts, "review_sha256": digest}
        if reviewed_digest != digest:
            raise ConfigurationError("receipt export preview changed")
        if not definition.enabled:
            return {**facts, "status": "disabled"}
        stored = ReceiptExportDefinition.model_validate(
            repository.get("toolkit_receipt_export", ref)
        )
        if (
            stored != definition
            or definition.request.authorization_id != meter.scope.request.authorization_id
        ):
            raise ConfigurationError("receipt export authority differs from the workflow")
        request = definition.request.model_copy(
            update={
                "definition_digests": list(
                    dict.fromkeys(
                        [
                            *definition.request.definition_digests,
                            ref,
                            definition.deployment_review_ref,
                        ]
                    )
                )
            }
        )
        repository.authorize(request)
        meter.authorize()
        # New key only; never read provider credentials or Codex state.
        auth = os.environ.get("AEEP_LANGFUSE_LOCAL_AUTH", "")
        if not auth.startswith("Basic ") or len(auth) > 2048 or any(c in auth for c in "\r\n"):
            raise ConfigurationError(
                "reviewed task-owned local export authentication is unavailable"
            )
        operation = "receipt-export:" + ref + ":" + preview["receipt_sha256"]
        # Deterministic identity prevents retries even with another CLI operation key.
        repository.reserve(
            request,
            operation,
            AssessmentLimits(
                max_operations=1,
                max_model_turns=0,
                max_elapsed_seconds=definition.timeout_seconds + 10,
            ),
            stage="workflow_receipt_export",
        )
        spec = spec_for(definition)
        action = ActionRequest(action_id=operation, capability=spec.capability, input=payload)
        began, started = time.perf_counter(), utc_now()
        raw = None
        failure = None
        evidence_ref = None

        def authorize() -> str:
            meter.authorize()
            repository.authorize(request)
            _, current = _read(binding, root)
            if ReceiptExportDefinition.model_validate_json(current) != definition:
                raise ConfigurationError("receipt export configuration changed")
            current_receipt = repository.store.get_receipt(receipt_id)
            if (
                current_receipt is None
                or receipt_otlp_preview(current_receipt)["receipt_sha256"]
                != preview["receipt_sha256"]
            ):
                raise ConfigurationError("canonical source receipt changed")
            return ref

        async def invoke() -> RawExecution:
            authorize()
            executor = HTTPExecutor()
            try:
                return await (
                    await executor.start(
                        ExecutionContext(
                            request=action,
                            spec=spec,
                            estimate=spec.estimate,
                            attempt=1,
                            attempt_id=operation,
                            approved_side_effect=SideEffect.WRITE,
                            invocation_check=authorize,
                        )
                    )
                ).task
            finally:
                await executor.close()

        with meter.exclude("canonical_receipt_export"):
            try:
                with persist_execution_events(
                    lambda identity, event: repository.put(
                        "execution_event", identity + ":" + str(event.sequence), event
                    )
                ):
                    raw = asyncio.run(invoke())
                if not accepted(raw):
                    raise ConfigurationError(
                        "receipt transport failed or returned partial/invalid acceptance; no retry"
                    )
                evidence = ExecutionEvidence.model_validate(raw.metadata["execution_evidence"])
                if not evidence.complete:
                    raise ConfigurationError("receipt transport evidence is incomplete")
                evidence_ref = repository.put("execution_evidence", evidence.digest(), evidence)
            except BaseException as error:
                failure = error
            finally:
                elapsed = time.perf_counter() - began
                transport = ExecutionReceipt(
                    decision_id=operation,
                    action_id=operation,
                    capability=spec.capability,
                    executor_id=spec.id,
                    executor_kind=spec.kind,
                    executor_fingerprint=executor_fingerprint(spec),
                    status=ExecutionStatus.SUCCESS if failure is None else ExecutionStatus.FAILED,
                    started_at=started,
                    ended_at=utc_now(),
                    estimated=spec.estimate,
                    actual_resources=raw.resources
                    if raw
                    else ResourceVector(latency_ms=elapsed * 1000),
                    execution_success=failure is None,
                    error_type=type(failure).__name__ if failure else None,
                    metadata={
                        "definition_ref": ref,
                        "source_receipt_sha256": preview["receipt_sha256"],
                        "trace_id": span["traceId"],
                        "execution_evidence_ref": evidence_ref,
                        "operation_wall_seconds": elapsed,
                        "observed_resource_dimensions": ["latency_ms", "network_bytes"]
                        if raw and "response_bytes" in raw.metadata
                        else [],
                        "legacy_vector_defaults_are_not_observations": True,
                        "ingestion_verified": False,
                        "response_contents_not_retained": True,
                    },
                )
                repository.store.save_receipt(transport)
                transport_ref = repository.put(
                    "toolkit_receipt_export_transport", operation, transport
                )
                repository.finish_operation(
                    operation,
                    elapsed_seconds=elapsed,
                    accounting=raw.accounting if raw else None,
                    resources=transport.actual_resources,
                )
        if failure is not None:
            raise ConfigurationError(
                "receipt export ended without verified acceptance; retain charge and reconcile before another attempt"
            ) from None
        record = ReceiptExportRecord(
            definition_ref=ref,
            deployment_review_ref=definition.deployment_review_ref,
            source_receipt_id=receipt_id,
            source_receipt_sha256=preview["receipt_sha256"],
            trace_id=span["traceId"],
            span_id=span["spanId"],
            operation_id=operation,
            transport_receipt_ref=transport_ref,
            executor_fingerprint=executor_fingerprint(spec),
            transport_accepted=True,
        )
        result_ref = repository.put("toolkit_receipt_export_record", operation, record)
        return {
            **record.model_dump(mode="json"),
            "record_ref": result_ref,
            "export_performed": True,
        }


def _read_bytes(path: Path) -> bytes:
    from .cli import read_bytes

    return read_bytes(path)
