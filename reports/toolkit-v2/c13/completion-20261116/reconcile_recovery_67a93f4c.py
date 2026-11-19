"""Read back the seven approved recovery scopes and updated case capacity."""

import json
from collections import Counter
from unittest.mock import patch

import audit_extractbench_transport_capacity as transport
import audit_extractbench_year_groups as years
import audit_software_reproduction_pool as pool
import check_migrated_graders as migrated
from audit_extractbench_collection_shapes import observed_paths
from audit_software_carrier_coverage import expected_rows
from check_linux_install import docker
from recover_extractbench_schemas import bound_inputs
from stage_repository_transport import HERE, ROOT, WORK, digest, read

from aeep.assessment.containment import container_name
from aeep.assessment.models import content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.attempts import ExecutionAttemptState
from aeep.store import ReceiptStore

SCOPE = WORK / "recovery-67a93f4c-20261119"
APPROVED = "67a93f4c0eeb82756491771d8261a394eec698c4178e597be62ace2ef9e9913a"
PYGLS = WORK / "c13-pygls-contract-20261118/timeout-diagnostic/execution"
ALCHEMY = WORK / "larger-multifile-source-20261118"
CONAN = WORK / "c13-conan-protected-pair-20261118"
OTEL = WORK / "c13-expansion-contracts-20261118"
BRAINDROP = WORK / "c13-braindrop-protected-audit-20261118"


def load(path):
    return json.loads(path.read_bytes())


def ref(path):
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path.read_bytes())}


def absent(name):
    if docker("ps", "-aq", "--filter", f"name=^/{name}$"):
        raise ValueError("owned grader container is still present")


def operations(doc):
    rows = {row["operation_id"]: row for row in doc["operations"]}
    if len(rows) != len(doc["operations"]):
        raise ValueError("duplicate operation identity")
    return rows


def elapsed(row):
    reservation = row["reserved"]
    if (
        row["elapsed_seconds"] is None
        or reservation["max_model_turns"]
        or float(reservation["max_cash_usd"])
    ):
        raise ValueError("recovery charge missing or outside the approved scope")
    return {
        "observed_seconds": row["elapsed_seconds"],
        "reserved_seconds": reservation["max_elapsed_seconds"],
    }


def settled_group(db, ledger, prior_ledger, ids, pin, owners):
    exported = load(ledger)
    after = operations(exported)
    before = operations(load(prior_ledger)) if prior_ledger else {}
    with ReceiptStore(db, read_only=True) as store:
        actual = (
            AssessmentRepository(store)
            .operation_ledger(exported["plan_id"])
            .model_dump(mode="json")
        )
        if actual != exported or any(after.get(key) != value for key, value in before.items()):
            raise ValueError("ledger changed or an earlier charge was lost")
        measurements = []
        for identity in ids:
            receipt = store.get_receipt(identity)
            if (
                receipt is None
                or receipt.action_id not in after
                or receipt.action_id in before
                or receipt.metadata.get(
                    "review_sha256", receipt.metadata.get("operation_review_sha256")
                )
                != pin
                or not receipt.metadata.get(
                    "container_absent", receipt.metadata.get("owned_container_absent")
                )
            ):
                raise ValueError("receipt differs from reviewed recovery or cleanup")
            measurements.append(
                {
                    "receipt": identity,
                    "operation": receipt.action_id,
                    "execution_success": receipt.execution_success,
                    **elapsed(after[receipt.action_id]),
                }
            )
    if {row["operation"] for row in measurements} != after.keys() - before.keys():
        raise ValueError("group launched an extra operation or the result lost a charge")
    for owner in owners:
        absent(owner)
    return measurements


def check_pair(result):
    rows = result["observations"]
    if not result["verified"] or [row["score"] for row in rows] != [1.0, 0.0]:
        raise ValueError("both previously reviewed outcomes must settle")
    return [row["receipt_id"] for row in rows]


