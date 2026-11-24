"""Run CCFlow's protected pair using retained libraries and temporary imports."""

import argparse
import ast
import asyncio
import json
import shutil
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import check_retained_carrier_batch as batch
from audit_staged_repository_graders import bind, wheel_probe_assets
from check_ccflow_guest_dependencies import entries
from check_expansion_contracts import NoRedirect, inspect_wheel
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from stage_repository_transport import HERE, ROOT, digest, read, write

from aeep.models import utc_now
from aeep_toolkit.install_runtime import file_digest

BASE = ROOT / ".aeep/c13-cohort-runtime-20261124"
NAME = "c13-ccflow-24-protected-pair-20261124"
WORK = BASE / NAME
INTAKE = BASE / "c13-docling-ccflow-archive-only-v2-20261124/ccflow-verified-archive-projection"
INDEX = "134de2257195b1ac5b2e6a7dcb3aaa604b625de003e136d08271143f8dbef8a5"
REVISION = "67f4b6dcbb387e2e486e408806789d94c9b02886"
FIRST_ATTEMPT = "b47c720f2214fdc9785b0e7f6fa14178cf6b895881f313407244a2d9a09c983f"
ACQUIRED = "3d9742aa2d79759b28c492e9b5de3a6915d903ce6f2d21d905e55d0de3bcf97f"
CHAIN = "81e6cb3d76ea504a15215b99d59c030c85a4a396cb1a20fea4156ab63ec23b92"
DIRECT = {
    "cloudpathlib": "0.23.0",
    "cloudpickle": "3.1.1",
    "dask": "2025.5.1",
    "hydra-core": "1.3.2",
    "ipython": "8.37.0",
    "orjson": "3.11.3",
    "smart-open": "7.3.0.post1",
    "tenacity": "9.1.2",
}
DEPS = {
    "antlr4-python3-runtime": "4.9.3",
    "asttokens": "3.0.0",
    "decorator": "5.2.1",
    "executing": "2.2.0",
    "jedi": "0.19.2",
    "locket": "1.0.0",
    "matplotlib-inline": "0.1.7",
    "omegaconf": "2.3.0",
    "parso": "0.8.4",
    "partd": "1.4.2",
    "pexpect": "4.9.0",
    "ptyprocess": "0.7.0",
    "pure-eval": "0.2.3",
    "stack-data": "0.6.3",
    "toolz": "1.0.0",
    "traitlets": "5.14.3",
}
RETAINED = {
    "nested-pandas": {
        "fsspec": "2026.3.0",
        "numpy": "2.2.6",
        "packaging": "25.0",
        "pandas": "2.2.3",
        "pyarrow": "18.1.0",
        "python-dateutil": "2.9.0.post0",
        "pytz": "2025.2",
        "six": "1.17.0",
        "tzdata": "2025.2",
    },
    "confluence": {
        "annotated-types": "0.7.0",
        "click": "8.2.1",
        "prompt-toolkit": "3.0.52",
        "pydantic": "2.11.7",
        "pydantic-core": "2.33.2",
        "pygments": "2.19.2",
        "pyyaml": "6.0.2",
        "typing-extensions": "4.15.0",
        "typing-inspection": "0.4.1",
        "wcwidth": "0.2.13",
        "wrapt": "1.17.3",
    },
    "pdoc": {"jinja2": "3.1.6", "markupsafe": "3.0.3"},
}
REUSED_PATHS = {
    "nested-pandas": BASE / "c13-nested-pandas-302-20261124/support/nested-pandas",
    "confluence": BASE / "c13-confluence-exporter-contract-20261124/support/cli",
    "pdoc": BASE / "c13-pdoc-806-20261124/support/pdoc",
}
VERSIONS = DIRECT | DEPS | {name: ver for group in RETAINED.values() for name, ver in group.items()}
MARKERS = {
    "python_version": "3.13",
    "python_full_version": "3.13.15",
    "sys_platform": "linux",
    "platform_system": "Linux",
    "platform_machine": "aarch64",
    "os_name": "posix",
    "extra": "",
}
CACHED_WHEELS = (
    *(path.parents[1] / "wheels" for path in REUSED_PATHS.values()),
    BASE / "c13-virtualizarr-395-20261124/wheels",
    ROOT / ".aeep/completion-20261116/fusesoc-runtime-wheels",
)
runner = batch.runner
BASE_REVIEW, BASE_VERIFY = runner.review_fields, runner.verify_probe


