"""Destination checks use operator configuration, never advertised safety hints."""

from __future__ import annotations

from urllib.parse import urlsplit

from ..errors import ConfigurationError
from ..models import ExecutorKind, ExecutorSpec
from .models import AssessmentAuthorization, AssessmentEnvironment


def require_destination(spec: ExecutorSpec, environment: AssessmentEnvironment, grant: AssessmentAuthorization) -> None:
    destination = "local"
    http_transport = spec.kind == ExecutorKind.HTTP or (
        spec.kind == ExecutorKind.MCP
        and spec.config.get("transport", "stdio") in {"http", "streamable_http", "streamable-http"}
    )
    remote = spec.requires_network or http_transport
    if spec.kind == ExecutorKind.MANAGED_HOST:
        destination = "codex"
        invocation = spec.managed_host_config().invocation
        if invocation is not None and invocation.mode == "mcp_tool":
            destination = f"codex:mcp:{invocation.server}"
            locality = environment.identity.get(f"mcp_server.{invocation.server}.locality")
            if locality not in {"local", "remote"}:
                raise ConfigurationError("host MCP target requires an operator-reviewed destination locality")
            remote = locality == "remote"
    elif remote:
        if http_transport and (spec.config.get("follow_redirects") or spec.config.get("trust_proxy_env")):
            raise ConfigurationError("assessment HTTP destinations require redirects and environment proxies disabled")
        url = urlsplit(str(spec.config.get("url", "")))
        if url.scheme not in {"http", "https"} or not url.hostname or "{" in url.netloc:
            raise ConfigurationError("network assessment requires an explicit destination origin")
        destination = f"{url.scheme}://{url.netloc}"
    if environment.network and environment.kind == "container":
        destination, remote = "network:any", True
    if destination not in grant.allowed_destinations:
        raise ConfigurationError("assessment destination is outside operator authorization")
    if remote and not grant.remote_disclosure:
        raise ConfigurationError("remote candidate disclosure is not authorized")
