"""Prepare a protected local unit-suite projection without launching a grader."""

import argparse
import ast
import json
import tomllib

from acquire_larger_multifile_source import CASE, SCOPE, binding
from audit_staged_repository_graders import bind, wheel_probe_assets
from packaging.markers import Marker
from packaging.utils import parse_wheel_filename
from stage_repository_transport import digest, encode, read, write

from aeep.assessment.repository_suites import archive_files, pack_files

BASE = SCOPE / "execution"
INDEX_PIN = "3520592806a57a758aa9c4037a01776217c0bfb863b0a692e3c58032cb6af56e"
CONFT = "tests/conftest.py"
TEST = "tests/unit/test_repository.py"
TARGET = SCOPE / "unit-grader-preflight"
PROVIDER_FIXTURES = {"monkeypatch", "request", "mocker", "testrun_uid"}
ROOT_PACKAGES = {
    "alembic",
    "greenlet",
    "msgspec",
    "numpy",
    "pydantic",
    "pytest",
    "pytest-asyncio",
    "pytest-lazy-fixtures",
    "pytest-mock",
    "pytest-xdist",
    "sqlalchemy",
    "typing-extensions",
}
MODEL_ENV = {
    "implementation_name": "cpython",
    "implementation_version": "3.13.0",
    "os_name": "posix",
    "platform_machine": "aarch64",
    "platform_python_implementation": "CPython",
    "platform_system": "Linux",
    "python_full_version": "3.13.0",
    "python_version": "3.13",
    "sys_platform": "linux",
    "platform_release": "",
    "platform_version": "",
    "extra": "",
}
PLATFORMS = {
    "manylinux2014_aarch64",
    "manylinux_2_17_aarch64",
    "manylinux_2_24_aarch64",
    "manylinux_2_27_aarch64",
    "manylinux_2_28_aarch64",
}


def functions(tree):
    return (node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))


def fixture(node):
    return any(ast.unparse(dec).split("(")[0] == "pytest.fixture" for dec in node.decorator_list)


def local_projection(parent, tests):
    tree = ast.parse(tests)
    inline = {node.name for node in functions(tree) if fixture(node)}
    scopes = [tree, *(node for node in tree.body if isinstance(node, ast.ClassDef))]
    observed = set()
    for node in (node for scope in scopes for node in functions(scope)):
        if not node.name.startswith("test_") and not fixture(node):
            continue
        values = {arg.arg for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs}
        values.discard("self")
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            method = ast.unparse(dec.func)
            if method == "pytest.mark.parametrize":
                names = ast.literal_eval(dec.args[0])
                values -= set(names.split(",") if isinstance(names, str) else names)
        observed |= values
    blocked = {
        ast.unparse(node.func).split(".")[-1]
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and ast.unparse(node.func).split(".")[-1] in {"getfixturevalue", "usefixtures"}
    }
    if observed - inline - PROVIDER_FIXTURES or blocked or "pytest_plugins" in tests:
        raise ValueError("the unit suite has an unreviewed fixture or dynamic fixture request")
    lazy = {
        ast.literal_eval(node.args[0])
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "lf"
    }
    if lazy != {"sync_mock_repo", "async_mock_repo"} or not lazy <= inline:
        raise ValueError("lazy fixture references changed")

    config = parent.decode()
    handlers = list(functions(ast.parse(config)))
    auto = [
        node
        for node in handlers
        if fixture(node)
        and any(
            isinstance(dec, ast.Call)
            and any(
                key.arg == "autouse" and ast.literal_eval(key.value) is True for key in dec.keywords
            )
            for dec in node.decorator_list
        )
    ]
    if [node.name for node in auto] != ["configure_logging"]:
        raise ValueError("upstream autouse fixture set changed")
    if observed & {node.name for node in handlers if node not in auto}:
        raise ValueError("the selected suite needs a removed parent fixture")
    logging_fixture = auto[0]
    names = {node.id for node in ast.walk(logging_fixture) if isinstance(node, ast.Name)}
    if not names <= {"pytest", "logging", "logger_name"}:
        raise ValueError("the retained upstream autouse fixture depends on unexpected imports")
    lines = config.splitlines(keepends=True)
    retained = "".join(
        lines[logging_fixture.decorator_list[0].lineno - 1 : logging_fixture.end_lineno]
    )
    projected = ("import logging\n\nimport pytest\n\n\n" + retained + "\n").encode()
    (compare,) = list(functions(ast.parse(projected)))
    if ast.dump(compare) != ast.dump(logging_fixture):
        raise ValueError("the upstream logging fixture was changed")
    return projected, {
        "parent_autouse_fixture_retained": logging_fixture.name,
        "parent_service_fixtures_needed_by_declared_unit_signatures": [],
        "in_module_fixtures": sorted(inline),
        "explicit_plugin_or_pytest_fixtures": sorted(observed & PROVIDER_FIXTURES),
        "lazy_fixtures": sorted(lazy),
    }