def migrated_readback(path, review):
    completed = pool.artifact(path)
    expected = [item["operation_id"] for item in review["dispatches"]]
    results = completed["results"]
    if [item["operation_id"] for item in results] != expected or len(results) != 4:
        raise ValueError("ordinary role result does not match the reviewed chapter")
    recovered = []
    with ReceiptStore(migrated.DATABASE, read_only=True) as app:
        repo = AssessmentRepository(app)
        ledger = repo.operation_ledger(migrated.NAME).model_dump(mode="json")
        fees = operations(ledger)
        if fees.keys() != set(expected):
            raise ValueError("ordinary recipe budget has other operations")
        for index, (approved, result) in enumerate(zip(review["dispatches"], results, strict=True)):
            operation = expected[index]
            summary = load(migrated.RUN / f"{index}-receipt.json")
            observation = load(migrated.RUN / f"{index}-raw.json")
            score = float(index % 2 == 0)
            if (
                summary["operation_id"] != operation
                or not summary["original_cleanup_confirmed"]
                or result["grade"]["trust"] != "verified"
                or result["grade"]["quality_score"] != score
                or observation["archive_sha256"] != approved["archive_sha256"]
            ):
                raise ValueError("ordinary score, original cleanup or protected payload differs")
            db = migrated.OPERATIONS / migrated.NAME / "recipe-operations" / f"{operation}.sqlite3"
            with ReceiptStore(db, read_only=True) as single:
                saved = single.get_receipt(summary["receipt_id"])
                attempt = single.get_execution_attempt(summary["attempt_id"])
                if (
                    saved is None
                    or attempt is None
                    or attempt.state is not ExecutionAttemptState.COMPLETED
                    or saved.receipt_id not in attempt.terminal_receipt_ids
                    or content_digest(saved) != summary["receipt_sha256"]
                    or content_digest(fees[operation]) != summary["measurement_sha256"]
                ):
                    raise ValueError("ordinary terminal receipt or charge changed")
            absent(container_name(summary["attempt_id"]))
            recovered.append(
                {
                    "receipt": summary["receipt_id"],
                    "operation": operation,
                    "case": approved["case_id"],
                    "score": score,
                    **elapsed(fees[operation]),
                }
            )
    return recovered


def intake_readback():
    base = WORK / "rebench-full-metadata-20261118/protected-identities"
    saved = load(base / "result.json")
    original = HERE / "full-rebench-metadata-intake-20261118.json"
    inputs = json.loads(read(original, saved["review_sha256"]))
    discovery = inputs["protected_identity_intake_plan"]
    cases = {}
    verified_ranges = set()
    for group in discovery["row_groups"]:
        for case in group["row_positions"]:
            row = saved["cases"][case]
            data = json.loads(read(base / f"{case}.json", row["protected_record_sha256"]))
            for column in row["column_observations"]:
                proof = group["allowed_ranges"][column["column"]]
                if column["bytes"] != proof["bytes"] or column["start"] != proof["start"]:
                    raise ValueError("intake left the exact bounded public ranges")
                verified_ranges.add((column["column"], column["start"]))
            counts = [len(data.get(k) or []) for k in ("FAIL_TO_PASS", "PASS_TO_PASS")]
            if all(counts) and counts != [row["issue_tests"], row["preservation_tests"]]:
                raise ValueError("protected identity count changed")
            cases[case] = {k: v for k, v in row.items() if k != "column_observations"}
    if (
        set(cases) != saved["cases"].keys()
        or len(verified_ranges) != discovery["maximum_range_requests"]
    ):
        raise ValueError("protected row or range inventory changed")
    return {
        "result": ref(base / "result.json"),
        "cases": cases,
        "ranges_verified": len(verified_ranges),
    }


