from __future__ import annotations

import os

import pytest

from aeep.config import load_manifest, write_default_manifest
from aeep.errors import ConfigurationError, InputValidationError
from aeep.registry import Registry, validate_json
from aeep.templates import extract_path, render, render_string

from conftest import python_spec


def test_template_preserves_full_placeholder_type(monkeypatch):
    values = {"input": {"count": 3, "payload": {"a": 1}}}
    assert render_string("{input.count}", values) == 3
    assert render("x-{input.count}", values) == "x-3"
    monkeypatch.setenv("TOKEN", "secret")
    assert render("${ENV:TOKEN}", values, allow_env=True) == "secret"
    with pytest.raises(ConfigurationError):
        render("${ENV:TOKEN}", values, allow_env=False)


def test_extract_paths():
    data = {"a": {"b": [10, 20]}, "x/y": 3}
    assert extract_path(data, "a.b.1") == 20
    assert extract_path({"a": [1]}, "/a/0") == 1


def test_json_schema_validation():
    schema = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}
    validate_json({"n": 1}, schema, label="value")
    with pytest.raises(InputValidationError):
        validate_json({"n": "1"}, schema, label="value")


def test_registry_duplicate_and_compatibility():
    executor = python_spec(
        "x",
        "aeep.examples.tools:text_stats",
        input_schema={"type": "object", "required": ["text"]},
    )
    registry = Registry([executor])
    with pytest.raises(ConfigurationError):
        registry.register(executor)
    compatible, errors = registry.compatible("text.stats", {"wrong": 1})
    assert not compatible
    assert "x" in errors


def test_default_manifest_resolves_relative_database(tmp_path):
    path = write_default_manifest(tmp_path / "aeep.yaml")
    manifest, resolved = load_manifest(path)
    assert resolved == path
    assert manifest.database.startswith(str(tmp_path))
    assert "balanced" in manifest.policies
