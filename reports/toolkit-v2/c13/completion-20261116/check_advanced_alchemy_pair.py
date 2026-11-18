"""Run one isolated Advanced Alchemy collection and reference/original pair."""

import argparse
import asyncio
import base64
import json
import re
import shutil
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import repository_offline_pair_batch as runner
from acquire_larger_multifile_source import AUTHORITY, CASE, SCOPE, binding
from audit_staged_repository_graders import bind, wheel_probe_assets
from stage_advanced_alchemy_unit_grader import BASE, INDEX_PIN, TARGET
from stage_repository_transport import HERE, ROOT, digest, read

import aeep
from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentLimits,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.repository_suites import LARGE_PAYLOAD, SuiteTruthV6, grade_suite_output
from aeep.assessment.verification import verification_source_digest
from aeep.errors import ConfigurationError
from aeep.models import ExecutionReceipt, ExecutorSpec, utc_now
from aeep.store import ReceiptStore

FROZEN = SCOPE.parent.parent / "c13-document-archive-verification.wvK9pP/source"
SOURCE = "e060413cc2af11fd3c967384ad908026d8e8d467aaa430729ae28462b4f5afc7"
NAME = "aeep-c13-advanced-alchemy-protected-unit-20261118"
REPORT = HERE / "advanced-alchemy-import-tree-20261118.json"
REPORT_PIN = "82a517599c59576277b932d0ac60e5fad5ae98390d8a832f59f552275d47bb13"
REVIEW = SCOPE / "protected-pair-review.json"
APPROVAL = SCOPE / "protected-pair-authority.json"
RUN = SCOPE / "protected-pair-execution"
STAGED = TARGET / "import-only-files/libraries"
ROLES = ("collection", "reference", "original")
PLUGINS = ["pytest_asyncio.plugin", "pytest_lazy_fixtures.plugin", "pytest_mock", "xdist.plugin"]
SECONDS = 65
FREE = 52 * 1024**3

BOOT_PROBE = """
import importlib.metadata as metadata
import platform
from pathlib import Path

library = Path(LIBS)
assert os.getuid() == os.getgid() == 65534
assert platform.machine() == 'aarch64' and not os.access(library, os.W_OK)
for name, version in DISTRIBUTIONS.items():
    item = metadata.distribution(name)
    assert item.version == version and Path(item.locate_file('')).resolve() == library
for name in ('numpy._core._multiarray_umath', 'greenlet._greenlet', 'msgspec._core',
             'pydantic_core._pydantic_core', 'markupsafe._speedups', 'sqlalchemy', 'alembic'):
    module = importlib.import_module(name)
    assert Path(module.__file__).resolve().is_relative_to(library)
"""


def pin(ref):
    return read(ROOT / ref["path"], ref["sha256"])


def bind_tree():
    doc = json.loads(read(REPORT, REPORT_PIN))
    intake = json.loads(pin(doc["intake_review"]))
    native = json.loads(pin(doc["staged_result"]))
    tree = json.loads(pin(doc["read_only_tree_check"]))
    if (
        ROOT / native["staged_libraries"] != STAGED
        or len(tree) != 2144
        or sum(row["bytes"] for row in tree) != native["bytes"]
        or {row["path"] for row in tree}
        != {path.relative_to(STAGED).as_posix() for path in STAGED.rglob("*") if path.is_file()}
    ):
        raise ValueError("staged native wheel tree differs")
    for row in tree:
        path = STAGED / row["path"]
        if path.stat().st_mode & 0o777 != 0o444 or len(read(path, row["sha256"])) != row["bytes"]:
            raise ValueError("staged native file changed")
    return intake


