"""Stage a COPY-only protected workbook runtime and ordinary recipe, without executing either."""

import base64
import io
import json
import re
import shutil
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from check_linux_install import HERE, IMAGE, ROOT, WORK, docker, get, put, verified_image
from stage_protected_inputs import freeze

from aeep.assessment.extensions import bounded_batches, grader_name
from aeep.assessment.models import RecipeDefinition, content_digest
from aeep.benchmarking import BenchmarkCase
from aeep.models import ActionRequest, ExecutorSpec, ValidationSpec
from aeep.registry import validate_json
from aeep_toolkit.benchmarks import BenchmarkPack, task_input
from aeep_toolkit.install_runtime import file_digest

TASK_ID = "xlsx-recover-data"
CAPABILITY = "assessment.skillsbench.workbook-recovery@1"
GUEST = "/opt/aeep-workbook-recovery"
TARGET = WORK / "workbook-ordinary-recipe"
SOURCE = WORK / "xlsx-recover-preparation" / "reviewed-protected-mount"
ORIGINAL_REVIEW = SOURCE.parent / "reference-bootstrap-correction.json"
ORIGINAL_RESULT = HERE / "workbook-reference-result.json"
INPUT_NAME = "nasa_budget_incomplete.xlsx"
ARTIFACT_BOUND = 128_000
MAIN_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def filled_with_zero(original):
    buffer = io.BytesIO()
    replacements = 0
    with ZipFile(io.BytesIO(original)) as source, ZipFile(buffer, "w") as destination:
        for member in source.infolist():
            raw = source.read(member)
            if re.fullmatch(r"xl/worksheets/sheet[1-4]\.xml", member.filename):
                root = ElementTree.fromstring(raw)
                for cell in root.iter(MAIN_NS + "c"):
                    if cell.get("t") == "inlineStr" and cell.findtext(
                        MAIN_NS + "is/" + MAIN_NS + "t"
                    ) == "???":
                        cell.set("t", "n")
                        cell.remove(cell.find(MAIN_NS + "is"))
                        ElementTree.SubElement(cell, MAIN_NS + "v").text = "0"
                        replacements += 1
                raw = ElementTree.tostring(root, encoding="utf-8")
            destination.writestr(member, raw)
    if replacements != 15:
        raise ValueError("pinned recovery gaps changed")
    return buffer.getvalue()


def program(role):
    return ExecutorSpec(
        id="skillsbench.workbook-recovery." + role,
        capability=CAPABILITY,
        kind="command",
        description="Reviewed contained workbook " + role,
        config={
            "argv": ["python3", "-I", "-B", f"{GUEST}/guest.py", role],
            "argv_literal": True,
            "stdin_json": True,
            "output": {"type": "json"},
            "timeout_seconds": 45 if role == "grade" else 30,
            "max_output_bytes": 4_096 if role == "grade" else 180_000,
        },
    )


