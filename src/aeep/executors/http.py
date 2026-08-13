"""Bounded HTTP API executor with SSRF-conscious defaults."""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from ..errors import ConfigurationError
from ..models import ExecutionStatus, RawExecution, ResourceVector
from ..profiler import approximate_tokens
from ..templates import extract_path, render
from .base import BaseExecutor, ExecutionContext
from .network import validate_http_url


class HTTPExecutor(BaseExecutor):
    async def execute(self, context: ExecutionContext) -> RawExecution:
        config = context.spec.config
        url_template = config.get("url")
        if not isinstance(url_template, str):
            raise ConfigurationError(f"HTTP executor {context.spec.id} requires config.url")
        values = {"input": context.request.input, "action": context.request.model_dump(mode="json")}
        url = str(render(url_template, values))
        try:
            await validate_http_url(url, config)
        except Exception as exc:
            return RawExecution(
                status=ExecutionStatus.REJECTED,
                error_type=type(exc).__name__,
                error_message=str(exc),
                resources=ResourceVector(monetary_usd=context.estimate.resources.monetary_usd),
            )

        method = str(config.get("method", "GET")).upper()
        headers_template = config.get("headers", {})
        if not isinstance(headers_template, dict):
            raise ConfigurationError("HTTP config.headers must be a mapping")
        headers = {
            str(key): str(value)
            for key, value in render(headers_template, values, allow_env=True).items()
        }
        if context.request.idempotency_key and config.get("propagate_idempotency_key", True):
            headers.setdefault("Idempotency-Key", context.request.idempotency_key)
        params = render(config.get("query", {}), values)
        json_body = render(config.get("json"), values) if "json" in config else None
        content = render(config.get("body"), values) if "body" in config else None
        timeout = float(config.get("timeout_seconds", 30.0))
        max_response_bytes = int(config.get("max_response_bytes", 2_000_000))
        follow_redirects = bool(config.get("follow_redirects", False))
        started = time.perf_counter()
        request_bytes = 0
        if json_body is not None:
            request_bytes += len(json.dumps(json_body, ensure_ascii=False).encode("utf-8"))
        if content is not None:
            content = str(content)
            request_bytes += len(content.encode("utf-8"))

        try:
            async with (
                httpx.AsyncClient(
                    timeout=timeout,
                    follow_redirects=follow_redirects,
                    trust_env=bool(config.get("trust_proxy_env", False)),
                ) as client,
                client.stream(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json_body,
                    content=content,
                ) as response,
            ):
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > max_response_bytes:
                        raise ConfigurationError(
                            "HTTP response exceeds configured max_response_bytes"
                        )
                    chunks.append(chunk)
                body = b"".join(chunks)
                status_code = response.status_code
                content_type = response.headers.get("content-type", "")
                cost_header = (
                    response.headers.get(str(config.get("cost_header", "")))
                    if config.get("trust_cost_header")
                    else None
                )
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            resources = ResourceVector(
                monetary_usd=(
                    float(cost_header)
                    if cost_header is not None
                    else context.estimate.resources.monetary_usd
                ),
                latency_ms=elapsed_ms,
                network_bytes=request_bytes + total,
                context_tokens=approximate_tokens(body.decode("utf-8", errors="replace")),
            )
            metadata = {
                "method": method,
                "host": urlparse(url).hostname,
                "status_code": status_code,
                "response_bytes": total,
                "response_truncated": False,
            }
            accepted = config.get("accepted_statuses")
            if accepted is None:
                successful_status = 200 <= status_code < 300
            else:
                successful_status = status_code in {int(item) for item in accepted}
            if not successful_status:
                return RawExecution(
                    status=ExecutionStatus.FAILED,
                    resources=resources,
                    error_type="HTTPStatusError",
                    error_message=f"HTTP request returned status {status_code}",
                    metadata=metadata,
                )
            text = body.decode(response.encoding or "utf-8", errors="replace")
            output_type = str(config.get("output", {}).get("type", "auto"))
            if output_type == "json" or (output_type == "auto" and "json" in content_type):
                output: Any = json.loads(text)
            elif output_type in {"text", "auto"}:
                output = text.strip() if config.get("output", {}).get("strip", True) else text
            else:
                raise ConfigurationError(f"unsupported HTTP output type {output_type!r}")
            output = extract_path(output, config.get("output", {}).get("path"))
            resources.context_tokens = approximate_tokens(output)
            return RawExecution(
                status=ExecutionStatus.SUCCESS,
                output=output,
                resources=resources,
                metadata=metadata,
            )
        except TimeoutError:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            return RawExecution(
                status=ExecutionStatus.TIMEOUT,
                resources=ResourceVector(
                    monetary_usd=context.estimate.resources.monetary_usd,
                    latency_ms=elapsed_ms,
                    network_bytes=request_bytes,
                ),
                error_type="TimeoutError",
                error_message=f"HTTP request exceeded {timeout:g} seconds",
            )
        except httpx.TimeoutException as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            return RawExecution(
                status=ExecutionStatus.TIMEOUT,
                resources=ResourceVector(
                    monetary_usd=context.estimate.resources.monetary_usd,
                    latency_ms=elapsed_ms,
                    network_bytes=request_bytes,
                ),
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            return RawExecution(
                status=ExecutionStatus.FAILED,
                resources=ResourceVector(
                    monetary_usd=context.estimate.resources.monetary_usd,
                    latency_ms=elapsed_ms,
                    network_bytes=request_bytes,
                ),
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
