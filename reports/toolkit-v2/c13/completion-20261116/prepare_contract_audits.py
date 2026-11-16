"""Stage five distinct source-bound contract audits from retained upstream fixes."""

import argparse
import ast
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from audit_formal_inputs import repository
from screen_candidate_patches import INTAKE, assess, load_reviewed_helpers
from stage_repository_transport import HERE, ROOT, WORK, digest, encode, read, write

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import (
    SuiteInput,
    archive_files,
    compressed_patch_artifact,
    pack_files,
    public_archive,
)
from aeep.assessment.repository_tasks import RepositoryPatch

SELECTED = {
    "lmstudio-ai__venvstacks-197": "docs/changelog.d/20250603_050408_ncoghlan_only_lock_if_necessary_in_build_subcommand.rst",
    "pypa__build-1027": "docs/changelog/860.bugfix.rst",
    "pypa__twine-1225": "changelog/1224.bugfix.rst",
    "tox-dev__tox-3759": "docs/changelog/3758.bugfix.rst",
    "twisted__towncrier-687": "src/towncrier/newsfragments/687.feature.rst",
}
TARGET = WORK / "new-contract-audits"
INTAKE_SHA = "637b43c855fc20ff403a992e63a5088b6d711eb5be9a3294356ca8f8782da61c"


def load(path):
    return json.loads(path.read_bytes())


def prior_origins():
    prepared = load(HERE / "formal-transport-preparation.json")
    staged = load(HERE / "rebound-worker-transport.json")
    recovered = load(HERE / "multifile-acquisition-result.json")
    scope = WORK / "multifile-acquisition-static-handoff/worker-transport/private-index.json"
    recovered_pin = recovered["private_evidence_sha256"][scope.relative_to(ROOT).as_posix()]
    sources = [
        (ROOT / prepared["prepared_pool_relative_path"], prepared["prepared_pool_sha256"]),
        (ROOT / staged["private_index_relative_path"], staged["private_index_sha256"]),
        (scope, recovered_pin),
    ]
    prior = [
        row
        for path, digest in sources
        for row in json.loads(read(path, digest))
        if row["input"]["task_id"] != "a2aproject__a2a-python-472"
    ]
    origins = {(repository(row["source_repository"]), row["source_revision"]) for row in prior}
    if len(origins) != len(prior) or len(prior) != 89:
        raise ValueError("retained prospective pool changed")
    return prior, origins


def guard_source(root, fixed, editable):
    expected = {name: hashlib.sha256(fixed[name]).hexdigest() for name in editable}
    depth = len(PurePosixPath(root).parts)
    code = (
        "import hashlib\nfrom pathlib import Path\n\n"
        "def test_snapshot_preserved():\n"
        f"    root = Path(__file__).resolve().parents[{depth}]\n"
        f"    expected = {expected!r}\n"
        "    assert all(hashlib.sha256((root / name).read_bytes()).hexdigest() == pin\n"
        "               for name, pin in expected.items())\n"
    )
    ast.parse(code)
    return code.encode()


def verify_guard(code, test_name, fixed, base, scratch):
    for name, content in fixed.items():
        path = scratch / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    namespace = {"__file__": str(scratch / test_name)}
    # Only the coordinator-authored guard is executed.
    exec(compile(code, "<first-party-preservation-guard>", "exec"), namespace)
    check = namespace["test_snapshot_preserved"]
    check()
    for name, content in base.items():
        path = scratch / name
        path.write_bytes(content)
        try:
            check()
        except AssertionError:
            pass
        else:
            raise ValueError("byte preservation guard accepted a restored source file")
        path.write_bytes(fixed[name])