def extractbench_readback(path):
    original = json.loads(read(transport.RECOVERY, transport.RECOVERY_PIN))
    rows, _, _ = bound_inputs(original, transport.RECOVERY.parent)
    saved = pool.artifact(path)
    root = ROOT / path["path"]
    counts, unsupported = observed_paths(
        root.parent, load(root.parent / "recovered-acquisition.json")
    )
    if (
        unsupported
        or len(counts) != 71
        or len(saved["requests"]) != 5
        or any(r["status"] != "verified" for r in saved["requests"])
    ):
        raise ValueError("public recovery did not verify the exact schema inventory")
    unresolved = {r["schema_sha256"] for r in original["requests"]}
    groups = transport.eligible_groups(rows)
    linked, annual, _, _ = years.linked_groups(rows, groups, unresolved)
    _, entries = transport.acquisition(years.ACQUISITION, years.ACQUISITION_REVIEW)
    inventory, _ = transport.file_sizes(rows, entries)
    with patch.object(transport, "INSTRUCTION_LIMIT", 600_000):
        classes = {
            case: transport.transport_class(inventory[case])
            for _, cases in groups.items()
            for case in cases
        }
    outcomes = {}
    for scope, allowed in (
        ("stored_size", {"stored_zip_size_within_limit"}),
        (
            "includes_unmeasured_compression",
            {"stored_zip_size_within_limit", "compressed_zip_size_needed"},
        ),
    ):
        outcomes[scope] = {}
        for name, excluded in (
            ("with_linked_annual_family", set()),
            ("holding_annual_family", set(annual)),
        ):
            viable = {
                g: [case for case in cases if case not in excluded and classes[case] in allowed]
                for g, cases in linked.items()
            }
            totals, result = years.evaluate(rows, viable, counts)
            outcomes[scope][name] = {
                "at_most_one_collection": totals[0],
                "multiple_collections": totals[1],
                "balanced_metadata_witness": result,
            }
    return {
        "result": path,
        "verified_schema_bodies": len(counts),
        "downloaded_bytes": sum(r["body_read_bytes"] for r in saved["requests"]),
        "transport_classes": dict(Counter(classes.values())),
        "linked_annual_cases": len(annual),
        "updated_feasibility": outcomes,
        "scope": "Pinned source-family and ZIP metadata capacity. PDF rights, exact ZIP materialization, protected grading and stage admission remain open.",
    }


