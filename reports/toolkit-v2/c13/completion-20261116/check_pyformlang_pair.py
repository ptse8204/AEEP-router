"""Grade the protected Pyformlang CFG regression on the retained offline carrier."""

import argparse
import ast
import asyncio
import io
import json
import shutil
import tarfile
from datetime import timedelta
from pathlib import Path
from zipfile import ZipFile, ZipInfo

import check_retained_carrier_batch as batch
from audit_staged_repository_graders import bind, wheel_probe_assets
from plan_repository_expansion import previous_repositories
from stage_repository_transport import ROOT, digest, read, write

from aeep.assessment.repository_suites import archive_files
from aeep.models import utc_now
from aeep_toolkit.install_runtime import file_digest

NAME = "c13-pyformlang-35-licensed-runtime-20261124"
BASE = ROOT / ".aeep/c13-cohort-runtime-20261124"
WORK = BASE / NAME
INTAKE = BASE / "c13-parser-docs-first-sources-20261124/intake"
INDEX = "ef2d1648ce8de16958631c24968acc85848ece47e82b1a1f6bffe0125b8fdfc5"
SDIST_SHA = "c2148f681c4a33e08bf0e26a9e5f8e4099a82e0e2a068098f32ce86577364ad5"
ACQUIRED_BY = "58cc5f10e278fcd90147271c681665ccbf83feb12d62662d85c75461057198da"
CASE = "Aunsiels__pyformlang-35-aeep-contract-audit"
REVISION = "04d769ab7da44a7ae80eec49661c0b03fdcd0bac"
LICENSE = "eb94cc996b24f6a5d162693e5cc0b75671810ec10b3731f93b445705a0ae6182"
VERSIONS = {"networkx": "3.4.2", "numpy": "2.2.6", "pydot": "4.0.1", "pyparsing": "3.3.2"}
runner = batch.runner
BASE_REVIEW, BASE_VERIFY = runner.review_fields, runner.verify_probe


def subject():
    batch.cases()
    (row,) = [
        row
        for row in json.loads(read(INTAKE / "index.json", INDEX))
        if row["input"]["task_id"] == CASE
    ]
    task, truth, reference, original, metadata = bind(
        row, INTAKE / "transport", wheel_probe_assets()[1]
    )
    source = archive_files(truth.source.read(), large=True)
    required = json.loads(
        read(
            INTAKE / "transport/protected" / CASE / "required.json",
            row["protected_assets"]["required.json"]["sha256"],
        )
    )
    faults = {row["protected_guard"], *required["published_fail_to_pass"]}
    setup = ast.parse(source["setup.py"])
    (dependency_name,) = [
        node.value
        for node in ast.walk(setup)
        if isinstance(node, ast.keyword) and node.arg == "install_requires"
    ]
    declared = [
        ast.literal_eval(node.value)
        for node in setup.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(name, ast.Name) and name.id == dependency_name.id for name in node.targets
        )
    ]
    if (
        task.task_id != CASE
        or row["source_revision"] != REVISION
        or digest(source["LICENSE"]) != LICENSE
        or declared != [["networkx", "numpy", "pydot"]]
        or metadata.get("admits_python_3_13_0") is False
        or metadata["names_not_declared_in_selected_module"]
        or row["source_repository"] in previous_repositories()[2]
        or truth.fail_to_pass
        or len(truth.pass_to_pass) != 48
        or len(faults) != 2
        or not faults <= set(truth.pass_to_pass)
    ):
        raise ValueError(
            f"publisher source, runtime declarations or grade scope changed: {declared}"
        )
    return {
        "case_id": CASE,
        "source_revision": REVISION,
        "input": task.model_dump(mode="json"),
        "truth": truth.model_dump(mode="json"),
        "roles": {"reference": reference, "original": original},
        "reference_archive_sha256": row["reference_archive_sha256"],
        "existing_image_dependencies": [],
    }, faults