def subject():
    batch.cases()
    (row,) = json.loads(read(INTAKE / "index.json", INDEX))
    task, truth, reference, original, metadata = bind(
        row, INTAKE / "transport", wheel_probe_assets()[1]
    )
    required = json.loads(
        read(
            INTAKE / "transport/protected" / task.task_id / "required.json",
            row["protected_assets"]["required.json"]["sha256"],
        )
    )
    if (
        row["source_revision"] != REVISION
        or row["source_repository"] != "point72/ccflow"
        or row["source_repository"] in batch.previous_repositories()[2]
        or len(truth.pass_to_pass) != 25
        or not metadata["admits_python_3_13_0"]
        or metadata["names_not_declared_in_selected_module"]
        or {test.split("[")[0] for test in required["published_fail_to_pass"]}
        != {"ccflow/tests/test_callable.py::TestCallableModel::test_signature"}
    ):
        raise ValueError("archived source, Python range or required checks changed")
    return {
        "case_id": task.task_id,
        "source_revision": REVISION,
        "input": task.model_dump(mode="json"),
        "truth": truth.model_dump(mode="json"),
        "roles": {"reference": reference, "original": original},
        "reference_archive_sha256": row["reference_archive_sha256"],
        "existing_image_dependencies": [],
    }, {row["protected_guard"], *required["published_fail_to_pass"]}


def check_edges(requirements):
    for item in requirements:
        require = Requirement(item)
        if require.marker is not None and not require.marker.evaluate(MARKERS):
            continue
        name = canonicalize_name(require.name)
        if (
            require.url
            or require.extras
            or name not in VERSIONS
            or VERSIONS[name] not in require.specifier
        ):
            raise ValueError(f"unbound Linux runtime requirement: {item}")


def release(item):
    name, version = item
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(f"https://pypi.org/pypi/{name}/{version}/json", timeout=15) as response:
        data = response.read(700001)
    if len(data) > 700000:
        raise ValueError("publisher metadata exceeded the bound")
    metadata = json.loads(data)
    check_edges(metadata["info"]["requires_dist"] or [])
    source = name == "antlr4-python3-runtime"
    choices = [
        row
        for row in metadata["urls"]
        if not row["yanked"]
        and (
            row["packagetype"] == "sdist"
            if source
            else row["packagetype"] == "bdist_wheel" and batch.wheel_rank(row["filename"])
        )
    ]
    choices.sort(key=lambda row: 1 if source else batch.wheel_rank(row["filename"]), reverse=True)
    if not choices or (
        not source
        and len(choices) > 1
        and batch.wheel_rank(choices[0]["filename"]) == batch.wheel_rank(choices[1]["filename"])
    ):
        raise ValueError(f"no unique Linux artifact for {name} {version}")
    row = choices[0]
    if row["requires_python"] and "3.13.15" not in SpecifierSet(row["requires_python"]):
        raise ValueError(f"{name} does not admit Python 3.13")
    filename, sha = row["filename"], row["digests"]["sha256"]
    owner = next((key for key, values in RETAINED.items() if name in values), None)
    cached = next(
        (
            path
            for folder in CACHED_WHEELS
            if (path := folder / filename).is_file() and digest(path.read_bytes()) == sha
        ),
        None,
    )
    if owner and cached is None:
        raise ValueError(f"existing projection for {name} has no verified wheel")
    if (
        not row["url"].startswith("https://files.pythonhosted.org/packages/")
        or row["url"].rsplit("/", 1)[-1] != filename
    ):
        raise ValueError("publisher returned an unexpected artifact location")
    return name, {
        "version": version,
        "filename": filename,
        "sha256": sha,
        "size": row["size"],
        "url": row["url"],
        "publisher_metadata_sha256": digest(data),
        "reuse": owner,
        "cached_wheel": cached.relative_to(ROOT).as_posix() if cached else None,
    }


