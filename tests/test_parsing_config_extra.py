from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from aeep.config import find_manifest, load_manifest, write_default_manifest
from aeep.errors import ConfigurationError, ExecutorError
from aeep.executors.parsing import _coerce, parse_output


def test_output_parsers_and_coercions():
    assert _coerce("x", "string") == "x"
    assert _coerce("3", "integer") == 3
    assert _coerce("3.5", "number") == 3.5
    assert _coerce("yes", "boolean") is True
    assert _coerce("off", "boolean") is False
    assert _coerce('{"a":1}', "json") == {"a": 1}
    with pytest.raises(ValueError):
        _coerce("maybe", "boolean")
    with pytest.raises(ValueError):
        _coerce("x", "other")

    assert parse_output(" x \n", {"type": "text"}) == "x"
    assert parse_output("a\nb\n", {"type": "lines"}) == ["a", "b"]
    assert parse_output('{"a":{"b":2}}', {"type": "json", "path": "a.b"}) == 2
    named = parse_output(
        "count=42 enabled=true",
        {
            "type": "regex",
            "pattern": r"count=(?P<count>\d+) enabled=(?P<enabled>\w+)",
            "groups": {"count": "integer", "enabled": "boolean"},
        },
    )
    assert named == {"count": 42, "enabled": True}
    assert parse_output("value=2.5", {"type": "regex", "pattern": r"value=(\S+)", "coerce": "number"}) == 2.5
    with pytest.raises(ExecutorError):
        parse_output("x", {"type": "regex", "pattern": r"(nope)"})
    with pytest.raises(ExecutorError):
        parse_output("x", {"type": "unknown"})
    with pytest.raises(ExecutorError):
        parse_output("not-json", {"type": "json"})


def test_manifest_discovery_and_errors(tmp_path, monkeypatch):
    with pytest.raises(ConfigurationError):
        find_manifest(tmp_path / "missing.yaml")

    manifest = write_default_manifest(tmp_path / "aeep.yaml")
    monkeypatch.setenv("AEEP_CONFIG", str(manifest))
    assert find_manifest() == manifest
    monkeypatch.delenv("AEEP_CONFIG")

    monkeypatch.chdir(tmp_path)
    assert find_manifest() == manifest

    with pytest.raises(ConfigurationError):
        write_default_manifest(manifest)
    assert write_default_manifest(manifest, force=True) == manifest

    bad_root = tmp_path / "bad-root.yaml"
    bad_root.write_text("- one\n- two\n")
    with pytest.raises(ConfigurationError, match="root"):
        load_manifest(bad_root)

    bad_yaml = tmp_path / "bad-yaml.yaml"
    bad_yaml.write_text("x: [\n")
    with pytest.raises(ConfigurationError, match="cannot read"):
        load_manifest(bad_yaml)

    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("executors:\n  - id: 'bad id'\n")
    with pytest.raises(ConfigurationError, match="invalid manifest"):
        load_manifest(invalid)

    missing_policy = tmp_path / "missing-policy.yaml"
    missing_policy.write_text("default_policy: does-not-exist\n")
    with pytest.raises(ConfigurationError, match="default policy"):
        load_manifest(missing_policy)


def test_executor_cwd_is_resolved(tmp_path):
    manifest = tmp_path / "aeep.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "executors": [
                    {
                        "id": "cmd",
                        "capability": "x",
                        "kind": "command",
                        "description": "x",
                        "side_effect": "none",
                        "config": {"argv": ["echo", "x"], "cwd": "work"},
                    }
                ]
            }
        )
    )
    parsed, _ = load_manifest(manifest)
    assert parsed.executors[0].config["cwd"] == str((tmp_path / "work").resolve())