def prepare():
    prior = get(ORIGINAL_RESULT)
    review = get(ORIGINAL_REVIEW)
    observed = prior["test_runs"]["reference"]
    if (
        file_digest(ORIGINAL_REVIEW) != prior["operation_review_sha256"]
        or not observed["passed"] or observed["observation"]["passed"] != 19
        or prior["image"] != IMAGE
        or review["environment"]["read_only_roots"] != [str(SOURCE)]
        or verified_image() != review["layers"]
    ):
        raise ValueError("the verified workbook reference or carrier changed")
    parent = json.loads(docker("image", "inspect", "--format", "{{json .}}", IMAGE))
    tags = parent["RepoTags"]
    if (
        not tags or parent["Config"]["User"] != "65534:65534"
        or not re.fullmatch(r"[a-z0-9._/-]+:[a-zA-Z0-9._-]+", tags[0])
    ):
        raise ValueError("retained carrier lacks a bounded local alias")
    parent_tag = tags[0]
    pins = {name: pin for name, pin in review["pins"].items() if Path(name).is_relative_to(SOURCE)}
    if (
        set(pins) != {str(path) for path in SOURCE.rglob("*") if path.is_file()}
        or any(path.is_symlink() or not (path.is_file() or path.is_dir()) for path in SOURCE.rglob("*"))
        or any(file_digest(Path(name)) != pin for name, pin in pins.items())
    ):
        raise ValueError("retained workbook runtime inventory changed")

    intake = get(HERE / "independent-document-pack-intake.json")
    pack_root = WORK / "independent-document-pack"
    pack_file = pack_root / "pack.json"
    pack = BenchmarkPack.model_validate_json(pack_file.read_bytes())
    value = task_input(pack, pack_root / "pack-assets", TASK_ID)
    if (
        file_digest(pack_file) != intake["manifest_file_sha256"]
        or value["benchmark_pack_sha256"] != intake["pack_sha256"]
        or value["task_archive_sha256"] != intake["tasks"][TASK_ID]["archive_sha256"]
        or value["output_paths"] != ["nasa_budget_recovered.xlsx"]
    ):
        raise ValueError("ordinary workbook asset or output binding changed")

    supplement = get(HERE / "workbook-preservation-preflight.json")
    if (
        file_digest(HERE / "workbook_preservation.py") != supplement["prospective_rule_sha256"]
        or pins[str(SOURCE / INPUT_NAME)] != supplement["input_sha256"]
        or pins[str(SOURCE / "test_outputs.py")] != supplement["upstream_verifier_sha256"]
        or shutil.disk_usage(WORK).free < 52 * 1024**3 + 8 * 1024**2
    ):
        raise ValueError("preservation supplement or disk space changed")
    TARGET.mkdir(mode=0o700)
    context = TARGET / "image"
    context.mkdir(mode=0o700)
    runtime = context / "runtime"
    shutil.copytree(SOURCE, runtime)
    # copytree preserves the read-only source directory modes.
    runtime.chmod(0o700)
    shutil.copyfile(HERE / "workbook_recipe_guest.py", runtime / "guest.py")
    shutil.copyfile(HERE / "workbook_preservation.py", runtime / "workbook_preservation.py")
    binding = {
        "input_digest": content_digest(value),
        "archive_sha256": value["task_archive_sha256"],
        "identities_sha256": observed["observation"]["identity_sha256"],
    }
    put(runtime / "binding.json", binding)
    freeze(runtime)
    dockerfile = context / "Dockerfile"
    dockerfile.write_text(f"FROM {parent_tag}\nCOPY runtime/ {GUEST}/\n")
    inventory = {
        path.relative_to(context).as_posix(): {"sha256": file_digest(path), "bytes": path.stat().st_size}
        for path in sorted(context.rglob("*")) if path.is_file()
    }

    original = (SOURCE / INPUT_NAME).read_bytes()
    artifacts = (original, filled_with_zero(original))
    faults = [{"workbook_b64": base64.b64encode(artifact).decode("ascii")} for artifact in artifacts]
    properties = {name: {"const": item} for name, item in value.items() if name != "task_archive_b64"}
    properties["task_archive_b64"] = {"type": "string", "maxLength": 400_000}
    truth = {"task_archive_sha256": binding["archive_sha256"]}
    generator = program("reference").model_copy(update={"id": "skillsbench.workbook-recovery.generator"})
    generator.config["argv"] = ["python3", "-I", "-B", "-c", "raise SystemExit(2)"]
    failures = ["output_contract", "preservation_rejected", "upstream_rejected"]
    recipe = RecipeDefinition.model_validate({
        "schema_version": "assessment.recipe.v2",
        "recipe_id": "skillsbench-workbook-recovery-protected-v1",
        "capability": CAPABILITY,
        "description": "Pinned workbook recovery with the original tests and an unaffected-value check.",
        "input_schema": {"type": "object", "required": sorted(properties), "additionalProperties": False,
                         "properties": properties},
        "output_schema": {"type": "object", "required": ["workbook_b64"], "additionalProperties": False,
                          "properties": {"workbook_b64": {"type": "string", "minLength": 1,
                                                          "maxLength": 4 * ((ARTIFACT_BOUND + 2) // 3)}}},
        "generator": "contained_json:1",
        "grader": "contained_json:1",
        "extractor": "structural_json:1",
        "generator_config": {"official_reproduction": False, "integration_only": True},
        "dependencies": {"benchmark_pack": value["benchmark_pack_sha256"],
                         "build_context": content_digest(inventory),
                         "protected_reference": file_digest(ORIGINAL_RESULT)},
        "variations": [TASK_ID],
        "exclusions": ["formal holdout", "candidate usefulness", "selection usefulness", "automatic admission"],
        "extension": {
            "schema_version": "assessment.recipe-extension.v6",
            "generator": generator,
            "reference": program("reference"),
            "grader": program("grade"),
            "truth_schema": {"type": "object", "required": sorted(truth), "additionalProperties": False,
                             "properties": {key: {"const": item} for key, item in truth.items()}},
            "failure_codes": failures,
            "independent_fixtures": [],
            "transformed_fixtures": [],
            "fault_outputs": faults,
            "feature_rules": {"task": {"path": "/task_id", "operation": "enum", "values": [TASK_ID]}},
            "variation_features": {TASK_ID: {"task": TASK_ID}},
            "template_families": ["skillsbench:" + TASK_ID],
        },
    })
    case = BenchmarkCase(
        case_id="workbook-recovery-ordinary-integration",
        split="qualification",
        variation=TASK_ID,
        template_family="skillsbench:" + TASK_ID,
        action=ActionRequest(action_id="act_" + binding["input_digest"][:32], capability=CAPABILITY, input=value),
        validators=[ValidationSpec(kind="callback", config={
            "name": grader_name(value, truth), "expected": truth, "failure_codes": failures,
        })],
    )
    validate_json(value, recipe.input_schema, label="ordinary workbook task")
    assert recipe.extension is not None
    validate_json(truth, recipe.extension.truth_schema, label="ordinary workbook truth")
    for fault in faults:
        validate_json(fault, recipe.output_schema, label="workbook fault")
    # Verify the existing validator can batch even the largest reviewed artifact.
    largest = {"workbook_b64": "A" * (4 * ((ARTIFACT_BOUND + 2) // 3))}
    assert len(bounded_batches([{"input": value, "output": largest, "expected": truth}])) == 1
    put(TARGET / "recipe.json", recipe.model_dump(mode="json"))
    put(TARGET / "case.json", case.model_dump(mode="json"))
    record = {
        "task_id": TASK_ID,
        "protected_reference_receipt": observed["receipt_id"],
        "parent_id": IMAGE,
        "parent_tag": parent_tag,
        "parent_layers": review["layers"],
        "build_context": str(context.relative_to(ROOT)),
        "build_context_sha256": content_digest(inventory),
        "files": inventory,
        "file_bytes": sum(item["bytes"] for item in inventory.values()),
        "recipe_digest": content_digest(recipe),
        "case_digest": content_digest(case),
        "environment_bound": False,
        "build_executed": False,
        "verifier_executed": False,
        "provider_disclosure": False,
        "formal_case_adopted": False,
    }
    put(HERE / "workbook-ordinary-preparation.json", record)
    print(json.dumps({key: record[key] for key in ("task_id", "file_bytes", "build_context_sha256", "recipe_digest")}))


if __name__ == "__main__":
    prepare()
