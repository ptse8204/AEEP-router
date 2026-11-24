"""Bind the qBraid visualization verifier and its retained Linux runtime."""

import json
import struct
import tomllib
import zlib
from pathlib import Path
from urllib.request import build_opener

from audit_staged_repository_graders import audit_row, bind, index_paths, wheel_probe_assets
from check_expansion_contracts import NoRedirect
from check_linux_install import docker
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name, parse_wheel_filename
from rebind_cached_repository_sources import inventory
from stage_repository_transport import HERE, ROOT, digest, read, write

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import (
    _decode_suite_patch,
    archive_files,
    compressed_patch_artifact,
    pack_files,
)

CASE = "qBraid__pyqasm-168"
REVISION = "b1687f05782a7bad9e622e27c03d0c5139cd7a13"
INDEX = "378a7a9cf4dc2184f5af65b063547cbc27fc253d6f51d1e74cb3278280d5d4bc"
TEST = "tests/visualization/test_mpl_draw.py"
GIT_TREE = "13629c093ba00ab89e7ae7f9f53911c21d3032a4"
ARCHIVE_SHA = "07db40bff2c4422e5604dd8dda8bc7344b04a2e45a2bc7033f22117f210b067d"
PUBLISHER_FIXTURES = {
    "tests/visualization/images/bell.png": "fb63be1d339a46b2b26bb1fd834dc03f23de7909421ca85f73cfc29b22575ad4",
    "tests/visualization/images/misc.png": "34a49dd8d159216b8b1bf3ded5e41919b76877ffe2ea4912aad73ced6b9dd458",
}
BASELINES = set(PUBLISHER_FIXTURES)
SIGNATURE = b"\x89PNG\r\n\x1a\n"
CANDIDATES = {
    "openqasm3": "1.0.1",
    "antlr4-python3-runtime": "4.13.2",
    "pytest-mpl": "0.17.0",
    "jinja2": "3.1.6",
    "markupsafe": "3.0.2",
}
RETAINED = {
    "matplotlib": "3.10.0",
    "numpy": "2.2.3",
    "packaging": "26.3",
    "pillow": "13.0.0",
    "pytest": "8.3.4",
}
BASE = ROOT / ".aeep/completion-20261116"
PYTHON = {
    "python_version": "3.12",
    "python_full_version": "3.12.13",
    "platform_machine": "aarch64",
    "platform_system": "Linux",
    "os_name": "posix",
    "sys_platform": "linux",
}


def ref(path):
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path.read_bytes())}


def png_payload(raw):
    """Check the stored chunk CRCs and the complete RGBA scanline stream."""
    if not raw.startswith(SIGNATURE):
        return None
    offset, dimensions, compressed = len(SIGNATURE), None, []
    while offset + 12 <= len(raw):
        size, kind = struct.unpack_from(">I4s", raw, offset)
        start = offset + 8
        end = start + size
        if (
            end + 4 > len(raw)
            or zlib.crc32(raw[offset + 4 : end]) != struct.unpack_from(">I", raw, end)[0]
        ):
            return None
        if kind == b"IHDR":
            if dimensions is not None or size != 13:
                return None
            width, height, *format_ = struct.unpack(">IIBBBBB", raw[start:end])
            if format_ != [8, 6, 0, 0, 0] or not (0 < width <= 2000 and 0 < height <= 1000):
                return None
            dimensions = width, height
        elif kind == b"IDAT":
            compressed.append(raw[start:end])
        elif kind == b"IEND":
            if dimensions is None or not compressed or end + 4 != len(raw) or size:
                return None
            width, height = dimensions
            expected = (4 * width + 1) * height
            stream = zlib.decompressobj()
            try:
                pixels = stream.decompress(b"".join(compressed), expected + 1)
            except zlib.error:
                return None
            if len(pixels) != expected or not stream.eof or stream.unused_data:
                return None
            return {"width": width, "height": height, "scanline_sha256": digest(pixels)}
        offset = end + 4
    return None


def restore_png(raw, expected_sha):
    if digest(raw) != expected_sha or not raw.startswith(SIGNATURE.replace(b"\r\n", b"\n")):
        raise ValueError("pinned publisher image bytes changed")
    header = raw[:4] + b"\r" + raw[4:]
    if (payload := png_payload(header)) is not None:
        return header, payload | {"inserted_carriage_returns": [4]}
    recoveries = []
    for position, byte in enumerate(header):
        if position < len(SIGNATURE) or byte != 10:
            continue
        candidate = header[:position] + b"\r" + header[position:]
        if (payload := png_payload(candidate)) is not None:
            recoveries.append((candidate, payload | {"inserted_carriage_returns": [4, position]}))
    if len(recoveries) != 1:
        raise ValueError("the original PNG checksums do not establish a unique recovery")
    return recoveries[0]


