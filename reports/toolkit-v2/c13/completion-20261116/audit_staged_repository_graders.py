"""Bind staged source and test assets through the ordinary grader without running them."""

import ast
import asyncio
import json
import tomllib
from collections import Counter

from audit_corpus_capacity import EXTRA_INDEXES
from packaging.specifiers import SpecifierSet
from plan_repository_expansion import HERE, ROOT, WORK, load, read
from pydantic import ValidationError
from stage_repository_transport import digest

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import (
    SuiteInput,
    SuiteTruthV6,
    archive_files,
    compressed_patch_artifact,
    grade_suite_output,
)
from aeep.assessment.repository_tasks import RepositoryPatch
from aeep.errors import ConfigurationError

ROLE_OBSERVATIONS = ("reference", "original")
BASELINE_TEST_WHEELS = (
    "pytest-8.3.5-py3-none-any.whl",
    "iniconfig-2.1.0-py3-none-any.whl",
    "packaging-25.0-py3-none-any.whl",
    "pluggy-1.6.0-py3-none-any.whl",
)


def index_paths():
    rebound = load(HERE / "rebound-worker-transport.json")
    recovered = load(HERE / "multifile-acquisition-result.json")
    name = WORK / "multifile-acquisition-static-handoff/worker-transport/private-index.json"
    yield ROOT / rebound["private_index_relative_path"], rebound["private_index_sha256"]
    yield name, recovered["private_evidence_sha256"][name.relative_to(ROOT).as_posix()]
    for filename, field in EXTRA_INDEXES:
        record = load(HERE / filename)
        yield ROOT / record[field], record[field + "_sha256"]


def asset(path, pin):
    raw = read(path, pin["sha256"])
    if len(raw) != pin["bytes"]:
        raise ValueError(f"asset size changed: {path.name}")
    return {"path": str(path), "sha256": pin["sha256"], "size_bytes": len(raw)}


def wheel_probe_assets():
    """Use an already pinned size floor for the protected payload, with no imports."""
    raw = (HERE.parent / "repository-native-identity-20261028/operation-review.json").read_bytes()
    lock = json.loads(raw)["assets"]
    root = ROOT / ".aeep/repository-replacement-runtime-20261022-wheels"
    wheels = []
    for name in BASELINE_TEST_WHEELS:
        path = root / name
        sha = lock[str(path)]
        wheels.append({"path": str(path), "sha256": sha, "size_bytes": len(read(path, sha))})
    return digest(raw), wheels


