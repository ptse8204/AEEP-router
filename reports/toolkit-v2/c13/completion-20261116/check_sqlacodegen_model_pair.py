"""Grade SQLacodegen 419 with the declared SQLAlchemy range and local SQLite."""

import argparse
import ast
import asyncio
import io
import json
import tomllib
from datetime import timedelta
from pathlib import Path
from zipfile import ZipFile

import check_retained_carrier_batch as batch
import check_sqlacodegen_cli_pair as cli
from audit_staged_repository_graders import bind, index_paths, wheel_probe_assets
from packaging.requirements import Requirement
from stage_repository_transport import ROOT, digest, read, write

import aeep
from aeep.assessment.models import AssessmentEnvironment
from aeep.assessment.repository_suites import LARGE_PAYLOAD, archive_files
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec, utc_now
from aeep_toolkit.install_runtime import file_digest

runner = batch.runner
BASE_REVIEW, BASE_VERIFY = runner.review_fields, runner.verify_probe
CASE, NAME = "agronholm__sqlacodegen-419", "c13-sqlacodegen-419-20261124"
WORK = ROOT / ".aeep/c13-cohort-runtime-20261124" / NAME
SUPPORT = WORK / "cli-support"
FROZEN, SOURCE = cli.FROZEN, cli.SOURCE
REQUIRED = {
    "tests/test_cli.py": 7,
    "tests/test_generator_dataclass.py": 6,
    "tests/test_generator_declarative.py": 46,
    "tests/test_generator_sqlmodel.py": 5,
}


def bind_case(pins):
    if (
        Path(aeep.__file__).resolve().parents[2] != FROZEN
        or verification_source_digest(FROZEN) != SOURCE
    ):
        raise ValueError("load the verified toolkit source")
    index, pin = next(index_paths())
    if pin != cli.INDEX_PIN:
        raise ValueError("source inventory changed")
    (row,) = [item for item in json.loads(read(index, pin)) if item["input"]["task_id"] == CASE]
    publisher_review = json.loads(read(cli.UPSTREAM / "source-review.json", cli.SOURCE_REVIEW))
    (publisher,) = [item for item in publisher_review["sources"] if item["instance_id"] == CASE]
    read(ROOT / publisher["private_cache"] / "source.tar.gz", publisher["archive_sha256"])
    _, core = wheel_probe_assets()
    task, truth, reference, original, metadata = bind(row, index.parent, core)
    source = archive_files(truth.source.read(), large=True)
    files = source | archive_files(truth.tests.read(), large=True)
    required = truth.fail_to_pass + truth.pass_to_pass
    if (
        row["source_repository"] != publisher["repository"]
        or publisher["repository"] in cli.previous_repositories()[2]
        or row["source_revision"] != publisher["revision"]
        or not publisher["licenses"]
        or any(digest(source[item["file"]]) != item["sha256"] for item in publisher["licenses"])
        or not metadata["admits_python_3_13_0"]
        or metadata["names_not_declared_in_selected_module"]
        or set(truth.test_paths) != REQUIRED.keys()
        or len(truth.fail_to_pass) != 9
        or any(
            sum(test.startswith(path + "::") for test in required) != n
            for path, n in REQUIRED.items()
        )
    ):
        raise ValueError("publisher source, rights, or test inventory differs")
    # The generator tests build engines for dialect compilation. The CLI
    # tests connect only to the SQLite file created in the test workspace.
    allowed_engines = {
        "postgresql+psycopg:///testdb",
        "mysql+mysqlconnector://testdb",
        "sqlite:///:memory:",
    }
    engines = set()
    for path in [*REQUIRED, "tests/conftest.py"]:
        for node in ast.walk(ast.parse(files[path])):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "create_engine"
            ):
                engines.add(ast.literal_eval(node.args[0]))
            if (
                path != "tests/test_cli.py"
                and isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"connect", "begin", "execute", "create_all", "reflect"}
            ):
                raise ValueError("generator tests reach database I/O")
    cli_source = files["tests/test_cli.py"].decode()
    if engines != allowed_engines or cli_source.count("sqlite:///") != 6:
        raise ValueError("local database fixture or adapter set changed")

    project = tomllib.loads(source["pyproject.toml"].decode())["project"]
    requirements = [
        Requirement(item)
        for item in project["dependencies"] + project["optional-dependencies"]["sqlmodel"]
    ]
    for requirement in requirements:
        if requirement.marker and not requirement.marker.evaluate({"python_version": "3.13"}):
            continue
        name = requirement.name.lower()
        if name not in pins or pins[name]["version"] not in requirement.specifier:
            raise ValueError(
                f"publisher dependency incompatible with pinned carrier: {requirement}"
            )
    entry = project["scripts"]["sqlacodegen"]
    plugins = project["entry-points"]["sqlacodegen.generators"]
    if entry != "sqlacodegen.cli:main" or plugins != {
        "tables": "sqlacodegen.generators:TablesGenerator",
        "declarative": "sqlacodegen.generators:DeclarativeGenerator",
        "dataclasses": "sqlacodegen.generators:DataclassGenerator",
        "sqlmodels": "sqlacodegen.generators:SQLModelGenerator",
    }:
        raise ValueError("publisher entry points changed")
    version = "0+g" + row["source_revision"]
    metadata_path = f"metadata/sqlacodegen-{version}.dist-info"
    projection = {
        "bin/sqlacodegen": b"#!/usr/local/bin/python3\nfrom sqlacodegen.cli import main\nmain()\n",
        f"{metadata_path}/METADATA": (
            f"Metadata-Version: 2.1\nName: sqlacodegen\nVersion: {version}\n"
            + "".join(f"Requires-Dist: {item}\n" for item in project["dependencies"])
        ).encode(),
        f"{metadata_path}/entry_points.txt": (
            f"[console_scripts]\nsqlacodegen = {entry}\n\n[sqlacodegen.generators]\n"
            + "".join(f"{name} = {target}\n" for name, target in sorted(plugins.items()))
        ).encode(),
    }
    return (
        {
            "case_id": CASE,
            "source_revision": row["source_revision"],
            "input": task.model_dump(mode="json"),
            "truth": truth.model_dump(mode="json"),
            "roles": {"reference": reference, "original": original},
            "reference_archive_sha256": row["reference_archive_sha256"],
            "existing_image_dependencies": [],
        },
        projection,
        version,
    )


