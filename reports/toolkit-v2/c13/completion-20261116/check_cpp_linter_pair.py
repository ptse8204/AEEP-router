"""Grade retained software repairs with their unchanged protected Python tests."""

import argparse
import asyncio
import json
import re
import runpy
import tomllib
from datetime import timedelta
from pathlib import Path

import repository_offline_pair_batch as runner
from audit_staged_repository_graders import bind, index_paths, wheel_probe_assets
from check_pyserde_ordinary import validate_image as pyserde_image
from plan_repository_expansion import previous_repositories
from rebind_intake_stack import CURRENT_SOURCE
from stage_repository_transport import HERE, ROOT, digest, read

import aeep
from aeep.assessment.models import AssessmentEnvironment, content_digest
from aeep.assessment.repository_suites import LARGE_PAYLOAD, archive_files, grade_suite_output
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec, utc_now

CASE = "cpp-linter__cpp-linter-hooks-142"
PYSERDE = "yukinarit__pyserde-657"
NAME = "c13-cpp-linter-pair-20261124"
TARGET = ROOT / ".aeep/c13-cohort-runtime-20261124" / NAME
FROZEN = ROOT / ".aeep/c13-intake-wheel-20261124/linux/source"
INDEX = "378a7a9cf4dc2184f5af65b063547cbc27fc253d6f51d1e74cb3278280d5d4bc"
PUBLISHER_REVIEW = "c5775f55bad2993969613e12f36eb920c53731a11f362a6fbc45aad48b65f5a6"
BASE_REVIEW = runner.review_fields
BASE_PROBE = runner.verify_probe
DIAGNOSTICS = []
DIAGNOSE = False
PYSERDE_RUN = {
    "result_sha256": "c3a3a2c0126bbff0ce0b7ead9617995ab59d26706f3780cbba6692f3e3a05ef2",
    "review_sha256": "7e644e0d73f729d867dda397120356b21308d2209ec77f9bed58aff0c9ddcfd8",
    "typing_extensions_sha256": "04e5ca0351e0f3f85c6853954072df659d0d13fac324d0072316b67d7794700d",
}
TYPING_EXTENSION = ROOT / (
    ".aeep/completion-20261116/locify-locked-runtime-assets-20261119/downloads/"
    "typing_extensions-4.12.2-py3-none-any.whl"
)
REQUIRED = {PYSERDE: (5, 7), CASE: (2, 27)}
SANITIZER = HERE.parent / "repository-collection-diagnostics-20261027/sanitize.py"
IMPORTS = (
    "black", "casefy", "beartype", "beartype.door", "click", "jinja2", "markupsafe",
    "msgpack", "msgpack.fallback", "orjson", "serde", "tests", "tests.test_json", "tests.test_se", "typing_extensions",
    "TypeAliasType", "TypeGuard", "ParamSpec", "dataclass_transform", "typing_inspect", "plum",
)
SUPPORT = ROOT / ".aeep/c13-cohort-runtime-20261124/pyserde-657-msgpack"
MSG_PACK = {
    "source_sha256": "3b60763c1373dd60f398488069bcdc703cd08a711477b5d480eecc9f9626f47e",
    "projection_sha256": "f849baf513ca038efca023499625d2364f01f4a39bf0d6ee6c37a69bfff0d3b3",
    "version": "1.1.2",
}
MSGPACK_FALLBACK = False
ORIGINAL_ONLY = False
REFERENCE_DIR = ROOT / ".aeep/c13-cohort-runtime-20261124/c13-pyserde-657-pair-20261124-msgpack"
REFERENCE_PINS = {
    "operation-review.json": "0181f911ef225053ecdb682616969eabc6dd79e8a03814c478aa04a74aca06c6",
    "execution/diagnostic.json": "3df8556c110478ebeea1650ac807405c4e241d19f9b6c62c82811f48ed9cbe6e",
    "execution/result.json": "5f2ef713ccc355abcd58b9d5b58b5e08c29026130b5f6a8feadd5981101fe634",
    "execution/ledger.json": "c90989c5d073c28c0272b50c21ce06fc7c93350aa6faba9188319dc66361ae14",
    "execution/receipt-rcpt_4fc35ada37d44a0d8e15ddb2456706a3.json": (
        "99ce2a61fde594f7717e2cc27284e763f583b513a78277bd5f45614347fe26e2"
    ),
}


