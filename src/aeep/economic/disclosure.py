"""Operator-declared, privacy-bounded quote feature disclosure."""

from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator, model_validator

from ..errors import ConfigurationError
from ..models import ActionFeatures, JsonPrimitive, StrictModel

_SOURCE = re.compile(r"^(action_features|action_input)\.([A-Za-z][A-Za-z0-9_-]{0,63})$")
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,99}$")
_ALWAYS_DENIED_NAME_PARTS = (
    "access_key",
    "authorization",
    "cookie",
    "credential",
    "email",
    "name",
    "password",
    "secret",
    "token",
    "url",
    "uri",
)
_FREE_FORM_NAME_PARTS = ("body", "content", "file", "prompt", "resume", "text")
_AGGREGATE_SUFFIXES = ("_bucket", "_bytes", "_characters", "_count", "_items")
_FEATURE_TYPES = {
    "input_bytes": "integer",
    "input_items": "integer",
    "text_characters": "integer",
    "max_depth": "integer",
    "size_bucket": "enum",
}


class QuoteDisclosureError(ConfigurationError):
    """A configured quote disclosure is unsafe or cannot be produced."""


class DisclosureValueType(StrEnum):
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ENUM = "enum"


def _safe_name(value: str, *, label: str) -> str:
    normalized = value.lower().replace("-", "_")
    aggregate = normalized.endswith(_AGGREGATE_SUFFIXES)
    if any(part in normalized for part in _ALWAYS_DENIED_NAME_PARTS) or (
        not aggregate and any(part in normalized for part in _FREE_FORM_NAME_PARTS)
    ):
        raise ValueError(f"{label} selects a sensitive or free-form field")
    return value


def _safe_enum(value: str) -> str:
    if not value or len(value) > 64 or "://" in value or "@" in value:
        raise QuoteDisclosureError("quote enum value is not a bounded category")
    if any(character.isspace() for character in value):
        raise QuoteDisclosureError("quote enum values cannot contain whitespace")
    return value