def identity_locations(truth, files):
    """Count node names absent from their named module. Inheritance can supply them."""
    declarations = {
        path: {
            node.name
            for node in ast.walk(ast.parse(files[path], filename=path))
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for path in truth.test_paths
    }
    absent = Counter()
    for identity in truth.fail_to_pass + truth.pass_to_pass:
        path, _, node = identity.partition("::")
        parts = node.partition("[")[0].split("::")
        if any(part not in declarations[path] for part in parts):
            absent[path] += 1
    return dict(absent)


def python_requirement(files):
    if "pyproject.toml" not in files:
        return {}
    project = tomllib.loads(files["pyproject.toml"].decode()).get("project", {})
    requires = project.get("requires-python")
    if requires is None:
        return {}
    return {
        "declared_requires_python": requires,
        "admits_python_3_13_0": SpecifierSet(requires).contains("3.13.0"),
    }


def bind(row, root, wheels):
    task = SuiteInput.model_validate(row["input"])
    bound = root / "protected" / task.task_id
    audit = "protected_assets" in row
    source_pin = row.get("public_source")
    source = root / "public" / (task.source_sha256 + ".tar.gz")
    if source_pin is None:
        # Audit indices bind the public archive through the frozen task input.
        source_pin = {"sha256": task.source_sha256, "bytes": source.stat().st_size}
    elif source_pin["name"] != source.name:
        raise ValueError("public archive pointer differs from the task input")
    overlay_pin = row["protected_assets"]["tests.tar.gz"] if audit else row["protected_tests"]
    required_pin = row["protected_assets"]["required.json"] if audit else row["required_identities"]
    reference_pin = row["protected_assets"]["reference.json"] if audit else row["reference"]
    required = json.loads(read(bound / "required.json", required_pin["sha256"]))
    if audit:
        issue = required["published_fail_to_pass"]
        preserve = required["published_pass_to_pass"]
        all_tests = [*issue, *preserve, row["protected_guard"]]
        if all_tests != required["protected_audit_required"]:
            raise ValueError("authored audit changed the original test identities")
        required = {"fail_to_pass": [], "pass_to_pass": all_tests}
    truth = SuiteTruthV6(
        input_sha256=content_digest(task),
        source=asset(source, source_pin),
        tests=asset(bound / "tests.tar.gz", overlay_pin),
        wheels=wheels,
        python="3.13",
        pytest="8.3.5",
        test_paths=row["test_modules"],
        test_roots=row["test_roots"],
        patch_encoding="gzip-json",
        archive_profile="repository-v1",
        identity_format="pytest-native-v1",
        **required,
    )
    public = archive_files(truth.source.read(), large=True)
    protected = archive_files(truth.tests.read(), large=True)
    if truth.source.sha256 != task.source_sha256 or any(
        public.get(name) == body for name, body in protected.items()
    ):
        raise ValueError("public source does not match its binding or exposes a protected overlay")
    if not set(truth.test_paths) <= public.keys() | protected.keys():
        raise ValueError("declared protected test module is absent")
    reference = json.loads(read(bound / "reference.json", reference_pin["sha256"]))
    if audit:
        fault_pin = row["protected_assets"]["original-source-fault.json"]
        original = json.loads(read(bound / "original-source-fault.json", fault_pin["sha256"]))
    else:
        original = compressed_patch_artifact(
            RepositoryPatch(base_sha256=truth.input_sha256, files={})
        )
    metadata = python_requirement(public)
    metadata["names_not_declared_in_selected_module"] = identity_locations(
        truth, public | protected
    )
    return task, truth, reference, original, metadata


async def observe(task, truth, artifact, *, original, audit_guard):
    expected = truth.fail_to_pass + truth.pass_to_pass
    observation = {}

    async def substitute(payload):
        observation.update(
            archive_sha256=payload["archive_sha256"],
            bytes=len(json.dumps(payload).encode()),
        )
        statuses = dict.fromkeys(expected, "PASSED")
        if original:
            statuses[audit_guard or truth.fail_to_pass[0]] = "FAILED"
        return {
            "archive_sha256": payload["archive_sha256"],
            "python": payload["python"],
            "pytest": payload["pytest"],
            "exit_code": int(original),
            "statuses": statuses,
        }

    result = await grade_suite_output(
        task.model_dump(mode="json"), truth.model_dump(mode="json"), artifact, substitute
    )
    if not observation or result.valid == original or result.quality_score != int(not original):
        raise ValueError("ordinary callback did not dispatch or grade the substituted control")
    return observation


async def audit_row(row, root, wheels):
    task, truth, reference, original, metadata = bind(row, root, wheels)
    observations = {}
    for name, artifact in zip(ROLE_OBSERVATIONS, (reference, original), strict=True):
        observations[name] = await observe(
            task, truth, artifact, original=name == "original", audit_guard=row.get("protected_guard")
        )
    if observations["reference"]["archive_sha256"] != row["reference_archive_sha256"]:
        raise ValueError("protected reference archive does not match its frozen projection")
    original_digest = observations["original"]["archive_sha256"]
    if original_digest == row["reference_archive_sha256"] or (
        "fault_archive_sha256" in row and original_digest != row["fault_archive_sha256"]
    ):
        raise ValueError("protected counterexample archive does not match the original")
    return {
        "test_identities": len(truth.fail_to_pass) + len(truth.pass_to_pass),
        **metadata,
        "reference_transport": observations["reference"],
        "original_transport": observations["original"],
    }


async def audit():
    wheel_pin, wheels = wheel_probe_assets()
    indexes, rows, origins = {}, [], set()
    for path, pin in index_paths():
        relative = path.relative_to(ROOT).as_posix()
        indexes[relative] = pin
        for row in json.loads(read(path, pin)):
            task = row["input"]
            if task["task_id"] == "a2aproject__a2a-python-472":
                continue  # Already excluded after its protected counterexample audit.
            origin = (row["source_repository"].casefold(), row["source_revision"])
            if origin in origins:
                raise ValueError("staged repository source occurs in more than one frozen index")
            origins.add(origin)
            result = {
                "case": task["task_id"],
                "family": task["family"],
                "source_revision": row["source_revision"],
                "input_index": relative,
                "public_archive_sha256": task["source_sha256"],
            }
            try:
                result.update(await audit_row(row, path.parent, wheels))
            except ValidationError as exc:
                result["transport_blocker"] = "; ".join(
                    str(error["loc"]) + " " + error["msg"]
                    for error in exc.errors(include_input=False)
                )
            except (ConfigurationError, OSError, ValueError) as exc:
                result["transport_blocker"] = str(exc).splitlines()[0]
            rows.append(result)
    return {
        "schema_version": "aeep.c13.staged-repository-graders.v1",
        "frozen_index_sha256": indexes,
        "size_probe_wheel_review_sha256": wheel_pin,
        "callback_sha256": digest((ROOT / "src/aeep/assessment/repository_suites.py").read_bytes()),
        "case_counts": dict(Counter(row["family"] for row in rows)),
        "transport_bound": sum("reference_transport" in row for row in rows),
        "transport_blocked": sum("transport_blocker" in row for row in rows),
        "verification_scope": (
            "Ordinary native callback, staged assets and a substituted probe with the pinned "
            "base pytest wheel set. A name absent from its module can be inherited or generated. "
            "Per-case dependencies and actual collection remain open."
        ),
        "upstream_tests_executed": 0,
        "formal_cases_adopted": 0,
        "cases": rows,
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(audit()), indent=2, sort_keys=True))
