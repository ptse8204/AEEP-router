"""Small provider SDK and importers for existing Python, CLI, MCP, and OpenAPI tools."""

from __future__ import annotations

import hashlib
import inspect
import json
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urljoin, urlparse

import yaml
from pydantic import BaseModel

from .economic.canonical import canonical_payload
from .economic.signing import Signer
from .errors import ConfigurationError
from .executors.network import is_local_hostname, validate_http_url
from .mcp.client import MCPHTTPClient, MCPStdioClient
from .models import (
    BoundedQuote,
    CapabilityDefinition,
    CapabilityOffer,
    ExecutorKind,
    ExecutorSpec,
    Locality,
    Manifest,
    ProviderDescriptor,
    QuoteRequestV2,
    ResourceVector,
    RouteEstimate,
    SideEffect,
    TrustLevel,
    UsageStatement,
)
from .provider_package import (
    ArtifactReference,
    EvidenceReference,
    ProviderCompatibility,
    ProviderIdentity,
    ProviderPackage,
    ProviderPackageIntegrity,
    ProviderPackageMetadata,
    ProviderPackageSpec,
    PublishedExecutor,
    PublishedProviderRoute,
    RouteFingerprint,
    SmokeTestDefinition,
    portable_route_fingerprint,
    provider_package_digest,
)
from .templates import render

QuoteHandlerResult = BoundedQuote | Mapping[str, Any]
QuoteHandler = Callable[
    [QuoteRequestV2],
    QuoteHandlerResult | Awaitable[QuoteHandlerResult],
]
UsageHandlerResult = UsageStatement | Mapping[str, Any]
UsageHandler = Callable[
    [QuoteRequestV2, BoundedQuote, str, str],
    UsageHandlerResult | Awaitable[UsageHandlerResult],
]

_HandlerResult = TypeVar("_HandlerResult", QuoteHandlerResult, UsageHandlerResult)
_EconomicRecord = TypeVar("_EconomicRecord", CapabilityOffer, BoundedQuote, UsageStatement)
_RouteKey = tuple[str, str, str]


def build_provider_package(
    *,
    package_id: str,
    version: str,
    issued_at: datetime,
    provider: ProviderIdentity,
    compatibility: ProviderCompatibility,
    capabilities: Sequence[CapabilityDefinition],
    executors: Sequence[ExecutorSpec],
    artifacts: Sequence[ArtifactReference] = (),
    evidence: Sequence[EvidenceReference] = (),
    smoke_tests: Sequence[SmokeTestDefinition] = (),
    artifact_bindings: Mapping[str, Sequence[str]] | None = None,
) -> ProviderPackage:
    """Build an unsigned v0.6 package from operator-reviewed route records."""

    definitions = {item.capability: item for item in capabilities}
    routes: list[PublishedProviderRoute] = []
    for spec in executors:
        definition = definitions.get(spec.capability)
        if definition is None:
            raise ConfigurationError(
                f"executor {spec.id!r} has no exact capability definition"
            )
        published = PublishedProviderRoute(
            route_id=spec.id,
            capability=spec.capability,
            input_schema=definition.input_schema,
            output_schema=definition.output_schema,
            executor=PublishedExecutor(
                kind=spec.kind,
                description=spec.description,
                side_effect=spec.side_effect,
                locality=spec.locality,
                requires_network=spec.requires_network,
                data_residency=tuple(spec.data_residency),
                idempotent=spec.idempotent,
                resource_pool=spec.resource_pool,
                validators=tuple(spec.validators),
                config=spec.config,
            ),
            declared_fingerprint=RouteFingerprint(value="sha256:" + "0" * 64),
            artifact_bindings=tuple((artifact_bindings or {}).get(spec.id, ())),
            static_estimate=spec.estimate,
            tags=tuple(spec.tags),
        )
        routes.append(
            published.model_copy(
                update={
                    "declared_fingerprint": RouteFingerprint(
                        value=portable_route_fingerprint(published, provider.provider_id)
                    )
                }
            )
        )
    package = ProviderPackage(
        metadata=ProviderPackageMetadata(
            package_id=package_id,
            version=version,
            issued_at=issued_at,
        ),
        spec=ProviderPackageSpec(
            provider=provider,
            compatibility=compatibility,
            capabilities=tuple(capabilities),
            routes=tuple(routes),
            artifacts=tuple(artifacts),
            evidence=tuple(evidence),
            smoke_tests=tuple(smoke_tests),
        ),
        integrity=ProviderPackageIntegrity(digest="sha256:" + "0" * 64),
    )
    return package.model_copy(
        update={"integrity": ProviderPackageIntegrity(digest=provider_package_digest(package))}
    )


