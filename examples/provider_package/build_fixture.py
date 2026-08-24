"""Regenerate the deterministic AEEP v0.5 provider-package fixture."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import rfc8785
import yaml

from aeep.benchmarking import (
    BenchmarkCampaignReport,
    BenchmarkCondition,
    BenchmarkPhase,
    BenchmarkTrial,
)
from aeep.economic.signing import Ed25519Signer
from aeep.economic.trust import TrustedProviderKey, TrustStore
from aeep.models import (
    CapabilityDefinition,
    EstimateSource,
    ExecutionStatus,
    ExecutorKind,
    Locality,
    RateCardRate,
    RateCardSnapshot,
    RateType,
    ResourceVector,
    RouteEstimate,
    SideEffect,
    TrustedKeyRole,
    TrustLevel,
)
from aeep.provider_package import (
    ArtifactLocation,
    ArtifactPurpose,
    ArtifactReference,
    ComparativeMeasurement,
    EvidenceProducer,
    EvidenceReference,
    EvidenceSubject,
    EvidenceType,
    EvidenceValidity,
    ProviderCompatibility,
    ProviderIdentity,
    ProviderPackage,
    ProviderPackageIntegrity,
    ProviderPackageMetadata,
    ProviderPackageSpec,
    ProviderPublicKey,
    PublishedExecutor,
    PublishedProviderRoute,
    PublisherIdentity,
    RouteFingerprint,
    SmokeTestDefinition,
    portable_route_fingerprint,
    sign_evidence_attestation,
    sign_provider_package,
)
from aeep.qualification import QualificationReport

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
NOW = datetime(2026, 8, 21, tzinfo=UTC)
CAPABILITY = "text.statistics@1"


def write_json(name: str, value: object) -> tuple[bytes, Path]:
    path = EVIDENCE / name
    payload = (
        value.model_dump_json(indent=2).encode() + b"\n"
        if hasattr(value, "model_dump_json")
        else b""
    )
    path.write_bytes(payload)
    return payload, path


def summary_digest(summary: dict[str, object]) -> str:
    return f"sha256:{hashlib.sha256(rfc8785.dumps(summary)).hexdigest()}"


def main() -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    publisher = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="fixture-publisher")
    verifier = Ed25519Signer.from_private_bytes(bytes(reversed(range(32))), key_id="fixture-verifier")
    capability = CapabilityDefinition(
        namespace="text",
        name="statistics",
        version="1",
        description="Return deterministic character, word, and line counts.",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "characters": {"type": "integer"},
                "words": {"type": "integer"},
                "lines": {"type": "integer"},
            },
            "required": ["characters", "words", "lines"],
            "additionalProperties": False,
        },
        side_effect=SideEffect.NONE,
    )
    route = PublishedProviderRoute(
        route_id="fixture.command.text-statistics",
        capability=CAPABILITY,
        input_schema=capability.input_schema,
        output_schema=capability.output_schema,
        executor=PublishedExecutor(
            kind=ExecutorKind.COMMAND,
            description="Packaged deterministic text statistics command.",
            side_effect=SideEffect.NONE,
            locality=Locality.LOCAL,
            idempotent=True,
            config={
                "argv": [
                    "$PYTHON",
                    "-m",
                    "aeep.examples.text_stats_cli",
                    "{input.text}",
                ],
                "output": {"type": "json"},
                "inherit_env": False,
                "executable_identity": "python:>=3.11:aeep.examples.text_stats_cli",
            },
        ),
        declared_fingerprint=RouteFingerprint(value="sha256:" + "0" * 64),
        static_estimate=RouteEstimate(
            resources=ResourceVector(latency_ms=100),
            confidence=0.2,
            source=EstimateSource.STATIC,
        ),
    )
    route = route.model_copy(
        update={
            "declared_fingerprint": RouteFingerprint(
                value=portable_route_fingerprint(route, "fixture.provider")
            )
        }
    )
    qualification = QualificationReport(
        candidate_id="fixture-candidate",
        behavior_fingerprint=route.declared_fingerprint.value.removeprefix("sha256:"),
        static_checks={"schemas": True, "adapter_config": True},
        dynamic_cases=3,
        passed_cases=3,
        repetitions=1,
        dynamic_runs=3,
        passed_runs=3,
        passed=True,
    )
    benchmark = BenchmarkCampaignReport(
        run_id="fixture-benchmark-100",
        suite_id="fixture-suite",
        domain="text-statistics",
        deterministic_tools_available=True,
        pricing_snapshot_ids=[],
        frozen_holdout_decisions={},
        trials=[
            BenchmarkTrial(
                trial_id=f"fixture-trial-{index:03d}",
                run_id="fixture-benchmark-100",
                suite_id="fixture-suite",
                case_id="fixture-case",
                route_id=route.route_id,
                route_fingerprint=route.declared_fingerprint.value.removeprefix("sha256:"),
                condition=(
                    BenchmarkCondition.PROCESS_COLD
                    if index < 20
                    else BenchmarkCondition.ROUTER_WARM
                ),
                repetition=index,
                phase=BenchmarkPhase.MEASUREMENT,
                state="complete",
                ended_at=NOW,
                ok=True,
                valid=True,
                status=ExecutionStatus.SUCCESS,
                wall_time_ms=18,
                actual_resources=ResourceVector(latency_ms=18),
            )
            for index in range(100)
        ],
        summaries=[],
        baseline_deltas=[],
        oracles=[],
        subscription_conservation=[],
    )
    rate_card = RateCardSnapshot(
        provider="fixture.model",
        product="fixture-api",
        model="fixture-model",
        effective_from=NOW,
        retrieved_at=NOW,
        source_uri="fixture://rate-card",
        source_content_sha256="a" * 64,
        currency="USD",
        rates=[
            RateCardRate(
                rate_id="input",
                rate_type=RateType.INPUT_TOKEN,
                meter="input_tokens",
                input_unit="token",
                output_unit="USD",
                unit_quantity=1_000_000,
                rate_amount="1.00",
            )
        ],
    )
    comparison = ComparativeMeasurement(
        comparison_id="fixture-command-vs-host",
        workload_digest="sha256:" + "b" * 64,
        candidate_route_id=route.route_id,
        candidate_fingerprint=route.declared_fingerprint.value,
        baseline_route_id="fixture.host.text-statistics",
        baseline_fingerprint="sha256:" + "c" * 64,
        paired_trials=50,
        candidate_tokens={"input_tokens": 0, "output_tokens": 0},
        baseline_tokens={"input_tokens": 4200, "output_tokens": 260},
        candidate_latency_ms="18",
        baseline_latency_ms="2400",
    )
    artifacts: list[ArtifactReference] = []
    artifact_payloads: dict[str, bytes] = {}
    for artifact_id, filename, value, purpose, media_type, required in (
        (
            "qualification",
            "qualification.json",
            qualification,
            ArtifactPurpose.QUALIFICATION,
            "application/vnd.aeep.qualification-report+json;version=1",
            True,
        ),
        (
            "benchmark",
            "benchmark.json",
            benchmark,
            ArtifactPurpose.BENCHMARK,
            "application/vnd.aeep.benchmark-campaign+json;version=1",
            True,
        ),
        (
            "rate-card",
            "rate-card.json",
            rate_card,
            ArtifactPurpose.RATE_CARD,
            "application/vnd.aeep.rate-card-snapshot+json;version=1",
            False,
        ),
        (
            "comparison",
            "comparison.json",
            comparison,
            ArtifactPurpose.COMPARISON,
            "application/vnd.aeep.comparison-report+json;version=1",
            False,
        ),
    ):
        payload, _ = write_json(filename, value)
        artifact_payloads[artifact_id] = payload
        artifacts.append(
            ArtifactReference(
                artifact_id=artifact_id,
                digest=f"sha256:{hashlib.sha256(payload).hexdigest()}",
                media_type=media_type,
                size_bytes=len(payload),
                location=ArtifactLocation(path=f"evidence/{filename}"),
                required=required,
                purpose=purpose,
            )
        )
    artifact_by_id = {item.artifact_id: item for item in artifacts}
    evidences: list[EvidenceReference] = []
    for evidence_id, evidence_type, artifact_id, summary in (
        (
            "fixture-qualification",
            EvidenceType.QUALIFICATION_REPORT,
            "qualification",
            {"success": {"trials": 3, "successes": 3}},
        ),
        (
            "fixture-benchmark",
            EvidenceType.BENCHMARK_CAMPAIGN,
            "benchmark",
            {
                "sample_size": 100,
                "success": {"trials": 100, "successes": 100},
                "tokens": {"input_tokens": 0, "output_tokens": 0},
                "latency": {"median_ms": 18},
                "cost": {"actual_cash_usd": "0"},
            },
        ),
        (
            "fixture-rate-card",
            EvidenceType.RATE_CARD_SNAPSHOT,
            "rate-card",
            {"snapshot_id": rate_card.snapshot_id},
        ),
        (
            "fixture-comparison",
            EvidenceType.COMPARISON_REPORT,
            "comparison",
            {"paired_trials": 50},
        ),
    ):
        evidence = EvidenceReference(
            evidence_id=evidence_id,
            evidence_type=evidence_type,
            artifact_id=artifact_id,
            subject=EvidenceSubject(
                route_id=route.route_id,
                capability=CAPABILITY,
                route_fingerprint=route.declared_fingerprint.value,
                workload_digest="sha256:" + "b" * 64,
                protocol_identity="aeep-provider-package-v1",
                environment_class="portable",
            ),
            producer=EvidenceProducer(
                producer_id="fixture.verifier",
                role=TrustedKeyRole.INDEPENDENT_VERIFIER,
                key_id=verifier.key_id,
            ),
            trust_claim=TrustLevel.ATTESTED,
            validity=EvidenceValidity(
                issued_at=NOW,
                expires_at=NOW + timedelta(days=180),
            ),
            summary=summary,
            summary_digest=summary_digest(summary),
        )
        evidences.append(
            sign_evidence_attestation(
                evidence,
                artifact_digest=artifact_by_id[artifact_id].digest,
                signer=verifier,
                attestation_id=f"attest-{evidence_id}",
                role="independent_verifier",
                issued_at=NOW,
            )
        )
    package = ProviderPackage(
        metadata=ProviderPackageMetadata(
            package_id="fixture.provider.package",
            version="0.5.0",
            issued_at=NOW,
            expires_at=NOW + timedelta(days=365),
            description="Synthetic AEEP v0.5 provider-package fixture.",
        ),
        spec=ProviderPackageSpec(
            provider=ProviderIdentity(
                provider_id="fixture.provider",
                display_name="Fixture Provider",
                publisher=PublisherIdentity(name="AEEP fixtures", subject="fixture:aep-v05"),
                keys=(
                    ProviderPublicKey(
                        key_id=publisher.key_id,
                        public_key=publisher.public_key_base64url(),
                        roles=(TrustedKeyRole.PACKAGE_PUBLISHER,),
                        valid_from=NOW,
                        valid_until=NOW + timedelta(days=365),
                    ),
                    ProviderPublicKey(
                        key_id=verifier.key_id,
                        public_key=verifier.public_key_base64url(),
                        roles=(TrustedKeyRole.INDEPENDENT_VERIFIER,),
                        valid_from=NOW,
                        valid_until=NOW + timedelta(days=365),
                    ),
                ),
            ),
            compatibility=ProviderCompatibility(
                aeep_min="0.5.0",
                aeep_max_exclusive="0.6.0",
                python=">=3.11",
                platforms=("any",),
                protocols=("aeep-provider-package-v1",),
            ),
            capabilities=(capability,),
            routes=(route,),
            artifacts=tuple(artifacts),
            evidence=tuple(evidences),
            smoke_tests=(
                SmokeTestDefinition(
                    smoke_id="fixture-text-statistics-smoke",
                    route_id=route.route_id,
                    mode="cold_then_warm",
                    input={"text": "one two"},
                    expected={"output_schema_only": True},
                    timeout_ms=5_000,
                    max_executions=2,
                ),
            ),
            extensions={"x-aeep-fixture": {"non_production": True}},
        ),
        integrity=ProviderPackageIntegrity(digest="sha256:" + "0" * 64),
    )
    package = sign_provider_package(
        package,
        publisher,
        signature_id="fixture-publisher-signature",
        issued_at=NOW,
    )
    (HERE / "aeep-provider.yaml").write_text(
        yaml.safe_dump(
            package.model_dump(mode="json", by_alias=True),
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    TrustStore(
        (
            TrustedProviderKey(
                provider_id="fixture.provider",
                key_id=publisher.key_id,
                public_key=publisher.public_key_base64url(),
                valid_from=NOW,
                valid_until=NOW + timedelta(days=365),
                allowed_capabilities=(CAPABILITY,),
                roles=(TrustedKeyRole.PACKAGE_PUBLISHER,),
                allowed_package_ids=(package.metadata.package_id,),
                trust=TrustLevel.VERIFIED,
            ),
            TrustedProviderKey(
                provider_id="fixture.verifier",
                key_id=verifier.key_id,
                public_key=verifier.public_key_base64url(),
                valid_from=NOW,
                valid_until=NOW + timedelta(days=365),
                allowed_capabilities=(CAPABILITY,),
                roles=(TrustedKeyRole.INDEPENDENT_VERIFIER,),
                trust=TrustLevel.ATTESTED,
            ),
        )
    ).save(HERE / "trusted-keys.json")


if __name__ == "__main__":
    main()
