"""Rebind two retained repairs and read their exact Linux wheel requirements."""

import argparse
import asyncio
import json
import re
import tomllib
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

import audit_two_cohort_source_capacity as capacity
from audit_full_rebench_runtime_inputs import MARKERS, PLATFORMS
from audit_staged_repository_graders import audit_row, bind, wheel_probe_assets
from packaging.markers import Marker
from packaging.requirements import Requirement
from packaging.tags import compatible_tags, cpython_tags
from packaging.utils import canonicalize_name, parse_wheel_filename
from rebind_cached_repository_sources import inventory
from stage_repository_transport import HERE, ROOT, digest, encode, read, write

from aeep.assessment.repository_suites import archive_files

RECEIPT = (
    ROOT / ".aeep/c13-cohort-runtime-20261124/retained-multifile-publisher-readback-20261124.json"
)
RECEIPT_SHA = "34088fe2814433125ee3964e3333079a6e540d2b05998c371f5b0294046b1981"
ENV = MARKERS | {
    "implementation_version": "3.13.15",
    "python_full_version": "3.13.15",
    "python_version": "3.13",
}
TAGS = set(cpython_tags((3, 13), platforms=PLATFORMS)) | set(
    compatible_tags((3, 13), interpreter="cp313", platforms=PLATFORMS)
)
TEST_GROUPS = {
    "copier-org__copier-2646": (
        "dev",
        {"pexpect", "pytest", "pytest-cov", "pytest-gitconfig", "pytest-xdist"},
    ),
    "pyinfra-dev__pyinfra-1630": (
        "test",
        {"click", "coverage", "pytest", "pytest-cov", "pytest-testinfra", "pyyaml"},
    ),
}


def available_wheels():
    candidates = defaultdict(list)
    for path in (ROOT / ".aeep").rglob("*.whl"):
        if path.is_file() and not path.is_symlink() and path.resolve() == path:
            candidates[path.name].append(path)
    return candidates


def lock_projection(configuration, lock_bytes, case, cache):
    lock = tomllib.loads(lock_bytes.decode())
    if sum(Marker(mark).evaluate(ENV) for mark in lock["resolution-markers"]) != 1:
        raise ValueError("Linux ARM64 Python 3.13 must select exactly one lock resolution")
    group, test_names = TEST_GROUPS[case]
    declared = [
        req
        for req in map(Requirement, configuration["dependency-groups"][group])
        if canonicalize_name(req.name) in test_names
    ]
    if {canonicalize_name(req.name) for req in declared} != test_names:
        raise ValueError("required test package is absent from the publisher group")
    packages = defaultdict(list)
    for row in lock["package"]:
        marks = row.get("resolution-markers", ())
        if not marks or any(Marker(mark).evaluate(ENV) for mark in marks):
            packages[row["name"]].append(row)

    queue = []
    for req in map(Requirement, configuration["project"]["dependencies"]):
        if req.marker is None or req.marker.evaluate(ENV):
            queue.append(req)
    queue.extend(declared)
    selected = {}
    used_extras = defaultdict(set)
    while queue:
        requirement = queue.pop()
        name = canonicalize_name(requirement.name)
        (package,) = [
            row
            for row in packages[name]
            if requirement.specifier.contains(row["version"], prereleases=True)
        ]
        if package["source"] != {"registry": "https://pypi.org/simple"}:
            raise ValueError("the wheel projection accepts publisher-pinned PyPI sources only")
        extras = package.get("optional-dependencies", {})
        if not requirement.extras <= extras.keys():
            raise ValueError("requested extra is absent from the publisher lock")
        new_extras = requirement.extras - used_extras[name]
        edges = [edge for extra in sorted(new_extras) for edge in extras[extra]]
        used_extras[name].update(new_extras)
        if name in selected:
            if selected[name] != package:
                raise ValueError("dependency edges selected two versions of one package")
        else:
            selected[name] = package
            edges.extend(package.get("dependencies", ()))
        for dependency in edges:
            if dependency.get("marker") and not Marker(dependency["marker"]).evaluate(ENV):
                continue
            edge = dependency["name"]
            if dependency.get("extra"):
                edge += "[" + ",".join(dependency["extra"]) + "]"
            if "version" in dependency:
                edge += "==" + dependency["version"]
            queue.append(Requirement(edge))

    rows = {}
    for name, package in sorted(selected.items()):
        choices = []
        for artifact in package.get("wheels", ()):
            source = urlsplit(artifact["url"])
            file = source.path.rsplit("/", 1)[-1]
            if not file.endswith(".whl"):
                continue
            wheel_name, version, _, tags = parse_wheel_filename(file)
            sha = artifact["hash"]
            if (
                source.scheme != "https"
                or source.netloc != "files.pythonhosted.org"
                or source.query
                or source.fragment
                or wheel_name != name
                or str(version) != package["version"]
                or re.fullmatch(r"sha256:[a-f0-9]{64}", sha) is None
                or type(artifact["size"]) is not int
                or artifact["size"] <= 0
            ):
                raise ValueError("locked wheel has an unexpected source, package or digest")
            if tags & TAGS:
                choices.append(
                    {
                        "filename": file,
                        "url": artifact["url"],
                        "sha256": sha.removeprefix("sha256:"),
                        "bytes": artifact["size"],
                    }
                )
        choices.sort(key=lambda item: (item["bytes"], item["filename"]))
        hit = next(
            (
                (choice, path)
                for choice in choices
                for path in sorted(cache[choice["filename"]])
                if path.stat().st_size == choice["bytes"]
                and digest(path.read_bytes()) == choice["sha256"]
            ),
            None,
        )
        rows[name] = {
            "version": package["version"],
            "wheel": (hit[0] if hit else choices[0]) if choices else None,
            "verified_local_wheel": str(hit[1].relative_to(ROOT)) if hit else None,
        }
    return rows


