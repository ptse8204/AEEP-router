"""Rebuild the current C13 software inventory from protected evidence."""

import argparse
import json
from pathlib import Path

import audit_software_reproduction_pool as pool
import reconcile_cohort_batch as cohort
from stage_repository_transport import ROOT, digest, write


def check_receipt(receipt_ref, ledger_ref, review_ref, role, observation_ref=None):
    receipt = pool.artifact(receipt_ref)
    review = pool.artifact(review_ref)
    ledger = pool.artifact(ledger_ref)
    metadata = receipt["metadata"]
    operation = receipt["action_id"]
    (charge,) = [row for row in ledger["operations"] if row["operation_id"] == operation]
    if (
        not operation.endswith(":" + role)
        or not receipt["execution_success"]
        or metadata.get("container_absent") is not True
        or metadata.get("operation_review_sha256", metadata.get("review_sha256"))
        != review_ref["sha256"]
        or charge["elapsed_seconds"] is None
        or charge["reserved"]["max_model_turns"]
        or float(charge["reserved"]["max_cash_usd"])
        or review.get("environment", {}).get("network")
    ):
        raise ValueError(f"protected {role} receipt is unbound or unsettled")
    if observation_ref:
        observed = pool.artifact(observation_ref)
        observed_pin = metadata.get("protected_observation_sha256")
        if observed_pin and observed_pin != pool.content_digest(observed):
            raise ValueError(f"protected {role} observation changed")
    return receipt["receipt_id"]


def verified_pair(case, repo, revision, family, roles, scope):
    ids = []
    for role, score in (("reference", 1), ("original", 0)):
        record = roles[role]
        if record.get("score", record.get("grade")) != score:
            raise ValueError(f"missing independent {role} score for {case}")
        ids.append(
            check_receipt(
                record["receipt"],
                scope["ledger"],
                scope["review"],
                role,
                record.get("observation", record.get("native_observation")),
            )
        )
    return pool.case_row(case, repo, revision, family, "verified_protected_pair", ids)


def serde_pair(block):
    case = block["software_pair"]
    root = ROOT / ".aeep/c13-cohort-runtime-20261124/c13-pyserde-657-pair-20261124-msgpack"
    original = block["software_runs"][root.name + "-original"]
    reference = case["reference"]
    refs = {
        n: {"path": (root / n).relative_to(ROOT).as_posix(), "sha256": h}
        for n, h in reference["pins"].items()
    }
    (record,) = pool.artifact(refs["execution/diagnostic.json"])
    (fault_record,) = pool.artifact(original["diagnostic"])
    selected = case["controls"]["required_statuses"]
    reference_statuses = record["required_statuses"]
    if (
        len(selected) != 12
        or set(reference_statuses) != selected.keys()
        or set(reference_statuses.values()) != {"PASSED"}
        or record["exit_code"] != 0
        or fault_record != case["controls"]
        or list(selected.values()).count("FAILED") != 5
        or not case["controls"]["matched"]
        or reference["score"] != 1
        or case["original"]["score"] != 0
    ):
        raise ValueError("Pyserde recovered reference or original assertions changed")
    ref = check_receipt(
        refs[f"execution/receipt-{reference['receipt']}.json"],
        refs["execution/ledger.json"],
        refs["operation-review.json"],
        "reference",
    )
    (receipt,) = original["receipts"]
    fault = check_receipt(
        receipt,
        original["execution/ledger.json"],
        original["operation-review.json"],
        "original",
    )
    if ref != reference["receipt"] or fault != case["original"]["receipt_id"]:
        raise ValueError("Pyserde grade points at different receipts")
    return pool.case_row(
        case["case"],
        case["repository"],
        case["revision"],
        case["family"],
        "verified_recovered_reference_and_protected_original",
        [ref, fault],
    )


def protected_addition(record):
    if (
        record["schema_version"] != "aeep.c13.protected-case-addition.v1"
        or record["formal_case_adopted"]
        or not record["comparisons_paused"]
        or not record["waza_excluded"]
        or record["models"]
        or record["cash_usd"]
    ):
        raise ValueError("unexpected protected case scope")
    result = pool.artifact(record["result"])
    review = pool.artifact(record["review"])
    case = record["case"]
    if (
        not result["verified"]
        or result["review_sha256"] != record["review"]["sha256"]
        or review["cases"][case]["source_revision"] != record["revision"]
        or result["models"]
        or result["cash_usd"]
        or result["formal_cases_adopted"]
    ):
        raise ValueError("case evidence does not match its settled review")
    row = verified_pair(
        case, record["repository"], record["revision"], record["family"], record["roles"], record
    )
    (reference, original) = result["observations"]
    for role, proof, receipt, score in zip(
        ("reference", "original"), (reference, original), row["receipt_ids"], (1, 0), strict=True
    ):
        if (
            proof["receipt_id"] != receipt
            or not proof["contract_matched"]
            or proof["score"] != score
            or not proof["operation"].endswith(f":{case}:{role}")
        ):
            raise ValueError("reference or original outcome is bound to a different attempt")
    return row


