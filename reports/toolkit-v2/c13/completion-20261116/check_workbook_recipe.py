"""Review or verify the ordinary workbook recipe against a private COPY-only image."""

import argparse
import asyncio
import base64
import io
import json
import re
import shutil
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from check_linux_install import (
    DOCKER,
    FROZEN,
    IMAGE,
    SOCKET,
    Scope,
    docker,
    get,
    put,
    verified_image,
)
from prepare_workbook_recipe import (
    HERE,
    MAIN_NS,
    ORIGINAL_RESULT,
    ORIGINAL_REVIEW,
    TARGET,
    WORK,
)

from aeep.assessment import containment
from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.extensions import grader_results
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentBudgetAmendment,
    AssessmentEnvironment,
    AssessmentLimits,
    AssessmentScopeAmendment,
    IntegrationCaseSet,
    RecipeDefinition,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.recipes import faulty_outputs
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.benchmarking import BenchmarkCase
from aeep.errors import ConfigurationError, InputValidationError
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, utc_now
from aeep.registry import validate_json
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import file_digest

TAG = "aeep-skillsbench-workbook-recovery:protected-20261116"
BUILD_PLUGIN = Path("/Applications/Docker.app/Contents/Resources/cli-plugins/docker-buildx")
CONFIG = TARGET / "docker-config"
PRIOR_REVIEW = HERE / "workbook-ordinary-operation-review.json"
PRIOR_REVIEW_DIGEST = "8d35b573e5de5c23d2e1c97b6728d201f3665ed621952376ccc5ffad2625f589"
REVIEW = HERE / "workbook-ordinary-renewal-review-20261117.json"
APPROVAL = TARGET / "approval.json"
RESULT = TARGET / "execution"
RESERVE = 52 * 1024**3
BUILD_SECONDS = 120
BUILD_ENV = {"HOME": str(TARGET), "PATH": "/usr/bin:/bin", "LC_ALL": "C", "DOCKER_BUILDKIT": "1"}


def title_fault(output):
    original = base64.b64decode(output["workbook_b64"], validate=True)
    target = io.BytesIO()
    changed = False
    with ZipFile(io.BytesIO(original)) as source, ZipFile(target, "w") as sink:
        for member in source.infolist():
            data = source.read(member)
            if member.filename == "xl/worksheets/sheet1.xml":
                root = ElementTree.fromstring(data)
                cell = root.find(f".//{MAIN_NS}c[@r='A1']/{MAIN_NS}is/{MAIN_NS}t")
                if cell is None or not cell.text:
                    raise ValueError("reference workbook title is unavailable")
                cell.text += " (changed)"
                data = ElementTree.tostring(root, encoding="utf-8")
                changed = True
            sink.writestr(member, data)
    if not changed:
        raise ValueError("reference workbook sheet is unavailable")
    return {"workbook_b64": base64.b64encode(target.getvalue()).decode("ascii")}


