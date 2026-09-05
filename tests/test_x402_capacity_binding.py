from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from typer.testing import CliRunner

from aeep.capacity import (
    CapacitySignature,
    CapacityTransferability,
    capacity_digest,
    issue_entitlement,
)
from aeep.cli import app
from aeep.x402 import commit, run_local_conformance

NOW = datetime(2030, 1, 1, tzinfo=UTC)
DIGEST = capacity_digest({"fixture": True})


def self_only_entitlement():
    return issue_entitlement(
        issuer_principal_digest=DIGEST,
        beneficiary_principal_digest=DIGEST,
        backing_resource_id="openai-personal",
        backing_resource_fingerprint=DIGEST,
        capability="fixture.action@1",
        action_digest=DIGEST,
        maximum_quantity=Decimal(1),
        known_available=Decimal(1),
        unit="provider_unit",
        expires_at=NOW + timedelta(hours=1),
        nonce="self-only-nonce-0001",
        transferability=CapacityTransferability.SELF_ONLY,
        signature=CapacitySignature(
            algorithm="fixture", key_id="offline", value="signed"
        ),
        issued_at=NOW,
    )


def test_x402_is_disabled_by_default():
    with pytest.raises(ValueError, match="disabled"):
        commit(self_only_entitlement())


def test_openai_self_only_fails_before_x402_serialization():
    with pytest.raises(ValueError, match="self-only"):
        commit(self_only_entitlement(), enabled=True)


def test_local_batch_conformance_is_complete_and_offline(monkeypatch):
    import socket

    def deny_network(*_args: object, **_kwargs: object):
        raise AssertionError("offline conformance attempted network access")

    monkeypatch.setattr(socket, "create_connection", deny_network)
    report = run_local_conformance()
    by_id = {item.id: item.status for item in report.checks}
    assert report.passed
    assert by_id == {
        "beneficiary-action-binding": "PASS",
        "canonical-serialization": "PASS",
        "commitment-binding": "PASS",
        "dispute-on-overclaim": "PASS",
        "double-redemption": "PASS",
        "expiry": "PASS",
        "invalid-transferability": "PASS",
        "live-networking": "DISABLED",
        "maximum-quantity": "PASS",
        "missing-authority-evidence": "PASS",
        "offline-behavior": "PASS",
        "partial-use-release": "PASS",
        "replay": "PASS",
    }


def test_only_local_binding_exists():
    with pytest.raises(ValueError, match="only the offline"):
        run_local_conformance(binding="remote")


def test_x402_cli_emits_valid_json_report():
    result = CliRunner().invoke(
        app, ["x402", "conformance", "--binding", "aeep-local", "--json"]
    )
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("{")
    assert '"passed": true' in result.stdout
