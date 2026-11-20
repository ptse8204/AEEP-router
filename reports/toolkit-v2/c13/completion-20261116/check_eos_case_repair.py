"""Inspect EOS failures without retaining exception messages or raw test logs."""

import argparse
import asyncio
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

import run_grader_repairs_20261120 as prior
from stage_repository_transport import HERE, ROOT, WORK, encode, write

from aeep.assessment.models import AssessmentLimits, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutionReceipt, utc_now
from aeep.store import ReceiptStore

NAME = "c13-eos-exact-failures-20261120"
TARGET = WORK / NAME
REVIEW = TARGET / "operation-review.json"
HOOK = HERE / "eos_native_failure_details.py"
journal = prior.journal


def observer(spec, selected, overlay=""):
    argv = list(spec.config["argv"])
    program = argv[-1]
    source = ("\n" + HOOK.read_text() + "\n" + overlay
              + "\nNativeCapture = eos_details(NativeCapture, " + repr(selected)
              + ", globals().get('fixture_requests', lambda: []))\n")
    marker = "\n# Only an exact operator-reviewed program may enable collection and failure logs."
    program = prior.update_once(program, marker, "\nCAPTURE_SOURCE += " + repr(source) + marker)
    program = prior.update_once(program, "if not OPERATOR_REVIEW:\n            assert set(native) == {'statuses'}",
        "if not OPERATOR_REVIEW:\n            assert set(native) == "
        "{'statuses', 'native_ids', 'failure_sites', 'fixture_requests'}")
    compile(program, "<protected EOS failure observer>", "exec")
    return spec.model_copy(update={"config": dict(spec.config, argv=[*argv[:-1], program])})


def configuration():
    # Verify the previous scoped observations and use only their seven failing tests.
    native_record = prior.eos.native.TARGET / "result.json"
    native = journal.doc(native_record)
    if not native["passed"]:
        raise ValueError("EOS runtime imports are unverified")
    spec, environment, (case,) = prior.eos.definition(native)
    source = prior.TARGET / "eos-diagnostic.json"
    failed = journal.doc(source)["statuses"]
    if len(failed) != 7 or set(failed.values()) != {"FAILED"}:
        raise ValueError("previous seven-test diagnostic does not match")
    return observer(spec, sorted(failed)), environment, case, sorted(failed)


async def make_scope():
    spec, environment, case, selected = configuration()
    snapshot = None

    async def project(payload):
        nonlocal snapshot
        snapshot = payload
        if payload["archive_sha256"] != case["reference_archive_sha256"]:
            raise ValueError("published repair archive changed")
        return {key: payload[key] for key in ("archive_sha256", "python", "pytest")} | {
            "exit_code": 0, "statuses": prior.runner.expected_statuses(case["truth"], "reference")}

    await prior.ordinary(case, "reference", project)
    executor, trial, launch = prior.launch("eos", "exact-failures", environment, spec, snapshot)
    # The derived command name may differ from the old diagnostic. Its sandbox stays the same.
    docker, env = journal.docker_settings()
    image = journal.inspect(docker, env, environment.container_image)
    files = [Path(__file__), HOOK, Path(prior.__file__), Path(prior.eos.__file__),
             prior.TARGET / "eos-diagnostic.json", prior.TARGET / "ledger.json", prior.AUTHORITY]
    record = {
        "schema_version": "aeep.c13.eos-exact-failures.v1",
        "source_digest": verification_source_digest(prior.locify.VERIFIED_SOURCE),
        "pins": {str(path.relative_to(ROOT)): journal.fingerprint(path) for path in files},
        "image": image, "observer": content_digest(spec), "launch": launch, "selected": selected,
        "archive": case["reference_archive_sha256"], "case_sha256": content_digest(case),
        "operator_authority": "C13 finite correction delegation and the operator's direction to continue grading repairs.",
        "operations": 1, "reserved_seconds": 95, "retries": 0, "builds": 0, "downloads": 0,
        "models": 0, "cash_usd": 0, "formal_grade": False,
    }
    return record, executor, trial, snapshot


