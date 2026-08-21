"""Deterministic local step used by the prepared-workflow proof campaign."""

from __future__ import annotations


def identity_text(text: str) -> dict[str, str]:
    """Return text unchanged so the next step is quoted from a real dependency."""

    return {"text": text}
