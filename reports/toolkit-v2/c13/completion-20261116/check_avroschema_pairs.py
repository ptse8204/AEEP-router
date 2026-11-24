"""Verify two published Avro model-generation repairs in the ordinary protected grader."""

import argparse
import asyncio
import json
import shutil
import tomllib
import urllib.request
from datetime import timedelta
from pathlib import Path
from zipfile import ZipFile

import repository_offline_pair_batch as runner
from audit_staged_repository_graders import bind, index_paths, wheel_probe_assets
from check_expansion_contracts import NoRedirect, inspect_wheel
from packaging.requirements import Requirement
from plan_repository_expansion import previous_repositories
from stage_repository_transport import ROOT, digest, read, write
from stage_varex_calibration import FROZEN, SOURCE

import aeep
from aeep.assessment.models import AssessmentEnvironment
from aeep.assessment.repository_suites import LARGE_PAYLOAD, archive_files
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec, utc_now
from aeep_toolkit.install_runtime import file_digest

NAME = "c13-avroschema-pairs-20261124"
WORK = ROOT / ".aeep/c13-cohort-runtime-20261124" / NAME
WHEELS = WORK / "wheels"
SUPPORT = WORK / "support"
INDEX = "378a7a9cf4dc2184f5af65b063547cbc27fc253d6f51d1e74cb3278280d5d4bc"
PACKAGE_NAMES = {
    "annotated-types",
    "casefy",
    "dacite",
    "dnspython",
    "email-validator",
    "faker",
    "fastavro",
    "idna",
    "inflection",
    "pydantic",
    "pydantic-core",
    "python-dateutil",
    "six",
    "typing-extensions",
    "tzdata",
}
TEST_COUNTS = {"835": 44, "870": 14}
MAX_DOWNLOAD = 20_000_000
FLOOR = 50 * 2**30
BASE_REVIEW = runner.review_fields


def projects():
    if (
        Path(aeep.__file__).resolve().parents[2] != FROZEN
        or verification_source_digest(FROZEN) != SOURCE
    ):
        raise ValueError("use the previously verified toolkit source")
    index, pin = next(index_paths())
    if pin != INDEX:
        raise ValueError("retained transport index changed")
    _, _, exposed = previous_repositories()
    _, core = wheel_probe_assets()
    rows = json.loads(read(index, pin))
    for issue, count in TEST_COUNTS.items():
        case_id = f"marcosschroh__dataclasses-avroschema-{issue}"
        (row,) = [entry for entry in rows if entry["input"]["task_id"] == case_id]
        task, truth, fixed, original, metadata = bind(row, index.parent, core)
        source = archive_files(truth.source.read(), large=True)
        locks = {
            item["name"]: item for item in tomllib.loads(source["poetry.lock"].decode())["package"]
        }
        if (
            "MIT License" not in source["LICENSE"].decode()
            or row["source_repository"] in exposed
            or metadata["names_not_declared_in_selected_module"]
            or len(truth.fail_to_pass) != 1
            or len(truth.pass_to_pass) != count - 1
        ):
            raise ValueError("protected reproduction inventory, license or eligibility changed")
        projects = {}
        names = PACKAGE_NAMES | ({"typing-inspection"} if issue == "870" else set())
        for name in sorted(names):
            package = locks[name]
            (wheel,) = [
                item
                for item in package["files"]
                if item["file"].endswith("-none-any.whl")
                or "cp313-cp313-manylinux_2_17_aarch64" in item["file"]
            ]
            projects[name] = {
                "filename": wheel["file"],
                "sha256": wheel["hash"].removeprefix("sha256:"),
                "version": package["version"],
            }
        yield (
            issue,
            projects,
            {
                "case_id": case_id,
                "source_revision": row["source_revision"],
                "input": task.model_dump(mode="json"),
                "truth": truth.model_dump(mode="json"),
                "roles": {"reference": fixed, "original": original},
                "reference_archive_sha256": row["reference_archive_sha256"],
                "existing_image_dependencies": [],
                "license_sha256": digest(source["LICENSE"]),
                "poetry_lock_sha256": digest(source["poetry.lock"]),
            },
        )


