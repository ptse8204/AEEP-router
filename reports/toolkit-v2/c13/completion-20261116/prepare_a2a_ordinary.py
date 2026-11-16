"""Stage an offline ordinary A2A grader using the verified private runtime closure."""

import asyncio
import base64
import hashlib
import importlib.metadata
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from audit_a2a_receipt_bridge import CASES, FIXTURES, PRIVATE, case_assets, reviewed_wheels
from check_linux_install import DOCKER, FROZEN, HERE, IMAGE, SOCKET, WORK, docker, get, put
from stage_repository_transport import read

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import AssessmentEnvironment, content_digest
from aeep.assessment.repository_suites import (
    LARGE_PAYLOAD,
    compressed_patch_artifact,
    grade_suite_output,
    pack_files,
)
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.models import ActionRequest, ExecutorSpec
from aeep_toolkit.install_runtime import file_digest

TARGET = WORK / "a2a-ordinary-grader"
SUPPORT = "/opt/aeep-a2a-native-support"
RUNTIME = FROZEN / "integrations/assessment-runtime"
CONFIG_OVERRIDE = "addopts=-ra --strict-markers"
REPO_LITERAL = "repo = Path('/tmp/aeep-repository-native-v6')"


def replace_once(source, before, after):
    if source.count(before) != 1:
        raise ValueError("ordinary observer no longer matches the adaptation point")
    return source.replace(before, after, 1)


def observer_program(support):
    native = (RUNTIME / "repository_suite_native_program.py").read_text()
    with_capture = replace_once(
        native,
        "'__AEEP_NATIVE_CAPTURE_SOURCE__'",
        repr((RUNTIME / "repository_suite_native_capture.py").read_text()),
    )
    with_runtime = replace_once(
        with_capture, "repr(wheels)", "repr([" + repr(support) + ", *wheels])"
    )
    return replace_once(
        with_runtime,
        "'no:cacheprovider', *request['test_paths']",
        "'no:cacheprovider', '-o', " + repr(CONFIG_OVERRIDE) + ", *request['test_paths']",
    )


def check_observer(program):
    """Run authored pass/fail fixtures with the same launcher and sealed output format."""
    results = {}
    node_id = "tests/test_fixture.py::test_dep"
    for role, value in (("reference", 5), ("original", 3), ("early_exit", None)):
        with TemporaryDirectory(prefix="aeep-first-party-observer-") as path:
            root = Path(path)
            support = root / "support"
            support.mkdir()
            (support / "reviewed_support.py").write_text("EXPECTED = 5\n")
            source = (
                "import os\ndef test_dep():\n    os._exit(0)\n"
                if value is None
                else f"from reviewed_support import EXPECTED\ndef test_dep():\n    assert {value} == EXPECTED\n"
            )
            archive = pack_files(
                {
                    "tests/test_fixture.py": source.encode(),
                    "pytest.py": b"raise RuntimeError('shadowed pytest runtime')",
                    "pytest.ini": b"[pytest]\naddopts = --dist loadgroup --strict-markers\n",
                }
            )
            archive_sha = hashlib.sha256(archive).hexdigest()
            payload = {
                "archive": base64.b64encode(archive).decode(),
                "archive_sha256": archive_sha,
                "python": ".".join(map(str, sys.version_info[:2])),
                "pytest": importlib.metadata.version("pytest"),
                "test_paths": ["tests/test_fixture.py"],
                "wheels": [],
            }
            local = replace_once(program, repr(SUPPORT), repr(str(support)))
            local = replace_once(local, REPO_LITERAL, f"repo = Path({str(root / 'repo')!r})")
            child = subprocess.run(
                [sys.executable, "-B", "-c", local],
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                timeout=28,
                check=False,
            )
            if value is None:
                if child.returncode == 0 or child.stdout.strip():
                    raise ValueError("terminated observer yielded a grade")
            elif child.returncode or json.loads(child.stdout) != {
                "archive_sha256": archive_sha,
                "python": payload["python"],
                "pytest": payload["pytest"],
                "exit_code": int(role == "original"),
                "statuses": {node_id: "PASSED" if role == "reference" else "FAILED"},
            }:
                raise ValueError("authored observer fixture did not match")
            results[role] = "passed"
    return results


