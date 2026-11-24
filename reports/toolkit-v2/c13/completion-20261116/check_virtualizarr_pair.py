"""Run the unchanged VirtualiZarr 395 suite on an offline HDF5 runtime."""

import argparse
import asyncio
import json
import shutil
from datetime import timedelta
from pathlib import Path
from zipfile import ZipFile

import check_nested_pandas_pair as nested
import check_retained_carrier_batch as batch
import review_virtualizarr_runtime as runtime
from audit_staged_repository_graders import bind, wheel_probe_assets
from check_expansion_contracts import inspect_wheel
from stage_repository_transport import digest, read, write

from aeep.models import utc_now
from aeep_toolkit.install_runtime import Wheel, check_wheel, file_digest

runner = batch.runner
BASE_REVIEW, BASE_VERIFY = runner.review_fields, runner.verify_probe
NAME = "c13-virtualizarr-395-20261124"
WORK = runtime.WORK
SHARED = nested.WORK / "support/nested-pandas"
KEY = "virtualizarr"
SUPPORT = WORK / "support" / KEY
RUNTIME_REVIEW = runtime.BASE / "virtualizarr-395-runtime-review.json"
RUNTIME_SHA = "291229dc7052bfe0e254f60c3eed72da1fb9d1204ac84530095c1941607b1dc5"


def checked_libraries(pins, *, prepare):
    scoped = {}
    reused = {}
    provenance_path = WORK / "codec-registry-provenance.json"
    provenance = runner.get(provenance_path)
    license = read(WORK / "codec-registry-LICENSE", provenance["license_sha256"])
    if not license.startswith(b"BSD 3-Clause License"):
        raise ValueError("expected the retained publisher's BSD notice")
    for name, pin in pins.items():
        wheel = WORK / "wheels" / pin["filename"]
        if name == "imagecodecs-numcodecs":
            check_wheel(
                wheel,
                Wheel(
                    extension_id=name,
                    name="imagecodecs-numcodecs",
                    version=pin["version"],
                    filename=wheel.name,
                    sha256=pin["sha256"],
                ),
            )
            if (
                pin["sha256"] != provenance["wheel_sha256"]
                or not provenance["wheel_contains_only_metadata"]
            ):
                raise ValueError("codec registry metadata changed")
            scoped["imagecodecs_numcodecs-2024.6.1.dist-info/LICENSE"] = license
        else:
            inspected = inspect_wheel(wheel, name, pin["sha256"], pin["version"])
            if inspected["sha256"] != pin["sha256"]:
                raise ValueError("verified wheel inspection differs")
        shared_wheel = nested.WORK / "wheels" / wheel.name
        shared = shared_wheel.is_file() and file_digest(shared_wheel) == pin["sha256"]
        with ZipFile(wheel) as archive:
            for entry in archive.infolist():
                if entry.is_dir() or any(
                    part.endswith(".data") for part in Path(entry.filename).parts
                ):
                    continue
                target = reused if shared else scoped
                if entry.filename in scoped or entry.filename in reused:
                    raise ValueError("two packages supply the same runtime file")
                target[entry.filename] = archive.read(entry)
    if prepare and shutil.disk_usage(WORK).free < (
        batch.assets.FLOOR + sum(len(raw) + 4096 for raw in scoped.values()) + 8 * 1024**2
    ):
        raise ValueError("retained dependencies would cross the host reserve")
    for root, files in ((SHARED, reused), (SUPPORT, scoped)):
        for relative, body in files.items():
            path = root / relative
            sha = digest(body)
            if root == SUPPORT and prepare and not path.exists():
                write(path, body)
                path.chmod(0o444)
            read(path, sha)
            if path.stat().st_mode & 0o777 != 0o444:
                raise ValueError("reviewed dependency permissions changed")
    if (
        any(path.is_symlink() for path in SUPPORT.rglob("*"))
        or {path.relative_to(SUPPORT).as_posix() for path in SUPPORT.rglob("*") if path.is_file()}
        != scoped.keys()
    ):
        raise ValueError("unreviewed files in the VirtualiZarr support directory")
    return {
        "new_support_sha256": digest(
            json.dumps(
                {name: digest(body) for name, body in scoped.items()}, sort_keys=True
            ).encode()
        ),
        "shared_support_files_sha256": digest(
            json.dumps(
                {name: digest(body) for name, body in reused.items()}, sort_keys=True
            ).encode()
        ),
        "registry_license_provenance_sha256": file_digest(provenance_path),
        "new_support_bytes": sum(map(len, scoped.values())),
        "shared_support_bytes": sum(map(len, reused.values())),
    }


