"""Acquire one exact locked wheel batch and verify seven protected ExtractBench roles."""

import argparse
import asyncio
import json
import shutil
import tarfile
import time
import tomllib
import urllib.request
from datetime import datetime, timedelta
from email.parser import BytesParser
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile

from audit_extractbench_audent import LOCK_PIN, cached_wheels, declared_wheels, required_packages
from audit_extractbench_audent import ROOT as INTAKE_ROOT
from audit_extractbench_runtime import source_fallback
from check_linux_install import DOCKER, HERE, ROOT, SOCKET, Scope, docker, get, put
from check_migrated_graders import CARRIER, FROZEN, SOURCE, approved, project_source
from extractbench_harbor_observer import METRIC
from repository_offline_pair_batch import context
from stage_extractbench_protected_inputs import ROLES, STAGED, prepared, verify_staged
from stage_repository_transport import digest, read

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentLimits,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.models import ExecutionReceipt, ExecutorSpec, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import file_digest

NAME = "c13-extractbench-first-native-grade-20261116"
PRIVATE = INTAKE_ROOT / NAME
RUNTIME = PRIVATE / "runtime"
WHEELS = RUNTIME / "wheels"
REVIEW = PRIVATE / "operation-review.json"
APPROVAL = PRIVATE / "approval.json"
RUN = PRIVATE / "execution"
FETCH_SECONDS = 420
GRADER_SECONDS = 335
HOST_RESERVE = 52 * 1024**3
HELPERS = (
    "audit_extractbench_audent.py", "audit_extractbench_runtime.py", "stage_extractbench_protected_inputs.py",
    "stage_repository_transport.py", "check_linux_install.py", "check_migrated_graders.py",
    "repository_offline_pair_batch.py",
)


def closure():
    locked = required_packages(tomllib.loads(read(INTAKE_ROOT / "scorer-uv.lock", LOCK_PIN).decode()))
    pins, no_wheel = declared_wheels(locked)
    if no_wheel != [{"package": "fuzzysearch", "version": "0.8.1"}]:
        raise ValueError("locked offline wheel platform changed")
    fuzzy = source_fallback(next(row for row in locked if row["name"] == "fuzzysearch"))
    sdist = read(INTAKE_ROOT / "fuzzysearch-0.8.1.tar.gz", fuzzy["artifact"]["hash"].removeprefix("sha256:"))
    fallback = {}
    with tarfile.open(fileobj=BytesIO(sdist), mode="r:gz") as archive:
        for name, sha in fuzzy["inspected_files"].items():
            if name.endswith("setup.py"):
                continue
            target = Path(name).name
            with archive.extractfile(name) as stream:
                body = stream.read()
            if target in fallback or digest(body) != sha:
                raise ValueError("fuzzysearch support source drift")
            fallback[target] = body
    return pins, fallback


def static_runtime(pins, fallback):
    return {
        "requirements.txt": "".join(f"{name}=={entry['version']} --hash={entry['hash']}\n" for name, entry in pins.items()).encode(),
        **{name: (HERE / name).read_bytes() for name in ("extractbench_offline_guest.py", "extractbench_harbor_observer.py")},
        **{f"fuzzysearch/{name}": data for name, data in fallback.items()},
    }


def wheel_notice(path, pin, name):
    data = read(path, pin["hash"].removeprefix("sha256:"))
    if len(data) != pin["size"] or path.is_symlink():
        raise ValueError("wheel size or type differs from its upstream lock")
    with ZipFile(BytesIO(data)) as archive:
        names = archive.namelist()
        metadata, = [part for part in names if part.endswith(".dist-info/METADATA")]
        header = archive.read(metadata)
        info = BytesParser().parsebytes(header, headersonly=True)
        if info["Name"].lower().replace("_", "-").replace(".", "-") != name or info["Version"] != pin["version"]:
            raise ValueError("wheel metadata differs from the locked distribution")
        notices = {part: digest(archive.read(part)) for part in sorted(names)
                   if part.startswith(metadata.rsplit("/", 1)[0] + "/") and any(
                       word in Path(part).name.lower() for word in ("license", "licence", "copying", "notice")) and not part.endswith("/")}
        declared = bool(info.get("License-Expression") or info.get("License") or any(
            value.startswith("License ::") for value in info.get_all("Classifier", ())))
        if not notices and not declared:
            raise ValueError(f"license evidence unavailable for {name} {pin['version']}")
        return {"metadata_sha256": digest(header), "notice_sha256": notices, "declared_license_present": declared}


