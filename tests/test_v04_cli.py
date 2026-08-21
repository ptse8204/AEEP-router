from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from aeep.cli import app
from aeep.config import load_manifest
from aeep.economic.canonical import canonical_payload
from aeep.economic.signing import Ed25519Signer
from aeep.economic.trust import TrustedKeyStatus, TrustStore
from aeep.market_server import ReferenceMarket, example_quote_request
from aeep.models import (
    AgentBudget,
    AuthorizationPolicy,
    BillingReconciliation,
    CurrencyAmount,
    EconomicEvidenceLevel,
    MarketAggregate,
    PaymentReservationV2,
    PreparedDecisionState,
    PreparedRouteDecision,
    PreparedRouteTransition,
    ReconciliationStatus,
    SettlementReceipt,
    SettlementStatus,
)
from aeep.payments import CallbackPaymentAdapterV2
from aeep.router import Router
from aeep.store import ReceiptStore

runner = CliRunner()


def _economic_manifest(tmp_path: Path) -> tuple[Path, Path, ReferenceMarket]:
    now = datetime.now(UTC)
    market = ReferenceMarket(clock=lambda: now)
    trust_path = tmp_path / "provider-keys.json"
    TrustStore([market.trusted_key]).save(trust_path)
    database = tmp_path / "aeep.db"
    manifest = tmp_path / "aeep.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "version": "0.4",
                "database": str(database),
                "economic_evidence": {
                    "trust_store": {"path": str(trust_path)},
                },
                "executors": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return manifest, database, market


def _signed_market_aggregate(
    market: ReferenceMarket,
    *,
    now: datetime,
) -> MarketAggregate:
    unsigned = MarketAggregate(
        aggregate_id="aggregate-cli-1",
        capability=market.offer.capability,
        provider_id=market.offer.provider_id,
        executor_id=market.offer.executor_id,
        executor_fingerprint=market.executor_fingerprint,
        input_bucket="2^10",
        sample_size=20,
        window_start=now - timedelta(hours=2),
        window_end=now - timedelta(hours=1),
        actual_cost_p50=CurrencyAmount(amount="0.0038", currency="USD"),
        actual_cost_p95=CurrencyAmount(amount="0.0047", currency="USD"),
        latency_ms_p50=Decimal("12.5"),
        latency_ms_p95=Decimal("25"),
        valid_success_rate=Decimal("0.95"),
        valid_success_lower_bound=Decimal("0.86"),
        settlement_verified_fraction=Decimal("0.90"),
        billing_reconciled_fraction=Decimal("0.80"),
        generated_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(hours=1),
        signature=market.signer.sign(b""),
    )
    return unsigned.model_copy(
        update={"signature": market.signer.sign(canonical_payload(unsigned))}
    )


def _local_prepared_manifest(tmp_path: Path) -> Path:
    manifest, _, _ = _economic_manifest(tmp_path)
    value = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    value["executors"] = [
        {
            "id": "local.statistics",
            "capability": "text.statistics@1",
            "kind": "python",
            "description": "deterministic local statistics",
            "input_schema": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
            "estimate": {
                "resources": {
                    "monetary_usd": 0,
                    "latency_ms": 2,
                    "cpu_ms": 1,
                    "peak_memory_mb": 16,
                },
                "success_probability": 1,
                "quality_score": 1,
                "risk_score": 0,
                "confidence": 1,
            },
            "side_effect": "none",
            "locality": "in_process",
            "idempotent": True,
            "safe_to_auto_execute": True,
            "config": {"callable": "aeep.examples.tools:text_stats"},
        }
    ]
    manifest.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    return manifest


def test_v04_help_is_additive_and_legacy_route_quote_remain() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in (
        "offer",
        "economic",
        "settlement",
        "market",
        "run-prepared",
        "route",
        "quote",
    ):
        assert command in result.stdout


def test_new_economic_commands_default_to_human_errors_and_support_json(
    tmp_path: Path,
) -> None:
    manifest, _, _ = _economic_manifest(tmp_path)
    human = runner.invoke(app, ["offer", "show", "missing", "-m", str(manifest)])
    assert human.exit_code == 2
    assert "AEEP economic error: capability offer was not found" in human.output

    machine = runner.invoke(
        app,
        ["offer", "show", "missing", "-m", str(manifest), "--json"],
    )
    assert machine.exit_code == 2
    assert json.loads(machine.stdout)["error_type"] == "ConfigurationError"


