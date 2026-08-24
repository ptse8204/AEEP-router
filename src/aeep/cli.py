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
from datetime import UTC, datetime
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
    BoundedQuote,
    CapabilityOffer,
    ExecutionOutcome,
    ExecutionStatus,
    ExternalOutcomeReport,
    MarketAggregate,
    PaymentReservationState,
    PreparedRouteDecision,
    QuotaSource,
    QuotaState,
    QuoteFailurePolicy,
    QuoteRequest,
    ResourceVector,
    SettlementReceipt,
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
provider_app = typer.Typer(help="Validate, digest, verify, and sign provider packages.")
evidence_app = typer.Typer(help="Inspect accepted portable provider evidence.")
registry_app = typer.Typer(help="Search bounded provider-package registry metadata.")
workflow_app = typer.Typer(help="Run caller-authored bounded workflows.")
campaign_app = typer.Typer(help="Run isolated repeated benchmark campaigns.")
offer_app = typer.Typer(help="Inspect and import signed capability offers.")
economic_app = typer.Typer(help="Prepare routes and inspect economic evidence.")
settlement_app = typer.Typer(help="Inspect and reconcile settlement evidence.")
market_app = typer.Typer(help="Run the local reference economic market.")
app.add_typer(tools_app, name="tools")
app.add_typer(import_app, name="import")
app.add_typer(subscriptions_app, name="subscriptions")
app.add_typer(quota_app, name="quota")
app.add_typer(skill_app, name="skill")
app.add_typer(ingest_app, name="ingest")
app.add_typer(candidate_app, name="candidate")
app.add_typer(provider_app, name="provider")
app.add_typer(evidence_app, name="evidence")
app.add_typer(registry_app, name="registry")
app.add_typer(workflow_app, name="workflow")
app.add_typer(campaign_app, name="campaign")
app.add_typer(offer_app, name="offer")
app.add_typer(economic_app, name="economic")
app.add_typer(settlement_app, name="settlement")
app.add_typer(market_app, name="market")


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


def _economic_emit(
    value: Any,
    *,
    json_output: bool,
    title: str,
    fields: list[tuple[str, Any]],
) -> None:
    """Render new operator commands as prose unless JSON was requested."""

    if json_output:
        _emit(value)
        return
    typer.echo(title)
    for label, item in fields:
        if item is None:
            rendered = "unknown"
        elif isinstance(item, list | tuple):
            rendered = ", ".join(str(part) for part in item) or "none"
        else:
            rendered = str(item)
        typer.echo(f"{label}: {rendered}")


def _economic_fail(exc: Exception, *, json_output: bool) -> None:
    if json_output:
        _fail(exc, compact=True)
    typer.echo(f"AEEP economic error: {exc}", err=True)
    raise typer.Exit(code=2)


def _trust_verifier(router: Router) -> Any:
    """Load only operator-trusted keys, retaining database copies for audit."""

    from .economic import merge_trusted_provider_keys
    from .economic.trust import TrustStore, TrustStoreVerifier

    configured_path = Path(router.manifest.economic_evidence.trust_store.path).expanduser()
    configured_keys = (
        TrustStore.load(configured_path).list_keys() if configured_path.is_file() else []
    )
    stored_keys = router.store.list_provider_signing_keys()
    trust = merge_trusted_provider_keys(configured_keys, stored_keys)
    if not trust.list_keys():
        raise ConfigurationError(
            f"no trusted provider keys are configured at {configured_path} or in the database"
        )
    return TrustStoreVerifier(trust)


def _verify_offer(router: Router, offer: CapabilityOffer) -> dict[str, Any]:
    from .economic.canonical import canonical_payload

    now = datetime.now(UTC)
    status = router.store.capability_offer_status(offer.offer_id)
    signature = _trust_verifier(router).verify(
        canonical_payload(offer),
        offer.signature,
        offer.provider_id,
        capability=offer.capability,
    )
    active = offer.valid_at(now) and (status is None or status["status"] != "revoked")
    return {
        "ok": signature.valid and active,
        "offer_id": offer.offer_id,
        "provider_id": offer.provider_id,
        "signature_valid": signature.valid,
        "signature_reason": signature.reason,
        "active": active,
        "expires_at": offer.valid_until.isoformat(),
        "evidence_level": "PUBLISHED_OFFER",
    }


def _verify_quote(router: Router, quote: BoundedQuote) -> dict[str, Any]:
    from .economic.canonical import canonical_payload

    request = router.store.get_quote_request_v2(quote.quote_request_id)
    if request is None:
        raise ConfigurationError("the quote's bound request is not stored")
    verification = _trust_verifier(router).verify(
        canonical_payload(quote),
        quote.signature,
        quote.provider_id,
        capability=quote.capability,
    )
    binding_valid = False
    binding_reason = "signature verification failed"
    if verification.valid:
        try:
            quote.validate_binding(
                request,
                at=datetime.now(UTC),
                maximum_ttl_seconds=(
                    router.manifest.economic_evidence.live_quotes.maximum_quote_ttl_seconds
                ),
            )
            binding_valid = True
            binding_reason = "quote binding verified"
        except ValueError as exc:
            binding_reason = str(exc)
    return {
        "ok": verification.valid and binding_valid,
        "quote_id": quote.quote_id,
        "provider_id": quote.provider_id,
        "signature_valid": verification.valid,
        "signature_reason": verification.reason,
        "binding_valid": binding_valid,
        "binding_reason": binding_reason,
        "nonce_used": router.store.quote_nonce_was_used(quote.nonce),
        "expires_at": quote.expires_at.isoformat(),
        "evidence_level": quote.evidence_level.value,
    }


def _verify_market_aggregate(
    router: Router, aggregate: MarketAggregate
) -> dict[str, Any]:
    """Verify a market prior without treating it as qualification evidence."""

    from .economic.canonical import canonical_payload

    verifier = _trust_verifier(router)
    payload = canonical_payload(aggregate)
    current = verifier.verify(
        payload,
        aggregate.signature,
        aggregate.provider_id,
        capability=aggregate.capability,
    )
    historical = verifier.verify(
        payload,
        aggregate.signature,
        aggregate.provider_id,
        capability=aggregate.capability,
        signed_at=aggregate.generated_at,
        allow_historical=True,
    )
    now = datetime.now(UTC)
    fresh = aggregate.fresh_at(now)
    return {
        "ok": current.valid and historical.valid and fresh,
        "aggregate_id": aggregate.aggregate_id,
        "provider_id": aggregate.provider_id,
        "signature_valid": current.valid,
        "signature_reason": current.reason,
        "historical_signature_valid": historical.valid,
        "historical_signature_reason": historical.reason,
        "fresh": fresh,
        "expires_at": aggregate.expires_at.isoformat(),
        "evidence_level": "STATIC_PRIOR",
        "binding": False,
        "qualification_evidence": False,
        "activation_evidence": False,
    }


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


