"""Acquire reviewed new source snapshots and stage their existing grader transport."""

import argparse
import http.client
import json
import shutil
import subprocess
import tarfile
import urllib.error
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from audit_formal_inputs import repository
from plan_repository_expansion import TARGET as QUEUE
from plan_repository_expansion import previous_repositories
from prepare_contract_audits import bind_case
from reacquire_repository_sources import download
from rebind_cached_repository_sources import (
    ARCHIVE_BOUND,
    COMMIT_METADATA_LIMIT,
    inventory,
    published_tree,
)
from screen_candidate_patches import assess, load_reviewed_helpers, stage_file
from stage_repository_transport import HERE, ROOT, WORK, bind_row, digest, encode, read, write

from aeep.errors import ConfigurationError

TARGET = WORK / "repository-expansion-acquisition"
REVIEW = QUEUE / "acquisition-review.json"
APPROVAL = QUEUE / "acquisition-approval.json"
MAX_REPOSITORY_SIZE_HINT = 250_000
SOURCE_REFUSALS = {
    "public commit metadata exceeds the review bound": "commit_metadata_cap",
    "publisher did not return the requested commit": "commit_identity",
    "publisher commit lookup escaped approved scope": "commit_location",
    "source response differs from the exact destination": "archive_location",
    "declared source exceeds the reviewed cap": "archive_declared_size",
    "source response truncated or at the reviewed cap": "archive_response_size",
    "archive could not be tied to the published tree and notices": "archive_tree_or_license",
}
RESERVE = 52 * 1024**3


def load(path):
    return json.loads(path.read_bytes())


def definition():
    queue = load(QUEUE / "summary.json")
    leads = {
        row["case_id"]: row
        for row in json.loads(read(ROOT / queue["leads"]["path"], queue["leads"]["sha256"]))
    }
    rows = json.loads(read(ROOT / queue["rows"]["path"], queue["rows"]["sha256"]))
    metadata = load(QUEUE / "publisher-metadata.json")
    if (
        metadata["retries"] != 0
        or metadata["uses_credentials"]
        or metadata["lookups_attempted"] != len(metadata["rows"])
    ):
        raise ValueError("publisher metadata scope changed")
    retained, prior, exposed = previous_repositories()
    eligible = [
        item
        for item in metadata["rows"]
        if item["status"] == "public_metadata" and item["size_hint_kib"] <= MAX_REPOSITORY_SIZE_HINT
    ]
    # Repository size is a prioritization hint. Transport bounds and licenses
    # are checked independently against the immutable archive.
    selected = []
    for entry in sorted(eligible, key=lambda item: (item["size_hint_kib"], item["repository"])):
        lead = leads[entry["case_id"]]
        repo, revision = lead["repository"], lead["revision"]
        if (
            repo != entry["repository"]
            or repo in retained | prior | exposed
            or repository(rows[lead["case_id"]]["repo"]) != repo
            or rows[lead["case_id"]]["base_commit"] != revision
            or digest(encode(rows[lead["case_id"]])) != lead["row_sha256"]
            or entry["intake_role"] not in {"audit", "multi-file-repair"}
        ):
            raise ValueError("candidate scope or source exclusion changed")
        selected.append(
            {
                "case_id": lead["case_id"],
                "repository": repo,
                "revision": revision,
                "intent": entry["intake_role"],
                "archive_url": f"https://codeload.github.com/{repo}/tar.gz/{revision}",
                "commit_url": f"https://api.github.com/repos/{repo}/git/commits/{revision}",
                "metadata_sha256": entry["metadata_sha256"],
                "source_size_hint_kib": entry["size_hint_kib"],
                "license_hint": entry["declared_license_hint"],
            }
        )
    if not selected or len(selected) != len({item["repository"] for item in selected}):
        raise ValueError("unexpected duplicate source repository")
    review = {
        "schema_version": "aeep.c13.repository-expansion-acquisition.v1",
        "queue_summary_sha256": digest((QUEUE / "summary.json").read_bytes()),
        "publisher_metadata_sha256": digest((QUEUE / "publisher-metadata.json").read_bytes()),
        "source_helpers": {
            name: digest((HERE / name).read_bytes())
            for name in (
                Path(__file__).name,
                "reacquire_repository_sources.py",
                "rebind_cached_repository_sources.py",
                "plan_repository_expansion.py",
                "prepare_contract_audits.py",
                "screen_candidate_patches.py",
                "stage_repository_transport.py",
            )
        },
        "sources": selected,
        "maximum_archive_requests": len(selected),
        "maximum_archive_bytes_each": ARCHIVE_BOUND,
        "maximum_archive_response_bytes": len(selected) * ARCHIVE_BOUND,
        "maximum_commit_metadata_requests": len(selected),
        "maximum_commit_metadata_response_bytes": len(selected) * (COMMIT_METADATA_LIMIT + 1),
        "retries": 0,
        "upstream_tests": 0,
        "installs": 0,
        "models": 0,
        "cash_usd": 0,
        "provider_disclosure": False,
        "formal_adoption": False,
    }
    return review, leads, rows


