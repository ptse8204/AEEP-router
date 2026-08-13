"""Bounded output parsing shared by command and HTTP executors."""

from __future__ import annotations

import json
import re
from typing import Any

from ..errors import ExecutorError
from ..templates import extract_path


def _coerce(value: str, kind: str) -> Any:
    if kind == "string":
        return value
    if kind == "integer":
        return int(value)
    if kind == "number":
        return float(value)
    if kind == "boolean":
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        raise ValueError(f"cannot parse boolean {value!r}")
    if kind == "json":
        return json.loads(value)
    raise ValueError(f"unsupported coercion type {kind!r}")


def parse_output(text: str, config: dict[str, Any] | None = None) -> Any:
    options = config or {"type": "text"}
    output_type = str(options.get("type", "text"))
    strip = bool(options.get("strip", True))
    prepared = text.strip() if strip else text
    try:
        if output_type == "text":
            result: Any = prepared
        elif output_type == "json":
            result = json.loads(prepared)
        elif output_type == "lines":
            result = prepared.splitlines()
        elif output_type == "regex":
            pattern = str(options["pattern"])
            match = re.search(pattern, prepared, flags=re.MULTILINE | re.DOTALL)
            if not match:
                raise ExecutorError("executor output did not match configured regular expression")
            group_types = options.get("groups", {})
            if match.groupdict():
                result = {
                    name: _coerce(value, str(group_types.get(name, "string")))
                    for name, value in match.groupdict().items()
                }
            else:
                group = int(options.get("group", 1))
                result = _coerce(match.group(group), str(options.get("coerce", "string")))
        else:
            raise ExecutorError(f"unsupported output parser type {output_type!r}")
        return extract_path(result, options.get("path"))
    except ExecutorError:
        raise
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ExecutorError(f"cannot parse executor output as {output_type}: {exc}") from exc
