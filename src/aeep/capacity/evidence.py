"""Privacy-preserving capacity evidence helpers."""

from __future__ import annotations

import hashlib
import hmac


def principal_digest(principal: str, *, salt: bytes) -> str:
    if not principal or not salt:
        raise ValueError("principal and salt are required")
    return f"sha256:{hmac.new(salt, principal.encode(), hashlib.sha256).hexdigest()}"
