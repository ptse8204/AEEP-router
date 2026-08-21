from __future__ import annotations

import hashlib
import importlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from threading import Barrier

import pytest

from aeep.economic import (
    Ed25519Signer,
    TrustedKeyStatus,
    TrustedProviderKey,
    canonical_payload,
    encode_base64url,
)
from aeep.errors import ConfigurationError
from aeep.models import (
    AuthorizationKind,
    AuthorizationMeterQuantity,
    BillingReconciliation,
    BillingTrigger,
    BoundedQuote,
    CapabilityOffer,
    CashAccounting,
    CashClassification,
    CashEvidence,
    CurrencyAmount,
    EconomicEvidenceLevel,
    EconomicEvidenceLink,
    EvidenceSource,
    EvidenceStatus,
    ExecutionReceipt,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    FailureChargePolicy,
    MarketAggregate,
    MeasurementEvidence,
    MeterQuantity,
    PaymentReservationState,
    PaymentReservationV2,
    PreparedDecisionState,
    PreparedRouteDecision,
    PreparedRouteTransition,
    PricingDispute,
    PricingRule,
    ProviderExecutionStatus,
    QuoteRequestV2,
    RateCardRate,
    RateCardSnapshot,
    RateType,
    ReconciliationStatus,
    RefundReceiptV2,
    ResourceAccounting,
    RetryChargePolicy,
    RouteEstimate,
    SettlementReceipt,
    SettlementStatus,
    SignatureEnvelopeV2,
    TrustLevel,
    UsageStatement,
)
from aeep.qualification import RouteCandidate, RouteLifecycle
from aeep.store import LATEST_DATABASE_SCHEMA, ReceiptStore

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
CAPABILITY = "text.statistics@1"
FINGERPRINT = f"sha256:{'a' * 64}"
ACTION_DIGEST = f"sha256:{'b' * 64}"
POLICY_DIGEST = f"sha256:{'c' * 64}"
TERMS_DIGEST = f"sha256:{'d' * 64}"
SIGNER = Ed25519Signer.from_private_bytes(bytes(range(32)), key_id="reference-key")


def _operation_result_id(prefix: str, idempotency_key: str) -> str:
    payload = prefix + "\0" + idempotency_key
    return f"{prefix}_{hashlib.sha256(payload.encode()).hexdigest()}"


SETTLEMENT_ID = _operation_result_id("settlement", "settle-reservation-1")


def _signature() -> SignatureEnvelopeV2:
    return SIGNER.sign(b"test-placeholder")


def _key() -> TrustedProviderKey:
    return TrustedProviderKey(
        provider_id="local.reference-provider",
        key_id="reference-key",
        public_key=SIGNER.public_key_base64url(),
        valid_from=NOW - timedelta(days=1),
        valid_until=NOW + timedelta(days=365),
        allowed_capabilities=(CAPABILITY,),
        allowed_quote_hosts=("quotes.example.test",),
    )


def _offer() -> CapabilityOffer:
    offer = CapabilityOffer(
        offer_id="offer-1",
        provider_id="local.reference-provider",
        capability=CAPABILITY,
        executor_id="reference.http.statistics",
        executor_fingerprint=FINGERPRINT,
        pricing_rules=(
            PricingRule(
                rule_id="fixed",
                fixed_amount=CurrencyAmount(amount="0.0010", currency="USD"),
            ),
        ),
        billing_trigger=BillingTrigger.ON_SUCCESS,
        failure_charge_policy=FailureChargePolicy.NO_CHARGE,
        retry_charge_policy=RetryChargePolicy.EACH_ATTEMPT,
        settlement_currency="USD",
        valid_from=NOW - timedelta(minutes=1),
        valid_until=NOW + timedelta(hours=1),
        terms_digest=TERMS_DIGEST,
        issued_at=NOW - timedelta(minutes=1),
        signature=_signature(),
    )
    return offer.model_copy(update={"signature": SIGNER.sign(canonical_payload(offer))})


def _quote_request() -> QuoteRequestV2:
    return QuoteRequestV2(
        quote_request_id="quote-request-1",
        action_id="action-1",
        capability=CAPABILITY,
        executor_id="reference.http.statistics",
        executor_fingerprint=FINGERPRINT,
        action_digest=ACTION_DIGEST,
        input_features={
            "input_bytes": 14_336,
            "input_items": 1,
            "text_characters": 14_336,
            "max_depth": 2,
            "size_bucket": "2^14",
        },
        disclosed_quote_features={"input_bytes": 14_336},
        desired_currency="USD",
        maximum_acceptable_amount=CurrencyAmount(amount="0.0050", currency="USD"),
        nonce="nonce-0001",
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )


def _quote() -> BoundedQuote:
    quote = BoundedQuote(
        quote_id="quote-1",
        quote_request_id="quote-request-1",
        offer_id="offer-1",
        provider_id="local.reference-provider",
        capability=CAPABILITY,
        executor_id="reference.http.statistics",
        executor_fingerprint=FINGERPRINT,
        action_digest=ACTION_DIGEST,
        nonce="nonce-0001",
        expected_amount=CurrencyAmount(amount="0.0038", currency="USD"),
        maximum_amount=CurrencyAmount(amount="0.0050", currency="USD"),
        estimated_meters=(MeterQuantity(meter="bytes", unit="byte", quantity="14336"),),
        billing_trigger=BillingTrigger.ON_SUCCESS,
        failure_charge_policy=FailureChargePolicy.NO_CHARGE,
        retry_charge_policy=RetryChargePolicy.EACH_ATTEMPT,
        terms_digest=TERMS_DIGEST,
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
        signature=_signature(),
    )
    return quote.model_copy(update={"signature": SIGNER.sign(canonical_payload(quote))})


def _prepared() -> PreparedRouteDecision:
    return PreparedRouteDecision(
        prepared_id="prepared-1",
        action_id="action-1",
        action_digest=ACTION_DIGEST,
        effective_policy_digest=POLICY_DIGEST,
        selected_executor_id="reference.http.statistics",
        selected_executor_fingerprint=FINGERPRINT,
        selected_quote_id="quote-1",
        quote_ids=("quote-1",),
        disclosed_quote_features={"input_bytes": 14_336},
        maximum_cash_authorization=CurrencyAmount(amount="0.0050", currency="USD"),
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=4),
    )


def _reservation(suffix: str = "1", amount: str = "0.0050") -> PaymentReservationV2:
    return PaymentReservationV2(
        reservation_id=f"reservation-{suffix}",
        charge_id=f"charge-{suffix}",
        prepared_id="prepared-1",
        quote_id="quote-1",
        action_id="action-1",
        attempt_id=f"attempt-{suffix}",
        maximum_amount=CurrencyAmount(amount=amount, currency="USD"),
        adapter="prepaid",
        idempotency_key=f"reserve-key-{suffix}",
        created_at=NOW,
        updated_at=NOW,
    )


def _claim_for_reservation(
    store: ReceiptStore, reservation: PaymentReservationV2
) -> str:
    token = f"claim-{reservation.prepared_id}"
    store.claim_prepared_decision(
        reservation.prepared_id,
        claim_token=token,
        claimed_at=reservation.created_at,
    )
    return token


def _settlement() -> SettlementReceipt:
    return SettlementReceipt(
        settlement_id=SETTLEMENT_ID,
        charge_id="charge-1",
        prepared_id="prepared-1",
        quote_id="quote-1",
        reservation_id="reservation-1",
        attempt_id="attempt-1",
        reserved_amount=CurrencyAmount(amount="0.0050", currency="USD"),
        captured_amount=CurrencyAmount(amount="0.0038", currency="USD"),
        released_amount=CurrencyAmount(amount="0.0012", currency="USD"),
        payment_rail="prepaid",
        status=SettlementStatus.SETTLED,
        evidence_level=EconomicEvidenceLevel.PAYMENT_SETTLEMENT,
        settled_at=NOW + timedelta(seconds=2),
    )


def _seed_quote_chain(store: ReceiptStore) -> None:
    store.save_provider_signing_key(_key())
    store.save_capability_offer(_offer())
    store.save_quote_request_v2(_quote_request())
    store.save_bounded_quote(_quote())
    store.save_prepared_decision(_prepared())


def _seed_second_quote_chain(store: ReceiptStore) -> None:
    store.save_quote_request_v2(
        _quote_request().model_copy(
            update={
                "quote_request_id": "quote-request-2",
                "action_id": "action-2",
                "nonce": "nonce-0002",
            }
        )
    )
    second_quote = _quote().model_copy(
        update={
            "quote_id": "quote-2",
            "quote_request_id": "quote-request-2",
            "nonce": "nonce-0002",
        }
    )
    store.save_bounded_quote(
        second_quote.model_copy(
            update={"signature": SIGNER.sign(canonical_payload(second_quote))}
        )
    )
    store.save_prepared_decision(
        _prepared().model_copy(
            update={
                "prepared_id": "prepared-2",
                "action_id": "action-2",
                "selected_quote_id": "quote-2",
                "authorization_id": "quote-2",
                "quote_ids": ("quote-2",),
            }
        )
    )


def _claim_paid_invocation(
    store: ReceiptStore, reservation: PaymentReservationV2
) -> None:
    prepared = store.get_prepared_decision(reservation.prepared_id)
    assert prepared is not None
    assert prepared.selected_executor_id is not None
    assert prepared.selected_executor_fingerprint is not None
    assert reservation.authorization_kind is not None
    assert reservation.authorization_id is not None
    claim_token = store._connection.execute(
        "SELECT claim_token FROM prepared_route_decisions WHERE prepared_id = ?",
        (reservation.prepared_id,),
    ).fetchone()[0]
    assert isinstance(claim_token, str)
    store.claim_prepared_for_paid_invocation(
        reservation.prepared_id,
        claim_token=claim_token,
        expected_action_digest=prepared.action_digest,
        expected_policy_digest=prepared.effective_policy_digest,
        expected_executor_id=prepared.selected_executor_id,
        expected_executor_fingerprint=prepared.selected_executor_fingerprint,
        expected_authorization_kind=reservation.authorization_kind,
        expected_authorization_id=reservation.authorization_id,
        invoked_at=NOW + timedelta(milliseconds=1),
    )


def _advance_to_settling(
    store: ReceiptStore, reservation: PaymentReservationV2
) -> PaymentReservationV2:
    _claim_paid_invocation(store, reservation)
    state = PreparedDecisionState.INVOKING
    for index, target in enumerate(
        (
            PreparedDecisionState.AWAITING_USAGE,
            PreparedDecisionState.SETTLING,
        )
    ):
        store.save_prepared_transition(
            PreparedRouteTransition(
                prepared_id=reservation.prepared_id,
                from_state=state,
                to_state=target,
                occurred_at=NOW + timedelta(milliseconds=index + 2),
            )
        )
        state = target
    return store.claim_payment_settlement_v2(
        reservation.reservation_id,
        idempotency_key=f"settle-{reservation.reservation_id}",
        updated_at=NOW + timedelta(seconds=1),
    )


def _stage_intent_free_indeterminate(
    store: ReceiptStore,
    reservation: PaymentReservationV2,
    *,
    executor_id: str,
) -> ExecutionReceipt:
    _claim_paid_invocation(store, reservation)
    state = PreparedDecisionState.INVOKING
    store.save_prepared_transition(
        PreparedRouteTransition(
            prepared_id=reservation.prepared_id,
            from_state=state,
            to_state=PreparedDecisionState.AWAITING_USAGE,
            occurred_at=NOW + timedelta(milliseconds=2),
        )
    )
    state = PreparedDecisionState.AWAITING_USAGE
    store.transition_payment_reservation_v2(
        reservation.reservation_id,
        expected_state=PaymentReservationState.RESERVED,
        updated=reservation.model_copy(
            update={
                "state": PaymentReservationState.INDETERMINATE,
                "updated_at": NOW + timedelta(seconds=2),
                "indeterminate_reason": "crash before settlement intent",
            }
        ),
    )
    for target in (
        PreparedDecisionState.INDETERMINATE,
        PreparedDecisionState.SETTLING,
    ):
        store.save_prepared_transition(
            PreparedRouteTransition(
                prepared_id=reservation.prepared_id,
                from_state=state,
                to_state=target,
                occurred_at=NOW + timedelta(seconds=2 if target is PreparedDecisionState.INDETERMINATE else 3),
            )
        )
        state = target
    assert reservation.authorization_kind is not None
    assert reservation.authorization_id is not None
    receipt = ExecutionReceipt(
        decision_id=f"decision-{reservation.prepared_id}",
        action_id=reservation.action_id,
        capability=CAPABILITY,
        executor_id=executor_id,
        executor_kind=ExecutorKind.HTTP,
        status=ExecutionStatus.SUCCESS,
        started_at=NOW,
        ended_at=NOW + timedelta(seconds=1),
        estimated=RouteEstimate(),
        metadata={
            "prepared_id": reservation.prepared_id,
            "attempt_id": reservation.attempt_id,
            "charge_id": reservation.charge_id,
            "authorization_kind": reservation.authorization_kind.value,
            "authorization_id": reservation.authorization_id,
        },
    )
    store.save_receipt(receipt)
    return receipt


