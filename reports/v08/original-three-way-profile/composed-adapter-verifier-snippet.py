from typing import Any
from aeep.assessment.models import ConformanceProbeRequest, content_digest
from aeep.errors import ConfigurationError
from aeep.models import ExecutorSpec


def verify_composed_binding(repository: Any, record: Any, worker_digest: str) -> ExecutorSpec:
    if record.adapter.split(':', 1)[0] != 'codex-app-server':
        raise ConfigurationError('composed conformance adapter is unsupported')
    document = repository.get('codex_dynamic_tools', record.callback_binding_digest)
    identity = document.get('identity', {})
    if (content_digest(document) != record.callback_binding_digest
            or identity.get('worker_digest') != worker_digest
            or identity.get('native_backend_digest') != record.native_backend_digest):
        raise ConfigurationError('composed callback backend or worker binding differs')
    composite = repository.get('composed_pair_definition', record.composed_definition_digest)
    if (composite.get('callback_bindings', {}).get(worker_digest) != record.callback_binding_digest
            or composite.get('native_backends', {}).get(worker_digest) != record.native_backend_digest):
        raise ConfigurationError('composed definition does not bind selected callback/native worker')
    from ..hosts.workers import binding_from_config
    profiles = [ExecutorSpec.model_validate(composite[name]) for name in ('control', 'treatment')]
    selected = [spec for spec in profiles if (bound := binding_from_config(spec.managed_host_config().managed_worker)) is not None and bound.digest() == worker_digest]
    if len(selected) != 1 or selected[0].managed_host_config().invocation is None or selected[0].managed_host_config().invocation.dynamic_tools_digest != record.callback_binding_digest:
        raise ConfigurationError('composed profile identity is missing or ambiguous')
    if content_digest(composite) != record.composed_definition_digest:
        raise ConfigurationError('composed inspection definition differs')
    with repository.store._lock:
        for required_review in (record.callback_binding_digest, record.composed_definition_digest):
            reviewed = repository.store._connection.execute(
                'SELECT revoked FROM assessment_reviews WHERE digest=?', (required_review,)).fetchone()
            if reviewed is None or reviewed[0]:
                raise ConfigurationError('composed boundary requires current exact review')
    return selected[0]


def verify_composed_callback(repository: Any, record: Any, probe: Any, definition: Any,
                             evidence: Any, selected_spec: ExecutorSpec) -> None:
    identity = repository.get('codex_dynamic_tools', record.callback_binding_digest)['identity']
    identity_digest = record.identity_digest
    from ..models import ExecutionReceipt
    from ..economic.prepared import executor_fingerprint
    if probe.host_receipt_digest is None:
        raise ConfigurationError('actual callback host receipt is missing')
    host_receipt = ExecutionReceipt.model_validate(repository.get('conformance_host_receipt', probe.host_receipt_digest))
    if (content_digest(host_receipt) != probe.host_receipt_digest
            or host_receipt.executor_fingerprint != executor_fingerprint(selected_spec)
            or host_receipt.metadata.get('host_runtime_digest') != identity_digest
            or host_receipt.metadata.get('dynamic_tools_digest') != record.callback_binding_digest
            or host_receipt.metadata.get('model_turn_count') != 1
            or not host_receipt.accounting.model_usage):
        raise ConfigurationError('callback host receipt is not the pinned actual process identity')
    invocation = definition.executor.managed_host_config().invocation if definition.executor.kind.value == 'host_managed' else None
    if (invocation is None or invocation.dynamic_tools_digest != record.callback_binding_digest
            or probe.observed.get('callback_origin') != 'native_app_server'
            or probe.observed.get('native_callback_observed') is not True
            or not any(event.kind == 'action.completed' and isinstance(event.source_id, str) and event.source_id.startswith(('dynamic-complete:', 'adapter:dynamic-complete:')) for event in evidence.events)
            or not any(event.accounting is not None and event.accounting.model_usage for event in evidence.events)):
        raise ConfigurationError('full composed conformance requires an actual model-issued native callback')
    links = [event.evidence_ref for event in evidence.events
             if isinstance(event.source_id, str) and event.source_id.startswith(('dynamic-link:', 'adapter:dynamic-link:')) and event.evidence_ref is not None]
    if not links:
        raise ConfigurationError('native callback lacks durable child evidence')
    for reference in links:
        child = repository.get('callback_evidence', reference)
        claim = repository.get('callback_claim', child['claim_digest'])
        if (claim.get('context_kind') != 'conformance' or claim.get('model_turn_allowance') != 1
                or claim.get('binding_digest') != record.callback_binding_digest
                or child.get('task_scope_digest') != claim.get('task_scope_digest')
                or not child.get('child_attempt_digests') or not child.get('child_receipt_digests')):
            raise ConfigurationError('native callback evidence is not bound to a model conformance allowance')
        from ..attempts import ExecutionAttempt
        request = ConformanceProbeRequest.model_validate(repository.get('conformance_request', claim['request_digest']))
        operation = repository.get('operation_start', claim['operation_reference'])
        outer = ExecutionAttempt.model_validate(repository.get('callback_outer_attempt', claim['outer_attempt_reference']))
        if (content_digest(request) != claim['request_digest']
                or request.schema_version != 'assessment.conformance-request.v4'
                or request.operation != 'composed_pair_inspection' or request.composed_model_turns != 1
                or request.pair_definition_digest != record.composed_definition_digest
                or record.callback_binding_digest not in request.definition_digests
                or operation.get('plan_id') != request.plan_id or operation.get('stage') != 'composed_pair_inspection'
                or operation.get('reserved', {}).get('max_model_turns') != 1
                or outer.decision_id != host_receipt.decision_id
                or outer.executor_fingerprint != host_receipt.executor_fingerprint):
            raise ConfigurationError('native callback request/reservation/host attempt lineage differs')
        repository.authorize(request)
        from ..models import TaskScope
        scope = TaskScope.model_validate(repository.get('callback_task_scope', child['task_scope_reference']))
        if content_digest(scope) != child['task_scope_digest'] or scope.executor_fingerprints != identity.get('executor_fingerprints'):
            raise ConfigurationError('native callback scope evidence differs')
        attempts = [ExecutionAttempt.model_validate(repository.get('callback_child_attempt', item)) for item in child['child_attempt_digests']]
        receipts = [ExecutionReceipt.model_validate(repository.get('callback_child_receipt', item)) for item in child['child_receipt_digests']]
        for receipt in receipts:
            matching = [item for item in attempts if item.decision_id == receipt.decision_id
                        and item.task_scope_digest == child['task_scope_digest']
                        and receipt.receipt_id in item.terminal_receipt_ids
                        and item.executor_fingerprint == receipt.executor_fingerprint]
            if len(matching) != 1 or scope.executor_fingerprints.get(receipt.executor_id) != receipt.executor_fingerprint:
                raise ConfigurationError('callback child receipt does not match the scoped canonical attempt')
