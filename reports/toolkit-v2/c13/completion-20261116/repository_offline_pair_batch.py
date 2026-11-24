"""Prepare and verify retained repository pairs through the ordinary protected callback."""

import argparse
import asyncio
import json
import shutil
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from check_linux_install import DOCKER, FROZEN, HERE, ROOT, SOCKET, WORK, Scope, docker, get, put
from stage_repository_transport import read

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentLimits,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.repository_suites import (
    LARGE_PAYLOAD,
    SuiteInput,
    SuiteTruthV6,
    archive_files,
    compressed_patch_artifact,
    grade_suite_output,
)
from aeep.assessment.repository_tasks import RepositoryPatch
from aeep.assessment.verification import verification_source_digest
from aeep.errors import ConfigurationError
from aeep.executors.base import ExecutionContext
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import file_digest

NAME = "c13-cached-native-repository-pairs-20261116"
TARGET = WORK / NAME
REVIEW = TARGET / "operation-review.json"
APPROVAL = TARGET / "approval.json"
RUN = TARGET / "execution"
TRANSPORT = WORK / "cached-multifile-projections/worker-transport"
CARRIER = "sha256:35dc1bcb7e8162c2a0cef6cbd30bc4bf276c082b11b6e5fc259b6800e8c5ca04"
ROLE_SECONDS = 35
ROLES = ("reference", "original")
MAX_CALLS = 4

CORE_WHEELS = (
    "pytest-8.3.5-py3-none-any.whl",
    "iniconfig-2.1.0-py3-none-any.whl",
    "packaging-25.0-py3-none-any.whl",
    "pluggy-1.6.0-py3-none-any.whl",
)
LEGACY_WHEELS = ROOT / ".aeep/repository-replacement-runtime-20261022-wheels"
COVERAGE_WHEELS = ROOT / ".aeep/repository-supported-suite-wheels-20261027"
SCANNER_WHEELS = ROOT / ".aeep/scanner-runtime-context-20261102/wheels"
PROFILES = {
    "getsentry__sentry-python-4231": {
        "plugins": ["pytest_cov.plugin"],
        "existing_image_dependencies": ["jsonschema"],
        "wheelhouses": (
            (
                COVERAGE_WHEELS,
                ("coverage-7.11.0-py3-none-any.whl", "pytest_cov-7.0.0-py3-none-any.whl"),
            ),
            (
                LEGACY_WHEELS,
                (
                    "requests-2.32.5-py3-none-any.whl",
                    "urllib3-2.5.0-py3-none-any.whl",
                    "charset_normalizer-3.4.4-py3-none-any.whl",
                ),
            ),
        ),
        "locked": ("certifi", "idna", "typing-extensions"),
    },
    "huggingface__huggingface_hub-4056": {
        "plugins": ["pytest_mock"],
        "existing_image_dependencies": ["PyYAML", "typer"],
        "wheelhouses": (
            (
                LEGACY_WHEELS,
                ("pytest_mock-3.15.0-py3-none-any.whl", "tqdm-4.67.1-py3-none-any.whl"),
            ),
            (
                SCANNER_WHEELS,
                ("filelock-3.29.0-py3-none-any.whl", "fsspec-2026.3.0-py3-none-any.whl"),
            ),
        ),
        "locked": (
            "httpx",
            "httpcore",
            "h11",
            "anyio",
            "sniffio",
            "certifi",
            "idna",
            "typing-extensions",
        ),
    },
}


def asset(path, sha):
    raw = read(path, sha)
    return {"path": str(path), "sha256": sha, "size_bytes": len(raw)}


def inspect_carrier():
    image = json.loads(docker("image", "inspect", "--format", "{{json .}}", CARRIER))
    if (
        image["Id"] != CARRIER
        or image["Os"] != "linux"
        or image["Architecture"] != "arm64"
        or image["Config"]["User"] != "65534:65534"
        or image["Config"].get("Volumes")
        or image["Config"].get("Healthcheck")
    ):
        raise ValueError("retained grader image boundary differs")
    return image["RootFS"]["Layers"]


