"""Local HMAC compatibility and Ed25519 economic-record signatures."""

from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass
from typing import Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from ..models import SignatureAlgorithm, SignatureEnvelopeV2
from .canonical import CANONICALIZATION_VERSION

ED25519_ALGORITHM = SignatureAlgorithm.ED25519
HMAC_SHA256_ALGORITHM = SignatureAlgorithm.HMAC_SHA256
ALLOWED_SIGNATURE_ALGORITHMS = frozenset(
    {SignatureAlgorithm.ED25519.value, SignatureAlgorithm.HMAC_SHA256.value}
)


def encode_base64url(value: bytes) -> str:
    """Encode bytes as unpadded URL-safe base64."""

    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def decode_base64url(value: str) -> bytes:
    """Decode canonical unpadded URL-safe base64, rejecting aliases."""

    if not value or "=" in value:
        raise ValueError("signature encoding must be non-empty unpadded base64url")
    try:
        decoded = base64.b64decode(
            value + ("=" * (-len(value) % 4)),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, TypeError) as exc:
        raise ValueError("signature encoding is not valid base64url") from exc
    if encode_base64url(decoded) != value:
        raise ValueError("signature encoding is not canonical base64url")
    return decoded


class Signer(Protocol):
    """Signer for bytes already produced by economic canonicalization."""

    def sign(self, payload: bytes) -> SignatureEnvelopeV2: ...


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Structured signature verification result safe for audit output."""

    valid: bool
    reason: str
    provider_id: str | None = None
    key_id: str | None = None
    algorithm: str | None = None

    def require_valid(self) -> None:
        if not self.valid:
            raise ValueError(self.reason)


class Verifier(Protocol):
    """Provider-aware verifier for signed canonical bytes."""

    def verify(
        self,
        payload: bytes,
        signature: SignatureEnvelopeV2,
        expected_provider_id: str,
    ) -> VerificationResult: ...


class HMACSignerV1:
    """Shared-secret compatibility signer for local-only AEEP deployments."""

    algorithm = HMAC_SHA256_ALGORITHM

    def __init__(self, key: bytes, *, key_id: str) -> None:
        if len(key) < 32:
            raise ValueError("HMAC signing key must contain at least 32 bytes")
        if not key_id:
            raise ValueError("key_id must not be empty")
        self._key = key
        self.key_id = key_id

    def sign(self, payload: bytes) -> SignatureEnvelopeV2:
        digest = hmac.new(self._key, payload, hashlib.sha256).digest()
        return SignatureEnvelopeV2(
            algorithm=self.algorithm,
            key_id=self.key_id,
            value=encode_base64url(digest),
            canonicalization_version=CANONICALIZATION_VERSION,
        )

    def verify(self, payload: bytes, signature: SignatureEnvelopeV2) -> bool:
        if (
            signature.algorithm != self.algorithm
            or signature.key_id != self.key_id
            or signature.canonicalization_version != CANONICALIZATION_VERSION
        ):
            return False
        return hmac.compare_digest(self.sign(payload).value, signature.value)


class Ed25519Signer:
    """Ed25519 signer backed by ``cryptography``."""

    algorithm = ED25519_ALGORITHM

    def __init__(self, private_key: Ed25519PrivateKey, *, key_id: str) -> None:
        if not key_id:
            raise ValueError("key_id must not be empty")
        self._private_key = private_key
        self.key_id = key_id

    @classmethod
    def generate(cls, *, key_id: str) -> Ed25519Signer:
        return cls(Ed25519PrivateKey.generate(), key_id=key_id)

    @classmethod
    def from_private_bytes(cls, private_key: bytes, *, key_id: str) -> Ed25519Signer:
        return cls(Ed25519PrivateKey.from_private_bytes(private_key), key_id=key_id)

    @property
    def public_key(self) -> Ed25519PublicKey:
        return self._private_key.public_key()

    def private_key_bytes(self) -> bytes:
        return self._private_key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )

    def public_key_bytes(self) -> bytes:
        return self.public_key.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )

    def public_key_base64url(self) -> str:
        return encode_base64url(self.public_key_bytes())

    def sign(self, payload: bytes) -> SignatureEnvelopeV2:
        return SignatureEnvelopeV2(
            algorithm=self.algorithm,
            key_id=self.key_id,
            value=encode_base64url(self._private_key.sign(payload)),
            canonicalization_version=CANONICALIZATION_VERSION,
        )


def verify_ed25519(
    payload: bytes,
    signature: SignatureEnvelopeV2,
    public_key: Ed25519PublicKey,
) -> bool:
    """Verify an Ed25519 envelope without consulting provider trust policy."""

    if (
        signature.algorithm != ED25519_ALGORITHM
        or signature.canonicalization_version != CANONICALIZATION_VERSION
    ):
        return False
    try:
        raw_signature = decode_base64url(signature.value)
        if len(raw_signature) != 64:
            return False
        public_key.verify(raw_signature, payload)
    except (InvalidSignature, ValueError):
        return False
    return True
