"""Strict AEEP provider-package parsing, signing, and fingerprints."""

from __future__ import annotations

import hashlib
import math
import os
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import rfc8785
import yaml
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import ConfigDict, Field, JsonValue, model_validator

from .economic.signing import Ed25519Signer, decode_base64url
from .errors import ConfigurationError
from .models import (
    CapabilityDefinition,
    CurrencyAmount,
    ExecutorKind,
    ExecutorSpec,
    Locality,
    RouteEstimate,
    SideEffect,
    StrictModel,
    TrustedKeyRole,
    TrustLevel,
    ValidationSpec,
)

PROVIDER_PACKAGE_API_VERSION = "aeep.dev/v0.6"
SUPPORTED_PROVIDER_PACKAGE_API_VERSIONS = ("aeep.dev/v0.5", "aeep.dev/v0.6")
PROVIDER_PACKAGE_KIND = "ProviderPackage"
PROVIDER_PACKAGE_CANONICALIZATION = "RFC8785"
PROVIDER_PACKAGE_DIGEST_DOMAIN = b"aeep-provider-package-digest-v1\0"
EVIDENCE_ATTESTATION_DOMAIN = b"aeep-evidence-attestation-v1\0"
ROUTE_FINGERPRINT_DOMAIN = b"aeep-route-v1\0"
PROVIDER_DISCOVERY_DOMAIN = b"aeep-provider-discovery-v1\0"
MAXIMUM_MANIFEST_BYTES = 1_048_576
MAXIMUM_MANIFEST_DEPTH = 32
MAXIMUM_MANIFEST_NODES = 100_000

_IDENTIFIER_PATTERN = r"^[A-Za-z0-9_.:/-]+$"
_CAPABILITY_PATTERN = r"^[a-z0-9][a-z0-9_.-]*@[0-9]+(?:\.[0-9]+){0,2}$"
_DIGEST_PATTERN = r"^sha256:[a-f0-9]{64}$"


class ProviderPackageModel(StrictModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
        allow_inf_nan=False,
        populate_by_name=True,
    )


class EvidenceType(StrEnum):
    QUALIFICATION_REPORT = "qualification_report"
    BENCHMARK_CAMPAIGN = "benchmark_campaign"
    COMPARISON_REPORT = "comparison_report"
    RATE_CARD_SNAPSHOT = "rate_card_snapshot"
    COMPATIBILITY_REPORT = "compatibility_report"
    REVOCATION_STATEMENT = "revocation_statement"


class EvidenceAuthorityClass(StrEnum):
    PROVIDER_SELF_ATTESTED = "provider_self_attested"
    DISTRIBUTOR_ATTESTED = "distributor_attested"
    INDEPENDENT_LAB = "independent_lab"
    ORGANIZATION_ADMIN = "organization_admin"
    LOCAL_OPERATOR = "local_operator"


class ArtifactCompression(StrEnum):
    NONE = "none"
    GZIP = "gzip"


class ArtifactPurpose(StrEnum):
    EXECUTABLE = "executable"
    SCHEMA = "schema"
    QUALIFICATION = "qualification"
    BENCHMARK = "benchmark"
    COMPARISON = "comparison"
    RATE_CARD = "rate_card"
    COMPATIBILITY = "compatibility"
    SMOKE_FIXTURE = "smoke_fixture"
    OTHER = "other"


class PackageIntegrityStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"


class PackageSignatureStatus(StrEnum):
    ABSENT = "absent"
    VERIFIED = "verified"
    INVALID = "invalid"
    UNKNOWN_KEY = "unknown_key"
    REVOKED = "revoked"
    EXPIRED = "expired"
    WRONG_ROLE = "wrong_role"
    WRONG_SCOPE = "wrong_scope"


class FingerprintStatus(StrEnum):
    PENDING = "pending"
    MATCHED = "matched"
    MISMATCHED = "mismatched"
    UNAVAILABLE = "unavailable"


class ArtifactStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    MISSING = "missing"
    DIGEST_MISMATCH = "digest_mismatch"
    SIZE_MISMATCH = "size_mismatch"
    BLOCKED = "blocked"
    PARSE_FAILED = "parse_failed"


class EvidenceAcceptanceStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    ACCEPTED_AS_PRIOR = "accepted_as_prior"
    REJECTED = "rejected"
    STALE = "stale"
    SUPERSEDED = "superseded"


class SmokeStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    EXPIRED = "expired"


class ProviderPackageMetadata(ProviderPackageModel):
    package_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$")
    issued_at: datetime
    expires_at: datetime | None = None
    description: str | None = Field(default=None, max_length=4096)
    labels: dict[str, str] = Field(default_factory=dict, max_length=64)

    @model_validator(mode="after")
    def valid_times(self) -> ProviderPackageMetadata:
        if self.issued_at.tzinfo is None or self.issued_at.utcoffset() is None:
            raise ValueError("package issued_at must be timezone-aware")
        if self.expires_at is not None:
            if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
                raise ValueError("package expires_at must be timezone-aware")
            if self.expires_at <= self.issued_at:
                raise ValueError("package expires_at must be later than issued_at")
        return self


