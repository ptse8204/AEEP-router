"""Join the exact Locify and EOS correction scopes without replaying other work."""

import argparse
import asyncio
import base64
import json
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

import check_locify_source_wheels as journal
import prepare_eos_protected_diagnostic as eos
import prepare_locify_launcher_correction as locify
from stage_repository_transport import ROOT, WORK, encode, write

from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentLimits,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.repository_suites import grade_suite_output
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutionReceipt, utc_now
from aeep.store import ReceiptStore

NAME = "c13-software-lead-corrections-20261119"
TARGET = WORK / NAME
GROUP = TARGET / "operation-review.json"
APPROVAL = TARGET / "operator-approval.json"
SCOPE_REFS = {"locify": locify.REVIEW, "eos": eos.REVIEW}


def group_fields():
    scopes = {name: journal.doc(path) for name, path in SCOPE_REFS.items()}
    pins = {str(path.relative_to(ROOT)): journal.fingerprint(path) for path in [
        Path(__file__), Path(eos.__file__), Path(locify.__file__), Path(journal.__file__),
        Path(locify.locify.__file__), Path(locify.locify.runner.__file__), Path(eos.eos.__file__),
    ]}
    return {
        "schema_version": "aeep.c13.software-lead-corrections.v1",
        "scope_refs": {name: {"path": str(path.relative_to(ROOT)), "sha256": journal.fingerprint(path)}
                       for name, path in SCOPE_REFS.items()},
        "pins": pins, "source_digest": verification_source_digest(locify.locify.VERIFIED_SOURCE),
        "expires_at": min(scope["expires_at"] for scope in scopes.values()),
        "maximum_operations": sum(s["limits"]["operations"] for s in scopes.values()),
        "maximum_reserved_seconds": sum(s["limits"]["reserved_seconds"] for s in scopes.values()),
        "models": 0, "cash_usd": 0, "downloads": 0, "published": False,
        "retries": 0, "comparisons_paused": True, "waza_excluded": True,
    }


def grant(component, exact, expiry, operations, seconds):
    name = f"{NAME}:{component}"
    scope = journal.Scope(review_sha256=exact)
    identity = content_digest(scope)
    auth = AssessmentAuthorization(authorization_id=name, subject_digests=[identity],
        recipe_digests=[identity], environment_digests=[identity], allowed_destinations=["local"],
        expires_at=expiry, limits=AssessmentLimits(max_operations=operations, max_elapsed_seconds=seconds),
        remote_disclosure=False)
    req = RecipeMaterializationRequest(plan_id=name, authorization_id=name, subject_digest=identity,
        recipe_digest=identity, mapping_digest=identity, environment_digest=identity,
        definition_digests=[identity], seed=0)
    return scope, auth, req


def preflight(exact, live=False):
    if (journal.fingerprint(GROUP) != exact or journal.doc(GROUP) != group_fields()
            or utc_now() >= datetime.fromisoformat(journal.doc(GROUP)["expires_at"])):
        raise ValueError("exact grouped scope or expiry changed")
    if live and journal.doc(APPROVAL) != {"approved": True, "group_sha256": exact}:
        raise ValueError("operator approval must bind the exact group")
    if (eos.ACTUAL_SOURCE != locify.locify.VERIFIED_SOURCE or (TARGET / "result.json").exists()
            or (TARGET / "started.json").exists()):
        raise ValueError("requires unstarted group and frozen source")
    for name, path in SCOPE_REFS.items():
        if name == "eos":
            for file, checksum in journal.doc(path)["bindings"].items():
                if journal.fingerprint(ROOT / file) != checksum:
                    raise ValueError("protected EOS inputs changed")
        else:
            if journal.fingerprint(locify.CONTEXT / "Dockerfile") != journal.doc(path)["dockerfile_sha256"]:
                raise ValueError("Locify launcher repair changed")


