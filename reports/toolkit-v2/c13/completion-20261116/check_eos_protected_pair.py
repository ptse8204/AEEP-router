"""Grade EOS's published repair and original through the ordinary v7 evaluator."""

import argparse
import asyncio
import json
from datetime import timedelta
from pathlib import Path

import check_eos_native_runtime as native
import check_locify_protected_pair as binding

from aeep.assessment.models import AssessmentEnvironment, content_digest
from aeep.assessment.repository_suites import (
    LARGE_PAYLOAD,
    SuiteAssetV5,
    SuiteInputV7,
    SuiteTruthV7,
    archive_files,
    compressed_patch_artifact,
)
from aeep.assessment.repository_tasks import RepositoryPatch
from aeep.models import ExecutorSpec, utc_now

NAME = "c13-eos-protected-pair-20261119"
CASE = "Akkudoktor-EOS__EOS-459"
TARGET = binding.WORK / NAME
VERIFIED_SOURCE = binding.VERIFIED_SOURCE
runner = binding.runner


def definition(image):
    case = binding.load(binding.HERE / "full-rebench-three-leads-result-20261119.json")
    known = case["cases"][CASE]
    staged = json.loads(binding.asset(case["protected_staging"]))
    row, = [item for item in staged["cases"] if item["case"] == CASE]
    source = binding.asset(row["assets"]["untouched-source"])
    tests = binding.asset(known["protected_overlay"])
    archive = archive_files(binding.asset(known["reference_archive"]), large=True)
    statement = binding.asset(known["full_statement"]).decode()
    task = SuiteInputV7(task_id=CASE, task=statement, family="energy-analysis",
                       source_sha256=binding.digest(source), editable_paths=row["source_changes"],
                       instruction_format="source-statement-v1")
    summary = binding.load(binding.WORK / "eos-exact-instruction-transport-20261119.json")
    base = content_digest(task)
    if len(statement.encode()) != 11030 or summary["task_input_sha256"] != base:
        raise ValueError("original instructions or input changed")
    source_file = TARGET / "public" / f"{task.source_sha256}.tar.gz"
    tests_file = TARGET / "protected" / "tests.tar.gz"
    for path, body in ((source_file, source), (tests_file, tests)):
        if not path.exists():
            binding.write(path, body)
        binding.read(path, binding.digest(body))
    required = json.loads(binding.asset(row["assets"]["required.json"]))
    pytest_record, = list((native.CONTEXT / "wheels").glob("pytest-8.3.4-*.whl"))
    pin = binding.load(native.REVIEW)["manifest"]["pytest"]
    truth = SuiteTruthV7(
        input_sha256=base, source=SuiteAssetV5(path=str(source_file), sha256=task.source_sha256, size_bytes=len(source)),
        tests=SuiteAssetV5(path=str(tests_file), sha256=binding.digest(tests), size_bytes=len(tests)),
        wheels=[runner.asset(pytest_record, pin)], python="3.12", pytest="8.3.4",
        pytest_plugins=["xprocess.pytest_xprocess", "time_machine", "anyio.pytest_plugin"],
        patch_encoding="gzip-json", test_roots=["tests"],
        test_paths=sorted({name.split("::")[0] for group in required.values() for name in group}),
        archive_profile="repository-v1", identity_format="pytest-native-v1", create_paths=[], **required,
    )
    item = {
        "case_id": CASE,
        "input": task.model_dump(mode="json"),
        "truth": truth.model_dump(mode="json"),
        "source_revision": known["source_revision"],
        "roles": {
            role: compressed_patch_artifact(RepositoryPatch(base_sha256=base, files=edits))
            for role, edits in (("reference", {name: archive[name].decode() for name in task.editable_paths}),
                                ("original", {}))
        },
        "reference_archive_sha256": known["reference_archive"]["sha256"],
        "existing_image_dependencies": ["68 pinned Python distributions", "two ARM64 libraries", "ordinary AEEP launcher"],
    }
    env = AssessmentEnvironment(environment_id=NAME, kind="container",
        identity={"verified_runtime": image["review_sha256"]}, network=False,
        container_image=image["image"]["id"], container_runtime=runner.DOCKER, container_socket=runner.SOCKET,
        cpu_count=2, memory_mb=1024, process_limit=128, container_tmpfs_mb=96)
    runtime = VERIFIED_SOURCE / "integrations/assessment-runtime"
    program = (runtime / "repository_suite_native_program.py").read_text().replace(
        "'__AEEP_NATIVE_CAPTURE_SOURCE__'", repr((runtime / "repository_suite_native_capture.py").read_text()))
    anchors = {
        "'PATH': '/usr/local/bin:/usr/bin:/bin'": "'PATH': '/opt/c13-eos/bin:/usr/local/bin:/usr/bin:/bin'",
        "'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'": (
            "'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'OPENBLAS_NUM_THREADS': '1', "
            "'LD_LIBRARY_PATH': '/opt/c13-eos-native'"),
        "timeout=22": "timeout=75",
    }
    for before, after in anchors.items():
        if program.count(before) != 1:
            raise ValueError("ordinary observer changed")
        program = program.replace(before, after)
    compile(program, "<EOS ordinary observer>", "exec")
    observer = ExecutorSpec(id="repository.suite.observe", capability="assessment.repository_suite@1",
        kind="command", description="Native EOS verifier, with pinned scientific dependencies and local scratch.",
        config={"argv": [native.VENV + "/bin/python", "-B", "-c", program], "argv_literal": True,
                "stdin_json": True, "timeout_seconds": 85, "max_stdin_bytes": LARGE_PAYLOAD,
                "max_output_bytes": 500_000, "output": {"type": "json"}})
    return observer, env, [item]


