"""Operator-composed fixed helper; common task audit, without route selection."""
from __future__ import annotations

import re
from collections.abc import Callable
from contextvars import ContextVar
from copy import deepcopy
from typing import Any

from ..economic.prepared import executor_fingerprint
from ..errors import ConfigurationError
from ..models import ActionConstraints, ActionRequest, ExecutorKind, SideEffect
from ..registry import validate_json
from ..router import Router

_assessment_router: ContextVar[Router | None] = ContextVar("aeep_assessment_router", default=None)


def current_assessment_router() -> Router | None:
    return _assessment_router.get()


class FixedHelperService:
    profile = "task"

    def __init__(self, router: Router, executor_id: str, *, task_scope: str,
                 declaration: dict[str, Any], check: Callable[[], str],
                 approved_side_effect: SideEffect = SideEffect.READ,
                 task_activation: str | None = None) -> None:
        self.router = router
        self.executor_id = executor_id
        self._check = check
        self._binding = check()
        if not isinstance(self._binding, str) or re.fullmatch(r"[a-f0-9]{64}", self._binding) is None:
            raise ConfigurationError("fixed helper requires an exact current authority digest")
        if task_activation is not None:
            from ..models import TaskScope
            from ..tasks import require_activation
            from .models import content_digest
            from .repository import AssessmentRepository
            activation = require_activation(router, task_activation)
            scope = TaskScope.model_validate(AssessmentRepository(router.store).get('task_scope', task_scope))
            if activation.scope_digest != content_digest(scope):
                raise ConfigurationError('fixed helper activation belongs to another task scope')
            if router._task_activation_digest not in {None, content_digest(activation)}:
                raise ConfigurationError('fixed helper cannot replace session activation')
            router._task_activation_digest = content_digest(activation)
        scope_ceiling = router.bind_task_scope(task_scope)
        self.approved_side_effect = min(approved_side_effect, scope_ceiling, key=lambda level: level.rank)
        spec = router.registry.get(executor_id)
        native = spec.config.get("native_sandbox", {})
        if (spec.kind is not ExecutorKind.COMMAND or not native.get("single_process")
                or not spec.config.get("argv_literal")):
            raise ConfigurationError("fixed callback requires the literal single-process native helper")
        self._fingerprint = executor_fingerprint(spec)
        if declaration.get("inputSchema") != spec.input_schema:
            raise ConfigurationError("fixed helper input schema differs from reviewed executor")
        self._declaration = deepcopy(declaration)
        self._require_current()

    def _require_current(self) -> None:
        if self.router._task_activation_digest is not None:
            from ..tasks import require_activation
            activation = require_activation(self.router, self.router._task_activation_digest)
            if activation.scope_digest != self.router._task_scope_digest:
                raise ConfigurationError('fixed helper activation scope changed')
            if activation.capability_profile_digest is not None:
                from ..profiles import load
                from .models import content_digest
                profile = load(self.router, activation.capability_profile_digest)
                if content_digest({'tools': [self._declaration]}) != profile.tool_schema_digest:
                    raise ConfigurationError('fixed helper declarations differ from the reviewed capability profile')
        if self._check() != self._binding:
            raise ConfigurationError("fixed helper campaign binding changed")
        spec = self.router.registry.get(self.executor_id)
        if executor_fingerprint(spec) != self._fingerprint:
            raise ConfigurationError("fixed helper fingerprint changed")
        self.router._require_task_scope(spec)

    def list_tools(self) -> list[dict[str, Any]]:
        self._require_current()
        return [deepcopy(self._declaration)]

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        from ..mcp.server import _tool_result

        self._require_current()
        if name != self._declaration["name"]:
            raise ConfigurationError("unknown fixed helper")
        validate_json(arguments, self._declaration["inputSchema"], label=name)
        spec = self.router.registry.get(self.executor_id)
        from ..hosts.codex_dynamic_tools import current_dynamic_call
        context = current_dynamic_call()
        request = ActionRequest(capability=spec.capability, input=arguments,
                                constraints=ActionConstraints(max_side_effect=self.approved_side_effect))
        if context is not None:
            request.action_id = context.action_id
        outcome = await self.router.execute_fixed(
            request,
            spec.id, approved_side_effect=self.approved_side_effect,
        )
        # Attempts and receipts are already durable before an external callback returns.
        result = self.router.task_outcome(outcome, approved_side_effect=self.approved_side_effect)
        self._require_current()
        return _tool_result(result.model_dump(mode="json"), is_error=not outcome.ok)


