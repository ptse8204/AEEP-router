"""Provider-neutral capacity, reservation, and entitlement contracts."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

import rfc8785
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def capacity_digest(value: BaseModel | dict[str, Any]) -> str:
    payload = (
        value.model_dump(mode="json", exclude_computed_fields=True)
        if isinstance(value, BaseModel)
        else value
    )
    return f"sha256:{hashlib.sha256(rfc8785.dumps(payload)).hexdigest()}"


class CapacityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True, allow_inf_nan=False)


class CapacityKind(StrEnum):
    SUBSCRIPTION = "subscription"
    PURCHASED_CREDIT = "purchased_credit"
    LOCAL_COMPUTE = "local_compute"
    EXTERNAL_ENTITLEMENT = "external_entitlement"


class CapacityTransferability(StrEnum):
    SELF_ONLY = "self_only"
    SAME_PRINCIPAL = "same_principal"
    PROVIDER_AUTHORIZED = "provider_authorized"
    TRANSFERABLE = "transferable"


class CapacitySettlementMode(StrEnum):
    NONE = "none"
    SUBSCRIPTION_USAGE = "subscription_usage"
    X402_BATCH = "x402_batch"
    X402_EXACT = "x402_exact"


class CapacityReservationStatus(StrEnum):
    RESERVED = "reserved"
    CLAIMED = "claimed"
    RELEASED = "released"
    EXPIRED = "expired"
    CONSUMED = "consumed"


class EntitlementRedemptionStatus(StrEnum):
    PARTIAL = "partial"
    CONSUMED = "consumed"


class CapacitySignature(CapacityModel):
    algorithm: str = Field(min_length=1, max_length=50)
    key_id: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=2048)


class CapacityEvidence(CapacityModel):
    evidence_id: str = Field(default_factory=lambda: new_id("capacity-evidence"))
    source: str = Field(min_length=1, max_length=100)
    source_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    observed_at: datetime = Field(default_factory=utc_now)
    confidence: float = Field(default=0.5, ge=0, le=1)

    @field_validator("observed_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("capacity evidence time must be timezone-aware")
        return value.astimezone(UTC)


class CapacityWindow(CapacityModel):
    window_id: str = Field(min_length=1, max_length=200)
    unit: str = Field(default="provider_unit", min_length=1, max_length=100)
    used_percent: Decimal | None = Field(default=None, ge=0, le=100)
    allowance: Decimal | None = Field(default=None, ge=0)
    remaining: Decimal | None = Field(default=None, ge=0)
    reset_at: datetime | None = None
    duration_seconds: int | None = Field(default=None, gt=0)
    hard_limit: bool = True
    exhausted: bool = False
    confidence: float = Field(default=0.5, ge=0, le=1)
    evidence: tuple[CapacityEvidence, ...] = ()

    @model_validator(mode="after")
    def valid_window(self) -> CapacityWindow:
        if self.allowance is not None and self.remaining is not None and self.remaining > self.allowance:
            raise ValueError("capacity remaining cannot exceed allowance")
        if self.reset_at is not None and (
            self.reset_at.tzinfo is None or self.reset_at.utcoffset() is None
        ):
            raise ValueError("capacity reset time must be timezone-aware")
        if self.exhausted and self.remaining not in {None, Decimal(0)}:
            raise ValueError("an exhausted window cannot report positive remaining capacity")
        return self


class CapacityObservation(CapacityModel):
    observation_id: str = Field(default_factory=lambda: new_id("capacity"))
    resource_id: str = Field(min_length=1, max_length=200)
    windows: tuple[CapacityWindow, ...] = Field(min_length=1)
    source: str = Field(min_length=1, max_length=100)
    observed_at: datetime = Field(default_factory=utc_now)
    redacted_provider_metadata: dict[str, str | int | bool | None] = Field(
        default_factory=dict
    )

    @field_validator("observed_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("capacity observation time must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("redacted_provider_metadata")
    @classmethod
    def metadata_is_redacted(
        cls, value: dict[str, str | int | bool | None]
    ) -> dict[str, str | int | bool | None]:
        sensitive = {"account", "auth", "cookie", "display_name", "email", "secret", "token"}
        if any(any(part in key.lower() for part in sensitive) for key in value):
            raise ValueError("provider metadata contains an identity or secret field")
        return value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def canonical_digest(self) -> str:
        return capacity_digest(self)


class CapacityReservation(CapacityModel):
    reservation_id: str = Field(default_factory=lambda: new_id("capacity-reservation"))
    resource_id: str = Field(min_length=1, max_length=200)
    execution_id: str = Field(min_length=1, max_length=200)
    maximum_quantity: Decimal = Field(ge=0)
    unit: str = Field(min_length=1, max_length=100)
    expires_at: datetime
    status: CapacityReservationStatus = CapacityReservationStatus.RESERVED
    idempotency_key: str = Field(min_length=1, max_length=500)
    claim_token: str | None = Field(default=None, max_length=500)
    version: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def valid_reservation(self) -> CapacityReservation:
        for value in (self.expires_at, self.created_at, self.updated_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("capacity reservation times must be timezone-aware")
        if self.status is CapacityReservationStatus.CLAIMED and not self.claim_token:
            raise ValueError("claimed capacity requires a claim token")
        return self


class CapacityAuthorizationEvidence(CapacityModel):
    evidence_id: str = Field(default_factory=lambda: new_id("capacity-authority"))
    provider_id: str = Field(min_length=1, max_length=200)
    resource_id: str = Field(min_length=1, max_length=200)
    resource_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    issuer_principal_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    authorized_beneficiary_digest: str | None = Field(
        default=None, pattern=r"^sha256:[a-f0-9]{64}$"
    )
    transferability: Literal[
        CapacityTransferability.PROVIDER_AUTHORIZED,
        CapacityTransferability.TRANSFERABLE,
    ]
    issued_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    signature: CapacitySignature

    @model_validator(mode="after")
    def valid_evidence(self) -> CapacityAuthorizationEvidence:
        if any(
            value.tzinfo is None or value.utcoffset() is None
            for value in (self.issued_at, self.expires_at)
        ):
            raise ValueError("authorization evidence times must be timezone-aware")
        if self.expires_at <= self.issued_at:
            raise ValueError("authorization evidence must expire after issuance")
        return self


class ExecutionEntitlement(CapacityModel):
    entitlement_id: str = Field(default_factory=lambda: new_id("entitlement"))
    issuer_principal_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    beneficiary_principal_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    backing_resource_id: str = Field(min_length=1, max_length=200)
    backing_resource_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    capability: str = Field(min_length=1, max_length=200)
    action_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    maximum_quantity: Decimal = Field(gt=0)
    unit: str = Field(min_length=1, max_length=100)
    expires_at: datetime
    nonce: str = Field(min_length=16, max_length=500)
    transferability_basis: CapacityTransferability
    authorization_evidence_id: str | None = Field(default=None, max_length=200)
    signature: CapacitySignature
    issued_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def transferable_only_with_authority(self) -> ExecutionEntitlement:
        if any(
            value.tzinfo is None or value.utcoffset() is None
            for value in (self.issued_at, self.expires_at)
        ):
            raise ValueError("entitlement times must be timezone-aware")
        if self.expires_at <= self.issued_at:
            raise ValueError("entitlement must expire after issuance")
        same_principal = self.issuer_principal_digest == self.beneficiary_principal_digest
        if self.transferability_basis in {
            CapacityTransferability.SELF_ONLY,
            CapacityTransferability.SAME_PRINCIPAL,
        } and not same_principal:
            raise ValueError("self-only capacity cannot name an external beneficiary")
        if self.transferability_basis in {
            CapacityTransferability.PROVIDER_AUTHORIZED,
            CapacityTransferability.TRANSFERABLE,
        } and not self.authorization_evidence_id:
            raise ValueError("transferable capacity requires provider authorization evidence")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def canonical_digest(self) -> str:
        return capacity_digest(self)


class EntitlementRedemptionReceipt(CapacityModel):
    redemption_id: str = Field(default_factory=lambda: new_id("redemption"))
    entitlement_id: str = Field(min_length=1, max_length=200)
    attempt_id: str = Field(min_length=1, max_length=200)
    quantity_consumed: Decimal = Field(gt=0)
    remaining_quantity: Decimal = Field(ge=0)
    status: EntitlementRedemptionStatus
    evidence_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    timestamp: datetime = Field(default_factory=utc_now)

    @field_validator("timestamp")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("redemption time must be timezone-aware")
        return value.astimezone(UTC)


class CapacityResource(CapacityModel):
    id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:-]+$")
    kind: Literal["purchased_credit", "local_compute", "external_entitlement"]
    provider: str = Field(min_length=1, max_length=100)
    product: str = Field(min_length=1, max_length=100)
    unit: str = Field(min_length=1, max_length=100)
    resource_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    transferability: CapacityTransferability = CapacityTransferability.SELF_ONLY
    settlement_mode: CapacitySettlementMode = CapacitySettlementMode.NONE
    allowance: Decimal | None = Field(default=None, ge=0)
    remaining: Decimal | None = Field(default=None, ge=0)
    authorization_evidence_id: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def valid_resource(self) -> CapacityResource:
        if self.allowance is not None and self.remaining is not None and self.remaining > self.allowance:
            raise ValueError("capacity remaining cannot exceed allowance")
        if self.transferability in {
            CapacityTransferability.PROVIDER_AUTHORIZED,
            CapacityTransferability.TRANSFERABLE,
        } and not self.authorization_evidence_id:
            raise ValueError("transferable resources require provider authorization evidence")
        return self
