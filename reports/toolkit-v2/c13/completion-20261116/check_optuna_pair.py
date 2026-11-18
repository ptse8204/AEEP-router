"""Verify Optuna's pinned sampler audit with the retained offline grader."""

import argparse
import asyncio
import json
import tomllib
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import repository_offline_pair_batch as runner
from audit_staged_repository_graders import bind
from check_expansion_contracts import inspect_wheel
from check_returnn_pair import CARRIER, FROZEN, PINNED_OBSERVER, SOURCE
from packaging.utils import canonicalize_name
from stage_conan_inherited_runtime import check_closure, image_lineage, wheel_metadata
from stage_repository_transport import HERE, ROOT, WORK, digest, read

import aeep
from aeep.assessment.models import AssessmentEnvironment
from aeep.assessment.repository_suites import LARGE_PAYLOAD, archive_files
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec, utc_now

NAME = "c13-optuna-protected-pair-20261118"
CASE = "optuna__optuna-6428-aeep-contract-audit"
REVISION = "52f6ef6ffe5a2a4c6386f8d83cd39335d7f3a2ae"
TARGET = WORK / NAME
REVIEW = HERE / "optuna-protected-pair-review-20261118.json"
ASSETS = ROOT / ".aeep/c13-optuna-runtime.qorIpf"
ARTIFACTS = "621f14637a1157eb35091b00b8a3bdf7f5b86303658d220ffd1cc792cfffaed3"
INDEX = "36667d01dde573c5754894f99b13d061500eead71d0816cfc00970a5faf3fe86"
INHERITED = (
    ("repository-replacement-runtime-20261022", "runtime-wheel-review.json",
     "17fee7b95a861079738b743d258b12e52a0901048e755bd2a4d291337b73e513",
     "1af99d1b3226e82f346327308d7e50006babae96bdd1ecf616d9c51a222dc6d1",
     {"numpy", "packaging", "pyyaml", "pytest", "pluggy", "iniconfig", "tqdm", "typing-extensions"}),
    ("repository-independent-sources-20261024", "runtime-install-review.json",
     "dbe2f153b0bb855015adb89c60006df86a44c7572ac7e69a0b5e5d9cd90f36ac",
     "249c5f9652904225fc1a35581ca96ef8cc7dee8893f94df70beee578f82f5049", {"sqlalchemy", "greenlet"}),
    ("repository-test-roots-20261027", "runtime-support-review.json",
     "6354820f5e0f9664def4a4a245e3f52cbcdb9da76b3b0ee17a55b6b0a37da5dd",
     "165e2b6c14f6f65271848b605c496eeef49abae41fccea3f37d2a54bf082aa09", {"markupsafe"}),
)
LARGE = HERE.parent / "repository-large-archives-20261027"
LARGE_REVIEW = "32bf5845ef8d1c9208fe6b251d4255538fb817941c11b58d407297e57794d0eb"
BASE_REVIEW, BASE_PROBE = runner.review_fields, runner.verify_probe


def inherited_inventory():
    inventory, images = [], []
    for name, manifest, build_pin, manifest_pin, projects in INHERITED:
        folder = HERE.parent / name
        build = json.loads(read(folder / "build-result.json", build_pin))
        if not all(build[key] for key in ("passed", "parent_layers_verified", "inherited_config_verified")):
            raise ValueError("retained runtime build did not verify")
        images.append(build["image_id"])
        catalog = json.loads(read(folder / manifest, manifest_pin))
        wheels = [row for row in catalog["pins"] if canonicalize_name(row["project"]) in projects]
        if len(wheels) != len(projects):
            raise ValueError("runtime inventory differs")
        inventory.extend(wheel_metadata(ROOT / row["private_cache"], row["sha256"],
                                        row["size_bytes"]) for row in wheels)
    build = json.loads(read(LARGE / "build-result.json", "d3dceb540ad0465f927f3b1db97cc3a8430dfd877355c395e843db144d419ced"))
    if (build["image_id"] != CARRIER or build["parent_review_sha256"] != LARGE_REVIEW
            or not all(build[key] for key in ("passed", "parent_layers_verified", "inherited_config_verified"))):
        raise ValueError("SciPy carrier differs from the reviewed build")
    scipy = json.loads(read(LARGE / "runtime-review.json", LARGE_REVIEW))["pending_wheel_fetch"]
    fetch = json.loads(read(LARGE / "wheel-fetch-result.json", "f9f51f19bdc0a36def7f200f70335f26aed97afe26b0171cda6d5786d13500b2"))
    if scipy["sha256"] != fetch["sha256"]:
        raise ValueError("SciPy acquisition changed")
    inventory.append(wheel_metadata(Path(fetch["artifact"]), scipy["sha256"], scipy["size_bytes"]))
    return inventory, image_lineage([*images, CARRIER])


