"""Bounded content-addressed storage for provider-package artifacts."""

from __future__ import annotations

import gzip
import hashlib
import ipaddress
import os
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import httpx

from .errors import ConfigurationError, ProtocolError
from .executors.network import resolved_addresses
from .provider_package import ArtifactCompression, ArtifactReference

MAXIMUM_ARTIFACT_BYTES = 52_428_800
MAXIMUM_COMPRESSION_RATIO = 100


@dataclass(frozen=True, slots=True)
class ResolvedArtifact:
    reference: ArtifactReference
    cas_path: Path
    payload: bytes
    source_kind: str


def _safe_local_path(package_root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ConfigurationError("artifact path must be relative and cannot traverse")
    root = package_root.resolve()
    current = root
    for part in candidate.parts:
        current = current / part
        try:
            if current.is_symlink():
                raise ConfigurationError("artifact symlinks are not supported")
        except OSError as exc:
            raise ConfigurationError("cannot inspect artifact path") from exc
    resolved = current.resolve()
    if not resolved.is_relative_to(root):
        raise ConfigurationError("artifact path escapes the provider-package root")
    if not resolved.is_file():
        raise ConfigurationError("artifact path is not a regular file")
    return resolved


def _read_stable_file(path: Path, maximum: int) -> bytes:
    try:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            chunks: list[bytes] = []
            total = 0
            while chunk := stream.read(64 * 1024):
                total += len(chunk)
                if total > maximum:
                    raise ConfigurationError("artifact exceeds configured byte limit")
                chunks.append(chunk)
            after = os.fstat(stream.fileno())
    except OSError as exc:
        raise ConfigurationError("cannot read provider-package artifact") from exc
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or (before.st_ino and after.st_ino and before.st_ino != after.st_ino)
    ):
        raise ConfigurationError("artifact changed while it was being read")
    return b"".join(chunks)


def _decode(reference: ArtifactReference, raw: bytes, maximum: int) -> bytes:
    if reference.compression is ArtifactCompression.NONE:
        return raw
    if reference.compression is not ArtifactCompression.GZIP:  # pragma: no cover - enum guard
        raise ConfigurationError("unsupported artifact compression")
    output = bytearray()
    try:
        with gzip.GzipFile(fileobj=BytesIO(raw), mode="rb") as stream:
            while chunk := stream.read(64 * 1024):
                output.extend(chunk)
                if len(output) > maximum:
                    raise ConfigurationError("decompressed artifact exceeds configured limit")
                if raw and len(output) > len(raw) * MAXIMUM_COMPRESSION_RATIO:
                    raise ConfigurationError("artifact compression ratio exceeds safe limit")
    except (gzip.BadGzipFile, EOFError, OSError) as exc:
        raise ConfigurationError("artifact gzip payload is invalid") from exc
    return bytes(output)


def _verify_blob(reference: ArtifactReference, raw: bytes) -> None:
    if len(raw) != reference.size_bytes:
        raise ConfigurationError("artifact size does not match its declaration")
    digest = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    if digest != reference.digest:
        raise ConfigurationError("artifact digest does not match its declaration")


