"""Run a grouped, offline protected check on retained software revisions."""

import argparse
import asyncio
import json
import os
from collections import Counter
from datetime import timedelta
from pathlib import Path

import check_eos_case_repair as checked
import check_staged_offline_cases as staged
import repository_offline_pair_batch as runner
from audit_software_carrier_coverage import expected_rows
from audit_staged_repository_graders import bind, index_paths, wheel_probe_assets
from check_linux_install import HERE, ROOT, get, put
from plan_repository_expansion import previous_repositories, repository
from rebind_intake_stack import CURRENT_SOURCE
from stage_repository_transport import read

from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentLimits,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.repository_suites import LARGE_PAYLOAD, archive_files, grade_suite_output
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import file_digest
from aeep_toolkit.stack_verification import ROOT as SOURCE_ROOT

NAME = "c13-software-cohort-batch-20261124"
WORK = ROOT / ".aeep/c13-cohort-batch-20261124/software-pinned-carrier"
PARAM = "holoviz__param-1073"
BIRD = "joshuadavidthomas__django-bird-239"
BUILD_AUDIT = "pypa__build-1027-aeep-contract-audit"
TARGETS = (PARAM, BIRD)
BASE_EXPECTED = runner.expected_statuses
AUDIT_GUARDS = {}
COLLECT = False
BACKEND = False
BUILD_SUBPROCESS_PATHS = False
LOCK_DIR = runner.WORK / "a2a-offline-assets"
GUARDIAN = runner.WORK / "c13-django-guardian-protected-audit-20261118/operation-review.json"
OLD_FIELDS = runner.review_fields


