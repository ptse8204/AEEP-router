"""Resume Waza from a settled local runtime setup and retain bounded diagnostics."""

import argparse
import contextlib
import json
import os
import stat
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import check
import prepare
import resume
import run

from aeep.assessment.repository import AssessmentRepository
from aeep.errors import ConfigurationError
from aeep.store import ReceiptStore

PARENT = "d5b47cc809101b10e593d52b9dfdc0bd4bb1b0ceb7dddc139400e4254b543d24"
PRIOR = prepare.ROOT / ".aeep/waza-ollama-20261115-retained-continuation"
RETAINED = PRIOR / "retained"
INDEX = PRIOR / "archive-index.json"
STAGES = prepare.STAGES | {
    "download_and_install": {"operations": 0, "model_turns": 0, "reserved_seconds": 0},
}
CATEGORIES = {
    b"address already in use": "address_in_use",
    b"operation not permitted": "operation_denied",
    b"permission denied": "permission_denied",
    b"failed to get cache": "application_cache",
    b"metal": "metal",
    b"listening on": "listener_started",
    b"discovering available gpus": "gpu_discovery",
    b"failed to": "reported_failure",
    b"level=error": "reported_error",
    b"panic:": "panic",
}


def parent_evidence(database):
    paths = [
        PRIOR / name
        for name in (
            "operation-review.json",
            "started.json",
            "operator-approval.json",
            "result.json",
        )
    ]
    if run.file_digest(paths[0]) != PARENT:
        raise ValueError("the exact preceding review differs")
    review, started, approval, result = map(prepare.load, paths)
    setup, service = result["operations"]["operations"]
    if (
        review["database"] != database
        or started["review_sha256"] != PARENT
        or approval["review_sha256"] != PARENT
        or approval["approved"] is not True
        or result["passed"] is not False
        or result["cleanup_uncertain"] is not False
        or setup["stage"] != "waza_local_download_and_install"
        or service["stage"] != "waza_local_service_and_boundaries"
        or any(row["reserved"]["max_model_turns"] for row in (setup, service))
        or run.file_digest(INDEX) != review["pins"][str(INDEX)]
    ):
        raise ValueError("preceding review did not settle at the expected boundary")
    with ReceiptStore(database, read_only=True) as store:
        repo = AssessmentRepository(store)
        rows = []
        for operation, status in ((setup, "success"), (service, "failed")):
            operation_id = operation["operation_id"]
            receipt = repo.get("toolkit_component_receipt", operation_id)
            measured = repo.get("operation_measurement", operation_id)
            if (
                not measured
                or receipt["status"] != status
                or receipt["metadata"]["review_sha256"] != PARENT
            ):
                raise ValueError("preceding receipt or measurement is unavailable")
            rows.append(
                {
                    "operation_id": operation_id,
                    "receipt_ref": run.content_digest(receipt),
                    "measurement_ref": run.content_digest(measured),
                    "status": status,
                }
            )
    return review, paths, rows


