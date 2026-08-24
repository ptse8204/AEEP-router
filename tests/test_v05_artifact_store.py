from __future__ import annotations

import gzip
import hashlib
import ipaddress
from pathlib import Path

import httpx
import pytest

from aeep.artifact_store import ContentArtifactStore
from aeep.errors import ConfigurationError
from aeep.provider_package import (
    ArtifactCompression,
    ArtifactLocation,
    ArtifactReference,
)


def reference(payload: bytes, path: str, *, compression: str = "none") -> ArtifactReference:
    return ArtifactReference(
        artifact_id="artifact-1",
        digest=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        media_type="application/json",
        size_bytes=len(payload),
        location=ArtifactLocation(path=path),
        compression=ArtifactCompression(compression),
    )


def test_local_artifact_is_verified_decoded_and_stored(tmp_path: Path) -> None:
    package_root = tmp_path / "package"
    package_root.mkdir()
    raw = gzip.compress(b'{"ok":true}')
    (package_root / "evidence.json.gz").write_bytes(raw)
    item = reference(raw, "evidence.json.gz", compression="gzip")

    resolved = ContentArtifactStore(tmp_path / "cas").resolve_local(
        item,
        package_root=package_root,
    )

    assert resolved.payload == b'{"ok":true}'
    assert resolved.cas_path.read_bytes() == raw
    assert resolved.source_kind == "local"


def test_local_artifact_rejects_traversal_symlink_and_tampering(tmp_path: Path) -> None:
    package_root = tmp_path / "package"
    package_root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"{}")
    store = ContentArtifactStore(tmp_path / "cas")

    with pytest.raises(ConfigurationError, match="traverse"):
        store.resolve_local(reference(b"{}", "../outside.json"), package_root=package_root)

    link = package_root / "link.json"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are unavailable on this platform")
    with pytest.raises(ConfigurationError, match="symlink"):
        store.resolve_local(reference(b"{}", "link.json"), package_root=package_root)

    target = package_root / "target.json"
    target.write_bytes(b'{"tampered":true}')
    with pytest.raises(ConfigurationError, match=r"size|digest|limit"):
        store.resolve_local(reference(b"{}", "target.json"), package_root=package_root)


@pytest.mark.asyncio
async def test_https_artifact_connects_to_validated_ip_with_original_sni(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b'{"ok":true}'
    item = reference(payload, "unused")
    item = item.model_copy(update={"location": ArtifactLocation(uri="https://evidence.test/a")})

    async def resolved(_: str) -> set[ipaddress.IPv4Address]:
        return {ipaddress.ip_address("93.184.216.34")}

    observed: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        observed["host"] = request.headers["host"]
        observed["url"] = str(request.url)
        observed["sni"] = request.extensions.get("sni_hostname")
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=payload,
        )

    monkeypatch.setattr("aeep.artifact_store.resolved_addresses", resolved)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await ContentArtifactStore(tmp_path / "cas").resolve_https(
            item,
            allowed_hosts=("evidence.test",),
            client=client,
        )

    assert result.payload == payload
    assert observed == {
        "host": "evidence.test",
        "url": "https://93.184.216.34/a",
        "sni": "evidence.test",
    }