def configure(observed):
    if Path(binding.aeep.__file__).resolve().parents[2] != VERIFIED_SOURCE:
        raise ValueError("first protected attempt requires the frozen v7 source")
    image_path = native.TARGET / "result.json"
    image = binding.load(image_path)
    if not image["passed"]:
        raise ValueError("native carrier verification has not passed")
    observer, env, cases = definition(image)
    runner.NAME, runner.FROZEN, runner.CARRIER = NAME, VERIFIED_SOURCE, image["image"]["id"]
    runner.MAX_CALLS, runner.ROLE_SECONDS = 2, 95
    runner.REVIEW, runner.APPROVAL, runner.RUN = TARGET / "operation-review.json", TARGET / "approval.json", TARGET / "execution"
    runner.definitions = lambda: (observer, env, cases)

    def verify(reply, payload, expected, code):
        accepted = binding.BASE_PROBE(reply, payload, expected, code)
        if isinstance(reply, dict) and isinstance(reply.get("statuses"), dict):
            observed.append({"role": "original" if code else "reference", "exit": reply.get("exit_code"),
                "required_statuses": {name: reply["statuses"].get(name, "MISSING") for name in expected},
                "protected_observation_sha256": content_digest(reply), "contract_matched": accepted})
        return accepted

    async def review():
        baseline, *other = await binding.BASE_REVIEW()
        return (baseline | {
            "schema_version": "aeep.c13.eos-protected-pair.v1",
            "dispatcher_sha256": native.journal.fingerprint(Path(__file__)),
            "native_runtime_sha256": native.journal.fingerprint(image_path),
            "standing_authority_sha256": native.journal.fingerprint(binding.AUTHORITY),
            "result_scope": "Offline protected reference and original; no formal adoption.",
        }, *other)

    runner.verify_probe, runner.review_fields = verify, review


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--first-review")
    args = parser.parse_args()
    observed = []
    configure(observed)
    if args.prepare:
        record, *_ = await runner.review_fields()
        binding.write(runner.REVIEW, binding.encode(record | {"expires_at": (utc_now() + timedelta(hours=3)).isoformat()}))
        print(native.journal.fingerprint(runner.REVIEW))
        return
    exact = args.first_review
    if runner.RUN.exists() or native.journal.fingerprint(runner.REVIEW) != exact:
        raise ValueError("requires an exact unstarted protected review")
    binding.write(runner.APPROVAL, binding.encode({"approved": True, "review_sha256": exact}))
    binding.write(TARGET / "first-attempt-authority.json", binding.encode({
        "first_attempt": True, "review_sha256": exact, "authority": str(binding.AUTHORITY.relative_to(binding.ROOT)),
    }))
    try:
        raise SystemExit(0 if await runner.run(exact) else 1)
    finally:
        if runner.RUN.exists() and observed:
            binding.write(runner.RUN / "observations.json", binding.encode(observed))


if __name__ == "__main__":
    asyncio.run(main())