def test_offer_import_list_show_and_verify_human_and_json(tmp_path: Path) -> None:
    manifest, database, market = _economic_manifest(tmp_path)
    offer_path = tmp_path / "offer.json"
    offer_path.write_text(market.offer.model_dump_json(indent=2), encoding="utf-8")

    imported = runner.invoke(
        app,
        ["offer", "import", str(offer_path), "-m", str(manifest), "--json"],
    )
    assert imported.exit_code == 0, imported.output
    assert json.loads(imported.stdout)["evidence_level"] == "PUBLISHED_OFFER"

    listed = runner.invoke(app, ["offer", "list", "-m", str(manifest), "--json"])
    assert listed.exit_code == 0, listed.output
    assert listed.stdout.count(market.offer.offer_id) == 1

    shown = runner.invoke(
        app,
        ["offer", "show", market.offer.offer_id, "-m", str(manifest)],
    )
    assert shown.exit_code == 0, shown.output
    assert "evidence: PUBLISHED_OFFER" in shown.stdout
    assert "PRIVATE_RESUME" not in shown.stdout

    verified = runner.invoke(
        app,
        ["offer", "verify", market.offer.offer_id, "-m", str(manifest), "--json"],
    )
    assert verified.exit_code == 0, verified.output
    assert json.loads(verified.stdout)["signature_valid"] is True

    with ReceiptStore(database) as store:
        store.revoke_provider_signing_key(
            market.trusted_key.provider_id,
            market.trusted_key.key_id,
            revoked_at=datetime.now(UTC),
        )
    revoked = runner.invoke(
        app,
        ["offer", "verify", market.offer.offer_id, "-m", str(manifest), "--json"],
    )
    assert revoked.exit_code == 1
    assert json.loads(revoked.stdout)["signature_valid"] is False


def test_configured_key_retirement_overrides_stale_active_database(tmp_path: Path) -> None:
    manifest, database, market = _economic_manifest(tmp_path)
    trust_path = tmp_path / "provider-keys.json"
    with ReceiptStore(database) as store:
        store.save_provider_signing_key(market.trusted_key)
        store.save_capability_offer(market.offer)
    TrustStore(
        [market.trusted_key.model_copy(update={"status": TrustedKeyStatus.RETIRED})]
    ).save(trust_path)

    verified = runner.invoke(
        app,
        ["offer", "verify", market.offer.offer_id, "-m", str(manifest), "--json"],
    )

    assert verified.exit_code == 1
    assert json.loads(verified.stdout)["signature_valid"] is False


def test_trust_merge_rejects_conflicting_key_material(tmp_path: Path) -> None:
    manifest, database, market = _economic_manifest(tmp_path)
    trust_path = tmp_path / "provider-keys.json"
    with ReceiptStore(database) as store:
        store.save_provider_signing_key(market.trusted_key)
        store.save_capability_offer(market.offer)
    other = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id=market.trusted_key.key_id)
    TrustStore(
        [market.trusted_key.model_copy(update={"public_key": other.public_key_base64url()})]
    ).save(trust_path)

    verified = runner.invoke(
        app,
        ["offer", "verify", market.offer.offer_id, "-m", str(manifest), "--json"],
    )

    assert verified.exit_code == 2
    assert "conflicting configured and stored metadata" in verified.stdout


def test_quote_show_and_verify_render_exact_decimal_evidence(tmp_path: Path) -> None:
    manifest, database, market = _economic_manifest(tmp_path)
    now = datetime.now(UTC)
    request = example_quote_request(now=now)
    quote = market.request_quote(request)
    with ReceiptStore(database) as store:
        store.save_provider_signing_key(market.trusted_key)
        store.save_capability_offer(market.offer)
        store.save_quote_request_v2(request)
        store.save_bounded_quote(quote)

    shown = runner.invoke(
        app,
        ["economic", "quote-show", quote.quote_id, "-m", str(manifest)],
    )
    assert shown.exit_code == 0, shown.output
    assert "expected: USD" in shown.stdout
    assert "maximum: USD" in shown.stdout
    assert "evidence: SIGNED_QUOTE" in shown.stdout

    verified = runner.invoke(
        app,
        ["economic", "quote-verify", quote.quote_id, "-m", str(manifest), "--json"],
    )
    assert verified.exit_code == 0, verified.output
    payload = json.loads(verified.stdout)
    assert payload["ok"] is True
    assert payload["binding_valid"] is True


