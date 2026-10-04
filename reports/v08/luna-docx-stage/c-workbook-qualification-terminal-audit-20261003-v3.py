"""Read-only, content-free terminal audit for the frozen C qualification."""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
STAGE = Path(__file__).resolve().parent
PLAN = "plan_143001e5f4be4fd9b17f78d797340b70"
JOB = "assessment_a9369479529649cdab7a21b971dbabbc"
REVIEW = STAGE / "c-workbook-qualification-execution-review-20261003-v3.json"
REVIEW_SHA = "08cf5715c2d8dc8548d4f0f9efbbc27ffc3dc1d6a6c8db412fa0ec52756087d1"
RESULT = STAGE / "c-workbook-qualification-result-20261003-v3.json"
CANONICAL = ROOT / ".aeep/live-review-v3/aeep.sqlite3"
MANIFEST = ROOT / ".aeep/live-review-v3/aeep.json"
CAMPAIGN = ROOT / ".aeep/live-review-v3/.aeep/assessments" / PLAN / "campaign.sqlite3"
OUTPUT = STAGE / "c-workbook-qualification-terminal-audit-20261003-v3.json"
SPLITS = {"qualification": 8, "training": 28, "holdout": 105}
TIMEOUT_FLOORS = {"training": 1, "holdout": 4}