def definitions():
    transport = get(HERE / "cached-multifile-projections.json")
    index = json.loads(
        read(TRANSPORT / "private-index.json", transport["private_transport_index_sha256"])
    )
    runtime = FROZEN / "integrations/assessment-runtime"
    program = (
        (runtime / "repository_suite_native_program.py")
        .read_text()
        .replace(
            "'__AEEP_NATIVE_CAPTURE_SOURCE__'",
            repr((runtime / "repository_suite_native_capture.py").read_text()),
        )
    )
    compile(program, "<ordinary repository grader>", "exec")
    specimen = ExecutorSpec(
        id="repository.suite.observe",
        capability="assessment.repository_suite@1",
        kind="command",
        description="Contained repository native identity grader",
        config={
            "argv": ["python3", "-B", "-c", program],
            "argv_literal": True,
            "stdin_json": True,
            "output": {"type": "json"},
            "timeout_seconds": 30,
            "max_stdin_bytes": LARGE_PAYLOAD,
            "max_output_bytes": 500_000,
        },
    )
    environment = AssessmentEnvironment(
        environment_id=NAME,
        kind="container",
        container_image=CARRIER,
        identity={"source": verification_source_digest(FROZEN)},
        container_runtime=DOCKER,
        container_socket=SOCKET,
        memory_mb=512,
        process_limit=96,
        container_tmpfs_mb=64,
    )
    prior = get(WORK / "a2a-protected-reference-review.json")
    wheel_lock = json.loads(
        read(WORK / "a2a-offline-assets/wheel-lock.json", prior["wheel_lock_sha256"])
    )
    cases = []
    for row in index:
        task = SuiteInput.model_validate(row["input"])
        if task.task_id not in PROFILES:
            continue
        profile = PROFILES[task.task_id]
        file_root = TRANSPORT / "protected" / task.task_id
        required = json.loads(
            read(file_root / "required.json", row["required_identities"]["sha256"])
        )
        paths = [
            directory / name
            for directory, names in ((LEGACY_WHEELS, CORE_WHEELS), *profile["wheelhouses"])
            for name in names
        ]
        wheels = [asset(path, file_digest(path)) for path in paths]
        for name in profile["locked"]:
            pin = wheel_lock["wheels"][name]
            wheels.append(asset(ROOT / pin["path"], pin["sha256"]))
        source = TRANSPORT / "public" / row["public_source"]["name"]
        truth = SuiteTruthV6(
            input_sha256=content_digest(task),
            source=asset(source, task.source_sha256),
            tests=asset(file_root / "tests.tar.gz", row["protected_tests"]["sha256"]),
            wheels=wheels,
            python="3.13",
            pytest="8.3.5",
            pytest_plugins=profile["plugins"],
            test_paths=row["test_modules"],
            test_roots=row["test_roots"],
            patch_encoding="gzip-json",
            archive_profile="repository-v1",
            identity_format="pytest-native-v1",
            **required,
        )
        original = archive_files(truth.source.read(), large=True)
        original_patch = RepositoryPatch(
            base_sha256=truth.input_sha256,
            files={name: original[name].decode() for name in task.editable_paths},
        )
        reference = json.loads(read(file_root / "reference.json", row["reference"]["sha256"]))
        cases.append(
            {
                "case_id": task.task_id,
                "source_revision": row["source_revision"],
                "input": task.model_dump(mode="json"),
                "truth": truth.model_dump(mode="json"),
                "roles": {
                    "reference": reference,
                    "original": compressed_patch_artifact(original_patch),
                },
                "reference_archive_sha256": row["reference_archive_sha256"],
                "existing_image_dependencies": profile["existing_image_dependencies"],
            }
        )
    if {case["case_id"] for case in cases} != PROFILES.keys():
        raise ValueError("protected batch subject inventory differs")
    return specimen, environment, cases


def context(spec, identity, payload):
    return ExecutionContext(
        request=ActionRequest(action_id=identity, capability=spec.capability, input=payload),
        spec=spec,
        estimate=spec.estimate,
        attempt=1,
        attempt_id=identity,
        approved_side_effect=spec.side_effect,
    )


def expected_statuses(truth, role):
    statuses = dict.fromkeys(truth["fail_to_pass"] + truth["pass_to_pass"], "PASSED")
    if role == "original":
        statuses.update(dict.fromkeys(truth["fail_to_pass"], "FAILED"))
    return statuses


def verify_probe(reply, payload, expected, code):
    return (
        isinstance(reply, dict)
        and set(reply) == {"archive_sha256", "python", "pytest", "statuses", "exit_code"}
        and all(reply[key] == payload[key] for key in ("archive_sha256", "python", "pytest"))
        and type(reply["exit_code"]) is int
        and reply["exit_code"] == code
        and isinstance(reply["statuses"], dict)
        and len(reply["statuses"]) <= 10_000
        and all(
            isinstance(name, str)
            and isinstance(value, str)
            and value in {"PASSED", "FAILED", "ERROR", "SKIPPED", "XFAIL"}
            for name, value in reply["statuses"].items()
        )
        and all(reply["statuses"].get(name) == status for name, status in expected.items())
    )


