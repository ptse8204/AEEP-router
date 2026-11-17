"""Bind the verified Formula Extraction renderer to the ordinary integration recipe."""

import base64
import json
import shutil
from pathlib import Path

from check_linux_install import HERE, WORK, docker, get, put
from formula_recipe_guest import MAX_ARTIFACT, MAX_ENCODED, OUTPUT, digest
from stage_protected_inputs import freeze, tree

from aeep.assessment.extensions import bounded_batches, grader_name
from aeep.assessment.models import RecipeDefinition, content_digest
from aeep.benchmarking import BenchmarkCase
from aeep.models import ActionRequest, ExecutorSpec, ValidationSpec
from aeep.registry import validate_json
from aeep_toolkit.benchmarks import BenchmarkPack, task_input
from aeep_toolkit.install_runtime import file_digest

TASK_ID = "latex-formula-extraction"
CAPABILITY = "assessment.skillsbench.formula-extraction@1"
TARGET = WORK / "formula-ordinary-recipe"
CONTEXT = Path("/private/tmp/aeep-c13-formula-ordinary-20261116")
RUNTIME = Path("/private/tmp/aeep-c13-formula-check-20261116/renderer")
EXECUTION = WORK / "formula-protected-execution"
HISTORICAL_REVIEW = WORK / "formula-protected-operation-review.json"
HISTORICAL_GROUP = HERE / "protected-reference-group-result.json"
GUEST = "/opt/aeep-formula-renderer"
PARENT_TAG = "aeep-skillsbench-react:retained-amd64-6f04cf16"


def program(mode):
    name = "grade" if mode == "grade" else "reference"
    return ExecutorSpec(
        id=f"skillsbench.formula-extraction.{name}",
        capability=CAPABILITY,
        kind="command",
        description=f"Protected Formula Extraction {name}",
        config={
            "argv": ["python3", "-I", "-B", f"{GUEST}/ordinary.py", mode],
            "argv_literal": True,
            "stdin_json": True,
            "output": {"type": "json"},
            "timeout_seconds": 45 if mode == "grade" else 30,
            "max_output_bytes": 80_000,
        },
    )


