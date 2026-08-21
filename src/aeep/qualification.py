"""Fail-closed lifecycle for imported and discovered routes."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

from jsonschema import Draft202012Validator
from pydantic import Field, model_validator

from .errors import ConfigurationError
from .models import ExecutorKind, ExecutorSpec, SideEffect, StrictModel, new_id, utc_now


class RouteLifecycle(StrEnum):
    CANDIDATE = "candidate"
    QUALIFIED = "qualified"
    ACTIVE = "active"
    SUSPENDED = "suspended"


class QualificationCondition(StrEnum):
    PROCESS_COLD = "process-cold"
    ROUTER_WARM = "router-warm"


class RouteCandidate(StrictModel):
    candidate_id: str = Field(default_factory=lambda: new_id("candidate"))
    executor_id: str
    source_id: str
    provider_id: str | None = None
    capability: str
    behavior_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: RouteLifecycle = RouteLifecycle.CANDIDATE
    spec: ExecutorSpec
    qualification_report_id: str | None = None
    reason: str | None = Field(default=None, max_length=1000)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def disabled_until_active(self) -> RouteCandidate:
        self.spec.enabled = self.status == RouteLifecycle.ACTIVE
        return self


class QualificationReport(StrictModel):
    report_id: str = Field(default_factory=lambda: new_id("qual"))
    candidate_id: str
    behavior_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    static_checks: dict[str, bool]
    dynamic_cases: int = Field(default=0, ge=0)
    passed_cases: int = Field(default=0, ge=0)
    repetitions: int = Field(default=1, ge=1)
    conditions: list[QualificationCondition] = Field(
        default_factory=lambda: [QualificationCondition.PROCESS_COLD]
    )
    dynamic_runs: int = Field(default=0, ge=0)
    passed_runs: int = Field(default=0, ge=0)
    passed: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class QualificationCase(StrictModel):
    input: dict[str, Any]
    expected_output: Any | None = None


def behavior_fingerprint(spec: ExecutorSpec) -> str:
    config_keys = {
        ExecutorKind.COMMAND: {
            "argv",
            "cwd",
            "env",
            "inherit_env",
            "stdin_json",
            "output",
            "usage_capture",
            "timeout_seconds",
            "max_output_bytes",
            "max_stdin_bytes",
            "propagate_idempotency_key",
            "stdin",
        },
        ExecutorKind.PYTHON: {"callable", "argument_mode", "timeout_seconds"},
        ExecutorKind.HTTP: {
            "url",
            "method",
            "headers",
            "query",
            "json",
            "body",
            "timeout_seconds",
            "max_response_bytes",
            "max_request_bytes",
            "follow_redirects",
            "trust_proxy_env",
            "allowed_hosts",
            "allow_private_networks",
            "allow_insecure_http",
            "accepted_statuses",
            "propagate_idempotency_key",
            "cost_header",
            "trust_cost_header",
        },
        ExecutorKind.MCP: {
            "transport",
            "command",
            "args",
            "cwd",
            "env",
            "inherit_env",
            "url",
            "headers",
            "credential_scope_id",
            "tool",
            "arguments",
            "output",
            "parse_json_text",
            "protocol_mode",
            "protocol_version",
            "server_version",
            "server",
            "image",
            "image_digest",
            "profile",
            "gateway_version",
            "tool_schema_version",
            "timeout_seconds",
            "max_message_bytes",
            "max_request_bytes",
            "max_response_bytes",
            "follow_redirects",
            "trust_proxy_env",
            "allowed_hosts",
            "allow_private_networks",
            "allow_insecure_http",
            "propagate_idempotency_key",
            "subscription_unit",
        },
        ExecutorKind.HOST: {"instructions"},
        ExecutorKind.DELEGATE: {"instructions"},
    }[spec.kind]
    # Quote endpoints and disclosure rules affect both data flow and charges.
    config_keys.add("economic")
    payload: dict[str, Any] = {
        "id": spec.id,
        "provider_id": spec.provider_id,
        "capability": spec.capability,
        "kind": spec.kind,
        "input_schema": spec.input_schema,
        "output_schema": spec.output_schema,
        "config": {key: spec.config[key] for key in sorted(config_keys & spec.config.keys())},
        "validators": [item.model_dump(mode="json") for item in spec.validators],
        "side_effect": spec.side_effect,
        "idempotent": spec.idempotent,
        "safe_to_auto_execute": spec.safe_to_auto_execute,
        "locality": spec.locality,
        "requires_network": spec.requires_network,
        "data_residency": sorted(spec.data_residency),
        "resource_pool": spec.resource_pool,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(canonical).hexdigest()


def _references_only(headers: object) -> bool:
    if not isinstance(headers, dict):
        return False
    sensitive = ("authorization", "token", "secret", "key", "cookie")
    for key, value in headers.items():
        if any(part in str(key).lower() for part in sensitive):
            text = str(value)
            if "${ENV:" not in text and not text.startswith("env:"):
                return False
    return True


def static_qualification_checks(spec: ExecutorSpec) -> dict[str, bool]:
    try:
        Draft202012Validator.check_schema(spec.input_schema)
        if spec.output_schema is not None:
            Draft202012Validator.check_schema(spec.output_schema)
        schemas = True
    except Exception:
        schemas = False
    config = spec.config
    adapter = True
    secrets = True
    bounds = True
    if spec.kind == ExecutorKind.COMMAND:
        argv = config.get("argv")
        adapter = (
            isinstance(argv, list)
            and bool(argv)
            and isinstance(argv[0], str)
            and os.path.isabs(argv[0])
            and "{" not in argv[0]
            and all(isinstance(item, (str, int, float)) for item in argv)
            and not config.get("shell")
            and not config.get("inherit_env")
            and isinstance(config.get("env", {}), dict)
            and (config.get("cwd") is None or isinstance(config.get("cwd"), str))
        )
        secrets = _references_only(config.get("env", {}))
        bounds = _positive_limits(
            config, ("timeout_seconds", "max_output_bytes", "max_stdin_bytes")
        )
    elif spec.kind == ExecutorKind.HTTP:
        url = config.get("url")
        parsed = urlparse(url) if isinstance(url, str) else None
        allowed_hosts = config.get("allowed_hosts")
        adapter = (
            isinstance(url, str)
            and url.startswith("https://")
            and parsed is not None
            and parsed.hostname is not None
            and "{input" not in parsed.hostname
            and isinstance(allowed_hosts, list)
            and bool(allowed_hosts)
            and all(isinstance(item, str) for item in allowed_hosts)
            and parsed.hostname.rstrip(".").lower()
            in {item.rstrip(".").lower() for item in allowed_hosts}
            and not config.get("follow_redirects")
            and not config.get("trust_proxy_env")
            and not config.get("allow_private_networks")
        )
        secrets = _references_only(config.get("headers", {}))
        bounds = _positive_limits(
            config, ("timeout_seconds", "max_request_bytes", "max_response_bytes")
        )
    elif spec.kind == ExecutorKind.MCP:
        transport = str(config.get("transport", "stdio"))
        connection_identity = json.dumps(
            {
                key: config.get(key)
                for key in (
                    "transport",
                    "command",
                    "args",
                    "url",
                    "cwd",
                    "env",
                    "headers",
                )
            },
            sort_keys=True,
            default=str,
        )
        adapter = (
            (
                (
                    transport == "stdio"
                    and isinstance(config.get("command"), str)
                    and os.path.isabs(str(config.get("command")))
                    and isinstance(config.get("args", []), list)
                    and all(isinstance(item, (str, int, float)) for item in config.get("args", []))
                )
                or (
                    transport in {"http", "streamable_http", "streamable-http"}
                    and isinstance(config.get("url"), str)
                    and str(config["url"]).startswith("https://")
                    and "{input" not in str(config["url"])
                    and _url_is_allowlisted(str(config["url"]), config.get("allowed_hosts"))
                    and not config.get("allow_private_networks")
                    and (not config.get("headers") or bool(config.get("credential_scope_id")))
                )
            )
            and not config.get("inherit_env")
            and "{input" not in connection_identity
            and "{action" not in connection_identity
        )
        secrets = _references_only(config.get("headers", {})) and _references_only(
            config.get("env", {})
        )
        bounds = _positive_limits(
            config,
            (
                "timeout_seconds",
                "max_message_bytes",
                "max_request_bytes",
                "max_response_bytes",
            ),
        )
    return {
        "schemas": schemas,
        "adapter_config": adapter,
        "secret_references": secrets,
        "bounded_io": bounds,
        "read_only": spec.side_effect.rank <= SideEffect.READ.rank,
        "idempotent": spec.idempotent,
        "safe_to_auto_execute": spec.safe_to_auto_execute,
        "validator_present": spec.output_schema is not None or bool(spec.validators),
    }


def _positive_limits(config: dict[str, Any], names: tuple[str, ...]) -> bool:
    try:
        return all(float(config.get(name, 1)) > 0 for name in names)
    except (TypeError, ValueError):
        return False


def _url_is_allowlisted(url: str, allowed_hosts: object) -> bool:
    parsed = urlparse(url)
    return bool(
        parsed.hostname
        and isinstance(allowed_hosts, list)
        and allowed_hosts
        and all(isinstance(item, str) for item in allowed_hosts)
        and parsed.hostname.rstrip(".").lower()
        in {item.rstrip(".").lower() for item in allowed_hosts}
    )


def require_static_qualification(spec: ExecutorSpec) -> dict[str, bool]:
    checks = static_qualification_checks(spec)
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ConfigurationError(f"route failed static qualification: {', '.join(failed)}")
    return checks