def staged_inputs():
    cache = WORK / "repository-expansion-acquisition"
    row, = [x for x in json.loads(read(cache / "index.json", INDEX)) if x["input"]["task_id"] == CASE]
    if row["source_revision"] != REVISION:
        raise ValueError("publisher revision differs")
    artifact_result = json.loads(read(ASSETS / "artifact-result.json", ARTIFACTS))
    artifacts = artifact_result["artifacts"]
    if set(artifacts) != {"alembic", "colorlog", "mako"}:
        raise ValueError("three exact portable artifacts required")
    portable = []
    for project, saved in sorted(artifacts.items()):
        path = ROOT / saved["path"]
        if inspect_wheel(path, project, saved["sha256"], saved["version"]) != saved:
            raise ValueError("portable wheel review differs")
        portable.append(wheel_metadata(path, saved["sha256"], saved["size_bytes"]))
    wheels = [{key: item[key] for key in ("path", "sha256", "size_bytes")} for item in portable]
    task, truth, reference, original, checks = bind(row, cache / "transport", wheels)
    inherited, layers = inherited_inventory()
    target = {
        "python_version": "3.13", "python_full_version": "3.13.15", "sys_platform": "linux",
        "platform_system": "Linux", "platform_machine": "aarch64", "platform_python_implementation": "CPython",
    }
    files = archive_files(truth.source.read(), large=True)
    project = tomllib.loads(files["pyproject.toml"].decode())["project"]
    if not checks["admits_python_3_13_0"] or checks["names_not_declared_in_selected_module"]:
        raise ValueError("declared test coverage or Python contract differs")
    closure = check_closure([*project["dependencies"], "pytest==8.3.5", "scipy==1.15.3"],
                            inherited, portable, target)
    roles = {"reference": row["reference_archive_sha256"], "original": row["fault_archive_sha256"]}
    required = json.loads(read(cache / "transport/protected" / CASE / "required.json",
                               row["protected_assets"]["required.json"]["sha256"]))
    faults = {*required["published_fail_to_pass"], row["protected_guard"]}
    if len(truth.pass_to_pass) != 19 or truth.fail_to_pass or len(faults) != 2:
        raise ValueError("sampler and preservation obligations differ")
    case = {
        "case_id": CASE, "source_revision": REVISION, "input": task.model_dump(mode="json"),
        "truth": truth.model_dump(mode="json"), "roles": {"reference": reference, "original": original},
        "reference_archive_sha256": roles["reference"],
        "existing_image_dependencies": [f"{item['project']}=={item['version']}" for item in inherited],
    }
    return case, closure, layers, roles, faults


