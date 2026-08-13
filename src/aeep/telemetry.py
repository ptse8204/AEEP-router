"""Optional OpenTelemetry spans without imposing an SDK on applications."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

try:
    from opentelemetry import trace
    from opentelemetry.trace import Span
except ImportError:  # pragma: no cover - opentelemetry-api is a declared dependency
    trace = None
    Span = Any  # type: ignore[misc,assignment]


def _safe_attribute(value: Any) -> str | bool | int | float | None:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return str(value)


@contextmanager
def start_span(name: str, attributes: dict[str, Any] | None = None) -> Iterator[Span | None]:
    if trace is None:
        yield None
        return
    tracer = trace.get_tracer("aeep", "0.1.0")
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
