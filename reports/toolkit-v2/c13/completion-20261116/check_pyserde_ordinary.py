"""Prepare and observe the pinned pyserde repair with the ordinary protected grader."""

import argparse
import asyncio
import json
import re
import shutil
import subprocess
import time
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from zipfile import ZipFile

import check_migrated_graders as native
from audit_staged_repository_graders import bind, wheel_probe_assets
from check_linux_install import DOCKER, HERE, SOCKET, Scope, docker, get, put
from check_staged_offline_cases import launch_binding
from repository_offline_pair_batch import context, verify_probe
from stage_protected_inputs import RESERVE, tree
from stage_pyserde_production_repair import CASE, EVIDENCE, REVISION
from stage_repository_transport import digest, encode, read

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentLimits,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.repository_suites import grade_suite_output
from aeep.executors.command import CommandExecutor
from aeep.models import ExecutionReceipt, ExecutorSpec, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import file_digest
from aeep_toolkit.workflow_evidence import open_store

NAME = "aeep-c13-pyserde-682-ordinary"
NAME_TAG = "aeep-repository-grader:pyserde-682-20261116"
PARENT_TAG = "aeep-assessment-runtime:0.8"
PARENT = native.CARRIER
PREPARATION = HERE / "pyserde-production-repair-preflight.json"
ACQUISITION = EVIDENCE / "wheelhouse-evidence.json"
ARCHIVES = EVIDENCE / "staged-with-lock/worker-transport"
PRIVATE = EVIDENCE / "ordinary"
CONTEXT = PRIVATE / "build"
CONFIG = PRIVATE / "docker-config"
REVIEW = HERE / "pyserde-ordinary-operation-review.json"
APPROVAL = PRIVATE / "approval.json"
RUN = PRIVATE / "execution"
PLUGIN = Path("/Applications/Docker.app/Contents/Resources/cli-plugins/docker-buildx")
ROLES = ("reference", "original", "deserialization_only", "serialization_only")
BUILD_TIMEOUT = 180
ENV = {"HOME": str(PRIVATE), "PATH": "/usr/bin:/bin", "LC_ALL": "C", "DOCKER_BUILDKIT": "1"}
CLIENT = [DOCKER, "--config", str(CONFIG), "--host", f"unix://{SOCKET}", "buildx"]
FILES = (
    PREPARATION,
    ACQUISITION,
    CONFIG / "config.json",
    Path(__file__),
    Path(DOCKER),
    PLUGIN,
    *(
        HERE / (script + ".py")
        for script in (
            "check_linux_install",
            "check_migrated_graders",
            "audit_staged_repository_graders",
            "check_staged_offline_cases",
            "stage_pyserde_production_repair",
            "repository_offline_pair_batch",
            "stage_repository_transport",
            "stage_protected_inputs",
        )
    ),
)
INSTALL = [
    "python3",
    "-I",
    "-m",
    "pip",
    "--isolated",
    "install",
    "--no-index",
    "--no-deps",
    "--force-reinstall",
    "--no-compile",
    "--disable-pip-version-check",
    "--no-cache-dir",
    "--no-input",
    "--only-binary=:all:",
    "--require-hashes",
    "--find-links",
    "/opt/aeep-pyserde-runtime",
    "-r",
    "/opt/aeep-pyserde-runtime/requirements.txt",
]
DOCKERFILE = (
    f"FROM {PARENT_TAG}\nUSER 0:0\nCOPY wheels/ /opt/aeep-pyserde-runtime/\n"
    f"RUN {json.dumps(INSTALL)}\nUSER 65534:65534\n"
)


def wheel_inputs():
    lock = get(PREPARATION)["locked_dependency_projection"]
    acquired = get(ACQUISITION)
    if (
        set(acquired["assets"]) != set(lock["wheels"])
        or lock["missing_platform_wheels"]
        or acquired["source_lock_sha256"] != lock["lock_sha256"]
        or acquired["installed_or_executed"] is not False
    ):
        raise ValueError("staged wheel closure differs from the published lock")
    requirements, wheels = [], {}
    for project, pin in sorted(lock["wheels"].items()):
        item = acquired["assets"][project]
        name = pin["filename"]
        path = EVIDENCE / "wheelhouse" / name
        sha = pin["hash"].removeprefix("sha256:")
        data = read(path, sha)
        if (
            Path(name).name != name
            or path.is_symlink()
            or (
                item["filename"],
                item["artifact_sha256"],
                item["version"],
                item["bytes"],
                len(data),
            )
            != (name, sha, pin["version"], pin["size"], pin["size"])
        ):
            raise ValueError("wheel no longer matches the lock")
        licenses = item["licenses"]
        with ZipFile(path) as wheel:
            (metadata,) = [
                name for name in wheel.namelist() if name.endswith(".dist-info/METADATA")
            ]
            if (
                digest(wheel.read(metadata)) != licenses["metadata_sha256"]
                or not licenses["notice_sha256"]
                or any(
                    digest(wheel.read(name)) != value
                    for name, value in licenses["notice_sha256"].items()
                )
            ):
                raise ValueError("wheel notice drift")
        wheels[name] = data
        requirements.append(f"{project}=={pin['version']} --hash=sha256:{sha}")
    return wheels, ("\n".join(requirements) + "\n").encode()