def test_prepare_run_cancel_and_recover_use_bound_sanitized_actions(tmp_path: Path) -> None:
    manifest = _local_prepared_manifest(tmp_path)
    request_path = tmp_path / "action.json"
    private_input = "PRIVATE_CLI_ACTION_INPUT one"
    request_path.write_text(
        json.dumps(
            {
                "action_id": "action-cli-fixed",
                "capability": "text.statistics@1",
                "input": {"text": private_input},
                "policy": "balanced",
            }
        ),
        encoding="utf-8",
    )
    action = [
        "text.statistics@1",
        "--request",
        f"@{request_path}",
        "-m",
        str(manifest),
        "--json",
    ]
    prepared_result = runner.invoke(app, ["economic", "prepare", *action])
    assert prepared_result.exit_code == 0, prepared_result.output
    prepared = json.loads(prepared_result.stdout)
    assert prepared["feasible"] is True
    assert prepared["action_id"] == "action-cli-fixed"
    assert prepared["selected_executor_id"] == "local.statistics"
    assert prepared["quote_request_count"] == 0

    quote_result = runner.invoke(app, ["economic", "quote-request", *action])
    assert quote_result.exit_code == 0, quote_result.output
    quote_payload = json.loads(quote_result.stdout)
    assert quote_payload["quotes"] == []
    assert quote_payload["quote_failures"] == []

    cancelled = runner.invoke(
        app,
        [
            "economic",
            "prepared-cancel",
            prepared["prepared_id"],
            "-m",
            str(manifest),
            "--json",
        ],
    )
    assert cancelled.exit_code == 0, cancelled.output
    assert json.loads(cancelled.stdout)["state"] == "CANCELLED"

    request_without_id_path = tmp_path / "action-without-id.json"
    request_without_id_path.write_text(
        json.dumps(
            {
                "capability": "text.statistics@1",
                "input": {"text": private_input},
                "policy": "balanced",
            }
        ),
        encoding="utf-8",
    )
    executed = runner.invoke(
        app,
        [
            "run-prepared",
            quote_payload["prepared_id"],
            "--request",
            f"@{request_without_id_path}",
            "-m",
            str(manifest),
            "--json",
        ],
    )
    assert executed.exit_code == 0, executed.output
    execution_payload = json.loads(executed.stdout)
    assert execution_payload["ok"] is True
    assert execution_payload["prepared_state"] == "SETTLED"
    assert execution_payload["output_omitted"] is True
    assert execution_payload["settlements"] == []
    assert execution_payload["economic_evidence"] == ["OPERATOR_ATTESTED"]
    assert private_input not in executed.stdout

    mismatch_prepared = runner.invoke(app, ["economic", "prepare", *action])
    assert mismatch_prepared.exit_code == 0, mismatch_prepared.output
    mismatch_id = json.loads(mismatch_prepared.stdout)["prepared_id"]
    mismatched_path = tmp_path / "mismatched-action.json"
    mismatched_secret = "DIFFERENT_PRIVATE_ACTION_INPUT"
    mismatched_path.write_text(
        json.dumps(
            {
                "action_id": "different-action-id-is-rebound-locally",
                "capability": "text.statistics@1",
                "input": {"text": mismatched_secret},
                "policy": "balanced",
            }
        ),
        encoding="utf-8",
    )
    mismatch = runner.invoke(
        app,
        [
            "run-prepared",
            mismatch_id,
            "--request",
            f"@{mismatched_path}",
            "-m",
            str(manifest),
            "--json",
        ],
    )
    assert mismatch.exit_code == 2
    assert "action_id does not match" in mismatch.stdout
    assert mismatched_secret not in mismatch.stdout

    mismatched_path.write_text(
        json.dumps(
            {
                "action_id": "action-cli-fixed",
                "capability": "text.statistics@1",
                "input": {"text": mismatched_secret},
                "policy": "balanced",
            }
        ),
        encoding="utf-8",
    )
    digest_mismatch = runner.invoke(
        app,
        [
            "run-prepared",
            mismatch_id,
            "--request",
            f"@{mismatched_path}",
            "-m",
            str(manifest),
            "--json",
        ],
    )
    assert digest_mismatch.exit_code == 2
    assert "prepared action digest" in digest_mismatch.stdout
    assert mismatched_secret not in digest_mismatch.stdout

    recover_prepared = runner.invoke(app, ["economic", "prepare", *action])
    assert recover_prepared.exit_code == 0, recover_prepared.output
    recover_id = json.loads(recover_prepared.stdout)["prepared_id"]
    database = Path(yaml.safe_load(manifest.read_text(encoding="utf-8"))["database"])
    with ReceiptStore(database) as store:
        store.claim_prepared_decision(
            recover_id,
            claim_token="orphaned-cli-claim",
            claimed_at=datetime.now(UTC),
        )
    recovered = runner.invoke(
        app,
        ["economic", "recover", "-m", str(manifest), "--json"],
    )
    assert recovered.exit_code == 0, recovered.output
    recovery_payload = json.loads(recovered.stdout)
    assert recovery_payload["scanned"] == 0
    assert recovery_payload["pending_payment_operation_intents"] == 0
    assert recovery_payload["pending_refund_authorizations"] == 0
    assert recovery_payload["items"] == []
    human_recovery = runner.invoke(
        app,
        ["economic", "recover", "-m", str(manifest)],
    )
    assert human_recovery.exit_code == 0, human_recovery.output
    assert "Economic recovery" in human_recovery.stdout
    assert "scanned: 0" in human_recovery.stdout

    with ReceiptStore(database) as store:
        mismatch_stored = store.get_prepared_decision(mismatch_id)
        recovered_stored = store.get_prepared_decision(recover_id)
    assert mismatch_stored is not None
    assert mismatch_stored.state is PreparedDecisionState.PREPARED
    assert recovered_stored is not None
    assert recovered_stored.state is PreparedDecisionState.PREPARED


