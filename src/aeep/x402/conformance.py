"""Deterministic, offline conformance campaign for the AEEP local binding."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ..capacity import (
    CapacityAuthorizationEvidence,
    CapacitySignature,
    CapacityTransferability,
    capacity_digest,
    issue_entitlement,
)
from ..errors import ConfigurationError
from ..store import ReceiptStore
from .batch import accumulate, canonical_commitment_bytes, commit, reconcile
from .models import (
    X402BatchState,
    X402CapacityCommitment,
    X402ConformanceCheck,
    X402ConformanceReport,
)


def run_local_conformance(*, binding: str = "aeep-local") -> X402ConformanceReport:
    if binding != "aeep-local":
        raise ValueError("only the offline aeep-local binding is available")
    now = datetime(2030, 1, 1, tzinfo=UTC)
    issuer = capacity_digest({"principal": "issuer"})
    beneficiary = capacity_digest({"principal": "beneficiary"})
    fingerprint = capacity_digest({"resource": "mock-transferable"})
    action = capacity_digest({"action": "fixture@1"})
    signature = CapacitySignature(algorithm="fixture", key_id="offline", value="signed")
    authority = CapacityAuthorizationEvidence(
        evidence_id="capacity-authority-x402",
        provider_id="fixture",
        resource_id="mock-transferable",
        resource_fingerprint=fingerprint,
        issuer_principal_digest=issuer,
        authorized_beneficiary_digest=beneficiary,
        transferability=CapacityTransferability.PROVIDER_AUTHORIZED,
        issued_at=now,
        expires_at=now + timedelta(hours=2),
        signature=signature,
    )
    entitlement = issue_entitlement(
        issuer_principal_digest=issuer,
        beneficiary_principal_digest=beneficiary,
        backing_resource_id="mock-transferable",
        backing_resource_fingerprint=fingerprint,
        capability="fixture.action@1",
        action_digest=action,
        maximum_quantity=Decimal(10),
        known_available=Decimal(10),
        unit="fixture_unit",
        expires_at=now + timedelta(hours=1),
        nonce="offline-nonce-0001",
        transferability=CapacityTransferability.PROVIDER_AUTHORIZED,
        signature=signature,
        authorization=authority,
        issued_at=now,
    )
    checks: list[X402ConformanceCheck] = []

    def passed(check_id: str, reason: str = "") -> None:
        checks.append(X402ConformanceCheck(id=check_id, status="PASS", reason=reason))

    store = ReceiptStore(":memory:")
    try:
        store.save_capacity_authorization_evidence(authority)
        store.save_execution_entitlement(entitlement)
        batch = commit(entitlement, enabled=True)
        reordered = dict(
            reversed(
                list(
                    batch.commitment.model_dump(
                        mode="json", exclude_computed_fields=True
                    ).items()
                )
            )
        )
        if canonical_commitment_bytes(batch.commitment) != canonical_commitment_bytes(
            X402CapacityCommitment.model_validate(reordered)
        ):
            raise AssertionError("canonical serialization changed within one process")
        passed("canonical-serialization")
        if batch.commitment.entitlement_digest != entitlement.canonical_digest:
            raise AssertionError("commitment digest is not entitlement-bound")
        passed("commitment-binding")
        if (
            batch.commitment.maximum_quantity != Decimal(10)
            or batch.commitment.unit != "fixture_unit"
        ):
            raise AssertionError("commitment maximum or unit changed")
        passed("maximum-quantity")
        if (
            batch.commitment.beneficiary_principal_digest != beneficiary
            or batch.commitment.action_digest != action
        ):
            raise AssertionError("beneficiary or action binding changed")
        passed("beneficiary-action-binding")

        partial = store.redeem_entitlement(
            entitlement.entitlement_id,
            attempt_id="attempt-partial",
            quantity=Decimal(3),
            now=now + timedelta(minutes=1),
        )
        accumulated = accumulate(batch, partial)
        replay = store.redeem_entitlement(
            entitlement.entitlement_id,
            attempt_id="attempt-partial",
            quantity=Decimal(3),
            now=now + timedelta(minutes=1),
        )
        if replay != partial:
            raise AssertionError("idempotent redemption did not replay exactly")
        try:
            accumulate(accumulated, replay)
        except ValueError:
            passed("replay")
        else:
            raise AssertionError("x402 accumulator accepted replayed evidence")
        released = reconcile(
            accumulated,
            claimed_quantity=Decimal(3),
            release_remaining=True,
        )
        if released.state is not X402BatchState.RELEASED:
            raise AssertionError("partial use did not release remaining capacity")
        store.release_execution_entitlement(
            entitlement.entitlement_id,
            expected_version=1,
            now=now + timedelta(minutes=2),
        )
        passed("partial-use-release")
        try:
            store.redeem_entitlement(
                entitlement.entitlement_id,
                attempt_id="attempt-after-release",
                quantity=Decimal(1),
                now=now + timedelta(minutes=3),
            )
        except ConfigurationError:
            passed("double-redemption")
        else:
            raise AssertionError("released capacity remained redeemable")

        disputed = reconcile(accumulated, claimed_quantity=Decimal(11))
        if disputed.state is not X402BatchState.DISPUTED:
            raise AssertionError("overclaim was not disputed")
        passed("dispute-on-overclaim")

        expired = entitlement.model_copy(
            update={
                "entitlement_id": "entitlement-expired",
                "nonce": "offline-nonce-expired",
                "issued_at": now - timedelta(hours=2),
                "expires_at": now - timedelta(hours=1),
            }
        )
        store.save_execution_entitlement(expired)
        try:
            store.redeem_entitlement(
                expired.entitlement_id,
                attempt_id="attempt-expired",
                quantity=Decimal(1),
                now=now,
            )
        except ConfigurationError:
            passed("expiry")
        else:
            raise AssertionError("expired entitlement was redeemed")

        try:
            issue_entitlement(
                issuer_principal_digest=issuer,
                beneficiary_principal_digest=beneficiary,
                backing_resource_id="openai-personal",
                backing_resource_fingerprint=fingerprint,
                capability="fixture.action@1",
                action_digest=action,
                maximum_quantity=Decimal(1),
                known_available=Decimal(1),
                unit="provider_unit",
                expires_at=now + timedelta(minutes=1),
                nonce="openai-self-only-0001",
                transferability=CapacityTransferability.SELF_ONLY,
                signature=signature,
            )
        except ValueError:
            passed("invalid-transferability")
        else:
            raise AssertionError("SELF_ONLY entitlement named an external beneficiary")
        try:
            issue_entitlement(
                issuer_principal_digest=issuer,
                beneficiary_principal_digest=beneficiary,
                backing_resource_id="mock-transferable",
                backing_resource_fingerprint=fingerprint,
                capability="fixture.action@1",
                action_digest=action,
                maximum_quantity=Decimal(1),
                known_available=Decimal(1),
                unit="fixture_unit",
                expires_at=now + timedelta(minutes=1),
                nonce="missing-authority-0001",
                transferability=CapacityTransferability.PROVIDER_AUTHORIZED,
                signature=signature,
            )
        except ValueError:
            passed("missing-authority-evidence")
        else:
            raise AssertionError("transferable entitlement omitted authority")
        passed("offline-behavior", "networking and real value movement are absent")
        checks.append(
            X402ConformanceCheck(
                id="live-networking", status="DISABLED", reason="disabled by design"
            )
        )
    finally:
        store.close()
    return X402ConformanceReport(checks=tuple(checks))
