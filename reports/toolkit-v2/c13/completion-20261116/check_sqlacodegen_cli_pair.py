"""Prepare the unchanged SQLacodegen 391 CLI tests on the retained SQLite carrier."""

import argparse
import asyncio
import json
import tomllib
from datetime import timedelta
from pathlib import Path

import repository_offline_pair_batch as runner
from audit_staged_repository_graders import bind, index_paths, wheel_probe_assets
from plan_repository_expansion import previous_repositories
from stage_repository_transport import HERE, ROOT, digest, read, write
from stage_varex_calibration import FROZEN, SOURCE

import aeep
from aeep.assessment.models import AssessmentEnvironment
from aeep.assessment.repository_suites import LARGE_PAYLOAD, archive_files
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec, utc_now
from aeep_toolkit.install_runtime import file_digest

CASE = "agronholm__sqlacodegen-391"
NAME = "c13-sqlacodegen-sqlite-cli-391-20261124"
WORK = ROOT / ".aeep/c13-cohort-runtime-20261124" / NAME
SUPPORT = WORK / "cli-support"
UPSTREAM = HERE.parent / "repository-independent-sources-20261024"
BASE_REVIEW = runner.review_fields
SOURCE_REVIEW = "dd7b40a24a3604f7b66fd23487a5f33f7405459a2fc26769b26b903a45b675b1"
IMAGE_BUILD = "dbe2f153b0bb855015adb89c60006df86a44c7572ac7e69a0b5e5d9cd90f36ac"
DEPENDENCY_REVIEW = "249c5f9652904225fc1a35581ca96ef8cc7dee8893f94df70beee578f82f5049"
INDEX_PIN = "378a7a9cf4dc2184f5af65b063547cbc27fc253d6f51d1e74cb3278280d5d4bc"


def project():
    if Path(aeep.__file__).resolve().parents[2] != FROZEN or verification_source_digest(FROZEN) != SOURCE:
        raise ValueError("the previously verified source is required")
    index, pin = next(index_paths())
    if pin != INDEX_PIN:
        raise ValueError("staged repository source inventory changed")
    (row,) = [entry for entry in json.loads(read(index, pin)) if entry["input"]["task_id"] == CASE]
    upstream = json.loads(read(UPSTREAM / "source-review.json", SOURCE_REVIEW))
    (publisher,) = [entry for entry in upstream["sources"] if entry["instance_id"] == CASE]
    read(ROOT / publisher["private_cache"] / "source.tar.gz", publisher["archive_sha256"])
    _, _, exposed = previous_repositories()
    _, core = wheel_probe_assets()
    task, truth, reference, original, metadata = bind(row, index.parent, core)
    source = archive_files(truth.source.read(), large=True)
    if (
        publisher["repository"] != row["source_repository"] or publisher["repository"] in exposed
        or publisher["revision"] != row["source_revision"]
        or not metadata.get("admits_python_3_13_0") or metadata["names_not_declared_in_selected_module"]
        or len(truth.fail_to_pass) != 2 or len(truth.pass_to_pass) != 5
        or not publisher["licenses"] or any(
            digest(source[notice["file"]]) != notice["sha256"] for notice in publisher["licenses"]
        )
    ):
        raise ValueError("publisher identity, licence, or required test inventory changed")
    config = tomllib.loads(source["pyproject.toml"].decode())["project"]
    command = config["scripts"]["sqlacodegen"]
    plugins = config["entry-points"]["sqlacodegen.generators"]
    if command != "sqlacodegen.cli:main" or set(plugins) != {"tables", "declarative", "dataclasses", "sqlmodels"}:
        raise ValueError("published entry point declarations changed")
    if any(not value.startswith("sqlacodegen.generators:") or not value.split(":")[1].isidentifier()
           for value in plugins.values()):
        raise ValueError("generator entry point is outside the reviewed source")
    version = "0+g" + row["source_revision"]
    info = f"metadata/sqlacodegen-{version}.dist-info"
    sections = (
        "[console_scripts]\nsqlacodegen = " + command + "\n\n[sqlacodegen.generators]\n"
        + "".join(f"{name} = {target}\n" for name, target in sorted(plugins.items()))
    )
    files = {
        "bin/sqlacodegen": b"#!/usr/local/bin/python3\nfrom sqlacodegen.cli import main\nmain()\n",
        f"{info}/METADATA": (
            "Metadata-Version: 2.1\nName: sqlacodegen\nVersion: " + version
            + "\nRequires-Python: " + config["requires-python"] + "\n"
            + "".join("Requires-Dist: " + req + "\n" for req in config["dependencies"])
        ).encode(),
        f"{info}/entry_points.txt": sections.encode(),
    }
    case = {
        "case_id": CASE, "source_revision": row["source_revision"], "input": task.model_dump(mode="json"),
        "truth": truth.model_dump(mode="json"), "roles": {"reference": reference, "original": original},
        "reference_archive_sha256": row["reference_archive_sha256"],
        "existing_image_dependencies": ["SQLAlchemy==2.0.44", "inflect==7.5.0"],
    }
    return case, files, version