async def transport():
    (index,) = [path for path, sha in index_paths() if sha == INDEX]
    (row,) = [item for item in json.loads(read(index, INDEX)) if item["input"]["task_id"] == CASE]
    _, wheels = wheel_probe_assets()
    await audit_row(row, index.parent, wheels)
    task, truth, published, original, _ = bind(row, index.parent, wheels)
    public = archive_files(truth.source.read(), large=True)
    protected = archive_files(truth.tests.read(), large=True)
    project = tomllib.loads(public["pyproject.toml"].decode())["project"]
    if (
        row["source_revision"] != REVISION
        or row["source_repository"] != "qbraid/pyqasm"
        or truth.test_paths != [TEST]
        or len(truth.fail_to_pass) != 1
        or len(truth.pass_to_pass) != 8
        or not public.keys() >= BASELINES
        or BASELINES & protected.keys()
        or TEST not in protected
        or row.get("create_paths")
        or project["name"] != "pyqasm"
        or "3.12.13" not in SpecifierSet(project["requires-python"])
    ):
        raise ValueError("qBraid verifier, source rights or runtime requirements changed")

    source = ROOT / ".aeep/repository-library-sources-20261027-v2/qBraid__pyqasm-168/source.tar.gz"
    tree, licenses, count, archive_sha = inventory(source, REVISION)
    if (tree, count, archive_sha) != (GIT_TREE, 128, ARCHIVE_SHA) or {
        digest(public["LICENSE"])
    } != {item["sha256"] for item in licenses}:
        raise ValueError("publisher tree or license changed")
    restored, image_proofs = {}, {}
    for name, expected in sorted(PUBLISHER_FIXTURES.items()):
        data, png = restore_png(public[name], expected)
        if data.replace(b"\r\n", b"\n") != public[name]:
            raise ValueError("image restoration changed more than missing line endings")
        restored[name] = data
        image_proofs[name] = png | {"publisher_sha256": expected, "recovered_sha256": digest(data)}
    original_files = public | protected
    private_paths = BASELINES | {TEST}
    hidden = protected | restored
    worker = {name: data for name, data in public.items() if name not in private_paths}
    source_blob, verifier_blob = pack_files(worker, large=True), pack_files(hidden, large=True)
    new_input = task.model_copy(update={"source_sha256": digest(source_blob)})
    roles = {}
    for role, reply in (("reference", published), ("original", original)):
        patch = _decode_suite_patch(truth, reply)
        original_grade_input = pack_files(
            public | {k: v.encode() for k, v in patch.files.items()} | protected, large=True
        )
        rebound = patch.model_copy(update={"base_sha256": content_digest(new_input)})
        new_grade_input = pack_files(
            worker | {k: v.encode() for k, v in rebound.files.items()} | hidden, large=True
        )
        if (
            archive_files(original_grade_input, large=True) | restored
            != archive_files(new_grade_input, large=True)
            or patch.base_sha256 != truth.input_sha256
        ):
            raise ValueError("moving verifier assets changed protected grading bytes")
        roles[role] = {
            "protected_input_sha256": digest(new_grade_input),
            "old_protected_input_sha256": digest(original_grade_input),
            "rebound_patch_sha256": content_digest(compressed_patch_artifact(rebound)),
        }
    if (
        private_paths & archive_files(source_blob, large=True).keys()
        or original_files | restored != worker | hidden
        or roles["reference"]["old_protected_input_sha256"] != row["reference_archive_sha256"]
        or roles["reference"]["protected_input_sha256"]
        == roles["original"]["protected_input_sha256"]
    ):
        raise ValueError(
            "protected assets leaked, or reference and fault differ from the source pin"
        )
    return {
        "retained_index": ref(index),
        "publisher_license_sha256": digest(public["LICENSE"]),
        "publisher_git_tree": tree,
        "publisher_archive": ref(source),
        "image_recoveries": image_proofs,
        "input_source_sha256": digest(source_blob),
        "input_sha256": content_digest(new_input),
        "protected_overlay_sha256": digest(verifier_blob),
        "would_retain_archive_bytes": len(source_blob) + len(verifier_blob),
        "private_asset_sha256": {name: digest(hidden[name]) for name in sorted(private_paths)},
        "issue_identities": truth.fail_to_pass,
        "preservation_identities": truth.pass_to_pass,
        "roles": roles,
        "project_python": project["requires-python"],
        "project_version": project["version"],
        "project_dependencies": project["dependencies"],
    }


