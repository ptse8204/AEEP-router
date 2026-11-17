"""Screen the pinned SWE-rebench union and prepare a bounded new-source batch."""

import argparse
import json
import re
import shutil
from collections import Counter
from pathlib import Path, PurePosixPath

from audit_formal_inputs import repository
from prepare_contract_audits import prior_origins
from screen_candidate_patches import ROW_KEYS, python_source, test_roots
from stage_repository_transport import HERE, ROOT, WORK, digest, encode, read, write

COHORT = HERE.parent / "repository-cohort-20261022"
UNION = COHORT / "union-candidate-metadata.json"
TARGET = WORK / "repository-expansion-queue"
DATASET = "nebius/SWE-rebench-leaderboard"
REVISION = "34d5a58864acf91613740a09ec5d205228dcfa39"
CASE = re.compile(r"[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+-[0-9]+(?:_interface)?")
GIT_REV = re.compile(r"[0-9a-f]{40}")
PATHS = re.compile(r"a/([A-Za-z0-9_./+-]+) b/([A-Za-z0-9_./+-]+)")
SHAPE_CHANGED = (
    "old mode",
    "new mode",
    "deleted file",
    "new file",
    "Binary files",
    "GIT binary patch",
    "similarity",
    "rename from",
    "rename to",
)


def load(path):
    return json.loads(path.read_bytes())


def previous_repositories():
    prior, _ = prior_origins()
    for name, field in (
        ("additional-contract-audits.json", "private_index"),
        ("ancillary-contract-audits.json", "private_index"),
        ("cached-multifile-projections.json", "private_transport_index"),
    ):
        document = load(HERE / name)
        prior.extend(json.loads(read(ROOT / document[field], document[field + "_sha256"])))
    if (
        len(prior) != 105
        or len({(row["source_repository"], row["source_revision"]) for row in prior}) != 105
    ):
        raise ValueError("retained provisional source corpus changed")
    repositories = {repository(row["source_repository"]) for row in prior}
    cache = load(HERE.parent / "repository-review-bindings-20261029/cached-corpus-triage.json")
    seen = {repository(row["repository"]) for row in cache["rows"]}
    history = HERE.parent / "repository-usefulness-pilot-20261029"
    pilot = load(history / "cases.json")
    exposed = {repository(row["source_repository"]) for row in pilot}
    design = load(HERE.parent / "managed-comparison-20261115/sol-comparison-design.json")
    exposed.update(
        repository(row["repository"])
        for row in design["tasks_in_execution_order"]
        if row["domain"] == "software-engineering"
    )
    # Earlier inspected upstream and managed development sources are recorded in
    # the existing corpus exposure audit and original workload plan.
    exposed.update(
        {
            "delgan/loguru",
            "marshmallow-code/marshmallow",
            "pallets/click",
            "matthewwithanm/python-markdownify",
            "pgmpy/pgmpy",
        }
    )
    return repositories, seen, exposed


def patch_paths(text):
    paths = {}
    for section in text.split("diff --git ")[1:]:
        lines = section.splitlines()
        match = PATHS.fullmatch(lines[0])
        if match is None:
            raise ValueError("unreviewed_diff_path")
        name, other = match.groups()
        path = PurePosixPath(name)
        if (
            name != other
            or path.is_absolute()
            or path.as_posix() != name
            or ".." in path.parts
            or name in paths
        ):
            raise ValueError("unreviewed_diff_path")
        header = section.split("\n@@", 1)[0].splitlines()[1:]
        paths[name] = [line for line in header if line.startswith(SHAPE_CHANGED)]
    if not paths:
        raise ValueError("empty_patch")
    return paths