def observer(versions):
    runtime = FROZEN / "integrations/assessment-runtime"
    program = (runtime / "repository_suite_native_program.py").read_text()
    substitutions = {
        "'__AEEP_NATIVE_CAPTURE_SOURCE__'": repr(
            (runtime / "repository_suite_native_capture.py").read_text()
        ),
        "OPERATOR_REVIEW = False": "OPERATOR_REVIEW = True",
        "wheels = []": f"wheels = [{str(STAGED)!r}]",
        "+ ';import pytest;": "+ "
        + repr(
            ";exec("
            + repr(
                BOOT_PROBE.replace("LIBS", repr(str(STAGED))).replace(
                    "DISTRIBUTIONS", repr(versions)
                )
            )
            + ")"
        )
        + "\n            + ';import pytest;",
        "+ ';Path(' + repr(str(events))": '+ \';assert "advanced_alchemy" in sys.modules or code != 0;assert "advanced_alchemy" not in sys.modules or Path(sys.modules["advanced_alchemy"].__file__).resolve().is_relative_to(Path.cwd())\'\n            + \';Path(\' + repr(str(events))',
        "'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'": "'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'OPENBLAS_NUM_THREADS': '1'",
        "timeout=22, check=False": "timeout=50, check=False",
        "assert log.stat().st_size <= 500_000 and events.is_file()": "if not events.is_file():\n"
        "            tail = base64.b64encode(log.read_bytes()[-8192:]).decode('ascii')\n"
        "            return {'bootstrap_exit': child.returncode, 'failure_log_tail_b64': tail}\n"
        "        assert log.stat().st_size <= 500_000 and events.is_file()",
    }
    for old, new in substitutions.items():
        if program.count(old) != 1:
            raise ValueError("upstream observer modification target drifted")
        program = program.replace(old, new)
    compile(program, "<Advanced Alchemy protected observer>", "exec")
    return program


def launch(executor, spec, role, payload):
    request = payload | ({"collect_only": True} if role == "collection" else {})
    ctx = runner.context(spec, NAME + ":" + role, request)
    argv, owner = executor.command(ctx)
    mounts = {f"type=bind,src={root},dst={root},readonly" for root in (FROZEN / "src", STAGED)}
    if (
        {item for item in argv if item.startswith("type=bind,")} != mounts
        or argv[argv.index("--network") + 1] != "none"
        or argv[argv.index("--user") + 1] != "65534:65534"
        or argv[argv.index("--tmpfs") + 1] != "/tmp:rw,noexec,nosuid,nodev,size=64m"
        or not {
            "--rm",
            "--pull=never",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
        }
        <= set(argv)
    ):
        raise ValueError("protected grader containment differs")
    return ctx, {
        "container": owner,
        "argv_sha256": content_digest({"argv": argv}),
        "payload_sha256": content_digest(request),
        "archive_sha256": request["archive_sha256"],
    }


def verify_source():
    if (
        Path(aeep.__file__).resolve().parents[2] != FROZEN
        or verification_source_digest(FROZEN) != SOURCE
    ):
        raise ValueError("use the reviewed coordinator")


async def prepare():
    verify_source()
    intake = bind_tree()
    (row,) = json.loads(read(BASE / "index.json", INDEX_PIN))
    versions = {item["project"]: item["version"] for item in intake["wheel_results_read_only"]}
    transport_pytest = next(
        item for item in intake["wheel_results_read_only"] if item["project"] == "pytest"
    )
    task, previous, reference, original, _ = bind(row, BASE / "transport", wheel_probe_assets()[1])
    archive = pin(intake["projection"])
    if task.task_id != CASE or len(previous.fail_to_pass) != 3 or len(previous.pass_to_pass) != 171:
        raise ValueError("required protected test contract differs")
    truth = SuiteTruthV6.model_validate(
        previous.model_dump(mode="json")
        | {
            "tests": {
                "path": str(ROOT / intake["projection"]["path"]),
                "sha256": intake["projection"]["sha256"],
                "size_bytes": len(archive),
            },
            "wheels": [
                {
                    "path": str(ROOT / transport_pytest["path"]),
                    "sha256": transport_pytest["sha256"],
                    "size_bytes": transport_pytest["bytes"],
                }
            ],
            "pytest": versions["pytest"],
            "pytest_plugins": PLUGINS,
        }
    ).model_dump(mode="json")
    spec = ExecutorSpec(
        id="repository.suite.advanced-alchemy",
        capability="assessment.repository_suite@1",
        kind="command",
        description="Protected Advanced Alchemy native unit verifier",
        config={
            "argv": ["python3", "-B", "-c", observer(versions)],
            "argv_literal": True,
            "stdin_json": True,
            "max_stdin_bytes": LARGE_PAYLOAD,
            "max_output_bytes": 500_000,
            "timeout_seconds": 60,
            "output": {"type": "json"},
        },
    )
    env = AssessmentEnvironment(
        environment_id=NAME,
        kind="container",
        container_image=runner.CARRIER,
        network=False,
        container_runtime=runner.DOCKER,
        container_socket=runner.SOCKET,
        read_only_roots=[str(STAGED)],
        memory_mb=768,
        container_tmpfs_mb=64,
        process_limit=96,
        identity={"source": SOURCE, "import_tree": REPORT_PIN},
    )
    executor = ContainerExecutor(env)
    payload = {}
    inputs = task.model_dump(mode="json")
    for role, output in (("reference", reference), ("original", original)):

        async def record(values, role=role):
            payload[role] = values
            summary = {key: values[key] for key in ("archive_sha256", "python", "pytest")}
            return summary | {
                "exit_code": int(role == "original"),
                "statuses": runner.expected_statuses(truth, role),
            }

        grade = await grade_suite_output(inputs, truth, output, record)
        assert grade.quality_score == float(role == "reference")
    payload["collection"] = payload["reference"]
    launches = {role: launch(executor, spec, role, payload[role])[1] for role in ROLES}
    report = {
        "schema_version": "aeep.c13.advanced-alchemy-protected-pair.v1",
        "driver": binding(Path(__file__)),
        "authority_basis": binding(AUTHORITY),
        "import_tree": binding(REPORT),
        "source_verification_sha256": SOURCE,
        "docker_sha256": runner.file_digest(Path(runner.DOCKER)),
        "carrier_layers": runner.inspect_carrier(),
        "environment": env.model_dump(mode="json"),
        "observer_sha256": content_digest(spec),
        "case": CASE,
        "test_counts": {"issue": 3, "preservation": 171},
        "launches": launches,
        "maximum_operations": len(ROLES),
        "maximum_seconds": SECONDS * len(ROLES),
        "required_host_free_bytes": FREE,
        "automatic_retries": 0,
        "installs": 0,
        "downloads": 0,
        "builds": 0,
        "model_turns": 0,
        "cash_usd": 0,
        "comparisons_paused": True,
        "waza_excluded": True,
    }
    return (
        report,
        executor,
        spec,
        inputs,
        truth,
        {"reference": reference, "original": original},
        payload,
    )


