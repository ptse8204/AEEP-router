"""Prepare Conan's first contained pair using the ordinary protected observer."""

import argparse
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

import repository_offline_pair_batch as runner
from audit_conan_native_selectors import CASE, INDEX, REVISION
from audit_staged_repository_graders import bind
from check_returnn_pair import FROZEN, PINNED_OBSERVER, SOURCE
from stage_conan_inherited_runtime import audit as audit_runtime
from stage_repository_transport import digest, read

import aeep
from aeep.assessment.models import AssessmentEnvironment
from aeep.assessment.repository_suites import LARGE_PAYLOAD, SuiteTruthV6
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec, utc_now
from aeep_toolkit.install_runtime import file_digest

HERE, ROOT, WORK = runner.HERE, runner.ROOT, runner.WORK
NAME = "c13-conan-protected-pair-20261118"
TARGET = WORK / NAME
REVIEW = HERE / "conan-protected-pair-review-20261118.json"
PLAN = ROOT / ".aeep/c13-conan-inherited-runtime.9xVwQC/proposed-runtime-verified.json"
PLAN_SHA = "c146663c400b9617f538be6dafd01127738c98f45a0088ba602e4f5d5894839e"
SELECTOR = HERE / "conan-native-selector-preflight-20261118.json"
SELECTOR_SHA = "b501c28e32162841f974cb8375759a6fb3da17ba6afce5978c5c303836397a8a"
BASE_REVIEW = runner.review_fields
BASE_PROBE = runner.verify_probe


def staged_inputs():
    plan = json.loads(read(PLAN, PLAN_SHA))
    if plan != audit_runtime():
        raise ValueError("the retained dependency pins or image lineage changed")
    selector = json.loads(read(SELECTOR, SELECTOR_SHA))["private_selector_binding"]
    native = json.loads(read(ROOT / selector["path"], selector["sha256"]))
    source = WORK / "repository-expansion-acquisition"
    rows = json.loads(read(source / "index.json", INDEX))
    row, = [item for item in rows if item["input"]["task_id"] == CASE]
    wheels = [{key: item[key] for key in ("path", "sha256", "size_bytes")}
              for item in plan["protected_zip_imports"]]
    task, original_truth, reference, original, _ = bind(row, source / "transport", wheels)
    truth = SuiteTruthV6.model_validate(
        native["corrected_truth"] | {"pytest": "7.4.4", "wheels": wheels}
    )
    if (truth.tests != original_truth.tests or truth.source != original_truth.source
            or truth.input_sha256 != original_truth.input_sha256
            or truth.pass_to_pass != native["native_ids"] or len(truth.pass_to_pass) != 30):
        raise ValueError("native semantics or original source binding changed")
    if truth.fail_to_pass or not {native["regression_id"], row["protected_guard"]} <= set(truth.pass_to_pass):
        raise ValueError("repair and preservation semantics are unbound")
    role_archives = {key: row[field] for key, field in (
        ("reference", "reference_archive_sha256"), ("original", "fault_archive_sha256"),
    )}
    case = {
        "case_id": CASE, "source_revision": REVISION,
        "input": task.model_dump(mode="json"), "truth": truth.model_dump(mode="json"),
        "roles": {"reference": reference, "original": original},
        "reference_archive_sha256": role_archives["reference"],
        "existing_image_dependencies": [f"{item['project']}=={item['version']}"
                                        for item in plan["image_dependencies"]],
    }
    return plan, case, {native["regression_id"], row["protected_guard"]}, role_archives


