"""Proposed one-shot contained bootstrap; no Cisco import or host execution.

The future exact review must bind this file and its JSON input. Preparation
checks substitute the import and filesystem; they are not containment evidence.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import socket
import sys
from pathlib import Path

KNOWN_DEPENDENCIES = {
    "anyio", "jsonschema", "mcp", "opentelemetry", "packaging",
    "psutil", "pydantic", "yaml",
}


def protocol_check(expected_file: str, expected_sha256: str) -> dict:
    path = Path(expected_file)
    if (not path.is_absolute()
            or path.parts[-4:] != ("src", "aeep", "assessment", "container_worker.py")
            or not re.fullmatch(r"[a-f0-9]{64}", expected_sha256)):
        return {"passed": False, "category": "INVALID_REVIEWED_INPUT"}
    try:
        if path.is_symlink() or path.resolve() != path:
            return {"passed": False, "category": "PROTOCOL_SOURCE_DRIFT"}
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
            return {"passed": False, "category": "PROTOCOL_SOURCE_DRIFT"}
        module = importlib.import_module("aeep.assessment.container_worker")
        if Path(module.__file__).resolve() != path:
            return {"passed": False, "category": "PROTOCOL_IMPORT_PATH_MISMATCH"}
    except ModuleNotFoundError as error:
        name = (error.name or "").split(".", 1)[0]
        return {
            "passed": False, "category": "MISSING_RUNTIME_DEPENDENCY",
            "missing_module": name if name in KNOWN_DEPENDENCIES else "other",
        }
    except BaseException:
        # Never persist exception text, traceback, environment or file contents.
        return {"passed": False, "category": "PROTOCOL_IMPORT_FAILED"}
    return {"passed": True, "category": "PROTOCOL_IMPORT_VERIFIED",
            "protocol_sha256": expected_sha256}


def containment_checks(expected_file: str) -> dict:
    assert os.getuid() == 65534
    status = Path("/proc/self/status").read_text()
    assert "CapEff:\t0000000000000000" in status and "NoNewPrivs:\t1" in status
    source = Path(expected_file).parents[2]
    mounts = {}
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        fields = line.split()
        mounts[fields[4]] = set(fields[5].split(","))
    for package in ("aeep", "aeep_toolkit"):
        assert "ro" in mounts.get(str(source / package), set())
    with Path("/tmp/aeep-owned-bootstrap-probe").open("x") as stream:
        stream.write("reviewed containment probe")
    assert not Path("/var/run/docker.sock").exists()
    assert not Path("/Users/edwintse/.codex").exists()
    assert Path("/opt/aeep-scanner/bin/python").is_file()
    try:
        connection = socket.create_connection(("1.1.1.1", 443), timeout=0.2)
    except OSError:
        pass
    else:
        connection.close()
        raise AssertionError("network boundary failed")
    return {
        "nonroot": True, "capabilities_dropped": True,
        "no_new_privileges": True, "both_package_mounts_read_only": True,
        "private_tmp_writable": True, "no_docker_socket": True,
        "no_host_credentials": True, "external_network_unreachable": True,
        "scanner_interpreter_present_not_executed": True,
    }


def main() -> None:
    result = {"passed": False, "upstream_executed": False}
    try:
        data = sys.stdin.buffer.read(16_385)
        assert len(data) <= 16_384
        payload = json.loads(data)
        assert set(payload) == {"protocol_file", "protocol_sha256"}
        assert all(type(value) is str for value in payload.values())
        checks = containment_checks(payload["protocol_file"])
        result.update(protocol_check(payload["protocol_file"], payload["protocol_sha256"]))
        result["checks"] = checks
    except BaseException:
        result["category"] = "BOOTSTRAP_OR_CONTAINMENT_FAILED"
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
