"""Grade pdoc's table-of-contents regression using the complete native test IDs."""

import argparse
import ast
import asyncio
import json
import shutil
from datetime import timedelta
from pathlib import Path

import check_pyformlang_pair as parser
import check_retained_carrier_batch as batch
from audit_staged_repository_graders import bind, wheel_probe_assets
from plan_repository_expansion import previous_repositories
from stage_repository_transport import digest, read, write

from aeep.assessment.repository_suites import SuiteTruthV6, archive_files
from aeep.models import utc_now
from aeep_toolkit.install_runtime import file_digest

NAME = "c13-pdoc-806-20261124"
WORK = parser.BASE / NAME
CASE = "mitmproxy__pdoc-806-aeep-contract-audit"
REVISION = "ea2b69a4162226b07f68cd25d92d4d92dbbafaf8"
LICENSE = "2eb848789ee02930cfc8e5fd615b991abf66a66ca3a64bea1fa2e3c6f134b333"
TEST_FILE = "test/test_render_helpers.py"
runner = batch.runner
BASE_REVIEW = runner.review_fields


def exact_autolink_ids(overlay, truth):
    (test,) = [
        node
        for node in ast.parse(overlay[TEST_FILE]).body
        if isinstance(node, ast.FunctionDef) and node.name == "test_markdown_autolink"
    ]
    (marker,) = test.decorator_list
    if ast.unparse(marker.func) != "pytest.mark.parametrize" or marker.keywords:
        raise ValueError("protected parametrization changed")
    names, samples = map(ast.literal_eval, marker.args)
    if names != "md,html" or len(samples) != 7:
        raise ValueError("protected literal parameter rows changed")
    prefix = f"{TEST_FILE}::test_markdown_autolink["
    native = [
        prefix + "-".join(value.encode("unicode_escape").decode("ascii") for value in values) + "]"
        for values in samples
    ]
    incomplete = [value for value in truth.pass_to_pass if value.startswith(prefix)]
    if (
        len(incomplete) != 5
        or len(set(native)) != 7
        or any(not any(full.startswith(short) for full in native) for short in incomplete)
        or any(len(values) != 2 for values in samples)
    ):
        raise ValueError("truncated publisher IDs do not map to the full protected parameter set")
    return incomplete, native


def subject():
    batch.cases()
    (row,) = [
        row
        for row in json.loads(read(parser.INTAKE / "index.json", parser.INDEX))
        if row["input"]["task_id"] == CASE
    ]
    task, truth, reference, original, metadata = bind(
        row, parser.INTAKE / "transport", wheel_probe_assets()[1]
    )
    source = archive_files(truth.source.read(), large=True)
    overlay = archive_files(truth.tests.read(), large=True)
    incomplete, native = exact_autolink_ids(overlay, truth)
    required = json.loads(
        read(
            parser.INTAKE / "transport/protected" / CASE / "required.json",
            row["protected_assets"]["required.json"]["sha256"],
        )
    )
    faults = {row["protected_guard"], *required["published_fail_to_pass"]}
    if (
        task.task_id != CASE
        or row["source_revision"] != REVISION
        or digest(source["LICENSE"]) != LICENSE
        or truth.fail_to_pass
        or not metadata["admits_python_3_13_0"]
        or metadata["names_not_declared_in_selected_module"]
        or row["source_repository"] in previous_repositories()[2]
        or len(truth.pass_to_pass) != 29
        or len(faults) != 2
        or not faults <= (set(truth.pass_to_pass) - set(incomplete))
    ):
        raise ValueError("pdoc source rights or protected assertion binding changed")
    truth = SuiteTruthV6.model_validate(
        truth.model_dump(mode="json")
        | {
            "pass_to_pass": [name for name in truth.pass_to_pass if name not in incomplete]
            + native,
        }
    )
    return {
        "case_id": CASE,
        "source_revision": REVISION,
        "input": task.model_dump(mode="json"),
        "truth": truth.model_dump(mode="json"),
        "roles": {"reference": reference, "original": original},
        "reference_archive_sha256": row["reference_archive_sha256"],
        "existing_image_dependencies": [],
        "published_incomplete_selectors": incomplete,
        "native_preserved_selectors": native,
    }, faults


def runtime(*, prepare):
    town = parser.BASE / "c13-towncrier-contract-20261124/wheels"
    confluence = parser.BASE / "c13-confluence-exporter-contract-20261124/wheels"
    containers = {
        "jinja2": ("3.1.6", town / "jinja2-3.1.6-py3-none-any.whl"),
        "markupsafe": (
            "3.0.3",
            town
            / "markupsafe-3.0.3-cp313-cp313-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl",
        ),
        "pygments": ("2.19.2", confluence / "pygments-2.19.2-py3-none-any.whl"),
    }
    batch.assets.WHEELS = WORK / "wheels"
    batch.assets.SUPPORT = WORK / "support"
    if prepare and shutil.disk_usage(WORK).free < batch.assets.FLOOR + 15 * 1024**2:
        raise ValueError("insufficient headroom for the retained wheel projection")
    pins = {}
    for name, (version, path) in containers.items():
        sha = file_digest(path)
        dest = batch.assets.WHEELS / path.name
        if prepare and not dest.exists():
            write(dest, read(path, sha))
        read(dest, sha)
        pins[name] = {"name": name, "version": version, "filename": path.name, "sha256": sha}
    tree = batch.assets.support_check(
        "pdoc", pins, prepare=prepare and not (batch.assets.SUPPORT / "pdoc").exists()
    )
    return pins, tree


async def main():
    cli = argparse.ArgumentParser(description=__doc__)
    action = cli.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--execute")
    args = cli.parse_args()
    case, faults = subject()
    if args.prepare:
        WORK.mkdir(mode=0o700, exist_ok=True)
    batch.WORK = WORK
    pins, tree = runtime(prepare=args.prepare)
    batch.PROFILES["pdoc"] = {"native": ("markupsafe._speedups",)}
    batch.configure("pdoc", case, faults, pins)
    spec, env, _ = runner.definitions()

    async def fields():
        base, _, _, _ = await BASE_REVIEW()
        return (
            base
            | {
                "coordinator_sha256": file_digest(Path(__file__)),
                "storage_floor_bytes": batch.assets.FLOOR,
                "source_index_sha256": parser.INDEX,
                "source_license_sha256": LICENSE,
                "package_pins": pins,
                "support_tree_sha256": digest(json.dumps(tree, sort_keys=True).encode()),
                "expected_original_failures": sorted(faults),
                "native_autolink_ids": case["native_preserved_selectors"],
                "authority": "First bounded protected C13 pair on an existing offline carrier.",
            },
            spec,
            env,
            [case],
        )

    runner.review_fields = fields
    if args.prepare:
        runner.REVIEW.parent.mkdir(mode=0o700, exist_ok=True)
        review, _, _, _ = await fields()
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
