"""One-operation operator runner with a reviewed same-worker capacity successor. Importing never launches a host.

This is conformance bootstrapping, not a campaign or passing conformance record.
The operator registers the reviewed union factory before calling this function.
No credentials, login, capacity probe, review or grant creation occurs here.
"""
from __future__ import annotations

import asyncio
import math
import inspect
import time
from datetime import datetime, timezone
from pathlib import Path

from aeep.assessment.boundary import BoundaryProbe, BoundaryProbeDefinition
from aeep.assessment.destinations import require_destination
from aeep.assessment.identity import file_digest, verify_dependencies
from aeep.assessment.models import (
    AssessmentEnvironment, AssessmentLimits, ConformanceProbeRequest, content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.attempts import ExecutionAttempt
from aeep.errors import ConfigurationError
from aeep.execution import EventJournal, ExecutionEvidence
from aeep.hosts.codex_pair_inspection import ComposedPairDefinition, docker
from aeep.hosts.workers import binding_from_config
from aeep.models import ActionRequest, ExecutionReceipt, ExecutionStatus, RawExecution, SideEffect, StrictModel, new_id

SOURCE = 'ade3b4e98078a7a33a9a1ff9bf1a917063872dbc4eeba96d42ee33cec554a3d1'
RESET = datetime(2026, 10, 3, 20, 27, 22, tzinfo=timezone.utc)


class RunnerObservation(StrictModel):
    operation_id: str
    request_digest: str
    source_digest: str
    stage: str
    error_type: str | None
    cleanup_confirmed: bool
    host_receipt_digest: str | None
    outer_attempt_digests: list[str]
    outer_receipt_digests: list[str]
    elapsed_seconds: float
    full_conformance: bool = False


def pinned_factory(factory, dependencies):
    """Pin actual operator function and captured producer functions, boundedly.

    This is limited to ordinary functions/bound methods and their direct
    closure/default producer functions. Unknown callable objects are rejected.
    Exact file pins are implementation inputs, not a general Python callgraph
    proof. Launch from a fresh process with the reviewed source/import path.
    """
    pending = [factory]
    visited = set()
    while pending:
        function = pending.pop()
        if inspect.ismethod(function):
            function = function.__func__
        if not inspect.isfunction(function):
            raise ConfigurationError('operator factory must be an inspectable pinned function')
        if id(function) in visited:
            continue
        visited.add(id(function))
        if len(visited) > 16:
            raise ConfigurationError('operator factory dependency bound exceeded')
        path = Path(function.__code__.co_filename).resolve()
        if dependencies.get(str(path)) != file_digest(path):
            raise ConfigurationError('actual operator factory or producer source is not pinned')
        captured = [cell.cell_contents for cell in function.__closure__ or ()]
        captured.extend(function.__defaults__ or ())
        captured.extend((function.__kwdefaults__ or {}).values())
        for value in captured:
            if inspect.isfunction(value) or inspect.ismethod(value):
                pending.append(value)
            elif callable(value):
                raise ConfigurationError('uninspectable captured producer callable')


def _reviewed(repository, kind, identity, model):
    value = model.model_validate(repository.get(kind, identity))
    digest = content_digest(value)
    with repository.store._lock:
        row = repository.store._connection.execute(
            'SELECT revoked FROM assessment_reviews WHERE digest=?', (digest,)
        ).fetchone()
    if row is None or row[0]:
        raise ConfigurationError('exact operator review is absent or revoked')
    return value, digest


def prepare(service, request_id, definition_digest, action_digest, source_root):
    """Validate only; does not create requests, reserve allowance or launch hosts."""
    repository = service.repository
    request = ConformanceProbeRequest.model_validate(repository.get('conformance_request', request_id))
    if (request.schema_version != 'assessment.conformance-request.v4'
            or request.operation != 'composed_pair_inspection'
            or request.composed_model_turns != 1):
        raise ConfigurationError('one-turn composed request required; zero-turn requests are separate')
    with repository.store._lock:
        review = repository.store._connection.execute(
            'SELECT approved_at,revoked FROM assessment_reviews WHERE digest=?',
            (content_digest(request),)).fetchone()
    if (review is None or review[1]
            or datetime.fromisoformat(review[0]) < datetime(2026,9,30,20,43,34,tzinfo=timezone.utc)):
        raise ConfigurationError('fresh post-capacity-observation exact request review required')
    import aeep.router
    loaded_root = Path(aeep.router.__file__).resolve().parents[2]
    if Path(source_root).resolve() != loaded_root or verification_source_digest(loaded_root) != SOURCE:
        raise ConfigurationError('renew source review before using this runner')
    if request.executable_dependencies.get(str(Path(__file__).resolve())) != file_digest(Path(__file__).resolve()):
        raise ConfigurationError('runner executable is not pinned in this request')
    verify_dependencies(request.executable_dependencies)
    grant = repository.authorize(request)
    composite, digest = _reviewed(repository, 'composed_pair_definition', request.pair_definition_digest, ComposedPairDefinition)
    if digest != request.pair_definition_digest:
        raise ConfigurationError('composed definition hash differs')
    profiles = [spec for spec in (composite.control, composite.treatment)
                if binding_from_config(spec.managed_host_config().managed_worker).digest() == request.worker_digest]
    if len(profiles) != 1:
        raise ConfigurationError('selected worker profile is ambiguous')
    spec = profiles[0]
    config = spec.managed_host_config()
    registered = service.router.managed_hosts._factories.get(config.adapter_id.split(':',1)[0])
    pinned_factory(registered, request.executable_dependencies)
    if config.invocation is None or config.invocation.dynamic_tools_digest is None:
        raise ConfigurationError('operator dynamic binding required')
    binding = repository.get('codex_dynamic_tools', config.invocation.dynamic_tools_digest)
    if (content_digest(binding) != config.invocation.dynamic_tools_digest
            or binding.get('max_calls') != 1
            or binding.get('identity', {}).get('approval_ceiling') != 'read'):
        raise ConfigurationError('one-call READ callback behavior required')
    definition, digest = _reviewed(repository, 'boundary_probe_definition', definition_digest, BoundaryProbeDefinition)
    action, actual_action_digest = _reviewed(repository, 'composed_callback_action', action_digest, ActionRequest)
    policy = service.router._policy_for(action)
    if policy.fallback.enabled and policy.fallback.max_attempts != 1:
        raise ConfigurationError('operator policy must bound this probe to one host attempt')
    if (digest != definition_digest or actual_action_digest != action_digest
            or not {definition_digest, action_digest, config.invocation.dynamic_tools_digest}.issubset(request.definition_digests)
            or definition.name != 'callback_authority' or content_digest(definition.executor) != content_digest(spec)
            or action.capability != spec.capability or action.constraints.allowed_executor_ids != [spec.id]
            or not spec.idempotent or spec.side_effect.rank > SideEffect.READ.rank
            or config.approval_ceiling.rank > SideEffect.READ.rank
            or spec.estimate.cash.upper_bound_usd != 0
            or not math.isfinite(config.timeout_seconds) or not 0 < config.timeout_seconds <= 240):
        raise ConfigurationError('probe, action, ceiling or finite bounds differ')
    require_destination(spec, AssessmentEnvironment.model_validate(repository.get('environment', request.environment_digest)), grant)
    return request, definition, action, spec


def preserve_scoped(repository, scoped, action_id):
    """Copy exact action lineage before its owned store closes, including failures."""
    local = AssessmentRepository(scoped.store)
    with scoped.store._lock:
        attempts = scoped.store._connection.execute(
            'SELECT a.payload_json FROM execution_attempts a JOIN decisions d ON d.decision_id=a.decision_id WHERE d.action_id=? LIMIT 2',
            (action_id,)).fetchall()
        receipts = scoped.store._connection.execute(
            'SELECT payload_json FROM receipts WHERE action_id=? LIMIT 2', (action_id,)).fetchall()
    attempt_refs = []
    receipt_refs = []
    parsed = []
    for row in attempts:
        value = ExecutionAttempt.model_validate_json(row[0])
        attempt_refs.append(repository.put('conformance_outer_attempt', content_digest(value), value))
    for row in receipts:
        value = ExecutionReceipt.model_validate_json(row[0])
        receipt_refs.append(repository.put('conformance_host_receipt', content_digest(value), value))
        parsed.append(value)
        reference = value.metadata.get('execution_evidence_digest')
        if reference is not None:
            evidence = ExecutionEvidence.model_validate(local.get('execution_evidence', reference))
            repository.put('execution_evidence', content_digest(evidence), evidence)
    return attempt_refs, receipt_refs, parsed[0] if len(parsed) == 1 else None


async def confirm_cleanup(adapter):
    """Observe exact owned worker absence, not merely close() returning."""
    from aeep.assessment.containment import container_name
    process = adapter.transport._process
    if (process is not None and process.returncode is None) or adapter.transport._dynamic_tasks:
        return False
    worker = adapter._worker
    identity = adapter._worker_process_id
    if worker is None or identity is None:
        return False
    # Fixed argv/filter; this cannot enumerate unrelated containers or read logs.
    remaining = await docker(worker, 'ps', '-a', '--filter',
        'name=^/'+container_name(identity)+'$', '--format', '{{.ID}}')
    return remaining.strip() == ''


async def run_once(service, *, request_id, definition_digest, action_digest,
                   operation_id, source_root, fresh_database, capacity_confirmed=False):
    """Run one reviewed callback probe, retaining failure costs with no retries.

    capacity_confirmed is operator evidence, checked against the exact fresh
    same-worker observation. This function never creates or reviews requests.
    """
    if capacity_confirmed is not True:
        raise ConfigurationError('operator capacity confirmation required')
    capacity_path = Path(__file__).resolve().parents[1]/'worker1592-successor/capacity-refresh-composed-ready-ade3-result.json'
    if file_digest(capacity_path) != '202657d65e6075d455d8b8d441f8dcdf846710c7be60964183c7cf186f7c6d72':
        raise ConfigurationError('reviewed same-worker capacity observation changed')
    import json
    from datetime import timedelta
    refreshed = json.loads(capacity_path.read_text())
    current = refreshed['capacity']
    observed = datetime.fromisoformat(current['observed_at'].replace('Z','+00:00'))
    now = datetime.now(timezone.utc)
    if (not refreshed.get('cleanup_confirmed') or not refreshed.get('source_unchanged')
            or current.get('resource_id') != 'codex.self'
            or not current.get('windows')
            or any(window.get('exhausted') is not False or window.get('used_percent') != '3' for window in current['windows'])
            or not observed <= now < observed+timedelta(minutes=30)):
        raise ConfigurationError('fresh reviewed same-worker capacity not available')
    request, definition, action, spec = prepare(
        service, request_id, definition_digest, action_digest, source_root)
    if request.worker_digest != refreshed['worker_digest']:
        raise ConfigurationError('capacity observation belongs to a different worker')
    if operation_id != 'composed:'+request.plan_id:
        raise ConfigurationError('operation identity must uniquely bind this one-turn request')
    database = Path(fresh_database)
    if not database.is_absolute() or database.exists() or not database.parent.is_dir():
        raise ConfigurationError('operator-owned fresh scoped database required')
    repository = service.repository
    seconds = spec.managed_host_config().timeout_seconds
    # Existing canonical reserve rejects operation-id reuse before any effect.
    repository.reserve(request, operation_id, AssessmentLimits(
        max_operations=1, max_model_turns=1, max_elapsed_seconds=seconds+5,
        max_cash_usd=0), stage='composed_pair_inspection')
    started = time.perf_counter()
    deadline = asyncio.get_running_loop().time()+seconds
    scoped = None
    receipt = None
    probe = None
    adapter = None
    attempt_refs = []
    receipt_refs = []
    host_digest = None
    stage = 'scoped_setup'
    error_type = None
    cleanup_confirmed = False
    try:
        scoped = service.router._campaign_router([spec],
            plan_digest=content_digest(request), database=database)
        scoped._callback_conformance_identity = (request.plan_id, operation_id)
        adapter = scoped.managed_hosts.get(spec.managed_host_config().adapter_id)
        pinned_factory(adapter.dynamic_tools_factory, request.executable_dependencies)
        scoped._trial_deadline = deadline
        def recheck():
            repository.authorize(request)
            verify_dependencies(request.executable_dependencies)
            pinned_factory(adapter.dynamic_tools_factory, request.executable_dependencies)
            if asyncio.get_running_loop().time() >= scoped._trial_deadline:
                raise ConfigurationError('composed operation deadline exhausted')
        scoped._trial_check = recheck
        # This bootstrap reference names the exact worker, not passing composite
        # evidence. Native/worker controls remain in their normal adapters.
        scoped._trial_boundary_references = {spec.id: request.worker_digest}
        stage = 'runtime_identity'
        async with asyncio.timeout_at(scoped._trial_deadline):
            await scoped._resolve_host_identity(spec)
            identity = scoped.store.host_runtime_digests.get(spec.id)
            if identity is None:
                raise ConfigurationError('actual managed runtime identity unavailable')
            scoped.store.expected_host_runtime_digests[spec.id] = identity[1]
            stage = 'host_execution'
            outcome = await scoped.execute(action, approved_side_effect=SideEffect.READ)
        stage = 'receipt_verification'
        if len(outcome.receipts) != 1 or outcome.receipts[0].executor_id != spec.id:
            raise ConfigurationError('single selected host receipt required')
        receipt = outcome.receipts[0]
        host_digest = repository.put('conformance_host_receipt', content_digest(receipt), receipt)
        evidence = ExecutionEvidence.model_validate(AssessmentRepository(scoped.store).get(
            'execution_evidence', receipt.metadata.get('execution_evidence_digest')))
        # Keep the original complete journal even if the exact observation fails.
        repository.put('execution_evidence', content_digest(evidence), evidence)
        complete_calls = [event for event in evidence.events if event.kind == 'action.completed'
                          and event.source_id.startswith(('dynamic-complete:', 'adapter:dynamic-complete:'))]
        links = [event for event in evidence.events if event.source_id.startswith(('dynamic-link:', 'adapter:dynamic-link:'))]
        observed = {'callback_origin': 'native_app_server',
                    'native_callback_observed': bool(len(complete_calls) == len(links) == 1 and receipt.accounting.model_usage
                        and receipt.metadata.get('model_turn_count') == 1
                        and receipt.metadata.get('dynamic_cleanup_confirmed') is True)}
        if (not outcome.ok or receipt.status is not ExecutionStatus.SUCCESS
                or not evidence.complete or observed != definition.expected):
            raise ConfigurationError('actual callback observation failed; retained receipt and journal')
        journal = EventJournal(evidence.attempt_id)
        for event in evidence.events:
            if event.kind in {'execution.completed', 'execution.failed'}:
                continue
            journal.append(event.kind, 'adapter:'+event.source_id,
                action_digest=event.action_digest, evidence_ref=event.evidence_ref,
                accounting=event.accounting, accounting_mode=event.accounting_mode)
        journal.append('artifact.created', 'composed-observation', evidence_ref=content_digest(observed))
        journal.append('execution.completed', 'composed-terminal')
        canonical = journal.evidence(evidence.adapter, RawExecution(status=receipt.status,
            metadata={'host_runtime_digest': identity[1], 'boundary_digest': request.worker_digest}))
        evidence_digest = repository.put('execution_evidence', content_digest(canonical), canonical)
        probe = BoundaryProbe(probe_id=new_id('composed-probe'), name=definition.name,
            implementation_digest=definition_digest, worker_digest=request.worker_digest,
            execution_evidence_digest=evidence_digest, host_receipt_digest=host_digest, observed=observed)
        stage = 'observation_verified_pending_cleanup'
    except BaseException as exc:
        error_type = type(exc).__name__
        raise
    finally:
        try:
            try:
                if scoped is not None:
                    attempt_refs, receipt_refs, partial = preserve_scoped(repository, scoped, action.action_id)
                    if receipt is None:
                        receipt = partial
                        host_digest = receipt_refs[0] if len(receipt_refs) == 1 else None
            finally:
                # One shared cleanup budget fits the original seconds+5 reservation.
                async with asyncio.timeout_at(deadline+5):
                    if scoped is not None:
                        await scoped.close()
                    cleanup_confirmed = adapter is not None and await confirm_cleanup(adapter)
                if scoped is not None and not cleanup_confirmed:
                    raise ConfigurationError('owned host/worker cleanup unconfirmed')
        except BaseException as exc:
            stage = 'cleanup_unconfirmed'
            error_type = type(exc).__name__
            raise
        finally:
            elapsed = time.perf_counter()-started
            try:
                repository.put('composed_runner_result', operation_id, RunnerObservation(
                    operation_id=operation_id, request_digest=content_digest(request),
                    source_digest=SOURCE, stage=stage, error_type=error_type,
                    cleanup_confirmed=cleanup_confirmed, host_receipt_digest=host_digest,
                    outer_attempt_digests=attempt_refs, outer_receipt_digests=receipt_refs,
                    elapsed_seconds=elapsed))
            finally:
                repository.finish_operation(operation_id, elapsed_seconds=elapsed,
                    accounting=receipt.accounting if receipt is not None else None,
                    resources=receipt.actual_resources if receipt is not None else None)
    # No positive probe exists unless actual owned cleanup and accounting finish.
    if probe is None or not cleanup_confirmed:
        raise ConfigurationError('completed callback probe unavailable')
    repository.put('boundary_probe', probe.probe_id, probe)
    return probe
