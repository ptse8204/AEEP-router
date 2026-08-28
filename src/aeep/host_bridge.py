"""Bounded local JSONL bridge for host-native integrations."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, BinaryIO

from .errors import AEEPError
from .models import (
    ActionRequest,
    ExecutionStatus,
    ExternalOutcomeReport,
    ResourceAccounting,
    ResourceVector,
    ToolFootprint,
)
from .router import Router
from .version import __version__

_DEFAULT_HOST_INTEGRATION = "host-native-v1"
_MAX_CORRELATED_RECEIPTS = 32


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return value


def _only(payload: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"unknown bridge fields: {', '.join(unknown)}")


def _request_id(payload: Mapping[str, Any]) -> str:
    value = payload.get("id")
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        raise ValueError("bridge id must be a non-empty string of at most 128 characters")
    return value


def _correlated_receipts(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > _MAX_CORRELATED_RECEIPTS:
        raise ValueError("preceding_tool_receipt_ids must be a list of at most 32 IDs")
    if any(not isinstance(item, str) or not 1 <= len(item) <= 200 for item in value):
        raise ValueError("preceding_tool_receipt_ids contains an invalid ID")
    if len(set(value)) != len(value):
        raise ValueError("preceding_tool_receipt_ids must be unique")
    return value


def _integration_id(value: str) -> str:
    if not 1 <= len(value) <= 100 or not value[0].isalnum() or any(
        not (character.isalnum() or character in ".-_") for character in value
    ):
        raise ValueError("integration_id must be 1-100 letters, digits, dots, dashes, or underscores")
    return value


class HostBridge:
    """Translate a minimal trusted host protocol into ordinary Router calls."""

    def __init__(
        self, router: Router, *, integration_id: str = _DEFAULT_HOST_INTEGRATION
    ) -> None:
        self.router = router
        self.integration_id = _integration_id(integration_id)

    async def handle(self, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        request_id = _request_id(payload)
        operation = payload.get("op")
        if operation == "ping":
            _only(payload, {"id", "op"})
            result: dict[str, Any] = {"version": __version__}
        elif operation == "route":
            _only(payload, {"id", "op", "capability", "input", "policy"})
            capability = payload.get("capability")
            if not isinstance(capability, str) or not capability:
                raise ValueError("route capability must be a non-empty string")
            policy = payload.get("policy", "balanced")
            if not isinstance(policy, str) or not policy:
                raise ValueError("route policy must be a non-empty string")
            decision = await self.router.route_with_discovery(
                ActionRequest(
                    capability=capability,
                    input=_object(payload.get("input"), "route input"),
                    policy=policy,
                )
            )
            result = self.router.compact_decision(decision).model_dump(mode="json")
        elif operation == "record":
            _only(
                payload,
                {
                    "id",
                    "op",
                    "decision_id",
                    "executor_id",
                    "status",
                    "resources",
                    "tool_footprint",
                    "preceding_tool_receipt_ids",
                },
            )
            decision_id = payload.get("decision_id")
            executor_id = payload.get("executor_id")
            if not isinstance(decision_id, str) or not decision_id:
                raise ValueError("record decision_id must be a non-empty string")
            if not isinstance(executor_id, str) or not executor_id:
                raise ValueError("record executor_id must be a non-empty string")
            status = payload.get("status")
            if not isinstance(status, str):
                raise ValueError("record status must be a string")
            resources = ResourceVector.model_validate(
                _object(payload.get("resources", {}), "record resources")
            )
            footprint_value = payload.get("tool_footprint")
            footprint = (
                ToolFootprint.model_validate(_object(footprint_value, "tool_footprint"))
                if footprint_value is not None
                else None
            )
            preceding = _correlated_receipts(payload.get("preceding_tool_receipt_ids"))
            metadata: dict[str, Any] = {"host_integration": self.integration_id}
            if preceding:
                metadata["preceding_tool_receipt_ids"] = preceding
                metadata["route_attribution_ambiguous"] = len(preceding) != 1
            receipt = self.router.record_external_outcome(
                ExternalOutcomeReport(
                    decision_id=decision_id,
                    executor_id=executor_id,
                    status=ExecutionStatus(status),
                    actual_resources=resources,
                ),
                _trusted_accounting=ResourceAccounting(tool_footprint=footprint),
                _trusted_metadata=metadata,
            )
            result = receipt.model_dump(mode="json")
        elif operation == "close":
            _only(payload, {"id", "op"})
            result = {"closed": True}
            return {"id": request_id, "ok": True, "result": result}, True
        else:
            raise ValueError("bridge op must be ping, route, record, or close")
        return {"id": request_id, "ok": True, "result": result}, False


def _write_response(stream: BinaryIO, response: dict[str, Any], maximum: int) -> None:
    encoded = (json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    if len(encoded) > maximum:
        encoded = b'{"id":null,"ok":false,"error":"bridge response exceeds configured limit"}\n'
    stream.write(encoded)
    stream.flush()


def run_host_bridge(
    manifest: Path | None,
    input_stream: BinaryIO,
    output_stream: BinaryIO,
    *,
    integration_id: str = _DEFAULT_HOST_INTEGRATION,
    max_input_bytes: int,
    max_output_bytes: int,
) -> int:
    """Serve sequential bridge requests while retaining one event loop and Router."""

    router = Router.from_manifest(manifest)
    bridge = HostBridge(router, integration_id=integration_id)
    loop = asyncio.new_event_loop()
    try:
        while True:
            line = input_stream.readline(max_input_bytes + 1)
            if not line:
                return 0
            if len(line) > max_input_bytes or not line.endswith(b"\n"):
                _write_response(
                    output_stream,
                    {"id": None, "ok": False, "error": "bridge input exceeds configured limit"},
                    max_output_bytes,
                )
                return 2
            payload: dict[str, Any] | None = None
            try:
                payload = _object(json.loads(line), "bridge request")
                response, close = loop.run_until_complete(bridge.handle(payload))
            except (AEEPError, ValueError, TypeError, json.JSONDecodeError) as exc:
                request_id = payload.get("id") if payload is not None else None
                response = {"id": request_id, "ok": False, "error": str(exc)}
                close = False
            _write_response(output_stream, response, max_output_bytes)
            if close:
                return 0
    finally:
        loop.run_until_complete(router.close())
        loop.close()
