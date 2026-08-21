from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest

from aeep.economic import merge_trusted_provider_keys
from aeep.economic.canonical import canonical_payload
from aeep.economic.signing import Ed25519Signer, encode_base64url
from aeep.economic.trust import (
    TrustedKeyStatus,
    TrustedProviderKey,
    TrustStore,
    TrustStoreVerifier,
)
from aeep.models import SignatureEnvelopeV2

NOW = datetime(2026, 8, 14, 12, tzinfo=UTC)
PAYLOAD = canonical_payload({"provider_id": "provider.example", "quote_id": "quote-1"})


def trusted_key(
    signer: Ed25519Signer,
    *,
    provider_id: str = "provider.example",
    valid_from: datetime = NOW - timedelta(days=1),
    valid_until: datetime = NOW + timedelta(days=1),
    status: TrustedKeyStatus = TrustedKeyStatus.ACTIVE,
    revoked_at: datetime | None = None,
) -> TrustedProviderKey:
    return TrustedProviderKey(
        provider_id=provider_id,
        key_id=signer.key_id,
        public_key=signer.public_key_base64url(),
        valid_from=valid_from,
        valid_until=valid_until,
        revoked_at=revoked_at,
        status=status,
        allowed_capabilities=("text.statistics@1",),
        allowed_quote_hosts=("Quotes.Example.",),
    )


def test_trust_store_binds_provider_capability_and_host() -> None:
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    verifier = TrustStoreVerifier(TrustStore([trusted_key(signer)]), clock=lambda: NOW)
    signature = signer.sign(PAYLOAD)

    accepted = verifier.verify(
        PAYLOAD,
        signature,
        "provider.example",
        capability="text.statistics@1",
        quote_host="quotes.example",
    )

    assert accepted.valid
    assert not verifier.verify(PAYLOAD, signature, "other.provider").valid
    assert not verifier.verify(
        PAYLOAD, signature, "provider.example", capability="document.extract@1"
    ).valid
    assert not verifier.verify(
        PAYLOAD, signature, "provider.example", quote_host="evil.example"
    ).valid
    assert not verifier.verify(PAYLOAD + b"x", signature, "provider.example").valid


def test_unknown_algorithm_and_key_are_rejected() -> None:
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    verifier = TrustStoreVerifier(TrustStore([trusted_key(signer)]), clock=lambda: NOW)
    signature = signer.sign(PAYLOAD)
    unknown_algorithm = SignatureEnvelopeV2.model_construct(
        algorithm="rsa-sha256",
        key_id=signature.key_id,
        value=signature.value,
        canonicalization_version=signature.canonicalization_version,
    )

    assert not verifier.verify(PAYLOAD, unknown_algorithm, "provider.example").valid
    assert not verifier.verify(
        PAYLOAD,
        signature.model_copy(update={"key_id": "unknown"}),
        "provider.example",
    ).valid


def test_expired_and_revoked_keys_fail_new_execution() -> None:
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    signature = signer.sign(PAYLOAD)
    expired = trusted_key(signer, valid_until=NOW - timedelta(microseconds=1))
    revoked = trusted_key(
        signer,
        status=TrustedKeyStatus.REVOKED,
        revoked_at=NOW,
    )

    assert not TrustStoreVerifier(TrustStore([expired]), clock=lambda: NOW).verify(
        PAYLOAD, signature, "provider.example"
    ).valid
    assert not TrustStoreVerifier(TrustStore([revoked]), clock=lambda: NOW).verify(
        PAYLOAD, signature, "provider.example"
    ).valid


def test_historical_verification_accepts_only_pre_revocation_signature() -> None:
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    revoked = trusted_key(
        signer,
        status=TrustedKeyStatus.REVOKED,
        revoked_at=NOW,
    )
    verifier = TrustStoreVerifier(TrustStore([revoked]), clock=lambda: NOW)
    signature = signer.sign(PAYLOAD)

    assert verifier.verify(
        PAYLOAD,
        signature,
        "provider.example",
        signed_at=NOW - timedelta(seconds=1),
        allow_historical=True,
    ).valid
    assert not verifier.verify(
        PAYLOAD,
        signature,
        "provider.example",
        signed_at=NOW,
        allow_historical=True,
    ).valid
    assert not verifier.verify(
        PAYLOAD,
        signature,
        "provider.example",
        allow_historical=True,
    ).valid


def test_trust_store_round_trip_and_immutable_ids(tmp_path) -> None:
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    key = trusted_key(signer)
    store = TrustStore([key])
    path = tmp_path / "trust.json"

    assert store.add_key(key) is key
    with pytest.raises(ValueError, match="different content"):
        store.add_key(key.model_copy(update={"public_key": encode_base64url(b"y" * 32)}))
    store.save(path)

    assert TrustStore.load(path).list_keys() == [key]
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600


