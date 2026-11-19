"""Check the EOS metadata closure and quote its exact artifact intake."""

import argparse
import json
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from acquire_full_rebench_leads import ref
from audit_eos_retained_transitives import RESULT as RETAINED
from audit_full_rebench_runtime_inputs import MARKERS, cached_wheels, pure_linux_wheel
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from resolve_eos_runtime_metadata import CARRIER_REPORT, EOS, QUOTE, QUOTE_PIN
from resolve_eos_runtime_metadata import RESULT as RESOLVED
from stage_locify_locked_dependencies import headers
from stage_repository_transport import ROOT, digest, encode, read, write

RESULT = RESOLVED.with_name("eos-resolved-asset-quote-20261119.json")


def active_graph(selected, direct):
    pending = deque((name, "") for name in direct)
    reached = set()
    edges = set()
    while pending:
        name, extra = pending.popleft()
        if (name, extra) in reached:
            continue
        reached.add((name, extra))
        if name not in selected:
            raise ValueError(f"selected closure lacks {name}")
        row = selected[name]
        expected = direct.get(name)
        if expected and row["version"] != expected["version"]:
            raise ValueError(f"selected closure changed the direct pin for {name}")
        supported = row.get("requires_python")
        if supported and not SpecifierSet(supported).contains(MARKERS["python_full_version"]):
            raise ValueError(f"selected {name} excludes the target interpreter")
        for requirement in map(Requirement, row["requirements"]):
            if requirement.marker and not requirement.marker.evaluate(MARKERS | {"extra": extra}):
                continue
            child = canonicalize_name(requirement.name)
            if (child not in selected or requirement.url
                    or not requirement.specifier.contains(selected[child]["version"], prereleases=True)):
                raise ValueError(f"selected {name} conflicts with {requirement}")
            edges.add((name, extra, str(requirement)))
            pending.extend((child, option) for option in ("", *sorted(requirement.extras)))
    return sorted(reached), sorted(edges)


def reuse_cached(selected, direct, retained):
    chosen = dict(selected)
    reused = []
    for name, row in sorted(retained.items()):
        proof = row["verified_wheel"]
        if name in direct or name not in chosen or not proof:
            continue
        artifact = row["release_metadata"]["available"]
        path = ROOT / proof["path"]
        data = read(path, proof["sha256"])
        if (proof["sha256"] != artifact["sha256"] or len(data) != artifact["bytes"]
                or pure_linux_wheel(path) != (name, row["version"])):
            raise ValueError("publisher-verified retained EOS wheel drifted")
        metadata = headers(data, False)
        candidate = {
            "version": row["version"], "requirements": metadata.get_all("Requires-Dist", []),
            "requires_python": metadata.get("Requires-Python"), "requested_extras": [],
            "artifact": {"url": artifact["url"], "sha256": artifact["sha256"],
                         "bytes": artifact["bytes"], "kind": "pypi-wheel"},
        }
        proposed = chosen | {name: candidate}
        try:
            active_graph(proposed, direct)
        except ValueError:
            continue
        chosen = proposed
        reused.append(name)
    return chosen, reused


def quote_missing(url, hosts):
    remote = urlsplit(url)
    if remote.scheme != "https" or remote.netloc not in hosts or remote.query or remote.fragment:
        raise ValueError("unexpected publisher artifact address")
    with urlopen(Request(url, method="HEAD"), timeout=12) as response:
        if response.geturl() != url:
            raise ValueError("publisher artifact size request redirected")
        size = int(response.headers["Content-Length"])
    if not 0 < size <= 100 * 1024**2:
        raise ValueError("publisher artifact size exceeds the quote bound")
    return size


def quote_one(item):
    name, artifact = item
    return name, quote_missing(artifact["url"], {"files.pythonhosted.org", "conda.anaconda.org"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quote-resolved-closure", required=True, action="store_true")
    parser.parse_args()
    if RESULT.exists():
        raise ValueError("EOS resolved closure already has a quote")
    original = json.loads(RESOLVED.read_bytes())
    direct = json.loads(read(QUOTE, QUOTE_PIN))["cases"][EOS]
    selected = original["packages"]
    active_graph(selected, direct)
    retained = json.loads(RETAINED.read_bytes())["retained_candidates"]
    chosen, reuse = reuse_cached(selected, direct, retained)
    contexts, edges = active_graph(chosen, direct)
    names = {name for name, _ in contexts}
    chosen = {name: chosen[name] for name in sorted(names)}
    cache = cached_wheels()
    available = {}
    for name, entry in chosen.items():
        artifact = entry["artifact"]
        if artifact["kind"] == "pypi-wheel":
            filename = Path(urlsplit(artifact["url"]).path).name
            if pure_linux_wheel(Path(filename)) != (name, entry["version"]):
                raise ValueError("selected wheel cannot run in the EOS target")
            for path in cache.get((name, entry["version"]), {}).get(filename, []):
                if digest(path.read_bytes()) == artifact["sha256"]:
                    available[name] = ref(path) | {"bytes": path.stat().st_size}
                    break
    missing = [(name, row["artifact"]) for name, row in chosen.items() if name not in available]
    known = {name: artifact["bytes"] for name, artifact in missing if "bytes" in artifact}
    requests = [(name, artifact) for name, artifact in missing if name not in known]
    with ThreadPoolExecutor(max_workers=4) as pool:
        sizes = known | dict(pool.map(quote_one, requests))
    write(RESULT, encode({
        "schema_version": "aeep.c13.eos-resolved-asset-quote.v1",
        "resolved_metadata": ref(RESOLVED), "driver": ref(Path(__file__).resolve()),
        "target": MARKERS, "selected": chosen, "direct_pin_count": len(direct),
        "bytes_by_missing_package": sizes, "missing_package_download_bytes": sum(sizes.values()),
        "reused_retained_candidates": reuse, "exact_cached": available,
        "active_dependency_contexts": contexts, "active_dependency_edges": edges,
        "pending_conda_system_closure": json.loads(CARRIER_REPORT.read_bytes())["eos"]["abi_and_dependencies"],
        "artifact_head_requests": len(requests), "artifact_downloads": 0, "installs": 0,
        "protected_grader_invocations": 0, "model_turns": 0,
    }))
    print(f"Verified {len(chosen)} dependencies, reused {len(available)} archives, quoted {sum(sizes.values())} bytes.")


if __name__ == "__main__":
    main()
