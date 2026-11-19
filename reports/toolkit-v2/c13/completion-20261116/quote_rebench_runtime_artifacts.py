"""Bind public release metadata and measure exact direct-download sizes."""

import json
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import urlopen

from acquire_full_rebench_leads import RESERVE, ref
from audit_full_rebench_runtime_inputs import OUTPUT, pure_linux_wheel
from packaging.utils import canonicalize_name
from stage_full_rebench_reference_assets import EOS, LOCIFY
from stage_repository_transport import digest, encode, write

AUDIT = OUTPUT / "runtime-input-audit.json"
FIRE = {
    "fire-0.7.0.tar.gz": "961550f07936eaf65ad1dc8360f2b2bf8408fad46abbfa4d2a3794f8d2a95cdf",
}


def extract_files(name, version, release, allowed):
    info = release["info"]
    if canonicalize_name(info["name"]) != name or info["version"] != version:
        raise ValueError("PyPI metadata identity differs")
    candidates = []
    for item in release["urls"]:
        filename = item["filename"]
        if item["yanked"] or (allowed is not None and filename not in allowed):
            continue
        if item["packagetype"] == "bdist_wheel":
            if pure_linux_wheel(Path(filename)) != (name, version):
                continue
        elif name != "fire" or filename not in FIRE or allowed != FIRE:
            continue
        checksum = item["digests"]["sha256"]
        address = urlsplit(item["url"])
        if (
            not re.fullmatch("[a-f0-9]{64}", checksum)
            or address.scheme != "https"
            or address.netloc != "files.pythonhosted.org"
            or address.path.rsplit("/", 1)[-1] != filename
            or address.query
            or address.fragment
            or not isinstance(item["size"], int)
            or item["size"] <= 0
            or (allowed is not None and allowed[filename] != checksum)
        ):
            raise ValueError("publisher artifact differs from the allowed distribution")
        candidates.append({
            "filename": filename,
            "bytes": item["size"],
            "sha256": checksum,
            "type": item["packagetype"],
            "url": item["url"],
        })
    return sorted(candidates, key=lambda row: (row["bytes"], row["filename"]))


def quote_release(query):
    case, name, requirements = query
    version = requirements["version"]
    address = f"https://pypi.org/pypi/{quote(name, safe='')}/{quote(version, safe='')}/json"
    try:
        with urlopen(address, timeout=15) as response:
            if response.geturl() != address:
                raise ValueError("release metadata unexpectedly redirected")
            raw = response.read(512 * 1024 + 1)
        if len(raw) > 512 * 1024:
            raise ValueError("release metadata exceeded its byte cap")
    except (HTTPError, URLError, TimeoutError) as error:
        return case, name, {
            "release_metadata": address,
            "version": version,
            "available": None,
            "metadata_error": f"HTTP {error.code}" if isinstance(error, HTTPError) else type(error).__name__,
        }
    allowed = requirements.get("locked_linux_arm64_wheels") if case == LOCIFY else None
    allowed = FIRE if case == LOCIFY and name == "fire" and allowed == {} else allowed
    release = json.loads(raw)
    candidates = extract_files(name, version, release, allowed)
    return case, name, {
        "release_metadata": address,
        "release_metadata_sha256": digest(raw),
        "version": version,
        "available": candidates[0] if candidates else None,
        "considered_compatible_artifacts": len(candidates),
        "requires_dist": release["info"].get("requires_dist") or [],
    }


def main():
    saved = json.loads(AUDIT.read_bytes())["cases"]
    missing = {
        LOCIFY: {
            name: requirements
            for name, requirements in saved[LOCIFY]["packages"].items()
            if not requirements["verified_retained_wheels"]
        },
        EOS: saved[EOS]["dependencies"],
    }
    queries = [(case, name, requirements) for case, rows in missing.items()
               for name, requirements in rows.items()]
    if len(queries) != 70 or shutil.disk_usage(OUTPUT).free < RESERVE + 8 * 1024**2:
        raise ValueError("runtime metadata review scope or headroom changed")
    staged = {case: {} for case in missing}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for case, name, result in pool.map(quote_release, queries):
            staged[case][name] = result
    totals = {
        case: {
            "known_archive_bytes": sum(row["available"]["bytes"] for row in rows.values() if row["available"]),
            "missing_compatible_artifacts": [name for name, row in rows.items() if row["available"] is None],
        }
        for case, rows in staged.items()
    }
    write(OUTPUT / "runtime-artifact-quote.json", encode({
        "source": ref(AUDIT),
        "driver": ref(Path(__file__).resolve()),
        "target": "Linux ARM64 CPython 3.12 glibc up to 2.36",
        "release_metadata_requests": len(queries),
        "package_artifacts_downloaded": 0,
        "cases": staged,
        "totals": totals,
    }))
    print(json.dumps(totals, indent=2))


if __name__ == "__main__":
    main()
