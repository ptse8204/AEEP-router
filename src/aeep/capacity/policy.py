"""Fail-closed transferability checks."""

from __future__ import annotations

from decimal import Decimal

from .models import CapacityAuthorizationEvidence, CapacityTransferability


def require_entitlement_authority(
    *,
    transferability: CapacityTransferability,
    issuer_principal_digest: str,
    beneficiary_principal_digest: str,
    known_available: Decimal | None,
    requested: Decimal,
    authorization: CapacityAuthorizationEvidence | None,
) -> None:
    if requested <= 0:
        raise ValueError("entitlement quantity must be positive")
    if known_available is None:
        raise ValueError("unknown capacity cannot authorize an entitlement")
    if requested > known_available:
        raise ValueError("entitlement exceeds known available capacity")
    same_principal = issuer_principal_digest == beneficiary_principal_digest
    if transferability in {
        CapacityTransferability.SELF_ONLY,
        CapacityTransferability.SAME_PRINCIPAL,
    }:
        if not same_principal:
            raise ValueError("self-only capacity cannot name an external beneficiary")
        return
    if authorization is None:
        raise ValueError("external entitlement requires provider authorization evidence")
    if authorization.issuer_principal_digest != issuer_principal_digest:
        raise ValueError("authorization issuer does not match entitlement issuer")
    if (
        authorization.authorized_beneficiary_digest is not None
        and authorization.authorized_beneficiary_digest != beneficiary_principal_digest
    ):
        raise ValueError("authorization beneficiary does not match entitlement beneficiary")
