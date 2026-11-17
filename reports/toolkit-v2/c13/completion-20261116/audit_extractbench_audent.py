"""Bind one real document and its protected calibration inputs to the upstream scorer."""

import json
import re
import subprocess
import tomllib
from collections import deque
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit

from audit_document_corpus_capacity import EXTRACT, SCORER
from check_linux_install import HERE, WORK
from jsonschema import Draft202012Validator
from packaging.markers import Marker
from packaging.tags import compatible_tags, cpython_tags
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version
from stage_repository_transport import digest, read

from aeep.assessment.models import content_digest
from aeep_toolkit.benchmarks import BenchmarkTask, asset_path
from aeep_toolkit.install_runtime import file_digest

ROOT = WORK / "extractbench-audent-source"
TASK = "short--13f--audent-global-2025q4-65363d4890"
INVENTORY = WORK / "document-corpus-metadata/extract-manifest"
INVENTORY_PIN = "0452463e5b1be2c627c0b7d1a076531f0fd301b3297affdb7d9613735bc04840"
TREE_PIN = "ef884eff9090b054b256e58038c1f740c352d1c0b2ce9bdfc62ba9155841b5de"
LOCK_PIN = "af5277a55f234ba8b251e341685e2a5a61391f5064ffc85639dcee23b244d574"
SEC_PIN = "13ab2878f69c6f70e055da03e10523be7fee6a24a3c5db558a83921e2c3c3953"
LAYOUT_PIN = "8c3e746ef99b714388dc77232baa5570171c2ad8d8d3d1cbbbea8db558444d51"
SEC_FILING = "https://www.sec.gov/Archives/edgar/data/1834874/000208585326000296/"
ASSETS = {
    "instruction.md": ("agent", "instruction"),
    "environment/document.pdf": ("agent", "input"),
    "environment/schema.json": ("agent", "input"),
    "environment/Dockerfile": ("protected", "environment"),
    "task.toml": ("protected", "environment"),
    "solution/expected.json": ("protected", "oracle"),
    "solution/solve.sh": ("protected", "oracle"),
    "tests/reference.test.json": ("protected", "oracle"),
    "tests/verifier.py": ("protected", "verifier"),
    "tests/test.sh": ("protected", "verifier"),
    "tests/Dockerfile": ("protected", "environment"),
}
ROW = re.compile(r"^\s*(\d+)\s+.*?\b([A-Z0-9]{9})\s+([\d,]+)\s+([\d,]+)\s+SH\b")


def task_assets():
    inventory = json.loads(read(INVENTORY, INVENTORY_PIN))
    pins = inventory["tasks"][TASK]["files"]
    prefix = f"tasks/{TASK}/"
    tree = json.loads(read(ROOT / "publisher-tree.json", TREE_PIN))
    sizes = {
        row["path"].removeprefix(prefix): row["size"]
        for row in tree if row["type"] == "file" and row["path"].startswith(prefix)
    }
    if ASSETS.keys() != pins.keys() or pins.keys() != sizes.keys():
        raise ValueError("upstream task inventory changed")
    task = BenchmarkTask(
        task_id=TASK, domain="document-data", difficulty="unknown",
        output_paths=["output.json"], upstream_score="native_reward",
        assets=[
            {"path": name, "role": role, "sha256": pins[name], "bytes": sizes[name]}
            for name, (_, role) in ASSETS.items()
        ],
    )
    paths = {asset.path: asset_path(ROOT / ASSETS[asset.path][0], asset) for asset in task.assets}
    for directory in ("agent", "protected"):
        actual = {
            path.relative_to(ROOT / directory).as_posix()
            for path in (ROOT / directory).rglob("*") if not path.is_dir()
        }
        if actual != {name for name, (where, _) in ASSETS.items() if directory == where}:
            raise ValueError("private input or grader root includes an unexpected asset")
    return task, paths


def confirm_filing(layout, sec_rows, expected):
    parsed = [ROW.match(line) for line in layout.splitlines()]
    numbers = [int(row[1]) for row in parsed if row]
    pdf = [
        [row[2], int(row[3].replace(",", "")), int(row[4].replace(",", ""))]
        for row in parsed if row
    ]
    oracle = [
        [entry[key] for key in ("cusip", "value_usd", "shares_or_principal_amount")]
        for entry in expected["holdings"]
    ]
    if (
        numbers != list(range(1, 53)) or pdf != sec_rows or pdf != oracle
        or len({entry[0] for entry in pdf}) != len(pdf)
        or sum(entry[1] for entry in pdf) != expected["table_value_total_usd"]
        or len(pdf) != expected["table_entry_total"]
        or "Audent Global Asset Management, LLC" not in layout or "12-31-2025" not in layout
    ):
        raise ValueError("published filing, source PDF and protected reference disagree")
    return len(pdf)


