from __future__ import annotations

from datetime import UTC, datetime, timedelta

from aeep.economic.canonical import (
    JCS_CANONICALIZATION_VERSION,
    LEGACY_CANONICALIZATION_VERSION,
    canonical_payload,
)
from aeep.economic.signing import Ed25519Signer
from aeep.economic.trust import TrustedProviderKey, TrustStore, TrustStoreVerifier
from aeep.models import TrustedKeyRole

NOW = datetime(2026, 8, 21, tzinfo=UTC)


def verifier(signer: Ed25519Signer) -> TrustStoreVerifier:
    return TrustStoreVerifier(
        TrustStore(
            (
                TrustedProviderKey(
                    provider_id="provider.fixture",
                    key_id=signer.key_id,
                    public_key=signer.public_key_base64url(),
                    valid_from=NOW - timedelta(days=1),
                    valid_until=NOW + timedelta(days=1),
                    allowed_capabilities=("fixture.action@1",),
                    roles=(TrustedKeyRole.PROVIDER_RECORD,),
                ),
            )
        ),
        clock=lambda: NOW,
    )


def test_legacy_signatures_are_historical_only_after_v05_cutover() -> None:
    legacy = Ed25519Signer.from_private_bytes(
        bytes(range(32)),
        key_id="provider-key",
        canonicalization_version=LEGACY_CANONICALIZATION_VERSION,
    )
    value = {
        "schema_version": "0.4",
        "provider_id": "provider.fixture",
        "capability": "fixture.action@1",
        "issued_at": NOW,
    }
    payload = canonical_payload(value, version=LEGACY_CANONICALIZATION_VERSION)
    signature = legacy.sign(payload)
    trust = verifier(legacy)

    live = trust.verify(
        payload,
        signature,
        "provider.fixture",
        capability="fixture.action@1",
    )
    historical = trust.verify(
        payload,
        signature,
        "provider.fixture",
        capability="fixture.action@1",
        signed_at=NOW,
        allow_historical=True,
    )

    assert not live.valid
    assert "historical-only" in live.reason
    assert historical.valid


def test_new_jcs_signatures_remain_live() -> None:
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="provider-key")
    value = {
        "schema_version": "0.5",
        "provider_id": "provider.fixture",
        "capability": "fixture.action@1",
        "issued_at": NOW,
    }
    payload = canonical_payload(value, version=JCS_CANONICALIZATION_VERSION)
    signature = signer.sign(payload)

    assert verifier(signer).verify(
        payload,
        signature,
        "provider.fixture",
        capability="fixture.action@1",
    ).valid
