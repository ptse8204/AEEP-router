"""Passive trace ingestion and dependency-free model SDK instrumentation."""

from __future__ import annotations

import inspect
import json
import time
from collections.abc import Awaitable, Callable
from datetime import timedelta
from pathlib import Path
from typing import Any, Literal

from .models import (
    EstimateSource,
    ExecutionReceipt,
    ExecutionStatus,
    ExecutorKind,
    PassiveRecommendation,
    ResourceVector,
    RouteEstimate,
    TraceCall,
    TraceCallKind,
    TraceProfileReport,
    new_id,
    utc_now,
)
from .registry import Registry
from .store import ReceiptStore

CostCalculator = Callable[[str | None, int, int], float]


def _value(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    for key in ("stringValue", "intValue", "doubleValue", "boolValue", "bytesValue"):
        if key in value:
            return value[key]
    if "arrayValue" in value:
        values = value["arrayValue"].get("values", [])
        return [_value(item) for item in values]
    return value


def _attributes(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): _value(item) for key, item in value.items()}
    if isinstance(value, list):
        return {
            str(item["key"]): _value(item.get("value"))
            for item in value
            if isinstance(item, dict) and "key" in item
        }
    return {}


def _spans(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []
    if isinstance(value.get("resourceSpans"), list):
        found: list[dict[str, Any]] = []
        for resource in value["resourceSpans"]:
            if not isinstance(resource, dict):
                continue
            resource_attrs = _attributes(resource.get("resource", {}).get("attributes", []))
            scopes = resource.get("scopeSpans") or resource.get("instrumentationLibrarySpans") or []
            for scope in scopes:
                if not isinstance(scope, dict):
                    continue
                for span in scope.get("spans", []):
                    if isinstance(span, dict):
                        merged = dict(span)
                        merged["_resource_attributes"] = resource_attrs
                        found.append(merged)
        return found
    if isinstance(value.get("spans"), list):
        return [item for item in value["spans"] if isinstance(item, dict)]
    return [value] if "name" in value else []


def _number(attributes: dict[str, Any], *names: str) -> float:
    for name in names:
        value = attributes.get(name)
        if isinstance(value, (int, float)):
            return max(0.0, float(value))
        if isinstance(value, str):
            try:
                return max(0.0, float(value))
            except ValueError:
                pass
    return 0.0


def _duration_ms(span: dict[str, Any], attributes: dict[str, Any]) -> float:
    explicit = _number(attributes, "aeep.resource.latency_ms", "duration_ms")
    if explicit:
        return explicit
    try:
        start_value = span.get("startTimeUnixNano", span.get("start_time_unix_nano"))
        end_value = span.get("endTimeUnixNano", span.get("end_time_unix_nano"))
        if not isinstance(start_value, (str, int, float)) or not isinstance(
            end_value, (str, int, float)
        ):
            return 0.0
        start = int(start_value)
        end = int(end_value)
        return max(0.0, (end - start) / 1_000_000)
    except (TypeError, ValueError):
        return 0.0


def _kind(name: str, attributes: dict[str, Any]) -> TraceCallKind:
    keys = " ".join(attributes).casefold()
    name_value = name.casefold()
    if "browser." in keys or "computer_use" in keys or "browser" in name_value:
        return TraceCallKind.BROWSER
    if "mcp." in keys or attributes.get("rpc.system") == "mcp" or "mcp" in name_value:
        return TraceCallKind.MCP
    if "process.command" in attributes or "subprocess" in name_value or "command" in name_value:
        return TraceCallKind.COMMAND
    if "http." in keys or "url." in keys:
        return TraceCallKind.HTTP
    if any(key in attributes for key in ("tool.name", "gen_ai.tool.name")):
        return TraceCallKind.TOOL
    if "gen_ai." in keys or "llm." in keys:
        return TraceCallKind.MODEL
    return TraceCallKind.UNKNOWN


def _status(
    span: dict[str, Any], attributes: dict[str, Any]
) -> Literal["success", "failed", "unknown"]:
    status = span.get("status", {})
    code = status.get("code") if isinstance(status, dict) else status
    if code in {"STATUS_CODE_ERROR", "ERROR", 2} or "error.type" in attributes:
        return "failed"
    if code in {"STATUS_CODE_OK", "OK", 1}:
        return "success"
    return "unknown"


class TraceIngestor:
    def __init__(self, registry: Registry | None = None) -> None:
        self.registry = registry

    def load(self, path: str | Path) -> TraceProfileReport:
        text = Path(path).read_text(encoding="utf-8")
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            value = [json.loads(line) for line in text.splitlines() if line.strip()]
        return self.profile(value)

    def profile(self, value: Any) -> TraceProfileReport:
        calls = [self._call(span) for span in _spans(value)]
        total = ResourceVector()
        for call in calls:
            total = total.plus(call.resources)
        return TraceProfileReport(
            calls=calls,
            total_resources=total,
            retries=sum(call.retries for call in calls),
            failures=sum(call.status == "failed" for call in calls),
            unmapped_calls=sum(call.capability is None for call in calls),
            recommendations=self._recommend(calls),
        )

    def _call(self, span: dict[str, Any]) -> TraceCall:
        attributes = {
            **_attributes(span.get("_resource_attributes", {})),
            **_attributes(span.get("attributes", {})),
        }
        name = str(span.get("name", "unnamed"))
        input_tokens = int(
            _number(
                attributes,
                "gen_ai.usage.input_tokens",
                "gen_ai.usage.prompt_tokens",
                "llm.usage.prompt_tokens",
            )
        )
        output_tokens = int(
            _number(
                attributes,
                "gen_ai.usage.output_tokens",
                "gen_ai.usage.completion_tokens",
                "llm.usage.completion_tokens",
            )
        )
        capability = next(
            (
                str(attributes[key])
                for key in ("aeep.capability", "mcp.tool.name", "gen_ai.tool.name", "tool.name")
                if attributes.get(key)
            ),
            None,
        )
        return TraceCall(
            trace_id=span.get("traceId") or span.get("trace_id"),
            span_id=span.get("spanId") or span.get("span_id"),
            name=name,
            capability=capability,
            executor_id=str(attributes.get("aeep.executor_id") or "") or None,
            kind=_kind(name, attributes),
            provider=str(attributes.get("gen_ai.system") or attributes.get("service.name") or "")
            or None,
            model=str(
                attributes.get("gen_ai.response.model")
                or attributes.get("gen_ai.request.model")
                or ""
            )
            or None,
            status=_status(span, attributes),
            retries=int(
                _number(attributes, "retry.count", "gen_ai.request.retry_count", "http.retry_count")
            ),
            resources=ResourceVector(
                monetary_usd=_number(
                    attributes,
                    "aeep.resource.monetary_usd",
                    "gen_ai.usage.cost",
                    "llm.usage.cost",
                ),
                latency_ms=_duration_ms(span, attributes),
                cpu_ms=_number(attributes, "aeep.resource.cpu_ms", "process.cpu.time_ms"),
                memory_mb_seconds=_number(attributes, "aeep.resource.memory_mb_seconds"),
                peak_memory_mb=_number(attributes, "aeep.resource.peak_memory_mb"),
                gpu_ms=_number(attributes, "aeep.resource.gpu_ms"),
                network_bytes=int(
                    _number(attributes, "aeep.resource.network_bytes")
                    or _number(attributes, "http.request.body.size")
                    + _number(attributes, "http.response.body.size")
                ),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                context_tokens=int(_number(attributes, "aeep.resource.context_tokens")),
                subscription_units=_number(attributes, "aeep.resource.subscription_units"),
            ),
        )

    def _recommend(self, calls: list[TraceCall]) -> list[PassiveRecommendation]:
        if self.registry is None:
            return []
        recommendations: list[PassiveRecommendation] = []
        for call in calls:
            if call.capability is None:
                continue
            candidates = [
                spec
                for spec in self.registry.find(call.capability)
                if spec.estimate.resources.monetary_usd <= call.resources.monetary_usd
                and spec.estimate.resources.latency_ms <= call.resources.latency_ms
                and (
                    spec.estimate.resources.monetary_usd < call.resources.monetary_usd
                    or spec.estimate.resources.latency_ms < call.resources.latency_ms
                )
            ]
            if not candidates:
                continue
            best = min(
                candidates,
                key=lambda spec: (
                    spec.estimate.resources.monetary_usd,
                    spec.estimate.resources.latency_ms,
                    spec.id,
                ),
            )
            recommendations.append(
                PassiveRecommendation(
                    capability=call.capability,
                    observed_kind=call.kind,
                    recommended_executor_id=best.id,
                    estimated_cash_saving_usd=max(
                        0.0,
                        call.resources.monetary_usd - best.estimate.resources.monetary_usd,
                    ),
                    estimated_latency_saving_ms=max(
                        0.0,
                        call.resources.latency_ms - best.estimate.resources.latency_ms,
                    ),
                    reason="registered route is no worse on estimated cash and latency",
                )
            )
        return recommendations

    @staticmethod
    def record(report: TraceProfileReport, store: ReceiptStore) -> list[ExecutionReceipt]:
        """Persist reconstructed calls as payload-free receipts."""

        receipts: list[ExecutionReceipt] = []
        kinds = {
            TraceCallKind.MODEL: ExecutorKind.HTTP,
            TraceCallKind.TOOL: ExecutorKind.DELEGATE,
            TraceCallKind.BROWSER: ExecutorKind.DELEGATE,
            TraceCallKind.COMMAND: ExecutorKind.COMMAND,
            TraceCallKind.MCP: ExecutorKind.MCP,
            TraceCallKind.HTTP: ExecutorKind.HTTP,
            TraceCallKind.UNKNOWN: ExecutorKind.DELEGATE,
        }
        statuses = {
            "success": ExecutionStatus.SUCCESS,
            "failed": ExecutionStatus.FAILED,
            "unknown": ExecutionStatus.UNKNOWN,
        }
        for call in report.calls:
            if call.capability is None:
                continue
            ended_at = utc_now()
            started_at = ended_at - timedelta(milliseconds=call.resources.latency_ms)
            receipt = ExecutionReceipt(
                decision_id=new_id("trace_dec"),
                action_id=new_id("trace_act"),
                capability=call.capability,
                executor_id=call.executor_id
                or f"trace.{call.provider or call.kind.value}.{call.model or call.name}",
                executor_kind=kinds[call.kind],
                status=statuses[call.status],
                started_at=started_at,
                ended_at=ended_at,
                estimated=RouteEstimate(source=EstimateSource.OBSERVED, confidence=0),
                actual_resources=call.resources,
                transport_success=True if call.status == "success" else None,
                execution_success=True
                if call.status == "success"
                else False
                if call.status == "failed"
                else None,
                metadata={
                    "instrumentation": "opentelemetry-ingest",
                    "trace_id": call.trace_id,
                    "span_id": call.span_id,
                    "retries": call.retries,
                    "payload_stored": False,
                    "output_stored": False,
                },
            )
            store.save_receipt(receipt)
            receipts.append(receipt)
        report.recorded_receipt_ids = [receipt.receipt_id for receipt in receipts]
        return receipts


def _get(value: Any, name: str, default: Any = None) -> Any:
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


class _InstrumentedProxy:
    def __init__(
        self,
        target: Any,
        *,
        path: tuple[str, ...],
        provider: str,
        store: ReceiptStore,
        capability: str,
        calls: set[tuple[str, ...]],
        cost_calculator: CostCalculator | None,
    ) -> None:
        self._target = target
        self._path = path
        self._provider = provider
        self._store = store
        self._capability = capability
        self._calls = calls
        self._cost_calculator = cost_calculator

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._target, name)
        path = (*self._path, name)
        if callable(value) and path in self._calls:
            return _InstrumentedProxy(
                value,
                path=path,
                provider=self._provider,
                store=self._store,
                capability=self._capability,
                calls=self._calls,
                cost_calculator=self._cost_calculator,
            )
        if any(candidate[: len(path)] == path for candidate in self._calls):
            return _InstrumentedProxy(
                value,
                path=path,
                provider=self._provider,
                store=self._store,
                capability=self._capability,
                calls=self._calls,
                cost_calculator=self._cost_calculator,
            )
        return value

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        started_at = utc_now()
        started = time.perf_counter()
        model = str(kwargs.get("model")) if kwargs.get("model") is not None else None
        try:
            result = self._target(*args, **kwargs)
        except Exception as exc:
            self._record(None, model, started_at, started, exc)
            raise
        if inspect.isawaitable(result):
            return self._await_and_record(result, model, started_at, started)
        self._record(result, model, started_at, started, None)
        return result

    async def _await_and_record(
        self,
        result: Awaitable[Any],
        model: str | None,
        started_at: Any,
        started: float,
    ) -> Any:
        try:
            value = await result
        except Exception as exc:
            self._record(None, model, started_at, started, exc)
            raise
        self._record(value, model, started_at, started, None)
        return value

    def _record(
        self,
        response: Any,
        model: str | None,
        started_at: Any,
        started: float,
        error: Exception | None,
    ) -> None:
        usage = _get(response, "usage", {})
        input_tokens = int(_get(usage, "input_tokens", _get(usage, "prompt_tokens", 0)) or 0)
        output_tokens = int(_get(usage, "output_tokens", _get(usage, "completion_tokens", 0)) or 0)
        actual_model = str(_get(response, "model", model) or model or "unknown")
        monetary = (
            max(0.0, self._cost_calculator(actual_model, input_tokens, output_tokens))
            if self._cost_calculator is not None
            else 0.0
        )
        ended_at = utc_now()
        status = ExecutionStatus.SUCCESS if error is None else ExecutionStatus.FAILED
        receipt = ExecutionReceipt(
            decision_id=new_id("sdk_dec"),
            action_id=new_id("sdk_act"),
            capability=self._capability,
            executor_id=f"{self._provider}.{actual_model}",
            executor_kind=ExecutorKind.HTTP,
            status=status,
            started_at=started_at,
            ended_at=ended_at,
            estimated=RouteEstimate(source=EstimateSource.STATIC, confidence=0.0),
            actual_resources=ResourceVector(
                monetary_usd=monetary,
                latency_ms=max(0.0, (time.perf_counter() - started) * 1000.0),
                input_tokens=max(0, input_tokens),
                output_tokens=max(0, output_tokens),
            ),
            transport_success=error is None,
            execution_success=error is None,
            task_valid=None,
            output_valid=None,
            error_type=type(error).__name__ if error else None,
            error_message=str(error) if error else None,
            metadata={
                "instrumentation": f"{self._provider}-sdk",
                "model": actual_model,
                "cost_observed": self._cost_calculator is not None,
                "payload_stored": False,
                "output_stored": False,
            },
        )
        self._store.save_receipt(receipt)


def instrument_openai(
    client: Any,
    *,
    store: ReceiptStore,
    capability: str = "model.generate@1",
    cost_calculator: CostCalculator | None = None,
) -> Any:
    """Wrap OpenAI Responses/Chat create calls without importing the OpenAI SDK."""

    return _InstrumentedProxy(
        client,
        path=(),
        provider="openai",
        store=store,
        capability=capability,
        calls={("responses", "create"), ("chat", "completions", "create")},
        cost_calculator=cost_calculator,
    )


def instrument_anthropic(
    client: Any,
    *,
    store: ReceiptStore,
    capability: str = "model.generate@1",
    cost_calculator: CostCalculator | None = None,
) -> Any:
    """Wrap Anthropic Messages create calls without importing the Anthropic SDK."""

    return _InstrumentedProxy(
        client,
        path=(),
        provider="anthropic",
        store=store,
        capability=capability,
        calls={("messages", "create")},
        cost_calculator=cost_calculator,
    )
