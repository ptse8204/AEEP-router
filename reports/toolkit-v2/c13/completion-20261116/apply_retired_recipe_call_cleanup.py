"""Apply the reviewed synthetic snapshot cleanup after an exact operator approval."""

import argparse
import hashlib
import json
import os
import runpy
import shutil

from review_retired_recipe_call_copies import FIXTURES, HELPER, RECIPE_COPY, SCRATCH
from stage_repository_transport import HERE, ROOT, digest, encode, read, write

WORK = ROOT / ".aeep/c13-cohort-runtime-20261124"
REVIEW = WORK / "retired-recipe-call-copy-review-20261124.json"
APPROVAL = WORK / "retired-recipe-call-copy-cleanup-approval-20261124.json"
EXECUTION = WORK / "retired-recipe-call-cleanup-execution-20261124"
HANDOFF = HERE / "retired-recipe-call-storage-handoff-20261124.json"


def allowed_copy(path, helper):
    fields = path.relative_to(SCRATCH).parts
    if (
        len(fields) != 5
        or fields[0] not in FIXTURES
        or fields[1] != "assessment"
        or helper["PLAN_NAME"].fullmatch(fields[2]) is None
        or fields[3] != "recipe-operations"
        or RECIPE_COPY.fullmatch(fields[4]) is None
        or path.resolve() != path
    ):
        raise ValueError("path leaves the exact retired recipe-call fixture scope")


def preserved(scope):
    for row in scope["preserved"]:
        read(ROOT / row["path"], row["sha256"])


def check_copy(row, helper, opened):
    path = ROOT / row["path"]
    allowed_copy(path, helper)
    helper["inactive"](path, opened)
    if helper["metadata"](path, path.lstat()) != row["stat"]:
        raise ValueError("reviewed copy identity drifted")
    return path


def unlink_copy(path, row, helper):
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        with os.fdopen(fd, "rb") as stream:
            before = helper["metadata"](path, os.fstat(stream.fileno()))
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
            current = helper["metadata"](
                path, os.stat(path.name, dir_fd=directory, follow_symlinks=False)
            )
            if before != row["stat"] or current != before or checksum != row["sha256"]:
                raise ValueError("reviewed copy changed before removal")
            os.unlink(path.name, dir_fd=directory)
    finally:
        os.close(directory)


def log_event(journal, value):
    journal.write(json.dumps(value, separators=(",", ":")) + "\n")
    journal.flush()
    os.fsync(journal.fileno())


def execute(exact):
    if not __debug__ or EXECUTION.resolve() != EXECUTION or EXECUTION.exists():
        raise ValueError("cleanup requires an unstarted exact review with fixture checks enabled")
    handoff = json.loads(HANDOFF.read_bytes())
    raw = read(REVIEW, exact)
    if (
        handoff["review"]["sha256"] != exact
        or handoff["review"]["path"] != REVIEW.relative_to(ROOT).as_posix()
        or not APPROVAL.is_file()
        or APPROVAL.resolve() != APPROVAL
        or json.loads(APPROVAL.read_bytes()) != {"approved": True, "review_sha256": exact}
    ):
        raise ValueError("operator approval for the exact cleanup review is required")
    scope = json.loads(raw)
    rows = scope["copies"]
    if (
        scope["schema_version"] != "aeep.c13.retired-recipe-call-copy-review.v1"
        or scope["root"] != SCRATCH.relative_to(ROOT).as_posix()
        or tuple(scope["fixture_names"]) != FIXTURES
        or scope["copy_count"] != len(rows)
        or len({row["path"] for row in rows}) != len(rows)
        or not rows
        or sum(row["stat"][2] for row in rows) != scope["maximum_allocated_candidate_bytes"]
        or scope["maximum_allocated_candidate_bytes"] != handoff["maximum_allocated_bytes"]
        or scope["target_usable_bytes"] != handoff["target_usable_bytes"]
        or scope["required_usable_bytes_for_supplementary_intake"]
        != handoff["required_usable_bytes"]
        or scope["driver_sha256"]
        != digest((HERE / "review_retired_recipe_call_copies.py").read_bytes())
        or scope["fixture_guard_sha256"] != digest(HELPER.read_bytes())
    ):
        raise ValueError("cleanup scope or reviewed files changed")
    preserved(scope)
    helper = runpy.run_path(str(HELPER))
    opened = helper["opened_files"]()
    for row in rows:
        check_copy(row, helper, opened)
    before = shutil.disk_usage(ROOT).free
    stop_at = scope["target_usable_bytes"]
    EXECUTION.mkdir(mode=0o700)
    write(EXECUTION / "started.json", encode({"review_sha256": exact, "free_before_bytes": before}))
    removed = []
    finished = False
    dirname = None
    try:
        with (EXECUTION / "events.jsonl").open("x", encoding="utf-8") as journal:
            for row in rows:
                if (
                    before >= scope["required_usable_bytes_for_supplementary_intake"]
                    or shutil.disk_usage(ROOT).free >= stop_at
                ):
                    break
                parent = (ROOT / row["path"]).parent
                if parent != dirname:
                    opened = helper["opened_files"]()
                    dirname = parent
                path = check_copy(row, helper, opened)
                log_event(journal, {"stage": "before_unlink", **row})
                unlink_copy(path, row, helper)
                removed.append(row)
                log_event(journal, {"stage": "unlinked", "path": row["path"]})
        finished = True
    finally:
        intact = False
        try:
            preserved(scope)
            intact = True
        finally:
            after = shutil.disk_usage(ROOT).free
            write(
                EXECUTION / "result.json",
                encode(
                    {
                        "review_sha256": exact,
                        "finished_without_error": finished,
                        "removed_count": len(removed),
                        "removed_allocated_bytes": sum(row["stat"][2] for row in removed),
                        "before_bytes": before,
                        "after_bytes": after,
                        "observed_free_change_bytes": after - before,
                        "target_reached": after >= stop_at,
                        "intake_storage_requirement_met": (
                            after >= scope["required_usable_bytes_for_supplementary_intake"]
                        ),
                        "preserved_files_verified": intact,
                    }
                ),
            )
    return EXECUTION / "result.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-approved", required=True)
    args = parser.parse_args()
    print(execute(args.execute_approved))