class PublisherIdentity(ProviderPackageModel):
    name: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=500)
    contact: str | None = Field(default=None, max_length=500)


class ProviderPublicKey(ProviderPackageModel):
    key_id: str = Field(min_length=1, max_length=256)
    algorithm: Literal["ed25519"] = "ed25519"
    public_key: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    roles: tuple[TrustedKeyRole, ...] = Field(min_length=1)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    revocation_hint: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def valid_key(self) -> ProviderPublicKey:
        if len(set(self.roles)) != len(self.roles):
            raise ValueError("provider public-key roles must be unique")
        if len(decode_base64url(self.public_key)) != 32:
            raise ValueError("Ed25519 public key must contain exactly 32 bytes")
        for value in (self.valid_from, self.valid_until):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("provider public-key timestamps must be timezone-aware")
        if (
            self.valid_from is not None
            and self.valid_until is not None
            and self.valid_until <= self.valid_from
        ):
            raise ValueError("provider public-key validity window is invalid")
        return self


class ProviderIdentity(ProviderPackageModel):
    provider_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    display_name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4096)
    publisher: PublisherIdentity
    homepage: str | None = Field(default=None, max_length=2048)
    source_repository: str | None = Field(default=None, max_length=2048)
    keys: tuple[ProviderPublicKey, ...] = ()

    @model_validator(mode="after")
    def unique_keys(self) -> ProviderIdentity:
        identities = [key.key_id for key in self.keys]
        if len(identities) != len(set(identities)):
            raise ValueError("provider package contains duplicate key IDs")
        return self


class ProviderCompatibility(ProviderPackageModel):
    aeep_min: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    aeep_max_exclusive: str | None = Field(
        default=None, pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$"
    )
    python: str | None = Field(default=None, max_length=128)
    platforms: tuple[Literal["linux", "macos", "windows", "any"], ...] = ("any",)
    protocols: tuple[str, ...] = ()


class RouteFingerprint(ProviderPackageModel):
    profile: Literal["aeep-route-v1"] = "aeep-route-v1"
    algorithm: Literal["sha256"] = "sha256"
    value: str = Field(pattern=_DIGEST_PATTERN)


class PublishedExecutor(ProviderPackageModel):
    kind: ExecutorKind
    description: str = Field(min_length=1, max_length=4000)
    side_effect: SideEffect = SideEffect.READ
    locality: Locality = Locality.LOCAL
    requires_network: bool = False
    data_residency: tuple[str, ...] = ()
    idempotent: bool = False
    resource_pool: str | None = Field(default=None, max_length=200)
    validators: tuple[ValidationSpec, ...] = ()
    config: dict[str, JsonValue] = Field(default_factory=dict)


class PublishedProviderRoute(ProviderPackageModel):
    route_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    capability: str = Field(pattern=_CAPABILITY_PATTERN)
    input_schema: dict[str, JsonValue]
    output_schema: dict[str, JsonValue] | None = None
    executor: PublishedExecutor
    declared_fingerprint: RouteFingerprint
    artifact_bindings: tuple[str, ...] = ()
    static_estimate: RouteEstimate | None = None
    tags: tuple[str, ...] = ()

    def executor_spec(self, provider_id: str) -> ExecutorSpec:
        config = dict(self.executor.config)
        if self.executor.kind is ExecutorKind.PYTHON:
            config["isolation"] = "subprocess"
            config.setdefault("inherit_env", False)
        argv = config.get("argv")
        if (
            self.executor.kind is ExecutorKind.COMMAND
            and isinstance(argv, list)
            and argv
            and argv[0] == "$PYTHON"
            and str(config.get("executable_identity", "")).startswith("python:")
        ):
            config["argv"] = [sys.executable, *argv[1:]]
        return ExecutorSpec(
            id=self.route_id,
            capability=self.capability,
            kind=self.executor.kind,
            description=self.executor.description,
            input_schema=dict(self.input_schema),
            output_schema=(dict(self.output_schema) if self.output_schema is not None else None),
            estimate=self.static_estimate or RouteEstimate(),
            side_effect=SideEffect.FINANCIAL,
            locality=self.executor.locality,
            requires_network=self.executor.requires_network,
            data_residency=list(self.executor.data_residency),
            idempotent=False,
            safe_to_auto_execute=False,
            enabled=False,
            tags=list(self.tags),
            resource_pool=self.executor.resource_pool,
            provider_id=provider_id,
            validators=list(self.executor.validators),
            config=config,
        )