def acquisition_review():
    with ThreadPoolExecutor(max_workers=8) as pool:
        pins = dict(pool.map(release, sorted(VERSIONS.items())))
    chain = json.loads(
        read(HERE / "ccflow-configuration-dependency-preflight-20261124.json", CHAIN)
    )
    if any(
        pins[name]["sha256"] != row["artifact"]["sha256"]
        for name, row in chain["candidate_chain"].items()
    ):
        raise ValueError("configuration dependency changed from the reviewed candidate")
    new = [item for item in pins.values() if item["reuse"] is None]
    total = sum(row["size"] for row in new)
    if total > 6 * 1024**2:
        raise ValueError("compressed inputs exceed temporary runtime scope")
    return {
        "schema_version": "aeep.c13.ccflow-runtime-intake.v1",
        "pins": pins,
        "source_index_sha256": INDEX,
        "driver_sha256": file_digest(Path(__file__)),
        "additional_retention_bytes": total,
        "maximum_download_bytes": sum(row["size"] for row in new if row["cached_wheel"] is None),
        "installations": 0,
        "models": 0,
        "cash_usd": 0,
        "retries": 0,
    }


def retain(review):
    if (
        shutil.disk_usage(WORK).free
        < batch.assets.FLOOR + review["additional_retention_bytes"] + 1024**2
    ):
        raise ValueError("preserve the host reserve through runtime intake")
    artifacts = WORK / "artifacts"
    artifacts.mkdir(mode=0o700)
    opener = urllib.request.build_opener(NoRedirect())
    for row in review["pins"].values():
        if row["reuse"] is not None:
            continue
        if row["cached_wheel"]:
            data = read(ROOT / row["cached_wheel"], row["sha256"])
        else:
            with opener.open(row["url"], timeout=20) as response:
                data = response.read(row["size"] + 1)
        if len(data) != row["size"] or digest(data) != row["sha256"]:
            raise ValueError(f"publisher artifact changed: {row['filename']}")
        path = artifacts / row["filename"]
        write(path, data)
        path.chmod(0o444)
    return artifacts


def inspect_runtime_wheel(path, name, pin, files):
    if name not in {"ipython", "cloudpickle"}:
        return inspect_wheel(path, name, pin["sha256"], pin["version"])
    with TemporaryDirectory(dir=WORK, prefix="runtime-wheel-check-") as directory:
        copy = Path(directory) / path.name
        with ZipFile(path) as original, ZipFile(copy, mode="w") as libraries:
            for item in original.infolist():
                if item.filename != "ipython-8.37.0.data/data/share/man/man1/ipython.1":
                    libraries.writestr(item, original.read(item))
            if name == "cloudpickle":
                notice = "cloudpickle-3.1.1.dist-info/LICENSE.txt"
                libraries.writestr(notice, files[notice])
        return inspect_wheel(copy, name, file_digest(copy), pin["version"])


def verify_inputs(lock, *, prepare, earlier):
    if earlier is None and shutil.disk_usage(WORK).free < batch.assets.FLOOR + 2 * 1024**2:
        raise ValueError("preserve the host reserve during library validation")
    projected, retained, licenses = {}, {}, {}
    seen = set()
    expanded = 0
    for name, pin in lock["pins"].items():
        owner = pin["reuse"]
        path = ROOT / pin["cached_wheel"] if owner else WORK / "artifacts" / pin["filename"]
        raw = read(path, pin["sha256"])
        if len(raw) != pin["size"]:
            raise ValueError("runtime artifact length differs")
        files = entries(path)
        if earlier and name in {"cloudpickle", "ipython"}:
            verified = earlier["license_notices"][name]
            if not verified or any(digest(files[key]) != sha for key, sha in verified.items()):
                raise ValueError("previously reviewed library projection changed")
            licenses[name] = verified
        elif path.name.endswith(".whl"):
            meta = inspect_runtime_wheel(path, name, pin, files)
            check_edges(meta["active_requires_dist"])
            licenses[name] = meta["license_notice_digests"]
        if owner or name == "orjson":
            # Native extension code cannot load from the worker's noexec tmpfs.
            root = REUSED_PATHS[owner] if owner else WORK / "native"
            for filename, data in files.items():
                target = root / filename
                if prepare and not owner and not target.exists():
                    write(target, data)
                    target.chmod(0o444)
                if read(target, digest(data)) != data:
                    raise ValueError(f"retained projection changed: {name}")
            retained[name] = str(root)
        else:
            if seen.intersection(files):
                raise ValueError("temporary dependency paths overlap")
            seen.update(files)
            expanded += sum(
                max(4096, (len(value) + 4095) // 4096 * 4096) for value in files.values()
            )
            projected[str(path)] = pin["sha256"]
            if name == "antlr4-python3-runtime":
                licenses[name] = {
                    key: digest(value)
                    for key, value in files.items()
                    if key.endswith(("/LICENSE.txt", "/LICENSE"))
                }
                if not licenses[name]:
                    raise ValueError("ANTLR source has no reviewed license notice")
    if expanded > 50 * 1024**2:
        raise ValueError("temporary dependency projection exceeds its allocation bound")
    return projected, retained, licenses, expanded


def compile_bootstrap(program):
    # Exercise the generated child code without importing upstream dependencies.
    (assignment,) = [
        node
        for node in ast.walk(ast.parse(program))
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "boot" for target in node.targets)
    ]
    reviewed = {
        "wheels": [],
        "repo": Path("/tmp/aeep-repository-native-v6"),
        "request": {"pytest": "8.3.5"},
        "plugins": [],
        "source_modules": ["ccflow"],
        "CAPTURE_SOURCE": "pass",
        "collect_only": False,
        "support": Path("/tmp/ccflow-imports"),
        "argv": ["--no-header"],
        "events": Path("/tmp/native-events.json"),
    }
    assembled = eval(
        compile(ast.Expression(assignment.value), "<reviewed startup assembly>", "eval"),
        {"__builtins__": {"repr": repr, "str": str}},
        reviewed,
    )
    compile(assembled, "<reviewed pytest child>", "exec")