def wheel_closure(raw_lock):
    lock = tomllib.loads(raw_lock.decode())
    packages = {}
    for row in lock["package"]:
        markers = row.get("resolution-markers")
        if markers and not any(Marker(marker).evaluate(MODEL_ENV) for marker in markers):
            continue
        if row["name"] in packages:
            raise ValueError("ambiguous lock entry for the target Python")
        packages[row["name"]] = row

    seen = {}
    stack = sorted(ROOT_PACKAGES)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        row = packages[name]
        edges = [
            edge
            for edge in row.get("dependencies", [])
            if ("marker" not in edge or Marker(edge["marker"]).evaluate(MODEL_ENV))
        ]
        if any("extra" in edge for edge in edges):
            raise ValueError("runtime lock closure needs an explicit extra")
        wheels = []
        for wheel in row.get("wheels", []):
            url = wheel["url"]
            fname = url.rsplit("/", 1)[-1]
            universal = fname.endswith("-none-any.whl")
            native = any(
                tag.interpreter == "cp313" and tag.abi == "cp313" and tag.platform in PLATFORMS
                for tag in parse_wheel_filename(fname)[3]
            )
            if universal or native:
                if (
                    not url.startswith("https://files.pythonhosted.org/packages/")
                    or wheel["size"] <= 0
                ):
                    raise ValueError("lock artifact destination or size changed")
                wheels.append((not universal, wheel["size"], fname, wheel))
        if not wheels:
            raise ValueError(f"no matching locked wheel for {name}")
        native, _, filename, wheel = min(wheels)
        seen[name] = {
            "project": name,
            "version": row["version"],
            "filename": filename,
            "wheel_url": wheel["url"],
            "sha256": wheel["hash"].removeprefix("sha256:"),
            "bytes": wheel["size"],
            "native": native,
            "locked_dependencies": sorted(edge["name"] for edge in edges),
        }
        stack.extend(edge["name"] for edge in edges)
    return sorted(seen.values(), key=lambda row: row["project"])


def prepare(target):
    (row,) = json.loads(read(BASE / "index.json", INDEX_PIN))
    _, wheels = wheel_probe_assets()
    subject, truth, _, _, _ = bind(row, BASE / "transport", wheels)
    if (
        subject.task_id != CASE
        or truth.test_paths != [TEST]
        or len(truth.fail_to_pass + truth.pass_to_pass) != 174
    ):
        raise ValueError("unexpected staged unit task")
    source = archive_files(truth.source.read(), large=True)
    overlay = archive_files(truth.tests.read(), large=True)
    if set(overlay) != {TEST, "tests/fixtures/uuid/models.py"} or any(
        path in source for path in ("conftest.py", "tests/unit/conftest.py")
    ):
        raise ValueError("protected overlay or parent chain changed")
    projection, scope = local_projection(source[CONFT], overlay[TEST].decode())
    packed = pack_files(overlay | {CONFT: projection}, large=True)
    if archive_files(packed, large=True) != overlay | {CONFT: projection}:
        raise ValueError("projected archive changed protected test bytes")
    closure = wheel_closure(source["uv.lock"])
    report = {
        "schema_version": "aeep.c13.advanced-alchemy-unit-preflight.v1",
        "case": subject.task_id,
        "archive_intake_index": binding(BASE / "index.json"),
        "source_archive_sha256": truth.source.sha256,
        "test_overlay_sha256": truth.tests.sha256,
        "test_assertion_files_unchanged": {path: digest(body) for path, body in overlay.items()},
        "original_parent_configuration_sha256": digest(source[CONFT]),
        "projected_parent_configuration_sha256": digest(projection),
        "projected_protected_archive_sha256": digest(packed),
        "uv_lock_sha256": digest(source["uv.lock"]),
        "fixture_scope": scope,
        "test_identities": {
            "issue": len(truth.fail_to_pass),
            "preservation": len(truth.pass_to_pass),
        },
        "target": MODEL_ENV,
        "wheel_candidates": closure,
        "wheel_candidates_bytes": sum(row["bytes"] for row in closure),
        "static_scope": "Proposed unit-only fixture projection. Parent service plugins are omitted. Protected overlay assertions and identities remain unchanged.",
        "remaining": [
            "Review omitted plugin effects and verify actual fixture collection in containment.",
            "Verify each wheel publisher, license and runtime dependency metadata before execution.",
            "Stage a compatible native carrier for the compiled wheels and verify source import origin.",
            "Run protected reference and original-source controls before formal assignment.",
        ],
        "upstream_tests_run": 0,
        "models": 0,
        "formal_cases_adopted": 0,
        "unit_profile_only": True,
        "official_benchmark_reproduction": False,
        "comparisons_paused": True,
        "waza_excluded": True,
    }
    if target is not None:
        if target.resolve() != target or target.parent != SCOPE:
            raise ValueError("private projection must use a fresh child of the reviewed scope")
        target.mkdir(mode=0o700)
        write(target / "tests.tar.gz", packed)
        write(target / "conftest-projected.py", projection)
        write(target / "preflight.json", encode(report))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", action="store_true")
    args = parser.parse_args()
    print(json.dumps(prepare(TARGET if args.stage else None), indent=2, sort_keys=True))