def test_fresh_database_has_latest_schema_indexes_and_foreign_keys(tmp_path):
    database = tmp_path / "fresh.db"
    with ReceiptStore(database) as store:
        connection = store._connection
        assert connection.execute("PRAGMA user_version").fetchone()[0] == LATEST_DATABASE_SCHEMA
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {
            "provider_signing_keys",
            "capability_offers",
            "quote_requests_v2",
            "bounded_quotes",
            "quote_nonce_uses",
            "prepared_route_decisions",
            "prepared_route_transitions",
            "payment_reservations_v2",
            "usage_statements",
            "settlement_receipts",
            "refund_receipts_v2",
            "refund_authorizations_v2",
            "billing_reconciliations",
            "market_aggregates",
            "pricing_disputes",
            "economic_evidence_links",
            "prepared_action_idempotency",
        } <= tables
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }
        assert {
            "idx_bounded_quotes_lookup",
            "idx_prepared_route_decisions_state_expiry",
            "idx_payment_reservations_v2_prepared_state",
            "idx_market_aggregates_lookup",
            "idx_receipts_action_executor_started",
        } <= indexes
        quote_foreign_keys = {
            row[2]
            for row in connection.execute("PRAGMA foreign_key_list(bounded_quotes)").fetchall()
        }
        assert quote_foreign_keys == {"quote_requests_v2", "capability_offers"}
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_unversioned_legacy_database_migrates_without_data_loss(tmp_path):
    database = tmp_path / "legacy.db"
    connection = sqlite3.connect(database)
    connection.execute(
        """
        CREATE TABLE decisions (
            decision_id TEXT PRIMARY KEY,
            action_id TEXT NOT NULL,
            capability TEXT NOT NULL,
            created_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "INSERT INTO decisions VALUES (?, ?, ?, ?, ?)",
        ("legacy-decision", "legacy-action", "legacy@1", NOW.isoformat(), '{"legacy":true}'),
    )
    connection.commit()
    connection.close()

    with ReceiptStore(database) as store:
        row = store._connection.execute(
            "SELECT payload_json FROM decisions WHERE decision_id = 'legacy-decision'"
        ).fetchone()
        assert row[0] == '{"legacy":true}'
        assert (
            store._connection.execute("PRAGMA user_version").fetchone()[0]
            == LATEST_DATABASE_SCHEMA
        )
        assert store._connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'bounded_quotes'"
        ).fetchone()

    with ReceiptStore(database) as reopened:
        assert (
            reopened._connection.execute(
                "SELECT count(*) FROM decisions WHERE decision_id = 'legacy-decision'"
            ).fetchone()[0]
            == 1
        )


def _downgrade_economic_tables_to_intermediate_v1(database: Path) -> None:
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA foreign_keys=OFF")
    connection.executescript(
        """
        CREATE TABLE prepared_route_decisions__v1 (
            prepared_id TEXT PRIMARY KEY,
            action_id TEXT NOT NULL,
            action_digest TEXT NOT NULL,
            effective_policy_digest TEXT NOT NULL,
            selected_executor_id TEXT,
            selected_executor_fingerprint TEXT,
            selected_quote_id TEXT,
            state TEXT NOT NULL,
            claim_token TEXT UNIQUE,
            claimed_at TEXT,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            payload_digest TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            FOREIGN KEY (selected_quote_id) REFERENCES bounded_quotes(quote_id)
        );
        INSERT INTO prepared_route_decisions__v1
        SELECT prepared_id, action_id, action_digest, effective_policy_digest,
               selected_executor_id, selected_executor_fingerprint, selected_quote_id,
               state, claim_token, claimed_at, created_at, expires_at,
               payload_digest, payload_json
        FROM prepared_route_decisions;
        DROP TABLE prepared_route_decisions;
        ALTER TABLE prepared_route_decisions__v1 RENAME TO prepared_route_decisions;

        CREATE TABLE settlement_receipts__v1 (
            settlement_id TEXT PRIMARY KEY,
            charge_id TEXT NOT NULL UNIQUE,
            prepared_id TEXT NOT NULL,
            quote_id TEXT NOT NULL UNIQUE,
            reservation_id TEXT NOT NULL UNIQUE,
            attempt_id TEXT NOT NULL,
            reserved_amount TEXT NOT NULL,
            captured_amount TEXT NOT NULL,
            released_amount TEXT NOT NULL,
            currency TEXT NOT NULL,
            status TEXT NOT NULL,
            evidence_level TEXT NOT NULL,
            settled_at TEXT NOT NULL,
            payload_digest TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            FOREIGN KEY (prepared_id) REFERENCES prepared_route_decisions(prepared_id),
            FOREIGN KEY (quote_id) REFERENCES bounded_quotes(quote_id),
            FOREIGN KEY (reservation_id) REFERENCES payment_reservations_v2(reservation_id)
        );
        INSERT INTO settlement_receipts__v1
        SELECT settlement_id, charge_id, prepared_id, quote_id, reservation_id,
               attempt_id, reserved_amount, captured_amount, released_amount,
               currency, status, evidence_level, settled_at, payload_digest, payload_json
        FROM settlement_receipts;
        DROP TABLE settlement_receipts;
        ALTER TABLE settlement_receipts__v1 RENAME TO settlement_receipts;

        CREATE TABLE payment_reservations_v2__v1 (
            reservation_id TEXT PRIMARY KEY,
            charge_id TEXT NOT NULL UNIQUE,
            prepared_id TEXT NOT NULL UNIQUE,
            quote_id TEXT NOT NULL UNIQUE,
            action_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            maximum_amount TEXT NOT NULL,
            currency TEXT NOT NULL,
            adapter TEXT NOT NULL,
            state TEXT NOT NULL,
            operation_intent TEXT,
            idempotency_key TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            indeterminate_reason TEXT,
            payload_digest TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            FOREIGN KEY (prepared_id) REFERENCES prepared_route_decisions(prepared_id),
            FOREIGN KEY (quote_id) REFERENCES bounded_quotes(quote_id)
        );
        INSERT INTO payment_reservations_v2__v1
        SELECT reservation_id, charge_id, prepared_id, quote_id, action_id,
               attempt_id, maximum_amount, currency, adapter, state,
               operation_intent, idempotency_key, created_at, updated_at,
               indeterminate_reason, payload_digest, payload_json
        FROM payment_reservations_v2;
        DROP TABLE payment_reservations_v2;
        ALTER TABLE payment_reservations_v2__v1 RENAME TO payment_reservations_v2;
        PRAGMA user_version=1;
        """
    )
    connection.commit()
    connection.close()


def test_intermediate_v1_database_gets_authorization_columns_and_nullable_quote(tmp_path):
    database = tmp_path / "intermediate-v1.db"
    with ReceiptStore(database) as store:
        _seed_quote_chain(store)
        reservation = _reservation()
        store.reserve_payment_v2(
            reservation,
            claim_token=_claim_for_reservation(store, reservation),
            budget_limit=CurrencyAmount(amount="1", currency="USD"),
        )
        _advance_to_settling(store, reservation)
        store.save_settlement_receipt(_settlement())
    _downgrade_economic_tables_to_intermediate_v1(database)

    with ReceiptStore(database) as migrated:
        assert (
            migrated._connection.execute("PRAGMA user_version").fetchone()[0]
            == LATEST_DATABASE_SCHEMA
        )
        prepared = migrated.get_prepared_decision("prepared-1")
        assert prepared is not None
        assert prepared.authorization_kind is AuthorizationKind.SIGNED_QUOTE
        row = migrated._connection.execute(
            """
            SELECT authorization_kind, authorization_id, maximum_amount, currency
            FROM prepared_route_decisions WHERE prepared_id = 'prepared-1'
            """
        ).fetchone()
        assert tuple(row) == ("SIGNED_QUOTE", "quote-1", "0.0050", "USD")
        migrated_reservation = migrated.get_payment_reservation_v2("reservation-1")
        assert migrated_reservation is not None
        assert migrated_reservation.authorization_kind is AuthorizationKind.SIGNED_QUOTE
        migrated_settlement = migrated.get_settlement_receipt(SETTLEMENT_ID)
        assert migrated_settlement is not None
        assert migrated_settlement.captured_amount.amount == Decimal("0.0038")
        payment_columns = {
            column[1]: column
            for column in migrated._connection.execute(
                "PRAGMA table_info(payment_reservations_v2)"
            )
        }
        settlement_columns = {
            column[1]: column
            for column in migrated._connection.execute(
                "PRAGMA table_info(settlement_receipts)"
            )
        }
        assert payment_columns["quote_id"][3] == 0
        assert settlement_columns["quote_id"][3] == 0
        assert {"authorization_kind", "authorization_id"} <= payment_columns.keys()
        assert {"authorization_kind", "authorization_id"} <= settlement_columns.keys()
        assert migrated._connection.execute("PRAGMA foreign_key_check").fetchall() == []

    # Opening the latest schema again is an idempotent no-op.
    with ReceiptStore(database) as reopened:
        assert reopened.get_prepared_decision("prepared-1") is not None


def test_intermediate_v2_database_adds_prepared_action_idempotency_binding(tmp_path):
    database = tmp_path / "intermediate-v2.db"
    with ReceiptStore(database):
        pass

    connection = sqlite3.connect(database)
    connection.execute("DROP TABLE prepared_action_idempotency")
    connection.execute("PRAGMA user_version=2")
    connection.commit()
    connection.close()

    with ReceiptStore(database) as migrated:
        assert (
            migrated._connection.execute("PRAGMA user_version").fetchone()[0]
            == LATEST_DATABASE_SCHEMA
        )
        assert migrated._connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'prepared_action_idempotency'"
        ).fetchone()
        assert migrated._connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_failed_migration_rolls_back_as_one_transaction(tmp_path, monkeypatch):
    database = tmp_path / "rollback.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
    connection.execute("INSERT INTO sentinel VALUES ('kept')")
    connection.commit()
    connection.close()

    store_module = importlib.import_module("aeep.store")
    monkeypatch.setattr(
        store_module,
        "_V04_SCHEMA",
        ("CREATE TABLE rollback_probe (value TEXT)", "THIS IS NOT VALID SQL"),
    )
    with pytest.raises(ConfigurationError, match="cannot migrate"):
        ReceiptStore(database)

    connection = sqlite3.connect(database)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
    assert connection.execute("SELECT value FROM sentinel").fetchone()[0] == "kept"
    assert (
        connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'rollback_probe'").fetchone()
        is None
    )
    assert (
        connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'decisions'").fetchone()
        is None
    )
    connection.close()


def test_failed_v1_upgrade_rolls_back_and_retains_schema_marker(tmp_path, monkeypatch):
    database = tmp_path / "rollback-v1.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
    connection.execute("INSERT INTO sentinel VALUES ('kept')")
    connection.execute("PRAGMA user_version=1")
    connection.commit()
    connection.close()

    def fail_upgrade(connection: sqlite3.Connection) -> None:
        connection.execute("CREATE TABLE migration_probe (value TEXT)")
        connection.execute("THIS IS NOT VALID SQL")

    store_module = importlib.import_module("aeep.store")
    monkeypatch.setattr(store_module, "_migrate_v1_to_v2", fail_upgrade)
    with pytest.raises(ConfigurationError, match="cannot migrate"):
        ReceiptStore(database)

    connection = sqlite3.connect(database)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
    assert connection.execute("SELECT value FROM sentinel").fetchone()[0] == "kept"
    assert (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'migration_probe'"
        ).fetchone()
        is None
    )
    assert (
        connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'decisions'").fetchone()
        is None
    )
    connection.close()


def test_immutable_records_accept_exact_retry_and_reject_collision(tmp_path):
    with ReceiptStore(tmp_path / "immutable.db") as store:
        request = _quote_request()
        assert store.save_quote_request_v2(request) == request
        assert store.save_quote_request_v2(request) == request
        assert store.get_quote_request_v2(request.quote_request_id) == request
        row = store._connection.execute(
            "SELECT payload_digest FROM quote_requests_v2 WHERE quote_request_id = ?",
            (request.quote_request_id,),
        ).fetchone()
        assert row[0].startswith("sha256:")

        changed = request.model_copy(update={"action_id": "different-action"})
        with pytest.raises(ConfigurationError, match="different content"):
            store.save_quote_request_v2(changed)
        same_nonce = request.model_copy(
            update={"quote_request_id": "quote-request-2", "action_id": "action-2"}
        )
        with pytest.raises(ConfigurationError, match="conflicts"):
            store.save_quote_request_v2(same_nonce)


def test_nonce_use_and_prepared_transitions_are_atomic(tmp_path):
    with ReceiptStore(tmp_path / "state.db") as store:
        _seed_quote_chain(store)
        store.save_bounded_quote_and_use_nonce(_quote(), used_at=NOW)
        store.save_bounded_quote_and_use_nonce(_quote(), used_at=NOW)
        assert store.quote_nonce_was_used("nonce-0001")
        conflicting = _quote().model_copy(update={"quote_id": "quote-conflicting"})
        with pytest.raises(ConfigurationError, match="already used"):
            store.save_bounded_quote_and_use_nonce(
                conflicting, used_at=NOW + timedelta(seconds=1)
            )
        assert store.get_bounded_quote("quote-conflicting") is None
        with pytest.raises(ConfigurationError, match="already used"):
            store.mark_quote_nonce_used(
                nonce="nonce-0001",
                quote_request_id="quote-request-1",
                quote_id="quote-1",
                action_digest=ACTION_DIGEST,
                used_at=NOW,
            )

        transition = PreparedRouteTransition(
            transition_id="transition-1",
            prepared_id="prepared-1",
            from_state=PreparedDecisionState.PREPARED,
            to_state=PreparedDecisionState.CANCELLED,
            occurred_at=NOW,
        )
        store.save_prepared_transition(transition)
        store.save_prepared_transition(transition)
        assert store.get_prepared_decision("prepared-1").state is (
            PreparedDecisionState.CANCELLED
        )
        assert store.recoverable_prepared_decisions() == []


def test_quote_request_pruning_retains_requests_with_quote_evidence(tmp_path):
    with ReceiptStore(tmp_path / "prune.db") as store:
        _seed_quote_chain(store)
        unquoted = _quote_request().model_copy(
            update={
                "quote_request_id": "quote-request-unquoted",
                "action_id": "action-unquoted",
                "nonce": "nonce-unquoted",
                "created_at": NOW - timedelta(hours=2),
                "expires_at": NOW - timedelta(hours=1),
            }
        )
        store.save_quote_request_v2(unquoted)
        assert store.prune_expired_quote_requests(expired_before=NOW + timedelta(hours=1)) == 1
        assert store.get_quote_request_v2(unquoted.quote_request_id) is None
        assert store.get_quote_request_v2("quote-request-1") is not None


def test_concurrent_prepared_claim_allows_one_worker(tmp_path):
    database = tmp_path / "claims.db"
    with ReceiptStore(database) as seed:
        _seed_quote_chain(seed)
    first = ReceiptStore(database)
    second = ReceiptStore(database)
    barrier = Barrier(2)

    def claim(store: ReceiptStore, token: str) -> str:
        barrier.wait()
        return store.claim_prepared_decision(
            "prepared-1", claim_token=token, claimed_at=NOW
        ).prepared_id

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(claim, first, "worker-1"),
                executor.submit(claim, second, "worker-2"),
            ]
            results: list[str] = []
            errors: list[Exception] = []
            for future in futures:
                try:
                    results.append(future.result())
                except Exception as exc:
                    errors.append(exc)
        assert results == ["prepared-1"]
        assert len(errors) == 1 and isinstance(errors[0], ConfigurationError)
        winner = first._connection.execute(
            "SELECT claim_token FROM prepared_route_decisions WHERE prepared_id = 'prepared-1'"
        ).fetchone()[0]
        assert winner in {"worker-1", "worker-2"}
        assert (
            first.claim_prepared_decision(
                "prepared-1", claim_token=winner, claimed_at=NOW
            ).prepared_id
            == "prepared-1"
        )
    finally:
        first.close()
        second.close()


def test_atomic_decimal_budget_reservation_blocks_concurrent_overcommit(tmp_path):
    database = tmp_path / "budget.db"
    with ReceiptStore(database) as seed:
        _seed_quote_chain(seed)
        _seed_second_quote_chain(seed)
        seed.claim_prepared_decision(
            "prepared-1", claim_token="claim-prepared-1", claimed_at=NOW
        )
        seed.claim_prepared_decision(
            "prepared-2", claim_token="claim-prepared-2", claimed_at=NOW
        )
    first = ReceiptStore(database)
    second = ReceiptStore(database)
    barrier = Barrier(2)

    def reserve(store: ReceiptStore, reservation: PaymentReservationV2) -> str:
        barrier.wait()
        return store.reserve_payment_v2(
            reservation,
            claim_token=f"claim-{reservation.prepared_id}",
            budget_limit=CurrencyAmount(amount="0.0075", currency="USD"),
        ).reservation_id

    try:
        reservations = (
            _reservation("a"),
            _reservation("b").model_copy(
                update={
                    "prepared_id": "prepared-2",
                    "quote_id": "quote-2",
                    "authorization_id": "quote-2",
                    "action_id": "action-2",
                }
            ),
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(reserve, first, reservations[0]),
                executor.submit(reserve, second, reservations[1]),
            ]
            successes = 0
            failures = 0
            for future in futures:
                try:
                    future.result()
                    successes += 1
                except ConfigurationError:
                    failures += 1
        assert (successes, failures) == (1, 1)
        assert len(first.list_payment_reservations_v2()) == 1
        stored_reservation = first.list_payment_reservations_v2()[0]
        assert first.list_payment_reservations_v2(
            prepared_id=stored_reservation.prepared_id
        ) == [stored_reservation]
        assert first.list_payment_reservations_v2(prepared_id="prepared-missing") == []
        reserved = first.list_prepared_decisions(
            states=(PreparedDecisionState.RESERVED,)
        )
        assert len(reserved) == 1
        assert first.list_prepared_transitions(reserved[0].prepared_id)[-1].to_state is (
            PreparedDecisionState.RESERVED
        )
    finally:
        first.close()
        second.close()


def test_reservation_requires_the_durable_prepared_claim(tmp_path):
    with ReceiptStore(tmp_path / "claim-binding.db") as store:
        _seed_quote_chain(store)
        reservation = _reservation()
        store.claim_prepared_decision(
            reservation.prepared_id,
            claim_token="claim-owner",
            claimed_at=reservation.created_at,
        )
        assert store.recoverable_prepared_decisions() == []
        assert store.recoverable_prepared_decisions(
            as_of=NOW + timedelta(minutes=5)
        )[0].state is (
            PreparedDecisionState.PREPARED
        )
        with pytest.raises(ConfigurationError, match="atomic reserve_payment_v2"):
            store.save_payment_reservation_v2(reservation)
        with pytest.raises(ConfigurationError, match="does not own"):
            store.reserve_payment_v2(
                reservation,
                claim_token="claim-attacker",
                budget_limit=CurrencyAmount(amount="1", currency="USD"),
            )
        assert store.get_payment_reservation_v2(reservation.reservation_id) is None
        assert store.get_prepared_decision(reservation.prepared_id).state is (
            PreparedDecisionState.PREPARED
        )


def test_paid_invocation_gate_atomically_rechecks_candidate_and_signing_key(tmp_path):
    with ReceiptStore(tmp_path / "candidate-invocation-gate.db") as store:
        _seed_quote_chain(store)
        candidate = RouteCandidate(
            executor_id="reference.http.statistics",
            source_id="catalog:test",
            capability=CAPABILITY,
            behavior_fingerprint="a" * 64,
            status=RouteLifecycle.ACTIVE,
            spec=ExecutorSpec(
                id="reference.http.statistics",
                capability=CAPABILITY,
                kind=ExecutorKind.HTTP,
                description="qualified reference route",
            ),
        )
        store.save_route_candidate(candidate)
        reservation = _reservation()
        store.reserve_payment_v2(
            reservation,
            claim_token=_claim_for_reservation(store, reservation),
            budget_limit=CurrencyAmount(amount="1", currency="USD"),
        )
        store.save_route_candidate(
            candidate.model_copy(update={"status": RouteLifecycle.SUSPENDED})
        )
        with pytest.raises(ConfigurationError, match="imported route is not active"):
            _claim_paid_invocation(store, reservation)
        assert store.get_prepared_decision(reservation.prepared_id).state is (
            PreparedDecisionState.RESERVED
        )
        assert store.get_payment_reservation_v2(reservation.reservation_id).state is (
            PaymentReservationState.RESERVED
        )
        with pytest.raises(ConfigurationError, match="atomic route and trust"):
            store.save_prepared_transition(
                PreparedRouteTransition(
                    prepared_id=reservation.prepared_id,
                    from_state=PreparedDecisionState.RESERVED,
                    to_state=PreparedDecisionState.INVOKING,
                    occurred_at=NOW + timedelta(milliseconds=1),
                )
            )

    with ReceiptStore(tmp_path / "key-invocation-gate.db") as store:
        _seed_quote_chain(store)
        reservation = _reservation()
        store.reserve_payment_v2(
            reservation,
            claim_token=_claim_for_reservation(store, reservation),
            budget_limit=CurrencyAmount(amount="1", currency="USD"),
        )
        store.revoke_provider_signing_key(
            "local.reference-provider",
            "reference-key",
            revoked_at=NOW,
        )
        with pytest.raises(ConfigurationError, match="signing key is not active"):
            _claim_paid_invocation(store, reservation)
        assert store.get_prepared_decision(reservation.prepared_id).state is (
            PreparedDecisionState.RESERVED
        )
        store.claim_payment_release_v2(
            reservation.reservation_id,
            idempotency_key="key-revoked-preinvoke-release",
            updated_at=NOW + timedelta(seconds=1),
        )
        released = store.save_settlement_receipt(
            _settlement().model_copy(
                update={
                    "settlement_id": _operation_result_id(
                        "release", "key-revoked-preinvoke-release"
                    ),
                    "captured_amount": CurrencyAmount(amount=0, currency="USD"),
                    "released_amount": reservation.maximum_amount,
                    "status": SettlementStatus.RELEASED,
                }
            )
        )
        assert released.captured_amount.amount == 0
        assert released.released_amount == reservation.maximum_amount


def test_prepaid_limit_does_not_reset_with_daily_budget_window(tmp_path):
    with ReceiptStore(tmp_path / "prepaid-lifetime.db") as store:
        _seed_quote_chain(store)
        _seed_second_quote_chain(store)
        first = _reservation()
        store.reserve_payment_v2(
            first,
            claim_token=_claim_for_reservation(store, first),
            budget_limit=CurrencyAmount(amount="0.0050", currency="USD"),
            prepaid_limit=CurrencyAmount(amount="0.0075", currency="USD"),
            period_start=NOW,
        )
        _advance_to_settling(store, first)
        store.save_settlement_receipt(_settlement())
        second = _reservation("2").model_copy(
            update={
                "prepared_id": "prepared-2",
                "quote_id": "quote-2",
                "authorization_id": "quote-2",
                "action_id": "action-2",
            }
        )
        with pytest.raises(ConfigurationError, match="prepaid"):
            store.reserve_payment_v2(
                second,
                claim_token=_claim_for_reservation(store, second),
                budget_limit=CurrencyAmount(amount="0.0050", currency="USD"),
                prepaid_limit=CurrencyAmount(amount="0.0075", currency="USD"),
                period_start=NOW + timedelta(days=1),
            )
        assert store.get_payment_reservation_v2(second.reservation_id) is None


def test_daily_budget_counts_outstanding_holds_from_before_period_start(tmp_path):
    with ReceiptStore(tmp_path / "daily-outstanding-rollover.db") as store:
        _seed_quote_chain(store)
        _seed_second_quote_chain(store)
        first = _reservation()
        store.reserve_payment_v2(
            first,
            claim_token=_claim_for_reservation(store, first),
            budget_limit=CurrencyAmount(amount="1", currency="USD"),
            period_start=NOW,
        )
        second = _reservation("2").model_copy(
            update={
                "prepared_id": "prepared-2",
                "quote_id": "quote-2",
                "authorization_id": "quote-2",
                "action_id": "action-2",
                "created_at": NOW + timedelta(seconds=2),
                "updated_at": NOW + timedelta(seconds=2),
            }
        )
        with pytest.raises(ConfigurationError, match="daily budget"):
            store.reserve_payment_v2(
                second,
                claim_token=_claim_for_reservation(store, second),
                budget_limit=CurrencyAmount(amount="0.0075", currency="USD"),
                period_start=NOW + timedelta(seconds=1),
            )
        assert store.get_payment_reservation_v2(first.reservation_id).state is (
            PaymentReservationState.RESERVED
        )
        assert store.get_payment_reservation_v2(second.reservation_id) is None


def test_claimed_quote_free_invocation_requires_confirmed_zero_cash(tmp_path):
    confirmed_cash = CashAccounting(
        status=EvidenceStatus.COMPLETE,
        components=[
            CashEvidence(
                charge_id="local-free",
                amount=0,
                currency="USD",
                classification=CashClassification.VERIFIED,
                evidence=MeasurementEvidence(
                    status=EvidenceStatus.COMPLETE,
                    source=EvidenceSource.CONFIRMED_NO_INCREMENTAL_CHARGE,
                    trust=TrustLevel.VERIFIED,
                ),
            )
        ],
    )
    base = PreparedRouteDecision(
        prepared_id="prepared-free",
        action_id="action-free",
        action_digest=ACTION_DIGEST,
        effective_policy_digest=POLICY_DIGEST,
        selected_executor_id="local.free",
        selected_executor_fingerprint=FINGERPRINT,
        maximum_cash_authorization=CurrencyAmount(amount=0, currency="USD"),
        expected_accounting=ResourceAccounting(cash=confirmed_cash),
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=4),
    )
    with ReceiptStore(tmp_path / "free-invocation.db") as store:
        store.save_prepared_decision(base)
        store.claim_prepared_decision(
            base.prepared_id, claim_token="free-owner", claimed_at=NOW
        )
        invoking = store.claim_prepared_for_invocation(
            base.prepared_id,
            claim_token="free-owner",
            expected_action_digest=ACTION_DIGEST,
            expected_policy_digest=POLICY_DIGEST,
            expected_executor_fingerprint=FINGERPRINT,
            invoked_at=NOW + timedelta(seconds=1),
        )
        assert invoking.state is PreparedDecisionState.INVOKING
        assert store.get_prepared_decision(base.prepared_id).state is (
            PreparedDecisionState.INVOKING
        )
        assert store.list_payment_reservations_v2() == []

        unknown = base.model_copy(
            update={
                "prepared_id": "prepared-unknown",
                "action_id": "action-unknown",
                "expected_accounting": ResourceAccounting(),
            }
        )
        store.save_prepared_decision(unknown)
        store.claim_prepared_decision(
            unknown.prepared_id, claim_token="unknown-owner", claimed_at=NOW
        )
        with pytest.raises(ConfigurationError, match="confirmed zero"):
            store.claim_prepared_for_invocation(
                unknown.prepared_id,
                claim_token="unknown-owner",
                expected_action_digest=ACTION_DIGEST,
                expected_policy_digest=POLICY_DIGEST,
                expected_executor_fingerprint=FINGERPRINT,
                invoked_at=NOW + timedelta(seconds=1),
            )
        assert store.get_prepared_decision(unknown.prepared_id).state is (
            PreparedDecisionState.PREPARED
        )


def test_signed_offer_and_pinned_rate_card_authorize_exact_maximum(tmp_path):
    with ReceiptStore(tmp_path / "nonquote-authorization.db") as store:
        store.save_provider_signing_key(_key())
        offer = _offer()
        store.save_capability_offer(offer)
        offer_prepared = PreparedRouteDecision(
            prepared_id="prepared-offer",
            action_id="action-offer",
            action_digest=ACTION_DIGEST,
            effective_policy_digest=POLICY_DIGEST,
            selected_executor_id=offer.executor_id,
            selected_executor_fingerprint=offer.executor_fingerprint,
            selected_offer_id=offer.offer_id,
            authorization_kind=AuthorizationKind.PUBLISHED_OFFER,
            authorization_id=offer.offer_id,
            maximum_cash_authorization=CurrencyAmount(amount="0.001", currency="USD"),
            created_at=NOW,
            expires_at=NOW + timedelta(minutes=4),
        )
        store.save_prepared_decision(offer_prepared)
        store.claim_prepared_decision(
            offer_prepared.prepared_id, claim_token="offer-owner", claimed_at=NOW
        )
        offer_reservation = PaymentReservationV2(
            reservation_id="reservation-offer",
            charge_id="charge-offer",
            prepared_id=offer_prepared.prepared_id,
            authorization_kind=AuthorizationKind.PUBLISHED_OFFER,
            authorization_id=offer.offer_id,
            action_id=offer_prepared.action_id,
            attempt_id="attempt-offer",
            maximum_amount=CurrencyAmount(amount="0.001", currency="USD"),
            adapter="prepaid",
            idempotency_key="reserve-offer",
            created_at=NOW,
            updated_at=NOW,
        )
        store.reserve_payment_v2(
            offer_reservation,
            claim_token="offer-owner",
            budget_limit=CurrencyAmount(amount="1", currency="USD"),
        )
        store.revoke_capability_offer(
            offer.offer_id, revoked_at=NOW + timedelta(seconds=1)
        )
        with pytest.raises(ConfigurationError, match="offer authorization is not active"):
            store.reserve_payment_v2(
                offer_reservation,
                claim_token="offer-owner",
                budget_limit=CurrencyAmount(amount="1", currency="USD"),
            )

        snapshot = RateCardSnapshot(
            provider="operator.pinned",
            product="local-tool",
            model="fixed-v1",
            effective_from=NOW - timedelta(days=1),
            effective_until=NOW + timedelta(days=1),
            retrieved_at=NOW,
            source_uri="https://operator.example/rates.json",
            source_content_sha256="1" * 64,
            currency="USD",
            rates=[
                RateCardRate(
                    rate_id="request-rate",
                    rate_type=RateType.OTHER,
                    meter="requests",
                    input_unit="request",
                    output_unit="USD",
                    unit_quantity=1,
                    rate_amount="0.002",
                )
            ],
        )
        store.save_rate_card_snapshot(snapshot)
        rate_prepared = PreparedRouteDecision(
            prepared_id="prepared-rate",
            action_id="action-rate",
            action_digest=ACTION_DIGEST,
            effective_policy_digest=POLICY_DIGEST,
            selected_executor_id="local.rated",
            selected_executor_fingerprint=FINGERPRINT,
            selected_rate_card_id=snapshot.snapshot_id,
            authorization_kind=AuthorizationKind.PINNED_RATE_CARD,
            authorization_id=snapshot.snapshot_id,
            authorization_rate_ids=("request-rate",),
            authorization_meter_quantities=(
                AuthorizationMeterQuantity(
                    rate_id="request-rate",
                    meter="requests",
                    unit="request",
                    quantity=2,
                ),
            ),
            maximum_cash_authorization=CurrencyAmount(amount="0.004", currency="USD"),
            created_at=NOW,
            expires_at=NOW + timedelta(minutes=4),
        )
        store.save_prepared_decision(rate_prepared)
        store.claim_prepared_decision(
            rate_prepared.prepared_id, claim_token="rate-owner", claimed_at=NOW
        )
        rate_reservation = PaymentReservationV2(
            reservation_id="reservation-rate",
            charge_id="charge-rate",
            prepared_id=rate_prepared.prepared_id,
            authorization_kind=AuthorizationKind.PINNED_RATE_CARD,
            authorization_id=snapshot.snapshot_id,
            action_id=rate_prepared.action_id,
            attempt_id="attempt-rate",
            maximum_amount=CurrencyAmount(amount="0.004", currency="USD"),
            adapter="prepaid",
            idempotency_key="reserve-rate",
            created_at=NOW,
            updated_at=NOW,
        )
        store.reserve_payment_v2(
            rate_reservation,
            claim_token="rate-owner",
            budget_limit=CurrencyAmount(amount="1", currency="USD"),
        )
        _advance_to_settling(store, rate_reservation)
        rate_settlement = SettlementReceipt(
            settlement_id=_operation_result_id(
                "settlement", "settle-reservation-rate"
            ),
            charge_id=rate_reservation.charge_id,
            prepared_id=rate_prepared.prepared_id,
            authorization_kind=AuthorizationKind.PINNED_RATE_CARD,
            authorization_id=snapshot.snapshot_id,
            reservation_id=rate_reservation.reservation_id,
            attempt_id=rate_reservation.attempt_id,
            reserved_amount=CurrencyAmount(amount="0.004", currency="USD"),
            captured_amount=CurrencyAmount(amount="0.003", currency="USD"),
            released_amount=CurrencyAmount(amount="0.001", currency="USD"),
            payment_rail="prepaid",
            status=SettlementStatus.SETTLED,
            evidence_level=EconomicEvidenceLevel.PAYMENT_SETTLEMENT,
            settled_at=NOW + timedelta(seconds=2),
        )
        store.save_settlement_receipt(rate_settlement)
        assert store.get_settlement_receipt(rate_settlement.settlement_id) == rate_settlement

        conditional_snapshot = RateCardSnapshot(
            **snapshot.model_dump(exclude={"snapshot_id", "rates", "source_content_sha256"}),
            source_content_sha256="2" * 64,
            rates=[snapshot.rates[0].model_copy(update={"region": "private-tier"})],
        )
        store.save_rate_card_snapshot(conditional_snapshot)
        conditional_prepared = rate_prepared.model_copy(
            update={
                "prepared_id": "prepared-rate-conditional",
                "action_id": "action-rate-conditional",
                "selected_rate_card_id": conditional_snapshot.snapshot_id,
                "authorization_id": conditional_snapshot.snapshot_id,
                "authorization_meter_quantities": (
                    AuthorizationMeterQuantity(
                        rate_id="request-rate",
                        meter="requests",
                        unit="request",
                        quantity=1,
                    ),
                ),
                "maximum_cash_authorization": CurrencyAmount(
                    amount="0.002", currency="USD"
                ),
            }
        )
        store.save_prepared_decision(conditional_prepared)
        store.claim_prepared_decision(
            conditional_prepared.prepared_id,
            claim_token="conditional-rate-owner",
            claimed_at=NOW,
        )
        conditional_reservation = rate_reservation.model_copy(
            update={
                "reservation_id": "reservation-rate-conditional",
                "charge_id": "charge-rate-conditional",
                "prepared_id": conditional_prepared.prepared_id,
                "authorization_id": conditional_snapshot.snapshot_id,
                "action_id": conditional_prepared.action_id,
                "attempt_id": "attempt-rate-conditional",
                "maximum_amount": CurrencyAmount(amount="0.002", currency="USD"),
                "idempotency_key": "reserve-rate-conditional",
            }
        )
        with pytest.raises(ConfigurationError, match="conditional pinned rates"):
            store.reserve_payment_v2(
                conditional_reservation,
                claim_token="conditional-rate-owner",
                budget_limit=CurrencyAmount(amount="1", currency="USD"),
            )


def test_signed_offer_attempt_fee_can_define_authorized_maximum(tmp_path):
    with ReceiptStore(tmp_path / "offer-attempt-fee.db") as store:
        store.save_provider_signing_key(_key())
        unsigned = _offer().model_copy(
            update={
                "offer_id": "offer-attempt-fee",
                "failure_charge_policy": FailureChargePolicy.CHARGE_FIXED_ATTEMPT_FEE,
                "fixed_attempt_fee": CurrencyAmount(amount="0.003", currency="USD"),
            }
        )
        offer = unsigned.model_copy(
            update={"signature": SIGNER.sign(canonical_payload(unsigned))}
        )
        store.save_capability_offer(offer)
        prepared = PreparedRouteDecision(
            prepared_id="prepared-offer-attempt-fee",
            action_id="action-offer-attempt-fee",
            action_digest=ACTION_DIGEST,
            effective_policy_digest=POLICY_DIGEST,
            selected_executor_id=offer.executor_id,
            selected_executor_fingerprint=offer.executor_fingerprint,
            selected_offer_id=offer.offer_id,
            authorization_kind=AuthorizationKind.PUBLISHED_OFFER,
            authorization_id=offer.offer_id,
            maximum_cash_authorization=CurrencyAmount(amount="0.003", currency="USD"),
            created_at=NOW,
            expires_at=NOW + timedelta(minutes=4),
        )
        store.save_prepared_decision(prepared)
        reservation = PaymentReservationV2(
            reservation_id="reservation-offer-attempt-fee",
            charge_id="charge-offer-attempt-fee",
            prepared_id=prepared.prepared_id,
            authorization_kind=AuthorizationKind.PUBLISHED_OFFER,
            authorization_id=offer.offer_id,
            action_id=prepared.action_id,
            attempt_id="attempt-offer-attempt-fee",
            maximum_amount=CurrencyAmount(amount="0.003", currency="USD"),
            adapter="prepaid",
            idempotency_key="reserve-offer-attempt-fee",
            created_at=NOW,
            updated_at=NOW,
        )
        assert store.reserve_payment_v2(
            reservation,
            claim_token=_claim_for_reservation(store, reservation),
            budget_limit=CurrencyAmount(amount="1", currency="USD"),
        ) == reservation


def test_revoked_quote_signing_key_blocks_reservation(tmp_path):
    with ReceiptStore(tmp_path / "revoked-quote-key.db") as store:
        _seed_quote_chain(store)
        reservation = _reservation()
        store.claim_prepared_decision(
            reservation.prepared_id,
            claim_token="revoked-key-owner",
            claimed_at=NOW,
        )
        store.revoke_provider_signing_key(
            "local.reference-provider",
            "reference-key",
            revoked_at=NOW,
        )
        with pytest.raises(ConfigurationError, match="signing key is not active"):
            store.reserve_payment_v2(
                reservation,
                claim_token="revoked-key-owner",
                budget_limit=CurrencyAmount(amount="1", currency="USD"),
            )
        assert store.get_payment_reservation_v2(reservation.reservation_id) is None


def test_forged_quote_and_offer_cannot_authorize_a_payment_hold(tmp_path):
    with ReceiptStore(tmp_path / "forged-authorization.db") as store:
        store.save_provider_signing_key(_key())
        store.save_capability_offer(_offer())
        store.save_quote_request_v2(_quote_request())
        forged_quote = _quote().model_copy(
            update={
                "maximum_amount": CurrencyAmount(amount="0.004", currency="USD")
            }
        )
        store.save_bounded_quote(forged_quote)
        forged_prepared = _prepared().model_copy(
            update={
                "maximum_cash_authorization": CurrencyAmount(
                    amount="0.004", currency="USD"
                )
            }
        )
        store.save_prepared_decision(forged_prepared)
        forged_reservation = _reservation(amount="0.004")
        store.claim_prepared_decision(
            forged_prepared.prepared_id,
            claim_token="forged-quote-owner",
            claimed_at=NOW,
        )
        with pytest.raises(ConfigurationError, match="signature verification failed"):
            store.reserve_payment_v2(
                forged_reservation,
                claim_token="forged-quote-owner",
                budget_limit=CurrencyAmount(amount="1", currency="USD"),
            )

    with ReceiptStore(tmp_path / "forged-offer.db") as store:
        store.save_provider_signing_key(_key())
        forged_offer = _offer().model_copy(
            update={
                "offer_id": "offer-forged",
                "pricing_rules": (
                    PricingRule(
                        rule_id="forged-fixed",
                        fixed_amount=CurrencyAmount(amount="0.002", currency="USD"),
                    ),
                ),
            }
        )
        store.save_capability_offer(forged_offer)
        forged_prepared = PreparedRouteDecision(
            prepared_id="prepared-forged-offer",
            action_id="action-forged-offer",
            action_digest=ACTION_DIGEST,
            effective_policy_digest=POLICY_DIGEST,
            selected_executor_id=forged_offer.executor_id,
            selected_executor_fingerprint=forged_offer.executor_fingerprint,
            selected_offer_id=forged_offer.offer_id,
            authorization_kind=AuthorizationKind.PUBLISHED_OFFER,
            authorization_id=forged_offer.offer_id,
            maximum_cash_authorization=CurrencyAmount(amount="0.002", currency="USD"),
            created_at=NOW,
            expires_at=NOW + timedelta(minutes=4),
        )
        store.save_prepared_decision(forged_prepared)
        store.claim_prepared_decision(
            forged_prepared.prepared_id,
            claim_token="forged-offer-owner",
            claimed_at=NOW,
        )
        forged_reservation = PaymentReservationV2(
            reservation_id="reservation-forged-offer",
            charge_id="charge-forged-offer",
            prepared_id=forged_prepared.prepared_id,
            authorization_kind=AuthorizationKind.PUBLISHED_OFFER,
            authorization_id=forged_offer.offer_id,
            action_id=forged_prepared.action_id,
            attempt_id="attempt-forged-offer",
            maximum_amount=CurrencyAmount(amount="0.002", currency="USD"),
            adapter="prepaid",
            idempotency_key="reserve-forged-offer",
            created_at=NOW,
            updated_at=NOW,
        )
        with pytest.raises(ConfigurationError, match="signature verification failed"):
            store.reserve_payment_v2(
                forged_reservation,
                claim_token="forged-offer-owner",
                budget_limit=CurrencyAmount(amount="1", currency="USD"),
            )


def test_release_intent_blocks_invocation_and_settles_atomically(tmp_path):
    with ReceiptStore(tmp_path / "release-intent.db") as store:
        _seed_quote_chain(store)
        reservation = _reservation()
        store.reserve_payment_v2(
            reservation,
            claim_token=_claim_for_reservation(store, reservation),
            budget_limit=CurrencyAmount(amount="1", currency="USD"),
        )
        settling = store.claim_payment_release_v2(
            reservation.reservation_id,
            idempotency_key="release-intent-key",
            updated_at=NOW + timedelta(seconds=1),
        )
        assert settling.state is PaymentReservationState.SETTLING
        assert store.payment_reservation_operation_intent(
            reservation.reservation_id
        ) == "release:release-intent-key"
        indeterminate = settling.model_copy(
            update={
                "state": PaymentReservationState.INDETERMINATE,
                "updated_at": NOW + timedelta(milliseconds=1_200),
                "indeterminate_reason": "release rail timeout",
            }
        )
        store.transition_payment_reservation_v2(
            reservation.reservation_id,
            expected_state=PaymentReservationState.SETTLING,
            updated=indeterminate,
        )
        with pytest.raises(ConfigurationError, match="state race"):
            store.claim_payment_release_v2(
                reservation.reservation_id,
                idempotency_key="different-release-key",
                updated_at=NOW + timedelta(milliseconds=1_500),
            )
        settling = store.claim_payment_release_v2(
            reservation.reservation_id,
            idempotency_key="release-intent-key",
            updated_at=NOW + timedelta(milliseconds=1_500),
        )
        assert settling.state is PaymentReservationState.SETTLING
        with pytest.raises(ConfigurationError, match="reservation binding changed"):
            _claim_paid_invocation(store, reservation)
        released = _settlement().model_copy(
            update={
                "settlement_id": _operation_result_id(
                    "release", "release-intent-key"
                ),
                "captured_amount": CurrencyAmount(amount=0, currency="USD"),
                "released_amount": CurrencyAmount(amount="0.0050", currency="USD"),
                "status": SettlementStatus.RELEASED,
            }
        )
        store.save_settlement_receipt(released)
        assert store.get_payment_reservation_v2(reservation.reservation_id).state is (
            PaymentReservationState.RELEASED
        )
        assert store.get_prepared_decision(reservation.prepared_id).state is (
            PreparedDecisionState.RELEASED
        )
        assert store.payment_reservation_operation_intent(reservation.reservation_id) is None


def test_intent_free_indeterminate_hold_only_resumes_with_durable_settlement_evidence(
    tmp_path,
):
    with ReceiptStore(tmp_path / "indeterminate-recovery.db") as store:
        _seed_quote_chain(store)
        reservation = _reservation()
        store.reserve_payment_v2(
            reservation,
            claim_token=_claim_for_reservation(store, reservation),
            budget_limit=CurrencyAmount(amount="1", currency="USD"),
        )
        _claim_paid_invocation(store, reservation)
        state = PreparedDecisionState.INVOKING
        store.save_prepared_transition(
            PreparedRouteTransition(
                prepared_id=reservation.prepared_id,
                from_state=state,
                to_state=PreparedDecisionState.AWAITING_USAGE,
                occurred_at=NOW + timedelta(milliseconds=2),
            )
        )
        state = PreparedDecisionState.AWAITING_USAGE
        indeterminate_reservation = reservation.model_copy(
            update={
                "state": PaymentReservationState.INDETERMINATE,
                "updated_at": NOW + timedelta(seconds=2),
                "indeterminate_reason": "crash after usage capture",
            }
        )
        store.transition_payment_reservation_v2(
            reservation.reservation_id,
            expected_state=PaymentReservationState.RESERVED,
            updated=indeterminate_reservation,
        )
        store.save_prepared_transition(
            PreparedRouteTransition(
                prepared_id=reservation.prepared_id,
                from_state=PreparedDecisionState.AWAITING_USAGE,
                to_state=PreparedDecisionState.INDETERMINATE,
                occurred_at=NOW + timedelta(seconds=2),
            )
        )
        store.save_prepared_transition(
            PreparedRouteTransition(
                prepared_id=reservation.prepared_id,
                from_state=PreparedDecisionState.INDETERMINATE,
                to_state=PreparedDecisionState.SETTLING,
                occurred_at=NOW + timedelta(seconds=3),
            )
        )
        with pytest.raises(ConfigurationError, match="only resume settlement"):
            store.claim_payment_release_v2(
                reservation.reservation_id,
                idempotency_key="unsafe-release",
                updated_at=NOW + timedelta(seconds=3),
            )
        with pytest.raises(ConfigurationError, match="lacks durable execution evidence"):
            store.claim_payment_settlement_v2(
                reservation.reservation_id,
                idempotency_key="recover-settle",
                updated_at=NOW + timedelta(seconds=3),
            )

        store.save_usage_statement(
            UsageStatement(
                usage_statement_id="usage-recovery",
                quote_id="quote-1",
                prepared_id=reservation.prepared_id,
                action_id=reservation.action_id,
                attempt_id=reservation.attempt_id,
                provider_id="local.reference-provider",
                executor_id="reference.http.statistics",
                executor_fingerprint=FINGERPRINT,
                execution_status=ProviderExecutionStatus.SUCCESS,
                meters=(MeterQuantity(meter="bytes", unit="byte", quantity="14336"),),
                provider_calculated_amount=CurrencyAmount(
                    amount="0.0038", currency="USD"
                ),
                started_at=NOW,
                completed_at=NOW + timedelta(seconds=1),
                issued_at=NOW + timedelta(seconds=1),
                signature=_signature(),
            )
        )
        local_receipt = ExecutionReceipt(
            decision_id="decision-recovery",
            action_id=reservation.action_id,
            capability=CAPABILITY,
            executor_id="reference.http.statistics",
            executor_kind=ExecutorKind.HTTP,
            status=ExecutionStatus.SUCCESS,
            started_at=NOW,
            ended_at=NOW + timedelta(seconds=1),
            estimated=RouteEstimate(),
            metadata={
                "prepared_id": reservation.prepared_id,
                "attempt_id": reservation.attempt_id,
                "charge_id": reservation.charge_id,
                "authorization_kind": reservation.authorization_kind.value,
                "authorization_id": reservation.authorization_id,
            },
        )
        store.save_receipt(local_receipt)
        assert store.list_receipts_for_prepared(
            reservation.prepared_id,
            action_id=reservation.action_id,
            executor_id="reference.http.statistics",
            attempt_id=reservation.attempt_id,
            charge_id=reservation.charge_id,
        ) == [local_receipt]
        assert store.list_receipts_for_prepared(
            reservation.prepared_id,
            action_id=reservation.action_id,
            executor_id="reference.http.statistics",
            attempt_id="wrong-attempt",
            charge_id=reservation.charge_id,
        ) == []
        resumed = store.claim_payment_settlement_v2(
            reservation.reservation_id,
            idempotency_key="recover-settle",
            updated_at=NOW + timedelta(seconds=3),
        )
        assert resumed.state is PaymentReservationState.SETTLING
        assert store.payment_reservation_operation_intent(
            reservation.reservation_id
        ) == "settle:recover-settle"


def test_fixed_authorizations_resume_intent_free_indeterminate_settlement(tmp_path):
    with ReceiptStore(tmp_path / "offer-indeterminate-recovery.db") as store:
        store.save_provider_signing_key(_key())
        offer = store.save_capability_offer(_offer())
        prepared = PreparedRouteDecision(
            prepared_id="prepared-offer-recovery",
            action_id="action-offer-recovery",
            action_digest=ACTION_DIGEST,
            effective_policy_digest=POLICY_DIGEST,
            selected_executor_id=offer.executor_id,
            selected_executor_fingerprint=offer.executor_fingerprint,
            selected_offer_id=offer.offer_id,
            authorization_kind=AuthorizationKind.PUBLISHED_OFFER,
            authorization_id=offer.offer_id,
            maximum_cash_authorization=CurrencyAmount(
                amount="0.0010", currency="USD"
            ),
            created_at=NOW,
            expires_at=NOW + timedelta(minutes=4),
        )
        store.save_prepared_decision(prepared)
        reservation = PaymentReservationV2(
            reservation_id="reservation-offer-recovery",
            charge_id="charge-offer-recovery",
            prepared_id=prepared.prepared_id,
            authorization_kind=AuthorizationKind.PUBLISHED_OFFER,
            authorization_id=offer.offer_id,
            action_id=prepared.action_id,
            attempt_id="attempt-offer-recovery",
            maximum_amount=CurrencyAmount(amount="0.0010", currency="USD"),
            adapter="prepaid",
            idempotency_key="reserve-offer-recovery",
            created_at=NOW,
            updated_at=NOW,
        )
        store.reserve_payment_v2(
            reservation,
            claim_token=_claim_for_reservation(store, reservation),
            budget_limit=CurrencyAmount(amount="1", currency="USD"),
        )
        _stage_intent_free_indeterminate(
            store, reservation, executor_id=offer.executor_id
        )
        assert store.list_usage_statements(prepared_id=prepared.prepared_id) == []
        resumed = store.claim_payment_settlement_v2(
            reservation.reservation_id,
            idempotency_key="recover-offer-settle",
            updated_at=NOW + timedelta(seconds=4),
        )
        assert resumed.state is PaymentReservationState.SETTLING

    with ReceiptStore(tmp_path / "rate-indeterminate-recovery.db") as store:
        snapshot = RateCardSnapshot(
            provider="operator.pinned",
            product="local-tool",
            model="fixed-v1",
            effective_from=NOW - timedelta(days=1),
            effective_until=NOW + timedelta(days=1),
            retrieved_at=NOW,
            source_uri="https://operator.example/rates.json",
            source_content_sha256="7" * 64,
            currency="USD",
            rates=[
                RateCardRate(
                    rate_id="request-rate",
                    rate_type=RateType.OTHER,
                    meter="requests",
                    input_unit="request",
                    output_unit="USD",
                    unit_quantity=1,
                    rate_amount="0.002",
                )
            ],
        )
        store.save_rate_card_snapshot(snapshot)
        prepared = PreparedRouteDecision(
            prepared_id="prepared-rate-recovery",
            action_id="action-rate-recovery",
            action_digest=ACTION_DIGEST,
            effective_policy_digest=POLICY_DIGEST,
            selected_executor_id="local.rated",
            selected_executor_fingerprint=FINGERPRINT,
            selected_rate_card_id=snapshot.snapshot_id,
            authorization_kind=AuthorizationKind.PINNED_RATE_CARD,
            authorization_id=snapshot.snapshot_id,
            authorization_rate_ids=("request-rate",),
            authorization_meter_quantities=(
                AuthorizationMeterQuantity(
                    rate_id="request-rate",
                    meter="requests",
                    unit="request",
                    quantity=2,
                ),
            ),
            maximum_cash_authorization=CurrencyAmount(
                amount="0.004", currency="USD"
            ),
            created_at=NOW,
            expires_at=NOW + timedelta(minutes=4),
        )
        store.save_prepared_decision(prepared)
        reservation = PaymentReservationV2(
            reservation_id="reservation-rate-recovery",
            charge_id="charge-rate-recovery",
            prepared_id=prepared.prepared_id,
            authorization_kind=AuthorizationKind.PINNED_RATE_CARD,
            authorization_id=snapshot.snapshot_id,
            action_id=prepared.action_id,
            attempt_id="attempt-rate-recovery",
            maximum_amount=CurrencyAmount(amount="0.004", currency="USD"),
            adapter="prepaid",
            idempotency_key="reserve-rate-recovery",
            created_at=NOW,
            updated_at=NOW,
        )
        store.reserve_payment_v2(
            reservation,
            claim_token=_claim_for_reservation(store, reservation),
            budget_limit=CurrencyAmount(amount="1", currency="USD"),
        )
        _stage_intent_free_indeterminate(
            store, reservation, executor_id=prepared.selected_executor_id
        )
        assert store.list_usage_statements(prepared_id=prepared.prepared_id) == []
        resumed = store.claim_payment_settlement_v2(
            reservation.reservation_id,
            idempotency_key="recover-rate-settle",
            updated_at=NOW + timedelta(seconds=4),
        )
        assert resumed.state is PaymentReservationState.SETTLING


def test_settled_finalization_scan_never_requires_payment_or_provider_replay(tmp_path):
    with ReceiptStore(tmp_path / "settled-finalization.db") as store:
        _seed_quote_chain(store)
        reservation = _reservation()
        store.reserve_payment_v2(
            reservation,
            claim_token=_claim_for_reservation(store, reservation),
            budget_limit=CurrencyAmount(amount="1", currency="USD"),
        )
        _advance_to_settling(store, reservation)
        settlement = store.save_settlement_receipt(_settlement())
        assert [
            item.prepared_id
            for item in store.settled_prepared_decisions_needing_finalization()
        ] == [reservation.prepared_id]

        settlement_key = f"{reservation.prepared_id}:settle"
        assert (
            store.claim_payment_operation(
                "settle", settlement_key, f"sha256:{'f' * 64}"
            )
            is None
        )
        store.complete_payment_operation(
            "settle",
            settlement_key,
            result_type=SettlementReceipt.__name__,
            result_id=settlement.settlement_id,
        )
        store.save_economic_evidence_link(
            EconomicEvidenceLink(
                link_id="link-final-settlement",
                charge_id=reservation.charge_id,
                evidence_level=settlement.evidence_level,
                evidence_type="settlement_receipt",
                evidence_id=settlement.settlement_id,
                payload_digest=f"sha256:{'e' * 64}",
                authoritative=True,
                created_at=NOW + timedelta(seconds=3),
            )
        )
        store.save_receipt(
            ExecutionReceipt(
                decision_id="decision-wrong-attempt",
                action_id=reservation.action_id,
                capability=CAPABILITY,
                executor_id="reference.http.statistics",
                executor_kind=ExecutorKind.HTTP,
                status=ExecutionStatus.SUCCESS,
                started_at=NOW,
                ended_at=NOW + timedelta(seconds=1),
                estimated=RouteEstimate(),
                metadata={
                    "prepared_id": reservation.prepared_id,
                    "attempt_id": "wrong-attempt",
                    "charge_id": reservation.charge_id,
                    "settlement_id": settlement.settlement_id,
                },
            )
        )
        assert [
            item.prepared_id
            for item in store.settled_prepared_decisions_needing_finalization()
        ] == [reservation.prepared_id]
        store.save_receipt(
            ExecutionReceipt(
                decision_id="decision-finalized",
                action_id=reservation.action_id,
                capability=CAPABILITY,
                executor_id="reference.http.statistics",
                executor_kind=ExecutorKind.HTTP,
                status=ExecutionStatus.SUCCESS,
                started_at=NOW,
                ended_at=NOW + timedelta(seconds=1),
                estimated=RouteEstimate(),
                metadata={
                    "prepared_id": reservation.prepared_id,
                    "attempt_id": reservation.attempt_id,
                    "charge_id": reservation.charge_id,
                    "settlement_id": settlement.settlement_id,
                },
            )
        )
        assert store.settled_prepared_decisions_needing_finalization() == []

        # A complete oldest row must not consume the result limit and starve a
        # later incomplete row from recovery visibility.
        _seed_second_quote_chain(store)
        second_reservation = _reservation("2").model_copy(
            update={
                "prepared_id": "prepared-2",
                "quote_id": "quote-2",
                "authorization_id": "quote-2",
                "action_id": "action-2",
            }
        )
        store.reserve_payment_v2(
            second_reservation,
            claim_token=_claim_for_reservation(store, second_reservation),
            budget_limit=CurrencyAmount(amount="1", currency="USD"),
        )
        _advance_to_settling(store, second_reservation)
        store.save_settlement_receipt(
            _settlement().model_copy(
                update={
                    "settlement_id": _operation_result_id(
                        "settlement", "settle-reservation-2"
                    ),
                    "charge_id": second_reservation.charge_id,
                    "prepared_id": second_reservation.prepared_id,
                    "quote_id": second_reservation.quote_id,
                    "authorization_id": second_reservation.authorization_id,
                    "reservation_id": second_reservation.reservation_id,
                    "attempt_id": second_reservation.attempt_id,
                }
            )
        )
        assert [
            item.prepared_id
            for item in store.settled_prepared_decisions_needing_finalization(limit=1)
        ] == [second_reservation.prepared_id]


def test_settled_prepared_action_can_complete_durable_idempotency_after_restart(
    tmp_path,
):
    database = tmp_path / "prepared-action-idempotency.db"
    with ReceiptStore(database) as store:
        _seed_quote_chain(store)
        idempotency_key = "caller-action-key"
        claim_token = "claim-prepared-1"
        claimed = store.claim_prepared_decision_with_action_idempotency(
            "prepared-1",
            claim_token=claim_token,
            claimed_at=NOW,
            idempotency_key=idempotency_key,
            action_digest=ACTION_DIGEST,
        )
        assert claimed.prepared_id == "prepared-1"
        binding = store.get_prepared_action_idempotency("prepared-1")
        assert binding == {
            "prepared_id": "prepared-1",
            "idempotency_key": idempotency_key,
            "action_digest": ACTION_DIGEST,
            "bound_at": NOW,
        }
        assert store.claim_prepared_decision_with_action_idempotency(
            "prepared-1",
            claim_token=claim_token,
            claimed_at=NOW + timedelta(seconds=1),
            idempotency_key=idempotency_key,
            action_digest=ACTION_DIGEST,
        ).prepared_id == "prepared-1"
        store.mark_idempotency_executing(idempotency_key)

        reservation = _reservation()
        store.reserve_payment_v2(
            reservation,
            claim_token=claim_token,
            budget_limit=CurrencyAmount(amount="1", currency="USD"),
        )
        _advance_to_settling(store, reservation)
        settlement = store.save_settlement_receipt(_settlement())
        receipt = ExecutionReceipt(
            decision_id="decision-action-recovery",
            action_id=reservation.action_id,
            capability=CAPABILITY,
            executor_id="reference.http.statistics",
            executor_kind=ExecutorKind.HTTP,
            status=ExecutionStatus.SUCCESS,
            started_at=NOW,
            ended_at=NOW + timedelta(seconds=1),
            estimated=RouteEstimate(),
            metadata={
                "prepared_id": reservation.prepared_id,
                "attempt_id": reservation.attempt_id,
                "charge_id": reservation.charge_id,
                "settlement_id": settlement.settlement_id,
            },
        )
        store.save_receipt(receipt)
        store.mark_idempotency_indeterminate(idempotency_key)
        settlement_key = "prepared-1:settle"
        assert (
            store.claim_payment_operation(
                "settle", settlement_key, f"sha256:{'8' * 64}"
            )
            is None
        )
        store.complete_payment_operation(
            "settle",
            settlement_key,
            result_type=SettlementReceipt.__name__,
            result_id=settlement.settlement_id,
        )
        store.save_economic_evidence_link(
            EconomicEvidenceLink(
                link_id="link-action-recovery-settlement",
                charge_id=reservation.charge_id,
                evidence_level=settlement.evidence_level,
                evidence_type="settlement_receipt",
                evidence_id=settlement.settlement_id,
                payload_digest=f"sha256:{'7' * 64}",
                authoritative=True,
                created_at=NOW + timedelta(seconds=3),
            )
        )
        assert [
            item.prepared_id
            for item in store.settled_prepared_decisions_needing_finalization()
        ] == [reservation.prepared_id]

    with ReceiptStore(database) as recovered:
        recovered.complete_prepared_action_idempotency(
            "prepared-1",
            action_digest=ACTION_DIGEST,
            decision_id=receipt.decision_id,
            status=receipt.status.value,
            receipt_id=receipt.receipt_id,
        )
        assert recovered.settled_prepared_decisions_needing_finalization() == []
        duplicate = recovered.claim_idempotency(idempotency_key, ACTION_DIGEST)
        assert duplicate == {
            "state": "complete",
            "decision_id": receipt.decision_id,
            "status": receipt.status.value,
            "receipt_ids": [receipt.receipt_id],
        }
        recovered.complete_prepared_action_idempotency(
            "prepared-1",
            action_digest=ACTION_DIGEST,
            decision_id=receipt.decision_id,
            status=receipt.status.value,
            receipt_id=receipt.receipt_id,
        )
        with pytest.raises(ConfigurationError, match="digest does not match"):
            recovered.bind_prepared_action_idempotency(
                "prepared-1",
                idempotency_key=idempotency_key,
                action_digest=POLICY_DIGEST,
                bound_at=NOW,
            )
        stored_fields = recovered._connection.execute(
            "SELECT prepared_id, idempotency_key, action_digest FROM prepared_action_idempotency"
        ).fetchone()
        assert tuple(stored_fields) == (
            "prepared-1",
            idempotency_key,
            ACTION_DIGEST,
        )


def test_atomic_prepared_action_claim_rolls_back_and_abandons_without_invocation(
    tmp_path,
):
    with ReceiptStore(tmp_path / "atomic-action-claim.db") as store:
        _seed_quote_chain(store)
        store._connection.execute(
            """
            CREATE TRIGGER fail_prepared_action_binding
            BEFORE INSERT ON prepared_action_idempotency
            BEGIN
                SELECT RAISE(ABORT, 'prepared action binding failpoint');
            END
            """
        )
        with pytest.raises(ConfigurationError, match="atomic prepared action claim"):
            store.claim_prepared_decision_with_action_idempotency(
                "prepared-1",
                claim_token="atomic-owner",
                claimed_at=NOW,
                idempotency_key="atomic-action-key",
                action_digest=ACTION_DIGEST,
            )
        assert store._connection.execute(
            "SELECT 1 FROM idempotency_records WHERE idempotency_key = 'atomic-action-key'"
        ).fetchone() is None
        assert store.get_prepared_action_idempotency("prepared-1") is None
        assert store._connection.execute(
            "SELECT claim_token FROM prepared_route_decisions WHERE prepared_id = 'prepared-1'"
        ).fetchone()[0] is None

        store._connection.execute("DROP TRIGGER fail_prepared_action_binding")
        store.claim_prepared_decision_with_action_idempotency(
            "prepared-1",
            claim_token="atomic-owner",
            claimed_at=NOW,
            idempotency_key="atomic-action-key",
            action_digest=ACTION_DIGEST,
        )
        assert store.recoverable_prepared_decisions() == []
        assert [
            item.prepared_id
            for item in store.recoverable_prepared_decisions(
                as_of=NOW + timedelta(minutes=5)
            )
        ] == ["prepared-1"]
        with pytest.raises(ConfigurationError, match="live prepared action"):
            store.abandon_prepared_action_idempotency(
                "prepared-1",
                action_digest=ACTION_DIGEST,
                abandoned_at=NOW + timedelta(seconds=1),
            )
        cancelled = store.abandon_prepared_action_idempotency(
            "prepared-1",
            action_digest=ACTION_DIGEST,
            abandoned_at=NOW + timedelta(seconds=1),
            claim_token="atomic-owner",
        )
        assert cancelled.state is PreparedDecisionState.CANCELLED
        assert store.get_prepared_action_idempotency("prepared-1") is None
        assert store._connection.execute(
            "SELECT 1 FROM idempotency_records WHERE idempotency_key = 'atomic-action-key'"
        ).fetchone() is None
        with pytest.raises(ConfigurationError, match="atomic prepared claim"):
            store.bind_prepared_action_idempotency(
                "prepared-1",
                idempotency_key="standalone-key",
                action_digest=ACTION_DIGEST,
                bound_at=NOW,
            )


def test_confirmed_free_indeterminate_action_finalizes_without_reinvocation(tmp_path):
    database = tmp_path / "free-action-recovery.db"
    confirmed_cash = CashAccounting(
        status=EvidenceStatus.COMPLETE,
        components=[
            CashEvidence(
                charge_id="local-free-recovery",
                amount=0,
                currency="USD",
                classification=CashClassification.VERIFIED,
                evidence=MeasurementEvidence(
                    status=EvidenceStatus.COMPLETE,
                    source=EvidenceSource.CONFIRMED_NO_INCREMENTAL_CHARGE,
                    trust=TrustLevel.VERIFIED,
                ),
            )
        ],
    )
    prepared = PreparedRouteDecision(
        prepared_id="prepared-free-recovery",
        action_id="action-free-recovery",
        action_digest=ACTION_DIGEST,
        effective_policy_digest=POLICY_DIGEST,
        selected_executor_id="local.free",
        selected_executor_fingerprint=FINGERPRINT,
        maximum_cash_authorization=CurrencyAmount(amount=0, currency="USD"),
        expected_accounting=ResourceAccounting(cash=confirmed_cash),
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=4),
    )
    with ReceiptStore(database) as store:
        store.save_prepared_decision(prepared)
        store.claim_prepared_decision_with_action_idempotency(
            prepared.prepared_id,
            claim_token="free-recovery-owner",
            claimed_at=NOW,
            idempotency_key="free-recovery-action-key",
            action_digest=ACTION_DIGEST,
        )
        store.claim_prepared_for_invocation(
            prepared.prepared_id,
            claim_token="free-recovery-owner",
            expected_action_digest=ACTION_DIGEST,
            expected_policy_digest=POLICY_DIGEST,
            expected_executor_fingerprint=FINGERPRINT,
            invoked_at=NOW + timedelta(seconds=1),
        )
        store.mark_idempotency_executing("free-recovery-action-key")
        receipt = ExecutionReceipt(
            decision_id="decision-free-recovery",
            action_id=prepared.action_id,
            capability=CAPABILITY,
            executor_id="local.free",
            executor_kind=ExecutorKind.COMMAND,
            status=ExecutionStatus.SUCCESS,
            started_at=NOW + timedelta(seconds=1),
            ended_at=NOW + timedelta(seconds=2),
            estimated=RouteEstimate(),
            metadata={
                "prepared_id": prepared.prepared_id,
                "attempt_id": "attempt-free-recovery",
                "charge_id": "charge-free-recovery",
            },
        )
        store.save_receipt(receipt)
        store.save_prepared_transition(
            PreparedRouteTransition(
                prepared_id=prepared.prepared_id,
                from_state=PreparedDecisionState.INVOKING,
                to_state=PreparedDecisionState.INDETERMINATE,
                occurred_at=NOW + timedelta(seconds=3),
                reason="simulated crash before free accounting transition",
            )
        )
        store.mark_idempotency_indeterminate("free-recovery-action-key")

    with ReceiptStore(database) as recovered:
        assert recovered.list_receipts_for_prepared_action(
            prepared.prepared_id,
            action_id=prepared.action_id,
            executor_id="local.free",
        ) == [receipt]
        pending = recovered.free_actions_needing_finalization()
        assert pending == [
            {
                "prepared_id": prepared.prepared_id,
                "action_digest": ACTION_DIGEST,
                "receipt_id": receipt.receipt_id,
                "decision_id": receipt.decision_id,
                "status": receipt.status.value,
            }
        ]
        settled = recovered.settle_recovered_free_prepared(
            prepared.prepared_id,
            receipt_id=receipt.receipt_id,
            recovered_at=NOW + timedelta(seconds=4),
        )
        assert settled.state is PreparedDecisionState.SETTLED
        recovered.complete_prepared_action_idempotency(
            prepared.prepared_id,
            action_digest=ACTION_DIGEST,
            decision_id=receipt.decision_id,
            status=receipt.status.value,
            receipt_id=receipt.receipt_id,
        )
        assert recovered.free_actions_needing_finalization() == []
        with pytest.raises(ConfigurationError, match="receipt is immutable"):
            recovered.save_receipt(
                receipt.model_copy(update={"error_message": "late mutation"})
            )


def test_released_payment_operation_finalizes_locally_without_replaying_rail(tmp_path):
    with ReceiptStore(tmp_path / "release-finalization.db") as store:
        _seed_quote_chain(store)
        store.claim_prepared_decision_with_action_idempotency(
            "prepared-1",
            claim_token="release-action-owner",
            claimed_at=NOW,
            idempotency_key="release-action-key",
            action_digest=ACTION_DIGEST,
        )
        reservation = _reservation()
        store.reserve_payment_v2(
            reservation,
            claim_token="release-action-owner",
            budget_limit=CurrencyAmount(amount="1", currency="USD"),
        )
        release_key = "prepared-1:recover-release"
        request_digest = f"sha256:{'9' * 64}"
        assert store.claim_payment_operation("release", release_key, request_digest) is None
        store.mark_payment_operation_executing("release", release_key)
        store.claim_payment_release_v2(
            reservation.reservation_id,
            idempotency_key=release_key,
            updated_at=NOW + timedelta(seconds=1),
        )
        settlement_id = "release_" + hashlib.sha256(
            f"release\0{release_key}".encode()
        ).hexdigest()
        settlement = store.save_settlement_receipt(
            _settlement().model_copy(
                update={
                    "settlement_id": settlement_id,
                    "captured_amount": CurrencyAmount(amount="0.0000", currency="USD"),
                    "released_amount": CurrencyAmount(amount="0.0050", currency="USD"),
                    "status": SettlementStatus.RELEASED,
                }
            )
        )
        assert store.released_payment_operations_needing_finalization() == [
            {
                "prepared_id": reservation.prepared_id,
                "reservation_id": reservation.reservation_id,
                "settlement_id": settlement.settlement_id,
                "operation": "release",
                "idempotency_key": release_key,
                "request_digest": request_digest,
            }
        ]
        assert [
            item.prepared_id
            for item in store.released_prepared_actions_needing_abandonment()
        ] == [reservation.prepared_id]
        store.complete_payment_operation(
            "release",
            release_key,
            result_type=SettlementReceipt.__name__,
            result_id=settlement.settlement_id,
        )
        assert store.released_payment_operations_needing_finalization() == []
        assert [
            item.prepared_id
            for item in store.released_prepared_actions_needing_abandonment()
        ] == [reservation.prepared_id]
        released = store.abandon_prepared_action_idempotency(
            reservation.prepared_id,
            action_digest=ACTION_DIGEST,
            abandoned_at=NOW + timedelta(seconds=3),
        )
        assert released.state is PreparedDecisionState.RELEASED
        assert store.released_prepared_actions_needing_abandonment() == []


def test_refund_authorization_blocks_cross_process_over_refund(tmp_path):
    database = tmp_path / "refund-authorization.db"
    with ReceiptStore(database) as seed:
        _seed_quote_chain(seed)
        reservation = _reservation()
        seed.reserve_payment_v2(
            reservation,
            claim_token=_claim_for_reservation(seed, reservation),
            budget_limit=CurrencyAmount(amount="1", currency="USD"),
        )
        _advance_to_settling(seed, reservation)
        seed.save_settlement_receipt(_settlement())
    first = ReceiptStore(database)
    second = ReceiptStore(database)
    barrier = Barrier(2)

    def authorize(store: ReceiptStore, suffix: str):
        barrier.wait()
        return store.authorize_refund_v2(
            refund_id=f"refund-{suffix}",
            settlement_id=SETTLEMENT_ID,
            amount=CurrencyAmount(amount="0.003", currency="USD"),
            idempotency_key=f"refund-key-{suffix}",
            request_digest=f"sha256:{suffix * 64}",
            authorized_at=NOW + timedelta(seconds=3),
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(authorize, first, "a"),
                executor.submit(authorize, second, "b"),
            ]
            records = []
            errors = []
            for future in futures:
                try:
                    records.append(future.result())
                except ConfigurationError as exc:
                    errors.append(exc)
        assert len(records) == 1
        assert len(errors) == 1
        record = records[0]
        assert len(first.pending_refund_authorizations_v2()) == 1
        receipt = RefundReceiptV2(
            refund_id=record["refund_id"],
            settlement_id=record["settlement_id"],
            charge_id=record["charge_id"],
            amount=record["amount"],
            reason="operator correction",
            idempotency_key=record["idempotency_key"],
            refunded_at=NOW + timedelta(seconds=4),
        )
        first.complete_refund_v2(receipt)
        assert first.get_refund_authorization_v2(record["refund_id"])["state"] == (
            "COMPLETED"
        )
        assert first.pending_refund_authorizations_v2() == []
        with pytest.raises(ConfigurationError, match="unrefunded"):
            second.authorize_refund_v2(
                refund_id="refund-too-large",
                settlement_id=SETTLEMENT_ID,
                amount=CurrencyAmount(amount="0.001", currency="USD"),
                idempotency_key="refund-key-too-large",
                request_digest=f"sha256:{'c' * 64}",
                authorized_at=NOW + timedelta(seconds=5),
            )
        remaining = second.authorize_refund_v2(
            refund_id="refund-remaining",
            settlement_id=SETTLEMENT_ID,
            amount=CurrencyAmount(amount="0.0008", currency="USD"),
            idempotency_key="refund-key-remaining",
            request_digest=f"sha256:{'d' * 64}",
            authorized_at=NOW + timedelta(seconds=5),
        )
        indeterminate = second.mark_refund_authorization_indeterminate(
            remaining["refund_id"], updated_at=NOW + timedelta(seconds=6)
        )
        assert indeterminate["state"] == "INDETERMINATE"
        released = second.release_refund_authorization_v2(
            remaining["refund_id"],
            request_digest=remaining["request_digest"],
            released_at=NOW + timedelta(seconds=7),
        )
        assert released["state"] == "RELEASED"
        assert second.pending_refund_authorizations_v2() == []
        assert second.get_refund_authorization_v2("missing-refund") is None
    finally:
        first.close()
        second.close()


def test_complete_economic_chain_round_trips_without_binary_money(tmp_path):
    with ReceiptStore(tmp_path / "chain.db") as store:
        _seed_quote_chain(store)
        reservation = _reservation()
        store.reserve_payment_v2(
            reservation,
            claim_token=_claim_for_reservation(store, reservation),
            budget_limit=CurrencyAmount(amount="1", currency="USD"),
        )
        _advance_to_settling(store, reservation)
        usage = UsageStatement(
            usage_statement_id="usage-1",
            quote_id="quote-1",
            prepared_id="prepared-1",
            action_id="action-1",
            attempt_id="attempt-1",
            provider_id="local.reference-provider",
            executor_id="reference.http.statistics",
            executor_fingerprint=FINGERPRINT,
            execution_status=ProviderExecutionStatus.SUCCESS,
            meters=(MeterQuantity(meter="bytes", unit="byte", quantity="14336"),),
            provider_calculated_amount=CurrencyAmount(amount="0.0038", currency="USD"),
            started_at=NOW,
            completed_at=NOW + timedelta(seconds=1),
            issued_at=NOW + timedelta(seconds=1),
            signature=_signature(),
        )
        store.save_usage_statement(usage)
        with pytest.raises(ConfigurationError, match="immutable usage_statements"):
            store.save_usage_statement(
                usage.model_copy(update={"usage_statement_id": "usage-conflicting"})
            )
        settlement = _settlement()
        store.save_settlement_receipt(settlement)
        assert store.get_payment_reservation_v2("reservation-1").state is (
            PaymentReservationState.SETTLED
        )
        assert store.get_prepared_decision("prepared-1").state is PreparedDecisionState.SETTLED
        reconciliation = BillingReconciliation(
            reconciliation_id="reconciliation-1",
            settlement_id=SETTLEMENT_ID,
            provider_id="local.reference-provider",
            expected_amount=CurrencyAmount(amount="0.0038", currency="USD"),
            billed_amount=CurrencyAmount(amount="0.0038", currency="USD"),
            discrepancy=CurrencyAmount(amount="0", currency="USD"),
            status=ReconciliationStatus.MATCHED,
            reconciled_at=NOW + timedelta(days=1),
        )
        store.save_billing_reconciliation(reconciliation)
        pending_reconciliation = reconciliation.model_copy(
            update={
                "reconciliation_id": "reconciliation-pending",
                "status": ReconciliationStatus.PENDING,
            }
        )
        store.save_billing_reconciliation(pending_reconciliation)
        evidence_rows = {
            row["reconciliation_id"]: row["evidence_level"]
            for row in store._connection.execute(
                """
                SELECT reconciliation_id, evidence_level
                FROM billing_reconciliations
                WHERE reconciliation_id IN (?, ?)
                """,
                (
                    reconciliation.reconciliation_id,
                    pending_reconciliation.reconciliation_id,
                ),
            )
        }
        assert evidence_rows == {
            reconciliation.reconciliation_id: "BILLING_RECONCILED",
            pending_reconciliation.reconciliation_id: "UNKNOWN",
        }
        aggregate = MarketAggregate(
            aggregate_id="aggregate-1",
            capability=CAPABILITY,
            provider_id="local.reference-provider",
            executor_id="reference.http.statistics",
            executor_fingerprint=FINGERPRINT,
            input_bucket="2^14",
            sample_size=20,
            window_start=NOW - timedelta(days=7),
            window_end=NOW,
            actual_cost_p50=CurrencyAmount(amount="0.0038", currency="USD"),
            actual_cost_p95=CurrencyAmount(amount="0.0045", currency="USD"),
            settlement_verified_fraction="1",
            billing_reconciled_fraction="1",
            generated_at=NOW,
            expires_at=NOW + timedelta(days=1),
            signature=_signature(),
        )
        store.save_market_aggregate(aggregate)
        dispute = PricingDispute(
            dispute_id="dispute-1",
            prepared_id="prepared-1",
            quote_id="quote-1",
            usage_statement_id="usage-1",
            provider_id="local.reference-provider",
            quoted_maximum=CurrencyAmount(amount="0.0050", currency="USD"),
            provider_claimed_amount=CurrencyAmount(amount="0.0060", currency="USD"),
            reason="provider claim exceeded signed quote maximum",
            created_at=NOW + timedelta(seconds=2),
        )
        store.save_pricing_dispute(dispute)
        link = EconomicEvidenceLink(
            link_id="link-1",
            charge_id="charge-1",
            evidence_level=EconomicEvidenceLevel.PAYMENT_SETTLEMENT,
            evidence_type="settlement",
            evidence_id=SETTLEMENT_ID,
            payload_digest=f"sha256:{'e' * 64}",
            authoritative=True,
            created_at=NOW + timedelta(seconds=2),
        )
        store.save_economic_evidence_link(link)

        assert store.get_usage_statement("usage-1") == usage
        assert store.get_settlement_receipt(SETTLEMENT_ID) == settlement
        assert store.get_billing_reconciliation("reconciliation-1") == reconciliation
        assert store.get_market_aggregate("aggregate-1") == aggregate
        assert store.get_pricing_dispute("dispute-1") == dispute
        assert store.get_economic_evidence_link("link-1") == link
        payloads = " ".join(
            row[0]
            for table in (
                "bounded_quotes",
                "payment_reservations_v2",
                "settlement_receipts",
                "billing_reconciliations",
            )
            for row in store._connection.execute(f"SELECT payload_json FROM {table}")
        )
        assert '"0.0038"' in payloads
        assert "0.003799999" not in payloads


def test_settlement_binding_rejects_amount_above_signed_quote_maximum(tmp_path):
    with ReceiptStore(tmp_path / "overcapture.db") as store:
        _seed_quote_chain(store)
        reservation = _reservation()
        store.reserve_payment_v2(
            reservation,
            claim_token=_claim_for_reservation(store, reservation),
            budget_limit=CurrencyAmount(amount="1", currency="USD"),
        )
        _advance_to_settling(store, reservation)
        overcapture = _settlement().model_copy(
            update={
                "reserved_amount": CurrencyAmount(amount="0.0060", currency="USD"),
                "captured_amount": CurrencyAmount(amount="0.0060", currency="USD"),
                "released_amount": CurrencyAmount(amount="0", currency="USD"),
            }
        )
        with pytest.raises(ConfigurationError, match="signed quote maximum"):
            store.save_settlement_receipt(overcapture)
        assert store.get_settlement_receipt(SETTLEMENT_ID) is None
        assert store.get_payment_reservation_v2("reservation-1").state is (
            PaymentReservationState.SETTLING
        )
        assert store.get_prepared_decision("prepared-1").state is (PreparedDecisionState.SETTLING)


def test_settlement_id_must_match_exact_claimed_operation_intent(tmp_path):
    with ReceiptStore(tmp_path / "settlement-intent-binding.db") as store:
        _seed_quote_chain(store)
        reservation = _reservation()
        store.reserve_payment_v2(
            reservation,
            claim_token=_claim_for_reservation(store, reservation),
            budget_limit=CurrencyAmount(amount="1", currency="USD"),
        )
        _advance_to_settling(store, reservation)
        mismatched = _settlement().model_copy(
            update={
                "settlement_id": _operation_result_id(
                    "settlement", "unrelated-settlement-key"
                )
            }
        )
        with pytest.raises(ConfigurationError, match="claimed payment operation"):
            store.save_settlement_receipt(mismatched)
        assert store.get_settlement_receipt(mismatched.settlement_id) is None
        assert store.get_payment_reservation_v2(reservation.reservation_id).state is (
            PaymentReservationState.SETTLING
        )


def test_revocations_overlay_immutable_payloads(tmp_path):
    with ReceiptStore(tmp_path / "revocation.db") as store:
        key = _key()
        offer = _offer()
        store.save_provider_signing_key(key)
        store.save_capability_offer(offer)
        revoked_at = NOW + timedelta(minutes=1)
        revoked = store.revoke_provider_signing_key(
            key.provider_id, key.key_id, revoked_at=revoked_at
        )
        assert revoked.status is TrustedKeyStatus.REVOKED
        assert store.get_provider_signing_key(key.provider_id, key.key_id).status is (
            TrustedKeyStatus.REVOKED
        )
        store.revoke_capability_offer(offer.offer_id, revoked_at=revoked_at)
        assert store.get_capability_offer(offer.offer_id) is None
        assert store.get_capability_offer(offer.offer_id, include_revoked=True) == offer
        assert store.list_capability_offers() == []
        rotated = key.model_copy(
            update={
                "key_id": "reference-key-rotated",
                "public_key": encode_base64url(bytes(reversed(range(32)))),
            }
        )
        store.save_provider_signing_key(rotated)
        retired = store.retire_provider_signing_key(
            rotated.provider_id, rotated.key_id
        )
        assert retired.status is TrustedKeyStatus.RETIRED
        assert (
            store.retire_provider_signing_key(rotated.provider_id, rotated.key_id).status
            is TrustedKeyStatus.RETIRED
        )


def test_raw_action_input_is_absent_and_payment_operation_is_durable(tmp_path):
    secret = "DO-NOT-PERSIST-RESUME-TEXT"
    with ReceiptStore(tmp_path / "sanitized.db") as store:
        _seed_quote_chain(store)
        stored = " ".join(
            row[0]
            for table in (
                "quote_requests_v2",
                "bounded_quotes",
                "prepared_route_decisions",
            )
            for row in store._connection.execute(f"SELECT payload_json FROM {table}")
        )
        assert secret not in stored
        assert store.claim_payment_operation("settle", "settle-key", ACTION_DIGEST) is None
        duplicate = store.claim_payment_operation("settle", "settle-key", ACTION_DIGEST)
        assert duplicate is not None and duplicate["state"] == "claimed"
        with pytest.raises(ConfigurationError, match="different action"):
            store.claim_payment_operation("settle", "settle-key", POLICY_DIGEST)
        store.complete_payment_operation(
            "settle",
            "settle-key",
            result_type="SettlementReceipt",
            result_id="settlement-1",
        )
        operation = store.get_payment_operation("settle", "settle-key")
        assert operation is not None and operation["result_ids"] == ["settlement-1"]
        store.complete_payment_operation(
            "settle",
            "settle-key",
            result_type="SettlementReceipt",
            result_id="settlement-1",
        )
        with pytest.raises(ConfigurationError, match="conflicts"):
            store.complete_payment_operation(
                "settle",
                "settle-key",
                result_type="SettlementReceipt",
                result_id="settlement-different",
            )
        assert store.claim_payment_operation(
            "release", "release-recovery-key", ACTION_DIGEST
        ) is None
        store.mark_payment_operation_executing("release", "release-recovery-key")
        store.mark_payment_operation_indeterminate("release", "release-recovery-key")
        assert store.get_payment_operation("release", "release-recovery-key")["state"] == (
            "indeterminate"
        )
        store.mark_payment_operation_executing("release", "release-recovery-key")
        store.mark_payment_operation_indeterminate("release", "release-recovery-key")
        store.complete_payment_operation(
            "release",
            "release-recovery-key",
            result_type="SettlementReceipt",
            result_id="release-settlement",
        )


def test_refund_receipt_v2_is_immutable_and_idempotent(tmp_path):
    with ReceiptStore(tmp_path / "refund.db") as store:
        _seed_quote_chain(store)
        _seed_second_quote_chain(store)
        reservation = _reservation()
        store.reserve_payment_v2(
            reservation,
            claim_token=_claim_for_reservation(store, reservation),
            budget_limit=CurrencyAmount(amount="1", currency="USD"),
        )
        _advance_to_settling(store, reservation)
        store.save_settlement_receipt(_settlement())
        refund = RefundReceiptV2(
            refund_id="refund-1",
            settlement_id=SETTLEMENT_ID,
            charge_id="charge-1",
            amount=CurrencyAmount(amount="0.001", currency="USD"),
            reason="operator correction",
            idempotency_key="refund-key",
            refunded_at=NOW,
        )
        store.save_refund_receipt_v2(refund)
        store.save_refund_receipt_v2(refund)
        assert store.get_refund_receipt_v2("refund-1") == refund
        second = _reservation("2").model_copy(
            update={
                "prepared_id": "prepared-2",
                "quote_id": "quote-2",
                "authorization_id": "quote-2",
                "action_id": "action-2",
            }
        )
        assert (
            store.reserve_payment_v2(
                second,
                claim_token=_claim_for_reservation(store, second),
                budget_limit=CurrencyAmount(amount="0.0078", currency="USD"),
            )
            == second
        )
        changed = refund.model_copy(
            update={"amount": CurrencyAmount(amount="0.002", currency="USD")}
        )
        with pytest.raises(ConfigurationError, match="different content"):
            store.save_refund_receipt_v2(changed)
        with pytest.raises(ConfigurationError, match="exceeds captured"):
            store.save_refund_receipt_v2(
                refund.model_copy(
                    update={
                        "refund_id": "refund-2",
                        "amount": CurrencyAmount(amount="0.003", currency="USD"),
                        "idempotency_key": "refund-key-2",
                    }
                )
            )
