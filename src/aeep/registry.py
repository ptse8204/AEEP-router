"""In-memory capability and executor registry."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from jsonschema.validators import validator_for

from .errors import ConfigurationError, InputValidationError
from .models import ExecutorSpec


def validate_json(instance: Any, schema: dict[str, Any], *, label: str) -> None:
    try:
        validator_cls = validator_for(schema)
        validator_cls.check_schema(schema)
        validator = validator_cls(schema)
        errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.path))
    except Exception as exc:
        raise ConfigurationError(f"invalid JSON Schema for {label}: {exc}") from exc
    if errors:
        fragments: list[str] = []
        for error in errors[:5]:
            location = ".".join(str(part) for part in error.absolute_path) or "$"
            fragments.append(f"{location}: {error.message}")
        raise InputValidationError(f"{label} validation failed: {'; '.join(fragments)}")


class Registry:
    def __init__(self, executors: Iterable[ExecutorSpec] = ()) -> None:
        self._by_id: dict[str, ExecutorSpec] = {}
        self._by_capability: dict[str, list[ExecutorSpec]] = defaultdict(list)
        for executor in executors:
            self.register(executor)

    def register(self, executor: ExecutorSpec) -> None:
        if executor.id in self._by_id:
            raise ConfigurationError(f"executor {executor.id!r} is already registered")
        self._by_id[executor.id] = executor
        self._by_capability[executor.capability].append(executor)
        self._by_capability[executor.capability].sort(key=lambda item: item.id)

    def get(self, executor_id: str) -> ExecutorSpec:
        try:
            return self._by_id[executor_id]
        except KeyError as exc:
            raise ConfigurationError(f"unknown executor {executor_id!r}") from exc

    def contains(self, executor_id: str) -> bool:
        return executor_id in self._by_id

    def find(self, capability: str, *, include_disabled: bool = False) -> list[ExecutorSpec]:
        return [
            executor
            for executor in self._by_capability.get(capability, [])
            if include_disabled or executor.enabled
        ]

    def compatible(self, capability: str, input_value: dict[str, Any]) -> tuple[list[ExecutorSpec], dict[str, str]]:
        compatible: list[ExecutorSpec] = []
        errors: dict[str, str] = {}
        for executor in self.find(capability):
            try:
                validate_json(
                    input_value,
                    executor.input_schema,
                    label=f"input for {executor.id}",
                )
            except InputValidationError as exc:
                errors[executor.id] = str(exc)
            else:
                compatible.append(executor)
        return compatible, errors

    def capabilities(self) -> list[str]:
        return sorted(
            capability
            for capability, executors in self._by_capability.items()
            if any(executor.enabled for executor in executors)
        )

    def all(self, *, include_disabled: bool = False) -> list[ExecutorSpec]:
        return [
            self._by_id[key]
            for key in sorted(self._by_id)
            if include_disabled or self._by_id[key].enabled
        ]

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "capability": capability,
                "executors": [
                    {
                        "id": executor.id,
                        "kind": executor.kind.value,
                        "description": executor.description,
                        "side_effect": executor.side_effect.value,
                        "locality": executor.locality.value,
                    }
                    for executor in self.find(capability)
                ],
            }
            for capability in self.capabilities()
        ]
