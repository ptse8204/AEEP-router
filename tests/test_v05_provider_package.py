from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from aeep.artifact_store import ContentArtifactStore
from aeep.conformance import run_provider_conformance
from aeep.economic.signing import Ed25519Signer
from aeep.economic.trust import TrustStore, TrustStoreVerifier
from aeep.errors import ConfigurationError
from aeep.models import (
    CapabilityDefinition,
    ExecutorKind,
    Locality,
    Manifest,
    PolicyConfig,
    SideEffect,
    TrustedKeyRole,
    TrustLevel,
)
from aeep.provider_ingest import ProviderPackageIngestor
from aeep.provider_package import (
    EvidenceAcceptanceStatus,
    EvidenceAuthorityClass,
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
    load_provider_package,
    parse_provider_package_bytes,
    portable_route_fingerprint,
    provider_package_digest,
    sign_provider_package,
    verify_embedded_package_signature,
)
from aeep.qualification import RouteLifecycle
from aeep.router import Router
from aeep.sdk import build_provider_package
from aeep.store import LATEST_DATABASE_SCHEMA, ReceiptStore

ROOT = Path(__file__).resolve().parents[1]


def package_fixture() -> tuple[ProviderPackage, Ed25519Signer]:
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="fixture-publisher")
    capability = CapabilityDefinition(
        namespace="fixture",
        name="echo",
        version="1",
        description="Echo one bounded value.",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        side_effect=SideEffect.NONE,
    )
    route = PublishedProviderRoute(
        route_id="fixture.command.echo",
        capability=capability.capability,
        input_schema=capability.input_schema,
        output_schema=capability.output_schema,
        executor=PublishedExecutor(
            kind=ExecutorKind.COMMAND,
            description="Fixture command",
            side_effect=SideEffect.NONE,
            locality=Locality.LOCAL,
            idempotent=True,
            config={
                "argv": [
                    "$PYTHON",
                    "-c",
                    "import json,sys; print(json.dumps(json.load(sys.stdin)))",
                ],
                "executable_identity": "python:runtime",
                "stdin_json": True,
                "output": {"type": "json"},
            },
        ),
        declared_fingerprint=RouteFingerprint(value="sha256:" + "0" * 64),
    )
    fingerprint = portable_route_fingerprint(route, "fixture.provider")
    route = route.model_copy(
        update={"declared_fingerprint": RouteFingerprint(value=fingerprint)}
    )
    now = datetime(2026, 8, 21, tzinfo=UTC)
    package = ProviderPackage(
        metadata=ProviderPackageMetadata(
            package_id="fixture.provider.package",
            version="0.6.0",
            issued_at=now,
            expires_at=now + timedelta(days=365),
        ),
        spec=ProviderPackageSpec(
            provider=ProviderIdentity(
                provider_id="fixture.provider",
                display_name="Fixture Provider",
                publisher=PublisherIdentity(name="Fixture", subject="fixture:test"),
                keys=(
                    ProviderPublicKey(
                        key_id=signer.key_id,
                        public_key=signer.public_key_base64url(),
                        roles=(TrustedKeyRole.PACKAGE_PUBLISHER,),
                        valid_from=now,
                        valid_until=now + timedelta(days=365),
                    ),
                ),
            ),
            compatibility=ProviderCompatibility(
                aeep_min="0.5.0",
                aeep_max_exclusive="0.7.0",
            ),
            capabilities=(capability,),
            routes=(route,),
            smoke_tests=(
                SmokeTestDefinition(
                    smoke_id="fixture-echo-smoke",
                    route_id=route.route_id,
                    input={"value": "x"},
                    expected={"output_schema_only": True},
                    timeout_ms=5_000,
                ),
            ),
        ),
        integrity=ProviderPackageIntegrity(digest="sha256:" + "0" * 64),
    )
    return sign_provider_package(
        package,
        signer,
        signature_id="fixture-signature",
        issued_at=now,
    ), signer


def test_package_digest_signature_and_portable_fingerprint() -> None:
    package, _ = package_fixture()

    assert package.integrity.digest == provider_package_digest(package)
    assert verify_embedded_package_signature(package, package.signatures[0])
    assert package.spec.routes[0].declared_fingerprint.value == portable_route_fingerprint(
        package.spec.routes[0], package.spec.provider.provider_id
    )

    changed = package.model_copy(
        update={
            "metadata": package.metadata.model_copy(update={"description": "tampered"})
        }
    )
    assert not verify_embedded_package_signature(changed, changed.signatures[0])
    report = run_provider_conformance(package)
    assert report.passed
    assert all(item.passed for item in report.checks)


