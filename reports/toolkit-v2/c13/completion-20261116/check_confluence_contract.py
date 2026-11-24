"""Grade the published Confluence exporter CLI configuration repair offline."""

import argparse
import asyncio
import io
import json
import shutil
import tarfile
import tomllib
from datetime import timedelta
from pathlib import Path
from zipfile import ZipFile, ZipInfo

import check_avroschema_pairs as runtime_assets
import repository_offline_pair_batch as runner
from audit_staged_repository_graders import bind, index_paths, wheel_probe_assets
from packaging.markers import Marker
from packaging.tags import Tag
from packaging.utils import parse_wheel_filename
from plan_repository_expansion import previous_repositories
from stage_repository_transport import ROOT, digest, read, write
from stage_varex_calibration import FROZEN, SOURCE

import aeep
from aeep.assessment.repository_suites import archive_files
from aeep.assessment.verification import verification_source_digest
from aeep.models import utc_now
from aeep_toolkit.install_runtime import file_digest

CASE = "Spenhouet__confluence-markdown-exporter-92-aeep-contract-audit"
NAME = "c13-confluence-exporter-contract-20261124"
WORK = ROOT / ".aeep/c13-cohort-runtime-20261124" / NAME
INDEX = "668b21cc6493bbffc4a54fd622c63ef304f9953fd7853ba8b7651f536f556d3a"
MAX_BYTES = 12_000_000
FLOOR = runtime_assets.FLOOR
BASE_REVIEW = runner.review_fields
TQDM_SOURCE = "f8aef9c52c08c13a65f30ea34f4e5aac3fd1a34959879d7e59e63027286627f2"
TQDM_NOTICE = "dc33252e829015e3b150086fb9b3a40f6ad6fb32c2f4610ce812fa677d35986a"
RUNTIME_MARKERS = {
    "python_version": "3.13",
    "python_full_version": "3.13.15",
    "sys_platform": "linux",
    "platform_system": "Linux",
    "platform_machine": "aarch64",
    "extra": "",
}


def wheel_candidate(asset):
    filename = asset["url"].rsplit("/", 1)[-1]
    _, _, _, tags = parse_wheel_filename(filename)
    if Tag("py3", "none", "any") in tags:
        return 1
    pinned_linux = {
        Tag("cp313", "cp313", "manylinux2014_aarch64"),
        Tag("cp313", "cp313", "manylinux_2_17_aarch64"),
    }
    return 2 if tags & pinned_linux else 0


def locked_assets(source):
    lock = tomllib.loads(source["uv.lock"].decode())
    packages = {package["name"]: package for package in lock["package"]}
    if len(packages) != len(lock["package"]):
        raise ValueError("dependency lock has ambiguous project names")
    paths = ["confluence-markdown-exporter"]
    pins = {}
    while paths:
        name = paths.pop()
        if name in pins:
            continue
        package = packages[name]
        paths.extend(
            dep["name"]
            for dep in package.get("dependencies", [])
            if "marker" not in dep or Marker(dep["marker"]).evaluate(RUNTIME_MARKERS)
        )
        if name == "confluence-markdown-exporter":
            continue
        if package["source"] != {"registry": "https://pypi.org/simple"}:
            raise ValueError("publisher lock uses a different artifact registry")
        chosen = [asset for asset in package["wheels"] if wheel_candidate(asset)]
        chosen.sort(key=wheel_candidate, reverse=True)
        if not chosen or (
            len(chosen) > 1 and wheel_candidate(chosen[0]) == wheel_candidate(chosen[1])
        ):
            raise ValueError(f"no unique reviewed Linux wheel for {name}")
        asset = chosen[0]
        pins[name] = {
            "project": name,
            "version": package["version"],
            "size": asset["size"],
            "url": asset["url"],
            "filename": asset["url"].rsplit("/", 1)[-1],
            "sha256": asset["hash"].removeprefix("sha256:"),
        }
    return pins


