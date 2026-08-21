"""Composable task validators that keep transport, schema, and task validity distinct."""

from __future__ import annotations

import inspect
import math
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from .errors import ConfigurationError
from .models import (
    TrustLevel,
    ValidationKind,
    ValidationResult,
    ValidationSpec,
)
from .registry import validate_json
from .templates import extract_path


@dataclass(slots=True)
class ValidationContext:
    input: dict[str, Any]
    output: Any
    previous_state: Any = None


class Validator(Protocol):
    async def validate(self, context: ValidationContext) -> ValidationResult: ...


class SchemaValidator:
    def __init__(self, schema: dict[str, Any]) -> None:
        self.schema = schema

    async def validate(self, context: ValidationContext) -> ValidationResult:
        try:
            validate_json(context.output, self.schema, label="validator output")
            return ValidationResult(kind=ValidationKind.SCHEMA, valid=True, quality_score=1.0)
        except Exception as exc:
            return ValidationResult(
                kind=ValidationKind.SCHEMA,
                valid=False,
                quality_score=0.0,
                detail=str(exc),
            )


class ExactMatchValidator:
    def __init__(self, expected: Any, *, path: str | None = None) -> None:
        self.expected = expected
        self.path = path

    async def validate(self, context: ValidationContext) -> ValidationResult:
        actual = extract_path(context.output, self.path)
        valid = actual == self.expected
        return ValidationResult(
            kind=ValidationKind.EXACT_MATCH,
            valid=valid,
            quality_score=1.0 if valid else 0.0,
            detail="exact match" if valid else "output does not match expected value",
        )


class RangeValidator:
    def __init__(
        self,
        *,
        path: str | None = None,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> None:
        self.path = path
        self.minimum = minimum
        self.maximum = maximum

    async def validate(self, context: ValidationContext) -> ValidationResult:
        actual = extract_path(context.output, self.path)
        valid = (
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and math.isfinite(actual)
        )
        if valid and self.minimum is not None:
            valid = actual >= self.minimum
        if valid and self.maximum is not None:
            valid = actual <= self.maximum
        return ValidationResult(
            kind=ValidationKind.RANGE,
            valid=valid,
            quality_score=1.0 if valid else 0.0,
            detail="within range" if valid else "output is outside the accepted range",
        )


class StateTransitionValidator:
    def __init__(
        self,
        transitions: Mapping[str, list[str]],
        *,
        before_path: str,
        after_path: str,
    ) -> None:
        self.transitions = {
            str(key): {str(item) for item in values} for key, values in transitions.items()
        }
        self.before_path = before_path
        self.after_path = after_path

    async def validate(self, context: ValidationContext) -> ValidationResult:
        before = str(extract_path(context.input, self.before_path))
        after = str(extract_path(context.output, self.after_path))
        valid = after in self.transitions.get(before, set())
        return ValidationResult(
            kind=ValidationKind.STATE_TRANSITION,
            valid=valid,
            quality_score=1.0 if valid else 0.0,
            detail=(
                "allowed state transition" if valid else "state transition is not allowed"
            ),
        )


ValidatorCallback = Callable[
    [ValidationContext], ValidationResult | bool | Awaitable[ValidationResult | bool | None] | None
]


class CallbackValidator:
    kind = ValidationKind.CALLBACK
    trust = TrustLevel.VERIFIED

    def __init__(self, callback: ValidatorCallback) -> None:
        self.callback = callback

    async def validate(self, context: ValidationContext) -> ValidationResult:
        value = self.callback(context)
        if inspect.isawaitable(value):
            value = await value
        if isinstance(value, ValidationResult):
            return value
        return ValidationResult(
            kind=self.kind,
            valid=value,
            quality_score=(1.0 if value is True else 0.0 if value is False else None),
            trust=self.trust,
        )


class DownstreamValidator(CallbackValidator):
    kind = ValidationKind.DOWNSTREAM
    trust = TrustLevel.VERIFIED


class LLMValidator(CallbackValidator):
    kind = ValidationKind.LLM
    trust = TrustLevel.SELF_ASSERTED


class HumanValidator(CallbackValidator):
    kind = ValidationKind.HUMAN
    trust = TrustLevel.ATTESTED


def validator_from_spec(
    spec: ValidationSpec,
    callbacks: Mapping[str, ValidatorCallback],
) -> Validator:
    config = spec.config
    if spec.kind == ValidationKind.SCHEMA:
        schema = config.get("schema")
        if not isinstance(schema, dict):
            raise ConfigurationError("schema validator requires config.schema")
        return SchemaValidator(schema)
    if spec.kind == ValidationKind.EXACT_MATCH:
        return ExactMatchValidator(config.get("expected"), path=config.get("path"))
    if spec.kind == ValidationKind.RANGE:
        return RangeValidator(
            path=config.get("path"),
            minimum=config.get("minimum"),
            maximum=config.get("maximum"),
        )
    if spec.kind == ValidationKind.STATE_TRANSITION:
        transitions = config.get("transitions")
        if not isinstance(transitions, dict):
            raise ConfigurationError("state_transition validator requires config.transitions")
        return StateTransitionValidator(
            transitions,
            before_path=str(config.get("before_path", "state")),
            after_path=str(config.get("after_path", "state")),
        )
    name = config.get("name")
    callback = callbacks.get(str(name)) if name is not None else None
    if callback is None:
        raise ConfigurationError(f"{spec.kind.value} validator requires a registered callback")
    return {
        ValidationKind.CALLBACK: CallbackValidator,
        ValidationKind.DOWNSTREAM: DownstreamValidator,
        ValidationKind.LLM: LLMValidator,
        ValidationKind.HUMAN: HumanValidator,
    }[spec.kind](callback)


async def run_validators(
    specs: list[ValidationSpec],
    context: ValidationContext,
    callbacks: Mapping[str, ValidatorCallback],
) -> list[ValidationResult]:
    results: list[ValidationResult] = []
    for spec in specs:
        try:
            results.append(await validator_from_spec(spec, callbacks).validate(context))
        except Exception as exc:
            results.append(
                ValidationResult(
                    kind=spec.kind,
                    valid=False,
                    quality_score=0.0,
                    detail=f"validator failed: {type(exc).__name__}",
                )
            )
    return results
