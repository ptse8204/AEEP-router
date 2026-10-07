"""Supported Codex inventory and exact invocation targets; credentials stay in Codex."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from ..errors import ConfigurationError
from ..models import ManagedHostInvocation, RawExecution
from .base import ManagedHostExecutionContext


class Transport(Protocol):
    async def request(
        self, method: str, params: dict[str, Any] | None = None, *, timeout: float | None = None
    ) -> dict[str, Any]: ...


def worker_permissions(*, writable: bool, skill_path: str | None = None) -> dict[str, Any]:
    """Named profile shared by worker sessions and harmless local boundary probes."""
    filesystem: dict[str, Any] = {":minimal": "read", ":workspace_roots": {".": "write" if writable else "read"}}
    if skill_path is not None:
        filesystem[skill_path] = "read"
    return {"permissions.aeep_assessment.filesystem": filesystem, "permissions.aeep_assessment.network.enabled": False}


def contract_digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


async def inventory(
    transport: Transport, cwd: str | None, *, thread_id: str | None = None
) -> dict[str, Any]:
    """May initialize host-owned servers. Call only within an authorized operation."""
    skills = await transport.request(
        "skills/list", {"cwds": [cwd] if cwd else [], "forceReload": True}
    )
    apps = await transport.request(
        "app/installed", {"forceRefresh": False, **({"threadId": thread_id} if thread_id else {})}
    )
    servers = []
    cursor = None
    seen: set[str] = set()
    for _ in range(100):
        page = await transport.request(
            "mcpServerStatus/list",
            {
                "detail": "toolsAndAuthOnly",
                "limit": 100,
                **({"threadId": thread_id} if thread_id else {}),
                **({"cursor": cursor} if cursor else {}),
            },
        )
        if not isinstance(page.get("data"), list):
            raise ConfigurationError("Codex MCP inventory is unavailable")
        for server in page["data"]:
            if not isinstance(server, dict) or not isinstance(server.get("tools"), dict):
                raise ConfigurationError("Codex MCP inventory is malformed")
            # Do not retain auth status, endpoints, resource URIs or account fields.
            servers.append(
                {
                    key: server.get(key)
                    for key in ("name", "tools", "pluginId", "serverInfo", "toolsError")
                }
            )
        cursor = page.get("nextCursor")
        if not cursor:
            break
        if not isinstance(cursor, str) or cursor in seen:
            raise ConfigurationError("Codex inventory cursor repeated")
        seen.add(cursor)
    else:
        raise ConfigurationError("Codex inventory exceeds the page limit")
    if not isinstance(skills.get("data"), list) or not isinstance(apps.get("apps"), list):
        raise ConfigurationError("Codex skill or app inventory is unavailable")
    entries = []
    for group in skills["data"]:
        if (
            not isinstance(group, dict)
            or group.get("errors")
            or not isinstance(group.get("skills"), list)
        ):
            raise ConfigurationError("Codex skill inventory is incomplete")
        for skill in group["skills"]:
            if not isinstance(skill, dict):
                raise ConfigurationError("Codex skill inventory is malformed")
            entries.append(
                {
                    key: skill.get(key)
                    for key in (
                        "name",
                        "path",
                        "description",
                        "enabled",
                        "pluginId",
                        "dependencies",
                    )
                }
            )
    return {
        "skills": entries,
        "apps": [
            {key: app.get(key) for key in ("id", "runtimeName", "enabled", "callable")}
            for app in apps["apps"]
            if isinstance(app, dict)
        ],
        "servers": servers,
    }


_BUNDLED_AEEP_SKILL_SHA256 = {
    '8670c149355a4960bba3f996499483df075e3a1df1c531201ff8f7c61dec901a',
    'f6e642b50fb67722841d6332cda22c2a67d8728bb57316af258c6a15c3042d50',
    'c87c9d22e22aba152fd56b796ec74dc85fc07366c91e0958f1040c2638fdd8b6',
    '25d1d391ab0d679f615282b2121ec9234f6b6dc7da35a0db629259728d02678f',
    'd0489c6744f8b0eb0cd6d4e2a71c05389aeb75eb0d799158d93677b762c1a522',
}


def _recursive_aeep_skill(skill: dict[str, Any], path: Path, digest: str | None) -> bool:
    """Match skill identity, not incidental ancestor text in a project path."""
    name = str(skill.get('name', '')).rsplit(':', 1)[-1].lower()
    parts = [part.lower() for part in path.parts]
    packaged = any(parts[index:index + 3] == ['integrations', 'aeep', 'skills']
                   for index in range(len(parts) - 2))
    plugin = str(skill.get('pluginId', '')).split('@', 1)[0].lower()
    return (name in {'aeep', 'assess-plugin'} or name.startswith('aeep-')
            or plugin == 'aeep' or plugin.startswith('aeep-') or packaged
            or digest in _BUNDLED_AEEP_SKILL_SHA256)


def isolated_config(catalog: dict[str, Any], target: ManagedHostInvocation, *, verified_worker_skill: bool = False, reviewed_worker_files: dict[str, str] | None = None) -> dict[str, Any]:
    """Thread-local overrides only. Never edit the user's Codex configuration."""
    overrides: dict[str, Any] = {
        "apps._default.enabled": False,
        "features.apps": False,
        "features.code_mode_host": False,
        "features.computer_use": False,
        "features.browser_use": False,
        "features.browser_use_external": False,
        "features.skill_search": False,
        "features.tool_suggest": False,
        "features.multi_agent": False,
        "agents.enabled": False,
        "features.image_generation": False,
        "features.sleep_tool": False,
        "features.view_image": False,
        "features.goals": False,
        "features.hooks": False,
        "features.memories": False,
        "features.skill_mcp_dependency_install": False,
        "features.shell_tool": False,
        "features.unified_exec": False,
        "tools.view_image": False,
        "web_search": "disabled",
    }
    if target.local_profile == "capable_local":
        overrides.update({"features.shell_tool": True, "features.unified_exec": True})
    if target.native_catalog:
        overrides.update({"features.skill_search": True, "features.tool_suggest": True})
    for app in catalog["apps"]:
        identity = app["id"]
        if not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", identity):
            raise ConfigurationError("Codex app identity cannot be safely scoped")
        overrides[f"apps.{identity}.enabled"] = False
    skill_found = False
    skill_config = []
    supporting = {item.path: item for item in target.supporting_skills}
    found_supporting: set[str] = set()
    skill_path_type = PurePosixPath if reviewed_worker_files is not None or verified_worker_skill else Path
    for skill in catalog["skills"]:
        path = skill["path"]
        if not isinstance(path, str) or not skill_path_type(path).is_absolute():
            raise ConfigurationError("Codex skill has no explicit absolute path")
        selected = (
            target.mode == "skill"
            and path == target.skill_path
            and skill["name"] == target.skill_name
        )
        if selected:
            file = Path(path)
            if (
                not skill["enabled"]
                or (reviewed_worker_files is not None and not verified_worker_skill)
                or (not verified_worker_skill and (file.is_symlink()
                    or not file.is_file()
                    or file.stat().st_size > 1_000_000
                    or hashlib.sha256(file.read_bytes()).hexdigest() != target.skill_sha256))
                or _recursive_aeep_skill(skill, file, target.skill_sha256)
            ):
                raise ConfigurationError("skill is unavailable, changed or recursive")
            # Skills that need tools require a separately reviewed workflow mapping.
            if (skill.get("dependencies") or {}).get("tools") and not target.supporting_tools:
                raise ConfigurationError(
                    "skill tool dependencies require a reviewed workflow mapping"
                )
            skill_found = True
        if path in supporting:
            reviewed = supporting[path]
            file = Path(path)
            verified = (reviewed_worker_files or {}).get(path) == reviewed.sha256
            if (skill["name"] != reviewed.name or not skill["enabled"]
                    or _recursive_aeep_skill(skill, file, reviewed.sha256)
                    or (reviewed_worker_files is not None and not verified)
                    or (not verified and (file.is_symlink() or not file.is_file()
                        or file.stat().st_size > 1_000_000
                        or hashlib.sha256(file.read_bytes()).hexdigest() != reviewed.sha256))):
                raise ConfigurationError("supporting skill is unavailable, changed or recursive")
            if (skill.get("dependencies") or {}).get("tools") and not target.supporting_tools:
                raise ConfigurationError("supporting skill dependencies require a reviewed workflow mapping")
            found_supporting.add(path)
            selected = True
        skill_config.append({"path": str(skill_path_type(path).parent), "enabled": selected})
    if found_supporting != set(supporting):
        raise ConfigurationError("reviewed supporting skill is absent from host inventory")
    overrides["skills.config"] = skill_config
    allowed = {(item.server, item.tool): item.sha256 for item in target.supporting_tools}
    if target.mode == "mcp_tool":
        assert target.server is not None and target.tool is not None and target.tool_sha256 is not None
        allowed[(target.server, target.tool)] = target.tool_sha256
    found = set()
    tool_found = False
    for server in catalog["servers"]:
        name = server["name"]
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise ConfigurationError("Codex MCP server identity cannot be safely scoped")
        selected = any(server_name == name for server_name, _ in allowed)
        plugin = server.get("pluginId")
        # Host-generated servers have no configured transport to override. Their
        # feature switches are above; the effective catalog must still be checked.
        if plugin is None and name in {"codex_apps", "node_repl", "computer-use", "shortlist"}:
            if selected:
                raise ConfigurationError("host-generated MCP tools require a supported isolated host mapping")
            continue
        if plugin is not None and (not isinstance(plugin, str) or not re.fullmatch(r"[A-Za-z0-9_@./+-]+", plugin)):
            raise ConfigurationError("Codex plugin identity cannot be safely scoped")
        prefix = f"plugins.{json.dumps(plugin)}.mcp_servers.{name}" if plugin else f"mcp_servers.{name}"
        overrides[f"{prefix}.enabled"] = selected
        if selected:
            names = [tool_name for server_name, tool_name in allowed if server_name == name]
            for tool_name in names:
                tool = server["tools"].get(tool_name)
                if (
                    server.get("toolsError") or not isinstance(tool, dict)
                    or contract_digest(tool) != allowed[(name, tool_name)]
                    or "aeep" in name.lower()
                    or "aeep" in str((server.get("serverInfo") or {}).get("name", "")).lower()
                    or {"route_action", "execute_action", "prepare_action"}.intersection(server["tools"])
                    or any(str(key).startswith("aeep_") for key in server["tools"])
                ):
                    raise ConfigurationError("MCP target is unavailable, changed or recursive")
                found.add((name, tool_name))
                tool_found |= target.mode == "mcp_tool" and name == target.server and tool_name == target.tool
            overrides[f"{prefix}.enabled_tools"] = names
    if set(allowed) != found:
        raise ConfigurationError("reviewed supporting tool is absent from the current inventory")
    if (target.mode == "skill" and not skill_found) or (
        target.mode == "mcp_tool" and not tool_found
    ):
        raise ConfigurationError("reviewed invocation target is absent from the current inventory")
    return overrides


