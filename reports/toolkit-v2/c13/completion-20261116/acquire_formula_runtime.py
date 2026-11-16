"""Acquire the two exact public browser artifacts after operator approval."""

import argparse
import base64
import hashlib
import json
import shutil
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[4]
PRIVATE = ROOT / ".aeep/completion-20261116/formula-offline-assets"
PUBLICATIONS = PRIVATE / "runtime-publications.json"
FIXTURES = PRIVATE / "protected-fixtures/protected-fixture-lock.json"
REVIEW = PRIVATE / "acquisition-review.json"
APPROVAL = PRIVATE / "acquisition-approval.json"
RESULTS = PRIVATE / "acquired"
ORDER = ("playwright", "chromium-headless-shell")
RESERVE = 50 * 1024**3


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("publisher redirect is outside the reviewed acquisition")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, data):
    with path.open("x") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")


def expected_review():
    pins = json.loads(PUBLICATIONS.read_bytes())
    files = pins["large_artifacts_unstarted"]
    if tuple(files) != ORDER or sum(row["bytes"] for row in files.values()) != pins["pending_transfer_bytes"]:
        raise ValueError("runtime acquisition inventory changed")
    browser, wheel = files["chromium-headless-shell"], files["playwright"]
    if (wheel["version"] != "1.57.0" or browser["playwright_revision"] != "1200"
            or urlsplit(wheel["url"]).netloc != "files.pythonhosted.org"
            or urlsplit(browser["url"]).netloc != "storage.googleapis.com"
            or any(urlsplit(row["url"]).scheme != "https" for row in files.values())):
        raise ValueError("runtime acquisition does not match the published profile")
    return {
        "scope": "Receive and inspect the pinned Playwright wheel and Chromium Linux amd64 ZIP.",
        "driver_sha256": digest(Path(__file__)), "publication_sha256": digest(PUBLICATIONS),
        "fixture_sha256": digest(FIXTURES), "artifacts": files, "maximum_gets": 2,
        "maximum_payload_bytes": pins["pending_transfer_bytes"], "automatic_retries": 0,
        "executables_launched": 0, "installations": 0, "model_turns": 0, "cash_usd": 0,
        "receipt_contract": [
            "Require PyPI SHA-256 and the bundled Playwright Chromium revision for the wheel.",
            "Require Google object generation, byte size, published MD5 and the reviewed ZIP directory.",
            "Verify every ZIP member for CRC corruption. Record SHA-256 for the downloaded browser.",
            "Retain validated archives only as private data. A separate launch review binds their actual SHA-256.",
        ],
    }


def verify_archive(path, key, row):
    with ZipFile(path) as archive:
        if key == "playwright":
            registry = json.loads(archive.read("playwright/driver/package/browsers.json"))
            browser, = [item for item in registry["browsers"] if item["name"] == "chromium-headless-shell"]
            if browser["revision"] != "1200" or browser["browserVersion"] != "143.0.7499.4":
                raise ValueError("wheel's bundled browser revision changed")
            if "playwright/driver/node" not in archive.namelist():
                raise ValueError("wheel lacks the expected Linux driver")
        else:
            directory = {}
            for entry in archive.infolist():
                if entry.is_dir():
                    continue
                if entry.filename in directory:
                    raise ValueError("browser ZIP has repeated member paths")
                directory[entry.filename] = {"expanded_bytes": entry.file_size,
                    "compressed_bytes": entry.compress_size, "zip_crc32": f"{entry.CRC:08x}"}
            if directory != row["zip_central_directory"]:
                raise ValueError("browser ZIP differs from its reviewed file metadata")
        if archive.testzip() is not None:
            raise ValueError("archive member failed its ZIP checksum")


def receive(opener, key, row, folder):
    destination = folder / row["filename"]
    partial = folder / (row["filename"] + ".partial")
    deadline = time.monotonic() + 240
    sha = hashlib.sha256()
    md5 = hashlib.md5(usedforsecurity=False)
    nbytes = 0
    request = Request(row["url"], headers={"Accept-Encoding": "identity"})
    with opener.open(request, timeout=15) as response, partial.open("xb") as output:
        if (response.status != 200 or response.geturl() != row["url"]
                or response.headers["Content-Length"] != str(row["bytes"])
                or response.headers.get("Content-Encoding", "identity") != "identity"):
            raise ValueError("publisher returned an unreviewed response")
        if key == "chromium-headless-shell" and response.headers["x-goog-generation"] != row["publisher_generation"]:
            raise ValueError("publisher object generation changed")
        while nbytes < row["bytes"]:
            if time.monotonic() > deadline:
                raise ValueError("publisher response exceeded its time bound")
            chunk = response.read(min(1024 * 1024, row["bytes"] - nbytes))
            if not chunk:
                break
            nbytes += len(chunk)
            sha.update(chunk)
            md5.update(chunk)
            output.write(chunk)
    if nbytes != row["bytes"]:
        raise ValueError("publisher object is truncated")
    if key == "playwright" and sha.hexdigest() != row["sha256"]:
        raise ValueError("wheel does not match PyPI's SHA-256")
    if key == "chromium-headless-shell" and md5.digest() != base64.b64decode(row["publisher_md5_base64"]):
        raise ValueError("browser does not match the publisher object's MD5")
    verify_archive(partial, key, row)
    partial.rename(destination)
    return {"file": destination.name, "bytes": nbytes, "sha256": sha.hexdigest()}


def acquire(exact):
    if digest(REVIEW) != exact or json.loads(REVIEW.read_bytes()) != expected_review():
        raise ValueError("exact acquisition review changed")
    if not APPROVAL.is_file():
        raise ValueError("operator approval is required for this acquisition")
    approval = json.loads(APPROVAL.read_bytes())
    if approval.get("approved") is not True or approval.get("review_sha256") != exact:
        raise ValueError("approval does not bind the exact acquisition")
    review = json.loads(REVIEW.read_bytes())
    if shutil.disk_usage(PRIVATE).free < RESERVE + review["maximum_payload_bytes"]:
        raise ValueError("insufficient free space for this acquisition")
    RESULTS.mkdir(mode=0o700)
    write(RESULTS / "started.json", {"review_sha256": exact})
    opener = build_opener(NoRedirect)
    receipts = []
    for key in ORDER:
        item = receive(opener, key, review["artifacts"][key], RESULTS)
        write(RESULTS / (key + "-receipt.json"), item)
        receipts.append(item)
    write(RESULTS / "result.json", {"review_sha256": exact, "received": receipts, "installed": False, "executed": False})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--exact-review")
    args = parser.parse_args()
    if args.prepare:
        write(REVIEW, expected_review())
        print(digest(REVIEW))
    else:
        acquire(args.exact_review)
