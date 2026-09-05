"""Pure commit, accumulate, and reconcile operations for the local binding."""

from __future__ import annotations

from decimal import Decimal

import rfc8785

from ..capacity import (
    CapacityTransferability,
    EntitlementRedemptionReceipt,
    ExecutionEntitlement,
)
from .models import X402BatchRecord, X402BatchState, X402CapacityCommitment


def commit(entitlement: ExecutionEntitlement, *, enabled: bool = False) -> X402BatchRecord:
    if not enabled:
        raise ValueError("x402 capacity binding is disabled")
    if entitlement.transferability_basis in {
        CapacityTransferability.SELF_ONLY,
        CapacityTransferability.SAME_PRINCIPAL,
    }:
        raise ValueError("self-only capacity cannot be serialized as x402")
    if entitlement.authorization_evidence_id is None:
        raise ValueError("x402 capacity commitment requires provider authority evidence")
    commitment = X402CapacityCommitment(
        entitlement_id=entitlement.entitlement_id,
        entitlement_digest=entitlement.canonical_digest,
        beneficiary_principal_digest=entitlement.beneficiary_principal_digest,
        backing_resource_fingerprint=entitlement.backing_resource_fingerprint,
        capability=entitlement.capability,
        action_digest=entitlement.action_digest,
        maximum_quantity=entitlement.maximum_quantity,
        unit=entitlement.unit,
        expires_at=entitlement.expires_at,
        nonce=entitlement.nonce,
        authorization_evidence_id=entitlement.authorization_evidence_id,
        signature=entitlement.signature,
    )
    return X402BatchRecord(
        commitment=commitment,
        remaining_quantity=commitment.maximum_quantity,
    )


def canonical_commitment_bytes(commitment: X402CapacityCommitment) -> bytes:
    return rfc8785.dumps(commitment.model_dump(mode="json", exclude_computed_fields=True))


def accumulate(
    record: X402BatchRecord, receipt: EntitlementRedemptionReceipt
) -> X402BatchRecord:
    if record.state not in {X402BatchState.COMMITTED, X402BatchState.ACCUMULATING}:
        raise ValueError(f"cannot accumulate a {record.state.value} x402 batch")
    if receipt.entitlement_id != record.commitment.entitlement_id:
        raise ValueError("redemption does not match x402 commitment")
    if receipt.evidence_digest in record.redemption_evidence_digests:
        raise ValueError("x402 redemption evidence replay")
    consumed = record.accumulated_quantity + receipt.quantity_consumed
    if consumed > record.commitment.maximum_quantity:
        raise ValueError("x402 accumulation exceeds maximum authorization")
    remaining = record.commitment.maximum_quantity - consumed
    if receipt.remaining_quantity != remaining:
        raise ValueError("x402 redemption remaining quantity conflicts")
    return record.model_copy(
        update={
            "state": (
                X402BatchState.REDEEMED if remaining == 0 else X402BatchState.ACCUMULATING
            ),
            "accumulated_quantity": consumed,
            "remaining_quantity": remaining,
            "redemption_evidence_digests": (
                *record.redemption_evidence_digests,
                receipt.evidence_digest,
            ),
        }
    )


def reconcile(
    record: X402BatchRecord,
    *,
    claimed_quantity: Decimal,
    release_remaining: bool = False,
) -> X402BatchRecord:
    claimed = Decimal(str(claimed_quantity))
    if not claimed.is_finite() or claimed < 0:
        raise ValueError("x402 reconciliation quantity must be finite and non-negative")
    if claimed > record.commitment.maximum_quantity or claimed > record.accumulated_quantity:
        return record.model_copy(
            update={
                "state": X402BatchState.DISPUTED,
                "dispute_reason": "claimed quantity exceeds authorized observed consumption",
            }
        )
    if claimed != record.accumulated_quantity:
        return record.model_copy(
            update={
                "state": X402BatchState.DISPUTED,
                "dispute_reason": "claimed quantity conflicts with redemption evidence",
            }
        )
    if release_remaining and record.remaining_quantity:
        return record.model_copy(
            update={
                "state": X402BatchState.RELEASED,
                "released_quantity": record.remaining_quantity,
            }
        )
    return record.model_copy(
        update={
            "state": (
                X402BatchState.REDEEMED
                if record.remaining_quantity == 0
                else X402BatchState.ACCUMULATING
            )
        }
    )
