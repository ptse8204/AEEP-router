"""Prepare one reference diagnostic against the settled Advanced Alchemy grant."""

import argparse
import asyncio
import shutil
import time
from datetime import datetime
from pathlib import Path

import check_advanced_alchemy_pair as pair

from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentLimits,
    AssessmentScopeAmendment,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.models import ExecutionReceipt, utc_now
from aeep.store import ReceiptStore

REVIEW = pair.SCOPE / "reference-diagnostic-review.json"
APPROVAL = pair.SCOPE / "reference-diagnostic-approval.json"
RUN = pair.SCOPE / "reference-diagnostic-execution"
DB = pair.RUN / "receipts.sqlite3"
OPERATION = pair.NAME + ":reference-diagnostic"


def settled_prior(store):
    repo = AssessmentRepository(store)
    results = pair.runner.get(pair.RUN / "result.json")
    ledger = pair.runner.get(pair.RUN / "ledger.json")
    before = repo.operation_ledger(pair.NAME).model_dump(mode="json")
    grant = AssessmentAuthorization.model_validate(repo.get("authorization", pair.NAME))
    if (
        results["verified"]
        or [item["role"] for item in results["observations"]] != ["collection", "reference"]
        or [item["verified"] for item in results["observations"]] != [True, False]
        or before != ledger
        or [item["operation_id"] for item in before["operations"]]
        != [pair.NAME + ":collection", pair.NAME + ":reference"]
        or any(item["elapsed_seconds"] is None for item in before["operations"])
        or repo.current_grant(pair.NAME) != grant
        or grant.limits.max_operations != 3
        or grant.limits.max_elapsed_seconds != 195
        or grant.limits.max_model_turns
        or grant.limits.max_cash_usd
        or grant.remote_disclosure
        or grant.allowed_destinations != ["local"]
    ):
        raise ValueError("the settled first attempt or its remaining scope changed")
    for item in results["observations"]:
        receipt = store.get_receipt(item["receipt_id"])
        exported = pair.runner.get(pair.RUN / (item["role"] + "-receipt.json"))
        if (
            receipt is None
            or receipt.model_dump(mode="json") != exported
            or receipt.execution_success != item["verified"]
            or not receipt.metadata["owned_container_absent"]
            or receipt.metadata["summary"] != item["summary"]
        ):
            raise ValueError("the canonical original receipt differs")
    return repo, grant


def diagnostics(reply, payload, truth):
    if not isinstance(reply, dict) or not isinstance(reply.get("evaluation"), dict):
        return None
    frame = reply["evaluation"]
    statuses = frame.get("statuses")
    if (
        any(frame.get(key) != payload[key] for key in ("archive_sha256", "python", "pytest"))
        or type(frame.get("exit_code")) is not int
        or frame["exit_code"] not in range(6)
        or not isinstance(statuses, dict)
        or len(statuses) > 10_000
        or any(
            not isinstance(value, str)
            or value not in {"PASSED", "FAILED", "ERROR", "SKIPPED", "XFAIL"}
            for value in statuses.values()
        )
    ):
        return None
    # Retain only identities already present in the protected oracle and their observed status.
    required = truth["fail_to_pass"] + truth["pass_to_pass"]
    failures = [
        {
            "node_id": node,
            "status": statuses.get(node, "MISSING"),
            "kind": "issue" if node in truth["fail_to_pass"] else "preservation",
        }
        for node in required
        if statuses.get(node) != "PASSED"
    ]
    return {
        "exit_code": frame["exit_code"],
        "observed_status_count": len(statuses),
        "required_test_count": len(required),
        "required_mismatches": failures,
        "grade": None,
        "protected_observation_sha256": content_digest(frame),
    }


async def prepare():
    baseline, executor, spec, _, truth, _, payloads = await pair.prepare()
    prior = pair.runner.get(pair.REVIEW)
    if prior != baseline | {"expires_at": prior["expires_at"]}:
        raise ValueError("prior protected review no longer reproduces")
    with ReceiptStore(DB, read_only=True) as store:
        _repo, _grant = settled_prior(store)
    reference = payloads["reference"]
    old_ctx, _ = pair.launch(executor, spec, "reference", reference)
    old_argv, old_owner = executor.command(old_ctx)
    context = pair.runner.context(spec, OPERATION, reference)
    argv, owner = executor.command(context)
    if argv != [owner if value == old_owner else value for value in old_argv]:
        raise ValueError("only the fresh container identity may differ")
    fields = {
        "schema_version": "aeep.c13.advanced-alchemy-reference-diagnostic.v1",
        "driver": pair.binding(Path(__file__)),
        "original_review": pair.binding(pair.REVIEW),
        "original_result": pair.binding(pair.RUN / "result.json"),
        "original_ledger": pair.binding(pair.RUN / "ledger.json"),
        "original_reference_receipt": pair.binding(pair.RUN / "reference-receipt.json"),
        "image": baseline["environment"]["container_image"],
        "argv_sha256": content_digest({"argv": argv}),
        "protected_payload_sha256": content_digest(reference),
        "owned_container": owner,
        "operation": OPERATION,
        "one_repeat": True,
        "remaining_operations": 1,
        "reserve_seconds": pair.SECONDS,
        "expires_at": prior["expires_at"],
        "retain_only_mismatched_oracle_identities": True,
        "retain_raw_logs": False,
        "protected_grade": False,
        "model_turns": 0,
        "cash_usd": 0,
        "builds": 0,
        "downloads": 0,
        "provider_disclosure": False,
        "comparisons_paused": True,
        "waza_excluded": True,
    }
    return fields, executor, context, truth


