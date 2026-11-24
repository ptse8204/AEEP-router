"""Recover comparable grader-operation timings from the reconciled C13 corpus."""

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median

import audit_two_cohort_source_capacity as capacity
from audit_formal_reservation_capacity import ledger_balance
from stage_repository_transport import HERE, ROOT, digest, encode, read, write

TIMING_REPORTS = (
    "retained-grader-evidence.json",
    "optype-and-storage-20261119.json",
    "grader-repair-result-20261120.json",
    "eos-repaired-grader-result-20261120.json",
)


def records(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from records(child)
    elif isinstance(value, list):
        for child in value:
            yield from records(child)


def evidence_files(seed_paths):
    pending = dict(seed_paths)
    used = set()
    while remaining := sorted(pending.keys() - used):
        for path in remaining:
            used.add(path)
            pin = pending[path]
            data = json.loads(read(path, pin))
            yield path, pin, data
            for row in records(data):
                name, sha = row.get("path"), row.get("sha256")
                if (
                    not isinstance(name, str)
                    or not name.endswith(".json")
                    or not isinstance(sha, str)
                ):
                    continue
                location = ROOT / name
                if (
                    not location.is_relative_to(ROOT)
                    or not (
                        location.is_relative_to(ROOT / ".aeep")
                        or location.is_relative_to(HERE.parent)
                    )
                    or location.resolve() != location
                    or any(word in location.name.casefold() for word in ("auth", "credential"))
                    or not location.is_file()
                ):
                    continue
                if pending.setdefault(location, sha) != sha:
                    raise ValueError("two reports disagree on a retained evidence digest")


def positive(value):
    return type(value) in {int, float} and math.isfinite(value) and value > 0


def unique_measurement(rows):
    values = {seconds for seconds, _, _ in rows}
    if len(values) != 1:
        raise ValueError("settled operation timing is inconsistent across retained evidence")
    seconds, path, pin = min(rows)
    return {"elapsed_seconds": seconds, "source": {"path": path, "sha256": pin}}


def resolved_timings(allowed, sources):
    actions, explicit, ledger = defaultdict(set), defaultdict(set), defaultdict(set)
    for path, pin, data in evidence_files(sources):
        for row in records(data):
            receipt = row.get("receipt_id")
            if not isinstance(receipt, str):
                receipt = row.get("receipt")
            action = row.get("operation_id", row.get("action_id", row.get("operation")))
            seconds = row.get("elapsed_seconds")
            ref = path.relative_to(ROOT).as_posix()
            if isinstance(receipt, str) and receipt in allowed:
                if isinstance(action, str):
                    actions[receipt].add(action)
                if (
                    positive(seconds)
                    and isinstance(row.get("measurement_sha256"), str)
                    and isinstance(row.get("receipt_sha256"), str)
                    and isinstance(action, str)
                ):
                    explicit[receipt].add((seconds, ref, pin))
            if (
                isinstance(action, str)
                and "operation_id" in row
                and positive(seconds)
                and isinstance(reservation := row.get("reserved"), dict)
                and reservation.get("max_model_turns") == 0
                and float(reservation["max_cash_usd"]) == 0
            ):
                ledger[action].add((seconds, ref, pin))
    matched = {}
    for receipt in sorted(allowed):
        observations = set(explicit[receipt])
        for action in actions[receipt]:
            observations.update(ledger[action])
        if observations:
            matched[receipt] = unique_measurement(observations)
    return matched


def statistics(seconds):
    values = sorted(seconds)
    if not values:
        return {"observations": 0}
    return {
        "observations": len(values),
        "minimum_seconds": values[0],
        "median_seconds": median(values),
        "p95_nearest_rank_seconds": values[math.ceil(len(values) * 0.95) - 1],
        "maximum_seconds": values[-1],
        "sum_elapsed_seconds": math.fsum(values),
    }


def document_batches():
    scopes = (
        (
            "varex-protected-cohort-result-20261124.json",
            "native_grades",
            "protected_reference_grade_count",
            "ledger",
            "receipt",
        ),
        (
            "varex-balanced-capacity-20261124.json",
            "complementary_grades",
            "complementary_reference_checks_passed",
            "complementary_operation_ledger",
            "complementary_receipt_id",
        ),
    )
    result = []
    for name, grades, passing, ledger, receipt in scopes:
        path = HERE / name
        raw = path.read_bytes()
        proof = json.loads(raw)
        (operation,) = proof[ledger]["operations"]
        seconds = operation["elapsed_seconds"]
        if (
            operation["stage"] != "protected_reference_verification"
            or not positive(seconds)
            or operation["reserved"]["max_model_turns"] != 0
            or float(operation["reserved"]["max_cash_usd"])
            or proof["model_turns"]
            or proof["formal_assignments"]
        ):
            raise ValueError("VAREX effort is outside the protected reference batch scope")
        result.append(
            {
                "input_documents": len(proof[grades]),
                "passing_references": proof[passing],
                "settled_batch_elapsed_seconds": seconds,
                "receipt": proof[receipt],
                "source": {"path": path.relative_to(ROOT).as_posix(), "sha256": digest(raw)},
            }
        )
    return result


def audit(observed_at):
    verified, _ = capacity.source_pools()
    inventory = capacity.load(capacity.INVENTORY)
    earlier = capacity.load("software-reproduction-pool-20261117.json")
    pins = {HERE / name: sha for name, sha in (inventory["inputs"] | earlier["inputs"]).items()}
    for name in TIMING_REPORTS:
        path = HERE / name
        pins.setdefault(path, digest(path.read_bytes()))
    receipt_family = {
        receipt: row["family"] for row in inventory["rows"] for receipt in row["receipt_ids"]
    }
    measured = resolved_timings(receipt_family.keys(), pins)
    family_totals = {
        family: statistics(
            row["elapsed_seconds"]
            for receipt, row in measured.items()
            if receipt_family[receipt] == family
        )
        for family in capacity.FAMILIES
    }
    for family, totals in family_totals.items():
        totals["receipts_in_inventory"] = sum(value == family for value in receipt_family.values())
    cases_with_full_timing = sum(
        all(receipt in measured for receipt in row["receipt_ids"]) for row in inventory["rows"]
    )
    grant = ledger_balance()
    if observed_at.tzinfo is None:
        raise ValueError("timing audit needs an explicit observation timezone")
    grant["expired_at_observation"] = datetime.fromisoformat(grant["expires_at"]) <= observed_at
    return {
        "schema_version": "aeep.c13.protected-grader-batch-cost.v1",
        "observed_at": observed_at.isoformat(),
        "inventory_sha256": digest((HERE / capacity.INVENTORY).read_bytes()),
        "verified_cases": len(verified),
        "complete_timing_case_count": cases_with_full_timing,
        "receipts_in_inventory": len(receipt_family),
        "timing_coverage": statistics(row["elapsed_seconds"] for row in measured.values()),
        "measurements_by_family": family_totals,
        "protected_grade_span_scope": "Settled protected operation elapsed time from bound receipts. "
        "Setup and reporting outside the operation, artifact acquisition and model calls are excluded.",
        "six_case_serial_example": {
            "cases_per_family": 2,
            "reference_and_original_operations": 12,
            "sum_of_observed_family_p95s_seconds": 4
            * sum(row["p95_nearest_rank_seconds"] for row in family_totals.values()),
            "sum_of_observed_family_maxima_seconds": 4
            * sum(row["maximum_seconds"] for row in family_totals.values()),
            "scope": "Illustrative protected-only elapsed time using the observed mix. "
            "Preparation, runtime changes, timeouts and resource allowances need separate review.",
        },
        "minimum_additional_protected_grader_calls": 2
        * inventory["capacity"]["minimum_missing_rows_if_all_reproduced_rows_are_eligible"],
        "document_protected_reference_batches": document_batches(),
        "document_timing_scope": "Two whole VAREX reference-calibration operations. "
        "Concurrent capacity, per-document timings and managed task output grading were not measured.",
        "operational_grant_readonly": grant,
        "new_model_turns": 0,
        "new_protected_operations": 0,
        "grant_changed": False,
        "resource_acceptance": "OPEN",
        "comparisons_paused": True,
        "waza_excluded": True,
        "timing_receipts": measured,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--at", type=datetime.fromisoformat, required=True)
    args = parser.parse_args()
    print(write(args.output, encode(audit(args.at))))
