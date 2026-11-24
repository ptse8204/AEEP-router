"""Reproduce Towncrier's configuration fallback in the protected CLI grader."""

import argparse
import asyncio
import io
import json
import shutil
import urllib.request
from datetime import timedelta
from pathlib import Path
from zipfile import ZipFile

import check_avroschema_pairs as assets
import repository_offline_pair_batch as runner
from audit_staged_repository_graders import bind, index_paths, wheel_probe_assets
from check_confluence_contract import wheel_candidate
from check_expansion_contracts import NoRedirect
from plan_repository_expansion import previous_repositories
from stage_repository_transport import ROOT, digest, read, write
from stage_varex_calibration import FROZEN, SOURCE

import aeep
from aeep.assessment.repository_suites import archive_files
from aeep.assessment.verification import verification_source_digest
from aeep.models import utc_now
from aeep_toolkit.install_runtime import file_digest

CASE = "twisted__towncrier-687-aeep-contract-audit"
NAME = "c13-towncrier-contract-20261124"
WORK = ROOT / ".aeep/c13-cohort-runtime-20261124" / NAME
INDEX = "96857b706c83613ea2eded9987ea5bb07260494f80945f868cbf3fa7720a8d48"
VERSIONS = {
    "attrs": "25.4.0",
    "automat": "24.8.1",
    "click": "8.2.1",
    "constantly": "23.10.4",
    "hyperlink": "21.0.0",
    "idna": "3.10",
    "incremental": "24.7.2",
    "jinja2": "3.1.6",
    "markupsafe": "3.0.3",
    "packaging": "25.0",
    "setuptools": "75.8.2",
    "twisted": "24.11.0",
    "typing-extensions": "4.15.0",
    "zope-interface": "7.2",
}
BASE_REVIEW = runner.review_fields


def project():
    if (
        Path(aeep.__file__).resolve().parents[2] != FROZEN
        or verification_source_digest(FROZEN) != SOURCE
    ):
        raise ValueError("source is outside the verified revision")
    (index,) = [path for path, pin in index_paths() if pin == INDEX]
    (row,) = [item for item in json.loads(read(index, INDEX)) if item["input"]["task_id"] == CASE]
    task, truth, repair, original, metadata = bind(row, index.parent, wheel_probe_assets()[1])
    source = archive_files(truth.source.read(), large=True)
    required = json.loads(
        read(
            index.parent / "protected" / CASE / "required.json",
            row["protected_assets"]["required.json"]["sha256"],
        )
    )
    faults = {row["protected_guard"], *required["published_fail_to_pass"]}
    if (
        len(truth.pass_to_pass) != 17
        or len(faults) != 3
        or not faults <= set(truth.pass_to_pass)
        or truth.fail_to_pass
        or not metadata["admits_python_3_13_0"]
        or metadata["names_not_declared_in_selected_module"]
        or row["source_repository"] in previous_repositories()[2]
        or not row["license_notices"]
        or any(
            digest(source[notice["file"]]) != notice["sha256"] for notice in row["license_notices"]
        )
    ):
        raise ValueError("published configuration audit bindings differ")
    return faults, {
        "case_id": CASE,
        "source_revision": row["source_revision"],
        "input": task.model_dump(mode="json"),
        "truth": truth.model_dump(mode="json"),
        "roles": {"reference": repair, "original": original},
        "reference_archive_sha256": row["reference_archive_sha256"],
        "existing_image_dependencies": [],
        "license_notices": row["license_notices"],
    }


def download_review(file):
    opener = urllib.request.build_opener(NoRedirect())
    pins = {}
    for name, version in VERSIONS.items():
        with opener.open(f"https://pypi.org/pypi/{name}/{version}/json", timeout=15) as response:
            metadata = json.loads(response.read(2_000_000))
        choices = [
            row
            for row in metadata["urls"]
            if row["packagetype"] == "bdist_wheel" and not row["yanked"] and wheel_candidate(row)
        ]
        choices.sort(key=wheel_candidate, reverse=True)
        if not choices or (
            len(choices) > 1 and wheel_candidate(choices[0]) == wheel_candidate(choices[1])
        ):
            raise ValueError(f"no unique compatible publisher wheel: {name}")
        row = choices[0]
        pins[row["filename"]] = {
            "project": name,
            "version": version,
            "filename": row["filename"],
            "size": row["size"],
            "sha256": row["digests"]["sha256"],
            "url": row["url"],
        }
    size = sum(item["size"] for item in pins.values())
    if size > assets.MAX_DOWNLOAD:
        raise ValueError("wheel acquisition exceeds review bound")
    runner.put(
        file,
        {
            "files": pins,
            "maximum_bytes": size,
            "maximum_downloads": len(pins),
            "retries": 0,
            "installations": 0,
            "provider_disclosure": False,
            "cash_usd": 0,
            "models": 0,
            "index_sha256": INDEX,
            "driver_sha256": file_digest(Path(assets.__file__)),
            "entry_point_sha256": file_digest(Path(__file__)),
        },
    )


def projection(pins, *, prepare=False):
    """Project the locked imports without registering startup hooks."""
    projected = {}
    for name, pin in pins.items():
        filename = pin["filename"]
        body = read(WORK / "wheels" / filename, pin["sha256"])
        if name in {"setuptools", "zope-interface"}:
            hook = (
                "distutils-precedence.pth"
                if name == "setuptools"
                else "zope.interface-7.2-py3.13-nspkg.pth"
            )
            buffer = io.BytesIO()
            excluded = []
            with ZipFile(io.BytesIO(body)) as upstream, ZipFile(buffer, "w") as clean:
                for entry in upstream.infolist():
                    if entry.filename == hook or (
                        entry.filename.startswith("setuptools/_vendor/")
                        and entry.filename.endswith(
                            (".dist-info/METADATA", ".dist-info/entry_points.txt")
                        )
                    ):
                        excluded.append(entry.filename)
                    else:
                        clean.writestr(entry, upstream.read(entry))
            if hook not in excluded:
                raise ValueError("locked startup hook inventory changed")
            body = buffer.getvalue()
        target = WORK / "libraries" / filename
        sha = digest(body)
        if prepare and not target.exists():
            write(target, body)
        read(target, sha)
        projected[name] = pin | {"sha256": sha}
    assets.WHEELS = WORK / "libraries"
    return projected


