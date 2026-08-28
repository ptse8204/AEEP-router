"""Run randomized paired DSH/direct trials against the host-native AEEP adapter."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sqlite3
import statistics
import subprocess
import time
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aeep.config import load_manifest
from aeep.proofs import DSHPluginCampaignReport

ARMS = ("DSH_DIRECT", "AEEP_HOST_NATIVE")
REQUIRED_CAPABILITIES = {
    "web.page.read@1",
    "github.file.read@1",
    "document.text.extract@1",
}


def digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def digest_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return digest_text(encoded)


def _json_bytes(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


def parse_session_events(lines: Iterable[str]) -> dict[str, Any]:
    """Reduce a DSH log to sanitized authoritative usage and pressure counters."""

    usage = {
        "model_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens": 0,
    }
    tools: list[str] = []
    exposed_tools: set[str] = set()
    tool_schema_bytes = 0
    rendered_result_bytes = 0
    rendered_result_approx_tokens = 0
    tool_result_digests: list[str] = []
    next_model_input_tokens = 0
    waiting_for_next_model = False
    final_text = ""
    completed = False
    for line in lines:
        event = json.loads(line)
        event_type = event.get("type")
        data = event.get("data", {})
        if event_type == "request/header":
            schemas = data.get("header", {}).get("tools", [])
            if isinstance(schemas, list):
                exposed_tools.update(
                    item["name"]
                    for item in schemas
                    if isinstance(item, dict) and isinstance(item.get("name"), str)
                )
                tool_schema_bytes = max(tool_schema_bytes, _json_bytes(schemas))
        elif event_type == "tool/call":
            name = data.get("name")
            if isinstance(name, str):
                tools.append(name)
        elif event_type == "tool/result":
            content = data.get("content")
            if content is None and isinstance(data.get("message"), dict):
                content = data["message"].get("content")
            if content is None and isinstance(data.get("result"), dict):
                content = data["result"].get("content")
            if isinstance(content, list):
                measured = _json_bytes(content)
                rendered_result_bytes += measured
                rendered_result_approx_tokens += (measured + 3) // 4
                tool_result_digests.append(digest_json(content))
                waiting_for_next_model = True
        elif event_type == "assistant/message":
            message = data.get("message", {})
            if message.get("source", {}).get("kind") != "model":
                continue
            measured = data.get("usage") or message.get("usage", {})
            usage["model_calls"] += 1
            for source, target in (
                ("inputTokens", "input_tokens"),
                ("outputTokens", "output_tokens"),
                ("cacheReadTokens", "cache_read_tokens"),
                ("cacheWriteTokens", "cache_write_tokens"),
                ("reasoningTokens", "reasoning_tokens"),
            ):
                value = measured.get(source, 0)
                if isinstance(value, int) and value >= 0:
                    usage[target] += value
            if waiting_for_next_model:
                next_model_input_tokens += sum(
                    measured.get(name, 0)
                    for name in ("inputTokens", "cacheReadTokens", "cacheWriteTokens")
                    if isinstance(measured.get(name, 0), int)
                    and measured.get(name, 0) >= 0
                )
                waiting_for_next_model = False
            text_blocks = [
                item.get("text", "")
                for item in message.get("content", [])
                if item.get("type") == "text"
            ]
            if text_blocks:
                final_text = "\n".join(text_blocks)
        elif event_type == "turn/end":
            completed = data.get("reason", {}).get("kind") == "completed"
    usage["total_input_tokens"] = (
        usage["input_tokens"]
        + usage["cache_read_tokens"]
        + usage["cache_write_tokens"]
    )
    usage["total_tokens"] = usage["total_input_tokens"] + usage["output_tokens"]
    return {
        "completed": completed,
        "tools": tools,
        "exposed_tool_names": sorted(exposed_tools),
        "exposed_tool_count": len(exposed_tools),
        "tool_schema_bytes": tool_schema_bytes,
        "rendered_result_bytes": rendered_result_bytes,
        "rendered_result_approx_tokens": rendered_result_approx_tokens,
        "tool_result_digests": tool_result_digests,
        "next_model_input_tokens": next_model_input_tokens,
        "final_text": final_text,
        "final_digest": digest_text(final_text),
        "usage": usage,
    }


def validate_definition(definition: dict[str, Any]) -> list[dict[str, Any]]:
    for name in ("harness_version", "model"):
        if not isinstance(definition.get(name), str) or not definition[name]:
            raise ValueError(f"campaign definition needs {name}")
    if not isinstance(definition.get("settings"), dict):
        raise ValueError("campaign definition needs fixed settings")
    if not isinstance(definition.get("plugins"), list) or any(
        not isinstance(item, str) or not item for item in definition["plugins"]
    ):
        raise ValueError("campaign definition needs a plugin inventory")
    cases = definition.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("campaign definition needs cases")
    capabilities = {item.get("capability") for item in cases}
    if capabilities != REQUIRED_CAPABILITIES:
        raise ValueError("campaign must cover web, GitHub, and document reads exactly once")
    if len({item.get("case_id") for item in cases}) != len(cases):
        raise ValueError("campaign case IDs must be unique")
    required = {
        "case_id",
        "capability",
        "input",
        "prompt",
        "expected",
        "expected_tool",
        "native_patch",
        "manifest",
    }
    if any(not required.issubset(item) for item in cases):
        raise ValueError("campaign case is missing a required field")
    if any(not isinstance(item["input"], dict) for item in cases):
        raise ValueError("campaign case input must be an object")
    return cases


def build_plan(
    cases: list[dict[str, Any]], repetitions: int, seed: int
) -> tuple[list[tuple[str, dict[str, Any], int, bool]], list[tuple[str, dict[str, Any], int, bool]]]:
    if not 1 <= repetitions <= 100:
        raise ValueError("repetitions must be between 1 and 100")
    rng = random.Random(seed)
    warmups: list[tuple[str, dict[str, Any], int, bool]] = []
    blocks: list[list[tuple[str, dict[str, Any], int, bool]]] = []
    for case in cases:
        order = list(ARMS)
        rng.shuffle(order)
        warmups.extend((arm, case, -1, True) for arm in order)
        for repetition in range(repetitions):
            order = list(ARMS)
            rng.shuffle(order)
            blocks.append([(arm, case, repetition, False) for arm in order])
    rng.shuffle(blocks)
    return warmups, [trial for block in blocks for trial in block]


def bootstrap_median_interval(
    values: Sequence[int | float], *, seed: int, resamples: int = 10_000
) -> dict[str, float]:
    if not values or resamples < 100:
        raise ValueError("bootstrap needs values and at least 100 resamples")
    rng = random.Random(seed)
    medians = sorted(
        statistics.median(rng.choice(values) for _ in values)
        for _ in range(resamples)
    )
    return {
        "median": float(statistics.median(values)),
        "ci95_low": float(medians[int(resamples * 0.025)]),
        "ci95_high": float(medians[min(resamples - 1, int(resamples * 0.975))]),
        "resamples": resamples,
    }


def _session_files(session_root: Path) -> set[Path]:
    return set(session_root.glob("*/session.jsonl.zstd"))


def _read_session(path: Path, zstd: str) -> dict[str, Any]:
    result = subprocess.run(
        [zstd, "-dc", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return parse_session_events(result.stdout.splitlines())


def _database(path: str | Path) -> Path:
    manifest, _ = load_manifest(path)
    database = Path(manifest.database)
    return database if database.is_absolute() else Path(path).resolve().parent / database


def _receipt_ids(database: Path) -> set[str]:
    if not database.exists():
        return set()
    with sqlite3.connect(database) as connection:
        try:
            return {row[0] for row in connection.execute("SELECT receipt_id FROM receipts")}
        except sqlite3.OperationalError:
            return set()


def _new_receipts(database: Path, before: set[str]) -> list[dict[str, Any]]:
    if not database.exists():
        return []
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT receipt_id, payload_json FROM receipts ORDER BY started_at"
        ).fetchall()
    return [json.loads(payload) for receipt_id, payload in rows if receipt_id not in before]


def _receipt_pressure(
    receipts: list[dict[str, Any]], capability: str
) -> dict[str, Any]:
    tool_receipts = [item for item in receipts if item.get("capability") == capability]
    tool_ids = {item.get("receipt_id") for item in tool_receipts}
    footprints = [
        item.get("accounting", {}).get("tool_footprint")
        for item in tool_receipts
        if item.get("accounting", {}).get("tool_footprint")
    ]
    following = [
        item
        for item in receipts
        if tool_ids.intersection(
            item.get("metadata", {}).get("preceding_tool_receipt_ids", [])
        )
    ]
    return {
        "receipt_ids": sorted(item["receipt_id"] for item in tool_receipts),
        "selected_executor_ids": sorted({item["executor_id"] for item in tool_receipts}),
        "raw_result_bytes": sum(item["raw_result_bytes"] for item in footprints),
        "rendered_result_bytes": sum(item["filtered_result_bytes"] for item in footprints),
        "rendered_result_approx_tokens": sum(
            item["filtered_result_approx_tokens"] for item in footprints
        ),
        "next_model_calls": len(following),
        "next_model_input_tokens": sum(
            item.get("actual_resources", {}).get("input_tokens", 0)
            + item.get("actual_resources", {}).get("cached_input_tokens", 0)
            + item.get("actual_resources", {}).get("cache_write_input_tokens", 0)
            for item in following
        ),
        "next_model_attribution_ambiguous": any(
            item.get("metadata", {}).get("route_attribution_ambiguous", False)
            for item in following
        ),
    }


def _run_trial(
    *,
    arm: str,
    case: dict[str, Any],
    repetition: int,
    warmup: bool,
    dsh: Path,
    profile: str,
    workspace: Path,
    session_root: Path,
    direct_patch: Path,
    zstd: str,
    timeout: int,
) -> dict[str, Any]:
    native = arm == "AEEP_HOST_NATIVE"
    manifest = Path(case["manifest"])
    database = _database(manifest)
    before_receipts = _receipt_ids(database) if native else set()
    before_sessions = _session_files(session_root)
    command = [str(dsh), "--profile", profile, "--patch", str(direct_patch)]
    if native:
        command.extend(["--patch", str(case["native_patch"])])
        prompt = "/aeep " + json.dumps(
            {
                "capability": case["capability"],
                "input": case["input"],
                "prompt": case["prompt"],
            },
            separators=(",", ":"),
        )
    else:
        prompt = case["prompt"]
    command.append(prompt)
    started = time.perf_counter()
    process = subprocess.run(
        command,
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env={**os.environ, "NO_COLOR": "1"},
    )
    latency_ms = round((time.perf_counter() - started) * 1000, 3)
    created = _session_files(session_root) - before_sessions
    if len(created) != 1:
        raise RuntimeError(f"expected one new DSH session, found {len(created)}")
    parsed = _read_session(created.pop(), zstd)
    receipts = _new_receipts(database, before_receipts) if native else []
    pressure = _receipt_pressure(receipts, case["capability"]) if native else {
        "receipt_ids": [],
        "selected_executor_ids": [],
        "raw_result_bytes": parsed["rendered_result_bytes"],
        "rendered_result_bytes": parsed["rendered_result_bytes"],
        "rendered_result_approx_tokens": parsed["rendered_result_approx_tokens"],
        "next_model_calls": 0,
        "next_model_input_tokens": 0,
        "next_model_attribution_ambiguous": False,
    }
    expected = str(case["expected"])
    return {
        "trial_id": f"{case['case_id']}:{repetition}:{arm}{':warmup' if warmup else ''}",
        "case_id": case["case_id"],
        "capability": case["capability"],
        "repetition": repetition,
        "warmup": warmup,
        "arm": arm,
        "completed": parsed["completed"] and process.returncode == 0,
        "correct": expected.casefold() in parsed["final_text"].casefold(),
        "model_calls": parsed["usage"]["model_calls"],
        "tool_calls": len(parsed["tools"]),
        "expected_tool_called": case["expected_tool"] in parsed["tools"],
        "observed_tool_names": sorted(set(parsed["tools"])),
        "exposed_tool_names": parsed["exposed_tool_names"],
        "exposed_tool_count": parsed["exposed_tool_count"],
        "tool_schema_bytes": parsed["tool_schema_bytes"],
        "end_to_end_latency_ms": latency_ms,
        "usage": parsed["usage"],
        "pressure": pressure,
        "rendered_result_bytes": parsed["rendered_result_bytes"],
        "rendered_result_approx_tokens": parsed["rendered_result_approx_tokens"],
        "next_model_input_tokens": parsed["next_model_input_tokens"],
        "tool_result_digest": digest_text("|".join(parsed["tool_result_digests"])),
        "final_output_digest": parsed["final_digest"],
        "expected_output_digest": digest_text(expected),
    }


def _pairs(trials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key = {(item["case_id"], item["repetition"], item["arm"]): item for item in trials}
    pairs = []
    for case_id, repetition in sorted({(item["case_id"], item["repetition"]) for item in trials}):
        direct = by_key[(case_id, repetition, "DSH_DIRECT")]
        native = by_key[(case_id, repetition, "AEEP_HOST_NATIVE")]
        pairs.append(
            {
                "case_id": case_id,
                "repetition": repetition,
                "direct_total_tokens": direct["usage"]["total_tokens"],
                "aeep_total_tokens": native["usage"]["total_tokens"],
                "tokens_saved_by_aeep": direct["usage"]["total_tokens"]
                - native["usage"]["total_tokens"],
                "token_savings": {
                    bucket: direct["usage"][bucket] - native["usage"][bucket]
                    for bucket in (
                        "input_tokens",
                        "cache_read_tokens",
                        "cache_write_tokens",
                        "output_tokens",
                        "total_tokens",
                    )
                },
                "rendered_result_bytes_saved": direct["rendered_result_bytes"]
                - native["rendered_result_bytes"],
                "rendered_result_tokens_saved": direct["rendered_result_approx_tokens"]
                - native["rendered_result_approx_tokens"],
                "next_model_input_tokens_saved": direct["next_model_input_tokens"]
                - native["next_model_input_tokens"],
                "schema_bytes_saved": direct["tool_schema_bytes"]
                - native["tool_schema_bytes"],
                "latency_ms_saved": direct["end_to_end_latency_ms"]
                - native["end_to_end_latency_ms"],
                "tool_results_match": direct["tool_result_digest"]
                == native["tool_result_digest"],
                "correctness_matches": direct["correct"] == native["correct"],
            }
        )
    return pairs


def _median(values: Iterable[int | float]) -> float:
    return float(statistics.median(values))


def _arm_summaries(trials: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    summaries = {}
    for arm in ARMS:
        selected = [item for item in trials if item["arm"] == arm]
        summaries[arm] = {
            "trials": len(selected),
            "correct": sum(item["correct"] for item in selected),
            "median_usage": {
                bucket: _median(item["usage"][bucket] for item in selected)
                for bucket in (
                    "input_tokens",
                    "cache_read_tokens",
                    "cache_write_tokens",
                    "output_tokens",
                    "total_tokens",
                )
            },
            "median_rendered_result_bytes": _median(
                item["rendered_result_bytes"] for item in selected
            ),
            "median_rendered_result_approx_tokens": _median(
                item["rendered_result_approx_tokens"] for item in selected
            ),
            "median_next_model_input_tokens": _median(
                item["next_model_input_tokens"] for item in selected
            ),
            "median_exposed_tool_count": _median(
                item["exposed_tool_count"] for item in selected
            ),
            "median_tool_schema_bytes": _median(
                item["tool_schema_bytes"] for item in selected
            ),
            "median_model_calls": _median(item["model_calls"] for item in selected),
            "median_tool_calls": _median(item["tool_calls"] for item in selected),
            "median_latency_ms": _median(
                item["end_to_end_latency_ms"] for item in selected
            ),
            "receipt_coverage": (
                sum(bool(item["pressure"]["receipt_ids"]) for item in selected)
                / len(selected)
            ),
        }
    return summaries


def classify_savings(gates: Iterable[dict[str, Any]], interval: dict[str, float]) -> str:
    if not all(item["passed"] for item in gates):
        return "invalid_campaign"
    if interval["ci95_low"] > 0:
        return "demonstrated_savings"
    if interval["ci95_high"] <= 0:
        return "no_demonstrated_savings"
    return "inconclusive"


def run_campaign(args: argparse.Namespace) -> dict[str, Any]:
    definition = json.loads(args.cases.read_text(encoding="utf-8"))
    cases = validate_definition(definition)
    before = args.preserve_pid is None or _pid_exists(args.preserve_pid)
    warmup_plan, main_plan = build_plan(cases, args.repetitions, args.seed)
    warmups = [
        _run_trial(
            arm=arm,
            case=case,
            repetition=repetition,
            warmup=warmup,
            dsh=args.dsh,
            profile=args.profile,
            workspace=args.workspace,
            session_root=args.session_root,
            direct_patch=args.direct_patch,
            zstd=args.zstd,
            timeout=args.timeout,
        )
        for arm, case, repetition, warmup in warmup_plan
    ]
    trials = [
        _run_trial(
            arm=arm,
            case=case,
            repetition=repetition,
            warmup=warmup,
            dsh=args.dsh,
            profile=args.profile,
            workspace=args.workspace,
            session_root=args.session_root,
            direct_patch=args.direct_patch,
            zstd=args.zstd,
            timeout=args.timeout,
        )
        for arm, case, repetition, warmup in main_plan
    ]
    pairs = _pairs(trials)
    after = args.preserve_pid is None or _pid_exists(args.preserve_pid)
    expected_trials = len(cases) * args.repetitions * len(ARMS)
    native = [item for item in trials if item["arm"] == "AEEP_HOST_NATIVE"]
    gates = [
        {"name": "paired-capability-coverage", "passed": len(trials) == expected_trials and len(pairs) * 2 == expected_trials},
        {"name": "task-oracles-pass", "passed": all(item["completed"] and item["correct"] for item in trials)},
        {"name": "expected-canonical-tools-called", "passed": all(item["expected_tool_called"] for item in trials)},
        {"name": "native-routes-have-one-tool-receipt", "passed": all(len(item["pressure"]["receipt_ids"]) == 1 for item in native)},
        {"name": "native-exposes-only-bounded-tools", "passed": all(item["exposed_tool_count"] <= 1 for item in native)},
        {"name": "existing-dsh-web-preserved", "passed": before and after},
    ]
    interval = bootstrap_median_interval(
        [item["tokens_saved_by_aeep"] for item in pairs],
        seed=args.seed,
        resamples=args.bootstrap_resamples,
    )
    savings_status = classify_savings(gates, interval)
    report = {
        "schema_version": "aeep-dsh-plugin-campaign-v2",
        "generated_at": datetime.now(UTC).isoformat(),
        "synthetic": True,
        "live_dsh": True,
        "requires_separate_user_approval": True,
        "arms": list(ARMS),
        "seed": args.seed,
        "repetitions_per_capability": args.repetitions,
        "harness_version": definition["harness_version"],
        "model": definition["model"],
        "settings_digest": digest_json(definition["settings"]),
        "installed_plugin_inventory": definition["plugins"],
        "installation": {
            "included_in_execution_tokens": False,
            "provider_tokens": 0,
            "detail": "npm/DSH installation performs no model call; transmitted schemas count in execution usage",
        },
        "excluded_warmup_trials": warmups,
        "excluded_prior_pilot": {
            "observed_delta_tokens": 28,
            "classification": "single-pair model variance; not savings evidence",
        },
        "trials": trials,
        "arm_summaries": _arm_summaries(trials),
        "pairs": pairs,
        "paired_token_savings": interval,
        "tokens_saved_by_aeep": sum(item["tokens_saved_by_aeep"] for item in pairs),
        "savings_status": savings_status,
        "gates": gates,
        "privacy": {
            "prompts_in_report": False,
            "tool_arguments_in_report": False,
            "tool_results_in_report": False,
            "session_ids_in_report": False,
        },
    }
    return DSHPluginCampaignReport.model_validate(report).model_dump(mode="json")


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--session-root", type=Path, required=True)
    parser.add_argument("--direct-patch", type=Path, required=True)
    parser.add_argument("--dsh", type=Path, required=True)
    parser.add_argument("--profile", default="headless")
    parser.add_argument("--zstd", default="zstd")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--seed", type=int, default=8204)
    parser.set_defaults(repetitions=10)
    parser.add_argument("--bootstrap-resamples", type=int, default=10_000)
    parser.add_argument("--preserve-pid", type=int)
    parser.add_argument("--approve-live-provider-calls", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.approve_live_provider_calls:
        parser.error("live campaign requires --approve-live-provider-calls")
    report = run_campaign(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    passed = all(item["passed"] for item in report["gates"])
    print(json.dumps({"gates_passed": passed, "trials": len(report["trials"])}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
