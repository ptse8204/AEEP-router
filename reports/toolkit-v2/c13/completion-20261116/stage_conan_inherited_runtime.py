"""Bind Conan's proposed runtime to retained image layers and exact artifacts."""

import argparse
import json
import subprocess
from email.parser import BytesParser
from itertools import pairwise
from pathlib import Path
from zipfile import ZipFile

from audit_conan_native_selectors import CASE, INDEX, REVISION
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from stage_repository_transport import HERE, ROOT, WORK, read

from aeep.assessment.repository_suites import archive_files

DOCKER = Path("/Applications/Docker.app/Contents/Resources/bin/docker")
SOCKET = Path.home() / ".docker/run/docker.sock"
CHAIN = (
    (
        "repository-replacement-runtime-20261022", "runtime-wheel-review.json",
        "17fee7b95a861079738b743d258b12e52a0901048e755bd2a4d291337b73e513",
        "1af99d1b3226e82f346327308d7e50006babae96bdd1ecf616d9c51a222dc6d1",
        {"requests", "urllib3", "pyyaml", "charset-normalizer", "certifi", "idna"},
    ),
    (
        "repository-test-roots-20261027", "runtime-support-review.json",
        "6354820f5e0f9664def4a4a245e3f52cbcdb9da76b3b0ee17a55b6b0a37da5dd",
        "165e2b6c14f6f65271848b605c496eeef49abae41fccea3f37d2a54bf082aa09",
        {"colorama", "jinja2", "markupsafe"},
    ),
    (
        "repository-effective-runtime-20261027", "runtime-support-review.json",
        "ae521a0607fda8fb4e82678c73749a13e901ee98d934c07d0dee5f92ac625ee8",
        "9bf1017b73525f292634fd451896f5a5a103f2ed8791669c1d746f6bca533119",
        {"python-dateutil", "six"},
    ),
)
SCANNER = HERE.parent / "scanner-runtime-20261102/context.json"
SCANNER_SHA = "67b7763da33caa19ad9b53e8d5de485444e39085aa971e2fdfa8838e27550191"
SELECTOR = HERE / "conan-native-selector-preflight-20261118.json"
DISTRO = "distro-1.9.0-py3-none-any.whl"


def wheel_metadata(path, pin, size):
    if len(read(path, pin)) != size:
        raise ValueError("wheel differs from its reviewed size")
    with ZipFile(path) as archive:
        item, = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        info = BytesParser().parsebytes(archive.read(item), headersonly=True)
    return {
        "path": str(path), "sha256": pin, "size_bytes": size,
        "project": canonicalize_name(info["Name"]), "version": info["Version"],
        "requires_python": info["Requires-Python"], "requires_dist": info.get_all("Requires-Dist", []),
    }


def image_lineage(ids):
    result = subprocess.run(
        [str(DOCKER), "-H", f"unix://{SOCKET}", "image", "inspect", *ids],
        capture_output=True, check=True, text=True, timeout=15,
    )
    images = json.loads(result.stdout)
    layers = [item["RootFS"]["Layers"] for item in images]
    if [item["Id"] for item in images] != ids or any(
        image["Os"] != "linux" or image["Architecture"] != "arm64"
        or image["Config"]["User"] != "65534:65534"
        or image["Config"].get("Volumes") or image["Config"].get("Healthcheck")
        for image in images
    ) or not all(later[:len(earlier)] == earlier for earlier, later in pairwise(layers)):
        raise ValueError("retained Linux ARM64 carrier or layer ancestry changed")
    return [dict(image=image, layers=pin) for image, pin in zip(ids, layers, strict=True)]


def declared_dependencies():
    source = WORK / "repository-expansion-acquisition"
    rows = json.loads(read(source / "index.json", INDEX))
    row, = [item for item in rows if item["input"]["task_id"] == CASE]
    if row["source_revision"] != REVISION:
        raise ValueError("source binding changed")
    source_pin = row["input"]["source_sha256"]
    archive = archive_files(read(source / "transport/public" / (source_pin + ".tar.gz"), source_pin),
                            large=True)
    runtime = archive["conans/requirements.txt"].decode().splitlines()
    developer = archive["conans/requirements_dev.txt"].decode().splitlines()
    pytest, = [line for line in developer if line.startswith("pytest>")]
    return [line for line in runtime if line.strip()] + [pytest]


