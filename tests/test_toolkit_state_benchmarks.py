"""State-output fixtures: no PostgreSQL, ToolHive, model or upstream code runs."""

import hashlib
import json

import pytest
from test_toolkit_benchmarks import pack as file_pack
from test_toolkit_workflow_v2 import definition

from aeep_toolkit.benchmarks import (
    BenchmarkPack,
    inspect_pack,
    parse_pack,
    stage_agent_assets,
    task_input,
)
from aeep_toolkit.cli import main
from aeep_toolkit.installation import manifest_digest
from aeep_toolkit.models import ExtensionManifest
from aeep_toolkit.stack_readiness import source_revisions
from aeep_toolkit.state_benchmarks import MCPStatePack
from aeep_toolkit.workflow import prepare_stack


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pack(tmp_path):
    root, original = file_pack(tmp_path)
    notice = root / "LICENSE"
    notice.write_text("First-party fixture data only")
    assets = [a.model_dump(mode="json") for a in original.tasks[0].assets]
    assets.append(
        dict(path="LICENSE", role="license", sha256=sha(notice), bytes=notice.stat().st_size)
    )
    value = MCPStatePack.model_validate(
        dict(
            pack_id="mcpmark",
            source=original.source.model_dump(mode="json")
            | {"revision": source_revisions("0" * 64)["mcpmark"]},
            tasks=[
                dict(
                    task_id="state-fixture",
                    difficulty="unknown",
                    assets=assets,
                    oracle_layout="separate_asset",
                    upstream_score="binary",
                    state_outputs=[
                        dict(backend_id="owned-database", table_name=name)
                        for name in ("security_audit_results", "security_audit_details")
                    ],
                )
            ],
        )
    )
    return root, value


def test_original_file_pack_keeps_its_exact_serialization_and_required_outputs(tmp_path):
    _, original = file_pack(tmp_path)
    raw = original.model_dump_json()
    assert parse_pack(json.loads(raw)).model_dump_json() == raw
    assert "state_outputs" not in raw
    data = json.loads(raw)
    data["tasks"][0]["output_paths"] = []
    with pytest.raises(ValueError):
        parse_pack(data)


def test_state_inspection_and_staging_preserve_protected_environment_and_original_inputs(
    tmp_path, capsys
):
    root, value = pack(tmp_path)
    file = tmp_path / "pack.json"
    file.write_text(value.model_dump_json())
    main(
        [
            "benchmark",
            "inspect",
            "--pack",
            str(file),
            "--root",
            str(root),
            "--task",
            "state-fixture",
        ]
    )
    facts = json.loads(capsys.readouterr().out)
    task = facts["tasks"][0]
    assert "output_paths" not in task and len(task["state_outputs"]) == 2
    assert task["runtime_binding"] == "REQUIRED_NOT_VERIFIED" and not facts["executed"]
    assert {a["role"] for a in task["protected_assets"]} == {"oracle", "verifier", "environment"}
    stage = tmp_path / "public"
    stage_agent_assets(value, root, "state-fixture", stage)
    assert {p.relative_to(stage).as_posix() for p in stage.rglob("*") if p.is_file()} == {
        "task.md",
        "data.csv",
    }
    assert (stage / "task.md").read_bytes() == (root / "task.md").read_bytes()
    with pytest.raises(ValueError, match=r"state-output.*reviewed MCP"):
        task_input(value, root, "state-fixture")


@pytest.mark.parametrize(
    "change",
    [
        "file-output",
        "missing-verifier",
        "missing-environment",
        "missing-notice",
        "oracle-layout",
        "duplicate-table",
        "sql",
        "dsn",
        "wrong-pin",
    ],
)
def test_state_contract_rejects_unsafe_or_ambiguous_bindings(tmp_path, change):
    _, value = pack(tmp_path)
    data = value.model_dump(mode="json")
    task = data["tasks"][0]
    if change == "file-output":
        task["output_paths"] = ["invented-report.json"]
    elif change.startswith("missing-"):
        role = {
            "missing-verifier": "verifier",
            "missing-environment": "environment",
            "missing-notice": "license",
        }[change]
        task["assets"] = [a for a in task["assets"] if a["role"] != role]
    elif change == "oracle-layout":
        task["oracle_layout"] = "embedded_in_verifier"
    elif change == "duplicate-table":
        task["state_outputs"][1] = task["state_outputs"][0]
    elif change == "sql":
        task["state_outputs"][0]["table_name"] = "table; DROP DATABASE other"
    elif change == "dsn":
        task["state_outputs"][0]["backend_id"] = "postgres://user:password@host/db"
    else:
        data["source"]["revision"] = "0" * 40
    with pytest.raises(ValueError):
        parse_pack(data)


def test_embedded_oracle_stays_only_in_protected_verifier_and_legacy_reader_rejects_pack(tmp_path):
    root, value = pack(tmp_path)
    data = value.model_dump(mode="json")
    task = data["tasks"][0]
    task["oracle_layout"] = "embedded_in_verifier"
    task["assets"] = [a for a in task["assets"] if a["role"] != "oracle"]
    task["instruction_json_key"] = "question"
    source = MCPStatePack.model_validate(data)
    assert (
        inspect_pack(source, root, ("state-fixture",))["tasks"][0]["oracle_layout"]
        == "embedded_in_verifier"
    )
    with pytest.raises(ValueError):
        BenchmarkPack.model_validate(data)
    with pytest.raises(ValueError, match="unknown benchmark task"):
        source.task("unselected")


def test_workflow_exposes_exact_state_requirement_without_opening_backend(tmp_path, monkeypatch):
    path, data, _ = definition(tmp_path)
    separate = tmp_path / "state-source"
    separate.mkdir()
    root, value = pack(separate)
    pack_file = tmp_path / "state-pack.json"
    pack_file.write_text(value.model_dump_json())
    registry_file = tmp_path / "registry.json"
    registry = json.loads(registry_file.read_bytes())
    metadata = registry["extensions"][1]
    metadata["extension_id"] = "mcpmark"
    registry_file.write_text(json.dumps(registry))
    policy_file = tmp_path / "policy.json"
    policy = json.loads(policy_file.read_bytes())
    policy["reviewed_dependency_manifests"].append(
        manifest_digest(ExtensionManifest.model_validate(metadata))
    )
    policy_file.write_text(json.dumps(policy))
    for key, file in [("registry", registry_file), ("policy", policy_file)]:
        data[key]["sha256"] = sha(file)
    selected = data["configurations"]["document-data"]
    selected.update(
        components=["aeep-evaluator", "mcpmark"],
        benchmark={"path": str(pack_file), "sha256": sha(pack_file)},
        asset_root=str(root),
        task_ids=["state-fixture"],
    )
    path.write_text(json.dumps(data))
    from aeep.router import Router

    monkeypatch.setattr(
        Router, "from_manifest", lambda *_: pytest.fail("state preview opened backend")
    )
    facts = prepare_stack(path, "document-data")
    assert any("ToolHive/server binding" in reason for reason in facts["blockers"])
    assert (
        facts["benchmark"]["tasks"][0]["state_outputs"][0]["table_name"] == "security_audit_results"
    )
