"""Read back prior and new protected pairs without opening enrollment or dispatch."""

import json
import sqlite3
from contextlib import closing

import audit_software_reproduction_pool as pool
from audit_software_carrier_coverage import expected_rows
from check_linux_install import HERE, ROOT
from plan_repository_expansion import previous_repositories
from stage_repository_transport import digest, read

BATCH = ROOT / ".aeep/c13-cohort-batch-20261124"
SOFTWARE = BATCH / "software-pinned-carrier"
BIRD = BATCH / "django-bird-grading"
DOCUMENTS = BATCH / "documents-verified"
TREASURY = BATCH / "treasury-october/document-verified"
A2A = BATCH / "a2a-current-ordinary"
CONTINUATION = ROOT / ".aeep/c13-cohort-continuation-20261124"
ENERGY = CONTINUATION / "energy-verified"
PYFAKEFS = CONTINUATION / "pyfakefs-pair"


def evidence(path):
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path.read_bytes())}


def audited(path):
    return pool.artifact(evidence(path))


def must_pair(roles):
    if len(roles) != 2 or [row["score"] for row in roles] != [1.0, 0.0]:
        raise ValueError("missing verified repair/original grades")


def settled(ledger, *operations):
    index = {row["operation_id"]: row for row in ledger["operations"]}
    if any(key not in index or index[key]["elapsed_seconds"] is None for key in operations):
        raise ValueError("unsettled operation cannot count as a reproduction")


def old_pairs():
    cases = audited(HERE / "full-rebench-three-leads-result-20261119.json")["cases"]
    for case, value in cases.items():
        for asset in (
            "source_archive",
            "reference_archive",
            "protected_overlay",
            "pinned_dataset_row",
        ):
            if (
                asset in ("reference_archive", "protected_overlay")
                and case == "jorenham__optype-29"
            ):
                continue
            pin = value[asset]
            read(ROOT / pin["path"], pin["sha256"])
        if not value["publisher_notices"] or not value["published_tree"]:
            raise ValueError(f"{case} lacks source or notice evidence")

    optype = audited(HERE / "optype-and-storage-20261119.json")["optype"]
    repair = optype["historical_reference_and_mismatch"]
    original = optype["approved_original_repeat"]
    score = optype["paired_scores"]
    roles = [pool.artifact(side["result"])["observations"][0] for side in (repair, original)]
    must_pair(roles)
    if not optype["verified_pair"] or score != {"published_repair": 1.0, "original": 0.0}:
        raise ValueError("Optype pair did not verify")
    for side, role in zip((repair, original), roles, strict=True):
        settled(pool.artifact(side["ledger"]), role["operation"])
        records = [pool.artifact(pin) for pin in side["receipts"]]
        if not any(
            record["receipt_id"] == role["receipt_id"] and record["execution_success"]
            for record in records
        ):
            raise ValueError("Optype receipt differs")
    optype_ids = [role["receipt_id"] for role in roles]

    locify = audited(HERE / "grader-repair-result-20261120.json")
    roles = [locify["observed"]["locify_" + role] for role in ("reference", "original")]
    must_pair(roles)
    locify_ids = []
    for row in roles:
        receipt = pool.artifact(row["receipt_record"])
        settled(pool.artifact(locify["ledger"]), receipt["action_id"])
        if not row["accepted"] or receipt["receipt_id"] != row["receipt"]:
            raise ValueError("Locify observation differs")
        locify_ids.append(row["receipt"])

    eos = audited(HERE / "eos-repaired-grader-result-20261120.json")
    roles = [eos["actual"][role] for role in ("reference", "original")]
    must_pair(roles)
    final = pool.artifact(eos["final_result"])
    run = eos["actual_operations"]["c13-eos-repaired-pair-local-date-20261120"]
    eos_ids = []
    for role, result in zip(("reference", "original"), roles, strict=True):
        matches = [item for item in run["receipts"] if item["receipt"] == result["receipt"]]
        (record,) = matches
        receipt = pool.artifact(record["observation"])
        settled(pool.artifact(run["ledger"]), receipt["action_id"])
        if not result["accepted"] or final[role]["receipt"] != receipt["receipt_id"]:
            raise ValueError("adapted EOS observation differs")
        eos_ids.append(receipt["receipt_id"])

    proof = [
        (
            "jorenham__optype-29",
            "multi-file-repair",
            "adapted_selector_and_original_suite",
            optype_ids,
        ),
        ("ryanhoangt__locify-8", "multi-file-repair", "published_repair_and_original", locify_ids),
        (
            "Akkudoktor-EOS__EOS-459",
            "single-file-repair",
            "adapted_offline_dependency_and_fixture",
            eos_ids,
        ),
    ]
    rows = [
        pool.case_row(
            case, cases[case]["repository"], cases[case]["source_revision"], family, mode, refs
        )
        for case, family, mode, refs in proof
    ]
    return rows


