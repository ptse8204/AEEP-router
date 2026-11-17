"""Verify the ordinary Formula Extraction recipe with the pinned offline renderer."""

import argparse
import asyncio
import base64
import json
import re
import shutil
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from check_linux_install import DOCKER, FROZEN, HERE, SOCKET, Scope, docker, get, put
from formula_recipe_guest import response
from prepare_formula_recipe import CONTEXT, EXECUTION, GUEST, HISTORICAL_REVIEW, TARGET
from repository_offline_pair_batch import context
from stage_protected_inputs import RESERVE, tree

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.extensions import grader_results, require_environment
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentLimits,
    IntegrationCaseSet,
    RecipeDefinition,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.benchmarking import BenchmarkCase
from aeep.executors.command import CommandExecutor
from aeep.models import ExecutionReceipt, ExecutorSpec, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import file_digest

NAME = "aeep-c13-formula-ordinary"
TAG = "aeep-skillsbench-formula:ordinary-amd64-20261116"
REVIEW = HERE / "formula-ordinary-operation-review.json"
APPROVAL = TARGET / "approval.json"
RUN = TARGET / "execution"
CONFIG = TARGET / "docker-config"
PLUGIN = Path("/Applications/Docker.app/Contents/Resources/cli-plugins/docker-buildx")
CONFIG_CONTENTS = {"cliPluginsExtraDirs": [str(PLUGIN.parent)]}
CLIENT_ENV = {
    "HOME": str(TARGET),
    "PATH": "/usr/bin:/bin",
    "LC_ALL": "C",
    "DOCKER_BUILDKIT": "1",
}
BUILD_CAP = 180
BUILD_CLIENT = [DOCKER, "--config", str(CONFIG), "--host", f"unix://{SOCKET}", "buildx"]
BUILD = [
    *BUILD_CLIENT,
    "build",
    "--builder",
    "default",
    "--pull=false",
    "--network=none",
    "--platform=linux/amd64",
    "--provenance=false",
    "--sbom=false",
    "--load",
    "--iidfile",
    str(RUN / "image-id"),
    "--tag",
    TAG,
    str(CONTEXT),
]


def image_info(reference):
    data = json.loads(docker("image", "inspect", "--format", "{{json .}}", reference))
    config = data["Config"]
    if (data["Os"], data["Architecture"]) != ("linux", "amd64"):
        raise ValueError("formula carrier platform changed")
    if config.get("Volumes") or config.get("Healthcheck"):
        raise ValueError("formula carrier declares a volume or healthcheck")
    return (
        data["Id"],
        data["RootFS"]["Layers"],
        {field: config.get(field) for field in ("User", "Entrypoint", "Cmd", "WorkingDir", "Env")},
    )


def commands(recipe, case, environment):
    extension = recipe.extension
    assert extension is not None
    require_environment(recipe, environment)
    inputs = case.action.input
    truth = case.validators[-1].config["expected"]
    ref = CONTEXT / "renderer/protected-fixtures/reference.md"
    artifact = {"markdown_b64": base64.b64encode(ref.read_bytes()).decode("ascii")}
    executor = ContainerExecutor(environment)
    rows = [
        (
            "reference",
            extension.reference,
            {"inputs": [inputs]},
            {"outputs": [artifact]},
        )
    ]
    for label, value, code in [
        ("grade-reference", artifact, None),
        ("grade-fault-0", extension.fault_outputs[0], "upstream_rejected"),
        ("grade-fault-1", extension.fault_outputs[1], "upstream_rejected"),
    ]:
        rows.append(
            (
                label,
                extension.grader,
                {"examples": [{"input": inputs, "expected": truth, "output": value}]},
                response(code),
            )
        )
    for role, spec, payload, expected in rows:
        operation = context(spec, NAME + ":" + role, payload)
        argv, owned = executor.command(operation)
        source = FROZEN / "src"
        if (
            {arg for arg in argv if arg.startswith("type=bind,")}
            != {f"type=bind,src={source},dst={source},readonly"}
            or argv[argv.index("--network") + 1] != "none"
            or argv[argv.index("--user") + 1] != "65534:65534"
            or not {
                "--read-only",
                "--pull=never",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
            }
            <= set(argv)
        ):
            raise ValueError("ordinary formula containment changed")
        # The reviewed placeholder image is replaced only by the verified build output.
        argv[argv.index(environment.container_image)] = "<verified-formula-image>"
        evidence = {
            "role": role,
            "container": owned,
            "argv_sha256": content_digest({"argv": argv}),
            "payload_sha256": content_digest(payload),
            "expected_sha256": content_digest(expected),
            "seconds": spec.config["timeout_seconds"] + 5,
        }
        yield operation, expected, evidence


