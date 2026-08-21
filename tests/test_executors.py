from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from conftest import manifest_with

from aeep.executors import ExecutionContext, HTTPExecutor
from aeep.models import (
    ActionRequest,
    ExecutorKind,
    ExecutorSpec,
    Locality,
    ResourceVector,
    RouteEstimate,
    SideEffect,
)
from aeep.router import Router


@pytest.mark.asyncio
async def test_command_executor_argv_no_shell(text_schema, stats_schema):
    executor = ExecutorSpec(
        id="cli",
        capability="text.stats",
        kind=ExecutorKind.COMMAND,
        description="cli",
        input_schema=text_schema,
        output_schema=stats_schema,
        estimate=RouteEstimate(resources=ResourceVector(latency_ms=50)),
        side_effect=SideEffect.NONE,
        locality=Locality.LOCAL,
        config={
            "argv": [sys.executable, "-m", "aeep.examples.text_stats_cli", "{input.text}"],
            "output": {"type": "json"},
            "inherit_env": True,
            "env": {"PYTHONPATH": str(Path(__file__).parents[1] / "src")},
        },
    )
    router = Router(manifest_with(executor))
    outcome = await router.execute(
        ActionRequest(capability="text.stats", input={"text": "one two"})
    )
    assert outcome.ok
    assert outcome.output["words"] == 2
    assert outcome.receipts[0].actual_resources.latency_ms > 0
    await router.close()


@pytest.mark.asyncio
async def test_command_shell_rejected(text_schema):
    executor = ExecutorSpec(
        id="bad",
        capability="text.stats",
        kind=ExecutorKind.COMMAND,
        description="bad",
        input_schema=text_schema,
        estimate=RouteEstimate(),
        side_effect=SideEffect.NONE,
        config={"argv": ["echo", "x"], "shell": True},
    )
    router = Router(manifest_with(executor))
    with pytest.raises(Exception, match="shell execution"):
        await router.execute(ActionRequest(capability="text.stats", input={"text": "x"}))
    await router.close()


@pytest.mark.asyncio
async def test_command_input_is_bounded_before_process_launch(text_schema):
    executor = ExecutorSpec(
        id="bounded",
        capability="text.stats",
        kind=ExecutorKind.COMMAND,
        description="bounded",
        input_schema=text_schema,
        side_effect=SideEffect.NONE,
        config={
            "argv": [sys.executable, "-c", "raise SystemExit(99)"],
            "stdin_json": True,
            "max_stdin_bytes": 2,
        },
    )
    router = Router(manifest_with(executor))
    outcome = await router.execute(
        ActionRequest(capability="text.stats", input={"text": "too large"})
    )
    assert not outcome.ok
    assert outcome.receipts[0].error_message == "command input exceeds configured max_stdin_bytes"
    await router.close()


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"# AEEP Agent Router\n\nBody\n"
        self.send_response(200)
        self.send_header("content-type", "text/plain")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("content-length", "0"))
        data = json.loads(self.rfile.read(length) or b"{}")
        text = data["text"]
        body = json.dumps(
            {"result": {"characters": len(text), "words": len(text.split()), "lines": 1}}
        ).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        return


