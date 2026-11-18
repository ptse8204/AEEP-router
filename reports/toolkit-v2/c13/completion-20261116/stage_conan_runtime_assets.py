"""Statically verify Conan's three retained direct runtime artifacts."""

import argparse
import ast
import base64
import csv
import hashlib
import io
import json
import sys
import tarfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, ZipInfo

from audit_conan_native_selectors import pytest_pin
from stage_repository_transport import digest, read

from aeep_toolkit.install_runtime import Wheel, check_wheel

SCOPE_PINS = {
    "pytest-7.4.4-py3-none-any.whl": "b090cdf5ed60bf4c45261be03239c2c1c22df034fbffe691abe93cd80cea01d8",
    "fasteners-0.19-py3-none-any.whl": "758819cb5d94cdedf4e836988b74de396ceacb8e2794d21f82d131fd9ee77237",
    "patch-ng-1.18.1.tar.gz": "52fd46ee46f6c8667692682c1fd7134edc65a2d2d084ebec1d295a6087fc0291",
}


def module_files(raw):
    prefix = "patch-ng-1.18.1"
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        items = archive.getmembers()
        names = [item.name for item in items]
        if (len(names) != len(set(names)) or len(names) > 64
                or any((not item.isfile() and not item.isdir())
                       or PurePosixPath(item.name).parts[:1] != (prefix,)
                       or ".." in PurePosixPath(item.name).parts for item in items)
                or sum(item.size for item in items) > 512 * 1024):
            raise ValueError("source distribution exceeds the reviewed pure-module layout")
        return {name: archive.extractfile(f"{prefix}/{name}").read()
                for name in ("patch_ng.py", "LICENSE", "PKG-INFO")}


def wheel_body(files):
    metadata = BytesParser().parsebytes(files["PKG-INFO"])
    if (metadata["Name"], metadata["Version"]) != ("patch-ng", "1.18.1"):
        raise ValueError("source package metadata changed")
    tree = ast.parse(files["patch_ng.py"])
    python_two_compatibility = {
        "from StringIO import StringIO": "from io import BytesIO as StringIO",
        "import urllib2 as urllib_request": "import urllib.request as urllib_request",
    }
    guarded = set()
    for node in tree.body:
        if (isinstance(node, ast.Try) and len(node.body) == len(node.handlers) == 1
                and isinstance(node.handlers[0].type, ast.Name)
                and node.handlers[0].type.id == "ImportError"
                and len(node.handlers[0].body) == 1
                and python_two_compatibility.get(ast.unparse(node.body[0]))
                == ast.unparse(node.handlers[0].body[0])):
            guarded.add(node.body[0])
    if len(guarded) != 2:
        raise ValueError("expected Python 3 fallback imports changed")
    imports = set()
    for node in ast.walk(tree):
        if node in guarded:
            continue
        if isinstance(node, ast.Import):
            imports.update(item.name.partition(".")[0] for item in node.names)
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            imports.add(node.module.partition(".")[0])
    if not imports <= sys.stdlib_module_names or metadata.get_all("Requires-Dist", []):
        raise ValueError("standalone module dependency scope changed")
    directory = "patch_ng-1.18.1.dist-info"
    entries = {
        "patch_ng.py": files["patch_ng.py"],
        f"{directory}/METADATA": files["PKG-INFO"],
        f"{directory}/licenses/LICENSE": files["LICENSE"],
        f"{directory}/WHEEL": (b"Wheel-Version: 1.0\nGenerator: AEEP local source carrier\n"
                               b"Root-Is-Purelib: true\nTag: py3-none-any\n"),
    }
    record = []
    for name, body in sorted(entries.items()):
        encoded = base64.urlsafe_b64encode(hashlib.sha256(body).digest()).rstrip(b"=").decode()
        record.append(f"{name},sha256={encoded},{len(body)}\n")
    entries[f"{directory}/RECORD"] = ("".join(record) + f"{directory}/RECORD,,\n").encode()
    output = io.BytesIO()
    with ZipFile(output, "w") as archive:
        for name, body in sorted(entries.items()):
            archive.writestr(ZipInfo(name), body)
    return output.getvalue()


def wheels(artifacts, destination):
    verified = {}
    for name, sha in SCOPE_PINS.items():
        raw = read(artifacts / name, sha)
        verified[name] = {"sha256": sha, "bytes": len(raw)}
    filename = "fasteners-0.19-py3-none-any.whl"
    check_wheel(artifacts / filename, Wheel(extension_id="fasteners", filename=filename,
                                            name="fasteners", version="0.19", sha256=SCOPE_PINS[filename]))
    filename = "pytest-7.4.4-py3-none-any.whl"
    # The protected grader ZIP-imports pytest. Its installer command policy is separate.
    record_name = "pytest-7.4.4.dist-info/RECORD"
    with ZipFile(artifacts / filename) as archive:
        entries = archive.namelist()
        records = list(csv.reader(archive.read(record_name).decode().splitlines()))
        if len(entries) != len(set(entries)) or sorted(entries) != sorted(row[0] for row in records):
            raise ValueError("pytest ZIP member inventory differs from its RECORD")
        for name, checksum, size in records:
            if name == record_name and not checksum and not size:
                continue
            if (PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts
                    or "\\" in name or name.endswith(".pth")):
                raise ValueError("invalid ZIP module path")
            raw = archive.read(name)
            token = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b"=").decode()
            if checksum != f"sha256={token}" or size != str(len(raw)):
                raise ValueError("pytest member differs from publisher metadata")
    pytest_rules = pytest_pin([{"path": str(artifacts / filename), "sha256": SCOPE_PINS[filename]}],
                              version="7.4.4")
    files = module_files(read(artifacts / "patch-ng-1.18.1.tar.gz", SCOPE_PINS["patch-ng-1.18.1.tar.gz"]))
    body = wheel_body(files)
    if body != wheel_body(files):
        raise ValueError("source archive packaging is nondeterministic")
    filename = "patch_ng-1.18.1-py3-none-any.whl"
    path = destination / filename
    with path.open("xb") as output:
        output.write(body)
    check_wheel(path, Wheel(extension_id="patch-ng", name="patch-ng", filename=filename,
                            version="1.18.1", sha256=digest(body)))
    with ZipFile(path) as archive:
        for name, original in (("patch_ng.py", "patch_ng.py"),
                               ("patch_ng-1.18.1.dist-info/METADATA", "PKG-INFO"),
                               ("patch_ng-1.18.1.dist-info/licenses/LICENSE", "LICENSE")):
            if archive.read(name) != files[original]:
                raise ValueError("local source carrier changed upstream bytes")
    return {
        "verified_publisher_artifacts": verified,
        "declared_pytest_7_4_4_identity_rules": pytest_rules,
        "local_patch_ng_carrier": {
            "filename": filename, "sha256": digest(body), "bytes": len(body),
            "source_module_sha256": digest(files["patch_ng.py"]),
            "license_sha256": digest(files["LICENSE"]),
            "publisher_metadata_sha256": digest(files["PKG-INFO"]),
        },
        "installs": 0, "package_code_executions": 0, "upstream_grader_executions": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(wheels(args.artifacts, args.output), indent=2, sort_keys=True))
