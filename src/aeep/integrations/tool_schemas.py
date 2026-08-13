"""Provider-neutral AEEP tool contracts and provider-specific schema exports.

The runtime behavior is identical across providers; only the declaration shape
changes. This keeps the agent-facing API stable for OpenAI/ChatGPT, Anthropic,
DeepSeek, Z.AI, OpenClaw, and generic MCP clients.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

ToolFormat = Literal[
    "mcp",
    "openai-responses",
    "openai-chat",
    "anthropic",
    "deepseek",
    "zai",
]

_ACTION_PROPERTIES: dict[str, Any] = {
    "capability": {
        "type": "string",
        "description": "Stable semantic action name, for example text.stats or github.issue.create.",
    },
    "input": {
        "type": "object",
        "description": "JSON input passed to the selected executor.",
        "additionalProperties": True,
    },
    "policy": {
        "type": "string",
        "default": "balanced",
        "description": "Routing policy name: balanced, cheapest, fastest, resource_saver, reliable, or a manifest policy.",
    },
    "constraints": {
        "type": "object",
        "description": "Optional hard budget, latency, compute, privacy, and safety constraints.",
        "additionalProperties": True,
    },
    "context": {
        "type": "object",
        "description": "Optional current quota/capacity, state-locality, sensitivity, and trace context.",
        "additionalProperties": True,
    },
    "idempotency_key": {
        "type": "string",
        "maxLength": 256,
        "description": "Stable key that prevents duplicate execution of the same action.",
    },
}

_BASE_TOOLS: list[dict[str, Any]] = [
    {
        "name": "aeep_list_capabilities",
        "description": (
            "List semantic capabilities and their available CLI, Python, HTTP, MCP, or "
            "host executors before choosing an action."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "default": ""},
                "prefix": {"type": ["string", "null"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                "cursor": {"type": "integer", "minimum": 0, "default": 0},
                "include_executors": {"type": "boolean", "default": False},
            },
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "idempotentHint": True},
    },
    {
        "name": "aeep_route_action",
        "description": (
            "Profile and rank feasible execution routes for an agent action without executing it. "
            "Returns estimates, hard-constraint rejections, score components, and the selected route."
        ),
        "schema": {
            "type": "object",
            "properties": {
                **deepcopy(_ACTION_PROPERTIES),
                "detail": {
                    "type": "string",
                    "enum": ["compact", "full"],
                    "default": "compact",
                },
            },
            "required": ["capability", "input"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "idempotentHint": True},
    },
    {
        "name": "aeep_execute_action",
        "description": (
            "Route and execute an agent action within the operator-configured server approval ceiling. "
            "AEEP applies hard constraints first, then balances cost, latency, compute pressure, "
            "reliability, quality, and risk. Returns execution receipts."
        ),
        "schema": {
            "type": "object",
            "properties": {
                **deepcopy(_ACTION_PROPERTIES),
                "dry_run": {
                    "type": "boolean",
                    "default": False,
                    "description": "Return the route decision without invoking the executor.",
                },
                "detail": {
                    "type": "string",
                    "enum": ["compact", "full"],
                    "default": "compact",
                },
            },
            "required": ["capability", "input"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "idempotentHint": False},
    },
    {
        "name": "aeep_record_outcome",
        "description": (
            "Report the observed result of a browser, computer-use, model, or other host-delegated "
            "route so future decisions learn its actual cost, latency, compute use, and reliability."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "decision_id": {"type": "string"},
                "executor_id": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["success", "failed", "timeout", "rejected"],
                },
                "actual_resources": {
                    "type": "object",
                    "properties": {
                        "monetary_usd": {"type": "number", "minimum": 0},
                        "latency_ms": {"type": "number", "minimum": 0},
                        "cpu_ms": {"type": "number", "minimum": 0},
                        "memory_mb_seconds": {"type": "number", "minimum": 0},
                        "peak_memory_mb": {"type": "number", "minimum": 0},
                        "gpu_ms": {"type": "number", "minimum": 0},
                        "network_bytes": {"type": "integer", "minimum": 0},
                        "context_tokens": {"type": "integer", "minimum": 0},
                        "input_tokens": {"type": "integer", "minimum": 0},
                        "output_tokens": {"type": "integer", "minimum": 0},
                        "subscription_units": {"type": "number", "minimum": 0},
                    },
                    "additionalProperties": False,
                },
                "output_valid": {"type": ["boolean", "null"]},
                "task_valid": {"type": ["boolean", "null"]},
                "quality_score": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
                "validation_results": {"type": "array", "items": {"type": "object"}},
                "quota_observation": {
                    "type": ["object", "null"],
                    "properties": {
                        "state": {
                            "type": "string",
                            "enum": [
                                "abundant",
                                "normal",
                                "tight",
                                "critical",
                                "exhausted",
                                "unknown",
                            ],
                        },
                        "reset_at": {"type": ["string", "null"], "format": "date-time"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "source": {
                            "type": "string",
                            "enum": [
                                "user",
                                "host",
                                "official_cli",
                                "rate_limit",
                                "heuristic",
                                "observed",
                            ],
                        },
                    },
                    "required": ["state"],
                    "additionalProperties": False,
                },
                "error_message": {"type": ["string", "null"]},
                "metadata": {"type": "object", "additionalProperties": True},
            },
            "required": ["decision_id", "executor_id", "status"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "idempotentHint": False},
    },
    {
        "name": "aeep_request_quotes",
        "description": (
            "Request expiring execution quotes for compatible routes without accepting or paying "
            "for one. Quote acceptance and financial approval remain operator-only."
        ),
        "schema": {
            "type": "object",
            "properties": {
                **deepcopy(_ACTION_PROPERTIES),
                "executor_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["capability", "input"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "idempotentHint": True},
    },
    {
        "name": "aeep_get_metrics",
        "description": (
            "Read private aggregate savings, substitutions, resource use, and subscription "
            "capacity conserved from local AEEP history."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 10000, "default": 10000}
            },
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "idempotentHint": True},
    },
]


def neutral_tools() -> list[dict[str, Any]]:
    """Return provider-neutral declarations (`name`, `description`, `schema`)."""

    return deepcopy(_BASE_TOOLS)


def export_tools(format: ToolFormat) -> list[dict[str, Any]]:
    """Export equivalent declarations in the selected provider's native shape."""

    tools = neutral_tools()
    if format == "mcp":
        return [
            {
                "name": tool["name"],
                "description": tool["description"],
                "inputSchema": tool["schema"],
                "annotations": tool["annotations"],
            }
            for tool in tools
        ]
    if format == "openai-responses":
        return [
            {
                "type": "function",
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["schema"],
            }
            for tool in tools
        ]
    if format in {"openai-chat", "deepseek", "zai"}:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["schema"],
                },
            }
            for tool in tools
        ]
    if format == "anthropic":
        return [
            {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["schema"],
            }
            for tool in tools
        ]
    raise ValueError(f"unsupported tool format {format!r}")
