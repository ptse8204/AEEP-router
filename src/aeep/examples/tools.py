"""Small deterministic tools used by the generated quickstart manifest."""

from __future__ import annotations

import time


def text_stats(text: str) -> dict[str, int]:
    return {
        "characters": len(text),
        "words": len(text.split()),
        "lines": len(text.splitlines()) or 1,
    }


def line_count(path: str) -> dict[str, int | str]:
    with open(path, encoding="utf-8") as handle:
        return {"path": path, "lines": sum(1 for _ in handle)}


def always_fail(text: str = "") -> dict[str, str]:
    raise RuntimeError(f"intentional failure: {text}")


def invalid_stats(text: str) -> dict[str, str]:
    return {"characters": "not-an-integer", "text": text}


async def async_text_stats(text: str) -> dict[str, int]:
    return text_stats(text)


def slow_text_stats(text: str) -> dict[str, int]:
    time.sleep(0.04)
    return text_stats(text)