def inspect(role, reply, payload, truth):
    if not isinstance(reply, dict):
        return False, None, {}
    category = {}
    tail = reply.get("failure_log_tail_b64")
    if isinstance(tail, str) and len(tail) <= 12_000:
        text = base64.b64decode(tail, validate=True).decode(errors="replace")
        category["log_sha256"] = digest(text.encode())
        missing = re.findall(r"No module named ['\"]([A-Za-z_][A-Za-z_0-9.]{0,78})['\"]", text)
        if missing:
            category["missing_import_modules"] = sorted(set(missing))
        category["failure_classes"] = sorted(
            set(re.findall(r"(?m)^([A-Z][A-Za-z_0-9]{0,60}(?:Error|Exception))(?::|$)", text))
        )
    expected = runner.expected_statuses(truth, role)
    if role == "collection":
        native = reply.get("collection", {})
        ids = native.get("selected_ids", [])
        facts = {
            "collected": len(ids),
            "required_collected": len(set(ids) & expected.keys()),
            "exit_code": native.get("exit_code"),
            "bootstrap_exit": reply.get("bootstrap_exit"),
        }
        accepted = (
            native.get("exit_code") == 0
            and len(ids) == len(set(ids)) <= 10_000
            and set(ids) == set(native.get("native_ids", []))
            and expected.keys() <= set(ids)
            and all(
                native.get(key) == payload[key] for key in ("archive_sha256", "python", "pytest")
            )
        )
        return accepted, native, facts | category
    evaluation = reply.get("evaluation", {})
    accepted = runner.verify_probe(evaluation, payload, expected, int(role == "original"))
    statuses = evaluation.get("statuses", {})
    facts = {
        "exit_code": evaluation.get("exit_code"),
        "required_status_counts": dict(Counter(statuses.get(node, "MISSING") for node in expected)),
        "required_unexpected": sum(
            statuses.get(node) != outcome for node, outcome in expected.items()
        ),
        "bootstrap_exit": reply.get("bootstrap_exit"),
    }
    return accepted, evaluation, facts | category