def project():
    if (
        Path(aeep.__file__).resolve().parents[2] != FROZEN
        or verification_source_digest(FROZEN) != SOURCE
    ):
        raise ValueError("verified toolkit source changed")
    (path,) = [path for path, pin in index_paths() if pin == INDEX]
    (row,) = [entry for entry in json.loads(read(path, INDEX)) if entry["input"]["task_id"] == CASE]
    _, core = wheel_probe_assets()
    task, truth, repair, original, metadata = bind(row, path.parent, core)
    files = archive_files(truth.source.read(), large=True)
    req_path = path.parent / "protected" / CASE / "required.json"
    required = json.loads(read(req_path, row["protected_assets"]["required.json"]["sha256"]))
    faults = {row["protected_guard"], *required["published_fail_to_pass"]}
    if (
        len(truth.pass_to_pass) != 9
        or truth.fail_to_pass
        or len(faults) != 2
        or not faults <= set(truth.pass_to_pass)
        or metadata["names_not_declared_in_selected_module"]
        or not metadata["admits_python_3_13_0"]
        or row["source_repository"] in previous_repositories()[2]
        or not row["license_notices"]
        or any(
            digest(files[notice["file"]]) != notice["sha256"] for notice in row["license_notices"]
        )
    ):
        raise ValueError("protected identities, case independence or source licenses changed")
    pins = locked_assets(files)
    return (
        pins,
        faults,
        {
            "case_id": CASE,
            "source_revision": row["source_revision"],
            "input": task.model_dump(mode="json"),
            "truth": truth.model_dump(mode="json"),
            "roles": {"reference": repair, "original": original},
            "reference_archive_sha256": row["reference_archive_sha256"],
            "existing_image_dependencies": [],
            "lock_sha256": digest(files["uv.lock"]),
            "source_license_notices": row["license_notices"],
        },
    )


def import_only_pins(pins, *, prepare):
    """Keep publisher library bytes and exclude the unsupported JMESPath CLI."""
    source = read(WORK / "tqdm-4.67.1.tar.gz", TQDM_SOURCE)
    with tarfile.open(fileobj=io.BytesIO(source), mode="r:gz") as archive:
        member = archive.getmember("tqdm-4.67.1/LICENCE")
        if not member.isfile() or member.size > 32_000:
            raise ValueError("publisher license exceeds its evidence bounds")
        with archive.extractfile(member) as notice_file:
            notice = notice_file.read()
    if digest(notice) != TQDM_NOTICE:
        raise ValueError("tqdm license notice changed")
    projected = dict(pins)
    for name in ("jmespath", "tqdm"):
        pin = pins[name]
        filename = pin["filename"]
        raw = read(WORK / "wheels" / filename, pin["sha256"])
        target = WORK / "import-only-licensed" / filename
        buffer = io.BytesIO()
        with ZipFile(io.BytesIO(raw)) as zip_in, ZipFile(buffer, "w") as zip_out:
            excluded = []
            for item in zip_in.infolist():
                if name == "jmespath" and item.filename == "jmespath-1.0.1.data/scripts/jp.py":
                    excluded.append(item.filename)
                else:
                    zip_out.writestr(item, zip_in.read(item))
            if name == "tqdm":
                zip_out.writestr(ZipInfo("tqdm-4.67.1.dist-info/licenses/LICENSE"), notice)
            elif excluded != ["jmespath-1.0.1.data/scripts/jp.py"]:
                raise ValueError("the import-only wheel projection differs")
        payload = buffer.getvalue()
        if prepare and not target.exists():
            write(target, payload)
        read(target, digest(payload))
        projected[name] = pin | {"sha256": digest(payload), "publisher_wheel_sha256": pin["sha256"]}
    return projected


def projected_support(pins, *, prepare=False):
    projected = import_only_pins(pins, prepare=prepare)
    for item in projected.values():
        if "publisher_wheel_sha256" in item:
            continue
        source = WORK / "wheels" / item["filename"]
        target = WORK / "import-only-licensed" / item["filename"]
        if prepare and not target.exists():
            write(target, read(source, item["sha256"]))
        read(target, item["sha256"])
    runtime_assets.WHEELS = WORK / "import-only-licensed"
    tree = runtime_assets.support_check(
        "cli", projected, prepare=prepare and not (runtime_assets.SUPPORT / "cli").exists()
    )
    return projected, tree


