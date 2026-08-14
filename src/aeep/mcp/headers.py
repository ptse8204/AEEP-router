"""MCP 2026-07-28 HTTP header mirroring and validation helpers."""

from __future__ import annotations

import base64
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..errors import ProtocolError

_SENTINEL_PREFIX = "=?base64?"
_SENTINEL_SUFFIX = "?="
_TCHAR = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_MAX_SAFE_INTEGER = 2**53 - 1


@dataclass(frozen=True, slots=True)
class ToolHeaderBinding:
    name: str
    path: tuple[str, ...]
    value_type: str

    @property
    def header_name(self) -> str:
        return f"Mcp-Param-{self.name}"


def encode_header_value(value: str) -> str:
    """Encode an MCP mirrored value using the required Base64 sentinel when needed."""

    is_visible_ascii = all(
        character == "\t" or 0x20 <= ord(character) <= 0x7E for character in value
    )
    needs_encoding = (
        not is_visible_ascii
        or value != value.strip(" \t")
        or (value.startswith(_SENTINEL_PREFIX) and value.endswith(_SENTINEL_SUFFIX))
    )
    if not needs_encoding:
        return value
    encoded = base64.b64encode(value.encode("utf-8")).decode("ascii")
    return f"{_SENTINEL_PREFIX}{encoded}{_SENTINEL_SUFFIX}"


def decode_header_value(value: str) -> str:
    if value.startswith(_SENTINEL_PREFIX) and value.endswith(_SENTINEL_SUFFIX):
        encoded = value[len(_SENTINEL_PREFIX) : -len(_SENTINEL_SUFFIX)]
        try:
            return base64.b64decode(encoded, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise ProtocolError("invalid MCP Base64 sentinel header value") from exc
    if not all(character == "\t" or 0x20 <= ord(character) <= 0x7E for character in value):
        raise ProtocolError("MCP header contains invalid characters")
    return value


def primitive_header_value(value: Any, value_type: str) -> str:
    if value_type == "string" and isinstance(value, str):
        return value
    if value_type == "boolean" and isinstance(value, bool):
        return "true" if value else "false"
    if value_type == "integer" and isinstance(value, int) and not isinstance(value, bool):
        if abs(value) > _MAX_SAFE_INTEGER:
            raise ProtocolError("MCP integer header value exceeds JavaScript safe integer range")
        return str(value)
    raise ProtocolError(f"MCP mirrored parameter must be a {value_type}")


def _walk_valid_properties(
    schema: dict[str, Any],
    *,
    path: tuple[str, ...] = (),
    bindings: list[ToolHeaderBinding],
    valid_nodes: set[int],
) -> None:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return
    for property_name, property_schema in properties.items():
        if not isinstance(property_name, str) or not isinstance(property_schema, dict):
            continue
        valid_nodes.add(id(property_schema))
        property_path = (*path, property_name)
        annotation = property_schema.get("x-mcp-header")
        if annotation is not None:
            if (
                not isinstance(annotation, str)
                or not annotation
                or not _TCHAR.fullmatch(annotation)
            ):
                raise ProtocolError("invalid x-mcp-header name")
            value_type = property_schema.get("type")
            if value_type not in {"string", "integer", "boolean"}:
                raise ProtocolError(
                    "x-mcp-header may only annotate string, integer, or boolean properties"
                )
            bindings.append(ToolHeaderBinding(annotation, property_path, value_type))
        _walk_valid_properties(
            property_schema,
            path=property_path,
            bindings=bindings,
            valid_nodes=valid_nodes,
        )


def _find_annotations(node: Any, *, valid_nodes: set[int]) -> None:
    if isinstance(node, dict):
        if "x-mcp-header" in node and id(node) not in valid_nodes:
            raise ProtocolError(
                "x-mcp-header is only valid on properties statically reachable through properties"
            )
        for value in node.values():
            _find_annotations(value, valid_nodes=valid_nodes)
    elif isinstance(node, list):
        for value in node:
            _find_annotations(value, valid_nodes=valid_nodes)


def tool_header_bindings(tool: Mapping[str, Any]) -> list[ToolHeaderBinding]:
    schema = tool.get("inputSchema", {})
    if not isinstance(schema, dict):
        raise ProtocolError("MCP tool inputSchema must be an object")
    bindings: list[ToolHeaderBinding] = []
    valid_nodes: set[int] = set()
    _walk_valid_properties(schema, bindings=bindings, valid_nodes=valid_nodes)
    _find_annotations(schema, valid_nodes=valid_nodes)
    names = [binding.name.lower() for binding in bindings]
    if len(names) != len(set(names)):
        raise ProtocolError("x-mcp-header names must be case-insensitively unique")
    return bindings


def _value_at_path(arguments: Mapping[str, Any], path: tuple[str, ...]) -> tuple[bool, Any]:
    current: Any = arguments
    for part in path:
        if not isinstance(current, Mapping) or part not in current:
            return False, None
        current = current[part]
    return True, current


def tool_parameter_headers(tool: Mapping[str, Any], arguments: Mapping[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for binding in tool_header_bindings(tool):
        present, value = _value_at_path(arguments, binding.path)
        if not present or value is None:
            continue
        converted = primitive_header_value(value, binding.value_type)
        headers[binding.header_name] = encode_header_value(converted)
    return headers


def validate_tool_parameter_headers(
    tool: Mapping[str, Any],
    arguments: Mapping[str, Any],
    headers: Mapping[str, str],
) -> None:
    lowered = {key.lower(): value for key, value in headers.items()}
    for binding in tool_header_bindings(tool):
        present, body_value = _value_at_path(arguments, binding.path)
        header_key = binding.header_name.lower()
        actual = lowered.get(header_key)
        if not present or body_value is None:
            if actual is not None:
                raise ProtocolError(f"unexpected {binding.header_name} header")
            continue
        if actual is None:
            raise ProtocolError(f"missing required {binding.header_name} header")
        expected = primitive_header_value(body_value, binding.value_type)
        decoded = decode_header_value(actual)
        if binding.value_type == "integer":
            try:
                if int(decoded) != int(expected):
                    raise ProtocolError(f"{binding.header_name} does not match request body")
            except ValueError as exc:
                raise ProtocolError(f"{binding.header_name} is not an integer") from exc
        elif decoded != expected:
            raise ProtocolError(f"{binding.header_name} does not match request body")