def prepare():
    group = get(HISTORICAL_GROUP)
    previous = group["results"]["formula"]
    review = get(HISTORICAL_REVIEW)
    if (
        file_digest(HISTORICAL_REVIEW) != previous["review_sha256"]
        or file_digest(EXECUTION / "ledger.json") != previous["ledger_sha256"]
        or previous["passed_exact_contract"] is not True
        or previous["settled_operations"] != 4
    ):
        raise ValueError("protected formula evidence changed")
    record = previous["roles"]["reference"]
    lock = get(RUNTIME / "protected-fixtures/protected-fixture-lock.json")
    if record["observation"]["grade"] != 1 or set(record["observation"]["outcomes"]) != set(
        lock["identities"]
    ):
        raise ValueError("protected reference observations changed")
    bootstrap = Path(review["staged"]["bootstrap"])
    expected = review["staged"]["sha256_by_staged_root"]
    roots = {str(path): tree(path) for path in (RUNTIME, bootstrap)}
    if {name: content_digest(items) for name, items in roots.items()} != expected:
        raise ValueError("retained formula renderer or bootstrap drifted")
    parent = json.loads(docker("image", "inspect", "--format", "{{json .}}", review["image_id"]))
    tags = parent.get("RepoTags") or []
    if (
        parent["Id"] != previous["runtime_image_id"]
        or parent["Architecture"] != "amd64"
        or parent["Os"] != "linux"
        or parent["RootFS"]["Layers"] != review["image_layers"]
        or parent["Config"].get("Volumes")
        or parent["Config"].get("Healthcheck")
        or PARENT_TAG not in tags
    ):
        raise ValueError("retained formula carrier is outside its reviewed image profile")
    copied = sum(
        file.stat().st_size
        for root in (RUNTIME, bootstrap)
        for file in root.rglob("*")
        if file.is_file()
    )
    if shutil.disk_usage(CONTEXT.parent).free < 52 * 1024**3 + copied:
        raise ValueError("storage reserve excludes renderer staging")
    pack = WORK / "independent-document-pack"
    intake = get(HERE / "independent-document-pack-intake.json")
    pack_file = pack / "pack.json"
    model = BenchmarkPack.model_validate_json(pack_file.read_bytes())
    value = task_input(model, pack / "pack-assets", TASK_ID)
    if (
        file_digest(pack_file) != intake["manifest_file_sha256"]
        or value["benchmark_pack_sha256"] != intake["pack_sha256"]
        or value["task_archive_sha256"] != intake["tasks"][TASK_ID]["archive_sha256"]
        or value["output_paths"] != [OUTPUT]
        or digest(value) != content_digest(value)
    ):
        raise ValueError("formula benchmark input no longer matches the private pack")
    fixtures = RUNTIME / "protected-fixtures"
    binding = {
        "input_digest": content_digest(value),
        "archive_sha256": value["task_archive_sha256"],
        "reference_sha256": lock["files"]["reference.md"],
        "identities": lock["identities"],
    }
    reference = (fixtures / "reference.md").read_bytes()
    controls = {
        name: (fixtures / f"{name}.md").read_bytes() for name in ("wrong-value", "incomplete")
    }
    if any(not 0 < len(payload) <= MAX_ARTIFACT for payload in [reference, *controls.values()]):
        raise ValueError("protected reference or controls exceed the transport")
    TARGET.mkdir(mode=0o700)
    context = CONTEXT
    context.mkdir(mode=0o700)
    shutil.copytree(RUNTIME, context / "renderer")
    shutil.copytree(bootstrap, context / "python")
    renderer = context / "renderer"
    renderer.chmod(0o755)
    shutil.copyfile(HERE / "formula_recipe_guest.py", renderer / "ordinary.py")
    put(renderer / "ordinary-binding.json", binding)
    freeze(renderer)
    freeze(context / "python")
    (context / "aeep-assessment.pth").write_text("/opt/aeep-assessment-python\n")
    (context / "Dockerfile").write_text(
        f"FROM {PARENT_TAG}\n"
        f"COPY renderer/ {GUEST}/\n"
        "COPY python/ /opt/aeep-assessment-python/\n"
        "COPY aeep-assessment.pth /usr/local/lib/python3.12/dist-packages/aeep-assessment.pth\n"
    )
    files = {
        path.relative_to(context).as_posix(): {
            "sha256": file_digest(path),
            "bytes": path.stat().st_size,
            "mode": format(path.stat().st_mode & 0o777, "04o"),
        }
        for path in sorted(context.rglob("*"))
        if path.is_file()
    }
    properties = {key: {"const": item} for key, item in value.items() if key != "task_archive_b64"}
    properties["task_archive_b64"] = {"type": "string", "maxLength": 400_000}
    truth = {"task_archive_sha256": binding["archive_sha256"]}
    failures = ["output_contract", "upstream_rejected"]
    faults = [
        {"markdown_b64": base64.b64encode(data).decode("ascii")} for data in controls.values()
    ]
    generator = program("reference").model_copy(
        update={"id": "skillsbench.formula-extraction.generator"}
    )
    generator.config["argv"] = ["python3", "-I", "-B", "-c", "raise SystemExit(2)"]
    recipe = RecipeDefinition.model_validate(
        {
            "schema_version": "assessment.recipe.v2",
            "recipe_id": "skillsbench-formula-extraction-protected-v1",
            "capability": CAPABILITY,
            "description": "Pinned offline rendering and all seven published formula assertions",
            "input_schema": {
                "type": "object",
                "required": sorted(properties),
                "properties": properties,
                "additionalProperties": False,
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "markdown_b64": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": MAX_ENCODED,
                    }
                },
                "required": ["markdown_b64"],
                "additionalProperties": False,
            },
            "generator": "contained_json:1",
            "grader": "contained_json:1",
            "extractor": "structural_json:1",
            "generator_config": {"integration_only": True, "official_reproduction": False},
            "dependencies": {
                "benchmark_pack": value["benchmark_pack_sha256"],
                "build_context": content_digest(files),
                "reference_evidence": file_digest(HISTORICAL_GROUP),
            },
            "variations": [TASK_ID],
            "exclusions": [
                "formal holdout",
                "candidate usefulness",
                "selection usefulness",
                "automatic admission",
            ],
            "extension": {
                "schema_version": "assessment.recipe-extension.v6",
                "generator": generator,
                "reference": program("reference"),
                "grader": program("grade"),
                "truth_schema": {
                    "type": "object",
                    "required": sorted(truth),
                    "additionalProperties": False,
                    "properties": {key: {"const": item} for key, item in truth.items()},
                },
                "failure_codes": failures,
                "independent_fixtures": [],
                "transformed_fixtures": [],
                "fault_outputs": faults,
                "feature_rules": {
                    "task": {"path": "/task_id", "operation": "enum", "values": [TASK_ID]}
                },
                "variation_features": {TASK_ID: {"task": TASK_ID}},
                "template_families": ["skillsbench:" + TASK_ID],
            },
        }
    )
    case = BenchmarkCase(
        case_id="formula-extraction-ordinary-integration",
        split="qualification",
        variation=TASK_ID,
        template_family="skillsbench:" + TASK_ID,
        action=ActionRequest(
            action_id="act_" + binding["input_digest"][:32],
            capability=CAPABILITY,
            input=value,
        ),
        validators=[
            ValidationSpec(
                kind="callback",
                config={
                    "name": grader_name(value, truth),
                    "expected": truth,
                    "failure_codes": failures,
                },
            )
        ],
    )
    validate_json(value, recipe.input_schema, label="formula task")
    assert recipe.extension is not None
    validate_json(truth, recipe.extension.truth_schema, label="formula truth")
    for artifact in [*faults, {"markdown_b64": base64.b64encode(reference).decode("ascii")}]:
        validate_json(artifact, recipe.output_schema, label="formula artifact")
    assert (
        len(
            bounded_batches(
                [
                    {
                        "input": value,
                        "output": {"markdown_b64": "A" * MAX_ENCODED},
                        "expected": truth,
                    }
                ]
            )
        )
        == 1
    )
    put(TARGET / "recipe.json", recipe.model_dump(mode="json"))
    put(TARGET / "case.json", case.model_dump(mode="json"))
    summary = {
        "task_id": TASK_ID,
        "recipe_digest": content_digest(recipe),
        "case_digest": content_digest(case),
        "reference_receipt_id": record["receipt_id"],
        "historical_review_sha256": previous["review_sha256"],
        "historical_ledger_sha256": previous["ledger_sha256"],
        "source_parent": parent["Id"],
        "parent_tag": PARENT_TAG,
        "parent_layers": parent["RootFS"]["Layers"],
        "copied_runtime_source_digests": expected,
        "context_digest": content_digest(files),
        "context_path": str(context),
        "file_count": len(files),
        "context_bytes": sum(entry["bytes"] for entry in files.values()),
        "compiled_renderer_supported_architecture": "linux/amd64",
        "all_upstream_identities_retained": len(lock["identities"]),
        "historical_durations": {
            role: observation["operation_elapsed_seconds"]
            for role, observation in previous["roles"].items()
        },
        "environment_bound": False,
        "build_executed": False,
        "ordinary_tests_executed": 0,
        "provider_disclosure": False,
        "formal_assignment": False,
    }
    put(TARGET / "context-files.json", files)
    put(TARGET / "summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    prepare()
