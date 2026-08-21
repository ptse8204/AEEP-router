from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from aeep.economic.canonical import (
    CANONICALIZATION_VERSION,
    canonical_digest,
    canonical_payload,
)
from aeep.economic.signing import (
    Ed25519Signer,
    HMACSignerV1,
    decode_base64url,
    verify_ed25519,
)


def test_canonical_economic_json_fixed_vector() -> None:
    value = {
        "note": "Cafe\u0301",
        "amount": Decimal("0.003800"),
        "at": datetime(2026, 8, 14, 5, 2, 3, 4, tzinfo=timezone(timedelta(hours=-7))),
        "optional": None,
        "signature": {"excluded": True},
    }

    payload = canonical_payload(value)

    assert payload == (
        b'{"canonicalization_version":"aeep-canonical-json-v1","payload":'
        b'{"amount":"0.0038","at":"2026-08-14T12:02:03.000004Z",'
        b'"note":"Caf\xc3\xa9","optional":null}}'
    )
    assert canonical_payload(value) == payload
    assert canonical_digest(value) == "sha256:2b553bac4ceda2f0b279ba976d05f4487ef43b52a2084888fade9a5bc37a1edf"


@pytest.mark.parametrize(
    "value, message",
    [
        ({"value": 0.1}, "binary floating-point"),
        ({"value": Decimal("NaN")}, "non-finite"),
        ({"value": Decimal("-0")}, "negative zero"),
        ({"value": datetime(2026, 1, 1)}, "timezone-aware"),
    ],
)
def test_canonical_economic_json_rejects_ambiguous_values(
    value: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        canonical_payload(value)


def test_canonical_economic_json_rejects_normalized_duplicate_keys() -> None:
    with pytest.raises(ValueError, match="duplicate object key"):
        canonical_payload({"Caf\u00e9": 1, "Cafe\u0301": 2})


def test_ed25519_fixed_vector_and_tampering() -> None:
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="provider-key-1")
    payload = canonical_payload(
        {
            "schema_version": "0.4",
            "provider_id": "provider.example",
            "amount": Decimal("0.0050"),
            "issued_at": datetime(2026, 8, 14, tzinfo=UTC),
        }
    )

    signature = signer.sign(payload)

    assert signature.canonicalization_version == CANONICALIZATION_VERSION
    assert signer.public_key_base64url() == "A6EHv_POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg"
    assert signature.value == (
        "-ANDcRdgtPAYpClcNRDHD25m80qNwtENCARn2rGIB8BfqJUvhZg4-"
        "25gUOc-6yKcPRDqFFI0ubOTLiZfL7ahCQ"
    )
    assert verify_ed25519(payload, signature, signer.public_key)
    assert not verify_ed25519(payload + b" ", signature, signer.public_key)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("maximum_amount", Decimal("0.006")),
        ("expires_at", datetime(2026, 8, 15, tzinfo=UTC)),
        ("executor_fingerprint", "sha256:changed"),
        ("action_digest", "sha256:changed"),
    ],
)
def test_each_request_binding_field_is_signed(field: str, replacement: object) -> None:
    signer = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="provider-key-1")
    record = {
        "schema_version": "0.4",
        "maximum_amount": Decimal("0.005"),
        "expires_at": datetime(2026, 8, 14, tzinfo=UTC),
        "executor_fingerprint": "sha256:executor",
        "action_digest": "sha256:action",
    }
    signature = signer.sign(canonical_payload(record))

    changed = {**record, field: replacement}

    assert not verify_ed25519(canonical_payload(changed), signature, signer.public_key)


def test_hmac_v1_uses_v2_signature_envelope() -> None:
    signer = HMACSignerV1(b"x" * 32, key_id="local-hmac")
    payload = canonical_payload({"schema_version": "0.4", "amount": Decimal("0")})

    signature = signer.sign(payload)

    assert signature.algorithm == "hmac-sha256"
    assert signature.canonicalization_version == CANONICALIZATION_VERSION
    assert signer.verify(payload, signature)
    assert not signer.verify(payload + b"x", signature)


def test_base64url_decoder_rejects_padding_and_aliases() -> None:
    for value in ("", "YQ==", "+w", "a"):
        with pytest.raises(ValueError, match="base64url"):
            decode_base64url(value)