def stage_runtime(review, context):
    prefix = "shared/support/"
    expected = {
        name.removeprefix(prefix): sha
        for name, sha in review["files"].items()
        if name.startswith(prefix)
    }
    source = FIXTURES / prefix
    entries = list(source.rglob("*"))
    if (
        any(path.is_symlink() or not (path.is_dir() or path.is_file()) for path in entries)
        or {path.relative_to(source).as_posix() for path in entries if path.is_file()}
        != expected.keys()
    ):
        raise ValueError("protected support directory inventory changed")
    support = context / "support"
    for name, sha in sorted(expected.items()):
        output = support / name
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(read(source / name, sha))
        output.chmod(0o444)
    for path in (support, *support.rglob("*")):
        if path.is_dir():
            path.chmod(0o555)
    return expected


async def stage_inputs(review, observer, environment):
    replay = get(HERE / "a2a-receipt-bridge-audit.json")
    wheels, _ = reviewed_wheels(review)
    # The image supplies the complete closure. Only the transport's required
    # pure-wheel entry remains in the payload.
    (pytest_wheel,) = [
        asset for asset in wheels if Path(asset.path).name == "pytest-8.4.1-py3-none-any.whl"
    ]
    index = get(HERE / "rebound-worker-transport.json")
    rows = json.loads(read(PRIVATE / "private-index.json", index["private_index_sha256"]))
    result = {}
    for row in rows:
        case = row["input"]["task_id"]
        if case not in CASES:
            continue
        task, oracle, reference, original, _ = case_assets(row, [pytest_wheel])
        artifacts = {"reference": reference, "original": compressed_patch_artifact(original)}
        checks = {}
        for role, artifact in artifacts.items():
            binding = f"{case}/{role}/binding.json"
            held = json.loads(read(FIXTURES / binding, review["files"][binding]))
            calls = []

            operation = f"aeep-c13-a2a-ordinary:{case}:{role}"

            async def probe(payload, held=held, calls=calls, operation=operation):
                if payload["archive_sha256"] != held["archive_sha256"]:
                    raise ValueError(
                        "ordinary callback no longer reconstructs the reviewed fixture"
                    )
                trial = ExecutionContext(
                    request=ActionRequest(
                        action_id=operation, capability=observer.capability, input=payload
                    ),
                    spec=observer,
                    estimate=observer.estimate,
                    attempt=1,
                    attempt_id=operation,
                    approved_side_effect=observer.side_effect,
                )
                argv, name = ContainerExecutor(environment).command(trial)
                path = FROZEN / "src"
                if (
                    {arg for arg in argv if arg.startswith("type=bind,")}
                    != {f"type=bind,src={path},dst={path},readonly"}
                    or argv[argv.index("--network") + 1] != "none"
                    or argv[argv.index("--user") + 1] != "65534:65534"
                    or not {
                        "--read-only",
                        "--cap-drop=ALL",
                        "--pull=never",
                        "--security-opt=no-new-privileges",
                    }
                    <= set(argv)
                ):
                    raise ValueError("reviewed grader launch escaped its boundary")
                calls.append(
                    {
                        "container": name,
                        "payload_sha256": content_digest(payload),
                        "argument_count": len(argv),
                        "archive_sha256": payload["archive_sha256"],
                    }
                )
                return {
                    "archive_sha256": payload["archive_sha256"],
                    "python": payload["python"],
                    "pytest": payload["pytest"],
                    "exit_code": held["exit_code"],
                    "statuses": held["outcomes"],
                }

            grade = await grade_suite_output(
                task.model_dump(mode="json"), oracle.model_dump(mode="json"), artifact, probe
            )
            source = replay["cases"][case]["read_only_grade_projection"][role]
            if (
                grade.quality_score != source["score"]
                or grade.detail != source["detail"]
                or len(calls) != 1
            ):
                raise ValueError("historical grade projection changed")
            checks[role] = {
                **calls[0],
                "prior_receipt_id": source["source_receipt_id"],
                "expected_score": grade.quality_score,
            }
        put(
            TARGET / f"{case}.json",
            {
                "input": task.model_dump(mode="json"),
                "truth": oracle.model_dump(mode="json"),
                "artifacts": artifacts,
            },
        )
        result[case] = checks
    if set(result) != CASES:
        raise ValueError("ordinary A2A preparation omitted a reproduced case")
    return result