def msgpack_projection():
    read(SUPPORT / "msgpack-1.1.2.tar.gz", MSG_PACK["source_sha256"])
    projection = json.loads(read(SUPPORT / "projection.json", MSG_PACK["projection_sha256"]))
    root = SUPPORT / "support"
    if (
        root.is_symlink() or {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()} != set(projection)
        or any(path.is_symlink() for path in root.rglob("*"))
    ):
        raise ValueError("MsgPack fallback projection differs")
    for name, metadata in projection.items():
        if len(read(root / name, metadata["sha256"])) != metadata["bytes"]:
            raise ValueError("MsgPack byte count changed")
    return root


def definitions():
    if Path(aeep.__file__).resolve().parents[2] != FROZEN or verification_source_digest(FROZEN) != CURRENT_SOURCE:
        raise ValueError("load the frozen verified source")
    index, pin = next(index_paths())
    if pin != INDEX:
        raise ValueError("retained index drift")
    (row,) = [entry for entry in json.loads(read(index, pin)) if entry["input"]["task_id"] == CASE]
    prior = HERE.parent / "repository-library-reproduction-20261027/source-review.json"
    (publisher,) = [x for x in json.loads(read(prior, PUBLISHER_REVIEW))["sources"] if x["instance_id"] == CASE]
    archive = ROOT / publisher["private_cache"] / "source.tar.gz"
    read(archive, publisher["archive_sha256"])
    _, _, exposed = previous_repositories()
    _, wheels = wheel_probe_assets()
    if CASE == PYSERDE:
        wheels += [runner.asset(TYPING_EXTENSION, PYSERDE_RUN["typing_extensions_sha256"])]
    task, truth, ref, original, metadata = bind(row, index.parent, wheels)
    files = archive_files(truth.source.read(), large=True)
    compatible_python = metadata.get("admits_python_3_13_0")
    if CASE == PYSERDE:
        dependencies = tomllib.loads(files["pyproject.toml"].decode())["tool"]["poetry"]["dependencies"]
        compatible_python = dependencies["python"] == "^3.9.0" and dependencies["typing_extensions"]["version"] == ">=4.1.0,<4.13.0"
    if (
        row["source_repository"] != publisher["repository"] or publisher["repository"] in exposed
        or row["source_revision"] != publisher["revision"]
        or metadata["names_not_declared_in_selected_module"] or not compatible_python
        or (len(truth.fail_to_pass), len(truth.pass_to_pass)) != REQUIRED[CASE]
        or not publisher["licenses"] or any(
            digest(files[notice["file"]]) != notice["sha256"] for notice in publisher["licenses"]
        )
    ):
        raise ValueError("publisher rights, independence, runtime or protected tests changed")
    runtime = FROZEN / "integrations/assessment-runtime"
    capture = (runtime / "repository_suite_native_capture.py").read_text()
    program = (runtime / "repository_suite_native_program.py").read_text()
    capture += "\n" + (HERE / "pytest_failure_diagnostics.py").read_text()
    capture += "\nNativeCapture = diagnostic_capture(NativeCapture)\n"
    shape = "assert set(native) == {'statuses'}"
    if program.count(shape) != 2:
        raise ValueError("retained native response envelope changed")
    program = program.replace(shape, "assert set(native) == {'statuses', 'failure_sites'}")
    program = program.replace("'__AEEP_NATIVE_CAPTURE_SOURCE__'", repr(capture))
    marker = "            return {**header, **native}"
    if program.count(marker) != 1:
        raise ValueError("retained native log boundary changed")
    before_main = "\nif __name__ == '__main__':"
    if program.count(before_main) != 1:
        raise ValueError("retained native entry point changed")
    program = program.replace(
        before_main,
        "\nsanitizer_scope = {'__name__': 'aeep_sanitizer'}\n"
        + "exec(" + repr(SANITIZER.read_text()) + ", sanitizer_scope)\n"
        + "summarize_log = sanitizer_scope['summarize_log']\n" + before_main,
    )
    program = program.replace(marker, (
        "            facts = summarize_log(log.read_bytes().decode('utf-8', errors='replace'), "
        + repr(IMPORTS) + ") if child.returncode == 2 else None\n"
        + "            return {**header, **native, 'collection_errors': facts}"
    ))
    mounts = []
    if MSGPACK_FALLBACK:
        support = msgpack_projection()
        anchor = "            + ';os.chdir('"
        if program.count(anchor) != 1:
            raise ValueError("protected import point changed")
        origin = repr(str(support / "msgpack/__init__.py"))
        bootstrap = (
            ";sys.path.insert(0," + repr(str(support)) + ");import msgpack"
            + ";assert str(Path(msgpack.__file__).resolve())==" + origin
            + ";assert msgpack.Packer.__module__=='msgpack.fallback'"
        )
        program = program.replace(anchor, "            + " + repr(bootstrap) + "\n" + anchor)
        mounts.append(str(support))
    compile(program, "<protected repository verifier>", "exec")
    spec = ExecutorSpec(
        id="repository.suite.observe", capability="assessment.repository_suite@1", kind="command",
        description="Grade a pinned repository repair through the ordinary protected callback",
        config={"argv": ["python3", "-B", "-c", program], "argv_literal": True, "stdin_json": True,
                "timeout_seconds": 30, "max_stdin_bytes": LARGE_PAYLOAD, "max_output_bytes": 500_000,
                "output": {"type": "json"}},
    )
    env = AssessmentEnvironment(
        environment_id=NAME, kind="container", container_image=runner.CARRIER,
        container_runtime=runner.DOCKER, container_socket=runner.SOCKET, identity={"source": CURRENT_SOURCE},
        memory_mb=512, process_limit=96, container_tmpfs_mb=64, read_only_roots=mounts,
    )
    return spec, env, [{
        "case_id": CASE, "source_revision": publisher["revision"], "input": task.model_dump(mode="json"),
        "truth": truth.model_dump(mode="json"), "roles": {"reference": ref, "original": original},
        "reference_archive_sha256": row["reference_archive_sha256"], "existing_image_dependencies": [],
    }]