def test_run_prepared_keeps_action_and_payment_approvals_separate(tmp_path: Path) -> None:
    manifest = _local_prepared_manifest(tmp_path)
    value = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    value["executors"][0]["side_effect"] = "write"
    value["policies"] = {
        "write": {
            "name": "write",
            "constraints": {"max_side_effect": "write"},
        }
    }
    manifest.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    secret = "PRIVATE_CONSEQUENTIAL_CLI_INPUT"
    request_path = tmp_path / "write-action.json"
    request_path.write_text(
        json.dumps(
            {
                "action_id": "action-cli-write",
                "capability": "text.statistics@1",
                "input": {"text": secret},
                "policy": "write",
                "constraints": {"max_side_effect": "write"},
            }
        ),
        encoding="utf-8",
    )
    prepared_result = runner.invoke(
        app,
        [
            "economic",
            "prepare",
            "text.statistics@1",
            "--request",
            f"@{request_path}",
            "-m",
            str(manifest),
            "--json",
        ],
    )
    assert prepared_result.exit_code == 0, prepared_result.output
    prepared_id = json.loads(prepared_result.stdout)["prepared_id"]

    payment_only = runner.invoke(
        app,
        [
            "run-prepared",
            prepared_id,
            "--request",
            f"@{request_path}",
            "--approve-payment",
            "-m",
            str(manifest),
            "--json",
        ],
    )
    assert payment_only.exit_code == 2
    assert "requires 'write' approval" in payment_only.stdout
    assert secret not in payment_only.stdout

    action_approved = runner.invoke(
        app,
        [
            "run-prepared",
            prepared_id,
            "--request",
            f"@{request_path}",
            "--approve",
            "write",
            "-m",
            str(manifest),
        ],
    )
    assert action_approved.exit_code == 0, action_approved.output
    assert "Prepared execution" in action_approved.stdout
    assert "prepared state: SETTLED" in action_approved.stdout
    assert "result payload: omitted" in action_approved.stdout
    assert secret not in action_approved.stdout


