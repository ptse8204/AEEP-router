"""Re-encode retained plain repository cases without running their tests."""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import (
    RepositorySuiteCase,
    archive_files,
    compressed_patch_artifact,
    decode_patch,
    grade_suite_output,
    patch_artifact,
)

ROOT = Path(__file__).resolve().parents[4]
WORK = ROOT / ".aeep/completion-20261116"
POOL = WORK.parent / "repository-future-eligible-after-usefulness-20261029/cases.json"
POOL_SHA256 = "d432f38882b0fdb75addee6e2ef1af8c0aedb82c52cd63da7eccbf55ad6e2f63"
TARGETS = {
    "fox-it__dissect.cstruct-120-single-file-scope",
    "kaste__mockito-python-93-single-file-scope",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, record):
    data = (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode()
    with path.open("xb") as file:
        file.write(data)
    return {"path": str(path), "sha256": sha(data), "size_bytes": len(data)}


async def observe(case, artifact, *, fail_test=False):
    oracle = case.truth
    payloads = []

    async def observe_payload(payload):
        payloads.append(payload)
        statuses = dict.fromkeys(oracle.fail_to_pass + oracle.pass_to_pass, "PASSED")
        if fail_test:
            statuses[oracle.pass_to_pass[0]] = "FAILED"
        return {
            "archive_sha256": payload["archive_sha256"],
            "python": payload["python"],
            "pytest": payload["pytest"],
            "exit_code": int(fail_test),
            "statuses": statuses,
        }

    result = await grade_suite_output(
        case.input.model_dump(mode="json"),
        oracle.model_dump(mode="json"),
        artifact,
        observe_payload,
    )
    return result, payloads


async def compare(old, new, plain, zipped, *, fail_test):
    def project(payloads):
        assert len(payloads) == 1
        payload = payloads[0].copy()
        payload.pop("source_modules", None)
        payload.pop("pytest_plugins", None)
        return payload

    first, plain_payload = await observe(old, plain, fail_test=fail_test)
    second, zipped_payload = await observe(new, zipped, fail_test=fail_test)
    assert first == second
    assert first.valid is (not fail_test)
    assert project(plain_payload) == project(zipped_payload)
    assert zipped_payload[0]["pytest_plugins"] == []
    assert zipped_payload[0]["source_modules"]
    return {
        "grader_archive_sha256": zipped_payload[0]["archive_sha256"],
        "same_archive_and_dependencies": True,
        "source_module_guards": zipped_payload[0]["source_modules"],
        "synthetic_grader_rejection": fail_test,
    }


async def convert(case, target):
    before = case.model_dump(mode="json")
    plain_reference = json.loads(case.reference.read())
    reference_patch = decode_patch(plain_reference)
    if (
        reference_patch.base_sha256 != case.truth.input_sha256
        or not reference_patch.files
        or not reference_patch.files.keys() <= set(case.input.editable_paths)
    ):
        raise ValueError("unexpected prior reference binding")
    source = archive_files(case.truth.source.read())
    assert all(source[name] != value.encode() for name, value in reference_patch.files.items())
    compact_reference = compressed_patch_artifact(reference_patch)
    reference = write_json(
        target / (case.independent_case_id + "-reference.json"), compact_reference
    )
    fault_outputs = list(map(compressed_patch_artifact, map(decode_patch, case.fault_outputs)))
    updated = {
        **before,
        "schema_version": "assessment.repository-suite-case.v3",
        "truth": {**before["truth"], "patch_encoding": "gzip-json", "pytest_plugins": []},
        "reference": reference,
        "fault_outputs": fault_outputs,
    }
    compact = RepositorySuiteCase.model_validate(updated)
    exact = compact.model_dump(mode="json")
    assert exact == updated
    reference_check = await compare(
        case, compact, plain_reference, compact_reference, fail_test=False
    )
    fault_checks = [
        await compare(case, compact, old_fault, new_fault, fail_test=True)
        for old_fault, new_fault in zip(case.fault_outputs, fault_outputs, strict=True)
    ]
    wrong_base = reference_patch.model_copy(update={"base_sha256": "0" * 64})
    for plan, output in (
        (case, patch_artifact(wrong_base)),
        (compact, compressed_patch_artifact(wrong_base)),
    ):
        observed, payloads = await observe(plan, output)
        assert not observed.valid and observed.detail == "input_binding" and not payloads
    return exact, {
        "case_id": case.independent_case_id,
        "revision": case.source_revision,
        "before_case_sha256": content_digest(case),
        "after_case_sha256": content_digest(compact),
        "protected_test_archive_sha256": case.truth.tests.sha256,
        "required_test_count": len(case.truth.fail_to_pass) + len(case.truth.pass_to_pass),
        "edit_scope_preserved": True,
        "reference": reference_check,
        "faults": fault_checks,
        "bad_base_rejected_before_dispatch": True,
    }


async def prepare(target):
    data = POOL.read_bytes()
    if sha(data) != POOL_SHA256:
        raise ValueError("retained pool no longer matches exact prior evidence")
    cases = json.loads(data)
    if len(cases) != 41:
        raise ValueError("retained case count changed")
    plain = [row for row in cases if row["schema_version"] == "assessment.repository-suite-case.v1"]
    if len(plain) != 2 or {row["independent_case_id"] for row in plain} != TARGETS:
        raise ValueError("unexpected plain repository cases")
    target = target.resolve()
    if target.parent != WORK.resolve():
        raise ValueError("use a fresh private output under the retained C13 workspace")
    target.mkdir(mode=0o700)
    replacements, changes = {}, []
    for raw in plain:
        old = RepositorySuiteCase.model_validate(raw)
        replacements[old.independent_case_id], evidence = await convert(old, target)
        changes.append(evidence)
    normalized = [replacements.get(row["independent_case_id"], row) for row in cases]
    assert all(row["truth"].get("patch_encoding") == "gzip-json" for row in normalized)
    assert len({row["input"]["source_sha256"] for row in normalized}) == len(normalized)
    assert all(
        old["input"] == new["input"]
        and old["split"] == new["split"]
        and old["used_for_development"] == new["used_for_development"]
        for old, new in zip(cases, normalized, strict=True)
    )
    result = write_json(target / "cases.json", normalized)
    evidence = {
        "schema_version": "aeep.c13.formal-transport-preparation.v1",
        "source_pool_sha256": POOL_SHA256,
        "prepared_pool_sha256": result["sha256"],
        "prepared_pool_relative_path": str((target / "cases.json").relative_to(ROOT)),
        "unchanged_cases": 39,
        "converted_cases": changes,
        "common_bridge_provisional_rows": len(normalized),
        "minimum_remaining_rows_before_independence_and_adoption": 141 - len(normalized),
        "grading_observations_are_synthetic": True,
        "formal_cases_adopted": 0,
        "real_executions": 0,
        "new_model_turns": 0,
    }
    write_json(target / "evidence.json", evidence)
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(prepare(parser.parse_args().output))
