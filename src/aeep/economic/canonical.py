"""Canonical serialization for signed AEEP economic records."""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel

CANONICALIZATION_VERSION: Literal["aeep-canonical-json-v1"] = "aeep-canonical-json-v1"


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("canonical economic JSON rejects non-finite decimals")
    if value.is_zero():
        if value.is_signed():
            raise ValueError("canonical economic JSON rejects negative zero")
        return "0"

    sign, raw_digits, exponent = value.as_tuple()
    if not isinstance(exponent, int):  # narrowed by is_finite() at runtime
        raise ValueError("canonical economic JSON rejects non-finite decimals")
    digits = list(raw_digits)
    while digits[-1] == 0:
        digits.pop()
        exponent += 1
    coefficient = "".join(str(digit) for digit in digits)
    if exponent >= 0:
        result = coefficient + ("0" * exponent)
    else:
        point = len(coefficient) + exponent
        result = (
            f"{coefficient[:point]}.{coefficient[point:]}"
            if point > 0
            else f"0.{('0' * -point)}{coefficient}"
        )
    return f"-{result}" if sign else result


def _datetime_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("canonical economic JSON requires timezone-aware datetimes")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _normalize(value: Any) -> Any:
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        raise ValueError("canonical economic JSON rejects binary floating-point values")
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if isinstance(value, datetime):
        return _datetime_text(value)
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Enum):
        return _normalize(value.value)
    if isinstance(value, BaseModel):
        return _normalize(value.model_dump(mode="python", by_alias=True))
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical economic JSON object keys must be strings")
            normalized_key = unicodedata.normalize("NFC", key)
            if normalized_key in normalized:
                raise ValueError("Unicode normalization produced a duplicate object key")
            normalized[normalized_key] = _normalize(item)
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return [_normalize(item) for item in value]
    raise TypeError(f"unsupported canonical economic JSON value: {type(value).__name__}")


def _normalize_action_value(value: Any) -> Any:
    """Canonicalize legacy action/policy data while permitting finite JSON floats.

    Signed economic records continue to use :func:`_normalize` and reject every
    binary float.  Existing action and policy models predate that rule, so their
    request-binding digest uses this narrowly relaxed normalization in the same
    canonicalization module.
    """

    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical action JSON rejects non-finite numeric values")
        return 0 if value == 0 else value
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("canonical action JSON rejects non-finite decimals")
        return "0" if value.is_zero() else _decimal_text(value)
    if isinstance(value, datetime):
        return _datetime_text(value)
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Enum):
        return _normalize_action_value(value.value)
    if isinstance(value, BaseModel):
        return _normalize_action_value(value.model_dump(mode="python", by_alias=True))
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical action JSON object keys must be strings")
            normalized_key = unicodedata.normalize("NFC", key)
            if normalized_key in normalized:
                raise ValueError("Unicode normalization produced a duplicate object key")
            normalized[normalized_key] = _normalize_action_value(item)
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return [_normalize_action_value(item) for item in value]
    raise TypeError(f"unsupported canonical action JSON value: {type(value).__name__}")


def canonical_payload(value: BaseModel | Mapping[str, Any]) -> bytes:
    """Return the signed bytes for a record, excluding its root signature field.

    All model fields, including explicit ``null`` optionals, are retained. The
    canonicalization version is part of the signed bytes and the signature
    envelope records the same version.
    """

    if isinstance(value, BaseModel):
        payload: Mapping[str, Any] = value.model_dump(
            mode="python",
            by_alias=True,
            exclude={"signature"},
        )
    else:
        payload = {key: item for key, item in value.items() if key != "signature"}
    envelope = {
        "canonicalization_version": CANONICALIZATION_VERSION,
        "payload": payload,
    }
    return json.dumps(
        _normalize(envelope),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_digest(value: BaseModel | Mapping[str, Any]) -> str:
    """Return a tagged SHA-256 digest of a canonical economic record."""

    return f"sha256:{hashlib.sha256(canonical_payload(value)).hexdigest()}"


def canonical_action_digest(value: BaseModel | Mapping[str, Any]) -> str:
    """Return a tagged digest for finite legacy action or effective-policy data."""

    envelope = {
        "canonicalization_version": CANONICALIZATION_VERSION,
        "purpose": "action-binding",
        "payload": value,
    }
    payload = json.dumps(
        _normalize_action_value(envelope),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"
