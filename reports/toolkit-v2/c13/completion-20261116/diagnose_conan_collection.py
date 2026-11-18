"""Prepare or run one exact, sanitized Conan collection diagnostic."""

import argparse
import asyncio
import shutil
import time
from datetime import datetime
from pathlib import Path
from types import ModuleType

import check_conan_pair as conan
from stage_repository_transport import digest, read

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentLimits,
    AssessmentScopeAmendment,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.repository_suites import grade_suite_output
from aeep.models import ExecutionReceipt, utc_now
from aeep.store import ReceiptStore

ROOT, TARGET, runner = conan.ROOT, conan.TARGET, conan.runner
ACTIVE = TARGET / "execution"
REVIEW = TARGET / "collection-review.json"
APPROVAL = TARGET / "collection-approval.json"
MARKER = TARGET / "collection-started.json"
TEMPLATE = conan.WORK / "c13-braindrop-protected-audit-20261118/diagnose_collection.py"
TEMPLATE_SHA = "366d36844c51f8cbfe7b5e276261fbed0859ad6e85f1e9c7e45d77218fce9316"
SANITIZER_SHA = "402a5fed53038b82fffef0706b32f2cdd2fa075b5db3484b153e7e21d9b97c26"
NAMES = ["conan", "conan.internal.api.detect.detect_api", "test_detect_compiler",
         "test_detect_cc_versioning", "pytest", "patch_ng", "yaml", "fasteners", "distro",
         "requests", "jinja2", "markupsafe", "colorama", "dateutil", "iniconfig", "packaging", "pluggy"]


def sanitizer():
    module = ModuleType("retained_collection_diagnostic")
    module.__file__ = str(TEMPLATE)
    raw = read(TEMPLATE, TEMPLATE_SHA)
    exec(compile(raw, str(TEMPLATE), "exec"), module.__dict__)
    read(module.SANITIZER, SANITIZER_SHA)
    module.NAMES = NAMES
    return module


async def prepare():
    conan.select_attempt()
    parent = runner.get(conan.REVIEW)
    baseline = runner.get(ACTIVE / "result.json")
    ledger = runner.get(ACTIVE / "ledger.json")
    observation, = baseline["observations"]
    charge, = ledger["operations"]
    if (baseline["verified"] or observation["contract_matched"] or charge["elapsed_seconds"] is None
            or observation["operation"] != charge["operation_id"]
            or not observation["operation"].endswith(":reference")):
        raise ValueError("the original protected attempt is unsettled or has changed")
    fields, original_spec, environment, cases = await runner.review_fields()
    if fields | {"expires_at": parent["expires_at"]} != parent:
        raise ValueError("failed reference scope changed")
    entry, = cases
    body = {}
    expected = runner.expected_statuses(entry["truth"], "reference")

    async def capture(payload):
        body.update(payload)
        return {k: payload[k] for k in ("archive_sha256", "python", "pytest")} | {
            "exit_code": 0, "statuses": expected,
        }

    await grade_suite_output(entry["input"], entry["truth"], entry["roles"]["reference"], capture)
    if content_digest(body) != parent["launches"][0]["payload_sha256"]:
        raise ValueError("diagnostic payload differs from the exact reference")
    tools = sanitizer()
    spec = tools.build_program(original_spec, expected)
    op = conan.NAME + ":collection-diagnostic"
    trial = runner.context(spec, op, body | {"collect_only": True})
    executor = ContainerExecutor(environment)
    argv, owner = executor.command(trial)
    if argv[argv.index("--network") + 1] != "none" or not {
        "--pull=never", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
    } <= set(argv) or runner.docker("ps", "-aq", "--filter", f"name=^/{owner}$"):
        raise ValueError("diagnostic escaped the reviewed local boundary")
    review = {
        "schema_version": "aeep.c13.conan-collection-diagnostic.v1",
        "prior_review_sha256": runner.file_digest(conan.REVIEW),
        "prior_result_sha256": runner.file_digest(ACTIVE / "result.json"),
        "prior_ledger_sha256": runner.file_digest(ACTIVE / "ledger.json"),
        "driver_sha256": runner.file_digest(Path(__file__)),
        "retained_diagnostic_template_sha256": TEMPLATE_SHA, "sanitizer_sha256": SANITIZER_SHA,
        "payload_sha256": content_digest(trial.request.input), "spec_sha256": content_digest(spec),
        "argv_sha256": content_digest({"argv": argv}), "operation": op, "owned_container": owner,
        "expires_at": parent["expires_at"], "remaining_operations": 1, "reserved_seconds": 35,
        "allowlisted_public_identifiers": NAMES, "raw_log_retention": False,
        "collection_only": True, "protected_grade": False, "maximum_retries": 0,
        "models": 0, "cash_usd": 0, "downloads": 0, "installs": 0, "provider_disclosure": False,
    }
    return review, ledger, executor, trial, tools