def retain_source(choice, row):
    case = TARGET / "archives" / choice["case_id"]
    case.mkdir(mode=0o700, parents=True)
    archive = case / "source-original.tar.gz"
    publisher = published_tree(choice["repository"], choice["revision"])
    if publisher["url"] != choice["commit_url"]:
        raise ValueError("publisher commit lookup escaped approved scope")
    download(choice["archive_url"], archive)
    tree, licenses, count, sha = inventory(archive, choice["revision"])
    if tree != publisher["published_tree"] or not licenses:
        raise ValueError("archive could not be tied to the published tree and notices")
    row_path = case / "row.json"
    write(row_path, encode(row))
    result = {
        "publisher": publisher,
        "archive_sha256": sha,
        "archive_entries": count,
        "archive_bytes": archive.stat().st_size,
        "license_notices": licenses,
    }
    return case, result


def project_source(choice, lead, case, result, helpers):
    archive = case / "source-original.tar.gz"
    binding = {
        **lead,
        "instance_id": lead["case_id"],
        "base_commit": lead["revision"],
        "source_bindings": [
            {
                "archive": archive.relative_to(ROOT).as_posix(),
                "sha256": result["archive_sha256"],
                "license_notices": result["license_notices"],
            }
        ],
    }
    if choice["intent"] == "audit":
        with TemporaryDirectory(prefix="aeep-expansion-audit-") as scratch:
            candidate = bind_case(binding, helpers, TARGET / "transport", Path(scratch), {})
    else:
        details, raw = assess(binding, helpers)
        details["case_id"] = choice["case_id"]
        details["assets"] = [stage_file(case, name, data) for name, data in raw.items()]
        candidate = bind_row(
            details, binding, TARGET / "transport", case.parent, str(archive.relative_to(ROOT))
        )
    return candidate


def run(exact):
    if not APPROVAL.is_file() or not REVIEW.is_file() or TARGET.exists():
        raise ValueError("exact reviewed acquisition needs an unstarted approval")
    approved_bytes = APPROVAL.read_bytes()
    approval = json.loads(approved_bytes)
    if (
        set(approval) != {"approved", "review_sha256"}
        or approval["approved"] is not True
        or approval["review_sha256"] != exact
        or digest(REVIEW.read_bytes()) != exact
    ):
        raise ValueError("approval does not bind the exact acquisition")
    review = load(REVIEW)
    expiry = datetime.fromisoformat(review.pop("expires_at"))
    expected, leads, source_rows = definition()
    if (
        expiry <= datetime.now(UTC)
        or review != expected
        or shutil.disk_usage(WORK).free < RESERVE + review["maximum_archive_response_bytes"]
    ):
        raise ValueError("review drift, expiry or insufficient storage")
    project = review.get("transport_projection", True)
    helpers = load_reviewed_helpers() if project else None
    TARGET.mkdir(mode=0o700)
    observations, candidates = [], []
    stopped = None
    for source in review["sources"]:
        if (
            not APPROVAL.is_file()
            or not REVIEW.is_file()
            or digest(REVIEW.read_bytes()) != exact
            or APPROVAL.read_bytes() != approved_bytes
        ):
            stopped = "approval_or_review_changed"
            break
        if expiry <= datetime.now(UTC) or shutil.disk_usage(WORK).free < RESERVE + ARCHIVE_BOUND:
            stopped = "expiry_or_space"
            break
        case_id = source["case_id"]
        attempt = TARGET / "attempts" / case_id
        attempt.mkdir(mode=0o700, parents=True)
        write(attempt / "started.json", encode({"case_id": case_id, "review_sha256": exact}))
        observation = {"case_id": case_id}
        phase = "archive_intake"
        try:
            case, info = retain_source(source, source_rows[case_id])
            if project:
                phase = "transport_projection"
                candidate = project_source(source, leads[case_id], case, info, helpers)
        except urllib.error.HTTPError as failure:
            observation.update(
                status="publisher_request_failed", http_code=failure.code, phase=phase
            )
            if failure.code in {403, 429}:
                stopped = "publisher_rate_or_authority_limit"
        except (
            OSError,
            tarfile.TarError,
            http.client.HTTPException,
            KeyError,
            AssertionError,
            ConfigurationError,
            ValueError,
            SyntaxError,
            subprocess.CalledProcessError,
        ) as failure:
            # Some checked archives legitimately do not fit the source or test contract.
            # Preserve partial files and record the terminal result without retrying.
            observation.update(
                status="source_or_transport_unverified",
                error_type=type(failure).__name__,
                phase=phase,
            )
            if phase == "archive_intake" and type(failure) is ValueError:
                reason = SOURCE_REFUSALS.get(str(failure))
                if reason:
                    observation["reason"] = reason
        else:
            if project:
                candidates.append(candidate)
            observation.update(status="transport_staged" if project else "archive_verified", **info)
        write(attempt / "result.json", encode(observation))
        observations.append(observation)
        if stopped is not None:
            break
    index = write(TARGET / "index.json", encode(candidates))
    result = {
        "review_sha256": exact,
        "started": len(observations),
        "stopped": stopped,
        "observations": observations,
        "candidate_index": index,
        "staged_by_family": dict(Counter(row["input"]["family"] for row in candidates)),
        "formal_cases_adopted": 0,
        "upstream_tests": 0,
        "models": 0,
        "cash_usd": 0,
    }
    write(TARGET / "result.json", encode(result))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--exact-review")
    args = parser.parse_args()
    if args.prepare:
        assembled, _, _ = definition()
        assembled["expires_at"] = (datetime.now(UTC) + timedelta(days=7)).isoformat()
        print(write(REVIEW, encode(assembled))["sha256"])
    else:
        print(json.dumps(run(args.exact_review), indent=2))
