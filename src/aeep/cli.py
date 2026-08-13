"""Agent-friendly AEEP command-line interface.

Route/run/record commands emit JSON to stdout and diagnostics to stderr. This
makes them safe to invoke from shell tools, Claude/OpenAI skills, OpenClaw, CI,
or another agent without scraping prose.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import typer
import yaml

from .config import load_manifest, write_default_manifest
from .errors import AEEPError, ApprovalRequired, ConfigurationError
from .executors.python import load_callable
from .integrations import export_tools
from .models import (
    ActionConstraints,
    ActionContext,
    ActionRequest,
    ExecutionStatus,
    ExternalOutcomeReport,
    ResourceVector,
    SideEffect,
)
from .router import Router
from .version import __version__

app = typer.Typer(
    name="aeep",
    help="Profile and route agent actions across Python, CLI, HTTP, MCP, and host agents.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
tools_app = typer.Typer(help="Export AEEP as native tools for agent providers.")
app.add_typer(tools_app, name="tools")


def _emit(value: Any, *, compact: bool = False) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    text = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":") if compact else None,
        indent=None if compact else 2,
        sort_keys=False,
        default=str,
    )
    typer.echo(text)


def _read_data(value: str | None, *, default: Any) -> Any:
    if value is None:
        return default
    if value == "-":
        text = sys.stdin.read()
        suffix = ""
    elif value.startswith("@"):
        path = Path(value[1:]).expanduser()
        text = path.read_text(encoding="utf-8")
        suffix = path.suffix.lower()
    else:
        text = value
        suffix = ""
    if not text.strip():
        return default
    try:
        if suffix in {".yaml", ".yml"}:
            return yaml.safe_load(text)
        return json.loads(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise typer.BadParameter(f"invalid JSON/YAML value: {exc}") from exc


def _mapping(value: str | None, *, name: str) -> dict[str, Any]:
    parsed = _read_data(value, default={})
    if not isinstance(parsed, dict):
        raise typer.BadParameter(f"{name} must be a JSON/YAML object")
    return parsed


def _request(
    *,
    capability: str,
    input_value: str,
    policy: str,
    constraints_value: str | None,
    context_value: str | None,
    max_cost_usd: float | None,
    max_latency_ms: float | None,
    max_context_tokens: int | None,
    max_peak_memory_mb: float | None,
    no_network: bool,
    require_local: bool,
    executor_id: str | None,
    max_side_effect: SideEffect | None,
) -> ActionRequest:
    constraints = _mapping(constraints_value, name="constraints")
    context = _mapping(context_value, name="context")
    overrides: dict[str, Any] = {
        "max_cost_usd": max_cost_usd,
        "max_latency_ms": max_latency_ms,
        "max_context_tokens": max_context_tokens,
        "max_peak_memory_mb": max_peak_memory_mb,
    }
    for key, value in overrides.items():
        if value is not None:
            constraints[key] = value
    if no_network:
        constraints["allow_network"] = False
    if require_local:
        constraints["require_local"] = True
    if executor_id is not None:
        constraints["allowed_executor_ids"] = [executor_id]
    if max_side_effect is not None:
        constraints["max_side_effect"] = max_side_effect.value
    return ActionRequest(
        capability=capability,
        input=_mapping(input_value, name="input"),
        policy=policy,
        constraints=ActionConstraints.model_validate(constraints),
        context=ActionContext.model_validate(context),
    )


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


async def _await_and_close(router: Router, awaitable: Any) -> Any:
    """Keep event-loop-bound subprocess/HTTP clients on one loop."""

    try:
        return await awaitable
    finally:
        await router.close()


def _fail(exc: Exception, *, compact: bool = False) -> None:
    payload: dict[str, Any] = {"ok": False, "error": str(exc), "error_type": type(exc).__name__}
    if isinstance(exc, ApprovalRequired):
        payload.update(
            {"executor_id": exc.executor_id, "required_level": exc.required_level}
        )
    _emit(payload, compact=compact)
    raise typer.Exit(code=2)


@app.command()
def version() -> None:
    """Print the package version."""

    typer.echo(__version__)


@app.command()
def init(
    path: Path = typer.Argument(Path("aeep.yaml"), help="Manifest path to create."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing manifest."),
) -> None:
    """Create a runnable manifest with equivalent Python and CLI routes."""

    try:
        created = write_default_manifest(path, force=force)
        _emit(
            {
                "ok": True,
                "manifest": str(created),
                "next": [
                    "aeep doctor",
                    "aeep route text.stats --input '{\"text\":\"hello world\"}'",
                    "aeep run text.stats --input '{\"text\":\"hello world\"}'",
                ],
            }
        )
    except AEEPError as exc:
        _fail(exc)


@app.command()
def doctor(
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Validate the manifest and check local integration prerequisites."""

    try:
        parsed, manifest_path = load_manifest(manifest)
        checks: list[dict[str, Any]] = []
        for spec in parsed.executors:
            ok = True
            detail = "configuration recognized"
            if spec.kind.value == "command":
                argv = spec.config.get("argv", [])
                executable = str(argv[0]) if isinstance(argv, list) and argv else ""
                found = shutil.which(executable) if "{" not in executable else None
                ok = bool(found or "{" in executable)
                detail = f"executable: {found or executable or 'missing'}"
            elif spec.kind.value == "python":
                try:
                    load_callable(str(spec.config.get("callable", "")))
                    detail = "callable import succeeded"
                except Exception as exc:
                    ok = False
                    detail = str(exc)
            elif spec.kind.value == "http":
                ok = isinstance(spec.config.get("url"), str)
                detail = "URL configured" if ok else "missing config.url"
            elif spec.kind.value == "mcp":
                transport = spec.config.get("transport", "stdio")
                key = "command" if transport == "stdio" else "url"
                ok = isinstance(spec.config.get(key), str)
                detail = f"{transport} {key} configured" if ok else f"missing config.{key}"
            elif spec.kind.value == "delegate":
                ok = isinstance(spec.config.get("instructions"), str)
                detail = "instructions configured" if ok else "missing config.instructions"
            checks.append({"executor_id": spec.id, "kind": spec.kind.value, "ok": ok, "detail": detail})

        # Opening the router verifies the database path and all model-level constraints.
        router = Router(parsed, manifest_path=manifest_path)
        _run(router.close())
        overall = all(item["ok"] for item in checks)
        _emit(
            {
                "ok": overall,
                "version": __version__,
                "manifest": str(manifest_path),
                "database": parsed.database,
                "capabilities": sorted({item.capability for item in parsed.executors if item.enabled}),
                "checks": checks,
            },
            compact=compact,
        )
        if not overall:
            raise typer.Exit(code=1)
    except (AEEPError, OSError, ValueError) as exc:
        _fail(exc, compact=compact)


