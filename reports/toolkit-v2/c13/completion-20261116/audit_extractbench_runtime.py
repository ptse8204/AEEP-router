"""Audit the pinned Harbor grader's imports without running upstream Python."""

import ast
import hashlib
import json
import sys
import tarfile
import tomllib
from collections import defaultdict, deque
from importlib.util import resolve_name
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from audit_extractbench_audent import (
    LOCK_PIN,
    ROOT,
    SCORER,
    cached_wheels,
    declared_wheels,
    required_packages,
    task_assets,
)
from stage_repository_transport import digest, read

TREE_PIN = "d84d3876be88bcaf21485c9a3678dad1732ea54c7f68f4d4694044a82ea93149"
SOURCES = ROOT / "scorer-sources"
PROVIDER_ROOT = "extract_bench.inference.providers."
DISTRIBUTIONS = {"bs4": "beautifulsoup4", "dateutil": "python-dateutil", "pydantic_core": "pydantic-core"}
DISTRIBUTION_SOURCE = "https://pypi.org/project/fuzzysearch/0.8.1/"


def module_name(path):
    return path.removesuffix(".py").removesuffix("/__init__").replace("/", ".")


def immediate_imports(node):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        yield node
    if isinstance(node, ast.If) and ast.unparse(node.test) in {"TYPE_CHECKING", "typing.TYPE_CHECKING"}:
        children = node.orelse
    else:
        children = ast.iter_child_nodes(node)
    for child in children:
        yield from immediate_imports(child)


def imports(tree, package, module_paths):
    for node in immediate_imports(tree):
        if isinstance(node, ast.Import):
            yield from ((item.name, node.lineno) for item in node.names)
            continue
        origin = node.module or ""
        if node.level:
            origin = resolve_name("." * node.level + origin, package)
        yield origin, node.lineno
        for item in node.names:
            submodule = f"{origin}.{item.name}"
            if submodule in module_paths:
                yield submodule, node.lineno


def pinned_git_blob(path, entry):
    source = (SOURCES / path).read_bytes()
    header = f"blob {len(source)}\0".encode()
    if len(source) != entry["size"] or hashlib.sha1(header + source, usedforsecurity=False).hexdigest() != entry["sha"]:
        raise ValueError(f"upstream Git blob changed: {path}")
    return source


def trace(verifier, git, archive):
    module_paths = {module_name(path.removeprefix("src/")): path for path in git if path.endswith(".py")}
    members = archive.namelist()
    if len(set(members)) != len(members):
        raise ValueError("ParseBench wheel has duplicate members")
    module_paths.update({module_name(path): path for path in members if path.startswith("parse_bench/") and path.endswith(".py")})
    pending = deque(["verifier"])
    observed, providers = {}, {}
    dependencies = defaultdict(list)
    while pending:
        module = pending.popleft()
        if module in observed:
            continue
        if module == "verifier":
            path, data = verifier.name, verifier.read_bytes()
        else:
            path = module_paths[module]
            data = pinned_git_blob(path, git[path]) if path in git else archive.read(path)
        parsed = ast.parse(data, filename=path)
        observed[module] = {"path": path, "bytes": len(data), "sha256": digest(data)}
        package = module if path.endswith("/__init__.py") else module.rpartition(".")[0]
        for origin, line in imports(parsed, package, module_paths):
            base = origin.split(".", 1)[0]
            if base in {"extract_bench", "parse_bench"}:
                if origin not in module_paths:
                    raise ValueError(f"missing upstream module: {origin}")
                parts = origin.split(".")
                parents = (".".join(parts[:index]) for index in range(1, len(parts) + 1))
                pending.extend(parent for parent in parents if parent in module_paths)
            elif base not in sys.stdlib_module_names:
                dependencies[base].append({"module": module, "line": line, "import": origin})
        if module in {PROVIDER_ROOT + suffix for suffix in ("extract", "layoutdet", "parse")}:
            declarations = [
                node for node in parsed.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "_PROVIDER_MODULES" for target in node.targets)
            ]
            if len(declarations) != 1:
                raise ValueError("expected one literal provider registry")
            names = ast.literal_eval(declarations[0].value)
            if len(set(names)) != len(names) or any(
                f"{module}.{name}" not in module_paths for name in names
            ):
                raise ValueError("the provider registry differs from its pinned source tree")
            providers[module] = {"module_count": len(names), "source_line": declarations[0].lineno}
    return observed, dict(dependencies), providers


