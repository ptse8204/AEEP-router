"""Make prospective repository cases reusable through the ordinary artifact bridge."""

import argparse
import base64
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path, PurePosixPath

from audit_formal_inputs import repository

from aeep.assessment.adapters import prepare_context
from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import (
    SuiteInput,
    archive_files,
    compressed_patch_artifact,
    pack_files,
)
from aeep.assessment.repository_tasks import RepositoryPatch, checked_files
from aeep.executors.base import ExecutionContext
from aeep.models import ActionRequest, ExecutorSpec

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
WORK = ROOT / ".aeep/completion-20261116"
STAGED = WORK / "patch-batch-verified"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path, expected):
    if path.is_symlink() or path.resolve() != path or not path.is_file():
        raise ValueError("asset must be a regular canonical file")
    raw = path.read_bytes()
    if digest(raw) != expected:
        raise ValueError(f"asset drift: {path.name}")
    return raw


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as file:
        file.write(value)
    return {"sha256": digest(value), "bytes": len(value)}


def encode(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def bind_row(row, lead, target, staged, original_archive):
    case = row["case_id"]
    if (
        repository(row["repository"]) != repository(lead["repository"])
        or row["revision"] != lead["base_commit"]
        or row["metadata_semantic_sha256"] != lead["metadata_semantic_sha256"]
    ):
        raise ValueError("pinned issue identity changed")
    assets = {
        item["file"]: read(staged / case / item["file"], item["sha256"]) for item in row["assets"]
    }
    if {name: len(raw) for name, raw in assets.items()} != {
        entry["file"]: entry["bytes"] for entry in row["assets"]
    }:
        raise ValueError("staged asset size differs")
    source, overlay = (
        archive_files(assets[name], large=True) for name in ("source.tar.gz", "tests.tar.gz")
    )
    if any(source.get(path) == content for path, content in overlay.items()):
        raise ValueError("protected overlay matches the same location in the public archive")
    roots = [PurePosixPath(value) for value in row["test_roots"]]
    if (
        not all(any(PurePosixPath(path).is_relative_to(root) for root in roots) for path in overlay)
        or set(row["editable_changes"]) & overlay.keys()
        or not set(row["test_modules"]) <= source.keys() | overlay.keys()
    ):
        raise ValueError("protected overlay boundary differs")
    issue = json.loads(
        read((ROOT / original_archive).with_name("row.json"), row["dataset_row_sha256"])
    )
    identities = json.loads(assets["required.json"])
    if (
        identities != {"fail_to_pass": issue["FAIL_TO_PASS"], "pass_to_pass": issue["PASS_TO_PASS"]}
        or len(identities["fail_to_pass"]) != row["required_issue_tests"]
        or len(identities["pass_to_pass"]) != row["required_preservation_tests"]
    ):
        raise ValueError("required grade identities changed")
    actual_input = SuiteInput(
        task_id=case,
        task=issue["problem_statement"]
        + ("\n\n" + issue["interface"] if issue.get("interface") else ""),
        family=row["family"],
        source_sha256=digest(assets["source.tar.gz"]),
        editable_paths=row["editable_changes"],
    )
    public_root = target / "public"
    source_name = actual_input.source_sha256 + ".tar.gz"
    public_pin = write(public_root / source_name, assets["source.tar.gz"])
    input_json = actual_input.model_dump(mode="json")
    spec = ExecutorSpec(
        id="repository-intake",
        capability="assessment.repository.suite@1",
        description="Inert ordinary input mapping check",
        kind="command",
        config={
            "assessment_adapter": {
                "read_only_roots": [str(public_root)],
                "input_transform": "repository_archive:2",
            }
        },
    )
    context = ExecutionContext(
        request=ActionRequest(capability=spec.capability, input=input_json),
        spec=spec,
        estimate=spec.estimate,
        attempt=1,
        approved_side_effect=spec.side_effect,
    )
    mapped, adapter = prepare_context(context)
    assert adapter is not None and adapter.input_transform == "repository_archive:2"
    transformed = mapped.request.input
    assert set(transformed) == input_json.keys() | {"base_sha256", "source_b64"}
    assert base64.b64decode(transformed["source_b64"], validate=True) == assets["source.tar.gz"]
    edits = json.loads(assets["repair.json"])
    checked_files(edits, max_bytes=4_000_000)
    assert set(edits) == set(row["editable_changes"]) and edits.keys() <= source.keys()
    patch = RepositoryPatch(base_sha256=transformed["base_sha256"], files=edits)
    assert patch.base_sha256 == content_digest(input_json)
    compact = compressed_patch_artifact(patch)
    # Pack the same archive bytes expected by the protected callback after decoding the reference.
    repaired = pack_files(
        {**source, **{name: body.encode() for name, body in edits.items()}, **overlay}, large=True
    )
    private = target / "protected" / case
    result = {
        "input": input_json,
        "source_repository": repository(row["repository"]),
        "source_revision": row["revision"],
        "public_source": {"name": source_name, **public_pin},
        "base_sha256": patch.base_sha256,
        "reference_archive_sha256": digest(repaired),
        "protected_tests": write(private / "tests.tar.gz", assets["tests.tar.gz"]),
        "reference": write(private / "reference.json", encode(compact)),
        "required_identities": write(private / "required.json", assets["required.json"]),
        "test_roots": row["test_roots"],
        "test_modules": row["test_modules"],
        "published_python": row["published_python"],
        "runtime_binding": None,
        "protected_runtime_verified": False,
        "formal_stage": None,
    }
    return result


def main(target, *, include_rebound=False):
    intake = json.loads((HERE / "repository-patch-batch-intake.json").read_bytes())
    source = json.loads(read(STAGED / "private-index.json", intake["private_index_sha256"]))
    leads = {
        item["instance_id"]: item
        for item in json.loads(
            read(WORK / "source-bound-leads.json", source["source_inventory_sha256"])
        )
    }
    old = json.loads((HERE / "formal-transport-preparation.json").read_bytes())
    pool = json.loads(read(ROOT / old["prepared_pool_relative_path"], old["prepared_pool_sha256"]))
    prior = {(repository(row["source_repository"]), row["source_revision"]) for row in pool}
    rows = [row for row in source["records"] if row["status"] == "ready_for_runtime_review"]
    if len(rows) != intake["ready_for_runtime_review"]:
        raise ValueError("existing case count changed")
    scoped = [(row, STAGED, leads[row["case_id"]]["source_bindings"][0]["archive"]) for row in rows]
    if include_rebound:
        rebound = json.loads((HERE / "cached-repository-rebinding.json").read_bytes())
        path = ROOT / rebound["retained_private_stage_path"]
        raw = json.loads(read(path, rebound["private_stage_results_sha256"]))
        additional = [row for row in raw if row["status"] == "ready_for_runtime_review"]
        if len(additional) != rebound["provisional_staged_cases"]:
            raise ValueError("rebound case count differs")
        scoped += [
            (row, path.parent / "staged", leads[row["case_id"]]["archives"][0])
            for row in additional
        ]
    candidates = {(repository(row["repository"]), row["revision"]) for row, _, _ in scoped}
    if len(candidates) != len(scoped) or candidates & prior:
        raise ValueError("source-origin overlap")
    target = target.resolve()
    if target.parent != WORK or shutil.disk_usage(WORK).free < 52 * 1024**3:
        raise ValueError("use a fresh output under the bounded private workspace")
    target.mkdir(mode=0o700)
    records = [
        bind_row(row, leads[row["case_id"]], target, staged, archive)
        for row, staged, archive in scoped
    ]
    public = list((target / "public").iterdir())
    assert len(public) == len(records) and all(path.name.endswith(".tar.gz") for path in public)
    private_index = write(target / "private-index.json", encode(records))
    coverage = Counter(row["input"]["family"] for row in pool + records)
    assert set(coverage) == {"single-file-repair", "multi-file-repair", "contract-audit"}
    result = {
        "schema_version": "aeep.c13.repository-worker-transport.v1",
        "input_index_sha256": intake["private_index_sha256"],
        "private_index_relative_path": (target / "private-index.json").relative_to(ROOT).as_posix(),
        "private_index_sha256": private_index["sha256"],
        "existing_worker_transform": "repository_archive:2",
        "patch_field": "patch_gzip_b64",
        "public_archives_verified": len(public),
        "protected_assets_outside_public_root": len(records) * 3,
        "provisional_counts_if_all_cases_survive_runtime_review": dict(coverage),
        "minimum_missing_rows_in_optimistic_pool": 141 - sum(coverage.values()),
        "minimum_holdout_rows_still_missing_by_family": {
            family: max(0, 35 - count) for family, count in coverage.items()
        },
        "qualification_training_and_independence_may_increase_shortfall": True,
        "formal_cases_adopted": 0,
        "upstream_test_executions": 0,
        "provider_transfers": 0,
    }
    write(target / "evidence.json", encode(result))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-rebound", action="store_true")
    args = parser.parse_args()
    main(args.output, include_rebound=args.include_rebound)
