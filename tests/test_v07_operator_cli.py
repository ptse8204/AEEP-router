from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from aeep.cli import app
from aeep.models import ActionRequest
from aeep.router import Router

FAKE = Path(__file__).parent / "fixtures" / "fake_codex_app_server.py"


def manifest_file(tmp_path: Path) -> Path:
    path = tmp_path / "aeep.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": "0.7",
                "database": str(tmp_path / "aeep.sqlite3"),
                "resources": [
                    {
                        "id": "fixture-subscription",
                        "kind": "subscription",
                        "provider": "openai",
                        "product": "codex",
                        "transferability": "self_only",
                    }
                ],
                "executors": [
                    {
                        "id": "codex-managed",
                        "capability": "text.length@1",
                        "kind": "host_managed",
                        "description": "fixture",
                        "resource_pool": "fixture-subscription",
                        "input_schema": {
                            "type": "object",
                            "properties": {"text": {"type": "string"}},
                            "required": ["text"],
                            "additionalProperties": False,
                        },
                        "output_schema": {
                            "type": "object",
                            "properties": {"characters": {"type": "integer"}},
                            "required": ["characters"],
                            "additionalProperties": False,
                        },
                        "side_effect": "none",
                        "config": {
                            "adapter_id": "codex-app-server",
                            "argv": [
                                sys.executable,
                                "-u",
                                str(FAKE),
                                "--scenario",
                                "success",
                            ],
                            "instructions": "Count {input.text}",
                            "working_directory_policy": "manifest",
                            "sandbox_policy": "read_only",
                            "approval_ceiling": "read",
                            "output_mode": "json",
                            "timeout_seconds": 2,
                            "max_message_bytes": 4096,
                            "environment_allowlist": [],
                            "store_prompt": False,
                            "store_output": False,
                            "redaction_policy": "strict",
                        },
                    }
                ],
            },
            sort_keys=False,
        )
    )
    return path


def invoke_json(path: Path, *args: str):
    result = CliRunner().invoke(app, [*args, "--manifest", str(path), "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def test_codex_operator_commands_use_fake_without_model_turn(tmp_path: Path):
    path = manifest_file(tmp_path)
    doctor = invoke_json(path, "hosts", "codex", "doctor")
    account = invoke_json(path, "hosts", "codex", "account")
    models = invoke_json(path, "hosts", "codex", "models")
    quota = invoke_json(path, "hosts", "codex", "quota")
    assert doctor["status"] == "ready"
    assert account["authenticated"] is True
    assert "fixture-principal" not in json.dumps(account)
    assert [item["id"] for item in models] == ["fixture-model-a", "fixture-model-b"]
    assert len(quota["windows"]) == 2


def test_codex_login_is_operator_only_and_does_not_echo_login_id(tmp_path: Path):
    path = manifest_file(tmp_path)
    result = CliRunner().invoke(
        app, ["hosts", "codex", "login", "--manifest", str(path)]
    )
    assert result.exit_code == 0, result.output
    assert "https://example.invalid/operator-login" in result.stdout
    assert "fixture-login" not in result.stdout


def test_capacity_commands_emit_json(tmp_path: Path):
    path = manifest_file(tmp_path)
    listed = invoke_json(path, "capacity", "list")
    status = invoke_json(path, "capacity", "status", "fixture-subscription")
    reservations = invoke_json(path, "capacity", "reservations")
    assert listed["resources"][0]["resource"]["transferability"] == "self_only"
    assert status["resource"]["id"] == "fixture-subscription"
    assert reservations == {"reservations": []}


@pytest.mark.asyncio
async def test_manifest_codex_route_auto_registers_official_adapter(tmp_path: Path):
    router = Router.from_manifest(manifest_file(tmp_path))
    try:
        outcome = await router.execute(
            ActionRequest(capability="text.length@1", input={"text": "abc"})
        )
        assert outcome.ok and outcome.output == {"characters": 3}
        assert outcome.receipts[0].metadata["model_turn_count"] == 1
    finally:
        await router.close()
