from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from aeep.capacity import (
    CapacityAuthorizationEvidence,
    CapacityEvidence,
    CapacityObservation,
    CapacityReservationStatus,
    CapacitySignature,
    CapacityTransferability,
    CapacityWindow,
    EntitlementRedemptionStatus,
    issue_entitlement,
    principal_digest,
    reservation,
)
from aeep.errors import ConfigurationError
from aeep.models import Manifest, SubscriptionResource
from aeep.store import LATEST_DATABASE_SCHEMA, ReceiptStore

NOW = datetime(2026, 9, 2, 12, tzinfo=UTC)
DIGEST = f"sha256:{'a' * 64}"
FINGERPRINT = f"sha256:{'b' * 64}"
ISSUER = f"sha256:{'c' * 64}"
BENEFICIARY = f"sha256:{'d' * 64}"
SIGNATURE = CapacitySignature(algorithm="test", key_id="provider-key", value="signed")


def test_old_subscription_resources_keep_safe_defaults():
    manifest = Manifest.model_validate(
        {"version": "0.2", "resources": [{"id": "openai", "provider": "openai", "product": "chatgpt"}]}
    )
    resource = manifest.resources[0]
    assert isinstance(resource, SubscriptionResource)
    assert resource.transferability is CapacityTransferability.SELF_ONLY
    assert resource.settlement_mode.value == "subscription_usage"


def test_capacity_observation_preserves_all_windows_and_redacts_metadata():
    evidence = CapacityEvidence(source="official_host", source_digest=DIGEST)
    observation = CapacityObservation(
        resource_id="openai",
        source="codex_app_server",
        observed_at=NOW,
        windows=(
            CapacityWindow(window_id="primary", used_percent="20", evidence=(evidence,)),
            CapacityWindow(window_id="secondary", remaining="8", allowance="10", evidence=(evidence,)),
        ),
        redacted_provider_metadata={"plan": "managed"},
    )
    assert observation.canonical_digest.startswith("sha256:")
    assert len(observation.windows) == 2
    with pytest.raises(ValueError, match="identity or secret"):
        CapacityObservation(
            resource_id="openai",
            source="codex_app_server",
            windows=observation.windows,
            redacted_provider_metadata={"email": "x@example.test"},
        )


@pytest.mark.parametrize("quantity", ["0", "0.1", "1", "2.50"])
def test_capacity_reservation_release_and_replay_are_atomic(tmp_path, quantity):
    with ReceiptStore(tmp_path / "capacity.db") as store:
        value = reservation(
            resource_id="resource-1",
            execution_id="attempt-1",
            maximum_quantity=Decimal(quantity),
            unit="turn",
            expires_at=NOW + timedelta(minutes=5),
            idempotency_key=f"reserve-{quantity}",
        )
        stored = store.reserve_capacity(value, known_available=Decimal("10"), now=NOW)
        assert store.reserve_capacity(value, known_available=Decimal("10"), now=NOW) == stored
        claimed = store.claim_capacity_reservation(
            value.reservation_id, claim_token="worker-1", expected_version=0, now=NOW
        )
        assert claimed.status is CapacityReservationStatus.CLAIMED
        assert store.claim_capacity_reservation(
            value.reservation_id, claim_token="worker-1", expected_version=0, now=NOW
        ) == claimed
        released = store.release_capacity_reservation(
            value.reservation_id, expected_version=1, now=NOW
        )
        assert released.status is CapacityReservationStatus.RELEASED
        assert store.release_capacity_reservation(
            value.reservation_id, expected_version=1, now=NOW
        ) == released
        assert LATEST_DATABASE_SCHEMA == 7
        assert store._connection.execute("PRAGMA user_version").fetchone()[0] == 7