async def simulate_launches(spec, env, cases):
    executor = ContainerExecutor(env)
    launches = []
    for entry in cases:
        case, truth = entry["case_id"], entry["truth"]
        for role in ROLES:
            identity = f"{NAME}:{case}:{role}"
            expected = expected_statuses(truth, role)
            code = int(role == "original")

            async def project(
                payload, role=role, entry=entry, identity=identity, code=code, expected=expected
            ):
                if (
                    role == "reference"
                    and payload["archive_sha256"] != entry["reference_archive_sha256"]
                ):
                    raise ValueError("protected archive changed")
                argv, owned = executor.command(context(spec, identity, payload))
                root = FROZEN / "src"
                if (
                    {arg for arg in argv if arg.startswith("type=bind,")}
                    != {f"type=bind,src={root},dst={root},readonly"}
                    or argv[argv.index("--network") + 1] != "none"
                    or argv[argv.index("--user") + 1] != "65534:65534"
                    or not {
                        "--pull=never",
                        "--read-only",
                        "--cap-drop=ALL",
                        "--security-opt=no-new-privileges",
                    }
                    <= set(argv)
                ):
                    raise ValueError("ordinary protected launch escaped its boundary")
                launches.append(
                    {
                        "operation": identity,
                        "container": owned,
                        "argv_sha256": content_digest({"argv": argv}),
                        "payload_sha256": content_digest(payload),
                        "archive_sha256": payload["archive_sha256"],
                        "payload_bytes": len(json.dumps(payload).encode()),
                        "required_tests": len(expected),
                    }
                )
                observed = {key: payload[key] for key in ("archive_sha256", "python", "pytest")}
                return {**observed, "exit_code": code, "statuses": expected}

            score = await grade_suite_output(entry["input"], truth, entry["roles"][role], project)
            if score.valid is not (code == 0) or score.detail != (
                "" if code == 0 else "test_failure"
            ):
                raise ValueError("ordinary scoring contract differs")
    if len(launches) != MAX_CALLS:
        raise ValueError("expected four scoped protected calls")
    return launches


async def review_fields():
    spec, environment, cases = definitions()
    data = {
        "schema_version": "aeep.c13.cached-native-repository-pairs.v1",
        "source_digest": verification_source_digest(FROZEN),
        "driver_sha256": file_digest(Path(__file__)),
        "docker_sha256": file_digest(Path(DOCKER)),
        "carrier_layers": inspect_carrier(),
        "environment": environment.model_dump(mode="json"),
        "observer_fingerprint": content_digest(spec),
        "case_fingerprints": {entry["case_id"]: content_digest(entry) for entry in cases},
        "cases": {
            entry["case_id"]: {
                "source_revision": entry["source_revision"],
                "wheels": entry["truth"]["wheels"],
                "pytest_plugins": entry["truth"]["pytest_plugins"],
                "existing_image_dependencies": entry["existing_image_dependencies"],
            }
            for entry in cases
        },
        "launches": await simulate_launches(spec, environment, cases),
        "maximum_operations": MAX_CALLS,
        "maximum_reserved_seconds": MAX_CALLS * ROLE_SECONDS,
        "models": 0,
        "cash_usd": 0,
        "builds": 0,
        "downloads": 0,
        "retries": 0,
        "provider_disclosure": False,
        "formal_adoption": False,
    }
    return data, spec, environment, cases


