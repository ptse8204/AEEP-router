"""Stage the production scope of pyserde PR 682 with its unchanged published tests."""

import argparse
import ast
import asyncio
import json
import re
import shutil
import tomllib
from collections import Counter, defaultdict
from pathlib import Path

import audit_corpus_capacity as corpus
import audit_staged_repository_graders as transport
from audit_extractbench_audent import cached_wheels, declared_wheels, target_environment
from packaging.markers import Marker
from plan_repository_expansion import previous_repositories
from rebind_cached_repository_sources import inventory
from screen_candidate_patches import ROW_KEYS, assess, load_reviewed_helpers, stage_file
from stage_repository_transport import HERE, ROOT, WORK, bind_row, digest, encode, read, write

from aeep.assessment.repository_suites import archive_files, compressed_patch_artifact
from aeep.assessment.repository_tasks import RepositoryPatch

CASE = "yukinarit__pyserde-682"
REPO = "yukinarit/pyserde"
REVISION = "59af51ef2292821900629ec8a3f5b898e20f8078"
ORIGINAL = ROOT / ".aeep/repository-workload-batch-20261022-sources" / CASE
EVIDENCE = WORK / "pyserde-production-repair-20261116"
TREE_PIN = "8135540b783de9b1fef9c5ae7821bbd846a46d9e7c272632a7a62e5b96db36d4"
PR_PIN = "923f0262914a3835670099856e51fed3a170bbf42606b0c9b69f955144e1b063"
ROW_PIN = "50d9e7fb91cdcb6b130cd8d0d55b543e9be3694eef6f97e9759ca0329e785fdb"
SOURCE_FILES = ("serde/de.py", "serde/se.py")
EXAMPLES = ("examples/runner.py", "examples/type_statement.py")
VERIFIER = "tests/test_type_alias.py"


def headings(patch):
    sections = list(re.finditer(r"^diff --git a/([^\n ]+) b/([^\n ]+)\n", patch, re.MULTILINE))
    values = {}
    for index, match in enumerate(sections):
        if match[1] != match[2] or match[1] in values:
            raise ValueError("source rename or repeated patch section")
        end = sections[index + 1].start() if index + 1 < len(sections) else len(patch)
        values[match[1]] = patch[match.start():end]
    return values


def semantic_digest(row):
    return digest(json.dumps({key: row[key] for key in ROW_KEYS}, sort_keys=True).encode())


def upstream():
    tree = json.loads(read(EVIDENCE / "publisher-tree.json", TREE_PIN))
    raw = read(ORIGINAL / "source.tar.gz", tree["archive_sha256"])
    computed, notices, files, sha = inventory(ORIGINAL / "source.tar.gz", REVISION)
    if (computed, notices, files, sha, tree["revision"]) != (
        tree["published_tree"], tree["license_notices"], tree["files"], tree["archive_sha256"], REVISION
    ):
        raise ValueError("retained source failed reproduction against the published Git tree")
    row = json.loads(read(ORIGINAL / "row.json", ROW_PIN))
    lead = next(item for item in corpus.load(WORK / "source-bound-leads.json") if item["instance_id"] == CASE)
    if semantic_digest(row) != lead["metadata_semantic_sha256"] or row["repo"].casefold() != REPO or row["base_commit"] != REVISION:
        raise ValueError("retained SWE-rebench task identity changed")
    repair = headings(row["patch"])
    tests = headings(row["test_patch"])
    publisher_patch = read(EVIDENCE / "publisher-pr.patch", PR_PIN).decode()
    # Strip the mail patch's Git version footer before comparing the last section.
    official = headings(publisher_patch.rsplit("\n-- \n", 1)[0] + "\n")
    if (repair.keys() != set(SOURCE_FILES) | set(EXAMPLES) or tests.keys() != {VERIFIER}
            or any(official[name].rstrip() != content.rstrip() for name, content in (repair | tests).items())):
        raise ValueError("SWE-rebench scopes differ from the publisher patch")
    projected = {**row, "patch": "".join(repair[name] for name in SOURCE_FILES)}
    return tree, raw, row, projected, {name: digest(repair[name].encode()) for name in EXAMPLES}