def resolve_skill_name(catalog: dict[str, Any], target: ManagedHostInvocation) -> ManagedHostInvocation:
    """A host namespace may qualify the name; the reviewed path still identifies the skill."""
    if target.mode != "skill":
        return target
    matches = [skill for skill in catalog["skills"] if skill.get("path") == target.skill_path]
    if len(matches) != 1:
        raise ConfigurationError("reviewed skill path is absent or ambiguous")
    name = matches[0].get("name")
    if not isinstance(name, str) or (name != target.skill_name and name.rsplit(":", 1)[-1] != target.skill_name):
        raise ConfigurationError("reviewed skill name changed")
    return target.model_copy(update={"skill_name": name})


async def verify_thread_inventory(
    transport: Transport, thread_id: str, target: ManagedHostInvocation
) -> dict[str, Any] | None:
    """Check advertised inventory consistency; this alone does not attest enforcement."""
    allowed = {(item.server, item.tool): item.sha256 for item in target.supporting_tools}
    if target.mode == "mcp_tool":
        assert target.server is not None and target.tool is not None and target.tool_sha256 is not None
        allowed[(target.server, target.tool)] = target.tool_sha256
    advertised = await advertised_tools(transport, thread_id)
    selected = None
    for (server, name), tool in advertised.items():
        if allowed.get((server, name)) != contract_digest(tool):
            raise ConfigurationError("environment verification unavailable: advertised inventory differs from reviewed tools")
        if target.mode == "mcp_tool" and server == target.server and name == target.tool:
            selected = tool
    if set(advertised) != set(allowed):
        raise ConfigurationError("reviewed MCP tool is unavailable in the thread")
    apps = await transport.request("app/installed", {"threadId": thread_id, "forceRefresh": False})
    if not isinstance(apps.get("apps"), list) or any(not isinstance(app, dict) or app.get("callable") for app in apps["apps"]):
        raise ConfigurationError("environment verification unavailable: callable app inventory is not isolated")
    return selected


