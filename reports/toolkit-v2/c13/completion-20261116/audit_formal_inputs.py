"""Audit retained formal-campaign inputs without importing or running task code."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase
from aeep.errors import ConfigurationError

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent
ROOT = HERE.parents[3]
REQUIRED = {"qualification": 8, "training": 28, "holdout": 105}


def repository(value: str) -> str:
    url = urlsplit(value)
    if url.scheme and (url.scheme != "https" or url.netloc != "github.com"):
        raise ValueError("unexpected repository host")
    slug = url.path.strip("/").removesuffix(".git").casefold()
    if len(slug.split("/")) != 2 or not all(slug.split("/")):
        raise ValueError("expected an owner/repository pair")
    return slug


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(path: Path, pins: dict[str, str]):
    data = path.read_bytes()
    pins[str(path.relative_to(ROOT))] = digest(data)
    return json.loads(data)


def source_records(pins: dict[str, str]) -> dict[tuple[str, str, str], list[dict]]:
    records: dict[tuple[str, str, str], list[dict]] = {}
    for path in sorted(PREVIOUS.glob("repository-*/*source-review.json")):
        report = load(path, pins)
        sources = report.get("sources", ()) if isinstance(report, dict) else ()
        for row in sources:
            if not isinstance(row, dict) or not all(row.get(key) for key in (
                "instance_id", "revision", "private_cache", "archive_sha256"
            )):
                continue
            archive = (ROOT / row["private_cache"] / "source.tar.gz").resolve()
            if archive.is_relative_to(ROOT / ".aeep"):
                key = (row["instance_id"], row["revision"], str(archive.relative_to(ROOT)))
                records.setdefault(key, []).append(row)
    return records


def verify_lead(lead: dict, records: dict) -> tuple[str, list[dict]]:
    matched = []
    exclusions = False
    for name in lead["archives"]:
        candidates = records.get((lead["instance_id"], lead["base_commit"], name), [])
        if not candidates:
            continue
        path = ROOT / name
        with path.open("rb") as archived:
            sha = hashlib.file_digest(archived, "sha256").hexdigest()
        for record in candidates:
            if sha != record["archive_sha256"]:
                continue
            if record.get("status") == "EXCLUDED":
                exclusions = True
                continue
            licenses = record.get("licenses") or []
            if licenses and all(entry.get("file") and entry.get("sha256") for entry in licenses):
                binding = {"archive": name, "sha256": sha, "license_notices": licenses}
                if binding not in matched:
                    matched.append(binding)
    if exclusions:
        return "matching_prior_source_exclusion", matched
    return ("matches_acquisition_and_license_record" if matched
            else "requires_source_binding_or_license_record"), matched


def audit() -> tuple[dict, list[dict]]:
    pins: dict[str, str] = {}
    pilot_root = PREVIOUS / "repository-usefulness-pilot-20261029"
    overlay = load(pilot_root / "formal-exposure-exclusions.json", pins)
    pool = Path(overlay["remaining_cases_file"])
    pool = ROOT / ".aeep" / pool.parent.name / pool.name
    raw_cases = load(pool, pins)
    if pins[str(pool.relative_to(ROOT))] != overlay["remaining_cases_sha256"]:
        raise ValueError("retained case inventory hash mismatch")
    if len(raw_cases) != overlay["remaining_potential_snapshots"] or overlay["adopted_cases"]:
        raise ValueError("the retained pool no longer has the reviewed provisional scope")
    pilot = load(pilot_root / "cases.json", pins)
    if len(pilot) != overlay["exposed_original_task_slots"]:
        raise ValueError("pilot exposure inventory does not match the exposure decision")
    current_study = PREVIOUS / "managed-comparison-20261115"
    design = load(current_study / "sol-comparison-design.json", pins)
    load(current_study / "libcst-direct-result.json", pins)
    skillrank = load(PREVIOUS / "skillrank-managed-diagnostic-20261107/managed-result.json", pins)
    if not skillrank["passed"] or skillrank["turns"] != 2:
        raise ValueError("SkillRank exposure could not be reconciled")
    earlier_development = load(PREVIOUS / "repository-task-delivery-20261023/model-result.json", pins)
    if len(earlier_development["records"]) != 6:
        raise ValueError("repository development exposure could not be reconciled")
    # These are the source families in the six settled trial IDs and the
    # Markdownify SkillRank diagnostic. Exclude the entire families.
    exact_development = {
        "delgan/loguru": "development-delgan__loguru-1451",
        "marshmallow-code/marshmallow": "development-marshmallow-code__marshmallow-2800",
        "pallets/click": "development-pallets__click-3239",
    }
    if any(sum(marker in key for key in earlier_development["records"]) != 2
           for marker in exact_development.values()) or not all(
               trial["case_id"] == "matthewwithanm__python-markdownify-200"
               for trial in skillrank["trials"]
           ):
        raise ValueError("a task binding changed in the retained development records")
    exposed = {repository(row["source_repository"]) for row in pilot}
    exposed.update(repository(task["repository"]) for task in design["tasks_in_execution_order"]
                   if task["domain"] == "software-engineering")
    exposed.update(exact_development)
    exposed.add("matthewwithanm/python-markdownify")
    cases = [RepositorySuiteCase.model_validate(case) for case in raw_cases]
    identities = [
        (case.independent_case_id, (repository(case.source_repository), case.source_revision),
         content_digest(case.input), case.input.source_sha256)
        for case in cases
    ]
    if any(len(set(values)) != len(cases) for values in zip(*identities, strict=True)):
        raise ValueError("case pool contains duplicate case IDs, origins, inputs or snapshots")
    candidate_rows = []
    rejected = Counter()
    checked = set()
    for case in cases:
        repo = repository(case.source_repository)
        if repo in exposed or case.used_for_development:
            rejected["development_exposure"] += 1
            continue
        if case.origin_kind == "synthetic_fixture":
            rejected["synthetic_fixture"] += 1
            continue
        assets = [case.truth.source, case.truth.tests, case.reference, *case.truth.wheels]
        try:
            for asset in assets:
                key = (asset.path, asset.sha256, asset.size_bytes)
                if key not in checked:
                    asset.read()
                    checked.add(key)
        except (ConfigurationError, OSError) as exc:
            raise ValueError(f"could not verify assets for {case.independent_case_id}") from exc
        candidate_rows.append((repo, case))

    triage = load(PREVIOUS / "repository-review-bindings-20261029/cached-corpus-triage.json", pins)
    for name, expected in triage["queue_sha256"].items():
        with (ROOT / name).open("rb") as queue:
            pins[name] = hashlib.file_digest(queue, "sha256").hexdigest()
        if pins[name] != expected:
            raise ValueError(f"prior cached queue changed: {name}")
    retained_origins = {row[1] for row in identities}
    leads = []
    filtered = Counter()
    for row in triage["rows"]:
        repo = repository(row["repository"])
        if repo in exposed:
            filtered["development_exposure"] += 1
        elif (repo, row["base_commit"]) in retained_origins:
            filtered["duplicate_base"] += 1
        elif row["conflicting_cached_metadata"]:
            filtered["conflicting_metadata"] += 1
        elif not row["published_fail_to_pass_count"] or not row["published_pass_to_pass_count"]:
            filtered["published_bug_or_preservation_tests_missing"] += 1
        else:
            archives = [path for path in row["cached_archives_not_yet_verified"]
                        if (ROOT / path).is_file()]
            if not archives:
                filtered["local_archive_missing"] += 1
                continue
            leads.append({"repository": repo, "instance_id": row["instance_id"],
                          "base_commit": row["base_commit"], "archives": archives,
                          "metadata_semantic_sha256": row["metadata_semantic_sha256"],
                          "queue_files": row["queue_files"]})

    recorded = source_records(pins)
    for lead in leads:
        status, binding = verify_lead(lead, recorded)
        lead.update(source_status=status, source_bindings=binding)
    lead_status_counts = Counter(row["source_status"] for row in leads)
    candidate_repos = {repo for repo, _ in candidate_rows}
    lead_repos = {row["repository"] for row in leads}
    return {
        "input_sha256": dict(sorted(pins.items())),
        "required_case_counts": REQUIRED,
        "stages_frozen": False,
        "adopted_cases": 0,
        "verified_retained_asset_bindings": len(checked),
        "supplied_provisional_rows": len(cases),
        "asset_verified_provisional_rows": len(candidate_rows),
        "asset_verified_provisional_repositories": len(candidate_repos),
        "asset_verified_provisional_families": dict(sorted(
            Counter(case.input.family for _, case in candidate_rows).items())),
        "excluded_provisional_rows": dict(rejected),
        "documented_development_repository_exclusions": len(exposed),
        "minimum_row_shortfall_before_independence_and_adoption": sum(REQUIRED.values()) - len(candidate_rows),
        "cached_inventory_rows": len(triage["rows"]),
        "filtered_cached_rows": dict(sorted(filtered.items())),
        "cached_leads_requiring_rights_source_and_grader_review": len(leads),
        "cached_lead_repositories": len(lead_repos),
        "cached_lead_repositories_new_to_retained_pool": len(lead_repos - candidate_repos),
        "cached_lead_acquisition_status": dict(sorted(lead_status_counts.items())),
        "cached_leads_sha256": content_digest({"leads": leads}),
    }, leads


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-leads", type=Path, help="optional new, ignored .aeep file")
    args = parser.parse_args()
    result, leads = audit()
    if args.private_leads:
        destination = args.private_leads.resolve()
        if not destination.is_relative_to(ROOT / ".aeep"):
            parser.error("the unadopted task queue belongs in the private .aeep directory")
        with destination.open("x") as output:
            output.write(json.dumps(leads, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
