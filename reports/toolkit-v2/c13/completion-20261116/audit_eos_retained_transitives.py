"""Verify candidate retained wheels against EOS direct dependency metadata."""

import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from acquire_full_rebench_leads import ref
from audit_full_rebench_runtime_inputs import MARKERS, OUTPUT, cached_wheels
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version
from quote_rebench_runtime_artifacts import LOCIFY, quote_release
from stage_repository_transport import digest, encode, read, write

EOS = "Akkudoktor-EOS__EOS-459"
QUOTE_FILE = OUTPUT / "runtime-artifact-quote.json"
QUOTE_PIN = "708378f0dc00fd43c382c7512bb768bcacc12350db4bc36658819635bf06c64a"
RESULT = OUTPUT / "eos-retained-transitives-20261119.json"


def active_dependencies(direct):
    external = defaultdict(list)
    for parent, row in direct.items():
        for raw in row["requires_dist"]:
            requirement = Requirement(raw)
            if requirement.marker and not requirement.marker.evaluate(MARKERS):
                continue
            name = canonicalize_name(requirement.name)
            if name in direct:
                if not requirement.specifier.contains(direct[name]["version"], prereleases=True):
                    raise ValueError(f"published direct pins conflict: {parent} requires {name}")
            else:
                external[name].append((parent, requirement))
    return external


def matching_candidates(external, cache):
    for name, requirements in sorted(external.items()):
        retained = ((Version(version), paths) for (package, version), paths in cache.items()
                    if package == name and all(requirement.specifier.contains(version, prereleases=False)
                                               for _, requirement in requirements))
        versions = sorted(retained, key=lambda item: item[0], reverse=True)
        if versions:
            version, groups = versions[0]
            yield name, str(version), [path for paths in groups.values() for path in paths]


def verify_cache_candidate(item):
    name, version, paths = item
    expected = {}
    by_identity = {}
    for path in sorted(paths):
        checksum = digest(path.read_bytes())
        identity = (path.name, checksum)
        if path.name not in expected:
            expected[path.name] = checksum
            by_identity[identity] = path
    # Use the existing publisher lookup with an explicit file/hash allowlist.
    _, _, metadata = quote_release((LOCIFY, name, {
        "version": version, "locked_linux_arm64_wheels": expected,
    }))
    artifact = metadata["available"]
    path = by_identity.get((artifact["filename"], artifact["sha256"])) if artifact else None
    if path is None or artifact["bytes"] != path.stat().st_size:
        return name, {"version": version, "verified_wheel": None, "release_metadata": metadata}
    return name, {"version": version, "verified_wheel": ref(path), "release_metadata": metadata}


def main():
    if RESULT.exists():
        raise ValueError("retained wheel audit already has a result")
    direct = json.loads(read(QUOTE_FILE, QUOTE_PIN))["cases"][EOS]
    external = active_dependencies(direct)
    candidates = list(matching_candidates(external, cached_wheels()))
    if len(direct) != 18 or len(external) != 37 or len(candidates) > len(external):
        raise ValueError("expected source-bound direct dependency inventory changed")
    with ThreadPoolExecutor(max_workers=4) as pool:
        checked = dict(pool.map(verify_cache_candidate, candidates))
    verified_count = sum(row["verified_wheel"] is not None for row in checked.values())
    write(RESULT, encode({
        "schema_version": "aeep.c13.eos-retained-first-level-dependencies.v1",
        "case": EOS,
        "direct_metadata": ref(QUOTE_FILE),
        "driver": ref(Path(__file__).resolve()),
        "target": MARKERS,
        "direct_pins": len(direct),
        "first_level_constraints": {
            name: [{"package": parent, "requires": str(requirement)} for parent, requirement in requirements]
            for name, requirements in sorted(external.items())
        },
        "retained_candidates": checked,
        "publisher_verified_count": verified_count,
        "publisher_metadata_requests": len(checked),
        "without_cache_filename_match": sorted(external.keys() - checked.keys()),
        "scope": "Candidate wheel bytes only. Full transitive resolution and ABI execution remain open.",
        "artifacts_downloaded": 0,
        "packages_imported_or_executed": 0,
        "grader_invocations": 0,
        "model_turns": 0,
    }))
    print(f"Verified {verified_count} publisher file identities across {len(external)} first-level dependencies.")


if __name__ == "__main__":
    main()
