"""Verify three published SQLacodegen dialect repairs without database servers."""

import argparse
import ast
import asyncio
import json
import shutil
from datetime import timedelta
from pathlib import Path

import check_retained_carrier_batch as batch
import check_sqlacodegen_cli_pair as cli
from audit_staged_repository_graders import bind, index_paths, wheel_probe_assets
from stage_repository_transport import ROOT, digest, read

import aeep
from aeep.assessment.models import AssessmentEnvironment
from aeep.assessment.repository_suites import LARGE_PAYLOAD, SuiteTruthV6, archive_files
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec, utc_now
from aeep_toolkit.install_runtime import file_digest

runner = batch.runner
FROZEN, SOURCE = batch.FROZEN, batch.SOURCE
NAME = "c13-sqlacodegen-dialects-20261124"
WORK = ROOT / ".aeep/c13-cohort-runtime-20261124" / NAME
INDEX = "378a7a9cf4dc2184f5af65b063547cbc27fc253d6f51d1e74cb3278280d5d4bc"
CASES = {f"agronholm__sqlacodegen-{issue}" for issue in (368, 371, 375)}
LICENSE_SHA = "6163f7987dfb38d6bc320ce2b70b2f02b862bc41126516d552ef1cd43247e758"
VERSIONS = {"mysql-connector-python": "9.4.0", "psycopg": "3.2.10", "psycopg-binary": "3.2.10"}
BASE = runner.review_fields
PROTECTED = "tests/test_generator_tables.py"
NETWORK_CALLS = {
    "connect",
    "begin",
    "execute",
    "exec_driver_sql",
    "reflect",
    "create_all",
    "drop_all",
}


def native_selectors(test):
    (node,) = [
        node
        for node in ast.parse(test).body
        if isinstance(node, ast.FunctionDef) and node.name == "test_computed_column"
    ]
    (call,) = node.decorator_list
    if ast.unparse(call.func) != "pytest.mark.parametrize" or call.keywords:
        raise ValueError("publisher parametrization changed")
    names, data = map(ast.literal_eval, call.args)
    if names != "persisted, extra_args" or data != [
        (None, ""),
        (False, ", persisted=False"),
        (True, ", persisted=True"),
    ]:
        raise ValueError("published parameter fixtures changed")
    prefix = f"{PROTECTED}::test_computed_column"
    return {
        f"{prefix}[{value}-,": f"{prefix}[{value}-{text}]"
        for value, text in data
        if value is not None
    }


def cases():
    if (
        Path(aeep.__file__).resolve().parents[2] != FROZEN
        or verification_source_digest(FROZEN) != SOURCE
    ):
        raise ValueError("load the already verified toolkit source")
    index, pin = next(index_paths())
    if pin != INDEX or "agronholm/sqlacodegen" in cli.previous_repositories()[2]:
        raise ValueError("staged registry or family exposure changed")
    result = []
    _, wheels = wheel_probe_assets()
    for row in json.loads(read(index, pin)):
        if row["input"]["task_id"] not in CASES:
            continue
        task, truth, reference, original, metadata = bind(row, index.parent, wheels)
        source = archive_files(truth.source.read(), large=True)
        overlay = archive_files(truth.tests.read(), large=True)
        files = source | overlay
        if (
            digest(source["LICENSE"]) != LICENSE_SHA
            or not metadata["admits_python_3_13_0"]
            or metadata["names_not_declared_in_selected_module"]
            or truth.test_paths != [PROTECTED]
            or (len(truth.fail_to_pass), len(truth.pass_to_pass)) != (1, 38)
        ):
            raise ValueError("protected identity or licensing context changed")
        # The published fixture constructs dialect-specific engines. Loading
        # their authentic DBAPI modules permits compilation without a server.
        bound = [PROTECTED, "tests/conftest.py", "src/sqlacodegen/generators.py"]
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in NETWORK_CALLS
            for path in bound
            for node in ast.walk(ast.parse(files[path]))
        ):
            raise ValueError("a protected module now performs database I/O")
        fix = native_selectors(files[PROTECTED])
        if fix.keys() != {
            name for name in truth.pass_to_pass if "[" in name and not name.endswith("]")
        }:
            raise ValueError("publisher selector mismatch is wider than the reviewed two aliases")
        truth = SuiteTruthV6.model_validate(
            truth.model_dump(mode="json")
            | {
                "pass_to_pass": [fix.get(name, name) for name in truth.pass_to_pass],
            }
        )
        result.append(
            {
                "case_id": task.task_id,
                "source_revision": row["source_revision"],
                "input": task.model_dump(mode="json"),
                "truth": truth.model_dump(mode="json"),
                "roles": {"reference": reference, "original": original},
                "reference_archive_sha256": row["reference_archive_sha256"],
                "existing_image_dependencies": ["SQLAlchemy==2.0.44", "inflect==7.5.0"],
                "publisher_selector_aliases": fix,
            }
        )
    if {case["case_id"] for case in result} != CASES:
        raise ValueError("exact dialect case selection changed")
    return result


def observe(pins):
    runtime = FROZEN / "integrations/assessment-runtime"
    program = (runtime / "repository_suite_native_program.py").read_text()
    capture = (runtime / "repository_suite_native_capture.py").read_text()
    root = str(batch.assets.SUPPORT / "drivers")
    versions = {name: value["version"] for name, value in pins.items()} | {
        "SQLAlchemy": "2.0.44",
        "inflect": "7.5.0",
    }
    check = (
        f";sys.path.insert(0,{root!r});from importlib.metadata import version;"
        f"assert all(version(k)==v for k,v in {versions!r}.items());"
        "import psycopg.pq,mysql.connector;"
        f"assert psycopg.pq.__impl__=='binary' and Path(mysql.connector.__file__).is_relative_to({root!r})"
    )
    hook = "            + ';import pytest;"
    if program.count(hook) != 1:
        raise ValueError("native bootstrap entry point changed")
    program = program.replace(hook, "            + " + repr(check) + "\n" + hook)
    return program.replace("'__AEEP_NATIVE_CAPTURE_SOURCE__'", repr(capture))


