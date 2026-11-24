"""Bind the real WASDE verifier to a reviewed document pack and calibrate it offline."""

import asyncio
import copy
import io
import os
import shutil
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path
from zipfile import ZipFile

from check_linux_install import DOCKER, SOCKET, Scope, docker, get, put, verified_image
from prepare_usda_wasde_reference import ORIGIN, SOURCES, source
from prepare_wasde_recipe import CALIBRATION, REFERENCE_PIN, SCHEMA_PIN, artifact, recipe_for
from rebind_intake_stack import CURRENT_SOURCE, REPO
from repository_offline_pair_batch import context
from stage_repository_transport import HERE, digest, read, write

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.extensions import grader_results
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentLimits,
    DocumentTaskInput,
    RecipeDefinition,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutionReceipt, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.benchmarks import BenchmarkPack, BenchmarkTask
from aeep_toolkit.install_runtime import file_digest
from aeep_toolkit.models import SourcePin
from aeep_toolkit.stack_verification import ROOT

NAME = "c13-wasde-reviewed-pack-20261124"
WORK = REPO / ".aeep" / NAME
PROTECTED = WORK / "grader"
TASK_ID = "usda-wasde-677-local-calibration"
ROLES = {
    "instruction.md": "instruction",
    "environment/document.pdf": "input",
    "environment/schema.json": "input",
    "solution/expected.json": "oracle",
    "tests/verifier.py": "verifier",
}
RECIPE_EXECS = ("reference", "grader")
IMAGE = "sha256:4474cf22f867c681aa6120ce2f98d809413f89755cf11a445444b1b993754ea1"
SIZE, PDF_PIN = SOURCES["wasde1126.pdf"]
PUBLIC_URL = "https://esmis.nal.usda.gov/publication/world-agricultural-supply-and-demand-estimates"
RIGHTS = "https://www.nal.usda.gov/web-policies-and-important-links"


