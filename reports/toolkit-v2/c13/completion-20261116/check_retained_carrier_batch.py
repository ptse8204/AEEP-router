"""Prepare protected software cases on one retained, network-disabled carrier."""

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
from check_expansion_contracts import NoRedirect
from packaging.utils import parse_wheel_filename
from plan_repository_expansion import previous_repositories
from stage_repository_transport import ROOT, digest, read, write
from stage_varex_calibration import FROZEN, SOURCE

import aeep
from aeep.assessment.repository_suites import archive_files
from aeep.assessment.verification import verification_source_digest
from aeep.models import utc_now
from aeep_toolkit.install_runtime import file_digest

NAME = "c13-retained-carrier-batch-20261124"
WORK = ROOT / ".aeep/c13-cohort-runtime-20261124" / NAME
CACHE_DIRS = (
    ".aeep/scanner-runtime-context-20261102/wheels",
    ".aeep/evoagentx-distribution-20261106/runtime-context/wheels",
    ".aeep/c13-cohort-runtime-20261124/c13-confluence-exporter-contract-20261124/wheels",
    ".aeep/c13-cohort-runtime-20261124/c13-towncrier-contract-20261124/wheels",
    ".aeep/repository-large-runtime-image-20261027",
    ".aeep/repository-test-root-wheels-20261027",
)
PROFILES = {
    "skelebot": {
        "case": "carsdotcom__skelebot-280-aeep-contract-audit",
        "index": "668b21cc6493bbffc4a54fd622c63ef304f9953fd7853ba8b7651f536f556d3a",
        "license": "c47489c74a47c99008f758a67578f1198c30ab04e0e1dec61b312443a503f75e",
        "required": 7,
        "failures": 2,
        "native": ("yaml._yaml",),
        "versions": {
            "boto3": "1.43.126",
            "botocore": "1.43.126",
            "certifi": "2025.8.3",
            "charset-normalizer": "3.4.3",
            "colorama": "0.4.6",
            "dohq-artifactory": "0.10.3",
            "idna": "3.10",
            "jmespath": "1.1.0",
            "pyjwt": "2.10.1",
            "python-dateutil": "2.9.0.post0",
            "pyyaml": "6.0.3",
            "requests": "2.32.5",
            "s3transfer": "0.19.3",
            "schema": "0.7.7",
            "six": "1.17.0",
            "urllib3": "2.5.0",
        },
    },
    "anyio": {
        "case": "agronholm__anyio-935",
        "index": "378a7a9cf4dc2184f5af65b063547cbc27fc253d6f51d1e74cb3278280d5d4bc",
        "license": "5361ac9dc58f2ef5fd2e9b09c68297c17f04950909bbc8023bdb82eacf22c2b0",
        "required": 30,
        "failures": 3,
        "native": ("uvloop.loop", "cryptography.hazmat.bindings._rust", "_cffi_backend"),
        "local_plugin": "anyio.pytest_plugin",
        "versions": {
            "attrs": "25.4.0",
            "cffi": "1.17.1",
            "cryptography": "45.0.7",
            "idna": "3.10",
            "outcome": "1.3.0.post0",
            "pycparser": "2.22",
            "sniffio": "1.3.1",
            "sortedcontainers": "2.4.0",
            "trio": "0.30.0",
            "trustme": "1.2.1",
            "uvloop": "0.22.1",
        },
        "adaptation": "The upstream optional BlockBuster fixture remains inactive. The three published backends are available.",
    },
}
BASE_REVIEW = runner.review_fields
MAX_FETCH = 20_000_000


