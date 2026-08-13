from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from aeep.cli import app

runner = CliRunner()


def _init(tmp_path: Path) -> Path:
    manifest = tmp_path / "aeep.yaml"
    result = runner.invoke(app, ["init", str(manifest)])
    assert result.exit_code == 0, result.output
    return manifest


def test_version_list_policies_show_and_dry_run(tmp_path):
    manifest = _init(tmp_path)
    assert runner.invoke(app, ["version"]).stdout.strip() == "0.1.0"

    listed = runner.invoke(app, ["list", "-m", str(manifest), "--compact"])
    assert listed.exit_code == 0
    assert listed.stdout and json.loads(listed.stdout)["capabilities"][0]["capability"] == "text.stats"

    policies = runner.invoke(app, ["policies", "-m", str(manifest), "--compact"])
    assert policies.exit_code == 0
    names = {item["name"] for item in json.loads(policies.stdout)["policies"]}
    assert {"balanced", "fastest", "resource_saver"} <= names

    dry = runner.invoke(
        app,
        [
            "run",
            "text.stats",
            "-i",
            '{"text":"abc"}',
            "--dry-run",
            "-m",
            str(manifest),
            "--compact",
        ],
    )
    assert dry.exit_code == 0
    assert json.loads(dry.stdout)["status"] == "unknown"

    routed = runner.invoke(
        app,
        ["route", "text.stats", "-i", '{"text":"abc"}', "-m", str(manifest), "--compact"],
    )
    decision_id = json.loads(routed.stdout)["decision_id"]
    shown = runner.invoke(app, ["show", decision_id, "-m", str(manifest), "--compact"])
    assert shown.exit_code == 0
    assert json.loads(shown.stdout)["decision_id"] == decision_id

    missing = runner.invoke(app, ["show", "rcpt_missing", "-m", str(manifest), "--compact"])
    assert missing.exit_code == 1
    assert json.loads(missing.stdout)["error"] == "not found"


def test_input_file_constraints_and_machine_errors(tmp_path):
    manifest = _init(tmp_path)
    data = tmp_path / "input.yaml"
    data.write_text("text: one two\n")
    result = runner.invoke(
        app,
        [
            "route",
            "text.stats",
            "--input",
            f"@{data}",
            "--require-local",
            "--no-network",
            "--max-cost-usd",
            "0.01",
            "--max-latency-ms",
            "1000",
            "--max-context-tokens",
            "100",
            "--max-peak-memory-mb",
            "1000",
            "--max-side-effect",
            "read",
            "--context",
            '{"compute":{"context_tokens_remaining":1000}}',
            "-m",
            str(manifest),
            "--compact",
        ],
    )
    assert result.exit_code == 0, result.output

    malformed = runner.invoke(
        app, ["route", "text.stats", "-i", "not-json", "-m", str(manifest), "--compact"]
    )
    assert malformed.exit_code != 0

    unknown_tool = runner.invoke(
        app,
        ["tool-call", "missing", "-a", "{}", "-m", str(manifest), "--compact"],
    )
    assert unknown_tool.exit_code == 4
    assert "unknown tool" in unknown_tool.stdout

    bad_export = runner.invoke(app, ["tools", "export", "unknown", "--compact"])
    assert bad_export.exit_code == 2
    assert json.loads(bad_export.stdout)["error_type"] == "ValueError"


