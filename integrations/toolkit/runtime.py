"""Read the selected runtime without importing it or executing its startup files."""

from __future__ import annotations

import hashlib
import re
from email.parser import BytesParser
from itertools import islice
from pathlib import Path

from aeep_toolkit.cli import read_bytes


def normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def inspect_runtime(runtime: Path, stack: dict, packages: list[dict]) -> dict:
    runtime = runtime.absolute()
    if runtime.resolve() != runtime or not runtime.is_dir():
        raise ValueError("Runtime must be an existing canonical directory")
    configuration = read_bytes(runtime / "pyvenv.cfg").decode("utf-8")
    settings = dict(line.split("=", 1) for line in configuration.splitlines() if "=" in line)
    settings = {key.strip(): value.strip() for key, value in settings.items()}
    version = settings.get("version", "")
    if not re.fullmatch(r"3\.13\.[0-9]+", version) or settings.get("include-system-site-packages") != "false":
        raise ValueError("Expected an isolated Python 3.13 environment")
    site = runtime / "lib/python3.13/site-packages"
    if site.resolve() != site or not site.is_dir():
        raise ValueError("Runtime package directory is missing or linked")
    directories = list(islice(site.glob("*.dist-info"), 257))
    if len(directories) > 256:
        raise ValueError("Runtime inventory exceeds the bounded view")
    distributions = {}
    metadata_hashes = {}
    for directory in sorted(directories):
        if directory.resolve() != directory or not directory.is_dir():
            raise ValueError("Distribution metadata directory is linked or invalid")
        raw = read_bytes(directory / "METADATA")
        headers = BytesParser().parsebytes(raw, headersonly=True)
        name, declared_version = headers.get("Name", ""), headers.get("Version", "")
        if (not isinstance(name, str) or not isinstance(declared_version, str)
                or len(headers.get_all("Name", [])) != 1 or len(headers.get_all("Version", [])) != 1
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}", name)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+!-]{0,99}", declared_version)):
            raise ValueError("Malformed distribution identity")
        identity = normalized(name)
        if identity in distributions:
            raise ValueError("Duplicate installed distribution")
        distributions[identity] = declared_version
        metadata_hashes[str(directory.relative_to(site) / "METADATA")] = hashlib.sha256(raw).hexdigest()
    expected = {normalized(item["name"]): item for item in packages}
    rows = [{"name": item["name"], "expected_version": item["version"],
             "observed_version": distributions.get(name),
             "metadata_matches": distributions.get(name) == item["version"],
             "license": item["license"], "wheel_sha256": item["sha256"],
             "requires_dist": item["requires_dist"], "artifact_integrity": None}
            for name, item in expected.items()]
    hashes = {}
    for name in stack["evaluator"]["source_files"]:
        path = site / name
        if (not name.startswith("agent_skill_eval/") or Path(name).is_absolute()
                or ".." in Path(name).parts or path.resolve() != path):
            raise ValueError("Evaluator source path is outside the reviewed package")
        try:
            hashes[name] = hashlib.sha256(read_bytes(path)).hexdigest()
        except FileNotFoundError:
            hashes[name] = None
    hooks = list(islice(site.glob("*.pth"), 257))
    has_startup_hooks = bool(hooks) or any((site / name).exists() or (site / name).is_symlink()
                                         for name in ("sitecustomize.py", "usercustomize.py",
                                                      "sitecustomize", "usercustomize", "sitecustomize.pyc", "usercustomize.pyc"))
    # pip is venv bootstrap tooling, not part of the evaluator's reviewed wheel closure.
    unexpected = sorted(set(distributions) - set(expected) - {"pip"})
    blockers = []
    if not all(item["metadata_matches"] for item in rows):
        blockers.append("Missing or mismatched package metadata")
    if hashes != stack["evaluator"]["source_files"]:
        blockers.append("Missing or changed evaluator source")
    if unexpected:
        blockers.append("Unselected distributions are present")
    if has_startup_hooks:
        blockers.append("Unreviewed Python startup hooks are present")
    return {"versions": {item["name"]: distributions.get(normalized(item["name"])) for item in packages},
            "source_files": hashes, "python_configuration": version,
            "packages": rows, "metadata_sha256": metadata_hashes,
            "bootstrap_pip_version": distributions.get("pip"), "unexpected_distributions": unexpected,
            "startup_hooks_present": has_startup_hooks, "blockers": blockers,
            "status": "blocked" if blockers else "metadata_and_evaluator_source_match",
            "limitations": ["Distribution versions and Python configuration are declarations, not runtime execution observations.",
                            "Only the listed evaluator source files are checked against reviewed source hashes.",
                            "Dependency/interpreter integrity, effective host access and worker containment are not established."]}