def cases():
    if (
        Path(aeep.__file__).resolve().parents[2] != FROZEN
        or verification_source_digest(FROZEN) != SOURCE
    ):
        raise ValueError("load the already verified toolkit source")
    indices = {pin: path for path, pin in index_paths()}
    _, core = wheel_probe_assets()
    exposed = previous_repositories()[2]
    output = {}
    for key, profile in PROFILES.items():
        index = indices[profile["index"]]
        subject = profile["case"]
        (row,) = [
            row
            for row in json.loads(read(index, profile["index"]))
            if row["input"]["task_id"] == subject
        ]
        task, truth, fixed, original, metadata = bind(row, index.parent, core)
        public = archive_files(truth.source.read(), large=True)
        expected_faults = set(truth.fail_to_pass)
        if guard := row.get("protected_guard"):
            required = index.parent / "protected" / subject / "required.json"
            pin = row["protected_assets"]["required.json"]["sha256"]
            expected_faults = {guard, *json.loads(read(required, pin))["published_fail_to_pass"]}
        total = len(truth.fail_to_pass) + len(truth.pass_to_pass)
        if (
            row["source_repository"] in exposed
            or digest(public["LICENSE"]) != profile["license"]
            or metadata["names_not_declared_in_selected_module"]
            or not metadata["admits_python_3_13_0"]
            or total != profile["required"]
            or len(expected_faults) != profile["failures"]
            or not expected_faults <= set(truth.pass_to_pass + truth.fail_to_pass)
            or any(
                "[" in test and not test.endswith("]")
                for test in truth.pass_to_pass + truth.fail_to_pass
            )
        ):
            raise ValueError(
                f"source eligibility, rights or published test identities changed for {key}"
            )
        output[key] = (
            expected_faults,
            {
                "case_id": subject,
                "source_revision": row["source_revision"],
                "input": task.model_dump(mode="json"),
                "truth": truth.model_dump(mode="json"),
                "roles": {"reference": fixed, "original": original},
                "reference_archive_sha256": row["reference_archive_sha256"],
                "existing_image_dependencies": [],
            },
        )
    return output


def wheel_rank(filename):
    _, _, _, tags = parse_wheel_filename(filename)
    ranks = []
    for tag in tags:
        if tag.interpreter == "py3" and tag.abi == "none" and tag.platform == "any":
            ranks.append(1)
        elif tag.platform in {"manylinux_2_17_aarch64", "manylinux2014_aarch64"}:
            if tag.interpreter == "cp313" and tag.abi == "cp313":
                ranks.append(100)
            elif tag.abi == "abi3" and tag.interpreter in {
                "cp37",
                "cp38",
                "cp39",
                "cp310",
                "cp311",
                "cp312",
                "cp313",
            }:
                ranks.append(int(tag.interpreter[3:]))
    return max(ranks, default=0)


def acquire_plan():
    versions = {
        (name, version)
        for profile in PROFILES.values()
        for name, version in profile["versions"].items()
    }
    opener = urllib.request.build_opener(NoRedirect())
    pins = {}
    for name, version in sorted(versions):
        with opener.open(f"https://pypi.org/pypi/{name}/{version}/json", timeout=15) as response:
            data = json.loads(response.read(2_000_000))
        candidates = [
            row
            for row in data["urls"]
            if row["packagetype"] == "bdist_wheel"
            and not row["yanked"]
            and wheel_rank(row["filename"])
        ]
        candidates.sort(key=lambda row: wheel_rank(row["filename"]), reverse=True)
        if not candidates or (
            len(candidates) > 1
            and wheel_rank(candidates[0]["filename"]) == wheel_rank(candidates[1]["filename"])
        ):
            raise ValueError(
                f"publisher wheel selection is ambiguous or missing for {name} {version}"
            )
        row = candidates[0]
        filename, sha = row["filename"], row["digests"]["sha256"]
        cache = next(
            (
                f"{folder}/{filename}"
                for folder in CACHE_DIRS
                if (path := ROOT / folder / filename).is_file() and file_digest(path) == sha
            ),
            None,
        )
        pins[filename] = {
            "name": name,
            "version": version,
            "filename": filename,
            "sha256": sha,
            "url": row["url"],
            "size": row["size"],
            "cache": cache,
        }
    downloads = [item for item in pins.values() if not item["cache"]]
    total = sum(item["size"] for item in downloads)
    if total > MAX_FETCH:
        raise ValueError("bound public wheel intake is too large")
    return {
        "driver_sha256": file_digest(Path(__file__)),
        "files": pins,
        "maximum_response_bytes": total,
        "maximum_downloads": len(downloads),
        "models": 0,
        "cash_usd": 0,
        "retries": 0,
        "installations": 0,
        "provider_disclosure": False,
    }