def test_reservation_rejects_unknown_overdraw_and_expiry(tmp_path):
    value = reservation(
        resource_id="resource-1",
        execution_id="attempt-1",
        maximum_quantity=Decimal("2"),
        unit="turn",
        expires_at=NOW + timedelta(minutes=5),
        idempotency_key="reserve-1",
    )
    with ReceiptStore(tmp_path / "capacity.db") as store:
        with pytest.raises(ConfigurationError, match="unknown capacity"):
            store.reserve_capacity(value, known_available=None, now=NOW)
        with pytest.raises(ConfigurationError, match="exceeds"):
            store.reserve_capacity(value, known_available=Decimal("1"), now=NOW)
        with pytest.raises(ConfigurationError, match="expired"):
            store.reserve_capacity(
                value.model_copy(update={"expires_at": NOW - timedelta(seconds=1)}),
                known_available=Decimal("10"),
                now=NOW,
            )


def test_self_only_openai_capacity_cannot_issue_external_entitlement():
    with pytest.raises(ValueError, match="self-only"):
        issue_entitlement(
            issuer_principal_digest=ISSUER,
            beneficiary_principal_digest=BENEFICIARY,
            backing_resource_id="openai.personal",
            backing_resource_fingerprint=FINGERPRINT,
            capability="code.review@1",
            action_digest=DIGEST,
            maximum_quantity=Decimal("1"),
            known_available=Decimal("1"),
            unit="turn",
            expires_at=NOW + timedelta(minutes=5),
            nonce="self-only-nonce-001",
            transferability=CapacityTransferability.SELF_ONLY,
            signature=SIGNATURE,
        )


def test_provider_authorized_entitlement_redeems_once_without_double_spend(tmp_path):
    evidence = CapacityAuthorizationEvidence(
        provider_id="mock-provider",
        resource_id="mock-resource",
        resource_fingerprint=FINGERPRINT,
        issuer_principal_digest=ISSUER,
        authorized_beneficiary_digest=BENEFICIARY,
        transferability=CapacityTransferability.PROVIDER_AUTHORIZED,
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        signature=SIGNATURE,
    )
    entitlement = issue_entitlement(
        issuer_principal_digest=ISSUER,
        beneficiary_principal_digest=BENEFICIARY,
        backing_resource_id="mock-resource",
        backing_resource_fingerprint=FINGERPRINT,
        capability="code.review@1",
        action_digest=DIGEST,
        maximum_quantity=Decimal("2"),
        known_available=Decimal("2"),
        unit="turn",
        expires_at=NOW + timedelta(minutes=5),
        nonce="provider-nonce-001",
        transferability=CapacityTransferability.PROVIDER_AUTHORIZED,
        authorization=evidence,
        signature=SIGNATURE,
        issued_at=NOW,
    )
    with ReceiptStore(tmp_path / "entitlement.db") as store:
        store.save_capacity_authorization_evidence(evidence)
        store.save_execution_entitlement(entitlement)
        first = store.redeem_entitlement(
            entitlement.entitlement_id, attempt_id="attempt-1", quantity=Decimal("1"), now=NOW
        )
        assert first.status is EntitlementRedemptionStatus.PARTIAL
        assert store.redeem_entitlement(
            entitlement.entitlement_id, attempt_id="attempt-1", quantity=Decimal("1"), now=NOW
        ) == first
        second = store.redeem_entitlement(
            entitlement.entitlement_id, attempt_id="attempt-2", quantity=Decimal("1"), now=NOW
        )
        assert second.status is EntitlementRedemptionStatus.CONSUMED
        with pytest.raises(ConfigurationError, match="consumed"):
            store.redeem_entitlement(
                entitlement.entitlement_id,
                attempt_id="attempt-3",
                quantity=Decimal("1"),
                now=NOW,
            )
        assert len(store.list_entitlement_redemptions(entitlement.entitlement_id)) == 2


def test_principal_digest_is_salted_and_stable():
    assert principal_digest("principal", salt=b"one") == principal_digest(
        "principal", salt=b"one"
    )
    assert principal_digest("principal", salt=b"one") != principal_digest(
        "principal", salt=b"two"
    )
