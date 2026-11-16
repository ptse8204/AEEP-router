"""Read the footprint of approved retained runtimes without starting them."""

import json
import re
import shutil
import stat
import subprocess
from collections import defaultdict
from pathlib import Path

from check_linux_install import DOCKER, FROZEN, HERE, ROOT, SOCKET, WORK, get, put

from aeep.assessment.models import content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import digest as installation_digest
from aeep_toolkit.install_runtime import file_digest, parse_installation

REBIND = HERE.parent / "managed-comparison-20261115/offline-evidence/source-stack-rebinding.json"
FOOTPRINT = WORK / "retained-runtime-footprint.json"


def pin(ref):
    path = Path(ref["path"])
    if not path.is_relative_to(ROOT) or file_digest(path) != ref["sha256"]:
        raise ValueError("retained evidence binding changed")
    return get(path)


def lookup(path, kind, ref):
    if not Path(path).is_relative_to(ROOT):
        raise ValueError("store is outside the bound workspace")
    with ReceiptStore(path, read_only=True) as store:
        row = AssessmentRepository(store).get(kind, ref)
    if content_digest(row) != ref:
        raise ValueError("runtime ledger record does not match its bound digest")
    return row


def engine(*args):
    return subprocess.run(
        [DOCKER, "--host", f"unix://{SOCKET}", *args],
        env={},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=35,
        check=True,
    ).stdout


def logical_files(path):
    if path.resolve() != path or not path.is_relative_to(WORK.parent) or not path.exists():
        return {"state": "unavailable"}
    entries = [path] if path.is_file() else path.rglob("*")
    total = 0
    seen = set()
    links = 0
    for entry in entries:
        metadata = entry.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            links += 1
            continue
        if stat.S_ISREG(metadata.st_mode):
            inode = metadata.st_dev, metadata.st_ino
            if inode not in seen:
                seen.add(inode)
                total += metadata.st_size
    return {
        "state": "measured",
        "regular_file_logical_bytes": total,
        "regular_file_inodes": len(seen),
        "symlinks_not_followed": links,
    }