def configure(subjects, pins):
    runner.NAME, runner.FROZEN = NAME, FROZEN
    runner.MAX_CALLS, runner.ROLE_SECONDS = 6, 50
    runner.REVIEW, runner.RUN, runner.APPROVAL = (
        WORK / "operation-review.json",
        WORK / "execution",
        WORK / "scope.json",
    )
    built = json.loads(read(cli.UPSTREAM / "build-result.json", cli.IMAGE_BUILD))
    if (
        not built["passed"]
        or not built["inherited_config_verified"]
        or not built["parent_layers_verified"]
    ):
        raise ValueError("retained SQLAlchemy carrier lineage differs")
    runner.CARRIER = built["image_id"]

    def definitions():
        spec = ExecutorSpec(
            id="repository.suite.observe",
            capability="assessment.repository_suite@1",
            kind="command",
            description="Protected SQL dialect generation without external database services",
            config={
                "argv": ["python3", "-B", "-c", observe(pins)],
                "argv_literal": True,
                "stdin_json": True,
                "timeout_seconds": 38,
                "max_stdin_bytes": LARGE_PAYLOAD,
                "max_output_bytes": 500_000,
                "output": {"type": "json"},
            },
        )
        env = AssessmentEnvironment(
            environment_id=NAME,
            kind="container",
            container_image=runner.CARRIER,
            identity={"source": SOURCE},
            container_runtime=runner.DOCKER,
            container_socket=runner.SOCKET,
            memory_mb=512,
            process_limit=96,
            container_tmpfs_mb=64,
            read_only_roots=[str(batch.assets.SUPPORT / "drivers")],
        )
        return spec, env, subjects

    verify = runner.verify_probe

    def observed(reply, payload, expected, code):
        suffix = digest(payload["archive_sha256"].encode())[:16]
        runner.put(runner.RUN / f"observation-{suffix}.json", reply)
        return verify(reply, payload, expected, code)

    async def fields():
        contents = batch.assets.support_check("drivers", pins)
        base, spec, env, cases = await BASE()
        return (
            base
            | {
                "wrapper_sha256": file_digest(Path(__file__)),
                "storage_floor_bytes": batch.assets.FLOOR,
                "source_license_sha256": LICENSE_SHA,
                "wheel_pins": pins,
                "driver_mount_sha256": digest(json.dumps(contents, sort_keys=True).encode()),
                "selector_aliases": {
                    case["case_id"]: case["publisher_selector_aliases"] for case in subjects
                },
                "reviewed_network": "none",
                "database_services": 0,
                "published_checks_per_role": 39,
                "provenance": "First protected attempts. Source variants share the SQLacodegen stage family.",
            },
            spec,
            env,
            cases,
        )

    runner.definitions, runner.review_fields, runner.verify_probe = definitions, fields, observed


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare-intake", action="store_true")
    action.add_argument("--acquire")
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--execute")
    options = parser.parse_args()
    subjects = cases()
    WORK.mkdir(mode=0o700, exist_ok=True)
    batch.WORK = WORK
    batch.assets.WHEELS, batch.assets.SUPPORT = WORK / "wheels", WORK / "support"
    intake = WORK / "acquisition-review.json"
    if options.prepare_intake:
        batch.PROFILES = {"dialect-drivers": {"versions": VERSIONS}}
        fields = batch.acquire_plan() | {"coordinator_sha256": file_digest(Path(__file__))}
        runner.put(intake, fields)
        print(file_digest(intake))
        return
    if options.acquire:
        fields = json.loads(read(intake, options.acquire))
        if fields["coordinator_sha256"] != file_digest(Path(__file__)):
            raise ValueError("driver acquisition scope changed")
        batch.acquire(fields)
        runner.put(
            WORK / "acquisition-result.json", {"review_sha256": options.acquire, "completed": True}
        )
        return
    transferred = runner.get(WORK / "acquisition-result.json")
    pins = {
        meta["name"]: meta
        for meta in json.loads(read(intake, transferred["review_sha256"]))["files"].values()
    }
    if {key: item["version"] for key, item in pins.items()} != VERSIONS:
        raise ValueError("driver wheel selection changed")
    configure(subjects, pins)
    if options.prepare:
        if shutil.disk_usage(WORK).free < batch.assets.FLOOR + 3 * batch.MAX_FETCH:
            raise ValueError("preserve required host storage reserve")
        batch.assets.support_check(
            "drivers", pins, prepare=not (batch.assets.SUPPORT / "drivers").exists()
        )
        fields, _, _, _ = await runner.review_fields()
        runner.put(
            runner.REVIEW, fields | {"expires_at": (utc_now() + timedelta(hours=4)).isoformat()}
        )
        print(file_digest(runner.REVIEW))
    else:
        read(runner.REVIEW, options.execute)
        if runner.RUN.exists() or runner.APPROVAL.exists():
            raise ValueError("preserve the existing protected attempt")
        runner.put(runner.APPROVAL, {"approved": True, "review_sha256": options.execute})
        raise SystemExit(not await runner.run(options.execute))


if __name__ == "__main__":
    asyncio.run(main())
