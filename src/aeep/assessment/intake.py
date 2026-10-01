"""Bounded static declarations from selected packages; never starts an integration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field

from ..errors import ConfigurationError
from ..models import StrictModel
from ..sdk import import_openapi


class IntakeDeclarations(StrictModel):
    description: str = ""
    tools: list[dict[str, Any]] = Field(default_factory=list)
    skills: list[dict[str, Any]] = Field(default_factory=list)
    workflows: list[dict[str, Any]] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


def _document(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text()) if path.suffix == ".json" else yaml.safe_load(path.read_text())
    except (UnicodeError, ValueError, yaml.YAMLError) as exc:
        raise ConfigurationError("selected package has malformed static metadata") from exc
    if not isinstance(value, dict):
        raise ConfigurationError("selected metadata must contain an object")
    return value


def declarations(location: Path, files: dict[str, str], kind: str) -> IntakeDeclarations:
    result = IntakeDeclarations()
    paths = [location / name for name in files] if location.is_dir() else [location]
    for path in paths:
        if path.name == "SKILL.md":
            text = path.read_text()
            parts = text.split("---", 2) if text.startswith("---") else []
            try:
                metadata = yaml.safe_load(parts[1]) if len(parts) == 3 else {}
            except yaml.YAMLError as exc:
                raise ConfigurationError("skill front matter is malformed") from exc
            if not isinstance(metadata, dict):
                raise ConfigurationError("skill front matter must contain an object")
            result.skills.append({
                "name": str(metadata.get("name", path.parent.name)),
                "description": str(metadata.get("description", ""))[:10000],
                "path": str(path), "sha256": files[str(path.relative_to(location)) if location.is_dir() else path.name],
            })
            # Preserve concrete runtime requirements found in instructions. These
            # are review prompts, not executable configuration or approval.
            for dependency in ("@oai/artifact-tool", "load_workspace_dependencies"):
                if dependency in text:
                    result.missing.append(f"Skill runtime dependency requires a reviewed mapping: {dependency}")
        elif path.name == "plugin.json" and path.parent.name == ".codex-plugin":
            metadata = _document(path)
            result.description = str(metadata.get("description", ""))[:10000]
        elif path.name in {".mcp.json", "mcp.json"}:
            # Commands, URLs and environment values are deliberately not copied into proposals.
            servers = _document(path).get("mcpServers", {})
            if not isinstance(servers, dict):
                raise ConfigurationError("MCP server declarations must contain an object")
            for name, server in servers.items():
                if not isinstance(server, dict):
                    raise ConfigurationError("MCP server declaration is malformed")
                result.missing.append(f"Server {name}: authorized tools/list is needed for callable schemas.")
        elif kind == "openapi" and path == location:
            provider = import_openapi(path, provider_id="selected-plugin")
            for spec in provider.executors:
                result.tools.append({"name": spec.id, "description": spec.description, "inputSchema": spec.input_schema, "outputSchema": spec.output_schema, "capability": spec.capability})
        elif path.suffix in {".json", ".yaml", ".yml"} and (kind in {"provider_package", "mcp", "command"} or path.name in {"manifest.json", "tools.json", "workflows.json", "aeep-provider.yaml", "aeep-provider.yml"}):
            metadata = _document(path)
            document = metadata.get("spec", metadata)
            if not isinstance(document, dict):
                raise ConfigurationError("package specification must contain an object")
            tools = document.get("tools", document.get("executors", document.get("routes", [])))
            if isinstance(tools, dict):
                tools = list(tools.values())
            if not isinstance(tools, list):
                raise ConfigurationError("tool declarations must be a list")
            for tool in tools:
                if not isinstance(tool, dict):
                    raise ConfigurationError("tool declaration must contain an object")
                result.tools.append({
                    "name": tool.get("name", tool.get("id", tool.get("route_id"))),
                    "description": str(tool.get("description", ""))[:10000],
                    "inputSchema": tool.get("inputSchema", tool.get("input_schema")),
                    "outputSchema": tool.get("outputSchema", tool.get("output_schema")),
                    "annotations": tool.get("annotations", {}),
                })
            workflows = document.get("workflows", [])
            if not isinstance(workflows, list):
                raise ConfigurationError("workflow declarations must be a list")
            for workflow in workflows:
                if not isinstance(workflow, dict):
                    raise ConfigurationError("workflow declaration must contain an object")
                steps = workflow.get("steps", [])
                if not isinstance(steps, list) or any(not isinstance(step, dict) or not isinstance(step.get("action", {}), dict) for step in steps):
                    raise ConfigurationError("workflow steps must contain action objects")
                # Retain structure, never literal task inputs or executor environment values.
                result.workflows.append({"name": workflow.get("workflow_id"), "steps": [{"step_id": step.get("step_id"), "capability": step.get("action", {}).get("capability"), "depends_on": step.get("depends_on", []), "bindings": step.get("bindings", [])} for step in steps], "outputs": workflow.get("outputs", [])})
    if not (result.tools or result.skills or result.workflows):
        result.missing.append("No callable contract found; select a skill, advertise tool schemas, or review a command wrapper.")
    if result.skills:
        result.missing.append("Skills need a reviewed task mapping and supported Codex sandbox access.")
    if not result.description:
        result.description = next((str(item["description"]) for item in [*result.skills, *result.tools] if item.get("description")), "Locally selected package; declarations are not execution approval.")
    return result