def projection_check(files, *, prepare):
    for name, body in files.items():
        path = SUPPORT / name
        mode = 0o555 if name.startswith("bin/") else 0o444
        if prepare and not path.exists():
            write(path, body)
            path.chmod(mode)
        read(path, digest(body))
        if path.stat().st_mode & 0o777 != mode:
            raise ValueError("read-only CLI metadata permissions changed")
    if (
        any(path.is_symlink() for path in SUPPORT.rglob("*"))
        or {path.relative_to(SUPPORT).as_posix() for path in SUPPORT.rglob("*") if path.is_file()}
        != files.keys()
    ):
        raise ValueError("unreviewed CLI metadata or launchers detected")


def import_wheels(pins, *, prepare):
    """Remove a C header that is outside greenlet's importable wheel files."""
    directory = WORK / "import-wheels"
    projected = {}
    removed = {}
    for name, pin in pins.items():
        data = read(WORK / "wheels" / pin["filename"], pin["sha256"])
        if name == "greenlet":
            root = "greenlet-3.2.4.data/"
            header = root + "headers/greenlet.h"
            output = io.BytesIO()
            with ZipFile(io.BytesIO(data)) as source, ZipFile(output, "w") as target:
                omitted = {
                    item.filename for item in source.infolist() if item.filename.startswith(root)
                }
                if omitted != {root, root + "headers/", header}:
                    raise ValueError("reviewed greenlet development header set differs")
                removed[header] = digest(source.read(header))
                for item in source.infolist():
                    if item.filename not in omitted:
                        target.writestr(item, source.read(item))
            data = output.getvalue()
        sha = digest(data)
        path = directory / pin["filename"]
        if prepare and not path.exists():
            write(path, data)
        read(path, sha)
        projected[name] = pin | {"sha256": sha}
    return directory, projected, removed


def observer(version, pins, import_root):
    cli.SUPPORT = SUPPORT
    program = cli.projected_observer(version)
    capture = (
        FROZEN / "integrations/assessment-runtime/repository_suite_native_capture.py"
    ).read_text()
    diagnostic = Path(__file__).with_name("pytest_failure_diagnostics.py").read_text()
    verification = ";assert version('SQLAlchemy')=='2.0.44' and version('inflect')=='7.5.0'"
    if program.count(verification) != 1 or program.count(repr(capture)) != 1:
        raise ValueError("protected bootstrap or capture template changed")
    versions = {name: item["version"] for name, item in pins.items()}
    check = (
        f";sys.path.insert(0,{str(import_root)!r});"
        f"assert all(version(name)==v for name,v in {versions!r}.items());"
        "import sqlalchemy,sqlmodel,psycopg.pq,mysql.connector,pydantic_core;"
        "assert psycopg.pq.__impl__=='binary';"
        "assert all(Path(m.__file__).is_relative_to("
        f"{str(import_root)!r}) for m in (sqlalchemy,sqlmodel,mysql.connector,pydantic_core))"
    )
    # Replace only the inherited version check and add the reviewed directory
    # to the ordinary console-script subprocess search path.
    program = program.replace(verification, repr(check)[1:-1])
    pythonpath_end = repr(str(SUPPORT / "metadata")) + "))"
    if program.count(pythonpath_end) != 1:
        raise ValueError("projected console-script environment changed")
    program = program.replace(
        pythonpath_end, repr(str(SUPPORT / "metadata")) + ", " + repr(str(import_root)) + "))"
    )
    program = program.replace(
        repr(capture),
        repr(capture + "\n" + diagnostic + "\nNativeCapture = diagnostic_capture(NativeCapture)\n"),
    )
    program = program.replace(
        "assert set(native) == {'statuses'}", "assert set(native) == {'statuses', 'failure_sites'}"
    )
    compile(program, "<SQLacodegen protected observer>", "exec")
    return program