def intake():
    batch.PROFILES = {"pyformlang": {"versions": VERSIONS}}
    batch.CACHE_DIRS += (
        str((BASE / "c13-nested-pandas-302-20261124/wheels").relative_to(ROOT)),
        ".aeep/completion-20261116/locify-locked-runtime-assets-20261119/downloads",
        ".aeep/completion-20261116/fusesoc-runtime-wheels",
    )
    batch.MAX_FETCH = 100_000
    batch.WORK = WORK
    review = batch.acquire_plan() | {
        "coordinator_sha256": file_digest(Path(__file__)),
        "source_index_sha256": INDEX,
    }
    downloads = [pin for pin in review["files"].values() if not pin["cache"]]
    if len(downloads) != 1 or downloads[0]["sha256"] != (
        "869c0efadd2708c0be1f916eb669f3d664ca684bc57ffb7ecc08e70d5e93fee6"
    ):
        raise ValueError("expected only the one published Pydot wheel")
    if shutil.disk_usage(WORK).free < batch.assets.FLOOR + 96 * 1024**2:
        raise ValueError("insufficient headroom for the pinned archives and projection")
    path = WORK / "acquisition-review.json"
    runner.put(path, review)
    batch.acquire(review)
    runner.put(
        WORK / "acquisition-result.json",
        {
            "review_sha256": file_digest(path),
            "retained_files": len(review["files"]),
            "download_bytes": review["maximum_response_bytes"],
        },
    )


def project_notices(pins, *, prepare):
    """Supply same-release notices missing from the Pydot wheel."""
    root = WORK / "libraries"
    raw_source = read(WORK / "pydot-4.0.1.tar.gz", SDIST_SHA)
    result = {}
    for name, item in pins.items():
        filename = item["filename"]
        raw = read(WORK / "wheels" / filename, item["sha256"])
        if name == "pydot":
            projection = io.BytesIO()
            with (
                tarfile.open(fileobj=io.BytesIO(raw_source)) as source,
                ZipFile(io.BytesIO(raw)) as wheel,
                ZipFile(projection, "w") as amended,
            ):
                for entry in wheel.infolist():
                    value = wheel.read(entry)
                    if entry.filename.endswith(".py"):
                        member = source.getmember("pydot-4.0.1/src/" + entry.filename)
                        if not member.isfile() or source.extractfile(member).read() != value:
                            raise ValueError("wheel code differs from the notice-bearing source")
                    amended.writestr(entry, value)
                for license_name in ("MIT", "Python-2.0"):
                    member = source.getmember(f"pydot-4.0.1/LICENSES/{license_name}.txt")
                    target = f"pydot-4.0.1.dist-info/licenses/LICENSE-{license_name}.txt"
                    if not member.isfile() or target in wheel.namelist():
                        raise ValueError("license projection no longer matches the source")
                    # Preserve the two retained notice entries byte for byte.
                    entry = ZipInfo(target, (2026, 11, 24, 14, 53, 10))
                    amended.writestr(entry, source.extractfile(member).read())
            raw = projection.getvalue()
        sha = digest(raw)
        path = root / filename
        if prepare and not path.exists():
            write(path, raw)
        read(path, sha)
        result[name] = item | {"sha256": sha}
    batch.assets.WHEELS = root
    return result