def audit():
    status = load(SCOPE / "member-status.json")
    plans = load(SCOPE / "member-dispatches.json")
    approval = load(SCOPE / "operator-approval.json")
    pool.artifact(approval["review"])
    if not (
        status["group_sha256"] == plans["group_sha256"] == approval["review"]["sha256"] == APPROVED
        and len(status["members"]) == 7
    ):
        raise ValueError("the seven-member group did not settle")
    counted = {}
    reviewed = {}
    files = {}
    for p, r in zip(plans["planned"], status["members"], strict=True):
        if p["name"] != r["name"] or not r["result_present"] or not r["marker_present"]:
            raise ValueError("group is missing a terminal member")
        name = p["name"]
        reviewed[name] = pool.artifact(p["review"])
        files[name] = {"path": p["result"], "sha256": r["result_sha256"]}
        counted[name] = pool.artifact(files[name])
    pygls = counted["pygls-reference-diagnostic"]
    (sample,) = pygls["observations"]
    alchemy = counted["advanced-alchemy-reference-diagnostic"]
    conan = counted["conan-collection-diagnostic"]
    otel = counted["opentelemetry-current-review-rebuild"]
    braindrop = counted["braindrop-native-selector-repair"]
    recovered = {
        "pygls": settled_group(
            PYGLS / "receipts.sqlite3",
            PYGLS / "ledger.json",
            None,
            [sample["receipt_id"]],
            pygls["review_sha256"],
            [reviewed["pygls-reference-diagnostic"]["launches"][0]["container"]],
        ),
        "alchemy": settled_group(
            ALCHEMY / "protected-pair-execution/receipts.sqlite3",
            ALCHEMY / "reference-diagnostic-execution/ledger.json",
            ALCHEMY / "protected-pair-execution/ledger.json",
            [alchemy["receipt_id"]],
            alchemy["authority"],
            [reviewed["advanced-alchemy-reference-diagnostic"]["owned_container"]],
        ),
        "conan": settled_group(
            CONAN / "execution/receipts.sqlite3",
            CONAN / "collection-ledger.json",
            CONAN / "execution/ledger.json",
            [conan["receipt_id"]],
            conan["review_sha256"],
            [reviewed["conan-collection-diagnostic"]["owned_container"]],
        ),
        "opentelemetry": settled_group(
            WORK / "c13-opentelemetry-protected-audit-20261118/execution/receipts.sqlite3",
            OTEL / "otel-pids-continuation-ledger.json",
            OTEL / "thread-ceiling-ledger.json",
            check_pair(otel),
            otel["review_sha256"],
            [
                x["container"]
                for x in reviewed["opentelemetry-current-review-rebuild"]["commands"].values()
            ],
        ),
        "braindrop": settled_group(
            BRAINDROP / "execution/receipts.sqlite3",
            BRAINDROP / "native-selector-repeat-ledger.json",
            BRAINDROP / "braindrop-collection-ledger.json",
            check_pair(braindrop),
            braindrop["review_sha256"],
            [
                x["container"]
                for x in reviewed["braindrop-native-selector-repair"]["commands"].values()
            ],
        ),
        "migrated": migrated_readback(
            files["dissect-cstruct-and-mockito-migrated-grader"],
            reviewed["dissect-cstruct-and-mockito-migrated-grader"],
        ),
    }
    receipts = [row for members in recovered.values() for row in members]
    if len(receipts) != 11 or sum(row["reserved_seconds"] for row in receipts) != 415:
        raise ValueError("recovery reservation inventory differs from the approved envelope")
    source = load(HERE / "repository-expansion-acquisition-result.json")["candidates"]
    inserted = []
    for section, label in (
        ("opentelemetry", "open-telemetry__opentelemetry-python-4891"),
        ("braindrop", "davep__braindrop-96"),
    ):
        (row,) = [x for x in source if x["case"].startswith(label)]
        inserted.append(
            pool.case_row(
                row["case"],
                row["repository"],
                row["revision"],
                "contract-audit",
                "settled_ordinary_reference_and_original",
                [x["receipt"] for x in recovered[section]],
            )
        )
    prep = load(HERE / "formal-transport-preparation.json")
    staged = json.loads(
        read(ROOT / prep["prepared_pool_relative_path"], prep["prepared_pool_sha256"])
    )
    for case in sorted({x["case"] for x in recovered["migrated"]}):
        (row,) = [r for r in staged if r["independent_case_id"] == case]
        inserted.append(
            pool.case_row(
                case,
                row["source_repository"],
                row["source_revision"],
                row["input"]["family"],
                "settled_ordinary_reference_and_counterexample",
                [x["receipt"] for x in recovered["migrated"] if x["case"] == case],
            )
        )
    current = expected_rows()
    _, _, excluded = pool.previous_repositories()
    snapshot = load(SCOPE / "local-snapshot-result.json")
    if not snapshot["only_authorized_removed"]:
        raise ValueError("snapshot delta differs from the exact authorized operation")
    pygls_detail = load(PYGLS / "worker-diagnostic.json")
    if (
        pygls_detail["operation"] != recovered["pygls"][0]["operation"]
        or pygls_detail["archive_sha256"]
        != reviewed["pygls-reference-diagnostic"]["launches"][0]["archive_sha256"]
        or pygls_detail["observer_category"] != "child_timeout"
    ):
        raise ValueError("PyGLS progress differs from the exact timed-out reference")
    return {
        "schema_version": "aeep.c13.recovery-67a93f4c-result.v1",
        "approved": approval["review"],
        "approval_record": ref(SCOPE / "operator-approval.json"),
        "snapshot_result": ref(SCOPE / "local-snapshot-result.json"),
        "usable_gained_bytes": snapshot["free_gain_bytes"],
        "retained_other_local_snapshots": [x["SnapshotName"] for x in snapshot["after_snapshots"]],
        "dispatch_result": ref(SCOPE / "member-status.json"),
        "report_files": files,
        "rebench_intake": intake_readback(),
        "extractbench": extractbench_readback(files["extractbench-schema-recovery"]),
        "software_reproduction_pool": {
            "new_rows": inserted,
            "capacity": pool.assess(current + inserted, excluded),
        },
        "verified_pairs": {
            "opentelemetry": otel["observations"],
            "braindrop": braindrop["observations"],
            "migrated": recovered["migrated"],
        },
        "diagnostic_only": {
            "pygls": {
                "category": pygls_detail["observer_category"],
                "last_required_test_retained_privately": bool(pygls_detail["last_required_test"]),
                "details": ref(PYGLS / "worker-diagnostic.json"),
            },
            "advanced_alchemy": {
                "required_test_count": alchemy["diagnostic"]["required_test_count"],
                "observed_status_count": alchemy["diagnostic"]["observed_status_count"],
                "mismatches_by_role": dict(
                    Counter(row["kind"] for row in alchemy["diagnostic"]["required_mismatches"])
                ),
                "protected_grade": None,
            },
            "conan": conan["observations"],
        },
        "settled_receipts": recovered,
        "settled_operations": len(receipts),
        "observed_total_seconds": sum(row["observed_seconds"] for row in receipts),
        "reserved_total_seconds": sum(row["reserved_seconds"] for row in receipts),
        "comparisons_paused": True,
        "waza_excluded": True,
        "model_turns": 0,
        "cash_usd": 0,
        "formal_cases_adopted": 0,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), sort_keys=True, indent=2, allow_nan=False))
