"""Pure assembly for the current two-role B qualification profile.

Input is caller-supplied immutable profile/callback metadata. This module does
not load callback services, inspect a repository, create conformance records,
or create a qualification plan. It does not construct the later three-role
normal/discovery/AEEP value definition.
"""
from __future__ import annotations

import copy
import math
import re
from pathlib import Path
from typing import Any

from aeep.assessment.models import DifferentialEnvironment, content_digest
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_invocation import contract_digest
from aeep.hosts.codex_pair_inspection import ComposedPairDefinition
from aeep.hosts.workers import binding_from_config, validate_worker_pair
from aeep.models import ExecutorSpec

SOURCE = "9d09d61a152e79eaf01f8c51f9039f06468e13d07ad304544eb302ad3b39d751"
ROLES = ("control", "treatment")
SHARED_SKILL_SCHEMA = "assessment.b-shared-spreadsheets.v1"
CANONICAL_SKILL_PATH = "/opt/dependencies/plugin/skills/spreadsheets/SKILL.md"
SKILL_ALIAS_PATH = "/etc/codex/skills/spreadsheets/SKILL.md"
SHARED_RUNTIME_PATH = "/opt/dependencies/runtime"
SHARED_ALIAS_NAMES = {"Spreadsheets", "spreadsheets:Spreadsheets"}


def _shared_spreadsheets(document: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ValueError("shared Spreadsheets definition must be an object")
    required = {
        "schema_version", "image_digest", "skill_path", "alias_path",
        "runtime_path", "skill_sha256", "alias_paths", "shared_versions",
        "dependency_expectations",
    }
    if set(document) != required or document.get("schema_version") != SHARED_SKILL_SCHEMA:
        raise ValueError("exact reviewed shared Spreadsheets definition is required")
    if any(not isinstance(document[field], str)
           for field in ("image_digest", "skill_path", "alias_path", "runtime_path", "skill_sha256")):
        raise ValueError("shared Spreadsheets paths and digests must be strings")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(document["image_digest"])):
        raise ValueError("shared Spreadsheets image must be digest-pinned")
    for field in ("skill_path", "alias_path", "runtime_path"):
        path = Path(document[field])
        if not path.is_absolute() or ".." in path.parts:
            raise ValueError("shared Spreadsheets paths must be absolute and bounded")
    if (Path(document["skill_path"]).name != "SKILL.md"
            or Path(document["alias_path"]).name != "SKILL.md"
            or document["skill_path"] != CANONICAL_SKILL_PATH
            or document["alias_path"] != SKILL_ALIAS_PATH
            or document["runtime_path"] != SHARED_RUNTIME_PATH
            or not re.fullmatch(r"[0-9a-f]{64}", str(document["skill_sha256"]))):
        raise ValueError("shared Spreadsheets skill paths or digest differ")
    aliases = document["alias_paths"]
    if (not isinstance(aliases, dict) or not aliases
            or set(aliases) not in ({"Spreadsheets"}, {"spreadsheets:Spreadsheets"})
            or any(not isinstance(path, str) for path in aliases.values())
            or len(aliases) != 1 or set(aliases.values()) != {document["skill_path"]}
            or len(set(aliases.values())) != len(aliases)):
        raise ValueError("one enabled alias must map to the canonical Spreadsheets skill path")
    versions = document["shared_versions"]
    if (not isinstance(versions, dict) or set(versions) != {"pandas", "openpyxl"}
            or any(not isinstance(value, str) or not value for value in versions.values())):
        raise ValueError("exact pandas and openpyxl versions are required")
    dependencies = document["dependency_expectations"]
    if (not isinstance(dependencies, dict)
            or set(dependencies) != {"authoring_helper", "artifact_tool_csv"}
            or any(value is not True for value in dependencies.values())):
        raise ValueError("both reviewed shared Spreadsheets dependencies are required")
    return copy.deepcopy(document)