def controls(expected, validator):
    no_row, changed_amount, duplicate = (deepcopy(expected) for _ in range(3))
    no_row["holdings"].pop()
    changed_amount["holdings"][0]["value_usd"] += 1
    duplicate["holdings"][-1] = deepcopy(duplicate["holdings"][0])
    scenarios = {"oracle": expected, "missing-row": no_row, "changed-value": changed_amount, "repeated-row": duplicate}
    encoded = {}
    for name, document in scenarios.items():
        validator.validate(document)
        encoded[name + ".json"] = json.dumps(document, sort_keys=True).encode() + b"\n"
    encoded["malformed.json"] = b'{"holdings":'
    if len({digest(value) for value in encoded.values()}) != len(encoded):
        raise ValueError("grading controls are not distinct")
    return encoded


def target_environment():
    return {
        "implementation_name": "cpython", "implementation_version": "3.13.15",
        "os_name": "posix", "platform_machine": "aarch64",
        "platform_python_implementation": "CPython", "platform_system": "Linux",
        "python_full_version": "3.13.15", "python_version": "3.13", "sys_platform": "linux",
        "platform_version": "", "platform_release": "",
    }


def required_packages(lock):
    """Project the publisher's base wheel closure with no project extras or dev tools."""
    packages = {row["name"]: row for row in lock["package"]}
    if len(packages) != len(lock["package"]):
        raise ValueError("runtime projection requires exactly one resolved version per package")
    project = packages["llama-extract-bench"]
    if project["source"] != {"editable": "."}:
        raise ValueError("upstream lock's project binding differs")
    environment = target_environment()
    pending = deque([(project["name"], "")])
    seen = set()
    while pending:
        name, extra = pending.popleft()
        if (name, extra) in seen:
            continue
        seen.add((name, extra))
        package = packages[name]
        edges = package["optional-dependencies"][extra] if extra else package.get("dependencies", ())
        for edge in edges:
            if set(edge) - {"name", "marker", "extra"}:
                raise ValueError("upstream dependency requires variant-aware selection")
            if "marker" in edge and not Marker(edge["marker"]).evaluate({**environment, "extra": extra}):
                continue
            pending.append((edge["name"], ""))
            pending.extend((edge["name"], item) for item in edge.get("extra", ()))
    return [
        packages[name] for name in sorted({name for name, _ in seen} - {project["name"]})
    ]


def declared_wheels(packages):
    platforms = [f"manylinux_2_{minor}_aarch64" for minor in range(41, 16, -1)]
    platforms.append("manylinux2014_aarch64")
    supported = list(cpython_tags((3, 13), ["cp313"], platforms))
    supported.extend(compatible_tags((3, 13), "cp313", platforms))
    precedence = {tag: index for index, tag in reversed(tuple(enumerate(supported)))}
    wheels, missing = {}, []
    for package in packages:
        if "registry" not in package["source"]:
            raise ValueError("dependency outside the publisher lock's registry")
        candidates = []
        for item in package.get("wheels", ()):
            url = urlsplit(item["url"])
            if url.scheme != "https" or url.hostname != "files.pythonhosted.org":
                raise ValueError("wheel source escaped the reviewed package registry")
            name = Path(url.path).name
            project, version, _, tags = parse_wheel_filename(name)
            if project != canonicalize_name(package["name"]) or version != Version(package["version"]):
                raise ValueError("wheel name differs from its locked release")
            matches = {tag: precedence[tag] for tag in tags if tag in precedence}
            if matches:
                candidates.append((min(matches.values()), name, item))
        key = package["name"]
        if not candidates:
            missing.append({"package": key, "version": package["version"]})
            continue
        _, filename, best = min(candidates, key=lambda entry: entry[:2])
        wheels[key] = {"version": package["version"], "filename": filename, **best}
    return wheels, missing