async def execute(exact, review, executor, context, truth):
    if pair.runner.get(APPROVAL) != {"approved": True, "review_sha256": exact}:
        raise ValueError("exact operator authority is required for this repeat")
    if (
        RUN.exists()
        or datetime.fromisoformat(review["expires_at"]) <= utc_now()
        or shutil.disk_usage(pair.SCOPE).free < pair.FREE
    ):
        raise ValueError("reviewed repeat is terminal, expired or below storage reserve")
    owner = review["owned_container"]
    if pair.runner.docker("ps", "-aq", "--filter", f"name=^/{owner}$"):
        raise ValueError("diagnostic identity already exists")
    RUN.mkdir(mode=0o700)
    with ReceiptStore(DB) as store:
        repo, grant = settled_prior(store)
        (original,) = grant.subject_digests
        scope = pair.runner.Scope(review_sha256=exact)
        reviewed = content_digest(scope)
        repo.put("c13_advanced_alchemy_reference_diagnostic_scope", reviewed, scope)
        repo.approve_bundle(
            AssessmentScopeAmendment(
                amendment_id=OPERATION,
                authorization_id=pair.NAME,
                authorization_digest=content_digest(grant),
                subject_digests=[original],
                recipe_digests=[original],
                environment_digests=[original],
                reviewed_digests=[reviewed],
            ),
            {
                original: repo.get("c13_advanced_alchemy_scope", original),
                reviewed: scope.model_dump(mode="json"),
            },
        )
        request = RecipeMaterializationRequest(
            plan_id=pair.NAME,
            authorization_id=pair.NAME,
            subject_digest=original,
            recipe_digest=original,
            environment_digest=original,
            mapping_digest=original,
            definition_digests=[original, reviewed],
            seed=0,
        )
        repo.reserve(
            request,
            OPERATION,
            AssessmentLimits(max_operations=1, max_elapsed_seconds=pair.SECONDS),
            stage="protected_reference_diagnostic",
            require_settled_plan=True,
        )
        start, clock = utc_now(), time.monotonic()
        try:
            raw = await executor.execute(context)
        finally:
            await executor.close()
        if pair.runner.docker("ps", "-aq", "--filter", f"name=^/{owner}$"):
            raise RuntimeError("cleanup remains uncertain; preserve the pending reservation")
        facts = (
            diagnostics(raw.output, context.request.input, truth)
            if raw.status.value == "success"
            else None
        )
        receipt = ExecutionReceipt(
            decision_id=OPERATION,
            action_id=OPERATION,
            capability=context.spec.capability,
            executor_id=context.spec.id,
            executor_kind=context.spec.kind,
            status="success" if facts else "failed",
            execution_success=bool(facts),
            started_at=start,
            ended_at=utc_now(),
            estimated=context.estimate,
            actual_resources=raw.resources,
            error_type=None if facts else raw.error_type or "DIAGNOSTIC_PROTOCOL_MISMATCH",
            metadata={
                "review_sha256": exact,
                "owned_container_absent": True,
                "diagnostic_sha256": content_digest(facts) if facts else None,
            },
        )
        store.save_receipt(receipt)
        repo.finish_operation(
            OPERATION, elapsed_seconds=time.monotonic() - clock, resources=raw.resources
        )
        pair.runner.put(RUN / "receipt.json", receipt.model_dump(mode="json"))
        pair.runner.put(
            RUN / "ledger.json", repo.operation_ledger(pair.NAME).model_dump(mode="json")
        )
        pair.runner.put(
            RUN / "result.json",
            {
                "receipt_id": receipt.receipt_id,
                "diagnostic": facts,
                "authority": exact,
                "protected_grade": None,
            },
        )
    return bool(facts)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--verify")
    mode.add_argument("--exact-review")
    args = parser.parse_args()
    review, *prepared = await prepare()
    if args.prepare:
        pair.runner.put(REVIEW, review)
    else:
        exact = args.verify or args.exact_review
        if pair.runner.file_digest(REVIEW) != exact or pair.runner.get(REVIEW) != review:
            raise ValueError("reference repeat differs from the exact review")
        if args.exact_review:
            raise SystemExit(0 if await execute(exact, review, *prepared) else 1)
    print(pair.runner.file_digest(REVIEW))


if __name__ == "__main__":
    asyncio.run(main())
