"""Pin an exact cleanup scope for verified copies from one completed pytest run."""

import argparse
import hashlib
import json
import os
import runpy
import shutil
import stat
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
LOGS = ROOT / ".aeep/stack-receipts-20261114"
SCRATCH = LOGS / "coverage-tmp"
HOME = ROOT / ".aeep/completion-20261116/retired-coverage-copies-20261119"
REVIEW = HOME / "operation-review.json"
APPROVAL = HOME / "approval.json"
STARTED = HOME / "started.json"
RESULT = HOME / "result.json"
GIB = 1024**3
FLOOR = 52 * GIB
MAX_ALLOCATED = 13 * GIB // 4
HELPER = HERE.parent / (
    "skillsbench-software-substitute-20261109/managed-preparation/carrier-verification/"
    "cleanup-fixtures.py"
)
FIXTURES = (
    "test_complete_assessment_admis0",
    "test_reviewed_executable_recip0",
    "test_calibrated_main_executes_0",
    "test_pilot_uses_campaign_but_c0",
    "test_search_workflow_assessmen0",
    "test_preview_matches_fresh_cam0",
    "test_completed_worker_exit_pre0",
    "test_other_families_run_throug1",
)
LOG_FILES = (
    "coverage-complete", "coverage-tests.log", "coverage.data", "coverage-report.log",
    "coverage.json", "critical-coverage.log", "assessment-coverage.log",
)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def record(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path)}


