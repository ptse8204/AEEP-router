"""Freeze local v7 definitions and rehearse the protected carrier without upstream execution."""

import argparse
import base64
import io
import json
import stat
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from extractbench_recipe_guest import (
    FAILURES,
    MAX_ENCODED_PREDICTION,
    MAX_PREDICTION,
    OUTPUT_FIELD,
    evaluate,
)
from extractbench_recipe_guest import ROOT as GUEST_ROOT
from stage_repository_transport import HERE, ROOT, WORK, digest, read

from aeep.assessment.extensions import bounded_batches, grader_results
from aeep.assessment.models import RecipeDefinition, content_digest
from aeep.models import ExecutorSpec, ManagedHostArtifact
from aeep.registry import validate_json
from aeep_toolkit.benchmarks import BenchmarkTask, asset_path

PUBLIC_PIN = "1d1deab7eec27adc85f8bce3907b345b825493fc562aac874af68b29b71132ca"
PROTECTED_PIN = "10c71bc17c7961e2268c30140957bd22967d2869b63415258762d6b062a61141"
CAPABILITY = "assessment.extractbench@1"
PUBLIC = WORK / "extractbench-cfpb-source-review"


def write(file, value):
    with file.open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    return digest(file.read_bytes())


def worker_input(task, source, pack_ref):
    buffer = io.BytesIO()
    paths = set()
    instruction = None
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for asset in sorted(task.assets, key=lambda asset: asset.path):
            if asset.role not in ("input", "instruction"):
                continue
            body = asset_path(source, asset).read_bytes()
            if digest(body) != asset.sha256:
                raise ValueError("public input changed while archiving")
            paths.add(asset.path)
            if asset.role == "instruction":
                instruction = body.decode("utf-8")
            info = ZipInfo(asset.path, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = (stat.S_IFREG | 0o444) << 16
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, body)
    if instruction is None or paths != {"instruction.md", "environment/document.pdf", "environment/schema.json"}:
        raise ValueError("worker archive includes out-of-scope inputs")
    raw = buffer.getvalue()
    return {
        "task_id": task.task_id, "task": instruction,
        "benchmark_pack_sha256": pack_ref, "task_archive_sha256": digest(raw),
        "task_archive_b64": base64.b64encode(raw).decode(), "output_paths": list(task.output_paths),
    }


def spec(mode, argv):
    return ExecutorSpec(
        id=f"extractbench.{mode}", capability=CAPABILITY, kind="command",
        description=f"Contained ExtractBench {mode}",
        config={"argv": ["python3", "-I", "-B", *argv], "argv_literal": True,
                "stdin_json": True, "output": {"type": "json"},
                "timeout_seconds": 30 if mode != "grade" else 35,
                "max_output_bytes": 800_000 if mode == "reference" else 1024},
    )


def definition(pack_ref, cases, bridge_pin):
    task_ids = [case.task_id for case in cases]
    return RecipeDefinition.model_validate({
        "schema_version": "assessment.recipe.v2",
        "recipe_id": "extractbench-cfpb-integration-v1",
        "capability": CAPABILITY,
        "description": "Locally adapted protected ExtractBench value F1 with exact-match correctness.",
        "input_schema": {"type": "object", "additionalProperties": False,
                         "required": ["task", "task_id", "benchmark_pack_sha256", "task_archive_b64",
                                      "task_archive_sha256", "output_paths"], "properties": {
                             "task": {"type": "string"}, "task_id": {"enum": task_ids},
                             "benchmark_pack_sha256": {"const": pack_ref},
                             "task_archive_b64": {"type": "string", "maxLength": 400_000},
                             "task_archive_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                             "output_paths": {"const": ["output.json"]},
                         }},
        "output_schema": {"type": "object", "additionalProperties": False,
                          "required": [OUTPUT_FIELD], "properties": {
                              OUTPUT_FIELD: {"type": "string", "minLength": 1, "maxLength": MAX_ENCODED_PREDICTION},
                          }},
        "generator": "contained_json:1", "grader": "contained_json:1", "extractor": "structural_json:1",
        "generator_config": {"integration_only": True, "official_reproduction": False},
        "dependencies": {"benchmark_pack": pack_ref, "protected_preparation": PROTECTED_PIN,
                         "recipe_guest": bridge_pin},
        "variations": task_ids, "exclusions": ["formal cohort", "candidate usefulness", "selection usefulness"],
        "extension": {
            "schema_version": "assessment.recipe-extension.v7",
            "generator": spec("generate", ["-c", "raise SystemExit(2)"]),
            "reference": spec("reference", [str(GUEST_ROOT / "extractbench_recipe_guest.py"), "reference"]),
            "grader": spec("grade", [str(GUEST_ROOT / "extractbench_recipe_guest.py"), "grade"]),
            "independent_fixtures": [], "transformed_fixtures": [],
            "fault_outputs": [{OUTPUT_FIELD: "e30="}],
            "truth_schema": {"type": "object", "additionalProperties": False,
                             "required": ["input_sha256"],
                             "properties": {"input_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"}}},
            "failure_codes": FAILURES,
            "feature_rules": {"task": {"path": "/task_id", "operation": "enum", "values": task_ids}},
            "variation_features": {name: {"task": name} for name in task_ids},
            "template_families": ["extractbench:cfpb-closing-disclosure"],
        },
    })


