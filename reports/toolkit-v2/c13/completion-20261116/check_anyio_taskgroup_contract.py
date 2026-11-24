"""Verify the AnyIO task-group contract using the established offline carrier."""

import argparse
import asyncio
import json
import shlex
import tomllib
from datetime import timedelta
from itertools import pairwise
from pathlib import Path

import check_retained_carrier_batch as batch
import complete_anyio_pair as lowlevel
from audit_staged_repository_graders import bind, index_paths, wheel_probe_assets
from plan_repository_expansion import previous_repositories
from stage_repository_transport import ROOT, digest, read

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import archive_files
from aeep.models import utc_now
from aeep_toolkit.install_runtime import file_digest

runner = batch.runner
CASE = "agronholm__anyio-975-aeep-contract-audit"
NAME = "c13-anyio-taskgroup-contract-20261124"
WORK = ROOT / ".aeep/c13-cohort-runtime-20261124" / NAME
INDEX = "668b21cc6493bbffc4a54fd622c63ef304f9953fd7853ba8b7651f536f556d3a"
LICENSE_SHA = "5361ac9dc58f2ef5fd2e9b09c68297c17f04950909bbc8023bdb82eacf22c2b0"
EXCEPTIONGROUP = (
    ROOT
    / ".aeep/proposal-optimizer-preparation-20261105/aflow-wheelhouse/exceptiongroup-1.3.0-py3-none-any.whl"
)
EXCEPTIONGROUP_SHA = "4d111e6e0c13d0644cad6ddaa7ed0261a0b36971f6d23e7ec9b4b9097da78a10"
BASE_FIELDS = runner.review_fields
BASE_VERIFY = runner.verify_probe


def subject():
    (index,) = [path for path, value in index_paths() if value == INDEX]
    (row,) = [row for row in json.loads(read(index, INDEX)) if row["input"]["task_id"] == CASE]
    _, core = wheel_probe_assets()
    wheel_pins = [
        runner.asset(lowlevel.PYTEST_MOCK, lowlevel.PYTEST_MOCK_SHA),
        runner.asset(EXCEPTIONGROUP, EXCEPTIONGROUP_SHA),
    ]
    task, truth, repaired, original, screen = bind(row, index.parent, [*core, *wheel_pins])
    public = archive_files(truth.source.read(), large=True)
    _, _, exposed = previous_repositories()
    required = json.loads(
        read(
            index.parent / "protected" / CASE / "required.json",
            row["protected_assets"]["required.json"]["sha256"],
        )
    )
    faults = {row["protected_guard"], *required["published_fail_to_pass"]}
    if (
        row["source_repository"] in exposed
        or digest(public["LICENSE"]) != LICENSE_SHA
        or truth.fail_to_pass
        or len(truth.pass_to_pass) != 386
        or len(faults) != 11
        or not faults <= set(truth.pass_to_pass)
        or truth.test_paths != ["tests/test_aeep_preservation.py", "tests/test_taskgroups.py"]
        or not screen["admits_python_3_13_0"]
        or screen["names_not_declared_in_selected_module"]
    ):
        raise ValueError("the staged project, source family or protected assertion set changed")
    config = tomllib.loads(public["pyproject.toml"].decode())
    addopts = shlex.split(config["tool"]["pytest"]["ini_options"]["addopts"])
    if {arg for flag, arg in pairwise(addopts) if flag == "-p"} != {
        "anyio",
        "pytest_mock",
        "no:asyncio",
        "no:trio",
    }:
        raise ValueError("published plugin configuration differs from the known carrier")
    return (
        {
            "case_id": CASE,
            "source_revision": row["source_revision"],
            "input": task.model_dump(mode="json"),
            "truth": truth.model_dump(mode="json"),
            "roles": {"reference": repaired, "original": original},
            "reference_archive_sha256": row["reference_archive_sha256"],
            "existing_image_dependencies": [],
        },
        public,
        faults,
    )