class ArtifactLocation(ProviderPackageModel):
    path: str | None = Field(default=None, min_length=1, max_length=1024)
    uri: str | None = Field(default=None, min_length=1, max_length=2048)
    oci: str | None = Field(default=None, min_length=1, max_length=2048)

    @model_validator(mode="after")
    def one_location(self) -> ArtifactLocation:
        if sum(value is not None for value in (self.path, self.uri, self.oci)) != 1:
            raise ValueError("artifact location requires exactly one of path, uri, or oci")
        return self


class ArtifactReference(ProviderPackageModel):
    artifact_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    digest: str = Field(pattern=_DIGEST_PATTERN)
    media_type: str = Field(min_length=1, max_length=256)
    size_bytes: int = Field(ge=0, le=52_428_800)
    location: ArtifactLocation
    required: bool = False
    compression: ArtifactCompression = ArtifactCompression.NONE
    purpose: ArtifactPurpose = ArtifactPurpose.OTHER


class EvidenceSubject(ProviderPackageModel):
    route_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    capability: str = Field(pattern=_CAPABILITY_PATTERN)
    route_fingerprint: str = Field(pattern=_DIGEST_PATTERN)
    workload_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    executor_artifact_digests: tuple[str, ...] = ()
    model_identity: str | None = Field(default=None, max_length=500)
    protocol_identity: str | None = Field(default=None, max_length=500)
    environment_class: str | None = Field(default=None, max_length=200)


class EvidenceCohortDeclaration(ProviderPackageModel):
    profile: Literal["aeep-evidence-cohort-v1"] = "aeep-evidence-cohort-v1"
    provider_version: str | None = Field(default=None, max_length=200)
    model_version: str | None = Field(default=None, max_length=200)
    region: str | None = Field(default=None, max_length=100)
    account_tier: str | None = Field(default=None, max_length=100)
    adapter_type: str = Field(min_length=1, max_length=100)
    adapter_version: str | None = Field(default=None, max_length=100)
    action_feature_profile: str = Field(min_length=1, max_length=200)
    validator_digest: str = Field(pattern=_DIGEST_PATTERN)
    cache_namespace: str | None = Field(default=None, max_length=200)
    period_start: datetime
    period_end: datetime
    economic_evidence_level: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def valid_period(self) -> EvidenceCohortDeclaration:
        if any(
            value.tzinfo is None or value.utcoffset() is None
            for value in (self.period_start, self.period_end)
        ):
            raise ValueError("evidence cohort period must be timezone-aware")
        if self.period_end <= self.period_start:
            raise ValueError("evidence cohort period_end must follow period_start")
        return self


class EvidenceProducer(ProviderPackageModel):
    producer_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    role: TrustedKeyRole
    key_id: str | None = Field(default=None, min_length=1, max_length=256)


class EvidenceValidity(ProviderPackageModel):
    issued_at: datetime
    not_before: datetime | None = None
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def valid_window(self) -> EvidenceValidity:
        values = (self.issued_at, self.not_before, self.expires_at)
        if any(
            value is not None and (value.tzinfo is None or value.utcoffset() is None)
            for value in values
        ):
            raise ValueError("evidence timestamps must be timezone-aware")
        if (
            self.not_before is not None
            and self.expires_at is not None
            and self.expires_at <= self.not_before
        ):
            raise ValueError("evidence expiry must follow not_before")
        return self


class EvidenceAttestation(ProviderPackageModel):
    attestation_id: str = Field(min_length=1, max_length=256)
    algorithm: Literal["ed25519"] = "ed25519"
    key_id: str = Field(min_length=1, max_length=256)
    role: Literal["evidence_producer", "independent_verifier"]
    payload_type: Literal[
        "application/vnd.aeep.evidence-attestation+json;version=1"
    ] = "application/vnd.aeep.evidence-attestation+json;version=1"
    digest: str = Field(pattern=_DIGEST_PATTERN)
    signature: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    issued_at: datetime

    @model_validator(mode="after")
    def aware_time(self) -> EvidenceAttestation:
        if self.issued_at.tzinfo is None or self.issued_at.utcoffset() is None:
            raise ValueError("evidence attestation issued_at must be timezone-aware")
        return self


class EvidenceReference(ProviderPackageModel):
    evidence_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    evidence_type: EvidenceType
    artifact_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    subject: EvidenceSubject
    producer: EvidenceProducer
    authority_class: EvidenceAuthorityClass | None = None
    cohort: EvidenceCohortDeclaration | None = None
    trust_claim: TrustLevel = TrustLevel.UNTRUSTED
    validity: EvidenceValidity
    summary: dict[str, JsonValue] | None = None
    summary_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    attestations: tuple[EvidenceAttestation, ...] = ()

    @model_validator(mode="after")
    def valid_attestations(self) -> EvidenceReference:
        ids = [item.attestation_id for item in self.attestations]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence attestations must have unique IDs")
        if self.summary is not None and self.summary_digest is None:
            raise ValueError("evidence summary requires summary_digest")
        return self