def prepared():
    staging = get(HERE / "workbook-ordinary-preparation.json")
    recipe = RecipeDefinition.model_validate_json((TARGET / "recipe.json").read_bytes())
    case = BenchmarkCase.model_validate_json((TARGET / "case.json").read_bytes())
    context = TARGET / "image"
    inventory = {
        path.relative_to(context).as_posix(): {"sha256": file_digest(path), "bytes": path.stat().st_size}
        for path in sorted(context.rglob("*")) if path.is_file()
    }
    parent = json.loads(docker("image", "inspect", "--format", "{{json .}}", staging["parent_tag"]))
    if (
        content_digest(recipe) != staging["recipe_digest"] or content_digest(case) != staging["case_digest"]
        or any(path.is_symlink() or not (path.is_dir() or path.is_file()) for path in context.rglob("*"))
        or inventory != staging["files"] or content_digest(inventory) != staging["build_context_sha256"]
        or parent["Id"] != IMAGE or verified_image() != staging["parent_layers"]
        or (context / "Dockerfile").read_text() != (
            f"FROM {staging['parent_tag']}\nCOPY runtime/ /opt/aeep-workbook-recovery/\n"
        )
        or get(CONFIG / "config.json") != {"cliPluginsExtraDirs": [str(BUILD_PLUGIN.parent)]}
    ):
        raise ValueError("workbook recipe, context, or offline carrier changed")
    prior = get(ORIGINAL_RESULT)
    prior_review = get(ORIGINAL_REVIEW)
    before = ORIGINAL_REVIEW.parent / f"reference-execution-{prior['operation_review_sha256'][:12]}"
    original_attempt = ORIGINAL_REVIEW.parent / "reference-execution"
    with ReceiptStore(before / "receipts.sqlite3", read_only=True) as store:
        repo = AssessmentRepository(store)
        name = prior_review["scope_id"]
        grant = AssessmentAuthorization.model_validate(repo.get("authorization", name))
        ledger = repo.operation_ledger(name).model_dump(mode="json")
        if (
            repo.effective_grant(name) != grant or len(ledger["operations"]) != 3
            or ledger != get(before / "ledger.json")
            or any(row["elapsed_seconds"] is None for row in ledger["operations"])
            or grant.limits.max_cash_usd or grant.limits.max_model_turns or grant.remote_disclosure
            or grant.allowed_destinations != ["local"]
            or len(set(grant.subject_digests + grant.recipe_digests + grant.environment_digests)) != 1
        ):
            raise ValueError("earlier workbook accounting changed")
    assert recipe.extension is not None
    builds = [
        DOCKER, "--config", str(CONFIG), "--host", f"unix://{SOCKET}",
        "build", "--pull=false", "--network=none", "--platform=linux/arm64",
        "--provenance=false", "--sbom=false", "--iidfile", str(RESULT / "image-id"),
        "--tag", TAG, str(context),
    ]
    count = 1 + len(faulty_outputs({"workbook_b64": "example"})) + len(recipe.extension.fault_outputs) + 1
    reserved = BUILD_SECONDS + 5 + 35 + count * 50
    review = {
        "parent_id": IMAGE, "derived_tag": TAG,
        "build_command": builds, "build_context_sha256": staging["build_context_sha256"],
        "build_plugin_sha256": file_digest(BUILD_PLUGIN), "docker_sha256": file_digest(Path(DOCKER)),
        "source": verification_source_digest(FROZEN),
        "driver_sha256": file_digest(Path(__file__)),
        "recipe_digest": content_digest(recipe), "case_digest": content_digest(case),
        "prior_ledger_sha256": file_digest(before / "ledger.json"),
        "first_ledger_sha256": file_digest(original_attempt / "ledger.json"),
        "root_grant_digest": content_digest(grant), "expires_at": grant.expires_at.isoformat(),
        "max_new_operations": 2 + count,
        "max_new_reserved_seconds": reserved,
        "max_operations_on_root": grant.limits.max_operations + 2 + count,
        "max_seconds_on_root": grant.limits.max_elapsed_seconds + reserved,
        "reference_and_grader": {
            "reference": recipe.extension.reference.config["argv"],
            "grader": recipe.extension.grader.config["argv"],
            "negative_controls": ["five protocol faults", "unfilled workbook", "zero replacements", "changed title"],
        },
        "provider_disclosure": False, "models": 0, "cash_usd": 0, "retries": 0,
    }
    return review, before, grant, recipe, case


def renewed_fields(review, expires):
    prior = get(PRIOR_REVIEW)
    if (
        file_digest(PRIOR_REVIEW) != PRIOR_REVIEW_DIGEST
        or {**review, "driver_sha256": prior["driver_sha256"]} != prior
        or not datetime.fromisoformat(prior["expires_at"]) <= utc_now() < expires
        or expires > utc_now() + timedelta(days=7)
    ):
        raise ValueError("expired workbook scope or renewal window differs")
    return {
        **review, "expires_at": expires.isoformat(), "previous_expires_at": prior["expires_at"],
        "previous_review_sha256": PRIOR_REVIEW_DIGEST, "build_env": BUILD_ENV,
    }


def preflight(review):
    if (
        not Path(containment.__file__).resolve().is_relative_to(FROZEN / "src")
        or RESULT.exists() or docker("image", "ls", "--filter", "reference=" + TAG, "-q")
        or shutil.disk_usage(WORK).free < RESERVE
    ):
        raise ValueError("workbook requires its pinned source, fresh tag and host reserve")
    builder = subprocess.run(
        [*review["build_command"][:5], "buildx", "inspect", "default"],
        env=BUILD_ENV, stdin=subprocess.DEVNULL, timeout=20, check=True, capture_output=True, text=True,
    ).stdout
    if (
        not re.search(r"^Driver:\s+docker\s*$", builder, re.M)
        or not re.search(r"^Status:\s+running\s*$", builder, re.M)
        or not re.search(r"^Platforms:\s+.*\blinux/arm64(?:,|$)", builder, re.M)
    ):
        raise ValueError("local workbook Docker builder is unavailable")


def load_review(*, prepare=False):
    current, *scope = prepared()
    published = None if prepare else get(REVIEW)
    expires = (utc_now() + timedelta(days=7) if published is None
               else datetime.fromisoformat(published["expires_at"]))
    renewed = renewed_fields(current, expires)
    if published is not None and published != renewed:
        raise ValueError("workbook renewal bindings changed")
    preflight(renewed)
    return renewed, expires, *scope


