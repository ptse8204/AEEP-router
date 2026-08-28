from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from aeep.cli import app

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]


def test_cli_init_doctor_route_run_history(tmp_path):
    manifest = tmp_path / "aeep.yaml"
    result = runner.invoke(app, ["init", str(manifest)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["ok"] is True

    result = runner.invoke(app, ["doctor", "-m", str(manifest), "--compact"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["ok"] is True

    args = ["text.stats", "-i", '{"text":"hello world"}', "-m", str(manifest), "--compact"]
    result = runner.invoke(app, ["route", *args])
    assert result.exit_code == 0, result.output
    decision = json.loads(result.stdout)
    assert decision["selected_executor_id"] == "builtin.text-stats"

    result = runner.invoke(app, ["run", *args])
    assert result.exit_code == 0, result.output
    outcome = json.loads(result.stdout)
    assert outcome["output"]["words"] == 2

    result = runner.invoke(app, ["history", "--receipts", "-m", str(manifest), "--compact"])
    assert result.exit_code == 0
    assert len(json.loads(result.stdout)["receipts"]) == 1


def test_cli_tools_and_tool_call(tmp_path):
    manifest = tmp_path / "aeep.yaml"
    assert runner.invoke(app, ["init", str(manifest)]).exit_code == 0
    result = runner.invoke(app, ["tools", "export", "anthropic", "--compact"])
    assert result.exit_code == 0
    assert {tool["name"] for tool in json.loads(result.stdout)["tools"]} == {
        "aeep_execute_action",
        "aeep_estimate_route_prices",
        "aeep_get_metrics",
        "aeep_list_capabilities",
        "aeep_record_outcome",
        "aeep_request_quotes",
        "aeep_route_action",
        "aeep_show_prepared_decision",
        "aeep_show_quote",
        "aeep_show_settlement",
    }

    result = runner.invoke(
        app,
        [
            "tool-call",
            "aeep_execute_action",
            "-a",
            '{"capability":"text.stats","input":{"text":"a b c"}}',
            "-m",
            str(manifest),
            "--compact",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["output"]["words"] == 3


def test_cli_provider_conformance() -> None:
    result = runner.invoke(
        app,
        [
            "provider",
            "conformance",
            str(ROOT / "examples" / "provider_package" / "aeep-provider.yaml"),
            "--compact",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["passed"] is True


def test_cli_missing_route_has_machine_readable_error(tmp_path):
    manifest = tmp_path / "aeep.yaml"
    runner.invoke(app, ["init", str(manifest)])
    result = runner.invoke(app, ["route", "missing", "-m", str(manifest), "--compact"])
    assert result.exit_code == 3
    payload = json.loads(result.stdout)
    assert payload["selected_executor_id"] is None