def test_run_prepared_terminal_failure_has_meaningful_exit_without_secret(
    tmp_path: Path,
) -> None:
    manifest = _local_prepared_manifest(tmp_path)
    value = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    value["executors"][0]["config"]["callable"] = "aeep.examples.tools:always_fail"
    manifest.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    secret = "PRIVATE_FAILED_CLI_INPUT"
    request_path = tmp_path / "failed-action.json"
    request_path.write_text(
        json.dumps(
            {
                "action_id": "action-cli-failed",
                "capability": "text.statistics@1",
                "input": {"text": secret},
                "policy": "balanced",
            }
        ),
        encoding="utf-8",
    )
    prepared_result = runner.invoke(
        app,
        [
            "economic",
            "prepare",
            "text.statistics@1",
            "--request",
            f"@{request_path}",
            "-m",
            str(manifest),
            "--json",
        ],
    )
    assert prepared_result.exit_code == 0, prepared_result.output
    prepared_id = json.loads(prepared_result.stdout)["prepared_id"]
    failed = runner.invoke(
        app,
        [
            "run-prepared",
            prepared_id,
            "--request",
            f"@{request_path}",
            "-m",
            str(manifest),
            "--json",
        ],
    )
    assert failed.exit_code == 4
    payload = json.loads(failed.stdout)
    assert payload["ok"] is False
    assert payload["status"] == "failed"
    assert payload["output_omitted"] is True
    assert secret not in failed.stdout