def acquire(review):
    if review["driver_sha256"] != file_digest(Path(__file__)) or assets.WHEELS.exists():
        raise ValueError("acquisition is changed or already started")
    if shutil.disk_usage(WORK).free < assets.FLOOR + 3 * MAX_FETCH:
        raise ValueError("preserve the 50 GiB usable reserve during acquisition")
    assets.WHEELS.mkdir(mode=0o700)
    opener = urllib.request.build_opener(NoRedirect())
    for filename, item in review["files"].items():
        url = item["url"]
        if (
            not url.startswith("https://files.pythonhosted.org/packages/")
            or url.rsplit("/", 1)[-1] != filename
        ):
            raise ValueError("unexpected wheel host or filename")
        if cache := item["cache"]:
            body = read(ROOT / cache, item["sha256"])
        else:
            with opener.open(url, timeout=30) as response:
                body = response.read(item["size"] + 1)
        if len(body) != item["size"] or digest(body) != item["sha256"]:
            raise ValueError("publisher wheel size or checksum changed")
        write(assets.WHEELS / filename, body)


def observer(key, pins):
    folder = FROZEN / "integrations/assessment-runtime"
    program = (folder / "repository_suite_native_program.py").read_text()
    capture = (folder / "repository_suite_native_capture.py").read_text()
    root = str(assets.SUPPORT / key)
    versions = {name: item["version"] for name, item in pins.items()}
    native_modules = PROFILES[key]["native"]
    check = (
        f";sys.path.insert(0,{root!r});from importlib.metadata import version;"
        f"assert all(version(n)==v for n,v in {versions!r}.items());"
        f"assert all(Path(importlib.import_module(n).__file__).is_relative_to({root!r}) for n in {native_modules!r})"
    )
    hook = "            + ';import pytest;"
    if program.count(hook) != 1:
        raise ValueError("native bootstrap entry point changed")
    program = program.replace(hook, "            + " + repr(check) + "\n" + hook)
    if module := PROFILES[key].get("local_plugin"):
        hook = "            + ';os.chdir('"
        if program.count(hook) != 1:
            raise ValueError("native source entry point changed")
        check = (
            f";m=importlib.import_module({module!r});"
            "assert Path(m.__file__).is_relative_to('/tmp/aeep-repository-native-v6/src');plugins.append(m)"
        )
        program = program.replace(hook, "            + " + repr(check) + "\n" + hook)
    return program.replace("'__AEEP_NATIVE_CAPTURE_SOURCE__'", repr(capture))


def import_only_pins(key, pins, *, prepare=False):
    """Make a reviewed library-only projection when a wheel has a CLI wrapper."""
    if key != "skelebot":
        return pins
    root = WORK / "skelebot" / "libraries"
    artifacts = {}
    for name, item in pins.items():
        filename = item["filename"]
        raw = read(WORK / "wheels" / filename, item["sha256"])
        if name == "jmespath":
            buffer = io.BytesIO()
            cli = "jmespath-1.1.0.data/scripts/jp.py"
            with ZipFile(io.BytesIO(raw)) as upstream, ZipFile(buffer, "w") as copy:
                if upstream.namelist().count(cli) != 1:
                    raise ValueError("the expected script wrapper is absent or duplicated")
                for entry in upstream.infolist():
                    if entry.filename != cli:
                        copy.writestr(entry, upstream.read(entry))
            raw = buffer.getvalue()
        sha = digest(raw)
        path = root / filename
        if prepare and not path.exists():
            write(path, raw)
        read(path, sha)
        artifacts[name] = item | {"sha256": sha}
    assets.WHEELS = root
    return artifacts