async def dispatch(review, executor, spec, inputs, truth, outputs, payload, exact):
    RUN.mkdir(mode=0o700)
    scope = runner.Scope(review_sha256=exact)
    fingerprint = content_digest(scope)
    request = RecipeMaterializationRequest(
        plan_id=NAME,
        authorization_id=NAME,
        subject_digest=fingerprint,
        recipe_digest=fingerprint,
        mapping_digest=fingerprint,
        environment_digest=fingerprint,
        definition_digests=[fingerprint],
        seed=0,
    )
    budget = AssessmentAuthorization(
        authorization_id=NAME,
        subject_digests=[fingerprint],
        recipe_digests=[fingerprint],
        environment_digests=[fingerprint],
        allowed_destinations=["local"],
        remote_disclosure=False,
        expires_at=review["expires_at"],
        limits=AssessmentLimits(
            max_operations=len(ROLES), max_elapsed_seconds=SECONDS * len(ROLES)
        ),
    )
    records = []
    with ReceiptStore(RUN / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        repo.put("c13_advanced_alchemy_scope", fingerprint, scope)
        repo.approve_bundle(budget, {fingerprint: scope.model_dump(mode="json")})
        try:
            for role in ROLES:
                if digest(REVIEW.read_bytes()) != exact or shutil.disk_usage(SCOPE).free < FREE:
                    raise RuntimeError("review or storage changed before dispatch")
                bind_tree()
                ctx, identity = launch(executor, spec, role, payload[role])
                owner = identity["container"]

                def existing(owner=owner):
                    return runner.docker("ps", "-aq", "--filter", f"name=^/{owner}$")

                if identity != review["launches"][role] or existing():
                    raise ValueError(
                        "protected launch scope changed or its container already exists"
                    )
                operation = ctx.attempt_id
                assert operation
                repo.reserve(
                    request,
                    operation,
                    AssessmentLimits(max_operations=1, max_elapsed_seconds=SECONDS),
                    stage="protected_unit_reproduction",
                    require_settled_plan=True,
                )
                start, clock = utc_now(), time.monotonic()
                raw = await executor.execute(ctx)
                if existing():
                    raise RuntimeError("container absence uncertain; preserve the reservation")
                accepted, response, notes = inspect(role, raw.output, payload[role], truth)
                accepted = raw.status.value == "success" and accepted
                metadata = {
                    "review_sha256": exact,
                    "owned_container_absent": True,
                    "role": role,
                    "summary": notes,
                }
                if accepted:
                    metadata["protected_observation_sha256"] = content_digest(response)
                receipt = ExecutionReceipt(
                    decision_id=operation,
                    action_id=operation,
                    capability=spec.capability,
                    executor_id=spec.id,
                    executor_kind=spec.kind,
                    status="success" if accepted else "failed",
                    execution_success=accepted,
                    started_at=start,
                    ended_at=utc_now(),
                    estimated=ctx.estimate,
                    actual_resources=raw.resources,
                    error_type=None if accepted else raw.error_type or "OBSERVATION_MISMATCH",
                    metadata=metadata,
                )
                store.save_receipt(receipt)
                repo.finish_operation(
                    operation, elapsed_seconds=time.monotonic() - clock, resources=raw.resources
                )
                runner.put(RUN / (role + "-receipt.json"), receipt.model_dump(mode="json"))
                record = {
                    "role": role,
                    "receipt_id": receipt.receipt_id,
                    "verified": accepted,
                    "error": receipt.error_type,
                    "summary": notes,
                }
                records.append(record)
                if not accepted:
                    break
                if role == "collection":
                    continue

                async def replay(values, role=role, response=response):
                    if values != payload[role]:
                        raise ConfigurationError("verified observation belongs to another payload")
                    return response

                grade = await grade_suite_output(inputs, truth, outputs[role], replay)
                if grade.quality_score != float(role == "reference"):
                    raise RuntimeError("canonical verdict differs from the reviewed contract")
                record["score"] = grade.quality_score
        finally:
            await executor.close()
            runner.put(RUN / "ledger.json", repo.operation_ledger(NAME).model_dump(mode="json"))
    result = {
        "review_sha256": exact,
        "observations": records,
        "verified": len(records) == len(ROLES) and all(row["verified"] for row in records),
        "models": 0,
        "cash_usd": 0,
        "formal_cases_adopted": 0,
    }
    runner.put(RUN / "result.json", result)
    return result


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--exact-review")
    args = parser.parse_args()
    report, *args_for_dispatch = await prepare()
    if args.prepare:
        runner.put(REVIEW, report | {"expires_at": (utc_now() + timedelta(days=7)).isoformat()})
        print(digest(REVIEW.read_bytes()))
        return
    saved = json.loads(read(REVIEW, args.exact_review))
    authority = json.loads(APPROVAL.read_bytes())
    expiry = saved["expires_at"]
    if (
        saved != (report | {"expires_at": expiry})
        or authority["exact_review_sha256"] != args.exact_review
        or datetime.fromisoformat(expiry) <= utc_now()
        or RUN.exists()
        or shutil.disk_usage(SCOPE).free < FREE
    ):
        raise ValueError("exact unstarted authority, scope or storage differs")
    outcome = await dispatch(saved, *args_for_dispatch, args.exact_review)
    print(json.dumps(outcome, indent=2))
    if not outcome["verified"]:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
