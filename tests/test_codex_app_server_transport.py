from __future__ import annotations

import sys
from pathlib import Path

import pytest

from aeep.errors import ConfigurationError
from aeep.hosts import CodexAppServerTransport, CodexProtocolError

FAKE = Path(__file__).parent / "fixtures" / "fake_codex_app_server.py"


def argv(scenario: str = "success") -> tuple[str, ...]:
    return (sys.executable, "-u", str(FAKE), "--scenario", scenario)


@pytest.mark.asyncio
async def test_transport_handshake_requests_and_clean_shutdown():
    transport = CodexAppServerTransport(argv(), request_timeout=2)
    await transport.start()
    account = await transport.request("account/read", {"refreshToken": False})
    process = transport._process
    assert transport.protocol_version == "fixture-app-server/2"
    assert account["account"]["type"] == "chatgpt"
    assert process is not None and process.returncode is None
    await transport.close()
    assert process.returncode == 0


def test_executable_path_and_optional_digest_are_validated(tmp_path):
    with pytest.raises(ConfigurationError, match="executable file"):
        CodexAppServerTransport((str(tmp_path / "missing"),))
    with pytest.raises(ConfigurationError, match="digest mismatch"):
        CodexAppServerTransport(argv(), executable_sha256=f"sha256:{'0' * 64}")


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["malformed", "oversized", "duplicate-response"])
async def test_transport_fails_closed_on_invalid_frames(scenario: str):
    transport = CodexAppServerTransport(
        argv(scenario), max_message_bytes=1024, request_timeout=2
    )
    try:
        if scenario == "duplicate-response":
            await transport.request("account/read", {})
            with pytest.raises(CodexProtocolError):
                await transport.request("account/rateLimits/read", {})
        else:
            with pytest.raises(CodexProtocolError):
                await transport.request("model/list", {})
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_unknown_server_request_receives_error_without_deadlock():
    transport = CodexAppServerTransport(argv("unknown-request"), request_timeout=2)
    await transport.start()
    await transport.request("turn/start", {"threadId": "fixture", "input": []})
    await transport.close()


@pytest.mark.asyncio
async def test_process_disconnect_is_deterministic():
    transport = CodexAppServerTransport(argv("disconnect"), request_timeout=2)
    await transport.start()
    with pytest.raises(CodexProtocolError, match="exited"):
        await transport.request("turn/start", {"threadId": "fixture", "input": []})
    await transport.close()