def build_inputs():
    wheels, requirements = wheel_inputs()
    return {
        "Dockerfile": DOCKERFILE.encode(),
        "wheels/requirements.txt": requirements,
        **{f"wheels/{name}": data for name, data in wheels.items()},
    }


def stage():
    if REVIEW.exists() or shutil.disk_usage(EVIDENCE).free < RESERVE + 256 * 1024**2:
        raise ValueError("fresh review and sufficient free capacity required")
    files = build_inputs()
    PRIVATE.mkdir(mode=0o700)
    (CONTEXT / "wheels").mkdir(parents=True)
    CONFIG.mkdir(mode=0o700)
    for name, data in files.items():
        (CONTEXT / name).write_bytes(data)
        (CONTEXT / name).chmod(0o444)
    put(CONFIG / "config.json", {"cliPluginsExtraDirs": [str(PLUGIN.parent)]})


def image(reference):
    data = json.loads(docker("image", "inspect", "--format", "{{json .}}", reference))
    cfg = data["Config"]
    if (
        (data["Os"], data["Architecture"], cfg["User"]) != ("linux", "arm64", "65534:65534")
        or cfg.get("Volumes")
        or cfg.get("Healthcheck")
        or cfg.get("OnBuild")
    ):
        raise ValueError("retained grader image boundary changed")
    return data["Id"], data["RootFS"]["Layers"], content_digest(cfg)


