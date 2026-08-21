"""In-memory capability and executor registry."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from jsonschema.validators import validator_for

from .errors import ConfigurationError, InputValidationError
from .models import ExecutorSpec


def _declared_property_names(schema: Any) -> set[str]:
    """Return schema-authored property names without consulting instance data."""

    names: set[str] = set()
    pending: list[Any] = [schema]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if not isinstance(current, (dict, list, tuple)) or id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, dict):
            properties = current.get("properties")
            if isinstance(properties, dict):
                names.update(str(name) for name in properties)
            pending.extend(current.values())
        else:
            pending.extend(current)
    return names


def _safe_validation_fragment(error: Any, schema: dict[str, Any]) -> str:
    """Describe a validation failure without reflecting input or output values."""

    declared = _declared_property_names(schema)
    location = "$"
    for part in error.absolute_path:
        if isinstance(part, int):
            location += f"[{part}]"
        elif isinstance(part, str) and part in declared:
            location += f".{part}"
        else:
            # Dynamic object keys come from the payload and may themselves be
            # confidential. Preserve the structural location without echoing
            # the key.
            location += ".*"
    validator = error.validator
    keyword = (
        validator
        if isinstance(validator, str)
        and validator
        and all(character.isalnum() or character in "_-$" for character in validator)
        else "unknown"
    )
    return f"{location}: violates JSON Schema {keyword!r} constraint"


def validate_json(instance: Any, schema: dict[str, Any], *, label: str) -> None:
    try:
        validator_cls = validator_for(schema)
        validator_cls.check_schema(schema)
        validator = validator_cls(schema)
        errors = sorted(
            validator.iter_errors(instance),
            key=lambda error: tuple(str(part) for part in error.path),
        )
    except Exception as exc:
        raise ConfigurationError(f"invalid JSON Schema for {label}: {exc}") from exc
    if errors:
        fragments = [_safe_validation_fragment(error, schema) for error in errors[:5]]
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

    def replace(self, executor: ExecutorSpec) -> None:
        existing = self._by_id.get(executor.id)
        if existing is not None:
            self._by_capability[existing.capability] = [
                item for item in self._by_capability[existing.capability] if item.id != executor.id
            ]
        self._by_id[executor.id] = executor
        self._by_capability[executor.capability].append(executor)
        self._by_capability[executor.capability].sort(key=lambda item: item.id)

    def find(self, capability: str, *, include_disabled: bool = False) -> list[ExecutorSpec]:
        return [
            executor
            for executor in self._by_capability.get(capability, [])
            if include_disabled or executor.enabled
        ]

    def compatible(
        self, capability: str, input_value: dict[str, Any]
    ) -> tuple[list[ExecutorSpec], dict[str, str]]:
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

    def search(
        self,
        query: str = "",
        *,
        prefix: str | None = None,
        limit: int = 20,
        cursor: int = 0,
        include_executors: bool = False,
    ) -> dict[str, Any]:
        terms = query.casefold().split()
        matches: list[dict[str, Any]] = []
        for capability in self.capabilities():
            if prefix is not None and not capability.startswith(prefix):
                continue
            executors = self.find(capability)
            haystack = " ".join(
                [
                    capability,
                    *(item.id for item in executors),
                    *(item.description for item in executors),
                ]
            ).casefold()
            if any(term not in haystack for term in terms):
                continue
            item: dict[str, Any] = {
                "capability": capability,
                "executor_count": len(executors),
                "kinds": sorted({executor.kind.value for executor in executors}),
            }
            if include_executors:
                item["executors"] = [
                    {
                        "id": executor.id,
                        "kind": executor.kind.value,
                        "description": executor.description,
                        "side_effect": executor.side_effect.value,
                        "locality": executor.locality.value,
                    }
                    for executor in executors
                ]
            matches.append(item)
        start = max(0, cursor)
        page_size = max(1, min(limit, 100))
        page = matches[start : start + page_size]
        next_cursor = start + len(page) if start + len(page) < len(matches) else None
        return {
            "capabilities": page,
            "next_cursor": next_cursor,
            "total": len(matches),
        }
