"""Continue the locked ExtractBench calibration after a wheel metadata parser error."""

import argparse
import asyncio
import json
import shutil
from datetime import datetime
from email.parser import BytesParser
from io import BytesIO
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

import check_extractbench_native_grade as driver

PRIOR = driver.PRIVATE
NAME = "c13-extractbench-native-grade-continuation-20261117"
PRIVATE = driver.INTAKE_ROOT / NAME
REVIEW = PRIVATE / "operation-review.json"
PRIOR_PINS = {
    "operation-review.json": "ba9f338866750df709e9beee92552b80a43c29560ebc2ad3e073187caa473414",
    "approval.json": "90174586d1f2ceec7e3ce2fc589718ff438d382647254c61f62acaab6ca5cacb",
    "approved-execution.log": "d3cd4214b4be4c40b319162a0a1d09e91a2e74e3391da9ccf70ce9f395940939",
    "execution/ledger.json": "b6e7fd84fc8510bf30b198e97dc5d7196b7ec9fc0cbae794db5e67c8df925db3",
    "execution/started.json": "ae7e4340ab4f0232531a3f830652ca6eff89fc52334d012a12f7532e0d1f7d56",
    "execution/receipts.sqlite3": "5afbf1c1cd3adbd337d8a30643d23bfacfffe862cc49a18843b8184e7d9a66db",
}
ACQUIRED = {"aiohttp", "anls-star", "anyio", "apted", "autoevals", "beautifulsoup4", "bleach"}
ACQUISITION_SECONDS = 419


def wheel_notice(path, pin, name):
    data = driver.read(path, pin["hash"].removeprefix("sha256:"))
    if len(data) != pin["size"]:
        raise ValueError("wheel size differs from its upstream lock")
    with ZipFile(BytesIO(data)) as archive:
        names = archive.namelist()
        # Vendored Python packages can ship their own nested distribution metadata.
        metadata, = [
            part for part in names
            if len(PurePosixPath(part).parts) == 2 and part.endswith(".dist-info/METADATA")
        ]
        header = archive.read(metadata)
        info = BytesParser().parsebytes(header, headersonly=True)
        distribution = info.get("Name", "").lower().replace("_", "-").replace(".", "-")
        if distribution != name or info["Version"] != pin["version"]:
            raise ValueError("wheel metadata differs from the locked distribution")
        root = metadata.rsplit("/", 1)[0] + "/"
        notices = {
            part: driver.digest(archive.read(part)) for part in sorted(names)
            if part.startswith(root) and not part.endswith("/") and any(
                word in Path(part).name.lower() for word in ("license", "licence", "copying", "notice")
            )
        }
        declared = bool(info.get("License-Expression") or info.get("License") or any(
            value.startswith("License ::") for value in info.get_all("Classifier", ())
        ))
        if not notices and not declared:
            raise ValueError(f"license evidence unavailable for {name} {pin['version']}")
        return {"metadata_sha256": driver.digest(header), "notice_sha256": notices, "declared_license_present": declared}


def prior_attempt():
    records = {name: driver.read(PRIOR / name, pin) for name, pin in PRIOR_PINS.items()}
    review = json.loads(records["operation-review.json"])
    ledger = json.loads(records["execution/ledger.json"])
    operation, = ledger["operations"]
    elapsed = operation["elapsed_seconds"]
    if (
        operation["stage"] != "pinned_dependency_acquisition"
        or not 0 <= elapsed <= 1
        or (PRIOR / "execution/result.json").exists()
        or (PRIOR / "execution/wheel-licenses.json").exists()
    ):
        raise ValueError("original attempt must show settled acquisition only")
    return review, operation


