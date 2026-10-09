import json
import sys
import time

import pytest

from aeep.hosts.codex_accounting import TOKEN_FIELDS, turn_accounting
from aeep.hosts.codex_app_server import (
    CodexAppServerAdapter,
    CodexProtocolError,
    _token_usage,
    _TurnCollector,
)
from aeep.models import EvidenceStatus, ExecutionStatus


@pytest.mark.parametrize("wire", list(TOKEN_FIELDS))
def test_each_missing_field_stays_unknown_instead_of_a_complete_zero(wire):
    supplied = dict(
        inputTokens=10,
        outputTokens=5,
        cachedInputTokens=2,
        cacheWriteInputTokens=0,
        reasoningOutputTokens=1,
        totalTokens=15,
    )
    del supplied[wire]
    parsed = _token_usage(supplied)
    assert parsed == supplied and wire not in parsed
    resources, accounting = turn_accounting(parsed, model="fixture-model", resource_pool="fixture")
    assert TOKEN_FIELDS[wire] not in resources.model_fields_set
    assert (
        not accounting.model_usage
        or accounting.model_usage[0].evidence.status == EvidenceStatus.PARTIAL
    )
    assert resources.input_tokens == (0 if wire == "inputTokens" else 10)


def test_explicit_zero_counts_remain_complete_and_unknown_cash_is_not_zero():
    parsed = _token_usage(dict.fromkeys([*TOKEN_FIELDS, "totalTokens"], 0))
    resources, accounting = turn_accounting(parsed, model="fixture-model", resource_pool="fixture")
    assert resources.input_tokens == resources.output_tokens == 0
    assert accounting.model_usage[0].evidence.status == EvidenceStatus.COMPLETE
    assert accounting.cash.actual_cash_cost("USD") is None
    resources, accounting = turn_accounting(
        _token_usage({"totalTokens": 17}), model="fixture-model", resource_pool="fixture"
    )
    assert "input_tokens" not in resources.model_fields_set and not accounting.model_usage


@pytest.mark.asyncio
async def test_invalid_later_usage_stops_the_turn_and_retains_prior_partial_counts():
    collector = _TurnCollector(max_output_bytes=1024)
    collector.actual_model = "fixture-model"
    collector.turn_id = "fixture-turn"
    collector.handle(
        "thread/tokenUsage/updated",
        {"tokenUsage": {"total": {"inputTokens": 12, "outputTokens": 4}}},
    )
    collector.handle("thread/tokenUsage/updated", {"tokenUsage": {"total": {"inputTokens": True}}})
    with pytest.raises(CodexProtocolError, match="invalid token usage"):
        await collector.future
    adapter = CodexAppServerAdapter(
        argv=(sys.executable,), resource_id="fixture", principal_salt=b"fixture-key"
    )
    try:
        raw = adapter._partial_execution(collector, ExecutionStatus.FAILED, time.monotonic())
        assert (
            raw.resources.input_tokens == 12
            and "cached_input_tokens" not in raw.resources.model_fields_set
        )
        assert raw.accounting.model_usage[0].evidence.status == EvidenceStatus.PARTIAL
        assert json.loads(raw.metadata["codex_token_fields"]) == ["inputTokens", "outputTokens"]
    finally:
        await adapter.close()


@pytest.mark.parametrize(
    "payload", [{}, None, {"outputTokens": None}, {"inputTokens": -1}, {"outputTokens": 1.5}]
)
def test_invalid_or_empty_usage_cannot_create_zero_observations(payload):
    assert _token_usage(payload) is None


@pytest.mark.asyncio
async def test_completed_protocol_without_one_token_category_remains_partial(tmp_path):
    from dataclasses import replace

    from test_codex_subscription_adapter import FAKE, context

    script = tmp_path / "fake_codex_missing_usage.py"
    original = FAKE.read_text()
    assert '        "cachedInputTokens": 2,\n' in original
    script.write_text(original.replace('        "cachedInputTokens": 2,\n', ""))
    argv = (sys.executable, "-u", str(script), "--scenario", "success")
    host = CodexAppServerAdapter(
        argv=argv, resource_id="fixture", principal_salt=b"fixture-key", request_timeout=2
    )
    current = context()
    current = replace(current, config=current.config.model_copy(update={"argv": argv}))
    try:
        raw = await host.execute(current)
        assert raw.status == ExecutionStatus.SUCCESS
        assert raw.resources.input_tokens == 7 and raw.resources.output_tokens == 3
        assert "cachedInputTokens" not in json.loads(raw.metadata["codex_token_fields"])
        assert raw.accounting.model_usage[0].evidence.status == EvidenceStatus.PARTIAL
    finally:
        await host.close()


def test_receipt_retains_only_usage_field_names_not_unreviewed_task_contents():
    from aeep.router import Router

    retained = Router._safe_receipt_metadata(
        {"codex_token_fields": '["inputTokens"]', "task_prompt": "private fixture"}
    )
    assert retained == {"codex_token_fields": '["inputTokens"]'}


@pytest.mark.asyncio
async def test_missing_later_usage_retains_known_counts_without_completion_claim():
    collector = _TurnCollector(max_output_bytes=1024)
    known = dict.fromkeys([*TOKEN_FIELDS, "totalTokens"], 0)
    collector.handle("thread/tokenUsage/updated", {"tokenUsage": {"total": known}})
    collector.handle("thread/tokenUsage/updated", {"tokenUsage": {"total": {}}})
    assert collector.token_usage == known and collector.usage_incomplete
    collector.handle("turn/completed", {"turn": {"status": "completed"}})
    assert (await collector.future).token_usage == known


def test_unresolved_model_does_not_erase_observed_raw_counts():
    resources, accounting = turn_accounting({"inputTokens": 7}, model=None, resource_pool="fixture")
    assert resources.input_tokens == 7
    assert resources.model_fields_set == {"input_tokens"}
    assert not accounting.model_usage


@pytest.mark.asyncio
async def test_empty_final_snapshot_cannot_reuse_complete_earlier_usage(tmp_path):
    from dataclasses import replace

    from test_codex_subscription_adapter import FAKE, context

    script = tmp_path / "fake_codex_empty_final_usage.py"
    original = FAKE.read_text()
    assert "    terminal()\n" in original
    script.write_text(
        original.replace(
            "    terminal()\n",
            '    send({"method": "thread/tokenUsage/updated", "params": {"tokenUsage": {"total": {}}}})\n    terminal()\n',
            1,
        )
    )
    argv = (sys.executable, "-u", str(script), "--scenario", "success")
    host = CodexAppServerAdapter(
        argv=argv, resource_id="fixture", principal_salt=b"fixture-key", request_timeout=2
    )
    current = context()
    current = replace(current, config=current.config.model_copy(update={"argv": argv}))
    try:
        raw = await host.execute(current)
        assert raw.status == ExecutionStatus.SUCCESS
        assert raw.resources.input_tokens == 7 and raw.resources.output_tokens == 3
        assert raw.accounting.model_usage[0].evidence.status == EvidenceStatus.PARTIAL
        assert json.loads(raw.metadata["codex_token_fields"]) == []
    finally:
        await host.close()