def configure(*, prepare):
    batch.cases()
    first = runner.get(WORK / "acquisition-result.json")
    lock = json.loads(read(WORK / "acquisition-review.json", first["review_sha256"]))
    plan = json.loads(read(RUNTIME_REVIEW, RUNTIME_SHA))
    if (
        not first["completed"]
        or lock["runtime_review_sha256"] != RUNTIME_SHA
        or lock["wrapper_sha256"] != file_digest(Path(runtime.__file__))
        or lock["driver_sha256"] != file_digest(Path(batch.__file__))
    ):
        raise ValueError("completed artifact acquisition no longer binds the review")
    pins = plan["wheel_pins"]
    _, _, required, _, _, _ = runtime.find_subject()
    (row,) = json.loads(read(runtime.INTAKE / "index.json", runtime.INDEX))
    _, core = wheel_probe_assets()
    task, truth, reference, original, _ = bind(row, runtime.INTAKE / "transport", core)
    source = {
        "case_id": task.task_id,
        "source_revision": row["source_revision"],
        "input": task.model_dump(mode="json"),
        "truth": truth.model_dump(mode="json"),
        "roles": {"reference": reference, "original": original},
        "reference_archive_sha256": row["reference_archive_sha256"],
        "existing_image_dependencies": [],
    }
    if len(required) != 78 or task.task_id != plan["case"]:
        raise ValueError("test scope changed")
    library_review = checked_libraries(pins, prepare=prepare)
    batch.WORK, batch.assets.SUPPORT = WORK, SUPPORT.parent
    batch.PROFILES[KEY] = {"native": ("h5py.h5", "numcodecs.blosc", "imagecodecs._zstd", "ujson")}
    batch.configure(KEY, source, set(truth.fail_to_pass), pins)
    spec, env, _ = runner.definitions()
    runner.NAME, runner.REVIEW, runner.RUN, runner.APPROVAL = (
        NAME,
        WORK / "operation-review.json",
        WORK / "execution",
        WORK / "scope.json",
    )
    runner.MAX_CALLS, runner.ROLE_SECONDS = 2, 100
    argv = list(spec.config["argv"])
    body = argv[-1]
    marker = f";sys.path.insert(0,{str(SUPPORT)!r});"
    if body.count(marker) != 1 or body.count("timeout=22") != 1:
        raise ValueError("runtime and timeout bootstrap hooks changed")
    body = body.replace(marker, f";sys.path[:0]=[{str(SUPPORT)!r},{str(SHARED)!r}];")
    capture = (
        batch.FROZEN / "integrations/assessment-runtime/repository_suite_native_capture.py"
    ).read_text()
    extra = Path(__file__).with_name("pytest_failure_diagnostics.py").read_text()
    if body.count(repr(capture)) != 1:
        raise ValueError("native failure diagnostics hook changed")
    body = body.replace(
        repr(capture),
        repr(capture + "\n" + extra + "\nNativeCapture = diagnostic_capture(NativeCapture)\n"),
    )
    body = body.replace(
        "assert set(native) == {'statuses'}", "assert set(native) == {'statuses', 'failure_sites'}"
    )
    argv[-1] = body.replace("timeout=22", "timeout=75")
    compile(argv[-1], "<reviewed VirtualiZarr observer>", "exec")
    spec = spec.model_copy(update={"config": spec.config | {"argv": argv, "timeout_seconds": 90}})
    env = env.model_copy(
        update={"environment_id": NAME, "read_only_roots": [str(SUPPORT), str(SHARED)]}
    )
    runner.definitions = lambda: (spec, env, [source])
    runner.scorer_reply = lambda reply: {k: v for k, v in reply.items() if k != "failure_sites"}

    def verify(reply, payload, expected, code):
        if not isinstance(reply, dict) or not isinstance(reply.get("failure_sites"), list):
            return False
        runner.put(runner.RUN / f"observation-{'original' if code else 'reference'}.json", reply)
        return BASE_VERIFY(runner.scorer_reply(reply), payload, expected, code)

    runner.verify_probe = verify

    async def fields():
        value, _, _, _ = await BASE_REVIEW()
        return (
            value
            | library_review
            | {
                "coordinator_sha256": file_digest(Path(__file__)),
                "storage_floor_bytes": batch.assets.FLOOR,
                "runtime_review_sha256": RUNTIME_SHA,
                "acquisition_review_sha256": first["review_sha256"],
                "published_network_tests_excluded_by_upstream_default": plan[
                    "publisher_remote_tests_skipped_by_default"
                ],
                "required_tests": len(required),
                "authority": "First contained, network-disabled protected pair under C13 engineering delegation.",
            },
            spec,
            env,
            [source],
        )

    runner.review_fields = fields


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_mutually_exclusive_group(required=True)
    command.add_argument("--prepare", action="store_true")
    command.add_argument("--execute")
    args = parser.parse_args()
    configure(prepare=args.prepare)
    if args.prepare:
        review, _, _, _ = await runner.review_fields()
        runner.put(
            runner.REVIEW, review | {"expires_at": (utc_now() + timedelta(hours=4)).isoformat()}
        )
        print(file_digest(runner.REVIEW))
    else:
        read(runner.REVIEW, args.execute)
        if runner.RUN.exists() or runner.APPROVAL.exists():
            raise ValueError("previous attempts must remain immutable")
        runner.put(runner.APPROVAL, {"approved": True, "review_sha256": args.execute})
        raise SystemExit(not await runner.run(args.execute))


if __name__ == "__main__":
    asyncio.run(main())