async def locify_correction(exact, expiry):
    scope = journal.doc(locify.REVIEW)
    docker, env = journal.docker_settings()
    if (env != scope["build"]["environment"] or scope["docker_pins"] != journal.docker_pins(docker)
            or any(journal.inspect(docker, env, tag) != pinned for tag, pinned in scope["parents"].items())
            or shutil.disk_usage(ROOT).free < scope["minimum_build_free_bytes"]):
        raise ValueError("Locify parent, driver or storage checks did not pass")
    store_path = TARGET / "locify"
    store_path.mkdir(mode=0o700)
    journal.HOME_DIR, journal.LABEL = store_path, NAME + ":locify"
    definition, auth, request = grant("locify", exact, expiry, 2, 190)
    with ReceiptStore(store_path / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        repo.put("c13_runtime_scope", content_digest(definition), definition)
        repo.approve_bundle(auth, {content_digest(definition): definition.model_dump(mode="json")})
        try:
            await journal.run_operation(repo, store, request, scope["build"]["argv"], "copy-launcher", 150, exact, env)
            image = journal.inspect(docker, env, locify.TAG)
            parent = scope["build"]["verify_lineage_before_use"]["layers"]
            if image["layers"][:-1] != parent:
                raise ValueError("Locify child must append only the reviewed launcher layer")
            mount = f"type=bind,src={locify.locify.VERIFIED_SOURCE / 'src'},dst=/opt/aeep-source,readonly"
            smoke = [*docker, "run", "--pull=never", "--rm", "--name", NAME + "-locify-smoke",
                     "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                     "--user=65534:65534", "--memory=256m", "--memory-swap=256m", "--pids-limit=32",
                     "--mount", mount, "--entrypoint", "python3", image["id"], *scope["pre_grade_checks"]["command"][1:]]
            result = await journal.run_operation(repo, store, request, smoke, "validate-launcher", 25, exact, env)
            outcome = json.loads(result.stdout)
            if not outcome["worker_import"] or outcome["python"] != [3, 13] or not all(outcome["present"].values()):
                raise ValueError("corrected CPython 3.13 launcher did not pass")
            write(store_path / "launcher.json", encode({"image": image, "observations": outcome}))
        finally:
            write(store_path / "ledger.json", encode(repo.operation_ledger(auth.authorization_id).model_dump(mode="json")))
    return image


async def locify_roles(exact, image, expiry):
    binding = locify.locify
    runner = binding.runner
    observed = []
    binding.configure(observed)
    observer, env, cases = runner.definitions()
    runner.NAME = locify.NAME
    runner.CARRIER = image["id"]
    runner.REVIEW, runner.APPROVAL, runner.RUN = (
        TARGET / "locify-protected-review.json", TARGET / "locify-protected-approval.json", TARGET / "locify-protected")
    runner.definitions = lambda: (observer, env.model_copy(update={"container_image": image["id"]}), cases)
    old = runner.review_fields

    async def derived_review():
        details, *other = await old()
        supplied = journal.doc(locify.REVIEW)
        expected = [(item["payload_sha256"], item["archive_sha256"]) for item in supplied["grade_roles"]]
        measured = [(item["payload_sha256"], item["archive_sha256"]) for item in details["launches"]]
        if expected != measured or details["observer_fingerprint"] != supplied["observer_fingerprint"]:
            raise ValueError("protected grade payload or observer changed")
        return (details | {"operator_repeat_scope_sha256": exact}, *other)

    runner.review_fields = derived_review
    details, *_ = await derived_review()
    write(runner.REVIEW, encode(details | {"expires_at": expiry.isoformat()}))
    pin = journal.fingerprint(runner.REVIEW)
    write(runner.APPROVAL, encode({"approved": True, "review_sha256": pin}))
    try:
        return await runner.run(pin)
    finally:
        if observed:
            write(runner.RUN / "observations.json", encode(observed))


def summarize_diagnostic(role, reply, payload, missing, failed):
    key = {"collect": "collection", "failure-sites": "evaluation"}[role]
    if not isinstance(reply, dict) or set(reply) != {key, "failure_log_tail_b64"}:
        raise ValueError("diagnostic observer response shape changed")
    result = reply[key]
    if any(payload[field] != result[field] for field in ("archive_sha256", "python", "pytest")):
        raise ValueError("diagnostic observer response bound another input")
    if role == "collect":
        if result["exit_code"] != 0:
            raise ValueError("protected collection failed")
        identities = result["native_ids"]
        matches = {short: sorted(node for node in identities if node.startswith(short + " ")) for short in missing}
        return {"native_id_count": len(identities), "unique_matches": {k: v[0] for k, v in matches.items() if len(v) == 1},
                "unresolved": {k: len(v) for k, v in matches.items() if len(v) != 1}}
    sites = json.loads(base64.b64decode(reply["failure_log_tail_b64"], validate=True))
    if len(sites) > 50 or any(set(row) != {"file", "line", "category"} for row in sites):
        raise ValueError("unexpected retained diagnostic fields")
    return {"exit_code": result["exit_code"], "statuses": {k: result["statuses"].get(k, "MISSING") for k in failed},
            "failure_sites": sites}


async def eos_diagnose_operation(repo, store, request, role, trial, payload, env, scope, exact, missing, failed):
    executor = eos.ContainerExecutor(env)
    argv, owned = executor.command(trial)
    pins = scope["launches"][role]
    if (owned != pins["container"] or content_digest(payload) != pins["payload_sha256"]
            or content_digest({"argv": argv}) != pins["argv_sha256"]
            or eos.eos.runner.docker("ps", "-aq", "--filter", f"name=^/{owned}$")):
        raise ValueError("EOS diagnostic launch drifted")
    name = trial.attempt_id
    repo.reserve(request, name, AssessmentLimits(max_operations=1, max_elapsed_seconds=95), stage=role)
    clock, started = time.monotonic(), utc_now()
    raw = await executor.execute(trial)
    if eos.eos.runner.docker("ps", "-aq", "--filter", f"name=^/{owned}$"):
        raise RuntimeError("EOS owned container cleanup uncertain")
    receipt = ExecutionReceipt(decision_id=name, action_id=name, capability=trial.spec.capability,
        executor_id=trial.spec.id, executor_kind=trial.spec.kind, status=raw.status, started_at=started,
        ended_at=utc_now(), estimated=trial.estimate, actual_resources=raw.resources,
        execution_success=raw.status.value == "success", error_type=raw.error_type,
        metadata={"review_sha256": exact, "container_absent": True})
    store.save_receipt(receipt)
    repo.finish_operation(name, elapsed_seconds=time.monotonic()-clock, resources=raw.resources)
    write(TARGET / f"eos-{role}-receipt.json", encode(receipt.model_dump(mode="json")))
    if not receipt.execution_success:
        raise RuntimeError("EOS protected diagnostic transport failed")
    record = summarize_diagnostic(role, raw.output, payload, missing, failed)
    record["receipt"] = receipt.receipt_id
    record["protected_response_sha256"] = content_digest(raw.output)
    write(TARGET / f"eos-{role}.json", encode(record))
    return record


async def eos_diagnostics(exact, expiry):
    scope = journal.doc(eos.REVIEW)
    observer, env, case, failed, missing = eos.configuration()
    if shutil.disk_usage(ROOT).free < scope["minimum_free_bytes"]:
        raise ValueError("EOS diagnostic storage check did not pass")
    definition, auth, request = grant("eos", exact, expiry, 2, 190)
    with ReceiptStore(TARGET / "eos-receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        repo.put("c13_diagnostic_scope", content_digest(definition), definition)
        repo.approve_bundle(auth, {content_digest(definition): definition.model_dump(mode="json")})

        async def diagnose(payload):
            for role, projected in (("collect", dict(payload, collect_only=True)), ("failure-sites", dict(payload, test_paths=failed))):
                if shutil.disk_usage(ROOT).free < scope["minimum_free_bytes"]:
                    raise ValueError("EOS diagnostic storage decreased")
                trial = eos.eos.runner.context(observer, f"{eos.NAME}:{role}", projected)
                await eos_diagnose_operation(repo, store, request, role, trial, projected, env, scope, exact, missing, failed)
            return {key: payload[key] for key in ("archive_sha256", "python", "pytest")} | {
                "statuses": {}, "exit_code": 1}

        try:
            # Use the real payload assembly. Discard this deliberately empty scoring
            # response. Diagnostic receipts cannot satisfy the protected grade gate.
            await grade_suite_output(case["input"], case["truth"], case["roles"]["reference"], diagnose)
        finally:
            write(TARGET / "eos-ledger.json", encode(repo.operation_ledger(auth.authorization_id).model_dump(mode="json")))


async def execute(exact):
    preflight(exact, live=True)
    if shutil.disk_usage(ROOT).free < 53 * 2**30:
        raise ValueError("restore 53 GiB usable to start both reviewed branches")
    expiry = datetime.fromisoformat(journal.doc(GROUP)["expires_at"])
    write(TARGET / "started.json", encode({"exact_review": exact}))
    result = {}
    try:
        try:
            image = await locify_correction(exact, expiry)
            result["locify"] = "pair_verified" if await locify_roles(exact, image, expiry) else "indeterminate"
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            result["locify"] = type(error).__name__
        try:
            result["eos"] = "diagnostics_completed" if await eos_diagnostics(exact, expiry) is None else "indeterminate"
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            result["eos"] = type(error).__name__
    finally:
        write(TARGET / "result.json", encode({"exact_review": exact, "outcomes": result, "formal_adoptions": 0}))


async def prepare():
    _, _, bound, *_ = await eos.definitions()
    if bound != journal.doc(eos.REVIEW)["launches"]:
        raise ValueError("EOS diagnostic command rehearsal drifted")
    write(GROUP, encode(group_fields()))
    exact = journal.fingerprint(GROUP)
    preflight(exact)
    print(exact)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--verify")
    mode.add_argument("--execute")
    args = parser.parse_args()
    if args.prepare:
        asyncio.run(prepare())
    elif args.verify:
        preflight(args.verify)
        labor = journal.doc(GROUP)
        print(json.dumps({"verified": True, "operations": labor["maximum_operations"],
                          "seconds": labor["maximum_reserved_seconds"], "launched": 0}))
    else:
        asyncio.run(execute(args.execute))


if __name__ == "__main__":
    main()
