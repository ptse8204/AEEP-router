"""Bind reviewed local CFPB inputs to the ordinary CLI without dispatch authority."""

import argparse
import base64
import contextlib
import io
import json
import shutil
from pathlib import Path
from zipfile import ZipFile

from prepare_extractbench_recipe import (
    GUEST_ROOT,
    MAX_PREDICTION,
    PROTECTED_PIN,
    PUBLIC,
    PUBLIC_PIN,
    definition,
    rehearse,
    write,
)
from stage_extractbench_protected_inputs import verifier_with_document_path
from stage_repository_transport import HERE, ROOT, WORK, digest, read

from aeep.assessment.models import content_digest
from aeep_toolkit.benchmarks import (
    EXTRACTBENCH_REPOSITORY,
    EXTRACTBENCH_REVISION,
    BenchmarkPack,
    BenchmarkTask,
    asset_path,
    task_input,
)
from aeep_toolkit.candidate import inspect
from aeep_toolkit.cli import main
from aeep_toolkit.installation import PreviewPolicy
from aeep_toolkit.models import ExtensionManifest, ExtensionRegistry
from aeep_toolkit.workflow import StackWorkflow

RUN = WORK / "extractbench-ordinary-workflow"
CONFIGURATION = "cfpb-document-data"
PUBLIC_PATHS = {"instruction.md", "environment/document.pdf", "environment/schema.json"}


def write_bytes(path, payload):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)