@offer_app.command("list")
def offer_list(
    capability: str | None = typer.Option(None, "--capability"),
    provider_id: str | None = typer.Option(None, "--provider-id"),
    include_revoked: bool = typer.Option(False, "--include-revoked"),
    limit: int = typer.Option(100, "--limit", min=1, max=1_000),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """List immutable signed offers without exposing action data."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        offers = router.store.list_capability_offers(
            capability=capability,
            provider_id=provider_id,
            include_revoked=include_revoked,
            limit=limit,
        )
        now = datetime.now(UTC)
        values = [
            {
                "offer_id": item.offer_id,
                "provider_id": item.provider_id,
                "capability": item.capability,
                "executor_id": item.executor_id,
                "currency": item.settlement_currency,
                "valid_until": item.valid_until.isoformat(),
                "status": (
                    "expired"
                    if not item.valid_at(now)
                    else (router.store.capability_offer_status(item.offer_id) or {}).get(
                        "status", "active"
                    )
                ),
                "evidence_level": "PUBLISHED_OFFER",
            }
            for item in offers
        ]
        _economic_emit(
            {"offers": values},
            json_output=json_output,
            title="Capability offers",
            fields=[
                (
                    str(item["offer_id"]),
                    f"{item['capability']} via {item['provider_id']} "
                    f"({item['status']}, expires {item['valid_until']})",
                )
                for item in values
            ]
            or [("offers", "none")],
        )
    except (AEEPError, ValueError, OSError) as exc:
        _economic_fail(exc, json_output=json_output)
    finally:
        if router is not None:
            _run(router.close())


@offer_app.command("show")
def offer_show(
    offer_id: str = typer.Argument(...),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show one offer and its local lifecycle state."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        offer = router.store.get_capability_offer(offer_id, include_revoked=True)
        if offer is None:
            raise ConfigurationError("capability offer was not found")
        status = router.store.capability_offer_status(offer_id) or {"status": "active"}
        if not offer.valid_at(datetime.now(UTC)) and status["status"] == "active":
            status = {**status, "status": "expired"}
        value = {
            "offer": offer.model_dump(mode="json"),
            "status": status,
            "evidence_level": "PUBLISHED_OFFER",
        }
        fixed_attempt_fee = (
            f"{offer.fixed_attempt_fee.currency} {offer.fixed_attempt_fee.amount}"
            if offer.fixed_attempt_fee is not None
            else None
        )
        _economic_emit(
            value,
            json_output=json_output,
            title=f"Capability offer {offer.offer_id}",
            fields=[
                ("provider", offer.provider_id),
                ("capability", offer.capability),
                ("executor", offer.executor_id),
                ("fingerprint", offer.executor_fingerprint),
                ("currency", offer.settlement_currency),
                ("billing trigger", offer.billing_trigger.value),
                ("failure policy", offer.failure_charge_policy.value),
                ("retry policy", offer.retry_charge_policy.value),
                ("fixed attempt fee", fixed_attempt_fee),
                ("status", status["status"]),
                ("expires", offer.valid_until.isoformat()),
                ("evidence", "PUBLISHED_OFFER"),
            ],
        )
    except (AEEPError, ValueError, OSError) as exc:
        _economic_fail(exc, json_output=json_output)
    finally:
        if router is not None:
            _run(router.close())


@offer_app.command("import")
def offer_import(
    path: Path = typer.Argument(..., exists=True, dir_okay=False),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Verify and import an immutable offer from a local JSON or YAML file."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        offer = CapabilityOffer.model_validate(_read_data(f"@{path}", default={}))
        result = _verify_offer(router, offer)
        if not result["ok"]:
            reason = (
                result["signature_reason"]
                if not result["signature_valid"]
                else "offer is expired or revoked"
            )
            raise ConfigurationError(
                f"offer verification failed: {reason}"
            )
        verifier = _trust_verifier(router)
        trusted_key = verifier.store.get(offer.provider_id, offer.signature.key_id)
        if trusted_key is None:  # pragma: no cover - successful verification requires it
            raise ConfigurationError("verified provider key disappeared")
        router.store.save_provider_signing_key(trusted_key)
        router.store.save_capability_offer(offer)
        _economic_emit(
            result,
            json_output=json_output,
            title=f"Imported capability offer {offer.offer_id}",
            fields=[
                ("provider", offer.provider_id),
                ("capability", offer.capability),
                ("signature", result["signature_reason"]),
                ("expires", result["expires_at"]),
                ("evidence", result["evidence_level"]),
            ],
        )
    except (AEEPError, ValueError, OSError) as exc:
        _economic_fail(exc, json_output=json_output)
    finally:
        if router is not None:
            _run(router.close())


@offer_app.command("verify")
def offer_verify(
    offer_id: str = typer.Argument(...),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Verify an offer against the operator trust store and current lifecycle."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        offer = router.store.get_capability_offer(offer_id, include_revoked=True)
        if offer is None:
            raise ConfigurationError("capability offer was not found")
        result = _verify_offer(router, offer)
        _economic_emit(
            result,
            json_output=json_output,
            title=f"Offer verification {offer_id}",
            fields=[
                ("valid", result["ok"]),
                ("signature", result["signature_reason"]),
                ("active", result["active"]),
                ("expires", result["expires_at"]),
                ("evidence", result["evidence_level"]),
            ],
        )
        if not result["ok"]:
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except (AEEPError, ValueError, OSError) as exc:
        _economic_fail(exc, json_output=json_output)
    finally:
        if router is not None:
            _run(router.close())


@economic_app.command("quote-show")
def economic_quote_show(
    quote_id: str = typer.Argument(...),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show a bounded quote without exposing its source action payload."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        quote_value = router.store.get_bounded_quote(quote_id)
        if quote_value is None:
            raise ConfigurationError("bounded quote was not found")
        expected = quote_value.expected_amount
        maximum = quote_value.maximum_amount
        _economic_emit(
            quote_value,
            json_output=json_output,
            title=f"Bounded quote {quote_value.quote_id}",
            fields=[
                ("provider", quote_value.provider_id),
                ("capability", quote_value.capability),
                ("executor", quote_value.executor_id),
                (
                    "expected",
                    f"{expected.currency} {expected.amount}" if expected is not None else None,
                ),
                ("maximum", f"{maximum.currency} {maximum.amount}"),
                ("expires", quote_value.expires_at.isoformat()),
                ("evidence", quote_value.evidence_level.value),
            ],
        )
    except (AEEPError, ValueError, OSError) as exc:
        _economic_fail(exc, json_output=json_output)
    finally:
        if router is not None:
            _run(router.close())


@economic_app.command("quote-verify")
def economic_quote_verify(
    quote_id: str = typer.Argument(...),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Verify signature, request binding, expiry, and local nonce state."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        quote_value = router.store.get_bounded_quote(quote_id)
        if quote_value is None:
            raise ConfigurationError("bounded quote was not found")
        result = _verify_quote(router, quote_value)
        _economic_emit(
            result,
            json_output=json_output,
            title=f"Quote verification {quote_id}",
            fields=[
                ("valid", result["ok"]),
                ("signature", result["signature_reason"]),
                ("binding", result["binding_reason"]),
                ("nonce already used", result["nonce_used"]),
                ("expires", result["expires_at"]),
                ("evidence", result["evidence_level"]),
            ],
        )
        if not result["ok"]:
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except (AEEPError, ValueError, OSError) as exc:
        _economic_fail(exc, json_output=json_output)
    finally:
        if router is not None:
            _run(router.close())


def _prepared_request(
    *,
    capability: str,
    request_document: str | None,
    input_value: str,
    policy: str,
    constraints: str | None,
    context: str | None,
    max_cost_usd: float | None,
    no_network: bool,
    require_local: bool,
    executor_id: str | None,
    max_side_effect: SideEffect | None,
) -> ActionRequest:
    if request_document is not None:
        try:
            request = ActionRequest.model_validate(_read_data(request_document, default={}))
        except (ValueError, typer.BadParameter) as exc:
            raise typer.BadParameter("--request must contain a valid ActionRequest") from exc
        if request.capability != capability:
            raise typer.BadParameter("--request capability does not match the command argument")
        return request
    return _request(
        capability=capability,
        input_value=input_value,
        policy=policy,
        constraints_value=constraints,
        context_value=context,
        max_cost_usd=max_cost_usd,
        max_latency_ms=None,
        max_context_tokens=None,
        max_peak_memory_mb=None,
        no_network=no_network,
        require_local=require_local,
        executor_id=executor_id,
        max_side_effect=max_side_effect,
    )


@economic_app.command("prepare")
def economic_prepare(
    capability: str = typer.Argument(...),
    request_document: str | None = typer.Option(
        None,
        "--request",
        help="Full ActionRequest JSON/YAML or @file; replaces other action options.",
    ),
    input_value: str = typer.Option("{}", "--input", "-i", help="JSON, @file, or -."),
    policy: str = typer.Option("balanced", "--policy", "-p"),
    constraints: str | None = typer.Option(None, "--constraints"),
    context: str | None = typer.Option(None, "--context"),
    max_cost_usd: float | None = typer.Option(None, "--max-cost-usd", min=0),
    no_network: bool = typer.Option(False, "--no-network"),
    require_local: bool = typer.Option(False, "--require-local"),
    executor_id: str | None = typer.Option(None, "--executor-id"),
    max_side_effect: SideEffect | None = typer.Option(None, "--max-side-effect"),
    quote_policy: QuoteFailurePolicy | None = typer.Option(None, "--quote-policy"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Prepare, quote when required, and persist one immutable route decision."""

    router: Router | None = None
    try:
        request = _prepared_request(
            capability=capability,
            request_document=request_document,
            input_value=input_value,
            policy=policy,
            constraints=constraints,
            context=context,
            max_cost_usd=max_cost_usd,
            no_network=no_network,
            require_local=require_local,
            executor_id=executor_id,
            max_side_effect=max_side_effect,
        )
        router = Router.from_manifest(manifest)
        prepared = _run(
            _await_and_close(
                router,
                router.prepare_route(request, quote_policy=quote_policy),
            )
        )
        router = None
        selected = next(
            (
                item
                for item in prepared.candidate_rankings
                if item.executor_id == prepared.selected_executor_id
            ),
            None,
        )
        maximum = prepared.maximum_cash_authorization
        prepared_value = {
            **prepared.model_dump(mode="json"),
            "feasible": prepared.feasible,
        }
        _economic_emit(
            prepared_value,
            json_output=json_output,
            title=f"Prepared route {prepared.prepared_id}",
            fields=[
                ("feasible", prepared.feasible),
                ("executor", prepared.selected_executor_id),
                (
                    "expected",
                    (
                        f"{selected.expected_amount.currency} "
                        f"{selected.expected_amount.amount}"
                        if selected is not None and selected.expected_amount is not None
                        else None
                    ),
                ),
                (
                    "maximum",
                    f"{maximum.currency} {maximum.amount}" if maximum is not None else None,
                ),
                ("quote", prepared.selected_quote_id),
                ("expires", prepared.expires_at.isoformat()),
                (
                    "rejected",
                    [
                        f"{item.executor_id}: {', '.join(item.reasons)}"
                        for item in prepared.rejected_candidates
                    ]
                    or ["none"],
                ),
            ],
        )
        if not prepared.feasible:
            raise typer.Exit(code=3)
    except typer.Exit:
        raise
    except (AEEPError, ValueError, OSError) as exc:
        _economic_fail(exc, json_output=json_output)
    finally:
        if router is not None:
            _run(router.close())


@economic_app.command("quote-request")
def economic_quote_request(
    capability: str = typer.Argument(...),
    request_document: str | None = typer.Option(
        None,
        "--request",
        help="Full ActionRequest JSON/YAML or @file; replaces other action options.",
    ),
    input_value: str = typer.Option("{}", "--input", "-i", help="JSON, @file, or -."),
    policy: str = typer.Option("balanced", "--policy", "-p"),
    constraints: str | None = typer.Option(None, "--constraints"),
    context: str | None = typer.Option(None, "--context"),
    max_cost_usd: float | None = typer.Option(None, "--max-cost-usd", min=0),
    no_network: bool = typer.Option(False, "--no-network"),
    require_local: bool = typer.Option(False, "--require-local"),
    executor_id: str | None = typer.Option(None, "--executor-id"),
    max_side_effect: SideEffect | None = typer.Option(None, "--max-side-effect"),
    quote_policy: QuoteFailurePolicy | None = typer.Option(None, "--quote-policy"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Request bounded quotes through prepared routing's qualified top-K shortlist."""

    router: Router | None = None
    try:
        request = _prepared_request(
            capability=capability,
            request_document=request_document,
            input_value=input_value,
            policy=policy,
            constraints=constraints,
            context=context,
            max_cost_usd=max_cost_usd,
            no_network=no_network,
            require_local=require_local,
            executor_id=executor_id,
            max_side_effect=max_side_effect,
        )
        active_router = Router.from_manifest(manifest)
        router = active_router

        async def prepare_and_close() -> tuple[Any, list[BoundedQuote]]:
            try:
                prepared = await active_router.prepare_route(
                    request, quote_policy=quote_policy
                )
                quotes = [
                    quote
                    for quote_id in prepared.quote_ids
                    if (quote := active_router.store.get_bounded_quote(quote_id)) is not None
                ]
                return prepared, quotes
            finally:
                await active_router.close()

        prepared, quotes = _run(prepare_and_close())
        router = None
        value = {
            "prepared_id": prepared.prepared_id,
            "feasible": prepared.feasible,
            "quotes": [item.model_dump(mode="json") for item in quotes],
            "quote_failures": [
                item.model_dump(mode="json") for item in prepared.quote_failures
            ],
            "rejected_candidates": [
                item.model_dump(mode="json") for item in prepared.rejected_candidates
            ],
        }
        _economic_emit(
            value,
            json_output=json_output,
            title=f"Quote request for {capability}",
            fields=[
                ("prepared decision", prepared.prepared_id),
                ("feasible", prepared.feasible),
                ("quotes", [item.quote_id for item in quotes] or ["none"]),
                (
                    "failures",
                    [
                        f"{item.executor_id}: {item.code} {item.reason}"
                        for item in prepared.quote_failures
                    ]
                    or ["none"],
                ),
            ],
        )
        if not prepared.feasible:
            raise typer.Exit(code=3)
    except typer.Exit:
        raise
    except (AEEPError, ValueError, OSError) as exc:
        _economic_fail(exc, json_output=json_output)
    finally:
        if router is not None:
            _run(router.close())


@economic_app.command("prepared-cancel")
def economic_prepared_cancel(
    prepared_id: str = typer.Argument(...),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Cancel before invocation, releasing any existing reservation."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        prepared = _run(_await_and_close(router, router.cancel_prepared(prepared_id)))
        router = None
        _economic_emit(
            prepared,
            json_output=json_output,
            title=f"Cancelled prepared route {prepared_id}",
            fields=[("state", prepared.state.value), ("executor", prepared.selected_executor_id)],
        )
    except RuntimeError:
        _economic_fail(
            ConfigurationError(
                "prepared cancellation did not complete; inspect the decision before retrying"
            ),
            json_output=json_output,
        )
    except (AEEPError, ValueError, OSError) as exc:
        _economic_fail(exc, json_output=json_output)
    finally:
        if router is not None:
            _run(router.close())


@app.command("run-prepared")
def run_prepared(
    prepared_id: str = typer.Argument(...),
    request_document: str = typer.Option(
        ...,
        "--request",
        help=(
            "Original ActionRequest JSON/YAML or @file; action_id may be omitted but cannot "
            "conflict. Input stays local and is not persisted by prepared routing."
        ),
    ),
    approve: SideEffect = typer.Option(SideEffect.READ, "--approve"),
    approve_payment: bool = typer.Option(False, "--approve-payment"),
    human_approved: bool = typer.Option(False, "--human-approved"),
    allow_unsafe_executor: bool = typer.Option(False, "--allow-unsafe-executor"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Execute one immutable prepared route after rechecking its original action."""

    router: Router | None = None
    try:
        active_router = Router.from_manifest(manifest)
        router = active_router
        prepared = active_router.get_prepared_decision(prepared_id)
        try:
            request_value = _read_data(request_document, default={})
            if not isinstance(request_value, dict):
                raise ValueError("ActionRequest document must be an object")
            supplied_action_id = request_value.get("action_id")
            if supplied_action_id is not None and supplied_action_id != prepared.action_id:
                raise ConfigurationError(
                    "resupplied ActionRequest action_id does not match the prepared decision"
                )
            request = ActionRequest.model_validate(
                {**request_value, "action_id": prepared.action_id}
            )
        except ConfigurationError:
            raise
        except (ValueError, typer.BadParameter) as exc:
            raise typer.BadParameter("--request must contain a valid ActionRequest") from exc

        async def execute_and_collect() -> tuple[
            ExecutionOutcome,
            PreparedRouteDecision,
            list[SettlementReceipt],
        ]:
            try:
                outcome = await active_router.execute_prepared(
                    prepared_id,
                    request=request,
                    approved_side_effect=approve,
                    payment_approved=approve_payment,
                    human_approved=human_approved,
                    allow_unsafe_executor=allow_unsafe_executor,
                )
                final_prepared = active_router.get_prepared_decision(prepared_id)
                settlements = active_router.store.list_settlement_receipts(
                    prepared_id=prepared_id
                )
                return outcome, final_prepared, settlements
            finally:
                await active_router.close()

        outcome, final_prepared, settlements = _run(execute_and_collect())
        router = None
        selected = next(
            (
                item
                for item in prepared.candidate_rankings
                if item.executor_id == prepared.selected_executor_id
            ),
            None,
        )
        maximum = prepared.maximum_cash_authorization
        if selected is None or maximum is None:
            raise ConfigurationError("executed prepared route is missing economic evidence")
        currency = maximum.currency
        receipt_values = []
        for receipt in outcome.receipts:
            actual_cash = receipt.accounting.cash.actual_cash_cost(currency)
            receipt_values.append(
                {
                    "receipt_id": receipt.receipt_id,
                    "executor_id": receipt.executor_id,
                    "status": receipt.status.value,
                    "task_valid": receipt.task_valid,
                    "quality_score": receipt.quality_score,
                    "started_at": receipt.started_at.isoformat(),
                    "ended_at": receipt.ended_at.isoformat(),
                    "actual_resources": receipt.actual_resources.model_dump(
                        mode="json", exclude={"monetary_usd"}
                    ),
                    "actual_cash": (
                        {"amount": str(actual_cash), "currency": currency}
                        if actual_cash is not None
                        else None
                    ),
                    "cash_evidence_status": receipt.accounting.cash.status.value,
                }
            )
        settlement_values = [
            {
                "settlement_id": item.settlement_id,
                "status": item.status.value,
                "reserved_amount": item.reserved_amount.model_dump(mode="json"),
                "captured_amount": item.captured_amount.model_dump(mode="json"),
                "released_amount": item.released_amount.model_dump(mode="json"),
                "evidence_level": item.evidence_level.value,
                "settled_at": item.settled_at.isoformat(),
            }
            for item in settlements
        ]
        evidence = (
            [item.evidence_level.value for item in settlements]
            or [
                str(
                    receipt.metadata.get(
                        "cash_evidence_level", selected.evidence_level.value
                    )
                )
                for receipt in outcome.receipts
            ]
            or [selected.evidence_level.value]
        )
        captured = settlements[0].captured_amount if len(settlements) == 1 else None
        released = settlements[0].released_amount if len(settlements) == 1 else None
        value = {
            "ok": outcome.ok,
            "status": outcome.status.value,
            "prepared_id": prepared_id,
            "prepared_state": final_prepared.state.value,
            "executor_id": prepared.selected_executor_id,
            "expected_amount": (
                selected.expected_amount.model_dump(mode="json")
                if selected.expected_amount is not None
                else None
            ),
            "maximum_amount": maximum.model_dump(mode="json"),
            "receipts": receipt_values,
            "settlements": settlement_values,
            "economic_evidence": evidence,
            "output_omitted": True,
        }
        _economic_emit(
            value,
            json_output=json_output,
            title=f"Prepared execution {prepared_id}",
            fields=[
                ("status", outcome.status.value),
                ("prepared state", final_prepared.state.value),
                ("executor", prepared.selected_executor_id),
                (
                    "expected",
                    (
                        f"{selected.expected_amount.currency} "
                        f"{selected.expected_amount.amount}"
                        if selected.expected_amount is not None
                        else None
                    ),
                ),
                (
                    "maximum",
                    f"{maximum.currency} {maximum.amount}",
                ),
                (
                    "captured",
                    f"{captured.currency} {captured.amount}" if captured is not None else None,
                ),
                (
                    "released",
                    f"{released.currency} {released.amount}" if released is not None else None,
                ),
                ("evidence", evidence),
                ("receipt", [item.receipt_id for item in outcome.receipts]),
                ("result payload", "omitted"),
            ],
        )
        if not outcome.ok:
            raise typer.Exit(code=4)
    except typer.Exit:
        raise
    except RuntimeError:
        _economic_fail(
            ConfigurationError(
                "prepared execution did not complete; inspect the prepared decision and run "
                "economic recovery"
            ),
            json_output=json_output,
        )
    except (AEEPError, ValueError, OSError) as exc:
        _economic_fail(exc, json_output=json_output)
    finally:
        if router is not None:
            _run(router.close())


@settlement_app.command("list")
def settlement_list(
    prepared_id: str | None = typer.Option(None, "--prepared-id"),
    limit: int = typer.Option(100, "--limit", min=1, max=1_000),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """List settlement receipts with captured and released amounts."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        receipts = router.store.list_settlement_receipts(
            prepared_id=prepared_id,
            limit=limit,
        )
        values = [
            item.model_dump(mode="json", exclude={"external_reference"})
            for item in receipts
        ]
        _economic_emit(
            {"settlements": values},
            json_output=json_output,
            title="Settlement receipts",
            fields=[
                (
                    item.settlement_id,
                    f"{item.status.value}: captured {item.captured_amount.currency} "
                    f"{item.captured_amount.amount}; released "
                    f"{item.released_amount.amount}; evidence {item.evidence_level.value}",
                )
                for item in receipts
            ]
            or [("settlements", "none")],
        )
    except (AEEPError, ValueError, OSError) as exc:
        _economic_fail(exc, json_output=json_output)
    finally:
        if router is not None:
            _run(router.close())


@settlement_app.command("show")
def settlement_show(
    settlement_id: str = typer.Argument(...),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show one immutable settlement and reconciliation history."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        receipt = router.store.get_settlement_receipt(settlement_id)
        if receipt is None:
            raise ConfigurationError("settlement receipt was not found")
        reconciliations = router.store.list_billing_reconciliations(
            settlement_id=settlement_id
        )
        value = {
            "settlement": receipt.model_dump(mode="json", exclude={"external_reference"}),
            "reconciliations": [
                item.model_dump(
                    mode="json",
                    exclude={
                        "invoice_reference",
                        "billing_record_reference",
                        "evidence_digest",
                    },
                )
                for item in reconciliations
            ],
        }
        _economic_emit(
            value,
            json_output=json_output,
            title=f"Settlement {settlement_id}",
            fields=[
                (
                    "reserved",
                    f"{receipt.reserved_amount.currency} {receipt.reserved_amount.amount}",
                ),
                ("captured", receipt.captured_amount.amount),
                ("released", receipt.released_amount.amount),
                ("status", receipt.status.value),
                ("evidence", receipt.evidence_level.value),
                (
                    "reconciliation",
                    [item.status.value for item in reconciliations] or ["none"],
                ),
            ],
        )
    except (AEEPError, ValueError, OSError) as exc:
        _economic_fail(exc, json_output=json_output)
    finally:
        if router is not None:
            _run(router.close())


@settlement_app.command("reconcile")
def settlement_reconcile(
    settlement_id: str = typer.Argument(...),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Ask the configured payment rail to reconcile one stored settlement."""

    router: Router | None = None
    try:
        active_router = Router.from_manifest(manifest)
        router = active_router
        if active_router.store.get_settlement_receipt(settlement_id) is None:
            raise ConfigurationError("settlement receipt was not found")
        if active_router.budget_manager is None:
            raise ConfigurationError("billing reconciliation requires a configured payment adapter")
        reconciliation = _run(
            _await_and_close(
                active_router,
                active_router.budget_manager.reconcile_v2(
                    settlement_id,
                    idempotency_key=f"cli-reconcile:{settlement_id}",
                ),
            )
        )
        router = None
        evidence_level = reconciliation.status.economic_evidence_level.value
        value = {
            "reconciliation": reconciliation.model_dump(
                mode="json",
                exclude={
                    "invoice_reference",
                    "billing_record_reference",
                    "evidence_digest",
                },
            ),
            "evidence_level": evidence_level,
        }
        _economic_emit(
            value,
            json_output=json_output,
            title=f"Billing reconciliation {reconciliation.reconciliation_id}",
            fields=[
                ("settlement", reconciliation.settlement_id),
                ("status", reconciliation.status.value),
                (
                    "expected",
                    f"{reconciliation.expected_amount.currency} "
                    f"{reconciliation.expected_amount.amount}",
                ),
                ("billed", reconciliation.billed_amount.amount),
                ("discrepancy", reconciliation.discrepancy.amount),
                ("evidence", evidence_level),
            ],
        )
    except RuntimeError:
        _economic_fail(
            ConfigurationError(
                "billing reconciliation did not complete; retry with the same settlement ID"
            ),
            json_output=json_output,
        )
    except (AEEPError, ValueError, OSError) as exc:
        _economic_fail(exc, json_output=json_output)
    finally:
        if router is not None:
            _run(router.close())


@economic_app.command("prepared-show")
def economic_prepared_show(
    prepared_id: str = typer.Argument(...),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show a sanitized prepared route decision and its transitions."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        prepared = router.get_prepared_decision(prepared_id)
        transitions = router.store.list_prepared_transitions(prepared_id)
        value = {
            "prepared": prepared.model_dump(mode="json"),
            "transitions": [item.model_dump(mode="json") for item in transitions],
        }
        expected = next(
            (
                item.expected_amount
                for item in prepared.candidate_rankings
                if item.executor_id == prepared.selected_executor_id
            ),
            None,
        )
        maximum = prepared.maximum_cash_authorization
        rejections = [
            f"{item.executor_id}: {', '.join(item.reasons)}"
            for item in prepared.rejected_candidates
        ]
        failures = [
            f"{item.executor_id}: {item.code} {item.reason}"
            for item in prepared.quote_failures
        ]
        _economic_emit(
            value,
            json_output=json_output,
            title=f"Prepared route {prepared.prepared_id}",
            fields=[
                ("state", prepared.state.value),
                ("feasible", prepared.feasible),
                ("executor", prepared.selected_executor_id),
                (
                    "expected",
                    f"{expected.currency} {expected.amount}" if expected is not None else None,
                ),
                (
                    "maximum",
                    f"{maximum.currency} {maximum.amount}" if maximum is not None else None,
                ),
                ("quote", prepared.selected_quote_id),
                ("expires", prepared.expires_at.isoformat()),
                ("rejected", rejections or ["none"]),
                ("quote failures", failures or ["none"]),
            ],
        )
    except (AEEPError, ValueError, OSError) as exc:
        _economic_fail(exc, json_output=json_output)
    finally:
        if router is not None:
            _run(router.close())


@economic_app.command("doctor")
def economic_doctor(
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Report whether economic networking, trust, storage, and payment are configured."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        config = router.manifest.economic_evidence
        configured_path = Path(config.trust_store.path).expanduser()
        stored_keys = len(router.store.list_provider_signing_keys())
        trust_available = configured_path.is_file() or stored_keys > 0
        recoverable = router.store.recoverable_prepared_decisions()
        pending_refunds = router.store.pending_refund_authorizations_v2()
        pending_payment_intents = sum(
            router.store.payment_reservation_operation_intent(item.reservation_id) is not None
            for item in router.store.list_payment_reservations_v2(limit=1_000)
            if item.state
            in {
                PaymentReservationState.SETTLING,
                PaymentReservationState.INDETERMINATE,
            }
        )
        legacy_signed_records = sum(
            item.signature.canonicalization_version == "aeep-canonical-json-v1"
            for item in router.store.list_capability_offers(limit=10_000)
        ) + sum(
            item.signature.canonicalization_version == "aeep-canonical-json-v1"
            for item in router.store.list_bounded_quotes(limit=10_000)
        ) + sum(
            item.signature.canonicalization_version == "aeep-canonical-json-v1"
            for item in router.store.list_market_aggregates(limit=10_000)
        )
        checks = {
            "enabled": config.enabled,
            "live_quotes_enabled": config.live_quotes.enabled,
            "allowed_quote_hosts": list(config.network.allowed_quote_hosts),
            "trust_store_path": str(configured_path),
            "trust_available": trust_available,
            "stored_trusted_keys": stored_keys,
            "payment_adapter": config.payment.adapter,
            "settlement_currency": config.settlement_currency,
            "recoverable_prepared_decisions": len(recoverable),
            "pending_payment_operation_intents": pending_payment_intents,
            "pending_refund_authorizations": len(pending_refunds),
            "rfc8785_live_cutover_at": router.store.protocol_cutover(
                "rfc8785_live_cutover"
            ),
            "legacy_historical_only_records": legacy_signed_records,
            "remote_networking_default": "disabled" if not config.enabled else "enabled",
        }
        _economic_emit(
            checks,
            json_output=json_output,
            title="Economic evidence doctor",
            fields=[(key.replace("_", " "), value) for key, value in checks.items()],
        )
    except (AEEPError, ValueError, OSError) as exc:
        _economic_fail(exc, json_output=json_output)
    finally:
        if router is not None:
            _run(router.close())


@economic_app.command("recover")
def economic_recover(
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Resume idempotent settlement for incomplete decisions without re-executing."""

    router: Router | None = None
    try:
        active_router = Router.from_manifest(manifest)
        router = active_router

        async def recover_and_collect() -> tuple[dict[str, object], int, int]:
            try:
                report = await active_router.economic_recover()
                pending_refunds = len(
                    active_router.store.pending_refund_authorizations_v2()
                )
                pending_payment_intents = sum(
                    active_router.store.payment_reservation_operation_intent(
                        item.reservation_id
                    )
                    is not None
                    for item in active_router.store.list_payment_reservations_v2(
                        limit=1_000
                    )
                    if item.state
                    in {
                        PaymentReservationState.SETTLING,
                        PaymentReservationState.INDETERMINATE,
                    }
                )
                return report, pending_refunds, pending_payment_intents
            finally:
                await active_router.close()

        report, pending_refunds, pending_payment_intents = _run(recover_and_collect())
        router = None
        raw_items = report.get("items", [])
        items = [
            {
                "prepared_id": str(item.get("prepared_id", "")),
                "result": str(item.get("result", "unresolved")),
            }
            for item in raw_items
            if isinstance(item, dict)
        ]
        value = {
            "scanned": int(report.get("scanned", 0)),
            "settled": int(report.get("settled", 0)),
            "released": int(report.get("released", 0)),
            "unresolved": int(report.get("unresolved", 0)),
            "pending_payment_operation_intents": pending_payment_intents,
            "pending_refund_authorizations": pending_refunds,
            "items": items,
        }
        _economic_emit(
            value,
            json_output=json_output,
            title="Economic recovery",
            fields=[
                ("scanned", value["scanned"]),
                ("settled", value["settled"]),
                ("released", value["released"]),
                ("unresolved", value["unresolved"]),
                (
                    "pending payment operation intents",
                    value["pending_payment_operation_intents"],
                ),
                (
                    "pending refund authorizations",
                    value["pending_refund_authorizations"],
                ),
                (
                    "decisions",
                    [f"{item['prepared_id']}: {item['result']}" for item in items]
                    or ["none"],
                ),
            ],
        )
    except RuntimeError:
        _economic_fail(
            ConfigurationError("economic recovery did not complete; retry with the same store"),
            json_output=json_output,
        )
    except (AEEPError, ValueError, OSError) as exc:
        _economic_fail(exc, json_output=json_output)
    finally:
        if router is not None:
            _run(router.close())


@market_app.command("aggregate-import")
def market_aggregate_import(
    path: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=False),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Verify and import one bounded local JSON aggregate envelope."""

    from .economic import MarketAggregateImporter

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        if path.stat().st_size > 262_144:
            raise ConfigurationError("aggregate response exceeds its configured size limit")
        payload = path.read_bytes()
        verifier = _trust_verifier(router)
        aggregates = MarketAggregateImporter(
            router.store,
            verifier,
        ).import_response(payload)
        for aggregate in aggregates:
            trusted_key = verifier.store.get(
                aggregate.provider_id,
                aggregate.signature.key_id,
            )
            if trusted_key is None:  # pragma: no cover - importer verified this key
                raise ConfigurationError("verified provider key disappeared")
            router.store.save_provider_signing_key(trusted_key)
        values = [
            {
                "aggregate_id": item.aggregate_id,
                "provider_id": item.provider_id,
                "capability": item.capability,
                "executor_id": item.executor_id,
                "executor_fingerprint": item.executor_fingerprint,
                "sample_size": item.sample_size,
                "expires_at": item.expires_at.isoformat(),
                "evidence_level": "STATIC_PRIOR",
            }
            for item in aggregates
        ]
        _economic_emit(
            {
                "count": len(values),
                "aggregates": values,
                "qualification_evidence": False,
                "activation_evidence": False,
            },
            json_output=json_output,
            title="Imported market aggregates",
            fields=[
                ("count", len(values)),
                (
                    "aggregates",
                    [f"{item['aggregate_id']}: {item['capability']}" for item in values]
                    or ["none"],
                ),
                ("evidence", "STATIC_PRIOR"),
                ("qualification evidence", False),
                ("activation evidence", False),
            ],
        )
    except (AEEPError, ValueError, OSError) as exc:
        _economic_fail(exc, json_output=json_output)
    finally:
        if router is not None:
            _run(router.close())


@market_app.command("aggregate-list")
def market_aggregate_list(
    capability: str | None = typer.Option(None, "--capability"),
    limit: int = typer.Option(100, "--limit", min=1, max=1_000),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """List stored privacy-safe market priors without fetching the network."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        aggregates = router.store.list_market_aggregates(
            capability=capability,
            limit=limit,
        )
        _economic_emit(
            {
                "aggregates": [item.model_dump(mode="json") for item in aggregates],
                "evidence_level": "STATIC_PRIOR",
                "qualification_evidence": False,
                "activation_evidence": False,
            },
            json_output=json_output,
            title="Market aggregates",
            fields=[
                (
                    item.aggregate_id,
                    f"{item.capability} via {item.provider_id}; "
                    f"samples {item.sample_size}; expires {item.expires_at.isoformat()}",
                )
                for item in aggregates
            ]
            or [("aggregates", "none")],
        )
    except (AEEPError, ValueError, OSError) as exc:
        _economic_fail(exc, json_output=json_output)
    finally:
        if router is not None:
            _run(router.close())


@market_app.command("aggregate-show")
def market_aggregate_show(
    aggregate_id: str = typer.Argument(...),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show one stored market prior and its exact fingerprint binding."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        aggregate = router.store.get_market_aggregate(aggregate_id)
        if aggregate is None:
            raise ConfigurationError("market aggregate was not found")
        p50 = aggregate.actual_cost_p50
        p95 = aggregate.actual_cost_p95
        _economic_emit(
            {
                "aggregate": aggregate.model_dump(mode="json"),
                "evidence_level": "STATIC_PRIOR",
                "binding": False,
                "qualification_evidence": False,
                "activation_evidence": False,
            },
            json_output=json_output,
            title=f"Market aggregate {aggregate.aggregate_id}",
            fields=[
                ("provider", aggregate.provider_id),
                ("capability", aggregate.capability),
                ("executor", aggregate.executor_id),
                ("fingerprint", aggregate.executor_fingerprint),
                ("input bucket", aggregate.input_bucket),
                ("sample size", aggregate.sample_size),
                (
                    "actual cost p50",
                    f"{p50.currency} {p50.amount}" if p50 is not None else None,
                ),
                (
                    "actual cost p95",
                    f"{p95.currency} {p95.amount}" if p95 is not None else None,
                ),
                ("expires", aggregate.expires_at.isoformat()),
                ("evidence", "STATIC_PRIOR"),
                ("binding", False),
                ("qualification evidence", False),
                ("activation evidence", False),
            ],
        )
    except (AEEPError, ValueError, OSError) as exc:
        _economic_fail(exc, json_output=json_output)
    finally:
        if router is not None:
            _run(router.close())


@market_app.command("aggregate-verify")
def market_aggregate_verify(
    aggregate_id: str = typer.Argument(...),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Verify one aggregate's signature, key trust, and current freshness."""

    router: Router | None = None
    try:
        router = Router.from_manifest(manifest)
        aggregate = router.store.get_market_aggregate(aggregate_id)
        if aggregate is None:
            raise ConfigurationError("market aggregate was not found")
        result = _verify_market_aggregate(router, aggregate)
        _economic_emit(
            result,
            json_output=json_output,
            title=f"Market aggregate verification {aggregate.aggregate_id}",
            fields=[
                ("valid", result["ok"]),
                ("signature", result["signature_reason"]),
                ("historical signature", result["historical_signature_reason"]),
                ("fresh", result["fresh"]),
                ("expires", result["expires_at"]),
                ("evidence", result["evidence_level"]),
                ("qualification evidence", False),
                ("activation evidence", False),
            ],
        )
        if not result["ok"]:
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except (AEEPError, ValueError, OSError) as exc:
        _economic_fail(exc, json_output=json_output)
    finally:
        if router is not None:
            _run(router.close())


@market_app.command("serve")
def market_serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8787, "--port", min=1, max=65_535),
    token_env: str = typer.Option("AEEP_REFERENCE_MARKET_TOKEN", "--token-env"),
) -> None:
    """Run the deterministic local reference market/provider service."""

    token = os.getenv(token_env)
    if host not in {"127.0.0.1", "localhost", "::1"} and not token:
        raise typer.BadParameter(
            f"refusing non-loopback market binding without bearer token in {token_env}"
        )
    try:
        import uvicorn

        from .market_server import (
            ReferenceMarket,
            create_app,
            reference_executor_spec,
        )
    except ImportError as exc:
        raise typer.BadParameter(
            "market serving requires the http-server optional dependency"
        ) from exc
    advertised_host = host if host in {"127.0.0.1", "localhost", "::1"} else "127.0.0.1"
    url_host = (
        f"[{advertised_host}]"
        if ":" in advertised_host and not advertised_host.startswith("[")
        else advertised_host
    )
    executor = reference_executor_spec(
        base_url=f"http://{url_host}:{port}",
        auth_token_env=token_env if token else None,
    )
    market = ReferenceMarket(executor_spec=executor)
    uvicorn.run(
        create_app(market=market, bearer_token=token),
        host=host,
        port=port,
        log_level="info",
    )


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


@provider_app.command("validate")
def provider_validate(
    path: Path,
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Validate one strict v0.5 package without resolving artifacts or executing."""

    from .provider_package import load_provider_package

    try:
        package, _ = load_provider_package(path)
        _emit(
            {
                "ok": True,
                "package_id": package.metadata.package_id,
                "version": package.metadata.version,
                "provider_id": package.spec.provider.provider_id,
                "routes": len(package.spec.routes),
                "artifacts": len(package.spec.artifacts),
            },
            compact=compact,
        )
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)


@provider_app.command("digest")
def provider_digest(
    path: Path,
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Recompute the RFC 8785 package digest without executing provider code."""

    from .provider_package import load_provider_package, provider_package_digest

    try:
        package, _ = load_provider_package(path)
        actual = provider_package_digest(package)
        _emit(
            {
                "ok": actual == package.integrity.digest,
                "declared_digest": package.integrity.digest,
                "computed_digest": actual,
            },
            compact=compact,
        )
        if actual != package.integrity.digest:
            raise typer.Exit(code=2)
    except typer.Exit:
        raise
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)


@provider_app.command("verify")
def provider_verify(
    path: Path,
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Verify package signatures and derive local identity trust without ingesting."""

    from .artifact_store import ContentArtifactStore
    from .economic.trust import TrustStore
    from .provider_ingest import ProviderPackageIngestor
    from .provider_package import load_provider_package

    router = Router.from_manifest(manifest)
    try:
        package, _ = load_provider_package(path)
        try:
            trust = _trust_verifier(router).store
        except ConfigurationError:
            trust = TrustStore()
        verification = ProviderPackageIngestor(
            router.store,
            ContentArtifactStore(router.manifest.provider_packages.artifact_root),
            trust,
        ).verify_package(package)
        _emit(verification, compact=compact)
        if verification.integrity_status.value != "verified":
            raise typer.Exit(code=2)
    except typer.Exit:
        raise
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)
    finally:
        _run(router.close())


@provider_app.command("sign")
def provider_sign(
    path: Path,
    private_key_file: Path = typer.Option(..., "--private-key-file"),
    key_id: str = typer.Option(..., "--key-id"),
    signature_id: str | None = typer.Option(None, "--signature-id"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Sign one package using private key bytes read only from a protected file."""

    from .economic.signing import Ed25519Signer, decode_base64url
    from .provider_package import (
        load_provider_package,
        sign_provider_package,
        write_provider_package,
    )

    try:
        package, _ = load_provider_package(path)
        if os.name == "posix" and private_key_file.stat().st_mode & 0o077:
            raise ConfigurationError(
                "private key file must not be readable or writable by group/other"
            )
        encoded = private_key_file.read_bytes()
        if len(encoded) == 32:
            private_key = encoded
        else:
            text = encoded.decode("utf-8").strip()
            private_key = (
                bytes.fromhex(text)
                if len(text) == 64 and all(character in "0123456789abcdefABCDEF" for character in text)
                else decode_base64url(text)
            )
        if len(private_key) != 32:
            raise ConfigurationError("Ed25519 private key file must contain exactly 32 bytes")
        signed = sign_provider_package(
            package,
            Ed25519Signer.from_private_bytes(private_key, key_id=key_id),
            signature_id=(signature_id or key_id),
        )
        write_provider_package(signed, path)
        _emit(
            {
                "ok": True,
                "package_digest": signed.integrity.digest,
                "signature_id": signature_id or key_id,
            },
            compact=compact,
        )
    except (AEEPError, UnicodeDecodeError, ValueError, OSError) as exc:
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


@candidate_app.command("inspect")
def candidate_inspect(
    executor_id: str,
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    router = Router.from_manifest(manifest)
    try:
        _emit(router.inspect_candidate(executor_id), compact=compact)
    except (AEEPError, ValueError) as exc:
        _fail(exc, compact=compact)
    finally:
        _run(router.close())


@candidate_app.command("smoke")
def candidate_smoke(
    executor_id: str,
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    router = Router.from_manifest(manifest)
    try:
        result = _run(_await_and_close(router, router.smoke_candidate(executor_id)))
        _emit([item.model_dump(mode="json") for item in result], compact=compact)
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)


@candidate_app.command("ingest")
def candidate_ingest(
    descriptor: str = typer.Argument(
        ...,
        help="aeep-provider.yaml/directory or legacy ProviderDescriptor JSON/YAML/@file",
    ),
    source_id: str | None = typer.Option(None, "--source-id"),
    capability: str | None = typer.Option(None, "--capability"),
    offline: bool = typer.Option(False, "--offline"),
    allow_remote_artifacts: bool = typer.Option(False, "--allow-remote-artifacts"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Persist imported provider routes as inert candidates."""

    from .models import ProviderDescriptor

    router = Router.from_manifest(manifest)
    try:
        candidate_path = Path(descriptor[1:] if descriptor.startswith("@") else descriptor)
        is_package = candidate_path.is_dir() or candidate_path.name == "aeep-provider.yaml"
        if is_package:
            candidates = list(
                _run(
                    router.ingest_provider_package(
                        candidate_path,
                        source_id=source_id,
                        allow_remote_artifacts=(allow_remote_artifacts and not offline),
                    )
                )
            )
            if capability is not None:
                candidates = [item for item in candidates if item.capability == capability]
        else:
            if source_id is None:
                raise typer.BadParameter("legacy descriptor ingest requires --source-id")
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
    reuse_evidence: bool = typer.Option(False, "--reuse-evidence"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    from .qualification import QualificationCase, QualificationCondition

    parsed = _read_data(cases, default=[])
    if not isinstance(parsed, list):
        raise typer.BadParameter("cases must be a list")
    router = Router.from_manifest(manifest)
    try:
        if reuse_evidence:
            result = router.qualify_candidate_from_evidence(executor_id)
        else:
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
    finally:
        _run(router.close())


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


@candidate_app.command("refresh")
def candidate_refresh(
    executor_id: str,
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    router = Router.from_manifest(manifest)
    try:
        result = _run(_await_and_close(router, router.refresh_candidate(executor_id)))
        _emit(result, compact=compact)
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)


@evidence_app.command("list")
def evidence_list(
    route: str = typer.Option(..., "--route"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    router = Router.from_manifest(manifest)
    try:
        _emit(
            {
                "records": router.store.list_evidence_records(route),
                "acceptances": router.store.list_evidence_acceptances(route),
            },
            compact=compact,
        )
    except (AEEPError, ValueError) as exc:
        _fail(exc, compact=compact)
    finally:
        _run(router.close())


@evidence_app.command("show")
def evidence_show(
    evidence_id: str,
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    router = Router.from_manifest(manifest)
    try:
        item = router.store.get_evidence_record(evidence_id)
        if item is None:
            raise ConfigurationError(f"unknown evidence {evidence_id!r}")
        _emit(item, compact=compact)
    except (AEEPError, ValueError) as exc:
        _fail(exc, compact=compact)
    finally:
        _run(router.close())


@evidence_app.command("explain")
def evidence_explain(
    route: str,
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    router = Router.from_manifest(manifest)
    try:
        _emit(router.inspect_candidate(route), compact=compact)
    except (AEEPError, ValueError) as exc:
        _fail(exc, compact=compact)
    finally:
        _run(router.close())


@evidence_app.command("revalue")
def evidence_revalue(
    rate_card: str = typer.Option(..., "--rate-card"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """Revalue accepted benchmark usage without rewriting historical resources."""

    import gzip

    from .benchmarking import BenchmarkCampaignReport, revalue_campaign

    router = Router.from_manifest(manifest)
    try:
        snapshot = router.store.get_rate_card_snapshot(rate_card)
        if snapshot is None:
            raise ConfigurationError(f"unknown rate-card snapshot {rate_card!r}")
        reports = []
        for path in router.store.list_evidence_artifact_paths("benchmark_campaign"):
            payload = path.read_bytes()
            if payload.startswith(b"\x1f\x8b"):
                payload = gzip.decompress(payload)
            campaign = BenchmarkCampaignReport.model_validate_json(payload)
            reports.append(revalue_campaign(campaign, snapshot))
        _emit(reports, compact=compact)
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)
    finally:
        _run(router.close())


@registry_app.command("search")
def registry_search(
    query: str,
    registry: str = typer.Option("mcp", "--registry"),
    fixture: Path | None = typer.Option(None, "--fixture"),
    catalog: str | None = typer.Option(None, "--catalog"),
    token_env: str | None = typer.Option(None, "--token-env"),
    limit: int = typer.Option(20, "--limit", min=1, max=100),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    from .discovery import (
        DockerCatalogAdapter,
        FixtureRegistryAdapter,
        MCPCommunityRegistryAdapter,
        PackageRegistryAdapter,
        RegistryQuery,
        SmitheryRegistryAdapter,
    )

    router = Router.from_manifest(manifest)
    try:
        adapter: PackageRegistryAdapter
        if registry == "fixture":
            if fixture is None:
                raise typer.BadParameter("fixture registry requires --fixture")
            adapter = FixtureRegistryAdapter(fixture)
        elif registry == "mcp":
            adapter = MCPCommunityRegistryAdapter()
        elif registry == "docker":
            if catalog is None:
                raise typer.BadParameter("Docker registry requires --catalog")
            adapter = DockerCatalogAdapter(catalog)
        elif registry == "smithery":
            if token_env is None:
                raise typer.BadParameter("Smithery registry requires --token-env")
            adapter = SmitheryRegistryAdapter(token_env=token_env)
        else:
            raise typer.BadParameter("registry must be fixture, mcp, docker, or smithery")
        results = _run(adapter.search(RegistryQuery(query=query, limit=limit)))
        for item in results:
            router.store.save_registry_candidate(item)
        _emit(results, compact=compact)
    except (AEEPError, ValueError, OSError) as exc:
        _fail(exc, compact=compact)
    finally:
        _run(router.close())


@registry_app.command("inspect")
def registry_inspect(
    candidate_id: str,
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    router = Router.from_manifest(manifest)
    try:
        candidate = router.store.get_registry_candidate(candidate_id)
        if candidate is None:
            raise ConfigurationError(f"unknown registry result {candidate_id!r}")
        _emit(candidate, compact=compact)
    except (AEEPError, ValueError) as exc:
        _fail(exc, compact=compact)
    finally:
        _run(router.close())


@workflow_app.command("run")
def workflow_run(
    request: str = typer.Argument(..., help="Workflow JSON/YAML or @file"),
    manifest: Path | None = typer.Option(None, "--manifest", "-m"),
    approve: SideEffect = typer.Option(SideEffect.READ, "--approve"),
    approve_payment: bool = typer.Option(False, "--approve-payment"),
    human_approved: bool = typer.Option(False, "--human-approved"),
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
                    payment_approved=approve_payment,
                    human_approved=human_approved,
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
    approve_payment: bool = typer.Option(False, "--approve-payment"),
    human_approved: bool = typer.Option(False, "--human-approved"),
    approve_unsafe_executor: bool = typer.Option(False, "--approve-unsafe-executor"),
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
                    payment_approved=approve_payment,
                    human_approved=human_approved,
                    allow_unsafe_executor=approve_unsafe_executor,
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
    """Evaluate release proof thresholds without filling missing economic evidence."""

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
        if not result.passed:
            raise typer.Exit(code=4)
    except typer.Exit:
        raise
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