def inputs():
    previous, operation = prior_attempt()
    pins, fallback = driver.closure()
    files = driver.static_runtime(pins, fallback)
    fetch = set(previous["missing_wheels_to_fetch"]) - ACQUIRED
    if (
        pins != previous["wheels"]
        or len(fetch) != 29
        or sum(pins[name]["size"] for name in fetch) != 74_481_611
        or {item.name for item in (PRIOR / "runtime/wheels").iterdir()}
        != {pin["filename"] for name, pin in pins.items() if name not in fetch}
    ):
        raise ValueError("retained wheel set or outstanding artifacts changed")
    prior_notices = {
        name: wheel_notice(PRIOR / "runtime/wheels" / pin["filename"], pin, name)
        for name, pin in pins.items() if name not in fetch
    }
    if any(prior_notices.get(name) != notice for name, notice in previous["cached_wheel_license_evidence"].items()):
        raise ValueError("original cached wheel evidence changed")
    return previous, operation, pins, files, fetch, prior_notices


def fields():
    previous, operation, pins, files, fetch, retained_notices = inputs()
    current = driver.fields(pins, files, fetch)
    changes = {
        "cached_wheel_license_evidence", "missing_wheels_to_fetch", "download_byte_limit",
        "maximum_download_attempts", "invocation", "operation_seconds",
    }
    if {k: v for k, v in current.items() if k not in changes} != {
        k: v for k, v in previous.items() if k not in changes | {"expires_at"}
    }:
        raise ValueError("locked grader, dependencies or protections differ from the parent review")
    if current["cached_wheel_license_evidence"] != retained_notices:
        raise ValueError("continuation cache differs from the original wheel files")
    return {
        **current,
        "schema_version": "aeep.c13.extractbench-native-grade-continuation-review.v1",
        "continuation_driver_sha256": driver.file_digest(Path(__file__)),
        "previous_attempt_files": PRIOR_PINS,
        "previous_settled_operation": operation,
        "retained_wheels_not_redownloaded": sorted(ACQUIRED),
        "cumulative_operations": 3,
        "cumulative_maximum_elapsed_seconds": operation["elapsed_seconds"] + sum(current["operation_seconds"].values()),
        "expires_at": previous["expires_at"],
    }, pins, files


def configure_driver():
    driver.NAME = NAME
    driver.PRIVATE = PRIVATE
    driver.RUNTIME = PRIVATE / "runtime"
    driver.WHEELS = driver.RUNTIME / "wheels"
    driver.REVIEW = REVIEW
    driver.APPROVAL = PRIVATE / "approval.json"
    driver.RUN = PRIVATE / "execution"
    driver.FETCH_SECONDS = ACQUISITION_SECONDS
    driver.wheel_notice = wheel_notice


def prepare():
    previous, _, pins, files, fetch, _ = inputs()
    if datetime.fromisoformat(previous["expires_at"]) <= driver.utc_now():
        raise ValueError("original review window expired")
    if shutil.disk_usage(driver.ROOT).free < driver.HOST_RESERVE:
        raise ValueError("52 GiB preparation reserve unavailable")
    PRIVATE.mkdir(mode=0o700)
    driver.WHEELS.mkdir(mode=0o755, parents=True)
    for name, data in files.items():
        path = driver.RUNTIME / name
        path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        with path.open("xb") as target:
            target.write(data)
        path.chmod(0o444)
    for name, pin in pins.items():
        if name not in fetch:
            source = PRIOR / "runtime/wheels" / pin["filename"]
            target = driver.WHEELS / source.name
            with target.open("xb") as stream:
                stream.write(driver.read(source, pin["hash"].removeprefix("sha256:")))
            target.chmod(0o444)
    review, _, _ = fields()
    driver.put(REVIEW, review)


def verify(expected_digest=None):
    raw = REVIEW.read_bytes()
    if expected_digest is not None and driver.digest(raw) != expected_digest:
        raise ValueError("review changed after approval")
    current, pins, files = fields()
    if json.loads(raw) != current or datetime.fromisoformat(current["expires_at"]) <= driver.utc_now():
        raise ValueError("continuation review expired or has drifted")
    return current, pins, files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--execute-approved")
    args = parser.parse_args()
    configure_driver()
    if args.execute_approved:
        driver.verify_review = lambda: verify(args.execute_approved)
        raise SystemExit(not asyncio.run(driver.run(args.execute_approved)))
    if args.prepare:
        prepare()
    verify()
    print(driver.file_digest(REVIEW))


if __name__ == "__main__":
    main()