@pytest.mark.asyncio
async def test_http_executor_local_allowlisted(text_schema, stats_schema):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        executor = ExecutorSpec(
            id="http",
            capability="text.stats",
            kind=ExecutorKind.HTTP,
            description="http",
            input_schema=text_schema,
            output_schema=stats_schema,
            estimate=RouteEstimate(resources=ResourceVector(latency_ms=100)),
            side_effect=SideEffect.NONE,
            locality=Locality.LAN,
            requires_network=True,
            config={
                "url": f"http://127.0.0.1:{server.server_port}/stats",
                "method": "POST",
                "json": {"text": "{input.text}"},
                "allowed_hosts": ["127.0.0.1"],
                "allow_private_networks": True,
                "output": {"type": "json", "path": "result"},
            },
        )
        router = Router(manifest_with(executor))
        outcome = await router.execute(
            ActionRequest(capability="text.stats", input={"text": "a b c"})
        )
        assert outcome.ok
        assert outcome.output["words"] == 3
        assert outcome.receipts[0].actual_resources.network_bytes > 0
        await router.close()
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.asyncio
@pytest.mark.parametrize("body_field", ["json", "body"])
async def test_http_executor_renders_prepared_execution_ids(body_field):
    received: dict[str, object] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("content-length", "0"))
            received["query"] = parse_qs(urlparse(self.path).query)
            received["body"] = self.rfile.read(length).decode()
            body = json.dumps(
                {
                    "output": "ok",
                    "usage_statement": {"usage_statement_id": "usage-1"},
                }
            ).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        identifiers = {
            "prepared_id": "prepared-1",
            "quote_id": "quote-1",
            "attempt_id": "attempt-1",
        }
        template = {key: f"{{{key}}}" for key in identifiers}
        config = {
            "url": f"http://127.0.0.1:{server.server_port}/execute",
            "method": "POST",
            "query": template,
            "allowed_hosts": ["127.0.0.1"],
            "allow_private_networks": True,
            "output": {"type": "json", "path": "output"},
        }
        config[body_field] = template if body_field == "json" else "{prepared_id}"
        spec = ExecutorSpec(
            id=f"http-{body_field}",
            capability="prepared.http@1",
            kind=ExecutorKind.HTTP,
            description="prepared HTTP binding",
            input_schema={"type": "object"},
            side_effect=SideEffect.NONE,
            locality=Locality.LAN,
            requires_network=True,
            config=config,
        )
        request = ActionRequest(capability=spec.capability, input={})
        context = ExecutionContext(
            request=request,
            spec=spec,
            estimate=spec.estimate,
            attempt=1,
            **identifiers,
        )

        raw = await HTTPExecutor().execute(context)

        assert raw.status.value == "success"
        assert raw.output == "ok"
        assert raw.metadata["_economic_usage_statement"] == {
            "usage_statement_id": "usage-1"
        }
        assert received["query"] == {key: [value] for key, value in identifiers.items()}
        assert received["body"] == (
            json.dumps(identifiers, separators=(",", ":"))
            if body_field == "json"
            else identifiers["prepared_id"]
        )
    finally:
        server.shutdown()
        server.server_close()


def test_execution_context_prepared_ids_default_to_none(text_schema):
    spec = ExecutorSpec(
        id="python",
        capability="text.stats",
        kind=ExecutorKind.PYTHON,
        description="python",
        input_schema=text_schema,
        side_effect=SideEffect.NONE,
        config={"callable": "aeep.examples.tools:text_stats"},
    )
    context = ExecutionContext(
        request=ActionRequest(capability=spec.capability, input={"text": "x"}),
        spec=spec,
        estimate=spec.estimate,
        attempt=1,
    )

    assert (context.prepared_id, context.quote_id, context.attempt_id) == (None, None, None)


@pytest.mark.asyncio
async def test_http_executor_reuses_bounded_output_parsers():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        executor = ExecutorSpec(
            id="http-regex",
            capability="markdown.title",
            kind=ExecutorKind.HTTP,
            description="http regex",
            output_schema={"type": "string"},
            side_effect=SideEffect.READ,
            locality=Locality.LAN,
            requires_network=True,
            config={
                "url": f"http://127.0.0.1:{server.server_port}/README.md",
                "allowed_hosts": ["127.0.0.1"],
                "allow_private_networks": True,
                "output": {"type": "regex", "pattern": r"^#\s+(.+?)\s*$", "group": 1},
            },
        )
        router = Router(manifest_with(executor))
        outcome = await router.execute(ActionRequest(capability="markdown.title"))
        assert outcome.ok
        assert outcome.output == "AEEP Agent Router"
        await router.close()
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.asyncio
async def test_http_private_target_rejected_by_default(text_schema):
    executor = ExecutorSpec(
        id="http",
        capability="x",
        kind=ExecutorKind.HTTP,
        description="http",
        input_schema={"type": "object"},
        estimate=RouteEstimate(),
        side_effect=SideEffect.NONE,
        locality=Locality.LAN,
        requires_network=True,
        config={"url": "http://192.168.1.10/value"},
    )
    router = Router(manifest_with(executor))
    outcome = await router.execute(ActionRequest(capability="x", input={}))
    assert not outcome.ok
    assert outcome.receipts[0].status.value == "rejected"
    await router.close()
