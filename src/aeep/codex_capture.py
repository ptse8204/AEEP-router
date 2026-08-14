"""Bounded Codex JSONL usage capture without a vendor SDK dependency."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from .errors import ConfigurationError
from .models import (
    EvidenceSource,
    EvidenceStatus,
    MeasurementEvidence,
    ModelAccessChannel,
    ModelTokenUsage,
    TrustLevel,
)


def parse_codex_jsonl(
    lines: Iterable[str],
    *,
    provider: str = "openai",
    model: str,
    access_channel: ModelAccessChannel = ModelAccessChannel.SUBSCRIPTION,
    fallback_usage: list[ModelTokenUsage] | None = None,
    max_bytes: int = 10_000_000,
) -> ModelTokenUsage:
    """Extract only terminal usage; prompts, outputs, commands, and diffs are discarded."""

    total = 0
    terminal: dict[str, Any] | None = None
    failed = False
    fields = (
        "input_tokens",
        "cached_input_tokens",
        "cache_write_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
    )
    for line in lines:
        total += len(line.encode("utf-8"))
        if total > max_bytes:
            raise ConfigurationError("Codex JSONL exceeds the configured size limit")
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ConfigurationError("Codex emitted malformed JSONL") from exc
        if not isinstance(event, dict):
            continue
        if event.get("type") == "turn.failed":
            failed = True
            continue
        if event.get("type") != "turn.completed":
            continue
        usage = event.get("usage")
        if not isinstance(usage, dict):
            continue
        normalized = {field: usage[field] for field in fields if field in usage}
        if terminal is not None and terminal != normalized:
            raise ConfigurationError("conflicting terminal Codex usage events")
        terminal = normalized
    had_terminal = terminal is not None
    if terminal is None and failed:
        raise ConfigurationError("Codex turn failed without terminal usage")
    usable_fallbacks = [
        usage
        for usage in fallback_usage or []
        if usage.evidence.status != EvidenceStatus.UNAVAILABLE
    ]
    if terminal is None and not usable_fallbacks:
        raise ConfigurationError("Codex JSONL contains no terminal usage event")
    terminal = dict(terminal or {})
    conflict = False
    for fallback in usable_fallbacks:
        if fallback.provider != provider or fallback.model != model:
            raise ConfigurationError("fallback usage does not match Codex provider/model")
        for field in fields:
            if field not in fallback.model_fields_set:
                continue
            fallback_value = getattr(fallback, field)
            if field in terminal:
                conflict |= terminal[field] != fallback_value
            else:
                terminal[field] = fallback_value
    status = (
        EvidenceStatus.CONFLICT
        if conflict
        else EvidenceStatus.COMPLETE
        if all(
            field in terminal for field in ("input_tokens", "cached_input_tokens", "output_tokens")
        )
        else EvidenceStatus.PARTIAL
    )
    return ModelTokenUsage(
        provider=provider,
        model=model,
        access_channel=access_channel,
        **terminal,
        evidence=MeasurementEvidence(
            status=status,
            source=(
                EvidenceSource.LOCAL_METER if had_terminal else usable_fallbacks[0].evidence.source
            ),
            trust=(TrustLevel.OBSERVED if had_terminal else usable_fallbacks[0].evidence.trust),
        ),
    )
