"""Reconcile the completed offline group without rerunning upstream software."""
import asyncio
from collections import Counter
import json

import check_arta_pair as arta
import check_returnn_pair as returnn
from audit_software_reproduction_pool import assess, audit, case_row
from plan_repository_expansion import previous_repositories
from stage_repository_transport import HERE, ROOT, WORK, digest, read

from aeep.assessment.models import content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.repository_suites import grade_suite_output
from aeep.store import ReceiptStore

RETURNN_RUNTIME = WORK / "returnn-native-runtime-20261118"
IMPORT_DIAGNOSTIC = WORK / "returnn-import-diagnostic-20261117"
GROUP_PATH = HERE / "offline-group-9ee3ca0f-result-20261117.json"
CORRECTIONS_PATH = HERE / "offline-correction-results-20261117.json"


def reference(path):
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path.read_bytes())}


def load(path):
    return json.loads(path.read_bytes())


def retained(ref):
    return json.loads(read(ROOT / ref["path"], ref["sha256"]))


def operations(ledger):
    rows = {entry["operation_id"]: entry for entry in ledger["operations"]}
    if len(rows) != len(ledger["operations"]) or any(
        row["elapsed_seconds"] is None or row["reserved"]["max_model_turns"]
        or float(row["reserved"]["max_cash_usd"]) for row in rows.values()
    ):
        raise ValueError("unexpected resource reservation or unsettled operation")
    return rows


async def prove_grade(case, role, launch, receipt, expected, metadata_key, scores):
    code = int(role == "original")

    async def reconstitute(payload):
        observed = {
            key: payload[key] for key in ("archive_sha256", "python", "pytest")
        } | {"exit_code": code, "statuses": expected}
        if (content_digest(payload) != launch["payload_sha256"]
                or observed["archive_sha256"] != launch["archive_sha256"]
                or content_digest(observed) != receipt.metadata[metadata_key]):
            raise ValueError("receipt no longer matches the exact protected observation")
        return observed

    grade = await grade_suite_output(case["input"], case["truth"], case["roles"][role], reconstitute)
    if grade.trust != "verified" or grade.quality_score != scores:
        raise ValueError("protected callback no longer reproduces the score")


def read_receipt(store, path, operation, sample, review_digest, metadata_key):
    data = load(path)
    receipt = store.get_receipt(sample["receipt_id"])
    if (receipt is None or receipt.model_dump(mode="json") != data
            or receipt.action_id != operation or receipt.decision_id != operation
            or not receipt.execution_success or receipt.error_type
            or not receipt.metadata["container_absent"]
            or receipt.metadata[metadata_key] != review_digest):
        raise ValueError("receipt or cleanup does not match the canonical ledger")
    return receipt


async def returnn_result():
    record = load(RETURNN_RUNTIME / "result.json")
    review_path = RETURNN_RUNTIME / "operation-review.json"
    review = load(review_path)
    previous = load(IMPORT_DIAGNOSTIC / "ledger.json")
    ledger = load(RETURNN_RUNTIME / "ledger.json")
    prior = operations(previous)
    current = operations(ledger)
    if (not record["verified"] or record["review_sha256"] != reference(review_path)["sha256"]
            or record["model_turns"] or record["cash_usd"] or record["formal_cases_adopted"]
            or prior != {key: current[key] for key in prior}
            or [row["role"] for row in record["observations"]] != ["import", "runtime", "reference", "original"]
            or not all(row["contract_matched"] for row in record["observations"])):
        raise ValueError("RETURNN continuation evidence does not match")
    for path, sha in review["bindings"].items():
        read(ROOT / path, sha)
    stages = review["launches_normalized_to_parent_image"]
    returnn.select_attempt()
    _, _, cases = returnn.definitions()
    case, = cases
    source = next(row for row in load(returnn.PUBLISHER)["bindings"] if row["case"] == returnn.CASE)
    fresh = {key: row for key, row in current.items() if key not in prior}
    if set(fresh) != {f"{returnn.NAME}:native-dependency:{role}" for role in ("import", *stages)}:
        raise ValueError("unexpected operation in the RETURNN continuation")
    with ReceiptStore(returnn.RUN / "receipts.sqlite3", read_only=True) as store:
        repo = AssessmentRepository(store)
        if repo.operation_ledger(returnn.NAME).model_dump(mode="json") != ledger:
            raise ValueError("RETURNN operation records changed")
        for sample in record["observations"]:
            role = sample["role"]
            operation = f"{returnn.NAME}:native-dependency:{role}"
            path = RETURNN_RUNTIME / (role + "-receipt.json")
            if role == "import":
                receipt = store.get_receipt(sample["receipt_id"])
                if (receipt is None or receipt.model_dump(mode="json") != load(path)
                        or receipt.action_id != operation or not receipt.execution_success
                        or receipt.metadata["review_sha256"] != record["review_sha256"]
                        or receipt.metadata["observation_sha256"] != content_digest(record["imported"])):
                    raise ValueError("retained imported image differs from its receipt")
                continue
            receipt = read_receipt(store, path, operation, sample, record["review_sha256"], "review_sha256")
            if role == "runtime":
                if receipt.metadata["observation_sha256"] != content_digest(sample["facts"]):
                    raise ValueError("runtime probe receipt differs")
                continue
            expected = dict.fromkeys(case["truth"]["pass_to_pass"] + case["truth"]["fail_to_pass"], "PASSED")
            if role == "original":
                expected.update(dict.fromkeys(case["truth"]["fail_to_pass"], "FAILED"))
            if sample["status_counts"] != dict(Counter(expected.values())):
                raise ValueError("RETURNN protected statuses differ")
            await prove_grade(case, role, stages[role], receipt, expected, "observation_sha256", sample["score"])
    rows = record["observations"][-2:]
    result = {
        "verified": True, "case": source["case"], "source_revision": source["source_revision"],
        "prior_operations_preserved": len(prior), "new_operations": len(fresh),
        "new_settled_seconds": sum(row["elapsed_seconds"] for row in fresh.values()),
        "new_reserved_seconds": sum(row["reserved"]["max_elapsed_seconds"] for row in fresh.values()),
        "runtime": record["imported"] | {"versions": review["versions"]},
        "protected_pair": rows,
        "driver": reference(RETURNN_RUNTIME / "verify.py"),
        "dependency_review": reference(RETURNN_RUNTIME / "dependency-review.json"),
        "review": reference(review_path), "rehearsal": reference(RETURNN_RUNTIME / "rehearsal.json"),
        "ledger": reference(RETURNN_RUNTIME / "ledger.json"), "result": reference(RETURNN_RUNTIME / "result.json"),
        "verified_protected_statuses": 13,
    }
    pool_row = case_row(source["case"], source["source_repository"], source["source_revision"], source["family"],
                        "settled_ordinary_reference_and_original", [row["receipt_id"] for row in rows])
    return result, pool_row


