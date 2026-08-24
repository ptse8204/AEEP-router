from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from aeep.discovery import (
    FixtureRegistryAdapter,
    MCPCommunityRegistryAdapter,
    PackageLocatorKind,
    RegistryQuery,
)

NOW = datetime(2026, 8, 21, tzinfo=UTC)


@pytest.mark.asyncio
async def test_fixture_registry_returns_metadata_without_trust_or_execution(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "registry.json"
    fixture.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "registry_candidate_id": "fixture-web",
                        "name": "Fixture Web Reader",
                        "description": "read deterministic web pages",
                        "package_locator": {
                            "kind": "local",
                            "value": "packages/web/aeep-provider.yaml",
                        },
                        "marketplace_labels": {"verified": True},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    results = await FixtureRegistryAdapter(fixture, clock=lambda: NOW).search(
        RegistryQuery(query="web reader")
    )

    assert len(results) == 1
    assert results[0].package_locator is not None
    assert results[0].package_locator.kind is PackageLocatorKind.LOCAL
    assert results[0].marketplace_labels == {"verified": True}
    assert not hasattr(results[0], "trust")


@pytest.mark.asyncio
async def test_mcp_registry_maps_package_metadata_without_promoting_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def validate(*_: object, **__: object) -> None:
        return None

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "servers": [
                    {
                        "server": {
                            "name": "io.github.fixture/web",
                            "version": "1.0.0",
                            "description": "Fixture server",
                            "repository": {"url": "https://github.com/fixture/web"},
                            "_meta": {"verified": True},
                            "packages": [{"registryType": "pypi", "identifier": "fixture"}],
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr("aeep.discovery.validate_http_url", validate)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        results = await MCPCommunityRegistryAdapter(
            base_url="https://registry.test",
            client=client,
            clock=lambda: NOW,
        ).search(RegistryQuery(query="fixture"))

    assert len(results) == 1
    assert results[0].package_locator is not None
    assert results[0].package_locator.kind is PackageLocatorKind.REPOSITORY
    assert results[0].marketplace_labels == {"verified": True}
