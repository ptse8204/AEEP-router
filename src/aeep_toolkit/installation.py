"""Pure installation preview. No imports, network calls or installer effects."""

from __future__ import annotations

import hashlib
import json
from graphlib import CycleError, TopologicalSorter
from typing import Any, Literal

from pydantic import Field, SerializerFunctionWrapHandler, model_serializer, model_validator

from .models import ContractModel, Count, Digest, ExtensionManifest, ExtensionRegistry, Identifier

PROFILES = {
    "essentials": {"name": "Evaluation Essentials", "roles": ("evaluator", "benchmark", "support", "isolation")},
    "evaluation": {"name": "Evaluation Toolkit", "roles": ("evaluator", "benchmark", "support", "catalog", "scanner", "observability", "isolation")},
    "full": {"name": "Full Toolkit", "roles": ("evaluator", "benchmark", "support", "catalog", "scanner", "observability", "isolation", "router", "orchestrator")},
}
Profile = Literal["essentials", "evaluation", "full"]


def manifest_digest(manifest: ExtensionManifest) -> str:
    # Match assessment.models.content_digest without loading the legacy runtime.
    raw = json.dumps(manifest.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


class InstalledObservation(ContractModel):
    extension_id: Identifier
    installed: bool | None = None
    enabled: bool | None = None
    manifest_sha256: Digest | None = None
    source_ref: Digest | None = None

    @model_validator(mode="after")
    def backed_observation(self) -> InstalledObservation:
        if self.installed is not None and self.source_ref is None:
            raise ValueError("installation observation requires provenance")
        if self.installed is True and self.manifest_sha256 is None:
            raise ValueError("installed observation requires exact manifest identity")
        if self.enabled is not None and self.installed is not True:
            raise ValueError("enabled state requires an installed observation")
        return self


class PreviewPolicy(ContractModel):
    host: Identifier
    platform: Identifier
    allowed_licenses: tuple[str, ...] = ()
    allowed_data_rights: tuple[str, ...] = ()
    allowed_network_destinations: tuple[str, ...] = ()
    allowed_filesystem_scopes: tuple[Literal["none", "workspace", "user", "system"], ...] = ("none",)
    allowed_authentication: tuple[Literal["none", "host_owned", "operator_setup"], ...] = ("none",)
    allowed_financial_exposure: tuple[Literal["none", "subscription_unpriced", "metered"], ...] = ("none",)
    free_disk_bytes: Count | None = None
    allow_unknown_memory: bool = Field(default=False, strict=True)

    @model_serializer(mode='wrap')
    def preserve_existing_reviews(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        value: dict[str, Any] = handler(self)
        if not self.allow_unknown_memory:
            value.pop('allow_unknown_memory', None)
        return value

    # Operator-supplied metadata review, never a grant or execution approval.
    reviewed_dependency_manifests: tuple[Digest, ...] = ()


class PreviewItem(ContractModel):
    manifest: ExtensionManifest
    manifest_sha256: Digest
    selection: Literal["direct", "dependency"]
    observation: InstalledObservation
    blockers: tuple[str, ...]


class InstallationPreview(ContractModel):
    schema_version: Literal["aeep.toolkit.installation-preview.v1"] = "aeep.toolkit.installation-preview.v1"
    profile: Profile
    selected: tuple[Identifier, ...]
    items: tuple[PreviewItem, ...]
    blockers: tuple[str, ...]
    known_disk_bytes: Count
    disk_complete: bool
    status: Literal["blocked", "ready_for_review"]
    execution_authorized: Literal[False] = False
    limitations: tuple[str, ...] = (
        "Metadata and supplied observations are declarations, not authenticated installation or conformance evidence.",
        "Memory figures are per component; simultaneous runtime consumption is unmeasured.",
        "This preview performs no installation and cannot authorize execution or spending.",
    )


def preview(
    registry: ExtensionRegistry,
    selected: tuple[str, ...],
    policy: PreviewPolicy,
    *,
    profile: Profile = "essentials",
    observations: tuple[InstalledObservation, ...] = (),
) -> InstallationPreview:
    """Resolve explicit selection and its dependency closure without touching the host."""
    if profile not in PROFILES:
        raise ValueError("unknown installation profile")
    if len(registry.extensions) > 256:
        raise ValueError("registry exceeds the bounded preview limit")
    if len(selected) != len(set(selected)):
        raise ValueError("duplicate selected extension")
    observed = {item.extension_id: item for item in observations}
    if len(observed) != len(observations):
        raise ValueError("duplicate installation observation")
    manifests = {item.extension_id: item for item in registry.extensions}
    graph: dict[str, set[str]] = {}
    problems: dict[str, list[str]] = {}
    global_problems: list[str] = []
    pending = list(reversed(selected))
    if not selected:
        global_problems.append("Select at least one component explicitly; profiles never select everything.")
    while pending:
        identity = pending.pop()
        if identity in graph:
            continue
        graph[identity] = set()
        problems[identity] = []
        manifest = manifests.get(identity)
        if manifest is None:
            global_problems.append(f"{identity}: exact artifact manifest unavailable")
            continue
        digest = manifest_digest(manifest)
        failures = problems[identity]
        if manifest.role not in PROFILES[profile]["roles"]:
            failures.append("role is outside the selected profile")
        if policy.host not in manifest.hosts or policy.platform not in manifest.platforms:
            failures.append("unsupported host or platform")
        if manifest.source.license_expression not in policy.allowed_licenses:
            failures.append("license not accepted by preview policy")
        if manifest.source.data_rights not in policy.allowed_data_rights:
            failures.append("data rights not accepted by preview policy")
        if digest not in policy.reviewed_dependency_manifests:
            failures.append("complete artifact/dependency inventory has not been reviewed")
        permissions = manifest.permissions
        if not set(permissions.network_destinations) <= set(policy.allowed_network_destinations):
            failures.append("network destination outside preview policy")
        for label, value, allowed in (
            ("filesystem", permissions.filesystem_scope, policy.allowed_filesystem_scopes),
            ("authentication", permissions.authentication, policy.allowed_authentication),
            ("financial exposure", permissions.financial_exposure, policy.allowed_financial_exposure),
        ):
            if value not in allowed:
                failures.append(f"{label} outside preview policy or unknown")
        if manifest.disk_bytes is None:
            failures.append("disk requirement unknown")
        if manifest.memory_bytes is None and not policy.allow_unknown_memory:
            failures.append("memory requirement unknown")
        if manifest.status == "blocked" or manifest.blockers:
            failures.append("extension is blocked: " + "; ".join(manifest.blockers))
        state = observed.get(identity)
        if state and state.installed:
            if state.manifest_sha256 != digest:
                failures.append("installed manifest differs; replacement needs an exact effect review")
            if state.enabled is False:
                failures.append("installed extension is disabled; enabling needs separate review")
        for dependency in manifest.dependencies:
            graph[identity].add(dependency.extension_id)
            child = manifests.get(dependency.extension_id)
            if child is not None and manifest_digest(child) != dependency.manifest_sha256:
                failures.append(f"dependency manifest mismatch: {dependency.extension_id}")
            pending.append(dependency.extension_id)
    try:
        order = list(TopologicalSorter({name: sorted(deps) for name, deps in graph.items()}).static_order())
    except CycleError:
        global_problems.append("dependency cycle; no installation order is valid")
        order = sorted(graph)
    items = tuple(PreviewItem(
        manifest=manifests[identity], manifest_sha256=manifest_digest(manifests[identity]),
        selection="direct" if identity in selected else "dependency",
        observation=observed.get(identity, InstalledObservation(extension_id=identity)),
        blockers=tuple(problems[identity]),
    ) for identity in order if identity in manifests)
    known_disk = sum(item.manifest.disk_bytes or 0 for item in items)
    if policy.free_disk_bytes is None:
        global_problems.append("free disk space unknown")
    elif policy.free_disk_bytes - known_disk < 50 * 1024**3:
        global_problems.append("selected stack would cross the 50 GiB free-space reserve")
    blockers = tuple(global_problems + [f"{item.manifest.extension_id}: {reason}" for item in items for reason in item.blockers])
    result = InstallationPreview(
        profile=profile, selected=selected, items=items, blockers=blockers,
        known_disk_bytes=known_disk,
        disk_complete=all(item.manifest.disk_bytes is not None for item in items) and len(items) == len(graph),
        status="blocked" if blockers else "ready_for_review",
    )
    if policy.allow_unknown_memory and any(item.manifest.memory_bytes is None for item in items):
        result.limitations += ("The operator preview policy accepts unknown memory requirements; actual runtime memory remains unmeasured.",)
    return result


def require_compatible(plan: InstallationPreview) -> None:
    """A precondition for a future reviewed installer, never execution authority."""
    if plan.status != "ready_for_review" or plan.blockers:
        raise ValueError("installation blocked: " + "; ".join(plan.blockers))