def configure(*, prepare):
    intake = runner.get(WORK / "acquisition-result.json")
    lock = json.loads(read(WORK / "acquisition-review.json", intake["review_sha256"]))
    if not intake["completed"] or lock["driver_sha256"] != file_digest(Path(batch.__file__)):
        raise ValueError("dependency intake has no matching completed review")
    pins = {item["name"]: item for item in lock["files"].values()}
    case, files, version = bind_case(pins)
    wheel_directory, import_pins, excluded_headers = import_wheels(pins, prepare=prepare)
    batch.assets.WHEELS, batch.assets.SUPPORT = wheel_directory, WORK / "support"
    tree = batch.assets.support_check("models", import_pins, prepare=prepare)
    projection_check(files, prepare=prepare)
    image = json.loads(read(cli.UPSTREAM / "build-result.json", cli.IMAGE_BUILD))
    if not all(
        image[key] for key in ("passed", "inherited_config_verified", "parent_layers_verified")
    ):
        raise ValueError("retained runtime lacks verified parent configuration")
    runner.NAME, runner.FROZEN, runner.CARRIER = NAME, FROZEN, image["image_id"]
    runner.REVIEW, runner.APPROVAL, runner.RUN = (
        WORK / "operation-review.json",
        WORK / "scope.json",
        WORK / "execution",
    )
    runner.ROLE_SECONDS, runner.MAX_CALLS = 65, 2
    import_root = batch.assets.SUPPORT / "models"
    spec = ExecutorSpec(
        id="repository.suite.observe",
        capability="assessment.repository_suite@1",
        kind="command",
        description="SQLacodegen model generation and local SQLite CLI tests",
        config={
            "argv": ["python3", "-B", "-c", observer(version, pins, import_root)],
            "argv_literal": True,
            "stdin_json": True,
            "timeout_seconds": 50,
            "max_stdin_bytes": LARGE_PAYLOAD,
            "max_output_bytes": 500_000,
            "output": {"type": "json"},
        },
    )
    env = AssessmentEnvironment(
        environment_id=NAME,
        kind="container",
        container_image=runner.CARRIER,
        identity={"source": SOURCE},
        container_runtime=runner.DOCKER,
        container_socket=runner.SOCKET,
        memory_mb=512,
        process_limit=96,
        container_tmpfs_mb=64,
        read_only_roots=[str(SUPPORT), str(import_root)],
    )
    runner.definitions = lambda: (spec, env, [case])
    runner.scorer_reply = lambda reply: {
        key: value for key, value in reply.items() if key != "failure_sites"
    }

    def checked(reply, payload, expected, code):
        if not isinstance(reply, dict) or not isinstance(reply.get("failure_sites"), list):
            return False
        runner.put(runner.RUN / f"observation-{'original' if code else 'reference'}.json", reply)
        return BASE_VERIFY(runner.scorer_reply(reply), payload, expected, code)

    runner.verify_probe = checked

    async def fields():
        reviewed, _, _, _ = await BASE_REVIEW()
        if any(item["required_tests"] != 64 for item in reviewed["launches"]):
            raise ValueError("review must bind all 64 exact native identities")
        return (
            reviewed
            | {
                "coordinator_sha256": file_digest(Path(__file__)),
                "storage_floor_bytes": batch.assets.FLOOR,
                "dependency_intake_sha256": intake["review_sha256"],
                "dependency_mount_sha256": digest(json.dumps(tree, sort_keys=True).encode()),
                "non_runtime_headers_excluded": excluded_headers,
                "launcher_projection": {name: digest(data) for name, data in files.items()},
                "external_database_services": 0,
                "authority": "First contained protected pair under C13's standing offline scope.",
            },
            spec,
            env,
            [case],
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
            raise ValueError("previous attempt must remain immutable")
        runner.put(runner.APPROVAL, {"approved": True, "review_sha256": args.execute})
        raise SystemExit(not await runner.run(args.execute))


if __name__ == "__main__":
    asyncio.run(main())
