"""Execution-entitlement issuance with provider-neutral policy enforcement."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from .models import (
    CapacityAuthorizationEvidence,
    CapacitySignature,
    CapacityTransferability,
    ExecutionEntitlement,
    utc_now,
)
from .policy import require_entitlement_authority


def issue_entitlement(
    *,
    issuer_principal_digest: str,
    beneficiary_principal_digest: str,
    backing_resource_id: str,
    backing_resource_fingerprint: str,
    capability: str,
    action_digest: str,
    maximum_quantity: Decimal,
    known_available: Decimal | None,
    unit: str,
    expires_at: datetime,
    nonce: str,
    transferability: CapacityTransferability,
    signature: CapacitySignature,
    authorization: CapacityAuthorizationEvidence | None = None,
    issued_at: datetime | None = None,
) -> ExecutionEntitlement:
    require_entitlement_authority(
        transferability=transferability,
        issuer_principal_digest=issuer_principal_digest,
        beneficiary_principal_digest=beneficiary_principal_digest,
        known_available=known_available,
        requested=maximum_quantity,
        authorization=authorization,
    )
    if authorization is not None:
        if authorization.resource_id != backing_resource_id:
            raise ValueError("authorization resource does not match entitlement")
        if authorization.resource_fingerprint != backing_resource_fingerprint:
            raise ValueError("authorization fingerprint does not match entitlement")
        if authorization.expires_at < expires_at:
            raise ValueError("entitlement cannot outlive authorization evidence")
    return ExecutionEntitlement(
        issuer_principal_digest=issuer_principal_digest,
        beneficiary_principal_digest=beneficiary_principal_digest,
        backing_resource_id=backing_resource_id,
        backing_resource_fingerprint=backing_resource_fingerprint,
        capability=capability,
        action_digest=action_digest,
        maximum_quantity=maximum_quantity,
        unit=unit,
        expires_at=expires_at,
        nonce=nonce,
        transferability_basis=transferability,
        authorization_evidence_id=authorization.evidence_id if authorization else None,
        signature=signature,
        issued_at=issued_at or utc_now(),
    )
