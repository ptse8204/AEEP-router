"""Reproduce the protected Nested Pandas 302 contract on Linux ARM64."""

import argparse
import asyncio
import json
import re
import tarfile
import tomllib
from datetime import timedelta
from pathlib import Path

import check_retained_carrier_batch as batch
import check_towncrier_contract as libraries
from audit_staged_repository_graders import bind, wheel_probe_assets
from packaging.requirements import Requirement
from plan_repository_expansion import previous_repositories
from stage_repository_transport import ROOT, digest, read

from aeep.assessment.repository_suites import archive_files
from aeep.models import utc_now
from aeep_toolkit.install_runtime import file_digest

runner = batch.runner
BASE_REVIEW, BASE_VERIFY = runner.review_fields, runner.verify_probe
NAME = "c13-nested-pandas-302-20261124"
BASE = ROOT / ".aeep/c13-cohort-runtime-20261124"
WORK = BASE / NAME
INTAKE = BASE / "nested-pandas-export-substitution-20261124"
CASE = "lincc-frameworks__nested-pandas-302-aeep-contract-audit"
REVISION = "1eeda4bafab06582e90b1266a36f6923ccf31fdc"
INDEX_SHA = "d40e1d7e28325e410e7d2f75d670a4c8fe9aa8dc838bcdfe3a359a36c216ca78"
RECOVERY_SHA = "4f62f211ae40572b09f16cd23243f84a88c8e2288f2279fdf041a7d81b61073d"
ORIGINAL = (
    BASE
    / "repository-intake-post-inventory-20261124/archives/lincc-frameworks__nested-pandas-302/source-original.tar.gz"
)


def subject(pins):
    # Reuse the source-freeze check already exercised by the native carrier.
    batch.cases()
    recovery = json.loads(read(INTAKE / "result.json", RECOVERY_SHA))
    (row,) = json.loads(read(INTAKE / "index.json", INDEX_SHA))
    _, core = wheel_probe_assets()
    task, truth, reference, original, metadata = bind(row, INTAKE / "transport", core)
    files = archive_files(truth.source.read(), large=True)
    required = json.loads(
        read(
            INTAKE / "transport/protected" / CASE / "required.json",
            row["protected_assets"]["required.json"]["sha256"],
        )
    )
    faults = {row["protected_guard"], *required["published_fail_to_pass"]}
    license = recovery["license_notices"]
    if (
        task.task_id != CASE
        or row["source_repository"] in previous_repositories()[2]
        or row["source_revision"] != REVISION
        or not metadata["admits_python_3_13_0"]
        or metadata["names_not_declared_in_selected_module"]
        or recovery["restored_tree"] != recovery["publisher_tree"]
        or len(license) != 1
        or digest(files[license[0]["file"]]) != license[0]["sha256"]
        or len(truth.pass_to_pass) != 56
        or truth.fail_to_pass
        or len(faults) != 2
        or not faults <= set(truth.pass_to_pass)
        or "src/nested_pandas/_version.py" in files
    ):
        raise ValueError("Nested Pandas source rights or protected assertion binding changed")
    config = tomllib.loads(files["pyproject.toml"].decode())
    if config["tool"]["setuptools_scm"] != {"write_to": "src/nested_pandas/_version.py"}:
        raise ValueError("publisher version-file configuration changed")
    for item in config["project"]["dependencies"] + config["build-system"]["requires"]:
        requirement = Requirement(item)
        if pins[requirement.name.lower().replace("_", "-")]["version"] not in requirement.specifier:
            raise ValueError(f"dependency outside publisher runtime range: {requirement}")
    read(ORIGINAL, recovery["original_archive_sha256"])
    with tarfile.open(ORIGINAL) as archive:
        (member,) = [m for m in archive if m.name.endswith("/.git_archival.txt")]
        with archive.extractfile(member) as stream:
            expanded = stream.read(4096)
    if (
        digest(expanded) != recovery["original_substituted_sha256"]
        or digest(files[".git_archival.txt"]) != recovery["publisher_archival_blob_sha256"]
    ):
        raise ValueError("archive exporter version metadata does not bind this checkout")
    lines = dict(line.split(": ", 1) for line in expanded.decode().splitlines())
    tag = re.fullmatch(r"(v0\.4\.5)-([0-9]+)-(g[0-9a-f]{8})", lines["describe-name"])
    if lines["node"] != REVISION or not tag or tag.groups() != ("v0.4.5", "4", "g" + REVISION[:8]):
        raise ValueError("publisher tag, commit distance or node abbreviation changed")
    return (
        {
            "case_id": CASE,
            "source_revision": REVISION,
            "input": task.model_dump(mode="json"),
            "truth": truth.model_dump(mode="json"),
            "roles": {"reference": reference, "original": original},
            "reference_archive_sha256": row["reference_archive_sha256"],
            "existing_image_dependencies": [],
        },
        faults,
        tag.groups(),
    )