def new_pairs():
    review = audited(SOFTWARE / "operation-review.json")
    result = audited(SOFTWARE / "execution/result.json")
    if result["review_sha256"] != evidence(SOFTWARE / "operation-review.json")["sha256"]:
        raise ValueError("software operation binding changed")
    param = "holoviz__param-1073"
    roles = [row for row in result["observations"] if f":{param}:" in row["operation"]]
    must_pair(roles)
    for row in roles:
        settled(audited(SOFTWARE / "execution/ledger.json"), row["operation"])
        receipt = audited(SOFTWARE / "execution" / f"receipt-{row['receipt_id']}.json")
        if not row["contract_matched"] or receipt["receipt_id"] != row["receipt_id"]:
            raise ValueError("unverified Param pair")
    bound = review["sources"][param]
    param_row = pool.case_row(
        param,
        bound["repository"],
        bound["source_revision"],
        "single-file-repair",
        "ordinary_protected_pair",
        [r["receipt_id"] for r in roles],
    )
    case = "joshuadavidthomas__django-bird-239"
    bound = review["sources"][case]
    bird = audited(BIRD / "result.json")
    roles = [bird["reference"], bird["original"]]
    must_pair(roles)
    if bird["required_native_counts"] != {"fail_to_pass": 1, "pass_to_pass": 73} or not all(
        row["accepted"] for row in roles
    ):
        raise ValueError("Django Bird did not preserve the full native scope")
    ledger = audited(BIRD / "ledger.json")
    settled(
        ledger,
        "c13-django-bird-complete-20261124:reference",
        "c13-django-bird-complete-20261124:original",
    )
    bird_row = pool.case_row(
        case,
        bound["repository"],
        bound["source_revision"],
        "multi-file-repair",
        "source_bound_native_selector_recovery",
        [row["receipt"] for row in roles],
    )
    return [param_row, bird_row]


def document_cases(directory):
    result = audited(directory / "result.json")
    if (
        result["model_turns"]
        or result["asset_use_reviewed_for_provider"]
        or result["formal_assignments"]
    ):
        raise ValueError("document evidence exceeded local calibration scope")
    for task, row in result["cases"].items():
        roles = row["checks"]
        if [
            roles[role]["score"]["score"] for role in ("reference-grade", "missing-row", "bad-json")
        ] != [1, 0, 0] or not all(item["verified"] for item in roles.values()):
            raise ValueError("document case lacks trustworthy calibration")
        root = directory / task
        ledger = audited(root / "ledger.json")
        if len(ledger["operations"]) != 4 or any(
            x["elapsed_seconds"] is None for x in ledger["operations"]
        ):
            raise ValueError("unsettled document grader")
        for role, observation in roles.items():
            if audited(root / f"{role}-result.json") != observation:
                raise ValueError("document grade differs from the retained result")
        archive = root / "public" / (row["public_zip_sha256"] + ".zip")
        if len(read(archive, row["public_zip_sha256"])) != row["public_zip_bytes"]:
            raise ValueError("document task archive size changed")
    return result["cases"]


def a2a_pairs():
    run = A2A / "execution"
    result = audited(run / "result.json")
    review = audited(A2A / "operation-review.json")
    bridge = audited(HERE / "a2a-receipt-bridge-audit.json")
    preparation = ROOT / ".aeep/completion-20261116/a2a-ordinary-grader"
    definitions = audited(preparation / "summary.json")
    ledger = audited(run / "ledger.json")
    historical = audited(A2A / "history/ledger.json")
    recorded = {row["operation_id"]: row for row in ledger["operations"]}
    if (
        not result["verified"]
        or len(recorded) != 10
        or any(recorded.get(row["operation_id"]) != row for row in historical["operations"])
        or any(result[key] for key in ("models", "cash_usd", "formal_cases_adopted"))
        or result["review_sha256"] != evidence(A2A / "operation-review.json")["sha256"]
        or definitions["execution_definition_files"]["observer.json"]
        != evidence(preparation / "observer.json")["sha256"]
    ):
        raise ValueError("A2A result or historical ledger differs")
    rows = []
    receipts = {row["role"]: row for row in result["operations"]}
    with closing(
        sqlite3.connect((A2A / "history/receipts.sqlite3").as_uri() + "?mode=ro", uri=True)
    ) as db:
        for case, source in bridge["cases"].items():
            name = f"{case}.json"
            definition = pool.artifact(
                {
                    "path": (preparation / name).relative_to(ROOT).as_posix(),
                    "sha256": definitions["execution_definition_files"][name],
                }
            )
            truth = definition["truth"]
            assert truth["tests"]["sha256"] == source["protected_test_archive_sha256"]
            assert (
                len(truth["pass_to_pass"]) + len(truth["fail_to_pass"])
                == source["required_assertions"]
            )
            pair = []
            for role, score in (("reference", 1.0), ("original", 0.0)):
                row = receipts[f"{case}-{role}"]
                operation = f"aeep-c13-a2a-ordinary:{case}:{role}"
                (stored,) = db.execute(
                    "SELECT payload_json FROM receipts WHERE receipt_id=?", (row["receipt_id"],)
                ).fetchone()
                receipt = json.loads(stored)
                settled(ledger, operation)
                if (
                    not row["contract_matched"]
                    or not receipt["execution_success"]
                    or receipt["decision_id"] != operation
                    or review["attempts"][case][role]["expected_score"] != score
                    or receipt["metadata"]["review_sha256"] != result["review_sha256"]
                    or receipt["metadata"]["container_absent"] is not True
                ):
                    raise ValueError("A2A grade lacks its settled protected evidence")
                pair.append(row["receipt_id"])
            rows.append(
                pool.case_row(
                    case,
                    "a2aproject/a2a-python",
                    source["source_revision"],
                    definition["input"]["family"],
                    "ordinary_protected_pair",
                    pair,
                )
            )
    return rows