def check_closure(declared, inherited, portable, target):
    inventory = {item["project"]: item for item in (*inherited, *portable)}
    if len(inventory) != len(inherited) + len(portable):
        raise ValueError("selected distributions compete for one module namespace")
    active = {}
    for owner, dependencies in [
        ("selected-conan-runtime-and-pytest", declared),
        *((name, package["requires_dist"]) for name, package in sorted(inventory.items())),
    ]:
        active[owner] = []
        for raw in dependencies:
            need = Requirement(raw)
            if need.marker and not need.marker.evaluate({**target, "extra": ""}):
                continue
            chosen = inventory.get(canonicalize_name(need.name))
            if (chosen is None or need.url or need.extras
                    or not need.specifier.contains(chosen["version"], prereleases=True)):
                raise ValueError(f"candidate closure has an unresolved dependency: {owner}: {need}")
            active[owner].append(f"{chosen['project']}=={chosen['version']}")
    for package in inventory.values():
        if not SpecifierSet(package["requires_python"] or "").contains(target["python_full_version"]):
            raise ValueError("locked distribution does not admit the target Python version")
    return active


def audit():
    inherited, builds, pins = [], [], {}
    target = None
    for prefix, manifest, build_hash, manifest_hash, required in CHAIN:
        folder = HERE.parent / prefix
        build_file, lookup = folder / "build-result.json", folder / manifest
        build = json.loads(read(build_file, build_hash))
        catalog = json.loads(read(lookup, manifest_hash))
        if not build["passed"] or not build["parent_layers_verified"] or not build["inherited_config_verified"]:
            raise ValueError("carrier build proof is incomplete")
        builds.append(build["image_id"])
        pins.update({str(build_file.relative_to(ROOT)): build_hash, str(lookup.relative_to(ROOT)): manifest_hash})
        if target is None:
            target = catalog["target_marker_environment"]
        peers = [item for item in catalog["pins"] if canonicalize_name(item["project"]) in required]
        if {canonicalize_name(item["project"]) for item in peers} != required:
            raise ValueError("retained dependency inventory changed")
        for pin in peers:
            inherited.append(wheel_metadata(ROOT / pin["private_cache"], pin["sha256"], pin["size_bytes"]))

    current = json.loads(SELECTOR.read_bytes())["runtime_preparation"]["declared_carrier_payload_rehearsal"]
    source = json.loads(read(ROOT / current["path"], current["sha256"]))
    portable = [wheel_metadata(Path(item["path"]), item["sha256"], item["size_bytes"])
                for item in source["bound_candidate_wheels"]]
    model = json.loads(read(SCANNER, SCANNER_SHA))
    path = ROOT / model["context"] / "wheels" / DISTRO
    portable.append(wheel_metadata(path, model["assets"]["wheels/" + DISTRO], path.stat().st_size))
    pins[str(SCANNER.relative_to(ROOT))] = SCANNER_SHA
    pins[current["path"]] = current["sha256"]
    edges = check_closure(declared_dependencies(), inherited, portable, target)
    return {
        "schema_version": "aeep.c13.conan-proposed-inherited-runtime.v1",
        "source_revision": REVISION,
        "build_and_wheel_pins": pins,
        "image_lineage": image_lineage(builds), "carrier": builds[-1],
        "carrier_python_marker_environment": target,
        "image_dependencies": inherited, "protected_zip_imports": portable,
        "active_dependencies": edges,
        "static_dependency_closure": True, "contained_imports_verified": False,
        "native_collection_verified": False, "upstream_grader_executions": 0,
        "downloads": 0, "installs": 0, "image_changes": 0, "model_turns": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(audit(), indent=2, sort_keys=True))
