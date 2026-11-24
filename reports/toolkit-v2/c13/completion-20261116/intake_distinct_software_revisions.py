"""Review first archive intake for exact, previously unstarted software snapshots."""

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import acquire_repository_expansion as acquisition
import audit_two_cohort_source_capacity as capacity
from intake_software_source_batch import WORK
from stage_repository_transport import HERE, digest, encode, read, write


def definition(cases):
    if not 1 <= len(cases) <= 6 or len(cases) != len(set(cases)):
        raise ValueError("select one to six distinct case IDs")
    published, rows, summary = capacity.sealed_leads()
    leads = {entry["case_id"]: entry for entry in published}
    _, staged = capacity.source_pools()
    used = set(staged) | capacity.attempted_origins()
    exposed = {capacity.lineage(repo) for repo in capacity.previous_repositories()[2]}
    records = []
    for case in sorted(cases):
        lead, source = leads[case], rows[case]
        repo, revision = lead["repository"], lead["revision"]
        origin = capacity.lineage(repo), revision
        if origin in used or origin[0] in exposed:
            raise ValueError("source revision was staged or attempted, or repository was exposed")
        if (
            source["repo"].casefold() != repo
            or source["base_commit"] != revision
            or digest(encode(source)) != lead["row_sha256"]
            or len(lead["candidate_python_paths"]) < 2
        ):
            raise ValueError("source pin or multi-file repair lead differs from scope")
        used.add(origin)
        records.append(
            {
                "case_id": case,
                "repository": repo,
                "revision": revision,
                "intent": "multi-file-repair",
                "archive_url": f"https://codeload.github.com/{repo}/tar.gz/{revision}",
                "commit_url": f"https://api.github.com/repos/{repo}/git/commits/{revision}",
                "dataset_row_sha256": lead["row_sha256"],
            }
        )

    scope = {
        "schema_version": "aeep.c13.multi-snapshot-source-intake.v1",
        "queue_leads_sha256": summary["leads"]["sha256"],
        "queue_rows_sha256": summary["rows"]["sha256"],
        "drivers": {
            name: digest((HERE / name).read_bytes())
            for name in (
                Path(__file__).name,
                "acquire_repository_expansion.py",
                "audit_two_cohort_source_capacity.py",
                "plan_repository_expansion.py",
                "reacquire_repository_sources.py",
                "rebind_cached_repository_sources.py",
                "stage_repository_transport.py",
            )
        },
        "sources": records,
        "lineage_requirement": "All snapshots from one repository stay in a single stage.",
        "maximum_archive_requests": len(records),
        "maximum_archive_response_bytes": len(records) * acquisition.ARCHIVE_BOUND,
        "maximum_commit_metadata_requests": len(records),
        "maximum_commit_metadata_response_bytes": len(records)
        * (acquisition.COMMIT_METADATA_LIMIT + 1),
        "transport_projection": False,
        "retries": 0,
        "upstream_tests": 0,
        "models": 0,
        "cash_usd": 0,
        "provider_disclosure": False,
        "authority": "First bounded public source intake under the C13 engineering delegation.",
    }
    return scope, leads, rows


def execute(folder, exact):
    acquisition.TARGET = folder / "intake"
    acquisition.REVIEW = folder / "review.json"
    acquisition.APPROVAL = folder / "scope.json"
    acquisition.RESERVE = 50 * 1024**3
    record = json.loads(read(acquisition.REVIEW, exact))
    cases = [entry["case_id"] for entry in record["sources"]]
    acquisition.definition = lambda: definition(cases)
    approval = encode({"approved": True, "review_sha256": exact})
    try:
        write(acquisition.APPROVAL, approval)
    except FileExistsError:
        read(acquisition.APPROVAL, digest(approval))
    return acquisition.run(exact)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch")
    parser.add_argument("cases", nargs="*")
    parser.add_argument("--execute")
    args = parser.parse_args()
    if not args.batch.isascii() or not args.batch.replace("-", "").isalnum():
        parser.error("batch must be a private directory name")
    folder = WORK / args.batch
    if args.execute:
        if args.cases:
            parser.error("execution uses only the exact reviewed cases")
        result = execute(folder, args.execute)
        print(json.dumps({k: v for k, v in result.items() if k != "observations"}))
    else:
        scope, _, _ = definition(args.cases)
        folder.mkdir(mode=0o700)
        expires_at = (datetime.now(UTC) + timedelta(hours=4)).isoformat()
        print(write(folder / "review.json", encode(scope | {"expires_at": expires_at}))["sha256"])


if __name__ == "__main__":
    main()