async def prepare():
    report = get(HERE / "approved-a2a-batch-results.json")
    review = json.loads(read(WORK / "a2a-batch-reference-review.json", report["review_sha256"]))
    parent = json.loads(docker("image", "inspect", "--format", "{{json .}}", IMAGE))
    (tag,) = parent["RepoTags"]
    source = verification_source_digest(FROZEN)
    if (
        parent["Id"] != IMAGE
        or parent["RootFS"]["Layers"] != review["layers"]
        or parent["Os"] != "linux"
        or parent["Architecture"] != "arm64"
        or parent["Config"]["User"] != "65534:65534"
        or parent["Config"].get("Volumes")
        or parent["Config"].get("Healthcheck")
        or source != review["source"]
        or not re.fullmatch(r"[a-z0-9._/-]+:[a-zA-Z0-9._-]+", tag)
        or shutil.disk_usage(WORK).free < 52 * 1024**3
    ):
        raise ValueError("retained grader runtime, source or storage changed")
    program = observer_program(SUPPORT)
    compile(program, "<reviewed-a2a-observer>", "exec")
    authored = check_observer(program)
    TARGET.mkdir(mode=0o700)
    context = TARGET / "image"
    context.mkdir(mode=0o700)
    support = stage_runtime(review, context)
    (context / "Dockerfile").write_text(f"FROM {tag}\nCOPY support/ {SUPPORT}/\n")
    spec = ExecutorSpec(
        id="repository.suite.observe",
        capability="assessment.repository_suite@1",
        kind="command",
        description="Ordinary native observer with pinned A2A grader dependencies",
        config={
            "argv": ["python3", "-B", "-c", program],
            "argv_literal": True,
            "stdin_json": True,
            "output": {"type": "json"},
            "timeout_seconds": 30,
            "max_stdin_bytes": LARGE_PAYLOAD,
            "max_output_bytes": 500_000,
        },
    )
    environment = AssessmentEnvironment(
        environment_id="c13-a2a-native",
        kind="container",
        container_image=IMAGE,
        identity={
            "purpose": "Preparation with parent identity. Bind the derived image before launch."
        },
        container_runtime=DOCKER,
        container_socket=SOCKET,
        cpu_count=1,
        memory_mb=512,
        process_limit=96,
        container_tmpfs_mb=32,
    )
    put(TARGET / "observer.json", spec.model_dump(mode="json"))
    put(TARGET / "environment-template.json", environment.model_dump(mode="json"))
    cases = await stage_inputs(review, spec, environment)
    summary = {
        "schema_version": "aeep.c13.a2a-ordinary-preparation.v1",
        "source": source,
        "historical_review_sha256": report["review_sha256"],
        "historical_ledger_sha256": report["operation_ledger_sha256"],
        "parent_image": IMAGE,
        "parent_tag": tag,
        "parent_layers": review["layers"],
        "protected_support_files": len(support),
        "support_inventory_sha256": content_digest(support),
        "dockerfile_sha256": file_digest(context / "Dockerfile"),
        "observer_sha256": content_digest(spec),
        "environment_template_sha256": content_digest(environment),
        "execution_definition_files": {
            path.name: file_digest(path) for path in sorted(TARGET.glob("*.json"))
        },
        "historical_pytest_option_adaptation": CONFIG_OVERRIDE,
        "authored_observer_checks": authored,
        "staged_callback_checks": cases,
        "module_wide_collection_checked": False,
        "images_built": 0,
        "upstream_tests_run": 0,
        "model_turns": 0,
        "formal_cases_adopted": 0,
    }
    put(TARGET / "summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(prepare())