def verify_tree(review, work, max_seconds):
    if work != Path(review["work"]) or max_seconds != 0:
        raise ValueError("this continuation does not install anything")
    inventory = prepare.load(INDEX)["members"]
    runtime = RETAINED / "runtime"
    if runtime.resolve(strict=True) != runtime or any(
        p.relative_to(runtime).as_posix() not in inventory for p in runtime.rglob("*")
    ):
        raise ValueError("retained runtime inventory changed")
    for name, member in inventory.items():
        path = runtime / resume.safe_name(name)
        info = path.lstat()
        if member["kind"] == "library_alias":
            if (
                not stat.S_ISLNK(info.st_mode)
                or os.readlink(path) != member["target"]
                or path.resolve(strict=True).parent != runtime
            ):
                raise ValueError("retained library alias changed")
        elif member["kind"] == "directory":
            if not stat.S_ISDIR(info.st_mode):
                raise ValueError("retained runtime directory changed")
        elif (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_size != member["size"]
            or bool(info.st_mode & stat.S_IXUSR) != member["executable"]
            or run.file_digest(path) != member["sha256"]
        ):
            raise ValueError("retained runtime file changed")
    models = RETAINED / "models"
    name, tag = review["model"].split(":")
    manifest = models / "manifests/registry.ollama.ai/library" / name / tag
    assets = {manifest: Path(review["model_manifest"]).stat().st_size}
    assets.update(
        {
            models / "blobs" / ("sha256-" + asset["sha256"]): asset["size"]
            for asset in review["model_assets"]
        }
    )
    if {path for path in models.rglob("*") if not path.is_dir()} != assets.keys():
        raise ValueError("retained model inventory changed")
    for path, size in assets.items():
        if path.resolve(strict=True) != path or path.stat().st_size != size:
            raise ValueError("retained model path or size changed")
        expected = (
            review["pins"][review["model_manifest"]]
            if path == manifest
            else path.name.removeprefix("sha256-")
        )
        if run.file_digest(path) != expected:
            raise ValueError("retained model bytes changed")
    return {
        "executable": str(runtime / "ollama"),
        "executable_sha256": inventory["ollama"]["sha256"],
        "model_manifest_sha256": review["pins"][review["model_manifest"]],
        "retained_artifacts_reused": len(assets),
        "download_bytes": 0,
    }


def prepare_review(work):
    file = prepare.prepare(work)
    review = prepare.load(file)
    file.rename(work / "unapproved-parent-template.json")
    previous, paths, prior_rows = parent_evidence(review["database"])
    for key in (
        "archive",
        "model",
        "model_assets",
        "waza_revision",
        "waza",
        "copilot",
        "implementation_source",
    ):
        if review[key] != previous[key]:
            raise ValueError("runtime, task or implementation identity changed")
    for relative in ("eval.yaml", "agent/aeep-receipt-check.agent.md", "tasks/receipt-total.yaml"):
        new, old = (root / "public" / relative for root in (work, PRIOR))
        if run.file_digest(new) != previous["pins"][str(old)]:
            raise ValueError("public Waza fixture differs")
    scratch = work / "scratch/ollama"
    serve = prepare.write(
        work / "serve-retained.sb",
        prepare.profile(
            [RETAINED, scratch],
            [scratch],
            local_runner=True,
        ),
    )
    review["pins"].pop(review["profiles"]["serve"])
    review["profiles"]["serve"] = str(serve)
    review["pins"].update(
        {
            str(path): run.file_digest(path)
            for path in [
                *paths,
                INDEX,
                serve,
                prepare.HERE / "resume.py",
                prepare.HERE / "service_resume_checks.py",
                Path(__file__).resolve(),
            ]
        }
    )
    baseline = review["grant_baseline"]
    if baseline["predecessor"] != run.content_digest(
        prepare.load(PRIOR / "applied-authority.json")["budget"]
    ):
        raise ValueError("preceding grant amendment is no longer current")
    limits = baseline["effective_limits"].copy()
    seconds = sum(item["reserved_seconds"] for item in STAGES.values())
    limits["max_operations"] = baseline["state"][1] + 3
    limits["max_elapsed_seconds"] = max(
        limits["max_elapsed_seconds"], baseline["state"][3] + seconds
    )
    if limits["max_model_turns"] - baseline["state"][2] != 1:
        raise ValueError("the unstarted local turn is unavailable")
    review.update(
        purpose="Start the retained Ollama service once with measured readiness diagnostics. "
        "Only after readiness passes, run the unstarted Waza completion and protected grade.",
        allowed_download_hosts=[],
        maximum_download_response_bytes=0,
        retention="Retain installed files and canonical receipts. Remove only this attempt's "
        "scratch after verified owned-process stop. Keep error codes and category flags only.",
        maximum_additional_operations=3,
        maximum_reserved_seconds=seconds,
        grant_absolute_limits=limits,
        stages=STAGES,
        prior_operations=prior_rows,
        startup_diagnostics={"readiness_phase": True, "stderr_known_categories_only": True},
        runtime_root=str(RETAINED),
    )
    review["boundaries"][0] = "Verify the already installed runtime and model. Read-only reuse."
    review["boundaries"][-2] = (
        "One service start. After all readiness checks, one local completion and one offline grade. No retries or fallback."
    )
    return prepare.write(file, review)


