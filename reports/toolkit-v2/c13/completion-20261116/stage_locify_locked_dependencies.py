"""Stage publisher-pinned Locify dependencies for an offline build."""

import argparse
import io
import json
import shutil
import tarfile
from concurrent.futures import ThreadPoolExecutor
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile

from acquire_full_rebench_leads import ref
from audit_full_rebench_runtime_inputs import OUTPUT as INTAKE
from packaging.utils import canonicalize_name
from quote_rebench_runtime_artifacts import FIRE, LOCIFY, quote_release
from stage_locify_litellm_source import HOST_RESERVE, fetch
from stage_locify_litellm_source import OUTPUT as LITELLM
from stage_repository_transport import ROOT, WORK, digest, encode, read, write

AUDIT_PIN = "823493d6e8287cf3eee4168498cb6623ca09a2faa2b4a1843c778b6dba979592"
QUOTE_PIN = "708378f0dc00fd43c382c7512bb768bcacc12350db4bc36658819635bf06c64a"
SETUPTOOLS_PIN = "558e47c15f1811c1fa7adbd0096669bf76c1d3f433f58324df69f3f5ecac4e8f"
SETUPTOOLS = ROOT / ".aeep/repository-test-root-wheels-20261027/setuptools-75.8.2-py3-none-any.whl"
OUTPUT = WORK / "locify-locked-runtime-assets-20261119"
BUILD_TOOLS = {"poetry-core": "1.9.1", "wheel": "0.45.1"}
MAX_BYTES = 80 * 1024**2


def headers(raw, source):
    if source:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
            member = tar.getmember("fire-0.7.0/PKG-INFO")
            if not member.isfile() or member.size > 100_000:
                raise ValueError("unexpected Fire metadata member")
            metadata = tar.extractfile(member).read()
    else:
        with ZipFile(io.BytesIO(raw)) as wheel:
            member, = [item for item in wheel.infolist()
                       if item.filename.count("/") == 1 and item.filename.endswith(".dist-info/METADATA")]
            if member.file_size > 1_000_000:
                raise ValueError("wheel metadata exceeds the read bound")
            metadata = wheel.read(member)
    return BytesParser().parsebytes(metadata, headersonly=True)


def identity(raw, name, version, *, source=False):
    metadata = headers(raw, source)
    if canonicalize_name(metadata["Name"]) != name or metadata["Version"] != version:
        raise ValueError("package metadata differs from its reviewed identity")


def inputs():
    locked = json.loads(read(INTAKE / "runtime-input-audit.json", AUDIT_PIN))["cases"][LOCIFY]
    quoted = json.loads(read(INTAKE / "runtime-artifact-quote.json", QUOTE_PIN))["cases"][LOCIFY]
    retained = []
    downloads = []
    for name, package in sorted(locked["packages"].items()):
        version = package["version"]
        allowed = package["locked_linux_arm64_wheels"]
        if name == "litellm":
            if version != "1.50.1" or quoted[name]["available"] is not None:
                raise ValueError("known publisher source fallback changed")
            publisher = json.loads((LITELLM / "verification.json").read_bytes())
            asset = publisher["archive"]
            read(ROOT / asset["path"], asset["sha256"])
            continue
        hits = package["verified_retained_wheels"]
        if hits:
            path = ROOT / hits[0]["path"]
            raw = read(path, allowed[path.name])
            identity(raw, name, version)
            retained.append({"name": name, "version": version, **ref(path), "bytes": len(raw)})
            continue
        artifact = quoted[name]["available"]
        hashes = FIRE if name == "fire" else allowed
        if quoted[name]["version"] != version or hashes[artifact["filename"]] != artifact["sha256"]:
            raise ValueError("publisher quote differs from its reviewed distribution")
        downloads.append({"name": name, "version": version, "usage": "runtime", **artifact})
    if len(locked["packages"]) != 65 or len(retained) != 13 or len(downloads) != 51:
        raise ValueError("Locify lock or cache shape changed")
    raw = read(SETUPTOOLS, SETUPTOOLS_PIN)
    identity(raw, "setuptools", "75.8.2")
    retained.append({
        "name": "setuptools", "version": "75.8.2", **ref(SETUPTOOLS), "bytes": len(raw),
        "usage": "source_build",
    })
    for name, version in BUILD_TOOLS.items():
        _, _, metadata = quote_release(("build_support", name, {"version": version}))
        artifact = metadata["available"]
        if artifact is None or artifact["type"] != "bdist_wheel":
            raise ValueError("no compatible artifact for the selected build tool")
        downloads.append({"name": name, "version": version, "usage": "source_build", **artifact})
    return retained, downloads, publisher


def download(row):
    url = urlsplit(row["url"])
    filename = row["filename"]
    if (
        Path(filename).name != filename or url.scheme != "https" or url.netloc != "files.pythonhosted.org"
        or url.path.rsplit("/", 1)[-1] != filename or url.query or url.fragment
    ):
        raise ValueError("artifact escaped the reviewed publisher destination")
    data = fetch(row["url"], row["bytes"])
    if len(data) != row["bytes"] or digest(data) != row["sha256"]:
        raise ValueError("publisher artifact did not match its exact pin")
    identity(data, row["name"], row["version"], source=row["type"] == "sdist")
    path = OUTPUT / "downloads" / filename
    if shutil.disk_usage(ROOT).free < HOST_RESERVE + len(data) + 4 * 1024**2:
        raise ValueError("available storage fell below the reserve")
    write(path, data)
    return ref(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-exact-dependencies", action="store_true", required=True)
    parser.parse_args()
    if OUTPUT.exists() or shutil.disk_usage(ROOT).free < HOST_RESERVE + MAX_BYTES + 8 * 1024**2:
        raise ValueError("source intake needs an unstarted directory and sufficient host space")
    retained, downloads, publisher = inputs()
    total = sum(item["bytes"] for item in downloads)
    if not 0 < total <= MAX_BYTES or len({row["filename"] for row in downloads}) != len(downloads):
        raise ValueError("artifact scope exceeds the reviewed acquisition bound")
    OUTPUT.mkdir(mode=0o700)
    review = OUTPUT / "public-source-intake.json"
    write(review, encode({
        "source_scope": "C13 delegated first-time public package acquisition, no package execution.",
        "driver": ref(Path(__file__).resolve()),
        "retained": retained, "downloads": downloads,
        "maximum_total_bytes": total, "host_reserve_bytes": HOST_RESERVE,
        "litellm_source_archive": publisher["archive"],
        "build_tool_versions_are_reviewed_choice": BUILD_TOOLS,
        "package_execution": False, "network_destination": "files.pythonhosted.org",
        "model_turns": 0, "cash_usd": 0,
    }))
    with ThreadPoolExecutor(max_workers=4) as pool:
        acquired = list(pool.map(download, downloads))
    write(OUTPUT / "result.json", encode({
        "source_intake": ref(review), "downloaded": acquired, "total_retained_bytes": total,
        "locked_runtime_identities": 65, "original_litellm_wheel_available": False,
        "first_party_manifest_verified": True, "builds": 0, "installs": 0,
        "protected_grader_invocations": 0, "model_turns": 0,
    }))
    print(f"Verified {len(acquired)} artifacts ({total} bytes) for the offline build.")


if __name__ == "__main__":
    main()