def select_pair(diagnostics=None):
    if (Path(aeep.__file__).resolve().parents[2] != FROZEN
            or verification_source_digest(FROZEN) != SOURCE):
        raise ValueError("load the reviewed coordinator archive")
    case, closure, layers, roles, faults = staged_inputs()
    runtime = FROZEN / "integrations/assessment-runtime"
    program = (runtime / "repository_suite_native_program.py").read_text().replace(
        "'__AEEP_NATIVE_CAPTURE_SOURCE__'", repr((runtime / "repository_suite_native_capture.py").read_text()),
    )
    if digest(program.encode()) != PINNED_OBSERVER:
        raise ValueError("protected native observer changed")
    spec = ExecutorSpec(
        id="repository.suite.observe", capability="assessment.repository_suite@1", kind="command",
        description="Contained Optuna sampler audit grader",
        config={"argv": ["python3", "-B", "-c", program], "argv_literal": True, "stdin_json": True,
                "output": {"type": "json"}, "timeout_seconds": 30, "max_stdin_bytes": LARGE_PAYLOAD,
                "max_output_bytes": 500_000},
    )
    env = AssessmentEnvironment(
        environment_id=NAME, kind="container", container_image=CARRIER, identity={"source": SOURCE},
        container_runtime=runner.DOCKER, container_socket=runner.SOCKET,
        memory_mb=512, process_limit=96, container_tmpfs_mb=64, network=False,
    )

    def expected(truth, role):
        states = dict.fromkeys(truth["pass_to_pass"], "PASSED")
        if role == "original":
            states.update(dict.fromkeys(faults, "FAILED"))
        return states

    def verify(reply, payload, statuses, code):
        matched = BASE_PROBE(reply, payload, statuses, code)
        if diagnostics is not None and isinstance(reply, dict):
            allowed = {"PASSED", "FAILED", "ERROR", "SKIPPED", "XFAIL"}
            values = reply.get("statuses")
            if (type(reply.get("exit_code")) is int and isinstance(values, dict) and len(values) <= 10000
                    and all(type(state) is str and state in allowed for state in values.values())):
                diagnostics.append({
                    "role": "original" if code else "reference",
                    "exit_code": reply["exit_code"], "observed_counts": dict(Counter(values.values())),
                    "required_status_matches": sum(values.get(name) == value for name, value in statuses.items()),
                    "required_status_count": len(statuses), "contract_matched": matched,
                })
        return matched

    async def review_fields():
        scope, *_ = await BASE_REVIEW()
        if any(launch["required_tests"] != 19 or launch["archive_sha256"] != roles[role]
               for launch, role in zip(scope["launches"], runner.ROLES, strict=True)):
            raise ValueError("reviewed protected role changed")
        return scope | {
            "schema_version": "aeep.c13.optuna-protected-pair.v1",
            "wrapper_sha256": runner.file_digest(Path(__file__)),
            "first_portable_artifact_result_sha256": ARTIFACTS,
            "dependency_closure": closure, "verified_inherited_roots": layers,
            "failed_reply_retention": "Bounded status counts and exit code only",
            "minimum_host_free_bytes": 52 * 1024**3, "comparisons_paused": True, "waza_excluded": True,
        }, spec, env, [case]

    runner.NAME, runner.TARGET, runner.REVIEW = NAME, TARGET, REVIEW
    runner.RUN, runner.APPROVAL, runner.MAX_CALLS = TARGET / "execution", TARGET / "approval.json", 2
    runner.FROZEN, runner.CARRIER = FROZEN, CARRIER
    runner.definitions = lambda: (spec, env, [case])
    runner.review_fields, runner.expected_statuses, runner.verify_probe = review_fields, expected, verify


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--verify")
    modes.add_argument("--exact-review")
    args = parser.parse_args()
    diagnostics = [] if args.exact_review else None
    select_pair(diagnostics)
    if args.exact_review:
        passed = await runner.run(args.exact_review)
        runner.put(runner.RUN / "status-counts.json", diagnostics)
        raise SystemExit(0 if passed else 1)
    scope, *_ = await runner.review_fields()
    if args.prepare:
        if REVIEW.exists() or TARGET.exists():
            raise ValueError("existing reviewed artifacts must be preserved")
        TARGET.mkdir(mode=0o700)
        runner.put(REVIEW, scope | {"expires_at": (utc_now() + timedelta(days=7)).isoformat()})
    else:
        previous = runner.get(REVIEW)
        expiry = previous["expires_at"]
        if (args.verify != runner.file_digest(REVIEW) or scope | {"expires_at": expiry} != previous
                or datetime.fromisoformat(expiry) <= utc_now()):
            raise ValueError("review differs or expired")
    print(runner.file_digest(REVIEW))


if __name__ == "__main__":
    asyncio.run(main())