def partition_projection(mapped):
    rows, _ = corpus.prior_origins()
    for name, field in corpus.EXTRA_INDEXES:
        record = corpus.load(HERE / name)
        rows.extend(json.loads(read(ROOT / record[field], record[field + "_sha256"])))
    staged = corpus.load(HERE / "staged-repository-grader-bindings.json")
    excluded = {row["case"] for row in staged["cases"] if row.get("admits_python_3_13_0") is False}
    if any(row["source_revision"] == REVISION and row["source_repository"].casefold() == REPO for row in rows):
        raise ValueError("case repeats a retained origin")
    siblings = [row["input"]["task_id"] for row in rows if row["source_repository"].casefold() == REPO]
    if siblings != ["yukinarit__pyserde-657"] or REPO in previous_repositories()[2]:
        raise ValueError("repository family or exposure scope changed")
    retained = corpus.grouped(
        (row["source_repository"].casefold(), row["source_revision"], row["input"]["family"])
        for row in [*rows, mapped] if row["input"]["task_id"] not in excluded
    )
    source = corpus.load(corpus.PREPARATION)
    review = json.loads(read(ROOT / source["review_path"], source["review_sha256"]))
    pending = corpus.grouped((row["repository"], row["revision"],
        "contract-audit" if row["intent"] == "audit" else row["intent"]) for row in review["sources"])
    needed = corpus.minimum_profiles(corpus.totals(retained), corpus.totals(pending))
    if len(needed) != 1 or needed[0][0] != Counter({"contract-audit": 26, "multi-file-repair": 17}):
        raise ValueError("conditional capacity projection changed")
    witness = corpus.witness(retained, pending, needed[0])
    return {"source_review_sha256": source["review_sha256"], "same_stage_with": siblings,
            "additional_case_counts": dict(needed[0][0]), "stage_capacity_example": witness,
            "formal_assignment": None, "scope": "Conditional capacity if every required prospect is accepted."}


def dependency_projection(lock_bytes):
    packages = defaultdict(list)
    for item in tomllib.loads(lock_bytes.decode())["package"]:
        packages[item["name"]].append(item)
    pending = [{"name": "pyserde", "source": {"editable": "."}}]
    chosen = {}
    environment = target_environment()
    while pending:
        edge = pending.pop()
        if set(edge) - {"name", "version", "source", "marker"}:
            raise ValueError("lock edge requires additional review")
        if "marker" in edge and not Marker(edge["marker"]).evaluate(environment):
            continue
        name = edge["name"]
        candidates = [item for item in packages[name]
                      if all(item.get(key) == edge[key] for key in ("version", "source") if key in edge)]
        if len(candidates) != 1:
            raise ValueError("source lock has an ambiguous runtime dependency")
        selected = candidates[0]
        if name in chosen:
            if chosen[name] != selected:
                raise ValueError("runtime lock selects inconsistent versions")
            continue
        chosen[name] = selected
        pending.extend(selected.get("dependencies", ()))
    del chosen["pyserde"]
    wheels, absent = declared_wheels([chosen[name] for name in sorted(chosen)])
    cached = cached_wheels(wheels)
    return {
        "lock_sha256": digest(lock_bytes), "runtime_target": environment,
        "wheels": {name: {**pin, "cached": pin["filename"] in cached,
                          "ordinary_transport_eligible": pin["size"] <= 650_000 and pin["filename"].endswith("-none-any.whl")}
                   for name, pin in wheels.items()},
        "missing_platform_wheels": absent,
        "missing_cache_bytes": sum(pin["size"] for pin in wheels.values() if pin["filename"] not in cached),
        "scope": "Published base lock projected onto the retained CPython 3.13 Linux ARM64 profile. Offline dependency authorization and actual native grading remain open.",
    }


