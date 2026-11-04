"""SkillRank local-registry CLI bridge; run only inside a reviewed offline worker."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

SOURCE_REVISION = "5216bae9149b4ff8a7f9e014b6889fb094cee8e1"
VERSION = "0.1.5"
BINARY = Path("/opt/aeep-skillrank")


def query(mode: str, value: str) -> dict[str, str]:
    if (
        mode not in {"search", "show"}
        or not isinstance(value, str)
        or not 1 <= len(value) <= 256
        or value.startswith("-")
        or "://" in value
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
        or (
            mode == "show"
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", value)
            is None
        )
    ):
        raise ValueError("catalog query must be bounded metadata, never CLI flags or a URL")
    return {"mode": mode, "value": value}


def lookup(request: dict[str, Any], workspace: Path) -> dict[str, Any]:
    if set(request) != {
        "binary_sha256",
        "catalog_sha256",
        "catalog_base64",
        "implementation_source",
        "query",
    }:
        raise ValueError("invalid catalog request envelope")
    for key in ("binary_sha256", "catalog_sha256", "implementation_source"):
        if not isinstance(request[key], str) or re.fullmatch("[a-f0-9]{64}", request[key]) is None:
            raise ValueError("invalid catalog source fingerprint")
    selected = query(**request["query"])
    binary = BINARY
    if (
        binary.is_symlink()
        or hashlib.sha256(binary.read_bytes()).hexdigest() != request["binary_sha256"]
    ):
        raise ValueError("selected SkillRank binary changed")
    if not isinstance(request["catalog_base64"], str) or len(request["catalog_base64"]) > 1500000:
        raise ValueError("catalog payload exceeds bound")
    data = base64.b64decode(request["catalog_base64"], validate=True)
    if len(data) > 1024**2 or hashlib.sha256(data).hexdigest() != request["catalog_sha256"]:
        raise ValueError("selected catalog data changed")
    entries = json.loads(data)
    if not isinstance(entries, list) or not 1 <= len(entries) <= 256:
        raise ValueError("catalog must contain a bounded reviewed entry list")
    workspace.mkdir(mode=0o700, parents=True, exist_ok=True)
    home = workspace / "home"
    home.mkdir(mode=0o700)
    catalog = workspace / "catalog.json"
    catalog.write_bytes(data)
    catalog.chmod(0o444)
    env = {
        "HOME": str(home),
        "SKILLRANK_HOME": str(home / ".skillrank"),
        "CI": "1",
        "SKILLRANK_NO_UPDATE_CHECK": "1",
        "SKILLRANK_API_URL": "http://127.0.0.1:18899",
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
    }

    def call(arguments: list[str]) -> subprocess.CompletedProcess[bytes]:
        completed = subprocess.run(
            [str(binary), *arguments],
            env=env,
            cwd=workspace,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=5,
        )
        if len(completed.stdout) + len(completed.stderr) > 500000:
            raise ValueError("catalog response exceeds its bound")
        return completed

    version = call(["--version"])
    if version.returncode != 0 or version.stdout.decode().strip() != "skillrank " + VERSION:
        raise ValueError("upstream CLI version differs")
    server = subprocess.Popen(
        [str(binary), "serve", "--host", "127.0.0.1", "--port", "18899", "--catalog", str(catalog)],
        env=env,
        cwd=workspace,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    stopped = False
    try:
        # These are bounded service-readiness probes, not task retries.
        for _attempt in range(5):
            ready = call(["search", "aeep-catalog-readiness", "--json"])
            if ready.returncode == 0:
                break
            if server.poll() is not None:
                raise ValueError("upstream registry exited during startup")
            time.sleep(0.05)
        else:
            raise ValueError("upstream registry did not become ready")
        completed = call([selected["mode"], selected["value"], "--json"])
        if (
            completed.returncode == 1
            and selected["mode"] == "show"
            and b"not found" in completed.stderr
        ):
            result, status = None, "not_found"
        elif completed.returncode == 0:
            result, status = json.loads(completed.stdout), "completed"
        else:
            raise ValueError("upstream catalog lookup failed")
    finally:
        if server.poll() is None:
            server.terminate()
        try:
            server.wait(timeout=2)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=2)
        stopped = server.poll() is not None
    return {
        "component": "skillrank",
        "source_revision": SOURCE_REVISION,
        "version": VERSION,
        "binary_sha256": request["binary_sha256"],
        "catalog_sha256": request["catalog_sha256"],
        "implementation_source": request["implementation_source"],
        "status": status,
        "result": result,
        "server_stopped": stopped,
        "provider_claims_are_not_scan_or_usefulness_evidence": True,
    }


def main() -> None:
    raw = sys.stdin.buffer.read(1800001)
    if len(raw) > 1800000:
        raise ValueError("catalog request exceeds its bound")
    with tempfile.TemporaryDirectory(prefix="aeep-catalog-", dir="/tmp") as folder:
        print(json.dumps(lookup(json.loads(raw), Path(folder)), allow_nan=False))


if __name__ == "__main__":
    main()