def configure(key, case, faults, pins):
    run_dir = WORK / key
    runner.NAME, runner.FROZEN = f"{NAME}-{key}", FROZEN
    runner.MAX_CALLS, runner.ROLE_SECONDS = 2, 50
    runner.REVIEW, runner.APPROVAL, runner.RUN = (
        run_dir / "operation-review.json",
        run_dir / "scope.json",
        run_dir / "execution",
    )
    assets.observer = observer

    def definitions():
        spec, env, cases = assets.definitions(key, pins, case)
        return (
            spec.model_copy(update={"description": f"Protected {key} regression tests"}),
            env,
            cases,
        )

    def expected(truth, role):
        statuses = dict.fromkeys(truth["fail_to_pass"] + truth["pass_to_pass"], "PASSED")
        if role == "original":
            statuses.update(dict.fromkeys(faults, "FAILED"))
        return statuses

    verify = runner.verify_probe

    def observed(reply, payload, statuses, code):
        runner.put(runner.RUN / f"observation-{'original' if code else 'reference'}.json", reply)
        return verify(reply, payload, statuses, code)

    async def review_fields():
        projected = import_only_pins(key, pins)
        tree = assets.support_check(key, projected)
        base, spec, env, cases = await BASE_REVIEW()
        return (
            base
            | {
                "wrapper_sha256": file_digest(Path(__file__)),
                "storage_floor_bytes": assets.FLOOR,
                "source_license_sha256": PROFILES[key]["license"],
                "package_pins": pins,
                "library_projections": {
                    name: pin["sha256"]
                    for name, pin in projected.items()
                    if pin["sha256"] != pins[name]["sha256"]
                },
                "read_only_import_tree_sha256": digest(json.dumps(tree, sort_keys=True).encode()),
                "published_assertions": PROFILES[key]["required"],
                "expected_original_failure_ids": sorted(faults),
                "runtime_adaptations": PROFILES[key].get("adaptation"),
                "authority": "First protected C13 grading attempt on the retained carrier under standing offline authority.",
            },
            spec,
            env,
            cases,
        )

    runner.definitions, runner.expected_statuses, runner.verify_probe = (
        definitions,
        expected,
        observed,
    )
    runner.review_fields = review_fields


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-download", action="store_true")
    mode.add_argument("--acquire")
    mode.add_argument("--prepare", choices=PROFILES)
    mode.add_argument("--execute", nargs=2, metavar=("PROFILE", "REVIEW_SHA256"))
    args = parser.parse_args()
    selection = cases()
    assets.WORK, assets.WHEELS, assets.SUPPORT = WORK, WORK / "wheels", WORK / "support"
    WORK.mkdir(mode=0o700, exist_ok=True)
    acquisition = WORK / "acquisition-review.json"
    if args.prepare_download:
        runner.put(acquisition, acquire_plan())
        print(file_digest(acquisition))
        return
    if args.acquire:
        acquire(json.loads(read(acquisition, args.acquire)))
        runner.put(
            WORK / "acquisition-result.json", {"review_sha256": args.acquire, "completed": True}
        )
        return
    transfer = runner.get(WORK / "acquisition-result.json")
    lock = json.loads(read(acquisition, transfer["review_sha256"]))
    key = args.prepare or args.execute[0]
    versions = PROFILES[key]["versions"]
    mask = {
        row["name"]: row
        for row in lock["files"].values()
        if versions.get(row["name"]) == row["version"]
    }
    if set(mask) != set(versions):
        raise ValueError("reviewed package versions changed")
    faults, case = selection[key]
    configure(key, case, faults, mask)
    if args.prepare:
        if shutil.disk_usage(WORK).free < assets.FLOOR + 3 * MAX_FETCH:
            raise ValueError("insufficient room to prepare the isolated import tree")
        runner.REVIEW.parent.mkdir(mode=0o700, exist_ok=True)
        projected = import_only_pins(key, mask, prepare=True)
        assets.support_check(key, projected, prepare=not (assets.SUPPORT / key).exists())
        fields, _, _, _ = await runner.review_fields()
        runner.put(
            runner.REVIEW, fields | {"expires_at": (utc_now() + timedelta(hours=4)).isoformat()}
        )
        print(file_digest(runner.REVIEW))
        return
    exact = args.execute[1]
    read(runner.REVIEW, exact)
    if runner.RUN.exists() or runner.APPROVAL.exists():
        raise ValueError("prior operation must be preserved")
    runner.put(runner.APPROVAL, {"approved": True, "review_sha256": exact})
    raise SystemExit(not await runner.run(exact))


if __name__ == "__main__":
    asyncio.run(main())
