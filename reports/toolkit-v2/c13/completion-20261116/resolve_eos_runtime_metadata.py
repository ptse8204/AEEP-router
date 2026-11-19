"""Resolve EOS with pip while allowing only bounded public package metadata."""

import argparse
import io
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile

import pip
from audit_full_rebench_runtime_inputs import MARKERS, OUTPUT, PLATFORMS
from pip._internal.cli.main import main as pip_main
from pip._internal.network.session import PipSession
from pip._internal.operations.prepare import RequirementPreparer
from pip._internal.utils.direct_url_helpers import direct_url_from_link
from pip._vendor.packaging import markers
from stage_repository_transport import ROOT, digest, encode, read, write

EOS = "Akkudoktor-EOS__EOS-459"
QUOTE = OUTPUT / "runtime-artifact-quote.json"
QUOTE_PIN = "708378f0dc00fd43c382c7512bb768bcacc12350db4bc36658819635bf06c64a"
CARRIER_REPORT = ROOT / "reports/toolkit-v2/c13/completion-20261116/rebench-storage-and-carriers-20261119.json"
HOST_RESERVE = 50 * 1024**3
RESULT = OUTPUT / "eos-wheel-metadata-resolution-20261119.json"


def eligible_url(value):
    url = urlsplit(value)
    if url.scheme != "https" or url.query or url.fragment:
        return False
    if url.netloc == "pypi.org":
        return re.fullmatch(r"/simple/[a-z0-9-]+/", url.path) is not None
    if url.netloc == "files.pythonhosted.org":
        return url.path.startswith("/packages/") and url.path.endswith(".whl.metadata")
    return False


def restrict_requests(events):
    request = PipSession.request
    limit = 64 * 1024**2
    received = 0

    def metadata_request(session, method, url, *args, **kwargs):
        nonlocal received
        if method.upper() != "GET" or not eligible_url(url) or len(events) >= 180:
            raise ValueError("pip attempted to exceed the reviewed metadata scope")
        session.trust_env = False
        session.auth = None
        kwargs.update(allow_redirects=False, stream=True)
        response = request(session, method, url, *args, **kwargs)
        body = bytearray()
        per_response_limit = (12 if url == "https://pypi.org/simple/pydantic-core/" else 8) * 1024**2
        with response:
            if response.is_redirect:
                raise ValueError("publisher metadata redirected")
            for chunk in response.iter_content(chunk_size=64 * 1024):
                body.extend(chunk)
                if len(body) > per_response_limit or received + len(body) > limit:
                    raise ValueError(f"publisher metadata exceeded its byte limit at {url}")
        raw = bytes(body)
        received += len(raw)
        response._content = raw
        response._content_consumed = True
        response.raw = io.BytesIO(raw)
        response.headers["Content-Length"] = str(len(raw))
        response.headers.pop("Content-Encoding", None)
        events.append({"url": url, "bytes": len(raw), "sha256": digest(raw), "status": response.status_code})
        return response

    PipSession.request = metadata_request