def prepare_download():
    opener = urllib.request.build_opener(NoRedirect())
    items = {}
    for _, pins, _ in projects():
        for package, pin in pins.items():
            filename = pin["filename"]
            if filename in items:
                continue
            url = f"https://pypi.org/pypi/{package}/{pin['version']}/json"
            with opener.open(url, timeout=15) as response:
                metadata = json.loads(response.read(2_000_000))
            (published,) = [row for row in metadata["urls"] if row["filename"] == filename]
            if published["yanked"] or published["digests"]["sha256"] != pin["sha256"]:
                raise ValueError("PyPI release differs from the publisher lock")
            items[filename] = pin | {
                "project": package,
                "url": published["url"],
                "size": published["size"],
            }
    total = sum(item["size"] for item in items.values())
    if total > MAX_DOWNLOAD:
        raise ValueError("reviewed artifact bytes exceed the cap")
    return {
        "files": items,
        "maximum_bytes": total,
        "maximum_downloads": len(items),
        "storage_floor_bytes": FLOOR,
        "models": 0,
        "cash_usd": 0,
        "installations": 0,
        "provider_disclosure": False,
        "retries": 0,
        "index_sha256": INDEX,
        "driver_sha256": digest(Path(__file__).read_bytes()),
    }


def acquire(exact):
    review = json.loads(read(WORK / "acquisition-review.json", exact))
    if review["driver_sha256"] != digest(Path(__file__).read_bytes()) or WHEELS.exists():
        raise ValueError("acquisition is not the exact unstarted review")
    if shutil.disk_usage(WORK).free < FLOOR + 3 * MAX_DOWNLOAD:
        raise ValueError("insufficient storage for acquisition and unpacking")
    WHEELS.mkdir(mode=0o700)
    opener = urllib.request.build_opener(NoRedirect())
    for name, item in review["files"].items():
        url = item["url"]
        if (
            not url.startswith("https://files.pythonhosted.org/packages/")
            or url.rsplit("/", 1)[-1] != name
        ):
            raise ValueError("unexpected file host or wheel name")
        with opener.open(url, timeout=30) as response:
            data = response.read(item["size"] + 1)
        if len(data) != item["size"] or digest(data) != item["sha256"]:
            raise ValueError("wheel size or publisher hash changed")
        write(WHEELS / name, data)
    runner.put(
        WORK / "acquisition-result.json",
        {
            "review_sha256": exact,
            "verified_files": len(review["files"]),
            "bytes": review["maximum_bytes"],
            "models": 0,
            "cash_usd": 0,
        },
    )


def support_files(pins):
    supplied = {}
    for name, item in pins.items():
        path = WHEELS / item["filename"]
        artifact = inspect_wheel(path, name, item["sha256"], item["version"])
        for require in map(Requirement, artifact["active_requires_dist"]):
            if (
                require.url
                or require.extras
                or require.name.lower().replace("_", "-") not in pins
                or (
                    pins[require.name.lower().replace("_", "-")]["version"] not in require.specifier
                )
            ):
                raise ValueError(f"publisher runtime dependency closure is incomplete: {require}")
        with ZipFile(path) as wheel:
            for entry in wheel.infolist():
                if entry.is_dir() or any(
                    part.endswith(".data") for part in Path(entry.filename).parts
                ):
                    continue
                if entry.filename in supplied:
                    raise ValueError("two wheel paths collide")
                supplied[entry.filename] = wheel.read(entry)
    return supplied


def support_check(issue, pins, *, prepare=False):
    root = SUPPORT / issue
    files = support_files(pins)
    if prepare:
        for name, value in files.items():
            path = root / name
            write(path, value)
            path.chmod(0o444)
    entries = list(root.rglob("*"))
    if (
        any(path.is_symlink() for path in entries)
        or {path.relative_to(root).as_posix() for path in entries if path.is_file()} != files.keys()
    ):
        raise ValueError("private read-only dependency projection differs")
    for name, value in files.items():
        path = root / name
        read(path, digest(value))
        if path.stat().st_mode & 0o777 != 0o444:
            raise ValueError("projected dependency permissions changed")
    return {name: digest(raw) for name, raw in files.items()}


def observer(issue, pins):
    runtime = FROZEN / "integrations/assessment-runtime"
    capture = (runtime / "repository_suite_native_capture.py").read_text()
    program = (runtime / "repository_suite_native_program.py").read_text()
    capture += "\n" + (Path(__file__).with_name("pytest_failure_diagnostics.py")).read_text()
    capture += "\nNativeCapture = diagnostic_capture(NativeCapture)\n"
    shape = "assert set(native) == {'statuses'}"
    if program.count(shape) != 2:
        raise ValueError("native response envelope changed")
    program = program.replace(shape, "assert set(native) == {'statuses', 'failure_sites'}")
    program = program.replace("'__AEEP_NATIVE_CAPTURE_SOURCE__'", repr(capture))
    root = str(SUPPORT / issue)
    versions = {key: pin["version"] for key, pin in pins.items()}
    expected = "assert all(version(n)==v for n,v in " + repr(versions) + ".items())"
    origin = (
        ";assert all(Path(module.__file__).is_relative_to("
        + repr(root)
        + ") for module in (fastavro._read,pydantic_core._pydantic_core))"
    )
    checks = (
        ";from importlib.metadata import version;"
        + expected
        + ";import fastavro._read,pydantic_core._pydantic_core"
        + origin
    )
    hook = "            + ';import pytest;"
    if program.count(hook) != 1:
        raise ValueError("native grader bootstrap hook changed")
    program = program.replace(
        hook,
        "            + " + repr(";sys.path.insert(0," + repr(root) + ")" + checks) + "\n" + hook,
    )
    compile(program, "<bound Avro protected grader>", "exec")
    return program