def pyfakefs_pair():
    run = PYFAKEFS / "execution"
    result = audited(run / "result.json")
    review_path = PYFAKEFS / "operation-review.json"
    review = audited(review_path)
    legacy = audited(HERE / "pyfakefs-protected-audit-result-20261118.json")
    if (
        not result["verified"]
        or result["review_sha256"] != evidence(review_path)["sha256"]
        or review["publisher_tree"] != legacy["publisher_tree"]
        or any(result[key] for key in ("models", "cash_usd", "formal_cases_adopted"))
    ):
        raise ValueError("Pyfakefs review or result changed")
    roles = result["observations"]
    must_pair(roles)
    counts = audited(run / "status-counts.json")
    if [role["required_status_counts"] for role in counts] != [
        {"PASSED": 432},
        {"PASSED": 431, "FAILED": 1},
    ] or any(role["unexpected_required_status_counts"] for role in counts):
        raise ValueError("Pyfakefs did not preserve all required identities")
    ledger = audited(run / "ledger.json")
    if len(ledger["operations"]) != 2:
        raise ValueError("Pyfakefs recorded an unexpected operation")
    receipt_ids = []
    for role, launch in zip(roles, review["launches"], strict=True):
        receipt_id = role["receipt_id"]
        receipt = audited(run / f"receipt-{receipt_id}.json")
        settled(ledger, role["operation"])
        if (
            role["operation"] != launch["operation"]
            or launch["required_tests"] != 432
            or not role["contract_matched"]
            or receipt["decision_id"] != role["operation"]
            or receipt["receipt_id"] != receipt_id
            or receipt["metadata"]["container_absent"] is not True
            or not receipt["execution_success"]
        ):
            raise ValueError("Pyfakefs grade lacks its settled evidence")
        receipt_ids.append(receipt_id)
    return pool.case_row(
        legacy["case"],
        "pytest-dev/pyfakefs",
        legacy["source_revision"],
        "single-file-repair",
        "ordinary_protected_pair_with_expanded_pytest_wheel",
        receipt_ids,
    )


def main():
    recovery = audited(HERE / "recovery-67a93f4c-result-20261119.json")[
        "software_reproduction_pool"
    ]
    initial = expected_rows() + recovery["new_rows"]
    _, _, excluded = previous_repositories()
    if pool.assess(initial, excluded) != recovery["capacity"]:
        raise ValueError("earlier 54-case pool did not reproduce")
    retained, fresh = old_pairs(), new_pairs() + a2a_pairs() + [pyfakefs_pair()]
    updated = pool.assess(initial + retained + fresh, excluded)
    cases = document_cases(DOCUMENTS) | document_cases(TREASURY) | document_cases(ENERGY)
    print(
        json.dumps(
            {
                "schema_version": "aeep.c13.cohort-batch-readback.v1",
                "software": {
                    "previous": recovery["capacity"],
                    "current": updated,
                    "previously_verified_now_reconciled": retained,
                    "fresh_protected_pairs": fresh,
                    "formal_cases_adopted": 0,
                },
                "document_data": {"new_local_grader_cases": cases, "formal_cases_adopted": 0},
                "evidence": {
                    p.name: evidence(p)
                    for p in (
                        SOFTWARE / "operation-review.json",
                        BIRD / "selector-map.json",
                        DOCUMENTS / "pack.json",
                    )
                }
                | {
                    "treasury_pack": evidence(TREASURY / "pack.json"),
                    "a2a_result": evidence(A2A / "execution/result.json"),
                    "a2a_ledger": evidence(A2A / "execution/ledger.json"),
                    "a2a_review": evidence(A2A / "operation-review.json"),
                    "pyfakefs_review": evidence(PYFAKEFS / "operation-review.json"),
                    "pyfakefs_result": evidence(PYFAKEFS / "execution/result.json"),
                    "energy_pack": evidence(ENERGY / "pack.json"),
                },
                "comparisons_paused": True,
                "waza_excluded": True,
                "model_turns": 0,
                "cash_usd": 0,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