async def audit():
    receipt = json.loads(read(RECEIPT, RECEIPT_SHA))
    old = HERE / "supplemental-archive-recovery-result.json"
    historical = json.loads(read(old, receipt["prior_report_sha256"]))
    evidence = {row["case"]: row for row in receipt["cases"]}
    ref = historical["verification"]["private_stage_index"]
    if receipt["private_stage_index"] != ref or evidence.keys() != TEST_GROUPS.keys():
        raise ValueError("publisher receipts differ from the staged case identities")
    cache = available_wheels()
    _, wheels = wheel_probe_assets()
    root = (ROOT / ref["path"]).parent
    verified, staged = capacity.source_pools()
    exposed = {capacity.lineage(name) for name in capacity.previous_repositories()[2]}
    cases = []
    for row in capacity.referenced(ref):
        case = row["input"]["task_id"]
        current = evidence[case]
        original = next(item for item in historical["findings"] if item["case"] == case)
        origin = capacity.lineage(row["source_repository"]), row["source_revision"]
        tree, notices, entries, sha = inventory(ROOT / original["copies"][0]["path"], origin[1])
        if (
            current["status"] != "matched_publisher_tree"
            or current["publisher"]["published_tree"] != tree
            or current["local_tree"] != tree
            or current["repository"] != origin[0]
            or current["revision"] != origin[1]
            or current["archive_sha256"] != sha
            or current["license_notices"] != notices
            or current["entries"] != entries
            or origin in staged
            or origin[0] in exposed
            or row["input"]["family"] != "multi-file-repair"
        ):
            raise ValueError("retained origin or publisher binding changed")
        transport = await audit_row(row, root, wheels)
        if transport != original["callback_replay"]:
            raise ValueError("publisher tree binding must preserve both protected transports")
        _, truth, _, _, _ = bind(row, root, wheels)
        source = archive_files(truth.source.read(), large=True)
        config = tomllib.loads(source["pyproject.toml"].decode())
        kits = lock_projection(config, source["uv.lock"], case, cache)
        cases.append(
            current
            | {
                "transport": transport,
                "project_lock_sha256": digest(source["uv.lock"]),
                "packages": kits,
                "pinned_packages": len(kits),
                "verified_cached_packages": sum(
                    bool(r["verified_local_wheel"]) for r in kits.values()
                ),
                "packages_without_compatible_wheel": [
                    name for name, r in kits.items() if not r["wheel"]
                ],
                "missing_wheel_bytes": sum(
                    r["wheel"]["bytes"]
                    for r in kits.values()
                    if r["wheel"] and not r["verified_local_wheel"]
                ),
                "runtime_verified": False,
            }
        )
        staged[origin] = {"multi-file-repair"}

    leads, _ = capacity.lead_pools(staged, exposed, capacity.attempted_origins())
    return {
        "schema_version": "aeep.c13.retained-multifile-publisher-and-runtime.v1",
        "publisher_readback": {"path": str(RECEIPT.relative_to(ROOT)), "sha256": RECEIPT_SHA},
        "cases": cases,
        "conditional_capacity_without_supplementary_metadata": capacity.feasible_witness(
            verified, staged, leads, {}
        ),
        "archive_downloads": 0,
        "upstream_tests": 0,
        "formal_assignments": 0,
        "model_turns": 0,
        "cash_usd": 0,
        "comparisons_paused": True,
        "waza_excluded": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    print(write(parser.parse_args().output, encode(asyncio.run(audit()))))