def _callback_inventory(
    document: dict[str, Any], worker_digest: str, implementation_digest: str,
    artifact: dict[str, Any] | None,
) -> tuple[str, str, dict[str, str]]:
    if (not isinstance(document, dict)
            or set(document) != {"namespace", "tools", "identity", "max_calls", "timeout_seconds"}):
        raise ValueError("callback document must be the exact operator-produced definition")
    namespace = document["namespace"]
    tools = document["tools"]
    identity = document["identity"]
    if (not isinstance(namespace, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", namespace)
            or not isinstance(tools, list) or not tools or len(tools) > 32
            or not isinstance(identity, dict)):
        raise ValueError("callback namespace, declarations, or identity are incomplete")
    if (type(document["max_calls"]) is not int or document["max_calls"] < 1
            or isinstance(document["timeout_seconds"], bool)
            or not isinstance(document["timeout_seconds"], (int, float))
            or not math.isfinite(document["timeout_seconds"])
            or document["timeout_seconds"] <= 0):
        raise ValueError("callback limits are invalid")
    for field in ("worker_digest", "native_backend_digest", "implementation_digest"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(identity.get(field, ""))):
            raise ValueError("callback identity lacks an exact digest")
    if identity["worker_digest"] != worker_digest:
        raise ValueError("callback document belongs to a different worker")
    if identity["implementation_digest"] != implementation_digest:
        raise ValueError("callback implementation digest differs from the current implementation")
    if (identity.get("approval_ceiling") != "read"
            or document["max_calls"] != 1 or document["timeout_seconds"] != 10.0
            or identity.get("scope_limits") != {"max_attempts": 1, "max_attempt_seconds": 10.0}):
        raise ValueError("B callback authority must retain the exact one-call READ scope")
    fingerprints = identity.get("executor_fingerprints")
    if (not isinstance(fingerprints, dict) or not fingerprints
            or any(not isinstance(key, str) or not key
                   or not re.fullmatch(r"[0-9a-f]{64}", str(value))
                   for key, value in fingerprints.items())
            or not isinstance(identity.get("scope_limits"), dict)
            or identity.get("artifact") != artifact):
        raise ValueError("fresh callback authority, scope, and artifact identity are required")
    names: set[str] = set()
    inventory: dict[str, str] = {}
    for tool in tools:
        if (not isinstance(tool, dict)
                or set(tool) - {"name", "description", "inputSchema", "outputSchema"}
                or not isinstance(tool.get("name"), str)
                or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", tool["name"])
                or tool["name"] in names or not isinstance(tool.get("description"), str)
                or not isinstance(tool.get("inputSchema"), dict)):
            raise ValueError("callback declaration is malformed or duplicated")
        names.add(tool["name"])
        inventory[f"dynamic:{namespace}:{tool['name']}"] = contract_digest(tool)
    return content_digest(document), identity["native_backend_digest"], inventory


def assemble_current_profile(
    *,
    profile_document: dict[str, Any],
    spreadsheets_definition: dict[str, Any],
    shared_physical_skill_inventory: dict[str, dict[str, str]],
    selected_worker: str,
    qualification_exposure: str,
    source_root: str | Path,
) -> dict[str, Any]:
    """Return a validated two-role component without creating evidence or plans.

    ``profile_document`` must provide ``pair.control``, ``pair.treatment`` and
    ``callback_documents_by_role`` from the exact current setup. The explicit
    physical inventory is expected metadata for both roles; only later worker
    observations can establish what was actually available.
    """
    if not isinstance(profile_document, dict):
        raise ValueError("profile_document must be an object")
    if not isinstance(selected_worker, str) or not re.fullmatch(r"[0-9a-f]{64}", selected_worker):
        raise ValueError("selected_worker must be an exact worker digest")
    if verification_source_digest(Path(source_root)) != SOURCE:
        raise ValueError("current source differs from the exact B assembler pin")
    from aeep.hosts.codex_dynamic_tools import CodexDynamicTools

    callback_implementation_digest = CodexDynamicTools.implementation_digest()
    if qualification_exposure != "required":
        raise ValueError("B qualification requires candidate exposure='required'")
    pair_input = profile_document.get("pair")
    callback_documents = profile_document.get("callback_documents_by_role")
    if (profile_document.get("source_digest") != SOURCE
            or not isinstance(pair_input, dict) or not {"control", "treatment"} <= set(pair_input)
            or not isinstance(callback_documents, dict)
            or set(callback_documents) != set(ROLES)):
        raise ValueError("current-source control/treatment profiles and callback documents are required")

    spreadsheets = _shared_spreadsheets(spreadsheets_definition)
    expected_physical = {path: spreadsheets["skill_sha256"]
                         for path in spreadsheets["alias_paths"].values()}
    if (not isinstance(shared_physical_skill_inventory, dict)
            or set(shared_physical_skill_inventory) != {"discovery", "aeep"}
            or any(shared_physical_skill_inventory[role] != expected_physical
                   for role in ("discovery", "aeep"))):
        raise ValueError("discovery and AEEP must supply the same exact physical skill inventory")

    specs: dict[str, ExecutorSpec] = {}
    workers: dict[str, Any] = {}
    callback_digests: dict[str, str] = {}
    native_backends: dict[str, str] = {}
    callback_inventories: dict[str, dict[str, str]] = {}
    expected_skills = sorted(
        ({"name": name, "path": path, "sha256": spreadsheets["skill_sha256"]}
         for name, path in spreadsheets["alias_paths"].items()),
        key=lambda item: (item["name"], item["path"]),
    )

    for role in ROLES:
        spec = ExecutorSpec.model_validate(copy.deepcopy(pair_input[role]))
        config = spec.managed_host_config()
        worker = binding_from_config(config.managed_worker)
        target = config.invocation
        if worker is None or target is None:
            raise ValueError(f"{role} requires an exact managed worker and invocation")
        if (config.model_constraints.allowed_model_ids != ("gpt-6-luna",)
                or config.reasoning_efforts != ("xhigh",)
                or config.approval_ceiling.value != "read"
                or spec.side_effect.value != "read"):
            raise ValueError("both roles must pin gpt-6-luna with xhigh reasoning")
        if (worker.image != spreadsheets["image_digest"]
                or worker.reviewed_files is None
                or worker.reviewed_files.get(spreadsheets["skill_path"]) != spreadsheets["skill_sha256"]
                or target.native_catalog is not False
                or target.supporting_tools
                or sorted((item.model_dump(mode="json") for item in target.supporting_skills),
                          key=lambda item: (item["name"], item["path"])) != expected_skills):
            raise ValueError("both roles require the same exact shared physical skill profile")
        if target.local_profile != "capable_local":
            raise ValueError("both roles require the reviewed capable-local profile")
        digest, backend, inventory = _callback_inventory(
            callback_documents[role], worker.digest(), callback_implementation_digest,
            config.artifact.model_dump(mode="json") if config.artifact is not None else None,
        )
        invocation = target.model_dump(mode="json")
        invocation["dynamic_tools_digest"] = digest
        if role == "control":
            if (target.mode != "turn" or target.server is not None or target.tool is not None
                    or target.tool_sha256 is not None or target.exposure is not None):
                raise ValueError("discovery control must remain fixed-turn with no AEEP target")
        else:
            if (target.mode != "dynamic_tool" or target.exposure != qualification_exposure
                    or not target.server or not target.tool or not target.tool_sha256):
                raise ValueError("AEEP treatment must bind its exact required-exposure callback target")
        config_value = spec.model_dump(mode="json")
        config_value["config"]["invocation"] = invocation
        specs[role] = ExecutorSpec.model_validate(config_value)
        workers[role] = worker
        callback_digests[worker.digest()] = digest
        native_backends[worker.digest()] = backend
        callback_inventories[role] = inventory

    validate_worker_pair(workers["treatment"], workers["control"])
    if (workers["control"].image != workers["treatment"].image
            or workers["control"].reviewed_files != workers["treatment"].reviewed_files):
        raise ValueError("B profiles must use the same exact worker image and reviewed files")
    if selected_worker != workers["treatment"].digest():
        raise ValueError("selected_worker must be the exact AEEP treatment worker digest")

    control_tools = callback_inventories["control"]
    treatment_tools = callback_inventories["treatment"]
    if any(key in treatment_tools and treatment_tools[key] != value
           for key, value in control_tools.items()):
        raise ValueError("fixed callback declarations changed between discovery and AEEP")
    candidate_dynamic_tools = {key: value for key, value in treatment_tools.items()
                               if key not in control_tools}
    if len(candidate_dynamic_tools) != 1:
        raise ValueError("AEEP callback document must add exactly one dynamic declaration")
    treatment_target = specs["treatment"].managed_host_config().invocation
    if treatment_target is None:
        raise ValueError("AEEP treatment invocation is missing")
    selected_key = f"dynamic:{treatment_target.server}:{treatment_target.tool}"
    if (selected_key not in candidate_dynamic_tools
            or candidate_dynamic_tools[selected_key] != treatment_target.tool_sha256):
        raise ValueError("required treatment invocation is not the exact added callback declaration")

    shared_digest = content_digest(spreadsheets)
    common_inventory = {"spreadsheets_bundle": shared_digest}
    differential = DifferentialEnvironment.model_validate({
        "shared_definition_digest": shared_digest,
        "control_inventory": {**common_inventory, **control_tools},
        "treatment_inventory": {**common_inventory, **treatment_tools},
        "candidate_inventory": candidate_dynamic_tools,
        "candidate_paths": [],
        "candidate_aliases": [],
        "candidate_dynamic_tools": candidate_dynamic_tools,
    })
    composed = ComposedPairDefinition.model_validate({
        "control": specs["control"].model_dump(mode="json"),
        "treatment": specs["treatment"].model_dump(mode="json"),
        "differential": differential.model_dump(mode="json"),
        "shared_versions": spreadsheets["shared_versions"],
        "callback_bindings": callback_digests,
        "native_backends": native_backends,
    })
    component = {
        "schema_version": "assessment.b-composed-worker-component.v1",
        "composed": composed.model_dump(mode="json"),
        "common_inventory": common_inventory,
        "spreadsheets": spreadsheets,
    }
    return {
        "schema_version": "assessment.b-current-profile-assembly.v1",
        "source_digest": SOURCE,
        "component": component,
        "component_digest": content_digest(component),
        "differential": differential.model_dump(mode="json"),
        "differential_digest": content_digest(differential),
        "shared_physical_skill_inventory": copy.deepcopy(shared_physical_skill_inventory),
        "selected_worker_digest": selected_worker,
        "callback_implementation_digest": callback_implementation_digest,
        "qualification_exposure": qualification_exposure,
        "shared_physical_inventory_observed": False,
        "boundary_conformance_created": False,
        "three_way_access_created": False,
        "qualification_plan_created": False,
        "execution_authorized": False,
    }
