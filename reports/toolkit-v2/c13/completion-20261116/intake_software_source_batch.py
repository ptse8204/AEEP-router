"""Stage fresh C13 source families via the existing reviewed acquisition path."""

import argparse
import json
from datetime import UTC, datetime, timedelta

import acquire_repository_expansion as acquisition
from plan_repository_expansion import previous_repositories
from stage_repository_transport import HERE, ROOT, digest, encode, read, write

WORK = ROOT / ".aeep/c13-cohort-runtime-20261124"
INVENTORY = HERE / "software-inventory-with-nested-pandas-20261124.json"
PRIOR_INTAKE = HERE / "scientific-python-source-intake-20261124.json"
QUEUE = acquisition.QUEUE


def definition(selected):
    summary = acquisition.load(QUEUE / "summary.json")
    leads = {
        row["case_id"]: row
        for row in json.loads(read(ROOT / summary["leads"]["path"], summary["leads"]["sha256"]))
    }
    rows = json.loads(read(ROOT / summary["rows"]["path"], summary["rows"]["sha256"]))
    already_seen = set.union(*previous_repositories())
    already_seen.update(row["repository"] for row in acquisition.load(INVENTORY)["rows"])
    already_seen.update(row["repository"] for row in acquisition.load(PRIOR_INTAKE)["cases"])
    already_seen.update(
        row["repository"] for row in acquisition.load(QUEUE / "publisher-metadata.json")["rows"]
    )
    if not 1 <= len(selected) <= 6:
        raise ValueError("the first source intake is scoped to at most six publisher families")
    records = []
    for case, intent in sorted(selected.items()):
        lead = leads[case]
        source = rows[case]
        repo, revision = lead["repository"], lead["revision"]
        if (
            intent not in {"audit", "multi-file-repair"}
            or repo in already_seen
            or source["repo"].casefold() != repo
            or source["base_commit"] != revision
            or digest(encode(source)) != lead["row_sha256"]
        ):
            raise ValueError("publisher or source pin is outside the fresh selection")
        already_seen.add(repo)
        records.append(
            {
                "case_id": case,
                "repository": repo,
                "revision": revision,
                "intent": intent,
                "archive_url": f"https://codeload.github.com/{repo}/tar.gz/{revision}",
                "commit_url": f"https://api.github.com/repos/{repo}/git/commits/{revision}",
                "dataset_row_sha256": lead["row_sha256"],
            }
        )
    definition = {
        "schema_version": "aeep.c13.first-public-source-intake.v1",
        "sources": records,
        "retained_queue_summary_sha256": digest((QUEUE / "summary.json").read_bytes()),
        "software_inventory_sha256": digest(INVENTORY.read_bytes()),
        "prior_intake_sha256": digest(PRIOR_INTAKE.read_bytes()),
        "drivers": {
            file.name: digest(file.read_bytes())
            for file in (
                HERE / "acquire_repository_expansion.py",
                HERE / "intake_software_source_batch.py",
            )
        },
        "maximum_archive_requests": len(records),
        "maximum_archive_response_bytes": len(records) * acquisition.ARCHIVE_BOUND,
        "maximum_commit_metadata_requests": len(records),
        "maximum_commit_metadata_response_bytes": len(records)
        * (acquisition.COMMIT_METADATA_LIMIT + 1),
        "retries": 0,
        "upstream_tests": 0,
        "models": 0,
        "cash_usd": 0,
        "provider_disclosure": False,
        "authority": "First bounded public source intake under the C13 engineering delegation.",
    }
    return definition, leads, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch")
    parser.add_argument("--audit", action="append", default=[])
    parser.add_argument("--repair", action="append", default=[])
    parser.add_argument("--execute")
    args = parser.parse_args()
    if not args.batch.isascii() or not args.batch.replace("-", "").isalnum():
        parser.error("batch must be a private directory name")
    folder = WORK / args.batch
    acquisition.TARGET = folder / "intake"
    acquisition.REVIEW = folder / "review.json"
    acquisition.APPROVAL = folder / "scope.json"
    acquisition.RESERVE = 50 * 1024**3
    if args.execute:
        record = json.loads(read(acquisition.REVIEW, args.execute))
        selected = {entry["case_id"]: entry["intent"] for entry in record["sources"]}
        acquisition.definition = lambda: definition(selected)
        write(acquisition.APPROVAL, encode({"approved": True, "review_sha256": args.execute}))
        report = acquisition.run(args.execute)
        print(json.dumps({k: v for k, v in report.items() if k != "observations"}))
    else:
        selected = {case: "audit" for case in args.audit} | {
            case: "multi-file-repair" for case in args.repair
        }
        if len(selected) != len(args.audit) + len(args.repair):
            parser.error("select each exact case once")
        payload, _, _ = definition(selected)
        folder.mkdir(mode=0o700)
        expiration = (datetime.now(UTC) + timedelta(hours=4)).isoformat()
        print(write(acquisition.REVIEW, encode(payload | {"expires_at": expiration}))["sha256"])


if __name__ == "__main__":
    main()
