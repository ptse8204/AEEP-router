"""Bind retained document controls to exact public task archives and settled receipts."""

import base64
import io
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from zipfile import ZipFile

from run_workbook_reference import verify_phase
from stage_protected_inputs import tree
from stage_repository_transport import HERE, ROOT, WORK, digest, read

from aeep.assessment.models import content_digest
from aeep.models import ExecutionReceipt
from aeep_toolkit.benchmarks import BenchmarkPack, task_input

PACK = WORK / "independent-document-pack"
FORMULA = WORK / "formula-protected-execution"
WORKBOOK = WORK / "xlsx-recover-preparation"
ECONOMIC = WORK / "economic-reference-execution"
SOURCE_REVISION = "9a1f4dd5f7659f75707435da3ce854b6e48321d1"


def get(path):
    return json.loads(path.read_bytes())


def pin(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": digest(path.read_bytes())}


def public_members(raw, expected):
    with ZipFile(io.BytesIO(raw)) as archive:
        if len(archive.infolist()) != len(expected) or set(archive.namelist()) != set(expected):
            raise ValueError("unexpected or protected asset is present in public archive")
        observed = {path: digest(archive.read(path)) for path in archive.namelist()}
    if observed != expected:
        raise ValueError("public archive member changed")
    return observed


def bind_pack():
    intake = get(HERE / "independent-document-pack-intake.json")
    pack = BenchmarkPack.model_validate_json(read(PACK / "pack.json", intake["manifest_file_sha256"]))
    if (pack.source.revision != SOURCE_REVISION
            or content_digest(pack.model_dump(mode="json")) != intake["pack_sha256"]):
        raise ValueError("retained pack version changed")
    rows = {}
    for task in pack.tasks:
        staged = intake["tasks"][task.task_id]
        value = task_input(pack, PACK / "pack-assets", task.task_id)
        data = base64.b64decode(value["task_archive_b64"], validate=True)
        if (len(data) != staged["archive_bytes"]
                or digest(data) != staged["archive_sha256"] or staged["rights_record_registered"]):
            raise ValueError("existing archive or authority scope changed")
        rows[task.task_id] = {
            "public_archive_sha256": digest(data),
            "public_members": public_members(data, {
                item.path: item.sha256 for item in task.assets if item.role in ("instruction", "input")
            }),
            "input_paths": {Path(item.path).name: item.sha256 for item in task.assets if item.role == "input"},
            "upstream_verifier_sha256": next(item.sha256 for item in task.assets if item.path.endswith("/test_outputs.py")),
            "provider_disclosure_authorized": False,
        }
    return rows


def bind_receipts(directory, expected_review, refs):
    ledger = get(directory / "ledger.json")
    operations = {row["operation_id"]: row for row in ledger["operations"]}
    checked = []
    db_path = directory / "receipts.sqlite3"
    with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        for rid, key, observation in refs:
            (raw,) = db.execute("SELECT payload_json FROM receipts WHERE receipt_id = ?", (rid,)).fetchone()
            receipt = ExecutionReceipt.model_validate_json(raw)
            (state, reservation) = db.execute(
                "SELECT state,reserved_json FROM assessment_operations WHERE id = ?", (receipt.action_id,)
            ).fetchone()
            record = operations[receipt.action_id]
            if (state != "complete" or record["elapsed_seconds"] is None
                    or record["reserved"] != json.loads(reservation)
                    or record["reserved"]["max_model_turns"] != 0
                    or receipt.metadata.get("review_sha256") != expected_review
                    or receipt.metadata.get("container_absent") is not True
                    or receipt.metadata.get(key) != observation):
                raise ValueError("canonical protected receipt or settlement changed")
            checked.append({
                "receipt_id": rid, "receipt_ref": content_digest(receipt), "operation": receipt.action_id,
                "elapsed_seconds": record["elapsed_seconds"], "container_absent_at_settlement": True,
            })
    if len(checked) != len(operations) or len({row["operation"] for row in checked}) != len(operations):
        raise ValueError("retained operation inventory changed")
    return {"ledger": pin(directory / "ledger.json"), "receipts": checked}


def bind_workbook(value):
    old = get(HERE / "workbook-reference-result.json")
    review = WORKBOOK / "reference-bootstrap-correction.json"
    exact = pin(review)["sha256"]
    if exact != old["operation_review_sha256"] or old["case_exposed_to_agent"]:
        raise ValueError("workbook protected review changed")
    pins = get(review)["pins"]
    published = ("nasa_budget_incomplete.xlsx", "test_outputs.py")
    selected = {Path(name).name: sha for name, sha in pins.items() if Path(name).name in published}
    if selected != value["input_paths"] | {"test_outputs.py": value["upstream_verifier_sha256"]}:
        raise ValueError("workbook verifier did not bind the same source data")
    for filename, sha in selected.items():
        read(WORKBOOK / "reviewed-protected-mount" / filename, sha)
    roles = old["test_runs"]
    if any(not verify_phase(role, item["observation"], 19) for role, item in roles.items()):
        raise ValueError("workbook observation does not meet its historical contract")
    directory = WORKBOOK / ("reference-execution-" + exact[:12])
    receipts = bind_receipts(directory, exact, [
        (item["receipt_id"], "observation", item["observation"]) for item in roles.values()
    ])
    rights = WORKBOOK / "local-rights-review.json"
    scope = get(rights)
    if (scope["task_id"] != "xlsx-recover-data" or scope["source_revision"] != SOURCE_REVISION
            or scope["local_execution_allowed"] is not True or scope["provider_disclosure_allowed"] is not False
            or any(scope["assets"].get(path) != sha for path, sha in value["public_members"].items())):
        raise ValueError("workbook local-only asset scope differs")
    return value | receipts | {
        "review": pin(review), "local_only_asset_review": pin(rights),
        "reference_assertions_passed": roles["reference"]["observation"]["passed"],
        "historical_role_outcomes": {name: item["observation"] for name, item in roles.items()},
        "ordinary_supplemental_preservation_verified": False,
    }


def bind_formula(value, old):
    review = WORK / "formula-protected-operation-review.json"
    exact = pin(review)["sha256"]
    if exact != old["review_sha256"] or pin(FORMULA / "ledger.json")["sha256"] != old["ledger_sha256"]:
        raise ValueError("formula protected review or ledger changed")
    roots = get(review)["staged"]["sha256_by_staged_root"]
    runtime = Path("/private/tmp/aeep-c13-formula-check-20261116/renderer")
    if content_digest(tree(runtime)) != roots[str(runtime)]:
        raise ValueError("offline formula renderer context drifted")
    lock = get(runtime / "protected-fixtures/protected-fixture-lock.json")
    if (lock["files"]["latex_paper.pdf"] != value["input_paths"]["latex_paper.pdf"]
            or lock["source_sha256"] != value["upstream_verifier_sha256"]):
        raise ValueError("formula input or upstream verifier differs")
    roles = {name: item["observation"] for name, item in old["roles"].items()}
    if {name: item["grade"] for name, item in roles.items()} != {
        "reference": 1, "wrong-value": 0, "incomplete": 0, "renderer-unavailable": None,
    }:
        raise ValueError("formula result lost its infrastructure distinction")
    if set(roles["reference"]["outcomes"]) != set(lock["identities"]):
        raise ValueError("formula reference assertions changed")
    receipts = bind_receipts(FORMULA, exact, [
        (item["receipt_id"], "observation", item["observation"]) for item in old["roles"].values()
    ])
    return value | receipts | {
        "review": pin(review), "reference_assertions_passed": roles["reference"]["collected"],
        "source_and_adaptation_record": pin(HERE / "formula-verifier-assessment.json"),
        "historical_role_grades": {name: item["grade"] for name, item in roles.items()},
        "ordinary_runtime_verified": False,
    }


def bind_economic(value, old):
    review = WORK / "economic-reference-operation-review.json"
    exact = pin(review)["sha256"]
    source = get(HERE / "economic-case-review.json")
    if (exact != old["review_sha256"] or pin(ECONOMIC / "ledger.json")["sha256"] != old["ledger_sha256"]
            or value["input_paths"] != {row["name"]: row["sha256"] for row in source["input_assets"]}
            or get(review)["files"]["upstream_test.py"] != value["upstream_verifier_sha256"]):
        raise ValueError("economic review bytes or calculated input bindings changed")
    observation = old["roles"]["economic"]
    if observation["observation"] != get(review)["expected_observations"]:
        raise ValueError("economic controls differ from their reviewed expectations")
    receipts = bind_receipts(ECONOMIC, exact, [
        (observation["receipt_id"], "observations", observation["observation"])
    ])
    ordinary = HERE / "economic-ordinary-initial-result.json"
    if get(ordinary)["verified"] is not False:
        raise ValueError("ordinary economic continuation state changed")
    return value | receipts | {
        "review": pin(review), "ordinary_launch": pin(ordinary),
        "source_and_adaptation_record": pin(HERE / "economic-case-review.json"),
        "reference_assertions_passed": len(observation["observation"]["reference"]["observations"]),
        "historical_upstream_and_precision_grades": {
            role: {"upstream_pass": row["upstream_valid"], "protected_grade": row["protected_grade"]}
            for role, row in observation["observation"].items()
        },
        "ordinary_runtime_verified": False,
    }


def audit():
    rows = bind_pack()
    old = get(HERE / "protected-reference-group-result.json")["results"]
    rows["xlsx-recover-data"] = bind_workbook(rows["xlsx-recover-data"])
    rows["latex-formula-extraction"] = bind_formula(rows["latex-formula-extraction"], old["formula"])
    rows["econ-detrending-correlation"] = bind_economic(rows["econ-detrending-correlation"], old["economic"])
    return {
        "schema_version": "aeep.c13.document-grader-evidence.v1", "source_revision": SOURCE_REVISION,
        "pack": pin(PACK / "pack.json"), "tasks": rows,
        "settled_protected_operations_verified": sum(len(row["receipts"]) for row in rows.values()),
        "native_cohort_staging_scope": "The current compact native-score profile binds ExtractBench PDFs and output.json. These SkillsBench tasks retain their prepared ordinary task bindings.",
        "scope": "Actual retained protected observations and deterministic public archives. Ordinary recipe runtime verification, asset-use review and formal assignment remain open.",
        "formal_cases_adopted": 0, "upstream_replays": 0, "new_model_turns": 0,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True, allow_nan=False))