class ContentArtifactStore:
    def __init__(self, root: str | Path, *, maximum_bytes: int = MAXIMUM_ARTIFACT_BYTES) -> None:
        if maximum_bytes < 1 or maximum_bytes > MAXIMUM_ARTIFACT_BYTES:
            raise ValueError("artifact maximum must be between 1 byte and 50 MiB")
        self.root = Path(root).expanduser()
        self.maximum_bytes = maximum_bytes

    def _store(self, reference: ArtifactReference, raw: bytes) -> Path:
        digest = reference.digest.removeprefix("sha256:")
        directory = self.root / "sha256" / digest[:2]
        destination = directory / digest
        directory.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
                raise ConfigurationError("content-addressed artifact has conflicting bytes")
            return destination
        descriptor, temporary = tempfile.mkstemp(prefix=f".{digest}.", dir=directory)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return destination

    def resolve_local(
        self,
        reference: ArtifactReference,
        *,
        package_root: str | Path,
    ) -> ResolvedArtifact:
        if reference.location.path is None:
            raise ConfigurationError("artifact does not declare a local path")
        path = _safe_local_path(Path(package_root), reference.location.path)
        raw = _read_stable_file(path, min(self.maximum_bytes, reference.size_bytes + 1))
        _verify_blob(reference, raw)
        destination = self._store(reference, raw)
        return ResolvedArtifact(
            reference=reference,
            cas_path=destination,
            payload=_decode(reference, raw, self.maximum_bytes),
            source_kind="local",
        )

    async def resolve_https(
        self,
        reference: ArtifactReference,
        *,
        allowed_hosts: tuple[str, ...],
        allow_private_networks: bool = False,
        client: httpx.AsyncClient | None = None,
        maximum_redirects: int = 2,
    ) -> ResolvedArtifact:
        if reference.location.uri is None:
            raise ConfigurationError("artifact does not declare a remote URI")
        raw = await self._download_pinned(
            reference.location.uri,
            reference=reference,
            allowed_hosts=allowed_hosts,
            allow_private_networks=allow_private_networks,
            client=client,
            maximum_redirects=maximum_redirects,
        )
        _verify_blob(reference, raw)
        destination = self._store(reference, raw)
        return ResolvedArtifact(
            reference=reference,
            cas_path=destination,
            payload=_decode(reference, raw, self.maximum_bytes),
            source_kind="https",
        )

    async def _download_pinned(
        self,
        url: str,
        *,
        reference: ArtifactReference,
        allowed_hosts: tuple[str, ...],
        allow_private_networks: bool,
        client: httpx.AsyncClient | None,
        maximum_redirects: int,
    ) -> bytes:
        current = url
        expected_host = urlparse(url).hostname
        if expected_host is None:
            raise ConfigurationError("artifact URI requires a hostname")
        normalized_allowed = {item.rstrip(".").lower() for item in allowed_hosts}
        owned_client = client is None
        active_client = client or httpx.AsyncClient(
            timeout=10,
            follow_redirects=False,
            trust_env=False,
        )
        try:
            for redirect in range(maximum_redirects + 1):
                parsed = urlparse(current)
                hostname = parsed.hostname.rstrip(".").lower() if parsed.hostname else None
                if parsed.scheme != "https" or hostname is None:
                    raise ConfigurationError("remote artifacts require an absolute HTTPS URI")
                if parsed.username or parsed.password:
                    raise ConfigurationError("artifact URIs cannot contain credentials")
                if hostname not in normalized_allowed:
                    raise ConfigurationError("artifact host is not operator-allowlisted")
                addresses = await resolved_addresses(hostname)
                if not addresses:
                    raise ProtocolError("artifact host resolved to no addresses")
                if not allow_private_networks and any(
                    not address.is_global
                    or address.is_multicast
                    or getattr(address, "is_site_local", False)
                    for address in addresses
                ):
                    raise ConfigurationError("artifact host resolves to a non-public address")
                address = sorted(addresses, key=lambda item: (item.version, int(item)))[0]
                host = f"[{address}]" if isinstance(address, ipaddress.IPv6Address) else str(address)
                port = parsed.port or 443
                netloc = host if port == 443 else f"{host}:{port}"
                pinned = urlunparse(parsed._replace(netloc=netloc))
                host_header = hostname if port == 443 else f"{hostname}:{port}"
                request = active_client.build_request(
                    "GET",
                    pinned,
                    headers={"host": host_header, "accept": reference.media_type},
                    extensions={"sni_hostname": hostname},
                )
                response = await active_client.send(request, stream=True)
                try:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        if redirect >= maximum_redirects:
                            raise ProtocolError("artifact redirect limit exceeded")
                        location = response.headers.get("location")
                        if not location:
                            raise ProtocolError("artifact redirect is missing Location")
                        redirected = urljoin(current, location)
                        target = urlparse(redirected)
                        if target.scheme != "https" or target.hostname != expected_host:
                            raise ConfigurationError("artifact redirects must remain same-origin")
                        current = redirected
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").split(";", 1)[0]
                    expected_type = reference.media_type.split(";", 1)[0]
                    if content_type != expected_type:
                        raise ProtocolError("artifact response content type is inconsistent")
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > min(self.maximum_bytes, reference.size_bytes + 1):
                            raise ProtocolError("artifact response exceeds configured limit")
                        chunks.append(chunk)
                    return b"".join(chunks)
                finally:
                    await response.aclose()
            raise ProtocolError("artifact could not be resolved")  # pragma: no cover
        finally:
            if owned_client:
                await active_client.aclose()
