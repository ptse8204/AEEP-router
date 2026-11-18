"""Verify contract-audit receipts and keep terminal repeats separate from grading."""
import asyncio
from collections import Counter
from datetime import datetime
import json
from pathlib import Path

import check_expansion_contracts as contracts
from audit_software_reproduction_pool import assess, audit, case_row
from plan_repository_expansion import previous_repositories
from reconcile_c13_offline_completion import operations, prove_grade, read_receipt, reference
from aeep.assessment.models import content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.models import utc_now
from aeep.store import ReceiptStore

HERE, WORK, runner = contracts.HERE, contracts.WORK, contracts.runner
BATCH = WORK / "c13-expansion-contracts-20261118"


async def guardian():
    contracts.configure("django-guardian")
    review, _, _, [case] = await runner.review_fields()
    recorded = runner.get(runner.REVIEW)
    result = runner.get(runner.RUN / "result.json")
    review_digest = runner.file_digest(runner.REVIEW)
    ledger = runner.get(runner.RUN / "ledger.json")
    entries = operations(ledger)
    if not result["verified"] or review_digest != result["review_sha256"]:
        raise ValueError("protected pair review reference differs")
    if review != {name: item for name, item in recorded.items() if name != "expires_at"}:
        raise ValueError("published scope changed")
    if len(entries) != 2 or len(result["observations"]) != 2:
        raise ValueError("exact two settled roles required")
    observations = []
    with ReceiptStore(runner.RUN / "receipts.sqlite3", read_only=True) as store:
        if AssessmentRepository(store).operation_ledger(runner.NAME).model_dump(mode="json") != ledger:
            raise ValueError("saved operation inventory changed")
        for role, row, command in zip(runner.ROLES, result["observations"], review["launches"], strict=True):
            if row["operation"] != command["operation"] or row["operation"] not in entries or not row["contract_matched"]:
                raise ValueError("operation and protected observer do not match")
            path = runner.RUN / f"receipt-{row['receipt_id']}.json"
            receipt = read_receipt(store, path, row["operation"], row, review_digest, "operation_review_sha256")
            expected = runner.expected_statuses(case["truth"], role)
            if len(expected) != 19 or receipt.metadata["status_counts"] != dict(Counter(expected.values())):
                raise ValueError("protected test counts changed")
            await prove_grade(case, role, command, receipt, expected, "protected_observation_sha256", row["score"])
            observations.append({"role": role, "receipt": reference(path), "score": row["score"],
                                 "test_outcomes": receipt.metadata["status_counts"]})
    row, *_ = contracts.source_inputs("django-guardian")
    evidence = case_row(case["case_id"], row["source_repository"], case["source_revision"],
                        case["input"]["family"], "settled_ordinary_reference_and_original",
                        [item["receipt_id"] for item in result["observations"]])
    return {
        "scope_review": reference(runner.REVIEW), "ledger": reference(runner.RUN / "ledger.json"),
        "result": reference(runner.RUN / "result.json"), "observations": observations,
        "settled_seconds": sum(row["elapsed_seconds"] for row in entries.values()),
        "operations": len(entries), "verified": True,
    }, evidence


def otel():
    contracts.configure("opentelemetry")
    first = runner.get(runner.RUN / "result.json")
    first_attempt = runner.get(runner.RUN / "ledger.json")
    namespace = runner.get(BATCH / "otel-namespace-pair-result.json")
    threads = runner.get(BATCH / "thread-ceiling-result.json")
    earlier_ledgers = (first_attempt, runner.get(BATCH / "otel-collection-ledger.json"),
                       runner.get(BATCH / "otel-namespace-pair-ledger.json"))
    path = BATCH / "thread-ceiling-ledger.json"
    ledger = runner.get(path)
    combined = operations(ledger)
    for previous in earlier_ledgers:
        prior = operations(previous)
        if prior != {name: combined[name] for name in prior}:
            raise ValueError("earlier failure, diagnostic or charge changed")
    if len(combined) != 5 or not threads["verified"] or namespace["verified"] or first["verified"]:
        raise ValueError("unexpected corrected-attempt or thread probe state")
    with ReceiptStore(runner.RUN / "receipts.sqlite3", read_only=True) as store:
        if AssessmentRepository(store).operation_ledger(runner.NAME).model_dump(mode="json") != ledger:
            raise ValueError("saved OpenTelemetry grouping differs")
        def receipt_data(row, operation, status):
            receipt = store.get_receipt(row["receipt_id"])
            if (receipt is None or receipt.action_id != operation or operation not in combined
                    or receipt.execution_success is not status or not receipt.metadata["container_absent"]):
                raise ValueError("OpenTelemetry receipt, operation or cleanup mismatch")
            return receipt

        first_ref, = first["observations"]
        receipt_data(first_ref, first_ref["operation"], False)
        diagnostic = runner.get(BATCH / "otel-collection-result.json")
        receipt = receipt_data(diagnostic, runner.NAME + ":collection-diagnostic", True)
        if receipt.metadata["validated_diagnostic_sha256"] != content_digest(diagnostic["observations"]):
            raise ValueError("collection diagnosis differs from its receipt")
        corrected_ref, = namespace["observations"]
        receipt_data(corrected_ref, runner.NAME + ":namespace-repair:reference", False)
        for row, cap, started in zip(threads["observations"], (96, 128), (94, 100), strict=True):
            receipt = receipt_data(row, runner.NAME + f":thread-cap-probe:{cap}", True)
            if (row["cap"] != cap or not row["verified"] or row["facts"]["threads_started"] != started
                    or receipt.metadata["facts"] != row["facts"]):
                raise ValueError("thread ceiling measurements differ")
    return {
        "original_observation": reference(runner.RUN / "result.json"),
        "collection_diagnostic": reference(BATCH / "otel-collection-result.json"),
        "bootstrap_repair": reference(BATCH / "otel-repair-preflight.json"),
        "first_corrected_reference": reference(BATCH / "otel-namespace-pair-result.json"),
        "thread_probe": reference(BATCH / "thread-ceiling-result.json"),
        "thread_caps_verified": threads["observations"], "ledger": reference(path), "operations": len(combined),
        "settled_seconds": sum(row["elapsed_seconds"] for row in combined.values()),
        "protected_grade_verified": False, "original_source_role_dispatched": False,
    }


async def main():
    baseline = HERE / "offline-completion-results-20261118.json"
    previous = runner.get(baseline)["software_reproduction_pool"]
    rows = [*audit()["rows"], *previous["additional_rows"]]
    _, _, excluded = previous_repositories()
    if assess(rows, excluded) != previous["capacity"]:
        raise ValueError("previous reproduction pool changed")
    completed, row = await guardian()
    observed = otel()
    capacity = assess([*rows, row], excluded)
    assert capacity["reproduced_rows"] == 48 and capacity["repository_families"] == 27
    print(json.dumps({
        "schema_version": "aeep.c13.expansion-contract-audit-results.v1",
        "authority": reference(BATCH / "delegated-authority.json"),
        "earlier_reproduction_pool": reference(baseline), "django_guardian": completed, "opentelemetry": observed,
        "software_reproduction_pool": {"new_row": row, "capacity": capacity},
        "accounted_operations": completed["operations"] + observed["operations"],
        "summed_settled_wall_seconds": completed["settled_seconds"] + observed["settled_seconds"],
        "new_wheel_download_bytes": 81985, "new_model_turns": 0, "cash_usd": 0,
        "comparisons_paused": True, "provider_disclosure": False, "waza_excluded": True,
        "formal_cases_adopted": 0,
    }, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    asyncio.run(main())