def runtime(requirements):
    bound = json.loads(
        read(
            HERE / "eos-repaired-grader-result-20261120.json",
            "8fbec746bb2f3ff25ffea63d273a56b429bba3a43569d9917b405d3d9eb6995c",
        )
    )
    child = bound["child_image"]
    descriptor = json.loads(read(ROOT / child["path"], child["sha256"]))
    image = descriptor["image"]
    observed = json.loads(docker("image", "inspect", "--format", "{{json .}}", image["id"]))
    if (
        observed["Id"] != image["id"]
        or observed["Os"] != "linux"
        or observed["Architecture"] != "arm64"
        or observed["Config"]["User"] != "65534:65534"
        or observed["Config"].get("Volumes")
        or observed["Config"].get("Healthcheck")
        or observed["RootFS"]["Layers"] != image["layers"]
    ):
        raise ValueError("reviewed carrier ancestry or permissions changed")
    context = BASE / "c13-eos-native-runtime-20261119"
    source = context / "operation-review.json"
    manifest = json.loads(source.read_bytes())["manifest"]
    reused = {}
    for wheel in (context / "context/wheels").glob("*.whl"):
        name, version, _, _ = parse_wheel_filename(wheel.name)
        if RETAINED.get(name) != str(version):
            continue
        read(wheel, manifest[name])
        reused[name] = ref(wheel)
    if reused.keys() != RETAINED.keys():
        raise ValueError("retained scientific runtime inputs do not match their recorded hashes")

    versions = {**CANDIDATES, **RETAINED}
    pending = {}
    edges = [(text, "") for text in requirements]
    opener = build_opener(NoRedirect())
    for name, version in CANDIDATES.items():
        url = f"https://pypi.org/pypi/{name}/{version}/json"
        response = opener.open(url, timeout=12)
        with response:
            raw = response.read(700001)
        if len(raw) > 700000:
            raise ValueError("publisher metadata exceeds the reviewed response bound")
        data = json.loads(raw)
        extra = "parser" if name == "openqasm3" else ""
        edges.extend((edge, extra) for edge in data["info"]["requires_dist"] or [])
        (wheel,) = [
            item
            for item in data["urls"]
            if not item["yanked"]
            and (
                item["filename"].endswith("-none-any.whl")
                or (
                    name == "markupsafe"
                    and item["filename"].endswith(
                        "-cp312-cp312-manylinux_2_17_aarch64.manylinux2014_aarch64.whl"
                    )
                )
            )
        ]
        if (
            not wheel["url"].startswith("https://files.pythonhosted.org/packages/")
            or wheel["url"].rsplit("/", 1)[-1] != wheel["filename"]
            or (
                wheel["requires_python"] and "3.12.13" not in SpecifierSet(wheel["requires_python"])
            )
        ):
            raise ValueError("runtime package URL or declared platform changed")
        pending[name] = {
            "version": version,
            "filename": wheel["filename"],
            "url": wheel["url"],
            "bytes": wheel["size"],
            "sha256": wheel["digests"]["sha256"],
            "publisher_metadata_sha256": digest(raw),
        }
    for text, extra in edges:
        edge = Requirement(text)
        if edge.marker is not None and not edge.marker.evaluate(PYTHON | {"extra": extra}):
            continue
        name = canonicalize_name(edge.name)
        if edge.url or name not in versions or versions[name] not in edge.specifier:
            raise ValueError(f"unresolved Python 3.12 requirement: {text}")
    jinja = (
        ROOT
        / ".aeep/c13-cohort-runtime-20261124/c13-pdoc-806-20261124/wheels"
        / pending["jinja2"]["filename"]
    )
    read(jinja, pending["jinja2"]["sha256"])
    pending["jinja2"]["retained_cache"] = ref(jinja)
    return {
        "carrier_pin": child,
        "carrier_id": image["id"],
        "layer_count": len(image["layers"]),
        "offline_launcher_review_required": True,
        "reused_carrier_build_scope": ref(source),
        "reused_artifacts": reused,
        "pending_wheels": pending,
        "maximum_wheel_response_bytes": sum(
            row["bytes"] for row in pending.values() if not row.get("retained_cache")
        ),
        "required_pytest_plugin": "pytest_mpl.plugin",
        "required_pytest_option": "--mpl",
        "metadata_adaptation": "Expose the pyproject version via temporary distribution metadata for the source import fallback.",
    }


if __name__ == "__main__":
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("proof", type=Path)
    args = parser.parse_args()
    boundary = asyncio.run(transport())
    runtime_plan = runtime(boundary["project_dependencies"])
    result = {
        "schema_version": "aeep.c13.pyqasm-image-verifier-preflight.v1",
        "case": CASE,
        "revision": REVISION,
        "transport": boundary,
        "runtime": runtime_plan,
        "protected_tests_executed": 0,
        "official_reproduction": False,
        "formal_assignments": 0,
        "downloads": 0,
        "model_turns": 0,
        "cash_usd": 0,
        "comparisons_paused": True,
        "waza_excluded": True,
    }
    print(write(args.proof, (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()))