def test_v05_package_signature_compatibility() -> None:
    package, signer = package_fixture()
    unsigned = package.model_copy(
        update={
            "api_version": "aeep.dev/v0.5",
            "integrity": ProviderPackageIntegrity(digest="sha256:" + "0" * 64),
            "signatures": (),
        }
    )
    legacy = sign_provider_package(
        unsigned,
        signer,
        signature_id="fixture-v05-signature",
        issued_at=package.metadata.issued_at,
    )

    assert legacy.integrity.digest == provider_package_digest(legacy)
    assert verify_embedded_package_signature(legacy, legacy.signatures[0])
    assert ProviderPackage.model_validate(
        legacy.model_dump(mode="json", by_alias=True)
    ) == legacy


def test_sdk_builds_content_addressed_v06_package() -> None:
    source, _ = package_fixture()
    published = source.spec.routes[0]
    executor = published.executor_spec(source.spec.provider.provider_id)
    executor.side_effect = published.executor.side_effect
    executor.idempotent = published.executor.idempotent
    built = build_provider_package(
        package_id="fixture.sdk.package",
        version="0.6.0",
        issued_at=source.metadata.issued_at,
        provider=source.spec.provider,
        compatibility=source.spec.compatibility,
        capabilities=source.spec.capabilities,
        executors=(executor,),
    )

    assert built.api_version == "aeep.dev/v0.6"
    assert built.integrity.digest == provider_package_digest(built)
    assert built.spec.routes[0].declared_fingerprint.value == portable_route_fingerprint(
        built.spec.routes[0], built.spec.provider.provider_id
    )


def test_v05_evidence_is_accepted_only_as_an_incomplete_prior() -> None:
    package, _ = load_provider_package(
        ROOT / "examples" / "provider_package" / "aeep-provider.yaml"
    )
    legacy = package.model_copy(update={"api_version": "aeep.dev/v0.5"})
    evidence = legacy.spec.evidence[0]

    acceptance = ProviderPackageIngestor._acceptance(
        legacy,
        evidence,
        metric="correctness",
        trust=TrustLevel.ATTESTED,
        subject_matches=True,
        allow_self_asserted_priors=True,
        evaluated_at=datetime(2026, 8, 21, tzinfo=UTC),
    )

    assert acceptance.status is EvidenceAcceptanceStatus.ACCEPTED_AS_PRIOR
    assert acceptance.reason_code == "legacy_incomplete_evidence_prior"


@pytest.mark.parametrize(
    "authority",
    [
        EvidenceAuthorityClass.PROVIDER_SELF_ATTESTED,
        EvidenceAuthorityClass.DISTRIBUTOR_ATTESTED,
    ],
)
def test_non_independent_v06_evidence_cannot_qualify(
    authority: EvidenceAuthorityClass,
) -> None:
    package, _ = load_provider_package(
        ROOT / "examples" / "provider_package" / "aeep-provider.yaml"
    )
    evidence = package.spec.evidence[0].model_copy(
        update={"authority_class": authority}
    )

    acceptance = ProviderPackageIngestor._acceptance(
        package,
        evidence,
        metric="correctness",
        trust=TrustLevel.ATTESTED,
        subject_matches=True,
        allow_self_asserted_priors=True,
        evaluated_at=datetime(2026, 8, 21, tzinfo=UTC),
    )

    assert acceptance.status is EvidenceAcceptanceStatus.ACCEPTED_AS_PRIOR
    assert acceptance.reason_code == "non_independent_authority_prior"


def test_strict_yaml_and_directory_resolution(tmp_path: Path) -> None:
    package, _ = package_fixture()
    package_path = tmp_path / "aeep-provider.yaml"
    package_path.write_text(
        yaml.safe_dump(package.model_dump(mode="json", by_alias=True), sort_keys=False),
        encoding="utf-8",
    )

    loaded, root = load_provider_package(tmp_path)

    assert loaded == package
    assert root == tmp_path.resolve()


@pytest.mark.parametrize(
    "payload",
    [
        b"apiVersion: aeep.dev/v0.5\napiVersion: aeep.dev/v0.5\n",
        b"root: &root {value: 1}\nalias: *root\n",
    ],
)
def test_strict_yaml_rejects_duplicates_and_aliases(payload: bytes) -> None:
    with pytest.raises(ConfigurationError):
        parse_provider_package_bytes(payload)