def definitions():
    if verification_source_digest(SOURCE_ROOT) != CURRENT_SOURCE:
        raise ValueError("expected the verified current source")
    _, core = wheel_probe_assets()
    prior = get(runner.WORK / "a2a-protected-reference-review.json")
    lock = json.loads(read(LOCK_DIR / "wheel-lock.json", prior["wheel_lock_sha256"]))
    pinned = {
        name: runner.asset(ROOT / row["path"], row["sha256"])
        for name, row in lock["wheels"].items()
    }
    guardian = get(GUARDIAN)
    if BACKEND:
        if runner.inspect_carrier() != staged.image_layers():
            raise ValueError("reviewed setuptools carrier layers differ")
    elif runner.inspect_carrier() != guardian["carrier_layers"]:
        raise ValueError("reviewed Django carrier layers differ")
    rows = expected_rows()
    rows += get(HERE / "recovery-67a93f4c-result-20261119.json")["software_reproduction_pool"][
        "new_rows"
    ]
    covered = {(row["repository"], row["revision"]) for row in rows}
    _, _, exposed = previous_repositories()
    cases = {}
    for index, pin in index_paths():
        for row in json.loads(read(index, pin)):
            case = row["input"]["task_id"]
            if case not in TARGETS:
                continue
            repo = repository(row["source_repository"])
            revision = row["source_revision"]
            if case in cases or repo in exposed or (repo, revision) in covered:
                raise ValueError("duplicate or exposed case in protected batch")
            if case == PARAM:
                wheels = [*core, pinned["pytest-asyncio"]]
                plugins, inherited = ["pytest_asyncio.plugin"], []
            elif case == BUILD_AUDIT:
                lock = get(WORK.parent / "build-audit-wheel-review.json")
                wheel = WORK.parent / "pyproject_hooks-1.2.0-py3-none-any.whl"
                old = get(
                    HERE.parent
                    / "repository-replacement-runtime-20261022/runtime-wheel-review.json"
                )
                (mock,) = [row for row in old["pins"] if row["project"] == "pytest-mock"]
                wheels = [
                    *core,
                    runner.asset(wheel, lock["sha256"]),
                    runner.asset(ROOT / mock["private_cache"], mock["sha256"]),
                ]
                plugins, inherited = ["pytest_mock"], ["setuptools-75.8.2"] if BACKEND else []
            else:
                wheels = core
                plugins = ["pytest_django.plugin"]
                inherited = ["django", "asgiref", "sqlparse", "pytest-django"]
            task, truth, reference, original, metadata = bind(row, index.parent, wheels)
            if metadata.get("admits_python_3_13_0") is False or ("protected_guard" in row) != (
                case == BUILD_AUDIT
            ):
                raise ValueError("unexpected case or runtime contract")
            files = archive_files(truth.source.read(), large=True)
            notices = {
                name: file_digest_path(body)
                for name, body in files.items()
                if name in {"LICENSE", "LICENSE.txt", "NOTICE"}
            }
            if not notices:
                raise ValueError("retained source lacks a publisher notice")
            truth = truth.model_copy(update={"pytest_plugins": plugins})
            if case == BUILD_AUDIT:
                AUDIT_GUARDS[truth.input_sha256] = row["protected_guard"]
            cases[case] = {
                "case_id": case,
                "repository": repo,
                "source_revision": revision,
                "source_index_sha256": pin,
                "local_source_notices": notices,
                "input": task.model_dump(mode="json"),
                "truth": truth.model_dump(mode="json"),
                "roles": {"reference": reference, "original": original},
                "reference_archive_sha256": row["reference_archive_sha256"],
                "existing_image_dependencies": inherited,
            }
    if set(cases) != set(TARGETS):
        raise ValueError("missing protected case")

    runtime = SOURCE_ROOT / "integrations/assessment-runtime"
    program = (
        (runtime / "repository_suite_native_program.py")
        .read_text()
        .replace(
            "'__AEEP_NATIVE_CAPTURE_SOURCE__'",
            repr((runtime / "repository_suite_native_capture.py").read_text()),
        )
    )
    marker = "argv = ['--no-header',"
    if program.count(marker) != 1:
        raise ValueError("observer parser changed")
    # These explicit test modules use Django's local fixture. Run them serially
    # without implicitly loading upstream test-distribution arguments.
    program = program.replace(marker, "argv = ['-o', 'addopts=', '--no-header',")
    if TARGETS == (BUILD_AUDIT,) and not COLLECT:
        oracle = cases[BUILD_AUDIT]["truth"]
        packed = get(WORK.parent / "software-contracts-collection/result.json")
        ids = packed["native_ids"]
        recovery = {}
        for name in oracle["pass_to_pass"]:
            same = [node for node in ids if node == name]
            if not same and name.count("[") > name.count("]"):
                same = [node for node in ids if node.startswith(name + " ")]
            if not same and name == AUDIT_GUARDS.get(oracle["input_sha256"]):
                same = [node for node in ids if node == name + "[False]"]
            if not same:
                raise ValueError("published identity still missing after real collection")
            recovery[name] = sorted(same)
        required = [node for group in recovery.values() for node in group]
        if len(required) != len(set(required)) or any(
            not node.startswith("tests/") for node in required
        ):
            raise ValueError("reviewed native identities overlap or escape the test root")
        old_guard = AUDIT_GUARDS[oracle["input_sha256"]]
        (AUDIT_GUARDS[oracle["input_sha256"]],) = recovery[old_guard]
        oracle["pass_to_pass"] = sorted(required)
        cases[BUILD_AUDIT]["native_selector_map"] = recovery
        selection = "*request['test_paths']"
        if program.count(selection) != 1:
            raise ValueError("reviewed module selection hook changed")
        program = program.replace(selection, "*" + repr(required))
    if BUILD_SUBPROCESS_PATHS:
        # PyPA Build starts a new interpreter in the fixture backend directory.
        # Supply the same reviewed source and wheel paths to those interpreters
        # after bootstrapping the protected pytest process.
        start_tests = "            + ';os.chdir('"
        if program.count(start_tests) != 1:
            raise ValueError("native observer bootstrap changed")
        program = program.replace(
            start_tests,
            '            + \';os.environ["PYTHONPATH"]=\' + repr(":".join('
            '[str(repo / "src"), str(repo), *wheels]))\n'
            '            + \';os.environ["PIP_NO_INDEX"]="1"\'\n'
            + start_tests,
        )
    compile(program, "<protected native observer>", "exec")
    spec = ExecutorSpec(
        id="repository.suite.observe",
        capability="assessment.repository_suite@1",
        kind="command",
        description="Offline protected preserved-test cohort verification",
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
        environment_id=NAME,
        kind="container",
        container_image=runner.CARRIER,
        container_socket=runner.SOCKET,
        container_runtime=runner.DOCKER,
        identity={"source": CURRENT_SOURCE},
        memory_mb=512,
        process_limit=96,
        container_tmpfs_mb=64,
    )
    return spec, environment, [cases[key] for key in TARGETS]


def file_digest_path(body):
    import hashlib

    return hashlib.sha256(body).hexdigest()


class ObservedExecutor(runner.ContainerExecutor):
    async def execute(self, context):
        raw = await super().execute(context)
        output = raw.output if isinstance(raw.output, dict) else {}
        reported = output.get("statuses", {})
        counts = Counter(reported.values()) if isinstance(reported, dict) else Counter()
        name = context.request.action_id
        put(
            runner.RUN / (name + "-diagnostic.json"),
            {
                "container_status": raw.status.value,
                "error_type": raw.error_type,
                "pytest_exit": output.get("exit_code"),
                "test_counts": dict(counts),
                "output_sha256": content_digest(output) if output else None,
            },
        )
        return raw


