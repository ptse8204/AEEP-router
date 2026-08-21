"""Dependency-free stdin/stdout route used by the local proof campaign."""

from __future__ import annotations

import json
import sys
from typing import Any

_MAXIMUM_REQUEST_BYTES = 262_144


def _statistics(text: str) -> dict[str, int]:
    return {
        "characters": len(text),
        "words": len(text.split()),
        "lines": len(text.splitlines()) or 1,
    }


def main() -> None:
    raw = sys.stdin.buffer.read(_MAXIMUM_REQUEST_BYTES + 1)
    if len(raw) > _MAXIMUM_REQUEST_BYTES:
        raise ValueError("request exceeds the bounded CLI input limit")
    payload: Any = json.loads(raw)
    if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
        raise ValueError("request must contain string field 'text'")
    sys.stdout.write(json.dumps(_statistics(payload["text"]), separators=(",", ":")))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