def export_evidence_artifact(record: BaseModel) -> tuple[bytes, str]:
    """Serialize one validated report and return its content-addressed digest."""

    payload = record.model_dump_json(indent=2).encode("utf-8") + b"\n"
    return payload, f"sha256:{hashlib.sha256(payload).hexdigest()}"


async def _handler_result(
    value: _HandlerResult | Awaitable[_HandlerResult],
) -> _HandlerResult:
    return await value if inspect.isawaitable(value) else value


class EconomicProvider:
    """Small provider-side helper for signed AEEP 0.5 economic evidence."""

    def __init__(self, provider_id: str, signer: Signer) -> None:
        if not provider_id:
            raise ConfigurationError("provider_id must not be empty")
        self.provider_id = provider_id
        self.signer = signer
        self._placeholder_signature = signer.sign(b"")
        self._offers: dict[str, CapabilityOffer] = {}
        self._quote_handlers: dict[_RouteKey, QuoteHandler] = {}
        self._usage_handlers: dict[_RouteKey, UsageHandler] = {}
        self._quote_requests: dict[str, QuoteRequestV2] = {}
        self._quote_ids_by_request: dict[str, str] = {}
        self._quotes: dict[str, BoundedQuote] = {}
        self._usage_ids_by_attempt: dict[tuple[str, str, str], str] = {}
        self._usage_statements: dict[str, UsageStatement] = {}

    @staticmethod
    def _route_key(value: CapabilityOffer | QuoteRequestV2 | BoundedQuote) -> _RouteKey:
        return (value.capability, value.executor_id, value.executor_fingerprint)

    def _sign_mapping(
        self,
        model: type[_EconomicRecord],
        value: Mapping[str, Any],
    ) -> _EconomicRecord:
        payload = dict(value)
        if payload.get("signature") is not None:
            raise ConfigurationError("unsigned economic record must omit signature")
        payload.pop("signature", None)
        payload.setdefault("provider_id", self.provider_id)
        candidate = model.model_validate(
            {**payload, "signature": self._placeholder_signature}
        )
        if candidate.provider_id != self.provider_id:
            raise ConfigurationError("economic record provider does not match provider SDK")
        return candidate.model_copy(
            update={"signature": self.signer.sign(canonical_payload(candidate))}
        )

    def _require_own_signature(
        self,
        value: CapabilityOffer | BoundedQuote | UsageStatement,
    ) -> None:
        if value.provider_id != self.provider_id:
            raise ConfigurationError("economic record provider does not match provider SDK")
        if self.signer.sign(canonical_payload(value)) != value.signature:
            raise ConfigurationError("economic record is not signed by the configured signer")

    def sign_offer(self, value: Mapping[str, Any]) -> CapabilityOffer:
        """Validate and sign an unsigned capability-offer mapping."""

        return self._sign_mapping(CapabilityOffer, value)

    def sign_quote(self, value: Mapping[str, Any]) -> BoundedQuote:
        """Validate and sign an unsigned bounded-quote mapping."""

        return self._sign_mapping(BoundedQuote, value)

    def sign_usage(self, value: Mapping[str, Any]) -> UsageStatement:
        """Validate and sign an unsigned provider-usage mapping."""

        return self._sign_mapping(UsageStatement, value)

    def register_offer(
        self,
        value: CapabilityOffer | Mapping[str, Any],
    ) -> CapabilityOffer:
        """Register one signed offer idempotently; altered ID reuse fails closed."""

        offer = (
            value
            if isinstance(value, CapabilityOffer)
            else CapabilityOffer.model_validate(value)
            if value.get("signature") is not None
            else self.sign_offer(value)
        )
        self._require_own_signature(offer)
        previous = self._offers.get(offer.offer_id)
        if previous is not None:
            if previous != offer:
                raise ConfigurationError("offer ID is already registered with different content")
            return previous
        self._offers[offer.offer_id] = offer
        return offer

    def get_offers(
        self,
        capability: str | None = None,
        executor_ids: Sequence[str] | None = None,
    ) -> tuple[CapabilityOffer, ...]:
        """Return registered offers in stable ID order with optional exact filters."""

        requested = set(executor_ids) if executor_ids is not None else None
        return tuple(
            offer
            for offer in sorted(self._offers.values(), key=lambda item: item.offer_id)
            if (capability is None or offer.capability == capability)
            and (requested is None or offer.executor_id in requested)
        )

    def _require_known_route(self, route: _RouteKey) -> None:
        if not any(self._route_key(offer) == route for offer in self._offers.values()):
            raise ConfigurationError("economic handler route has no registered offer")

    def register_quote_handler(
        self,
        capability: str,
        executor_id: str,
        executor_fingerprint: str,
        handler: QuoteHandler,
    ) -> None:
        route = (capability, executor_id, executor_fingerprint)
        self._require_known_route(route)
        previous = self._quote_handlers.get(route)
        if previous is not None and previous is not handler:
            raise ConfigurationError("quote handler route is already registered")
        self._quote_handlers[route] = handler

    def register_usage_handler(
        self,
        capability: str,
        executor_id: str,
        executor_fingerprint: str,
        handler: UsageHandler,
    ) -> None:
        route = (capability, executor_id, executor_fingerprint)
        self._require_known_route(route)
        previous = self._usage_handlers.get(route)
        if previous is not None and previous is not handler:
            raise ConfigurationError("usage handler route is already registered")
        self._usage_handlers[route] = handler

    def _validate_quote(self, quote: BoundedQuote, request: QuoteRequestV2) -> None:
        bindings = (
            (quote.provider_id, self.provider_id, "provider"),
            (quote.quote_request_id, request.quote_request_id, "quote request"),
            (quote.capability, request.capability, "capability"),
            (quote.executor_id, request.executor_id, "executor"),
            (quote.executor_fingerprint, request.executor_fingerprint, "executor fingerprint"),
            (quote.action_digest, request.action_digest, "action digest"),
            (quote.nonce, request.nonce, "nonce"),
            (quote.maximum_amount.currency, request.desired_currency, "currency"),
        )
        for actual, expected, label in bindings:
            if actual != expected:
                raise ConfigurationError(f"quote {label} does not match request")
        maximum = request.maximum_acceptable_amount
        if maximum is not None and quote.maximum_amount.amount > maximum.amount:
            raise ConfigurationError("quote exceeds requested maximum acceptable amount")
        if quote.offer_id is not None:
            offer = self._offers.get(quote.offer_id)
            if offer is None or self._route_key(offer) != self._route_key(quote):
                raise ConfigurationError("quote references an unknown or mismatched offer")
            offer_bindings: tuple[tuple[object, object, str], ...] = (
                (quote.terms_digest, offer.terms_digest, "terms"),
                (quote.billing_trigger, offer.billing_trigger, "billing trigger"),
                (
                    quote.failure_charge_policy,
                    offer.failure_charge_policy,
                    "failure charge policy",
                ),
                (quote.retry_charge_policy, offer.retry_charge_policy, "retry charge policy"),
                (quote.fixed_attempt_fee, offer.fixed_attempt_fee, "fixed attempt fee"),
                (quote.maximum_amount.currency, offer.settlement_currency, "offer currency"),
            )
            for offer_actual, offer_expected, offer_label in offer_bindings:
                if offer_actual != offer_expected:
                    raise ConfigurationError(
                        f"quote {offer_label} does not match offer"
                    )

    async def process_quote(self, request: QuoteRequestV2) -> BoundedQuote:
        """Invoke the exact-route handler and return its bound signed quote."""

        previous_request = self._quote_requests.get(request.quote_request_id)
        if previous_request is not None:
            if previous_request != request:
                raise ConfigurationError(
                    "quote request ID is already registered with different content"
                )
            return self._quotes[self._quote_ids_by_request[request.quote_request_id]]

        route = self._route_key(request)
        handler = self._quote_handlers.get(route)
        if handler is None:
            raise ConfigurationError("no quote handler is registered for the exact route")
        raw = await _handler_result(handler(request))
        quote = raw if isinstance(raw, BoundedQuote) else self.sign_quote(raw)
        self._require_own_signature(quote)
        self._validate_quote(quote, request)
        previous_quote = self._quotes.get(quote.quote_id)
        if previous_quote is not None and previous_quote != quote:
            raise ConfigurationError("quote ID is already registered with different content")
        self._quotes.setdefault(quote.quote_id, quote)
        self._quote_requests[request.quote_request_id] = request
        self._quote_ids_by_request[request.quote_request_id] = quote.quote_id
        return self._quotes[quote.quote_id]

    def _validate_usage(
        self,
        usage: UsageStatement,
        request: QuoteRequestV2,
        quote: BoundedQuote,
        prepared_id: str,
        attempt_id: str,
    ) -> None:
        bindings = (
            (usage.provider_id, self.provider_id, "provider"),
            (usage.quote_id, quote.quote_id, "quote"),
            (usage.prepared_id, prepared_id, "prepared decision"),
            (usage.action_id, request.action_id, "action"),
            (usage.attempt_id, attempt_id, "attempt"),
            (usage.executor_id, quote.executor_id, "executor"),
            (usage.executor_fingerprint, quote.executor_fingerprint, "executor fingerprint"),
        )
        for actual, expected, label in bindings:
            if actual != expected:
                raise ConfigurationError(f"usage {label} does not match issued quote")
        amount = usage.provider_calculated_amount
        if amount is not None and amount.currency != quote.maximum_amount.currency:
            raise ConfigurationError("usage currency does not match issued quote")

    async def process_usage(
        self,
        quote_id: str,
        *,
        prepared_id: str,
        attempt_id: str,
    ) -> UsageStatement:
        """Invoke the usage handler for an issued quote without inventing evidence."""

        attempt_key = (quote_id, prepared_id, attempt_id)
        previous_id = self._usage_ids_by_attempt.get(attempt_key)
        if previous_id is not None:
            return self._usage_statements[previous_id]
        quote = self._quotes.get(quote_id)
        if quote is None:
            raise ConfigurationError("usage references an unknown issued quote")
        request = self._quote_requests[quote.quote_request_id]
        handler = self._usage_handlers.get(self._route_key(quote))
        if handler is None:
            raise ConfigurationError("no usage handler is registered for the exact route")
        raw = await _handler_result(handler(request, quote, prepared_id, attempt_id))
        if not isinstance(raw, UsageStatement):
            missing = {
                "execution_status",
                "meters",
                "provider_calculated_amount",
            } - raw.keys()
            if missing:
                raise ConfigurationError(
                    "usage handler must explicitly provide execution status, meters, "
                    "and provider-calculated amount"
                )
        usage = raw if isinstance(raw, UsageStatement) else self.sign_usage(raw)
        self._require_own_signature(usage)
        self._validate_usage(usage, request, quote, prepared_id, attempt_id)
        previous_usage = self._usage_statements.get(usage.usage_statement_id)
        if previous_usage is not None and previous_usage != usage:
            raise ConfigurationError(
                "usage statement ID is already registered with different content"
            )
        self._usage_statements.setdefault(usage.usage_statement_id, usage)
        self._usage_ids_by_attempt[attempt_key] = usage.usage_statement_id
        return self._usage_statements[usage.usage_statement_id]


