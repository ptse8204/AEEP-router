"""Credential-free deterministic Codex App Server fixture."""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from typing import Any


def send(value: object) -> None:
    sys.stdout.write(json.dumps(value, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def response(request: dict[str, Any], result: dict[str, Any]) -> None:
    send({"id": request["id"], "result": result})


def account(authenticated: bool) -> dict[str, Any]:
    return {
        "account": (
            {"type": "chatgpt", "email": "fixture-principal", "planType": "unknown"}
            if authenticated
            else None
        ),
        "requiresOpenaiAuth": True,
    }


def model(model_id: str) -> dict[str, Any]:
    return {
        "id": model_id,
        "model": model_id,
        "displayName": "Fixture model",
        "description": "Offline test model",
        "hidden": False,
        "isDefault": model_id.endswith("b"),
        "defaultReasoningEffort": "low",
        "supportedReasoningEfforts": [
            {"reasoningEffort": "low", "description": "fixture"},
            {"reasoningEffort": "medium", "description": "fixture"},
        ],
        "inputModalities": ["text"],
    }


RATE_LIMITS = {
    "rateLimits": {
        "limitId": "legacy",
        "primary": {"usedPercent": 12, "resetsAt": 2000000000, "windowDurationMins": 300},
    },
    "rateLimitsByLimitId": {
        "fixture": {
            "limitId": "fixture",
            "primary": {
                "usedPercent": 20,
                "resetsAt": 2000000000,
                "windowDurationMins": 300,
            },
            "secondary": {
                "usedPercent": 40,
                "resetsAt": 2000003600,
                "windowDurationMins": 10080,
            },
            "credits": {"hasCredits": False, "unlimited": False, "balance": None},
        }
    },
    "rateLimitResetCredits": {"availableCount": 0, "credits": []},
}


def terminal(status: str = "completed") -> None:
    send(
        {
            "method": "turn/completed",
            "params": {
                "threadId": "fixture-thread",
                "turn": {
                    "id": "fixture-turn",
                    "status": status,
                    "items": [],
                    "error": None if status == "completed" else {"message": "fixture failure"},
                },
            },
        }
    )


def successful_events(*, conflicting_usage: bool = False) -> None:
    send(
        {
            "method": "item/plan/delta",
            "params": {
                "threadId": "fixture-thread",
                "turnId": "fixture-turn",
                "itemId": "fixture-plan",
                "delta": "fixture plan",
            },
        }
    )
    send(
        {
            "method": "model/rerouted",
            "params": {
                "threadId": "fixture-thread",
                "turnId": "fixture-turn",
                "fromModel": "fixture-model-a",
                "toModel": "fixture-model-b",
                "reason": "fixture",
            },
        }
    )
    usage = {
        "inputTokens": 7,
        "cachedInputTokens": 2,
        "cacheWriteInputTokens": 0,
        "outputTokens": 3,
        "reasoningOutputTokens": 1,
        "totalTokens": 10,
    }
    send(
        {
            "method": "thread/tokenUsage/updated",
            "params": {
                "threadId": "fixture-thread",
                "turnId": "fixture-turn",
                "tokenUsage": {"last": usage, "total": usage},
            },
        }
    )
    send(
        {
            "method": "item/completed",
            "params": {
                "threadId": "fixture-thread",
                "turnId": "fixture-turn",
                "completedAtMs": 1,
                "item": {
                    "id": "fixture-message",
                    "type": "agentMessage",
                    "text": '{"characters":3}',
                },
            },
        }
    )
    terminal()
    if conflicting_usage:
        usage["outputTokens"] = 4
        usage["totalTokens"] = 11
        send(
            {
                "method": "thread/tokenUsage/updated",
                "params": {
                    "threadId": "fixture-thread",
                    "turnId": "fixture-turn",
                    "tokenUsage": {"last": usage, "total": usage},
                },
            }
        )


def turn_started(request: dict[str, Any], scenario: str) -> None:
    if scenario == "disconnect":
        raise SystemExit(19)
    response(request, {"turn": {"id": "fixture-turn", "status": "inProgress", "items": []}})
    if scenario == "timeout":
        return
    if scenario == "failure":
        terminal("failed")
        return
    if scenario in {"approval-read", "approval-write", "unknown-request"}:
        method = (
            "item/fileChange/requestApproval"
            if scenario == "approval-write"
            else "fixture/unknown"
            if scenario == "unknown-request"
            else "item/commandExecution/requestApproval"
        )
        params: dict[str, Any] = {
            "threadId": "fixture-thread",
            "turnId": "fixture-turn",
            "itemId": "fixture-item",
            "startedAtMs": 1,
        }
        if scenario == "approval-read":
            params["commandActions"] = [
                {"type": "read", "command": "fixture", "name": "fixture", "path": "."}
            ]
        send({"id": "fixture-approval", "method": method, "params": params})
        reply = json.loads(sys.stdin.readline())
        accepted = reply.get("result", {}).get("decision") == "accept"
        if scenario == "unknown-request":
            accepted = "error" in reply
        terminal("completed" if accepted else "failed")
        return
    successful_events(conflicting_usage=scenario == "conflicting-usage")
    if scenario == "duplicate-terminal":
        terminal()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="success")
    scenario = parser.parse_args().scenario
    authenticated = scenario != "unauthenticated"
    for line in sys.stdin:
        request = json.loads(line)
        method = request.get("method")
        if "id" not in request:
            continue
        if method == "initialize":
            response(
                request,
                {
                    "userAgent": "fixture-app-server/2",
                    "codexHome": "/fixture/redacted",
                    "platformFamily": "fixture",
                    "platformOs": "fixture",
                },
            )
        elif method == "account/read":
            response(request, account(authenticated))
            if scenario == "duplicate-response":
                response(request, account(authenticated))
        elif method == "account/rateLimits/read":
            limits = copy.deepcopy(RATE_LIMITS)
            if scenario == "credits-present":
                limits["rateLimitResetCredits"]["availableCount"] = 2
            response(request, limits)
        elif method == "account/usage/read":
            response(
                request,
                {
                    "summary": {"lifetimeTokens": 99, "peakDailyTokens": 11},
                    "dailyUsageBuckets": [{"startDate": "fixture", "tokens": 11}],
                },
            )
        elif method == "model/list":
            if scenario == "malformed":
                sys.stdout.write("not-json\n")
                sys.stdout.flush()
            elif scenario == "oversized":
                sys.stdout.write("{" + "x" * 4096 + "}\n")
                sys.stdout.flush()
            elif request.get("params", {}).get("cursor") is None:
                response(request, {"data": [model("fixture-model-a")], "nextCursor": "page-2"})
            else:
                response(request, {"data": [model("fixture-model-b")], "nextCursor": None})
        elif method == "thread/start":
            response(
                request,
                {
                    "thread": {"id": "fixture-thread"},
                    "model": "fixture-model-a",
                    "approvalPolicy": "on-request",
                    "approvalsReviewer": "user",
                    "cwd": ".",
                    "modelProvider": "fixture",
                    "sandbox": {"type": "readOnly"},
                },
            )
        elif method == "turn/start":
            turn_started(request, scenario)
        elif method == "turn/interrupt":
            response(request, {})
            terminal("interrupted")
        elif method == "thread/resume":
            response(request, {"thread": {"id": "fixture-thread"}})
        elif method == "turn/steer":
            response(request, {"turnId": "fixture-turn"})
        elif method == "account/login/start":
            response(
                request,
                {
                    "type": "chatgpt",
                    "loginId": "fixture-login",
                    "authUrl": "https://example.invalid/operator-login",
                },
            )
        else:
            response(request, {})
        if scenario == "slow-shutdown":
            time.sleep(0.01)


if __name__ == "__main__":
    main()
