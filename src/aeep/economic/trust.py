"""Operator-controlled provider key trust and verification."""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Literal

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import ConfigDict, Field, field_validator, model_validator

from ..models import SignatureAlgorithm, SignatureEnvelopeV2, StrictModel
from .canonical import CANONICALIZATION_VERSION, canonical_payload
from .signing import (
    ALLOWED_SIGNATURE_ALGORITHMS,
    ED25519_ALGORITHM,
    VerificationResult,
    decode_base64url,
    verify_ed25519,
)

_IDENTIFIER_PATTERN = r"^[A-Za-z0-9_.:-]+$"
_HOST_PATTERN = re.compile(r"^[A-Za-z0-9.-]+$")
_MAXIMUM_ROTATION_CLOCK_SKEW = timedelta(minutes=5)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("trust-store timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _host(value: str) -> str:
    host = value.rstrip(".").lower()
    if not host or not _HOST_PATTERN.fullmatch(host) or ".." in host:
        raise ValueError("allowed_quote_hosts entries must be exact host names or IPv4 addresses")
    return host


class TrustedKeyStatus(StrEnum):
    ACTIVE = "active"
    RETIRED = "retired"
    REVOKED = "revoked"


_STATUS_RESTRICTIVENESS = {
    TrustedKeyStatus.ACTIVE: 0,
    TrustedKeyStatus.RETIRED: 1,
    TrustedKeyStatus.REVOKED: 2,
}
_MUTABLE_KEY_STATE = {"status", "revoked_at"}


class TrustedProviderKey(StrictModel):
    """One operator-trusted provider verification key."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    provider_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    key_id: str = Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)
    algorithm: SignatureAlgorithm = SignatureAlgorithm.ED25519
    public_key: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    valid_from: datetime
    valid_until: datetime
    revoked_at: datetime | None = None
    status: TrustedKeyStatus = TrustedKeyStatus.ACTIVE
    allowed_capabilities: tuple[str, ...] = Field(min_length=1)
    allowed_quote_hosts: tuple[str, ...] = ()
    rotation_from_key_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        pattern=_IDENTIFIER_PATTERN,
    )
    rotation_signed_at: datetime | None = None
    rotation_signature: SignatureEnvelopeV2 | None = None

    @field_validator("valid_from", "valid_until", "revoked_at", "rotation_signed_at")
    @classmethod
    def aware_utc(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value)

    @field_validator("allowed_capabilities")
    @classmethod
    def exact_capabilities(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any("@" not in value or not value.strip() for value in values):
            raise ValueError("trusted capabilities must be exact versioned identifiers")
        if len(set(values)) != len(values):
            raise ValueError("allowed_capabilities cannot contain duplicates")
        return values

    @field_validator("allowed_quote_hosts")
    @classmethod
    def exact_hosts(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_host(value) for value in values)
        if len(set(normalized)) != len(normalized):
            raise ValueError("allowed_quote_hosts cannot contain duplicates")
        return normalized

    @model_validator(mode="after")
    def valid_key(self) -> TrustedProviderKey:
        if self.valid_until <= self.valid_from:
            raise ValueError("key valid_until must be later than valid_from")
        if self.revoked_at is not None and self.revoked_at < self.valid_from:
            raise ValueError("key revoked_at cannot precede valid_from")
        if (self.status is TrustedKeyStatus.REVOKED) != (self.revoked_at is not None):
            raise ValueError("revoked keys require both revoked status and revoked_at")
        rotation_values = (
            self.rotation_from_key_id,
            self.rotation_signed_at,
            self.rotation_signature,
        )
        if any(value is not None for value in rotation_values) and any(
            value is None for value in rotation_values
        ):
            raise ValueError("key rotation metadata must be complete")
        if self.rotation_from_key_id == self.key_id:
            raise ValueError("a key cannot rotate from itself")
        if (
            self.algorithm is SignatureAlgorithm.ED25519
            and len(decode_base64url(self.public_key)) != 32
        ):
            raise ValueError("Ed25519 public keys must contain exactly 32 bytes")
        return self

    def permits_capability(self, capability: str) -> bool:
        return capability in self.allowed_capabilities

    def permits_quote_host(self, host: str) -> bool:
        return _host(host) in self.allowed_quote_hosts

    def rotation_payload(self) -> bytes:
        return canonical_payload(self.model_dump(mode="python", exclude={"rotation_signature"}))


class TrustStoreDocument(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    schema_version: Literal["0.4"] = "0.4"
    keys: tuple[TrustedProviderKey, ...] = ()


class TrustStore:
    """Local immutable-key registry; additions require operator action or a rotation chain."""

    def __init__(self, keys: Iterable[TrustedProviderKey] = ()) -> None:
        self._keys: dict[tuple[str, str], TrustedProviderKey] = {}
        for key in keys:
            self.add_key(key)

    @classmethod
    def load(cls, path: str | Path) -> TrustStore:
        document = TrustStoreDocument.model_validate_json(Path(path).expanduser().read_bytes())
        return cls(document.keys)

    def save(self, path: str | Path) -> None:
        destination = Path(path).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        document = TrustStoreDocument(keys=tuple(self.list_keys()))
        descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(document.model_dump_json(indent=2))
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def add_key(self, key: TrustedProviderKey) -> TrustedProviderKey:
        identity = (key.provider_id, key.key_id)
        existing = self._keys.get(identity)
        if existing is not None:
            if existing != key:
                raise ValueError("trusted key ID already exists with different content")
            return existing
        self._keys[identity] = key
        return key

    def add_rotated_key(
        self,
        key: TrustedProviderKey,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> TrustedProviderKey:
        existing = self.get(key.provider_id, key.key_id)
        if existing is not None:
            if existing != key:
                raise ValueError("trusted key ID already exists with different content")
            return existing
        if key.rotation_from_key_id is None or key.rotation_signed_at is None:
            raise ValueError("rotated keys require signed rotation metadata")
        signature = key.rotation_signature
        if signature is None or signature.key_id != key.rotation_from_key_id:
            raise ValueError("rotation signature must use rotation_from_key_id")
        now = _utc((clock or (lambda: datetime.now(UTC)))())
        if not now - _MAXIMUM_ROTATION_CLOCK_SKEW <= key.rotation_signed_at <= now + _MAXIMUM_ROTATION_CLOCK_SKEW:
            raise ValueError("rotation signature time exceeds allowed clock skew")
        predecessor = self.get(key.provider_id, key.rotation_from_key_id)
        if predecessor is None or predecessor.status is not TrustedKeyStatus.ACTIVE:
            raise ValueError("rotation predecessor must be trusted and active now")
        if not predecessor.valid_from <= now <= predecessor.valid_until:
            raise ValueError("rotation predecessor is outside its validity period")
        if not set(key.allowed_capabilities).issubset(predecessor.allowed_capabilities):
            raise ValueError("rotated key cannot expand operator-trusted capabilities")
        if not set(key.allowed_quote_hosts).issubset(predecessor.allowed_quote_hosts):
            raise ValueError("rotated key cannot expand operator-trusted quote hosts")
        result = TrustStoreVerifier(self, clock=lambda: now).verify(
            key.rotation_payload(),
            signature,
            expected_provider_id=key.provider_id,
        )
        result.require_valid()
        if key.valid_from < key.rotation_signed_at:
            raise ValueError("rotated key cannot become valid before its rotation was signed")
        return self.add_key(key)

    def get(self, provider_id: str, key_id: str) -> TrustedProviderKey | None:
        return self._keys.get((provider_id, key_id))

    def providers_for_key_id(self, key_id: str) -> tuple[str, ...]:
        return tuple(sorted(provider for provider, candidate in self._keys if candidate == key_id))

    def list_keys(self) -> list[TrustedProviderKey]:
        return [self._keys[key] for key in sorted(self._keys)]


def merge_trusted_provider_keys(
    configured: Iterable[TrustedProviderKey],
    stored: Iterable[TrustedProviderKey],
) -> TrustStore:
    """Merge trusted keys without allowing stale state or key material to win."""

    merged: dict[tuple[str, str], TrustedProviderKey] = {}
    for source in (configured, stored):
        for key in source:
            identity = (key.provider_id, key.key_id)
            existing = merged.get(identity)
            if existing is None:
                merged[identity] = key
                continue
            if existing.model_dump(exclude=_MUTABLE_KEY_STATE) != key.model_dump(
                exclude=_MUTABLE_KEY_STATE
            ):
                raise ValueError(
                    f"trusted key {key.key_id!r} has conflicting configured and stored metadata "
                    "(immutable material differs)"
                )
            existing_rank = _STATUS_RESTRICTIVENESS[existing.status]
            key_rank = _STATUS_RESTRICTIVENESS[key.status]
            earlier_revocation = (
                key.status is existing.status is TrustedKeyStatus.REVOKED
                and key.revoked_at is not None
                and existing.revoked_at is not None
                and key.revoked_at < existing.revoked_at
            )
            if key_rank > existing_rank or earlier_revocation:
                merged[identity] = key
    return TrustStore(merged.values())


class TrustStoreVerifier:
    """Verify signatures and the provider/capability/endpoint trust policy."""

    def __init__(
        self,
        store: TrustStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.clock = clock or (lambda: datetime.now(UTC))

    def verify(
        self,
        payload: bytes,
        signature: SignatureEnvelopeV2,
        expected_provider_id: str,
        *,
        capability: str | None = None,
        quote_host: str | None = None,
        signed_at: datetime | None = None,
        allow_historical: bool = False,
    ) -> VerificationResult:
        algorithm = str(signature.algorithm)
        common = {
            "provider_id": expected_provider_id,
            "key_id": signature.key_id,
            "algorithm": algorithm,
        }
        if algorithm not in ALLOWED_SIGNATURE_ALGORITHMS:
            return VerificationResult(False, "signature algorithm is not allowed", **common)
        if signature.canonicalization_version != CANONICALIZATION_VERSION:
            return VerificationResult(False, "canonicalization version is not supported", **common)
        key = self.store.get(expected_provider_id, signature.key_id)
        if key is None:
            providers = self.store.providers_for_key_id(signature.key_id)
            reason = (
                "signing key belongs to a different provider"
                if providers
                else "signing key is not trusted"
            )
            return VerificationResult(False, reason, **common)
        if key.algorithm.value != algorithm:
            return VerificationResult(False, "signature algorithm does not match trusted key", **common)
        if capability is not None and not key.permits_capability(capability):
            return VerificationResult(False, "signing key is not trusted for this capability", **common)
        if quote_host is not None and not key.permits_quote_host(quote_host):
            return VerificationResult(False, "quote host is not trusted for this signing key", **common)

        if allow_historical:
            if signed_at is None:
                return VerificationResult(False, "historical verification requires signed_at", **common)
            effective_time = _utc(signed_at)
        else:
            effective_time = _utc(self.clock())
            if key.status is not TrustedKeyStatus.ACTIVE:
                return VerificationResult(False, "signing key is not active", **common)
        if not key.valid_from <= effective_time <= key.valid_until:
            return VerificationResult(False, "signing key is outside its validity period", **common)
        if key.revoked_at is not None and effective_time >= key.revoked_at:
            return VerificationResult(False, "signing key was revoked at verification time", **common)

        if algorithm != ED25519_ALGORITHM.value:
            return VerificationResult(
                False,
                "provider trust store accepts public-key signatures only",
                **common,
            )
        try:
            public_key = Ed25519PublicKey.from_public_bytes(decode_base64url(key.public_key))
        except ValueError:
            return VerificationResult(False, "trusted public key is invalid", **common)
        if not verify_ed25519(payload, signature, public_key):
            return VerificationResult(False, "signature verification failed", **common)
        return VerificationResult(True, "signature verified", **common)
