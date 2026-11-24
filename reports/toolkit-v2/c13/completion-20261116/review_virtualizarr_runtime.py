"""Bind a native, offline dependency plan for the VirtualiZarr protected case."""

import argparse
import ast
import json
import tomllib
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import check_retained_carrier_batch as batch
from audit_staged_repository_graders import bind, wheel_probe_assets
from check_expansion_contracts import NoRedirect
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from stage_repository_transport import ROOT, digest, read, write

from aeep.assessment.repository_suites import archive_files
from aeep_toolkit.install_runtime import file_digest

BASE = ROOT / ".aeep/c13-cohort-runtime-20261124"
INTAKE = BASE / "repository-intake-post-inventory-20261124"
INDEX = "c5040e1831cfbbe888824bdce76f5839fe4afdbf97971c865b248f4d7bef5d08"
PROFILE = {
    "xarray": "2024.11.0",
    "numpy": "2.2.6",
    "pandas": "2.2.3",
    "python-dateutil": "2.9.0.post0",
    "pytz": "2025.2",
    "tzdata": "2025.2",
    "six": "1.17.0",
    "packaging": "25.0",
    "universal-pathlib": "0.2.6",
    "fsspec": "2026.3.0",
    "kerchunk": "0.2.8",
    "zarr": "3.0.8",
    "numcodecs": "0.16.3",
    "crc32c": "2.7",
    "donfig": "0.8.1.post1",
    "pyyaml": "6.0.3",
    "typing-extensions": "4.15.0",
    "ujson": "5.10.0",
    "h5py": "3.12.1",
    "hdf5plugin": "5.0.0",
    "imagecodecs": "2024.12.30",
    "imagecodecs-numcodecs": "2024.6.1",
    "netcdf4": "1.7.2",
    "cftime": "1.6.4.post1",
    "certifi": "2026.4.22",
}
CACHE = (
    BASE / "c13-nested-pandas-302-20261124/wheels",
    ROOT / ".aeep/scanner-runtime-context-20261102/wheels",
    ROOT / ".aeep/repository-replacement-runtime-20261022-wheels",
)
HDF_WHEEL = "hdf5plugin-5.0.0-py3-none-manylinux_2_17_aarch64.manylinux2014_aarch64.whl"
WORK = BASE / "c13-virtualizarr-395-20261124"
ENVIRONMENT = {
    "python_version": "3.13",
    "python_full_version": "3.13.15",
    "platform_machine": "aarch64",
    "sys_platform": "linux",
    "platform_system": "Linux",
    "os_name": "posix",
}


def test_marks(nodes, filename, parents=(), inherited=()):
    for node in nodes:
        if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        names = (*parents, node.name)
        marks = inherited + tuple(ast.unparse(d).split("(")[0] for d in node.decorator_list)
        if isinstance(node, ast.ClassDef):
            yield from test_marks(node.body, filename, names, marks)
        elif node.name.startswith("test"):
            yield "::".join((filename, *names)), marks


def find_subject():
    (row,) = json.loads(read(INTAKE / "index.json", INDEX))
    _, wheels = wheel_probe_assets()
    task, truth, _, _, metadata = bind(row, INTAKE / "transport", wheels)
    source = archive_files(truth.source.read(), large=True)
    files = source | archive_files(truth.tests.read(), large=True)
    required = truth.fail_to_pass + truth.pass_to_pass
    base_names = {test.split("[", 1)[0] for test in required}
    marks = {
        name: values
        for filename in truth.test_paths
        for name, values in test_marks(ast.parse(files[filename]).body, filename)
    }
    remote = {
        name
        for name, values in marks.items()
        if "requires_network" in values or "pytest.mark.network" in values
    }
    if (
        task.task_id != "zarr-developers__VirtualiZarr-395"
        or metadata["names_not_declared_in_selected_module"]
        or len(required) != 78
        or len(truth.fail_to_pass) != 6
        or not base_names <= marks.keys()
        or base_names & remote
        or not remote
        or b'not item.config.getoption("--run-network-tests")' not in files["conftest.py"]
    ):
        raise ValueError("required identifiers or published network skip policy changed")
    config = tomllib.loads(source["pyproject.toml"].decode())["project"]
    requirements = config["dependencies"] + config["optional-dependencies"]["hdf_reader"]
    return task, truth, required, marks, sorted(remote), requirements


def wheel_pin(project_version):
    name, version = project_version
    metadata_url = f"https://pypi.org/pypi/{name}/{version}/json"
    with urllib.request.build_opener(NoRedirect()).open(metadata_url, timeout=15) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError(f"publisher metadata exceeds bounds for {name}")
    data = json.loads(raw)
    python_range = data["info"]["requires_python"]
    if python_range and ENVIRONMENT["python_full_version"] not in SpecifierSet(python_range):
        raise ValueError(f"publisher wheel does not support the retained Python for {name}")
    candidates = [
        (100 if row["filename"] == HDF_WHEEL else batch.wheel_rank(row["filename"]), row)
        for row in data["urls"]
        if row["packagetype"] == "bdist_wheel" and not row["yanked"]
    ]
    candidates = sorted((x for x in candidates if x[0]), key=lambda pair: pair[0], reverse=True)
    if not candidates or (len(candidates) > 1 and candidates[0][0] == candidates[1][0]):
        raise ValueError(f"platform wheel missing or ambiguous for {name} {version}")
    _, row = candidates[0]
    sha, filename = row["digests"]["sha256"], row["filename"]
    cache = next(
        (
            (directory / filename).relative_to(ROOT).as_posix()
            for directory in CACHE
            if (directory / filename).is_file()
            and digest((directory / filename).read_bytes()) == sha
        ),
        None,
    )
    return name, {
        "project": name,
        "version": version,
        "filename": filename,
        "sha256": sha,
        "bytes": row["size"],
        "url": row["url"],
        "publisher_metadata_sha256": digest(raw),
        "publisher_metadata_url": metadata_url,
        "cache": cache,
        "requires_dist": data["info"]["requires_dist"] or [],
        "requires_python": data["info"]["requires_python"],
    }


