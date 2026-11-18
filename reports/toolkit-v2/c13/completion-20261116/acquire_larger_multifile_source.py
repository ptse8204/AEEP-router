"""Bind the first larger multi-file lead to the existing archive intake."""

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import acquire_repository_expansion as intake
from audit_larger_multifile_leads import audit, long_suite
from plan_repository_expansion import UNION
from screen_candidate_patches import ROW_KEYS
from stage_repository_transport import HERE, ROOT, WORK, digest, encode, read, write

CASE = "litestar-org__advanced-alchemy-673_interface"
REPORT = HERE / "larger-multifile-intake-20261118.json"
REPORT_PIN = "27ce6f132f298c61a5fff85d9a8f8056d4ee454f514756d0992b5bd3dea16280"
AUTHORITY = HERE.parent / "pipeline-standing-authority-20261104.json"
SCOPE = WORK / "larger-multifile-source-20261118"


def binding(path):
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path.read_bytes())}


def definition():
    facts = json.loads(read(REPORT, REPORT_PIN))
    checked, leads = audit()
    if any(facts[key] != value for key, value in checked.items()):
        raise ValueError("larger multi-file intake differs from the retained audit")
    (lead,) = [item for item in leads if item["case_id"] == CASE]
    repo, revision = lead["repository"], lead["revision"]
    if facts["publisher_metadata"]["first_archive_review_candidate"] != repo:
        raise ValueError("source does not match the retained intake priority")
    union = json.loads(read(UNION, checked["publisher_manifest_sha256"]))
    matches = []
    for page in union["sources"]:
        payload = json.loads(read(ROOT / page["private_cache"], page["sha256"]))
        matches.extend(entry for entry in payload["rows"] if entry["row"]["instance_id"] == CASE)
    (match,) = matches
    row = match["row"]
    (meta,) = [
        item
        for item in facts["publisher_metadata"]["projects"]
        if item["repository"] == repo and item["revision"] == revision
    ]
    for file in meta["files"]:
        read(ROOT / file["path"], file["sha256"])
    if (
        match["truncated_cells"]
        or digest(encode(row)) != lead["row_sha256"]
        or long_suite(row) is None
        or len(row["FAIL_TO_PASS"]) != 3
        or len(row["PASS_TO_PASS"]) != 171
    ):
        raise ValueError("the exact larger suite or test identities changed")
    source = {
        "case_id": CASE,
        "repository": repo,
        "revision": revision,
        "intent": "multi-file-repair",
        "archive_url": f"https://codeload.github.com/{repo}/tar.gz/{revision}",
        "commit_url": f"https://api.github.com/repos/{repo}/git/commits/{revision}",
        "publisher_metadata": meta["files"],
        "retained_row_sha256": lead["row_sha256"],
        "required_tests": 174,
    }
    semantic_pin = digest(json.dumps({key: row[key] for key in ROW_KEYS}, sort_keys=True).encode())
    files = (
        Path(__file__),
        HERE / "acquire_repository_expansion.py",
        HERE / "audit_larger_multifile_leads.py",
        HERE / "reacquire_repository_sources.py",
        HERE / "rebind_cached_repository_sources.py",
        HERE / "screen_candidate_patches.py",
        HERE / "stage_repository_transport.py",
    )
    return (
        {
            "schema_version": "aeep.c13.larger-multifile-source-acquisition.v1",
            "sources": [source],
            "intake_audit": binding(REPORT),
            "driver_bindings": [binding(path) for path in files],
            "maximum_archive_requests": 1,
            "maximum_archive_bytes_each": intake.ARCHIVE_BOUND,
            "maximum_archive_response_bytes": intake.ARCHIVE_BOUND,
            "maximum_commit_metadata_requests": 1,
            "maximum_commit_metadata_response_bytes": intake.COMMIT_METADATA_LIMIT + 1,
            "minimum_host_free_bytes": intake.RESERVE + intake.ARCHIVE_BOUND,
            "retries": 0,
            "upstream_tests": 0,
            "installs": 0,
            "models": 0,
            "cash_usd": 0,
            "provider_disclosure": False,
            "formal_adoption": False,
            "delegated_authority": binding(AUTHORITY),
            "comparisons_paused": True,
            "waza_excluded": True,
        },
        {CASE: lead | {"metadata_semantic_sha256": semantic_pin}},
        {CASE: row},
    )


def configure():
    intake.TARGET = SCOPE / "execution"
    intake.REVIEW = SCOPE / "operation-review.json"
    intake.APPROVAL = SCOPE / "approval.json"
    intake.definition = definition


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--exact-review")
    args = parser.parse_args()
    configure()
    if args.prepare:
        review, _, _ = definition()
        SCOPE.mkdir(mode=0o700)
        review["expires_at"] = (datetime.now(UTC) + timedelta(days=7)).isoformat()
        print(write(intake.REVIEW, encode(review))["sha256"])
    else:
        print(json.dumps(intake.run(args.exact_review), indent=2))


if __name__ == "__main__":
    main()