class SmokeTestDefinition(ProviderPackageModel):
    smoke_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    route_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    mode: Literal["cold", "warm", "cold_then_warm"] = "cold"
    safety: Literal["read_only", "dry_run", "sandbox"] = "read_only"
    input: dict[str, JsonValue]
    expected: dict[str, JsonValue] = Field(default_factory=dict)
    timeout_ms: int = Field(ge=1, le=300_000)
    max_executions: int = Field(default=1, ge=1, le=2)
    max_cash: CurrencyAmount | None = None
    max_tokens: int | None = Field(default=None, ge=0)


class ProviderPackageSpec(ProviderPackageModel):
    provider: ProviderIdentity
    compatibility: ProviderCompatibility
    capabilities: tuple[CapabilityDefinition, ...] = Field(min_length=1, max_length=256)
    routes: tuple[PublishedProviderRoute, ...] = Field(min_length=1, max_length=1024)
    artifacts: tuple[ArtifactReference, ...] = Field(default=(), max_length=2048)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=2048)
    smoke_tests: tuple[SmokeTestDefinition, ...] = Field(default=(), max_length=512)
    extensions: dict[str, JsonValue] = Field(default_factory=dict, max_length=64)

    @model_validator(mode="after")
    def valid_references(self) -> ProviderPackageSpec:
        for values, label in (
            ([route.route_id for route in self.routes], "route"),
            ([artifact.artifact_id for artifact in self.artifacts], "artifact"),
            ([item.evidence_id for item in self.evidence], "evidence"),
            ([item.smoke_id for item in self.smoke_tests], "smoke test"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"provider package contains duplicate {label} IDs")
        route_ids = {route.route_id for route in self.routes}
        capabilities = {capability.capability: capability for capability in self.capabilities}
        artifact_ids = {artifact.artifact_id for artifact in self.artifacts}
        for route in self.routes:
            definition = capabilities.get(route.capability)
            if definition is None:
                raise ValueError(f"route {route.route_id!r} references an unknown capability")
            if (
                definition.input_schema != route.input_schema
                or definition.output_schema != route.output_schema
            ):
                raise ValueError(
                    f"route {route.route_id!r} schemas do not match its capability contract"
                )
            if not set(route.artifact_bindings) <= artifact_ids:
                raise ValueError(f"route {route.route_id!r} references an unknown artifact")
        for item in self.evidence:
            if item.subject.route_id not in route_ids or item.artifact_id not in artifact_ids:
                raise ValueError(f"evidence {item.evidence_id!r} has an unknown subject/artifact")
        if any(item.route_id not in route_ids for item in self.smoke_tests):
            raise ValueError("smoke test references an unknown route")
        if any(not key.startswith("x-") for key in self.extensions):
            raise ValueError("provider package extension keys must begin with x-")
        return self


class ProviderPackageIntegrity(ProviderPackageModel):
    canonicalization: Literal["RFC8785"] = "RFC8785"
    digest_algorithm: Literal["sha256"] = "sha256"
    payload_scope: Literal[
        "apiVersion+kind+metadata+spec"
    ] = "apiVersion+kind+metadata+spec"
    digest: str = Field(pattern=_DIGEST_PATTERN)


class ProviderPackageSignature(ProviderPackageModel):
    signature_id: str = Field(min_length=1, max_length=256)
    algorithm: Literal["ed25519"] = "ed25519"
    key_id: str = Field(min_length=1, max_length=256)
    role: Literal["package_publisher"] = "package_publisher"
    payload_type: Literal[
        "application/vnd.aeep.provider-package-digest+json;version=1"
    ] = "application/vnd.aeep.provider-package-digest+json;version=1"
    digest: str = Field(pattern=_DIGEST_PATTERN)
    signature: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    issued_at: datetime

    @model_validator(mode="after")
    def aware_time(self) -> ProviderPackageSignature:
        if self.issued_at.tzinfo is None or self.issued_at.utcoffset() is None:
            raise ValueError("package signature issued_at must be timezone-aware")
        return self


class ProviderPackage(ProviderPackageModel):
    api_version: Literal["aeep.dev/v0.5", "aeep.dev/v0.6"] = Field(
        default="aeep.dev/v0.6", alias="apiVersion"
    )
    kind: Literal["ProviderPackage"] = "ProviderPackage"
    metadata: ProviderPackageMetadata
    spec: ProviderPackageSpec
    integrity: ProviderPackageIntegrity
    signatures: tuple[ProviderPackageSignature, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def valid_package(self) -> ProviderPackage:
        signatures = [item.signature_id for item in self.signatures]
        if len(signatures) != len(set(signatures)):
            raise ValueError("provider package contains duplicate signature IDs")
        if any(item.digest != self.integrity.digest for item in self.signatures):
            raise ValueError("provider package signature digest does not match integrity digest")
        if any(item.issued_at < self.metadata.issued_at for item in self.signatures):
            raise ValueError("provider package cannot be signed before it is issued")
        if self.api_version == "aeep.dev/v0.6" and any(
            item.authority_class is None or item.cohort is None
            for item in self.spec.evidence
        ):
            raise ValueError("v0.6 evidence requires authority_class and cohort")
        return self


class SignatureVerificationResult(ProviderPackageModel):
    signature_id: str
    key_id: str
    status: PackageSignatureStatus
    effective_trust: TrustLevel
    key_source: str | None = None
    failure_code: str | None = None


class ArtifactVerificationResult(ProviderPackageModel):
    artifact_id: str
    digest: str
    status: ArtifactStatus
    failure_code: str | None = None


class PackageVerificationResult(ProviderPackageModel):
    package_digest: str = Field(pattern=_DIGEST_PATTERN)
    integrity_status: PackageIntegrityStatus
    signatures: tuple[SignatureVerificationResult, ...] = ()
    artifacts: tuple[ArtifactVerificationResult, ...] = ()
    effective_identity_trust: TrustLevel = TrustLevel.UNTRUSTED
    failure_codes: tuple[str, ...] = ()
    evaluated_at: datetime


class EvidenceAcceptance(ProviderPackageModel):
    acceptance_id: str
    evidence_id: str
    package_digest: str = Field(pattern=_DIGEST_PATTERN)
    candidate_id: str
    metric: str
    status: EvidenceAcceptanceStatus
    reason_code: str
    applicability: str
    confidence: Decimal = Field(ge=0, le=1)
    effective_trust: TrustLevel
    evaluated_at: datetime
    rate_card_snapshot_id: str | None = None


class CandidateVerificationSnapshot(ProviderPackageModel):
    snapshot_id: str
    candidate_id: str
    package_digest: str = Field(pattern=_DIGEST_PATTERN)
    route_fingerprint: str = Field(pattern=_DIGEST_PATTERN)
    integrity_status: PackageIntegrityStatus
    identity_trust: TrustLevel
    fingerprint_status: FingerprintStatus
    artifact_status: ArtifactStatus
    evidence_status: EvidenceAcceptanceStatus
    smoke_status: SmokeStatus
    blocking_reasons: tuple[str, ...] = ()
    created_at: datetime


class SmokeTestReport(ProviderPackageModel):
    smoke_report_id: str
    candidate_id: str
    route_fingerprint: str = Field(pattern=_DIGEST_PATTERN)
    smoke_definition_id: str
    environment_digest: str = Field(pattern=_DIGEST_PATTERN)
    mode: Literal["cold", "warm"]
    status: SmokeStatus
    started_at: datetime
    finished_at: datetime
    execution_receipt_id: str | None = None
    failure_code: str | None = None


class ComparativeMeasurement(ProviderPackageModel):
    comparison_id: str
    workload_digest: str = Field(pattern=_DIGEST_PATTERN)
    candidate_route_id: str
    candidate_fingerprint: str = Field(pattern=_DIGEST_PATTERN)
    baseline_route_id: str
    baseline_fingerprint: str = Field(pattern=_DIGEST_PATTERN)
    paired_trials: int = Field(ge=1)
    candidate_tokens: dict[str, int]
    baseline_tokens: dict[str, int]
    candidate_actual_cash: CurrencyAmount | None = None
    baseline_actual_cash: CurrencyAmount | None = None
    candidate_api_equivalent: CurrencyAmount | None = None
    baseline_api_equivalent: CurrencyAmount | None = None
    rate_card_snapshot_id: str | None = None
    candidate_latency_ms: Decimal | None = Field(default=None, ge=0)
    baseline_latency_ms: Decimal | None = Field(default=None, ge=0)


class ProviderDiscoverySignature(ProviderPackageModel):
    algorithm: Literal["ed25519"] = "ed25519"
    key_id: str = Field(min_length=1, max_length=256)
    digest: str = Field(pattern=_DIGEST_PATTERN)
    signature: str = Field(pattern=r"^[A-Za-z0-9_-]+$")


class ProviderDiscoveryDocument(ProviderPackageModel):
    api_version: Literal["aeep.dev/v0.6"] = Field(
        default="aeep.dev/v0.6", alias="apiVersion"
    )
    kind: Literal["ProviderDiscovery"] = "ProviderDiscovery"
    provider_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    organization: str = Field(min_length=1, max_length=500)
    protocol_versions: tuple[str, ...] = Field(min_length=1, max_length=16)
    endpoints: dict[str, str] = Field(default_factory=dict, max_length=16)
    capabilities: tuple[str, ...] = Field(max_length=1024)
    executor_fingerprints: dict[str, str] = Field(default_factory=dict, max_length=1024)
    signing_keys: tuple[ProviderPublicKey, ...] = Field(min_length=1, max_length=32)
    auth_schemes: tuple[str, ...] = ()
    artifact_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    sbom_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    conformance_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    valid_from: datetime
    valid_until: datetime
    integrity_digest: str = Field(pattern=_DIGEST_PATTERN)
    signature: ProviderDiscoverySignature | None = None

    @model_validator(mode="after")
    def valid_discovery(self) -> ProviderDiscoveryDocument:
        if any(
            value.tzinfo is None or value.utcoffset() is None
            for value in (self.valid_from, self.valid_until)
        ):
            raise ValueError("provider discovery timestamps must be timezone-aware")
        if self.valid_until <= self.valid_from:
            raise ValueError("provider discovery validity window is invalid")
        if any(not key or not value for key, value in self.endpoints.items()):
            raise ValueError("provider discovery endpoints must be named URLs")
        if any(not _valid_discovery_endpoint(value) for value in self.endpoints.values()):
            raise ValueError("provider discovery endpoints require HTTPS or loopback HTTP")
        if any(not re.fullmatch(_DIGEST_PATTERN, value)
               for value in self.executor_fingerprints.values()):
            raise ValueError("provider discovery executor fingerprints are invalid")
        return self


def _valid_discovery_endpoint(value: str) -> bool:
    try:
        parsed = urlparse(value)
        _ = parsed.port
    except ValueError:
        return False
    return bool(
        parsed.hostname
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
        and (
            parsed.scheme == "https"
            or (parsed.scheme == "http" and parsed.hostname == "127.0.0.1")
        )
    )


class _StrictLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: _StrictLoader, node: yaml.MappingNode, deep: bool = False) -> Any:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise ConfigurationError("provider package YAML keys must be strings")
        if key in mapping:
            raise ConfigurationError(f"provider package YAML contains duplicate key {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _count_nodes(value: Any, *, depth: int = 0) -> int:
    if depth > MAXIMUM_MANIFEST_DEPTH:
        raise ConfigurationError("provider package exceeds maximum nesting depth")
    if value is None or isinstance(value, bool | int | float | str):
        if isinstance(value, float) and not math.isfinite(value):
            raise ConfigurationError("provider package contains a non-finite number")
        return 1
    if isinstance(value, Mapping):
        return 1 + sum(_count_nodes(item, depth=depth + 1) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | str):
        return 1 + sum(_count_nodes(item, depth=depth + 1) for item in value)
    raise ConfigurationError(
        f"provider package contains non-JSON value {type(value).__name__}"
    )


def parse_provider_package_bytes(payload: bytes) -> ProviderPackage:
    if len(payload) > MAXIMUM_MANIFEST_BYTES:
        raise ConfigurationError("provider package manifest exceeds 1 MiB")
    try:
        tokens = tuple(yaml.scan(payload.decode("utf-8")))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ConfigurationError("provider package manifest is not valid UTF-8 YAML") from exc
    if any(isinstance(token, yaml.tokens.AnchorToken | yaml.tokens.AliasToken) for token in tokens):
        raise ConfigurationError("provider package YAML anchors and aliases are not supported")
    try:
        value = yaml.load(payload, Loader=_StrictLoader)
    except (yaml.YAMLError, ConfigurationError) as exc:
        raise ConfigurationError(f"provider package manifest parse failed: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigurationError("provider package manifest must be an object")
    if _count_nodes(value) > MAXIMUM_MANIFEST_NODES:
        raise ConfigurationError("provider package exceeds maximum parsed node count")
    try:
        return ProviderPackage.model_validate(value)
    except ValueError as exc:
        raise ConfigurationError("provider package schema validation failed") from exc


def resolve_provider_package_path(path: str | Path) -> Path:
    source = Path(path).expanduser()
    manifest = source / "aeep-provider.yaml" if source.is_dir() else source
    if manifest.name != "aeep-provider.yaml":
        raise ConfigurationError("provider package manifest must be named aeep-provider.yaml")
    if not manifest.is_file():
        raise ConfigurationError("provider package manifest does not exist")
    return manifest.resolve()


def load_provider_package(path: str | Path) -> tuple[ProviderPackage, Path]:
    manifest = resolve_provider_package_path(path)
    try:
        payload = manifest.read_bytes()
    except OSError as exc:
        raise ConfigurationError("cannot read provider package manifest") from exc
    return parse_provider_package_bytes(payload), manifest.parent


def write_provider_package(package: ProviderPackage, path: str | Path) -> None:
    destination = resolve_provider_package_path(path)
    payload = yaml.safe_dump(
        package.model_dump(mode="json", by_alias=True),
        sort_keys=False,
        allow_unicode=True,
    )
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        dir=destination.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def provider_package_payload(package: ProviderPackage) -> bytes:
    value = package.model_dump(
        mode="json",
        by_alias=True,
        include={"api_version", "kind", "metadata", "spec"},
    )
    # v0.5 signatures predate additive runtime uncertainty fields.
    if package.api_version == "aeep.dev/v0.5":
        for route in value["spec"]["routes"]:
            estimate = route.get("static_estimate")
            if isinstance(estimate, dict):
                estimate.pop("uncertainty", None)
        for evidence in value["spec"]["evidence"]:
            evidence.pop("authority_class", None)
            evidence.pop("cohort", None)
    try:
        return rfc8785.dumps(value)
    except rfc8785.CanonicalizationError as exc:
        raise ConfigurationError(f"provider package canonicalization failed: {exc}") from exc


def provider_package_digest(package: ProviderPackage) -> str:
    return f"sha256:{hashlib.sha256(provider_package_payload(package)).hexdigest()}"


def package_signature_payload(digest: str) -> bytes:
    if re.fullmatch(_DIGEST_PATTERN, digest) is None:
        raise ConfigurationError("provider package digest is invalid")
    return PROVIDER_PACKAGE_DIGEST_DOMAIN + bytes.fromhex(digest.removeprefix("sha256:"))


def evidence_attestation_digest(
    evidence: EvidenceReference,
    *,
    artifact_digest: str,
) -> str:
    payload = {
        "evidence_id": evidence.evidence_id,
        "artifact_digest": artifact_digest,
        "subject": evidence.subject.model_dump(mode="json"),
        "summary_digest": evidence.summary_digest,
        "producer": evidence.producer.model_dump(mode="json"),
        "validity": evidence.validity.model_dump(mode="json"),
    }
    try:
        canonical = rfc8785.dumps(payload)
    except rfc8785.CanonicalizationError as exc:
        raise ConfigurationError(f"evidence attestation canonicalization failed: {exc}") from exc
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def evidence_attestation_payload(digest: str) -> bytes:
    if re.fullmatch(_DIGEST_PATTERN, digest) is None:
        raise ConfigurationError("evidence attestation digest is invalid")
    return EVIDENCE_ATTESTATION_DOMAIN + bytes.fromhex(digest.removeprefix("sha256:"))


def verify_evidence_attestation(
    evidence: EvidenceReference,
    attestation: EvidenceAttestation,
    *,
    artifact_digest: str,
    public_key: str,
) -> bool:
    digest = evidence_attestation_digest(evidence, artifact_digest=artifact_digest)
    if attestation.digest != digest:
        return False
    try:
        Ed25519PublicKey.from_public_bytes(decode_base64url(public_key)).verify(
            decode_base64url(attestation.signature),
            evidence_attestation_payload(digest),
        )
    except (InvalidSignature, ValueError):
        return False
    return True


def sign_evidence_attestation(
    evidence: EvidenceReference,
    *,
    artifact_digest: str,
    signer: Ed25519Signer,
    attestation_id: str,
    role: Literal["evidence_producer", "independent_verifier"],
    issued_at: datetime | None = None,
) -> EvidenceReference:
    digest = evidence_attestation_digest(evidence, artifact_digest=artifact_digest)
    envelope = signer.sign(evidence_attestation_payload(digest))
    attestation = EvidenceAttestation(
        attestation_id=attestation_id,
        key_id=envelope.key_id,
        role=role,
        digest=digest,
        signature=envelope.value,
        issued_at=issued_at or datetime.now(UTC),
    )
    return evidence.model_copy(update={"attestations": (*evidence.attestations, attestation)})


def sign_provider_package(
    package: ProviderPackage,
    signer: Ed25519Signer,
    *,
    signature_id: str,
    issued_at: datetime | None = None,
) -> ProviderPackage:
    digest = provider_package_digest(package)
    envelope = signer.sign(package_signature_payload(digest))
    signature = ProviderPackageSignature(
        signature_id=signature_id,
        key_id=envelope.key_id,
        digest=digest,
        signature=envelope.value,
        issued_at=(issued_at or datetime.now(UTC)),
    )
    signatures = tuple(
        item for item in package.signatures if item.signature_id != signature_id
    )
    return ProviderPackage.model_validate(
        {
            **package.model_dump(mode="python", by_alias=True),
            "integrity": ProviderPackageIntegrity(digest=digest),
            "signatures": (*signatures, signature),
        }
    )


def provider_discovery_payload(document: ProviderDiscoveryDocument) -> bytes:
    value = document.model_dump(
        mode="json",
        by_alias=True,
        exclude={"integrity_digest", "signature"},
    )
    try:
        return rfc8785.dumps(value)
    except rfc8785.CanonicalizationError as exc:
        raise ConfigurationError(f"provider discovery canonicalization failed: {exc}") from exc


def provider_discovery_digest(document: ProviderDiscoveryDocument) -> str:
    return f"sha256:{hashlib.sha256(provider_discovery_payload(document)).hexdigest()}"


def sign_provider_discovery(
    document: ProviderDiscoveryDocument,
    signer: Ed25519Signer,
) -> ProviderDiscoveryDocument:
    digest = provider_discovery_digest(document)
    envelope = signer.sign(
        PROVIDER_DISCOVERY_DOMAIN + bytes.fromhex(digest.removeprefix("sha256:"))
    )
    return document.model_copy(
        update={
            "integrity_digest": digest,
            "signature": ProviderDiscoverySignature(
                key_id=envelope.key_id,
                digest=digest,
                signature=envelope.value,
            ),
        }
    )


def verify_provider_discovery(
    document: ProviderDiscoveryDocument,
    public_key: str,
) -> bool:
    signature = document.signature
    digest = provider_discovery_digest(document)
    if signature is None or signature.digest != digest or document.integrity_digest != digest:
        return False
    declared = next(
        (key for key in document.signing_keys if key.key_id == signature.key_id),
        None,
    )
    if declared is None or declared.public_key != public_key:
        return False
    try:
        Ed25519PublicKey.from_public_bytes(decode_base64url(public_key)).verify(
            decode_base64url(signature.signature),
            PROVIDER_DISCOVERY_DOMAIN + bytes.fromhex(digest.removeprefix("sha256:")),
        )
    except (InvalidSignature, ValueError):
        return False
    return True


def verify_embedded_package_signature(
    package: ProviderPackage,
    signature: ProviderPackageSignature,
) -> bool:
    key = next((item for item in package.spec.provider.keys if item.key_id == signature.key_id), None)
    if key is None or TrustedKeyRole.PACKAGE_PUBLISHER not in key.roles:
        return False
    if signature.digest != provider_package_digest(package):
        return False
    try:
        public_key = Ed25519PublicKey.from_public_bytes(decode_base64url(key.public_key))
        public_key.verify(
            decode_base64url(signature.signature),
            package_signature_payload(signature.digest),
        )
    except (InvalidSignature, ValueError):
        return False
    return True


def portable_route_fingerprint(route: PublishedProviderRoute, provider_id: str) -> str:
    config = dict(route.executor.config)
    if route.executor.kind is ExecutorKind.COMMAND:
        argv = config.get("argv")
        executable_identity = config.get("executable_identity")
        if not isinstance(argv, list) or not argv or not isinstance(executable_identity, str):
            raise ConfigurationError(
                "package command routes require argv and executable_identity"
            )
        config["argv"] = ["$EXECUTABLE", *argv[1:]]
    payload = {
        "profile": "aeep-route-v1",
        "route_id": route.route_id,
        "provider_id": provider_id,
        "capability": route.capability,
        "input_schema": route.input_schema,
        "output_schema": route.output_schema,
        "kind": route.executor.kind.value,
        "side_effect": route.executor.side_effect.value,
        "idempotent": route.executor.idempotent,
        "locality": route.executor.locality.value,
        "requires_network": route.executor.requires_network,
        "data_residency": sorted(route.executor.data_residency),
        "validators": [item.model_dump(mode="json") for item in route.executor.validators],
        "resource_pool": route.executor.resource_pool,
        "config": config,
        "artifact_bindings": sorted(route.artifact_bindings),
    }
    try:
        canonical = rfc8785.dumps(payload)
    except rfc8785.CanonicalizationError as exc:
        raise ConfigurationError(f"route fingerprint canonicalization failed: {exc}") from exc
    return f"sha256:{hashlib.sha256(ROUTE_FINGERPRINT_DOMAIN + canonical).hexdigest()}"


def runtime_route_identity_matches(
    route: PublishedProviderRoute,
    spec: ExecutorSpec,
) -> bool:
    if route.executor.kind is not spec.kind:
        return False
    if spec.kind is not ExecutorKind.COMMAND:
        return True
    argv = spec.config.get("argv")
    identity = route.executor.config.get("executable_identity")
    if not isinstance(argv, list) or not argv or not isinstance(argv[0], str):
        return False
    executable = Path(argv[0])
    if not executable.is_absolute() or not executable.is_file():
        return False
    if isinstance(identity, str) and identity.startswith("sha256:"):
        try:
            digest = hashlib.sha256()
            with executable.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            return f"sha256:{digest.hexdigest()}" == identity
        except OSError:
            return False
    if isinstance(identity, str) and identity.startswith("python:"):
        try:
            same_runtime = executable.samefile(sys.executable)
        except OSError:
            return False
        module = identity.rpartition(":")[2]
        return same_runtime and (
            module == "runtime" or ("-m" in argv and module in argv)
        )
    return False


def validate_declared_fingerprints(package: ProviderPackage) -> dict[str, bool]:
    return {
        route.route_id: portable_route_fingerprint(route, package.spec.provider.provider_id)
        == route.declared_fingerprint.value
        for route in package.spec.routes
    }