def dependency_edges(pins, project):
    checks = {}
    all_requirements = {"VirtualiZarr": project} | {
        name: pin["requires_dist"] for name, pin in pins.items()
    }
    for parent, requirements in all_requirements.items():
        active = []
        extras = ("", "crc32c") if parent == "numcodecs" else ("",)
        for text in requirements:
            req = Requirement(text)
            if req.marker and not any(
                req.marker.evaluate(ENVIRONMENT | {"extra": item}) for item in extras
            ):
                continue
            name = req.name.lower().replace("_", "-")
            if (
                req.url
                or name not in pins
                or pins[name]["version"] not in req.specifier
                or (req.extras and (name, req.extras) != ("numcodecs", {"crc32c"}))
            ):
                raise ValueError(f"unresolved publisher requirement for {parent}: {text}")
            active.append(str(req))
        checks[parent] = active
    return checks


def review():
    task, truth, required, marks, remote, requirements = find_subject()
    with ThreadPoolExecutor(max_workers=4) as executor:
        pins = dict(executor.map(wheel_pin, PROFILE.items()))
    edges = dependency_edges(pins, requirements)
    downloads = [pin for pin in pins.values() if not pin["cache"]]
    return {
        "schema_version": "aeep.c13.virtualizarr-native-runtime-review.v1",
        "case": task.task_id,
        "source_index_sha256": INDEX,
        "protected_tests_sha256": truth.tests.sha256,
        "required_published_assertions": len(required),
        "required_network_marked_assertions": 0,
        "publisher_remote_tests_skipped_by_default": remote,
        "required_hdf_codec_assertions": sum(
            "requires_imagecodecs" in marks[test.split("[", 1)[0]] for test in required
        ),
        "runtime": ENVIRONMENT,
        "wheel_pins": pins,
        "publisher_requirement_edges": edges,
        "maximum_wheel_downloads": len(downloads),
        "maximum_wheel_response_bytes": sum(pin["bytes"] for pin in downloads),
        "wheel_license_and_native_import_audit_pending": True,
        "acquisition_started": False,
        "protected_execution_started": False,
        "models": 0,
        "cash_usd": 0,
        "retries": 0,
    }


def acquire(path, exact):
    """Retain the reviewed publisher wheels without loading any package."""
    record = json.loads(read(path, exact))
    task, truth, required, _, _, project = find_subject()
    pins = record["wheel_pins"]
    if (
        record["case"] != task.task_id
        or record["source_index_sha256"] != INDEX
        or record["protected_tests_sha256"] != truth.tests.sha256
        or record["required_published_assertions"] != len(required)
        or {name: pin["version"] for name, pin in pins.items()} != PROFILE
        or record["publisher_requirement_edges"] != dependency_edges(pins, project)
        or record["acquisition_started"]
        or record["protected_execution_started"]
        or any(record[key] for key in ("models", "cash_usd", "retries"))
    ):
        raise ValueError("the planned protected source or publisher scope has changed")
    downloads = [pin for pin in pins.values() if not pin["cache"]]
    size = sum(pin["bytes"] for pin in downloads)
    if (len(downloads), size) != (
        record["maximum_wheel_downloads"],
        record["maximum_wheel_response_bytes"],
    ):
        raise ValueError("wheel transfer bounds do not match the reviewed manifest")
    WORK.mkdir(mode=0o700)
    batch.WORK = WORK
    batch.assets.WHEELS = WORK / "wheels"
    batch.MAX_FETCH = size
    transfer = {
        "driver_sha256": file_digest(Path(batch.__file__)),
        "wrapper_sha256": file_digest(Path(__file__)),
        "runtime_review_sha256": exact,
        "maximum_downloads": len(downloads),
        "maximum_response_bytes": size,
        "files": {
            pin["filename"]: {
                "name": name,
                "version": pin["version"],
                "filename": pin["filename"],
                "cache": pin["cache"],
                "url": pin["url"],
                "size": pin["bytes"],
                "sha256": pin["sha256"],
            }
            for name, pin in pins.items()
        },
        "model_turns": 0,
        "cash_usd": 0,
        "retries": 0,
        "authority": "First bounded public dependency intake under the C13 delegation.",
    }
    encoded = (json.dumps(transfer, indent=2, sort_keys=True) + "\n").encode()
    write(WORK / "acquisition-review.json", encoded)
    batch.acquire(transfer)
    completed = {"review_sha256": digest(encoded), "completed": True}
    write(WORK / "acquisition-result.json", (json.dumps(completed) + "\n").encode())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("--acquire")
    args = parser.parse_args()
    if args.acquire:
        acquire(args.out.resolve(), args.acquire)
    else:
        record = (json.dumps(review(), indent=2, sort_keys=True) + "\n").encode()
        write(args.out.resolve(), record)
        print(digest(record))
