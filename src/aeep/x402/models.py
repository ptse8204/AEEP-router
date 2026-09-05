"""Offline, resource-specific x402 capacity binding records."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import Field, computed_field, model_validator

from ..capacity import CapacitySignature, capacity_digest
from ..capacity.models import CapacityModel


class X402BatchState(StrEnum):
    COMMITTED = "committed"
    ACCUMULATING = "accumulating"
    REDEEMED = "redeemed"
    RELEASED = "released"
    DISPUTED = "disputed"


class X402CapacityCommitment(CapacityModel):
    binding: Literal["aeep-local"] = "aeep-local"
    protocol_version: Literal["x402-v2-batch"] = "x402-v2-batch"
    entitlement_id: str = Field(min_length=1, max_length=200)
    entitlement_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    beneficiary_principal_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    backing_resource_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    capability: str = Field(min_length=1, max_length=200)
    action_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    maximum_quantity: Decimal = Field(gt=0)
    unit: str = Field(min_length=1, max_length=100)
    expires_at: datetime
    nonce: str = Field(min_length=16, max_length=500)
    authorization_evidence_id: str = Field(min_length=1, max_length=200)
    signature: CapacitySignature

    @computed_field  # type: ignore[prop-decorator]
    @property
    def commitment_digest(self) -> str:
        return capacity_digest(self)


class X402BatchRecord(CapacityModel):
    commitment: X402CapacityCommitment
    state: X402BatchState = X402BatchState.COMMITTED
    accumulated_quantity: Decimal = Field(default=Decimal(0), ge=0)
    remaining_quantity: Decimal = Field(ge=0)
    redemption_evidence_digests: tuple[str, ...] = ()
    released_quantity: Decimal = Field(default=Decimal(0), ge=0)
    dispute_reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def quantities_balance(self) -> X402BatchRecord:
        if self.accumulated_quantity + self.remaining_quantity != (
            self.commitment.maximum_quantity
        ):
            raise ValueError("x402 accumulated and remaining quantities must balance")
        if self.released_quantity > self.remaining_quantity:
            raise ValueError("x402 release exceeds remaining quantity")
        if self.state is X402BatchState.DISPUTED and not self.dispute_reason:
            raise ValueError("x402 dispute requires a reason")
        return self


class X402ConformanceCheck(CapacityModel):
    id: str = Field(min_length=1, max_length=200)
    status: Literal["PASS", "FAIL", "DISABLED"]
    reason: str = Field(default="", max_length=2000)


class X402ConformanceReport(CapacityModel):
    schema_version: Literal["aeep-x402-conformance-v1"] = "aeep-x402-conformance-v1"
    binding: Literal["aeep-local"] = "aeep-local"
    production: Literal[False] = False
    network_enabled: Literal[False] = False
    checks: tuple[X402ConformanceCheck, ...]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(item.status in {"PASS", "DISABLED"} for item in self.checks)