async def fields():
    data, spec, environment, cases = await OLD_FIELDS()
    data.update(
        {
            "driver_sha256": file_digest(Path(__file__)),
            "authority": "Finite protected case verification under the November 24 batch direction and standing delegation.",
            "contract_case_scope": (
                "Keep every published test identity plus the authored guard. The earlier full-module reference with five failures stays retained."
                if TARGETS == (BUILD_AUDIT,)
                else None
            ),
            "build_subprocess_paths": BUILD_SUBPROCESS_PATHS,
            "sources": {
                row["case_id"]: {
                    key: row[key]
                    for key in (
                        "repository",
                        "source_revision",
                        "source_index_sha256",
                        "local_source_notices",
                    )
                }
                for row in cases
            },
        }
    )
    return data, spec, environment, cases


def expected(truth, role):
    result = BASE_EXPECTED(truth, role)
    guard = AUDIT_GUARDS.get(truth["input_sha256"])
    if guard is not None and role == "original":
        result[guard] = "FAILED"
    return result


async def collect_contract(*, diagnose=False):
    spec, env, (case,) = definitions()
    input_payload = {}
    old_expected = expected(case["truth"], "reference")

    async def record(payload):
        input_payload.update(payload)
        header = {key: payload[key] for key in ("archive_sha256", "python", "pytest")}
        return header | {"exit_code": 0, "statuses": old_expected}

    await grade_suite_output(case["input"], case["truth"], case["roles"]["reference"], record)
    earlier = "software-contracts-native-grading" if diagnose else "software-contracts-verified"
    if BACKEND and diagnose:
        earlier = "software-contracts-offline-backend"
    if BUILD_SUBPROCESS_PATHS and diagnose:
        earlier = "software-contracts-subprocess-paths-v2"
    previous = get(WORK.parent / earlier / "operation-review.json")
    (attempt,) = [item for item in previous["launches"] if item["operation"].endswith(":reference")]
    if content_digest(input_payload) != attempt["payload_sha256"]:
        raise ValueError("protected collection would use different input")
    code = spec.config["argv"][-1]
    if code.count("OPERATOR_REVIEW = False") != 1:
        raise ValueError("native observer collection policy changed")
    code = code.replace("OPERATOR_REVIEW = False", "OPERATOR_REVIEW = True")
    previous_inputs = input_payload
    if diagnose:
        native = (
            SOURCE_ROOT / "integrations/assessment-runtime/repository_suite_native_capture.py"
        ).read_text()
        extension = (HERE / "pytest_failure_diagnostics.py").read_text()
        if code.count(repr(native)) != 1:
            raise ValueError("unexpected diagnostic hook")
        code = code.replace(
            repr(native),
            repr(
                native + "\n" + extension + "\nNativeCapture = diagnostic_capture(NativeCapture)\n"
            ),
        )
        native_shape = "assert set(native) == {'statuses'}"
        if code.count(native_shape) != 2:
            raise ValueError("observer response contract changed")
        code = code.replace(native_shape, "assert set(native) == {'statuses', 'failure_sites'}")
    else:
        previous_inputs = input_payload | {"collect_only": True}
    spec = spec.model_copy(update={"config": spec.config | {"argv": ["python3", "-B", "-c", code]}})
    executor = runner.ContainerExecutor(env)
    trial = runner.context(
        spec, NAME + (":diagnose" if diagnose else ":collection"), previous_inputs
    )
    argv, owned = executor.command(trial)
    checked.REVIEW = WORK / "operation-review.json"
    fields = {
        "source": CURRENT_SOURCE,
        "minimum_free_bytes": 52 * 2**30,
        "models": 0,
        "cash_usd": 0,
        "input_sha256": content_digest(trial.request.input),
        "argv_sha256": content_digest(argv),
        "launch": {"container": owned},
        "authority": "One scoped protected diagnostic. Retain native identities and sanitized exception locations only.",
    }
    put(checked.REVIEW, fields)
    exact = file_digest(checked.REVIEW)
    scope = runner.Scope(review_sha256=exact)
    ref = content_digest(scope)
    request = RecipeMaterializationRequest(
        plan_id=NAME,
        authorization_id=NAME,
        subject_digest=ref,
        recipe_digest=ref,
        environment_digest=ref,
        mapping_digest=ref,
        definition_digests=[ref],
        seed=0,
    )
    grant = AssessmentAuthorization(
        authorization_id=NAME,
        subject_digests=[ref],
        recipe_digests=[ref],
        environment_digests=[ref],
        allowed_destinations=["local"],
        limits=AssessmentLimits(max_operations=1, max_model_turns=0, max_elapsed_seconds=95),
        expires_at=utc_now() + timedelta(hours=2),
        remote_disclosure=False,
    )
    with ReceiptStore(WORK / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        repo.put("toolkit_c13_contract_collection", ref, scope)
        repo.approve_bundle(grant, {ref: scope.model_dump(mode="json")})
        try:
            raw, receipt = await checked.run_checked(
                repo, store, request, fields, exact, executor, trial
            )
            data = (raw.output or {}).get("evaluation" if diagnose else "collection", {})
            if (
                raw.status.value != "success"
                or data.get("archive_sha256") != input_payload["archive_sha256"]
            ):
                raise ValueError("could not verify native diagnostic")
            if diagnose:
                put(
                    WORK / "result.json",
                    {
                        "receipt": receipt.receipt_id,
                        "exit_code": data["exit_code"],
                        "failures": data["failure_sites"],
                    },
                )
            else:
                if data["exit_code"] != 0 or sorted(data["native_ids"]) != sorted(
                    data["selected_ids"]
                ):
                    raise ValueError("could not verify native collection")
                put(
                    WORK / "result.json",
                    {"receipt": receipt.receipt_id, "native_ids": data["native_ids"]},
                )
        finally:
            put(WORK / "ledger.json", repo.operation_ledger(NAME).model_dump(mode="json"))


async def main():
    global NAME, WORK, TARGETS, COLLECT, BACKEND, BUILD_SUBPROCESS_PATHS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract-audits", action="store_true")
    parser.add_argument("--collect-contract", action="store_true")
    parser.add_argument("--diagnose-contract", action="store_true")
    parser.add_argument("--contract-backend", action="store_true")
    parser.add_argument("--contract-subprocess-paths", action="store_true")
    args = parser.parse_args()
    BUILD_SUBPROCESS_PATHS = args.contract_subprocess_paths
    BACKEND = args.contract_backend or BUILD_SUBPROCESS_PATHS
    if BUILD_SUBPROCESS_PATHS and args.collect_contract:
        parser.error("the subprocess path review reuses the native identities")
    if args.contract_audits or args.collect_contract or args.diagnose_contract or BACKEND:
        NAME = "c13-software-cohort-contracts-20261124"
        WORK = WORK.parent / "software-contracts-published-ids"
        TARGETS = (BUILD_AUDIT,)
        if args.collect_contract:
            COLLECT = True
            NAME = NAME + "-collection"
            WORK = WORK.parent / "software-contracts-collection"
        elif args.diagnose_contract:
            if BUILD_SUBPROCESS_PATHS:
                suffix = "-subprocess-diagnosis"
            else:
                suffix = "-backend-diagnosis" if BACKEND else "-diagnosis"
            NAME += suffix
            WORK = WORK.parent / ("software-contracts" + suffix)
        elif BUILD_SUBPROCESS_PATHS:
            NAME = NAME + "-subprocess-paths-v2"
            WORK = WORK.parent / "software-contracts-subprocess-paths-v2"
        elif BACKEND:
            NAME = NAME + "-backend"
            WORK = WORK.parent / "software-contracts-offline-backend"
        else:
            WORK = WORK.parent / "software-contracts-native-grading"
    os.umask(0o077)
    WORK.mkdir(mode=0o700)
    runner.NAME = NAME
    runner.FROZEN = SOURCE_ROOT
    runner.CARRIER = staged.CARRIER if BACKEND else get(GUARDIAN)["environment"]["container_image"]
    runner.REVIEW = WORK / "operation-review.json"
    runner.APPROVAL = WORK / "delegated-review.json"
    runner.RUN = WORK / "execution"
    runner.MAX_CALLS = 2 * len(TARGETS)
    runner.expected_statuses = expected
    runner.definitions = definitions
    runner.review_fields = fields
    if COLLECT or args.diagnose_contract:
        await collect_contract(diagnose=args.diagnose_contract)
        return
    runner.ContainerExecutor = ObservedExecutor
    scope, _, _, _ = await fields()
    put(runner.REVIEW, scope | {"expires_at": (utc_now() + timedelta(days=1)).isoformat()})
    exact = file_digest(runner.REVIEW)
    put(runner.APPROVAL, {"approved": True, "review_sha256": exact})
    await runner.run(exact)


if __name__ == "__main__":
    asyncio.run(main())