class AssessmentCallbackAuthority:
    """Supporting calls consume an existing outer reservation, never a second clock."""

    def __init__(self, assessment: Any, plan: Any, assessment_id: str,
                 operation_id: str, *, outer_router: Router, outer_attempt_id: str, binding_digest: str,
                 resolve_binding: Callable[[], str], max_calls: int, _conformance: bool = False) -> None:
        self.assessment, self.plan = assessment, plan
        self.assessment_id, self.operation_id = assessment_id, operation_id
        self.binding_digest, self.resolve_binding = binding_digest, resolve_binding
        self.max_calls = max_calls
        self._conformance = _conformance
        self.outer_router, self.outer_attempt_id = outer_router, outer_attempt_id
        from ..hosts.codex_invocation import contract_digest
        self.outer_attempt_digest = contract_digest({"attempt_id": outer_attempt_id})
        if (type(max_calls) is not int or not 1 <= max_calls <= 32
                or not isinstance(binding_digest, str) or re.fullmatch(r"[a-f0-9]{64}", binding_digest) is None):
            raise ConfigurationError("invalid callback authority binding")
        self.check()

    @classmethod
    def for_conformance(cls, assessment: Any, request: Any, operation_id: str, *,
                        outer_router: Router, outer_attempt_id: str, binding_digest: str,
                        resolve_binding: Callable[[], str], max_calls: int) -> AssessmentCallbackAuthority:
        from .models import ConformanceProbeRequest
        if (not isinstance(request, ConformanceProbeRequest)
                or request.schema_version != 'assessment.conformance-request.v4'
                or request.operation != 'composed_pair_inspection'):
            raise ConfigurationError('composed authority requires an exact v4 inspection request')
        return cls(assessment, request, request.plan_id, operation_id,
                   outer_router=outer_router, outer_attempt_id=outer_attempt_id,
                   binding_digest=binding_digest, resolve_binding=resolve_binding,
                   max_calls=max_calls, _conformance=True)

    def _require_reserved(self, connection: Any) -> None:
        import asyncio
        from datetime import timedelta

        from ..models import utc_now
        from .models import AssessmentOperation

        self.assessment.repository.authorize(self.plan)
        if self._conformance:
            row = None
            context_identity = getattr(self.outer_router, '_callback_conformance_identity', None)
            stage = 'composed_pair_inspection'
        else:
            row = connection.execute("SELECT state FROM assessment_jobs WHERE id=? AND plan_id=?",
                                     (self.assessment_id, self.plan.plan_id)).fetchone()
            context_identity = getattr(self.outer_router, '_callback_trial_identity', None)
            stage = 'trial' 
        reserved = connection.execute("SELECT state FROM assessment_operations WHERE id=?",
                                      (self.operation_id,)).fetchone()
        operation = AssessmentOperation.model_validate(
            self.assessment.repository.get("operation_start", self.operation_id))
        if (context_identity != (self.assessment_id, self.operation_id)
                or utc_now() < operation.started_at
                or utc_now() >= operation.started_at + timedelta(seconds=operation.reserved.max_elapsed_seconds)
                or (self.outer_router._trial_deadline is not None
                    and asyncio.get_running_loop().time() >= self.outer_router._trial_deadline)):
            raise ConfigurationError("callback trial identity or reservation deadline differs")
        if ((not self._conformance and (row is None or row[0] != "running"))
                or reserved is None or reserved[0] != "reserved"
                or operation.plan_id != self.plan.plan_id or operation.stage != stage
                or (self._conformance and operation.reserved.max_model_turns != self.plan.composed_model_turns)):
            raise ConfigurationError("callback requires a running reserved outer trial")

    def check(self) -> str:
        if self._conformance:
            from .identity import verify_dependencies
            from .models import content_digest
            verify_dependencies(self.plan.executable_dependencies)
            current = self.assessment.repository.get('conformance_request', self.plan.plan_id)
            if (content_digest(current) != content_digest(self.plan)
                    or self.binding_digest not in self.plan.definition_digests):
                raise ConfigurationError('composed request or callback definition differs')
        else:
            self.assessment._verify_dependencies(self.plan)
        from ..attempts import ExecutionAttemptState
        attempt = self.outer_router.store.get_execution_attempt(self.outer_attempt_id)
        if attempt is None or attempt.state is not ExecutionAttemptState.INVOKING:
            raise ConfigurationError("callback outer attempt is not invoking")
        if self.outer_router._trial_check is None:
            raise ConfigurationError("callback lacks controlled assessment trial")
        self.outer_router._trial_check()
        if self.resolve_binding() != self.binding_digest:
            raise ConfigurationError("callback effective binding changed")
        with self.assessment.router.store._lock:
            self._require_reserved(self.assessment.router.store._connection)
        return self.binding_digest

    async def call(self, service: Any, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        import hashlib

        from ..hosts.codex_dynamic_tools import current_dynamic_call
        from ..models import StrictModel
        from .models import content_digest

        context = current_dynamic_call()
        if context is None:
            raise ConfigurationError("callback lacks operator-installed call identity")
        self.check()
        if context.outer_attempt_digest != self.outer_attempt_digest:
            raise ConfigurationError("callback outer attempt differs")
        outer_digest = hashlib.sha256(self.operation_id.encode()).hexdigest()
        key = content_digest({"outer_operation": outer_digest, "call": context.call_digest})

        class Claim(StrictModel):
            outer_operation_digest: str
            outer_attempt_digest: str
            call_digest: str
            binding_digest: str
            task_scope_digest: str
            context_kind: str
            model_turn_allowance: int
            request_digest: str
            operation_reference: str
            outer_attempt_reference: str

        scope_digest = service.router._task_scope_digest
        if not isinstance(scope_digest, str) or re.fullmatch(r"[a-f0-9]{64}", scope_digest) is None:
            raise ConfigurationError("callback requires an exact execution task scope")
        repo = self.assessment.repository
        outer_attempt = self.outer_router.store.get_execution_attempt(self.outer_attempt_id)
        if outer_attempt is None:
            raise ConfigurationError('callback outer attempt disappeared')
        outer_reference = repo.put('callback_outer_attempt', content_digest(outer_attempt), outer_attempt)
        operation_reference = content_digest(repo.get('operation_start', self.operation_id))
        from ..models import TaskScope
        from .repository import AssessmentRepository
        scope = TaskScope.model_validate(AssessmentRepository(service.router.store).get('task_scope', scope_digest))
        claim = Claim(outer_operation_digest=outer_digest,
                      outer_attempt_digest=context.outer_attempt_digest,
                      call_digest=context.call_digest, binding_digest=self.binding_digest,
                      task_scope_digest=scope_digest,
                      context_kind="conformance" if self._conformance else "trial",
                      model_turn_allowance=self.plan.composed_model_turns if self._conformance else 0,
                      request_digest=content_digest(self.plan), operation_reference=operation_reference,
                      outer_attempt_reference=outer_reference)
        repo = self.assessment.repository
        with repo.store._immediate_transaction() as connection:
            self._require_reserved(connection)
            from ..attempts import ExecutionAttemptState
            current_outer = self.outer_router.store.get_execution_attempt(self.outer_attempt_id)
            if current_outer is None or current_outer.state is not ExecutionAttemptState.INVOKING:
                raise ConfigurationError('callback outer attempt stopped before claim')
            if self.resolve_binding() != self.binding_digest or service.router._task_scope_digest != scope_digest:
                raise ConfigurationError('callback binding or execution scope changed before claim')
            for spec in service.router.registry.all():
                if spec.id in scope.executor_fingerprints:
                    service.router._require_task_scope(spec)
            if connection.execute("SELECT 1 FROM assessment_records WHERE kind='callback_claim' AND id=?", (key,)).fetchone():
                raise ConfigurationError("callback already claimed; blind retry denied")
            count = connection.execute(
                "SELECT count(*) FROM assessment_records WHERE kind='callback_claim' AND json_extract(payload_json,'$.outer_operation_digest')=?",
                (outer_digest,)).fetchone()[0]
            if count >= self.max_calls:
                raise ConfigurationError("outer callback allowance exhausted")
            repo._put(connection, "callback_claim", key, claim)
        try:
            result = await service.call(name, arguments)
            if not isinstance(result, dict):
                raise ConfigurationError("callback result is not a tool envelope")
            return result
        finally:
            # Resolve existing durable evidence even if handler/output validation was cancelled.
            with service.router.store._lock:
                rows = service.router.store._connection.execute(
                    "SELECT a.payload_json FROM execution_attempts a JOIN decisions d ON d.decision_id=a.decision_id WHERE d.action_id=?",
                    (context.action_id,)).fetchall()
                receipts = service.router.store._connection.execute(
                    "SELECT payload_json FROM receipts WHERE action_id=?", (context.action_id,)).fetchall()
            from ..attempts import ExecutionAttempt
            from ..models import ExecutionReceipt, TaskScope
            from .repository import AssessmentRepository
            child_attempts = [ExecutionAttempt.model_validate_json(row[0]) for row in rows]
            child_receipts = [ExecutionReceipt.model_validate_json(row[0]) for row in receipts]
            scope = TaskScope.model_validate(AssessmentRepository(service.router.store).get('task_scope', scope_digest))
            scope_reference = repo.put('callback_task_scope', scope_digest, scope)
            attempt_references = [repo.put('callback_child_attempt', content_digest(item), item) for item in child_attempts]
            receipt_references = [repo.put('callback_child_receipt', content_digest(item), item) for item in child_receipts]
            child_specs = {name: service.router.registry.get(name) for name in scope.executor_fingerprints}
            spec_references = {name: repo.put("callback_child_executor", content_digest(spec), spec) for name, spec in child_specs.items()}
            class Evidence(StrictModel):
                claim_digest: str
                task_scope_digest: str
                task_scope_reference: str
                child_attempt_digests: list[str]
                child_receipt_digests: list[str]
                child_executor_digests: dict[str, str]
                resources_overlap_outer_trial: bool = True

            evidence_digest = repo.put("callback_evidence", key, Evidence(
                claim_digest=content_digest(claim), task_scope_digest=scope_digest, task_scope_reference=scope_reference,
                child_attempt_digests=attempt_references,
                child_receipt_digests=receipt_references, child_executor_digests=spec_references))
            context.record_link(evidence_digest)