async def fields():
    record, spec, environment, cases = await BASE_REVIEW()
    if any(row["required_tests"] != sum(REQUIRED[CASE]) for row in record["launches"]):
        raise ValueError("the protected pair changed its native test inventory")
    record.update(
        source_index_sha256=INDEX, publisher_review_sha256=PUBLISHER_REVIEW,
        wrapper_sha256=runner.file_digest(Path(__file__)), storage_floor_bytes=50 * 2**30,
        authority="C13 bounded offline first-check delegation",
        comparisons_paused=True, waza_excluded=True,
    )
    if CASE == PYSERDE:
        record["retained_runtime"] = PYSERDE_RUN
    if MSGPACK_FALLBACK:
        record["msgpack_source_projection"] = MSG_PACK
    if ORIGINAL_ONLY:
        (case,) = cases
        record["recovered_reference"] = await recover_reference(case)
        old = json.loads(read(REFERENCE_DIR / "operation-review.json", REFERENCE_PINS["operation-review.json"]))
        if record["launches"][0]["payload_sha256"] != old["launches"][1]["payload_sha256"]:
            raise ValueError("unstarted control payload changed")
    return record, spec, environment, cases


def canonical_reply(reply):
    return {key: reply[key] for key in ("archive_sha256", "python", "pytest", "exit_code", "statuses")}


