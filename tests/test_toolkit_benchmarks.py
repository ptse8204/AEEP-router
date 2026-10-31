"""Task-pack fixtures check separation and identity, not upstream reproduction."""

import hashlib
import json

import pytest

from aeep_toolkit.benchmarks import (
    SKILLSBENCH_REVISION,
    BenchmarkPack,
    asset_path,
    inspect_pack,
    stage_agent_assets,
)
from aeep_toolkit.cli import main


def pack(tmp_path):
    root = tmp_path.resolve() / "task-pack"
    root.mkdir()
    assets = []
    for name, role in (
        ("task.md", "instruction"),
        ("data.csv", "input"),
        ("skill/SKILL.md", "candidate_skill"),
        ("oracle/answer.txt", "oracle"),
        ("verifier/check.py", "verifier"),
        ("environment/Dockerfile", "environment"),
    ):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = ("synthetic " + role).encode()
        path.write_bytes(raw)
        assets.append(
            dict(path=name, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw), role=role)
        )
    value = BenchmarkPack.model_validate(
        dict(
            pack_id="skillsbench",
            source=dict(
                repository="https://github.com/benchflow-ai/skillsbench",
                revision=SKILLSBENCH_REVISION,
                artifact_sha256="a" * 64,
                license_expression="Apache-2.0",
                data_rights="synthetic fixture only",
            ),
            tasks=[
                dict(
                    task_id="fixture",
                    domain="document-data",
                    difficulty="hard",
                    assets=assets,
                    output_paths=["report.json"],
                    upstream_score="binary",
                )
            ],
        )
    )
    return root, value


def test_staging_protects_oracles_verifiers_and_baseline_candidate_absence(tmp_path):
    root, value = pack(tmp_path)
    summary = inspect_pack(value, root, ("fixture",))
    assert summary["executed"] is summary["official_benchmark_reproduction"] is False
    assert len(summary["tasks"][0]["protected_assets"]) == 2
    for available in (False, True):
        destination = tmp_path.resolve() / str(available)
        stage_agent_assets(value, root, "fixture", destination, candidate_available=available)
        names = {str(p.relative_to(destination)) for p in destination.rglob("*") if p.is_file()}
        assert names == {"task.md", "data.csv"} | ({"skill/SKILL.md"} if available else set())
        assert (destination / "data.csv").read_bytes() == (root / "data.csv").read_bytes()
        with pytest.raises(ValueError, match="new directory"):
            stage_agent_assets(value, root, "fixture", destination)


@pytest.mark.parametrize(
    "change", ["content", "size", "link", "parent-link", "hard-link", "directory"]
)
def test_asset_substitution_is_rejected_before_staging(tmp_path, change):
    root, value = pack(tmp_path)
    path = root / "data.csv"
    if change == "content":
        path.write_bytes(b"X" * path.stat().st_size)
    elif change == "size":
        path.write_bytes(b"changed length")
    elif change == "directory":
        path.unlink()
        path.mkdir()
    elif change == "parent-link":
        linked = tmp_path / "linked"
        linked.symlink_to(root, target_is_directory=True)
        root = linked
    elif change == "hard-link":
        (root / "alias.csv").hardlink_to(path)
    else:
        original = root / "original.csv"
        path.rename(original)
        path.symlink_to(original)
    with pytest.raises((ValueError, OSError)):
        stage_agent_assets(value, root, "fixture", tmp_path.resolve() / "staged")
    assert not (tmp_path / "staged").exists()


@pytest.mark.parametrize(
    "path", ["../answer", "/root/data", ".codex/auth.json", "auth.json", ".env", "a\\b", "./data"]
)
def test_pack_rejects_unsafe_asset_paths(tmp_path, path):
    _, value = pack(tmp_path)
    data = value.model_dump(mode="json")
    data["tasks"][0]["assets"][1]["path"] = path
    with pytest.raises(ValueError):
        BenchmarkPack.model_validate(data)


