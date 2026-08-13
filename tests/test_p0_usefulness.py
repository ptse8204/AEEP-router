from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from aeep.cli import app
from aeep.config import load_manifest, write_default_manifest
from aeep.instrumentation import TraceIngestor, instrument_anthropic, instrument_openai
from aeep.models import (
    ActionRequest,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    ExternalOutcomeReport,
    Manifest,
    ResourceVector,
    RouteEstimate,
    SideEffect,
    SubscriptionQuota,
)
from aeep.registry import Registry
from aeep.router import Router
from aeep.sdk import import_mcp_server
from aeep.store import ReceiptStore


@pytest.mark.asyncio
async def test_idempotency_replays_receipt_without_reexecuting_output():
    manifest, _ = load_manifest(Path(__file__).parents[1] / "examples" / "quickstart" / "aeep.yaml")
    manifest.database = ":memory:"
    router = Router(manifest)
    request = ActionRequest(
        capability="text.stats",
        input={"text": "one two"},
        idempotency_key="same-action",
    )
    first = await router.execute(request)
    second = await router.execute(request)
    assert first.ok and second.ok
    assert first.output["words"] == 2
    assert second.output is None
    assert second.receipts[0].receipt_id == first.receipts[0].receipt_id
    assert second.receipts[0].metadata["idempotency_replay"] is True
    assert len(router.store.list_receipts(decision_id=first.decision.decision_id)) == 1
    with pytest.raises(Exception, match="different action"):
        await router.execute(request.model_copy(update={"input": {"text": "different"}}))
    await router.close()


@pytest.mark.asyncio
async def test_quota_observation_changes_host_routing():
    manifest = Manifest.model_validate(
        {
            "database": ":memory:",
            "resources": [
                {
                    "id": "host.plan",
                    "provider": "test",
                    "product": "plan",
                    "quota": {"state": "abundant", "confidence": 1},
                }
            ],
            "executors": [
                {
                    "id": "host.route",
                    "capability": "demo.action@1",
                    "kind": "host",
                    "resource_pool": "host.plan",
                    "description": "host",
                    "estimate": {
                        "resources": {"latency_ms": 1, "subscription_units": 1},
                        "confidence": 1,
                    },
                    "side_effect": "none",
                    "config": {"instructions": "do it"},
                },
                {
                    "id": "local.route",
                    "capability": "demo.action@1",
                    "kind": "python",
                    "description": "local",
                    "estimate": {"resources": {"latency_ms": 500}, "confidence": 1},
                    "side_effect": "none",
                    "locality": "in_process",
                    "config": {"callable": "aeep.examples.tools:text_stats"},
                },
            ],
        }
    )
    router = Router(manifest)
    request = ActionRequest(capability="demo.action@1")
    assert router.route(request).selected_executor_id == "host.route"
    outcome = await router.execute(request)
    assert outcome.status == ExecutionStatus.HOST_SELECTED
    router.record_external_outcome(
        ExternalOutcomeReport(
            decision_id=outcome.decision.decision_id,
            executor_id="host.route",
            status=ExecutionStatus.SUCCESS,
            actual_resources=ResourceVector(subscription_units=1),
            quota_observation=SubscriptionQuota(state="exhausted", confidence=1, source="host"),
        )
    )
    assert router.route(request).selected_executor_id == "local.route"
    assert router.subscription_status()[0]["quota"]["state"] == "exhausted"
    await router.close()


def test_compact_decision_and_progressive_search_are_small(tmp_path):
    manifest = write_default_manifest(tmp_path / "aeep.yaml")
    router = Router.from_manifest(manifest)
    decision = router.route(ActionRequest(capability="text.stats", input={"text": "hello"}))
    compact = router.compact_decision(decision).model_dump(mode="json")
    assert compact["selected"] == "builtin.text-stats"
    assert "policy" not in compact
    assert len(json.dumps(compact)) < 700
    page = router.search_capabilities("text", limit=1)
    assert page["total"] == 1
    assert "executors" not in page["capabilities"][0]
    asyncio.run(router.close())


def test_otel_ingestion_reconstructs_calls_and_recommends_route():
    registry = Registry(
        [
            ExecutorSpec(
                id="local.tool",
                capability="github.lookup@1",
                kind=ExecutorKind.PYTHON,
                description="local",
                estimate=RouteEstimate(
                    resources=ResourceVector(latency_ms=10),
                    confidence=1,
                ),
                side_effect=SideEffect.READ,
                config={"callable": "aeep.examples.tools:text_stats"},
            )
        ]
    )
    report = TraceIngestor(registry).profile(
        {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [{"key": "service.name", "value": {"stringValue": "agent"}}]
                    },
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "traceId": "trace",
                                    "spanId": "span",
                                    "name": "browser lookup",
                                    "startTimeUnixNano": "1000000000",
                                    "endTimeUnixNano": "3000000000",
                                    "status": {"code": "STATUS_CODE_OK"},
                                    "attributes": [
                                        {
                                            "key": "aeep.capability",
                                            "value": {"stringValue": "github.lookup@1"},
                                        },
                                        {
                                            "key": "browser.action",
                                            "value": {"stringValue": "click"},
                                        },
                                        {
                                            "key": "gen_ai.usage.input_tokens",
                                            "value": {"intValue": "100"},
                                        },
                                        {
                                            "key": "retry.count",
                                            "value": {"intValue": "1"},
                                        },
                                        {
                                            "key": "http.request.body.size",
                                            "value": {"intValue": "20"},
                                        },
                                        {
                                            "key": "http.response.body.size",
                                            "value": {"intValue": "30"},
                                        },
                                    ],
                                }
                            ]
                        }
                    ],
                }
            ]
        }
    )
    assert report.calls[0].kind.value == "browser"
    assert report.calls[0].resources.input_tokens == 100
    assert report.calls[0].resources.network_bytes == 50
    assert report.retries == 1
    assert report.recommendations[0].recommended_executor_id == "local.tool"