def source_fallback(package):
    artifact = package["sdist"]
    path = ROOT / Path(artifact["url"]).name
    data = read(path, artifact["hash"].removeprefix("sha256:"))
    if len(data) != artifact["size"]:
        raise ValueError("fuzzysearch source distribution size differs")
    with tarfile.open(fileobj=BytesIO(data), mode="r:gz") as archive:
        prefix = f"fuzzysearch-{package['version']}/"
        files = {}
        seen = set()
        for member in archive.getmembers():
            if (
                member.name in seen
                or Path(member.name).is_absolute()
                or ".." in Path(member.name).parts
                or not (member.isdir() or member.isfile())
                or not (member.name.startswith(prefix) or (member.name == prefix[:-1] and member.isdir()))
            ):
                raise ValueError("unexpected fuzzysearch source archive member")
            seen.add(member.name)
            if member.isfile() and (
                (member.name.startswith(prefix + "src/fuzzysearch/") and member.name.endswith(".py"))
                or member.name in {prefix + "setup.py", prefix + "LICENSE"}
            ):
                with archive.extractfile(member) as stream:
                    files[member.name] = digest(stream.read())
    return {
        "artifact": artifact,
        "inspected_files": files,
        "publisher_fallback_documentation": DISTRIBUTION_SOURCE,
        "integration_status": "Upstream Python fallback is present. Contained startup and behavior are unverified.",
    }


def audit():
    _, assets = task_assets()
    tree = json.loads(read(ROOT / "scorer-git-tree.json", TREE_PIN))
    if tree["sha"] != SCORER or tree["truncated"]:
        raise ValueError("incomplete or different scorer Git tree")
    git = {row["path"]: row for row in tree["tree"] if row["type"] == "blob" and row["path"].startswith("src/extract_bench/")}
    license_entry = next(row for row in tree["tree"] if row["path"] == "LICENSE")
    lock = tomllib.loads(read(ROOT / "scorer-uv.lock", LOCK_PIN).decode())
    packages = required_packages(lock)
    wheels, unavailable = declared_wheels(packages)
    parsed_wheel = wheels["parse-bench"]
    wheel = ROOT / parsed_wheel["filename"]
    parsed_bytes = read(wheel, parsed_wheel["hash"].removeprefix("sha256:"))
    with ZipFile(BytesIO(parsed_bytes)) as archive:
        license_path = f"parse_bench-{parsed_wheel['version']}.dist-info/licenses/LICENSE"
        license_digest = digest(archive.read(license_path))
        modules, dependencies, providers = trace(assets["tests/verifier.py"], git, archive)
    # In the normal package path this module loads by relative import. The bare
    # name appears in the upstream document sandbox's ImportError fallback.
    if dependencies.pop("table_parser", []) != [{
        "module": PROVIDER_ROOT + "extract.table_codegen.document", "line": 38, "import": "table_parser",
    }]:
        raise ValueError("unexpected use of a bare table_parser import")
    needed = {DISTRIBUTIONS.get(name, name): sites for name, sites in dependencies.items()}
    if not (set(needed) | {"parse-bench"}) <= set(wheels):
        raise ValueError("an immediate dependency has no corresponding locked wheel")
    available = cached_wheels(wheels)
    remaining = {name: entry for name, entry in wheels.items() if entry["filename"] not in available}
    return {
        "schema_version": "aeep.c13.extractbench-runtime-audit.v1",
        "scorer_revision": SCORER,
        "source_tree_sha256": TREE_PIN,
        "source_license_sha256": digest(pinned_git_blob("LICENSE", license_entry)),
        "lock_sha256": LOCK_PIN,
        "parse_bench_wheel": {**parsed_wheel, "license_sha256": license_digest},
        "immediate_imports": needed,
        "inspected_module_count": len(modules),
        "inspected_module_bytes": sum(record["bytes"] for record in modules.values()),
        "inspected_module_manifest_sha256": digest(json.dumps(modules, sort_keys=True).encode()),
        "dynamic_provider_initializers": providers,
        "runtime_projection": {
            "available_exact_wheels": len(available),
            "remaining_wheel_count": len(remaining),
            "remaining_wheel_bytes": sum(item["size"] for item in remaining.values()),
            "numpy_and_scipy_wheel_bytes": sum(wheels[name]["size"] for name in ("numpy", "scipy")),
            "missing_compatible_wheels": unavailable,
            "missing_wheel_pins_sha256": digest(json.dumps(remaining, sort_keys=True).encode()),
        },
        "fuzzysearch_source_fallback": source_fallback(next(row for row in packages if row["name"] == "fuzzysearch")),
        "scope": "Static module imports and bounded wheel metadata. Provider registration loads dynamically. Exact runtime, native grading and task controls remain unverified.",
        "models": 0,
        "native_grades": 0,
        "formal_cases_adopted": 0,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
