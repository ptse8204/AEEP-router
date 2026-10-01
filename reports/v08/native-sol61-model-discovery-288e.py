"""Read only sanitized model availability from the installed native App Server."""

import asyncio
import hashlib
import json
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_app_server import CodexAppServerTransport


ROOT = Path(__file__).resolve().parents[2]
SOURCE = "288e082274cf22631398ca404180f6b58cb27ed7d5654fec0420d1ee6a0a2782"
CODEX = Path("/Users/edwintse/.local/bin/codex").resolve()
OUTPUT = ROOT / "reports/v08/native-sol61-model-discovery-result-288e.json"


async def main() -> None:
    assert verification_source_digest(ROOT) == SOURCE
    assert not OUTPUT.exists()
    binary_digest = "sha256:" + hashlib.sha256(CODEX.read_bytes()).hexdigest()
    started = time.perf_counter()
    models = []
    seen_models = set()
    seen_cursors = set()
    error_type = None
    cleanup_confirmed = False
    protocol_version = None
    complete = False
    with tempfile.TemporaryDirectory(prefix="aeep-native-model-discovery-") as directory:
        transport = CodexAppServerTransport(
            (str(CODEX), "app-server", "-c", "mcp_servers={}", "-c", "features.apps=false"),
            environment_allowlist=("HOME", "CODEX_HOME", "PATH"), cwd=str(Path(directory).resolve()),
            executable_sha256=binary_digest, request_timeout=20)
        try:
            async with asyncio.timeout(30):
                cursor = None
                for _ in range(100):
                    params = {"includeHidden": True}
                    if cursor is not None:
                        params["cursor"] = cursor
                    payload = await transport.request("model/list", params, timeout=15)
                    protocol_version = transport.protocol_version
                    page = payload.get("data")
                    if not isinstance(page, list):
                        raise ValueError("model/list omitted data")
                    for item in page:
                        if not isinstance(item, dict):
                            continue
                        model_id = item.get("model") or item.get("id")
                        if not isinstance(model_id, str) or not model_id or model_id in seen_models:
                            continue
                        efforts = item.get("supportedReasoningEfforts")
                        names = sorted({entry["reasoningEffort"] for entry in efforts
                                        if isinstance(entry, dict) and isinstance(entry.get("reasoningEffort"), str)}) \
                            if isinstance(efforts, list) else []
                        models.append({"id": model_id, "reasoning_efforts": names})
                        seen_models.add(model_id)
                    next_cursor = payload.get("nextCursor")
                    if not isinstance(next_cursor, str) or not next_cursor:
                        complete = True
                        break
                    if next_cursor in seen_cursors:
                        raise ValueError("model/list cursor repeated")
                    seen_cursors.add(next_cursor)
                    cursor = next_cursor
                else:
                    raise ValueError("model/list exceeded page bound")
        except BaseException as exc:
            error_type = type(exc).__name__
        finally:
            try:
                await asyncio.wait_for(transport.close(), 5)
                cleanup_confirmed = not transport.running
            except BaseException as exc:
                error_type = error_type or type(exc).__name__
    sol = [item for item in models if item["id"] == "gpt-6.1-sol"]
    value = {"recorded_at": datetime.now(timezone.utc).isoformat(), "source_digest": SOURCE,
             "binary_sha256": binary_digest, "protocol_version": protocol_version,
             "method": "model/list", "include_hidden": True, "models": models,
             "complete": complete, "cleanup_confirmed": cleanup_confirmed,
             "error_type": error_type, "reviewed_model_present": len(sol) == 1,
             "reviewed_medium_present": len(sol) == 1 and "medium" in sol[0]["reasoning_efforts"],
             "process_wall_seconds": time.perf_counter() - started,
             "model_turns": 0, "assessment_grant_debit": 0,
             "auth_state": "unknown; no account/auth method or file read by diagnostic",
             "configuration": "ephemeral per-process MCP empty/apps disabled override; no global write",
             "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             "source_unchanged": verification_source_digest(ROOT) == SOURCE,
             "release_ready": False}
    with OUTPUT.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"complete": complete, "reviewed_model_present": value["reviewed_model_present"],
                      "cleanup_confirmed": cleanup_confirmed, "model_turns": 0}))


asyncio.run(main())