def configure(*, stage=False):
    origin = runner.get(lowlevel.TARGET / "operation-review.json")
    proof = runner.get(lowlevel.NATIVE_DEST / "result.json")
    if not proof["verified"] or proof["review_sha256"] != file_digest(
        lowlevel.NATIVE_DEST / "operation-review.json"
    ):
        raise ValueError("previous carrier qualification evidence changed")
    # This also checks the source freeze and excludes known development repositories.
    batch.cases()
    case, public, faults = subject()
    batch.assets.SUPPORT = batch.WORK / "support"
    batch.assets.WHEELS = batch.WORK / "wheels"
    pins = origin["package_pins"]
    inventory = batch.assets.support_check("anyio", batch.import_only_pins("anyio", pins))
    if (
        digest(json.dumps(inventory, sort_keys=True).encode())
        != origin["read_only_import_tree_sha256"]
    ):
        raise ValueError("shared AnyIO import closure changed")
    batch.configure("anyio", case, faults, pins)
    base, env, _ = runner.definitions()
    if (
        content_digest(base) != origin["observer_fingerprint"]
        or env.model_dump(mode="json") != origin["environment"]
    ):
        raise ValueError("retained native carrier or observer changed")
    spec, env, projected = lowlevel.entry_point(base, env, public, stage=stage)
    env = env.model_copy(update={"environment_id": NAME})
    argv = list(spec.config["argv"])
    if argv[-1].count("timeout=22") != 1:
        raise ValueError("reviewed child timeout boundary changed")
    argv[-1] = argv[-1].replace("timeout=22", "timeout=95")
    spec = spec.model_copy(
        update={
            "description": "Protected AnyIO task-group assertions",
            "config": spec.config | {"argv": argv, "timeout_seconds": 115},
        }
    )
    runner.NAME, runner.FROZEN = NAME, batch.FROZEN
    runner.REVIEW, runner.RUN, runner.APPROVAL = (
        WORK / "operation-review.json",
        WORK / "execution",
        WORK / "scope.json",
    )
    runner.MAX_CALLS, runner.ROLE_SECONDS = 2, 130
    runner.definitions = lambda: (spec, env, [case])

    def observed(reply, payload, expected, code):
        runner.put(runner.RUN / f"observation-{'original' if code else 'reference'}.json", reply)
        return BASE_VERIFY(reply, payload, expected, code)

    async def fields():
        current, spec, env, subjects = await BASE_FIELDS()
        return (
            current
            | {
                "wrapper_sha256": file_digest(Path(__file__)),
                "storage_floor_bytes": batch.assets.FLOOR,
                "prior_carrier_result_sha256": file_digest(lowlevel.NATIVE_DEST / "result.json"),
                "readonly_import_tree_sha256": origin["read_only_import_tree_sha256"],
                "pytest_entry_point_projection": projected,
                "source_license_sha256": LICENSE_SHA,
                "original_expected_failure_ids": sorted(faults),
                "published_checks_per_role": 386,
                "runtime_adaptation": "Use pinned backends and publisher pytest entry point. Optional BlockBuster is absent.",
            },
            spec,
            env,
            subjects,
        )

    runner.verify_probe, runner.review_fields = observed, fields


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_mutually_exclusive_group(required=True)
    command.add_argument("--prepare", action="store_true")
    command.add_argument("--execute")
    args = parser.parse_args()
    configure(stage=args.prepare)
    if args.prepare:
        WORK.mkdir(mode=0o700)
        plan, _, _, _ = await runner.review_fields()
        runner.put(
            runner.REVIEW, plan | {"expires_at": (utc_now() + timedelta(hours=4)).isoformat()}
        )
        print(file_digest(runner.REVIEW))
    else:
        read(runner.REVIEW, args.execute)
        if runner.RUN.exists() or runner.APPROVAL.exists():
            raise ValueError("preserve earlier hardware and grading receipts")
        runner.put(runner.APPROVAL, {"approved": True, "review_sha256": args.execute})
        raise SystemExit(not await runner.run(args.execute))


if __name__ == "__main__":
    asyncio.run(main())