def capability(
    name: str,
    *,
    input_schema: dict[str, Any] | None = None,
    output_schema: dict[str, Any] | None = None,
    description: str | None = None,
    estimate: RouteEstimate | None = None,
    side_effect: SideEffect = SideEffect.READ,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Annotate a callable so it can become a normal in-process executor."""

    def decorate(function: Callable[..., Any]) -> Callable[..., Any]:
        function.__aeep_spec__ = {  # type: ignore[attr-defined]
            "capability": name,
            "input_schema": input_schema or {"type": "object", "additionalProperties": True},
            "output_schema": output_schema,
            "description": description or (function.__doc__ or function.__name__).strip(),
            "estimate": estimate or RouteEstimate(),
            "side_effect": side_effect,
        }
        return function

    return decorate


def executor_from_callable(
    function: Callable[..., Any], *, executor_id: str | None = None
) -> ExecutorSpec:
    metadata = getattr(function, "__aeep_spec__", None)
    if not isinstance(metadata, dict):
        raise ConfigurationError("callable is not decorated with @aeep.capability")
    return ExecutorSpec(
        id=executor_id or f"python.{function.__module__}.{function.__name__}",
        capability=metadata["capability"],
        kind=ExecutorKind.PYTHON,
        description=metadata["description"],
        input_schema=metadata["input_schema"],
        output_schema=metadata["output_schema"],
        estimate=metadata["estimate"],
        side_effect=metadata["side_effect"],
        locality=Locality.IN_PROCESS,
        config={"callable": f"{function.__module__}:{function.__name__}"},
    )


def provider_from_manifest(
    manifest: Manifest,
    *,
    provider_id: str,
    name: str,
) -> ProviderDescriptor:
    definitions = list(manifest.capabilities)
    defined = {definition.capability for definition in definitions}
    for executor in manifest.executors:
        if executor.capability in defined:
            continue
        base, separator, version = executor.capability.rpartition("@")
        semantic = base if separator else executor.capability
        namespace, dot, capability_name = semantic.rpartition(".")
        definitions.append(
            CapabilityDefinition(
                namespace=namespace if dot else provider_id.lower().replace(":", "-"),
                name=capability_name if dot else semantic,
                version=version if separator else "1",
                authority=provider_id,
                owner=provider_id,
                description=executor.description,
                input_schema=executor.input_schema,
                output_schema=executor.output_schema,
                side_effect=executor.side_effect,
            )
        )
        defined.add(executor.capability)
    executors = [
        executor.model_copy(update={"provider_id": provider_id}, deep=True)
        for executor in manifest.executors
    ]
    return ProviderDescriptor(
        provider_id=provider_id,
        name=name,
        capabilities=definitions,
        executors=executors,
        signing_key_id=manifest.signing.key_id if manifest.signing else None,
        trust=TrustLevel.SELF_ASSERTED,
        metadata={
            "mcp": {"command": "aeep", "args": ["serve", "--transport", "stdio"]},
            "health": "/healthz",
            "price_estimates": "aeep_estimate_route_prices",
            "quotes_legacy": "aeep_request_quotes",
            "metering": "aeep_get_metrics",
        },
    )


def import_cli(
    *,
    provider_id: str,
    capability_name: str,
    argv: list[str],
    input_schema: dict[str, Any] | None = None,
    output_schema: dict[str, Any] | None = None,
) -> ProviderDescriptor:
    if not argv or any(not isinstance(item, str) for item in argv):
        raise ConfigurationError("CLI importer requires a non-empty argv string list")
    spec = ExecutorSpec(
        id=f"{provider_id}.cli.{capability_name.replace('@', '.').replace(':', '.')}",
        capability=capability_name,
        kind=ExecutorKind.COMMAND,
        description=f"Imported argv-only command: {argv[0]}",
        input_schema=input_schema or {"type": "object", "additionalProperties": True},
        output_schema=output_schema,
        estimate=RouteEstimate(
            resources=ResourceVector(latency_ms=100, peak_memory_mb=64),
            confidence=0.2,
        ),
        side_effect=SideEffect.READ,
        locality=Locality.LOCAL,
        idempotent=False,
        safe_to_auto_execute=False,
        enabled=False,
        provider_id=provider_id,
        config={"argv": argv, "stdin_json": True, "output": {"type": "json"}},
    )
    return ProviderDescriptor(provider_id=provider_id, name=provider_id, executors=[spec])


def import_mcp(
    *,
    provider_id: str,
    capability_name: str,
    tool: str,
    transport: str,
    endpoint: str,
    args: list[str] | None = None,
    headers: dict[str, str] | None = None,
    credential_scope_id: str | None = None,
    protocol_mode: str = "auto",
    input_schema: dict[str, Any] | None = None,
    output_schema: dict[str, Any] | None = None,
) -> ProviderDescriptor:
    if transport not in {"stdio", "http"}:
        raise ConfigurationError("MCP transport must be stdio or http")
    if protocol_mode not in {"auto", "modern", "legacy"}:
        raise ConfigurationError("MCP protocol mode must be auto, modern, or legacy")
    config: dict[str, Any] = {
        "transport": transport,
        "tool": tool,
        "arguments": "{input}",
        "protocol_mode": protocol_mode,
    }
    locality = Locality.LOCAL
    requires_network = False
    if transport == "stdio":
        config["command"] = endpoint
        config["args"] = list(args or [])
    else:
        if headers and not credential_scope_id:
            raise ConfigurationError("MCP HTTP headers require a credential_scope_id")
        config["url"] = endpoint
        if hostname := urlparse(endpoint).hostname:
            config["allowed_hosts"] = [hostname]
            if is_local_hostname(hostname):
                config["allow_private_networks"] = True
        config["headers"] = dict(headers or {})
        if credential_scope_id:
            config["credential_scope_id"] = credential_scope_id
        locality = Locality.INTERNET
        requires_network = True
    spec = ExecutorSpec(
        id=f"{provider_id}.mcp.{tool}",
        capability=capability_name,
        kind=ExecutorKind.MCP,
        description=f"Imported MCP tool {tool}",
        input_schema=input_schema or {"type": "object", "additionalProperties": True},
        output_schema=output_schema,
        estimate=RouteEstimate(
            resources=ResourceVector(latency_ms=500, network_bytes=1000),
            confidence=0.2,
        ),
        provider_id=provider_id,
        locality=locality,
        requires_network=requires_network,
        idempotent=False,
        safe_to_auto_execute=False,
        enabled=False,
        config=config,
    )
    return ProviderDescriptor(provider_id=provider_id, name=provider_id, executors=[spec])


async def import_mcp_server(
    *,
    provider_id: str,
    transport: str,
    endpoint: str,
    args: list[str] | None = None,
    headers: dict[str, str] | None = None,
    credential_scope_id: str | None = None,
    capability_prefix: str | None = None,
    protocol_mode: str = "auto",
) -> ProviderDescriptor:
    """Inspect one reviewed MCP endpoint and import all advertised tools."""

    if transport == "stdio":
        client: MCPStdioClient | MCPHTTPClient = MCPStdioClient(
            command=endpoint,
            args=args or [],
            protocol_mode=protocol_mode,
        )
    elif transport in {"http", "streamable_http", "streamable-http"}:
        hostname = urlparse(endpoint).hostname
        network_config: dict[str, Any] = {"allowed_hosts": [hostname]} if hostname else {}
        if hostname and is_local_hostname(hostname):
            network_config["allow_private_networks"] = True
        await validate_http_url(
            endpoint,
            network_config,
            label="MCP import",
        )
        resolved_headers = render(headers or {}, {}, allow_env=True)
        client = MCPHTTPClient(
            url=endpoint,
            headers={str(key): str(value) for key, value in resolved_headers.items()},
            protocol_mode=protocol_mode,
        )
    else:
        raise ConfigurationError("MCP transport must be stdio or streamable HTTP")
    try:
        response = await client.list_tools()
    finally:
        await client.close()
    tools = response.result.get("tools", [])
    prefix = re.sub(r"[^a-z0-9.-]+", "-", (capability_prefix or provider_id).lower()).strip("-.")
    if not prefix:
        raise ConfigurationError("capability prefix must contain a letter or number")
    descriptors = [
        import_mcp(
            provider_id=provider_id,
            capability_name=(
                f"{prefix}.{re.sub(r'[^a-z0-9.-]+', '-', str(tool['name']).lower())}@1"
            ),
            tool=str(tool["name"]),
            transport=(
                "http" if transport in {"streamable_http", "streamable-http"} else transport
            ),
            endpoint=endpoint,
            args=args,
            headers=headers,
            credential_scope_id=credential_scope_id,
            protocol_mode=protocol_mode,
            input_schema=(
                tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else None
            ),
        )
        for tool in tools
        if isinstance(tool, dict) and isinstance(tool.get("name"), str)
    ]
    executors = [executor for descriptor in descriptors for executor in descriptor.executors]
    definitions = [
        CapabilityDefinition(
            namespace=executor.capability.rsplit(".", 1)[0],
            name=executor.capability.rsplit(".", 1)[1].removesuffix("@1"),
            authority=provider_id,
            owner=provider_id,
            description=executor.description,
            input_schema=executor.input_schema,
            output_schema=executor.output_schema,
            side_effect=executor.side_effect,
        )
        for executor in executors
    ]
    return ProviderDescriptor(
        provider_id=provider_id,
        name=provider_id,
        capabilities=definitions,
        executors=executors,
        metadata={"mcp_tool_count": len(executors)},
    )


def import_openapi(
    path: str | Path,
    *,
    provider_id: str,
    base_url: str | None = None,
    capability_map: dict[str, str] | None = None,
) -> ProviderDescriptor:
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
        document = json.loads(text) if source.suffix.lower() == ".json" else yaml.safe_load(text)
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ConfigurationError(f"cannot read OpenAPI document: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("paths"), dict):
        raise ConfigurationError("OpenAPI document requires a paths object")
    servers = document.get("servers", [])
    root_url = base_url or (
        servers[0].get("url")
        if isinstance(servers, list) and servers and isinstance(servers[0], dict)
        else None
    )
    if not isinstance(root_url, str):
        raise ConfigurationError("OpenAPI importer requires a base URL")
    root_hostname = urlparse(root_url).hostname
    if not root_hostname:
        raise ConfigurationError("OpenAPI base URL requires a hostname")
    executors: list[ExecutorSpec] = []
    definitions: list[CapabilityDefinition] = []
    for route_path, path_item in sorted(document["paths"].items()):
        if not isinstance(path_item, dict):
            continue
        for method in ("get", "post", "put", "patch", "delete"):
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            operation_id = str(
                operation.get("operationId")
                or f"{method}.{route_path.strip('/').replace('/', '.')}"
            )
            semantic = (capability_map or {}).get(
                operation_id,
                f"{provider_id}.{operation_id}@1".lower().replace("_", "-"),
            )
            if "@" not in semantic:
                raise ConfigurationError(
                    f"mapped capability for {operation_id!r} must include a version"
                )
            if "." not in semantic.rpartition("@")[0]:
                raise ConfigurationError(
                    f"mapped capability for {operation_id!r} must include a namespace"
                )
            request_body = operation.get("requestBody", {})
            content = request_body.get("content", {}) if isinstance(request_body, dict) else {}
            json_content = content.get("application/json", {}) if isinstance(content, dict) else {}
            input_schema = json_content.get("schema") if isinstance(json_content, dict) else None
            responses = operation.get("responses", {})
            response = (
                next(
                    (
                        value
                        for key, value in responses.items()
                        if str(key).startswith("2") and isinstance(value, dict)
                    ),
                    {},
                )
                if isinstance(responses, dict)
                else {}
            )
            response_content = response.get("content", {}) if isinstance(response, dict) else {}
            response_json = (
                response_content.get("application/json", {})
                if isinstance(response_content, dict)
                else {}
            )
            output_schema = response_json.get("schema") if isinstance(response_json, dict) else None
            executor = ExecutorSpec(
                id=f"{provider_id}.http.{operation_id}",
                capability=semantic,
                kind=ExecutorKind.HTTP,
                description=str(
                    operation.get("summary") or operation.get("description") or operation_id
                ),
                input_schema=input_schema or {"type": "object", "additionalProperties": True},
                output_schema=output_schema,
                estimate=RouteEstimate(
                    resources=ResourceVector(latency_ms=1000, network_bytes=2000),
                    confidence=0.2,
                ),
                side_effect=(
                    SideEffect.READ
                    if method == "get"
                    else SideEffect.DESTRUCTIVE
                    if method == "delete"
                    else SideEffect.WRITE
                ),
                idempotent=False,
                safe_to_auto_execute=False,
                enabled=False,
                provider_id=provider_id,
                locality=Locality.INTERNET,
                requires_network=True,
                config={
                    "url": urljoin(
                        root_url.rstrip("/") + "/",
                        re.sub(
                            r"\{([^{}]+)\}",
                            r"{input.\1}",
                            str(route_path).lstrip("/"),
                        ),
                    ),
                    "method": method.upper(),
                    "allowed_hosts": [root_hostname],
                    **({"query": "{input}"} if method == "get" else {"json": "{input}"}),
                    "output": {"type": "json"},
                },
            )
            executors.append(executor)
            unversioned, _, capability_version = semantic.rpartition("@")
            namespace, _, name = unversioned.rpartition(".")
            definitions.append(
                CapabilityDefinition(
                    namespace=namespace,
                    name=name,
                    version=capability_version,
                    authority=root_url,
                    owner=provider_id,
                    description=executor.description,
                    input_schema=executor.input_schema,
                    output_schema=executor.output_schema,
                    side_effect=executor.side_effect,
                )
            )
    return ProviderDescriptor(
        provider_id=provider_id,
        name=str(document.get("info", {}).get("title", provider_id)),
        capabilities=definitions,
        executors=executors,
    )