def image_layers():
    details = json.loads(docker("image", "inspect", "--format", "{{json .}}", CARRIER))
    config = details["Config"]
    if (details["Id"] != CARRIER or details["Os"] != "linux" or details["Architecture"] != "arm64"
            or config["User"] != "65534:65534" or config.get("Volumes") or config.get("Healthcheck")
            or "PYTHON_VERSION=3.13.15" not in config["Env"]):
        raise ValueError("retained grader image or Python version differs")
    return details["RootFS"]["Layers"]


def launch(pins):
    environment = AssessmentEnvironment(
        environment_id=NAME, kind="container", identity={"source": SOURCE}, container_image=CARRIER,
        container_runtime=DOCKER, container_socket=SOCKET, read_only_roots=[str(STAGED), str(RUNTIME)],
        memory_mb=1024, process_limit=96, container_tmpfs_mb=640,
    )
    spec = ExecutorSpec(
        id=NAME, capability="toolkit.upstream-engineering@1", kind="command", side_effect="read",
        description="Calibrate one pinned ExtractBench value-F1 verifier offline",
        config={"argv": ["python3", "-I", "-B", str(RUNTIME / "extractbench_offline_guest.py"),
                         "--runtime", str(RUNTIME), "--support", str(STAGED)], "argv_literal": True,
                "stdin_json": True, "timeout_seconds": 325, "max_output_bytes": 12_000, "output": {"type": "json"}},
    )
    value = {"packages": {name: pin["version"] for name, pin in pins.items()},
             "roles": {name: {"prediction": p, "reference": r} for name, (p, r, _) in ROLES.items()}}
    execution = context(spec, NAME + ":grade", value)
    executor = ContainerExecutor(environment)
    argv, container = executor.command(execution)
    if ({arg for arg in argv if arg.startswith("type=bind,")} != {
        f"type=bind,src={path},dst={path},readonly" for path in (FROZEN / "src", STAGED, RUNTIME)
    } or argv[argv.index("--network") + 1] != "none" or argv[argv.index("--user") + 1] != "65534:65534"
            or not {"--pull=never", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges", "-i"} <= set(argv)):
        raise ValueError("grader command differs from its offline containment")
    return executor, execution, {"argv_sha256": content_digest({"argv": argv}), "container": container,
                                  "input_sha256": content_digest(value), "environment": environment.model_dump(mode="json"),
                                  "executor": spec.model_dump(mode="json")}


def runtime_tree(expected, wheel_names):
    all_paths = list(RUNTIME.rglob("*"))
    if RUNTIME.is_symlink() or any(path.is_symlink() for path in all_paths):
        raise ValueError("runtime contains a symlink")
    files = {path.relative_to(RUNTIME).as_posix() for path in all_paths if path.is_file()}
    directories = {path.relative_to(RUNTIME).as_posix() for path in all_paths if path.is_dir()}
    if (files != set(expected) | {"wheels/" + name for name in wheel_names} or directories != {"fuzzysearch", "wheels"}
            or len(all_paths) != len(files) + len(directories)):
        raise ValueError("runtime contains an unexpected artifact")
    if any(read(RUNTIME / name, digest(data)) != data for name, data in expected.items()):
        raise ValueError("reviewed runtime bytes differ")


def fields(pins, files, fetch):
    project_source()
    if shutil.disk_usage(ROOT).free < HOST_RESERVE:
        raise ValueError("52 GiB launch reserve unavailable")
    intake, manifest, entries = prepared()
    verify_staged(manifest, entries)
    cached = {name for name in pins if name not in fetch}
    runtime_tree(files, (pins[name]["filename"] for name in cached))
    prior_notices = {name: wheel_notice(WHEELS / pins[name]["filename"], pins[name], name) for name in sorted(cached)}
    _, _, invocation = launch(pins)
    return {
        "schema_version": "aeep.c13.extractbench-first-native-grade-review.v1", "source": SOURCE,
        "driver_sha256": file_digest(Path(__file__)), "docker_sha256": file_digest(Path(DOCKER)), "image": CARRIER,
        "helper_files": {name: file_digest(HERE / name) for name in HELPERS},
        "image_layers": image_layers(), "lock_sha256": LOCK_PIN,
        "protected_intake_sha256": content_digest(intake), "protected_mount_inventory_sha256": intake["protected_inventory_sha256"],
        "runtime_files": {name: digest(data) for name, data in files.items()}, "wheels": pins,
        "missing_wheels_to_fetch": sorted(fetch), "cached_wheel_license_evidence": prior_notices,
        "download_host": "files.pythonhosted.org", "download_byte_limit": sum(pins[name]["size"] for name in fetch),
        "maximum_download_attempts": len(fetch), "invocation": invocation, "controls": intake["roles"],
        "maximum_operations": 2, "operation_seconds": {"acquisition": FETCH_SECONDS, "grade": GRADER_SECONDS},
        "network_in_grader": False, "minimum_host_free_bytes": HOST_RESERVE, "model_turns": 0, "cash_usd": 0,
        "builds_pulls_or_provider_disclosures": 0, "host_installations": 0, "retries": 0, "formal_cases_adopted": 0,
    }


def prepare_review():
    project_source()
    if shutil.disk_usage(ROOT).free < HOST_RESERVE:
        raise ValueError("52 GiB preparation reserve unavailable")
    pins, fallback = closure()
    cached = cached_wheels(pins)
    fetch = {name for name, pin in pins.items() if pin["filename"] not in cached}
    if len(fetch) != 36 or sum(pins[name]["size"] for name in fetch) != 76_701_027:
        raise ValueError("previously verified cache projection changed")
    files = static_runtime(pins, fallback)
    PRIVATE.mkdir(mode=0o700)
    WHEELS.mkdir(mode=0o755, parents=True)
    for name, data in files.items():
        path = RUNTIME / name
        path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
        path.chmod(0o444)
    for name in cached:
        shutil.copyfile(ROOT / ".aeep" / cached[name], WHEELS / name)
        (WHEELS / name).chmod(0o444)
    put(REVIEW, {**fields(pins, files, fetch), "expires_at": (utc_now() + timedelta(days=7)).isoformat()})


class RejectRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("pinned artifact origin redirected")


def acquire(review, pins, deadline):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), RejectRedirect())
    for name in review["missing_wheels_to_fetch"]:
        pin = pins[name]
        parsed = urlsplit(pin["url"])
        if (parsed.scheme != "https" or parsed.netloc != review["download_host"] or Path(parsed.path).name != pin["filename"]
                or parsed.query or parsed.fragment or shutil.disk_usage(ROOT).free < HOST_RESERVE):
            raise ValueError("unreviewed wheel acquisition destination or storage reserve")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("wheel acquisition allowance exhausted")
        path = WHEELS / pin["filename"]
        with opener.open(pin["url"], timeout=min(remaining, 12)) as response, path.open("xb") as output:
            size = 0
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutError("wheel acquisition allowance exhausted")
                data = response.read1(min(131_072, pin["size"] - size + 1))
                if not data:
                    break
                size += len(data)
                if size > pin["size"]:
                    raise ValueError("wheel response exceeds its exact size bound")
                output.write(data)
        wheel_notice(path, pin, name)
        path.chmod(0o444)


