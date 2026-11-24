"""Reproduce AnyIO issue 935 with the published pytest plugin requirements."""

import argparse
import asyncio
import json
import shlex
import tomllib
from datetime import timedelta
from itertools import pairwise
from pathlib import Path

import check_retained_carrier_batch as batch
from complete_skelebot_metadata_pair import execute
from stage_repository_transport import ROOT, digest, read, write

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import SuiteTruthV6, archive_files, grade_suite_output
from aeep.models import utc_now
from aeep_toolkit.install_runtime import file_digest

runner = batch.runner
KEY = "anyio"
TARGET = batch.WORK / KEY
DEST = TARGET / "with-declared-pytest-plugin"
REVIEW = DEST / "operation-review.json"
NATIVE_DEST = TARGET / "with-publisher-pytest-entry-point"
METADATA = TARGET / "publisher-pytest-entry-point"
PYTEST_MOCK = (
    ROOT
    / ".aeep/repository-replacement-runtime-20261022-wheels/pytest_mock-3.15.0-py3-none-any.whl"
)
PYTEST_MOCK_SHA = "ef2219485fb1bd256b00e7ad7466ce26729b30eadfc7cbcdb4fa9a92ca68db6f"


def entry_point(spec, environment, public, *, stage):
    project = tomllib.loads(public["pyproject.toml"].decode())["project"]
    if project["name"] != KEY or project["entry-points"]["pytest11"] != {
        "anyio": "anyio.pytest_plugin"
    }:
        raise ValueError("publisher pytest entry point changed")
    files = {
        "METADATA": b"Metadata-Version: 2.1\nName: anyio\nVersion: 0+protected.snapshot\n\n",
        "entry_points.txt": b"[pytest11]\nanyio = anyio.pytest_plugin\n",
    }
    info = METADATA / "anyio-0+protected.snapshot.dist-info"
    for name, body in files.items():
        path = info / name
        if stage and not path.exists():
            write(path, body)
            path.chmod(0o444)
        read(path, digest(body))
        if path.stat().st_mode & 0o777 != 0o444:
            raise ValueError("read-only metadata file mode changed")
    if any(path.is_symlink() for path in METADATA.rglob("*")) or {
        path for path in METADATA.rglob("*") if path.is_file()
    } != {info / name for name in files}:
        raise ValueError("entry-point projection contains unexpected content")
    argv = list(spec.config["argv"])
    preimport = (
        ";m=importlib.import_module('anyio.pytest_plugin');"
        "assert Path(m.__file__).is_relative_to('/tmp/aeep-repository-native-v6/src');plugins.append(m)"
    )
    result = "            + ';Path(' + repr(str(events))"
    if argv[-1].count(repr(preimport)) != 1 or argv[-1].count(result) != 1:
        raise ValueError("native startup template changed")
    argv[-1] = (
        argv[-1]
        .replace(repr(preimport), repr(f";sys.path.insert(0,{str(METADATA)!r})"))
        .replace(
            result,
            "            + \";m=sys.modules['anyio.pytest_plugin'];assert "
            "Path(m.__file__).is_relative_to('/tmp/aeep-repository-native-v6/src')\"\n" + result,
        )
    )
    compile(argv[-1], "<publisher pytest entry point>", "exec")
    return (
        spec.model_copy(update={"config": spec.config | {"argv": argv}}),
        environment.model_copy(
            update={"read_only_roots": [*environment.read_only_roots, str(METADATA)]}
        ),
        {name: digest(body) for name, body in files.items()},
    )