def put(path, data):
    with path.open("x") as stream:
        stream.write(json.dumps(data, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def regular(path):
    if path.resolve() != path or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("expected an unchanged regular path")


def check_path(path, helper):
    if (
        not path.is_relative_to(SCRATCH)
        or len(path.relative_to(SCRATCH).parts) != 5
        or path.relative_to(SCRATCH).parts[0] not in FIXTURES
        or path.parents[2].name != "assessment"
        or path.parent.name != "attempts"
        or not helper["PLAN_NAME"].fullmatch(path.parents[1].name)
        or not helper["DB_NAME"].fullmatch(path.name)
    ):
        raise ValueError("scope contains a file outside the selected test copies")
    regular(path)


def prepare():
    if SCRATCH.resolve() != SCRATCH or HOME.exists():
        raise ValueError("expected the original pytest scratch and a new review folder")
    if "2156 passed, 21 skipped" not in (LOGS / "coverage-tests.log").read_text():
        raise ValueError("the selected run lacks its expected terminal log")
    helper = runpy.run_path(str(HELPER))
    opened = helper["opened_files"]()
    preserved = {LOGS / name for name in LOG_FILES}
    records = []
    for fixture in FIXTURES:
        marker = SCRATCH / fixture / "plugin.txt"
        regular(marker)
        if marker.read_text() not in helper["MARKERS"]:
            raise ValueError("unexpected test fixture marker")
        preserved.add(marker)
        for path in sorted(marker.parent.glob("assessment/plan_*/attempts/worker_*.sqlite3")):
            check_path(path, helper)
            primary = path.parents[1] / "campaign.sqlite3"
            regular(primary)
            if primary not in preserved:
                helper["inactive"](primary, opened)
                preserved.add(primary)
            helper["inactive"](path, opened)
            before = helper["metadata"](path, path.lstat())
            helper["check_snapshot"](path, {marker})
            if helper["metadata"](path, path.lstat()) != before:
                raise ValueError("worker copy changed during inspection")
            records.append({"path": str(path.relative_to(ROOT)), "stat": before})
    if len({row["path"] for row in records}) != len(records):
        raise ValueError("scope repeats an identity")
    allocated = sum(row["stat"][2] for row in records)
    free = shutil.disk_usage(ROOT).free
    if not 0 < allocated <= MAX_ALLOCATED or free + allocated < FLOOR:
        raise ValueError("verified copies do not fit the reviewed reclaim envelope")
    for path in preserved:
        regular(path)
    scope = {
        "schema_version": "aeep.c13.retired-worker-copies.v1",
        "driver": record(Path(__file__).resolve()),
        "fixture_guard": record(HELPER),
        "run": str(LOGS.relative_to(ROOT)),
        "selected_fixtures": FIXTURES,
        "stop_at_usable_bytes": FLOOR,
        "usable_bytes_at_preparation": free,
        "maximum_allocated_candidate_bytes": allocated,
        "worker_copy_count": len(records),
        "records": records,
        "preserved_evidence": [record(path) for path in sorted(preserved)],
        "scope": "Only synthetic pytest worker SQLite copies. Preserve primary campaign databases, logs, backups, Docker resources and snapshots.",
        "no_automatic_retries": True,
        "models": 0,
        "cash_usd": 0,
        "comparisons_paused": True,
        "waza_excluded": True,
    }
    HOME.mkdir(mode=0o700)
    put(REVIEW, scope)
    print(json.dumps({"review_sha256": sha(REVIEW), "files": len(records), "allocated_bytes": allocated}))


def preserves(scope):
    for item in scope["preserved_evidence"]:
        path = ROOT / item["path"]
        regular(path)
        if sha(path) != item["sha256"]:
            return False
    return True


def execute(exact):
    if (
        not __debug__
        or HOME.resolve() != HOME
        or sha(REVIEW) != exact
        or STARTED.exists()
        or RESULT.exists()
        or json.loads(APPROVAL.read_bytes()) != {"approved": True, "review_sha256": exact}
    ):
        raise ValueError("an unstarted exact user approval is required")
    scope = json.loads(REVIEW.read_bytes())
    if (
        scope["driver"] != record(Path(__file__).resolve())
        or scope["fixture_guard"] != record(HELPER)
        or scope["stop_at_usable_bytes"] != FLOOR
        or scope["worker_copy_count"] != len(scope["records"])
        or sum(row["stat"][2] for row in scope["records"]) != scope["maximum_allocated_candidate_bytes"]
        or scope["maximum_allocated_candidate_bytes"] > MAX_ALLOCATED
        or not preserves(scope)
    ):
        raise ValueError("approved pins or preserved evidence differ")
    helper = runpy.run_path(str(HELPER))
    opened = helper["opened_files"]()
    for row in scope["records"]:
        path = ROOT / row["path"]
        check_path(path, helper)
        helper["inactive"](path, opened)
        if helper["metadata"](path, path.lstat()) != row["stat"]:
            raise ValueError("reviewed copy changed before cleanup")
    before = shutil.disk_usage(ROOT).free
    put(STARTED, {"review_sha256": exact, "free_before_bytes": before})
    removed = []
    used = 0
    completed = False
    try:
        for row in scope["records"]:
            if shutil.disk_usage(ROOT).free >= FLOOR:
                break
            path = ROOT / row["path"]
            check_path(path, helper)
            helper["inactive"](path, opened)
            fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                current = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
                if helper["metadata"](path, current) != row["stat"]:
                    raise ValueError("reviewed file identity changed")
                os.unlink(path.name, dir_fd=fd)
            finally:
                os.close(fd)
            used += current.st_blocks * 512
            removed.append(row["path"])
        completed = True
    finally:
        after = shutil.disk_usage(ROOT).free
        intact = preserves(scope)
        put(RESULT, {
            "review_sha256": exact,
            "finished_without_error": completed,
            "removed": removed,
            "allocated_bytes_removed": used,
            "free_before_bytes": before,
            "free_after_bytes": after,
            "observed_free_change_bytes": after - before,
            "floor_reached": after >= FLOOR,
            "preserved_evidence_verified": intact,
        })
        if not intact:
            raise ValueError("preservation check failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--execute-approved")
    args = parser.parse_args()
    if args.prepare and __debug__:
        prepare()
    elif args.execute_approved:
        execute(args.execute_approved)
    else:
        raise ValueError("fixture guards require enabled assertions")


if __name__ == "__main__":
    main()
