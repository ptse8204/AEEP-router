"""Small provider SDK and importers for existing Python, CLI, MCP, and OpenAPI tools."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import yaml

from .errors import ConfigurationError
from .executors.network import validate_http_url
from .mcp.client import MCPHTTPClient, MCPStdioClient
from .models import (
    CapabilityDefinition,
    ExecutorKind,
    ExecutorSpec,
    Locality,
    Manifest,
    ProviderDescriptor,
    ResourceVector,
    RouteEstimate,
    SideEffect,
    TrustLevel,
)
from .templates import render


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
            "quotes": "aeep_request_quotes",
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
        await validate_http_url(
            endpoint,
            {"allowed_hosts": [hostname]} if hostname else {},
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
            transport=transport,
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