def checked():
    prepared = get(HERE / "formula-ordinary-preparation.json")
    recipe = RecipeDefinition.model_validate(get(TARGET / "recipe.json"))
    case = BenchmarkCase.model_validate(get(TARGET / "case.json"))
    nodes = tree(CONTEXT)
    files = {
        str(Path(path).relative_to(CONTEXT)): {
            **node,
            "bytes": Path(path).stat().st_size,
            "mode": format(node["mode"], "04o"),
        }
        for path, node in nodes.items()
        if "sha256" in node
    }
    parent, layers, config = image_info(prepared["parent_tag"])
    if (
        files != get(TARGET / "context-files.json")
        or content_digest(files) != prepared["context_digest"]
        or content_digest(recipe) != prepared["recipe_digest"]
        or content_digest(case) != prepared["case_digest"]
        or parent != prepared["source_parent"]
        or layers != prepared["parent_layers"]
        or file_digest(HISTORICAL_REVIEW) != prepared["historical_review_sha256"]
        or file_digest(EXECUTION / "ledger.json") != prepared["historical_ledger_sha256"]
        or (CONTEXT / "Dockerfile").read_text()
        != (
            f"FROM {prepared['parent_tag']}\nCOPY renderer/ {GUEST}/\n"
            "COPY python/ /opt/aeep-assessment-python/\n"
            "COPY aeep-assessment.pth /usr/local/lib/python3.12/dist-packages/aeep-assessment.pth\n"
        )
        or get(CONFIG / "config.json") != CONFIG_CONTENTS
    ):
        raise ValueError("formula case, image context or protected evidence changed")
    original = get(HISTORICAL_REVIEW)
    environment = AssessmentEnvironment.model_validate(
        {
            **original["staged"]["carrier"],
            "environment_id": NAME,
            "container_image": parent,
            "read_only_roots": [],
            "identity": {"role": "protected-grader"},
        }
    )
    specs = [entry[2] for entry in commands(recipe, case, environment)]
    remaining = sum(entry["seconds"] for entry in specs)
    paths = [
        Path(__file__),
        HERE / "check_linux_install.py",
        HERE / "stage_protected_inputs.py",
        HERE / "prepare_formula_recipe.py",
        HERE / "formula_recipe_guest.py",
        HERE / "repository_offline_pair_batch.py",
        Path(DOCKER),
        PLUGIN,
    ]
    return (
        {
            "kind": "offline-formula-ordinary-grader",
            "delegated_definition_record": "reports/toolkit-v2/c13/pipeline-standing-authority-20261104.json",
            "previous_protected_run_sha256": prepared["historical_review_sha256"],
            "previous_ledger_sha256": prepared["historical_ledger_sha256"],
            "frozen_source_sha256": verification_source_digest(FROZEN),
            "pins": {str(path): file_digest(path) for path in paths},
            "context_tree_sha256": content_digest(nodes),
            "context_bytes": prepared["context_bytes"],
            "parent_image": parent,
            "parent_layers": layers,
            "parent_config_sha256": content_digest(config),
            "tag": TAG,
            "build_argv": BUILD,
            "build_client_env": CLIENT_ENV,
            "recipe_sha256": content_digest(recipe),
            "case_sha256": content_digest(case),
            "environment_template_sha256": content_digest(environment),
            "calls": specs,
            "maximum_operations": 1 + len(specs),
            "maximum_reserved_seconds": BUILD_CAP + remaining + 5,
            "minimum_free_bytes": RESERVE,
            "models": 0,
            "cash_usd": 0,
            "downloads": 0,
            "existing_resources_removed": 0,
            "provider_disclosure": False,
            "maximum_attempts": 1,
        },
        recipe,
        case,
        environment,
    )


