"""Shared outbound-network validation for HTTP-backed executors.

The validator is intentionally conservative: remote endpoints require HTTPS,
credentials embedded in URLs are rejected, and public-host configurations may
not resolve to private/special-use addresses unless the operator explicitly
opts in. This is a guardrail rather than a complete DNS-rebinding defence;
production deployments should also enforce egress policy at the network layer.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse

from ..errors import ConfigurationError, ExecutorError


async def resolved_addresses(
    hostname: str,
) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    def resolve() -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        addresses: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
        for item in socket.getaddrinfo(hostname, None):
            addresses.add(ipaddress.ip_address(item[4][0]))
        return addresses

    return await asyncio.to_thread(resolve)


def is_local_hostname(hostname: str) -> bool:
    normalized = hostname.rstrip(".").lower()
    return normalized in {"localhost", "127.0.0.1", "::1"} or normalized.endswith(".localhost")


async def validate_http_url(url: str, config: dict[str, Any], *, label: str = "HTTP") -> None:
    """Validate a rendered HTTP(S) URL against reviewed executor configuration."""

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ConfigurationError(f"{label} executor URL must be absolute http(s)")
    if parsed.username or parsed.password:
        raise ConfigurationError(f"credentials in {label} URLs are not allowed")

    hostname = parsed.hostname.rstrip(".").lower()
    allowed_hosts = config.get("allowed_hosts")
    if allowed_hosts is not None:
        if not isinstance(allowed_hosts, list) or not all(
            isinstance(item, str) for item in allowed_hosts
        ):
            raise ConfigurationError(f"{label} config.allowed_hosts must be a list of hosts")
        normalized_allowed = {item.rstrip(".").lower() for item in allowed_hosts}
        if hostname not in normalized_allowed:
            raise ConfigurationError(f"rendered {label} host {hostname!r} is not allowlisted")

    local = is_local_hostname(hostname)
    if parsed.scheme != "https" and not local and not config.get("allow_insecure_http", False):
        raise ConfigurationError(f"remote {label} executors require HTTPS by default")
    if local or config.get("allow_private_networks", False):
        return

    try:
        addresses = await resolved_addresses(hostname)
    except OSError as exc:
        raise ExecutorError(f"cannot resolve {label} host {hostname!r}: {exc}") from exc
    if not addresses:
        raise ExecutorError(f"cannot resolve {label} host {hostname!r}")
    if any(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        for address in addresses
    ):
        raise ConfigurationError(
            f"{label} target resolves to a private or non-public address; set "
            "allow_private_networks only for a reviewed endpoint"
        )