async def prepare(expires, *, native=False, stage=False):
    prior = runner.get(TARGET / "operation-review.json")
    startup = TARGET / "startup"
    latest = runner.get(startup / "result.json")
    ledger = runner.get(startup / "ledger.json")
    if (
        latest["grade"]
        or latest["observations"] != {"ok": True, "class": None, "sites": []}
        or len(ledger["operations"]) != 4
        or any(operation["elapsed_seconds"] is None for operation in ledger["operations"])
    ):
        raise ValueError("expected four settled operations and the successful startup diagnostic")

    faults, case = batch.cases()[KEY]
    truth = SuiteTruthV6.model_validate(case["truth"])
    public = archive_files(truth.source.read(), large=True)
    addopts = tomllib.loads(public["pyproject.toml"].decode())["tool"]["pytest"]["ini_options"][
        "addopts"
    ]
    args = shlex.split(addopts)
    declared = [name for option, name in pairwise(args) if option == "-p"]
    if "pytest_mock" not in declared or any("pytest_mock" in wheel.path for wheel in truth.wheels):
        raise ValueError("reviewed snapshot does not have the expected missing pytest dependency")
    wheel = runner.asset(PYTEST_MOCK, PYTEST_MOCK_SHA)
    corrected = SuiteTruthV6.model_validate(
        case["truth"]
        | {
            "wheels": [*case["truth"]["wheels"], wheel],
        }
    )

    batch.assets.SUPPORT = batch.WORK / "support"
    batch.assets.WHEELS = batch.WORK / "wheels"
    pins = prior["package_pins"]
    tree = batch.assets.support_check(KEY, batch.import_only_pins(KEY, pins))
    if digest(json.dumps(tree, sort_keys=True).encode()) != prior["read_only_import_tree_sha256"]:
        raise ValueError("retained dependencies changed")
    batch.configure(KEY, case, faults, pins)
    spec, environment, _ = runner.definitions()
    if (
        content_digest(spec) != prior["observer_fingerprint"]
        or environment.model_dump(mode="json") != prior["environment"]
    ):
        raise ValueError("prior carrier or observer changed")

    change = {}
    operation_tag = "declared-pytest-plugin"
    if native:
        observation = TARGET / "invocation" / "result.json"
        invocation = runner.get(observation)
        ledger_path = TARGET / "invocation" / "ledger.json"
        ledger = runner.get(ledger_path)
        if (
            invocation["grade"]
            or invocation["observations"]
            != {
                "ok": False,
                "class": "PytestAssertRewriteWarning",
                "sites": [],
            }
            or len(ledger["operations"]) != 6
            or any(item["elapsed_seconds"] is None for item in ledger["operations"])
        ):
            raise ValueError("expected a settled assertion-rewrite diagnostic")
        spec, environment, metadata = entry_point(spec, environment, public, stage=stage)
        operation_tag = "publisher-pytest-entry-point"
        change = {
            "invocation_result_sha256": file_digest(observation),
            "invocation_ledger_sha256": file_digest(ledger_path),
            "pytest_entry_point_projection": metadata,
        }
    case["truth"] = corrected.model_dump(mode="json")
    executor = ContainerExecutor(environment)
    actions, launches = [], []
    for role, previous in zip(("reference", "original"), prior["launches"], strict=True):
        expected = runner.expected_statuses(case["truth"], role)

        async def rehearse(payload, role=role, previous=previous, expected=expected):
            without_plugin = payload | {"wheels": payload["wheels"][:-1]}
            if (
                payload["wheels"][-1]["sha256"] != PYTEST_MOCK_SHA
                or content_digest(without_plugin) != previous["payload_sha256"]
            ):
                raise ValueError("only the declared pytest plugin may differ in the payload")
            context = runner.context(spec, f"{runner.NAME}:{operation_tag}:{role}", payload)
            argv, owner = executor.command(context)
            mounts = {
                f"type=bind,src={path},dst={path},readonly"
                for path in (str(batch.FROZEN / "src"), *environment.read_only_roots)
            }
            if (
                {arg for arg in argv if arg.startswith("type=bind,")} != mounts
                or argv[argv.index("--network") + 1] != "none"
                or argv[argv.index("--user") + 1] != "65534:65534"
                or not {
                    "--pull=never",
                    "--read-only",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                }
                <= set(argv)
            ):
                raise ValueError("protected execution boundary changed")
            actions.append(context)
            launches.append(
                {
                    "role": role,
                    "container": owner,
                    "argv_sha256": content_digest({"argv": argv}),
                    "payload_sha256": content_digest(payload),
                    "archive_sha256": payload["archive_sha256"],
                }
            )
            return {key: payload[key] for key in ("archive_sha256", "python", "pytest")} | {
                "exit_code": int(role == "original"),
                "statuses": expected,
            }

        grade = await grade_suite_output(
            case["input"], case["truth"], case["roles"][role], rehearse
        )
        if grade.quality_score != int(role == "reference"):
            raise ValueError("ordinary grader rehearsal failed")
    return (
        {
            "driver_sha256": file_digest(Path(__file__)),
            "continuation_engine_sha256": file_digest(Path(execute.__code__.co_filename)),
            "parent_review_sha256": file_digest(TARGET / "operation-review.json"),
            "startup_result_sha256": file_digest(startup / "result.json"),
            "startup_ledger_sha256": file_digest(startup / "ledger.json"),
            "pytest_mock": wheel,
            "original_addopts": args,
            "environment": environment.model_dump(mode="json"),
            "observer": content_digest(spec),
            "launches": launches,
            "expires_at": expires,
            "additional_operations": 2,
            "additional_reserved_seconds": 100,
            "downloads": 0,
            "installations": 0,
            "retries": 0,
            "models": 0,
            "cash_usd": 0,
            "provider_disclosure": False,
            **change,
        },
        case,
        executor,
        actions,
        ledger,
    )


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-entry-point", action="store_true")
    args = parser.add_mutually_exclusive_group(required=True)
    args.add_argument("--prepare", action="store_true")
    args.add_argument("--execute")
    selected = parser.parse_args()
    dest = NATIVE_DEST if selected.native_entry_point else DEST
    review = dest / "operation-review.json"
    prior = None if selected.prepare else json.loads(read(review, selected.execute))
    expires = (utc_now() + timedelta(hours=6)).isoformat() if prior is None else prior["expires_at"]
    plan, *context = await prepare(
        expires, native=selected.native_entry_point, stage=selected.prepare
    )
    if selected.prepare:
        dest.mkdir(mode=0o700)
        runner.put(review, plan)
        print(file_digest(review))
    else:
        if plan != prior:
            raise ValueError("approved continuation changed")
        raise SystemExit(
            not await execute(
                selected.execute,
                plan,
                *context,
                target=TARGET,
                correction=dest,
                budget_predecessor=":with-declared-pytest-plugin:budget"
                if selected.native_entry_point
                else ":startup:budget",
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