def local_metadata(directory, timezone):
    # Pip accepts a local metadata wheel for the Conda-provided package. No
    # Python module is included. Replace this placeholder in the retained plan.
    root = "timezonefinder-6.5.8.dist-info"
    path = directory / "timezonefinder-6.5.8-py3-none-any.whl"
    metadata = [
        "Metadata-Version: 2.1", "Name: timezonefinder", "Version: 6.5.8",
        *(f"Requires-Dist: {line}" for line in timezone["requires_dist"]),
    ]
    with ZipFile(path, "x") as wheel:
        wheel.writestr(root + "/METADATA", "\n".join(metadata) + "\n")
        wheel.writestr(root + "/WHEEL", "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
    return path


def resolve(directory, direct, events):
    stub = local_metadata(directory, direct["timezonefinder"])
    save = directory / "pip-report.json"
    prepared = {}

    def metadata_only(preparer, requirement):
        link = requirement.link
        if link.is_file and Path(link.file_path) == stub:
            return None
        if not link.is_wheel or link.metadata_link() is None:
            raise ValueError("required wheel lacks publisher-hosted metadata")
        dist = preparer._fetch_metadata_using_link_data_attr(requirement)
        if dist is None:
            raise ValueError("publisher wheel metadata could not be loaded")
        prepared[link.url] = dist
        return dist

    def skip_payloads(_preparer, requirements, **_kwargs):
        # Bind the report to metadata already verified by pip. Its normal
        # finalization would fetch each complete package before reporting.
        for requirement in requirements:
            link = requirement.link
            if link.is_file and Path(link.file_path) == stub:
                continue
            requirement.download_info = direct_url_from_link(link)
            requirement.get_dist = lambda dist=prepared[link.url]: dist

    markers.default_environment = lambda: {key: value for key, value in MARKERS.items() if key != "extra"}
    RequirementPreparer._fetch_metadata_only = metadata_only
    RequirementPreparer.prepare_linked_requirements_more = skip_payloads
    restrict_requests(events)
    os.environ["PIP_CONFIG_FILE"] = os.devnull
    args = [
        "--isolated", "--disable-pip-version-check", "--no-input", "--no-cache-dir",
        "install", "--dry-run", "--ignore-installed", "--only-binary=:all:",
        "--progress-bar", "off", "--index-url", "https://pypi.org/simple",
        "--retries", "0", "--resume-retries", "0", "--timeout", "12",
        "--python-version", MARKERS["python_full_version"],
        "--implementation", "cp", "--abi", "cp312", "--report", str(save),
    ]
    for platform in PLATFORMS:
        args.extend(("--platform", platform))
    if pip_main([*args, str(stub), *(f"{name}=={row['version']}" for name, row in direct.items()
                                   if name != "timezonefinder")]) != 0:
        raise ValueError("metadata-only resolution failed")
    return json.loads(save.read_bytes())


def result_plan(report, direct, conda, events):
    selected = {}
    for entry in report["install"]:
        metadata = entry["metadata"]
        name = metadata["name"].casefold().replace("_", "-")
        info = entry["download_info"]
        if name in selected:
            raise ValueError("duplicate selected dependency")
        if name == "timezonefinder":
            if not info["url"].startswith("file://") or metadata["version"] != "6.5.8":
                raise ValueError("unexpected timezonefinder source")
            artifact = {"url": conda["url"], "sha256": conda["sha256"], "bytes": conda["bytes"],
                        "kind": "conda-forge-linux-aarch64"}
        else:
            address = urlsplit(info["url"])
            checksum = info["archive_info"]["hashes"]["sha256"]
            if (not eligible_url(info["url"] + ".metadata") or not address.path.endswith(".whl")
                    or not re.fullmatch(r"[a-f0-9]{64}", checksum)):
                raise ValueError("resolver selected an unpinned or unsupported wheel")
            artifact = {"url": info["url"], "sha256": checksum, "kind": "pypi-wheel"}
        selected[name] = {
            "version": metadata["version"], "artifact": artifact,
            "requirements": metadata.get("requires_dist", []),
            "requires_python": metadata.get("requires_python"),
            "requested_extras": entry.get("requested_extras", []),
        }
    if any(name not in selected or row["version"] != selected[name]["version"]
           for name, row in direct.items()):
        raise ValueError("resolver changed a pinned EOS direct requirement")
    if not any(event["url"].endswith(".whl.metadata") for event in events):
        raise ValueError("publisher wheel metadata was not observed")
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resolve-metadata-only", required=True, action="store_true")
    parser.parse_args()
    if RESULT.exists() or pip.__version__ != "25.2" or shutil.disk_usage(ROOT).free < HOST_RESERVE + 8 * 1024**2:
        raise ValueError("metadata resolution preflight failed")
    direct = json.loads(read(QUOTE, QUOTE_PIN))["cases"][EOS]
    conda = json.loads(CARRIER_REPORT.read_bytes())["eos"]["archive"]
    events = []
    with tempfile.TemporaryDirectory(prefix="eos-metadata-", dir="/private/tmp") as temp:
        report = resolve(Path(temp).resolve(), direct, events)
    selected = result_plan(report, direct, conda, events)
    write(RESULT, encode({
        "schema_version": "aeep.c13.eos-pip-metadata-resolution.v1",
        "pip_version": pip.__version__, "target": MARKERS, "direct_pin_count": len(direct),
        "packages": selected, "selected_count": len(selected), "publisher_fetches": events,
        "conda_native_requirements_pending": ["libgcc >=13", "verify h3-py and Python ABI bindings"],
        "artifact_downloads": 0, "installs": 0, "upstream_packages_executed": 0, "model_turns": 0,
    }))
    print(f"Resolved {len(selected)} Python package identities without artifact downloads.")


if __name__ == "__main__":
    main()
