from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from aeep.cli import app

RUNNER = CliRunner()


def manifest(tmp_path: Path, fixture: Path) -> Path:
    path = tmp_path / "aeep.yaml"
    path.write_text(
        json.dumps(
            {
                "version": "0.5",
                "database": str(tmp_path / "aeep.db"),
                "provider_packages": {"artifact_root": str(tmp_path / "artifacts")},
                "economic_evidence": {
                    "trust_store": {"path": str(fixture / "trusted-keys.json")}
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_provider_and_candidate_cli_lifecycle(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    fixture = root / "examples" / "provider_package"
    package = fixture / "aeep-provider.yaml"
    config = manifest(tmp_path, fixture)

    for command in (
        ["provider", "validate", str(package), "--compact"],
        ["provider", "digest", str(package), "--compact"],
        ["provider", "verify", str(package), "-m", str(config), "--compact"],
    ):
        result = RUNNER.invoke(app, command)
        assert result.exit_code == 0, f"{command}: {result.output}"

    ingested = RUNNER.invoke(
        app,
        ["candidate", "ingest", str(package), "-m", str(config), "--compact"],
    )
    assert ingested.exit_code == 0, ingested.output
    candidate = json.loads(ingested.stdout)[0]
    executor_id = candidate["executor_id"]
    assert candidate["status"] == "candidate"
    rate_card_id = json.loads(
        (fixture / "evidence" / "rate-card.json").read_text(encoding="utf-8")
    )["snapshot_id"]

    for command in (
        ["candidate", "inspect", executor_id, "-m", str(config), "--compact"],
        ["candidate", "smoke", executor_id, "-m", str(config), "--compact"],
        [
            "candidate",
            "qualify",
            executor_id,
            "--reuse-evidence",
            "-m",
            str(config),
            "--compact",
        ],
        ["candidate", "activate", executor_id, "-m", str(config), "--compact"],
        ["evidence", "list", "--route", executor_id, "-m", str(config), "--compact"],
        [
            "evidence",
            "revalue",
            "--rate-card",
            rate_card_id,
            "-m",
            str(config),
            "--compact",
        ],
    ):
        result = RUNNER.invoke(app, command)
        assert result.exit_code == 0, f"{command}: {result.output}"