async def arta_result(group):
    evidence = group["results"]["arta-protected-grading"]
    role_rows = evidence["observations"]
    ledger = retained(evidence["ledger"])
    record = retained(evidence["result"])
    prepared, failures, case = arta.staged_case()
    scope = load(arta.REVIEW)
    review_digest = reference(arta.REVIEW)["sha256"]
    root = arta.TARGET / "execution"
    ops = operations(ledger)
    if (not record["verified"] or record["review_sha256"] != review_digest
            or record["models"] or record["cash_usd"] or record["formal_cases_adopted"]
            or len(role_rows) != len(ops) or len(ops) != 2):
        raise ValueError("Arta result no longer verifies")
    with ReceiptStore(root / "receipts.sqlite3", read_only=True) as store:
        if AssessmentRepository(store).operation_ledger(arta.NAME).model_dump(mode="json") != ledger:
            raise ValueError("Arta operation records changed")
        for role, sample, launch in zip(("reference", "original"), role_rows, scope["launches"], strict=True):
            operation = sample["operation"]
            if operation not in ops or operation != launch["operation"] or operation.rsplit(":", 1)[-1] != role:
                raise ValueError("Arta observation order differs")
            path = root / ("receipt-" + sample["receipt_id"] + ".json")
            receipt = read_receipt(store, path, operation, sample, review_digest, "operation_review_sha256")
            expected = dict.fromkeys(case["truth"]["pass_to_pass"], "PASSED")
            if role == "original":
                expected.update(dict.fromkeys(failures, "FAILED"))
            await prove_grade(case, role, launch, receipt, expected, "protected_observation_sha256", sample["score"])
    row = case_row(case["case_id"], "maif/arta", prepared["revision"], case["input"]["family"],
                   "settled_ordinary_reference_and_original", [sample["receipt_id"] for sample in role_rows])
    return row


async def reconcile():
    group = load(GROUP_PATH)
    corrections = load(CORRECTIONS_PATH)
    before = audit()
    previous = load(HERE / "software-reproduction-pool-20261117.json")
    if before != {key: value for key, value in previous.items() if key != "verification"}:
        raise ValueError("the prior reproducible pool changed")
    returnn_evidence, returnn_row = await returnn_result()
    arta_row = await arta_result(group)
    _, _, excluded = previous_repositories()
    rows = [*before["rows"], arta_row, returnn_row]
    capacity = assess(rows, excluded)
    accepted = {key for key, row in group["results"].items() if row["passed"]}
    if corrections["group"] != reference(GROUP_PATH) or not corrections["formula_extraction"]["verified"]:
        raise ValueError("earlier correction belongs to another group")
    accepted |= {"formula-ordinary-grading", "returnn-protected-grading"}
    if accepted != group["results"].keys():
        raise ValueError("offline group still has an unverified scope")
    return {
        "schema_version": "aeep.c13.offline-completion-reconciliation.v1",
        "initial_group": reference(GROUP_PATH), "earlier_corrections": reference(CORRECTIONS_PATH),
        "initial_passes": group["scopes_passed"], "scopes_verified_after_recovery": sorted(accepted),
        "unsettled_operations_in_group_and_repairs": group["new_unsettled_operations"] + corrections["unsettled_operations"],
        "operations_in_group_and_repairs": corrections["total_operations_group_and_corrections"]
                                           + returnn_evidence["new_operations"],
        "returnn": returnn_evidence,
        "software_reproduction_pool": {
            "previous": reference(HERE / "software-reproduction-pool-20261117.json"),
            "additional_rows": [arta_row, returnn_row], "capacity": capacity,
        },
        "formal_cases_adopted": 0, "formal_stages_assigned": 0, "new_upstream_tests_run_by_audit": 0,
        "model_turns": 0, "cash_usd": 0, "comparisons_paused": True, "waza_excluded": True,
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(reconcile()), indent=2, sort_keys=True, allow_nan=False))