def result_valid(raw):
    if (not isinstance(raw, dict) or raw.get("setup_status") != "ready" or raw.get("observer_exit_code") != 0
            or raw.get("installed_wheels") != 70 or not isinstance(raw.get("grader"), dict)):
        return False
    grader = raw["grader"]
    observations = grader.get("observations")
    if grader.get("metric") != METRIC or not isinstance(observations, dict) or set(observations) != ROLES.keys():
        return False
    for name, row in observations.items():
        if not isinstance(row, dict):
            return False
        status, score, exact, code = (row.get(key) for key in ("status", "value_f1", "perfect", "exit_code"))
        expected = ROLES[name][2]
        if expected == "infrastructure_error":
            if status != expected or score is not None or exact is not None or type(code) is not int or code == 0:
                return False
            continue
        if type(score) not in {int, float} or not 0 <= score <= 1 or type(code) is not int or code != 0 or type(exact) is not int:
            return False
        if expected == "invalid_submission":
            matches = status == expected and score == 0 and exact == 0
        elif expected == "perfect":
            matches = status == "scored" and score == 1 and exact == 1
        else:
            matches = status == "scored" and 0 <= score < 1 and exact == 0
        if not matches:
            return False
    return True


def verify_review():
    review = get(REVIEW)
    pins, fallback = closure()
    files = static_runtime(pins, fallback)
    if review != {**fields(pins, files, set(review["missing_wheels_to_fetch"])), "expires_at": review["expires_at"]}:
        raise ValueError("exact protected calibration inputs changed")
    return review, pins, files