def preflight_build():
    if get(CONFIG / "config.json") != {"cliPluginsExtraDirs": [str(PLUGIN.parent)]}:
        raise ValueError("private Docker client configuration differs")
    observed = subprocess.run(
        [*CLIENT, "inspect", "default"],
        env=ENV,
        stdin=subprocess.DEVNULL,
        timeout=20,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if (
        not re.search(r"^Driver:\s+docker\s*$", observed, re.M)
        or not re.search(r"^Status:\s+running\s*$", observed, re.M)
        or not re.search(r"^Platforms:\s+.*\blinux/arm64(?:,|$)", observed, re.M)
        or docker("image", "ls", "--filter", f"reference={NAME_TAG}", "-q")
        or shutil.disk_usage(EVIDENCE).free < RESERVE + 256 * 1024**2
    ):
        raise ValueError(
            "local Docker builder, unused image tag and additional free space required"
        )


def verify_execution_inputs(record, exact):
    native.project_source()
    if (
        file_digest(REVIEW) != exact
        or shutil.disk_usage(EVIDENCE).free < RESERVE
        or any(file_digest(Path(path)) != pin for path, pin in record["pins"].items())
    ):
        raise ValueError("reviewed inputs, executable or host reserve changed")


async def inspect():
    native.project_source()
    context_nodes = tree(CONTEXT)
    client_nodes = tree(CONFIG)
    files = {
        str(Path(name).relative_to(CONTEXT)): entry["sha256"]
        for name, entry in context_nodes.items()
        if "sha256" in entry
    }
    if (
        files != {path: digest(data) for path, data in build_inputs().items()}
        or get(CONFIG / "config.json") != {"cliPluginsExtraDirs": [str(PLUGIN.parent)]}
        or not set(client_nodes)
        <= {
            str(CONFIG / name)
            for name in (
                ".",
                "config.json",
                "buildx",
                "buildx/.lock",
                "buildx/activity",
                "buildx/defaults",
                "buildx/instances",
            )
        }
    ):
        raise ValueError("private build context changed")
    parent, layers, config = image(PARENT_TAG)
    if parent != PARENT:
        raise ValueError("local parent tag no longer resolves to the reviewed image")
    preparation = get(PREPARATION)
    (row,) = json.loads(read(ARCHIVES / "private-index.json", preparation["private_index_sha256"]))
    if (row["input"]["task_id"], row["source_revision"]) != (CASE, REVISION):
        raise ValueError("protected task identity changed")
    wheel_review, assets = wheel_probe_assets()
    task, truth, _, _, _ = bind(row, ARCHIVES, assets)
    artifacts = json.loads(
        read(
            ARCHIVES / "protected" / CASE / "calibration.json",
            preparation["private_control_set_sha256"],
        )
    )
    if set(artifacts) != set(ROLES):
        raise ValueError("protected role inventory changed")
    with closing(open_store(str(native.DATABASE))) as store:
        prior, _, definitions, _ = await native.prepare(AssessmentRepository(store))
    spec = definitions["recipe"].extension.grader
    environment = AssessmentEnvironment(
        environment_id=NAME,
        identity={"source": native.SOURCE},
        kind="container",
        container_image=parent,
        container_runtime=DOCKER,
        container_socket=SOCKET,
        container_tmpfs_mb=64,
        memory_mb=512,
        process_limit=96,
    )
    template = ContainerExecutor(environment)
    test_ids = truth.fail_to_pass + truth.pass_to_pass
    calls = {}
    for role in ROLES:
        operation = f"{NAME}:{role}"

        async def capture(payload, operation=operation, role=role):
            launch = context(spec, operation, payload)
            _, container = template.command(launch)
            calls[role] = {
                "archive_sha256": payload["archive_sha256"],
                "payload_sha256": digest(encode(payload)),
                "operation": operation,
                "container": container,
                "parent_argv_sha256": launch_binding(spec, template, operation, payload),
            }
            return {field: payload[field] for field in ("archive_sha256", "python", "pytest")} | {
                "exit_code": 0,
                "statuses": dict.fromkeys(test_ids, "PASSED"),
            }

        score = await grade_suite_output(
            task.model_dump(mode="json"), truth.model_dump(mode="json"), artifacts[role], capture
        )
        if (
            not score.valid
            or len(test_ids) != 5
            or any(
                calls[role][key] != val
                for key, val in preparation["ordinary_callback_payloads"][role].items()
            )
        ):
            raise ValueError("ordinary callback changed from the reviewed role")
    build = ExecutorSpec(
        id="toolkit.pyserde.grader.build",
        capability="toolkit.upstream-engineering@1",
        kind="command",
        side_effect="write",
        description="Install exactly the locked wheel closure in one private offline image.",
        config={
            "argv": [
                *CLIENT,
                "build",
                "--builder",
                "default",
                "--pull=false",
                "--network=none",
                "--platform=linux/arm64",
                "--provenance=false",
                "--sbom=false",
                "--load",
                "--iidfile",
                str(RUN / "image-id"),
                "--tag",
                NAME_TAG,
                str(CONTEXT),
            ],
            "argv_literal": True,
            "inherit_env": False,
            "env": ENV,
            "timeout_seconds": BUILD_TIMEOUT,
            "max_output_bytes": 65536,
            "output": {"type": "text"},
        },
    )
    record = {
        "schema_version": "aeep.c13.pyserde-ordinary-review.v1",
        "purpose": "Verify one published two-file repair, original source and two single-file partial repairs.",
        "source": prior["source"],
        "revision": REVISION,
        "runtime_template": environment.model_dump(mode="json"),
        "parent_layers": layers,
        "parent_config_sha256": config,
        "pins": {str(path): file_digest(path) for path in FILES},
        "protected_pytest_wheel_review_sha256": wheel_review,
        "build_context_sha256": content_digest(context_nodes),
        "private_client_state_sha256": content_digest(client_nodes),
        "build_inputs": files,
        "tag": NAME_TAG,
        "build_spec": build.model_dump(mode="json"),
        "grader_sha256": content_digest(spec),
        "required_identities": len(test_ids),
        "calls": calls,
        "maximum_operations": 1 + len(calls),
        "maximum_reserved_seconds": BUILD_TIMEOUT
        + 5
        + len(calls) * (spec.config["timeout_seconds"] + 5),
        "required_free_bytes": RESERVE,
        "minimum_build_headroom_bytes": 256 * 1024**2,
        "downloads": 0,
        "models": 0,
        "cash_usd": 0,
        "existing_resources_removed": 0,
        "provider_disclosure": False,
        "extra_host_mounts": False,
        "network": False,
        "maximum_attempts": 1,
        "stop_policy": "Stop after a build failure, uncertain cleanup or grader error. Run controls only after a passing reference. Retain actual scores and charges. No automatic repeat.",
    }
    return record, build, spec, environment, task, truth, artifacts


def validate_image(record):
    identity = (RUN / "image-id").read_text().strip()
    observed, layers, config = image(NAME_TAG)
    if (
        not re.fullmatch(r"sha256:[0-9a-f]{64}", identity)
        or observed != identity
        or layers[:-2] != record["parent_layers"]
        or config != record["parent_config_sha256"]
    ):
        raise ValueError("derived grader image layers or inherited configuration differ")
    return identity


def valid_reply(value, payload, required):
    return (
        isinstance(value, dict)
        and type(value.get("exit_code")) is int
        and value["exit_code"] in (0, 1)
        and isinstance(value.get("statuses"), dict)
        and all(value["statuses"].get(name) in ("PASSED", "FAILED") for name in required)
        and all(status in ("PASSED", "FAILED") for status in value["statuses"].values())
        and verify_probe(value, payload, {}, value["exit_code"])
        and (value["exit_code"] == 0)
        is all(status == "PASSED" for status in value["statuses"].values())
    )


async def measure(repo, request, stage, ctx, runner, validate, owned=None):
    operation = ctx.attempt_id
    if owned and docker("ps", "-aq", "--filter", f"name=^/{owned}$"):
        raise ValueError("protected container name already exists")
    repo.reserve(
        request,
        operation,
        AssessmentLimits(
            max_operations=1,
            max_elapsed_seconds=ctx.spec.config["timeout_seconds"] + 5,
        ),
        stage=stage,
        require_settled_plan=True,
    )
    started, tick = utc_now(), time.monotonic()
    raw = await runner.execute(ctx)
    if (owned and docker("ps", "-aq", "--filter", f"name=^/{owned}$")) or (
        not owned and raw.status.value == "timeout"
    ):
        raise RuntimeError("uncertain grader cleanup or build; retain the reservation")
    value, error = None, raw.error_type
    if raw.status.value == "success":
        try:
            value = validate(raw.output)
        except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
            error = type(exc).__name__
    receipt = ExecutionReceipt(
        decision_id=operation,
        action_id=operation,
        capability=ctx.spec.capability,
        executor_id=ctx.spec.id,
        executor_kind=ctx.spec.kind,
        status="success" if value is not None else "failed",
        execution_success=value is not None,
        error_type=None if value is not None else error or "PROTECTED_GRADER_UNVERIFIED",
        started_at=started,
        ended_at=utc_now(),
        estimated=ctx.estimate,
        actual_resources=raw.resources,
        metadata={
            "container_removed": True if owned else None,
            "observation_sha256": content_digest(value) if value is not None else None,
        },
    )
    repo.store.save_receipt(receipt)
    repo.finish_operation(
        operation, elapsed_seconds=time.monotonic() - tick, resources=raw.resources
    )
    return receipt.receipt_id, value


async def observe(record, repo, request, build, spec, environment, task, truth, artifacts, exact):
    verify_execution_inputs(record, exact)
    if (
        image(PARENT_TAG)
        != (environment.container_image, record["parent_layers"], record["parent_config_sha256"])
        or content_digest(tree(CONTEXT)) != record["build_context_sha256"]
        or content_digest(tree(CONFIG)) != record["private_client_state_sha256"]
    ):
        raise ValueError("local parent or build context drifted before dispatch")
    builder = CommandExecutor()
    try:
        receipt, derived = await measure(
            repo,
            request,
            "build_pyserde_grader",
            context(build, NAME + ":build", {}),
            builder,
            lambda _: validate_image(record),
        )
    finally:
        await builder.close()
    put(RUN / "build.json", {"receipt_id": receipt, "image_id": derived})
    if derived is None:
        return []
    executor = ContainerExecutor(environment.model_copy(update={"container_image": derived}))
    parent = ContainerExecutor(environment)
    observations = []
    required = truth.fail_to_pass + truth.pass_to_pass
    try:
        for role in ROLES:
            binding = record["calls"][role]
            operation = binding["operation"]
            result = {}

            async def probe(
                payload, *, operation=operation, binding=binding, role=role, result=result
            ):
                verify_execution_inputs(record, exact)
                trial = context(spec, operation, payload)
                argv, owned = executor.command(trial)
                parent_argv, _ = parent.command(trial)
                if (
                    digest(encode(payload)) != binding["payload_sha256"]
                    or owned != binding["container"]
                    or payload["archive_sha256"] != binding["archive_sha256"]
                    or argv
                    != [
                        derived if word == environment.container_image else word
                        for word in parent_argv
                    ]
                    or launch_binding(spec, parent, operation, payload)
                    != binding["parent_argv_sha256"]
                ):
                    raise ValueError(
                        "observed grader invocation differs from the reviewed assignment"
                    )
                receipt_id, value = await measure(
                    repo,
                    request,
                    "protected_pyserde_grader",
                    trial,
                    executor,
                    lambda reply: reply if valid_reply(reply, payload, required) else None,
                    owned=owned,
                )
                result.update(role=role, receipt_id=receipt_id, native_observation=value)
                put(RUN / f"{role}-observation.json", result)
                if value is None:
                    raise RuntimeError(
                        "protected grader did not return complete native observations"
                    )
                return value

            score = await grade_suite_output(
                task.model_dump(mode="json"), truth.model_dump(mode="json"), artifacts[role], probe
            )
            failed = [
                name
                for name in required
                if result["native_observation"]["statuses"][name] == "FAILED"
            ]
            entry = {
                "role": role,
                "receipt_id": result["receipt_id"],
                "grade": score.model_dump(mode="json"),
                "failed_required_tests": failed,
            }
            put(RUN / f"{role}-grade.json", entry)
            observations.append(entry)
            if role == "reference" and not score.valid:
                break
    finally:
        await executor.close()
    return observations


async def run(exact):
    native.approved(exact, REVIEW, APPROVAL, RUN)
    reviewed = get(REVIEW)
    expires = datetime.fromisoformat(reviewed.pop("expires_at"))
    record, build, spec, environment, task, truth, artifacts = await inspect()
    if record != reviewed or expires <= utc_now():
        raise ValueError("approved pyserde scope drifted or expired")
    preflight_build()
    RUN.mkdir(mode=0o700)
    scope = Scope(review_sha256=exact)
    sha = content_digest(scope)
    request = RecipeMaterializationRequest(
        plan_id=NAME,
        authorization_id=NAME,
        subject_digest=sha,
        recipe_digest=sha,
        environment_digest=sha,
        mapping_digest=sha,
        definition_digests=[sha],
        seed=0,
    )
    grant = AssessmentAuthorization(
        authorization_id=NAME,
        subject_digests=[sha],
        recipe_digests=[sha],
        environment_digests=[sha],
        allowed_destinations=["local"],
        expires_at=expires,
        remote_disclosure=False,
        limits=AssessmentLimits(
            max_operations=record["maximum_operations"],
            max_elapsed_seconds=record["maximum_reserved_seconds"],
            max_model_turns=0,
        ),
    )
    with ReceiptStore(RUN / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        repo.put("pyserde_ordinary_scope", sha, scope)
        repo.approve_bundle(grant, {sha: scope.model_dump(mode="json")})
        try:
            rows = await observe(
                record, repo, request, build, spec, environment, task, truth, artifacts, exact
            )
        finally:
            put(RUN / "ledger.json", repo.operation_ledger(NAME).model_dump(mode="json"))
    passed = (
        len(rows) == len(ROLES)
        and rows[0]["grade"]["valid"]
        and bool(set(rows[1]["failed_required_tests"]) & set(truth.fail_to_pass))
        and all(row["failed_required_tests"] for row in rows[2:])
    )
    put(
        RUN / "result.json",
        {
            "review_sha256": exact,
            "multi_file_proof": passed,
            "roles": rows,
            "formal_case_adopted": False,
            "model_turns": 0,
            "cash_usd": 0,
        },
    )
    return passed


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--execute")
    args = parser.parse_args()
    if args.execute:
        return await run(args.execute)
    if args.prepare:
        stage()
    preflight_build()
    record, *_ = await inspect()
    if args.prepare:
        put(REVIEW, {**record, "expires_at": (utc_now() + timedelta(days=3)).isoformat()})
    elif record != {key: val for key, val in get(REVIEW).items() if key != "expires_at"}:
        raise ValueError("unstarted review does not match current inputs")
    print(
        json.dumps(
            {
                "review_sha256": file_digest(REVIEW),
                "operations": record["maximum_operations"],
                "reserved_seconds": record["maximum_reserved_seconds"],
                "protected_roles": list(record["calls"]),
            }
        )
    )
    return True


if __name__ == "__main__":
    raise SystemExit(not asyncio.run(main()))