@app.command("list")
def list_capabilities(
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """List capabilities and configured execution routes."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        _emit({"capabilities": router.list_capabilities()}, compact=compact)
    except AEEPError as exc:
        _fail(exc, compact=compact)
    finally:
        if router is not None:
            _run(router.close())


@app.command()
def policies(
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """List built-in and manifest-defined policies."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        _emit({"policies": router.list_policies()}, compact=compact)
    except AEEPError as exc:
        _fail(exc, compact=compact)
    finally:
        if router is not None:
            _run(router.close())


# Typer does not provide reusable option groups, so route/run deliberately mirror
# the same core options. Stable names matter for agent skills and shell scripts.
@app.command()
def route(
    capability: str = typer.Argument(...),
    input_value: str = typer.Option("{}", "--input", "-i", help="JSON, @file, or - for stdin."),
    policy: str = typer.Option("balanced", "--policy", "-p"),
    constraints: str | None = typer.Option(None, "--constraints", help="JSON/YAML object or @file."),
    context: str | None = typer.Option(None, "--context", help="JSON/YAML action context."),
    max_cost_usd: float | None = typer.Option(None, "--max-cost-usd"),
    max_latency_ms: float | None = typer.Option(None, "--max-latency-ms"),
    max_context_tokens: int | None = typer.Option(None, "--max-context-tokens"),
    max_peak_memory_mb: float | None = typer.Option(None, "--max-peak-memory-mb"),
    no_network: bool = typer.Option(False, "--no-network"),
    require_local: bool = typer.Option(False, "--require-local"),
    executor_id: str | None = typer.Option(None, "--executor-id", help="Force one reviewed executor."),
    max_side_effect: SideEffect | None = typer.Option(None, "--max-side-effect"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Rank execution alternatives without invoking one."""

    router: Router | None = None
    try:
        request = _request(
            capability=capability,
            input_value=input_value,
            policy=policy,
            constraints_value=constraints,
            context_value=context,
            max_cost_usd=max_cost_usd,
            max_latency_ms=max_latency_ms,
            max_context_tokens=max_context_tokens,
            max_peak_memory_mb=max_peak_memory_mb,
            no_network=no_network,
            require_local=require_local,
            executor_id=executor_id,
            max_side_effect=max_side_effect,
        )
        router = Router.from_manifest(manifest)
        decision = router.route(request)
        _emit(decision, compact=compact)
        if decision.selected_executor_id is None:
            raise typer.Exit(code=3)
    except typer.Exit:
        raise
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)
    finally:
        if router is not None:
            _run(router.close())


@app.command()
def run(
    capability: str = typer.Argument(...),
    input_value: str = typer.Option("{}", "--input", "-i", help="JSON, @file, or - for stdin."),
    policy: str = typer.Option("balanced", "--policy", "-p"),
    constraints: str | None = typer.Option(None, "--constraints"),
    context: str | None = typer.Option(None, "--context"),
    max_cost_usd: float | None = typer.Option(None, "--max-cost-usd"),
    max_latency_ms: float | None = typer.Option(None, "--max-latency-ms"),
    max_context_tokens: int | None = typer.Option(None, "--max-context-tokens"),
    max_peak_memory_mb: float | None = typer.Option(None, "--max-peak-memory-mb"),
    no_network: bool = typer.Option(False, "--no-network"),
    require_local: bool = typer.Option(False, "--require-local"),
    executor_id: str | None = typer.Option(None, "--executor-id", help="Force one reviewed executor."),
    max_side_effect: SideEffect | None = typer.Option(None, "--max-side-effect"),
    approve: SideEffect = typer.Option(SideEffect.READ, "--approve", help="Runtime approval ceiling."),
    approve_unsafe_executor: bool = typer.Option(False, "--approve-unsafe-executor"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Route, invoke, validate, persist a receipt, and safely fall back."""

    router: Router | None = None
    try:
        request = _request(
            capability=capability,
            input_value=input_value,
            policy=policy,
            constraints_value=constraints,
            context_value=context,
            max_cost_usd=max_cost_usd,
            max_latency_ms=max_latency_ms,
            max_context_tokens=max_context_tokens,
            max_peak_memory_mb=max_peak_memory_mb,
            no_network=no_network,
            require_local=require_local,
            executor_id=executor_id,
            max_side_effect=max_side_effect,
        )
        router = Router.from_manifest(manifest)
        outcome = _run(
            _await_and_close(
                router,
                router.execute(
                    request,
                    approved_side_effect=approve,
                    allow_unsafe_executor=approve_unsafe_executor,
                    dry_run=dry_run,
                ),
            )
        )
        router = None
        _emit(outcome, compact=compact)
        if not outcome.ok:
            raise typer.Exit(code=4)
    except typer.Exit:
        raise
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)
    finally:
        if router is not None:
            _run(router.close())


@app.command()
def benchmark(
    capability: str = typer.Argument(...),
    input_value: str = typer.Option("{}", "--input", "-i", help="JSON, @file, or - for stdin."),
    policy: str = typer.Option("balanced", "--policy", "-p"),
    constraints: str | None = typer.Option(None, "--constraints"),
    context: str | None = typer.Option(None, "--context"),
    max_cost_usd: float | None = typer.Option(None, "--max-cost-usd"),
    max_latency_ms: float | None = typer.Option(None, "--max-latency-ms"),
    max_context_tokens: int | None = typer.Option(None, "--max-context-tokens"),
    max_peak_memory_mb: float | None = typer.Option(None, "--max-peak-memory-mb"),
    no_network: bool = typer.Option(False, "--no-network"),
    require_local: bool = typer.Option(False, "--require-local"),
    max_side_effect: SideEffect | None = typer.Option(None, "--max-side-effect"),
    approve: SideEffect = typer.Option(SideEffect.READ, "--approve"),
    approve_unsafe_executor: bool = typer.Option(False, "--approve-unsafe-executor"),
    allow_non_idempotent: bool = typer.Option(False, "--allow-non-idempotent"),
    include_delegates: bool = typer.Option(False, "--include-delegates"),
    max_routes: int | None = typer.Option(None, "--max-routes", min=1),
    confirm_all_routes: bool = typer.Option(
        False,
        "--confirm-all-routes",
        help="Acknowledge that every feasible route may run and incur cost.",
    ),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Execute alternatives sequentially to calibrate actual cost/time/compute."""

    if not confirm_all_routes:
        _fail(
            ConfigurationError(
                "benchmark executes multiple routes; review constraints and pass --confirm-all-routes"
            ),
            compact=compact,
        )
    router: Router | None = None
    try:
        request = _request(
            capability=capability,
            input_value=input_value,
            policy=policy,
            constraints_value=constraints,
            context_value=context,
            max_cost_usd=max_cost_usd,
            max_latency_ms=max_latency_ms,
            max_context_tokens=max_context_tokens,
            max_peak_memory_mb=max_peak_memory_mb,
            no_network=no_network,
            require_local=require_local,
            executor_id=None,
            max_side_effect=max_side_effect,
        )
        router = Router.from_manifest(manifest)
        result = _run(
            _await_and_close(
                router,
                router.benchmark(
                    request,
                    approved_side_effect=approve,
                    allow_unsafe_executor=approve_unsafe_executor,
                    allow_non_idempotent=allow_non_idempotent,
                    include_delegates=include_delegates,
                    max_routes=max_routes,
                ),
            )
        )
        router = None
        _emit(result, compact=compact)
    except typer.Exit:
        raise
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)
    finally:
        if router is not None:
            _run(router.close())


@app.command()
def history(
    limit: int = typer.Option(20, "--limit", min=1, max=10_000),
    receipts: bool = typer.Option(False, "--receipts", help="List receipts instead of decisions."),
    executor_id: str | None = typer.Option(None, "--executor-id"),
    capability: str | None = typer.Option(None, "--capability"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Inspect persisted decisions or observed execution receipts."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        if receipts:
            values = router.store.list_receipts(
                limit=limit, executor_id=executor_id, capability=capability
            )
            _emit({"receipts": [item.model_dump(mode="json") for item in values]}, compact=compact)
        else:
            values = router.store.list_decisions(limit=limit)
            _emit({"decisions": [item.model_dump(mode="json") for item in values]}, compact=compact)
    except AEEPError as exc:
        _fail(exc, compact=compact)
    finally:
        if router is not None:
            _run(router.close())


@app.command()
def show(
    object_id: str = typer.Argument(..., help="Decision id (dec_...) or receipt id (rcpt_...)."),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Fetch one persisted decision or receipt."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        value = (
            router.store.get_decision(object_id)
            if object_id.startswith("dec_")
            else router.store.get_receipt(object_id)
        )
        if value is None:
            _emit({"ok": False, "error": "not found", "id": object_id}, compact=compact)
            raise typer.Exit(code=1)
        _emit(value, compact=compact)
    except typer.Exit:
        raise
    except AEEPError as exc:
        _fail(exc, compact=compact)
    finally:
        if router is not None:
            _run(router.close())


@app.command()
def record(
    decision_id: str = typer.Argument(...),
    executor_id: str = typer.Argument(...),
    status: ExecutionStatus = typer.Argument(...),
    resources: str | None = typer.Option(None, "--resources", help="JSON/YAML ResourceVector."),
    output_valid: bool | None = typer.Option(None, "--output-valid/--output-invalid"),
    error_message: str | None = typer.Option(None, "--error-message"),
    metadata: str | None = typer.Option(None, "--metadata"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Record the actual outcome of a delegated browser/model/computer-use route."""

    router: Router | None = None
    try:
        report = ExternalOutcomeReport(
            decision_id=decision_id,
            executor_id=executor_id,
            status=status,
            actual_resources=ResourceVector.model_validate(
                _mapping(resources, name="resources")
            ),
            output_valid=output_valid,
            error_message=error_message,
            metadata=_mapping(metadata, name="metadata"),
        )
        router = Router.from_manifest(manifest)
        receipt = router.record_external_outcome(report)
        _emit(receipt, compact=compact)
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)
    finally:
        if router is not None:
            _run(router.close())


@app.command("tool-call")
def tool_call(
    name: str = typer.Argument(..., help="One of the four exported AEEP tool names."),
    arguments: str = typer.Option("{}", "--arguments", "-a", help="JSON/YAML object, @file, or -."),
    approve: SideEffect = typer.Option(
        SideEffect.READ,
        "--approve",
        help="Operator-controlled runtime approval ceiling.",
    ),
    approve_unsafe_executor: bool = typer.Option(False, "--approve-unsafe-executor"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Invoke an AEEP tool over deterministic JSON without running an MCP server."""

    from .mcp.server import AEEPToolService

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        result = _run(
            _await_and_close(
                router,
                AEEPToolService(
                    router,
                    approved_side_effect=approve,
                    allow_unsafe_executor=approve_unsafe_executor,
                ).call(name, _mapping(arguments, name="arguments")),
            )
        )
        router = None
        structured = result.get("structuredContent")
        payload = structured if structured is not None else result
        _emit(payload, compact=compact)
        if bool(result.get("isError", False)):
            raise typer.Exit(code=4)
    except typer.Exit:
        raise
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)
    finally:
        if router is not None:
            _run(router.close())


@tools_app.command("export")
def tools_export(
    format: str = typer.Argument(
        ...,
        help="mcp, openai-responses, openai-chat, anthropic, deepseek, or zai",
    ),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Export the four AEEP agent tools in a provider-native declaration format."""

    try:
        _emit({"tools": export_tools(format)}, compact=compact)  # type: ignore[arg-type]
    except ValueError as exc:
        _fail(exc, compact=compact)


@app.command()
def serve(
    transport: str = typer.Option("stdio", "--transport", help="stdio or http"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    approve: SideEffect = typer.Option(
        SideEffect.READ,
        "--approve",
        help="Operator-controlled approval ceiling for MCP tool execution.",
    ),
    approve_unsafe_executor: bool = typer.Option(False, "--approve-unsafe-executor"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port", min=1, max=65_535),
    token_env: str = typer.Option("AEEP_BEARER_TOKEN", "--token-env"),
) -> None:
    """Expose AEEP as an MCP server for ChatGPT/Codex, Claude, or OpenClaw."""

    from .mcp.server import create_http_app, serve_stdio

    manifest_value = str(manifest) if manifest is not None else None
    if transport == "stdio":
        try:
            _run(
                serve_stdio(
                    manifest_value,
                    approved_side_effect=approve,
                    allow_unsafe_executor=approve_unsafe_executor,
                )
            )
        except (AEEPError, OSError, ValueError) as exc:
            # stdout is the protocol stream; diagnostics must remain on stderr.
            typer.echo(f"AEEP MCP server error: {exc}", err=True)
            raise typer.Exit(code=2) from exc
        return
    if transport != "http":
        raise typer.BadParameter("transport must be stdio or http")
    token = os.getenv(token_env)
    if host not in {"127.0.0.1", "localhost", "::1"} and not token:
        raise typer.BadParameter(
            f"refusing non-loopback HTTP binding without bearer token in {token_env}"
        )
    try:
        import uvicorn
    except ImportError as exc:
        raise typer.BadParameter(
            "HTTP serving requires the http-server optional dependency"
        ) from exc
    http_app = create_http_app(
        manifest_value,
        bearer_token=token,
        approved_side_effect=approve,
        allow_unsafe_executor=approve_unsafe_executor,
    )
    uvicorn.run(http_app, host=host, port=port, log_level="info")


if __name__ == "__main__":  # pragma: no cover
    app()
