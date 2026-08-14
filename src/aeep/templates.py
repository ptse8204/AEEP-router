"""Small, deterministic templating helpers for trusted executor manifests."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from .errors import ConfigurationError

_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_.-]*)\}")
_ENV = re.compile(r"\$\{ENV:([A-Za-z_][A-Za-z0-9_]*)\}")


def get_path(data: Any, path: str) -> Any:
    current = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, (list, tuple)) and part.isdigit():
            current = current[int(part)]
        else:
            raise ConfigurationError(f"template value {path!r} was not provided")
    return current


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple, bool)):
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    return str(value)


def render_string(template: str, values: dict[str, Any], *, allow_env: bool = False) -> Any:
    """Render `{input.path}` placeholders without evaluating expressions.

    A string that consists solely of one placeholder preserves the value's type,
    which allows JSON request bodies to carry numbers, booleans, lists, and
    objects. Partial interpolation always produces a string.
    """

    full = _PLACEHOLDER.fullmatch(template)
    if full:
        return get_path(values, full.group(1))

    def replace(match: re.Match[str]) -> str:
        return _stringify(get_path(values, match.group(1)))

    rendered = _PLACEHOLDER.sub(replace, template)
    if allow_env:
        rendered = _ENV.sub(lambda match: _read_env(match.group(1)), rendered)
    elif _ENV.search(rendered):
        raise ConfigurationError("environment interpolation is not allowed in this field")
    return rendered


def _read_env(name: str) -> str:
    try:
        return os.environ[name]
    except KeyError as exc:
        raise ConfigurationError(f"required environment variable {name!r} is not set") from exc


def render(value: Any, values: dict[str, Any], *, allow_env: bool = False) -> Any:
    if isinstance(value, str):
        return render_string(value, values, allow_env=allow_env)
    if isinstance(value, list):
        return [render(item, values, allow_env=allow_env) for item in value]
    if isinstance(value, tuple):
        return tuple(render(item, values, allow_env=allow_env) for item in value)
    if isinstance(value, dict):
        return {str(key): render(item, values, allow_env=allow_env) for key, item in value.items()}
    return value


def extract_path(data: Any, path: str | None) -> Any:
    if not path:
        return data
    normalized = path.removeprefix("$.").removeprefix("/")
    if path.startswith("/"):
        parts = [part.replace("~1", "/").replace("~0", "~") for part in normalized.split("/")]
        current = data
        for part in parts:
            current = current[int(part)] if isinstance(current, list) else current[part]
        return current
    return get_path(data, normalized)
