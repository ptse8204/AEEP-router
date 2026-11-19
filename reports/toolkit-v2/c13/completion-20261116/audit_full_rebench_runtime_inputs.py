"""Audit published runtime requirements against retained wheel bytes."""

import json
import shutil
import tomllib
from pathlib import Path

from acquire_full_rebench_leads import RESERVE, TARGET, ref
from packaging.markers import Marker
from packaging.requirements import Requirement
from packaging.tags import compatible_tags, cpython_tags
from packaging.utils import canonicalize_name, parse_wheel_filename
from stage_full_rebench_reference_assets import EOS, LOCIFY, OUTPUT
from stage_repository_transport import ROOT, digest, encode, read, write

from aeep.assessment.repository_suites import archive_files

PLATFORMS = [f"manylinux_2_{minor}_aarch64" for minor in range(36, 16, -1)]
PLATFORMS += ["manylinux2014_aarch64"]
TAGS = set(cpython_tags((3, 12), platforms=PLATFORMS)) | set(
    compatible_tags((3, 12), interpreter="cp312", platforms=PLATFORMS)
)
MARKERS = {
    "implementation_name": "cpython",
    "implementation_version": "3.12.12",
    "os_name": "posix",
    "platform_machine": "aarch64",
    "platform_python_implementation": "CPython",
    "platform_release": "",
    "platform_system": "Linux",
    "platform_version": "",
    "python_full_version": "3.12.12",
    "python_version": "3.12",
    "sys_platform": "linux",
    "extra": "",
}


def pure_linux_wheel(path):
    if not path.name.endswith(".whl"):
        return None
    name, version, _, tags = parse_wheel_filename(path.name)
    return (name, str(version)) if tags & TAGS else None


def cached_wheels():
    wheels = {}
    for path in (ROOT / ".aeep").rglob("*.whl"):
        if not path.is_file() or path.is_symlink() or path.resolve() != path:
            continue
        try:
            key = pure_linux_wheel(path)
        except ValueError:
            continue
        if key is not None:
            wheels.setdefault(key, {}).setdefault(path.name, []).append(path)
    return wheels


def locify_audit(files, cache):
    project = tomllib.loads(files["pyproject.toml"].decode())["tool"]["poetry"]
    lock = tomllib.loads(files["poetry.lock"].decode())
    packages = {canonicalize_name(pkg["name"]): pkg for pkg in lock["package"]}
    if len(packages) != len(lock["package"]):
        raise ValueError("lock requires explicit platform profile for duplicate packages")
    roots = set(project["dependencies"]) - {"python"}
    roots.update(project["group"]["tests"]["dependencies"])
    pending = [canonicalize_name(name) for name in roots]
    results = {}
    while pending:
        name = pending.pop()
        if name in results:
            continue
        pkg = packages[name]
        for dependency, alternatives in pkg.get("dependencies", {}).items():
            if not isinstance(alternatives, list):
                alternatives = [alternatives]
            for item in alternatives:
                if isinstance(item, str) or (
                    not item.get("optional", False)
                    and (
                        not item.get("markers")
                        or Marker(item["markers"]).evaluate(MARKERS)
                    )
                ):
                    pending.append(canonicalize_name(dependency))
                    break
        choices = {}
        hits = []
        for f in pkg["files"]:
            file = Path(f["file"])
            if pure_linux_wheel(file) is None:
                continue
            expected = f["hash"].removeprefix("sha256:")
            choices[file.name] = expected
            for path in cache.get((name, pkg["version"]), {}).get(file.name, []):
                if digest(path.read_bytes()) == expected:
                    hits.append({"path": str(path.relative_to(ROOT)), "sha256": expected})
                    break
        results[name] = {
            "version": pkg["version"],
            "locked_linux_arm64_wheels": choices,
            "verified_retained_wheels": hits,
        }
    return {
        "publisher_lock_sha256": digest(files["poetry.lock"]),
        "count": len(results),
        "exact_retained_count": sum(bool(row["verified_retained_wheels"]) for row in results.values()),
        "lock_without_compatible_wheel": sorted(
            name for name, row in results.items() if not row["locked_linux_arm64_wheels"]
        ),
        "host_resources_needed": ["A compatible retained Linux Git closure", "Offline tokenizer vocabulary"],
        "local_only_policy": "Upstream tests create fixture Git repositories and count tokens locally.",
        "packages": dict(sorted(results.items())),
    }


def eos_audit(files, cache):
    requirements = [Requirement(line) for line in files["requirements.txt"].decode().splitlines()]
    requirements += [
        Requirement(line)
        for line in files["requirements-dev.txt"].decode().splitlines()
        if line.startswith(("pytest==", "pytest-xprocess=="))
    ]
    exact = {}
    for req in requirements:
        (version,) = tuple(req.specifier)
        if version.operator != "==":
            raise ValueError("expected a pinned requirement")
        name = canonicalize_name(req.name)
        exact[name] = {
            "version": version.version,
            "extras": sorted(req.extras),
            "retained_exact_filenames_pending_hash_audit": sorted(
                cache.get((name, version.version), {})
            ),
        }
    return {
        "count": len(exact),
        "exact_filename_count": sum(
            bool(row["retained_exact_filenames_pending_hash_audit"]) for row in exact.values()
        ),
        "dependencies": dict(sorted(exact.items())),
        "transitive_lock_available": False,
        "declared_test_config": "Root conftest requires pendulum and pytest-xprocess. Local server fixtures need review under network isolation.",
        "runtime_effect_of_omitting_dotenv_verified": False,
    }


def main():
    if shutil.disk_usage(TARGET).free < RESERVE:
        raise RuntimeError("runtime input audit needs the 52 GiB floor")
    staging = OUTPUT / "result.json"
    prepared = {row["case"]: row for row in json.loads(staging.read_bytes())["cases"]}
    cache = cached_wheels()
    results = {}
    for case, audit in ((LOCIFY, locify_audit), (EOS, eos_audit)):
        asset = prepared[case]["assets"]["untouched-source"]
        files = archive_files(read(ROOT / asset["path"], asset["sha256"]), large=True)
        results[case] = audit(files, cache)
    write(
        OUTPUT / "runtime-input-audit.json",
        encode(
            {
                "staging": ref(staging),
                "target": "CPython 3.12 Linux ARM64 glibc <= 2.36",
                "audit_driver": ref(Path(__file__).resolve()),
                "runtime_ready": False,
                "cases": results,
            }
        ),
    )


if __name__ == "__main__":
    main()
