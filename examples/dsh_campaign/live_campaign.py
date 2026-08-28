"""Define and validate the bounded live DeepSeek Harness proof."""

from __future__ import annotations

import argparse
import json
import random
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from aeep.proofs import DSHLiveComparisonArm, DSHLiveComparisonReport, DSHLiveProofReport

NATIVE_ARMS = ("DSH_DIRECT", "AEEP_MODEL_FACING_MCP", "AEEP_HOST_NATIVE")
NATIVE_CATEGORIES = (
    "structured_extraction",
    "classification",
    "code_comprehension",
    "deterministic_file_text",
    "bounded_summarization",
)
NATIVE_CONDITIONS = (
    "cold",
    "warm",
    "cache_eviction",
    "compaction",
    "provider_switch",
    "tool_switch",
)


def native_plan() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for category in NATIVE_CATEGORIES:
        for condition in NATIVE_CONDITIONS:
            case_id = f"{category}:{condition}"
            order = list(NATIVE_ARMS)
            random.Random(f"aeep-0.5.1:{case_id}").shuffle(order)
            cases.append(
                {
                    "case_id": case_id,
                    "category": category,
                    "condition": condition,
                    "arm_order": order,
                    "prompt_contract": "task only; oracle answer is held outside the prompt",
                }
            )
    return {
        "schema_version": "0.5.1",
        "live_execution": False,
        "requires_separate_user_approval": True,
        "pilot_cases": 5,
        "pilot_excluded_from_main_results": True,
        "main_cases": len(cases),
        "main_trials": len(cases) * len(NATIVE_ARMS),
        "arms": list(NATIVE_ARMS),
        "fixed_model_and_reasoning": True,
        "cases": cases,
    }


def validate_native_plan() -> dict[str, Any]:
    plan = native_plan()
    assert plan["main_cases"] == 30
    assert plan["main_trials"] == 90
    assert all(set(item["arm_order"]) == set(NATIVE_ARMS) for item in plan["cases"])
    assert len({tuple(item["arm_order"]) for item in plan["cases"]}) > 1
    assert not any("expected answer" in item["prompt_contract"] for item in plan["cases"])
    return plan

LIST_TOOL = "mcp__aeep__aeep_list_capabilities"
ROUTE_TOOL = "mcp__aeep__aeep_route_action"
EXECUTE_TOOL = "mcp__aeep__aeep_execute_action"

LIVE_PLAN: tuple[dict[str, Any], ...] = (
    {
        "turn": 1,
        "session": "primary",
        "purpose": "discover only the AEEP-visible capabilities",
        "tool": LIST_TOOL,
        "arguments": {"query": "", "limit": 100, "include_executors": True},
        "expected_tool_status": "succeeded",
        "expected_aeep_receipts": 0,
        "assertion_code": "capabilities_discovered",
    },
    {
        "turn": 2,
        "session": "primary",
        "purpose": "execute deterministic built-in text statistics",
        "tool": EXECUTE_TOOL,
        "arguments": {
            "capability": "text.stats",
            "input": {"text": "alpha beta\nsecond line"},
            "dry_run": False,
            "detail": "compact",
        },
        "expected_tool_status": "succeeded",
        "expected_aeep_receipts": 1,
        "assertion_code": "text_stats_correct",
        "expected_result": {"characters": 22, "words": 4, "lines": 2},
    },
    {
        "turn": 3,
        "session": "primary",
        "purpose": "route the qualified read capability without execution",
        "tool": ROUTE_TOOL,
        "arguments": {
            "capability": "dsh.coding-tools.read-file@1",
            "input": {"path": "document.txt"},
            "detail": "compact",
        },
        "expected_tool_status": "succeeded",
        "expected_aeep_receipts": 0,
        "assertion_code": "read_route_selected",
    },
    {
        "turn": 4,
        "session": "primary",
        "purpose": "execute the qualified read capability once",
        "tool": EXECUTE_TOOL,
        "arguments": {
            "capability": "dsh.coding-tools.read-file@1",
            "input": {"path": "document.txt"},
            "dry_run": False,
            "detail": "compact",
        },
        "expected_tool_status": "succeeded",
        "expected_aeep_receipts": 1,
        "assertion_code": "read_output_digest_matched",
    },
    {
        "turn": 5,
        "session": "fresh",
        "purpose": "repeat the same read in a fresh Harness session",
        "tool": EXECUTE_TOOL,
        "arguments": {
            "capability": "dsh.coding-tools.read-file@1",
            "input": {"path": "document.txt"},
            "dry_run": False,
            "detail": "compact",
        },
        "expected_tool_status": "succeeded",
        "expected_aeep_receipts": 1,
        "assertion_code": "repeat_read_output_digest_matched",
    },
    {
        "turn": 6,
        "session": "fresh",
        "purpose": "prove an inactive write route fails closed",
        "tool": EXECUTE_TOOL,
        "arguments": {
            "capability": "dsh.coding-tools.apply-patch@1",
            "input": {
                "patch": "*** Begin Patch\n*** Add File: should-not-exist.txt\n+x\n*** End Patch"
            },
            "dry_run": False,
            "detail": "compact",
        },
        "expected_tool_status": "failed",
        "expected_aeep_receipts": 0,
        "assertion_code": "inactive_route_blocked",
    },
)


def prompts() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in LIVE_PLAN:
        result.append(
            {
                **item,
                "prompt": (
                    f"Call exactly `{item['tool']}` once with these JSON arguments: "
                    f"{json.dumps(item['arguments'], separators=(',', ':'))}. "
                    "Do not call another tool and do not retry. Do not repeat file contents; "
                    "return only the minimal result needed for this check."
                ),
            }
        )
    return result