async def advertised_tools(transport: Transport, thread_id: str) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    cursor = None
    seen: set[str] = set()
    for _ in range(100):
        page = await transport.request("mcpServerStatus/list", {"threadId": thread_id, "detail": "toolsAndAuthOnly", "limit": 100, **({"cursor": cursor} if cursor else {})})
        if not isinstance(page.get("data"), list):
            raise ConfigurationError("isolated MCP inventory cannot be verified")
        for server in page["data"]:
            if not isinstance(server, dict) or not isinstance(server.get("name"), str) or not isinstance(server.get("tools"), dict) or server.get("toolsError"):
                raise ConfigurationError("isolated MCP inventory is incomplete")
            for name, tool in server["tools"].items():
                key = (server["name"], name)
                if not isinstance(name, str) or not isinstance(tool, dict) or key in result:
                    raise ConfigurationError("isolated MCP inventory is malformed or duplicated")
                result[key] = tool
        cursor = page.get("nextCursor")
        if not cursor:
            return result
        if not isinstance(cursor, str) or cursor in seen:
            raise ConfigurationError("isolated MCP inventory pagination repeated")
        seen.add(cursor)
    raise ConfigurationError("isolated MCP inventory exceeds its page limit")


async def call_mcp(
    transport: Transport,
    context: ManagedHostExecutionContext,
    thread_id: str,
    tool: dict[str, Any] | None,
    started: float,
) -> RawExecution:
    import time

    from ..executors.mcp import _extract_result
    from ..models import ExecutionStatus, RawExecution, ResourceVector
    from ..registry import validate_json

    if tool is None:
        raise ConfigurationError("reviewed tool contract is unavailable")
    assert context.config.invocation is not None
    validate_json(context.request.input, tool["inputSchema"], label="host-owned MCP arguments")
    result = await transport.request(
        "mcpServer/tool/call",
        {
            "threadId": thread_id,
            "server": context.config.invocation.server,
            "tool": context.config.invocation.tool,
            "arguments": context.request.input,
        },
        timeout=context.config.timeout_seconds,
    )
    output = _extract_result(result, parse_json_text=True)
    # Host ownership authenticates the invocation, not provider accounting claims.
    return RawExecution(
        status=ExecutionStatus.FAILED if result.get("isError") else ExecutionStatus.SUCCESS,
        output=output,
        resources=ResourceVector(latency_ms=max(0, time.monotonic() - started) * 1000),
        error_type="MCPToolError" if result.get("isError") else None,
        metadata={"model_turn_count": 0, "tool_call_count": 1, "host_owned_mcp": True},
    )
