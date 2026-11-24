"""Prepare and run the isolated qBraid image verifier on the retained carrier."""

import argparse
import asyncio
import json
import shutil
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.request import build_opener

import check_ccflow_guest_dependencies as guest
import check_retained_carrier_batch as batch
import prepare_pyqasm_transport as preparation
from check_ccflow_pair import compile_bootstrap
from check_expansion_contracts import NoRedirect, inspect_wheel
from stage_repository_transport import HERE, ROOT, digest, read, write

from aeep.assessment.repository_suites import SuiteAsset, SuiteAssetV5, SuiteTruthV6
from aeep.models import utc_now
from aeep_toolkit.install_runtime import file_digest

NAME = "c13-pyqasm-168-protected-pair-20261124"
WORK = ROOT / ".aeep/c13-cohort-runtime-20261124" / NAME
ASSETS = WORK / "assets"
WHEELS = WORK / "runtime"
NATIVE = WORK / "native"
EVIDENCE = HERE / "pyqasm-renderer-bound-preflight-20261124.json"
PIN = "855aa792aee44f1441523b89cd5130e61b726884e34e629438eb10516aee3672"
FLOOR = 50 * 1024**3
NATIVE_PACKAGES = {"markupsafe", "matplotlib"}
runner = batch.runner
BASE_REVIEW, BASE_VERIFY = runner.review_fields, runner.verify_probe


async def subject(evidence):
    prepared, task, previous, roles, source, overlay = await preparation.bind_transport()
    if prepared != evidence["transport"]:
        raise ValueError("the recovered image or protected source binding changed")
    paths = {
        ASSETS / "source.tar.gz": source,
        ASSETS / "tests.tar.gz": overlay,
    }

    def asset(name, data):
        return SuiteAssetV5(path=str(name), sha256=digest(data), size_bytes=len(data))

    pytest_ref = evidence["runtime"]["reused_artifacts"]["pytest"]
    pytest_path = ROOT / pytest_ref["path"]
    pytest_bytes = read(pytest_path, pytest_ref["sha256"])
    oracle = SuiteTruthV6.model_validate(
        previous.model_dump(mode="json")
        | {
            "input_sha256": prepared["input_sha256"],
            "source": asset(ASSETS / "source.tar.gz", source).model_dump(),
            "tests": asset(ASSETS / "tests.tar.gz", overlay).model_dump(),
            "wheels": [
                SuiteAsset(
                    path=str(pytest_path), sha256=digest(pytest_bytes), size_bytes=len(pytest_bytes)
                ).model_dump()
            ],
            "python": "3.12",
            "pytest": "8.3.4",
            "pytest_plugins": ["pytest_mpl.plugin"],
        }
    )
    return {
        "case_id": task.task_id,
        "input": task.model_dump(mode="json"),
        "truth": oracle.model_dump(mode="json"),
        "roles": roles,
        "source_revision": evidence["revision"],
        "reference_archive_sha256": prepared["roles"]["reference"]["protected_input_sha256"],
        "existing_image_dependencies": [
            "Matplotlib 3.10.0",
            "Python 3.12",
            "NumPy 2.2.3",
            "Pillow 13.0.0",
        ],
    }, paths


def retain_inputs(paths, runtime):
    package_bytes = sum(item["bytes"] for item in runtime["pending_wheels"].values())
    archive_bytes = sum(len(raw) for raw in paths.values())
    if shutil.disk_usage(WORK).free < FLOOR + package_bytes + archive_bytes + 2 * 1024**2:
        raise ValueError("host reserve does not cover the reviewed offline inputs")
    if any(ASSETS.iterdir()) or any(WHEELS.iterdir()):
        raise ValueError("preserve the previous intake and its evidence")
    records = {}
    opener = build_opener(NoRedirect())
    for name, item in runtime["pending_wheels"].items():
        if item.get("retained_cache"):
            suite = item["retained_cache"]
            data = read(ROOT / suite["path"], suite["sha256"])
        else:
            if (
                not item["url"].startswith("https://files.pythonhosted.org/packages/")
                or item["url"].rsplit("/", 1)[-1] != item["filename"]
            ):
                raise ValueError("published wheel location differs")
            with opener.open(item["url"], timeout=20) as stream:
                data = stream.read(item["bytes"] + 1)
        if len(data) != item["bytes"] or digest(data) != item["sha256"]:
            raise ValueError(f"wheel digest changed: {name}")
        target = WHEELS / item["filename"]
        write(target, data)
        target.chmod(0o444)
        records[name] = inspect_wheel(target, name, item["sha256"], item["version"])
    for file, data in paths.items():
        write(file, data)
        file.chmod(0o444)
    runner.put(
        WORK / "retained-inputs.json",
        {
            "evidence_sha256": PIN,
            "package_notices": {
                name: record["license_notice_digests"] for name, record in records.items()
            },
            "source_archives": {
                str(file.relative_to(ROOT)): digest(raw) for file, raw in paths.items()
            },
            "maximum_new_wheel_bytes": runtime["maximum_wheel_response_bytes"],
        },
    )


