"""Selected-stack preparation is inert; all data here are synthetic fixtures."""

import hashlib
import json
import sqlite3

import pytest
from test_toolkit_benchmarks import pack
from test_toolkit_contracts import extension_data

from aeep.router import Router
from aeep_toolkit.candidate import inspect
from aeep_toolkit.cli import main
from aeep_toolkit.installation import PreviewPolicy, manifest_digest
from aeep_toolkit.models import ExtensionManifest, ExtensionRegistry


def definition(tmp_path):
    root, benchmark = pack(tmp_path)
    skill = tmp_path.resolve() / "selected-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: fixture\ndescription: synthetic\n---\n")
    manifests = []
    for name, role in [
        ("aeep-evaluator", "evaluator"),
        ("skillsbench", "benchmark"),
        ("waza", "evaluator"),
    ]:
        manifests.append(
            ExtensionManifest.model_validate(
                extension_data() | dict(extension_id=name, role=role, disk_bytes=0, memory_bytes=0)
            )
        )
    registry = ExtensionRegistry(extensions=tuple(manifests))
    policy = PreviewPolicy(
        host="codex",
        platform="darwin-arm64",
        allowed_licenses=("MIT",),
        allowed_data_rights=("no dataset",),
        allowed_filesystem_scopes=("workspace",),
        allowed_authentication=("host_owned",),
        allowed_financial_exposure=("subscription_unpriced",),
        free_disk_bytes=80 * 1024**3,
        reviewed_dependency_manifests=tuple(map(manifest_digest, manifests)),
    )
    bindings = {}
    for name, value in [("registry", registry), ("policy", policy), ("benchmark", benchmark)]:
        path = tmp_path.resolve() / (name + ".json")
        path.write_text(value.model_dump_json())
        bindings[name] = {
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    data = {
        "schema_version": "aeep.toolkit.workflow.v2",
        "registry": bindings["registry"],
        "policy": bindings["policy"],
        "configurations": {
            "document-data": {
                "evaluator": "managed",
                "candidate": {"path": str(skill), "sha256": inspect(skill).sha256},
                "benchmark": bindings["benchmark"],
                "asset_root": str(root),
                "task_ids": ["fixture"],
                "components": ["aeep-evaluator", "skillsbench"],
            }
        },
    }
    path = tmp_path.resolve() / "workflow.json"
    path.write_text(json.dumps(data))
    return path, data, skill


def test_v2_inspects_candidate_pack_and_selected_dependency_closure_without_mutation(
    tmp_path, monkeypatch, capsys
):
    path, _data, _skill = definition(tmp_path)
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: pytest.fail("database opened"))
    monkeypatch.setattr(Router, "from_manifest", lambda *a, **k: pytest.fail("backend initialized"))
    assert (
        main(["workflow", "prepare", "--workflow", str(path), "--configuration", "document-data"])
        == 0
    )
    value = json.loads(capsys.readouterr().out)
    assert value["installation"]["selected"] == ["aeep-evaluator", "skillsbench"]
    assert value["benchmark"]["tasks"][0]["domain"] == "document-data"
    assert value["candidate"]["executed"] is False
    assert any("rights" in reason for reason in value["blockers"])
    assert any("canonical assessment" in reason for reason in value["blockers"])
    assert {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


def test_unimplemented_backend_is_visible_and_never_silently_falls_back(tmp_path, capsys):
    path, data, _ = definition(tmp_path)
    selected = data["configurations"]["document-data"]
    selected["evaluator"] = "waza"
    selected["components"] = ["waza", "skillsbench"]
    path.write_text(json.dumps(data))
    main(["workflow", "plan", "--workflow", str(path), "--configuration", "document-data"])
    value = json.loads(capsys.readouterr().out)
    assert any(
        "external evaluator workflow dispatch is not implemented" in reason
        for reason in value["blockers"]
    )
    assert value["workflow"]["configurations"]["document-data"]["evaluator"] == "waza"


def test_changed_candidate_is_rejected_and_unready_run_never_opens_service(
    tmp_path, monkeypatch, capsys
):
    path, _data, skill = definition(tmp_path)
    main(["workflow", "prepare", "--workflow", str(path), "--configuration", "document-data"])
    reviewed = json.loads(capsys.readouterr().out)["review_sha256"]
    monkeypatch.setattr(
        Router, "from_manifest", lambda *a, **k: pytest.fail("unready workflow initialized backend")
    )
    with pytest.raises(SystemExit) as error:
        main(
            [
                "workflow",
                "run",
                "--workflow",
                str(path),
                "--configuration",
                "document-data",
                "--reviewed-digest",
                reviewed,
                "--manifest",
                str(tmp_path / "unused.json"),
                "--output",
                str(tmp_path / "out"),
            ]
        )
    assert error.value.code == 2 and not (tmp_path / "out").exists()
    (skill / "SKILL.md").write_text("changed source")
    with pytest.raises(SystemExit):
        main(["workflow", "prepare", "--workflow", str(path), "--configuration", "document-data"])
