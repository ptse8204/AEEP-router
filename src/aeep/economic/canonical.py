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
from typing import Any, Literal, TypeAlias

import rfc8785
from pydantic import BaseModel

LEGACY_CANONICALIZATION_VERSION: Literal["aeep-canonical-json-v1"] = (
    "aeep-canonical-json-v1"
)
JCS_CANONICALIZATION_VERSION: Literal["rfc8785-jcs-v1"] = "rfc8785-jcs-v1"
CanonicalizationVersion: TypeAlias = Literal[
    "aeep-canonical-json-v1",
    "rfc8785-jcs-v1",
]
CANONICALIZATION_VERSION: CanonicalizationVersion = JCS_CANONICALIZATION_VERSION
SUPPORTED_CANONICALIZATION_VERSIONS = frozenset(
    {LEGACY_CANONICALIZATION_VERSION, JCS_CANONICALIZATION_VERSION}
)

_ECONOMIC_RECORD_DOMAIN = b"aeep-economic-record-v2\0"
_ACTION_BINDING_DOMAIN = b"aeep-action-binding-v2\0"


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


def _json_value(value: Any) -> Any:
    """Return strict JSON values suitable for RFC 8785 canonicalization."""

    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("RFC 8785 canonical JSON rejects non-finite numbers")
        return 0 if value == 0 else value
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if isinstance(value, datetime):
        return _datetime_text(value)
    if isinstance(value, Enum):
        return _json_value(value.value)
    if isinstance(value, BaseModel):
        return _json_value(value.model_dump(mode="json", by_alias=True))
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("RFC 8785 canonical JSON object keys must be strings")
            if key in normalized:
                raise ValueError("RFC 8785 canonical JSON contains a duplicate object key")
            normalized[key] = _json_value(item)
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return [_json_value(item) for item in value]
    raise TypeError(f"unsupported RFC 8785 JSON value: {type(value).__name__}")


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


def _declared_canonicalization(
    value: BaseModel | Mapping[str, Any],
) -> CanonicalizationVersion:
    signature = getattr(value, "signature", None)
    if signature is None and isinstance(value, Mapping):
        signature = value.get("signature")
    declared = (
        getattr(signature, "canonicalization_version", None)
        if signature is not None
        else None
    )
    if declared is None and isinstance(signature, Mapping):
        declared = signature.get("canonicalization_version")
    if declared == LEGACY_CANONICALIZATION_VERSION:
        return LEGACY_CANONICALIZATION_VERSION
    if declared == JCS_CANONICALIZATION_VERSION:
        return JCS_CANONICALIZATION_VERSION

    schema_version = getattr(value, "schema_version", None)
    if schema_version is None and isinstance(value, Mapping):
        schema_version = value.get("schema_version")
    return (
        LEGACY_CANONICALIZATION_VERSION
        if schema_version == "0.4"
        else JCS_CANONICALIZATION_VERSION
    )


def canonical_payload(
    value: BaseModel | Mapping[str, Any],
    *,
    version: CanonicalizationVersion | None = None,
) -> bytes:
    """Return the signed bytes for a record, excluding its root signature field.

    All model fields, including explicit ``null`` optionals, are retained. The
    canonicalization version is part of the signed bytes and the signature
    envelope records the same version.
    """

    selected = version or _declared_canonicalization(value)
    if selected not in SUPPORTED_CANONICALIZATION_VERSIONS:
        raise ValueError(f"unsupported canonicalization version {selected!r}")

    if isinstance(value, BaseModel):
        payload: Mapping[str, Any] = value.model_dump(
            mode="python",
            by_alias=True,
            exclude={"signature"},
        )
    else:
        payload = {key: item for key, item in value.items() if key != "signature"}
    envelope = {
        "canonicalization_version": selected,
        "payload": payload,
    }
    if selected == JCS_CANONICALIZATION_VERSION:
        try:
            return _ECONOMIC_RECORD_DOMAIN + rfc8785.dumps(_json_value(envelope))
        except rfc8785.CanonicalizationError as exc:
            raise ValueError(f"RFC 8785 canonicalization failed: {exc}") from exc
    return json.dumps(
        _normalize(envelope),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_digest(
    value: BaseModel | Mapping[str, Any],
    *,
    version: CanonicalizationVersion | None = None,
) -> str:
    """Return a tagged SHA-256 digest of a canonical economic record."""

    return f"sha256:{hashlib.sha256(canonical_payload(value, version=version)).hexdigest()}"


def payload_matches_canonicalization(
    payload: bytes,
    version: CanonicalizationVersion,
) -> bool:
    return (
        payload.startswith(_ECONOMIC_RECORD_DOMAIN)
        if version == JCS_CANONICALIZATION_VERSION
        else not payload.startswith(_ECONOMIC_RECORD_DOMAIN)
    )


def canonical_action_digest(
    value: BaseModel | Mapping[str, Any],
    *,
    version: CanonicalizationVersion = JCS_CANONICALIZATION_VERSION,
) -> str:
    """Return a tagged digest for finite legacy action or effective-policy data."""

    envelope = {
        "canonicalization_version": version,
        "purpose": "action-binding",
        "payload": value,
    }
    if version == JCS_CANONICALIZATION_VERSION:
        try:
            payload = _ACTION_BINDING_DOMAIN + rfc8785.dumps(_json_value(envelope))
        except rfc8785.CanonicalizationError as exc:
            raise ValueError(f"RFC 8785 action canonicalization failed: {exc}") from exc
        return f"sha256:{hashlib.sha256(payload).hexdigest()}"
    if version != LEGACY_CANONICALIZATION_VERSION:
        raise ValueError(f"unsupported canonicalization version {version!r}")
    payload = json.dumps(
        _normalize_action_value(envelope),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"