async def execute(exact, review, earlier, executor, trial, tools):
    if not APPROVAL.is_file() or APPROVAL.is_symlink() or runner.get(APPROVAL) != {
        "approved": True, "review_sha256": exact,
    }:
        raise ValueError("exact operator approval is required for the collection repeat")
    if MARKER.exists() or datetime.fromisoformat(review["expires_at"]) <= utc_now():
        raise ValueError("diagnostic already attempted or expired")
    if shutil.disk_usage(TARGET).free < 52 * 1024**3:
        raise ValueError("host is below the reviewed free-space floor")
    op, owner = review["operation"], review["owned_container"]
    with ReceiptStore(ACTIVE / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        grant = AssessmentAuthorization.model_validate(repo.get("authorization", conan.NAME))
        if (repo.operation_ledger(conan.NAME).model_dump(mode="json") != earlier
                or repo.current_grant(conan.NAME) != grant or grant.limits.max_operations != 2
                or grant.remote_disclosure or grant.limits.max_model_turns or grant.limits.max_cash_usd):
            raise ValueError("the settled original ledger or authority changed")
        old, = grant.subject_digests
        scope = runner.Scope(review_sha256=exact)
        new = content_digest(scope)
        repo.put("conan_collection_scope", new, scope)
        repo.approve_bundle(AssessmentScopeAmendment(
            amendment_id=op, authorization_id=conan.NAME, authorization_digest=content_digest(grant),
            subject_digests=[old], recipe_digests=[old], environment_digests=[old], reviewed_digests=[new],
        ), {old: repo.get("c13_cached_repository_pair_scope", old), new: scope.model_dump(mode="json")})
        request = RecipeMaterializationRequest(
            plan_id=conan.NAME, authorization_id=conan.NAME, subject_digest=old,
            recipe_digest=old, environment_digest=old, mapping_digest=old,
            definition_digests=[old, new], seed=0,
        )
        runner.put(MARKER, {"review_sha256": exact})
        repo.reserve(request, op, AssessmentLimits(max_operations=1, max_elapsed_seconds=35),
                     stage="protected_collection_diagnostic", require_settled_plan=True)
        start, clock = utc_now(), time.monotonic()
        try:
            raw = await executor.execute(trial)
        finally:
            await executor.close()
        if runner.docker("ps", "-aq", "--filter", f"name=^/{owner}$"):
            raise RuntimeError("owned container absence is unverified")
        valid = raw.status.value == "success" and tools.valid_reply(raw.output)
        receipt = ExecutionReceipt(
            decision_id=op, action_id=op, capability=trial.spec.capability,
            executor_id=trial.spec.id, executor_kind=trial.spec.kind,
            status="success" if valid else "failed", execution_success=valid,
            started_at=start, ended_at=utc_now(), estimated=trial.estimate, actual_resources=raw.resources,
            error_type=None if valid else raw.error_type or "CONAN_COLLECTION_DIAGNOSTIC_MISMATCH",
            metadata={"review_sha256": exact, "container_absent": True,
                      "validated_diagnostic_sha256": content_digest(raw.output) if valid else None},
        )
        store.save_receipt(receipt)
        repo.finish_operation(op, elapsed_seconds=time.monotonic() - clock, resources=raw.resources)
        runner.put(TARGET / "collection-ledger.json", repo.operation_ledger(conan.NAME).model_dump(mode="json"))
        runner.put(TARGET / "collection-result.json", {
            "receipt_id": receipt.receipt_id, "review_sha256": exact,
            "observations": raw.output if valid else None,
            "error_category": receipt.error_type, "grade": False, "container_absent": True,
        })
        return valid


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--prepare", action="store_true")
    scope.add_argument("--verify")
    scope.add_argument("--exact-review")
    args = parser.parse_args()
    review, *context = await prepare()
    if args.prepare:
        runner.put(REVIEW, review)
    else:
        pin = digest(REVIEW.read_bytes())
        if pin != (args.verify or args.exact_review) or review != runner.get(REVIEW):
            raise ValueError("exact diagnostic review differs")
        if args.exact_review:
            raise SystemExit(0 if await execute(pin, review, *context) else 1)
    print(runner.file_digest(REVIEW))


if __name__ == "__main__":
    asyncio.run(main())