def configure(case, faults, *, prepare):
    result = runner.get(WORK / "acquisition-result.json")
    lock = json.loads(read(WORK / "acquisition-review.json", result["review_sha256"]))
    if (
        lock["coordinator_sha256"] not in {ACQUIRED_BY, file_digest(Path(__file__))}
        or lock["driver_sha256"] != file_digest(Path(batch.__file__))
        or lock["source_index_sha256"] != INDEX
    ):
        raise ValueError("acquisition review bindings changed")
    pins = {item["name"]: item for item in lock["files"].values()}
    if {name: item["version"] for name, item in pins.items()} != VERSIONS:
        raise ValueError("runtime pin set changed")
    batch.WORK = WORK
    batch.assets.SUPPORT = WORK / "support"
    stage_support = prepare and not (batch.assets.SUPPORT / "pyformlang").exists()
    if stage_support and shutil.disk_usage(WORK).free < batch.assets.FLOOR + 86 * 1024**2:
        raise ValueError("insufficient headroom for dependency projection")
    pins = project_notices(pins, prepare=prepare)
    tree = batch.assets.support_check("pyformlang", pins, prepare=stage_support)
    batch.PROFILES["pyformlang"] = {"native": ("numpy._core._multiarray_umath",)}
    batch.configure("pyformlang", case, faults, pins)
    spec, env, _ = runner.definitions()
    runner.NAME, runner.REVIEW, runner.RUN, runner.APPROVAL = (
        NAME,
        WORK / "operation-review-frozen-notices.json",
        WORK / "execution",
        WORK / "scope.json",
    )
    runner.definitions = lambda: (spec, env, [case])
    argv = list(spec.config["argv"])
    capture = (
        batch.FROZEN / "integrations/assessment-runtime/repository_suite_native_capture.py"
    ).read_text()
    diagnostics = Path(__file__).with_name("pytest_failure_diagnostics.py").read_text()
    program = argv[-1]
    envelope = "assert set(native) == {'statuses'}"
    if program.count(repr(capture)) != 1 or program.count(envelope) != 2:
        raise ValueError("protected pytest observer changed")
    argv[-1] = program.replace(
        repr(capture),
        repr(
            capture + "\n" + diagnostics + "\nNativeCapture = diagnostic_capture(NativeCapture)\n"
        ),
    ).replace(envelope, "assert set(native) == {'statuses', 'failure_sites'}")
    compile(argv[-1], "<reviewed Pyformlang observer>", "exec")
    spec = spec.model_copy(update={"config": spec.config | {"argv": argv}})

    def verify(reply, payload, expected, code):
        if not isinstance(reply, dict) or not isinstance(reply.get("failure_sites"), list):
            return False
        runner.put(runner.RUN / f"observation-{'original' if code else 'reference'}.json", reply)
        return BASE_VERIFY(runner.scorer_reply(reply), payload, expected, code)

    runner.scorer_reply = lambda reply: {k: v for k, v in reply.items() if k != "failure_sites"}
    runner.verify_probe = verify

    async def fields():
        value, _, _, _ = await BASE_REVIEW()
        return (
            value
            | {
                "coordinator_sha256": file_digest(Path(__file__)),
                "source_index_sha256": INDEX,
                "storage_floor_bytes": batch.assets.FLOOR,
                "source_license_sha256": LICENSE,
                "pydot_notice_source_sha256": SDIST_SHA,
                "package_pins_with_notices": pins,
                "wheel_intake_sha256": result["review_sha256"],
                "support_tree_sha256": digest(json.dumps(tree, sort_keys=True).encode()),
                "expected_original_failures": sorted(faults),
                "authority": "First bounded protected C13 pair with existing offline controls.",
            },
            spec,
            env,
            [case],
        )

    runner.review_fields = fields


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--acquire", action="store_true")
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--execute")
    args = parser.parse_args()
    case, faults = subject()
    batch.assets.WHEELS = WORK / "wheels"
    if args.acquire:
        WORK.mkdir(mode=0o700)
        intake()
        return
    configure(case, faults, prepare=args.prepare)
    if args.prepare:
        review, _, _, _ = await runner.review_fields()
        runner.put(
            runner.REVIEW, review | {"expires_at": (utc_now() + timedelta(hours=4)).isoformat()}
        )
        print(file_digest(runner.REVIEW))
    else:
        read(runner.REVIEW, args.execute)
        if runner.RUN.exists() or runner.APPROVAL.exists():
            raise ValueError("preserve the earlier attempt and charges")
        runner.put(runner.APPROVAL, {"approved": True, "review_sha256": args.execute})
        raise SystemExit(not await runner.run(args.execute))


if __name__ == "__main__":
    asyncio.run(main())