def bind_case(lead, helpers, target, scratch):
    original_id = lead["instance_id"]
    facts, assets = assess(lead, helpers, reviewed_documentation_additions=[SELECTED[original_id]])
    if SELECTED[original_id] not in facts["omitted_documentation_changes"]:
        raise ValueError("reviewed documentation adaptation was lost")
    base = archive_files(assets["source.tar.gz"], large=True)
    overlay = archive_files(assets["tests.tar.gz"], large=True)
    repair = {name: value.encode() for name, value in json.loads(assets["repair.json"]).items()}
    if any(base.get(name) == value for name, value in repair.items()):
        raise ValueError("repair includes an unchanged editable file")
    fixed = {**base, **repair}
    public = pack_files(fixed, large=True)
    source_hash = digest(public)
    task_id = original_id + "-aeep-contract-audit"
    issue_path = (ROOT / lead["source_bindings"][0]["archive"]).with_name("row.json")
    issue = json.loads(read(issue_path, facts["dataset_row_sha256"]))
    statement = issue["problem_statement"] + (
        "\n\n" + issue["interface"] if issue.get("interface") else ""
    )
    task = SuiteInput(
        task_id=task_id,
        family="contract-audit",
        source_sha256=source_hash,
        editable_paths=facts["editable_changes"],
        task=(
            "Audit the current checkout against the stated contract. Return an empty patch "
            "if it already satisfies the contract. Restrict any changes to the listed source "
            "files.\n\n" + statement
        ),
    )
    binding = content_digest(task)
    original = {name: base[name].decode("utf-8") for name in task.editable_paths}
    reference = compressed_patch_artifact(RepositoryPatch(base_sha256=binding, files={}))
    fault = compressed_patch_artifact(RepositoryPatch(base_sha256=binding, files=original))
    requirements = json.loads(assets["required.json"])
    root = facts["test_roots"][0]
    guard_file = root + "/test_aeep_preservation.py"
    if guard_file in fixed or guard_file in overlay:
        raise ValueError("authored guard conflicts with an existing test")
    guard = guard_source(root, fixed, task.editable_paths)
    verify_guard(guard, guard_file, repair, {name: base[name] for name in original}, scratch)
    overlay[guard_file] = guard
    required = requirements["fail_to_pass"] + requirements["pass_to_pass"]
    guard_id = guard_file + "::test_snapshot_preserved"
    if guard_id in required or set(overlay) & set(task.editable_paths):
        raise ValueError("protected guard or test archive conflicts with a published assertion")
    protected = pack_files(overlay, large=True)
    public_root = target / "public"
    write(public_root / f"{source_hash}.tar.gz", public)
    mapped = public_archive(task.model_dump(mode="json"), [str(public_root)], large=True)
    if mapped["base_sha256"] != binding or mapped["source_sha256"] != source_hash:
        raise ValueError("ordinary worker carrier changed")
    case_dir = target / "protected" / task_id
    files = {
        "tests.tar.gz": protected,
        "reference.json": encode(reference),
        "original-source-fault.json": encode(fault),
        "required.json": encode(
            {
                "published_fail_to_pass": requirements["fail_to_pass"],
                "published_pass_to_pass": requirements["pass_to_pass"],
                "protected_audit_required": [*required, guard_id],
            }
        ),
    }
    return {
        "input": task.model_dump(mode="json"),
        "source_repository": repository(facts["repository"]),
        "source_revision": facts["revision"],
        "original_source_sha256": facts["source_archive_sha256"],
        "dataset_row_sha256": facts["dataset_row_sha256"],
        "license_notices": facts["license_notices"],
        "origin_kind": "authored_control",
        "protected_assets": {name: write(case_dir / name, data) for name, data in files.items()},
        "test_roots": facts["test_roots"],
        "test_modules": sorted([*facts["test_modules"], guard_file]),
        "published_python": facts["published_python"],
        "omitted_documentation": facts["omitted_documentation_changes"],
        "reference_archive_sha256": digest(pack_files({**fixed, **overlay}, large=True)),
        "fault_archive_sha256": digest(pack_files({**base, **overlay}, large=True)),
        "upstream_assertion_count": len(required),
        "protected_guard": guard_id,
        "runtime_verified": False,
        "formal_assignment": None,
    }


def prepare(target):
    target = target.resolve()
    if not target.is_relative_to(WORK) or target == WORK:
        raise ValueError("audit staging must use a new private workspace")

    prior, origins = prior_origins()
    intake = {row["instance_id"]: row for row in json.loads(read(INTAKE, INTAKE_SHA))}
    if any(
        (repository(intake[k]["repository"]), intake[k]["base_commit"]) in origins for k in SELECTED
    ):
        raise ValueError("selected audit repeats an existing provisional source")
    if shutil.disk_usage(WORK).free < 50 * 1024**3 + 128 * 1024**2:
        raise ValueError("host storage is below the retained reserve")
    target.mkdir(mode=0o700)
    helpers, output = load_reviewed_helpers(), []
    for case_id in SELECTED:
        with TemporaryDirectory(prefix="aeep-audit-preservation-") as root:
            output.append(bind_case(intake[case_id], helpers, target, Path(root)))
    pool = [*prior, *output]
    families = Counter(row["input"]["family"] for row in pool)
    snapshots = {row["input"]["source_sha256"] for row in pool}
    expected_public_names = {row["input"]["source_sha256"] + ".tar.gz" for row in output}
    if {path.name for path in (target / "public").iterdir()} != expected_public_names:
        raise ValueError("ordinary worker root contains an unexpected artifact")
    if len(snapshots) != len(pool):
        raise ValueError("audit duplicates a public snapshot")
    index = write(target / "index.json", encode(output))
    result = {
        "schema_version": "aeep.c13.additional-contract-audits.v1",
        "private_index": str((target / "index.json").relative_to(ROOT)),
        "private_index_sha256": index["sha256"],
        "cases": [
            {
                key: row[key]
                for key in (
                    "source_repository",
                    "source_revision",
                    "upstream_assertion_count",
                    "omitted_documentation",
                )
            }
            | {
                "case_id": row["input"]["task_id"],
                "verified_guard_rejection_count": len(row["input"]["editable_paths"]),
            }
            for row in output
        ],
        "optimistic_case_count": len(pool),
        "distinct_repository_families": len({repository(row["source_repository"]) for row in pool}),
        "only_current_public_archives_in_worker_root": True,
        "optimistic_case_counts_by_family": dict(families),
        "minimum_additional_rows_before_independence": 141 - len(pool),
        "minimum_additional_holdout_rows_by_family": {
            family: max(0, 35 - count) for family, count in families.items()
        },
        "upstream_test_executions": 0,
        "model_turns": 0,
        "formal_cases_adopted": 0,
    }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=TARGET)
    arguments = parser.parse_args()
    print(json.dumps(prepare(arguments.output), indent=2))