class ReadinessError(RuntimeError):
    """The retained service failed one of its required startup observations."""


def observe_service(server, review, installed, facts):
    deadline = time.monotonic() + 35
    facts["readiness_phase"] = "version_endpoint"
    while time.monotonic() < deadline:
        exit_code = server.poll()
        if exit_code is not None:
            facts["service_exit_code"] = exit_code
            raise ReadinessError
        try:
            version = run.local_json(prepare.ENGINE_PORT, "/api/version")
            break
        except OSError:
            time.sleep(0.25)
    else:
        raise ReadinessError
    facts["readiness_phase"] = "version_identity"
    if version.get("version") != review["archive"]["version"]:
        raise ReadinessError
    facts["readiness_phase"] = "listener_identity"
    if run.listeners(prepare.ENGINE_PORT) != [
        f"p{server.pid}",
        f"n127.0.0.1:{prepare.ENGINE_PORT}",
    ]:
        raise ReadinessError
    facts["readiness_phase"] = "owned_listener_inventory"
    facts["owned_loopback_listeners_before_dispatch"] = run.group_listeners(server.pid)
    facts["readiness_phase"] = "model_inventory"
    tags = run.local_json(prepare.ENGINE_PORT, "/api/tags")["models"]
    facts["model_count"] = len(tags)
    if (
        len(tags) != 1
        or tags[0]["name"] != review["model"]
        or tags[0]["digest"].removeprefix("sha256:") != installed["model_manifest_sha256"]
    ):
        if len(tags) == 1:
            facts["model_name_matches"] = tags[0]["name"] == review["model"]
            facts["model_digest_matches"] = (
                tags[0]["digest"].removeprefix("sha256:") == installed["model_manifest_sha256"]
            )
        raise ReadinessError
    facts["readiness_phase"] = "gateway_catalogue"
    return {"version": version["version"], "model_manifest_verified": True, "loopback_only": True}


def categorize(stderr, categories):
    overlap = b""
    while data := stderr.read1(4096):
        sample = overlap + data.lower()
        categories.update(category for pattern, category in CATEGORIES.items() if pattern in sample)
        overlap = sample[-64:]


@contextlib.contextmanager
def observed_process(argv, cwd, env, categories):
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    assert proc.stderr is not None
    reader = threading.Thread(target=categorize, args=(proc.stderr, categories), daemon=True)
    reader.start()
    try:
        yield proc
    finally:
        try:
            run.stop_owned(proc)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise run.CleanupUncertain("owned process group cleanup is uncertain") from error
        finally:
            reader.join(timeout=2)
            if not reader.is_alive():
                proc.stderr.close()
        if reader.is_alive():
            raise run.CleanupUncertain("owned diagnostic pipe did not close")


def execute(review, file, ref):
    active_facts = {}
    observed = set()
    original_metered, original_local_json, original_owned = run.metered, run.local_json, run.owned

    @contextlib.contextmanager
    def metered(repo, request, review, ref, stage):
        if stage == "download_and_install":
            yield {}
            return
        with original_metered(repo, request, review, ref, stage) as facts:
            active_facts[stage] = facts
            try:
                yield facts
            except BaseException:
                if stage in ("service_and_boundaries", "waza_local_inference"):
                    facts["service_stderr_categories"] = sorted(observed)
                raise
            finally:
                active_facts.pop(stage)

    @contextlib.contextmanager
    def owned(argv, cwd, env):
        if argv[3:] == [str(RETAINED / "runtime/ollama"), "serve"]:
            active_facts["service_and_boundaries"]["readiness_phase"] = "process_launch"
            with observed_process(
                argv, cwd, env | {"OLLAMA_MODELS": str(RETAINED / "models")}, observed
            ) as proc:
                active_facts["service_and_boundaries"]["readiness_phase"] = "gateway_start"
                yield proc
        else:
            with original_owned(argv, cwd, env) as proc:
                yield proc

    def local_json(port, path):
        result = original_local_json(port, path)
        if port == prepare.PORT and path == "/v1/models":
            if result["data"][0]["id"] != review["model"]:
                raise ReadinessError
            active_facts["service_and_boundaries"]["readiness_phase"] = "complete"
        return result

    run.install = verify_tree
    run.metered = metered
    run.owned = owned
    run.local_json = local_json
    run.observe_service = lambda server, review, installed: observe_service(
        server, review, installed, active_facts["service_and_boundaries"]
    )
    return run.run(review, file, ref)


