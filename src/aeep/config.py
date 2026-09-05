"""Manifest discovery, loading, normalization, and initialization."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .errors import ConfigurationError
from .models import Manifest
from .policy import builtin_policies

DEFAULT_NAMES = ("aeep.yaml", "aeep.yml")


def find_manifest(explicit: str | Path | None = None) -> Path:
    if explicit is not None:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise ConfigurationError(f"manifest not found: {path}")
        return path.resolve()
    env_path = os.getenv("AEEP_CONFIG")
    if env_path:
        return find_manifest(env_path)
    for name in DEFAULT_NAMES:
        candidate = Path.cwd() / name
        if candidate.is_file():
            return candidate.resolve()
    user_path = Path.home() / ".config" / "aeep" / "config.yaml"
    if user_path.is_file():
        return user_path.resolve()
    raise ConfigurationError(
        "no AEEP manifest found; run `aeep init` or pass --manifest /path/to/aeep.yaml"
    )


def load_manifest(path: str | Path | None = None) -> tuple[Manifest, Path]:
    manifest_path = find_manifest(path)
    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigurationError(f"cannot read manifest {manifest_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigurationError("manifest root must be a mapping")
    try:
        manifest = Manifest.model_validate(raw)
    except ValidationError as exc:
        raise ConfigurationError(f"invalid manifest {manifest_path}: {exc}") from exc

    policies = builtin_policies()
    policies.update(manifest.policies)
    manifest.policies = policies
    if manifest.default_policy not in manifest.policies:
        raise ConfigurationError(
            f"default policy {manifest.default_policy!r} is not defined after policy loading"
        )

    database = Path(manifest.database).expanduser()
    if manifest.database != ":memory:" and not database.is_absolute():
        database = manifest_path.parent / database
    manifest.database = str(database)

    for executor in manifest.executors:
        cwd = executor.config.get("cwd")
        if isinstance(cwd, str):
            cwd_path = Path(cwd).expanduser()
            if not cwd_path.is_absolute():
                executor.config["cwd"] = str((manifest_path.parent / cwd_path).resolve())
    for registry in manifest.registries:
        if registry.kind == "local" and registry.path:
            registry_path = Path(registry.path).expanduser()
            if not registry_path.is_absolute():
                registry.path = str((manifest_path.parent / registry_path).resolve())
    return manifest, manifest_path


def default_manifest_dict() -> dict[str, Any]:
    return {
        "version": "0.7",
        "database": ".aeep/aeep.db",
        "default_policy": "balanced",
        "persistence": {
            "store_action_inputs": False,
            "store_action_context": False,
        },
        "policies": {},
        "resources": [
            {
                "id": "host.subscription",
                "kind": "subscription",
                "provider": "current-host",
                "product": "current-agent",
                "access": {"mode": "host"},
                "quota": {"state": "unknown", "confidence": 0.5, "source": "user"},
                "capabilities": {"reasoning": True, "coding": True},
            }
        ],
        "executors": [
            {
                "id": "builtin.text-stats",
                "capability": "text.stats",
                "kind": "python",
                "description": "Compute deterministic character, word, and line counts locally.",
                "input_schema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "characters": {"type": "integer"},
                        "words": {"type": "integer"},
                        "lines": {"type": "integer"},
                    },
                    "required": ["characters", "words", "lines"],
                    "additionalProperties": False,
                },
                "estimate": {
                    "resources": {
                        "monetary_usd": 0.0,
                        "latency_ms": 2,
                        "cpu_ms": 1,
                        "memory_mb_seconds": 0.2,
                        "peak_memory_mb": 32,
                    },
                    "success_probability": 0.999,
                    "quality_score": 1.0,
                    "risk_score": 0.001,
                    "confidence": 0.9,
                },
                "side_effect": "none",
                "locality": "in_process",
                "idempotent": True,
                "config": {"callable": "aeep.examples.tools:text_stats"},
            },
            {
                "id": "cli.text-stats",
                "capability": "text.stats",
                "kind": "command",
                "description": "Run the same text statistics operation through a local CLI.",
                "input_schema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "characters": {"type": "integer"},
                        "words": {"type": "integer"},
                        "lines": {"type": "integer"},
                    },
                    "required": ["characters", "words", "lines"],
                    "additionalProperties": False,
                },
                "estimate": {
                    "resources": {
                        "latency_ms": 35,
                        "cpu_ms": 15,
                        "memory_mb_seconds": 2,
                        "peak_memory_mb": 48,
                    },
                    "success_probability": 0.995,
                    "quality_score": 1.0,
                    "risk_score": 0.005,
                    "confidence": 0.8,
                },
                "side_effect": "none",
                "locality": "local",
                "idempotent": True,
                "config": {
                    "argv": [sys.executable, "-m", "aeep.examples.text_stats_cli", "{input.text}"],
                    "output": {"type": "json"},
                    "timeout_seconds": 10,
                },
            },
            {
                "id": "host.text-stats",
                "capability": "text.stats",
                "kind": "host",
                "description": "Let the current subscribed agent host perform the action.",
                "input_schema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "characters": {"type": "integer"},
                        "words": {"type": "integer"},
                        "lines": {"type": "integer"},
                    },
                    "required": ["characters", "words", "lines"],
                    "additionalProperties": False,
                },
                "estimate": {
                    "resources": {
                        "latency_ms": 2500,
                        "context_tokens": 1000,
                        "subscription_units": 1,
                    },
                    "success_probability": 0.9,
                    "quality_score": 0.95,
                    "risk_score": 0.05,
                    "confidence": 0.4,
                },
                "side_effect": "none",
                "locality": "local",
                "resource_pool": "host.subscription",
                "config": {
                    "instructions": "Count the characters, words, and lines in {input.text}."
                },
            },
        ],
    }


def write_default_manifest(path: str | Path = "aeep.yaml", *, force: bool = False) -> Path:
    destination = Path(path).expanduser()
    if destination.exists() and not force:
        raise ConfigurationError(f"refusing to overwrite existing file: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        yaml.safe_dump(default_manifest_dict(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return destination.resolve()