def definitions(issue, pins, case):
    spec = ExecutorSpec(
        id="repository.suite.observe",
        capability="assessment.repository_suite@1",
        kind="command",
        description="Protected Avro model generation tests with locked offline dependencies",
        config={
            "argv": ["python3", "-B", "-c", observer(issue, pins)],
            "argv_literal": True,
            "stdin_json": True,
            "timeout_seconds": 38,
            "max_stdin_bytes": LARGE_PAYLOAD,
            "max_output_bytes": 500_000,
            "output": {"type": "json"},
        },
    )
    return (
        spec,
        AssessmentEnvironment(
            environment_id=runner.NAME,
            kind="container",
            container_image=runner.CARRIER,
            identity={"source": SOURCE},
            container_runtime=runner.DOCKER,
            container_socket=runner.SOCKET,
            memory_mb=512,
            process_limit=96,
            container_tmpfs_mb=64,
            read_only_roots=[str(SUPPORT / issue)],
        ),
        [case],
    )


def configure(issue, pins, case):
    runner.NAME, runner.FROZEN = f"{NAME}-{issue}", FROZEN
    target = WORK / issue
    runner.REVIEW, runner.APPROVAL, runner.RUN = (
        target / "review.json",
        target / "scope.json",
        target / "execution",
    )
    runner.MAX_CALLS, runner.ROLE_SECONDS = 2, 50
    runner.definitions = lambda: definitions(issue, pins, case)
    base_probe = runner.verify_probe

    def checked_reply(reply, payload, expected, code):
        clean = scorer_reply(reply)
        runner.put(
            runner.RUN / f"observation-{'reference' if code == 0 else 'original'}.json", reply
        )
        return base_probe(clean, payload, expected, code)

    def scorer_reply(reply):
        return (
            {k: v for k, v in reply.items() if k != "failure_sites"}
            if isinstance(reply, dict)
            else reply
        )

    runner.verify_probe, runner.scorer_reply = checked_reply, scorer_reply

    async def review_fields():
        tree = support_check(issue, pins)
        fields, spec, env, cases = await BASE_REVIEW()
        return (
            fields
            | {
                "wrapper_sha256": file_digest(Path(__file__)),
                "storage_floor_bytes": FLOOR,
                "support_files": len(tree),
                "support_sha256": digest(json.dumps(tree, sort_keys=True).encode()),
                "source_lock_sha256": case["poetry_lock_sha256"],
                "source_license_sha256": case["license_sha256"],
                "wheel_pins": pins,
                "upstream_test_identities": len(case["truth"]["pass_to_pass"]) + 1,
                "authority": "Delegated first protected offline C13 checks, with no repeat or provider disclosure.",
            },
            spec,
            env,
            cases,
        )

    runner.review_fields = review_fields


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare-download", action="store_true")
    modes.add_argument("--acquire")
    modes.add_argument("--prepare", choices=TEST_COUNTS)
    modes.add_argument("--execute", nargs=2, metavar=("ISSUE", "DIGEST"))
    options = parser.parse_args()
    if options.prepare_download:
        path = WORK / "acquisition-review.json"
        WORK.mkdir(mode=0o700, exist_ok=True)
        runner.put(path, prepare_download())
        print(digest(path.read_bytes()))
    elif options.acquire:
        acquire(options.acquire)
    else:
        desired = options.prepare or options.execute[0]
        (project,) = [project for project in projects() if project[0] == desired]
        issue, pins, _ = project
        configure(*project)
        if options.prepare:
            support_check(issue, pins, prepare=not (SUPPORT / issue).exists())
            runner.REVIEW.parent.mkdir(mode=0o700, exist_ok=True)
            fields, _, _, _ = await runner.review_fields()
            runner.put(
                runner.REVIEW, fields | {"expires_at": (utc_now() + timedelta(hours=4)).isoformat()}
            )
            print(digest(runner.REVIEW.read_bytes()))
        else:
            exact = options.execute[1]
            read(runner.REVIEW, exact)
            if runner.RUN.exists() or runner.APPROVAL.exists():
                raise ValueError("retain all earlier attempts")
            runner.put(runner.APPROVAL, {"approved": True, "review_sha256": exact})
            raise SystemExit(not await runner.run(exact))


if __name__ == "__main__":
    asyncio.run(main())