def measures():
    frozen = get(REBIND)
    source = verification_source_digest(FROZEN)
    readiness = get(HERE / "readiness-audit.json")
    essentials = get(HERE / "beta-package-audit.json")
    previous_allocation = essentials["initial_checks"]["private_runtime_allocated_bytes_before_removal"]
    assert frozen["implementation_source"] == readiness["implementation_source"] == source
    assert readiness["stack_completion_ref"] == frozen["stack_completion_ref"]
    assert set(readiness["components"]) == set(frozen["records"])
    proof = {
        key: row["value"]["proof"]
        for key, row in frozen["records"].items()
        if "proof" in row["value"]
    }
    native = {"essentials-interrupted-residue": WORK / "beta-runtime"}
    images = defaultdict(set)

    def retain(component, digest):
        if re.fullmatch(r"sha256:[a-f0-9]{64}", digest) is None:
            raise ValueError("an image identity must be exact")
        images[digest].add(component)

    for kind in ("mcpmark", "mcp-universe"):
        for image in pin(proof[kind]["review"])["images"].values():
            retain(kind, image["id"])
    toolhive = pin(proof["toolhive"]["review"])
    retain("toolhive", toolhive["retained_image_id"])
    native["toolhive-binary"] = Path(toolhive["toolhive"])
    assert file_digest(native["toolhive-binary"]) == toolhive["toolhive_sha256"]
    for name in ("aflow", "evoagentx"):
        review = pin(proof[name]["review"])
        retain(name, review[name + "_image"])
        retain(name, review["stopped_proxy"]["Image"])
        for digest in review["worker_images"].values():
            retain(name, digest)
    for verifier in proof["skillsbench"]["verifiers"].values():
        retain("skillsbench-reviewed-grader", pin(verifier["review"])["image"]["image_id"])
    native["agent-framework"] = Path(pin(proof["agent-framework"]["review"])["runtime"])
    graph_path = Path(proof["langgraph"]["review"]["path"]).with_name("installation.json")
    graph_plan = get(graph_path)
    assert (
        installation_digest(parse_installation(graph_plan))
        == pin(proof["langgraph"]["review"])["installation_digest"]
    )
    native["langgraph-and-agent-skill-eval"] = Path(graph_plan["destination"])
    scanner = proof["skill-scanner"]
    record = lookup(scanner["store"], "toolkit_workflow_scan", scanner["scan_ref"])
    scan = lookup(scanner["store"], "toolkit_scanner_runtime", record["definition_ref"])
    retain("skill-scanner", scan["environment"]["container_image"])
    catalog = proof["skillrank"]
    record = lookup(catalog["catalog_store"], "toolkit_workflow_catalog", catalog["search_ref"])
    skillrank = lookup(
        catalog["catalog_store"], "toolkit_catalog_runtime", record["definition_ref"]
    )
    retain("skillrank-catalog", skillrank["environment"]["container_image"])
    workflow = frozen["records"]["workflow-document-data"]["value"]["request"]
    telemetry = pin(workflow["telemetry"][0]["observation_review"])["retained_runtime"]
    langfuse_services = {}
    for name, container in sorted(telemetry["containers"].items()):
        raw = engine(
            "container", "inspect", "--format", "{{.Id}}\t{{.Image}}\t{{.State.Status}}", container
        )
        identity, image_id, status = raw.strip().split("\t", 2)
        if identity != container or image_id not in telemetry["service_image_allowed_ids"][name]:
            raise ValueError("retained Langfuse container is outside its reviewed identity")
        langfuse_services[name] = status
        retain("langfuse", image_id)
    native["langfuse-coordinator"] = Path(telemetry["installed_runtime"])
    native_measurements = {name: logical_files(path) for name, path in native.items()}

    observed = {}
    for digest, components in sorted(images.items()):
        try:
            raw = engine(
                "image",
                "inspect",
                "--format",
                "{{.Id}}\t{{.Size}}\t{{.Architecture}}\t{{json .RootFS.Layers}}",
                digest,
            )
        except subprocess.CalledProcessError:
            observed[digest] = {"components": sorted(components), "state": "unavailable"}
            continue
        identity, size, machine, layers = raw.strip().split("\t", 3)
        if identity != digest:
            raise ValueError("retained Docker identity drifted")
        observed[digest] = {
            "components": sorted(components),
            "state": "measured",
            "engine_image_size_bytes": int(size),
            "machine": machine,
            "layer_count": len(json.loads(layers)),
        }
    selected_sizes = [
        row["engine_image_size_bytes"] for row in observed.values() if row["state"] == "measured"
    ]
    contained_volumes = set(
        engine(
            "volume",
            "ls",
            "--filter",
            f"label=com.docker.compose.project={telemetry['project']}",
            "--format",
            "{{.Name}}",
        ).splitlines()
    )
    volume_sizes = {}
    if contained_volumes:
        try:
            disk = engine("system", "df", "--verbose")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            disk = ""
        inside = False
        for line in disk.splitlines():
            if line == "Local Volumes space usage:":
                inside = True
                continue
            if inside and line.endswith("space usage:"):
                break
            columns = line.split(maxsplit=2)
            if inside and len(columns) == 3 and columns[0] in contained_volumes:
                volume_sizes[columns[0]] = columns[2]
    return {
        "schema_version": "aeep.c13.retained-runtime-footprint.v1",
        "observed_stack_completion_ref": frozen["stack_completion_ref"],
        "source_revision_records": len(frozen["records"]),
        "accepted_checks": frozen["verified_required_checks"],
        "host_free_bytes": shutil.disk_usage(WORK).free,
        "native_runtime_files": native_measurements,
        "reviewed_essentials_archive_bytes": essentials["archive_bytes"],
        "historical_essentials_installed_allocated_bytes": previous_allocation,
        "langfuse_retained_container_states": langfuse_services,
        "identified_image_count": len(observed),
        "measured_image_count": len(selected_sizes),
        "images": observed,
        "image_total_gross_engine_size_bytes": sum(selected_sizes),
        "image_largest_engine_size_bytes": max(selected_sizes, default=None),
        "langfuse_project_volume_count": len(contained_volumes),
        "langfuse_project_volume_measurements_as_printed": volume_sizes,
        "langfuse_volume_sizes_unavailable_count": len(contained_volumes - volume_sizes.keys()),
        "model_calls": 0,
        "resources_started_or_removed": 0,
        "limits": [
            "Reported image sizes include their parent layers. Distinct IDs can share data. This is a gross image measure.",
            "Native file lengths exclude system Python and symbolic-link targets. File lengths do not measure APFS allocation.",
            "The optional scope covers image identities recoverable from selected accepted records, plus explicitly bound native runtimes.",
            "Managed worker, cache, evidence-retention, and temporary-file allocation across the complete stack remain unmeasured.",
            "No estimate of reclaimable host bytes, recurring maintenance labor, or production capacity.",
        ],
    }


if __name__ == "__main__":
    record = measures()
    put(FOOTPRINT.with_name("retained-runtime-footprint-final.json"), record)
    print(json.dumps({key: value for key, value in record.items() if key != "images"}, indent=2))