def ledger_controls(review, file, work, *, interrupted):
    database = work / ("interrupted.sqlite3" if interrupted else "normal.sqlite3")
    with ReceiptStore(review["database"], read_only=True) as source, ReceiptStore(database) as copy:
        source._connection.backup(copy._connection)
    variant = review | {"database": str(database)}
    ref = run.file_digest(file)
    with ReceiptStore(database) as store:
        repo = AssessmentRepository(store)
        request, _ = run.amend(repo, variant, ref)
        if interrupted:
            try:
                with run.metered(repo, request, variant, ref, "service_and_boundaries"):
                    raise run.CleanupUncertain("first-party interrupted fixture")
            except run.CleanupUncertain:
                pass
            try:
                with run.metered(repo, request, variant, ref, "waza_local_inference"):
                    raise AssertionError("unsettled service allowed dispatch")
            except ConfigurationError:
                return
        for stage in ("service_and_boundaries", "waza_local_inference", "protected_grade"):
            with run.metered(repo, request, variant, ref, stage):
                pass
        ledger = repo.operation_ledger(request.plan_id)
        assert len(ledger.operations) == 3
        assert sum(row.reserved.max_model_turns for row in ledger.operations) == 1
        assert sum(row.reserved.max_elapsed_seconds for row in ledger.operations) == 315
        assert all(row.reserved.max_cash_usd == 0 for row in ledger.operations)


def preflight(review, file):
    from service_resume_checks import diagnostic_controls

    check.gateway_controls()
    with tempfile.TemporaryDirectory(prefix="waza-service-check-", dir=file.parent) as scratch:
        work = Path(scratch)
        sandbox = check.sandbox_controls(review, work)
        check.listener_controls()
        check.grading_controls(work)
        controls = diagnostic_controls(review, file, work)
        ledger_controls(review, file, work, interrupted=False)
        ledger_controls(review, file, work, interrupted=True)
    run.verify(review, file)
    return {
        "review_sha256": run.file_digest(file),
        "verified_pins": len(review["pins"]),
        "sandbox_first_party_controls": sandbox,
        "retained_runtime_and_model_verified": True,
        "first_party_driver_controls": controls,
        "copied_ledger": "Three reservations; uncertain service cleanup blocks model dispatch.",
        "downloaded_software_bytes": 0,
        "upstream_processes_started": 0,
        "model_turns": 0,
        "comparisons": "PAUSED",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--execute-approved")
    args = parser.parse_args()
    file = prepare_review(args.path.resolve()) if args.prepare else args.path.resolve()
    review = prepare.load(file)
    ref = run.file_digest(file)
    run.STAGES = STAGES
    run.verify(review, file)
    _, _, rows = parent_evidence(review["database"])
    if rows != review["prior_operations"]:
        raise SystemExit("preceding settlement drifted")
    verify_tree(review, file.parent, 0)
    if args.execute_approved:
        approval = prepare.load(file.with_name("operator-approval.json"))
        if not (
            args.execute_approved == ref == approval["review_sha256"]
            and approval["approved"] is True
        ):
            raise SystemExit("explicit approval for this exact continuation is required")
        result = execute(review, file, ref)
        print(json.dumps(result, indent=2))
        raise SystemExit(not result["passed"])
    print(json.dumps(preflight(review, file), indent=2))