def seal_case(origin, destination, observation, case_id):
    entries = sorted(origin.rglob("*"))
    if any(path.is_symlink() or not (path.is_file() or path.is_dir()) for path in entries):
        raise ValueError("protected material has an unexpected file type")
    inventory = {
        path.relative_to(origin).as_posix(): {"size": path.stat().st_size, "sha256": digest(path.read_bytes())}
        for path in entries if path.is_file()
    }
    frozen = (json.dumps(inventory, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if digest(frozen) != observation["payload_inventory_sha256"]:
        raise ValueError("protected material changed from the reviewed preparation")
    for name, entry in inventory.items():
        data = read(origin / name, entry["sha256"])
        if name == "verifier/harbor_on_carrier.py":
            continue
        write_bytes(destination / name, data)
    original = read(origin / "verifier/harbor_original.py", observation["original_verifier_sha256"])
    adjusted = verifier_with_document_path(original, GUEST_ROOT / "cases" / case_id / "verifier/document.pdf")
    write_bytes(destination / "verifier/harbor_on_carrier.py", adjusted)
    return {"files": len(inventory), "container_document_path": str(
        GUEST_ROOT / "cases" / case_id / "verifier/document.pdf"), "adapted_verifier_sha256": digest(adjusted)}


def draft_workflow(output, dataset):
    local_evaluator = ExtensionManifest.model_validate({
        "extension_id": "aeep-evaluator", "role": "evaluator", "purpose": "Managed AEEP workflow preview",
        "source": {"repository": "https://github.com/ptse8204/AEEP-router",
                   "revision": "a3be3fa85bc013f238372eb054a4fd5a64ca426e",
                   "artifact_sha256": "1e6fcef78254b7ccf5f5283f765882c25abbe0c944013dec7e5056a2ff895520",
                   "license_expression": "Apache-2.0", "data_rights": dataset.source.data_rights},
        "hosts": ["codex"], "platforms": ["darwin-arm64"], "dependencies": [],
        "permissions": {"network_destinations": [], "filesystem_scope": "workspace",
                        "authentication": "none", "financial_exposure": "none"},
        "disk_bytes": None, "memory_bytes": None, "install_effects": [],
        "rollback": "This preview stages no evaluator runtime.", "status": "blocked",
        "blockers": ["Exact controlled worker authority and protected runtime are pending."],
    })
    local_pack = local_evaluator.model_copy(update={
        "extension_id": "extractbench", "role": "benchmark", "source": dataset.source,
        "purpose": "Pinned CFPB document extraction tasks", "blockers": ("Asset-use reviews and native calibration are pending.",),
    })
    registry = ExtensionRegistry(extensions=(local_evaluator, local_pack))
    policy = PreviewPolicy(host="codex", platform="darwin-arm64", allowed_licenses=("Apache-2.0",),
                           allowed_filesystem_scopes=("none", "workspace"))
    write(output / "registry.json", registry.model_dump(mode="json"))
    write(output / "policy.json", policy.model_dump(mode="json"))
    candidate = ROOT / "integrations/toolkit/fixtures/format-json"
    candidate_digest = inspect(candidate).sha256
    def binding(name):
        return {"path": name, "sha256": digest((output / name).read_bytes())}

    workflow = StackWorkflow.model_validate({
        "registry": binding("registry.json"), "policy": binding("policy.json"),
        "configurations": {CONFIGURATION: {
            "evaluator": "managed", "candidate": {"path": str(candidate), "sha256": candidate_digest},
            "benchmark": binding("pack.json"), "benchmark_recipe": binding("recipe.json"),
            "asset_root": "pack-assets", "task_ids": [task.task_id for task in dataset.tasks],
            "components": ["aeep-evaluator", "extractbench"],
        }},
    })
    write(output / "workflow.json", workflow.model_dump(mode="json"))


def capture(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        if main(argv) != 0:
            raise ValueError("ordinary CLI preview failed")
    return json.loads(out.getvalue())


def stage(output):
    if output.exists() or output.resolve() != output or output.parent != WORK:
        raise ValueError("use a fresh private workspace")
    if shutil.disk_usage(output.parent).free < 52 * 1024**3:
        raise ValueError("insufficient host reserve for preparation")
    source = json.loads(read(HERE / "extractbench-cfpb-source-review.json", PUBLIC_PIN))
    protected = json.loads(read(HERE / "extractbench-cfpb-protected-preparation.json", PROTECTED_PIN))
    original = [source["task"], *[item["task"] for item in source["additional_verified_source_documents"].values()]]
    protected_rows = {item["case"]: item for item in protected["cases"]}
    output.mkdir(mode=0o700)
    pack_root = output / "pack-assets"
    runtime = output / "protected-context"
    tasks, case_paths = [], {}
    for value in original:
        task = BenchmarkTask.model_validate(value)
        original_root = PUBLIC if value == source["task"] else PUBLIC / task.task_id
        protected_root = ROOT / protected_rows[task.task_id]["mount"]
        prefix = f"tasks/{task.task_id}/"
        for asset in task.assets:
            origin = original_root / "agent" if asset.path in PUBLIC_PATHS else protected_root.parent / "publisher"
            path = asset_path(origin, asset)
            write_bytes(pack_root / (prefix + asset.path), read(path, asset.sha256))
        tasks.append({**value, "assets": [
            {**asset, "path": prefix + asset["path"]} for asset in value["assets"]
        ]})
        case_paths[task.task_id] = seal_case(protected_root, runtime / "cases" / task.task_id,
                                            protected_rows[task.task_id], task.task_id)
    data = BenchmarkPack.model_validate({
        "pack_id": "extractbench", "tasks": tasks,
        "source": {"repository": EXTRACTBENCH_REPOSITORY, "revision": EXTRACTBENCH_REVISION,
                   "artifact_sha256": PUBLIC_PIN, "license_expression": source["benchmark_bundle_declared_license"],
                   "data_rights": "Local provenance verified. Separate asset-use and provider disclosure reviews pending."},
    })
    pack_sha = content_digest(data.model_dump(mode="json"))
    write(output / "pack.json", data.model_dump(mode="json"))
    for name in ("extractbench_recipe_guest.py", "extractbench_harbor_observer.py"):
        write_bytes(runtime / name, (HERE / name).read_bytes())
    prepared_cases, bindings, observations = [], {}, []
    for task in data.tasks:
        value = task_input(data, pack_root, task.task_id)
        wire = base64.b64decode(value["task_archive_b64"], validate=True)
        with ZipFile(io.BytesIO(wire)) as archive:
            if set(archive.namelist()) != PUBLIC_PATHS or len(wire) > MAX_PREDICTION:
                raise ValueError("worker archive exceeds its reviewed public input scope")
        identity = content_digest(value)
        by_path = {asset.path.removeprefix(f"tasks/{task.task_id}/"): asset.sha256 for asset in task.assets}
        bindings[identity] = {"case": task.task_id, "reference_sha256": by_path["tests/reference.test.json"],
                              "oracle_sha256": by_path["solution/expected.json"]}
        prepared_cases.append({"input": value, "truth": {"input_sha256": identity}})
        observations.append({"task": task.task_id, "task_archive_sha256": digest(wire), "input_sha256": identity,
                             "original_worker_paths": sorted(PUBLIC_PATHS), "protected": case_paths[task.task_id]})
    write(runtime / "bindings.json", bindings)
    write(output / "draft-cases.json", prepared_cases)
    context_manifest = {path.relative_to(runtime).as_posix(): digest(path.read_bytes())
                        for path in sorted(runtime.rglob("*")) if path.is_file()}
    context_pin = write(output / "protected-context-manifest.json", context_manifest)
    recipe = definition(pack_sha, data.tasks, digest((runtime / "extractbench_recipe_guest.py").read_bytes()))
    recipe.dependencies["protected_context"] = context_pin
    write(output / "recipe.json", recipe.model_dump(mode="json"))
    checks = rehearse(recipe, runtime, prepared_cases, bindings)
    draft_workflow(output, data)
    observed = capture(["workflow", "plan", "--workflow", str(output / "workflow.json"),
                        "--configuration", CONFIGURATION])
    if (
        observed["benchmark"]["pack_sha256"] != pack_sha
        or {task["task_id"] for task in observed["benchmark"]["tasks"]} != set(case_paths)
        or not any("asset rights" in blocker for blocker in observed["blockers"])
        or observed["assessment"] is not None
    ):
        raise ValueError("ordinary CLI lost the selected pack or pending authority")
    write(output / "ordinary-plan.json", observed)
    return {"schema_version": "aeep.c13.extractbench-ordinary-pack-preflight.v1",
            "benchmark_source_revision": data.source.revision, "pack_sha256": pack_sha,
            "recipe_sha256": content_digest(recipe), "ordinary_workflow_preview_sha256": observed["review_sha256"],
            "case_count": len(case_paths), "case_observations": observations,
            "existing_protected_rehearsals_passed": checks, "ordinary_cli_blockers": observed["blockers"],
            "protected_context_files": len(context_manifest), "protected_context_sha256": context_pin,
            "runtime_dependency_site_bound": False, "upstream_grades": 0, "formal_cases_adopted": 0,
            "model_turns": 0, "provider_transfers": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=RUN)
    print(json.dumps(stage(parser.parse_args().output), indent=2, sort_keys=True))