def _encoded_size(values: dict[str, JsonPrimitive]) -> int:
    return len(
        json.dumps(
            values,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


class QuoteDisclosureField(StrictModel):
    """One reviewed top-level source projected into a quote request."""

    source: str
    name: str
    type: DisclosureValueType | None = None
    allowed_values: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    required: bool = False

    @field_validator("source")
    @classmethod
    def safe_source(cls, value: str) -> str:
        match = _SOURCE.fullmatch(value)
        if match is None:
            raise ValueError("quote disclosure sources must be top-level action fields")
        _safe_name(match.group(2), label="quote disclosure source")
        if match.group(1) == "action_features" and match.group(2) not in _FEATURE_TYPES:
            raise ValueError("unknown action feature in quote disclosure")
        return value

    @field_validator("name")
    @classmethod
    def safe_output_name(cls, value: str) -> str:
        if _NAME.fullmatch(value) is None:
            raise ValueError("quote disclosure names must be bounded identifiers")
        return _safe_name(value, label="quote disclosure name")

    @field_validator("minimum", "maximum", mode="before")
    @classmethod
    def strict_integer_bound(cls, value: Any) -> Any:
        if value is not None and (isinstance(value, bool | float) or not isinstance(value, int)):
            raise ValueError("quote disclosure bounds must be integers")
        return value

    @field_validator("allowed_values")
    @classmethod
    def bounded_allowed_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) > 64 or len(values) != len(set(values)):
            raise ValueError("quote enum allowlist must contain at most 64 unique values")
        for value in values:
            _safe_enum(value)
        return values

    @model_validator(mode="after")
    def consistent_type(self) -> QuoteDisclosureField:
        source_type = _FEATURE_TYPES.get(self.source.partition(".")[2])
        value_type = self.type.value if self.type is not None else source_type
        if value_type is None:
            raise ValueError("action_input quote disclosures require an explicit type")
        if source_type is not None and value_type != source_type:
            raise ValueError("action feature disclosure type does not match the feature")
        if value_type == DisclosureValueType.ENUM and not (
            self.allowed_values or self.source == "action_features.size_bucket"
        ):
            raise ValueError("enum quote disclosures require an operator allowlist")
        if value_type != DisclosureValueType.ENUM and self.allowed_values:
            raise ValueError("allowed_values applies only to enum quote disclosures")
        if value_type != DisclosureValueType.INTEGER and (
            self.minimum is not None or self.maximum is not None
        ):
            raise ValueError("numeric bounds apply only to integer quote disclosures")
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError("quote disclosure minimum cannot exceed maximum")
        return self

    @property
    def value_type(self) -> DisclosureValueType:
        if self.type is not None:
            return self.type
        return DisclosureValueType(_FEATURE_TYPES[self.source.partition(".")[2]])


class QuoteDisclosurePolicy(StrictModel):
    fields: tuple[QuoteDisclosureField, ...] = ()
    maximum_encoded_bytes: int = Field(default=4096, ge=2, le=65_536)

    @model_validator(mode="after")
    def unique_and_bounded(self) -> QuoteDisclosurePolicy:
        if len(self.fields) > 64:
            raise ValueError("quote disclosure supports at most 64 fields")
        names = [field.name for field in self.fields]
        if len(names) != len(set(names)):
            raise ValueError("quote disclosure names must be unique")
        return self


def _validate_value(field: QuoteDisclosureField, raw: Any) -> JsonPrimitive:
    if raw is None:
        raise QuoteDisclosureError(f"quote feature {field.name!r} cannot be null")
    if field.value_type is DisclosureValueType.INTEGER:
        if isinstance(raw, bool | float) or not isinstance(raw, int):
            raise QuoteDisclosureError(f"quote feature {field.name!r} must be an integer")
        minimum = field.minimum if field.minimum is not None else 0
        maximum = field.maximum if field.maximum is not None else 1_000_000_000
        if not minimum <= raw <= maximum:
            raise QuoteDisclosureError(f"quote feature {field.name!r} is outside its bounds")
        return int(raw)
    if field.value_type is DisclosureValueType.BOOLEAN:
        if not isinstance(raw, bool):
            raise QuoteDisclosureError(f"quote feature {field.name!r} must be a boolean")
        return raw
    if not isinstance(raw, str):
        raise QuoteDisclosureError(f"quote feature {field.name!r} must be an enum")
    _safe_enum(raw)
    if field.allowed_values and raw not in field.allowed_values:
        raise QuoteDisclosureError(f"quote feature {field.name!r} is not allowlisted")
    if field.source == "action_features.size_bucket" and not re.fullmatch(
        r"(?:empty|2\^[0-9]+)", raw
    ):
        raise QuoteDisclosureError("action size bucket is invalid")
    return raw


def validate_disclosed_quote_features(
    values: dict[str, JsonPrimitive],
    *,
    policy: QuoteDisclosurePolicy | None,
) -> None:
    """Revalidate a request projection at the outbound network trust boundary.

    A caller-created protocol model is not proof of operator approval. Non-empty
    disclosure therefore requires an injected policy, and every field must
    match that policy exactly before the HTTP client serializes the request.
    """

    if policy is None:
        if values:
            raise QuoteDisclosureError(
                "non-empty quote disclosure requires an operator-approved policy"
            )
        return

    configured = {field.name: field for field in policy.fields}
    required = {field.name for field in policy.fields if field.required}
    if required - values.keys():
        raise QuoteDisclosureError("required quote disclosure fields are unavailable")
    for name, raw in values.items():
        try:
            _safe_name(name, label="quote disclosure name")
        except ValueError as exc:
            raise QuoteDisclosureError(
                "quote disclosure contains a sensitive or free-form field"
            ) from exc
        field = configured.get(name)
        if field is None:
            raise QuoteDisclosureError("quote disclosure contains an unapproved field")
        _validate_value(field, raw)
    if _encoded_size(values) > policy.maximum_encoded_bytes:
        raise QuoteDisclosureError("quote disclosure exceeds its encoded size limit")


def disclose_quote_features(
    policy: QuoteDisclosurePolicy,
    *,
    action_input: dict[str, Any],
    action_features: ActionFeatures,
) -> dict[str, JsonPrimitive]:
    """Return only explicitly reviewed primitive quote features."""

    disclosed: dict[str, JsonPrimitive] = {}
    for field in policy.fields:
        namespace, _, key = field.source.partition(".")
        if namespace == "action_features":
            raw = getattr(action_features, key)
        elif key in action_input:
            raw = action_input[key]
        elif field.required:
            raise QuoteDisclosureError(f"required quote feature {field.name!r} is unavailable")
        else:
            continue

        if raw is None:
            if field.required:
                raise QuoteDisclosureError(f"required quote feature {field.name!r} is null")
            continue
        disclosed[field.name] = _validate_value(field, raw)

    if _encoded_size(disclosed) > policy.maximum_encoded_bytes:
        raise QuoteDisclosureError("quote disclosure exceeds its encoded size limit")
    return disclosed