def configure(case, faults, *, prepare, correction=False):
    review_file = WORK / "runtime-intake.json"
    lock = json.loads(read(review_file, ACQUIRED))
    if (
        lock["source_index_sha256"] != INDEX
        or {name: row["version"] for name, row in lock["pins"].items()} != VERSIONS
    ):
        raise ValueError("runtime intake changed")
    earlier = None
    root = WORK
    if correction:
        earlier = json.loads(read(WORK / "operation-review.json", FIRST_ATTEMPT))
        result = runner.get(WORK / "execution/result.json")
        observed = runner.get(WORK / "execution/observation-reference.json")
        if (
            earlier["runtime_intake_sha256"] != ACQUIRED
            or result["review_sha256"] != FIRST_ATTEMPT
            or len(result["observations"]) != 1
            or result["verified"]
            or observed.get("phase") != "pytest_bootstrap"
            or observed.get("category") != "SyntaxError"
        ):
            raise ValueError("correction requires the preserved pre-test startup failure")
        root = WORK / "bootstrap-correction"
    projected, retained, licenses, expanded = verify_inputs(
        lock,
        prepare=prepare and not correction,
        earlier=earlier,
    )
    runner.NAME, runner.REVIEW, runner.APPROVAL, runner.RUN = (
        NAME + ("-bootstrap-correction" if correction else ""),
        root / "operation-review.json",
        root / "scope.json",
        root / "execution",
    )
    runner.FROZEN = batch.FROZEN
    runner.MAX_CALLS, runner.ROLE_SECONDS = 2, 55
    helper = Path(__file__).with_name("check_ccflow_guest_dependencies.py")
    native = batch.FROZEN / "integrations/assessment-runtime"
    program = (native / "repository_suite_native_program.py").read_text()
    capture = (native / "repository_suite_native_capture.py").read_text()
    diagnostics = Path(__file__).with_name("pytest_failure_diagnostics.py").read_text()
    hook = "        argv = ['--no-header'"
    marker = "            + ';import pytest;"
    envelope = "assert set(native) == {'statuses'}"
    failure = "        assert log.stat().st_size"
    if (
        any(program.count(token) != 1 for token in (hook, marker, failure))
        or program.count(envelope) != 2
    ):
        raise ValueError("native observer hooks changed")
    bootstrap = (
        "from importlib.metadata import distribution;"
        + f"expected={VERSIONS!r}; retained={retained!r};"
        + 'assert all(distribution(n).version==v and str(distribution(n).locate_file(""))==retained.get(n,sys.path[0]) for n,v in expected.items())'
    )
    program = helper.read_text() + "\n" + program
    program = program.replace(hook, f"        support = project(root, {projected!r})\n" + hook)
    program = program.replace(
        marker,
        '            + ";sys.path[:0]=" + repr([str(support), *'
        + repr(sorted(set(retained.values())))
        + ']) + ";"\n'
        + "            + "
        + repr(bootstrap)
        + "\n"
        + marker,
    )
    program = program.replace(
        failure,
        "        if not events.exists():\n"
        "            return bootstrap_failure(log, child.returncode)\n" + failure,
    )
    program = program.replace(
        "'__AEEP_NATIVE_CAPTURE_SOURCE__'",
        repr(
            capture + "\n" + diagnostics + "\nNativeCapture = diagnostic_capture(NativeCapture)\n"
        ),
    ).replace(envelope, "assert set(native) == {'statuses', 'failure_sites'}")
    compile(program, "<CCFlow native observer>", "exec")
    compile_bootstrap(program)
    batch.assets.SUPPORT = WORK
    batch.assets.observer = lambda *_: program
    spec, environment, _ = batch.assets.definitions("ccflow", {}, case)
    spec = spec.model_copy(
        update={
            "description": "Protected CCFlow checks with temporary Linux imports",
            "config": spec.config | {"timeout_seconds": 45},
        }
    )
    environment = environment.model_copy(
        update={
            "read_only_roots": sorted({str(WORK / "artifacts"), *retained.values()}),
        }
    )
    runner.definitions = lambda: (spec, environment, [case])
    runner.expected_statuses = lambda truth, role: {
        test: "FAILED" if role == "original" and test in faults else "PASSED"
        for test in truth["fail_to_pass"] + truth["pass_to_pass"]
    }

    def observe(reply, payload, expected, code):
        if not isinstance(reply, dict):
            return False
        runner.put(runner.RUN / f"observation-{'original' if code else 'reference'}.json", reply)
        return BASE_VERIFY(runner.scorer_reply(reply), payload, expected, code)

    runner.scorer_reply = lambda reply: {
        key: value for key, value in reply.items() if key != "failure_sites"
    }
    runner.verify_probe = observe

    async def fields():
        raw, _, _, _ = await BASE_REVIEW()
        return (
            raw
            | {
                "coordinator_sha256": file_digest(Path(__file__)),
                "guest_projection_sha256": file_digest(helper),
                "runtime_intake_sha256": file_digest(review_file),
                "source_index_sha256": INDEX,
                "storage_floor_bytes": batch.assets.FLOOR,
                "license_notices": licenses,
                "temporary_dependency_allocation_bound": expanded,
                "expected_original_failures": sorted(faults),
                "prior_attempt_sha256": FIRST_ATTEMPT if correction else None,
                "prior_result_sha256": file_digest(WORK / "execution/result.json")
                if correction
                else None,
                "authority": "First protected C13 CCFlow pair on the retained offline carrier.",
            },
            spec,
            environment,
            [case],
        )

    runner.review_fields = fields


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare-download", action="store_true")
    action.add_argument("--acquire")
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--execute")
    action.add_argument("--prepare-correction", action="store_true")
    action.add_argument("--execute-correction")
    args = parser.parse_args()
    case, faults = subject()
    review_path = WORK / "runtime-intake.json"
    if args.prepare_download:
        lock = acquisition_review()
        print(write(review_path, (json.dumps(lock, indent=2) + "\n").encode())["sha256"])
        return
    if args.acquire:
        lock = json.loads(read(review_path, args.acquire))
        if lock["driver_sha256"] != file_digest(Path(__file__)):
            raise ValueError("runtime acquisition code changed after review")
        retain(lock)
        return
    if args.prepare:
        (WORK / "artifacts").chmod(0o555)
    configure(
        case,
        faults,
        prepare=args.prepare,
        correction=bool(args.prepare_correction or args.execute_correction),
    )
    if args.prepare or args.prepare_correction:
        review, _, _, _ = await runner.review_fields()
        runner.REVIEW.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        runner.put(
            runner.REVIEW, review | {"expires_at": (utc_now() + timedelta(hours=16)).isoformat()}
        )
        print(file_digest(runner.REVIEW))
    else:
        exact = args.execute or args.execute_correction
        read(runner.REVIEW, exact)
        if not runner.APPROVAL.exists():
            runner.put(runner.APPROVAL, {"approved": True, "review_sha256": exact})
        raise SystemExit(not await runner.run(exact))


if __name__ == "__main__":
    asyncio.run(main())
