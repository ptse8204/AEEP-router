from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from aeep.models import ExecutionStatus
from aeep.proofs import (
    ApplicationAttemptState,
    DSHCampaignArm,
    DSHLiveComparisonReport,
    DSHLiveProofReport,
    DSHProofReport,
    JobProofReport,
)

ROOT = Path(__file__).resolve().parents[1]


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