def configure(*, prepare):
    transfer = runner.get(WORK / "acquisition-result.json")
    lock = json.loads(read(WORK / "acquisition-review.json", transfer["review_sha256"]))
    if not transfer["completed"] or lock["driver_sha256"] != file_digest(Path(batch.__file__)):
        raise ValueError("missing completion of the exact wheel intake")
    pins = {entry["name"]: entry for entry in lock["files"].values()}
    case, faults, (tag, distance, node) = subject(pins)
    batch.WORK = libraries.WORK = WORK
    batch.assets.SUPPORT = WORK / "support"
    library_pins = libraries.projection(pins, prepare=prepare)
    tree = batch.assets.support_check("nested-pandas", library_pins, prepare=prepare)
    batch.PROFILES["nested-pandas"] = {
        "native": ("numpy._core._multiarray_umath", "pyarrow.lib", "pandas._libs.interval")
    }
    batch.configure("nested-pandas", case, faults, pins)
    spec, env, _ = runner.definitions()
    runner.NAME, runner.REVIEW, runner.RUN, runner.APPROVAL = (
        NAME,
        WORK / "operation-review.json",
        WORK / "execution",
        WORK / "scope.json",
    )
    runner.MAX_CALLS, runner.ROLE_SECONDS = 2, 85
    support = str(batch.assets.SUPPORT / "nested-pandas")
    argv = list(spec.config["argv"])
    program = argv[-1]
    renderer = (
        f"from pathlib import Path\n"
        f"from setuptools_scm import get_version\n"
        f"from setuptools_scm.version import meta\n"
        f"assert Path(get_version.__code__.co_filename).is_relative_to({support!r})\n"
        "target = repo / 'src/nested_pandas/_version.py'\n"
        "assert not target.exists() and not target.is_symlink()\n"
        "def parse(root, config):\n"
        "    assert Path(root) == repo\n"
        f"    return meta({tag!r}, distance={int(distance)}, node={node!r}, dirty=False, config=config)\n"
        "version = get_version(root=repo, write_to='src/nested_pandas/_version.py', parse=parse, dist_name='nested-pandas')\n"
        f"assert version == {'0.4.6.dev4+' + node!r} and target.is_file() and not target.is_symlink()\n"
    )
    insertion = "        argv = ['--no-header'"
    capture = (
        batch.FROZEN / "integrations/assessment-runtime/repository_suite_native_capture.py"
    ).read_text()
    diagnostic = Path(__file__).with_name("pytest_failure_diagnostics.py").read_text()
    if program.count(insertion) != 1 or program.count(repr(capture)) != 1:
        raise ValueError("native observer preparation hook changed")
    # The version renderer is part of the protected worker, not a host install.
    additions = (
        "        subprocess.run([sys.executable, '-B', '-c', "
        + repr(
            "import sys;from pathlib import Path;repo=Path(sys.argv[1]);sys.path.insert(0,"
            + repr(support)
            + ");exec("
            + repr(renderer)
            + ")"
        )
        + ", str(repo)], cwd=root, env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':str(root),"
        "'PYTHONNOUSERSITE':'1'}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=True)\n"
    )
    program = program.replace(insertion, additions + insertion)
    program = program.replace(
        repr(capture),
        repr(capture + "\n" + diagnostic + "\nNativeCapture = diagnostic_capture(NativeCapture)\n"),
    )
    program = program.replace(
        "assert set(native) == {'statuses'}", "assert set(native) == {'statuses', 'failure_sites'}"
    ).replace("timeout=22", "timeout=48")
    compile(program, "<reviewed Nested Pandas worker>", "exec")
    argv[-1] = program
    spec = spec.model_copy(update={"config": spec.config | {"argv": argv, "timeout_seconds": 72}})
    env = env.model_copy(update={"environment_id": NAME})
    runner.definitions = lambda: (spec, env, [case])
    runner.scorer_reply = lambda reply: {k: v for k, v in reply.items() if k != "failure_sites"}

    def validate(reply, payload, expected, code):
        if not isinstance(reply, dict) or not isinstance(reply.get("failure_sites"), list):
            return False
        runner.put(runner.RUN / f"observation-{'original' if code else 'reference'}.json", reply)
        return BASE_VERIFY(runner.scorer_reply(reply), payload, expected, code)

    runner.verify_probe = validate

    async def fields():
        value, _, _, _ = await BASE_REVIEW()
        return (
            value
            | {
                "coordinator_sha256": file_digest(Path(__file__)),
                "storage_floor_bytes": batch.assets.FLOOR,
                "wheel_intake_sha256": transfer["review_sha256"],
                "support_tree_sha256": digest(json.dumps(tree, sort_keys=True).encode()),
                "setuptools_projection_sha256": library_pins["setuptools"]["sha256"],
                "publisher_version": "0.4.6.dev4+" + node,
                "source_recovery_sha256": RECOVERY_SHA,
                "expected_original_failures": sorted(faults),
                "authority": "First ordinary protected C13 reference and original on the retained carrier.",
            },
            spec,
            env,
            [case],
        )

    runner.review_fields = fields


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_mutually_exclusive_group(required=True)
    sub.add_argument("--prepare", action="store_true")
    sub.add_argument("--execute")
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
            raise ValueError("preserve the earlier attempt and charge")
        runner.put(runner.APPROVAL, {"approved": True, "review_sha256": args.execute})
        raise SystemExit(not await runner.run(args.execute))


if __name__ == "__main__":
    asyncio.run(main())
