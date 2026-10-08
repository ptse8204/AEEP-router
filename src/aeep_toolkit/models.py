"""Inert toolkit contracts; provenance references never grant trust or execution."""

from __future__ import annotations

from typing import Annotated, Literal, Protocol
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContractModel(BaseModel):
    """Keep parsing independent of legacy package initialization."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True, allow_inf_nan=False)

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,199}$")]
Count = Annotated[int, Field(strict=True, ge=0)]
Measure = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
Metric = Literal["tokens", "agent_wall_seconds", "verification_wall_seconds", "setup_wall_seconds"]


class SourcePin(ContractModel):
    repository: str = Field(min_length=1, max_length=2048)
    revision: str = Field(pattern=r"^(?:[a-f0-9]{40}|[a-f0-9]{64})$")
    artifact_sha256: Digest
    license_expression: str = Field(min_length=1, max_length=200)
    data_rights: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def public_source(self) -> SourcePin:
        url = urlsplit(self.repository)
        if (url.scheme != "https" or not url.hostname or url.username or url.password
                or url.query or url.fragment):
            raise ValueError("source requires a public HTTPS URL without credentials, query or fragment")
        return self


class ExtensionPermissions(ContractModel):
    network_destinations: tuple[str, ...]
    filesystem_scope: Literal["none", "workspace", "user", "system", "unknown"]
    authentication: Literal["none", "host_owned", "operator_setup", "unknown"]
    financial_exposure: Literal["none", "subscription_unpriced", "metered", "unknown"]


    @model_validator(mode="after")
    def bounded_destinations(self) -> ExtensionPermissions:
        for destination in self.network_destinations:
            url = urlsplit(destination)
            if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in {"", "/"}:
                raise ValueError("network destinations must be HTTPS origins without credentials")
        return self


class ExtensionDependency(ContractModel):
    extension_id: Identifier
    manifest_sha256: Digest


class ExtensionManifest(ContractModel):
    schema_version: Literal["aeep.toolkit.extension.v1"] = "aeep.toolkit.extension.v1"
    extension_id: Identifier
    purpose: str = Field(min_length=1, max_length=1000)
    role: Literal["evaluator", "benchmark", "scanner", "catalog", "observability", "isolation", "router", "orchestrator", "support"]
    source: SourcePin
    hosts: tuple[Identifier, ...] = Field(min_length=1)
    platforms: tuple[Identifier, ...] = Field(min_length=1)
    dependencies: tuple[ExtensionDependency, ...]
    permissions: ExtensionPermissions
    disk_bytes: Count | None
    memory_bytes: Count | None
    install_effects: tuple[str, ...]
    rollback: str = Field(min_length=1, max_length=2000)
    status: Literal["not_installed", "blocked", "experimental", "qualified"]
    qualification_ref: Digest | None = None
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def consistent_status(self) -> ExtensionManifest:
        ids = [d.extension_id for d in self.dependencies]
        if self.extension_id in ids or len(ids) != len(set(ids)):
            raise ValueError("extension dependencies must be unique and cannot include itself")
        if self.status == "blocked" and not self.blockers:
            raise ValueError("blocked extension requires an explanation")
        if self.status == "qualified" and (self.qualification_ref is None or self.blockers):
            raise ValueError("qualified status requires evidence and no blockers")
        return self


class ExtensionRegistry(ContractModel):
    schema_version: Literal["aeep.toolkit.registry.v1"] = "aeep.toolkit.registry.v1"
    extensions: tuple[ExtensionManifest, ...]

    @model_validator(mode="after")
    def unique_extensions(self) -> ExtensionRegistry:
        if len({item.extension_id for item in self.extensions}) != len(self.extensions):
            raise ValueError("duplicate extension identities")
        return self

    def get(self, extension_id: str) -> ExtensionManifest:
        for item in self.extensions:
            if item.extension_id == extension_id:
                return item
        raise KeyError(extension_id)


class AdapterCapabilities(ContractModel):
    schema_version: Literal["aeep.toolkit.adapter.v1"] = "aeep.toolkit.adapter.v1"
    adapter_id: Identifier
    implementation_sha256: Digest
    hosts: tuple[Identifier, ...] = Field(min_length=1)
    candidate_types: tuple[Literal["skill", "mcp", "plugin", "tool"], ...] = Field(min_length=1)
    optional_invocation: bool
    telemetry: tuple[Metric, ...]
    containment: Literal["unverified", "controlled_workers"]
    conformance_ref: Digest | None = None

    @model_validator(mode="after")
    def containment_evidence(self) -> AdapterCapabilities:
        if self.containment == "controlled_workers" and self.conformance_ref is None:
            raise ValueError("controlled worker declaration requires a conformance reference")
        return self


class DeveloperIdentity(ContractModel):
    schema_version: Literal["aeep.toolkit.developer.v1"] = "aeep.toolkit.developer.v1"
    source: SourcePin
    identity: Identifier
    assertion_ref: Digest
    # A resolver must authenticate this assertion before showing a verified identity.
    support_url: str | None = Field(default=None, max_length=2048)
    support_kind: Literal["donation", "purchase"] | None = None

    @model_validator(mode="after")
    def support_link(self) -> DeveloperIdentity:
        if (self.support_url is None) != (self.support_kind is None):
            raise ValueError("support link and kind must be supplied together")
        if self.support_url is not None:
            url = urlsplit(self.support_url)
            if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
                raise ValueError("support URL must be public HTTPS without credentials or query")
        return self


class TokenObservation(ContractModel):
    source_ref: Digest
    input_tokens: Count | None = None
    output_tokens: Count | None = None
    cached_input_tokens: Count | None = None
    reasoning_output_tokens: Count | None = None
    cached_semantics: Literal["included_in_input", "separate", "unknown"]
    reasoning_semantics: Literal["included_in_output", "separate", "unknown"]

    @model_validator(mode="after")
    def subsets(self) -> TokenObservation:
        for part, total, semantics in (
            (self.cached_input_tokens, self.input_tokens, self.cached_semantics),
            (self.reasoning_output_tokens, self.output_tokens, self.reasoning_semantics)):
            if part is not None and semantics == "unknown":
                raise ValueError("reported token subcategories require explicit source semantics")
            if part is not None and total is not None and semantics.startswith("included") and part > total:
                raise ValueError("included token category exceeds its parent")
        return self


class EvaluationRun(ContractModel):
    schema_version: Literal["aeep.toolkit.run.v1"] = "aeep.toolkit.run.v1"
    run_id: Identifier
    plan_ref: Digest
    candidate_sha256: Digest
    adapter_sha256: Digest
    host: Identifier
    host_version: str = Field(min_length=1, max_length=100)
    model: Identifier
    effort: Identifier
    shared_environment_sha256: Digest
    worker_sha256: Digest
    task_sha256: Digest
    task_family: Identifier
    verifier_sha256: Digest
    prompt_sha256: Digest
    arm: Literal["control", "treatment"]
    mode: Literal["optional", "forced_diagnostic"]
    candidate_exposed: bool | None
    candidate_invoked: bool | None
    verification: Literal["pass", "fail", "skipped", "unknown"]
    verification_ref: Digest | None = None
    status: Literal["completed", "failed", "timeout", "indeterminate"]
    retries: Count
    evidence_kind: Literal["synthetic", "replay", "live"]
    receipt_refs: tuple[Digest, ...] = Field(min_length=1)
    tokens: TokenObservation | None = None
    agent_wall_seconds: Measure | None = None
    verification_wall_seconds: Measure | None = None
    setup_wall_seconds: Measure | None = None
    timing_source_ref: Digest | None = None
    cash_accounting_ref: Digest | None = None

    @model_validator(mode="after")
    def observations(self) -> EvaluationRun:
        if self.arm == "control" and (self.candidate_exposed is True or self.candidate_invoked is True):
            raise ValueError("control cannot expose or invoke the candidate")
        if self.candidate_invoked is True and self.candidate_exposed is False:
            raise ValueError("invocation contradicts observed absence")
        if self.verification in {"pass", "fail"} and self.verification_ref is None:
            raise ValueError("verification result requires independent evidence reference")
        if self.verification == "pass" and self.status != "completed":
            raise ValueError("unfinished execution cannot be a verified success")
        if any(v is not None for v in (self.agent_wall_seconds, self.verification_wall_seconds, self.setup_wall_seconds)) and self.timing_source_ref is None:
            raise ValueError("timing observations require provenance")
        return self


class EvidenceBundle(ContractModel):
    schema_version: Literal["aeep.toolkit.evidence.v1"] = "aeep.toolkit.evidence.v1"
    candidate: SourcePin
    adapter: AdapterCapabilities
    runs: tuple[EvaluationRun, ...]

    @model_validator(mode="after")
    def supported_runs(self) -> EvidenceBundle:
        if len({r.run_id for r in self.runs}) != len(self.runs):
            raise ValueError("duplicate runs would double count evidence")
        for run in self.runs:
            if run.candidate_sha256 != self.candidate.artifact_sha256:
                raise ValueError("run candidate does not match pinned subject")
            if run.host not in self.adapter.hosts or run.adapter_sha256 != self.adapter.implementation_sha256:
                raise ValueError("run host or implementation does not match adapter")
            if run.mode == "optional" and not self.adapter.optional_invocation:
                raise ValueError("adapter does not support optional invocation")
            for metric in ("tokens", "agent_wall_seconds", "verification_wall_seconds", "setup_wall_seconds"):
                if getattr(run, metric) is not None and metric not in self.adapter.telemetry:
                    raise ValueError("adapter does not support reported telemetry")
        return self


class ComparisonReport(ContractModel):
    schema_version: Literal["aeep.toolkit.comparison.v1"] = "aeep.toolkit.comparison.v1"
    evidence_bundle_ref: Digest
    plan_ref: Digest
    outcome: Literal["DEMONSTRATED_BENEFIT", "DEMONSTRATED_REGRESSION", "NO_DEMONSTRATED_MATERIAL_DIFFERENCE", "INCONCLUSIVE", "NOT_ASSESSED"]
    evidence_kind: Literal["synthetic", "replay", "live"]
    analysis_ref: Digest | None = None
    limitations: tuple[str, ...]

    @model_validator(mode="after")
    def evidence_for_verdict(self) -> ComparisonReport:
        if self.outcome.startswith("DEMONSTRATED") and (self.evidence_kind != "live" or self.analysis_ref is None):
            raise ValueError("demonstrated verdict requires live analysis evidence")
        return self


class EvaluatorAdapter(Protocol):
    """Implementations resolve existing operator review and authority before execution."""

    capabilities: AdapterCapabilities

    async def evaluate(self, reviewed_plan_id: str) -> EvidenceBundle: ...
