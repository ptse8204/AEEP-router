from __future__ import annotations

import json
import os
import runpy
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from aeep.models import ExecutionStatus
from aeep.proofs import (
    ApplicationAttemptState,
    DSHCampaignArm,
    DSHLiveComparisonReport,
    DSHLiveProofReport,
    DSHProofReport,
    JobProofReport,
    RoutingValueReport,
    RoutingValueStatus,
    RoutingValueTrial,
)

ROOT = Path(__file__).resolve().parents[1]


def test_live_plugin_campaign_parser_sanitizes_session_events() -> None:
    campaign = runpy.run_path(str(ROOT / "examples/dsh_campaign/plugin_campaign.py"))
    events = [
        {
            "type": "assistant/message",
            "data": {
                "usage": {
                    "inputTokens": 10,
                    "outputTokens": 2,
                    "cacheReadTokens": 20,
                    "cacheWriteTokens": 3,
                    "reasoningTokens": 1,
                },
                "message": {
                    "source": {"kind": "model"},
                    "content": [{"type": "text", "text": "proof-value"}],
                }
            },
        },
        {"type": "tool/call", "data": {"name": "web_fetch", "arguments": "secret"}},
        {
            "type": "tool/result",
            "data": {
                "message": {
                    "content": [
                        {
                            "type": "tool-result",
                            "toolCallId": "call-1",
                            "content": [{"type": "text", "text": "fixture output"}],
                            "isError": False,
                        }
                    ]
                }
            },
        },
        {"type": "turn/end", "data": {"reason": {"kind": "completed"}}},
    ]
    parsed = campaign["parse_session_events"](json.dumps(item) for item in events)

    assert parsed["completed"] is True
    assert parsed["tools"] == ["web_fetch"]
    assert parsed["usage"]["total_tokens"] == 35
    assert parsed["usage"]["cache_write_tokens"] == 3
    assert parsed["rendered_result_bytes"] > 0
    assert "secret" not in json.dumps(parsed)


def test_live_plugin_campaign_resolves_database_from_manifest(tmp_path: Path) -> None:
    campaign = runpy.run_path(str(ROOT / "examples/dsh_campaign/plugin_campaign.py"))
    manifest = tmp_path / "aeep.yaml"
    campaign["_database"].__globals__["load_manifest"] = lambda _: (
        SimpleNamespace(database=Path(".aeep/campaign.db")),
        {},
    )

    assert campaign["_database"](manifest) == tmp_path / ".aeep/campaign.db"


def test_live_plugin_campaign_requires_the_planned_capabilities() -> None:
    campaign = runpy.run_path(str(ROOT / "examples/dsh_campaign/plugin_campaign.py"))
    cases = [
        {
            "case_id": capability,
            "capability": capability,
            "input": {},
            "prompt": "fixture",
            "expected": "fixture",
            "expected_tool": "fixture",
            "native_patch": "fixture",
            "manifest": "fixture",
        }
        for capability in sorted(
            {"web.page.read@1", "github.file.read@1", "document.text.extract@1"}
        )
    ]
    definition = {
        "harness_version": "0.1.1-rc.2",
        "model": "fixture-model",
        "settings": {"temperature": 0},
        "plugins": ["fixture-tools", "aeep-dsh-router"],
        "cases": cases,
    }
    assert campaign["validate_definition"](definition) == cases

    warmups, trials = campaign["build_plan"](cases, repetitions=10, seed=8204)
    assert len(warmups) == 6
    assert len(trials) == 60
    assert campaign["build_plan"](cases, repetitions=10, seed=8204) == (
        warmups,
        trials,
    )