def audit(additions=()):
    pins = {}
    _, _, excluded = pool.previous_repositories()
    rows = cohort.expected_rows()

    def check_capacity(expected):
        actual = pool.assess(rows, excluded)
        if actual != expected:
            raise ValueError(f"stored software capacity does not match current evidence: {actual}")

    recovery = pool.load("recovery-67a93f4c-result-20261119.json", pins)[
        "software_reproduction_pool"
    ]
    rows.extend(recovery["new_rows"])
    check_capacity(recovery["capacity"])
    batch = pool.load("cohort-batch-20261124.json", pins)["software"]
    retained = cohort.old_pairs()
    fresh = cohort.new_pairs() + cohort.a2a_pairs() + [cohort.pyfakefs_pair(), cohort.pygls_pair()]
    if (
        retained != batch["previously_verified_now_reconciled"]
        or fresh != batch["fresh_protected_pairs"]
    ):
        raise ValueError("cohort's stored cases do not match revalidated protected evidence")
    rows.extend(retained + fresh)
    check_capacity(batch["current"])

    serde = pool.load("protected-cohort-followup-20261124.json", pins)
    rows.append(serde_pair(serde))
    check_capacity(serde["software_pool"])

    sqlite = pool.load("protected-cohort-expansion-20261124.json", pins)
    pair = sqlite["verified_sqlite_cli_pair"]
    roles = dict(zip(("reference", "original"), pair["cases"], strict=True))
    rows.append(
        verified_pair(
            pair["case"],
            pair["repository"],
            pair["source_revision"],
            "single-file-repair",
            roles,
            pair,
        )
    )
    check_capacity(sqlite["software_pool"])

    avro = pool.load("protected-avroschema-batch-20261124.json", pins)
    for pair in avro["new_pairs"]:
        rows.append(
            verified_pair(
                pair["case"],
                pair["repository"],
                pair["source_revision"],
                pair["case_family"],
                pair["roles"],
                pair,
            )
        )
    check_capacity(avro["software_pool"])

    confluence = pool.load("protected-confluence-cli-20261124.json", pins)
    rows.append(
        verified_pair(
            confluence["case"],
            confluence["repository"],
            confluence["source_revision"],
            confluence["case_family"],
            confluence["observations"],
            confluence["proof"],
        )
    )
    check_capacity(confluence["software_pool"])

    towncrier = pool.load("protected-towncrier-contract-20261124.json", pins)
    refs = towncrier["evidence"]
    rows.append(
        verified_pair(
            towncrier["case"],
            towncrier["repository"],
            towncrier["source_revision"],
            towncrier["case_family"],
            towncrier["roles"],
            {"ledger": refs["execution/ledger.json"], "review": refs["review.json"]},
        )
    )
    check_capacity(towncrier["software_pool"])

    skelebot = pool.load("protected-retained-carrier-batch-20261124.json", pins)
    rows.append(
        verified_pair(
            skelebot["case"],
            skelebot["repository"],
            skelebot["source_revision"],
            "contract-audit",
            skelebot["roles"],
            skelebot["grading_evidence"],
        )
    )
    check_capacity(skelebot["software_pool"])

    latest = pool.load("protected-anyio-and-dialect-batch-20261124.json", pins)
    anyio = latest["settled_anyio"]
    rows.append(
        verified_pair(
            anyio["case"],
            "agronholm/anyio",
            anyio["revision"],
            "single-file-repair",
            anyio["roles"],
            anyio,
        )
    )
    sql = latest["settled_dialect_batch"]
    for case in sql["verified_pairs"]:
        pair = sql["cases"][case]
        rows.append(
            verified_pair(
                case,
                "agronholm/sqlacodegen",
                pair["revision"],
                "single-file-repair",
                pair["roles"],
                sql,
            )
        )
    check_capacity(latest["software_pool"])
    for name in additions:
        if Path(name).name != name:
            raise ValueError("additional evidence must be a case report in this directory")
        rows.append(protected_addition(pool.load(name, pins)))
    return {
        "schema_version": "aeep.c13.current-protected-software-inventory.v1",
        "inputs": pins,
        "capacity": pool.assess(rows, excluded),
        "rows": sorted(rows, key=lambda row: row["case"]),
        "formal_cases_adopted": 0,
        "formal_assignments": 0,
        "new_model_turns": 0,
        "comparisons_paused": True,
        "waza_excluded": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("--add-case", action="append", default=[])
    args = parser.parse_args()
    report = (json.dumps(audit(args.add_case), indent=2, sort_keys=True) + "\n").encode()
    write(args.out.resolve(), report)
    print(digest(report))
