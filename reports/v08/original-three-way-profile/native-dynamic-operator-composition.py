"""Inert operator composition; importing this file starts no worker or assessment.

Caller supplies a protected, independently reviewed per-execution task service.
This is preparation, not evidence of composite boundary conformance.
"""
from typing import Any

from aeep.assessment.fixed_helper import AssessmentCallbackAuthority, current_assessment_router
from aeep.hosts.codex_dynamic_tools import CodexDynamicTools
from aeep.models import StrictModel


class DynamicDefinition(StrictModel):
    namespace: str
    tools: list[dict[str, Any]]
    identity: dict[str, Any]
    max_calls: int
    timeout_seconds: float


def inert_definition(binding: CodexDynamicTools) -> DynamicDefinition:
    """Existing repository.put/review accepts this exact StrictModel, not dict."""
    return DynamicDefinition.model_validate(binding.definition())


def operator_factory(*, assessment, plan, profile_identity, namespace,
                     max_calls, timeout_seconds, service_for_trial):
    """Return an adapter factory; only an operator may construct/register it.

    service_for_trial must select a pre-reviewed protected Mac task service by
    canonical trial identity. It must not create/reset allowances, review scopes,
    select a model-supplied executor, or share writable case/oracle state.
    """
    def compose(context, adapter):
        outer = current_assessment_router()
        if outer is None or outer._callback_trial_identity is None:
            raise ValueError('controlled trial router unavailable')
        assessment_id, operation_id = outer._callback_trial_identity
        service = service_for_trial(assessment_id, operation_id)
        holder = {}
        def resolve():
            return holder['binding'].require_reviewed_binding(
                assessment.repository, worker=adapter._worker, service=service,
                artifact=context.config.artifact)
        def authorized_call(name, arguments):
            return holder['authority'].call(service, name, arguments)
        binding = CodexDynamicTools.task_service(service, namespace=namespace,
            identity=profile_identity, max_calls=max_calls,
            timeout_seconds=timeout_seconds, check=resolve,
            artifact_context=context, artifact_worker=adapter._worker,
            execution_id=adapter._worker_process_id,
            authorized_call=authorized_call)
        holder['binding'] = binding
        invocation = context.config.invocation
        if invocation is None or invocation.dynamic_tools_digest != binding.digest:
            raise ValueError('frozen invocation differs from effective composition')
        holder['authority'] = AssessmentCallbackAuthority(assessment, plan,
            assessment_id, operation_id, outer_router=outer,
            outer_attempt_id=context.attempt_id, binding_digest=binding.digest,
            resolve_binding=resolve, max_calls=max_calls)
        return binding
    return compose


def union_operator_factory(*, assessment, plan, profile_identity, namespace,
                           max_calls, timeout_seconds, services_for_trial, conformance_request=None):
    """Treatment retains the fixed helper and adds AEEP on one shared allowance.

    Each named service must use the SAME protected Router, standing scope and
    exact executor/backend mapping. Inner artifact handlers are reused; no new
    input transport or mutable registry is introduced. This remains inert.
    """
    def compose(context, adapter):
        outer = current_assessment_router()
        identity = (getattr(outer, '_callback_conformance_identity', None)
                    if conformance_request is not None else
                    getattr(outer, '_callback_trial_identity', None))
        if outer is None or identity is None:
            raise ValueError('canonical controlled operation router unavailable')
        assessment_id, operation_id = identity
        if conformance_request is not None and assessment_id != conformance_request.plan_id:
            raise ValueError('conformance operation identity differs')
        services = tuple(services_for_trial(assessment_id, operation_id))
        if not services or any(service.router is not services[0].router for service in services):
            raise ValueError('union services must share one protected task Router and allowance')
        declarations = [service.list_tools() for service in services]
        holder = {}
        def resolve():
            if [service.list_tools() for service in services] != declarations:
                raise ValueError('union service declarations changed')
            for service in services:
                holder['binding'].require_reviewed_binding(assessment.repository,
                    worker=adapter._worker, service=service, artifact=context.config.artifact)
            return holder['binding'].digest
        by_name = {}
        tools = []
        for service in services:
            async def authorized(name, arguments, selected=service):
                return await holder['authority'].call(selected, name, arguments)
            inner = CodexDynamicTools.task_service(service, namespace=namespace,
                identity=profile_identity, max_calls=max_calls,
                timeout_seconds=timeout_seconds, check=resolve,
                artifact_context=context, artifact_worker=adapter._worker,
                execution_id=adapter._worker_process_id, authorized_call=authorized)
            for declaration in inner.definition()['tools']:
                name = declaration['name']
                if name in by_name:
                    raise ValueError('union task tool names overlap')
                tools.append(declaration)
                # Reuse the exact existing operator artifact handler.
                by_name[name] = inner._call
        async def call(name, arguments):
            return await by_name[name](name, arguments)
        binding = CodexDynamicTools(namespace=namespace, tools=tools,
            identity=profile_identity, max_calls=max_calls,
            timeout_seconds=timeout_seconds, call=call, check=resolve)
        holder['binding'] = binding
        if context.config.invocation.dynamic_tools_digest != binding.digest:
            raise ValueError('frozen union invocation differs')
        if conformance_request is not None:
            holder['authority'] = AssessmentCallbackAuthority.for_conformance(
                assessment, conformance_request, operation_id, outer_router=outer,
                outer_attempt_id=context.attempt_id, binding_digest=binding.digest,
                resolve_binding=resolve, max_calls=max_calls)
        else:
            holder['authority'] = AssessmentCallbackAuthority(assessment, plan,
                assessment_id, operation_id, outer_router=outer,
                outer_attempt_id=context.attempt_id, binding_digest=binding.digest,
                resolve_binding=resolve, max_calls=max_calls)
        services[0].router._trial_check = holder['authority'].check
        services[0].router._trial_deadline = outer._trial_deadline
        return binding
    return compose