@pytest.mark.asyncio
async def test_package_ingest_is_inert_idempotent_and_self_asserted(tmp_path: Path) -> None:
    package, _ = package_fixture()
    package_path = tmp_path / "aeep-provider.yaml"
    package_path.write_text(
        yaml.safe_dump(package.model_dump(mode="json", by_alias=True), sort_keys=False),
        encoding="utf-8",
    )
    store = ReceiptStore(tmp_path / "aeep.db")
    ingestor = ProviderPackageIngestor(
        store,
        ContentArtifactStore(tmp_path / "cas"),
        TrustStore(),
        clock=lambda: package.metadata.issued_at,
    )

    first = await ingestor.ingest(package_path)
    second = await ingestor.ingest(package_path)

    assert first == second
    assert len(first) == 1
    assert first[0].status is RouteLifecycle.CANDIDATE
    assert not first[0].spec.enabled
    assert not first[0].spec.safe_to_auto_execute
    assert not first[0].spec.idempotent
    assert first[0].spec.side_effect is SideEffect.FINANCIAL
    assert store.get_provider_package(package.integrity.digest) == package
    assert store.protocol_cutover("rfc8785_live_cutover") is not None
    assert LATEST_DATABASE_SCHEMA == 5
    router = Router(Manifest(database=str(tmp_path / "aeep.db")), store=store)
    reports = await router.smoke_candidate(first[0].executor_id)
    assert len(reports) == 1
    assert reports[0].status.value == "passed"
    assert router.inspect_candidate(first[0].executor_id)["smoke"]["status"] == "passed"
    await router.close()


@pytest.mark.asyncio
async def test_checked_package_completes_smoke_qualification_and_activation(
    tmp_path: Path,
) -> None:
    fixture = ROOT / "examples" / "provider_package"
    trust = TrustStore.load(fixture / "trusted-keys.json")
    manifest = Manifest.model_validate(
        {
            "database": str(tmp_path / "aeep.db"),
            "provider_packages": {"artifact_root": str(tmp_path / "artifacts")},
        }
    )
    router = Router(
        manifest,
        economic_verifier=TrustStoreVerifier(
            trust,
            clock=lambda: datetime(2026, 8, 21, tzinfo=UTC),
        ),
        clock=lambda: datetime(2026, 8, 21, tzinfo=UTC),
    )
    try:
        candidates = await router.ingest_provider_package(fixture / "aeep-provider.yaml")
        assert len(candidates) == 1
        assert candidates[0].status is RouteLifecycle.CANDIDATE
        assert router.store.list_receipts(limit=10) == []
        estimate = router.estimator.estimate(candidates[0].spec, PolicyConfig())
        assert estimate.sample_size == 100
        assert estimate.resources.latency_ms < 100

        smoke = await router.smoke_candidate(candidates[0].executor_id)
        assert len(smoke) == 2
        assert all(item.status.value == "passed" for item in smoke)
        report = router.qualify_candidate_from_evidence(candidates[0].executor_id)
        assert report.passed and report.qualification_method == "evidence_reuse"
        active = router.activate_candidate(candidates[0].executor_id)
        assert active.status is RouteLifecycle.ACTIVE
        outcome = await router.execute(
            {
                "capability": "text.statistics@1",
                "input": {"text": "one two"},
            }
        )
        assert outcome.ok
    finally:
        await router.close()


def test_v3_database_migrates_provider_package_state_transactionally(tmp_path: Path) -> None:
    database = tmp_path / "v3.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE route_candidates(
                executor_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        connection.execute("PRAGMA user_version=3")

    with ReceiptStore(database) as store:
        tables = {
            row[0]
            for row in store._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        columns = {
            row[1] for row in store._connection.execute("PRAGMA table_info(route_candidates)")
        }
        assert {
            "provider_packages",
            "content_artifacts",
            "evidence_acceptances",
            "smoke_test_reports",
            "cache_affinity_observations",
            "action_approval_records",
        } <= tables
        assert {"package_digest", "package_fingerprint", "verification_snapshot_id"} <= columns
        assert store.protocol_cutover("rfc8785_live_cutover") is not None
        assert store._connection.execute("PRAGMA user_version").fetchone()[0] == 5
        receipt_columns = {
            row[1] for row in store._connection.execute("PRAGMA table_info(receipts)")
        }
        assert {"executor_fingerprint", "cohort_digest"} <= receipt_columns
