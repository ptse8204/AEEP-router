"""No-model filesystem probes for two locally configured Codex workers.

This verifies the CLI filesystem profile only. It cannot establish the model's
complete tool access, and never supplies authority for assessment or admission.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from ..errors import ConfigurationError
from ..hosts.codex_app_server import CodexAppServerTransport
from ..hosts.codex_invocation import (
    advertised_tools,
    inventory,
    isolated_config,
    worker_permissions,
)
from ..models import ManagedHostInvocation


async def probe_sessions(codex: Path) -> list[dict[str, Any]]:
    """Check empty sessions; inventory may start host-owned servers, never a model."""
    workers = []
    for role in ("baseline", "candidate"):
        entry: dict[str, Any] = {"role": role, "model_turns_started": 0, "available_tools": "unknown", "tool_boundary_verified": False}
        workers.append(entry)
        with TemporaryDirectory(prefix="aeep-session-probe-") as temporary:
            cwd = str(await asyncio.to_thread(Path(temporary).resolve))
            transport = CodexAppServerTransport((str(codex), "app-server"), cwd=cwd, max_message_bytes=16777216, request_timeout=25)
            try:
                async with asyncio.timeout(55):
                    entry["stage"] = "inventory"
                    catalog = await inventory(transport, cwd)
                    config = isolated_config(catalog, ManagedHostInvocation())
                    config.update(worker_permissions(writable=True))
                    entry["stage"] = "session"
                    response = await transport.request("thread/start", {"ephemeral": True, "cwd": cwd, "permissions": "aeep_assessment", "approvalPolicy": "never", "approvalsReviewer": "user", "config": config})
                    profile = response.get("activePermissionProfile")
                    entry.update(
                        protocol_version=transport.protocol_version,
                        cwd_acknowledged=response.get("cwd") == cwd,
                        profile_acknowledged=isinstance(profile, dict) and profile.get("id") == "aeep_assessment" and profile.get("extends") is None,
                        approvals_acknowledged=response.get("approvalPolicy") == "never" and response.get("approvalsReviewer") == "user",
                    )
                    entry["stage"] = "thread_inventory"
                    thread = response.get("thread")
                    if not isinstance(thread, dict) or not isinstance(thread.get("id"), str):
                        raise ConfigurationError("thread/start omitted thread identity")
                    tools = await advertised_tools(transport, thread["id"])
                    entry["advertised_tool_count"] = len(tools)
                    entry["stage"] = "complete"
            except Exception as exc:
                # Keep already-observed facts even when the next check fails.
                entry["error_type"] = type(exc).__name__
                entry["reason"] = str(exc) if isinstance(exc, ConfigurationError) else "Host request failed; no model turn was started."
            finally:
                await transport.close()
    return workers


def probe_workers(codex: Path) -> dict[str, Any]:
    codex = codex.resolve(strict=True)
    if not codex.is_file() or not os.access(codex, os.X_OK):
        raise ConfigurationError("select an executable Codex CLI")
    cat, touch = shutil.which("cat"), shutil.which("touch")
    if cat is None or touch is None:
        raise ConfigurationError("worker probes require local cat and touch executables")
    with codex.open("rb") as stream:
        executable_digest = hashlib.file_digest(stream, "sha256").hexdigest()
    started = time.monotonic()
    profile = worker_permissions(writable=True)
    def inline_toml(value: Any) -> str:
        return "{" + ",".join(json.dumps(key) + "=" + inline_toml(item) for key, item in value.items()) + "}" if isinstance(value, dict) else json.dumps(value)

    common = [str(codex), "sandbox"]
    for key, value in profile.items():
        common.extend(["-c", f"{key}={inline_toml(value)}"])
    common.extend(["-P", "aeep_assessment"])
    workers: list[dict[str, Any]] = []
    with TemporaryDirectory(prefix="aeep-conformance-") as root:
        base = Path(root)
        for role in ("baseline", "candidate"):
            (base / role).mkdir()
            (base / role / "canary").write_text("aeep controlled fixture\n", encoding="utf-8", newline="")
        for role, other in (("baseline", "candidate"), ("candidate", "baseline")):
            cwd = base / role
            probes = {
                "own_read": ([cat, str(cwd / "canary")], True),
                "own_write": ([touch, str(cwd / "created")], True),
                "other_read_denied": ([cat, str(base / other / "canary")], False),
                "other_write_denied": ([touch, str(base / other / "forbidden")], False),
            }
            results = {}
            for name, (command, allowed) in probes.items():
                try:
                    completed = subprocess.run([*common, "-C", str(cwd), "--", *command], cwd=cwd, capture_output=True, timeout=20, check=False)
                    passed = completed.returncode == 0 if allowed else completed.returncode != 0 and b"Operation not permitted" in completed.stderr
                    if name == "own_read":
                        passed = passed and completed.stdout == b"aeep controlled fixture\n"
                    if name == "own_write":
                        passed = passed and (cwd / "created").is_file()
                    if name == "other_write_denied":
                        passed = passed and not (base / other / "forbidden").exists()
                    results[name] = {"passed": passed, "returncode": completed.returncode}
                except subprocess.TimeoutExpired:
                    results[name] = {"passed": False, "timeout": True}
            workers.append({"role": role, "checks": results})
    return {
        "schema_version": "assessment.worker-filesystem-probe.v1",
        "codex_executable_sha256": executable_digest,
        "probe_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "profile": profile,
        "workers": workers,
        "filesystem_verified": all(check["passed"] for worker in workers for check in worker["checks"].values()),
        "network_verified": False,
        "tool_boundary_verified": False,
        "model_turns_started": 0,
        "elapsed_seconds": time.monotonic() - started,
        "scope": "CLI filesystem profile only; separate App Server and tool-access verification remains required.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sessions", action="store_true", help="Also inspect two empty App Server sessions; may start host-owned servers, never models.")
    args = parser.parse_args()
    report = probe_workers(args.codex)
    if args.sessions:
        report["sessions"] = asyncio.run(probe_sessions(args.codex.resolve(strict=True)))
    encoded = json.dumps(report, indent=2) + "\n"
    if args.output:
        # Never overwrite historical evidence.
        with args.output.open("x") as stream:
            stream.write(encoded)
    print(encoded, end="")
    if not report["filesystem_verified"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