class NotTerminal(RuntimeError):
    pass


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def metadata(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise NotTerminal(f"missing metadata: {path.name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise NotTerminal(f"invalid metadata object: {path.name}")
    return value


def db_ro(path: Path) -> sqlite3.Connection:
    if path.is_symlink() or not path.is_file():
        raise NotTerminal(f"missing database: {path}")
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def trial_outcome(row: sqlite3.Row) -> str:
    category, error = str(row["failure_category"] or "").lower(), str(row["error_type"] or "").lower()
    if row["state"] == "running": return "running"
    if row["status"] == "timeout" or category == "timeout" or "timeout" in error: return "timeout"
    if row["correctness_failed"] in (1, True): return "correctness_failed"
    if row["state"] == "skipped": return "skipped"
    if row["state"] == "complete" and row["ok"] in (1, True) and row["valid"] in (1, True) and row["correctness_failed"] in (0, False, None): return "passed"
    if row["state"] == "failed" or category or row["error_type"]: return "failed"
    return "unknown"


def write_once(path: Path, data: dict[str, Any]) -> None:
    if path.exists(): raise FileExistsError(f"refusing to overwrite {path.name}")
    temp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        if path.exists(): raise FileExistsError(f"refusing to overwrite {path.name}")
        temp.replace(path)
    finally:
        if temp.exists(): temp.unlink()


def main() -> int:
    if OUTPUT.exists(): raise NotTerminal(f"audit already exists: {OUTPUT.name}")
    review, result = metadata(REVIEW), metadata(RESULT)
    review_sha = sha(REVIEW)
    if review_sha != REVIEW_SHA: raise NotTerminal("review differs from frozen execution review")
    if result.get("status") not in {"passed", "failed"} or result.get("qualification_completed") is not True:
        raise NotTerminal("runner result is not terminal")
    if any(result.get(key) != expected for key, expected in
           (("plan_id", PLAN), ("assessment_id", JOB), ("review_sha256", review_sha))):
        raise NotTerminal("runner result is not bound to the selected job, plan, and review")

    pin, stat = review["canonical_store"], CANONICAL.stat()
    if (str(CANONICAL) != pin["database"] or stat.st_dev != pin["device"] or stat.st_ino != pin["inode"]
            or str(MANIFEST) != pin["manifest"] or sha(MANIFEST) != pin["manifest_sha256"]):
        raise NotTerminal("canonical database/manifest identity differs from the reviewed pin")

    with db_ro(CANONICAL) as db:
        jobs = db.execute("SELECT id,state,report_id,error_code FROM assessment_jobs WHERE plan_id=?", (PLAN,)).fetchall()
        if len(jobs) != 1 or jobs[0]["id"] != JOB or jobs[0]["state"] != "complete" or not jobs[0]["report_id"]:
            raise NotTerminal("selected canonical assessment job is absent or nonterminal")
        job = jobs[0]
        plan = db.execute(
            "SELECT digest,json_extract(payload_json,'$.candidate_id') candidate,"
            "json_extract(payload_json,'$.baseline_id') baseline,"
            "json_extract(payload_json,'$.authorization_id') authorization,"
            "json_extract(payload_json,'$.recipe_case_set_digest') case_set,"
            "json_extract(payload_json,'$.suite.suite_id') suite,"
            "json_array_length(payload_json,'$.suite.cases') case_count "
            "FROM assessment_records WHERE kind='plan' AND id=?", (PLAN,)).fetchone()
        if plan is None: raise NotTerminal("selected plan record is missing")
        case_rows = db.execute(
            "SELECT json_extract(c.value,'$.case_id') id,json_extract(c.value,'$.split') split "
            "FROM assessment_records p,json_each(p.payload_json,'$.suite.cases') c "
            "WHERE p.kind='plan' AND p.id=?", (PLAN,)).fetchall()
        case_split = {row["id"]: row["split"] for row in case_rows}
        report = db.execute(
            "SELECT digest,json_extract(payload_json,'$.report_id') report_id,"
            "json_extract(payload_json,'$.plan_digest') plan_digest,"
            "json_extract(payload_json,'$.campaign_digest') campaign_digest,"
            "json_extract(payload_json,'$.operation_ledger_digest') ledger_digest,"
            "json_extract(payload_json,'$.grader_validation_digest') grader_digest,"
            "json_extract(payload_json,'$.outcome') outcome,"
            "json_extract(payload_json,'$.qualification_passed') passed,"
            "json_extract(payload_json,'$.correctness_failures') correctness_failures,"
            "json_extract(payload_json,'$.execution_failures') execution_failures,"
            "json_extract(payload_json,'$.measurement_coverage') coverage "
            "FROM assessment_records WHERE kind='report' AND id=?", (job["report_id"],)).fetchone()
        if (report is None or report["plan_digest"] != plan["digest"]
                or result.get("report_id") != report["report_id"]
                or result.get("plan_digest") != plan["digest"]
                or result.get("case_set_digest") != plan["case_set"]):
            raise NotTerminal("canonical report does not match the selected plan and runner result")
        campaign_record = db.execute(
            "SELECT json_extract(payload_json,'$.suite_id') suite,"
            "json_array_length(payload_json,'$.trials') trials FROM assessment_records "
            "WHERE kind='campaign' AND digest=?", (report["campaign_digest"],)).fetchone()
        if campaign_record is None: raise NotTerminal("canonical campaign record is missing")
        ledger = db.execute("SELECT json_array_length(payload_json,'$.operations') n FROM assessment_records "
                            "WHERE kind='operation_ledger' AND digest=?", (report["ledger_digest"],)).fetchone() if report["ledger_digest"] else None
        grader = db.execute("SELECT id FROM assessment_records WHERE kind='grader_validation' AND digest=?",
                            (report["grader_digest"],)).fetchone() if report["grader_digest"] else None
        ops = db.execute(
            "SELECT s.id,json_extract(s.payload_json,'$.stage') stage,"
            "json_extract(s.payload_json,'$.reserved.max_elapsed_seconds') reserved_seconds,"
            "json_extract(s.payload_json,'$.reserved.max_operations') reserved_operations,"
            "o.grant_id,o.state,json_extract(m.payload_json,'$.elapsed_seconds') elapsed,"
            "json_type(m.payload_json,'$.resources') resources "
            "FROM assessment_records s LEFT JOIN assessment_operations o ON o.id=s.id "
            "LEFT JOIN assessment_records m ON m.kind='operation_measurement' AND m.id=s.id "
            "WHERE s.kind='operation_start' AND json_extract(s.payload_json,'$.plan_id')=?", (PLAN,)).fetchall()
        reservations = db.execute(
            "SELECT json_extract(s.payload_json,'$.plan_id') plan_id,COUNT(*) n "
            "FROM assessment_operations o LEFT JOIN assessment_records s ON s.kind='operation_start' AND s.id=o.id "
            "WHERE o.grant_id='onboarding' AND o.state='reserved' "
            "GROUP BY json_extract(s.payload_json,'$.plan_id')").fetchall()
        markers = db.execute("SELECT COUNT(*) FROM assessment_admissions WHERE executor_id=?", (plan["candidate"],)).fetchone()[0]
        admissions = db.execute("SELECT COUNT(*) FROM assessment_records WHERE kind='admission' "
                                 "AND json_extract(payload_json,'$.executor_id')=?", (plan["candidate"],)).fetchone()[0]
        auth = db.execute("SELECT json_extract(payload_json,'$.automatic_admission') enabled FROM assessment_records "
                          "WHERE kind='authorization' AND id=?", (plan["authorization"],)).fetchone()

    with db_ro(CAMPAIGN) as db:
        if db.execute("SELECT 1 FROM suites WHERE suite_id=?", (plan["suite"],)).fetchone() is None:
            raise NotTerminal("selected suite is absent from campaign database")
        trials = db.execute(
            "SELECT trial_id,state,json_extract(payload_json,'$.case_id') case_id,"
            "json_extract(payload_json,'$.status') status,json_extract(payload_json,'$.ok') ok,"
            "json_extract(payload_json,'$.valid') valid,json_extract(payload_json,'$.correctness_failed') correctness_failed,"
            "json_extract(payload_json,'$.error_type') error_type,json_extract(payload_json,'$.failure_category') failure_category,"
            "json_extract(payload_json,'$.model_usage_complete') usage_complete,"
            "json_extract(payload_json,'$.operation_count') operation_count FROM trials WHERE suite_id=?",
            (plan["suite"],)).fetchall()

    outcomes = {split: Counter() for split in SPLITS}
    states, timeouts, seen_cases, seen_ids = Counter(), Counter(), set(), set()
    usage_count = operation_count = invalid_refs = 0
    for row in trials:
        split = case_split.get(row["case_id"])
        if split not in SPLITS: invalid_refs += 1; split = "unknown"
        else: seen_cases.add(row["case_id"])
        if row["trial_id"]: seen_ids.add(row["trial_id"])
        states[str(row["state"] or "unknown")] += 1
        label = trial_outcome(row)
        if split in outcomes: outcomes[split][label] += 1
        if label == "timeout": timeouts[split] += 1
        usage_count += row["usage_complete"] in (1, True)
        if isinstance(row["operation_count"], int) and row["operation_count"] >= 0:
            operation_count += row["operation_count"]
    totals = {s: sum(outcomes[s].values()) for s in SPLITS}
    timeout_counts = {s: timeouts[s] for s in SPLITS}
    timeout_floor = all(timeouts[s] >= n for s, n in TIMEOUT_FLOORS.items())
    if (len(trials) != 141 or len(seen_ids) != 141 or len(case_split) != 141 or seen_cases != set(case_split)
            or invalid_refs or states["running"] or totals != SPLITS or campaign_record["trials"] != 141):
        raise NotTerminal("campaign does not contain 141 terminal trials matching the frozen 8/28/105 split plan")

    by_stage, op_by_id, unsettled = defaultdict(lambda: {"count": 0, "states": Counter(), "measured": 0,
        "unmeasured": 0, "elapsed_total": 0.0, "resource_vectors": 0}), {}, 0
    for row in ops:
        bucket = by_stage[str(row["stage"] or "unknown")]
        state, elapsed = str(row["state"] or "missing_operation_row"), row["elapsed"]
        measured = isinstance(elapsed, (int, float)) and not isinstance(elapsed, bool) and math.isfinite(float(elapsed)) and elapsed >= 0
        bucket["count"] += 1; bucket["states"][state] += 1
        bucket["measured"] += measured; bucket["unmeasured"] += not measured
        bucket["resource_vectors"] += row["resources"] == "object"
        if measured: bucket["elapsed_total"] += float(elapsed)
        unsettled += state != "complete" or not measured
        op_by_id[row["id"]] = row
    stage_totals = {s: {"count": b["count"], "states": dict(b["states"]), "measured": b["measured"],
        "unmeasured": b["unmeasured"], "elapsed_seconds_total": round(b["elapsed_total"], 6),
        "resource_vectors_present": b["resource_vectors"]} for s, b in sorted(by_stage.items())}
    setup = {}
    setup_ids = {**review["operation_ids"], "scope_preparation": f"{PLAN}:workbook-task-scope-preparation-v1"}
    for label, op_id in setup_ids.items():
        row = op_by_id.get(op_id)
        setup[label] = {"operation_id": op_id, "present": row is not None}
        if row is not None:
            setup[label].update({"stage": row["stage"], "grant_id": row["grant_id"], "state": row["state"],
                "elapsed_seconds": row["elapsed"], "reserved_max_elapsed_seconds": row["reserved_seconds"],
                "reserved_max_operations": row["reserved_operations"]})
    reserved_by_plan = {row["plan_id"] or "unlinked_or_legacy": row["n"] for row in reservations}
    other_reserved = sum(n for pid, n in reserved_by_plan.items() if pid != PLAN)
    scope = {"present": False}
    scope_path = STAGE / "c-workbook-qualification-scopes-20261003-v3.json"
    if scope_path.is_file() and not scope_path.is_symlink():
        index = metadata(scope_path)
        scope = {"present": True, "sha256": sha(scope_path), "plan_id_matches": index.get("plan_id") == PLAN,
                 "digest_matches_result": index.get("scope_index_digest") == result.get("scope_index_digest"),
                 "scope_count": index.get("scope_count"), "operation_id": index.get("operation_id")}

    passed = report["passed"] in (1, True)
    admission_absent = markers == 0 and admissions == 0
    runner_agrees = result.get("outcome") == report["outcome"] and result.get("qualification_passed") is passed
    coverage = json.loads(report["coverage"]) if report["coverage"] else None
    whole_cost = result.get("whole_system_cost_complete") is True
    gaps = []
    if not timeout_floor: gaps.append("predeclared timeout floor was not independently met")
    if timeout_floor and passed: gaps.append("canonical report passes despite the predeclared timeout failure floor")
    if not runner_agrees: gaps.append("runner result disagrees with the canonical report")
    if campaign_record["suite"] != plan["suite"]: gaps.append("campaign record suite differs from the plan")
    if unsettled: gaps.append("selected-plan operations include unsettled or unmeasured records")
    if not admission_absent or result.get("candidate_admission_unchanged") is not True:
        gaps.append("admission exists after the run or runner unchanged assertion is absent")
    if review.get("admission") is not False or auth is None or auth["enabled"] not in (0, False):
        gaps.append("review/authorization does not establish disabled admission")
    if not result.get("coordinator_closed"): gaps.append("runner did not report coordinator closure")
    if result.get("capacity_snapshot", {}).get("owned_worker_cleanup_confirmed") is not True:
        gaps.append("runner did not report owned capacity-worker cleanup")
    if not scope.get("present") or not scope.get("digest_matches_result"):
        gaps.append("scope-index binding/cleanup metadata is missing or mismatched")
    gaps.append("no retained pre-run admission-row snapshot; a change cannot be independently reconstructed")
    gaps.append("proxy stopped state and host-worker cleanup require separate read-only Docker/host verification")
    gaps.append("whole-system cost completeness remains unproven; preserve the report coverage map as authoritative")

    audit = {
        "schema_version": "aeep.c-workbook-qualification-terminal-audit.v1",
        "audited_at_utc": datetime.now(UTC).isoformat(),
        "audit_status": "terminal_metadata_reconciled_with_open_gaps",
        "identity": {"plan_id": PLAN, "assessment_id": JOB, "plan_digest": plan["digest"],
            "case_set_digest": plan["case_set"], "candidate_id": plan["candidate"], "baseline_id": plan["baseline"],
            "review_sha256": review_sha, "result_sha256": sha(RESULT)},
        "canonical": {"job_state": job["state"], "report_id": job["report_id"], "report_digest": report["digest"],
            "outcome": report["outcome"], "qualification_passed": passed, "correctness_failures": report["correctness_failures"],
            "execution_failures": report["execution_failures"], "campaign_digest": report["campaign_digest"],
            "campaign_trial_count": campaign_record["trials"], "operation_ledger_count": ledger["n"] if ledger else None,
            "grader_validation_present": grader is not None, "measurement_coverage": coverage},
        "qualification": {"runner_status": result["status"], "campaign_trial_count": len(trials),
            "trial_state_counts": dict(states), "split_totals": totals,
            "outcomes_by_split": {s: dict(outcomes[s]) for s in SPLITS}, "timeouts_by_split": timeout_counts,
            "predeclared_timeout_floor_met": timeout_floor, "qualification_must_remain_failed": timeout_floor,
            "value_admission_and_normal_worker_setup_allowed": False,
            "model_usage_complete_trials": usage_count, "trial_operation_count_total": operation_count},
        "accounting": {"selected_plan_operation_count": len(ops), "unsettled_or_unmeasured": unsettled,
            "operation_totals_by_stage": stage_totals, "reviewed_setup_operations": setup,
            "reserved_by_plan_id": reserved_by_plan, "selected_plan_reserved": reserved_by_plan.get(PLAN, 0),
            "other_or_unlinked_reserved": other_reserved, "whole_system_cost_complete": whole_cost},
        "admission": {"review_disables_admission": review.get("admission") is False,
            "authorization_disables_automatic_admission": auth is not None and auth["enabled"] in (0, False),
            "runner_asserted_unchanged": result.get("candidate_admission_unchanged") is True,
            "candidate_marker_count_after": markers, "candidate_record_count_after": admissions,
            "no_candidate_admission_observed_after": admission_absent, "pre_run_snapshot_available": False},
        "cleanup": {"runner_proxy_restored_claim": result.get("proxy_restored"),
            "runner_proxy_cleanup_accounting_claim": result.get("proxy_cleanup_accounting_complete"),
            "runner_coordinator_closed_claim": result.get("coordinator_closed"),
            "runner_owned_capacity_worker_cleanup_claim": result.get("capacity_snapshot", {}).get("owned_worker_cleanup_confirmed"),
            "scope_index": scope, "proxy_stopped_state": "not checked here; parent performs read-only Docker inspection",
            "host_worker_process_state": "not independently checked here"},
        "read_method": {"database_mode": "SQLite URI mode=ro", "selected_metadata_only": True,
            "task_input_output_answer_receipt_or_auth_read_or_emitted": False, "canonical_state_mutated": False,
            "Docker_or_live_trial_commands_run": False},
        "gaps": gaps,
    }
    write_once(OUTPUT, audit)
    print(json.dumps({"audit_status": audit["audit_status"], "report_outcome": report["outcome"],
        "qualification_passed": passed, "timeouts_by_split": timeout_counts, "plan_operations": len(ops),
        "unsettled_operations": unsettled, "other_or_unlinked_reserved": other_reserved,
        "downstream_value_admission_worker_setup_allowed": False, "audit_path": str(OUTPUT.relative_to(ROOT))}, sort_keys=True))
    return 0 if not gaps else 2


if __name__ == "__main__":
    try: raise SystemExit(main())
    except NotTerminal as exc: raise SystemExit(f"audit not emitted: {exc}") from exc