def test_init_overwrite_doctor_failure_and_serve_guards(tmp_path, monkeypatch):
    manifest = _init(tmp_path)
    duplicate = runner.invoke(app, ["init", str(manifest)])
    assert duplicate.exit_code == 2
    overwritten = runner.invoke(app, ["init", str(manifest), "--force"])
    assert overwritten.exit_code == 0

    raw = yaml.safe_load(manifest.read_text())
    raw["executors"][1]["config"]["argv"][0] = "definitely-not-installed-aeep-test"
    manifest.write_text(yaml.safe_dump(raw, sort_keys=False))
    doctor = runner.invoke(app, ["doctor", "-m", str(manifest), "--compact"])
    assert doctor.exit_code == 1
    assert json.loads(doctor.stdout)["ok"] is False

    invalid_transport = runner.invoke(
        app, ["serve", "--transport", "bogus", "-m", str(manifest)]
    )
    assert invalid_transport.exit_code != 0

    monkeypatch.delenv("AEEP_BEARER_TOKEN", raising=False)
    exposed = runner.invoke(
        app,
        [
            "serve",
            "--transport",
            "http",
            "--host",
            "0.0.0.0",
            "-m",
            str(manifest),
        ],
    )
    assert exposed.exit_code != 0


def test_delegate_record_cli(tmp_path):
    manifest = tmp_path / "delegate.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "version": "0.1",
                "database": ".aeep/db.sqlite",
                "executors": [
                    {
                        "id": "browser",
                        "capability": "page.title",
                        "kind": "delegate",
                        "description": "browser",
                        "input_schema": {
                            "type": "object",
                            "properties": {"url": {"type": "string"}},
                            "required": ["url"],
                            "additionalProperties": False,
                        },
                        "estimate": {
                            "resources": {"latency_ms": 1000, "context_tokens": 500},
                            "success_probability": 0.9,
                        },
                        "side_effect": "read",
                        "locality": "local",
                        "config": {"instructions": "Read {input.url}"},
                    }
                ],
            },
            sort_keys=False,
        )
    )
    run = runner.invoke(
        app,
        [
            "run",
            "page.title",
            "-i",
            '{"url":"https://example.com"}',
            "-m",
            str(manifest),
            "--compact",
        ],
    )
    assert run.exit_code == 0, run.output
    outcome = json.loads(run.stdout)
    assert outcome["status"] == "delegated"
    decision_id = outcome["decision"]["decision_id"]

    record = runner.invoke(
        app,
        [
            "record",
            decision_id,
            "browser",
            "success",
            "--resources",
            '{"latency_ms":500,"input_tokens":100}',
            "--output-valid",
            "--metadata",
            '{"host":"test"}',
            "-m",
            str(manifest),
            "--compact",
        ],
    )
    assert record.exit_code == 0, record.output
    receipt = json.loads(record.stdout)
    assert receipt["metadata"]["externally_reported"] is True
    assert receipt["metadata"]["host"] == "test"

    history = runner.invoke(
        app,
        [
            "history",
            "--receipts",
            "--executor-id",
            "browser",
            "--capability",
            "page.title",
            "-m",
            str(manifest),
            "--compact",
        ],
    )
    assert history.exit_code == 0
    assert len(json.loads(history.stdout)["receipts"]) == 2


def test_force_executor_and_benchmark_cli(tmp_path):
    manifest = _init(tmp_path)
    forced = runner.invoke(
        app,
        [
            "route",
            "text.stats",
            "-i",
            '{"text":"abc"}',
            "--executor-id",
            "cli.text-stats",
            "-m",
            str(manifest),
            "--compact",
        ],
    )
    assert forced.exit_code == 0, forced.output
    assert json.loads(forced.stdout)["selected_executor_id"] == "cli.text-stats"

    refused = runner.invoke(
        app,
        ["benchmark", "text.stats", "-i", '{"text":"abc"}', "-m", str(manifest), "--compact"],
    )
    assert refused.exit_code == 2
    assert "confirm-all-routes" in refused.stdout

    benchmarked = runner.invoke(
        app,
        [
            "benchmark",
            "text.stats",
            "-i",
            '{"text":"abc"}',
            "--confirm-all-routes",
            "-m",
            str(manifest),
            "--compact",
        ],
    )
    assert benchmarked.exit_code == 0, benchmarked.output
    payload = json.loads(benchmarked.stdout)
    assert len(payload["entries"]) == 2
    assert all(item["receipt_id"] for item in payload["entries"])
