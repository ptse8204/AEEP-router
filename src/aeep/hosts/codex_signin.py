"""Operator-terminal login with Codex-owned credentials and bounded setup accounting."""

from __future__ import annotations

import asyncio
import sys
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from typing import Literal

from ..assessment.boundary import BoundaryProbeDefinition
from ..assessment.identity import verify_dependencies
from ..assessment.models import AssessmentLimits, ConformanceProbeRequest, content_digest
from ..assessment.service import AssessmentService
from ..errors import ConfigurationError
from ..models import StrictModel
from .workers import binding_from_config


class WorkerSignInResult(StrictModel):
    schema_version: Literal["assessment.worker-signin.v1"] = "assessment.worker-signin.v1"
    operation_id: str
    request_id: str
    worker_digest: str
    process_completed: bool
    cleanup_confirmed: bool | None = None
    conformance_verified: bool = False


async def signin_worker(service: AssessmentService, request_id: str) -> WorkerSignInResult:
    # Never call from MCP or a captured agent subprocess. Codex renders login
    # directly in the operator's terminal; AEEP never receives that stream.
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ConfigurationError('worker sign-in requires an operator terminal without output capture')
    repository = service.repository
    request = ConformanceProbeRequest.model_validate(repository.get('conformance_request', request_id))
    if request.operation is not None:
        raise ConfigurationError('worker inspection cannot authorize another sign-in')
    repository.authorize(request)
    verify_dependencies(request.executable_dependencies)
    definition = BoundaryProbeDefinition.model_validate(repository.get('boundary_probe_definition', request.mapping_digest))
    config = definition.executor.managed_host_config()
    if config.adapter_id.split(":", 1)[0] not in {"codex-app-server", "codex-exec"}:
        raise ConfigurationError("device login requires an explicitly configured Codex adapter")
    worker = binding_from_config(config.managed_worker)
    if (content_digest(definition) != request.mapping_digest or worker is None
            or worker.digest() != request.worker_digest or worker.credential_volume is None):
        raise ConfigurationError('worker sign-in requires the reviewed protected credential volume')
    operation = 'signin:' + request.plan_id
    repository.reserve(request, operation, AssessmentLimits(max_operations=1, max_elapsed_seconds=330), stage='worker_signin')
    started = time.perf_counter()
    process: asyncio.subprocess.Process | None = None
    result = WorkerSignInResult(operation_id=operation, request_id=request.plan_id,
                               worker_digest=worker.digest(), process_completed=False)
    try:
        with tempfile.TemporaryDirectory(prefix='aeep-signin-') as temporary:
            security = worker.prepare_security(Path(temporary))
            argv = worker.argv(('login', '--device-auth'), execution_id=operation, security_path=security)
            async with asyncio.timeout(300):
                # Inherited descriptors are deliberate: no pipes, captured output,
                # credential files, desktop cache or model invocation.
                process = await asyncio.create_subprocess_exec(*argv, stdin=None, stdout=None, stderr=None)
                while process.returncode is None:
                    repository.authorize(request)
                    await asyncio.sleep(.2)
                repository.authorize(request)
                result.process_completed = process.returncode == 0
    finally:
        try:
            try:
                result.cleanup_confirmed = await asyncio.wait_for(worker.cleanup(operation), timeout=20)
            finally:
                await stop_process(process)
        finally:
            repository.finish_operation(operation, elapsed_seconds=time.perf_counter() - started)
            repository.put('worker_signin', operation, result)
    if not result.process_completed or result.cleanup_confirmed is not True:
        raise ConfigurationError('Codex worker sign-in did not complete or cleanup is unconfirmed; no conformance was established')
    return result


async def stop_process(process: asyncio.subprocess.Process | None) -> None:
    if process is not None and process.returncode is None:
        with suppress(ProcessLookupError):
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            with suppress(ProcessLookupError):
                process.kill()
            await asyncio.wait_for(process.wait(), timeout=2)