async def run(exact):
    if (
        RESULT.exists() or file_digest(REVIEW) != exact
        or not APPROVAL.is_file() or get(APPROVAL) != {"approved": True, "review_sha256": exact}
    ):
        raise ValueError("this unstarted workbook operation needs its exact approval")
    review, expires, prior, grant, recipe, case = load_review()
    if file_digest(REVIEW) != exact:
        raise ValueError("workbook renewal changed during preflight")
    RESULT.mkdir(mode=0o700)
    scope = Scope(review_sha256=exact)
    subject = grant.subject_digests[0]
    ref = content_digest(scope)
    name = grant.authorization_id
    request = RecipeMaterializationRequest(
        plan_id=name, authorization_id=name, subject_digest=subject, recipe_digest=subject,
        environment_digest=subject, mapping_digest=subject, definition_digests=[subject, ref], seed=0,
    )
    measurements = []
    with ReceiptStore(prior / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        if repo.operation_ledger(name).model_dump(mode="json") != get(prior / "ledger.json") or repo.effective_grant(name) != grant:
            raise ValueError("original workbook grant changed before dispatch")
        repo.put("workbook_ordinary_scope", ref, scope)
        amendment = AssessmentScopeAmendment(
            amendment_id=name + ":ordinary", authorization_id=name, authorization_digest=content_digest(grant),
            subject_digests=[subject], recipe_digests=[subject], environment_digests=[subject], reviewed_digests=[ref],
        )
        budget = AssessmentBudgetAmendment(
            amendment_id=name + ":ordinary-budget", authorization_id=name, authorization_digest=content_digest(grant),
            expires_at=expires, limits=AssessmentLimits(
                max_model_turns=0, max_operations=review["max_operations_on_root"],
                max_elapsed_seconds=review["max_seconds_on_root"],
            ),
        )
        repo.approve_bundle(amendment, {
            subject: repo.get("toolkit_skillsbench_reference_scope", subject),
            ref: scope.model_dump(mode="json"),
        }, budget_amendment=budget)

        async def call(label, spec, executor, payload, validate):
            if file_digest(REVIEW) != exact or shutil.disk_usage(WORK).free < RESERVE:
                raise ValueError("workbook review or storage changed before dispatch")
            operation = name + ":ordinary:" + label
            context = ExecutionContext(
                request=ActionRequest(action_id=operation, capability=spec.capability, input=payload),
                spec=spec, estimate=spec.estimate, attempt=1, attempt_id=operation,
                approved_side_effect=spec.side_effect,
            )
            owned = None
            if isinstance(executor, ContainerExecutor):
                argv, owned = executor.command(context)
                path = FROZEN / "src"
                if ({arg for arg in argv if arg.startswith("type=bind,")} != {f"type=bind,src={path},dst={path},readonly"}
                        or argv[argv.index("--network") + 1] != "none"
                        or not {"--read-only", "--pull=never", "--cap-drop=ALL",
                                "--security-opt=no-new-privileges"} <= set(argv)
                        or argv[argv.index("--user") + 1] != "65534:65534"
                        or docker("ps", "-aq", "--filter", f"name=^/{owned}$")):
                    raise ValueError("ordinary workbook runner escaped its reviewed boundary")
            repo.reserve(request, operation, AssessmentLimits(
                max_operations=1, max_model_turns=0, max_elapsed_seconds=spec.config["timeout_seconds"] + 5,
            ), stage="ordinary_workbook_recipe", require_settled_plan=True)
            started, tick = utc_now(), time.monotonic()
            raw = await executor.execute(context)
            if owned and docker("ps", "-aq", "--filter", f"name=^/{owned}$"):
                raise RuntimeError("container cleanup is uncertain; retain the open reservation")
            if not owned and raw.status.value == "timeout":
                raise RuntimeError("image creation is uncertain; retain the open reservation")
            result = None
            failure = raw.error_type
            if raw.status.value == "success":
                try:
                    result = validate(raw.output)
                except (ValueError, KeyError, TypeError, OSError, ConfigurationError, InputValidationError) as error:
                    failure = type(error).__name__
            matched = result is not None
            receipt = ExecutionReceipt(
                decision_id=operation, action_id=operation, capability=spec.capability,
                executor_id=spec.id, executor_kind=spec.kind, status="success" if matched else "failed",
                execution_success=matched, started_at=started, ended_at=utc_now(), estimated=spec.estimate,
                actual_resources=raw.resources, error_type=None if matched else failure or "WORKBOOK_RECIPE_CONTRACT_MISMATCH",
                metadata={"review_sha256": exact, "guest_container_absent": True if owned else None},
            )
            store.save_receipt(receipt)
            repo.finish_operation(operation, elapsed_seconds=time.monotonic() - tick, resources=raw.resources)
            row = {"role": label, "receipt_id": receipt.receipt_id, "contract_matched": matched}
            if matched:
                row["output_sha256"] = content_digest(result if isinstance(result, dict) else {"value": result})
            put(RESULT / f"{label}.json", row)
            measurements.append(row)
            return result

        def inspected_image(_):
            identity = (RESULT / "image-id").read_text().strip()
            data = json.loads(docker("image", "inspect", "--format", "{{json .}}", TAG))
            parent_layers = get(HERE / "workbook-ordinary-preparation.json")["parent_layers"]
            if (
                not re.fullmatch(r"sha256:[a-f0-9]{64}", identity) or data["Id"] != identity
                or data["RootFS"]["Layers"][:-1] != parent_layers
                or data["Architecture"] != "arm64" or data["Os"] != "linux"
                or data["Config"]["User"] != "65534:65534"
                or data["Config"].get("Volumes") or data["Config"].get("Healthcheck")
            ):
                raise ValueError("built workbook image differs from the reviewed parent or permissions")
            return identity

        build = ExecutorSpec(
            id="skillsbench.workbook-recovery.build", capability="toolkit.upstream-engineering@1",
            kind="command", side_effect="write", description="Offline COPY-only workbook grader image",
            config={
                "argv": review["build_command"], "argv_literal": True, "inherit_env": False,
                "env": review["build_env"],
                "timeout_seconds": BUILD_SECONDS, "max_output_bytes": 65536, "output": {"type": "text"},
            },
        )
        executor = CommandExecutor()
        try:
            identity = await call("build", build, executor, {}, inspected_image)
        finally:
            await executor.close()
        if identity:
            env = AssessmentEnvironment(
                environment_id="workbook-ordinary-grader", kind="container",
                identity={"operation_review_sha256": exact}, container_image=identity,
                container_runtime=DOCKER, container_socket=SOCKET, memory_mb=512, process_limit=96,
            )
            def reference(value):
                if set(value) != {"outputs"} or len(value["outputs"]) != 1:
                    raise ValueError("invalid ordinary reference reply")
                output = value["outputs"][0]
                validate_json(output, recipe.output_schema, label="ordinary workbook reference")
                return output

            assert recipe.extension is not None
            protected = ContainerExecutor(env)
            artifact = await call("reference", recipe.extension.reference, protected, {"inputs": [case.action.input]}, reference)
            if artifact:
                truth = case.validators[-1].config["expected"]
                controls = [(artifact, None), *[(entry, "output_contract") for entry in faulty_outputs(artifact)],
                            (recipe.extension.fault_outputs[0], "preservation_rejected"),
                            (recipe.extension.fault_outputs[1], "upstream_rejected"),
                            (title_fault(artifact), "preservation_rejected")]
                for index, (output, expected) in enumerate(controls):
                    def grade(reply, expected=expected):
                        results = grader_results(reply, recipe.extension, 1)
                        if results[0].valid != (expected is None) or reply["failure_codes"] != [expected]:
                            raise ValueError("workbook grade differs from the reviewed behavior")
                        return reply

                    if await call(f"grade-{index:02d}", recipe.extension.grader, protected, {
                        "examples": [{"input": case.action.input, "expected": truth, "output": output}],
                    }, grade) is None:
                        break
                if len(measurements) == review["max_new_operations"] and all(row["contract_matched"] for row in measurements):
                    cases = IntegrationCaseSet(
                        request_id="workbook-recovery-ordinary-preparation", purpose="stack_integration_only",
                        recipe_digest=content_digest(recipe), environment_digest=content_digest(env),
                        benchmark_pack_digest=recipe.dependencies["benchmark_pack"], seed=0, cases=[case],
                    )
                    put(RESULT / "environment.json", env.model_dump(mode="json"))
                    put(RESULT / "case-set.json", cases.model_dump(mode="json"))
        put(RESULT / "ledger.json", repo.operation_ledger(name).model_dump(mode="json"))
    passed = len(measurements) == review["max_new_operations"] and all(row["contract_matched"] for row in measurements)
    put(RESULT / "result.json", {"review_sha256": exact, "passed": passed, "operations": measurements,
                               "image_id": identity, "models": 0, "cash_usd": 0, "formal_case_adopted": False})
    return passed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    args = parser.add_mutually_exclusive_group(required=True)
    args.add_argument("--prepare-renewal", action="store_true")
    args.add_argument("--preflight", action="store_true")
    args.add_argument("--exact-review")
    options = parser.parse_args()
    if options.exact_review:
        raise SystemExit(not asyncio.run(run(options.exact_review)))
    review, *_ = load_review(prepare=options.prepare_renewal)
    if options.prepare_renewal:
        put(REVIEW, review)
    print(file_digest(REVIEW))
