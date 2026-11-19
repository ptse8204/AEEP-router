"""Bind the saved WASDE reference and rehearse the ordinary protected protocol locally."""

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from extractbench_recipe_guest import OUTPUT_FIELD
from prepare_extractbench_recipe import definition
from stage_repository_transport import HERE, ROOT, WORK, digest, encode, read, write

from aeep.assessment.extensions import grader_results
from aeep.assessment.models import DocumentTaskInput, RecipeDefinition, content_digest
from aeep.registry import validate_json

CALIBRATION = WORK / "wasde-reference-calibration-20261119"
DRAFT = WORK / "reviewed-document-pack-draft-20261119"
OUTPUT = WORK / "wasde-recipe-protocol-20261119"
TASK_PIN = "95cfe3c4a468d9b71e50f659ee38d8dbbcbe9954c87d0163d7292f4741f44e29"
REFERENCE_PIN = "6b9a724e01d5654a574ba2cfa7424f85850c3a1ccd67fa1d97405a3a0b25bdfc"
SCHEMA_PIN = "464a57fd6a3c63a3beea398562159e7364ec568a71cf7e4a727e3bdae968a1d8"
SCRIPTS = ("wasde_recipe_guest.py", "extractbench_recipe_guest.py")


def ref(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": digest(path.read_bytes())}


def recipe_for(task, guest_pin, bridge_pin):
    # Reuse v7's observation envelope and fingerprint the actual binary metric.
    recipe = definition(task.benchmark_pack_sha256, (SimpleNamespace(task_id=task.task_id),), bridge_pin)
    data = recipe.model_dump(mode="json")
    data.update(
        recipe_id="wasde-677-local-exact-match-v1",
        description="Binary exact match of two ordered tables from the USDA WASDE-677 release.",
        input_schema=DocumentTaskInput.model_json_schema(),
        generator_config={
            **data["generator_config"], "score_metric": "ordered_json_exact_match",
            "calibration_only": True,
        },
        dependencies={
            "benchmark_pack": task.benchmark_pack_sha256, "recipe_guest": guest_pin,
            "transport_bridge": bridge_pin, "protected_reference": REFERENCE_PIN, "schema": SCHEMA_PIN,
        },
    )
    extension = data["extension"]
    extension["template_families"] = ["usda-wasde:world-and-us-grains"]
    for key, mode in (("reference", "reference"), ("grader", "grade")):
        extension[key]["config"]["argv"] = [
            "python3", "-I", "-B", "/opt/aeep-wasde/wasde_recipe_guest.py", mode,
            "--support", "/opt/aeep-wasde",
        ]
    return RecipeDefinition.model_validate(data)


def run_guest(scratch, mode, request, *, failed=False):
    command = [
        sys.executable, "-I", "-B", str(scratch / SCRIPTS[0]), mode, "--support", str(scratch),
    ]
    result = subprocess.run(
        command, input=encode(request), capture_output=True, timeout=5, cwd=scratch,
        env={"HOME": str(scratch), "LC_ALL": "C", "PATH": os.defpath},
        check=False,
    )
    if failed:
        if result.returncode == 0 or result.stdout:
            raise ValueError("protected infrastructure failure became a task score")
        return None
    if result.returncode != 0:
        raise ValueError("prepared guest failed at the protocol boundary")
    return json.loads(result.stdout)


def artifact(body):
    return {OUTPUT_FIELD: base64.b64encode(body).decode("ascii")}


def verify(root, task, recipe, reference):
    extension = recipe.extension
    action = task.model_dump(mode="json")
    truth = {"input_sha256": content_digest(action)}
    validate_json(action, recipe.input_schema, label="WASDE probe input")
    validate_json(truth, extension.truth_schema, label="WASDE probe truth")
    response = run_guest(root, "reference", {"inputs": [action]})
    good, = response["outputs"]
    validate_json(good, recipe.output_schema, label="WASDE reference output")
    if good != artifact(reference):
        raise ValueError("protected reference stdout or base64 wrapper changed")
    expected = json.loads(reference)
    wrong, missing, unordered, mistyped = (deepcopy(expected) for _ in range(4))
    wrong["world"][0]["output"] = "0.00"
    missing["united_states"].pop()
    unordered["world"].reverse()
    mistyped["world"][0]["output"] = float(expected["world"][0]["output"])
    shuffled_keys = {name: expected[name] for name in reversed(expected)}
    checks = {
        "exact_reference": (good, 1.0, ""),
        "different_group_key_order": (artifact(encode(shuffled_keys)), 1.0, ""),
        **{name: (artifact(encode(value)), 0.0, "inexact_extraction") for name, value in (
            ("wrong_cell", wrong), ("missing_row", missing), ("row_order_changed", unordered),
            ("wrong_value_type", mistyped),
        )},
        "duplicate_property": (artifact(b'{"world":[],' + reference.lstrip()[1:]),
                               0.0, "invalid_submission"),
        "nonfinite_json": (artifact(b'{"world":NaN}'), 0.0, "invalid_submission"),
        "malformed_base64": ({OUTPUT_FIELD: "??"}, 0.0, "invalid_submission"),
        "malformed_utf8": (artifact(b"\xff"), 0.0, "invalid_submission"),
    }
    results = {}
    for name, (prediction, score, reason) in checks.items():
        row = {"input": action, "expected": truth, "output": prediction}
        result, = grader_results(run_guest(root, "grade", {"examples": [row]}), extension, 1)
        if (result.valid, result.quality_score, result.detail) != (bool(score), score, reason):
            raise ValueError(f"WASDE grade contract failed: {name}")
        results[name] = {"score": score, "valid": result.valid, "reason": reason or None}
    row = {"input": action, "expected": truth, "output": good}
    run_guest(root, "grade", {"examples": [row | {"expected": {"input_sha256": "0" * 64}}]}, failed=True)
    altered = action | {"task_archive_sha256": "0" * 64}
    run_guest(root, "grade", {"examples": [row | {"input": altered, "expected": {
        "input_sha256": content_digest(altered),
    }}]}, failed=True)
    protected = root / "cases" / task.task_id / "verifier/reference.test.json"
    protected.write_bytes(reference + b" ")
    run_guest(root, "grade", {"examples": [row]}, failed=True)
    return results, truth


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline-rehearsal", action="store_true", required=True)
    parser.parse_args()
    retained = json.loads(read(DRAFT / "usda-stage-smoke.json", TASK_PIN))
    task = DocumentTaskInput.model_validate(retained["output_descriptor"])
    schema = json.loads(read(CALIBRATION / "schema.json", SCHEMA_PIN))
    reference = read(CALIBRATION / "protected-reference.json", REFERENCE_PIN)
    validate_json(json.loads(reference), schema, label="publisher-cross-checked WASDE output")
    scripts = {name: (HERE / name).read_bytes() for name in SCRIPTS}
    recipe = recipe_for(task, *(digest(scripts[name]) for name in SCRIPTS))
    bindings = {content_digest(task): {
        "case": task.task_id, "reference_sha256": REFERENCE_PIN, "oracle_sha256": REFERENCE_PIN,
    }}
    with tempfile.TemporaryDirectory(prefix="aeep-wasde-protocol-") as temp:
        root = Path(temp).resolve()
        for name, body in scripts.items():
            write(root / name, body)
        write(root / "bindings.json", encode(bindings))
        for path in ("verifier/reference.test.json", "controls/oracle.json"):
            write(root / "cases" / task.task_id / path, reference)
        checks, truth = verify(root, task, recipe, reference)
    OUTPUT.mkdir(mode=0o700)
    write(OUTPUT / "recipe.json", encode(recipe.model_dump(mode="json")))
    write(OUTPUT / "bindings.json", encode(bindings))
    write(OUTPUT / "case-envelope.json", encode({"input": task.model_dump(mode="json"), "truth": truth}))
    write(OUTPUT / "result.json", encode({
        "schema_version": "aeep.c13.wasde-recipe-protocol-rehearsal.v1",
        "evidence_scope": "first-party subprocess and ordinary v7 grader decoder",
        "score_metric": "ordered_json_exact_match",
        "checks": checks,
        "infrastructure_errors_without_grade": ["different_truth", "different_archive", "reference_drift"],
        "source_pins": [ref(HERE / name) for name in SCRIPTS],
        "task_descriptor": ref(DRAFT / "usda-stage-smoke.json"),
        "protected_reference": ref(CALIBRATION / "protected-reference.json"),
        "schema": ref(CALIBRATION / "schema.json"),
        "recipe": ref(OUTPUT / "recipe.json"),
        "bindings": ref(OUTPUT / "bindings.json"),
        "case_envelope": ref(OUTPUT / "case-envelope.json"),
        "required_before_offline_dispatch": [
            "restage document pack using the actual guest as its protected verifier",
            "bind reviewed protected runtime and record case-specific asset rights",
        ],
        "protected_containers_started": 0,
        "model_turns": 0,
        "formal_assignments": 0,
        "comparisons_paused": True,
        "waza_excluded": True,
    }))


if __name__ == "__main__":
    main()