def test_settlement_show_list_reconcile_and_economic_doctor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, database, market = _economic_manifest(tmp_path)
    now = datetime.now(UTC)
    request = example_quote_request(now=now)
    quote = market.request_quote(request)
    prepared = PreparedRouteDecision(
        prepared_id="prepared-cli-1",
        action_id=request.action_id,
        action_digest=request.action_digest,
        effective_policy_digest="sha256:" + ("a" * 64),
        selected_executor_id=quote.executor_id,
        selected_executor_fingerprint=quote.executor_fingerprint,
        selected_quote_id=quote.quote_id,
        quote_ids=(quote.quote_id,),
        maximum_cash_authorization=quote.maximum_amount,
        created_at=now,
        expires_at=quote.expires_at,
    )
    reservation = PaymentReservationV2(
        reservation_id="reservation-cli-1",
        charge_id="charge-cli-1",
        prepared_id=prepared.prepared_id,
        quote_id=quote.quote_id,
        action_id=request.action_id,
        attempt_id="attempt-cli-1",
        maximum_amount=quote.maximum_amount,
        adapter="test",
        idempotency_key="reserve-cli-1",
        created_at=now,
        updated_at=now,
    )
    settlement_key = "settle-cli-1"
    settlement_id = "settlement_" + hashlib.sha256(
        f"settlement\0{settlement_key}".encode()
    ).hexdigest()
    settlement = SettlementReceipt(
        settlement_id=settlement_id,
        charge_id="charge-cli-1",
        prepared_id="prepared-cli-1",
        quote_id=quote.quote_id,
        reservation_id="reservation-cli-1",
        attempt_id="attempt-cli-1",
        reserved_amount=quote.maximum_amount,
        captured_amount=CurrencyAmount(amount=Decimal("0.0038"), currency="USD"),
        released_amount=CurrencyAmount(
            amount=quote.maximum_amount.amount - Decimal("0.0038"), currency="USD"
        ),
        payment_rail="test",
        external_reference="PRIVATE_PAYMENT_REFERENCE_TOKEN",
        status=SettlementStatus.SETTLED,
        evidence_level=EconomicEvidenceLevel.PAYMENT_SETTLEMENT,
        settled_at=now,
    )
    with ReceiptStore(database) as store:
        store.save_provider_signing_key(market.trusted_key)
        store.save_capability_offer(market.offer)
        store.save_quote_request_v2(request)
        store.save_bounded_quote(quote)
        store.save_prepared_decision(prepared)
        claim_token = "claim-cli-1"
        store.claim_prepared_decision(
            prepared.prepared_id,
            claim_token=claim_token,
            claimed_at=now,
        )
        store.reserve_payment_v2(
            reservation,
            claim_token=claim_token,
            budget_limit=None,
            unlimited_budget=True,
        )
        assert prepared.authorization_kind is not None
        assert prepared.authorization_id is not None
        store.claim_prepared_for_paid_invocation(
            prepared.prepared_id,
            claim_token=claim_token,
            expected_action_digest=prepared.action_digest,
            expected_policy_digest=prepared.effective_policy_digest,
            expected_executor_id=prepared.selected_executor_id or "",
            expected_executor_fingerprint=(
                prepared.selected_executor_fingerprint or ""
            ),
            expected_authorization_kind=prepared.authorization_kind,
            expected_authorization_id=prepared.authorization_id,
            invoked_at=now,
        )
        store.save_prepared_transition(
            PreparedRouteTransition(
                transition_id="transition-cli-settling",
                prepared_id=prepared.prepared_id,
                from_state=PreparedDecisionState.INVOKING,
                to_state=PreparedDecisionState.SETTLING,
                occurred_at=now,
            )
        )
        store.claim_payment_settlement_v2(
            reservation.reservation_id,
            idempotency_key=settlement_key,
            updated_at=now,
        )
        store.save_settlement_receipt(settlement)

    prepared_show = runner.invoke(
        app,
        ["economic", "prepared-show", prepared.prepared_id, "-m", str(manifest)],
    )
    assert prepared_show.exit_code == 0, prepared_show.output
    assert "maximum: USD" in prepared_show.stdout
    assert "rejected: none" in prepared_show.stdout

    listed = runner.invoke(app, ["settlement", "list", "-m", str(manifest)])
    assert listed.exit_code == 0, listed.output
    assert "captured USD 0.0038; released 0.0012" in listed.stdout

    shown = runner.invoke(
        app,
        ["settlement", "show", settlement.settlement_id, "-m", str(manifest), "--json"],
    )
    assert shown.exit_code == 0, shown.output
    payload = json.loads(shown.stdout)["settlement"]
    assert payload["captured_amount"]["amount"] == "0.0038"
    assert payload["released_amount"]["amount"] == "0.0012"
    assert "PRIVATE_PAYMENT_REFERENCE_TOKEN" not in shown.stdout

    unavailable_reconciliation = runner.invoke(
        app,
        [
            "settlement",
            "reconcile",
            settlement.settlement_id,
            "-m",
            str(manifest),
            "--json",
        ],
    )
    assert unavailable_reconciliation.exit_code == 2
    assert "configured payment adapter" in unavailable_reconciliation.stdout

    callback_references: list[str] = []

    def reconcile(reference: str) -> BillingReconciliation:
        callback_references.append(reference)
        return BillingReconciliation(
            reconciliation_id="reconciliation-cli-1",
            settlement_id=reference,
            provider_id="provider.callback",
            billing_record_reference="PRIVATE_BILLING_RECORD_REFERENCE",
            expected_amount=settlement.captured_amount,
            billed_amount=CurrencyAmount(amount=Decimal("0.0040"), currency="USD"),
            discrepancy=CurrencyAmount(amount=Decimal("0.0002"), currency="USD"),
            status=ReconciliationStatus.PENDING,
            evidence_digest=f"sha256:{'b' * 64}",
            reconciled_at=now,
        )

    adapter = CallbackPaymentAdapterV2(
        "test",
        reserve=lambda *_args: None,
        settle=lambda *_args: None,
        release=lambda *_args: None,
        refund=lambda *_args: None,
        reconcile=reconcile,
        provider_id="provider.callback",
        clock=lambda: now,
    )

    def callback_router(cls: type[Router], path: str | Path | None = None) -> Router:
        manifest_model, manifest_path = load_manifest(path)
        manifest_model.budget = AgentBudget(
            daily_marketplace_limit_usd=1,
            max_per_action_usd=1,
            prepaid_balance_usd=1,
            authorization=AuthorizationPolicy(
                auto_approve_under_usd=1,
                financial_actions_require_human=False,
            ),
        )
        return cls(
            manifest_model,
            manifest_path=manifest_path,
            payment_adapter_v2=adapter,
        )

    monkeypatch.setattr(Router, "from_manifest", classmethod(callback_router))
    reconciled = runner.invoke(
        app,
        [
            "settlement",
            "reconcile",
            settlement.settlement_id,
            "-m",
            str(manifest),
            "--json",
        ],
    )
    assert reconciled.exit_code == 0, reconciled.output
    reconciliation_payload = json.loads(reconciled.stdout)
    assert reconciliation_payload["evidence_level"] == "UNKNOWN"
    assert reconciliation_payload["reconciliation"]["status"] == "PENDING"
    assert callback_references == [settlement.settlement_id]
    assert "PRIVATE_BILLING_RECORD_REFERENCE" not in reconciled.stdout
    reconciled_human = runner.invoke(
        app,
        [
            "settlement",
            "reconcile",
            settlement.settlement_id,
            "-m",
            str(manifest),
        ],
    )
    assert reconciled_human.exit_code == 0, reconciled_human.output
    assert "Billing reconciliation reconciliation-cli-1" in reconciled_human.stdout
    assert "evidence: UNKNOWN" in reconciled_human.stdout
    assert callback_references == [settlement.settlement_id]
    assert "PRIVATE_BILLING_RECORD_REFERENCE" not in reconciled_human.stdout

    doctor = runner.invoke(app, ["economic", "doctor", "-m", str(manifest), "--json"])
    assert doctor.exit_code == 0, doctor.output
    doctor_payload = json.loads(doctor.stdout)
    assert doctor_payload["remote_networking_default"] == "disabled"
    assert doctor_payload["pending_payment_operation_intents"] == 0
    assert doctor_payload["pending_refund_authorizations"] == 0