def test_pins_roles_and_explicit_task_selection_are_required(tmp_path):
    root, value = pack(tmp_path)
    for field, replacement in [("revision", "0" * 40)]:
        data = value.model_dump(mode="json")
        data["source"][field] = replacement
        with pytest.raises(ValueError, match="reviewed pin"):
            BenchmarkPack.model_validate(data)
    data = value.model_dump(mode="json")
    data["tasks"][0]["assets"] = [a for a in data["tasks"][0]["assets"] if a["role"] != "verifier"]
    with pytest.raises(ValueError, match="protected oracle"):
        BenchmarkPack.model_validate(data)
    for ids in ((), ("fixture", "fixture"), ("absent",)):
        with pytest.raises(ValueError):
            inspect_pack(value, root, ids)
    assert asset_path(root, value.tasks[0].assets[1]) == root / "data.csv"


def test_cli_lists_equal_domains_without_claiming_task_execution(capsys):
    assert main(["benchmark", "list"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["revision"] == SKILLSBENCH_REVISION
    assert sum(t["domain"] == "document-data" for t in result["tasks"]) == 3
    assert sum(t["domain"] == "software-engineering" for t in result["tasks"]) == 3
    assert all(t["functional_status"] == "NOT_VERIFIED" for t in result["tasks"])


def test_six_task_original_import_retains_blob_identity_and_never_clears_rights(tmp_path):
    from aeep_toolkit.benchmarks import INITIAL_TASKS, skillsbench_manifest

    root = tmp_path.resolve()
    entries = []
    for name, _domain, _difficulty in INITIAL_TASKS:
        for relative in (
            "task.md",
            "environment/workspace/input.txt",
            "oracle/solve.sh",
            "verifier/test.py",
            "environment/Dockerfile",
            "environment/api-simulator/server.ts",
            "environment/skills/test/SKILL.md",
            "environment/skills/test/LICENSE.txt",
        ):
            path = "tasks/" + name + "/" + relative
            raw = ("synthetic importer fixture " + relative).encode()
            dest = root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
            blob = b"blob " + str(len(raw)).encode() + bytes([0]) + raw
            entries.append(
                dict(
                    path=path,
                    sha256=hashlib.sha256(raw).hexdigest(),
                    sha=hashlib.sha1(blob).hexdigest(),
                    size=len(raw),
                )
            )
    inventory = root / "source-inventory.json"

    def freeze():
        inventory.write_text(json.dumps(dict(revision=SKILLSBENCH_REVISION, assets=entries)))
        return hashlib.sha256(inventory.read_bytes()).hexdigest()

    pin = freeze()
    value = skillsbench_manifest(root, pin)
    assert len(value.tasks) == 6 and all(t.rights_review_ref is None for t in value.tasks)
    assert {t.domain for t in value.tasks} == {"document-data", "software-engineering"}
    task = value.tasks[0]
    assert next(a for a in task.assets if a.path.endswith("server.ts")).role == "environment"
    assert next(a for a in task.assets if a.path.endswith("LICENSE.txt")).role == "license"
    with pytest.raises(ValueError, match="inventory changed"):
        skillsbench_manifest(root, "a" * 64)
    entries[0]["sha"] = "a" * 40
    with pytest.raises(ValueError, match="Git blob differs"):
        skillsbench_manifest(root, freeze())
    entries[0]["sha"] = hashlib.sha1(
        b"blob "
        + str(entries[0]["size"]).encode()
        + bytes([0])
        + (root / entries[0]["path"]).read_bytes()
    ).hexdigest()
    entries.append(entries[0])
    with pytest.raises(ValueError, match="duplicate"):
        skillsbench_manifest(root, freeze())
    entries.pop()
    entries[:] = [
        e
        for e in entries
        if not e["path"].startswith("tasks/financial-modeling-qa/environment/workspace/")
    ]
    with pytest.raises(ValueError, match="inputs are external"):
        skillsbench_manifest(root, freeze())