async def stage(target):
    if target.resolve() != target or target.exists() or not target.is_relative_to(WORK) or shutil.disk_usage(WORK).free < 52 * 1024**3:
        raise ValueError("use a fresh private directory above the storage reserve")
    tree, raw, original, row, example_pins = upstream()
    root = target / "input-review" / CASE
    root.mkdir(mode=0o700, parents=True)
    source = stage_file(root, "source-original.tar.gz", raw)
    row_pin = stage_file(root, "row.json", encode(row))
    lead = {"instance_id": CASE, "repository": REPO, "base_commit": REVISION,
            "source_bindings": [{"archive": str((root / source["file"]).relative_to(ROOT)),
                                 "sha256": source["sha256"], "license_notices": tree["license_notices"]}],
            "metadata_semantic_sha256": semantic_digest(row)}
    facts, assets = assess(lead, load_reviewed_helpers())
    if facts["family"] != "multi-file-repair" or tuple(facts["executable_changes"]) != SOURCE_FILES or facts["test_modules"] != [VERIFIER]:
        raise ValueError("the projected repair or tests differ from the reviewed scope")
    public = archive_files(assets["source.tar.gz"], large=True)
    overlay = archive_files(assets["tests.tar.gz"], large=True)
    # The selected test module and root conftest refer only to pytest and the
    # production library. The example addition and runner stay outside scope.
    for path in (VERIFIER, "conftest.py"):
        content = overlay.get(path, public.get(path))
        if content is None or any(marker in content for marker in (b"type_statement", b"examples/", b"examples.")):
            raise ValueError("selected verifier references the omitted demonstration")
    config = tomllib.loads(public["pyproject.toml"].decode())["project"]
    if len(set(original["FAIL_TO_PASS"] + original["PASS_TO_PASS"])) != 5:
        raise ValueError("published test identity count changed")
    summary = {**facts, "case_id": CASE, "assets": [stage_file(root, name, data) for name, data in assets.items()]}
    mapped_dir = target / "worker-transport"
    mapped = bind_row(summary, lead, mapped_dir, root.parent, lead["source_bindings"][0]["archive"])
    pinned_index = write(mapped_dir / "private-index.json", encode([mapped]))
    _, wheels = transport.wheel_probe_assets()
    task, truth, reference, baseline, _ = transport.bind(mapped, mapped_dir, wheels)
    observed = {}
    tests = {identity: "PASSED" for identity in truth.fail_to_pass + truth.pass_to_pass}
    replacements = json.loads(assets["repair.json"])
    controls = {"reference": reference, "original": baseline}
    for role, path in zip(("deserialization_only", "serialization_only"), SOURCE_FILES, strict=True):
        if not any(isinstance(node, ast.FunctionDef) for node in ast.walk(ast.parse(replacements[path]))):
            raise ValueError("partial repair no longer includes reviewed production code")
        controls[role] = compressed_patch_artifact(RepositoryPatch(base_sha256=truth.input_sha256, files={path: replacements[path]}))
    for role, artifact in controls.items():
        async def stub(payload, role=role):
            observed[role] = {"archive_sha256": payload["archive_sha256"], "payload_sha256": digest(encode(payload))}
            return {"archive_sha256": payload["archive_sha256"], "statuses": tests, "exit_code": 0,
                    "python": payload["python"], "pytest": payload["pytest"]}
        result = await transport.grade_suite_output(task.model_dump(mode="json"), truth.model_dump(mode="json"), artifact, stub)
        if role not in observed or not result.valid:
            raise ValueError("ordinary callback did not materialize the reviewed control")
    if len({row["archive_sha256"] for row in observed.values()}) != len(controls):
        raise ValueError("duplicate protected case role")
    private_controls = write(mapped_dir / "protected" / CASE / "calibration.json", encode(controls))
    return {
        "schema_version": "aeep.c13.pyserde-production-repair.v1", "publisher": "https://github.com/yukinarit/pyserde/pull/682",
        "repository": REPO, "case_id": CASE, "revision": REVISION, "publisher_tree": tree["published_tree"],
        "original_archive_sha256": tree["archive_sha256"], "publisher_patch_sha256": PR_PIN, "original_row_sha256": ROW_PIN,
        "projected_row_sha256": row_pin["sha256"], "production_files": list(SOURCE_FILES),
        "omitted_demonstration_sections": example_pins, "unchanged_published_test_identities": 5,
        "published_requires_python": config["requires-python"], "published_dependencies": config["dependencies"],
        "locked_dependency_projection": dependency_projection(public["uv.lock"]),
        "private_index_sha256": pinned_index["sha256"], "private_control_set_sha256": private_controls["sha256"],
        "ordinary_callback_payloads": observed, "capacity_projection": partition_projection(mapped),
        "evidence": "Static source and patch verification. All callback responses were substituted. Run the unchanged tests to determine reference and fault outcomes.",
        "archive_redownloads": 0, "upstream_tests_executed": 0, "model_turns": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(stage(args.output)), indent=2, sort_keys=True))
