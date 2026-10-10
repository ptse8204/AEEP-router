"""Optional OpenTelemetry spans without imposing an SDK on applications."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span

from .version import __version__


def _safe_attribute(value: Any) -> str | bool | int | float | None:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return str(value)


@contextmanager
def start_span(name: str, attributes: dict[str, Any] | None = None) -> Iterator[Span | None]:
    tracer = trace.get_tracer("aeep", __version__)
    with tracer.start_as_current_span(name) as span:
        for key, value in (attributes or {}).items():
            safe = _safe_attribute(value)
            if safe is not None:
                span.set_attribute(key, safe)
        yield span


def trace_id_from_span(span: Span | None) -> str | None:
    if span is None:
        return None
    context = span.get_span_context()
    if not context.is_valid:
        return None
    return f"{context.trace_id:032x}"


def receipt_otlp_preview(receipt: Any) -> dict[str, Any]:
    """Minimized OTLP/HTTP JSON for a supplied receipt; never configures an exporter."""
    import hashlib
    import json
    import math
    from datetime import UTC, datetime

    from .assessment.reporting import resource_measurements
    from .models import ExecutionReceipt

    record = ExecutionReceipt.model_validate(receipt)
    raw = record.model_dump(mode='json')
    source = hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    def nanos(value: datetime) -> int:
        if value.tzinfo is None:
            raise ValueError('trace timestamps require a timezone')
        delta = value - epoch
        return ((delta.days*86400 + delta.seconds)*1000000 + delta.microseconds)*1000
    start, end = nanos(record.started_at), nanos(record.ended_at)
    if start < 0 or end < start:
        raise ValueError('invalid receipt trace interval')
    attributes = [
        {'key': 'aeep.receipt.sha256', 'value': {'stringValue': source}},
        {'key': 'aeep.evidence.trust', 'value': {'stringValue': 'supplied_unverified'}},
        {'key': 'aeep.execution.status', 'value': {'stringValue': record.status.value}},
    ]
    measurements = resource_measurements(record.accounting, record.actual_resources)
    measurements['local.latency_ms'] = record.actual_resources.latency_ms or None
    measurements['local.peak_memory_mb'] = record.actual_resources.peak_memory_mb or None
    for key, value in measurements.items():
        if not key.startswith('local.') or value is None or type(value) not in (int, float):
            continue
        if not math.isfinite(value) or value < 0:
            raise ValueError('invalid receipt resource measurement')
        attributes.append({'key': 'aeep.resource.' + key,
                           'value': {'intValue': str(value)} if type(value) is int else {'doubleValue': value}})
    return {'schema_version': 'aeep.toolkit.otlp-preview.v1', 'receipt_sha256': source,
            'trust': 'supplied_unverified', 'destination': None, 'export_performed': False,
            'notice': 'Private preview. Digests and timings can identify an operation. No payload, model trace, billing inference or export authority.',
            'payload': {'resourceSpans': [{'resource': {'attributes': [
                {'key': 'service.name', 'value': {'stringValue': 'aeep'}}]},
                'scopeSpans': [{'scope': {'name': 'aeep.receipt', 'version': __version__},
                               'spans': [{'traceId': source[:32], 'spanId': source[32:48], 'name': 'aeep.execution',
                                          'kind': 1, 'startTimeUnixNano': str(start), 'endTimeUnixNano': str(end),
                                          'attributes': attributes}]}]}]}}