def validate(output, payload, selected):
    fields = {"archive_sha256", "python", "pytest", "exit_code", "statuses",
              "native_ids", "failure_sites", "fixture_requests"}
    if (not isinstance(output, dict) or set(output) != fields
            or any(output[k] != payload[k] for k in ("archive_sha256", "python", "pytest"))
            or set(output["statuses"]) != set(selected)):
        raise ValueError("EOS diagnostic did not establish the reviewed seven test identities")
    ids = output["native_ids"]
    if (not isinstance(ids, list) or len(ids) > 10000
            or any(not isinstance(item, str) or not item.startswith("tests/") or not item.isprintable() for item in ids)
            or len(set(ids)) != len(ids) or not set(selected) <= set(ids)):
        raise ValueError("EOS collected an invalid native test inventory")
    return output


async def run_checked(repo, store, request, record, exact, executor, trial):
    owned = record["launch"]["container"]
    if (journal.fingerprint(REVIEW) != exact or shutil.disk_usage(ROOT).free < record["minimum_free_bytes"]
            or prior.runner.docker("ps", "-aq", "--filter", f"name=^/{owned}$")):
        raise ValueError("review, free capacity or owned container changed")
    identity = trial.attempt_id
    repo.reserve(request, identity, AssessmentLimits(max_operations=1, max_elapsed_seconds=95), stage="eos-diagnostics")
    start, clock = utc_now(), time.monotonic()
    raw = await executor.execute(trial)
    if prior.runner.docker("ps", "-aq", "--filter", f"name=^/{owned}$"):
        raise RuntimeError("owned container cleanup is uncertain")
    receipt = ExecutionReceipt(
        decision_id=identity, action_id=identity, capability=trial.spec.capability,
        executor_id=trial.spec.id, executor_kind=trial.spec.kind, status=raw.status,
        started_at=start, ended_at=utc_now(), estimated=trial.estimate,
        actual_resources=raw.resources, execution_success=raw.status.value == "success",
        error_type=raw.error_type, metadata={"review_sha256": exact, "container_absent": True},
    )
    store.save_receipt(receipt)
    repo.finish_operation(identity, elapsed_seconds=time.monotonic()-clock, resources=receipt.actual_resources)
    return raw, receipt


async def main(args):
    record, executor, trial, snapshot = await make_scope()
    if args.prepare:
        free = shutil.disk_usage(ROOT).free
        if free <= 768 * 2**20:
            raise ValueError("insufficient working space for the single retained-image call")
        write(REVIEW, encode(record | {"minimum_free_bytes": free - 768*2**20,
            "expires_at": (utc_now() + timedelta(hours=2)).isoformat()}))
        print(journal.fingerprint(REVIEW))
        return
    existing = journal.doc(REVIEW)
    expiry = datetime.fromisoformat(existing["expires_at"])
    if (journal.fingerprint(REVIEW) != args.execute or utc_now() >= expiry
            or record | {k: existing[k] for k in ("minimum_free_bytes", "expires_at")} != existing):
        raise ValueError("EOS review pins or expiry drifted")
    write(TARGET / "started.json", encode({"review_sha256": args.execute}))
    definition, auth, request = prior.prior.grant(NAME, args.execute, expiry, 1, 95)
    with ReceiptStore(TARGET / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        repo.put("c13_eos_diagnostic_scope", content_digest(definition), definition)
        repo.approve_bundle(auth, {content_digest(definition): definition.model_dump(mode="json")})
        try:
            raw, receipt = await run_checked(repo, store, request, existing, args.execute, executor, trial)
            write(TARGET / "receipt.json", encode(receipt.model_dump(mode="json")))
            output = validate(raw.output, snapshot, record["selected"])
            write(TARGET / "result.json", encode(output | {"receipt": receipt.receipt_id}))
        finally:
            write(TARGET / "ledger.json", encode(repo.operation_ledger(auth.authorization_id).model_dump(mode="json")))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--execute")
    asyncio.run(main(parser.parse_args()))