def stage():
    if (
        verification_source_digest(ROOT) != CURRENT_SOURCE
        or shutil.disk_usage(REPO).free < 52 * 2**30
    ):
        raise ValueError("requires the current clean source and launch headroom")
    WORK.mkdir(mode=0o700)
    put(
        WORK / "acquisition-review.json",
        {
            "url": ORIGIN + "wasde1126.pdf",
            "bytes": SIZE,
            "sha256": PDF_PIN,
            "attempts": 1,
            "scope": "Recover the exact previously calibrated public PDF for local document-pack staging.",
            "authority": "Operator direction to complete C13 and standing bounded first-check delegation.",
            "provider_disclosure": False,
            "model_turns": 0,
        },
    )
    pdf = source("wasde1126.pdf")
    expected = read(CALIBRATION / "protected-reference.json", REFERENCE_PIN)
    retained = get(HERE / "usda-wasde-reference-calibration-20261119.json")
    instruction = read(
        CALIBRATION / "instruction.md", retained["retained_draft_instruction"]["sha256"]
    )
    schema = read(CALIBRATION / "schema.json", SCHEMA_PIN)
    guest = (HERE / "wasde_recipe_guest.py").read_bytes()
    bridge = (HERE / "extractbench_recipe_guest.py").read_bytes()
    files = dict(zip(ROLES, (instruction, pdf, schema, expected, guest), strict=True))
    task_root = WORK / "pack"
    assets = []
    for name, data in files.items():
        asset = f"tasks/{TASK_ID}/{name}"
        write(task_root / asset, data)
        assets.append(
            {"path": asset, "sha256": digest(data), "bytes": len(data), "role": ROLES[name]}
        )
    task = BenchmarkTask.model_validate(
        {
            "task_id": TASK_ID,
            "domain": "document-data",
            "difficulty": "unknown",
            "assets": assets,
            "output_paths": ["output.json"],
            "upstream_score": "binary",
            "adaptations": ["Local exact-match rubric over two ordered publisher tables."],
        }
    )
    pin = SourcePin(
        repository=ORIGIN + "wasde1126.pdf",
        revision=PDF_PIN,
        artifact_sha256=PDF_PIN,
        license_expression="LicenseRef-NAL-case-rights-review-pending",
        data_rights="Official USDA release. Local preparation only. Asset-use approval and provider disclosure are absent.",
    )
    inventory = {
        "tasks": [task.model_dump(mode="json")],
        "task_sources": {TASK_ID: pin.model_dump(mode="json")},
    }
    identity = content_digest(inventory)
    pack = BenchmarkPack(
        schema_version="aeep.toolkit.benchmark-pack.v2",
        pack_id="reviewed-documents",
        source=pin.model_copy(
            update={"repository": PUBLIC_URL, "revision": identity, "artifact_sha256": identity}
        ),
        tasks=(task,),
        task_sources={TASK_ID: pin},
    )
    manifest = WORK / "pack.json"
    put(manifest, pack.model_dump(mode="json"))
    public = WORK / "public"
    public.mkdir(mode=0o700)
    cli = [
        sys.executable,
        "-B",
        "-m",
        "aeep_toolkit",
        "benchmark",
        "stage-document",
        "--pack",
        str(manifest),
        "--root",
        str(task_root),
        "--task",
        TASK_ID,
        "--family",
        "multiple-collections",
        "--destination",
        str(public),
        "--archive-instructions",
    ]
    reply = subprocess.check_output(
        cli,
        cwd=ROOT,
        env={
            "PYTHONPATH": str(ROOT / "src"),
            "PATH": os.defpath,
            "HOME": str(WORK),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        timeout=20,
    )
    descriptor = DocumentTaskInput.model_validate_json(reply)
    if descriptor.benchmark_pack_sha256 != content_digest(pack.model_dump(mode="json")):
        raise ValueError("staged descriptor did not bind the reviewed pack")
    path = public / f"{descriptor.task_archive_sha256}.zip"
    with ZipFile(io.BytesIO(path.read_bytes())) as archive:
        permitted = {
            name: body for name, body in files.items() if ROLES[name] in {"input", "instruction"}
        }
        if (
            len(archive.namelist()) != 3
            or {name: archive.read(name) for name in archive.namelist()} != permitted
        ):
            raise ValueError("worker archive includes unexpected data")
    if file_digest(path) != descriptor.task_archive_sha256:
        raise ValueError("public ZIP changed")
    put(WORK / "document.json", descriptor.model_dump(mode="json"))
    recipe = recipe_for(descriptor, digest(guest), digest(bridge)).model_dump(mode="json")
    for name, mode in zip(RECIPE_EXECS, ("reference", "grade"), strict=True):
        recipe["extension"][name]["config"]["argv"] = [
            "python3",
            "-I",
            "-B",
            str(PROTECTED / "wasde_recipe_guest.py"),
            mode,
            "--support",
            str(PROTECTED),
        ]
    bound = RecipeDefinition.model_validate(recipe)
    put(WORK / "recipe.json", bound.model_dump(mode="json"))
    write(PROTECTED / "wasde_recipe_guest.py", guest)
    write(PROTECTED / "extractbench_recipe_guest.py", bridge)
    put(
        PROTECTED / "bindings.json",
        {
            content_digest(descriptor): {
                "case": TASK_ID,
                "reference_sha256": REFERENCE_PIN,
                "oracle_sha256": REFERENCE_PIN,
            }
        },
    )
    for key in ("verifier/reference.test.json", "controls/oracle.json"):
        write(PROTECTED / "cases" / TASK_ID / key, expected)
    PROTECTED.chmod(0o755)
    for item in PROTECTED.rglob("*"):
        item.chmod(0o555 if item.is_dir() else 0o444)
    return pack, descriptor, bound, expected


def observations(descriptor, expected):
    value = descriptor.model_dump(mode="json")
    protected_truth = {"input_sha256": content_digest(descriptor)}
    good = artifact(expected)
    import json

    wrong = copy.deepcopy(json.loads(expected))
    wrong["united_states"].pop()

    def row(output):
        return {"examples": [{"input": value, "expected": protected_truth, "output": output}]}

    return [
        ("reference", {"inputs": [value]}, good),
        ("reference-grade", row(good), (True, 1.0, "")),
        (
            "missing-row",
            row(artifact(json.dumps(wrong, allow_nan=False).encode())),
            (False, 0.0, "inexact_extraction"),
        ),
        ("bad-json", row(artifact(b"{")), (False, 0.0, "invalid_submission")),
    ]


async def grade(pack, descriptor, recipe, expected):
    layers = verified_image()
    environment = AssessmentEnvironment(
        environment_id=NAME,
        kind="container",
        identity={"source": CURRENT_SOURCE},
        container_image=IMAGE,
        container_runtime=DOCKER,
        container_socket=SOCKET,
        read_only_roots=[str(PROTECTED)],
    )
    executor = ContainerExecutor(environment)
    extension = recipe.extension
    assert extension is not None
    calls = []
    for role, payload, want in observations(descriptor, expected):
        spec = extension.reference if role == "reference" else extension.grader
        execution = context(spec, f"{NAME}:{role}", payload)
        argv, name = executor.command(execution)
        mounts = {arg for arg in argv if arg.startswith("type=bind,")}
        if mounts != {f"type=bind,src={p},dst={p},readonly" for p in (ROOT / "src", PROTECTED)}:
            raise ValueError("protected grader mounts changed")
        if (
            argv[argv.index("--network") + 1] != "none"
            or argv[argv.index("--user") + 1] != "65534:65534"
        ):
            raise ValueError("protected grader permissions changed")
        calls.append((role, execution, argv, name, want))
    expiry = utc_now() + timedelta(hours=2)
    review = WORK / "grader-review.json"
    inputs = {str(p): file_digest(p) for p in PROTECTED.rglob("*") if p.is_file()}
    put(
        review,
        {
            "source": CURRENT_SOURCE,
            "pack": content_digest(pack.model_dump(mode="json")),
            "recipe": content_digest(recipe),
            "image": IMAGE,
            "image_layers": layers,
            "docker_sha256": file_digest(Path(DOCKER)),
            "protected_files": inputs,
            "expires": expiry.isoformat(),
            "maximum_operations": len(calls),
            "reservation_seconds": 160,
            "commands": {
                role: {"argv": argv, "input_sha256": content_digest(run.request.input)}
                for role, run, argv, _, _ in calls
            },
            "authority": "First isolated reference and control check of the ordinary reviewed-documents pack, under the C13 first-check delegation.",
            "model_turns": 0,
            "cash_usd": 0,
            "remote_disclosure": False,
        },
    )
    exact = file_digest(review)
    scope = Scope(review_sha256=exact)
    ref = content_digest(scope)
    request = RecipeMaterializationRequest(
        plan_id=NAME,
        authorization_id=NAME,
        subject_digest=ref,
        recipe_digest=ref,
        environment_digest=ref,
        mapping_digest=ref,
        definition_digests=[ref],
        seed=0,
    )
    grant = AssessmentAuthorization(
        authorization_id=NAME,
        subject_digests=[ref],
        recipe_digests=[ref],
        environment_digests=[ref],
        limits=AssessmentLimits(
            max_operations=len(calls), max_model_turns=0, max_elapsed_seconds=160
        ),
        expires_at=expiry,
        allowed_destinations=["local"],
        remote_disclosure=False,
    )
    checked = {}
    with ReceiptStore(WORK / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        repo.put("c13_wasde_scope", ref, scope)
        repo.approve_bundle(grant, {ref: scope.model_dump(mode="json")})
        try:
            for role, run, argv, name, want in calls:
                scope_matches = file_digest(review) == exact and executor.command(run) == (
                    argv,
                    name,
                )
                assets_match = all(file_digest(Path(path)) == sha for path, sha in inputs.items())
                name_filter = f"name=^/{name}$"
                if (
                    not scope_matches
                    or not assets_match
                    or verified_image() != layers
                    or docker("ps", "-aq", "--filter", name_filter)
                    or shutil.disk_usage(REPO).free < 52 * 2**30
                ):
                    raise ValueError("review or execution boundary drift")
                operation = run.request.action_id
                repo.reserve(
                    request,
                    operation,
                    AssessmentLimits(max_operations=1, max_elapsed_seconds=40),
                    stage="wasde_protected_calibration",
                    require_settled_plan=True,
                )
                started, clock = utc_now(), time.monotonic()
                raw = await executor.execute(run)
                if docker("ps", "-aq", "--filter", name_filter):
                    raise RuntimeError("cleanup uncertain; reservation remains open")
                valid = False
                observed = None
                if raw.status.value == "success":
                    if role == "reference":
                        valid = raw.output == {"outputs": [want]}
                    else:
                        (score,) = grader_results(raw.output, extension, 1)
                        observed = {
                            "score": score.quality_score,
                            "valid": score.valid,
                            "detail": score.detail,
                        }
                        valid = (score.valid, score.quality_score, score.detail) == want
                receipt = ExecutionReceipt(
                    decision_id=operation,
                    action_id=operation,
                    capability=run.spec.capability,
                    executor_id=run.spec.id,
                    executor_kind=run.spec.kind,
                    status="success" if valid else "failed",
                    started_at=started,
                    ended_at=utc_now(),
                    estimated=run.estimate,
                    actual_resources=raw.resources,
                    execution_success=valid,
                    error_type=None if valid else "WASDE_UNVERIFIED",
                    metadata={"review_sha256": exact, "container_absent": True},
                )
                store.save_receipt(receipt)
                repo.finish_operation(
                    operation, elapsed_seconds=time.monotonic() - clock, resources=raw.resources
                )
                checked[role] = {
                    "verified": valid,
                    "score": observed,
                    "receipt": receipt.receipt_id,
                    "error_type": raw.error_type,
                }
                put(WORK / f"{role}-result.json", checked[role])
                if not valid:
                    raise ValueError(
                        f"unexpected protected {role} result: {raw.error_type or 'observations differ'}"
                    )
        finally:
            put(WORK / "ledger.json", repo.operation_ledger(NAME).model_dump(mode="json"))
    return exact, checked


if __name__ == "__main__":
    os.umask(0o077)
    pack, descriptor, recipe, expected = stage()
    review, checks = asyncio.run(grade(pack, descriptor, recipe, expected))
    put(
        WORK / "result.json",
        {
            "review_sha256": review,
            "checks": checks,
            "source": CURRENT_SOURCE,
            "pdf_sha256": PDF_PIN,
            "publisher": PUBLIC_URL,
            "publisher_policy": RIGHTS,
            "public_zip_sha256": descriptor.task_archive_sha256,
            "public_zip_files": 3,
            "pack_sha256": descriptor.benchmark_pack_sha256,
            "recipe_sha256": content_digest(recipe),
            "model_turns": 0,
            "cash_usd": 0,
            "operator_asset_use_review_registered": False,
            "provider_disclosure": False,
            "formal_cases_assigned": 0,
        },
    )
