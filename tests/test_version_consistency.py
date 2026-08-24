from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from aeep import __version__
from aeep.config import default_manifest_dict
from aeep.models import Manifest

ROOT = Path(__file__).resolve().parents[1]


def test_package_and_documentation_versions_are_consistent():
    with (ROOT / "pyproject.toml").open("rb") as source:
        project_version = tomllib.load(source)["project"]["version"]
    assert project_version == __version__

    protocol_version = project_version.rsplit(".", 1)[0]
    markers = {
        "README.md": f"**Status:** AEEP {protocol_version}",
        "SPEC.md": f"# AEEP {protocol_version} protocol specification",
        "docs/ACCOUNTING.md": f"AEEP {protocol_version} keeps",
        "examples/economic_evidence/README.md": (
            f"# AEEP {protocol_version} deterministic economic-evidence proof"
        ),
        "examples/economic_evidence/report.md": (
            f"# AEEP {protocol_version} economic evidence proof"
        ),
        "examples/proof/README.md": f"# AEEP {protocol_version} proof assets",
    }
    for path, marker in markers.items():
        assert marker in (ROOT / path).read_text(encoding="utf-8")

    assert Manifest().version == protocol_version
    assert default_manifest_dict()["version"] == protocol_version

    for schema_name in (
        "billing-reconciliation",
        "bounded-quote",
        "capability-offer",
        "economic-evidence-link",
        "economic-proof-campaign-report",
        "market-aggregate",
        "payment-reservation-v2",
        "prepared-route-decision",
        "prepared-route-transition",
        "pricing-dispute",
        "quote-request-v2",
        "refund-receipt-v2",
        "settlement-evidence",
        "settlement-receipt",
        "usage-statement",
    ):
        schema = json.loads(
            (ROOT / "schemas" / f"{schema_name}.schema.json").read_text(encoding="utf-8")
        )
        version_schema = schema["properties"]["schema_version"]
        assert version_schema["default"] == protocol_version
        assert version_schema["enum"] == ["0.4", "0.5"]

    proof = json.loads(
        (ROOT / "examples" / "economic_evidence" / "report.json").read_text(
            encoding="utf-8"
        )
    )
    assert proof["schema_version"] == protocol_version

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r"^## Unreleased — (\d+\.\d+\.\d+)$", changelog, re.MULTILINE)
    assert match is not None
    assert match.group(1) == project_version


def test_legacy_manifest_versions_remain_supported():
    versions = ("0.1", "0.15", "0.2", "0.3", "0.4")
    assert tuple(Manifest.model_validate({"version": version}).version for version in versions) == versions
    assert Manifest().version == "0.5"
    assert default_manifest_dict()["version"] == "0.5"