async def recover_reference(case):
    review, audit, result, ledger, receipt = (
        json.loads(read(REFERENCE_DIR / name, sha)) for name, sha in REFERENCE_PINS.items()
    )
    (observed,) = audit
    (original_record,) = result["observations"]
    (charge,) = ledger["operations"]
    if (
        observed["exit_code"] != 0 or not observed["matched"] or observed["failure_sites"]
        or observed["collection_errors"] is not None or not original_record["contract_matched"]
        or receipt["receipt_id"] != original_record["receipt_id"] or not receipt["execution_success"]
        or receipt["action_id"] != charge["operation_id"] or charge["elapsed_seconds"] is None
        or result["review_sha256"] != REFERENCE_PINS["operation-review.json"]
    ):
        raise ValueError("settled reference lacks its original verified observations")

    async def readback(payload):
        if content_digest(payload) != review["launches"][0]["payload_sha256"]:
            raise ValueError("reference payload does not match its settled review")
        value = {key: payload[key] for key in ("archive_sha256", "python", "pytest")} | {
            "exit_code": observed["exit_code"], "statuses": observed["required_statuses"],
            "failure_sites": observed["failure_sites"], "collection_errors": observed["collection_errors"],
        }
        if content_digest(value) != receipt["metadata"]["protected_observation_sha256"]:
            raise ValueError("reference observations do not reconstruct the original receipt digest")
        return canonical_reply(value)

    grade = await grade_suite_output(case["input"], case["truth"], case["roles"]["reference"], readback)
    if not grade.valid or grade.quality_score != 1:
        raise ValueError("ordinary reference grade did not reproduce from the saved receipt")
    return {"receipt": receipt["receipt_id"], "pins": REFERENCE_PINS, "score": grade.quality_score,
            "elapsed_seconds": charge["elapsed_seconds"]}


def diagnose_reply(reply, payload, expected, code):
    if not isinstance(reply, dict):
        DIAGNOSTICS.append({"reply": "missing_native_output"})
        return False
    if not {"archive_sha256", "python", "pytest", "exit_code", "statuses"} <= reply.keys():
        raise ValueError("native observation is incomplete")
    standard = canonical_reply(reply)
    if any(standard.get(key) != payload[key] for key in ("archive_sha256", "python", "pytest")):
        raise ValueError("diagnostic does not bind to the exact protected payload")
    statuses = standard.get("statuses", {})
    if not isinstance(statuses, dict) or any(
        status not in ("PASSED", "FAILED", "ERROR", "SKIPPED", "XFAIL") for status in statuses.values()
    ):
        raise ValueError("native status inventory is invalid")
    sites = reply.get("failure_sites", [])
    source_file = r"(?:cpp_linter_hooks/[A-Za-z0-9_]+|tests/test_util)\.py"
    if CASE == PYSERDE:
        source_file = r"(?:serde/[A-Za-z0-9_]+|tests/test_(?:json|se))\.py"
    if not isinstance(sites, list) or any(
        not isinstance(site, dict) or set(site) != {"test", "phase", "category", "file", "line"}
        or site["test"] not in expected or site["phase"] not in ("setup", "call", "teardown")
        or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,79}", site["category"])
        or (site["file"] is not None and not re.fullmatch(source_file, site["file"]))
        or (site["line"] is not None and (type(site["line"]) is not int or site["line"] <= 0))
        for site in sites
    ):
        raise ValueError("public failure site escaped the scoped test or module")
    matched = BASE_PROBE(standard, payload, expected, code)
    collection = reply.get("collection_errors")
    if collection is not None:
        sanitizer = runpy.run_path(str(SANITIZER))
        sanitizer["validate_reply"]({
            "schema_version": sanitizer["SCHEMA"], "diagnostics": collection,
            "exit_code": standard["exit_code"], "log_limit_exceeded": False, "timed_out": False,
            **{key: standard[key] for key in ("archive_sha256", "python", "pytest")},
        }, payload | {"reviewed_identifiers": IMPORTS})
    DIAGNOSTICS.append({
        "exit_code": standard.get("exit_code"), "required_statuses": {
            name: statuses.get(name, "MISSING") for name in expected
        }, "failure_sites": sites, "collection_errors": collection, "matched": matched,
    })
    return matched