def prepare_native(runtime):
    files = {}
    for name in sorted(NATIVE_PACKAGES):
        pin = runtime["pending_wheels"][name]
        path = WHEELS / pin["filename"]
        read(path, pin["sha256"])
        distribution = guest.entries(path)
        if files.keys() & distribution.keys():
            raise ValueError("native dependency projections overlap")
        files.update(distribution)
    missing = {name: raw for name, raw in files.items() if not (NATIVE / name).exists()}
    needed = sum(max(4096, (len(data) + 4095) // 4096 * 4096) for data in missing.values())
    if needed and shutil.disk_usage(WORK).free < FLOOR + needed + 1024**2:
        raise ValueError("host reserve does not cover the reviewed native wheel projection")
    for name, data in files.items():
        path = NATIVE / name
        if name in missing:
            write(path, data)
            path.chmod(0o444)
        read(path, digest(data))


def verify_carrier(runtime):
    bound = runtime["carrier_pin"]
    reviewed = json.loads(read(ROOT / bound["path"], bound["sha256"]))["image"]
    if runtime["carrier_id"] != reviewed["id"] or runner.inspect_carrier() != reviewed["layers"]:
        raise ValueError("retained carrier no longer matches the review")
    for value in runtime["reused_artifacts"].values():
        read(ROOT / value["path"], value["sha256"])


def program(runtime, version):
    helper = Path(guest.__file__).read_text()
    native = batch.FROZEN / "integrations/assessment-runtime"
    entry = (native / "repository_suite_native_program.py").read_text()
    capture = (native / "repository_suite_native_capture.py").read_text()
    diagnostics = (HERE / "pytest_failure_diagnostics.py").read_text()
    portable = {
        str(WHEELS / item["filename"]): item["sha256"]
        for name, item in runtime["pending_wheels"].items()
        if name not in NATIVE_PACKAGES
    }
    metadata = f"Metadata-Version: 2.1\nName: pyqasm\nVersion: {version}\n"
    renderer = runtime["pending_wheels"]["matplotlib"]["version"]
    bootstrap = (
        ";from importlib.metadata import distribution;"
        f"assert distribution('matplotlib').version == {renderer!r};"
        f"assert str(distribution('matplotlib').locate_file('')) == {str(NATIVE)!r}"
    )
    anchors = {
        "        argv = ['--no-header'": (
            f"        support = project(root, {portable!r})\n"
            f"        project_info = support / {f'pyqasm-{version}.dist-info'!r}\n"
            "        project_info.mkdir()\n"
            f"        (project_info / 'METADATA').write_text({metadata!r})\n"
            "        argv = ['--mpl', '--no-header'"
        ),
        "            + ';import pytest;": (
            f'            + ";sys.path[:0]=" + repr([str(support), {str(NATIVE)!r}])\n'
            f"            + {bootstrap!r}\n"
            "            + ';import pytest;"
        ),
        "'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'": (
            "'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'MPLBACKEND': 'Agg', "
            "'LD_LIBRARY_PATH': '/opt/c13-eos-native', 'OPENBLAS_NUM_THREADS': '1'"
        ),
        "timeout=22": "timeout=35",
        "        assert log.stat().st_size": (
            "        if not events.is_file():\n"
            "            return bootstrap_failure(log, child.returncode)\n"
            "        assert log.stat().st_size"
        ),
        "'__AEEP_NATIVE_CAPTURE_SOURCE__'": repr(
            capture + "\n" + diagnostics + "\nNativeCapture = diagnostic_capture(NativeCapture)\n"
        ),
    }
    for before, after in anchors.items():
        if entry.count(before) != 1:
            raise ValueError("the pinned pytest observer changed")
        entry = entry.replace(before, after)
    envelope = "assert set(native) == {'statuses'}"
    if entry.count(envelope) != 2:
        raise ValueError("native statuses contract changed")
    output = (
        helper
        + "\n"
        + entry.replace(envelope, "assert set(native) == {'statuses', 'failure_sites'}")
    )
    compile(output, "<reviewed qBraid observer>", "exec")
    compile_bootstrap(output)
    return output


async def configure(case, paths, evidence, *, simulate):
    runtime = evidence["runtime"]
    runner.NAME, runner.FROZEN, runner.CARRIER = NAME, batch.FROZEN, runtime["carrier_id"]
    runner.MAX_CALLS, runner.ROLE_SECONDS = 2, 55
    runner.REVIEW, runner.APPROVAL, runner.RUN = (
        WORK / "operation-review.json",
        WORK / "scope.json",
        WORK / "execution",
    )
    verify_carrier(runtime)
    batch.assets.observer = lambda *_: program(runtime, evidence["transport"]["project_version"])
    spec, environment, _ = batch.assets.definitions("pyqasm", {}, case)
    spec = spec.model_copy(
        update={
            "description": "Protected qBraid visualization tests and image comparisons",
            "config": spec.config
            | {
                "argv": ["/opt/c13-eos/bin/python", *spec.config["argv"][1:]],
                "timeout_seconds": 45,
            },
        }
    )
    environment = environment.model_copy(
        update={
            "read_only_roots": [str(NATIVE), str(WHEELS)],
            "memory_mb": 768,
        }
    )
    runner.definitions = lambda: (spec, environment, [case])

    def verify(reply, payload, expected, code):
        if not isinstance(reply, dict):
            return False
        runner.put(runner.RUN / f"observation-{'original' if code else 'reference'}.json", reply)
        return BASE_VERIFY(runner.scorer_reply(reply), payload, expected, code)

    runner.scorer_reply = lambda reply: {
        key: value for key, value in reply.items() if key != "failure_sites"
    }
    runner.verify_probe = verify
    pin = None
    if not simulate:
        lock = runner.get(WORK / "retained-inputs.json")
        if (
            lock["evidence_sha256"] != PIN
            or lock["package_notices"].keys() != runtime["pending_wheels"].keys()
        ):
            raise ValueError("verified package intake is absent")
        for file, raw in paths.items():
            read(file, digest(raw))
        for name, item in runtime["pending_wheels"].items():
            path = WHEELS / item["filename"]
            checked = inspect_wheel(path, name, item["sha256"], item["version"])
            if checked["license_notice_digests"] != lock["package_notices"][name]:
                raise ValueError("package notices changed")
            if name in NATIVE_PACKAGES:
                for file, raw in guest.entries(path).items():
                    read(NATIVE / file, digest(raw))
        pin = file_digest(WORK / "retained-inputs.json")

    async def fields():
        raw, _, _, _ = await BASE_REVIEW()
        return (
            raw
            | {
                "coordinator_sha256": file_digest(Path(__file__)),
                "transport_preflight_sha256": PIN,
                "retained_inputs_sha256": pin,
                "storage_floor_bytes": FLOOR,
                "authority": "First protected qBraid pair with the same nine required checks including two image comparisons.",
            },
            spec,
            environment,
            [case],
        )

    runner.review_fields = fields
    if simulate:
        return await plan_in_memory(paths)
    return None


async def plan_in_memory(paths):
    disk_read = SuiteAssetV5.read

    def source_read(asset):
        if (name := Path(asset.path)) not in paths:
            return disk_read(asset)
        raw = paths[name]
        if digest(raw) != asset.sha256 or len(raw) != asset.size_bytes:
            raise ValueError("in-memory archive did not match its reviewed identity")
        return raw

    with patch.object(SuiteAssetV5, "read", source_read):
        review, _, _, _ = await runner.review_fields()
    return review


async def main():
    cli = argparse.ArgumentParser(description=__doc__)
    modes = cli.add_mutually_exclusive_group(required=True)
    modes.add_argument("--simulate", action="store_true")
    modes.add_argument("--acquire", action="store_true")
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--execute")
    args = cli.parse_args()
    evidence = json.loads(read(EVIDENCE, PIN))
    case, paths = await subject(evidence)
    for folder in (ASSETS, NATIVE, WHEELS):
        folder.mkdir(mode=0o700 if folder == ASSETS else 0o755, parents=True, exist_ok=True)
    if args.acquire:
        retain_inputs(paths, evidence["runtime"])
    elif args.simulate:
        result = await configure(case, paths, evidence, simulate=True)
        runner.put(
            WORK / "in-memory-renderer-bound-launch-preflight.json",
            result | {"protected_executions": 0},
        )
        print(file_digest(WORK / "in-memory-renderer-bound-launch-preflight.json"))
    else:
        if args.prepare:
            prepare_native(evidence["runtime"])
        await configure(case, paths, evidence, simulate=False)
        if args.prepare:
            review, _, _, _ = await runner.review_fields()
            runner.put(
                runner.REVIEW, review | {"expires_at": (utc_now() + timedelta(hours=5)).isoformat()}
            )
            print(file_digest(runner.REVIEW))
        else:
            read(runner.REVIEW, args.execute)
            if not runner.APPROVAL.exists():
                runner.put(runner.APPROVAL, {"approved": True, "review_sha256": args.execute})
            raise SystemExit(not await runner.run(args.execute))


if __name__ == "__main__":
    asyncio.run(main())