async def run(exact):
    approved(exact, REVIEW, APPROVAL, RUN)
    review, pins, files = verify_review()
    expiry = datetime.fromisoformat(review["expires_at"])
    if expiry <= utc_now():
        raise ValueError("exact review expired")
    RUN.mkdir(mode=0o700)
    put(RUN / "started.json", {"exact_review_sha256": exact, "automatic_retry": False})
    scope = Scope(review_sha256=exact)
    ref = content_digest(scope)
    request = RecipeMaterializationRequest(plan_id=NAME, authorization_id=NAME, subject_digest=ref,
        recipe_digest=ref, mapping_digest=ref, environment_digest=ref, definition_digests=[ref], seed=0)
    grant = AssessmentAuthorization(authorization_id=NAME, subject_digests=[ref], recipe_digests=[ref],
        environment_digests=[ref], allowed_destinations=["local", review["download_host"]], expires_at=expiry,
        remote_disclosure=False, limits=AssessmentLimits(max_operations=2, max_elapsed_seconds=FETCH_SECONDS + GRADER_SECONDS))
    with ReceiptStore(RUN / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        repo.put("c13_extractbench_scope", ref, scope)
        repo.approve_bundle(grant, {ref: scope.model_dump(mode="json")})
        try:
            op = NAME + ":acquisition"
            repo.reserve(request, op, AssessmentLimits(max_operations=1, max_elapsed_seconds=FETCH_SECONDS), stage="pinned_dependency_acquisition")
            clock = time.monotonic()
            try:
                acquire(review, pins, clock + FETCH_SECONDS - 10)
                runtime_tree(files, (pin["filename"] for pin in pins.values()))
                put(RUN / "wheel-licenses.json", {name: wheel_notice(WHEELS / pin["filename"], pin, name) for name, pin in pins.items()})
            finally:
                repo.finish_operation(op, elapsed_seconds=time.monotonic() - clock)
            project_source()
            _, manifest, protected = prepared()
            verify_staged(manifest, protected)
            executor, execution, invocation = launch(pins)
            name_filter = f"name=^/{invocation['container']}$"
            if (file_digest(REVIEW) != exact or invocation != review["invocation"] or image_layers() != review["image_layers"]
                    or file_digest(Path(DOCKER)) != review["docker_sha256"] or shutil.disk_usage(ROOT).free < HOST_RESERVE
                    or docker("ps", "-aq", "--filter", name_filter)):
                raise ValueError("approved offline grader boundary drifted")
            op = execution.request.action_id
            repo.reserve(request, op, AssessmentLimits(max_operations=1, max_elapsed_seconds=GRADER_SECONDS),
                         stage="protected_native_grading", require_settled_plan=True)
            clock, started = time.monotonic(), utc_now()
            raw = await executor.execute(execution)
            if docker("ps", "-aq", "--filter", name_filter):
                raise RuntimeError("owned grader cleanup uncertain; reservation stays open")
            repo.finish_operation(op, elapsed_seconds=time.monotonic() - clock, resources=raw.resources)
            valid = raw.status.value == "success" and result_valid(raw.output)
            verify_staged(manifest, protected)
            receipt = ExecutionReceipt(decision_id=op, action_id=op, capability=execution.spec.capability,
                executor_id=execution.spec.id, executor_kind=execution.spec.kind, status="success" if valid else "failed",
                execution_success=valid, started_at=started, ended_at=utc_now(), estimated=execution.estimate,
                actual_resources=raw.resources, error_type=None if valid else "NATIVE_CALIBRATION_UNVERIFIED",
                metadata={"review_sha256": exact, "container_absent": True})
            store.save_receipt(receipt)
            put(RUN / "result.json", {"review_sha256": exact, "verified": valid, "receipt_id": receipt.receipt_id,
                "observation": raw.output, "actual_model_turns": 0, "cash_usd": 0, "formal_cases_adopted": 0})
            return valid
        finally:
            put(RUN / "ledger.json", repo.operation_ledger(NAME).model_dump(mode="json"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--execute-approved")
    args = parser.parse_args()
    if args.execute_approved:
        raise SystemExit(not asyncio.run(run(args.execute_approved)))
    if args.prepare:
        prepare_review()
    else:
        verify_review()
    print(file_digest(REVIEW))
