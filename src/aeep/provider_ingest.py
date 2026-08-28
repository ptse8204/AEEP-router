"""Fail-closed provider-package verification and inert candidate ingestion."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import rfc8785
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel

from .artifact_store import ContentArtifactStore, ResolvedArtifact
from .economic.signing import decode_base64url
from .economic.trust import TrustedKeyStatus, TrustStore
from .errors import ConfigurationError
from .models import RateCardSnapshot, TrustedKeyRole, TrustLevel
from .provider_package import (
    ArtifactStatus,
    ArtifactVerificationResult,
    CandidateVerificationSnapshot,
    ComparativeMeasurement,
    EvidenceAcceptance,
    EvidenceAcceptanceStatus,
    EvidenceAuthorityClass,
    EvidenceReference,
    EvidenceType,
    FingerprintStatus,
    PackageIntegrityStatus,
    PackageSignatureStatus,
    PackageVerificationResult,
    ProviderPackage,
    SignatureVerificationResult,
    SmokeStatus,
    load_provider_package,
    package_signature_payload,
    portable_route_fingerprint,
    provider_package_digest,
    verify_evidence_attestation,
)
from .qualification import RouteCandidate, RouteLifecycle, behavior_fingerprint
from .store import ReceiptStore


def _semver(value: str) -> tuple[int, int, int]:
    core = value.split("-", 1)[0].split("+", 1)[0]
    try:
        major, minor, patch = (int(part) for part in core.split("."))
    except (TypeError, ValueError) as exc:
        raise ConfigurationError("provider package compatibility version is invalid") from exc
    return major, minor, patch


def _trust_max(values: list[TrustLevel]) -> TrustLevel:
    if TrustLevel.ATTESTED in values:
        return TrustLevel.ATTESTED
    if TrustLevel.VERIFIED in values:
        return TrustLevel.VERIFIED
    if TrustLevel.SELF_ASSERTED in values:
        return TrustLevel.SELF_ASSERTED
    return TrustLevel.UNTRUSTED


def _verify_signature_bytes(signature: str, payload: bytes, public_key: str) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(decode_base64url(public_key)).verify(
            decode_base64url(signature),
            payload,
        )
    except (InvalidSignature, ValueError):
        return False
    return True


def _artifact_failure(exc: Exception) -> tuple[ArtifactStatus, str]:
    text = str(exc).lower()
    if "digest" in text:
        return ArtifactStatus.DIGEST_MISMATCH, "artifact_digest_mismatch"
    if "size" in text or "limit" in text or "ratio" in text:
        return ArtifactStatus.SIZE_MISMATCH, "artifact_size_mismatch"
    if "does not exist" in text or "not a regular file" in text:
        return ArtifactStatus.MISSING, "artifact_unavailable"
    if "parse" in text or "json" in text or "gzip" in text:
        return ArtifactStatus.PARSE_FAILED, "artifact_parse_failed"
    return ArtifactStatus.BLOCKED, "artifact_blocked"


def _validate_evidence_payload(evidence: EvidenceReference, payload: bytes) -> BaseModel | dict[str, Any]:
    if evidence.evidence_type is EvidenceType.QUALIFICATION_REPORT:
        from .qualification import QualificationReport

        return QualificationReport.model_validate_json(payload)
    if evidence.evidence_type is EvidenceType.BENCHMARK_CAMPAIGN:
        from .benchmarking import BenchmarkCampaignReport

        return BenchmarkCampaignReport.model_validate_json(payload)
    if evidence.evidence_type is EvidenceType.RATE_CARD_SNAPSHOT:
        from .models import RateCardSnapshot

        return RateCardSnapshot.model_validate_json(payload)
    if evidence.evidence_type is EvidenceType.COMPARISON_REPORT:
        return ComparativeMeasurement.model_validate_json(payload)
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ConfigurationError("evidence artifact is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ConfigurationError("evidence artifact must be an object")
    return value


def _summary_matches_artifact(
    evidence: EvidenceReference,
    parsed: BaseModel | dict[str, Any],
) -> bool:
    summary = evidence.summary
    if summary is None:
        return True
    if evidence.evidence_type is EvidenceType.QUALIFICATION_REPORT:
        success = summary.get("success")
        return bool(
            isinstance(success, dict)
            and _integer_summary(success.get("trials")) == getattr(parsed, "dynamic_runs", -1)
            and _integer_summary(success.get("successes"))
            == getattr(parsed, "passed_runs", -1)
        )
    if evidence.evidence_type is EvidenceType.BENCHMARK_CAMPAIGN:
        trials = getattr(parsed, "trials", None)
        if not isinstance(trials, list):
            return False
        success = summary.get("success")
        succeeded = sum(item.ok and item.valid is not False for item in trials)
        return bool(
            _integer_summary(summary.get("sample_size")) == len(trials)
            and isinstance(success, dict)
            and _integer_summary(success.get("trials")) == len(trials)
            and _integer_summary(success.get("successes")) == succeeded
        )
    if evidence.evidence_type is EvidenceType.COMPARISON_REPORT:
        return _integer_summary(summary.get("paired_trials")) == getattr(
            parsed, "paired_trials", -1
        )
    if evidence.evidence_type is EvidenceType.RATE_CARD_SNAPSHOT:
        return summary.get("snapshot_id") == getattr(parsed, "snapshot_id", None)
    return True


def _integer_summary(value: Any) -> int:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else -1


class ProviderPackageIngestor:
    def __init__(
        self,
        store: ReceiptStore,
        artifact_store: ContentArtifactStore,
        trust_store: TrustStore,
        *,
        clock: Any | None = None,
    ) -> None:
        self.store = store
        self.artifact_store = artifact_store
        self.trust_store = trust_store
        self.clock = clock or (lambda: datetime.now(UTC))

    def verify_package(
        self,
        package: ProviderPackage,
        *,
        at: datetime | None = None,
    ) -> PackageVerificationResult:
        now = (at or self.clock()).astimezone(UTC)
        digest = provider_package_digest(package)
        if digest != package.integrity.digest:
            return PackageVerificationResult(
                package_digest=digest,
                integrity_status=PackageIntegrityStatus.FAILED,
                effective_identity_trust=TrustLevel.UNTRUSTED,
                failure_codes=("manifest_digest_mismatch",),
                evaluated_at=now,
            )
        signatures = self._verify_package_signatures(package, now)
        accepted = [
            result
            for result in signatures
            if result.status in {PackageSignatureStatus.VERIFIED, PackageSignatureStatus.UNKNOWN_KEY}
        ]
        return PackageVerificationResult(
            package_digest=digest,
            integrity_status=(
                PackageIntegrityStatus.VERIFIED if accepted else PackageIntegrityStatus.FAILED
            ),
            signatures=tuple(signatures),
            effective_identity_trust=_trust_max(
                [item.effective_trust for item in accepted]
            ),
            failure_codes=(() if accepted else ("signature_invalid",)),
            evaluated_at=now,
        )

    async def ingest(
        self,
        path: str | Path,
        *,
        source_id: str | None = None,
        allow_remote_artifacts: bool = False,
        allowed_artifact_hosts: tuple[str, ...] = (),
        allow_private_networks: bool = False,
        allow_self_asserted_priors: bool = True,
        forbidden_executor_ids: frozenset[str] = frozenset(),
    ) -> tuple[RouteCandidate, ...]:
        package, package_root = load_provider_package(path)
        default_source = f"package-file:{package_root / 'aeep-provider.yaml'}"
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ConfigurationError("provider-package clock must be timezone-aware")
        now = now.astimezone(UTC)
        if not _semver(package.spec.compatibility.aeep_min) <= (0, 6, 0):
            raise ConfigurationError("provider package requires a newer AEEP version")
        if (
            package.spec.compatibility.aeep_max_exclusive is not None
            and _semver(package.spec.compatibility.aeep_max_exclusive) <= (0, 6, 0)
        ):
            raise ConfigurationError("provider package excludes AEEP 0.6")
        if package.metadata.expires_at is not None and now >= package.metadata.expires_at:
            raise ConfigurationError("provider package is expired")

        initial_verification = self.verify_package(package, at=now)
        digest = initial_verification.package_digest
        if initial_verification.integrity_status is not PackageIntegrityStatus.VERIFIED:
            self.store.save_provider_package_audit_event(
                event_id="package_audit_"
                + hashlib.sha256(f"{digest}:verification_failed".encode()).hexdigest()[:32],
                event_type="ingest_rejected",
                occurred_at=now,
                package_digest=digest,
                reason_code=(
                    initial_verification.failure_codes[0]
                    if initial_verification.failure_codes
                    else "signature_invalid"
                ),
            )
            raise ConfigurationError("provider package digest/signature verification failed")
        signature_results = list(initial_verification.signatures)
        accepted_signatures = [
            result
            for result in signature_results
            if result.status in {PackageSignatureStatus.VERIFIED, PackageSignatureStatus.UNKNOWN_KEY}
        ]
        if not accepted_signatures:
            raise ConfigurationError("provider package has no cryptographically valid signature")
        identity_trust = initial_verification.effective_identity_trust

        resolved: dict[str, ResolvedArtifact] = {}
        artifact_results: list[tuple[Any, ArtifactVerificationResult]] = []
        required_artifact_failed = False
        for reference in package.spec.artifacts:
            try:
                if reference.location.path is not None:
                    item = self.artifact_store.resolve_local(
                        reference,
                        package_root=package_root,
                    )
                elif reference.location.uri is not None and allow_remote_artifacts:
                    item = await self.artifact_store.resolve_https(
                        reference,
                        allowed_hosts=allowed_artifact_hosts,
                        allow_private_networks=allow_private_networks,
                    )
                else:
                    raise ConfigurationError("artifact location is disabled by local policy")
                resolved[reference.artifact_id] = item
                result = ArtifactVerificationResult(
                    artifact_id=reference.artifact_id,
                    digest=reference.digest,
                    status=ArtifactStatus.VERIFIED,
                )
            except Exception as exc:
                status, code = _artifact_failure(exc)
                result = ArtifactVerificationResult(
                    artifact_id=reference.artifact_id,
                    digest=reference.digest,
                    status=status,
                    failure_code=code,
                )
                required_artifact_failed |= reference.required
            artifact_results.append((reference, result))

        routes = {route.route_id: route for route in package.spec.routes}
        for route_id in routes:
            existing = self.store.get_route_candidate(route_id)
            if route_id in forbidden_executor_ids and existing is None:
                raise ConfigurationError(
                    f"package route {route_id!r} collides with a trusted manifest route"
                )
            if existing is not None and existing.source_id != (
                source_id or default_source
            ):
                raise ConfigurationError(
                    f"package route {route_id!r} collides with source {existing.source_id!r}"
                )
        fingerprints = {
            route_id: portable_route_fingerprint(route, package.spec.provider.provider_id)
            for route_id, route in routes.items()
        }
        fingerprint_matches = {
            route_id: fingerprints[route_id] == route.declared_fingerprint.value
            for route_id, route in routes.items()
        }

        evidence_records: list[tuple[EvidenceReference, str, str]] = []
        rate_cards: list[RateCardSnapshot] = []
        acceptances: list[EvidenceAcceptance] = []
        accepted_by_route: dict[str, list[EvidenceAcceptance]] = {route_id: [] for route_id in routes}
        for evidence in package.spec.evidence:
            artifact = resolved.get(evidence.artifact_id)
            if artifact is None:
                continue
            route = routes[evidence.subject.route_id]
            subject_matches = (
                evidence.subject.capability == route.capability
                and evidence.subject.route_fingerprint == fingerprints[route.route_id]
                and fingerprint_matches[route.route_id]
            )
            try:
                parsed_evidence = _validate_evidence_payload(evidence, artifact.payload)
                if not _summary_matches_artifact(evidence, parsed_evidence):
                    raise ConfigurationError("evidence summary does not match its artifact")
                if evidence.evidence_type is EvidenceType.RATE_CARD_SNAPSHOT:
                    assert isinstance(parsed_evidence, RateCardSnapshot)
                    rate_cards.append(parsed_evidence)
                if evidence.summary is not None:
                    if evidence.summary_digest is None:
                        raise ConfigurationError("evidence summary requires summary_digest")
                    summary_digest = f"sha256:{hashlib.sha256(rfc8785.dumps(evidence.summary)).hexdigest()}"
                    if summary_digest != evidence.summary_digest:
                        raise ConfigurationError("evidence summary digest is inconsistent")
            except (ConfigurationError, ValueError):
                subject_matches = False
            trust = self._evidence_trust(package, evidence, artifact.reference.digest, now)
            evidence_records.append((evidence, artifact.reference.digest, trust.value))
            metrics = self._evidence_metrics(evidence)
            for metric in metrics:
                acceptance = self._acceptance(
                    package,
                    evidence,
                    metric=metric,
                    trust=trust,
                    subject_matches=subject_matches,
                    allow_self_asserted_priors=allow_self_asserted_priors,
                    evaluated_at=now,
                )
                acceptances.append(acceptance)
                accepted_by_route[route.route_id].append(acceptance)

        verification = PackageVerificationResult(
            package_digest=digest,
            integrity_status=PackageIntegrityStatus.VERIFIED,
            signatures=tuple(signature_results),
            artifacts=tuple(result for _, result in artifact_results),
            effective_identity_trust=identity_trust,
            evaluated_at=now,
        )
        candidates: list[RouteCandidate] = []
        snapshots: list[CandidateVerificationSnapshot] = []
        source = source_id or default_source
        artifact_status = (
            ArtifactStatus.VERIFIED
            if all(result.status is ArtifactStatus.VERIFIED for _, result in artifact_results)
            else ArtifactStatus.BLOCKED
        )
        for route_id, route in routes.items():
            spec = route.executor_spec(package.spec.provider.provider_id)
            route_status = (
                RouteLifecycle.CANDIDATE
                if fingerprint_matches[route_id] and not required_artifact_failed
                else RouteLifecycle.SUSPENDED
            )
            snapshot_id = "verify_" + hashlib.sha256(
                f"{digest}\x1f{route_id}".encode()
            ).hexdigest()[:32]
            route_acceptances = accepted_by_route[route_id]
            evidence_status = (
                EvidenceAcceptanceStatus.ACCEPTED
                if any(item.status is EvidenceAcceptanceStatus.ACCEPTED for item in route_acceptances)
                else EvidenceAcceptanceStatus.ACCEPTED_AS_PRIOR
                if any(
                    item.status is EvidenceAcceptanceStatus.ACCEPTED_AS_PRIOR
                    for item in route_acceptances
                )
                else EvidenceAcceptanceStatus.REJECTED
                if route_acceptances
                else EvidenceAcceptanceStatus.PENDING
            )
            blockers = []
            if not fingerprint_matches[route_id]:
                blockers.append("route_fingerprint_mismatch")
            if required_artifact_failed:
                blockers.append("required_artifact_failed")
            snapshot = CandidateVerificationSnapshot(
                snapshot_id=snapshot_id,
                candidate_id=route_id,
                package_digest=digest,
                route_fingerprint=fingerprints[route_id],
                integrity_status=PackageIntegrityStatus.VERIFIED,
                identity_trust=identity_trust,
                fingerprint_status=(
                    FingerprintStatus.MATCHED
                    if fingerprint_matches[route_id]
                    else FingerprintStatus.MISMATCHED
                ),
                artifact_status=artifact_status,
                evidence_status=evidence_status,
                smoke_status=(
                    SmokeStatus.PENDING
                    if any(item.route_id == route_id for item in package.spec.smoke_tests)
                    else SmokeStatus.NOT_REQUIRED
                ),
                blocking_reasons=tuple(blockers),
                created_at=now,
            )
            candidate = RouteCandidate(
                candidate_id="candidate_" + hashlib.sha256(
                    f"{source}\x1f{route_id}".encode()
                ).hexdigest()[:32],
                executor_id=route_id,
                source_id=source,
                provider_id=package.spec.provider.provider_id,
                capability=route.capability,
                behavior_fingerprint=behavior_fingerprint(spec),
                package_digest=digest,
                package_fingerprint=fingerprints[route_id],
                verification_snapshot_id=snapshot_id,
                status=route_status,
                spec=spec,
                reason=("; ".join(blockers) if blockers else None),
                created_at=now,
                updated_at=now,
            )
            candidates.append(candidate)
            snapshots.append(snapshot)

        self.store.save_provider_package_ingest(
            package,
            verification,
            source_id=source,
            imported_at=now,
            content_artifacts=[
                (item.reference, str(item.cas_path), item.source_kind)
                for item in resolved.values()
            ],
            artifact_results=artifact_results,
            evidence_records=evidence_records,
            acceptances=acceptances,
            candidates=candidates,
            snapshots=snapshots,
        )
        for rate_card in rate_cards:
            self.store.save_rate_card_snapshot(rate_card)
        return tuple(candidates)

    def _verify_package_signatures(
        self,
        package: ProviderPackage,
        now: datetime,
    ) -> list[SignatureVerificationResult]:
        results: list[SignatureVerificationResult] = []
        provider_id = package.spec.provider.provider_id
        payload = package_signature_payload(package.integrity.digest)
        embedded = {key.key_id: key for key in package.spec.provider.keys}
        for signature in package.signatures:
            trusted = self.trust_store.get(provider_id, signature.key_id)
            if trusted is not None:
                status = PackageSignatureStatus.VERIFIED
                failure: str | None = None
                if trusted.status is TrustedKeyStatus.REVOKED:
                    status, failure = PackageSignatureStatus.REVOKED, "signer_revoked"
                elif not trusted.valid_from <= signature.issued_at <= trusted.valid_until:
                    status, failure = PackageSignatureStatus.EXPIRED, "signer_expired"
                elif signature.issued_at > now:
                    status, failure = PackageSignatureStatus.EXPIRED, "signature_future_dated"
                elif not trusted.permits_role(TrustedKeyRole.PACKAGE_PUBLISHER):
                    status, failure = PackageSignatureStatus.WRONG_ROLE, "signer_wrong_role"
                elif (
                    not trusted.permits_package(package.metadata.package_id)
                    or not {route.capability for route in package.spec.routes}.issubset(
                        trusted.allowed_capabilities
                    )
                ):
                    status, failure = PackageSignatureStatus.WRONG_SCOPE, "signer_wrong_scope"
                elif not _verify_signature_bytes(signature.signature, payload, trusted.public_key):
                    status, failure = PackageSignatureStatus.INVALID, "signature_invalid"
                results.append(
                    SignatureVerificationResult(
                        signature_id=signature.signature_id,
                        key_id=signature.key_id,
                        status=status,
                        effective_trust=(
                            trusted.trust
                            if status is PackageSignatureStatus.VERIFIED
                            else TrustLevel.UNTRUSTED
                        ),
                        key_source="operator_trust_store",
                        failure_code=failure,
                    )
                )
                continue
            key = embedded.get(signature.key_id)
            valid = bool(
                key is not None
                and (key.valid_from is None or key.valid_from <= signature.issued_at)
                and (key.valid_until is None or signature.issued_at <= key.valid_until)
                and signature.issued_at <= now
                and _verify_signature_bytes(
                    signature.signature,
                    payload,
                    key.public_key,
                )
            )
            results.append(
                SignatureVerificationResult(
                    signature_id=signature.signature_id,
                    key_id=signature.key_id,
                    status=(
                        PackageSignatureStatus.UNKNOWN_KEY
                        if valid
                        else PackageSignatureStatus.INVALID
                    ),
                    effective_trust=(
                        TrustLevel.SELF_ASSERTED if valid else TrustLevel.UNTRUSTED
                    ),
                    key_source=("embedded" if key is not None else None),
                    failure_code=(None if valid else "signature_invalid"),
                )
            )
        return results

    def _evidence_trust(
        self,
        package: ProviderPackage,
        evidence: EvidenceReference,
        artifact_digest: str,
        now: datetime,
    ) -> TrustLevel:
        accepted: list[TrustLevel] = []
        for attestation in evidence.attestations:
            key = self.trust_store.get(evidence.producer.producer_id, attestation.key_id)
            required_role = (
                TrustedKeyRole.INDEPENDENT_VERIFIER
                if attestation.role == "independent_verifier"
                else TrustedKeyRole.EVIDENCE_PRODUCER
            )
            if (
                key is None
                or key.status is not TrustedKeyStatus.ACTIVE
                or not key.valid_from <= attestation.issued_at <= key.valid_until
                or attestation.issued_at > now
                or not key.permits_role(required_role)
                or not key.permits_capability(evidence.subject.capability)
                or (
                    evidence.validity.not_before is not None
                    and attestation.issued_at < evidence.validity.not_before
                )
                or (
                    evidence.validity.expires_at is not None
                    and attestation.issued_at > evidence.validity.expires_at
                )
            ):
                continue
            if verify_evidence_attestation(
                evidence,
                attestation,
                artifact_digest=artifact_digest,
                public_key=key.public_key,
            ):
                accepted.append(key.trust)
        if accepted:
            return _trust_max(accepted)
        return TrustLevel.SELF_ASSERTED

    @staticmethod
    def _evidence_metrics(evidence: EvidenceReference) -> tuple[str, ...]:
        summary = evidence.summary or {}
        metrics: list[str] = []
        if evidence.evidence_type in {
            EvidenceType.QUALIFICATION_REPORT,
            EvidenceType.COMPATIBILITY_REPORT,
        } or "success" in summary:
            metrics.append("correctness")
        for key in ("tokens", "cost", "latency"):
            if key in summary or evidence.evidence_type is EvidenceType.BENCHMARK_CAMPAIGN:
                metrics.append(key)
        if evidence.evidence_type is EvidenceType.RATE_CARD_SNAPSHOT:
            metrics.append("rate_card")
        return tuple(dict.fromkeys(metrics))

    @staticmethod
    def _acceptance(
        package: ProviderPackage,
        evidence: EvidenceReference,
        *,
        metric: str,
        trust: TrustLevel,
        subject_matches: bool,
        allow_self_asserted_priors: bool,
        evaluated_at: datetime,
    ) -> EvidenceAcceptance:
        expired = (
            evidence.validity.expires_at is not None
            and evaluated_at >= evidence.validity.expires_at
        )
        if expired:
            status = EvidenceAcceptanceStatus.STALE
            reason, confidence = "evidence_expired", Decimal(0)
        elif not subject_matches:
            status = EvidenceAcceptanceStatus.REJECTED
            reason, confidence = "evidence_subject_mismatch", Decimal(0)
        elif trust in {TrustLevel.VERIFIED, TrustLevel.ATTESTED} and (
            package.api_version == "aeep.dev/v0.5"
            or evidence.authority_class is None
            or evidence.cohort is None
        ):
            status = EvidenceAcceptanceStatus.ACCEPTED_AS_PRIOR
            reason, confidence = "legacy_incomplete_evidence_prior", Decimal("0.25")
        elif trust in {TrustLevel.VERIFIED, TrustLevel.ATTESTED} and (
            evidence.authority_class
            in {
                EvidenceAuthorityClass.PROVIDER_SELF_ATTESTED,
                EvidenceAuthorityClass.DISTRIBUTOR_ATTESTED,
            }
        ):
            status = EvidenceAcceptanceStatus.ACCEPTED_AS_PRIOR
            reason = "non_independent_authority_prior"
            confidence = Decimal(
                "0.20"
                if evidence.authority_class
                is EvidenceAuthorityClass.PROVIDER_SELF_ATTESTED
                else "0.25"
            )
        elif trust in {TrustLevel.VERIFIED, TrustLevel.ATTESTED}:
            status = EvidenceAcceptanceStatus.ACCEPTED
            reason = "accepted_exact_subject"
            confidence = Decimal("0.90" if trust is TrustLevel.ATTESTED else "0.85")
            if metric == "latency" and evidence.subject.environment_class != "local-exact":
                status = EvidenceAcceptanceStatus.ACCEPTED_AS_PRIOR
                reason, confidence = "environment_sensitive_prior", Decimal("0.25")
        elif trust is TrustLevel.SELF_ASSERTED and allow_self_asserted_priors:
            status = EvidenceAcceptanceStatus.ACCEPTED_AS_PRIOR
            reason, confidence = "self_asserted_prior", Decimal("0.20")
        else:
            status = EvidenceAcceptanceStatus.REJECTED
            reason, confidence = "evidence_insufficient_trust", Decimal(0)
        acceptance_id = "accept_" + hashlib.sha256(
            f"{package.integrity.digest}\x1f{evidence.evidence_id}\x1f{metric}".encode()
        ).hexdigest()[:32]
        return EvidenceAcceptance(
            acceptance_id=acceptance_id,
            evidence_id=evidence.evidence_id,
            package_digest=package.integrity.digest,
            candidate_id=evidence.subject.route_id,
            metric=metric,
            status=status,
            reason_code=reason,
            applicability=(evidence.subject.environment_class or "unspecified"),
            confidence=confidence,
            effective_trust=trust,
            evaluated_at=evaluated_at,
        )
