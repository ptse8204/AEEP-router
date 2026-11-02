"""Selected workflow runtimes reuse the owned installer and canonical cost ledger."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any, Literal

from aeep.assessment.identity import protected_directory
from aeep.assessment.models import content_digest
from aeep.assessment.verification import verification_source_digest
from aeep.errors import ConfigurationError
from aeep.models import StrictModel

from .install_runtime import (
    RuntimeInstallation,
    apply,
    canonical,
    digest,
    load_state,
    paths,
    remove,
    snapshot,
)
from .installation import PreviewPolicy, preview
from .models import ExtensionRegistry
from .workflow import StackWorkflow, _read
from .workflow_accounting import account_workflow


class RuntimeLifecycleRecord(StrictModel):
    operation_id: str
    workflow_review: str
    installation_digest: str
    runtime_ids: tuple[str, ...]
    operation: Literal["setup", "remove"]
    status: Literal["installed", "removed", "failed"]
    journal_sha256: str | None
    error_type: str | None = None


def runtime_target(value: str) -> Path:
    target = canonical(value)
    if protected_directory(target) or any(
        part.casefold() in {".ssh", ".aws", ".azure", ".gnupg", ".config", ".docker", ".npm"}
        for part in target.parts
    ):
        raise ConfigurationError(
            "runtime lifecycle excludes home/root and credential-state directories"
        )
    return target


def observe(plan: RuntimeInstallation) -> dict[str, Any]:
    """Inspect owned bytes only; never import a package, probe a backend or sign in."""
    root, journal = paths(plan)
    runtime_target(str(root))
    result: dict[str, Any] = {
        "destination": str(root),
        "installed": None,
        "installer_status": "unknown",
        "enabled": None,
        "execution_permission": "NOT_VERIFIED",
        "functional_readiness": "NOT_VERIFIED",
        "usefulness": "NOT_ASSESSED",
        "journal_sha256": None,
        "tree_matches": None,
    }
    try:
        raw, state = load_state(journal)
        if raw is None:
            result.update(
                installed=False if not root.exists() and not root.is_symlink() else None,
                installer_status="absent" if not root.exists() else "unowned_destination",
            )
            return result
        result["journal_sha256"] = hashlib.sha256(raw).hexdigest()
        if state.get("plan_sha256") != digest(plan) or state.get("original") != "absent":
            result["installer_status"] = "ownership_conflict"
            return result
        status = state.get("status")
        result["installer_status"] = status
        if status == "removed" and not root.exists() and not root.is_symlink():
            result["installed"] = False
        elif status == "installed":
            matches = snapshot(root) == state.get("applied_tree_sha256")
            result.update(tree_matches=matches, installed=True if matches else None)
            if not matches:
                result["installer_status"] = "modified_runtime"
        # An installer flag never establishes effective component enablement.
        result["installer_enabled_declaration"] = state.get("enabled")
    except (OSError, ValueError):
        result["installer_status"] = "inspection_failed"
    return result


def lifecycle_preview(
    definition: Path,
    configuration: str,
    runtime_ids: tuple[str, ...],
    *,
    operation: Literal["setup", "readiness", "remove"],
) -> tuple[dict[str, Any], dict[str, RuntimeInstallation]]:
    from .cli import read_json

    workflow = StackWorkflow.model_validate(read_json(definition))
    if (
        configuration not in workflow.configurations
        or not runtime_ids
        or len(set(runtime_ids)) != len(runtime_ids)
    ):
        raise ConfigurationError(
            "select a known configuration and distinct explicit runtime bindings"
        )
    selected = workflow.configurations[configuration]
    if not set(runtime_ids) <= selected.runtimes.keys():
        raise ConfigurationError("selected runtime has no exact installation binding")
    root = definition.absolute().parent
    _, registry_raw = _read(workflow.registry, root)
    _, policy_raw = _read(workflow.policy, root)
    registry = ExtensionRegistry.model_validate_json(registry_raw)
    policy = PreviewPolicy.model_validate_json(policy_raw)
    plans: dict[str, RuntimeInstallation] = {}
    blockers: list[str] = []
    targets: dict[str, str] = {}
    for identity in runtime_ids:
        binding = selected.runtimes[identity]
        _, raw = _read(binding.installation, root)
        plan = RuntimeInstallation.model_validate_json(raw)
        runtime_target(plan.destination)
        packages = {item.manifest.extension_id: item.manifest for item in plan.preview.items}
        for component, package in binding.components.items():
            manifest = registry.get(component)
            if (
                package not in packages
                or manifest.source.artifact_sha256 != packages[package].source.artifact_sha256
            ):
                raise ConfigurationError(
                    "component label differs from the selected package artifact"
                )
        # Retain workflow hard constraints. The install plan supplies the explicit
        # local deployment target, distinct from the evaluation host selection.
        install_policy = policy.model_copy(
            update={"host": plan.policy.host, "platform": plan.policy.platform}
        )
        constrained = preview(
            ExtensionRegistry(extensions=tuple(packages.values())),
            plan.preview.selected,
            install_policy,
            profile="full",
        )
        blockers.extend(identity + ": " + value for value in constrained.blockers)
        existing = targets.get(plan.destination)
        if existing is not None and existing != digest(plan):
            raise ConfigurationError("selected installations conflict at one destination")
        targets[plan.destination] = digest(plan)
        plans[identity] = plan
    selected_targets = [
        (identity, runtime_target(plan.destination)) for identity, plan in plans.items()
    ]
    if any(
        a != b and (pa.is_relative_to(pb) or pb.is_relative_to(pa)) and pa != pb
        for a, pa in selected_targets
        for b, pb in selected_targets
    ):
        raise ConfigurationError("selected runtime directories must not contain each other")
    shared: dict[str, list[str]] = {identity: [] for identity in plans}
    if operation == "remove":
        # Preserve every known unselected workflow reference, including aliases
        # and a runtime nested below a removal target. No unselected code runs.
        for name, config in workflow.configurations.items():
            for identity, binding in config.runtimes.items():
                if name == configuration and identity in runtime_ids:
                    continue
                try:
                    _, raw = _read(binding.installation, root)
                    other = RuntimeInstallation.model_validate_json(raw)
                    destination = canonical(other.destination)
                except (ValueError, OSError):
                    blockers.append(
                        "unselected runtime reference cannot be resolved; removal is blocked"
                    )
                    continue
                for chosen, path in selected_targets:
                    if path.is_relative_to(destination) or destination.is_relative_to(path):
                        shared[chosen].append(name + ":" + identity)
        pending = [
            (reference, root)
            for identity in runtime_ids
            for reference in selected.runtimes[identity].references
        ]
        visited = set()
        while pending:
            reference, base = pending.pop()
            try:
                path, raw = _read(reference, base)
                key = (str(path), reference.sha256)
                if key in visited:
                    continue
                visited.add(key)
                if len(visited) > 16:
                    raise ValueError("runtime reference envelope exceeded")
                parent = StackWorkflow.model_validate_json(raw)
                for name, config in parent.configurations.items():
                    for identity, binding in config.runtimes.items():
                        _, data = _read(binding.installation, path.parent)
                        linked = RuntimeInstallation.model_validate_json(data)
                        destination = canonical(linked.destination)
                        for chosen, target in selected_targets:
                            if target.is_relative_to(destination) or destination.is_relative_to(
                                target
                            ):
                                shared[chosen].append(str(path) + ":" + name + ":" + identity)
                        pending.extend((ref, path.parent) for ref in binding.references)
            except (ValueError, OSError):
                blockers.append("retained parent workflow cannot be resolved; removal is blocked")
                break
        for identity, references in shared.items():
            if references:
                blockers.append(
                    identity + ": runtime is retained for unselected workflow references"
                )
    facts = {
        "workflow": workflow.model_dump(mode="json"),
        "configuration": configuration,
        "operation": operation,
        "runtime_ids": list(runtime_ids),
        "installation_plans": {
            identity: plan.model_dump(mode="json") for identity, plan in plans.items()
        },
        "shared_references": shared,
        "implementation_source": verification_source_digest(Path(__file__).resolve().parents[2]),
    }
    observations = {identity: observe(plan) for identity, plan in plans.items()}
    return {
        **facts,
        "review_sha256": content_digest(facts),
        "blockers": sorted(set(blockers)),
        "observations": observations,
        "execution_authorized": False,
        "notice": "Private Python installation lifecycle only. Exact execution/removal authority and an accounting v2 scope are required for writes. Installation does not establish enablement, execution permission, functional readiness or usefulness. Shared workflow references and changed/unfinished resources are preserved.",
    }, plans


def lifecycle(
    definition: Path,
    configuration: str,
    runtime_ids: tuple[str, ...],
    *,
    operation: Literal["setup", "readiness", "remove"],
    reviewed_digest: str | None,
    accounting: Path | None,
    operation_key: str | None,
) -> dict[str, Any]:
    with account_workflow(
        accounting,
        workflow_file=definition,
        configuration=configuration,
        stage=operation,
        operation_key=operation_key,
    ) as meter:
        details, plans = lifecycle_preview(
            definition, configuration, runtime_ids, operation=operation
        )
        details["workflow_accounting"] = meter.describe() if meter else {"coverage": "NOT_RECORDED"}
        if reviewed_digest is None or operation == "readiness":
            if reviewed_digest is not None and reviewed_digest != details["review_sha256"]:
                raise ConfigurationError("runtime readiness review changed")
            return details
        if reviewed_digest != details["review_sha256"] or details["blockers"]:
            raise ConfigurationError("exact unblocked runtime lifecycle review required")
        if meter is None or meter.scope is None or not meter.scope.schema_version.endswith(".v2"):
            raise ConfigurationError("runtime changes require an exact accounting v2 scope")
        assert meter.repository is not None
        results = []
        completed: dict[str, dict[str, Any]] = {}
        for identity, plan in plans.items():
            key = digest(plan)
            if key in completed:
                results.append({"runtime_id": identity, **completed[key], "shared_operation": True})
                continue
            meter.authorize()
            current, _ = lifecycle_preview(
                definition, configuration, runtime_ids, operation=operation
            )
            if current["review_sha256"] != reviewed_digest or current["blockers"]:
                raise ConfigurationError(
                    "runtime bindings changed; completed effects and costs remain"
                )
            error = None
            try:
                state = (apply if operation == "setup" else remove)(plan, key)
                status: Literal["installed", "removed", "failed"] = (
                    "installed" if operation == "setup" else "removed"
                )
                assert state["status"] == status
            except (OSError, ValueError, ConfigurationError, subprocess.SubprocessError) as failure:
                # Each private installer preserves its own terminal journal.
                # An independent destination remains eligible; no failed plan is retried.
                status, error = "failed", type(failure).__name__
            observation = observe(plan)
            record = RuntimeLifecycleRecord(
                operation_id=meter.operation_id,
                workflow_review=reviewed_digest,
                installation_digest=key,
                runtime_ids=tuple(name for name, value in plans.items() if digest(value) == key),
                operation=operation,
                status=status,
                journal_sha256=observation["journal_sha256"],
                error_type=error,
            )
            ref = meter.repository.put(
                "toolkit_runtime_lifecycle", meter.operation_id + ":" + key, record
            )
            value = {"status": status, "record_ref": ref, "observation": observation}
            completed[key] = value
            results.append({"runtime_id": identity, **value})
        if any(item["status"] == "failed" for item in results):
            meter.outcome_error = "RuntimeLifecycleFailure"
        return {
            "workflow_review": reviewed_digest,
            "operation": operation,
            "results": results,
            "workflow_accounting": meter.describe(),
            "complete": all(item["status"] != "failed" for item in results),
            "functional_readiness": "NOT_VERIFIED",
            "candidate_usefulness": "NOT_ASSESSED",
            "selection_usefulness": "NOT_ASSESSED",
        }
