"""Content-free configuration observations over existing profiles and receipts.

A compiled declaration is not host visibility. Selected receipt observations are
not a complete use census, comparative evidence, or permission to execute.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from pydantic import Field, model_validator

from .assessment.models import Digest, content_digest
from .assessment.reporting import resource_measurements
from .assessment.repository import AssessmentRepository
from .errors import ConfigurationError
from .models import (
    ExecutionReceipt,
    ResourceAccounting,
    ResourceVector,
    StrictModel,
    TrustLevel,
    new_id,
    utc_now,
)
from .profiles import inspect

if TYPE_CHECKING:
    from .router import Router


class ConfigurationState(StrictModel):
    status: Literal['observed', 'declared', 'unavailable'] = 'unavailable'
    value: bool | None = None
    basis: str = Field(default='unavailable', max_length=200)

    @model_validator(mode='after')
    def consistent(self) -> ConfigurationState:
        if (self.status == 'unavailable') != (self.value is None):
            raise ValueError('available state requires a value; unavailable state cannot assert one')
        return self


class ComponentObservation(StrictModel):
    component_id: str
    content_digest: Digest
    installed: ConfigurationState = Field(default_factory=ConfigurationState)
    discovered: ConfigurationState = Field(default_factory=ConfigurationState)
    permitted: ConfigurationState = Field(default_factory=ConfigurationState)
    exposed: ConfigurationState = Field(default_factory=ConfigurationState)
    invoked: ConfigurationState = Field(default_factory=ConfigurationState)
    successful: ConfigurationState = Field(default_factory=ConfigurationState)
    verified: ConfigurationState = Field(default_factory=ConfigurationState)
    receipt_ids: list[str] = Field(default_factory=list, max_length=100)


class ConfigurationReceiptObservation(StrictModel):
    receipt_id: str
    receipt_digest: Digest
    executor_id: str
    invocation_started: bool | None = None
    execution_success: bool | None = None
    schema_valid: bool | None = None
    task_valid: bool | None = None
    trusted_task_verification: bool | None = None
    quality_score: float | None = Field(default=None, ge=0, le=1)
    attempt_number: int = Field(ge=1)
    # Keep native dimensions alongside their nullable measurement interpretation.
    raw_resources: ResourceVector
    accounting: ResourceAccounting
    measurements: dict[str, float | None]
    measurement_status: dict[str, Literal['available', 'unavailable']]
    result_bytes: int | None = Field(default=None, ge=0)
    execution_evidence_digest: Digest | None = None
    host_inventory_digest: str | None = Field(default=None, max_length=200)
    preservation: Literal['unavailable'] = 'unavailable'
    comparative_contribution: Literal['not_established'] = 'not_established'


class ConfigurationObservation(StrictModel):
    schema_version: Literal['aeep.configuration-observation.v1'] = 'aeep.configuration-observation.v1'
    observation_id: str = Field(default_factory=lambda: new_id('configuration'))
    captured_at: datetime = Field(default_factory=utc_now)
    profile_digest: Digest
    scope_digest: Digest
    manifest_digest: Digest
    activation_digest: Digest | None = None
    compiled_tools_digest: Digest
    compiled_schema_bytes: int = Field(ge=0)
    compiled_tool_count: int = Field(ge=0)
    actual_host_context_tokens: None = None
    actual_visible_inventory: Literal['unavailable'] = 'unavailable'
    components: list[ComponentObservation] = Field(max_length=128)
    receipts: list[ConfigurationReceiptObservation] = Field(default_factory=list, max_length=100)
    receipt_coverage: Literal['operator-selected scope-bound receipts; not an exhaustive census'] = 'operator-selected scope-bound receipts; not an exhaustive census'
    activation_ready: bool = False
    limitations: list[str] = Field(default_factory=lambda: [
        'Compiled schema bytes describe the AEEP task surface, not loaded host context.',
        'Absent observations do not establish non-use, installation absence or zero resource use.',
        'Receipt scope binding does not identify which activation delivered an invocation.',
        'Execution success, task verification, preservation and comparative contribution are separate.',
    ])


def _state(values: list[bool | None], basis: str) -> ConfigurationState:
    known = [item for item in values if item is not None]
    # A positive record establishes at least one occurrence. Incomplete absence does not.
    value = True if any(known) else False if known and len(known) == len(values) else None
    return ConfigurationState(status='observed' if value is not None else 'unavailable', value=value, basis=basis)


def _receipt(router: Router, receipt: ExecutionReceipt) -> ConfigurationReceiptObservation:
    trusted = [check.valid for check in receipt.validation_results
               if check.kind.value != 'schema' and check.trust in {TrustLevel.OBSERVED, TrustLevel.VERIFIED}]
    verified = (False if False in trusted else True
                if trusted and all(item is True for item in trusted) and receipt.task_valid is True else None)
    attempt_id = receipt.metadata.get('attempt_id')
    attempt = router.store.get_execution_attempt(attempt_id) if isinstance(attempt_id, str) else None
    invoked = True if receipt.transport_success is True else None
    if attempt is not None:
        if (receipt.receipt_id not in attempt.terminal_receipt_ids
                or attempt.executor_id != receipt.executor_id
                or attempt.executor_fingerprint != receipt.executor_fingerprint
                or attempt.task_scope_digest != receipt.metadata.get('task_scope_digest')):
            raise ConfigurationError('receipt invocation binding conflicts with durable attempt')
        invoked = True if attempt.invocation_start_digest is not None else invoked
    measurements = resource_measurements(receipt.accounting, receipt.actual_resources)
    # Existing measurement interpretation deliberately treats legacy default zeros as unknown.
    measurements['local.latency_ms'] = receipt.actual_resources.latency_ms or None
    measurements['receipt.interval_ms'] = receipt.duration_ms
    measurements['local.peak_memory_mb'] = receipt.actual_resources.peak_memory_mb or None
    measurements['model.context_tokens'] = None
    if not receipt.accounting.model_usage:
        for name in ('input_tokens', 'cached_input_tokens', 'cache_write_input_tokens', 'output_tokens', 'reasoning_output_tokens'):
            measurements['model.' + name] = None
    if not receipt.accounting.subscription_usage:
        measurements['subscription.pressure'] = None
    if not receipt.accounting.cash.components:
        measurements['cash.external_charges'] = None
    size = receipt.metadata.get('result_bytes')
    result_bytes = size if type(size) is int and size >= 0 else None
    evidence = receipt.metadata.get('execution_evidence_digest')
    inventory = receipt.metadata.get('host_advertised_inventory_digest')
    return ConfigurationReceiptObservation(receipt_id=receipt.receipt_id, receipt_digest=content_digest(receipt),
        executor_id=receipt.executor_id, invocation_started=invoked, execution_success=receipt.execution_success,
        schema_valid=receipt.schema_valid, task_valid=receipt.task_valid, trusted_task_verification=verified,
        quality_score=receipt.quality_score, attempt_number=receipt.attempt, raw_resources=receipt.actual_resources,
        accounting=receipt.accounting, measurements=measurements,
        measurement_status={key: 'unavailable' if value is None else 'available' for key, value in measurements.items()},
        result_bytes=result_bytes,
        execution_evidence_digest=evidence if isinstance(evidence, str) else None,
        host_inventory_digest=inventory if isinstance(inventory, str) else None)


def capture(router: Router, profile_id: str, activation_id: str | None = None,
            receipt_ids: list[str] | None = None) -> ConfigurationObservation:
    """Capture existing local state; does not discover, probe a host or execute tools."""
    ids = receipt_ids or []
    if (len(ids) > 100 or any(not isinstance(item, str) or not 0 < len(item) <= 200 for item in ids)
            or len(set(ids)) != len(ids)):
        raise ConfigurationError('configuration capture requires at most 100 distinct receipt identities')
    resolved = inspect(router, profile_id, activation_id=activation_id)
    scope = resolved['scope']
    rows = []
    for identity in ids:
        receipt = router.store.get_receipt(identity)
        if (receipt is None or receipt.executor_id not in scope['executor_fingerprints']
                or receipt.metadata.get('task_scope_digest') != resolved['profile']['scope_digest']
                or receipt.executor_fingerprint != scope['executor_fingerprints'].get(receipt.executor_id)):
            raise ConfigurationError('configuration receipt is unavailable or outside the exact profile scope')
        rows.append(_receipt(router, receipt))
    components = []
    for item in resolved['components']:
        component = item['component']
        selected = [row for row in rows if row.executor_id == component['executor_id']]
        permitted = ConfigurationState()
        if component['executor_id'] is not None:
            permitted = ConfigurationState(status='observed' if resolved['activated'] else 'declared',
                value=bool(item['permitted'] if resolved['activated'] else item['configured_permitted']),
                basis='AEEP task-service scope; additional dispatch checks still apply')
        components.append(ComponentObservation(component_id=component['component_id'], content_digest=component['content_digest'],
            permitted=permitted, invoked=_state([row.invocation_started for row in selected], 'selected durable invocation-start records'),
            successful=_state([row.execution_success for row in selected], 'selected receipt execution-success fields'),
            verified=_state([row.trusted_task_verification for row in selected], 'selected trusted non-schema task checks'),
            receipt_ids=[row.receipt_id for row in selected]))
    tools = resolved['tools']
    record = ConfigurationObservation(profile_digest=resolved['profile_digest'], scope_digest=resolved['profile']['scope_digest'],
        manifest_digest=content_digest(router.manifest),
        activation_digest=resolved.get('activation', {}).get('activation_digest'),
        compiled_tools_digest=content_digest(tools), compiled_schema_bytes=len(json.dumps(tools, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()),
        compiled_tool_count=len(tools), components=components, receipts=rows, activation_ready=resolved['activated'])
    AssessmentRepository(router.store).put('configuration_observation', record.observation_id, record)
    return record


def _self_check() -> None:
    """Small data-only contract check; no host, assessment or receipt creation."""
    from pydantic import ValidationError
    assert _state([], 'empty').value is None
    assert _state([False, None], 'partial').value is None
    assert _state([True, None], 'positive').value is True
    try:
        ConfigurationState(status='unavailable', value=False)
    except ValidationError:
        pass
    else:
        raise AssertionError('missing state became a negative observation')


if __name__ == '__main__':
    _self_check()