def configured(plan, case):
    if Path(aeep.__file__).resolve().parents[2] != FROZEN or verification_source_digest(FROZEN) != SOURCE:
        raise ValueError("load the exact previously verified observer source")
    runtime = FROZEN / "integrations/assessment-runtime"
    program = (runtime / "repository_suite_native_program.py").read_text().replace(
        "'__AEEP_NATIVE_CAPTURE_SOURCE__'",
        repr((runtime / "repository_suite_native_capture.py").read_text()),
    )
    if digest(program.encode()) != PINNED_OBSERVER:
        raise ValueError("ordinary protected observer differs")
    compile(program, "<protected grader source>", "exec")
    spec = ExecutorSpec(
        id="repository.suite.observe", capability="assessment.repository_suite@1", kind="command",
        description="Contained Conan compiler-detection contract grading",
        config={"argv": ["python3", "-B", "-c", program], "argv_literal": True,
                "stdin_json": True, "output": {"type": "json"}, "timeout_seconds": 30,
                "max_stdin_bytes": LARGE_PAYLOAD, "max_output_bytes": 500_000},
    )
    environment = AssessmentEnvironment(
        environment_id=NAME, kind="container", container_image=plan["carrier"],
        identity={"source": SOURCE}, container_runtime=runner.DOCKER, container_socket=runner.SOCKET,
        memory_mb=512, process_limit=96, container_tmpfs_mb=64, network=False,
    )
    return spec, environment, [case]


def verify_probe(reply, payload, expected, code):
    return BASE_PROBE(reply, payload, expected, code) and reply["statuses"] == expected


def select_attempt():
    plan, case, faults, role_archives = staged_inputs()

    def expected_statuses(truth, role):
        expected = dict.fromkeys(truth["pass_to_pass"], "PASSED")
        if role == "original":
            expected.update(dict.fromkeys(faults, "FAILED"))
        return expected

    async def review_fields():
        fields, spec, environment, cases = await BASE_REVIEW()
        for observation, role in zip(fields["launches"], runner.ROLES, strict=True):
            if observation["required_tests"] != 30 or observation["archive_sha256"] != role_archives[role]:
                raise ValueError("preflight overlaid unexpected archive or test inventory")
        return fields | {
            "schema_version": "aeep.c13.conan-protected-pair.v1",
            "purpose": "Verify the intact 30-case compiler-detection audit on two protected source snapshots",
            "wrapper_sha256": file_digest(Path(__file__)), "exact_runtime_plan_sha256": PLAN_SHA,
            "native_selector_evidence_sha256": SELECTOR_SHA,
            "original_expected_failure_count": len(faults),
            "collection_and_import_policy": "Ordinary pytest imports and native collection run within each protected call. Accept only the exact reviewed identity and status inventory.",
            "minimum_host_free_bytes": 52 * 1024**3, "installations": 0,
            "comparisons_paused": True, "waza_excluded": True,
        }, spec, environment, cases

    runner.NAME, runner.FROZEN, runner.CARRIER = NAME, FROZEN, plan["carrier"]
    runner.REVIEW, runner.RUN, runner.APPROVAL = REVIEW, TARGET / "execution", TARGET / "approval.json"
    runner.MAX_CALLS = 2
    runner.definitions = lambda: configured(plan, case)
    runner.review_fields, runner.expected_statuses, runner.verify_probe = review_fields, expected_statuses, verify_probe


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--prepare", action="store_true")
    actions.add_argument("--verify")
    actions.add_argument("--exact-review")
    args = parser.parse_args()
    select_attempt()
    if args.exact_review:
        raise SystemExit(0 if await runner.run(args.exact_review) else 1)
    fields, *_ = await runner.review_fields()
    if args.prepare:
        if REVIEW.exists() or TARGET.exists():
            raise ValueError("review or attempt already exists")
        TARGET.mkdir(mode=0o700)
        runner.put(REVIEW, fields | {"expires_at": (utc_now() + timedelta(days=7)).isoformat()})
    else:
        document = runner.get(REVIEW)
        expiry = document["expires_at"]
        if (file_digest(REVIEW) != args.verify or document != fields | {"expires_at": expiry}
                or datetime.fromisoformat(expiry) <= utc_now()):
            raise ValueError("reviewed plan changed or expired")
    print(file_digest(REVIEW))


if __name__ == "__main__":
    asyncio.run(main())