async def run(exact):
    if (
        not REVIEW.is_file()
        or file_digest(REVIEW) != exact
        or RUN.exists()
        or not APPROVAL.is_file()
    ):
        raise ValueError("exact unstarted protected review requires approval")
    approval = get(APPROVAL)
    if (
        set(approval) != {"approved", "review_sha256"}
        or approval["approved"] is not True
        or approval["review_sha256"] != exact
    ):
        raise ValueError("operator approval does not bind this review")
    reviewed = get(REVIEW)
    scope, spec, environment, cases = await review_fields()
    expiry = datetime.fromisoformat(reviewed["expires_at"])
    if reviewed != {**scope, "expires_at": reviewed["expires_at"]} or expiry <= utc_now():
        raise ValueError("operation review drifted or expired")
    minimum_free = scope.get("storage_floor_bytes", 52 * 1024**3)
    if type(minimum_free) is not int or minimum_free < 50 * 1024**3:
        raise ValueError("protected review floor must preserve the 50 GiB host reserve")
    if shutil.disk_usage(WORK).free < minimum_free:
        raise ValueError("host is below the scoped storage floor")
    RUN.mkdir(mode=0o700)
    definition = Scope(review_sha256=exact)
    fingerprint = content_digest(definition)
    request = RecipeMaterializationRequest(
        plan_id=NAME,
        authorization_id=NAME,
        subject_digest=fingerprint,
        recipe_digest=fingerprint,
        mapping_digest=fingerprint,
        environment_digest=fingerprint,
        definition_digests=[fingerprint],
        seed=0,
    )
    grant = AssessmentAuthorization(
        authorization_id=NAME,
        subject_digests=[fingerprint],
        recipe_digests=[fingerprint],
        environment_digests=[fingerprint],
        allowed_destinations=["local"],
        expires_at=expiry,
        limits=AssessmentLimits(
            max_operations=MAX_CALLS, max_elapsed_seconds=MAX_CALLS * ROLE_SECONDS
        ),
        remote_disclosure=False,
    )
    expected_launches = {item["operation"]: item for item in scope["launches"]}
    executor = ContainerExecutor(environment)
    results = []
    with ReceiptStore(RUN / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        repo.put("c13_cached_repository_pair_scope", fingerprint, definition)
        repo.approve_bundle(grant, {fingerprint: definition.model_dump(mode="json")})
        try:
            for item in cases:
                for role in ROLES:
                    identity = f"{NAME}:{item['case_id']}:{role}"
                    expected = expected_statuses(item["truth"], role)
                    code = int(role == "original")
                    launch = expected_launches[identity]

                    async def probe(
                        payload, identity=identity, launch=launch, expected=expected, code=code
                    ):
                        if (
                            file_digest(REVIEW) != exact
                            or shutil.disk_usage(WORK).free < minimum_free
                        ):
                            raise RuntimeError("review or host free space changed")
                        trial = context(spec, identity, payload)
                        argv, owned = executor.command(trial)
                        if (
                            content_digest(payload) != launch["payload_sha256"]
                            or content_digest({"argv": argv}) != launch["argv_sha256"]
                            or owned != launch["container"]
                            or docker("ps", "-aq", "--filter", f"name=^/{owned}$")
                        ):
                            raise RuntimeError("operation boundary or identity differs")
                        repo.reserve(
                            request,
                            identity,
                            AssessmentLimits(max_operations=1, max_elapsed_seconds=ROLE_SECONDS),
                            stage="cached_repository_reference_control",
                            require_settled_plan=True,
                        )
                        started, clock = utc_now(), time.monotonic()
                        raw = await executor.execute(trial)
                        if docker("ps", "-aq", "--filter", f"name=^/{owned}$"):
                            raise RuntimeError(
                                "grader cleanup uncertain; keep reservation unresolved"
                            )
                        valid = raw.status.value == "success" and verify_probe(
                            raw.output, payload, expected, code
                        )
                        response = raw.output if valid else None
                        metadata = {"operation_review_sha256": exact, "container_absent": True}
                        if response is not None:
                            metadata.update(
                                protected_observation_sha256=content_digest(response),
                                status_counts=dict(Counter(response["statuses"].values())),
                                expected_status_count=len(expected),
                            )
                        receipt = ExecutionReceipt(
                            decision_id=identity,
                            action_id=identity,
                            capability=spec.capability,
                            executor_id=spec.id,
                            executor_kind=spec.kind,
                            status="success" if valid else "failed",
                            execution_success=valid,
                            started_at=started,
                            ended_at=utc_now(),
                            estimated=trial.estimate,
                            actual_resources=raw.resources,
                            error_type=None if valid else "OBSERVATION_MISMATCH",
                            metadata=metadata,
                        )
                        store.save_receipt(receipt)
                        repo.finish_operation(
                            identity,
                            elapsed_seconds=time.monotonic() - clock,
                            resources=raw.resources,
                        )
                        results.append(
                            {
                                "operation": identity,
                                "receipt_id": receipt.receipt_id,
                                "contract_matched": valid,
                            }
                        )
                        put(
                            RUN / f"receipt-{receipt.receipt_id}.json",
                            receipt.model_dump(mode="json"),
                        )
                        if response is None:
                            raise ConfigurationError("protected observation was indeterminate")
                        return response

                    try:
                        grade = await grade_suite_output(
                            item["input"], item["truth"], item["roles"][role], probe
                        )
                    except ConfigurationError:
                        break
                    if grade.quality_score != (1.0 if code == 0 else 0.0):
                        raise RuntimeError("ordinary score differs from verified observation")
                    results[-1]["score"] = grade.quality_score
        finally:
            await executor.close()
            put(RUN / "ledger.json", repo.operation_ledger(NAME).model_dump(mode="json"))
    verified = len(results) == MAX_CALLS and all(row["contract_matched"] for row in results)
    put(
        RUN / "result.json",
        {
            "verified": verified,
            "review_sha256": exact,
            "observations": results,
            "models": 0,
            "cash_usd": 0,
            "formal_cases_adopted": 0,
        },
    )
    return verified


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--prepare", action="store_true")
    actions.add_argument("--exact-review")
    args = parser.parse_args()
    if args.prepare:
        fields, *_ = await review_fields()
        TARGET.mkdir(mode=0o700)
        put(REVIEW, {**fields, "expires_at": (utc_now() + timedelta(days=7)).isoformat()})
        print(file_digest(REVIEW))
    else:
        raise SystemExit(0 if await run(args.exact_review) else 1)


if __name__ == "__main__":
    asyncio.run(main())
