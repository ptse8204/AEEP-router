"""Hermetic model-shaped fixtures for benchmark harness verification only."""

from __future__ import annotations

import json
import sys
import time

from .tools import text_stats


def _emit(output: object, *, input_tokens: int, output_tokens: int) -> None:
    print(
        json.dumps(
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": json.dumps(output)},
            },
            separators=(",", ":"),
        )
    )
    print(
        json.dumps(
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": input_tokens,
                    "cached_input_tokens": input_tokens // 3,
                    "output_tokens": output_tokens,
                    "reasoning_output_tokens": output_tokens // 2,
                },
            },
            separators=(",", ":"),
        )
    )


def main() -> None:
    command = sys.argv[1]
    time.sleep(0.04)
    if command == "text-stats":
        _emit(text_stats(sys.argv[2]), input_tokens=1200, output_tokens=120)
    elif command == "github-default-branch":
        _emit("main", input_tokens=1600, output_tokens=80)
    else:
        raise SystemExit(f"unknown proof fixture {command!r}")


if __name__ == "__main__":
    main()
