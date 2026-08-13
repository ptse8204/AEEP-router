"""Tiny dependency-free MCP server used to exercise AEEP's MCP executor."""

from __future__ import annotations

import json
import sys
from typing import Any

MODERN = "2026-07-28"
LEGACY = "2025-11-25"

TOOL = {
    "name": "text_stats",
    "description": "Return deterministic text statistics.",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
        "additionalProperties": False,
    },
}


def response(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params", {})
    if request_id is None:
        return None
    if method == "server/discover":
        return response(
            request_id,
            {
                "supportedVersions": [MODERN, LEGACY],
                "serverInfo": {"name": "example-text-stats", "version": "0.1"},
                "capabilities": {"tools": {"listChanged": False}},
            },
        )
    if method == "initialize":
        return response(
            request_id,
            {
                "protocolVersion": params.get("protocolVersion", LEGACY),
                "serverInfo": {"name": "example-text-stats", "version": "0.1"},
                "capabilities": {"tools": {"listChanged": False}},
            },
        )
    if method == "tools/list":
        return response(request_id, {"tools": [TOOL]})
    if method == "tools/call" and params.get("name") == "text_stats":
        text = str(params.get("arguments", {}).get("text", ""))
        output = {
            "characters": len(text),
            "words": len(text.split()),
            "lines": len(text.splitlines()) or 1,
        }
        return response(
            request_id,
            {
                "content": [{"type": "text", "text": json.dumps(output)}],
                "structuredContent": output,
                "isError": False,
                "_meta": {
                    "org.aeep/usage": {
                        "monetary_usd": 0.001,
                        "cpu_ms": 2,
                    }
                },
            },
        )
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> None:
    for line in sys.stdin:
        try:
            message = json.loads(line)
            result = handle(message)
        except Exception as exc:
            result = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error", "data": str(exc)},
            }
        if result is not None:
            print(json.dumps(result, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