def test_offline_market_aggregate_import_list_show_and_verify(tmp_path: Path) -> None:
    manifest, database, market = _economic_manifest(tmp_path)
    aggregate = _signed_market_aggregate(market, now=datetime.now(UTC))
    unknown_unsigned = aggregate.model_copy(
        update={
            "aggregate_id": "aggregate-cli-unknown",
            "actual_cost_p50": None,
            "actual_cost_p95": None,
            "signature": market.signer.sign(b""),
        }
    )
    unknown = unknown_unsigned.model_copy(
        update={"signature": market.signer.sign(canonical_payload(unknown_unsigned))}
    )
    envelope = tmp_path / "aggregates.json"
    envelope.write_text(
        json.dumps(
            {
                "aggregates": [
                    aggregate.model_dump(mode="json"),
                    unknown.model_dump(mode="json"),
                ]
            }
        ),
        encoding="utf-8",
    )

    imported = runner.invoke(
        app,
        [
            "market",
            "aggregate-import",
            str(envelope),
            "-m",
            str(manifest),
            "--json",
        ],
    )
    assert imported.exit_code == 0, imported.output
    imported_payload = json.loads(imported.stdout)
    assert imported_payload["count"] == 2
    assert imported_payload["aggregates"][0]["aggregate_id"] == aggregate.aggregate_id
    assert imported_payload["aggregates"][0]["evidence_level"] == "STATIC_PRIOR"
    assert imported_payload["qualification_evidence"] is False
    assert imported_payload["activation_evidence"] is False

    repeated = runner.invoke(
        app,
        ["market", "aggregate-import", str(envelope), "-m", str(manifest)],
    )
    assert repeated.exit_code == 0, repeated.output
    assert "evidence: STATIC_PRIOR" in repeated.stdout

    listed = runner.invoke(
        app,
        ["market", "aggregate-list", "-m", str(manifest)],
    )
    assert listed.exit_code == 0, listed.output
    assert aggregate.aggregate_id in listed.stdout
    assert "samples 20" in listed.stdout

    shown = runner.invoke(
        app,
        [
            "market",
            "aggregate-show",
            aggregate.aggregate_id,
            "-m",
            str(manifest),
            "--json",
        ],
    )
    assert shown.exit_code == 0, shown.output
    shown_payload = json.loads(shown.stdout)
    assert shown_payload["aggregate"]["actual_cost_p50"]["amount"] == "0.0038"
    assert shown_payload["evidence_level"] == "STATIC_PRIOR"
    assert shown_payload["binding"] is False

    unknown_shown = runner.invoke(
        app,
        [
            "market",
            "aggregate-show",
            unknown.aggregate_id,
            "-m",
            str(manifest),
        ],
    )
    assert unknown_shown.exit_code == 0, unknown_shown.output
    assert "actual cost p50: unknown" in unknown_shown.stdout
    assert "actual cost p50: USD 0" not in unknown_shown.stdout

    verified = runner.invoke(
        app,
        [
            "market",
            "aggregate-verify",
            aggregate.aggregate_id,
            "-m",
            str(manifest),
            "--json",
        ],
    )
    assert verified.exit_code == 0, verified.output
    verification_payload = json.loads(verified.stdout)
    assert verification_payload["ok"] is True
    assert verification_payload["qualification_evidence"] is False

    tampered = aggregate.model_dump(mode="json")
    tampered["actual_cost_p50"]["amount"] = "0.0001"
    tampered_path = tmp_path / "tampered-aggregates.json"
    tampered_path.write_text(
        json.dumps({"aggregates": [tampered]}),
        encoding="utf-8",
    )
    rejected = runner.invoke(
        app,
        [
            "market",
            "aggregate-import",
            str(tampered_path),
            "-m",
            str(manifest),
            "--json",
        ],
    )
    assert rejected.exit_code == 2
    assert "signature" in rejected.stdout
    with ReceiptStore(database) as store:
        assert len(store.list_market_aggregates()) == 2

    oversized = tmp_path / "oversized-aggregates.json"
    oversized.write_bytes(b" " * 262_145)
    bounded = runner.invoke(
        app,
        [
            "market",
            "aggregate-import",
            str(oversized),
            "-m",
            str(manifest),
            "--json",
        ],
    )
    assert bounded.exit_code == 2
    assert "size limit" in bounded.stdout

    with ReceiptStore(database) as store:
        store.revoke_provider_signing_key(
            market.trusted_key.provider_id,
            market.trusted_key.key_id,
            revoked_at=datetime.now(UTC),
        )
    revoked = runner.invoke(
        app,
        [
            "market",
            "aggregate-verify",
            aggregate.aggregate_id,
            "-m",
            str(manifest),
            "--json",
        ],
    )
    assert revoked.exit_code == 1
    assert json.loads(revoked.stdout)["signature_valid"] is False


