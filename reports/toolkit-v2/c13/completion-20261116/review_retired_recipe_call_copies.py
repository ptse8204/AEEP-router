"""Inventory retired synthetic recipe-call databases for an operator decision."""

import argparse
import json
import re
import runpy
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from stage_repository_transport import HERE, ROOT, digest, encode, read, write

RUN = ROOT / ".aeep/completion-20261116/selection-measurements-20261117"
SCRATCH = RUN / "pytest-tmp"
TEST_LOG_SHA = "f4fda4fb812f07e4d8db432f5843ccfcd8fe64f4a197220d764b11a28310e5e2"
HELPER = HERE.parent / (
    "skillsbench-software-substitute-20261109/managed-preparation/carrier-verification/"
    "cleanup-fixtures.py"
)
FIXTURES = ("test_reviewed_executable_recip0", "test_reviewed_diagnostics_surv0")
RECIPE_COPY = re.compile(r"recipe_call_[a-f0-9]{32}\.sqlite3")
MARKER = "Controlled fixture; not a real plugin benefit claim"
ALLOWANCE = 96 * 1024**2


def fixture_binding(path):
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        records = [
            json.loads(raw)
            for (raw,) in db.execute(
                "SELECT payload_json FROM assessment_records WHERE kind='recipe'"
            )
        ]
        (recipe,) = records
        if (
            recipe["recipe_id"] != "contained-list-count"
            or recipe["capability"] != "example.count@1"
            or recipe["generator"] != "contained_json:1"
            or recipe["grader"] != "contained_json:1"
            or db.execute("SELECT count(*) FROM assessment_operations").fetchone() != (0,)
            or db.execute("SELECT DISTINCT executor_id FROM receipts").fetchall()
            not in ([("grader",)], [("reference",)])
        ):
            raise ValueError("copy contains operations outside the synthetic recipe fixture")
        if db.execute("PRAGMA quick_check(1)").fetchone() != ("ok",):
            raise ValueError("copy failed its read-only integrity check")


def prepare():
    log = RUN / "pytest.log"
    if b"2181 passed, 21 skipped" not in read(log, TEST_LOG_SHA):
        raise ValueError("the completed pytest log differs")
    helper = runpy.run_path(str(HELPER))
    opened = helper["opened_files"]()
    preserved = {log}
    candidates = []
    for name in FIXTURES:
        fixture = SCRATCH / name
        marker = fixture / "plugin.txt"
        if marker.resolve() != marker or marker.read_text() != MARKER:
            raise ValueError("the selected fixture marker differs")
        preserved.add(marker)
        for plan in sorted((fixture / "assessment").glob("plan_*")):
            if not helper["PLAN_NAME"].fullmatch(plan.name):
                raise ValueError("unexpected test plan directory")
            primary = plan / "campaign.sqlite3"
            if primary.resolve() != primary or not primary.is_file():
                raise ValueError("the primary test campaign database is missing")
            helper["inactive"](primary, opened)
            preserved.add(primary)
            for path in sorted((plan / "recipe-operations").glob("recipe_call_*.sqlite3")):
                if not RECIPE_COPY.fullmatch(path.name) or path.resolve() != path:
                    raise ValueError("recipe copy path differs from the allowed fixture")
                helper["inactive"](path, opened)
                before = helper["metadata"](path, path.lstat())
                helper["check_snapshot"](path, {marker})
                fixture_binding(path)
                checksum = helper["sha"](path)
                if helper["metadata"](path, path.lstat()) != before:
                    raise ValueError("worker copy changed during the inventory")
                candidates.append(
                    {"path": path.relative_to(ROOT).as_posix(), "stat": before, "sha256": checksum}
                )
    preview = HERE / "supplementary-multifile-range-preview-20261124.json"
    needed = json.loads(preview.read_bytes())["minimum_prelaunch_free_bytes"]
    free = shutil.disk_usage(ROOT).free
    upper = sum(row["stat"][2] for row in candidates)
    stop_at = min(needed + ALLOWANCE, free + upper)
    if stop_at < needed or needed <= free or not candidates:
        raise ValueError("the proposed copies do not fit the current storage shortfall")
    return {
        "schema_version": "aeep.c13.retired-recipe-call-copy-review.v1",
        "driver_sha256": digest(Path(__file__).read_bytes()),
        "fixture_guard_sha256": digest(HELPER.read_bytes()),
        "completed_test_log_sha256": TEST_LOG_SHA,
        "root": str(SCRATCH.relative_to(ROOT)),
        "fixture_names": FIXTURES,
        "copy_count": len(candidates),
        "copies": candidates,
        "maximum_allocated_candidate_bytes": upper,
        "usable_bytes_at_preparation": free,
        "required_usable_bytes_for_supplementary_intake": needed,
        "target_usable_bytes": stop_at,
        "preserved": [
            {"path": path.relative_to(ROOT).as_posix(), "sha256": helper["sha"](path)}
            for path in sorted(preserved)
        ],
        "approval": "Pending exact operator decision for these recipe-call copies.",
        "actual_deletions": 0,
        "backup_changes": 0,
        "docker_changes": 0,
        "comparison_dispatch_paused": True,
        "waza_excluded": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    destination = args.output.resolve()
    if not __debug__ or not destination.is_relative_to(ROOT / ".aeep"):
        raise ValueError("review requires enabled checks and a private output path")
    print(write(destination, encode(prepare())))