def cached_wheels(wheels):
    wanted = {item["filename"]: item for item in wheels.values()}
    selected = {}
    base = WORK.parent
    filenames = subprocess.check_output(
        ["rg", "--files", "--hidden", "--glob", "*.whl", str(base)],
        text=True, timeout=30,
    )
    for filename in sorted(filenames.splitlines()):
        path = Path(filename)
        if path.name not in wanted or path.name in selected or path.resolve() != path:
            continue
        item = wanted[path.name]
        if path.stat().st_size == item["size"] and "sha256:" + file_digest(path) == item["hash"]:
            selected[path.name] = path.relative_to(base).as_posix()
    return selected


def audit():
    task, files = task_assets()
    layout = read(ROOT / "tmp/pdfs/source-layout.txt", LAYOUT_PIN).decode()
    official = json.loads(read(ROOT / "sec-table-normalized.json", SEC_PIN))
    if official["source"] != SEC_FILING + "xslForm13F_X02/infotable.xml":
        raise ValueError("reference evidence identifies a different filing")
    expected_bytes = files["solution/expected.json"].read_bytes()
    expected = json.loads(expected_bytes)
    raw_ref = json.loads(files["tests/reference.test.json"].read_bytes())
    schema = json.loads(files["environment/schema.json"].read_bytes())
    if raw_ref["expected_output"] != expected or raw_ref["data_schema"] != schema:
        raise ValueError("upstream reference and submitted output contract differ")
    rows = confirm_filing(layout, official["rows"], expected)
    calibrated = controls(expected, Draft202012Validator(schema))
    calibrated["oracle.json"] = expected_bytes
    wheel_pins, unavailable = declared_wheels(required_packages(
        tomllib.loads(read(ROOT / "scorer-uv.lock", LOCK_PIN).decode())
    ))
    available = cached_wheels(wheel_pins)
    score = json.loads((HERE / "document-corpus-metadata.json").read_bytes())
    family_digest = next(asset.sha256 for asset in task.assets if asset.path == "environment/schema.json")
    # Keep every case in this shared schema out of formal stages after calibration.
    manifest = json.loads(read(INVENTORY, INVENTORY_PIN))
    related = [
        name for name, entry in manifest["tasks"].items()
        if entry["files"]["environment/schema.json"] == family_digest
    ]
    return {
        "schema_version": "aeep.c13.extractbench-development-intake.v1",
        "dataset_revision": EXTRACT,
        "scorer_revision": SCORER,
        "publisher_declared_license": score["extractbench"]["declared_license"],
        "native_score": ["extract_unified_value_f1", "perfect"],
        "sec_filing": SEC_FILING + "0002085853-26-000296-index.htm",
        "sec_reuse_policy": "https://www.sec.gov/about/webmaster-frequently-asked-questions",
        "source_match": {
            "protected_expected_output_equals_solution": True,
            "source_tuples_matching_sec_and_protected_reference": rows,
            "fields": ["cusip", "value_usd", "shares_or_principal_amount"],
            "source_pdf_pages": 2,
            "sec_table_sha256": SEC_PIN,
            "pdf_text_receipt_sha256": LAYOUT_PIN,
        },
        "task": task.model_dump(mode="json"),
        "asset_bytes_by_root": {
            name: sum(asset.bytes for asset in task.assets if ASSETS[asset.path][0] == name)
            for name in ("agent", "protected")
        },
        "control_pins": {name: digest(data) for name, data in calibrated.items()},
        "no_file_control": "missing_output",
        "infrastructure_control": "reference_unavailable",
        "control_scope": "A schema preflight. Native grader behavior has not been measured.",
        "development_only": True,
        "related_schema_family": {"sha256": family_digest, "members": sorted(related)},
        "approved_task_disclosure": False,
        "native_evaluator_executions": 0,
        "formal_cases_adopted": 0,
        "declared_base_runtime": {
            "target": "CPython 3.13 Linux ARM64 glibc 2.41",
            "publisher_lock_sha256": LOCK_PIN,
            "wheel_count": len(wheel_pins),
            "wheel_archive_bytes": sum(item["size"] for item in wheel_pins.values()),
            "confirmed_cached_exact_wheels": available,
            "missing_wheel_archive_bytes": sum(
                item["size"] for item in wheel_pins.values() if item["filename"] not in available
            ),
            "unavailable_compatible_wheels_in_lock": unavailable,
            "lock_projection_sha256": content_digest(wheel_pins),
            "scope": "Complete declared base runtime. Minimal offline scorer imports still need review.",
        },
    }, calibrated, wheel_pins


if __name__ == "__main__":
    record, _, _ = audit()
    print(json.dumps(record, indent=2, sort_keys=True))