def validate_plan() -> None:
    assert [item["turn"] for item in LIVE_PLAN] == list(range(1, 7))
    assert [item["session"] for item in LIVE_PLAN] == [
        "primary",
        "primary",
        "primary",
        "primary",
        "fresh",
        "fresh",
    ]
    assert sum(item["expected_aeep_receipts"] for item in LIVE_PLAN) == 3
    assert LIVE_PLAN[-1]["expected_tool_status"] == "failed"
    assert LIVE_PLAN[-1]["arguments"]["capability"].endswith("apply-patch@1")


def validate_report(report: DSHLiveProofReport) -> None:
    errors: list[str] = []
    for expected, observed in zip(LIVE_PLAN, report.turns, strict=True):
        expected_status = expected["expected_tool_status"]
        status = "failed" if observed.tool_failed else "succeeded"
        if observed.expected_tool != expected["tool"] or observed.observed_tool != expected["tool"]:
            errors.append(f"turn {observed.turn}: wrong tool")
        if observed.tool_calls != 1 or observed.tool_unresolved:
            errors.append(f"turn {observed.turn}: expected one resolved tool call")
        if status != expected_status:
            errors.append(f"turn {observed.turn}: expected {expected_status}, got {status}")
        if observed.expected_aeep_receipts != expected["expected_aeep_receipts"]:
            errors.append(f"turn {observed.turn}: wrong AEEP receipt expectation")
        if observed.assertion_code != expected["assertion_code"] or not observed.assertion_passed:
            errors.append(f"turn {observed.turn}: assertion failed")

    if report.turns[3].result_digest is None:
        errors.append("turn 4: missing sanitized result digest")
    if report.turns[3].result_digest != report.turns[4].result_digest:
        errors.append("fresh-session read did not reproduce the same result digest")
    if report.fixture_digest_before != report.fixture_digest_after:
        errors.append("fixture changed during the proof")
    if report.qualification_executions > 2:
        errors.append("qualification exceeded the two-execution bound")
    if report.active_community_routes_during != 1:
        errors.append("exactly one community route must be active during the proof")
    if report.active_community_routes_after != 0:
        errors.append("community routes must be suspended after the proof")
    if report.persisted_sensitive_matches:
        errors.append("sensitive fixture content reached AEEP persistence")
    if report.usage.model_calls < 6:
        errors.append("fewer model calls than completed Harness turns")
    if not all(gate.passed for gate in report.gates):
        errors.append("one or more hard gates failed")
    if errors:
        raise ValueError("; ".join(errors))


def validate_comparison(report: DSHLiveComparisonReport) -> None:
    errors: list[str] = []
    direct = [item for item in report.trials if item.arm is DSHLiveComparisonArm.DIRECT_MODEL]
    routed = [item for item in report.trials if item.arm is DSHLiveComparisonArm.AEEP_ROUTED]
    if not report.plugin_capability_discovered or not report.plugin_route_selected:
        errors.append("plugin discovery or route selection did not complete")
    if not report.plugin_route_estimate_available:
        errors.append("plugin route estimate was unavailable")
    if report.plugin_token_estimate_status != "unavailable":
        errors.append("community plugin token estimates must not be overstated")
    if any(item.model_calls != 1 or item.tool_calls for item in direct):
        errors.append("direct arm must use exactly one model call and no tool")
    if any(item.model_calls != 2 or item.tool_calls != 1 for item in routed):
        errors.append("AEEP arm must use two model calls and exactly one tool")
    if report.aeep_correct < report.direct_correct:
        errors.append("AEEP arm regressed fixture correctness")
    if report.tokens_saved_by_aeep >= 0:
        errors.append("measured token overhead must be reported honestly as negative savings")
    if report.active_plugin_candidates_after:
        errors.append("community plugin routes must remain suspended after the comparison")
    if not all(gate.passed for gate in report.gates):
        errors.append("one or more comparison hard gates failed")
    if errors:
        raise ValueError("; ".join(errors))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--print-plan", action="store_true")
    action.add_argument("--check-plan", action="store_true")
    action.add_argument("--check-report", type=Path)
    action.add_argument("--check-comparison", type=Path)
    action.add_argument("--print-native-plan", action="store_true")
    action.add_argument("--check-native-plan", action="store_true")
    args = parser.parse_args(argv)
    validate_plan()
    if args.print_native_plan:
        print(json.dumps(validate_native_plan(), indent=2))
    elif args.check_native_plan:
        plan = validate_native_plan()
        print(json.dumps({key: plan[key] for key in ("main_cases", "main_trials", "requires_separate_user_approval")}))
    elif args.print_plan:
        print(json.dumps({"schema_version": "0.5", "turns": prompts()}, indent=2))
    elif args.check_plan:
        print(json.dumps({"turns": len(LIVE_PLAN), "expected_aeep_receipts": 3}))
    elif args.check_report is not None:
        report = DSHLiveProofReport.model_validate_json(args.check_report.read_bytes())
        validate_report(report)
        print(json.dumps({"gates_passed": True, "turns": len(report.turns)}))
    else:
        comparison = DSHLiveComparisonReport.model_validate_json(
            args.check_comparison.read_bytes()
        )
        validate_comparison(comparison)
        print(
            json.dumps(
                {
                    "gates_passed": True,
                    "trials": len(comparison.trials),
                    "tokens_saved_by_aeep": comparison.tokens_saved_by_aeep,
                }
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