def test_market_serve_refuses_exposed_binding_without_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Typer reaches the guard before importing or starting uvicorn.
    monkeypatch.delenv("AEEP_REFERENCE_MARKET_TOKEN", raising=False)
    result = runner.invoke(app, ["market", "serve", "--host", "0.0.0.0"])
    assert result.exit_code != 0
    assert "without bearer token" in result.output


def test_market_serve_allows_authenticated_binding_without_advertising_wildcard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import uvicorn

    calls: list[tuple[str, int]] = []
    monkeypatch.setenv("AEEP_REFERENCE_MARKET_TOKEN", "test-market-token")
    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda _app, *, host, port, log_level: calls.append((host, port)),
    )

    result = runner.invoke(app, ["market", "serve", "--host", "0.0.0.0"])

    assert result.exit_code == 0, result.output
    assert calls == [("0.0.0.0", 8787)]
    assert "test-market-token" not in result.output


def test_campaign_prove_exits_nonzero_after_emitting_failed_report(tmp_path: Path) -> None:
    report = {
        "run_id": "run-cli-failed-proof",
        "suite_id": "suite-cli-failed-proof",
        "domain": "deterministic-cli",
        "deterministic_tools_available": True,
        "pricing_snapshot_ids": [],
        "frozen_holdout_decisions": {},
        "trials": [],
        "summaries": [],
        "baseline_deltas": [],
        "oracles": [],
        "subscription_conservation": [],
    }
    output = tmp_path / "failed-proof.json"
    result = runner.invoke(
        app,
        [
            "campaign",
            "prove",
            json.dumps([report]),
            "--baseline-route",
            "baseline",
            "--hybrid-route",
            "hybrid",
            "--output",
            str(output),
            "--compact",
        ],
    )

    assert result.exit_code == 4, result.output
    assert json.loads(result.stdout)["passed"] is False
    assert json.loads(output.read_text(encoding="utf-8"))["passed"] is False