def test_live_plugin_campaign_bootstrap_is_deterministic() -> None:
    campaign = runpy.run_path(str(ROOT / "examples/dsh_campaign/plugin_campaign.py"))
    interval = campaign["bootstrap_median_interval"](
        [2, 3, 4, 5], seed=8204, resamples=500
    )

    assert interval == campaign["bootstrap_median_interval"](
        [2, 3, 4, 5], seed=8204, resamples=500
    )
    assert interval["ci95_low"] > 0
    assert campaign["classify_savings"](
        [{"passed": True}], {"ci95_low": -1.0, "ci95_high": 2.0}
    ) == "inconclusive"
    assert campaign["classify_savings"](
        [{"passed": True}], {"ci95_low": 1.0, "ci95_high": 2.0}
    ) == "demonstrated_savings"


def run_script(script: str, destination: Path) -> None:
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    process = subprocess.run(
        [
            sys.executable,
            str(ROOT / script),
            "--output-dir",
            str(destination),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert process.returncode == 0, process.stdout + process.stderr


def test_dsh_fixture_proof_uses_real_router_receipts_and_bounded_smoke(
    tmp_path: Path,
) -> None:
    run_script("examples/dsh_campaign/campaign.py", tmp_path)
    report = DSHProofReport.model_validate_json((tmp_path / "campaign.json").read_bytes())

    assert all(gate.passed for gate in report.gates)
    assert {trial.arm for trial in report.trials} == set(DSHCampaignArm)
    assert all(trial.receipt_id is not None and trial.task_valid for trial in report.trials)
    assert all(len(trial.receipt_ids) == trial.fallback_count + 1 for trial in report.trials)
    assert all(trial.smoke_executions <= 2 for trial in report.trials)
    assert all(
        trial.shared_trials_reused == 100
        for trial in report.trials
        if trial.arm in {DSHCampaignArm.AEEP_SHARED, DSHCampaignArm.AEEP_ADAPTIVE}
    )
    fallbacks = [trial for trial in report.trials if trial.workload_id != "static"]
    assert {trial.workload_id for trial in fallbacks} == {"js", "malformed"}
    assert all(trial.fallback_count == 1 and trial.task_valid for trial in fallbacks)
    for name in (
        "receipts.jsonl",
        "evidence-reuse.json",
        "cache-affinity.json",
        "rate-card-revaluation.json",
        "route-regret.json",
    ):
        assert (tmp_path / name).is_file()

    normal = [
        trial
        for trial in report.trials
        if trial.workload_id == "static" and trial.trial_id.endswith(":0")
    ]
    suggested = {
        trial.capability: (trial.actual_input_tokens or 0)
        + (trial.actual_output_tokens or 0)
        for trial in normal
        if trial.arm is DSHCampaignArm.DSH_SUGGESTED
    }
    assert all(
        (trial.actual_input_tokens or 0) + (trial.actual_output_tokens or 0)
        < suggested[trial.capability]
        for trial in normal
        if trial.arm in {DSHCampaignArm.AEEP_SHARED, DSHCampaignArm.AEEP_ADAPTIVE}
    )


def test_live_dsh_plan_requires_six_sanitized_fail_closed_turns(
    tmp_path: Path,
) -> None:
    tools = [
        "mcp__aeep__aeep_list_capabilities",
        "mcp__aeep__aeep_execute_action",
        "mcp__aeep__aeep_route_action",
        "mcp__aeep__aeep_execute_action",
        "mcp__aeep__aeep_execute_action",
        "mcp__aeep__aeep_execute_action",
    ]
    assertion_codes = [
        "capabilities_discovered",
        "text_stats_correct",
        "read_route_selected",
        "read_output_digest_matched",
        "repeat_read_output_digest_matched",
        "inactive_route_blocked",
    ]
    receipt_counts = [0, 1, 0, 1, 1, 0]
    turns = []
    result_digest = "sha256:" + "a" * 64
    for turn, (tool, assertion_code, receipt_count) in enumerate(
        zip(tools, assertion_codes, receipt_counts, strict=True),
        start=1,
    ):
        failed = turn == 6
        turns.append(
            {
                "turn": turn,
                "session": "primary" if turn <= 4 else "fresh",
                "expected_tool": tool,
                "observed_tool": tool,
                "tool_calls": 1,
                "tool_succeeded": int(not failed),
                "tool_failed": int(failed),
                "tool_unresolved": 0,
                "expected_aeep_receipts": receipt_count,
                "aeep_receipt_ids": tuple(
                    f"receipt-{turn}-{index}" for index in range(receipt_count)
                ),
                "verification_receipt_hash": "sha256:" + f"{turn:064x}",
                "assertion_code": assertion_code,
                "assertion_passed": True,
                "result_digest": result_digest if turn in {4, 5} else None,
            }
        )
    report = DSHLiveProofReport.model_validate(
        {
            "campaign_id": "aeep-v05-deepseek-harness-live",
            "generated_at": datetime(2026, 8, 24, tzinfo=UTC),
            "harness_version": "0.1.0-rc.8",
            "fixture_digest_before": "sha256:" + "b" * 64,
            "fixture_digest_after": "sha256:" + "b" * 64,
            "qualification_executions": 1,
            "active_community_routes_during": 1,
            "active_community_routes_after": 0,
            "persisted_sensitive_matches": 0,
            "turns": turns,
            "usage": {
                "provider": "deepseek-official",
                "model": "deepseek-v4-flash",
                "model_calls": 12,
                "input_tokens": 100,
                "output_tokens": 20,
                "cache_read_tokens": 10,
                "cache_write_tokens": 0,
                "total_tokens": 130,
            },
            "gates": [{"name": "all", "passed": True, "detail": "fixture"}],
        }
    )
    report_path = tmp_path / "live-report.json"
    report_path.write_text(report.model_dump_json(), encoding="utf-8")
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    command = [
        sys.executable,
        str(ROOT / "examples/dsh_campaign/live_campaign.py"),
        "--check-report",
        str(report_path),
    ]
    passed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert passed.returncode == 0, passed.stdout + passed.stderr

    report_path.write_text(
        report.model_copy(update={"active_community_routes_after": 1}).model_dump_json(),
        encoding="utf-8",
    )
    failed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert failed.returncode != 0
    assert "suspended after" in failed.stderr


def test_native_dsh_plan_is_paired_randomized_and_requires_approval() -> None:
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    process = subprocess.run(
        [
            sys.executable,
            str(ROOT / "examples/dsh_campaign/live_campaign.py"),
            "--print-native-plan",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    plan = __import__("json").loads(process.stdout)
    assert plan["main_cases"] == 30
    assert plan["main_trials"] == 90
    assert plan["requires_separate_user_approval"] is True
    assert set(plan["arms"]) == {
        "DSH_DIRECT",
        "AEEP_MODEL_FACING_MCP",
        "AEEP_HOST_NATIVE",
    }
    assert len({tuple(item["arm_order"]) for item in plan["cases"]}) > 1


def test_job_fixture_proof_requires_approval_and_reconciles_timeout(
    tmp_path: Path,
) -> None:
    run_script("examples/job_application/campaign.py", tmp_path)
    report = JobProofReport.model_validate_json((tmp_path / "campaign.json").read_bytes())

    assert all(gate.passed for gate in report.gates)
    assert report.postings == 30
    assert report.unique_canonical_jobs == 27
    assert report.duplicate_postings == 3
    assert len(report.attempts) == report.unique_canonical_jobs
    assert len(report.form_family_ids) == report.form_families == 3
    assert all(attempt.approval_id is not None for attempt in report.attempts)
    assert len({attempt.idempotency_key for attempt in report.attempts}) == len(
        report.attempts
    )
    assert any(
        attempt.state is ApplicationAttemptState.RECONCILED
        for attempt in report.attempts
    )
    assert ExecutionStatus.TIMEOUT in report.execution_statuses
    for name in (
        "receipts.jsonl",
        "routing-decisions.jsonl",
        "resume-provenance.jsonl",
        "application-attempts.jsonl",
        "safety-audit.json",
    ):
        assert (tmp_path / name).is_file()


def test_live_dsh_comparison_reports_overhead_without_marketing_it_as_savings(
    tmp_path: Path,
) -> None:
    trials = []
    for arm, model_calls, tool_calls, per_trial_tokens in (
        ("DIRECT_MODEL", 1, 0, 100),
        ("AEEP_ROUTED", 2, 1, 200),
    ):
        for index in range(3):
            trials.append(
                {
                    "trial_id": f"{arm}-{index}",
                    "task_id": f"task-{index}",
                    "arm": arm,
                    "correct": arm == "AEEP_ROUTED" or index != 1,
                    "model_calls": model_calls,
                    "tool_calls": tool_calls,
                    "receipt_id": f"receipt-{index}" if tool_calls else None,
                    "usage": {
                        "provider": "deepseek-official",
                        "model": "deepseek-v4-flash",
                        "model_calls": model_calls,
                        "input_tokens": per_trial_tokens - 10,
                        "output_tokens": 10,
                        "cache_read_tokens": 0,
                        "cache_write_tokens": 0,
                        "total_tokens": per_trial_tokens,
                    },
                }
            )
    report = DSHLiveComparisonReport.model_validate(
        {
            "campaign_id": "live-comparison",
            "generated_at": datetime(2026, 8, 24, tzinfo=UTC),
            "harness_version": "0.1.1-rc.2",
            "mcp_client_version": "0.1.0-rc.8",
            "model": "deepseek-v4-flash",
            "reasoning_effort": "low",
            "pilot_sessions_excluded": 3,
            "imported_plugin_candidates": 18,
            "active_plugin_candidates_after": 0,
            "plugin_capability_discovered": True,
            "plugin_route_selected": True,
            "plugin_route_estimate_available": True,
            "plugin_token_estimate_status": "unavailable",
            "trials": trials,
            "direct_total_tokens": 300,
            "aeep_total_tokens": 600,
            "tokens_saved_by_aeep": -300,
            "savings_percent": "-100",
            "direct_correct": 2,
            "aeep_correct": 3,
            "gates": [{"name": "honest", "passed": True, "detail": "fixture"}],
        }
    )
    path = tmp_path / "comparison.json"
    path.write_text(report.model_dump_json(), encoding="utf-8")
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    process = subprocess.run(
        [
            sys.executable,
            str(ROOT / "examples/dsh_campaign/live_campaign.py"),
            "--check-comparison",
            str(path),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert process.returncode == 0, process.stdout + process.stderr


def test_routing_value_report_keeps_negative_regret() -> None:
    trial = RoutingValueTrial(
        trial_id="negative-1",
        workload_digest="sha256:" + "a" * 64,
        cohort_digest="sha256:" + "b" * 64,
        selected_executor_id="selected",
        baseline_executor_id="baseline",
        selected_receipt_id="selected-receipt",
        baseline_receipt_id="baseline-receipt",
        routing_overhead_ms=Decimal("2"),
        selected_total_latency_ms=Decimal("120"),
        baseline_total_latency_ms=Decimal("100"),
        signed_latency_delta_ms=Decimal("20"),
        selected_cash_usd=Decimal("0.02"),
        baseline_cash_usd=Decimal("0.01"),
        signed_cash_delta_usd=Decimal("0.01"),
        selected_model_tokens=200,
        baseline_model_tokens=100,
        signed_token_delta=100,
        status=RoutingValueStatus.NEGATIVE,
    )
    report = RoutingValueReport(
        report_id="routing-value-1",
        generated_at=datetime(2026, 8, 26, tzinfo=UTC),
        paired_trials=(trial,),
    )

    assert report.paired_trials[0].signed_token_delta == 100
    assert report.paired_trials[0].status is RoutingValueStatus.NEGATIVE