def projected_observer(version):
    runtime = FROZEN / "integrations/assessment-runtime"
    program = (runtime / "repository_suite_native_program.py").read_text().replace(
        "'__AEEP_NATIVE_CAPTURE_SOURCE__'", repr((runtime / "repository_suite_native_capture.py").read_text())
    )
    old_path = "'PATH': '/usr/local/bin:/usr/bin:/bin'"
    old_bootstrap = "            + ';os.chdir('"
    if program.count(old_path) != 1 or program.count(old_bootstrap) != 1:
        raise ValueError("protected child launch interface changed")
    path = str(SUPPORT / "bin") + ":/usr/local/bin:/usr/bin:/bin"
    addition = (
        "'PATH': " + repr(path)
        + ", 'PYTHONPATH': ':'.join((str(repo / 'src'), str(repo), " + repr(str(SUPPORT / "metadata")) + "))"
        + ", 'PYTHONNOUSERSITE': '1'"
    )
    verification = (
        ";from importlib.metadata import version"
        + ";assert version('SQLAlchemy')=='2.0.44' and version('inflect')=='7.5.0'"
        + ";assert version('sqlacodegen')==" + repr(version)
    )
    program = program.replace(old_path, addition)
    program = program.replace(old_bootstrap, "            + " + repr(verification) + "\n" + old_bootstrap)
    compile(program, "<protected CLI observer>", "exec")
    return program


def definitions():
    case, files, version = project()
    entries = {str(path.relative_to(SUPPORT)): path for path in SUPPORT.rglob("*") if path.is_file()}
    if set(entries) != set(files) or any(path.is_symlink() for path in SUPPORT.rglob("*")):
        raise ValueError("read-only CLI projection changed")
    for name, body in files.items():
        read(entries[name], digest(body))
        mode = 0o555 if name.startswith("bin/") else 0o444
        if entries[name].stat().st_mode & 0o777 != mode:
            raise ValueError("read-only CLI support permissions changed")
    runtime = json.loads(read(UPSTREAM / "runtime-install-review.json", DEPENDENCY_REVIEW))
    if not runtime["complete_static_dependency_closure"]:
        raise ValueError("retained dependency inventory is incomplete")
    spec = ExecutorSpec(
        id="repository.suite.observe", capability="assessment.repository_suite@1", kind="command",
        description="Protected CLI behavior and preservation tests over a local SQLite fixture",
        config={"argv": ["python3", "-B", "-c", projected_observer(version)], "argv_literal": True,
                "stdin_json": True, "timeout_seconds": 40, "max_stdin_bytes": LARGE_PAYLOAD,
                "max_output_bytes": 500_000, "output": {"type": "json"}},
    )
    env = AssessmentEnvironment(
        environment_id=NAME, kind="container", container_image=runner.CARRIER, identity={"source": SOURCE},
        container_runtime=runner.DOCKER, container_socket=runner.SOCKET, memory_mb=512,
        process_limit=96, container_tmpfs_mb=64, read_only_roots=[str(SUPPORT)],
    )
    return spec, env, [case]


async def review_fields():
    fields, spec, env, cases = await BASE_REVIEW()
    _, support, local_version = project()
    if any(run["required_tests"] != 7 for run in fields["launches"]):
        raise ValueError("all seven upstream tests are required")
    return fields | {
        "source_review_sha256": SOURCE_REVIEW, "dependency_review_sha256": DEPENDENCY_REVIEW,
        "image_build_sha256": IMAGE_BUILD, "storage_floor_bytes": 50 * 2**30,
        "wrapper_sha256": file_digest(Path(__file__)), "local_distribution_version": local_version,
        "cli_projection": {name: digest(body) for name, body in support.items()},
        "authority": "C13 first SQLite protected pair. Preserve the source, test overlay and retained image.",
    }, spec, env, cases


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--execute")
    args = parser.parse_args()
    existing = json.loads(read(UPSTREAM / "build-result.json", IMAGE_BUILD))
    if not existing["passed"] or not existing["inherited_config_verified"] or not existing["parent_layers_verified"]:
        raise ValueError("retained SQLite carrier lacks verified lineage")
    runner.CARRIER, runner.FROZEN, runner.NAME = existing["image_id"], FROZEN, NAME
    runner.REVIEW, runner.RUN, runner.APPROVAL = WORK / "operation-review.json", WORK / "execution", WORK / "scope.json"
    runner.ROLE_SECONDS, runner.MAX_CALLS = 50, 2
    runner.definitions, runner.review_fields = definitions, review_fields
    if args.prepare:
        _, files, _ = project()
        WORK.mkdir(mode=0o700, exist_ok=True)
        for name, body in files.items():
            path = SUPPORT / name
            if path.exists():
                read(path, digest(body))
            else:
                write(path, body)
                path.chmod(0o555 if name.startswith("bin/") else 0o444)
        fields, _, _, _ = await review_fields()
        runner.put(runner.REVIEW, fields | {"expires_at": (utc_now() + timedelta(hours=4)).isoformat()})
        print(digest(runner.REVIEW.read_bytes()))
    else:
        read(runner.REVIEW, args.execute)
        if runner.RUN.exists() or runner.APPROVAL.exists():
            raise ValueError("the earlier attempt must remain settlement-bound")
        runner.put(runner.APPROVAL, {"approved": True, "review_sha256": args.execute})
        raise SystemExit(not await runner.run(args.execute))


if __name__ == "__main__":
    asyncio.run(main())