def configure(faults, case, pins):
    runner.NAME, runner.FROZEN = NAME, FROZEN
    runner.REVIEW, runner.APPROVAL, runner.RUN = (
        WORK / "review.json",
        WORK / "scope.json",
        WORK / "execution",
    )
    runner.MAX_CALLS, runner.ROLE_SECONDS = 2, 50

    def observer(issue, pins):
        source = FROZEN / "integrations/assessment-runtime"
        program = (source / "repository_suite_native_program.py").read_text()
        capture = (source / "repository_suite_native_capture.py").read_text()
        old = "            + ';import pytest;"
        support = str(assets.SUPPORT / issue)
        versions = {name: pin["version"] for name, pin in pins.items()}
        bootstrap = (
            f";sys.path.insert(0,{support!r});from importlib.metadata import version;"
            f"assert all(version(n)==v for n,v in {versions!r}.items());"
            "import markupsafe._speedups,zope.interface._zope_interface_coptimizations;"
            f"assert all(Path(m.__file__).is_relative_to({support!r}) "
            "for m in (markupsafe._speedups,zope.interface._zope_interface_coptimizations))"
        )
        if program.count(old) != 1:
            raise ValueError("native bootstrap entry point changed")
        program = program.replace(old, "            + " + repr(bootstrap) + "\n" + old)
        return program.replace("'__AEEP_NATIVE_CAPTURE_SOURCE__'", repr(capture))

    def definitions():
        spec, env, cases = assets.definitions("towncrier", pins, case)
        return (
            spec.model_copy(update={"description": "Protected Towncrier configuration checks"}),
            env,
            cases,
        )

    def statuses(truth, role):
        result = dict.fromkeys(truth["pass_to_pass"], "PASSED")
        if role == "original":
            result.update(dict.fromkeys(faults, "FAILED"))
        return result

    base_probe = runner.verify_probe

    def observe(reply, payload, expected, code):
        runner.put(runner.RUN / f"observation-{'original' if code else 'reference'}.json", reply)
        return base_probe(reply, payload, expected, code)

    assets.observer = observer
    runner.definitions, runner.expected_statuses, runner.verify_probe = (
        definitions,
        statuses,
        observe,
    )

    async def review_fields():
        library_pins = projection(pins)
        files = assets.support_check("towncrier", library_pins)
        fields, spec, env, cases = await BASE_REVIEW()
        return (
            fields
            | {
                "wrapper_sha256": file_digest(Path(__file__)),
                "storage_floor_bytes": assets.FLOOR,
                "support_sha256": digest(json.dumps(files, sort_keys=True).encode()),
                "support_files": len(files),
                "wheel_pins": pins,
                "library_projections": {
                    name: pin["sha256"]
                    for name, pin in library_pins.items()
                    if pin["sha256"] != pins[name]["sha256"]
                },
                "license_notices": case["license_notices"],
                "original_expected_failures": sorted(faults),
                "authority": "Delegated first protected offline C13 checks. Unchanged tests and no provider disclosure.",
            },
            spec,
            env,
            cases,
        )

    runner.review_fields = review_fields


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-download", action="store_true")
    mode.add_argument("--acquire")
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--execute")
    args = parser.parse_args()
    faults, case = project()
    assets.WORK, assets.WHEELS, assets.SUPPORT = WORK, WORK / "wheels", WORK / "support"
    WORK.mkdir(mode=0o700, exist_ok=True)
    acquisition = WORK / "acquisition-review.json"
    if args.prepare_download:
        download_review(acquisition)
        print(file_digest(acquisition))
        return
    if args.acquire:
        review = json.loads(read(acquisition, args.acquire))
        if review["entry_point_sha256"] != file_digest(Path(__file__)):
            raise ValueError("acquisition entry point changed")
        assets.acquire(args.acquire)
        return
    receipt = runner.get(WORK / "acquisition-result.json")
    lock = json.loads(read(acquisition, receipt["review_sha256"]))
    pins = {entry["project"]: entry for entry in lock["files"].values()}
    if {name: pin["version"] for name, pin in pins.items()} != VERSIONS:
        raise ValueError("reviewed dependency list changed")
    configure(faults, case, pins)
    if args.prepare:
        if shutil.disk_usage(WORK).free < assets.FLOOR + 3 * assets.MAX_DOWNLOAD:
            raise ValueError("insufficient storage to project dependencies")
        library_pins = projection(pins, prepare=True)
        assets.support_check(
            "towncrier", library_pins, prepare=not (assets.SUPPORT / "towncrier").exists()
        )
        fields, _, _, _ = await runner.review_fields()
        runner.put(
            runner.REVIEW, fields | {"expires_at": (utc_now() + timedelta(hours=4)).isoformat()}
        )
        print(file_digest(runner.REVIEW))
    else:
        read(runner.REVIEW, args.execute)
        if runner.APPROVAL.exists() or runner.RUN.exists():
            raise ValueError("preserve the previous attempt and its settlement")
        runner.put(runner.APPROVAL, {"approved": True, "review_sha256": args.execute})
        raise SystemExit(not await runner.run(args.execute))


if __name__ == "__main__":
    asyncio.run(main())