def preflight_build(fields):
    state = subprocess.run(
        [*BUILD_CLIENT, "inspect", "default"],
        env=CLIENT_ENV,
        stdin=subprocess.DEVNULL,
        timeout=20,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if (
        not re.search(r"^Driver:\s+docker\s*$", state, re.M)
        or not re.search(r"^Status:\s+running\s*$", state, re.M)
        or not re.search(r"^Platforms:\s+.*\blinux/amd64(?:,|$)", state, re.M)
        or docker("image", "ls", "--filter", f"reference={TAG}", "-q")
        or shutil.disk_usage(CONTEXT).free < RESERVE + fields["context_bytes"] * 2
    ):
        raise ValueError(
            "formula build requires the local Docker builder, a fresh tag and free capacity"
        )


def derived_image(review):
    identity = (RUN / "image-id").read_text().strip()
    observed, layers, config = image_info(TAG)
    if (
        not re.fullmatch("sha256:[a-f0-9]{64}", identity)
        or observed != identity
        or len(layers) != len(review["parent_layers"]) + 3
        or layers[:-3] != review["parent_layers"]
        or content_digest(config) != review["parent_config_sha256"]
    ):
        raise ValueError(
            "derived formula image differs from its local parent or COPY-only definition"
        )
    return identity


async def dispatch(exact):
    if (
        RUN.exists()
        or file_digest(REVIEW) != exact
        or not APPROVAL.is_file()
        or get(APPROVAL) != {"approved": True, "review_sha256": exact}
    ):
        raise ValueError("this unstarted formula execution requires the exact repeat approval")
    record = get(REVIEW)
    expires = datetime.fromisoformat(record.pop("expires_at"))
    review, recipe, case, template = checked()
    if record != review or utc_now() >= expires:
        raise ValueError("approved formula inputs or expiration changed")
    preflight_build(review)
    RUN.mkdir(mode=0o700)
    scope = Scope(review_sha256=exact)
    digest = content_digest(scope)
    grant = AssessmentAuthorization(
        authorization_id=NAME,
        subject_digests=[digest],
        recipe_digests=[digest],
        environment_digests=[digest],
        allowed_destinations=["local"],
        expires_at=expires,
        remote_disclosure=False,
        limits=AssessmentLimits(
            max_operations=review["maximum_operations"],
            max_elapsed_seconds=review["maximum_reserved_seconds"],
            max_model_turns=0,
        ),
    )
    request = RecipeMaterializationRequest(
        plan_id=NAME,
        authorization_id=NAME,
        subject_digest=digest,
        recipe_digest=digest,
        environment_digest=digest,
        mapping_digest=digest,
        definition_digests=[digest],
        seed=0,
    )
    operations = []
    with ReceiptStore(RUN / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        repo.put("formula_ordinary_scope", digest, scope)
        repo.approve_bundle(grant, {digest: scope.model_dump(mode="json")})

        async def run(ctx, executor, label, seconds, validate, container=None):
            pattern = f"name=^/{container}$"
            if (
                file_digest(REVIEW) != exact
                or shutil.disk_usage(CONTEXT).free < RESERVE
                or (container and docker("ps", "-aq", "--filter", pattern))
            ):
                raise ValueError("formula scope or owned execution boundary changed")
            operation = ctx.attempt_id
            repo.reserve(
                request,
                operation,
                AssessmentLimits(max_operations=1, max_elapsed_seconds=seconds),
                stage="formula_ordinary_grading",
                require_settled_plan=True,
            )
            start, clock = utc_now(), time.monotonic()
            raw = await executor.execute(ctx)
            if (container and docker("ps", "-aq", "--filter", pattern)) or (
                container is None and raw.status.value == "timeout"
            ):
                raise RuntimeError(
                    "formula execution is indeterminate; retain the open reservation"
                )
            result = None
            error = raw.error_type
            if raw.status.value == "success":
                try:
                    result = validate(raw.output)
                except (ValueError, KeyError, TypeError, OSError) as exc:
                    error = type(exc).__name__
            matched = result is not None
            metadata = {
                "role": label,
                "review_sha256": exact,
                "contract_matched": matched,
                "output_sha256": content_digest(result) if matched else None,
                "container_absent": True if container else None,
            }
            receipt = ExecutionReceipt(
                decision_id=operation,
                action_id=operation,
                capability=ctx.spec.capability,
                executor_id=ctx.spec.id,
                executor_kind=ctx.spec.kind,
                status="success" if matched else "failed",
                execution_success=matched,
                error_type=None if matched else error or "FORMULA_RECIPE_CONTRACT_MISMATCH",
                started_at=start,
                ended_at=utc_now(),
                estimated=ctx.estimate,
                actual_resources=raw.resources,
                metadata=metadata,
            )
            store.save_receipt(receipt)
            repo.finish_operation(
                operation, elapsed_seconds=time.monotonic() - clock, resources=raw.resources
            )
            row = {"receipt_id": receipt.receipt_id, **metadata}
            put(RUN / f"{label}.json", row)
            operations.append(row)
            return result

        spec = ExecutorSpec(
            id="skillsbench.formula.build",
            capability="toolkit.upstream-engineering@1",
            kind="command",
            side_effect="write",
            description="Pinned COPY-only formula grader",
            config={
                "argv": BUILD,
                "argv_literal": True,
                "inherit_env": False,
                "env": CLIENT_ENV,
                "timeout_seconds": BUILD_CAP,
                "max_output_bytes": 65536,
                "output": {"type": "text"},
            },
        )
        builder = CommandExecutor()
        try:
            image = await run(
                context(spec, NAME + ":build", {}),
                builder,
                "build",
                BUILD_CAP + 5,
                lambda _: {"image_id": derived_image(review)},
            )
        finally:
            await builder.close()

        if image:
            environment = template.model_copy(
                update={
                    "container_image": image["image_id"],
                    "identity": {"operation_review_sha256": exact},
                }
            )
            launch = list(commands(recipe, case, environment))
            if [entry[2] for entry in launch] != review["calls"]:
                raise ValueError("ordinary launch changed after the build")
            executor = ContainerExecutor(environment)
            assert recipe.extension is not None
            for ctx, expected, info in launch:

                def validate(value, expected=expected):
                    if not isinstance(value, dict) or content_digest(value) != content_digest(
                        expected
                    ):
                        raise ValueError("formula outcome differs from protected expectations")
                    if "failure_codes" in expected:
                        grader_results(value, recipe.extension, 1)
                    return value

                if (
                    await run(
                        ctx, executor, info["role"], info["seconds"], validate, info["container"]
                    )
                    is None
                ):
                    break
            if len(operations) == review["maximum_operations"] and all(
                row["contract_matched"] for row in operations
            ):
                cases = IntegrationCaseSet(
                    request_id=NAME,
                    purpose="stack_integration_only",
                    recipe_digest=content_digest(recipe),
                    environment_digest=content_digest(environment),
                    benchmark_pack_digest=recipe.dependencies["benchmark_pack"],
                    seed=0,
                    cases=[case],
                )
                put(RUN / "environment.json", environment.model_dump(mode="json"))
                put(RUN / "case-set.json", cases.model_dump(mode="json"))
        put(RUN / "ledger.json", repo.operation_ledger(NAME).model_dump(mode="json"))
    verified = len(operations) == review["maximum_operations"] and all(
        row["contract_matched"] for row in operations
    )
    put(
        RUN / "result.json",
        {
            "review_sha256": exact,
            "verified": verified,
            "operations": operations,
            "image": image,
            "models": 0,
            "cash_usd": 0,
            "formal_case_adopted": False,
        },
    )
    return verified


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--exact-review")
    args = parser.parse_args()
    if args.exact_review:
        return not asyncio.run(dispatch(args.exact_review))
    if args.prepare and not CONFIG.exists():
        CONFIG.mkdir(mode=0o700)
        put(CONFIG / "config.json", CONFIG_CONTENTS)
    fields = checked()[0]
    preflight_build(fields)
    if args.prepare:
        put(REVIEW, {**fields, "expires_at": (utc_now() + timedelta(days=3)).isoformat()})
    else:
        published = get(REVIEW)
        if utc_now() >= datetime.fromisoformat(published.pop("expires_at")) or fields != published:
            raise ValueError("formula review drifted or expired")
    print(file_digest(REVIEW))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