async def main():
    global CASE, DIAGNOSE, MSGPACK_FALLBACK, NAME, ORIGINAL_ONLY, TARGET
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--execute")
    parser.add_argument("--diagnostic-reference", action="store_true")
    parser.add_argument("--collection-errors", action="store_true")
    parser.add_argument("--pyserde", action="store_true")
    parser.add_argument("--with-msgpack", action="store_true")
    parser.add_argument("--unstarted-original", action="store_true")
    args = parser.parse_args()
    DIAGNOSE = args.diagnostic_reference or args.collection_errors
    MSGPACK_FALLBACK = args.with_msgpack
    ORIGINAL_ONLY = args.unstarted_original
    if ORIGINAL_ONLY and not MSGPACK_FALLBACK:
        parser.error("the unstarted original must reuse the settled Pyserde reference environment")
    if MSGPACK_FALLBACK and (not args.pyserde or DIAGNOSE):
        parser.error("MsgPack fallback is reviewed for the Pyserde pair")
    if args.pyserde:
        CASE = PYSERDE
        NAME = "c13-pyserde-657-pair-20261124"
        if MSGPACK_FALLBACK:
            NAME += "-msgpack"
        if ORIGINAL_ONLY:
            NAME += "-original"
            runner.ROLES = ("original",)
        TARGET = TARGET.with_name(NAME)
        review = json.loads(read(HERE / "pyserde-ordinary-operation-review.json", PYSERDE_RUN["review_sha256"]))
        result = json.loads(read(HERE / "pyserde-ordinary-result.json", PYSERDE_RUN["result_sha256"]))
        runner.CARRIER = pyserde_image(review)
        if not result["protected_ordinary_verification_passed"] or result["built_image"]["image_id"] != runner.CARRIER:
            raise ValueError("Pyserde carrier differs from the completed review")
    if DIAGNOSE:
        NAME += "-collection-envelope" if args.collection_errors else "-diagnostic"
        TARGET = TARGET.with_name(NAME)
        runner.ROLES = ("reference",)
    runner.verify_probe = diagnose_reply
    runner.scorer_reply = canonical_reply
    runner.NAME, runner.FROZEN, runner.MAX_CALLS = NAME, FROZEN, len(runner.ROLES)
    runner.REVIEW = TARGET / "operation-review.json"
    runner.RUN = TARGET / "execution"
    runner.APPROVAL = TARGET / "delegated-review.json"
    runner.definitions, runner.review_fields = definitions, fields
    if args.prepare:
        record, _, _, _ = await fields()
        TARGET.mkdir(mode=0o700)
        runner.put(runner.REVIEW, record | {"expires_at": (utc_now() + timedelta(hours=4)).isoformat()})
        print(runner.file_digest(runner.REVIEW))
    else:
        runner.read(runner.REVIEW, args.execute)
        if runner.RUN.exists() or runner.APPROVAL.exists():
            raise ValueError("this first-check authorization cannot replay a recorded attempt")
        runner.put(runner.APPROVAL, {"approved": True, "review_sha256": args.execute})
        try:
            success = await runner.run(args.execute)
        finally:
            if runner.RUN.is_dir():
                runner.put(runner.RUN / "diagnostic.json", DIAGNOSTICS)
        raise SystemExit(not success)


if __name__ == "__main__":
    asyncio.run(main())
