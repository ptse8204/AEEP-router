"""Small deterministic tools used by the generated quickstart manifest."""

from __future__ import annotations

import json
import re
import time


def text_stats(text: str) -> dict[str, int]:
    return {
        "characters": len(text),
        "words": len(text.split()),
        "lines": len(text.splitlines()) or 1,
    }


def printing_text_stats(text: str) -> dict[str, int]:
    print("callable diagnostic")
    return text_stats(text)


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


def github_default_branch_from_fetch(text: str) -> str:
    """Extract GitHub's JSON body from Docker fetch's bounded text envelope."""

    start = text.find("{")
    if start < 0:
        raise ValueError("fetch output does not contain a JSON object")
    value = json.loads(text[start:])
    branch = value.get("default_branch") if isinstance(value, dict) else None
    if not isinstance(branch, str) or not branch:
        raise ValueError("GitHub response does not contain default_branch")
    return branch


def markdown_title_from_fetch(text: str) -> str:
    """Return the first Markdown H1 from a bounded fetch response."""

    match = re.search(r"^#\s+(.+?)\s*$", text, flags=re.MULTILINE)
    if match is None:
        raise ValueError("fetch output does not contain a Markdown title")
    return match.group(1)