def test_openai_and_anthropic_sdk_wrappers_capture_usage_without_payloads():
    store = ReceiptStore(":memory:")

    class Create:
        def __call__(self, **_kwargs):
            return SimpleNamespace(
                model="gpt-test",
                usage=SimpleNamespace(input_tokens=12, output_tokens=3),
            )

    openai = SimpleNamespace(
        responses=SimpleNamespace(create=Create()),
        chat=SimpleNamespace(completions=SimpleNamespace(create=Create())),
    )
    instrumented = instrument_openai(openai, store=store)
    instrumented.responses.create(model="gpt-test", input="secret")

    anthropic = SimpleNamespace(messages=SimpleNamespace(create=Create()))
    instrument_anthropic(anthropic, store=store).messages.create(
        model="claude-test", messages=[{"content": "secret"}]
    )
    receipts = store.list_receipts()
    assert len(receipts) == 2
    assert all(receipt.actual_resources.input_tokens == 12 for receipt in receipts)
    assert all(receipt.metadata["payload_stored"] is False for receipt in receipts)
    store.close()


@pytest.mark.asyncio
async def test_mcp_server_import_discovers_tools(tmp_path):
    manifest = write_default_manifest(tmp_path / "aeep.yaml")
    descriptor = await import_mcp_server(
        provider_id="local-aeep",
        transport="stdio",
        endpoint=sys.executable,
        args=["-m", "aeep", "serve", "--transport", "stdio", "-m", str(manifest)],
        capability_prefix="imported",
    )
    assert len(descriptor.executors) == 6
    assert {executor.kind for executor in descriptor.executors} == {ExecutorKind.MCP}


def test_openapi_import_maps_operation_to_canonical_capability(tmp_path):
    from aeep.sdk import import_openapi

    document = tmp_path / "openapi.json"
    document.write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "info": {"title": "demo", "version": "1"},
                "servers": [{"url": "https://example.com"}],
                "paths": {
                    "/branch": {
                        "get": {
                            "operationId": "getBranch",
                            "responses": {"200": {"description": "ok"}},
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    descriptor = import_openapi(
        document,
        provider_id="demo",
        capability_map={"getBranch": "github.repository.default-branch@1"},
    )
    assert descriptor.executors[0].capability == "github.repository.default-branch@1"
    assert descriptor.capabilities[0].authority == "https://example.com"


def test_subscription_skill_and_trace_cli(tmp_path):
    runner = CliRunner()
    manifest = write_default_manifest(tmp_path / "aeep.yaml")
    added = runner.invoke(
        app,
        [
            "subscriptions",
            "add",
            "anthropic.max",
            "--provider",
            "anthropic",
            "--product",
            "claude-max",
            "-m",
            str(manifest),
            "--compact",
        ],
    )
    assert added.exit_code == 0, added.output
    observed = runner.invoke(
        app,
        [
            "quota",
            "observe",
            "anthropic.max",
            "tight",
            "-m",
            str(manifest),
            "--compact",
        ],
    )
    assert observed.exit_code == 0, observed.output
    status = runner.invoke(
        app,
        ["subscriptions", "status", "-m", str(manifest), "--compact"],
    )
    subscriptions = json.loads(status.stdout)["subscriptions"]
    assert (
        next(item for item in subscriptions if item["id"] == "anthropic.max")["quota"]["state"]
        == "tight"
    )

    target = tmp_path / "skill"
    installed = runner.invoke(
        app,
        ["skill", "install", "codex", "--target", str(target), "--compact"],
    )
    assert installed.exit_code == 0, installed.output
    assert (target / "SKILL.md").is_file()

    trace = tmp_path / "trace.json"
    trace.write_text(json.dumps({"spans": [{"name": "unknown"}]}), encoding="utf-8")
    ingested = runner.invoke(
        app,
        ["ingest", "otel", str(trace), "-m", str(manifest), "--compact"],
    )
    assert ingested.exit_code == 0, ingested.output
    assert json.loads(ingested.stdout)["unmapped_calls"] == 1


@pytest.mark.asyncio
async def test_real_github_capability_prefers_and_runs_local_git(tmp_path):
    root = Path(__file__).parents[1]
    repository = tmp_path / "repository"
    await asyncio.to_thread(
        subprocess.run,
        ["git", "init", "--initial-branch=main", str(repository)],
        check=True,
        capture_output=True,
    )
    await asyncio.to_thread(
        subprocess.run,
        [
            "git",
            "-C",
            str(repository),
            "symbolic-ref",
            "refs/remotes/origin/HEAD",
            "refs/remotes/origin/main",
        ],
        check=True,
        capture_output=True,
    )
    router = Router.from_manifest(root / "examples" / "github" / "aeep.yaml")
    assert router.search_capabilities("current git branch")["total"] == 1
    request = ActionRequest(
        capability="github.repository.default-branch@1",
        input={
            "repository": str(repository),
            "owner": "ptse8204",
            "name": "AEEP-router",
        },
    )
    decision = router.route(request)
    assert decision.selected_executor_id == "github.local-git-default-branch"
    outcome = await router.execute(decision)
    assert outcome.status == ExecutionStatus.SUCCESS
    assert outcome.output == "main"
    await router.close()
