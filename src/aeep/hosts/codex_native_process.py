"""Native owned command execution through the existing App Server transport."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import math
import os
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

import psutil

from ..errors import ConfigurationError
from .codex_app_server import (
    AppServerOptions,
    CodexAppServerTransport,
    CodexProtocolError,
    CodexRequestError,
)

READY = b'aeep-single-process-ready:'
# Fixed loaded code, never a mutable external helper executed by a persistent host.
SINGLE_PROCESS_GUARD = '''import os,resource,sys,json
if sys.platform!='darwin' or os.geteuid()==0: raise RuntimeError('unsupported single-process host')
if os.getpid()!=os.getpgrp() or os.getpid()!=os.getsid(0): raise RuntimeError('native command is not its session leader')
resource.setrlimit(resource.RLIMIT_NPROC,(0,0))
if resource.getrlimit(resource.RLIMIT_NPROC)!=(0,0): raise RuntimeError('process limit unavailable')
os.write(1,b'aeep-single-process-ready:'+str(os.getpid()).encode()+b'\\n')
if os.read(0,1)!=b'\\x00': raise RuntimeError('incomplete native command handshake')
os.execve(sys.argv[2],sys.argv[2:],json.loads(sys.argv[1]))
'''


def guard_digest() -> str:
    return hashlib.sha256(SINGLE_PROCESS_GUARD.encode()).hexdigest()


@dataclass
class NativeCommandResult:
    stdout: bytes
    stdout_total: int
    stderr: bytes
    stderr_total: int
    exit_code: int | None
    timed_out: bool
    stream_error: bool
    cleanup_incomplete: bool
    metrics: Any
    error_type: str = ""
    output_truncated: bool = False
    guard_stdout_bytes: int = 0


async def execute_single_process(boundary: Any, argv: list[str], environment: dict[str, str],
                                 stdin: bytes | None, timeout: float, max_output: int,
                                 observer: Any = None) -> NativeCommandResult:
    from ..executors.command import _monitor_process, _ProcessMetrics
    boundary.validate_single_process()
    if stdin is not None and len(stdin) > 1_048_576:
        raise ConfigurationError('single-process command input exceeds 1 MiB')
    if not argv or not argv[0].startswith('/'):
        raise ConfigurationError('single-process command requires an absolute executable')
    boundary.argv([])  # Exact launcher hash after the final dispatch authority check.
    transport = CodexAppServerTransport(
        (boundary.binary, 'app-server', '--stdio', *boundary.permission_overrides()),
        cwd=boundary.project_root, executable_sha256=boundary.binary_sha256,
        max_message_bytes=2_097_152, request_timeout=timeout + 3,
        options=AppServerOptions(experimental_api=True))
    stdout, stderr, prefix = bytearray(), bytearray(), bytearray()
    totals = {'stdout': 0, 'stderr': 0}
    ready = asyncio.Event()
    output_truncated = False
    started = time.monotonic()
    owned_target: psutil.Process | None = None
    guard_bytes = 0

    def notification(method: str, params: dict[str, Any]) -> None:
        if method != 'command/exec/outputDelta':
            return
        nonlocal output_truncated, owned_target, guard_bytes
        stream = params.get('stream')
        if (params.get('processId') != 'aeep-command' or stream not in totals
                or not isinstance(params.get('deltaBase64'), str)
                or type(params.get('capReached')) is not bool):
            raise CodexProtocolError('invalid or truncated native command notification')
        try:
            chunk = base64.b64decode(params['deltaBase64'], validate=True)
        except ValueError as exc:
            raise CodexProtocolError('invalid native output encoding') from exc
        if stream == 'stdout' and not ready.is_set():
            newline = chunk.find(b'\n')
            consumed = len(chunk) if newline < 0 else newline + 1
            prefix.extend(chunk[:consumed])
            if len(prefix) > 128 or not (READY.startswith(prefix) or prefix.startswith(READY)):
                raise CodexProtocolError('invalid native single-process readiness')
            if newline < 0:
                return
            identity = bytes(prefix[len(READY):-1])
            if (not identity.isdigit() or not 0 < int(identity) < 2**31
                    or transport._process is None):
                raise CodexProtocolError('invalid native command identity')
            candidate = psutil.Process(int(identity))
            server = psutil.Process(transport._process.pid)
            if (server not in candidate.parents()
                    or os.getpgid(candidate.pid) != candidate.pid
                    or os.getsid(candidate.pid) != candidate.pid):
                raise CodexProtocolError('native command ownership or session changed')
            owned_target = candidate
            guard_bytes = len(prefix)
            chunk = chunk[consumed:]
            ready.set()
        totals[stream] += len(chunk)
        target = stdout if stream == 'stdout' else stderr
        bounded = chunk[:max(0, max_output - len(target))]
        target.extend(bounded)
        if stream == 'stdout' and observer is not None:
            observer(bounded)
        if params['capReached']:
            output_truncated = True
            raise CodexProtocolError('native output capture limit reached')

    transport.subscribe(notification)
    stop = asyncio.Event()
    monitor = command_task = None
    timed_out = stream_error = cleanup_incomplete = False
    exit_code = None
    error_type = ""
    try:
        async with asyncio.timeout(timeout):
            await transport.start()
            assert transport._process is not None
            monitor = asyncio.create_task(_monitor_process(transport._process.pid, stop))
            command = [boundary.python_binary, '-I', '-c', SINGLE_PROCESS_GUARD,
                       json.dumps(environment, separators=(',', ':')), *argv]
            command_task = asyncio.create_task(transport.request('command/exec', {
                'command': command, 'processId': 'aeep-command', 'permissionProfile': 'aeep-native-task',
                'cwd': boundary.project_root, 'streamStdin': True, 'streamStdoutStderr': True,
                'outputBytesCap': max_output + 128,
                'timeoutMs': max(1, math.ceil((timeout - (time.monotonic() - started)) * 1000)),
            }))
            while not ready.is_set() and not command_task.done():
                transport._raise_if_failed()
                await asyncio.sleep(.01)
            if ready.is_set():
                await transport.request('command/exec/write', {'processId': 'aeep-command',
                    'deltaBase64': base64.b64encode(b'\x00' + (stdin or b'')).decode('ascii'),
                    'closeStdin': True})
            response = await asyncio.shield(command_task)
            if type(response.get('exitCode')) is not int or response.get('stdout') != '' or response.get('stderr') != '':
                raise CodexProtocolError('invalid native command response')
            exit_code = response['exitCode']
            if not ready.is_set():
                error_type = 'NATIVE_COMMAND_GUARD_FAILED'
                raise CodexProtocolError('native single-process guard did not become ready')
    except (TimeoutError, asyncio.CancelledError):
        timed_out = True
    except Exception as exc:
        stream_error = cleanup_incomplete = True
        error_type = ('NATIVE_OUTPUT_LIMIT' if output_truncated else error_type
                      or ('NATIVE_COMMAND_REJECTED' if isinstance(exc, CodexRequestError)
                          else 'NATIVE_COMMAND_PROTOCOL_FAILED'))
    finally:
        if timed_out or stream_error:
            try:
                await transport.request('command/exec/terminate', {'processId': 'aeep-command'}, timeout=1)
                if command_task is not None:
                    await asyncio.wait_for(asyncio.shield(command_task), timeout=1)
            except (Exception, asyncio.CancelledError):
                cleanup_incomplete = True
        await transport.close()  # Native connection EOF terminates its owned command.
        if owned_target is not None:
            try:
                if owned_target.is_running() and owned_target.status() != psutil.STATUS_ZOMBIE:
                    owned_target.kill()  # Creation-time handle, never a bare/reused PID.
                    await asyncio.to_thread(owned_target.wait, timeout=1)
                cleanup_incomplete = False
            except psutil.NoSuchProcess:
                cleanup_incomplete = False
            except psutil.Error:
                cleanup_incomplete = True
        if command_task is not None and not command_task.done():
            command_task.cancel()
        if command_task is not None:
            with suppress(Exception, asyncio.CancelledError):
                await command_task
        stop.set()
    metrics = await monitor if monitor is not None else _ProcessMetrics()
    return NativeCommandResult(bytes(stdout), totals['stdout'], bytes(stderr), totals['stderr'],
                               exit_code, timed_out, stream_error, cleanup_incomplete, metrics, error_type, output_truncated, guard_bytes)