def configure(pins, faults, case):
    runtime_assets.WORK, runtime_assets.WHEELS, runtime_assets.SUPPORT = (
        WORK,
        WORK / "wheels",
        WORK / "support",
    )
    runtime_assets.MAX_DOWNLOAD = MAX_BYTES
    runner.NAME, runner.FROZEN = NAME, FROZEN
    runner.REVIEW, runner.APPROVAL, runner.RUN = (
        WORK / "review.json",
        WORK / "scope.json",
        WORK / "execution",
    )
    runner.MAX_CALLS, runner.ROLE_SECONDS = 2, 50

    def observer(_issue, dependencies):
        source = FROZEN / "integrations/assessment-runtime"
        program = (source / "repository_suite_native_program.py").read_text()
        capture = (source / "repository_suite_native_capture.py").read_text()
        program = program.replace("'__AEEP_NATIVE_CAPTURE_SOURCE__'", repr(capture))
        root = str(runtime_assets.SUPPORT / "cli")
        versions = {key: pin["version"] for key, pin in dependencies.items()}
        check = (
            f";sys.path.insert(0,{root!r});from importlib.metadata import version;"
            f"assert all(version(n)==v for n,v in {versions!r}.items());"
            f"import pydantic_core._pydantic_core,yaml._yaml;"
            f"assert all(Path(m.__file__).is_relative_to({root!r}) "
            "for m in (pydantic_core._pydantic_core,yaml._yaml))"
        )
        hook = "            + ';import pytest;"
        if program.count(hook) != 1:
            raise ValueError("native grader bootstrap hook changed")
        program = program.replace(hook, "            + " + repr(check) + "\n" + hook)
        compile(program, "<protected exporter CLI grader>", "exec")
        return program

    def expected(truth, role):
        statuses = dict.fromkeys(truth["pass_to_pass"], "PASSED")
        if role == "original":
            statuses.update(dict.fromkeys(faults, "FAILED"))
        return statuses

    base_probe = runner.verify_probe

    def verify(reply, payload, statuses, code):
        runner.put(
            runner.RUN / f"observation-{'reference' if code == 0 else 'original'}.json", reply
        )
        return base_probe(reply, payload, statuses, code)

    def definitions():
        spec, env, cases = runtime_assets.definitions("cli", pins, case)
        return (
            spec.model_copy(
                update={"description": "Protected offline Confluence exporter CLI checks"}
            ),
            env,
            cases,
        )

    runtime_assets.observer = observer
    runner.definitions = definitions
    runner.expected_statuses, runner.verify_probe = expected, verify

    async def review_fields():
        projected, inventory = projected_support(pins)
        body, spec, env, cases = await BASE_REVIEW()
        return (
            body
            | {
                "wrapper_sha256": file_digest(Path(__file__)),
                "storage_floor_bytes": FLOOR,
                "uv_lock_sha256": case["lock_sha256"],
                "wheel_pins": pins,
                "library_only_projections": {
                    key: projected[key]["sha256"] for key in ("jmespath", "tqdm")
                },
                "tqdm_source_sha256": TQDM_SOURCE,
                "tqdm_license_sha256": TQDM_NOTICE,
                "support_files": len(inventory),
                "support_sha256": digest(json.dumps(inventory, sort_keys=True).encode()),
                "license_notices": case["source_license_notices"],
                "expected_original_failures": sorted(faults),
                "authority": "Delegated initial C13 protected grading. Existing image, two offline calls and no outside disclosure.",
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
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--execute")
    args = parser.parse_args()
    pins, faults, case = project()
    configure(pins, faults, case)
    WORK.mkdir(mode=0o700, exist_ok=True)
    total = sum(item["size"] for item in pins.values())
    if total > MAX_BYTES or shutil.disk_usage(WORK).free < FLOOR + 3 * MAX_BYTES:
        raise ValueError("offline runtime staging would exceed its storage envelope")
    if args.prepare_download:
        path = WORK / "acquisition-review.json"
        runner.put(
            path,
            {
                "files": {item["filename"]: item for item in pins.values()},
                "maximum_bytes": total,
                "maximum_downloads": len(pins),
                "installations": 0,
                "source_lock_sha256": case["lock_sha256"],
                "storage_floor_bytes": FLOOR,
                "models": 0,
                "cash_usd": 0,
                "provider_disclosure": False,
                "retries": 0,
                "driver_sha256": file_digest(Path(runtime_assets.__file__)),
                "entry_point_sha256": file_digest(Path(__file__)),
            },
        )
        print(file_digest(path))
    elif args.acquire:
        record = json.loads(read(WORK / "acquisition-review.json", args.acquire))
        if record["entry_point_sha256"] != file_digest(Path(__file__)):
            raise ValueError("acquisition coordinator changed")
        runtime_assets.acquire(args.acquire)
    elif args.prepare:
        projected_support(pins, prepare=True)
        body, _, _, _ = await runner.review_fields()
        runner.put(
            runner.REVIEW, body | {"expires_at": (utc_now() + timedelta(hours=4)).isoformat()}
        )
        print(file_digest(runner.REVIEW))
    else:
        read(runner.REVIEW, args.execute)
        if runner.RUN.exists() or runner.APPROVAL.exists():
            raise ValueError("retain the earlier attempt and its charges")
        runner.put(runner.APPROVAL, {"approved": True, "review_sha256": args.execute})
        raise SystemExit(not await runner.run(args.execute))


if __name__ == "__main__":
    asyncio.run(main())