def test_trust_merge_keeps_the_most_restrictive_state() -> None:
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    active = trusted_key(signer)
    retired = active.model_copy(update={"status": TrustedKeyStatus.RETIRED})
    revoked_late = active.model_copy(
        update={"status": TrustedKeyStatus.REVOKED, "revoked_at": NOW}
    )
    revoked_early = active.model_copy(
        update={
            "status": TrustedKeyStatus.REVOKED,
            "revoked_at": NOW - timedelta(hours=1),
        }
    )

    assert merge_trusted_provider_keys([active], [retired]).get(
        active.provider_id, active.key_id
    ) == retired
    assert merge_trusted_provider_keys([retired], [revoked_late]).get(
        active.provider_id, active.key_id
    ) == revoked_late
    assert merge_trusted_provider_keys([revoked_late], [revoked_early]).get(
        active.provider_id, active.key_id
    ) == revoked_early


def test_trust_merge_rejects_conflicting_immutable_material() -> None:
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    key = trusted_key(signer)
    conflicting = key.model_copy(update={"public_key": encode_base64url(b"y" * 32)})

    with pytest.raises(ValueError, match="immutable material differs"):
        merge_trusted_provider_keys([key], [conflicting])


def test_verified_key_rotation_chain() -> None:
    old_signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    new_signer = Ed25519Signer.from_private_bytes(bytes(range(1, 33)), key_id="key-2")
    store = TrustStore([trusted_key(old_signer)])
    base = trusted_key(new_signer, valid_from=NOW)
    unsigned_rotation = base.model_copy(
        update={
            "rotation_from_key_id": old_signer.key_id,
            "rotation_signed_at": NOW,
            "rotation_signature": old_signer.sign(b"placeholder"),
        }
    )
    rotated = TrustedProviderKey.model_validate(
        {
            **base.model_dump(mode="python"),
            "rotation_from_key_id": old_signer.key_id,
            "rotation_signed_at": NOW,
            "rotation_signature": old_signer.sign(unsigned_rotation.rotation_payload()),
        }
    )

    assert store.add_rotated_key(rotated, clock=lambda: NOW) is rotated
    assert store.get("provider.example", "key-2") == rotated

    tampered = rotated.model_copy(update={"public_key": encode_base64url(b"z" * 32)})
    with pytest.raises(ValueError, match="signature verification failed"):
        TrustStore([trusted_key(old_signer)]).add_rotated_key(tampered, clock=lambda: NOW)


@pytest.mark.parametrize(
    ("field", "expanded", "message"),
    [
        (
            "allowed_capabilities",
            ("text.statistics@1", "document.extract@1"),
            "operator-trusted capabilities",
        ),
        (
            "allowed_quote_hosts",
            ("quotes.example", "unapproved.example"),
            "operator-trusted quote hosts",
        ),
    ],
)
def test_key_rotation_cannot_expand_operator_trust_scope(
    field: str,
    expanded: tuple[str, ...],
    message: str,
) -> None:
    old_signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    new_signer = Ed25519Signer.from_private_bytes(bytes(range(1, 33)), key_id="key-2")
    base = trusted_key(new_signer, valid_from=NOW).model_copy(update={field: expanded})
    unsigned = base.model_copy(
        update={
            "rotation_from_key_id": old_signer.key_id,
            "rotation_signed_at": NOW,
            "rotation_signature": old_signer.sign(b"placeholder"),
        }
    )
    rotated = unsigned.model_copy(
        update={"rotation_signature": old_signer.sign(unsigned.rotation_payload())}
    )

    with pytest.raises(ValueError, match=message):
        TrustStore([trusted_key(old_signer)]).add_rotated_key(rotated, clock=lambda: NOW)


@pytest.mark.parametrize(
    "signed_at",
    [NOW - timedelta(minutes=6), NOW + timedelta(minutes=6)],
)
def test_key_rotation_rejects_material_clock_skew(signed_at: datetime) -> None:
    old_signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    new_signer = Ed25519Signer.from_private_bytes(bytes(range(1, 33)), key_id="key-2")
    base = trusted_key(new_signer, valid_from=signed_at)
    unsigned = base.model_copy(
        update={
            "rotation_from_key_id": old_signer.key_id,
            "rotation_signed_at": signed_at,
            "rotation_signature": old_signer.sign(b"placeholder"),
        }
    )
    rotated = unsigned.model_copy(
        update={"rotation_signature": old_signer.sign(unsigned.rotation_payload())}
    )

    with pytest.raises(ValueError, match="clock skew"):
        TrustStore([trusted_key(old_signer)]).add_rotated_key(rotated, clock=lambda: NOW)


def test_revoked_key_cannot_backdate_a_new_rotation() -> None:
    old_signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="key-1")
    new_signer = Ed25519Signer.from_private_bytes(bytes(range(1, 33)), key_id="key-2")
    signed_at = NOW - timedelta(minutes=2)
    predecessor = trusted_key(
        old_signer,
        status=TrustedKeyStatus.REVOKED,
        revoked_at=NOW - timedelta(minutes=1),
    )
    base = trusted_key(new_signer, valid_from=signed_at)
    unsigned = base.model_copy(
        update={
            "rotation_from_key_id": old_signer.key_id,
            "rotation_signed_at": signed_at,
            "rotation_signature": old_signer.sign(b"placeholder"),
        }
    )
    rotated = unsigned.model_copy(
        update={"rotation_signature": old_signer.sign(unsigned.rotation_payload())}
    )

    with pytest.raises(ValueError, match="active now"):
        TrustStore([predecessor]).add_rotated_key(rotated, clock=lambda: NOW)
