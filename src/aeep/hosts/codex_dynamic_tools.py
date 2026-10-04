"""Operator-bound Codex client tools; the model supplies only task arguments."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import math
import re
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema.validators import validator_for

from ..errors import ConfigurationError
from ..models import SideEffect
from ..registry import validate_json
from .codex_invocation import contract_digest


@dataclass(frozen=True)
class DynamicCallContext:
    outer_attempt_digest: str
    call_digest: str
    action_id: str
    record_link: Callable[[str], None]


_call_context: ContextVar[DynamicCallContext | None] = ContextVar('aeep_codex_dynamic_call', default=None)


def current_dynamic_call() -> DynamicCallContext | None:
    return _call_context.get()


class CodexDynamicTools:
    """A fixed, reviewed client-tool binding installed by operator composition.

    No handler, authority, path or command can be registered through JSON or a
    model call. The checker resolves current backend/scope/access evidence; a
    declared digest alone is not enforcement evidence.
    """

    def __init__(self, *, namespace: str, tools: list[dict[str, Any]],
                 identity: dict[str, Any], max_calls: int, timeout_seconds: float,
                 call: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
                 check: Callable[[], str]) -> None:
        if (not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', namespace)
                or type(max_calls) is not int or not 1 <= max_calls <= 32
                or isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
                or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 300
                or not tools or len(tools) > 32):
            raise ConfigurationError('invalid dynamic task binding limits')
        self.namespace = namespace
        self._tools = copy.deepcopy(tools)
        self._by_name = {item.get('name'): item for item in self._tools}
        if len(self._by_name) != len(tools) or any(
            not isinstance(name, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', name)
            or set(item) - {'name', 'description', 'inputSchema', 'outputSchema'}
            or not isinstance(item.get('description'), str)
            or not isinstance(item.get('inputSchema'), dict)
            for name, item in self._by_name.items()
        ):
            raise ConfigurationError('invalid dynamic task declarations')
        for item in self._tools:
            for key in ('inputSchema', 'outputSchema'):
                if key in item:
                    try:
                        validator_for(item[key]).check_schema(item[key])
                    except Exception as exc:
                        raise ConfigurationError('invalid dynamic task schema') from exc
        self.max_calls, self.timeout_seconds = max_calls, timeout_seconds
        self._call, self._check = call, check
        self.identity = copy.deepcopy(identity)
        try:
            self.approval_ceiling = SideEffect(identity["approval_ceiling"])
        except (KeyError, ValueError) as exc:
            raise ConfigurationError("dynamic task binding requires an operator ceiling") from exc
        for field in ('worker_digest', 'native_backend_digest', 'implementation_digest'):
            if not isinstance(identity.get(field), str) or not re.fullmatch(r'[a-f0-9]{64}', identity[field]):
                raise ConfigurationError('dynamic task binding requires exact worker/backend/implementation')
        self.digest = contract_digest({'namespace': namespace, 'tools': self._tools,
            'identity': self.identity, 'max_calls': max_calls, 'timeout_seconds': timeout_seconds})

    def definition(self) -> dict[str, Any]:
        return copy.deepcopy({'namespace': self.namespace, 'tools': self._tools,
            'identity': self.identity, 'max_calls': self.max_calls, 'timeout_seconds': self.timeout_seconds})

    @staticmethod
    def implementation_digest() -> str:
        root = Path(__file__).parents[1]
        names = ('hosts/codex_dynamic_tools.py', 'hosts/codex_app_server.py',
                 'hosts/codex_invocation.py', 'assessment/tools.py',
                 'assessment/fixed_helper.py', 'router.py', 'profiles.py', 'tasks.py',
                 'assessment/applicability.py')
        return contract_digest({name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                                for name in names})

    @staticmethod
    def profile_behavior(service: Any) -> str | None:
        """Operator composition pin for an activated profile; never an approval.

        Set identity['capability_profile_behavior_digest'] to this value before
        storing/reviewing a dynamic binding. Fresh scopes with the same limits
        can share behavior; their IDs, expiry and used allowances stay separate.
        Exact profile review and activation are rechecked on every resolution.
        """
        from ..assessment.repository import AssessmentRepository
        from ..models import TaskScope
        from ..profiles import load
        from ..tasks import require_activation
        activation_id = service.router._task_activation_digest
        if activation_id is None:
            return None
        activation = require_activation(service.router, activation_id)
        if activation.scope_digest != service.router._task_scope_digest:
            raise ConfigurationError('dynamic profile activation scope differs')
        if activation.capability_profile_digest is None:
            return None
        profile = load(service.router, activation.capability_profile_digest)
        scope = TaskScope.model_validate(AssessmentRepository(service.router.store).get(
            'task_scope', activation.scope_digest))
        return contract_digest({
            'profile': profile.model_dump(mode='json', exclude={'profile_id', 'scope_digest'}),
            'scope_contract': scope.model_dump(mode='json', exclude={'scope_id', 'expires_at'}),
        })

    @classmethod
    def _require_profile_behavior(cls, service: Any, identity: dict[str, Any]) -> None:
        current = cls.profile_behavior(service)
        expected = identity.get('capability_profile_behavior_digest')
        if current != expected or (expected is not None and (
                not isinstance(expected, str) or re.fullmatch(r'[a-f0-9]{64}', expected) is None)):
            raise ConfigurationError('dynamic capability profile behavior is missing or changed')

    def require_reviewed_binding(self, repository: Any, *, worker: Any,
                                 service: Any, artifact: Any = None) -> str:
        """Resolve the actual protected composition, not a supplied success bit."""
        from ..assessment.repository import AssessmentRepository
        from ..economic.prepared import executor_fingerprint
        from ..models import ExecutorKind, TaskScope
        from .codex_sandbox import NativeSandboxConfig, native_backend_digest
        self._require_profile_behavior(service, self.identity)
        document = repository.get('codex_dynamic_tools', self.digest)
        with repository.store._lock:
            review = repository.store._connection.execute(
                'SELECT revoked FROM assessment_reviews WHERE digest=?', (self.digest,)).fetchone()
        if (document != self.definition() or review is None or review[0]
                or worker.digest() != self.identity['worker_digest']
                or self.implementation_digest() != self.identity['implementation_digest']
                or self.identity.get('artifact') != (artifact.model_dump(mode='json') if artifact else None)):
            raise ConfigurationError('dynamic task composition is unreviewed or changed')
        scope = TaskScope.model_validate(AssessmentRepository(service.router.store).get(
            'task_scope', service.router._task_scope_digest))
        limits = self.identity.get('scope_limits', {})
        if (self.identity.get('executor_fingerprints') != scope.executor_fingerprints
                or scope.max_attempts > limits.get('max_attempts', 0)
                or scope.max_attempt_seconds > limits.get('max_attempt_seconds', 0)):
            raise ConfigurationError('dynamic task scope or executor binding differs')
        backends = {}
        for spec in service.router.registry.all():
            if spec.id not in scope.executor_fingerprints:
                continue
            if scope.executor_fingerprints[spec.id] != executor_fingerprint(spec):
                raise ConfigurationError('dynamic task executor fingerprint differs')
            service.router._require_active_spec(spec, configuration_only=True)
            boundary = NativeSandboxConfig.model_validate(spec.config.get('native_sandbox', {}))
            if spec.kind is not ExecutorKind.COMMAND or not spec.config.get('argv_literal') or not boundary.single_process:
                raise ConfigurationError('dynamic task composition requires the exact native single-process backend')
            boundary.validate_single_process()
            backends[spec.id] = native_backend_digest(boundary)
        if set(backends) != set(scope.executor_fingerprints):
            raise ConfigurationError('dynamic task scope executor is missing')
        if not backends or contract_digest(backends) != self.identity['native_backend_digest']:
            raise ConfigurationError('dynamic native backend binding differs')
        return self.digest

    @classmethod
    def task_service(cls, service: Any, *, namespace: str, identity: dict[str, Any],
                     max_calls: int, timeout_seconds: float,
                     check: Callable[[], str], artifact_context: Any = None,
                     artifact_worker: Any = None, execution_id: str | None = None,
                     authorized_call: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]] | None = None) -> CodexDynamicTools:
        from ..assessment.fixed_helper import FixedHelperService
        from ..mcp.server import AEEPToolService
        if not isinstance(service, (AEEPToolService, FixedHelperService)) or service.profile != 'task' or service.router._task_scope_digest is None:
            raise ConfigurationError('dynamic task tools require a bound task-only service')
        cls._require_profile_behavior(service, identity)
        if identity.get("approval_ceiling") != service.approved_side_effect.value:
            raise ConfigurationError("dynamic task service ceiling differs")
        from ..assessment.repository import AssessmentRepository
        from ..models import TaskScope
        scope = TaskScope.model_validate(AssessmentRepository(service.router.store).get("task_scope", service.router._task_scope_digest))
        if 'task_scope_digest' in identity:
            raise ConfigurationError('task scope is execution authority, not immutable behavior')
        if (identity.get('executor_fingerprints') != scope.executor_fingerprints
                or scope.max_attempts > identity.get('scope_limits', {}).get('max_attempts', 0)
                or scope.max_attempt_seconds > identity.get('scope_limits', {}).get('max_attempt_seconds', 0)):
            raise ConfigurationError('dynamic scope exceeds reviewed behavior')
        if max_calls > scope.max_attempts or timeout_seconds > scope.max_attempt_seconds:
            raise ConfigurationError("dynamic task limits exceed scope")
        declared = service.list_tools()
        def current() -> str:
            cls._require_profile_behavior(service, identity)
            for spec in service.router.registry.all():
                if spec.id in scope.executor_fingerprints:
                    service.router._require_active_spec(spec, configuration_only=True)
            if service.list_tools() != declared or service.approved_side_effect.value != identity["approval_ceiling"]:
                raise ConfigurationError('dynamic task declarations changed')
            return check()
        exposed = copy.deepcopy(declared)
        task_call = authorized_call or service.call
        handler = task_call
        if any(value is not None for value in (artifact_context, artifact_worker, execution_id)):
            if (artifact_context is None or artifact_worker is None or not execution_id
                    or artifact_context.config.artifact is None
                    or artifact_worker.digest() != identity['worker_digest']):
                raise ConfigurationError('dynamic artifact binding is incomplete')
            artifact = artifact_context.config.artifact
            for item in exposed:
                item['inputSchema'] = {'type': 'object', 'properties': {}, 'additionalProperties': False}
                item['description'] += ' Uses the operator-bound input artifact and writes the bound output artifact; no path arguments.'
            async def artifact_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
                # Existing transport names/limits are operator config, never model paths.
                data = await artifact_worker.artifact(execution_id, name=artifact.input_name,
                    limit=artifact.max_bytes, timeout=min(10, timeout_seconds))
                task_input = copy.deepcopy(artifact_context.request.input)
                task_input[artifact.input_field] = data['data']
                result = await task_call(name, task_input)
                outcome = result.get('structuredContent')
                if not isinstance(outcome, dict):
                    raise ConfigurationError('dynamic artifact task outcome unavailable')
                output = outcome.get('output')
                if outcome.get('ok') is True:
                    if not isinstance(output, dict) or not isinstance(output.get(artifact.output_field), str):
                        raise ConfigurationError('dynamic artifact task output unavailable')
                    await artifact_worker.artifact(execution_id, name=artifact.output_name,
                        limit=artifact.max_bytes, data=output[artifact.output_field], timeout=min(10, timeout_seconds))
                # Return existing receipt/recovery evidence without opaque artifact bytes.
                public = copy.deepcopy(outcome)
                public['output'] = None
                return {'isError': result.get('isError') is True, 'structuredContent': public,
                    'content': [{'type': 'text', 'text': json.dumps(public, separators=(',', ':'), allow_nan=False)}]}
            handler = artifact_call
        return cls(namespace=namespace, tools=exposed, identity=identity,
                   max_calls=max_calls, timeout_seconds=timeout_seconds,
                   call=handler, check=current)

    def verify(self, expected_digest: str, worker_digest: str) -> None:
        current = contract_digest({"namespace": self.namespace, "tools": self._tools,
            "identity": self.identity, "max_calls": self.max_calls, "timeout_seconds": self.timeout_seconds})
        if (self._by_name != {item["name"]: item for item in self._tools}
                or current != self.digest or self.digest != expected_digest or self.identity['worker_digest'] != worker_digest
                or self._check() != self.digest):
            raise ConfigurationError('environment verification unavailable: dynamic task binding differs')

    def declarations(self) -> list[dict[str, Any]]:
        return [{'type': 'namespace', 'name': self.namespace,
                 'description': 'Operator-scoped task tools.', 'tools': [
            {'type': 'function', 'name': item['name'], 'description': item['description'],
             'inputSchema': copy.deepcopy(item['inputSchema']), 'deferLoading': False}
            for item in self._tools]}]

    def inventory(self) -> dict[str, str]:
        return {f'dynamic:{self.namespace}:{name}': contract_digest(item)
                for name, item in self._by_name.items()}


class DynamicToolSession:
    """One turn's bounded callback authority, with identity established by replies."""

    def __init__(self, binding: CodexDynamicTools, *, worker_digest: str,
                 expected_digest: str, approved_side_effect: SideEffect, max_bytes: int, deadline: float,
                 outer_attempt_id: str = "diagnostic", journal: Any = None) -> None:
        binding.verify(expected_digest, worker_digest)
        if binding.approval_ceiling.rank > approved_side_effect.rank:
            raise ConfigurationError("dynamic task binding exceeds outer approval ceiling")
        self.binding, self.worker_digest, self.expected_digest = binding, worker_digest, expected_digest
        self.max_bytes, self.deadline = max_bytes, deadline
        self.outer_attempt_digest = contract_digest({"attempt_id": outer_attempt_id})
        self.journal = journal
        self.thread_id: str | None = None
        self.turn_id: str | None = None
        self._ready = asyncio.Event()
        self._calls: set[str] = set()
        self.closed = False
        self.tools_called: set[str] = set()
        self.tools_succeeded: set[str] = set()
        self.evidence: list[dict[str, Any]] = []

    def bind_thread(self, thread_id: str) -> None:
        self.thread_id = thread_id

    def bind_turn(self, turn_id: str) -> None:
        self.turn_id = turn_id
        self._ready.set()

    def close(self) -> None:
        self.closed = True
        self._ready.set()

    async def call(self, params: dict[str, Any]) -> dict[str, Any]:
        required = {'arguments', 'callId', 'threadId', 'turnId', 'tool'}
        if (not required <= params.keys() or set(params) - required - {'namespace'}
                or any(not isinstance(params[k], str) or not 1 <= len(params[k]) <= 200
                       for k in required - {'arguments'})
                or params.get('namespace') != self.binding.namespace
                or params['tool'] not in self.binding._by_name
                or not isinstance(params['arguments'], dict)
                or params['callId'] in self._calls or len(self._calls) >= self.binding.max_calls):
            raise ConfigurationError('invalid dynamic task call')
        self._calls.add(params['callId'])
        async with asyncio.timeout_at(self.deadline):
            await self._ready.wait()
            if self.closed or params['threadId'] != self.thread_id or params['turnId'] != self.turn_id:
                raise ConfigurationError('dynamic task call identity differs')
            self.binding.verify(self.expected_digest, self.worker_digest)
            validate_json(params['arguments'], self.binding._by_name[params['tool']]['inputSchema'],
                          label='dynamic task arguments')
            call_digest = contract_digest({key: params[key]
                for key in ('threadId', 'turnId', 'callId', 'namespace', 'tool')})
            def link(reference: str) -> None:
                if not isinstance(reference, str) or not re.fullmatch(r'[a-f0-9]{64}', reference):
                    raise ConfigurationError('invalid dynamic callback evidence reference')
                self.evidence.append({'call_digest': call_digest, 'evidence_ref': reference})
                if self.journal is not None:
                    self.journal.append('message.received', 'dynamic-link:' + reference,
                        action_digest=call_digest, evidence_ref=reference)
            context = DynamicCallContext(self.outer_attempt_digest, call_digest,
                'dynamic_' + call_digest, link)
            if self.journal is not None:
                self.journal.append('action.started', 'dynamic-start:' + call_digest, action_digest=call_digest)
            token = _call_context.set(context)
            try:
                async with asyncio.timeout(self.binding.timeout_seconds):
                    self.tools_called.add(params['tool'])
                    result = await self.binding._call(params['tool'], copy.deepcopy(params['arguments']))
            finally:
                _call_context.reset(token)
            if not isinstance(result, dict):
                raise ConfigurationError("dynamic task result must be an object")
            envelope = result.get('structuredContent', {})
            receipts = envelope.get('receipts', []) if isinstance(envelope, dict) else []
            self.evidence.append({'call_digest': contract_digest({key: params[key]
                for key in ('threadId', 'turnId', 'callId', 'namespace', 'tool')}),
                'task_scope_digest': envelope.get('task_scope_digest') if isinstance(envelope, dict)
                    and isinstance(envelope.get('task_scope_digest'), str)
                    and re.fullmatch(r'[a-f0-9]{64}', envelope['task_scope_digest']) else None,
                'receipt_ids': [item['receipt_id'] for item in receipts[:32]
                    if isinstance(item, dict) and isinstance(item.get('receipt_id'), str)
                    and re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}', item['receipt_id'])]
                    if isinstance(receipts, list) else []})
            self.binding.verify(self.expected_digest, self.worker_digest)
            output_schema = self.binding._by_name[params["tool"]].get("outputSchema")
            if output_schema is not None:
                validate_json(result.get("structuredContent"), output_schema, label="dynamic task output")
            text = json.dumps(result, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
            if len(text.encode()) > self.max_bytes:
                raise ConfigurationError('dynamic task result exceeds frame limit')
            if self.journal is not None:
                self.journal.append('action.completed', 'dynamic-complete:' + call_digest, action_digest=call_digest)
            if result.get('isError') is not True:
                self.tools_succeeded.add(params['tool'])
            return {'success': result.get('isError') is not True,
                    'contentItems': [{'type': 'inputText', 'text': text}]}


def _profile_binding_self_check() -> None:
    """Data-only invariant: an unprofiled service cannot claim a profile pin."""
    from types import SimpleNamespace
    service = SimpleNamespace(router=SimpleNamespace(_task_activation_digest=None))
    CodexDynamicTools._require_profile_behavior(service, {})
    try:
        CodexDynamicTools._require_profile_behavior(service, {
            'capability_profile_behavior_digest': '0' * 64})
    except ConfigurationError:
        return
    raise AssertionError('unprofiled service accepted a profile behavior claim')


if __name__ == '__main__':
    _profile_binding_self_check()