def rehearse(recipe, output, cases, bindings):
    assert recipe.extension is not None
    checks = 0
    for case in cases:
        value, case_dir = case["input"], output / "cases" / case["input"]["task_id"]
        reference = evaluate("reference", {"inputs": [value]}, bindings, output, None)["outputs"][0]
        validate_json(reference, recipe.output_schema, label="protected reference output")
        for name, score, status in (("perfect", 1.0, "scored"), ("partial", 0.625, "scored"),
                                    ("inexact", 0.0, "scored"), ("invalid", 0.0, "invalid_submission")):
            artifact = reference if name == "perfect" else {OUTPUT_FIELD: "e30="} if name != "invalid" else None
            example = {"input": value, "output": artifact, "expected": case["truth"]}
            assert bounded_batches([example], separate=True) == [[example]]

            def observer(support, _deps, prediction, pinned_reference, _work, *,
                         case_dir=case_dir, artifact=artifact, score=score, status=status):
                assert support == case_dir and pinned_reference.parent == support / "verifier"
                assert prediction.exists() == (artifact is not None)
                if artifact is not None:
                    assert prediction.read_bytes() == base64.b64decode(artifact[OUTPUT_FIELD], validate=True)
                return {"status": status, "value_f1": score, "perfect": int(score == 1), "exit_code": 0}

            wire = evaluate("grade", {"examples": [example]}, bindings, output, observer)
            grade = grader_results(wire, recipe.extension, 1)[0]
            assert grade.quality_score == score and grade.valid is (score == 1)
            checks += 1
        example = {"input": value, "output": reference, "expected": case["truth"]}
        for malformed in (
            {"status": "infrastructure_error", "value_f1": None, "perfect": None, "exit_code": 2},
            {"status": "timeout", "value_f1": None, "perfect": None, "exit_code": None},
            {"status": "scored", "value_f1": 0.625, "perfect": 1, "exit_code": 0},
        ):
            try:
                evaluate("grade", {"examples": [example]}, bindings, output, lambda *_, reply=malformed: reply)
            except ValueError:
                checks += 1
            else:
                raise ValueError("invalid native observation supplied a grade")
    return checks


def stage(output):
    if output.exists() or output.resolve() != output or output.parent != WORK / "native-score-contract":
        raise ValueError("use a fresh private output in the native-score workspace")
    original = json.loads(read(HERE / "extractbench-cfpb-source-review.json", PUBLIC_PIN))
    protected = json.loads(read(HERE / "extractbench-cfpb-protected-preparation.json", PROTECTED_PIN))
    declared_tasks = [original["task"], *[item["task"] for item in original["additional_verified_source_documents"].values()]]
    tasks = [BenchmarkTask.model_validate(item) for item in declared_tasks]
    packed = content_digest({"public_source": PUBLIC_PIN, "tasks": declared_tasks})
    bridge = digest((HERE / "extractbench_recipe_guest.py").read_bytes())
    recipe = definition(packed, tasks, bridge)
    assert recipe.extension is not None and recipe.extension.truth_schema is not None
    artifact = ManagedHostArtifact(input_field="task_archive_b64", output_field=OUTPUT_FIELD,
                                   input_name="extractbench-task.zip", output_name="output.json",
                                   max_bytes=MAX_PREDICTION)
    case_inputs, bindings, evidence = [], {}, []
    retained = {row["case"]: row for row in protected["cases"]}
    output.mkdir(mode=0o700)
    for task in tasks:
        origin = PUBLIC if task.task_id == original["task"]["task_id"] else PUBLIC / task.task_id
        value = worker_input(task, origin / "agent", packed)
        if len(base64.b64decode(value[artifact.input_field], validate=True)) > artifact.max_bytes:
            raise ValueError("public archive exceeds managed artifact bounds")
        identity = content_digest(value)
        truth = {"input_sha256": identity}
        validate_json(value, recipe.input_schema, label="pinned public ExtractBench input")
        validate_json(truth, recipe.extension.truth_schema, label="private ExtractBench truth binding")
        support = ROOT / retained[task.task_id]["mount"]
        dst = output / "cases" / task.task_id
        names = {"reference": "verifier/reference.test.json", "oracle": "controls/oracle.json"}
        assets = {asset.path: asset.sha256 for asset in task.assets}
        pins = {"reference": assets["tests/reference.test.json"], "oracle": assets["solution/expected.json"]}
        for role, path in names.items():
            body = read(support / path, pins[role])
            target = dst / path
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as file:
                file.write(body)
        bindings[identity] = {"case": task.task_id, **{role + "_sha256": sha for role, sha in pins.items()}}
        case_inputs.append({"input": value, "truth": truth})
        evidence.append({"case": task.task_id, "task_sha256": identity, "public_archive": value["task_archive_sha256"]})
    return {
        "schema_version": "aeep.c13.extractbench-recipe-preflight.v1",
        "recipe_sha256": content_digest(recipe), "recipe_file_sha256": write(output / "recipe.json", recipe.model_dump(mode="json")),
        "private_bindings_sha256": write(output / "bindings.json", bindings),
        "private_cases_sha256": write(output / "cases.json", case_inputs),
        "source_review_sha256": PUBLIC_PIN, "protected_preparation_sha256": PROTECTED_PIN,
        "guest_sha256": bridge, "cases": evidence,
        "managed_artifact": artifact.model_dump(mode="json"),
        "substituted_score_and_failure_checks": rehearse(recipe, output, case_inputs, bindings),
        "upstream_scores_observed": 0, "formal_cases_adopted": 0, "model_turns": 0,
        "scope": "Three locally staged definitions. Native scorer replies were substituted. The sealed runtime, pack registration, rights and native verification are pending.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    print(json.dumps(stage(parser.parse_args().output), sort_keys=True, indent=2))
