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
import sysconfig
from pathlib import Path
from typing import Any

import typer
import yaml

from .config import find_manifest, load_manifest, write_default_manifest
from .errors import AEEPError, ApprovalRequired, ConfigurationError
from .executors.python import load_callable
from .integrations import export_tools
from .models import (
    ActionConstraints,
    ActionContext,
    ActionRequest,
    ExecutionStatus,
    ExternalOutcomeReport,
    QuotaSource,
    QuotaState,
    QuoteRequest,
    ResourceVector,
    SideEffect,
    SubscriptionQuota,
    SubscriptionResource,
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
import_app = typer.Typer(help="Import existing CLI, MCP, or OpenAPI capabilities.")
subscriptions_app = typer.Typer(help="Manage user-owned model and tool subscriptions.")
quota_app = typer.Typer(help="Set or observe subscription quota pressure.")
skill_app = typer.Typer(help="Install the packaged AEEP skill into an agent host.")
ingest_app = typer.Typer(help="Ingest traces from existing agent runtimes.")
candidate_app = typer.Typer(help="Qualify and activate inert imported routes.")
workflow_app = typer.Typer(help="Run caller-authored bounded workflows.")
campaign_app = typer.Typer(help="Run isolated repeated benchmark campaigns.")
app.add_typer(tools_app, name="tools")
app.add_typer(import_app, name="import")
app.add_typer(subscriptions_app, name="subscriptions")
app.add_typer(quota_app, name="quota")
app.add_typer(skill_app, name="skill")
app.add_typer(ingest_app, name="ingest")
app.add_typer(candidate_app, name="candidate")
app.add_typer(workflow_app, name="workflow")
app.add_typer(campaign_app, name="campaign")


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
        payload.update({"executor_id": exc.executor_id, "required_level": exc.required_level})
    _emit(payload, compact=compact)
    raise typer.Exit(code=2)


def _manifest_document(path: Path | None) -> tuple[Path, dict[str, Any]]:
    manifest_path = find_manifest(path)
    value = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ConfigurationError("manifest root must be a mapping")
    return manifest_path, value


def _write_manifest_document(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(value, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _packaged_skill() -> Path:
    candidates = [
        Path(__file__).resolve().parents[2] / "skills" / "aeep-minimal",
        Path(sysconfig.get_path("data")) / "share" / "aeep" / "skills" / "aeep-minimal",
    ]
    for candidate in candidates:
        if (candidate / "SKILL.md").is_file():
            return candidate
    raise ConfigurationError("packaged AEEP skill was not found; reinstall the distribution")


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
                    'aeep route text.stats --input \'{"text":"hello world"}\'',
                    'aeep run text.stats --input \'{"text":"hello world"}\'',
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
            elif spec.kind.value in {"delegate", "host"}:
                ok = isinstance(spec.config.get("instructions"), str)
                detail = "instructions configured" if ok else "missing config.instructions"
            checks.append(
                {"executor_id": spec.id, "kind": spec.kind.value, "ok": ok, "detail": detail}
            )

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
                "capabilities": sorted(
                    {item.capability for item in parsed.executors if item.enabled}
                ),
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
    prefix: str | None = typer.Option(None, "--prefix"),
    limit: int = typer.Option(20, "--limit", min=1, max=100),
    cursor: int = typer.Option(0, "--cursor", min=0),
    details: bool = typer.Option(True, "--details/--summary"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """List capabilities and configured execution routes."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        _emit(
            router.search_capabilities(
                prefix=prefix,
                limit=limit,
                cursor=cursor,
                include_executors=details,
            ),
            compact=compact,
        )
    except AEEPError as exc:
        _fail(exc, compact=compact)
    finally:
        if router is not None:
            _run(router.close())


@app.command()
def search(
    query: str = typer.Argument(""),
    prefix: str | None = typer.Option(None, "--prefix"),
    limit: int = typer.Option(20, "--limit", min=1, max=100),
    cursor: int = typer.Option(0, "--cursor", min=0),
    details: bool = typer.Option(False, "--details"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Search capabilities without loading every executor into the response."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        _emit(
            router.search_capabilities(
                query,
                prefix=prefix,
                limit=limit,
                cursor=cursor,
                include_executors=details,
            ),
            compact=compact,
        )
    except AEEPError as exc:
        _fail(exc, compact=compact)
    finally:
        if router is not None:
            _run(router.close())


@subscriptions_app.command("add")
def subscriptions_add(
    resource_id: str = typer.Argument(...),
    provider: str = typer.Option(..., "--provider"),
    product: str = typer.Option(..., "--product"),
    unit: str = typer.Option("provider_unit", "--unit"),
    access: str = typer.Option("host", "--access"),
    state: QuotaState = typer.Option(QuotaState.UNKNOWN, "--state"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Add a named commercial or local subscription resource."""

    try:
        resource = SubscriptionResource.model_validate(
            {
                "id": resource_id,
                "provider": provider,
                "product": product,
                "unit": unit,
                "access": {"mode": access},
                "quota": {"state": state.value, "source": "user"},
            }
        )
        manifest_path, document = _manifest_document(manifest)
        resources = document.setdefault("resources", [])
        if not isinstance(resources, list):
            raise ConfigurationError("manifest resources must be a list")
        if any(isinstance(item, dict) and item.get("id") == resource_id for item in resources):
            raise ConfigurationError(f"subscription resource {resource_id!r} already exists")
        resources.append(resource.model_dump(mode="json"))
        _write_manifest_document(manifest_path, document)
        _emit({"ok": True, "manifest": str(manifest_path), "resource": resource}, compact=compact)
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)


@subscriptions_app.command("status")
def subscriptions_status(
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Show subscription products and their effective quota pressure."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        _emit({"subscriptions": router.subscription_status()}, compact=compact)
    except AEEPError as exc:
        _fail(exc, compact=compact)
    finally:
        if router is not None:
            _run(router.close())


@quota_app.command("set")
def quota_set(
    resource_id: str = typer.Argument(...),
    state: QuotaState = typer.Argument(...),
    reset_at: str | None = typer.Option(None, "--reset-at"),
    confidence: float = typer.Option(1.0, "--confidence", min=0.0, max=1.0),
    source: QuotaSource = typer.Option(QuotaSource.USER, "--source"),
    allowance_units: float | None = typer.Option(None, "--allowance-units", min=0),
    remaining_units: float | None = typer.Option(None, "--remaining-units", min=0),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Set the manifest's cold-start quota state."""

    try:
        quota = SubscriptionQuota.model_validate(
            {
                "state": state.value,
                "reset_at": reset_at,
                "confidence": confidence,
                "source": source.value,
                "allowance_units": allowance_units,
                "remaining_units": remaining_units,
            }
        )
        manifest_path, document = _manifest_document(manifest)
        resources = document.get("resources", [])
        target = next(
            (
                item
                for item in resources
                if isinstance(item, dict) and item.get("id") == resource_id
            ),
            None,
        )
        if target is None:
            raise ConfigurationError(f"unknown subscription resource {resource_id!r}")
        target["quota"] = quota.model_dump(mode="json")
        _write_manifest_document(manifest_path, document)
        _emit({"ok": True, "resource_id": resource_id, "quota": quota}, compact=compact)
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)


@quota_app.command("observe")
def quota_observe(
    resource_id: str = typer.Argument(...),
    state: QuotaState = typer.Argument(...),
    reset_at: str | None = typer.Option(None, "--reset-at"),
    confidence: float = typer.Option(1.0, "--confidence", min=0.0, max=1.0),
    source: QuotaSource = typer.Option(QuotaSource.OBSERVED, "--source"),
    note: str | None = typer.Option(None, "--note"),
    allowance_units: float | None = typer.Option(None, "--allowance-units", min=0),
    remaining_units: float | None = typer.Option(None, "--remaining-units", min=0),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Record a runtime quota signal without rewriting the manifest."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        observation = router.observe_quota(
            resource_id,
            {
                "state": state.value,
                "reset_at": reset_at,
                "confidence": confidence,
                "source": source.value,
                "allowance_units": allowance_units,
                "remaining_units": remaining_units,
            },
            note=note,
        )
        _emit(observation, compact=compact)
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)
    finally:
        if router is not None:
            _run(router.close())


@ingest_app.command("otel")
def ingest_otel(
    path: Path = typer.Argument(..., exists=True, dir_okay=False),
    record: bool = typer.Option(True, "--record/--no-record"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Reconstruct model, tool, browser, CLI, MCP, and HTTP calls from OTLP JSON."""

    from .instrumentation import TraceIngestor

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        ingestor = TraceIngestor(router.registry)
        report = ingestor.load(path)
        if record:
            ingestor.record(report, router.store)
        _emit(report, compact=compact)
    except (AEEPError, ValueError, OSError, json.JSONDecodeError) as exc:
        _fail(exc, compact=compact)
    finally:
        if router is not None:
            _run(router.close())


@skill_app.command("install")
def skill_install(
    host: str = typer.Argument(..., help="codex, claude, or openclaw"),
    target: Path | None = typer.Option(None, "--target", help="Override installation path."),
    force: bool = typer.Option(False, "--force"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Install the subscription-aware skill included in the wheel."""

    defaults = {
        "codex": Path(os.getenv("CODEX_HOME", Path.home() / ".codex")) / "skills" / "aeep",
        "claude": Path.home() / ".claude" / "skills" / "aeep",
        "openclaw": Path.home() / ".openclaw" / "skills" / "aeep",
    }
    try:
        if host not in defaults:
            raise ConfigurationError("host must be codex, claude, or openclaw")
        destination = (target or defaults[host]).expanduser()
        if destination.exists() and not force:
            raise ConfigurationError(
                f"refusing to overwrite existing skill {destination}; pass --force"
            )
        shutil.copytree(_packaged_skill(), destination, dirs_exist_ok=force)
        _emit({"ok": True, "host": host, "skill": str(destination)}, compact=compact)
    except (AEEPError, OSError) as exc:
        _fail(exc, compact=compact)


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


@app.command()
def metrics(
    limit: int = typer.Option(10_000, "--limit", min=1, max=10_000),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Summarize execution savings and subscription capacity conserved."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        _emit(router.metrics(limit=limit), compact=compact)
    except AEEPError as exc:
        _fail(exc, compact=compact)
    finally:
        if router is not None:
            _run(router.close())


@app.command()
def quote(
    capability: str = typer.Argument(...),
    input_value: str = typer.Option("{}", "--input", "-i", help="JSON, @file, or -."),
    executor_id: list[str] | None = typer.Option(None, "--executor-id"),
    policy: str = typer.Option("balanced", "--policy", "-p"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Request bounded static/provider quotes without accepting payment."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        request = QuoteRequest(
            action=ActionRequest(
                capability=capability,
                input=_mapping(input_value, name="input"),
                policy=policy,
            ),
            executor_ids=executor_id,
        )
        _emit(
            {"quotes": [item.model_dump(mode="json") for item in router.quotes(request)]},
            compact=compact,
        )
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)
    finally:
        if router is not None:
            _run(router.close())


@app.command("accept-quote")
def accept_quote(
    quote_id: str = typer.Argument(...),
    action_id: str = typer.Argument(...),
    max_amount_usd: float | None = typer.Option(None, "--max-amount-usd", min=0),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Explicitly accept one stored quote; this is not exposed as a model tool."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        _emit(
            router.accept_quote(
                quote_id,
                action_id=action_id,
                max_amount_usd=max_amount_usd,
            ),
            compact=compact,
        )
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)
    finally:
        if router is not None:
            _run(router.close())


@app.command("sign-receipt")
def sign_receipt(
    receipt_id: str = typer.Argument(...),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Sign a persisted receipt with the operator-configured local identity."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        _emit(router.signed_receipt(receipt_id), compact=compact)
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)
    finally:
        if router is not None:
            _run(router.close())


@app.command()
def counterfactual(
    receipt_id: str = typer.Argument(...),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Show feasible routes that could have avoided observed cost or scarcity."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        _emit(router.counterfactual(receipt_id), compact=compact)
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)
    finally:
        if router is not None:
            _run(router.close())


@app.command()
def reputation(
    provider_id: str = typer.Argument(...),
    capability: str = typer.Argument(...),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Aggregate measured or verified outcomes; provider claims are excluded."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        _emit(router.reputation(provider_id, capability), compact=compact)
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)
    finally:
        if router is not None:
            _run(router.close())


@app.command("reserve-payment")
def reserve_payment(
    quote_id: str = typer.Argument(...),
    action_id: str = typer.Argument(...),
    approve: SideEffect = typer.Option(SideEffect.READ, "--approve"),
    human_approved: bool = typer.Option(False, "--human-approved"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Reserve funds under the operator budget and financial approval ceiling."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        result = _run(
            _await_and_close(
                router,
                router.reserve_quote_payment(
                    quote_id,
                    action_id=action_id,
                    approved_side_effect=approve,
                    human_approved=human_approved,
                ),
            )
        )
        router = None
        _emit(result, compact=compact)
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)
    finally:
        if router is not None:
            _run(router.close())


@app.command("capture-payment")
def capture_payment(
    reservation_id: str = typer.Argument(...),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Capture a previously approved reservation after delivery."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        result = _run(_await_and_close(router, router.capture_payment(reservation_id)))
        router = None
        _emit(result, compact=compact)
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)
    finally:
        if router is not None:
            _run(router.close())


@app.command("refund-payment")
def refund_payment(
    capture_id: str = typer.Argument(...),
    amount_usd: float = typer.Argument(..., min=0),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Refund a captured payment through the configured adapter."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        result = _run(_await_and_close(router, router.refund_payment(capture_id, amount_usd)))
        router = None
        _emit(result, compact=compact)
    except (AEEPError, ValueError, OSError) as exc:
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
    constraints: str | None = typer.Option(
        None, "--constraints", help="JSON/YAML object or @file."
    ),
    context: str | None = typer.Option(None, "--context", help="JSON/YAML action context."),
    max_cost_usd: float | None = typer.Option(None, "--max-cost-usd"),
    max_latency_ms: float | None = typer.Option(None, "--max-latency-ms"),
    max_context_tokens: int | None = typer.Option(None, "--max-context-tokens"),
    max_peak_memory_mb: float | None = typer.Option(None, "--max-peak-memory-mb"),
    no_network: bool = typer.Option(False, "--no-network"),
    require_local: bool = typer.Option(False, "--require-local"),
    executor_id: str | None = typer.Option(
        None, "--executor-id", help="Force one reviewed executor."
    ),
    max_side_effect: SideEffect | None = typer.Option(None, "--max-side-effect"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    agent_view: bool = typer.Option(False, "--agent", help="Return the compact agent view."),
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
        decision = _run(_await_and_close(router, router.route_with_discovery(request)))
        rendered = router.compact_decision(decision) if agent_view else decision
        router = None
        _emit(rendered, compact=compact)
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
    executor_id: str | None = typer.Option(
        None, "--executor-id", help="Force one reviewed executor."
    ),
    max_side_effect: SideEffect | None = typer.Option(None, "--max-side-effect"),
    approve: SideEffect = typer.Option(
        SideEffect.READ, "--approve", help="Runtime approval ceiling."
    ),
    approve_unsafe_executor: bool = typer.Option(False, "--approve-unsafe-executor"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    agent_view: bool = typer.Option(False, "--agent", help="Return the compact agent view."),
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
        request.idempotency_key = idempotency_key
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
        rendered = router.compact_outcome(outcome) if agent_view else outcome
        router = None
        _emit(rendered, compact=compact)
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
            receipt_values = router.store.list_receipts(
                limit=limit, executor_id=executor_id, capability=capability
            )
            _emit(
                {"receipts": [item.model_dump(mode="json") for item in receipt_values]},
                compact=compact,
            )
        else:
            decision_values = router.store.list_decisions(limit=limit)
            _emit(
                {"decisions": [item.model_dump(mode="json") for item in decision_values]},
                compact=compact,
            )
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
    task_valid: bool | None = typer.Option(None, "--task-valid/--task-invalid"),
    quality_score: float | None = typer.Option(None, "--quality-score", min=0.0, max=1.0),
    quota_state: QuotaState | None = typer.Option(None, "--quota-state"),
    quota_reset_at: str | None = typer.Option(None, "--quota-reset-at"),
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
            actual_resources=ResourceVector.model_validate(_mapping(resources, name="resources")),
            output_valid=output_valid,
            task_valid=task_valid,
            quality_score=quality_score,
            quota_observation=(
                SubscriptionQuota.model_validate(
                    {
                        "state": quota_state.value,
                        "reset_at": quota_reset_at,
                        "confidence": 1,
                        "source": QuotaSource.HOST.value,
                    }
                )
                if quota_state is not None
                else None
            ),
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
    name: str = typer.Argument(..., help="One of the exported AEEP tool names."),
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
    """Export the AEEP agent tools in a provider-native declaration format."""

    try:
        _emit({"tools": export_tools(format)}, compact=compact)  # type: ignore[arg-type]
    except ValueError as exc:
        _fail(exc, compact=compact)


@app.command()
def publish(
    provider_id: str = typer.Option(..., "--provider-id"),
    name: str = typer.Option(..., "--name"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    output: Path | None = typer.Option(None, "--output", "-o"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Generate a local provider descriptor; network publication is registry-specific."""

    from .sdk import provider_from_manifest

    try:
        parsed, _ = load_manifest(manifest)
        descriptor = provider_from_manifest(parsed, provider_id=provider_id, name=name)
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(descriptor.model_dump_json(indent=2) + "\n", encoding="utf-8")
        _emit(descriptor, compact=compact)
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)


@import_app.command("cli")
def import_cli_command(
    provider_id: str = typer.Option(..., "--provider-id"),
    capability: str = typer.Option(..., "--capability"),
    argv: str = typer.Option(..., "--argv", help="JSON argv array; shell strings are rejected."),
    input_schema: str | None = typer.Option(None, "--input-schema"),
    output_schema: str | None = typer.Option(None, "--output-schema"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Create a provider descriptor for an argv-only JSON-stdin command."""

    from .sdk import import_cli

    try:
        argv_value = _read_data(argv, default=[])
        if not isinstance(argv_value, list) or not all(
            isinstance(item, str) for item in argv_value
        ):
            raise typer.BadParameter("--argv must be a JSON string array")
        descriptor = import_cli(
            provider_id=provider_id,
            capability_name=capability,
            argv=argv_value,
            input_schema=_mapping(input_schema, name="input-schema") if input_schema else None,
            output_schema=_mapping(output_schema, name="output-schema") if output_schema else None,
        )
        _emit(descriptor, compact=compact)
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)


@import_app.command("mcp")
def import_mcp_command(
    provider_id: str = typer.Option(..., "--provider-id"),
    capability: str = typer.Option(..., "--capability"),
    tool: str = typer.Option(..., "--tool"),
    transport: str = typer.Option("stdio", "--transport"),
    endpoint: str = typer.Option(..., "--endpoint"),
    args: str = typer.Option("[]", "--args", help="JSON argv tail for stdio."),
    headers: str | None = typer.Option(None, "--headers", help="JSON header templates."),
    credential_scope_id: str | None = typer.Option(None, "--credential-scope-id"),
    protocol_mode: str = typer.Option("auto", "--protocol-mode"),
    input_schema: str | None = typer.Option(None, "--input-schema"),
    output_schema: str | None = typer.Option(None, "--output-schema"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Create a provider descriptor for one reviewed MCP tool."""

    from .sdk import import_mcp

    try:
        if transport not in {"stdio", "http", "streamable_http", "streamable-http"}:
            raise typer.BadParameter("transport must be stdio or streamable HTTP")
        args_value = _read_data(args, default=[])
        if not isinstance(args_value, list) or not all(
            isinstance(item, str) for item in args_value
        ):
            raise typer.BadParameter("--args must be a JSON string array")
        if protocol_mode not in {"auto", "modern", "legacy"}:
            raise typer.BadParameter("--protocol-mode must be auto, modern, or legacy")
        descriptor = import_mcp(
            provider_id=provider_id,
            capability_name=capability,
            tool=tool,
            transport=transport,
            endpoint=endpoint,
            args=args_value,
            headers=(
                {str(key): str(value) for key, value in _mapping(headers, name="headers").items()}
                if headers
                else None
            ),
            credential_scope_id=credential_scope_id,
            protocol_mode=protocol_mode,
            input_schema=_mapping(input_schema, name="input-schema") if input_schema else None,
            output_schema=_mapping(output_schema, name="output-schema") if output_schema else None,
        )
        _emit(descriptor, compact=compact)
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)


@import_app.command("mcp-server")
def import_mcp_server_command(
    provider_id: str = typer.Option(..., "--provider-id"),
    transport: str = typer.Option("stdio", "--transport"),
    endpoint: str = typer.Option(..., "--endpoint"),
    args: str = typer.Option("[]", "--args", help="JSON argv tail for stdio."),
    capability_prefix: str | None = typer.Option(None, "--capability-prefix"),
    headers: str | None = typer.Option(None, "--headers", help="JSON header templates."),
    credential_scope_id: str | None = typer.Option(None, "--credential-scope-id"),
    protocol_mode: str = typer.Option("auto", "--protocol-mode"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Inspect an MCP server and import every advertised tool."""

    from .sdk import import_mcp_server

    try:
        args_value = _read_data(args, default=[])
        if not isinstance(args_value, list) or not all(
            isinstance(item, str) for item in args_value
        ):
            raise typer.BadParameter("--args must be a JSON string array")
        if protocol_mode not in {"auto", "modern", "legacy"}:
            raise typer.BadParameter("--protocol-mode must be auto, modern, or legacy")
        descriptor = _run(
            import_mcp_server(
                provider_id=provider_id,
                transport=transport,
                endpoint=endpoint,
                args=args_value,
                headers=(
                    {
                        str(key): str(value)
                        for key, value in _mapping(headers, name="headers").items()
                    }
                    if headers
                    else None
                ),
                credential_scope_id=credential_scope_id,
                capability_prefix=capability_prefix,
                protocol_mode=protocol_mode,
            )
        )
        _emit(descriptor, compact=compact)
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)


@import_app.command("openapi")
def import_openapi_command(
    path: Path = typer.Argument(...),
    provider_id: str = typer.Option(..., "--provider-id"),
    base_url: str | None = typer.Option(None, "--base-url"),
    capability_map: str | None = typer.Option(
        None,
        "--capability-map",
        help="JSON object mapping operationId to canonical capability@version.",
    ),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Create HTTP executor descriptors from an OpenAPI document."""

    from .sdk import import_openapi

    try:
        _emit(
            import_openapi(
                path,
                provider_id=provider_id,
                base_url=base_url,
                capability_map=(
                    {
                        str(key): str(value)
                        for key, value in _mapping(capability_map, name="capability-map").items()
                    }
                    if capability_map
                    else None
                ),
            ),
            compact=compact,
        )
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)


@candidate_app.command("status")
def candidate_status(
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    router = Router.from_manifest(manifest)
    try:
        _emit(
            [item.model_dump(mode="json") for item in router.candidate_status()],
            compact=compact,
        )
    except (AEEPError, ValueError) as exc:
        _fail(exc, compact=compact)
    finally:
        _run(router.close())


@candidate_app.command("ingest")
def candidate_ingest(
    descriptor: str = typer.Argument(..., help="ProviderDescriptor JSON/YAML or @file"),
    source_id: str = typer.Option(..., "--source-id"),
    capability: str | None = typer.Option(None, "--capability"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Persist imported provider routes as inert candidates."""

    from .models import ProviderDescriptor

    router = Router.from_manifest(manifest)
    try:
        provider = ProviderDescriptor.model_validate(_read_data(descriptor, default={}))
        candidates = [
            router.ingest_candidate(spec, source_id=source_id)
            for spec in provider.executors
            if capability is None or spec.capability == capability
        ]
        if not candidates:
            raise typer.BadParameter("descriptor contains no matching executors")
        _emit([item.model_dump(mode="json") for item in candidates], compact=compact)
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)
    finally:
        _run(router.close())


@candidate_app.command("qualify")
def candidate_qualify(
    executor_id: str,
    side_effect: SideEffect = typer.Option(SideEffect.READ, "--side-effect"),
    idempotent: bool = typer.Option(False, "--idempotent"),
    safe_to_auto_execute: bool = typer.Option(False, "--safe-to-auto-execute"),
    cases: str | None = typer.Option(None, "--cases", help="JSON/YAML list or @file"),
    repetitions: int = typer.Option(1, "--repetitions", min=1, max=1000),
    conditions: str = typer.Option(
        "process-cold", "--conditions", help="Comma-separated process-cold,router-warm"
    ),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    from .qualification import QualificationCase, QualificationCondition

    parsed = _read_data(cases, default=[])
    if not isinstance(parsed, list):
        raise typer.BadParameter("cases must be a list")
    router = Router.from_manifest(manifest)
    try:
        result = _run(
            _await_and_close(
                router,
                router.qualify_candidate(
                    executor_id,
                    side_effect=side_effect,
                    idempotent=idempotent,
                    safe_to_auto_execute=safe_to_auto_execute,
                    cases=[QualificationCase.model_validate(item) for item in parsed],
                    repetitions=repetitions,
                    conditions=[
                        QualificationCondition(item.strip())
                        for item in conditions.split(",")
                        if item.strip()
                    ],
                ),
            )
        )
        _emit(result, compact=compact)
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)


@candidate_app.command("activate")
def candidate_activate(
    executor_id: str,
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    router = Router.from_manifest(manifest)
    try:
        _emit(router.activate_candidate(executor_id), compact=compact)
    except (AEEPError, ValueError) as exc:
        _fail(exc, compact=compact)
    finally:
        _run(router.close())


@candidate_app.command("suspend")
def candidate_suspend(
    executor_id: str,
    reason: str = typer.Option(..., "--reason"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    router = Router.from_manifest(manifest)
    try:
        _emit(router.suspend_candidate(executor_id, reason=reason), compact=compact)
    except (AEEPError, ValueError) as exc:
        _fail(exc, compact=compact)
    finally:
        _run(router.close())


@workflow_app.command("run")
def workflow_run(
    request: str = typer.Argument(..., help="Workflow JSON/YAML or @file"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    approve: SideEffect = typer.Option(SideEffect.READ, "--approve"),
    approve_unsafe_executor: bool = typer.Option(False, "--approve-unsafe-executor"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    from .workflow import WorkflowRequest

    router = Router.from_manifest(manifest)
    try:
        result = _run(
            _await_and_close(
                router,
                router.execute_workflow(
                    WorkflowRequest.model_validate(_read_data(request, default={})),
                    approved_side_effect=approve,
                    allow_unsafe_executor=approve_unsafe_executor,
                ),
            )
        )
        _emit(result, compact=compact)
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)


@workflow_app.command("resume")
def workflow_resume(
    request: str = typer.Argument(..., help="Original workflow JSON/YAML or @file"),
    waiting: str = typer.Argument(..., help="WAITING outcome JSON/YAML or @file"),
    step_id: str = typer.Option(..., "--step-id"),
    output: str = typer.Option(..., "--output", help="Validated output JSON/YAML or @file"),
    accounting: str | None = typer.Option(
        None, "--accounting", help="Trusted ResourceAccounting JSON/YAML or @file"
    ),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    approve: SideEffect = typer.Option(SideEffect.READ, "--approve"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    from .models import ResourceAccounting
    from .workflow import WorkflowExecutionOutcome, WorkflowRequest

    router = Router.from_manifest(manifest)
    try:
        result = _run(
            _await_and_close(
                router,
                router.resume_workflow(
                    WorkflowRequest.model_validate(_read_data(request, default={})),
                    WorkflowExecutionOutcome.model_validate(_read_data(waiting, default={})),
                    step_id=step_id,
                    output=_read_data(output, default=None),
                    actual_accounting=(
                        ResourceAccounting.model_validate(_read_data(accounting, default={}))
                        if accounting is not None
                        else None
                    ),
                    approved_side_effect=approve,
                ),
            )
        )
        _emit(result, compact=compact)
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)


@campaign_app.command("run")
def campaign_run(
    suite: str = typer.Argument(..., help="Benchmark suite JSON/YAML or @file"),
    database: Path = typer.Option(Path(".aeep/benchmarks.db"), "--database"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    output: Path | None = typer.Option(None, "--output", "-o"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    from .benchmarking import BenchmarkRunner, BenchmarkSuite, format_campaign_report
    from .store import ReceiptStore

    source = Router.from_manifest(manifest)
    snapshot = source.manifest.model_copy(deep=True)
    snapshot.database = ":memory:"
    candidates = source.store.list_route_candidates()
    candidate_ids = {candidate.executor_id for candidate in candidates}
    reports = [
        report
        for candidate in candidates
        if candidate.qualification_report_id is not None
        and (report := source.store.get_qualification_report(candidate.qualification_report_id))
        is not None
    ]
    snapshot.executors = [
        spec.model_copy(deep=True) for spec in source.registry.all() if spec.id not in candidate_ids
    ]
    _run(source.close())

    def isolated_router() -> Router:
        store = ReceiptStore(":memory:")
        for candidate in candidates:
            store.save_route_candidate(candidate)
        for report in reports:
            store.save_qualification_report(report)
        return Router(snapshot, store=store)

    runner = BenchmarkRunner(isolated_router, database)
    try:
        report = _run(runner.run(BenchmarkSuite.model_validate(_read_data(suite, default={}))))
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
        if compact:
            _emit(report, compact=True)
        else:
            typer.echo(format_campaign_report(report))
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)


@campaign_app.command("prove")
def campaign_prove(
    reports: str | None = typer.Argument(None, help="BenchmarkCampaignReport list or @file"),
    report_file: list[Path] = typer.Option(
        [], "--report-file", help="Repeat for individual campaign report files."
    ),
    baseline_route: list[str] = typer.Option(..., "--baseline-route"),
    hybrid_route: str = typer.Option(..., "--hybrid-route"),
    output: Path | None = typer.Option(None, "--output", "-o"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Evaluate the locked 0.3 release thresholds without filling missing evidence."""

    from .benchmarking import (
        BenchmarkCampaignReport,
        evaluate_release_proof,
    )

    try:
        values = _read_data(reports, default=[])
        if not isinstance(values, list):
            raise typer.BadParameter("reports must be a list")
        values.extend(_read_data(f"@{path}", default={}) for path in report_file)
        if not values:
            raise typer.BadParameter("at least one campaign report is required")
        result = evaluate_release_proof(
            [BenchmarkCampaignReport.model_validate(item) for item in values],
            baseline_route_ids=baseline_route,
            hybrid_route_id=hybrid_route,
        )
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
        _emit(result, compact=compact)
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)


@campaign_app.command("revalue")
def campaign_revalue(
    report: str = typer.Argument(..., help="BenchmarkCampaignReport JSON/YAML or @file"),
    snapshot: str = typer.Argument(..., help="RateCardSnapshot JSON/YAML or @file"),
    output: Path | None = typer.Option(None, "--output", "-o"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Create a separate API-equivalent report under an immutable rate card."""

    from .benchmarking import BenchmarkCampaignReport, revalue_campaign
    from .models import RateCardSnapshot

    try:
        result = revalue_campaign(
            BenchmarkCampaignReport.model_validate(_read_data(report, default={})),
            RateCardSnapshot.model_validate(_read_data(snapshot, default={})),
        )
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
        _emit(result, compact=compact)
    except (AEEPError, ValueError, OSError) as exc:
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