def screen(row):
    case = row["instance_id"]
    repo = repository(row["repo"])
    version = row["install_config"]
    revision = row["base_commit"]
    if not CASE.fullmatch(case) or not GIT_REV.fullmatch(revision):
        raise ValueError("publisher_identity")
    if (
        version["log_parser"] != "parse_log_pytest"
        or version["env_vars"]
        or version["env_yml_path"]
    ):
        raise ValueError("unreviewed_runtime")
    fail, preserve = row["FAIL_TO_PASS"], row["PASS_TO_PASS"]
    if not fail or not preserve or len(fail + preserve) != len(set(fail + preserve)):
        raise ValueError("missing_or_duplicate_test_identities")
    if len(fail + preserve) > 170:
        raise ValueError("large_required_test_scope")
    try:
        _, roots = test_roots(fail + preserve)
    except ValueError as error:
        raise ValueError("unsupported_test_root_or_identity") from error
    source = patch_paths(row["patch"])
    if any(source.values()):
        raise ValueError("repair_changes_file_shape")
    editable = sorted(name for name in source if python_source(name, roots))
    if not editable or any(
        PurePosixPath(name).suffix not in {".md", ".rst"} for name in source.keys() - set(editable)
    ):
        raise ValueError("unsupported_edit_scope")
    overlay = patch_paths(row["test_patch"])
    if any(
        not any(PurePosixPath(name).is_relative_to(root) for root in roots)
        or any(change != "new file mode 100644" for change in changes)
        for name, changes in overlay.items()
    ):
        raise ValueError("unsupported_protected_overlay")
    if len((row["problem_statement"] or "") + "\n" + (row["interface"] or "")) > 3_700:
        raise ValueError("task_text_bound")
    return {
        "repository": repo,
        "case_id": case,
        "revision": revision,
        "declared_python": version["python"],
        "requires_preinstall_review": bool(version["pre_install"]),
        "requires_requirements_review": bool(version["reqs_path"]),
        "candidate_python_paths": editable,
        "published_issue_identities": len(fail),
        "published_preservation_identities": len(preserve),
        "metadata_semantic_sha256": digest(
            json.dumps({key: row[key] for key in ROW_KEYS}, sort_keys=True).encode()
        ),
        "row_sha256": digest(encode(row)),
    }


def priority(row, *, role):
    preferred_python = row["declared_python"] in {"3.13", "3.13.1"}
    modern = row["declared_python"] in {"3.11", "3.12", "3.13", "3.13.1"}
    preservation = row["published_preservation_identities"]
    min_depth = 12 if role == "audit" else 6
    return (
        not modern,
        row["requires_preinstall_review"],
        row["requires_requirements_review"],
        preservation < min_depth,
        not preferred_python,
        abs(preservation - 24),
        row["case_id"].casefold(),
    )


def prepare(target):
    target = target.resolve()
    if target.parent != WORK or shutil.disk_usage(WORK).free < 52 * 1024**3:
        raise ValueError("use a new private project directory above the host reserve")
    metadata = load(UNION)
    if metadata["dataset"] != DATASET or metadata["revision_before_and_after"] != REVISION:
        raise ValueError("pinned publisher response definition changed")
    prior, seen, exposed = previous_repositories()
    refusal = Counter()
    records = []
    sealed_rows = {}
    used = set()
    for page in metadata["sources"]:
        source = read(ROOT / page["private_cache"], page["sha256"])
        if len(source) != page["bytes"]:
            raise ValueError("retained dataset response size changed")
        for envelope in json.loads(source)["rows"]:
            row = envelope["row"]
            case = row["instance_id"]
            if case in used:
                raise ValueError("duplicate dataset identity")
            used.add(case)
            repo = repository(row["repo"])
            if envelope["truncated_cells"]:
                refusal["truncated_dataset_row"] += 1
            elif repo in exposed or repo in prior or repo in seen:
                refusal["previously_considered_or_exposed_repository"] += 1
            else:
                try:
                    lead = screen(row)
                except ValueError as error:
                    refusal[str(error)] += 1
                else:
                    records.append(lead)
                    sealed_rows[case] = row
    if len(used) != metadata["rows"] or len(used) != 860:
        raise ValueError("dataset inventory unexpectedly changed")
    target.mkdir(mode=0o700)
    index = write(target / "leads.json", encode(records))
    payload = write(target / "dataset-rows.json", encode(sealed_rows))
    return {
        "schema_version": "aeep.c13.repository-expansion-queue.v1",
        "dataset": DATASET,
        "revision": REVISION,
        "retained_manifest_sha256": digest(UNION.read_bytes()),
        "source_pages_verified": len(metadata["sources"]),
        "rows_screened": len(used),
        "candidate_rows": len(records),
        "candidate_repositories": len({row["repository"] for row in records}),
        "multifile_path_candidates": len(
            {row["repository"] for row in records if len(row["candidate_python_paths"]) > 1}
        ),
        "screening_rejections": dict(sorted(refusal.items())),
        "input_repositories_excluded_for_actual_exposure": len(exposed),
        "leads": {"path": (target / "leads.json").relative_to(ROOT).as_posix(), **index},
        "rows": {"path": (target / "dataset-rows.json").relative_to(ROOT).as_posix(), **payload},
        "qualification": False,
        "runtime_compatibility_proven": False,
        "formal_cases_adopted": 0,
        "new_archive_downloads": 0,
        "models": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=TARGET)
    args = parser.parse_args()
    result = prepare(args.output)
    write(args.output / "summary.json", encode(result))
    print(json.dumps(result, indent=2))
