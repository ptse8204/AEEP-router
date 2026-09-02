"""SQLite persistence for route decisions and execution receipts."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TypedDict, TypeVar

from pydantic import BaseModel

from .attempts import ExecutionAttempt, ExecutionAttemptState
from .capacity.models import (
    CapacityAuthorizationEvidence,
    CapacityObservation,
    CapacityReservation,
    CapacityReservationStatus,
    EntitlementRedemptionReceipt,
    EntitlementRedemptionStatus,
    ExecutionEntitlement,
    capacity_digest,
)
from .discovery import RegistryCandidate
from .economic.canonical import canonical_digest, canonical_payload
from .economic.trust import (
    TrustedKeyStatus,
    TrustedProviderKey,
    TrustStore,
    TrustStoreVerifier,
)
from .errors import ConfigurationError
from .models import (
    ActionApprovalRecord,
    AuthorizationKind,
    BillingReconciliation,
    BoundedQuote,
    CacheAffinityObservation,
    CapabilityOffer,
    CurrencyAmount,
    EconomicEvidenceLink,
    ExecutionReceipt,
    LedgerEvent,
    MarketAggregate,
    Observation,
    PaymentCapture,
    PaymentRefund,
    PaymentReservation,
    PaymentReservationState,
    PaymentReservationV2,
    PreparedDecisionState,
    PreparedRouteDecision,
    PreparedRouteTransition,
    PricingDispute,
    QuotaObservation,
    Quote,
    QuoteAcceptance,
    QuoteRequestV2,
    RateCardSnapshot,
    RateType,
    RefundReceiptV2,
    RouteDecision,
    SettlementReceipt,
    SettlementStatus,
    UsageStatement,
)
from .provider_package import (
    ArtifactReference,
    ArtifactVerificationResult,
    CandidateVerificationSnapshot,
    EvidenceAcceptance,
    EvidenceReference,
    PackageVerificationResult,
    ProviderPackage,
    SignatureVerificationResult,
    SmokeTestReport,
)
from .qualification import QualificationReport, RouteCandidate

LATEST_DATABASE_SCHEMA = 7

_LEGACY_SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS decisions (
        decision_id TEXT PRIMARY KEY,
        action_id TEXT NOT NULL,
        capability TEXT NOT NULL,
        created_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_decisions_capability_created
    ON decisions(capability, created_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS receipts (
        receipt_id TEXT PRIMARY KEY,
        decision_id TEXT NOT NULL,
        action_id TEXT NOT NULL,
        capability TEXT NOT NULL,
        executor_id TEXT NOT NULL,
        status TEXT NOT NULL,
        started_at TEXT NOT NULL,
        ended_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_receipts_executor_started
    ON receipts(executor_id, started_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_receipts_decision
    ON receipts(decision_id, started_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_receipts_action_executor_started
    ON receipts(action_id, executor_id, started_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS external_reports (
        decision_id TEXT NOT NULL,
        executor_id TEXT NOT NULL,
        receipt_id TEXT NOT NULL UNIQUE,
        PRIMARY KEY (decision_id, executor_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS quotes (
        quote_id TEXT PRIMARY KEY,
        expires_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS quote_acceptances (
        acceptance_id TEXT PRIMARY KEY,
        quote_id TEXT NOT NULL UNIQUE,
        accepted_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS payment_objects (
        object_id TEXT PRIMARY KEY,
        object_type TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ledger_events (
        event_id TEXT PRIMARY KEY,
        event_type TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ledger_occurred
    ON ledger_events(occurred_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS observations (
        observation_id TEXT PRIMARY KEY,
        provider_id TEXT,
        capability TEXT NOT NULL,
        observed_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_observations_provider_capability
    ON observations(provider_id, capability, observed_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS idempotency_records (
        idempotency_key TEXT PRIMARY KEY,
        request_hash TEXT NOT NULL,
        state TEXT NOT NULL,
        decision_id TEXT,
        status TEXT,
        receipt_ids_json TEXT NOT NULL DEFAULT '[]'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS quota_observations (
        observation_id TEXT PRIMARY KEY,
        resource_id TEXT NOT NULL,
        observed_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_quota_resource_observed
    ON quota_observations(resource_id, observed_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS route_candidates (
        executor_id TEXT PRIMARY KEY,
        source_id TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        status TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qualification_reports (
        report_id TEXT PRIMARY KEY,
        candidate_id TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rate_card_snapshots (
        snapshot_id TEXT PRIMARY KEY,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS workflow_checkpoints (
        workflow_id TEXT PRIMARY KEY,
        workflow_hash TEXT NOT NULL,
        status TEXT NOT NULL,
        waiting_step_id TEXT,
        waiting_decision_id TEXT
    )
    """,
)

_V04_SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS provider_signing_keys (
        provider_id TEXT NOT NULL,
        key_id TEXT NOT NULL,
        algorithm TEXT NOT NULL,
        status TEXT NOT NULL,
        valid_from TEXT NOT NULL,
        valid_until TEXT NOT NULL,
        revoked_at TEXT,
        payload_digest TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        PRIMARY KEY (provider_id, key_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_provider_signing_keys_status
    ON provider_signing_keys(provider_id, status, valid_until)
    """,
    """
    CREATE TABLE IF NOT EXISTS capability_offers (
        offer_id TEXT PRIMARY KEY,
        provider_id TEXT NOT NULL,
        capability TEXT NOT NULL,
        executor_id TEXT NOT NULL,
        executor_fingerprint TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        revoked_at TEXT,
        valid_from TEXT NOT NULL,
        valid_until TEXT NOT NULL,
        signature_algorithm TEXT NOT NULL,
        signature_key_id TEXT NOT NULL,
        evidence_level TEXT NOT NULL,
        payload_digest TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_capability_offers_lookup
    ON capability_offers(capability, executor_id, executor_fingerprint, valid_until)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_capability_offers_provider_status
    ON capability_offers(provider_id, status, valid_until)
    """,
    """
    CREATE TABLE IF NOT EXISTS quote_requests_v2 (
        quote_request_id TEXT PRIMARY KEY,
        action_id TEXT NOT NULL,
        capability TEXT NOT NULL,
        executor_id TEXT NOT NULL,
        executor_fingerprint TEXT NOT NULL,
        action_digest TEXT NOT NULL,
        nonce TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        payload_digest TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_quote_requests_v2_lookup
    ON quote_requests_v2(capability, executor_id, executor_fingerprint, expires_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS bounded_quotes (
        quote_id TEXT PRIMARY KEY,
        quote_request_id TEXT NOT NULL,
        offer_id TEXT,
        provider_id TEXT NOT NULL,
        capability TEXT NOT NULL,
        executor_id TEXT NOT NULL,
        executor_fingerprint TEXT NOT NULL,
        action_digest TEXT NOT NULL,
        nonce TEXT NOT NULL,
        expected_amount TEXT,
        maximum_amount TEXT NOT NULL,
        currency TEXT NOT NULL,
        issued_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        signature_algorithm TEXT NOT NULL,
        signature_key_id TEXT NOT NULL,
        evidence_level TEXT NOT NULL,
        payload_digest TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        FOREIGN KEY (quote_request_id) REFERENCES quote_requests_v2(quote_request_id),
        FOREIGN KEY (offer_id) REFERENCES capability_offers(offer_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_bounded_quotes_lookup
    ON bounded_quotes(capability, provider_id, executor_id, executor_fingerprint, expires_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_bounded_quotes_request
    ON bounded_quotes(quote_request_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS quote_nonce_uses (
        nonce TEXT PRIMARY KEY,
        quote_request_id TEXT NOT NULL,
        quote_id TEXT NOT NULL,
        action_digest TEXT NOT NULL,
        used_at TEXT NOT NULL,
        FOREIGN KEY (quote_request_id) REFERENCES quote_requests_v2(quote_request_id),
        FOREIGN KEY (quote_id) REFERENCES bounded_quotes(quote_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_quote_nonce_uses_request
    ON quote_nonce_uses(quote_request_id, used_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS prepared_route_decisions (
        prepared_id TEXT PRIMARY KEY,
        action_id TEXT NOT NULL,
        action_digest TEXT NOT NULL,
        effective_policy_digest TEXT NOT NULL,
        selected_executor_id TEXT,
        selected_executor_fingerprint TEXT,
        selected_quote_id TEXT,
        selected_offer_id TEXT,
        selected_rate_card_id TEXT,
        authorization_kind TEXT,
        authorization_id TEXT,
        maximum_amount TEXT,
        currency TEXT,
        state TEXT NOT NULL,
        claim_token TEXT UNIQUE,
        claimed_at TEXT,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        payload_digest TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        FOREIGN KEY (selected_quote_id) REFERENCES bounded_quotes(quote_id),
        FOREIGN KEY (selected_offer_id) REFERENCES capability_offers(offer_id),
        FOREIGN KEY (selected_rate_card_id) REFERENCES rate_card_snapshots(snapshot_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_prepared_route_decisions_state_expiry
    ON prepared_route_decisions(state, expires_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_prepared_route_decisions_action
    ON prepared_route_decisions(action_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_prepared_route_decisions_executor
    ON prepared_route_decisions(selected_executor_id, selected_executor_fingerprint)
    """,
    """
    CREATE TABLE IF NOT EXISTS prepared_route_transitions (
        transition_id TEXT PRIMARY KEY,
        prepared_id TEXT NOT NULL,
        from_state TEXT NOT NULL,
        to_state TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        reason TEXT,
        payload_digest TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        FOREIGN KEY (prepared_id) REFERENCES prepared_route_decisions(prepared_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_prepared_route_transitions_prepared
    ON prepared_route_transitions(prepared_id, occurred_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS payment_reservations_v2 (
        reservation_id TEXT PRIMARY KEY,
        charge_id TEXT NOT NULL UNIQUE,
        prepared_id TEXT NOT NULL,
        quote_id TEXT,
        authorization_kind TEXT NOT NULL,
        authorization_id TEXT NOT NULL,
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
        UNIQUE (prepared_id),
        UNIQUE (quote_id),
        FOREIGN KEY (prepared_id) REFERENCES prepared_route_decisions(prepared_id),
        FOREIGN KEY (quote_id) REFERENCES bounded_quotes(quote_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_payment_reservations_v2_prepared_state
    ON payment_reservations_v2(prepared_id, state)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_payment_reservations_v2_action
    ON payment_reservations_v2(action_id, created_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS usage_statements (
        usage_statement_id TEXT PRIMARY KEY,
        quote_id TEXT NOT NULL,
        prepared_id TEXT NOT NULL,
        action_id TEXT NOT NULL,
        attempt_id TEXT NOT NULL,
        provider_id TEXT NOT NULL,
        executor_id TEXT NOT NULL,
        executor_fingerprint TEXT NOT NULL,
        execution_status TEXT NOT NULL,
        issued_at TEXT NOT NULL,
        signature_algorithm TEXT NOT NULL,
        signature_key_id TEXT NOT NULL,
        evidence_level TEXT NOT NULL,
        payload_digest TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        FOREIGN KEY (quote_id) REFERENCES bounded_quotes(quote_id),
        FOREIGN KEY (prepared_id) REFERENCES prepared_route_decisions(prepared_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_usage_statements_prepared_attempt
    ON usage_statements(prepared_id, attempt_id)
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_usage_statements_one_per_attempt
    ON usage_statements(prepared_id, attempt_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_usage_statements_provider_executor
    ON usage_statements(provider_id, executor_id, executor_fingerprint, issued_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS settlement_receipts (
        settlement_id TEXT PRIMARY KEY,
        charge_id TEXT NOT NULL UNIQUE,
        prepared_id TEXT NOT NULL,
        quote_id TEXT,
        authorization_kind TEXT NOT NULL,
        authorization_id TEXT NOT NULL,
        reservation_id TEXT NOT NULL,
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
        UNIQUE (reservation_id),
        FOREIGN KEY (prepared_id) REFERENCES prepared_route_decisions(prepared_id),
        FOREIGN KEY (quote_id) REFERENCES bounded_quotes(quote_id),
        FOREIGN KEY (reservation_id) REFERENCES payment_reservations_v2(reservation_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_settlement_receipts_prepared_status
    ON settlement_receipts(prepared_id, status, settled_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_settlement_receipts_reservation
    ON settlement_receipts(reservation_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS refund_receipts_v2 (
        refund_id TEXT PRIMARY KEY,
        settlement_id TEXT NOT NULL,
        charge_id TEXT NOT NULL,
        amount TEXT NOT NULL,
        currency TEXT NOT NULL,
        idempotency_key TEXT NOT NULL UNIQUE,
        refunded_at TEXT NOT NULL,
        payload_digest TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        FOREIGN KEY (settlement_id) REFERENCES settlement_receipts(settlement_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_refund_receipts_v2_settlement
    ON refund_receipts_v2(settlement_id, refunded_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS refund_authorizations_v2 (
        refund_id TEXT PRIMARY KEY,
        settlement_id TEXT NOT NULL,
        charge_id TEXT NOT NULL,
        amount TEXT NOT NULL,
        currency TEXT NOT NULL,
        idempotency_key TEXT NOT NULL UNIQUE,
        request_digest TEXT NOT NULL,
        state TEXT NOT NULL,
        authorized_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (settlement_id) REFERENCES settlement_receipts(settlement_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_refund_authorizations_v2_settlement_state
    ON refund_authorizations_v2(settlement_id, state)
    """,
    """
    CREATE TABLE IF NOT EXISTS billing_reconciliations (
        reconciliation_id TEXT PRIMARY KEY,
        settlement_id TEXT NOT NULL,
        provider_id TEXT NOT NULL,
        expected_amount TEXT NOT NULL,
        billed_amount TEXT NOT NULL,
        discrepancy TEXT NOT NULL,
        currency TEXT NOT NULL,
        status TEXT NOT NULL,
        reconciled_at TEXT NOT NULL,
        evidence_level TEXT NOT NULL,
        payload_digest TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        FOREIGN KEY (settlement_id) REFERENCES settlement_receipts(settlement_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_billing_reconciliations_settlement
    ON billing_reconciliations(settlement_id, reconciled_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_billing_reconciliations_provider_status
    ON billing_reconciliations(provider_id, status, reconciled_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS market_aggregates (
        aggregate_id TEXT PRIMARY KEY,
        capability TEXT NOT NULL,
        provider_id TEXT NOT NULL,
        executor_id TEXT NOT NULL,
        executor_fingerprint TEXT NOT NULL,
        region TEXT,
        account_tier TEXT,
        input_bucket TEXT NOT NULL,
        sample_size INTEGER NOT NULL,
        window_start TEXT NOT NULL,
        window_end TEXT NOT NULL,
        generated_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        signature_algorithm TEXT NOT NULL,
        signature_key_id TEXT NOT NULL,
        evidence_level TEXT NOT NULL,
        payload_digest TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_market_aggregates_lookup
    ON market_aggregates(
        capability, provider_id, executor_id, executor_fingerprint,
        region, account_tier, input_bucket, expires_at
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pricing_disputes (
        dispute_id TEXT PRIMARY KEY,
        prepared_id TEXT NOT NULL,
        quote_id TEXT NOT NULL,
        usage_statement_id TEXT,
        provider_id TEXT NOT NULL,
        quoted_maximum TEXT NOT NULL,
        provider_claimed_amount TEXT NOT NULL,
        currency TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        resolved_at TEXT,
        payload_digest TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        FOREIGN KEY (prepared_id) REFERENCES prepared_route_decisions(prepared_id),
        FOREIGN KEY (quote_id) REFERENCES bounded_quotes(quote_id),
        FOREIGN KEY (usage_statement_id) REFERENCES usage_statements(usage_statement_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_pricing_disputes_prepared_status
    ON pricing_disputes(prepared_id, status, created_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS economic_evidence_links (
        link_id TEXT PRIMARY KEY,
        charge_id TEXT NOT NULL,
        evidence_type TEXT NOT NULL,
        evidence_id TEXT NOT NULL,
        evidence_level TEXT NOT NULL,
        evidence_payload_digest TEXT NOT NULL,
        authoritative INTEGER NOT NULL CHECK (authoritative IN (0, 1)),
        supersedes_link_id TEXT,
        created_at TEXT NOT NULL,
        payload_digest TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        UNIQUE (charge_id, evidence_type, evidence_id),
        FOREIGN KEY (supersedes_link_id) REFERENCES economic_evidence_links(link_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_economic_evidence_links_charge
    ON economic_evidence_links(charge_id, authoritative, evidence_level)
    """,
)

_PREPARED_ACTION_IDEMPOTENCY_SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS prepared_action_idempotency (
        prepared_id TEXT PRIMARY KEY,
        idempotency_key TEXT NOT NULL UNIQUE,
        action_digest TEXT NOT NULL,
        bound_at TEXT NOT NULL,
        FOREIGN KEY (prepared_id) REFERENCES prepared_route_decisions(prepared_id),
        FOREIGN KEY (idempotency_key) REFERENCES idempotency_records(idempotency_key)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_prepared_action_idempotency_digest
    ON prepared_action_idempotency(action_digest, prepared_id)
    """,
)

_V05_SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS protocol_cutovers (
        name TEXT PRIMARY KEY,
        occurred_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS provider_packages (
        package_digest TEXT PRIMARY KEY,
        package_id TEXT NOT NULL,
        package_version TEXT NOT NULL,
        provider_id TEXT NOT NULL,
        source_id TEXT NOT NULL,
        imported_at TEXT NOT NULL,
        integrity_status TEXT NOT NULL,
        effective_identity_trust TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_provider_packages_identity
    ON provider_packages(provider_id, package_id, package_version)
    """,
    """
    CREATE TABLE IF NOT EXISTS provider_package_signatures (
        package_digest TEXT NOT NULL,
        signature_id TEXT NOT NULL,
        key_id TEXT NOT NULL,
        role TEXT NOT NULL,
        status TEXT NOT NULL,
        effective_trust TEXT NOT NULL,
        verified_at TEXT NOT NULL,
        failure_code TEXT,
        payload_json TEXT NOT NULL,
        PRIMARY KEY(package_digest, signature_id),
        FOREIGN KEY(package_digest) REFERENCES provider_packages(package_digest)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS content_artifacts (
        artifact_digest TEXT PRIMARY KEY,
        media_type TEXT NOT NULL,
        size_bytes INTEGER NOT NULL,
        cas_path TEXT NOT NULL,
        source_kind TEXT NOT NULL,
        verified_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS provider_package_artifacts (
        package_digest TEXT NOT NULL,
        artifact_id TEXT NOT NULL,
        artifact_digest TEXT NOT NULL,
        required INTEGER NOT NULL CHECK(required IN (0, 1)),
        status TEXT NOT NULL,
        failure_code TEXT,
        payload_json TEXT NOT NULL,
        PRIMARY KEY(package_digest, artifact_id),
        FOREIGN KEY(package_digest) REFERENCES provider_packages(package_digest)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS evidence_records (
        package_digest TEXT NOT NULL,
        evidence_id TEXT NOT NULL,
        artifact_digest TEXT NOT NULL,
        evidence_type TEXT NOT NULL,
        route_id TEXT NOT NULL,
        route_fingerprint TEXT NOT NULL,
        workload_digest TEXT,
        producer_id TEXT NOT NULL,
        declared_trust TEXT NOT NULL,
        effective_trust TEXT NOT NULL,
        valid_from TEXT NOT NULL,
        expires_at TEXT,
        payload_json TEXT NOT NULL,
        PRIMARY KEY(package_digest, evidence_id),
        FOREIGN KEY(package_digest) REFERENCES provider_packages(package_digest),
        FOREIGN KEY(artifact_digest) REFERENCES content_artifacts(artifact_digest)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_evidence_records_route
    ON evidence_records(route_id, route_fingerprint, evidence_type)
    """,
    """
    CREATE TABLE IF NOT EXISTS evidence_acceptances (
        acceptance_id TEXT PRIMARY KEY,
        package_digest TEXT NOT NULL,
        evidence_id TEXT NOT NULL,
        executor_id TEXT NOT NULL,
        metric TEXT NOT NULL,
        status TEXT NOT NULL,
        reason_code TEXT NOT NULL,
        applicability TEXT NOT NULL,
        confidence TEXT NOT NULL,
        effective_trust TEXT NOT NULL,
        evaluated_at TEXT NOT NULL,
        rate_card_snapshot_id TEXT,
        payload_json TEXT NOT NULL,
        FOREIGN KEY(package_digest, evidence_id)
            REFERENCES evidence_records(package_digest, evidence_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_evidence_acceptances_candidate
    ON evidence_acceptances(executor_id, metric, status)
    """,
    """
    CREATE TABLE IF NOT EXISTS smoke_test_reports (
        smoke_report_id TEXT PRIMARY KEY,
        executor_id TEXT NOT NULL,
        route_fingerprint TEXT NOT NULL,
        status TEXT NOT NULL,
        finished_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_smoke_reports_candidate
    ON smoke_test_reports(executor_id, route_fingerprint, finished_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS candidate_verification_snapshots (
        snapshot_id TEXT PRIMARY KEY,
        executor_id TEXT NOT NULL,
        package_digest TEXT NOT NULL,
        route_fingerprint TEXT NOT NULL,
        created_at TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        FOREIGN KEY(package_digest) REFERENCES provider_packages(package_digest)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS provider_package_audit_events (
        event_id TEXT PRIMARY KEY,
        package_digest TEXT,
        executor_id TEXT,
        event_type TEXT NOT NULL,
        reason_code TEXT,
        occurred_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cache_affinity_observations (
        observation_id TEXT PRIMARY KEY,
        scope_key_hmac TEXT NOT NULL,
        route_id TEXT NOT NULL,
        observed_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_cache_affinity_scope
    ON cache_affinity_observations(scope_key_hmac, route_id, observed_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS registry_candidates (
        registry_candidate_id TEXT PRIMARY KEY,
        adapter_id TEXT NOT NULL,
        retrieved_at TEXT NOT NULL,
        raw_metadata_digest TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_registry_candidates_adapter
    ON registry_candidates(adapter_id, retrieved_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS action_approval_records (
        approval_id TEXT PRIMARY KEY,
        action_digest TEXT NOT NULL,
        prepared_id TEXT,
        attempt_id TEXT,
        granted_at TEXT NOT NULL,
        expires_at TEXT,
        payload_json TEXT NOT NULL
    )
    """,
)

_V07_CAPACITY_SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS capacity_observations (
        observation_id TEXT PRIMARY KEY,
        resource_id TEXT NOT NULL,
        observed_at TEXT NOT NULL,
        canonical_digest TEXT NOT NULL UNIQUE,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_capacity_observations_resource
    ON capacity_observations(resource_id, observed_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS capacity_reservations (
        reservation_id TEXT PRIMARY KEY,
        resource_id TEXT NOT NULL,
        execution_id TEXT NOT NULL,
        maximum_quantity TEXT NOT NULL,
        unit TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        state TEXT NOT NULL,
        idempotency_key TEXT NOT NULL UNIQUE,
        claim_token TEXT UNIQUE,
        version INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_capacity_reservations_resource_state
    ON capacity_reservations(resource_id, unit, state, expires_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS capacity_authorization_evidence (
        evidence_id TEXT PRIMARY KEY,
        provider_id TEXT NOT NULL,
        resource_id TEXT NOT NULL,
        resource_fingerprint TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        payload_digest TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS execution_entitlements (
        entitlement_id TEXT PRIMARY KEY,
        resource_id TEXT NOT NULL,
        resource_fingerprint TEXT NOT NULL,
        nonce TEXT NOT NULL UNIQUE,
        maximum_quantity TEXT NOT NULL,
        remaining_quantity TEXT NOT NULL,
        unit TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        state TEXT NOT NULL,
        version INTEGER NOT NULL,
        authorization_evidence_id TEXT,
        payload_digest TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        FOREIGN KEY (authorization_evidence_id)
            REFERENCES capacity_authorization_evidence(evidence_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_execution_entitlements_resource_state
    ON execution_entitlements(resource_id, state, expires_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS entitlement_redemptions (
        redemption_id TEXT PRIMARY KEY,
        entitlement_id TEXT NOT NULL,
        attempt_id TEXT NOT NULL UNIQUE,
        quantity_consumed TEXT NOT NULL,
        remaining_quantity TEXT NOT NULL,
        status TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        payload_digest TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        FOREIGN KEY (entitlement_id) REFERENCES execution_entitlements(entitlement_id),
        UNIQUE (entitlement_id, attempt_id)
    )
    """,
)

_V07_ATTEMPT_SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS execution_attempts (
        attempt_id TEXT PRIMARY KEY,
        decision_id TEXT NOT NULL,
        prepared_id TEXT,
        action_digest TEXT NOT NULL,
        executor_id TEXT NOT NULL,
        executor_fingerprint TEXT NOT NULL,
        state TEXT NOT NULL,
        owner_id TEXT,
        lease_expires_at TEXT,
        heartbeat_at TEXT,
        version INTEGER NOT NULL,
        updated_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_execution_attempts_recovery
    ON execution_attempts(state, lease_expires_at, updated_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_execution_attempts_decision
    ON execution_attempts(decision_id, updated_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_execution_attempts_prepared
    ON execution_attempts(prepared_id, updated_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS execution_attempt_transitions (
        transition_id TEXT PRIMARY KEY,
        attempt_id TEXT NOT NULL,
        from_state TEXT NOT NULL,
        to_state TEXT NOT NULL,
        version INTEGER NOT NULL,
        occurred_at TEXT NOT NULL,
        reason TEXT,
        FOREIGN KEY (attempt_id) REFERENCES execution_attempts(attempt_id),
        UNIQUE (attempt_id, version)
    )
    """,
)


def _table_columns(
    connection: sqlite3.Connection, table: str
) -> dict[str, sqlite3.Row]:
    return {row["name"]: row for row in connection.execute(f"PRAGMA table_info({table})")}


def _add_column_if_missing(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    if column not in _table_columns(connection, table):
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _migrate_v3_to_v4(connection: sqlite3.Connection) -> None:
    for statement in _V05_SCHEMA:
        connection.execute(statement)
    _add_column_if_missing(connection, "route_candidates", "package_digest", "TEXT")
    _add_column_if_missing(connection, "route_candidates", "package_fingerprint", "TEXT")
    _add_column_if_missing(
        connection,
        "route_candidates",
        "verification_snapshot_id",
        "TEXT",
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO protocol_cutovers(name, occurred_at)
        VALUES ('rfc8785_live_cutover', ?)
        """,
        (datetime.now(UTC).isoformat(),),
    )


def _migrate_v4_to_v5(connection: sqlite3.Connection) -> None:
    for table in ("receipts", "observations"):
        _add_column_if_missing(connection, table, "executor_fingerprint", "TEXT")
        _add_column_if_missing(connection, table, "cohort_digest", "TEXT")
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_receipts_evidence_cohort
        ON receipts(executor_id, executor_fingerprint, cohort_digest, started_at DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_observations_evidence_cohort
        ON observations(executor_fingerprint, cohort_digest, observed_at DESC)
        """
    )


def _migrate_v1_to_v2(connection: sqlite3.Connection) -> None:
    """Upgrade pre-authorization 0.4 development databases without losing evidence."""

    # A version-1 database may have been produced by an earlier 0.4 development
    # build. Ensure every additive table exists before rebuilding the two tables
    # whose quote foreign key changed from mandatory to optional.
    for statement in _V04_SCHEMA:
        connection.execute(statement)

    for column, definition in (
        ("selected_offer_id", "TEXT"),
        ("selected_rate_card_id", "TEXT"),
        ("authorization_kind", "TEXT"),
        ("authorization_id", "TEXT"),
        ("maximum_amount", "TEXT"),
        ("currency", "TEXT"),
    ):
        _add_column_if_missing(
            connection, "prepared_route_decisions", column, definition
        )

    connection.execute(
        """
        UPDATE prepared_route_decisions
        SET authorization_kind = COALESCE(authorization_kind, 'SIGNED_QUOTE'),
            authorization_id = COALESCE(authorization_id, selected_quote_id),
            maximum_amount = COALESCE(
                maximum_amount,
                (SELECT maximum_amount FROM bounded_quotes
                 WHERE quote_id = prepared_route_decisions.selected_quote_id)
            ),
            currency = COALESCE(
                currency,
                (SELECT currency FROM bounded_quotes
                 WHERE quote_id = prepared_route_decisions.selected_quote_id)
            )
        WHERE selected_quote_id IS NOT NULL
        """
    )

    for column, definition in (
        ("authorization_kind", "TEXT"),
        ("authorization_id", "TEXT"),
        ("operation_intent", "TEXT"),
    ):
        _add_column_if_missing(
            connection, "payment_reservations_v2", column, definition
        )
    connection.execute(
        """
        UPDATE payment_reservations_v2
        SET authorization_kind = COALESCE(authorization_kind, 'SIGNED_QUOTE'),
            authorization_id = COALESCE(authorization_id, quote_id)
        WHERE quote_id IS NOT NULL
        """
    )
    connection.execute("DROP TABLE IF EXISTS payment_reservations_v2__v2")
    connection.execute(
        """
        CREATE TABLE payment_reservations_v2__v2 (
            reservation_id TEXT PRIMARY KEY,
            charge_id TEXT NOT NULL UNIQUE,
            prepared_id TEXT NOT NULL,
            quote_id TEXT,
            authorization_kind TEXT NOT NULL,
            authorization_id TEXT NOT NULL,
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
            UNIQUE (prepared_id),
            UNIQUE (quote_id),
            FOREIGN KEY (prepared_id) REFERENCES prepared_route_decisions(prepared_id),
            FOREIGN KEY (quote_id) REFERENCES bounded_quotes(quote_id)
        )
        """
    )
    connection.execute(
        """
        INSERT INTO payment_reservations_v2__v2 (
            reservation_id, charge_id, prepared_id, quote_id,
            authorization_kind, authorization_id, action_id, attempt_id,
            maximum_amount, currency, adapter, state, operation_intent,
            idempotency_key, created_at, updated_at, indeterminate_reason,
            payload_digest, payload_json
        )
        SELECT reservation_id, charge_id, prepared_id, quote_id,
               authorization_kind, authorization_id, action_id, attempt_id,
               maximum_amount, currency, adapter, state, operation_intent,
               idempotency_key, created_at, updated_at, indeterminate_reason,
               payload_digest, payload_json
        FROM payment_reservations_v2
        """
    )
    connection.execute("DROP TABLE payment_reservations_v2")
    connection.execute(
        "ALTER TABLE payment_reservations_v2__v2 RENAME TO payment_reservations_v2"
    )

    for column, definition in (
        ("authorization_kind", "TEXT"),
        ("authorization_id", "TEXT"),
    ):
        _add_column_if_missing(connection, "settlement_receipts", column, definition)
    connection.execute(
        """
        UPDATE settlement_receipts
        SET authorization_kind = COALESCE(authorization_kind, 'SIGNED_QUOTE'),
            authorization_id = COALESCE(authorization_id, quote_id)
        WHERE quote_id IS NOT NULL
        """
    )
    connection.execute("DROP TABLE IF EXISTS settlement_receipts__v2")
    connection.execute(
        """
        CREATE TABLE settlement_receipts__v2 (
            settlement_id TEXT PRIMARY KEY,
            charge_id TEXT NOT NULL UNIQUE,
            prepared_id TEXT NOT NULL,
            quote_id TEXT,
            authorization_kind TEXT NOT NULL,
            authorization_id TEXT NOT NULL,
            reservation_id TEXT NOT NULL,
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
            UNIQUE (reservation_id),
            FOREIGN KEY (prepared_id) REFERENCES prepared_route_decisions(prepared_id),
            FOREIGN KEY (quote_id) REFERENCES bounded_quotes(quote_id),
            FOREIGN KEY (reservation_id) REFERENCES payment_reservations_v2(reservation_id)
        )
        """
    )
    settlement_columns = _table_columns(connection, "settlement_receipts")
    settlement_charge_id = (
        "charge_id"
        if "charge_id" in settlement_columns
        else "(SELECT charge_id FROM payment_reservations_v2 "
        "WHERE reservation_id = settlement_receipts.reservation_id)"
    )
    connection.execute(
        f"""
        INSERT INTO settlement_receipts__v2 (
            settlement_id, charge_id, prepared_id, quote_id,
            authorization_kind, authorization_id, reservation_id, attempt_id,
            reserved_amount, captured_amount, released_amount, currency, status,
            evidence_level, settled_at, payload_digest, payload_json
        )
        SELECT settlement_id, {settlement_charge_id}, prepared_id, quote_id,
               authorization_kind, authorization_id, reservation_id, attempt_id,
               reserved_amount, captured_amount, released_amount, currency, status,
               evidence_level, settled_at, payload_digest, payload_json
        FROM settlement_receipts
        """
    )
    connection.execute("DROP TABLE settlement_receipts")
    connection.execute(
        "ALTER TABLE settlement_receipts__v2 RENAME TO settlement_receipts"
    )

    # Recreate indexes dropped with the rebuilt tables, including additions made
    # after the initial development schema marker.
    for statement in _V04_SCHEMA:
        connection.execute(statement)

ModelT = TypeVar("ModelT", bound=BaseModel)


class RefundAuthorizationRecord(TypedDict):
    refund_id: str
    settlement_id: str
    charge_id: str
    amount: CurrencyAmount
    idempotency_key: str
    request_digest: str
    state: str
    authorized_at: datetime
    updated_at: datetime


class PreparedActionIdempotencyRecord(TypedDict):
    prepared_id: str
    idempotency_key: str
    action_digest: str
    bound_at: datetime


class PaymentOperationFinalizationRecord(TypedDict):
    prepared_id: str
    reservation_id: str
    settlement_id: str
    operation: str
    idempotency_key: str
    request_digest: str


class PreparedActionFinalizationRecord(TypedDict):
    prepared_id: str
    action_digest: str
    receipt_id: str | None
    decision_id: str | None
    status: str | None


class ReceiptStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            target = Path(self.path).expanduser()
            target.parent.mkdir(parents=True, exist_ok=True)
            self.path = str(target)
        try:
            self._connection = sqlite3.connect(
                self.path,
                check_same_thread=False,
                timeout=30.0,
            )
        except sqlite3.Error as exc:
            raise ConfigurationError(f"cannot open AEEP database {self.path!r}: {exc}") from exc
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._initialize()

    def _initialize(self) -> None:
        with self._lock:
            migration_disables_foreign_keys = False
            try:
                self._connection.execute("PRAGMA journal_mode=WAL")
                self._connection.execute("PRAGMA foreign_keys=ON")
                if self._connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
                    raise sqlite3.DatabaseError("foreign-key enforcement could not be enabled")
                version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
                if version > LATEST_DATABASE_SCHEMA:
                    raise ConfigurationError(
                        f"database schema {version} is newer than supported schema "
                        f"{LATEST_DATABASE_SCHEMA}"
                    )
                if version < LATEST_DATABASE_SCHEMA:
                    # Version 2 rebuilds tables to make quote_id nullable. SQLite
                    # requires foreign keys to be disabled before the transaction;
                    # integrity is checked before commit and enforcement restored.
                    self._connection.execute("PRAGMA foreign_keys=OFF")
                    migration_disables_foreign_keys = True
                self._connection.execute("BEGIN IMMEDIATE")
                for statement in _LEGACY_SCHEMA:
                    self._connection.execute(statement)
                if version < 1:
                    for statement in _V04_SCHEMA:
                        self._connection.execute(statement)
                    version = 1
                if version < 2:
                    _migrate_v1_to_v2(self._connection)
                    version = 2
                if version < 3:
                    for statement in _PREPARED_ACTION_IDEMPOTENCY_SCHEMA:
                        self._connection.execute(statement)
                    version = 3
                if version < 4:
                    _migrate_v3_to_v4(self._connection)
                    version = 4
                if version < 5:
                    _migrate_v4_to_v5(self._connection)
                    version = 5
                if version < 6:
                    for statement in _V07_CAPACITY_SCHEMA:
                        self._connection.execute(statement)
                    version = 6
                if version < 7:
                    for statement in _V07_ATTEMPT_SCHEMA:
                        self._connection.execute(statement)
                    version = 7
                self._connection.execute(f"PRAGMA user_version={version}")
                if self._connection.execute("PRAGMA foreign_key_check").fetchall():
                    raise sqlite3.IntegrityError(
                        "database contains invalid foreign-key relationships"
                    )
                self._connection.commit()
            except Exception as exc:
                if self._connection.in_transaction:
                    self._connection.rollback()
                if isinstance(exc, ConfigurationError):
                    raise
                raise ConfigurationError(f"cannot migrate AEEP database: {exc}") from exc
            finally:
                if migration_disables_foreign_keys:
                    self._connection.execute("PRAGMA foreign_keys=ON")

    @contextmanager
    def _immediate_transaction(self) -> Iterator[sqlite3.Connection]:
        """Serialize a read/check/write sequence across store instances."""

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self._connection
            except Exception:
                self._connection.rollback()
                raise
            else:
                self._connection.commit()

    @staticmethod
    def _immutable_insert_locked(
        connection: sqlite3.Connection,
        *,
        table: str,
        identity: dict[str, object],
        indexed: dict[str, object],
        value: BaseModel,
    ) -> bool:
        """Insert immutable evidence, accepting only an exact normalized retry."""

        payload = value.model_dump_json()
        digest = canonical_digest(value)
        columns = {**identity, **indexed, "payload_digest": digest, "payload_json": payload}
        names = ", ".join(columns)
        placeholders = ", ".join("?" for _ in columns)
        cursor = connection.execute(
            f"INSERT INTO {table} ({names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING",
            tuple(columns.values()),
        )
        where = " AND ".join(f"{column} = ?" for column in identity)
        row = connection.execute(
            f"SELECT payload_digest, payload_json FROM {table} WHERE {where}",
            tuple(identity.values()),
        ).fetchone()
        if row is None:
            raise ConfigurationError(f"immutable {table} identity conflicts with existing data")
        if row["payload_digest"] != digest or row["payload_json"] != payload:
            raise ConfigurationError(
                f"immutable {table} identity was reused with different content"
            )
        return cursor.rowcount == 1

    def _save_immutable(
        self,
        *,
        table: str,
        identity: dict[str, object],
        indexed: dict[str, object],
        value: ModelT,
    ) -> ModelT:
        try:
            with self._immediate_transaction() as connection:
                self._immutable_insert_locked(
                    connection,
                    table=table,
                    identity=identity,
                    indexed=indexed,
                    value=value,
                )
        except sqlite3.IntegrityError as exc:
            raise ConfigurationError(f"immutable {table} violates its evidence bindings") from exc
        return value

    def _get_typed(
        self,
        *,
        table: str,
        identity: dict[str, object],
        model: type[ModelT],
    ) -> ModelT | None:
        where = " AND ".join(f"{column} = ?" for column in identity)
        with self._lock:
            row = self._connection.execute(
                f"SELECT payload_json FROM {table} WHERE {where}", tuple(identity.values())
            ).fetchone()
        return model.model_validate_json(row[0]) if row else None

    def _list_typed(
        self,
        *,
        table: str,
        model: type[ModelT],
        clauses: tuple[str, ...] = (),
        parameters: tuple[object, ...] = (),
        order_by: str,
        limit: int,
    ) -> list[ModelT]:
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        bounded_limit = max(1, min(limit, 10_000))
        with self._lock:
            rows = self._connection.execute(
                f"SELECT payload_json FROM {table} {where} ORDER BY {order_by} LIMIT ?",
                (*parameters, bounded_limit),
            ).fetchall()
        return [model.model_validate_json(row[0]) for row in rows]

    @staticmethod
    def _utc_text(value: datetime) -> str:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ConfigurationError("store timestamps must be timezone-aware")
        return value.astimezone(UTC).isoformat()

    @staticmethod
    def _amount_text(value: Decimal) -> str:
        if not value.is_finite() or value < 0:
            raise ConfigurationError("stored economic amounts must be finite and non-negative")
        return format(value, "f")

    @staticmethod
    def _payment_operation_result_id(operation: str, idempotency_key: str) -> str:
        prefix = "settlement" if operation == "settle" else operation
        digest = hashlib.sha256(f"{prefix}\0{idempotency_key}".encode()).hexdigest()
        return f"{prefix}_{digest}"

    def save_provider_signing_key(self, key: TrustedProviderKey) -> TrustedProviderKey:
        self._save_immutable(
            table="provider_signing_keys",
            identity={"provider_id": key.provider_id, "key_id": key.key_id},
            indexed={
                "algorithm": key.algorithm.value,
                "status": key.status.value,
                "valid_from": self._utc_text(key.valid_from),
                "valid_until": self._utc_text(key.valid_until),
                "revoked_at": self._utc_text(key.revoked_at) if key.revoked_at else None,
            },
            value=key,
        )
        stored = self.get_provider_signing_key(key.provider_id, key.key_id)
        if stored is None:  # pragma: no cover - same-transaction insert invariant
            raise ConfigurationError("provider signing key disappeared after storage")
        return stored

    def get_provider_signing_key(self, provider_id: str, key_id: str) -> TrustedProviderKey | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT status, revoked_at, payload_json FROM provider_signing_keys
                WHERE provider_id = ? AND key_id = ?
                """,
                (provider_id, key_id),
            ).fetchone()
        return self._provider_key_from_row(row) if row else None

    @staticmethod
    def _provider_key_from_row(row: sqlite3.Row) -> TrustedProviderKey:
        key = TrustedProviderKey.model_validate_json(row["payload_json"])
        revoked_at = datetime.fromisoformat(row["revoked_at"]) if row["revoked_at"] else None
        return key.model_copy(
            update={"status": TrustedKeyStatus(row["status"]), "revoked_at": revoked_at}
        )

    def list_provider_signing_keys(
        self, *, provider_id: str | None = None, limit: int = 10_000
    ) -> list[TrustedProviderKey]:
        where = "WHERE provider_id = ?" if provider_id is not None else ""
        parameters: tuple[object, ...] = (provider_id,) if provider_id is not None else ()
        with self._lock:
            rows = self._connection.execute(
                f"""
                SELECT status, revoked_at, payload_json FROM provider_signing_keys
                {where} ORDER BY provider_id, key_id LIMIT ?
                """,
                (*parameters, max(1, min(limit, 10_000))),
            ).fetchall()
        return [self._provider_key_from_row(row) for row in rows]

    def revoke_provider_signing_key(
        self, provider_id: str, key_id: str, *, revoked_at: datetime
    ) -> TrustedProviderKey:
        revoked_text = self._utc_text(revoked_at)
        with self._immediate_transaction() as connection:
            row = connection.execute(
                """
                SELECT status, revoked_at, payload_json FROM provider_signing_keys
                WHERE provider_id = ? AND key_id = ?
                """,
                (provider_id, key_id),
            ).fetchone()
            if row is None:
                raise ConfigurationError("provider signing key does not exist")
            key = self._provider_key_from_row(row)
            if revoked_at < key.valid_from:
                raise ConfigurationError("key revocation cannot precede key validity")
            if key.status is TrustedKeyStatus.REVOKED:
                if key.revoked_at != revoked_at.astimezone(UTC):
                    raise ConfigurationError("provider signing key has a different revocation time")
                return key
            connection.execute(
                """
                UPDATE provider_signing_keys SET status = ?, revoked_at = ?
                WHERE provider_id = ? AND key_id = ?
                """,
                (TrustedKeyStatus.REVOKED.value, revoked_text, provider_id, key_id),
            )
            return key.model_copy(
                update={
                    "status": TrustedKeyStatus.REVOKED,
                    "revoked_at": revoked_at.astimezone(UTC),
                }
            )

    def retire_provider_signing_key(
        self, provider_id: str, key_id: str
    ) -> TrustedProviderKey:
        """Stop a rotated key signing new evidence without erasing history."""

        with self._immediate_transaction() as connection:
            row = connection.execute(
                """
                SELECT status, revoked_at, payload_json FROM provider_signing_keys
                WHERE provider_id = ? AND key_id = ?
                """,
                (provider_id, key_id),
            ).fetchone()
            if row is None:
                raise ConfigurationError("provider signing key does not exist")
            key = self._provider_key_from_row(row)
            if key.status is TrustedKeyStatus.REVOKED:
                raise ConfigurationError("revoked provider signing key cannot be retired")
            if key.status is TrustedKeyStatus.RETIRED:
                return key
            connection.execute(
                """
                UPDATE provider_signing_keys SET status = ?
                WHERE provider_id = ? AND key_id = ? AND status = ?
                """,
                (
                    TrustedKeyStatus.RETIRED.value,
                    provider_id,
                    key_id,
                    TrustedKeyStatus.ACTIVE.value,
                ),
            )
        return key.model_copy(update={"status": TrustedKeyStatus.RETIRED})

    def save_capability_offer(self, offer: CapabilityOffer) -> CapabilityOffer:
        return self._save_immutable(
            table="capability_offers",
            identity={"offer_id": offer.offer_id},
            indexed={
                "provider_id": offer.provider_id,
                "capability": offer.capability,
                "executor_id": offer.executor_id,
                "executor_fingerprint": offer.executor_fingerprint,
                "status": "active",
                "revoked_at": None,
                "valid_from": self._utc_text(offer.valid_from),
                "valid_until": self._utc_text(offer.valid_until),
                "signature_algorithm": offer.signature.algorithm.value,
                "signature_key_id": offer.signature.key_id,
                "evidence_level": "PUBLISHED_OFFER",
            },
            value=offer,
        )

    def get_capability_offer(
        self, offer_id: str, *, include_revoked: bool = False
    ) -> CapabilityOffer | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT status, payload_json FROM capability_offers WHERE offer_id = ?",
                (offer_id,),
            ).fetchone()
        if row is None or (row["status"] == "revoked" and not include_revoked):
            return None
        return CapabilityOffer.model_validate_json(row["payload_json"])

    def capability_offer_status(self, offer_id: str) -> dict[str, str | None] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT status, revoked_at FROM capability_offers WHERE offer_id = ?",
                (offer_id,),
            ).fetchone()
        return dict(row) if row else None

    def revoke_capability_offer(self, offer_id: str, *, revoked_at: datetime) -> CapabilityOffer:
        revoked_text = self._utc_text(revoked_at)
        with self._immediate_transaction() as connection:
            row = connection.execute(
                """
                SELECT status, revoked_at, payload_json FROM capability_offers WHERE offer_id = ?
                """,
                (offer_id,),
            ).fetchone()
            if row is None:
                raise ConfigurationError("capability offer does not exist")
            offer = CapabilityOffer.model_validate_json(row["payload_json"])
            if row["status"] == "revoked":
                if row["revoked_at"] != revoked_text:
                    raise ConfigurationError("capability offer has a different revocation time")
                return offer
            connection.execute(
                "UPDATE capability_offers SET status = 'revoked', revoked_at = ? WHERE offer_id = ?",
                (revoked_text, offer_id),
            )
            return offer

    def list_capability_offers(
        self,
        *,
        capability: str | None = None,
        provider_id: str | None = None,
        include_revoked: bool = False,
        limit: int = 1_000,
    ) -> list[CapabilityOffer]:
        clauses: list[str] = []
        parameters: list[object] = []
        if capability is not None:
            clauses.append("capability = ?")
            parameters.append(capability)
        if provider_id is not None:
            clauses.append("provider_id = ?")
            parameters.append(provider_id)
        if not include_revoked:
            clauses.append("status = 'active'")
        return self._list_typed(
            table="capability_offers",
            model=CapabilityOffer,
            clauses=tuple(clauses),
            parameters=tuple(parameters),
            order_by="valid_until DESC, offer_id",
            limit=limit,
        )

    def save_quote_request_v2(self, request: QuoteRequestV2) -> QuoteRequestV2:
        return self._save_immutable(
            table="quote_requests_v2",
            identity={"quote_request_id": request.quote_request_id},
            indexed={
                "action_id": request.action_id,
                "capability": request.capability,
                "executor_id": request.executor_id,
                "executor_fingerprint": request.executor_fingerprint,
                "action_digest": request.action_digest,
                "nonce": request.nonce,
                "created_at": self._utc_text(request.created_at),
                "expires_at": self._utc_text(request.expires_at),
            },
            value=request,
        )

    def get_quote_request_v2(self, quote_request_id: str) -> QuoteRequestV2 | None:
        return self._get_typed(
            table="quote_requests_v2",
            identity={"quote_request_id": quote_request_id},
            model=QuoteRequestV2,
        )

    def list_quote_requests_v2(
        self, *, action_id: str | None = None, limit: int = 1_000
    ) -> list[QuoteRequestV2]:
        return self._list_typed(
            table="quote_requests_v2",
            model=QuoteRequestV2,
            clauses=("action_id = ?",) if action_id is not None else (),
            parameters=(action_id,) if action_id is not None else (),
            order_by="created_at DESC, quote_request_id",
            limit=limit,
        )

    def prune_expired_quote_requests(self, *, expired_before: datetime, limit: int = 1_000) -> int:
        """Delete only expired requests that produced no retained quote evidence."""

        with self._immediate_transaction() as connection:
            cursor = connection.execute(
                """
                DELETE FROM quote_requests_v2
                WHERE quote_request_id IN (
                    SELECT request.quote_request_id
                    FROM quote_requests_v2 AS request
                    LEFT JOIN bounded_quotes AS quote
                        ON quote.quote_request_id = request.quote_request_id
                    WHERE request.expires_at < ? AND quote.quote_id IS NULL
                    ORDER BY request.expires_at
                    LIMIT ?
                )
                """,
                (self._utc_text(expired_before), max(1, min(limit, 10_000))),
            )
            return cursor.rowcount

    @staticmethod
    def _bounded_quote_indexed(quote: BoundedQuote) -> dict[str, object]:
        return {
            "quote_request_id": quote.quote_request_id,
            "offer_id": quote.offer_id,
            "provider_id": quote.provider_id,
            "capability": quote.capability,
            "executor_id": quote.executor_id,
            "executor_fingerprint": quote.executor_fingerprint,
            "action_digest": quote.action_digest,
            "nonce": quote.nonce,
            "expected_amount": (
                ReceiptStore._amount_text(quote.expected_amount.amount)
                if quote.expected_amount is not None
                else None
            ),
            "maximum_amount": ReceiptStore._amount_text(quote.maximum_amount.amount),
            "currency": quote.maximum_amount.currency,
            "issued_at": ReceiptStore._utc_text(quote.issued_at),
            "expires_at": ReceiptStore._utc_text(quote.expires_at),
            "signature_algorithm": quote.signature.algorithm.value,
            "signature_key_id": quote.signature.key_id,
            "evidence_level": quote.evidence_level.value,
        }

    def save_bounded_quote(self, quote: BoundedQuote) -> BoundedQuote:
        """Import immutable quote evidence without consuming it for execution."""

        return self._save_immutable(
            table="bounded_quotes",
            identity={"quote_id": quote.quote_id},
            indexed=self._bounded_quote_indexed(quote),
            value=quote,
        )

    def save_bounded_quote_and_use_nonce(
        self, quote: BoundedQuote, *, used_at: datetime
    ) -> BoundedQuote:
        """Atomically bind accepted quote evidence to its one permitted nonce use."""

        used_text = self._utc_text(used_at)
        try:
            with self._immediate_transaction() as connection:
                request_row = connection.execute(
                    """
                    SELECT payload_json
                    FROM quote_requests_v2 WHERE quote_request_id = ?
                    """,
                    (quote.quote_request_id,),
                ).fetchone()
                if request_row is None:
                    raise ConfigurationError("bounded quote request does not exist")
                request = QuoteRequestV2.model_validate_json(request_row["payload_json"])
                expected_bindings = {
                    "capability": quote.capability,
                    "executor_id": quote.executor_id,
                    "executor_fingerprint": quote.executor_fingerprint,
                    "action_digest": quote.action_digest,
                    "nonce": quote.nonce,
                    "desired_currency": quote.maximum_amount.currency,
                }
                if any(getattr(request, field) != value for field, value in expected_bindings.items()):
                    raise ConfigurationError("bounded quote does not match its request bindings")

                self._immutable_insert_locked(
                    connection,
                    table="bounded_quotes",
                    identity={"quote_id": quote.quote_id},
                    indexed=self._bounded_quote_indexed(quote),
                    value=quote,
                )
                existing = connection.execute(
                    """
                    SELECT quote_request_id, quote_id, action_digest, used_at
                    FROM quote_nonce_uses WHERE nonce = ?
                    """,
                    (quote.nonce,),
                ).fetchone()
                if existing is not None:
                    if (
                        existing["quote_request_id"] == quote.quote_request_id
                        and existing["quote_id"] == quote.quote_id
                        and existing["action_digest"] == quote.action_digest
                        and existing["used_at"] == used_text
                    ):
                        return quote
                    raise ConfigurationError(f"quote nonce {quote.nonce!r} was already used")
                connection.execute(
                    """
                    INSERT INTO quote_nonce_uses
                        (nonce, quote_request_id, quote_id, action_digest, used_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        quote.nonce,
                        quote.quote_request_id,
                        quote.quote_id,
                        quote.action_digest,
                        used_text,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ConfigurationError("bounded quote violates its request or nonce binding") from exc
        return quote

    def get_bounded_quote(self, quote_id: str) -> BoundedQuote | None:
        return self._get_typed(
            table="bounded_quotes", identity={"quote_id": quote_id}, model=BoundedQuote
        )

    def list_bounded_quotes(
        self,
        *,
        quote_request_id: str | None = None,
        provider_id: str | None = None,
        limit: int = 1_000,
    ) -> list[BoundedQuote]:
        clauses: list[str] = []
        parameters: list[object] = []
        if quote_request_id is not None:
            clauses.append("quote_request_id = ?")
            parameters.append(quote_request_id)
        if provider_id is not None:
            clauses.append("provider_id = ?")
            parameters.append(provider_id)
        return self._list_typed(
            table="bounded_quotes",
            model=BoundedQuote,
            clauses=tuple(clauses),
            parameters=tuple(parameters),
            order_by="issued_at DESC, quote_id",
            limit=limit,
        )

    def mark_quote_nonce_used(
        self,
        *,
        nonce: str,
        quote_request_id: str,
        quote_id: str,
        action_digest: str,
        used_at: datetime,
    ) -> None:
        try:
            with self._immediate_transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO quote_nonce_uses
                        (nonce, quote_request_id, quote_id, action_digest, used_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        nonce,
                        quote_request_id,
                        quote_id,
                        action_digest,
                        self._utc_text(used_at),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ConfigurationError(
                f"quote nonce {nonce!r} was already used or is invalid"
            ) from exc

    def quote_nonce_was_used(self, nonce: str) -> bool:
        with self._lock:
            return (
                self._connection.execute(
                    "SELECT 1 FROM quote_nonce_uses WHERE nonce = ?", (nonce,)
                ).fetchone()
                is not None
            )

    def save_prepared_decision(self, decision: PreparedRouteDecision) -> PreparedRouteDecision:
        self._save_immutable(
            table="prepared_route_decisions",
            identity={"prepared_id": decision.prepared_id},
            indexed={
                "action_id": decision.action_id,
                "action_digest": decision.action_digest,
                "effective_policy_digest": decision.effective_policy_digest,
                "selected_executor_id": decision.selected_executor_id,
                "selected_executor_fingerprint": decision.selected_executor_fingerprint,
                "selected_quote_id": decision.selected_quote_id,
                "selected_offer_id": decision.selected_offer_id,
                "selected_rate_card_id": decision.selected_rate_card_id,
                "authorization_kind": (
                    decision.authorization_kind.value
                    if decision.authorization_kind is not None
                    else None
                ),
                "authorization_id": decision.authorization_id,
                "maximum_amount": (
                    self._amount_text(decision.maximum_cash_authorization.amount)
                    if decision.maximum_cash_authorization is not None
                    else None
                ),
                "currency": (
                    decision.maximum_cash_authorization.currency
                    if decision.maximum_cash_authorization is not None
                    else None
                ),
                "state": decision.state.value,
                "claim_token": None,
                "claimed_at": None,
                "created_at": self._utc_text(decision.created_at),
                "expires_at": self._utc_text(decision.expires_at),
            },
            value=decision,
        )
        stored = self.get_prepared_decision(decision.prepared_id)
        if stored is None:  # pragma: no cover - same-transaction insert invariant
            raise ConfigurationError("prepared decision disappeared after storage")
        return stored

    @staticmethod
    def _prepared_from_row(row: sqlite3.Row) -> PreparedRouteDecision:
        decision = PreparedRouteDecision.model_validate_json(row["payload_json"])
        state = PreparedDecisionState(row["state"])
        return decision if decision.state is state else decision.model_copy(update={"state": state})

    def get_prepared_decision(self, prepared_id: str) -> PreparedRouteDecision | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT state, payload_json FROM prepared_route_decisions WHERE prepared_id = ?",
                (prepared_id,),
            ).fetchone()
        return self._prepared_from_row(row) if row else None

    def list_prepared_decisions(
        self,
        *,
        states: Iterable[PreparedDecisionState] | None = None,
        limit: int = 1_000,
    ) -> list[PreparedRouteDecision]:
        state_values = tuple(state.value for state in states) if states is not None else ()
        where = ""
        parameters: tuple[object, ...] = ()
        if state_values:
            where = f"WHERE state IN ({', '.join('?' for _ in state_values)})"
            parameters = state_values
        with self._lock:
            rows = self._connection.execute(
                f"""
                SELECT state, payload_json FROM prepared_route_decisions
                {where} ORDER BY created_at DESC, prepared_id LIMIT ?
                """,
                (*parameters, max(1, min(limit, 10_000))),
            ).fetchall()
        return [self._prepared_from_row(row) for row in rows]

    def claim_prepared_decision(
        self,
        prepared_id: str,
        *,
        claim_token: str,
        claimed_at: datetime,
    ) -> PreparedRouteDecision:
        if not claim_token or len(claim_token) > 256:
            raise ConfigurationError("prepared claim token must be non-empty and bounded")
        now_text = self._utc_text(claimed_at)
        with self._immediate_transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE prepared_route_decisions
                SET claim_token = ?, claimed_at = ?
                WHERE prepared_id = ? AND state = ? AND claim_token IS NULL AND expires_at > ?
                """,
                (
                    claim_token,
                    now_text,
                    prepared_id,
                    PreparedDecisionState.PREPARED.value,
                    now_text,
                ),
            )
            row = connection.execute(
                """
                SELECT state, claim_token, expires_at, payload_json
                FROM prepared_route_decisions WHERE prepared_id = ?
                """,
                (prepared_id,),
            ).fetchone()
            if row is None:
                raise ConfigurationError("prepared decision does not exist")
            if (
                row["state"] == PreparedDecisionState.PREPARED.value
                and row["expires_at"] <= now_text
            ):
                raise ConfigurationError("prepared decision has expired")
            if cursor.rowcount != 1 and row["claim_token"] != claim_token:
                raise ConfigurationError("prepared decision is not claimable")
            return self._prepared_from_row(row)

    def claim_prepared_decision_with_action_idempotency(
        self,
        prepared_id: str,
        *,
        claim_token: str,
        claimed_at: datetime,
        idempotency_key: str,
        action_digest: str,
    ) -> PreparedRouteDecision:
        """Atomically claim a keyed action and its prepared decision.

        No committed state can contain the caller action claim/binding without the
        prepared claim token. This closes the pre-invocation crash window while
        retaining only the action digest, never the action input.
        """

        if not claim_token or len(claim_token) > 256:
            raise ConfigurationError("prepared claim token must be non-empty and bounded")
        if not idempotency_key or len(idempotency_key) > 256:
            raise ConfigurationError("action idempotency key must be non-empty and bounded")
        if len(action_digest) != 71 or not action_digest.startswith("sha256:"):
            raise ConfigurationError("prepared action digest must be canonical SHA-256")
        claimed_text = self._utc_text(claimed_at)
        try:
            with self._immediate_transaction() as connection:
                prepared = connection.execute(
                    """
                    SELECT state, claim_token, expires_at, action_digest, payload_json
                    FROM prepared_route_decisions WHERE prepared_id = ?
                    """,
                    (prepared_id,),
                ).fetchone()
                if prepared is None:
                    raise ConfigurationError("prepared decision does not exist")
                if prepared["action_digest"] != action_digest:
                    raise ConfigurationError(
                        "prepared action idempotency digest does not match"
                    )
                if prepared["state"] != PreparedDecisionState.PREPARED.value:
                    raise ConfigurationError("prepared decision is not claimable")
                if prepared["expires_at"] <= claimed_text:
                    raise ConfigurationError("prepared decision has expired")
                if prepared["claim_token"] not in {None, claim_token}:
                    raise ConfigurationError("prepared decision is not claimable")

                action_claim = connection.execute(
                    """
                    SELECT request_hash, state FROM idempotency_records
                    WHERE idempotency_key = ?
                    """,
                    (idempotency_key,),
                ).fetchone()
                if action_claim is not None and (
                    action_claim["request_hash"] != action_digest
                    or action_claim["state"] != "claimed"
                ):
                    raise ConfigurationError(
                        "action idempotency key is already bound to another result"
                    )
                binding_rows = connection.execute(
                    """
                    SELECT * FROM prepared_action_idempotency
                    WHERE prepared_id = ? OR idempotency_key = ?
                    """,
                    (prepared_id, idempotency_key),
                ).fetchall()
                if binding_rows:
                    if len(binding_rows) != 1:
                        raise ConfigurationError(
                            "prepared action idempotency binding conflicts"
                        )
                    binding = self._prepared_action_idempotency_from_row(
                        binding_rows[0]
                    )
                    if (
                        binding["prepared_id"] != prepared_id
                        or binding["idempotency_key"] != idempotency_key
                        or binding["action_digest"] != action_digest
                    ):
                        raise ConfigurationError(
                            "prepared action idempotency binding conflicts"
                        )

                if action_claim is None:
                    connection.execute(
                        """
                        INSERT INTO idempotency_records
                            (idempotency_key, request_hash, state)
                        VALUES (?, ?, 'claimed')
                        """,
                        (idempotency_key, action_digest),
                    )
                if not binding_rows:
                    connection.execute(
                        """
                        INSERT INTO prepared_action_idempotency
                            (prepared_id, idempotency_key, action_digest, bound_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (prepared_id, idempotency_key, action_digest, claimed_text),
                    )
                if prepared["claim_token"] is None:
                    cursor = connection.execute(
                        """
                        UPDATE prepared_route_decisions
                        SET claim_token = ?, claimed_at = ?
                        WHERE prepared_id = ? AND state = ? AND claim_token IS NULL
                          AND expires_at > ?
                        """,
                        (
                            claim_token,
                            claimed_text,
                            prepared_id,
                            PreparedDecisionState.PREPARED.value,
                            claimed_text,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise ConfigurationError("prepared decision lost its claim race")
                row = connection.execute(
                    """
                    SELECT state, payload_json FROM prepared_route_decisions
                    WHERE prepared_id = ?
                    """,
                    (prepared_id,),
                ).fetchone()
        except sqlite3.IntegrityError as exc:
            raise ConfigurationError("atomic prepared action claim failed") from exc
        return self._prepared_from_row(row)

    def save_prepared_transition(
        self, transition: PreparedRouteTransition
    ) -> PreparedRouteTransition:
        if transition.from_state is PreparedDecisionState.PREPARED:
            if transition.to_state is PreparedDecisionState.RESERVED:
                raise ConfigurationError(
                    "PREPARED to RESERVED requires atomic claim-bound payment reservation"
                )
            if transition.to_state is PreparedDecisionState.INVOKING:
                raise ConfigurationError(
                    "direct prepared invocation requires the claim-guarded free-route operation"
                )
        if (
            transition.from_state is PreparedDecisionState.RESERVED
            and transition.to_state is PreparedDecisionState.INVOKING
        ):
            raise ConfigurationError(
                "paid prepared invocation requires atomic route and trust revalidation"
            )
        with self._immediate_transaction() as connection:
            self._transition_prepared_locked(connection, transition)
        return transition

    def _transition_prepared_locked(
        self,
        connection: sqlite3.Connection,
        transition: PreparedRouteTransition,
        *,
        required_claim_token: str | None = None,
    ) -> None:
        existing = connection.execute(
            """
            SELECT payload_digest, payload_json FROM prepared_route_transitions
            WHERE transition_id = ?
            """,
            (transition.transition_id,),
        ).fetchone()
        if existing is not None:
            payload = transition.model_dump_json()
            if (
                existing["payload_digest"] != canonical_digest(transition)
                or existing["payload_json"] != payload
            ):
                raise ConfigurationError(
                    "immutable prepared transition ID was reused with different content"
                )
            return
        if (
            transition.from_state is PreparedDecisionState.RESERVED
            and transition.to_state is PreparedDecisionState.INVOKING
        ):
            reservation = connection.execute(
                """
                SELECT state, operation_intent FROM payment_reservations_v2
                WHERE prepared_id = ?
                """,
                (transition.prepared_id,),
            ).fetchone()
            if (
                reservation is None
                or reservation["state"] != PaymentReservationState.RESERVED.value
                or reservation["operation_intent"] is not None
            ):
                raise ConfigurationError(
                    "prepared invocation conflicts with its payment operation state"
                )
        claim_clause = " AND claim_token = ?" if required_claim_token is not None else ""
        parameters: list[object] = [
            transition.to_state.value,
            transition.prepared_id,
            transition.from_state.value,
        ]
        if required_claim_token is not None:
            parameters.append(required_claim_token)
        cursor = connection.execute(
            f"""
            UPDATE prepared_route_decisions SET state = ?
            WHERE prepared_id = ? AND state = ?{claim_clause}
            """,
            parameters,
        )
        if cursor.rowcount != 1:
            raise ConfigurationError("prepared decision transition lost its state or claim race")
        self._immutable_insert_locked(
            connection,
            table="prepared_route_transitions",
            identity={"transition_id": transition.transition_id},
            indexed={
                "prepared_id": transition.prepared_id,
                "from_state": transition.from_state.value,
                "to_state": transition.to_state.value,
                "occurred_at": self._utc_text(transition.occurred_at),
                "reason": transition.reason,
            },
            value=transition,
        )

    transition_prepared_decision = save_prepared_transition

    def claim_prepared_for_invocation(
        self,
        prepared_id: str,
        *,
        claim_token: str,
        expected_action_digest: str,
        expected_policy_digest: str,
        expected_executor_fingerprint: str,
        invoked_at: datetime,
    ) -> PreparedRouteDecision:
        """Atomically enter INVOKING for a claimed, confirmed-free route.

        Paid routes must use :meth:`reserve_payment_v2`. A quote-free route is
        executable through this operation only when its authoritative local
        accounting distinguishes confirmed zero from unknown cash.
        """

        if not claim_token or len(claim_token) > 256:
            raise ConfigurationError("prepared invocation requires a bounded claim token")
        invoked_text = self._utc_text(invoked_at)
        with self._immediate_transaction() as connection:
            row = connection.execute(
                """
                SELECT state, claim_token, expires_at, payload_json
                FROM prepared_route_decisions WHERE prepared_id = ?
                """,
                (prepared_id,),
            ).fetchone()
            if row is None:
                raise ConfigurationError("prepared decision does not exist")
            decision = self._prepared_from_row(row)
            if row["state"] != PreparedDecisionState.PREPARED.value:
                raise ConfigurationError("prepared decision is not claimable for invocation")
            if row["claim_token"] != claim_token:
                raise ConfigurationError("prepared invocation does not own the claim")
            if row["expires_at"] <= invoked_text:
                raise ConfigurationError("prepared decision has expired")
            if (
                decision.action_digest != expected_action_digest
                or decision.effective_policy_digest != expected_policy_digest
                or decision.selected_executor_fingerprint != expected_executor_fingerprint
            ):
                raise ConfigurationError("prepared invocation binding changed after revalidation")
            authorization = decision.maximum_cash_authorization
            if decision.selected_quote_id is not None or authorization is None:
                raise ConfigurationError("paid or unknown-cost routes require a reservation")
            if authorization.amount != 0:
                raise ConfigurationError("paid routes require a reservation")
            if (
                decision.expected_accounting.cash.actual_cash_cost(authorization.currency)
                != Decimal(0)
            ):
                raise ConfigurationError("quote-free invocation requires confirmed zero cash")
            transition = PreparedRouteTransition(
                prepared_id=prepared_id,
                from_state=PreparedDecisionState.PREPARED,
                to_state=PreparedDecisionState.INVOKING,
                occurred_at=invoked_at,
                reason="confirmed-free claimed invocation",
            )
            self._transition_prepared_locked(
                connection,
                transition,
                required_claim_token=claim_token,
            )
        return decision.model_copy(update={"state": PreparedDecisionState.INVOKING})

    def claim_prepared_for_paid_invocation(
        self,
        prepared_id: str,
        *,
        claim_token: str,
        expected_action_digest: str,
        expected_policy_digest: str,
        expected_executor_id: str,
        expected_executor_fingerprint: str,
        expected_authorization_kind: AuthorizationKind,
        expected_authorization_id: str,
        invoked_at: datetime,
    ) -> PreparedRouteDecision:
        """Atomically establish the paid invocation point of no return.

        Imported candidates and economic trust stored in SQLite are rechecked in
        the same write transaction as RESERVED -> INVOKING. A missing candidate
        row denotes a trusted manifest route; its in-memory mutation boundary is
        intentionally owned by the Router lock rather than this database.
        """

        if not claim_token or len(claim_token) > 256:
            raise ConfigurationError("prepared claim token must be non-empty and bounded")
        invoked_text = self._utc_text(invoked_at)
        with self._immediate_transaction() as connection:
            row = connection.execute(
                """
                SELECT state, claim_token, expires_at, action_digest,
                       effective_policy_digest, selected_executor_id,
                       selected_executor_fingerprint, authorization_kind,
                       authorization_id, maximum_amount, currency, payload_json
                FROM prepared_route_decisions WHERE prepared_id = ?
                """,
                (prepared_id,),
            ).fetchone()
            if row is None:
                raise ConfigurationError("prepared decision does not exist")
            expected_bindings = (
                (row["action_digest"], expected_action_digest, "action digest"),
                (
                    row["effective_policy_digest"],
                    expected_policy_digest,
                    "policy digest",
                ),
                (row["selected_executor_id"], expected_executor_id, "executor"),
                (
                    row["selected_executor_fingerprint"],
                    expected_executor_fingerprint,
                    "executor fingerprint",
                ),
                (
                    row["authorization_kind"],
                    expected_authorization_kind.value,
                    "authorization kind",
                ),
                (
                    row["authorization_id"],
                    expected_authorization_id,
                    "authorization ID",
                ),
            )
            if any(actual != expected for actual, expected, _ in expected_bindings):
                label = next(
                    label
                    for actual, expected, label in expected_bindings
                    if actual != expected
                )
                raise ConfigurationError(f"prepared paid invocation {label} changed")
            if row["state"] != PreparedDecisionState.RESERVED.value:
                raise ConfigurationError("prepared decision is not reserved for invocation")
            if row["claim_token"] != claim_token:
                raise ConfigurationError("prepared paid invocation does not own the claim")
            if row["expires_at"] <= invoked_text:
                raise ConfigurationError("prepared decision has expired")
            decision = PreparedRouteDecision.model_validate_json(row["payload_json"])
            reservation_row = connection.execute(
                """
                SELECT state, operation_intent, authorization_kind, authorization_id,
                       quote_id, maximum_amount, currency, payload_json
                FROM payment_reservations_v2 WHERE prepared_id = ?
                """,
                (prepared_id,),
            ).fetchone()
            if reservation_row is None:
                raise ConfigurationError("prepared paid invocation reservation is missing")
            if (
                reservation_row["state"] != PaymentReservationState.RESERVED.value
                or reservation_row["operation_intent"] is not None
                or reservation_row["authorization_kind"]
                != expected_authorization_kind.value
                or reservation_row["authorization_id"] != expected_authorization_id
                or reservation_row["maximum_amount"] != row["maximum_amount"]
                or reservation_row["currency"] != row["currency"]
            ):
                raise ConfigurationError(
                    "prepared paid invocation reservation binding changed"
                )
            reservation = PaymentReservationV2.model_validate_json(
                reservation_row["payload_json"]
            )
            candidate = connection.execute(
                """
                SELECT status, fingerprint FROM route_candidates
                WHERE executor_id = ?
                """,
                (expected_executor_id,),
            ).fetchone()
            if candidate is not None and (
                candidate["status"] != "active"
                or candidate["fingerprint"]
                != expected_executor_fingerprint.removeprefix("sha256:")
            ):
                raise ConfigurationError(
                    "imported route is not active with the prepared fingerprint"
                )

            authorized_maximum: CurrencyAmount
            if expected_authorization_kind is AuthorizationKind.SIGNED_QUOTE:
                quote_row = connection.execute(
                    "SELECT payload_json FROM bounded_quotes WHERE quote_id = ?",
                    (expected_authorization_id,),
                ).fetchone()
                if quote_row is None:
                    raise ConfigurationError("signed quote authorization is missing")
                quote = BoundedQuote.model_validate_json(quote_row["payload_json"])
                if (
                    decision.selected_quote_id != quote.quote_id
                    or reservation.quote_id != quote.quote_id
                    or quote.action_digest != decision.action_digest
                    or quote.executor_id != expected_executor_id
                    or quote.executor_fingerprint != expected_executor_fingerprint
                    or quote.expires_at <= invoked_at
                ):
                    raise ConfigurationError("signed quote invocation binding changed")
                key = self._require_active_signing_key_locked(
                    connection,
                    provider_id=quote.provider_id,
                    key_id=quote.signature.key_id,
                    algorithm=quote.signature.algorithm.value,
                    at=invoked_at,
                    capability=quote.capability,
                )
                self._require_valid_authorization_signature(
                    quote, key=key, at=invoked_at
                )
                authorized_maximum = quote.maximum_amount
            elif expected_authorization_kind is AuthorizationKind.PUBLISHED_OFFER:
                offer_row = connection.execute(
                    """
                    SELECT status, revoked_at, payload_json FROM capability_offers
                    WHERE offer_id = ?
                    """,
                    (expected_authorization_id,),
                ).fetchone()
                if offer_row is None:
                    raise ConfigurationError("published offer authorization is missing")
                offer = CapabilityOffer.model_validate_json(offer_row["payload_json"])
                if (
                    decision.selected_offer_id != offer.offer_id
                    or offer.executor_id != expected_executor_id
                    or offer.executor_fingerprint != expected_executor_fingerprint
                    or offer_row["status"] != "active"
                    or offer_row["revoked_at"] is not None
                    or offer.valid_from > invoked_at
                    or offer.valid_until <= invoked_at
                ):
                    raise ConfigurationError(
                        "published offer invocation authorization is not active"
                    )
                key = self._require_active_signing_key_locked(
                    connection,
                    provider_id=offer.provider_id,
                    key_id=offer.signature.key_id,
                    algorithm=offer.signature.algorithm.value,
                    at=invoked_at,
                    capability=offer.capability,
                )
                self._require_valid_authorization_signature(
                    offer, key=key, at=invoked_at
                )
                authorized_maximum = self._offer_authorized_maximum(offer, decision)
            elif expected_authorization_kind is AuthorizationKind.PINNED_RATE_CARD:
                rate_row = connection.execute(
                    "SELECT payload_json FROM rate_card_snapshots WHERE snapshot_id = ?",
                    (expected_authorization_id,),
                ).fetchone()
                if rate_row is None:
                    raise ConfigurationError("pinned rate-card authorization is missing")
                snapshot = RateCardSnapshot.model_validate_json(rate_row["payload_json"])
                if (
                    decision.selected_rate_card_id != snapshot.snapshot_id
                    or snapshot.effective_from > invoked_at
                    or (
                        snapshot.effective_until is not None
                        and snapshot.effective_until <= invoked_at
                    )
                ):
                    raise ConfigurationError(
                        "pinned rate-card invocation authorization is not active"
                    )
                authorized_maximum = self._rate_card_authorized_maximum(
                    snapshot, decision
                )
            else:  # pragma: no cover - enum is exhaustive for paid authorization
                raise ConfigurationError("unsupported paid invocation authorization")
            if authorized_maximum != reservation.maximum_amount:
                raise ConfigurationError(
                    "paid invocation authorization maximum changed"
                )
            transition = PreparedRouteTransition(
                prepared_id=prepared_id,
                from_state=PreparedDecisionState.RESERVED,
                to_state=PreparedDecisionState.INVOKING,
                occurred_at=invoked_at,
                reason="claimed paid invocation after atomic route and trust revalidation",
            )
            self._transition_prepared_locked(
                connection,
                transition,
                required_claim_token=claim_token,
            )
        return decision.model_copy(update={"state": PreparedDecisionState.INVOKING})

    def get_prepared_transition(self, transition_id: str) -> PreparedRouteTransition | None:
        return self._get_typed(
            table="prepared_route_transitions",
            identity={"transition_id": transition_id},
            model=PreparedRouteTransition,
        )

    def list_prepared_transitions(
        self, prepared_id: str, *, limit: int = 1_000
    ) -> list[PreparedRouteTransition]:
        return self._list_typed(
            table="prepared_route_transitions",
            model=PreparedRouteTransition,
            clauses=("prepared_id = ?",),
            parameters=(prepared_id,),
            order_by="occurred_at, transition_id",
            limit=limit,
        )

    def recoverable_prepared_decisions(
        self, *, as_of: datetime | None = None, limit: int = 1_000
    ) -> list[PreparedRouteDecision]:
        as_of_text = self._utc_text(as_of) if as_of is not None else None
        states = (
            PreparedDecisionState.RESERVED,
            PreparedDecisionState.INVOKING,
            PreparedDecisionState.AWAITING_USAGE,
            PreparedDecisionState.SETTLING,
            PreparedDecisionState.INDETERMINATE,
        )
        placeholders = ", ".join("?" for _ in states)
        with self._lock:
            rows = self._connection.execute(
                f"""
                SELECT state, payload_json FROM prepared_route_decisions
                WHERE state IN ({placeholders})
                   OR (state = ? AND claim_token IS NOT NULL
                       AND ? IS NOT NULL AND expires_at <= ?)
                ORDER BY created_at, prepared_id LIMIT ?
                """,
                (
                    *(state.value for state in states),
                    PreparedDecisionState.PREPARED.value,
                    as_of_text,
                    as_of_text,
                    max(1, min(limit, 10_000)),
                ),
            ).fetchall()
        return [self._prepared_from_row(row) for row in rows]

    scan_incomplete_prepared_decisions = recoverable_prepared_decisions

    @staticmethod
    def _prepared_action_idempotency_from_row(
        row: sqlite3.Row,
    ) -> PreparedActionIdempotencyRecord:
        return PreparedActionIdempotencyRecord(
            prepared_id=row["prepared_id"],
            idempotency_key=row["idempotency_key"],
            action_digest=row["action_digest"],
            bound_at=datetime.fromisoformat(row["bound_at"]),
        )

    def bind_prepared_action_idempotency(
        self,
        prepared_id: str,
        *,
        idempotency_key: str,
        action_digest: str,
        bound_at: datetime,
    ) -> PreparedActionIdempotencyRecord:
        """Bind a caller key to one prepared digest without storing action input."""

        if not idempotency_key or len(idempotency_key) > 256:
            raise ConfigurationError("action idempotency key must be non-empty and bounded")
        if len(action_digest) != 71 or not action_digest.startswith("sha256:"):
            raise ConfigurationError("prepared action digest must be canonical SHA-256")
        self._utc_text(bound_at)
        with self._immediate_transaction() as connection:
            prepared = connection.execute(
                """
                SELECT state, action_digest FROM prepared_route_decisions
                WHERE prepared_id = ?
                """,
                (prepared_id,),
            ).fetchone()
            if prepared is None:
                raise ConfigurationError("prepared action idempotency decision is missing")
            if prepared["action_digest"] != action_digest:
                raise ConfigurationError("prepared action idempotency digest does not match")
            existing_rows = connection.execute(
                """
                SELECT * FROM prepared_action_idempotency
                WHERE prepared_id = ? OR idempotency_key = ?
                """,
                (prepared_id, idempotency_key),
            ).fetchall()
            if existing_rows:
                if len(existing_rows) != 1:
                    raise ConfigurationError("prepared action idempotency binding conflicts")
                existing = self._prepared_action_idempotency_from_row(existing_rows[0])
                if (
                    existing["prepared_id"] != prepared_id
                    or existing["idempotency_key"] != idempotency_key
                    or existing["action_digest"] != action_digest
                ):
                    raise ConfigurationError("prepared action idempotency binding conflicts")
                return existing
            raise ConfigurationError(
                "new action idempotency binding requires atomic prepared claim"
            )

    def get_prepared_action_idempotency(
        self, prepared_id: str
    ) -> PreparedActionIdempotencyRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM prepared_action_idempotency WHERE prepared_id = ?",
                (prepared_id,),
            ).fetchone()
        return self._prepared_action_idempotency_from_row(row) if row else None

    def abandon_prepared_action_idempotency(
        self,
        prepared_id: str,
        *,
        action_digest: str,
        abandoned_at: datetime,
        claim_token: str | None = None,
    ) -> PreparedRouteDecision:
        """Atomically abandon a keyed action proven not to have been invoked.

        PREPARED claims are cancelled in the same transaction. RELEASED claims
        require a durable full-release settlement. Later execution states are
        never eligible, so uncertainty cannot reopen a consequential action.
        """

        self._utc_text(abandoned_at)
        with self._immediate_transaction() as connection:
            row = connection.execute(
                """
                SELECT prepared.state, prepared.claim_token, prepared.expires_at,
                       prepared.payload_json,
                       binding.idempotency_key, binding.action_digest,
                       action.request_hash, action.state AS action_state
                FROM prepared_route_decisions AS prepared
                JOIN prepared_action_idempotency AS binding
                  ON binding.prepared_id = prepared.prepared_id
                JOIN idempotency_records AS action
                  ON action.idempotency_key = binding.idempotency_key
                WHERE prepared.prepared_id = ?
                """,
                (prepared_id,),
            ).fetchone()
            if row is None:
                raise ConfigurationError(
                    "prepared action idempotency binding is unavailable"
                )
            if (
                row["action_digest"] != action_digest
                or row["request_hash"] != action_digest
            ):
                raise ConfigurationError(
                    "prepared action abandonment digest does not match"
                )
            if claim_token is not None and row["claim_token"] != claim_token:
                raise ConfigurationError(
                    "prepared action abandonment does not own the claim"
                )
            if row["action_state"] != "claimed":
                raise ConfigurationError(
                    "executing or completed action idempotency cannot be abandoned"
                )
            state = PreparedDecisionState(row["state"])
            if state is PreparedDecisionState.PREPARED:
                if claim_token is None and row["expires_at"] > self._utc_text(abandoned_at):
                    raise ConfigurationError(
                        "live prepared action cannot be abandoned by recovery"
                    )
                reservation = connection.execute(
                    """
                    SELECT 1 FROM payment_reservations_v2
                    WHERE prepared_id = ? LIMIT 1
                    """,
                    (prepared_id,),
                ).fetchone()
                if reservation is not None:
                    raise ConfigurationError(
                        "prepared action with a reservation cannot be abandoned"
                    )
                self._transition_prepared_locked(
                    connection,
                    PreparedRouteTransition(
                        prepared_id=prepared_id,
                        from_state=PreparedDecisionState.PREPARED,
                        to_state=PreparedDecisionState.CANCELLED,
                        occurred_at=abandoned_at,
                        reason="pre-invocation action idempotency claim abandoned",
                    ),
                )
            elif state is PreparedDecisionState.RELEASED:
                released = connection.execute(
                    """
                    SELECT settlement.captured_amount
                    FROM payment_reservations_v2 AS reservation
                    JOIN settlement_receipts AS settlement
                      ON settlement.reservation_id = reservation.reservation_id
                    WHERE reservation.prepared_id = ?
                      AND reservation.state = ? AND settlement.status = ?
                    LIMIT 1
                    """,
                    (
                        prepared_id,
                        PaymentReservationState.RELEASED.value,
                        SettlementStatus.RELEASED.value,
                    ),
                ).fetchone()
                if released is None or Decimal(released["captured_amount"]) != 0:
                    raise ConfigurationError(
                        "released prepared action lacks full-release evidence"
                    )
            else:
                raise ConfigurationError(
                    f"prepared action cannot be abandoned from state {state.value}"
                )
            connection.execute(
                "DELETE FROM prepared_action_idempotency WHERE prepared_id = ?",
                (prepared_id,),
            )
            cursor = connection.execute(
                """
                DELETE FROM idempotency_records
                WHERE idempotency_key = ? AND request_hash = ? AND state = 'claimed'
                """,
                (row["idempotency_key"], action_digest),
            )
            if cursor.rowcount != 1:
                raise ConfigurationError(
                    "prepared action idempotency claim lost its abandonment race"
                )
            prepared_row = connection.execute(
                """
                SELECT state, payload_json FROM prepared_route_decisions
                WHERE prepared_id = ?
                """,
                (prepared_id,),
            ).fetchone()
        return self._prepared_from_row(prepared_row)

    def complete_prepared_action_idempotency(
        self,
        prepared_id: str,
        *,
        action_digest: str,
        decision_id: str,
        status: str,
        receipt_id: str,
    ) -> None:
        """Complete only a bound, settled action from exact durable local evidence."""

        with self._immediate_transaction() as connection:
            row = connection.execute(
                """
                SELECT binding.idempotency_key, binding.action_digest,
                       prepared.state, prepared.action_id,
                       prepared.selected_executor_id, prepared.payload_json
                FROM prepared_action_idempotency AS binding
                JOIN prepared_route_decisions AS prepared
                  ON prepared.prepared_id = binding.prepared_id
                WHERE binding.prepared_id = ?
                """,
                (prepared_id,),
            ).fetchone()
            if row is None:
                raise ConfigurationError(
                    "settled prepared action idempotency evidence is incomplete"
                )
            if (
                row["action_digest"] != action_digest
                or row["state"] != PreparedDecisionState.SETTLED.value
            ):
                raise ConfigurationError(
                    "prepared action idempotency is not bound to a settled action"
                )
            receipt_row = connection.execute(
                "SELECT payload_json FROM receipts WHERE receipt_id = ?",
                (receipt_id,),
            ).fetchone()
            if receipt_row is None:
                raise ConfigurationError("prepared action final receipt is missing")
            receipt = ExecutionReceipt.model_validate_json(receipt_row["payload_json"])
            base_binding_conflicts = (
                receipt.decision_id != decision_id
                or receipt.status.value != status
                or receipt.action_id != row["action_id"]
                or receipt.executor_id != row["selected_executor_id"]
                or receipt.metadata.get("prepared_id") != prepared_id
            )
            if base_binding_conflicts:
                raise ConfigurationError(
                    "prepared action final receipt binding does not match its decision"
                )
            reservation = connection.execute(
                """
                SELECT reservation_id, attempt_id, charge_id, state
                FROM payment_reservations_v2 WHERE prepared_id = ?
                """,
                (prepared_id,),
            ).fetchone()
            if reservation is None:
                prepared = PreparedRouteDecision.model_validate_json(row["payload_json"])
                maximum = prepared.maximum_cash_authorization
                if maximum is None:
                    raise ConfigurationError(
                        "prepared action free-route evidence is incomplete"
                    )
                if (
                    prepared.authorization_kind is not None
                    or prepared.authorization_id is not None
                    or maximum.amount != 0
                    or prepared.expected_accounting.cash.actual_cash_cost(
                        maximum.currency
                    )
                    != Decimal(0)
                    or not isinstance(receipt.metadata.get("attempt_id"), str)
                    or not receipt.metadata.get("attempt_id")
                    or not isinstance(receipt.metadata.get("charge_id"), str)
                    or not receipt.metadata.get("charge_id")
                    or receipt.metadata.get("settlement_id") is not None
                ):
                    raise ConfigurationError(
                        "prepared action free-route evidence is incomplete"
                    )
            else:
                settlement = connection.execute(
                    """
                    SELECT settlement_id, status FROM settlement_receipts
                    WHERE reservation_id = ?
                    """,
                    (reservation["reservation_id"],),
                ).fetchone()
                if (
                    reservation["state"] != PaymentReservationState.SETTLED.value
                    or settlement is None
                    or settlement["status"]
                    not in {
                        SettlementStatus.COMPLETED.value,
                        SettlementStatus.SETTLED.value,
                    }
                    or receipt.metadata.get("attempt_id") != reservation["attempt_id"]
                    or receipt.metadata.get("charge_id") != reservation["charge_id"]
                    or receipt.metadata.get("settlement_id")
                    != settlement["settlement_id"]
                ):
                    raise ConfigurationError(
                        "prepared action final receipt binding does not match settlement"
                    )
            action_claim = connection.execute(
                """
                SELECT request_hash, state, decision_id, status, receipt_ids_json
                FROM idempotency_records WHERE idempotency_key = ?
                """,
                (row["idempotency_key"],),
            ).fetchone()
            if action_claim is None or action_claim["request_hash"] != action_digest:
                raise ConfigurationError("prepared action idempotency claim is missing")
            expected_receipts = json.dumps([receipt_id])
            if action_claim["state"] == "complete":
                if (
                    action_claim["decision_id"] == decision_id
                    and action_claim["status"] == status
                    and action_claim["receipt_ids_json"] == expected_receipts
                ):
                    return
                raise ConfigurationError(
                    "prepared action idempotency completion conflicts with durable result"
                )
            cursor = connection.execute(
                """
                UPDATE idempotency_records
                SET state = 'complete', decision_id = ?, status = ?, receipt_ids_json = ?
                WHERE idempotency_key = ?
                  AND state IN ('claimed', 'executing', 'indeterminate')
                """,
                (
                    decision_id,
                    status,
                    expected_receipts,
                    row["idempotency_key"],
                ),
            )
            if cursor.rowcount != 1:
                raise ConfigurationError(
                    "prepared action idempotency claim cannot be completed"
                )

    def free_actions_needing_finalization(
        self, *, limit: int = 1_000
    ) -> list[PreparedActionFinalizationRecord]:
        """Find durable confirmed-free actions needing state/key finalization.

        Results contain only durable local evidence and are recovery inputs for
        ``complete_prepared_action_idempotency``; they never authorize invocation.
        A missing/ambiguous receipt is returned with null receipt fields so the
        caller can report the row unresolved instead of silently losing it.
        """

        bounded_limit = max(1, min(limit, 10_000))
        results: list[PreparedActionFinalizationRecord] = []
        last_created_at: str | None = None
        last_prepared_id = ""
        with self._lock:
            while len(results) < bounded_limit:
                rows = self._connection.execute(
                    """
                    SELECT prepared.prepared_id, prepared.created_at, prepared.state,
                           prepared.action_id, prepared.selected_executor_id,
                           binding.action_digest, action.request_hash,
                           action.state AS action_state,
                           action.decision_id AS action_decision_id,
                           action.status AS action_status,
                           action.receipt_ids_json
                    FROM prepared_route_decisions AS prepared
                    JOIN prepared_action_idempotency AS binding
                      ON binding.prepared_id = prepared.prepared_id
                    LEFT JOIN idempotency_records AS action
                      ON action.idempotency_key = binding.idempotency_key
                    LEFT JOIN payment_reservations_v2 AS reservation
                      ON reservation.prepared_id = prepared.prepared_id
                    WHERE prepared.state IN (?, ?, ?, ?)
                      AND reservation.reservation_id IS NULL
                      AND (
                        ? IS NULL OR prepared.created_at > ?
                        OR (prepared.created_at = ? AND prepared.prepared_id > ?)
                      )
                    ORDER BY prepared.created_at, prepared.prepared_id LIMIT 256
                    """,
                    (
                        PreparedDecisionState.INVOKING.value,
                        PreparedDecisionState.SETTLING.value,
                        PreparedDecisionState.INDETERMINATE.value,
                        PreparedDecisionState.SETTLED.value,
                        last_created_at,
                        last_created_at,
                        last_created_at,
                        last_prepared_id,
                    ),
                ).fetchall()
                if not rows:
                    break
                for row in rows:
                    receipt_rows = self._connection.execute(
                        """
                        SELECT payload_json FROM receipts
                        WHERE action_id = ? AND executor_id = ?
                        """,
                        (row["action_id"], row["selected_executor_id"]),
                    ).fetchall()
                    receipts: list[ExecutionReceipt] = []
                    for receipt_row in receipt_rows:
                        try:
                            receipt = ExecutionReceipt.model_validate_json(
                                receipt_row["payload_json"]
                            )
                        except (TypeError, ValueError):
                            continue
                        if (
                            receipt.metadata.get("prepared_id") == row["prepared_id"]
                            and isinstance(receipt.metadata.get("attempt_id"), str)
                            and receipt.metadata.get("attempt_id")
                            and isinstance(receipt.metadata.get("charge_id"), str)
                            and receipt.metadata.get("charge_id")
                            and receipt.metadata.get("settlement_id") is None
                        ):
                            receipts.append(receipt)
                    final_receipt = receipts[0] if len(receipts) == 1 else None
                    complete = (
                        final_receipt is not None
                        and row["state"] == PreparedDecisionState.SETTLED.value
                        and row["request_hash"] == row["action_digest"]
                        and row["action_state"] == "complete"
                        and row["action_decision_id"] == final_receipt.decision_id
                        and row["action_status"] == final_receipt.status.value
                        and row["receipt_ids_json"]
                        == json.dumps([final_receipt.receipt_id])
                    )
                    if not complete:
                        results.append(
                            PreparedActionFinalizationRecord(
                                prepared_id=row["prepared_id"],
                                action_digest=row["action_digest"],
                                receipt_id=(
                                    final_receipt.receipt_id if final_receipt else None
                                ),
                                decision_id=(
                                    final_receipt.decision_id if final_receipt else None
                                ),
                                status=(
                                    final_receipt.status.value if final_receipt else None
                                ),
                            )
                        )
                        if len(results) == bounded_limit:
                            return results
                last_created_at = rows[-1]["created_at"]
                last_prepared_id = rows[-1]["prepared_id"]
        return results

    settled_free_actions_needing_finalization = free_actions_needing_finalization

    def settle_recovered_free_prepared(
        self,
        prepared_id: str,
        *,
        receipt_id: str,
        recovered_at: datetime,
    ) -> PreparedRouteDecision:
        """Finalize a receipt-proven confirmed-free action without reinvocation."""

        self._utc_text(recovered_at)
        with self._immediate_transaction() as connection:
            row = connection.execute(
                """
                SELECT state, action_id, selected_executor_id, payload_json
                FROM prepared_route_decisions WHERE prepared_id = ?
                """,
                (prepared_id,),
            ).fetchone()
            if row is None:
                raise ConfigurationError("recovered free prepared decision is missing")
            decision = self._prepared_from_row(row)
            maximum = decision.maximum_cash_authorization
            if (
                maximum is None
                or decision.authorization_kind is not None
                or decision.authorization_id is not None
                or maximum.amount != 0
                or decision.expected_accounting.cash.actual_cash_cost(maximum.currency)
                != Decimal(0)
            ):
                raise ConfigurationError(
                    "recovered prepared action is not confirmed free"
                )
            if connection.execute(
                "SELECT 1 FROM payment_reservations_v2 WHERE prepared_id = ? LIMIT 1",
                (prepared_id,),
            ).fetchone() is not None:
                raise ConfigurationError(
                    "recovered free prepared action cannot have a payment reservation"
                )
            receipt_row = connection.execute(
                "SELECT payload_json FROM receipts WHERE receipt_id = ?",
                (receipt_id,),
            ).fetchone()
            if receipt_row is None:
                raise ConfigurationError("recovered free action receipt is missing")
            receipt = ExecutionReceipt.model_validate_json(receipt_row["payload_json"])
            if (
                receipt.action_id != row["action_id"]
                or receipt.executor_id != row["selected_executor_id"]
                or receipt.metadata.get("prepared_id") != prepared_id
                or not isinstance(receipt.metadata.get("attempt_id"), str)
                or not receipt.metadata.get("attempt_id")
                or not isinstance(receipt.metadata.get("charge_id"), str)
                or not receipt.metadata.get("charge_id")
                or receipt.metadata.get("settlement_id") is not None
            ):
                raise ConfigurationError(
                    "recovered free action receipt binding does not match"
                )
            state = PreparedDecisionState(row["state"])
            if state is PreparedDecisionState.SETTLED:
                return decision
            if state not in {
                PreparedDecisionState.INVOKING,
                PreparedDecisionState.SETTLING,
                PreparedDecisionState.INDETERMINATE,
            }:
                raise ConfigurationError(
                    f"free prepared action cannot recover from state {state.value}"
                )
            if state is not PreparedDecisionState.SETTLING:
                self._transition_prepared_locked(
                    connection,
                    PreparedRouteTransition(
                        prepared_id=prepared_id,
                        from_state=state,
                        to_state=PreparedDecisionState.SETTLING,
                        occurred_at=recovered_at,
                        reason="durable confirmed-free receipt recovered",
                    ),
                )
            self._transition_prepared_locked(
                connection,
                PreparedRouteTransition(
                    prepared_id=prepared_id,
                    from_state=PreparedDecisionState.SETTLING,
                    to_state=PreparedDecisionState.SETTLED,
                    occurred_at=recovered_at,
                    reason="confirmed-free recovery finalized accounting",
                ),
            )
            settled_row = connection.execute(
                """
                SELECT state, payload_json FROM prepared_route_decisions
                WHERE prepared_id = ?
                """,
                (prepared_id,),
            ).fetchone()
        return self._prepared_from_row(settled_row)

    def settled_prepared_decisions_needing_finalization(
        self, *, limit: int = 1_000
    ) -> list[PreparedRouteDecision]:
        """Find settled rail operations whose local audit finalization is incomplete.

        These rows are safe recovery inputs because payment settlement already exists;
        callers must only recreate local links/receipts or complete idempotency state and
        must never invoke the provider or payment rail again.
        """

        bounded_limit = max(1, min(limit, 10_000))
        incomplete: list[PreparedRouteDecision] = []
        last_created_at: str | None = None
        last_prepared_id = ""

        def final_receipt_for_settlement(
            receipt_rows: Iterable[sqlite3.Row],
            *,
            prepared_id: str,
            settlement_id: str,
            attempt_id: str,
            charge_id: str,
        ) -> ExecutionReceipt | None:
            for receipt_row in receipt_rows:
                try:
                    receipt = ExecutionReceipt.model_validate_json(
                        receipt_row["payload_json"]
                    )
                except (TypeError, ValueError):
                    continue
                if (
                    receipt.metadata.get("prepared_id") == prepared_id
                    and receipt.metadata.get("settlement_id") == settlement_id
                    and receipt.metadata.get("attempt_id") == attempt_id
                    and receipt.metadata.get("charge_id") == charge_id
                ):
                    return receipt
            return None

        with self._lock:
            while len(incomplete) < bounded_limit:
                rows = self._connection.execute(
                    """
                    SELECT prepared.prepared_id, prepared.created_at,
                           prepared.state, prepared.payload_json,
                           reservation.attempt_id, reservation.charge_id,
                           settlement.settlement_id
                    FROM prepared_route_decisions AS prepared
                    JOIN payment_reservations_v2 AS reservation
                      ON reservation.prepared_id = prepared.prepared_id
                    JOIN settlement_receipts AS settlement
                      ON settlement.reservation_id = reservation.reservation_id
                    WHERE prepared.state = ?
                      AND (
                        ? IS NULL OR prepared.created_at > ?
                        OR (prepared.created_at = ? AND prepared.prepared_id > ?)
                      )
                    ORDER BY prepared.created_at, prepared.prepared_id LIMIT 256
                    """,
                    (
                        PreparedDecisionState.SETTLED.value,
                        last_created_at,
                        last_created_at,
                        last_created_at,
                        last_prepared_id,
                    ),
                ).fetchall()
                if not rows:
                    break
                for row in rows:
                    prepared = self._prepared_from_row(row)
                    authoritative_link = self._connection.execute(
                        """
                        SELECT 1 FROM economic_evidence_links
                        WHERE charge_id = ? AND evidence_type = 'settlement_receipt'
                          AND evidence_id = ? AND authoritative = 1 LIMIT 1
                        """,
                        (row["charge_id"], row["settlement_id"]),
                    ).fetchone()
                    receipt_rows = self._connection.execute(
                        """
                        SELECT payload_json FROM receipts
                        WHERE action_id = ? AND executor_id = ?
                        """,
                        (prepared.action_id, prepared.selected_executor_id),
                    ).fetchall()
                    final_receipt = final_receipt_for_settlement(
                        receipt_rows,
                        prepared_id=prepared.prepared_id,
                        settlement_id=row["settlement_id"],
                        attempt_id=row["attempt_id"],
                        charge_id=row["charge_id"],
                    )
                    operation = self._connection.execute(
                        """
                        SELECT 1 FROM idempotency_records
                        WHERE idempotency_key LIKE 'payment:settle:%'
                          AND state = 'complete' AND decision_id = 'settle'
                          AND status = ? AND receipt_ids_json = ? LIMIT 1
                        """,
                        (
                            SettlementReceipt.__name__,
                            json.dumps([row["settlement_id"]]),
                        ),
                    ).fetchone()
                    action_binding = self._connection.execute(
                        """
                        SELECT binding.action_digest, action.request_hash,
                               action.state, action.decision_id, action.status,
                               action.receipt_ids_json
                        FROM prepared_action_idempotency AS binding
                        LEFT JOIN idempotency_records AS action
                          ON action.idempotency_key = binding.idempotency_key
                        WHERE binding.prepared_id = ?
                        """,
                        (prepared.prepared_id,),
                    ).fetchone()
                    action_complete = action_binding is None
                    if action_binding is not None and final_receipt is not None:
                        action_complete = (
                            action_binding["action_digest"] == prepared.action_digest
                            and action_binding["request_hash"] == prepared.action_digest
                            and action_binding["state"] == "complete"
                            and action_binding["decision_id"]
                            == final_receipt.decision_id
                            and action_binding["status"] == final_receipt.status.value
                            and action_binding["receipt_ids_json"]
                            == json.dumps([final_receipt.receipt_id])
                        )
                    if (
                        authoritative_link is None
                        or final_receipt is None
                        or operation is None
                        or not action_complete
                    ):
                        incomplete.append(prepared)
                        if len(incomplete) == bounded_limit:
                            return incomplete
                last_created_at = rows[-1]["created_at"]
                last_prepared_id = rows[-1]["prepared_id"]
        return incomplete

    def released_payment_operations_needing_finalization(
        self, *, limit: int = 1_000
    ) -> list[PaymentOperationFinalizationRecord]:
        """Find durable releases whose local payment-operation result is unfinished."""

        bounded_limit = max(1, min(limit, 10_000))
        results: list[PaymentOperationFinalizationRecord] = []
        last_created_at: str | None = None
        last_prepared_id = ""
        prefix = "payment:release:"
        with self._lock:
            operations = self._connection.execute(
                """
                SELECT idempotency_key, request_hash FROM idempotency_records
                WHERE idempotency_key LIKE 'payment:release:%'
                  AND state IN ('claimed', 'executing', 'indeterminate')
                """
            ).fetchall()
            operations_by_result_id = {
                self._payment_operation_result_id(
                    "release", str(operation["idempotency_key"]).removeprefix(prefix)
                ): operation
                for operation in operations
            }
            while len(results) < bounded_limit:
                rows = self._connection.execute(
                    """
                    SELECT prepared.prepared_id, prepared.created_at,
                           reservation.reservation_id, settlement.settlement_id
                    FROM prepared_route_decisions AS prepared
                    JOIN payment_reservations_v2 AS reservation
                      ON reservation.prepared_id = prepared.prepared_id
                    JOIN settlement_receipts AS settlement
                      ON settlement.reservation_id = reservation.reservation_id
                    WHERE prepared.state = ? AND reservation.state = ?
                      AND settlement.status = ?
                      AND (
                        ? IS NULL OR prepared.created_at > ?
                        OR (prepared.created_at = ? AND prepared.prepared_id > ?)
                      )
                    ORDER BY prepared.created_at, prepared.prepared_id LIMIT 256
                    """,
                    (
                        PreparedDecisionState.RELEASED.value,
                        PaymentReservationState.RELEASED.value,
                        SettlementStatus.RELEASED.value,
                        last_created_at,
                        last_created_at,
                        last_created_at,
                        last_prepared_id,
                    ),
                ).fetchall()
                if not rows:
                    break
                for row in rows:
                    operation = operations_by_result_id.get(row["settlement_id"])
                    if operation is not None:
                        idempotency_key = str(
                            operation["idempotency_key"]
                        ).removeprefix(prefix)
                        results.append(
                            PaymentOperationFinalizationRecord(
                                prepared_id=row["prepared_id"],
                                reservation_id=row["reservation_id"],
                                settlement_id=row["settlement_id"],
                                operation="release",
                                idempotency_key=idempotency_key,
                                request_digest=operation["request_hash"],
                            )
                        )
                    if len(results) == bounded_limit:
                        return results
                last_created_at = rows[-1]["created_at"]
                last_prepared_id = rows[-1]["prepared_id"]
        return results

    def released_prepared_actions_needing_abandonment(
        self, *, limit: int = 1_000
    ) -> list[PreparedRouteDecision]:
        """Find claimed actions proven fully released before invocation."""

        bounded_limit = max(1, min(limit, 10_000))
        results: list[PreparedRouteDecision] = []
        last_created_at: str | None = None
        last_prepared_id = ""
        with self._lock:
            while len(results) < bounded_limit:
                rows = self._connection.execute(
                    """
                    SELECT prepared.created_at, prepared.prepared_id,
                           prepared.state, prepared.payload_json,
                           settlement.captured_amount
                    FROM prepared_route_decisions AS prepared
                    JOIN prepared_action_idempotency AS binding
                      ON binding.prepared_id = prepared.prepared_id
                    JOIN idempotency_records AS action
                      ON action.idempotency_key = binding.idempotency_key
                    JOIN payment_reservations_v2 AS reservation
                      ON reservation.prepared_id = prepared.prepared_id
                    JOIN settlement_receipts AS settlement
                      ON settlement.reservation_id = reservation.reservation_id
                    WHERE prepared.state = ? AND action.state = 'claimed'
                      AND reservation.state = ? AND settlement.status = ?
                      AND (
                        ? IS NULL OR prepared.created_at > ?
                        OR (prepared.created_at = ? AND prepared.prepared_id > ?)
                      )
                    ORDER BY prepared.created_at, prepared.prepared_id LIMIT 256
                    """,
                    (
                        PreparedDecisionState.RELEASED.value,
                        PaymentReservationState.RELEASED.value,
                        SettlementStatus.RELEASED.value,
                        last_created_at,
                        last_created_at,
                        last_created_at,
                        last_prepared_id,
                    ),
                ).fetchall()
                if not rows:
                    break
                for row in rows:
                    if Decimal(row["captured_amount"]) == 0:
                        results.append(self._prepared_from_row(row))
                        if len(results) == bounded_limit:
                            return results
                last_created_at = rows[-1]["created_at"]
                last_prepared_id = rows[-1]["prepared_id"]
        return results

    @staticmethod
    def _payment_indexed(reservation: PaymentReservationV2) -> dict[str, object]:
        if reservation.authorization_kind is None or reservation.authorization_id is None:
            raise ConfigurationError("payment reservation authorization basis is missing")
        return {
            "charge_id": reservation.charge_id,
            "prepared_id": reservation.prepared_id,
            "quote_id": reservation.quote_id,
            "authorization_kind": reservation.authorization_kind.value,
            "authorization_id": reservation.authorization_id,
            "action_id": reservation.action_id,
            "attempt_id": reservation.attempt_id,
            "maximum_amount": ReceiptStore._amount_text(reservation.maximum_amount.amount),
            "currency": reservation.maximum_amount.currency,
            "adapter": reservation.adapter,
            "state": reservation.state.value,
            "operation_intent": None,
            "idempotency_key": reservation.idempotency_key,
            "created_at": ReceiptStore._utc_text(reservation.created_at),
            "updated_at": ReceiptStore._utc_text(reservation.updated_at),
            "indeterminate_reason": reservation.indeterminate_reason,
        }

    @staticmethod
    def _require_active_signing_key_locked(
        connection: sqlite3.Connection,
        *,
        provider_id: str,
        key_id: str,
        algorithm: str,
        at: datetime,
        capability: str,
    ) -> TrustedProviderKey:
        row = connection.execute(
            """
            SELECT algorithm, status, valid_from, valid_until, revoked_at, payload_json
            FROM provider_signing_keys WHERE provider_id = ? AND key_id = ?
            """,
            (provider_id, key_id),
        ).fetchone()
        if row is None:
            raise ConfigurationError("economic authorization signing key is not trusted")
        if row["algorithm"] != algorithm:
            raise ConfigurationError("economic authorization signing algorithm changed")
        if row["status"] != TrustedKeyStatus.ACTIVE.value or row["revoked_at"] is not None:
            raise ConfigurationError("economic authorization signing key is not active")
        at_text = ReceiptStore._utc_text(at)
        if row["valid_from"] > at_text or row["valid_until"] <= at_text:
            raise ConfigurationError("economic authorization signing key is not currently valid")
        key = TrustedProviderKey.model_validate_json(row["payload_json"])
        if key.allowed_capabilities and capability not in key.allowed_capabilities:
            raise ConfigurationError("economic authorization capability is not trusted for key")
        return key

    @staticmethod
    def _require_valid_authorization_signature(
        record: CapabilityOffer | BoundedQuote,
        *,
        key: TrustedProviderKey,
        at: datetime,
    ) -> None:
        verifier = TrustStoreVerifier(TrustStore((key,)), clock=lambda: at)
        result = verifier.verify(
            canonical_payload(record),
            record.signature,
            record.provider_id,
            capability=record.capability,
        )
        if not result.valid:
            raise ConfigurationError(
                f"economic authorization signature verification failed: {result.reason}"
            )

    @staticmethod
    def _offer_authorized_maximum(
        offer: CapabilityOffer, decision: PreparedRouteDecision
    ) -> CurrencyAmount:
        total = Decimal(0)
        for rule in offer.pricing_rules:
            if rule.per_unit_amount is None:
                amount = rule.evaluate()
            else:
                disclosed = decision.disclosed_quote_features.get(rule.meter or "")
                if isinstance(disclosed, bool) or not isinstance(disclosed, int):
                    if rule.maximum_amount is None:
                        raise ConfigurationError(
                            f"offer rule {rule.rule_id!r} has no bounded disclosed quantity"
                        )
                    amount = rule.maximum_amount
                else:
                    amount = rule.evaluate(disclosed)
            if amount.currency != offer.settlement_currency:
                raise ConfigurationError("offer pricing-rule currency is inconsistent")
            total += amount.amount
        if offer.fixed_attempt_fee is not None:
            if offer.fixed_attempt_fee.currency != offer.settlement_currency:
                raise ConfigurationError("offer attempt-fee currency is inconsistent")
            total = max(total, offer.fixed_attempt_fee.amount)
        return CurrencyAmount(amount=total, currency=offer.settlement_currency)

    @staticmethod
    def _rate_card_authorized_maximum(
        snapshot: RateCardSnapshot, decision: PreparedRouteDecision
    ) -> CurrencyAmount:
        if snapshot.currency is None:
            raise ConfigurationError("subscription-only rate card cannot authorize cash")
        rates = {rate.rate_id: rate for rate in snapshot.rates}
        total = Decimal(0)
        for quantity in decision.authorization_meter_quantities:
            rate = rates.get(quantity.rate_id)
            if rate is None:
                raise ConfigurationError("prepared authorization names an unknown rate")
            if rate.rate_type is RateType.SUBSCRIPTION_UNIT:
                raise ConfigurationError("subscription units cannot authorize cash")
            if any(
                value is not None
                for value in (
                    rate.service_tier,
                    rate.region,
                    rate.tool_name,
                    rate.long_context_min,
                    rate.long_context_max,
                    rate.rule,
                )
            ):
                raise ConfigurationError(
                    "conditional pinned rates cannot authorize cash in protocol 0.4"
                )
            if rate.meter != quantity.meter or rate.input_unit != quantity.unit:
                raise ConfigurationError("authorization quantity does not match pinned rate")
            total += (
                quantity.quantity
                / rate.unit_quantity
                * rate.rate_amount
                * (rate.multiplier or Decimal(1))
            )
        return CurrencyAmount(amount=total, currency=snapshot.currency)

    def save_payment_reservation_v2(
        self, reservation: PaymentReservationV2
    ) -> PaymentReservationV2:
        if self.get_payment_reservation_v2(reservation.reservation_id) is None:
            raise ConfigurationError(
                "new payment holds require atomic reserve_payment_v2"
            )
        self._save_immutable(
            table="payment_reservations_v2",
            identity={"reservation_id": reservation.reservation_id},
            indexed=self._payment_indexed(reservation),
            value=reservation,
        )
        stored = self.get_payment_reservation_v2(reservation.reservation_id)
        if stored is None:  # pragma: no cover - same-transaction insert invariant
            raise ConfigurationError("payment reservation disappeared after storage")
        return stored

    @staticmethod
    def _payment_from_row(row: sqlite3.Row) -> PaymentReservationV2:
        reservation = PaymentReservationV2.model_validate_json(row["payload_json"])
        return reservation.model_copy(
            update={
                "state": PaymentReservationState(row["state"]),
                "updated_at": datetime.fromisoformat(row["updated_at"]),
                "indeterminate_reason": row["indeterminate_reason"],
            }
        )

    def get_payment_reservation_v2(self, reservation_id: str) -> PaymentReservationV2 | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT state, updated_at, indeterminate_reason, payload_json
                FROM payment_reservations_v2 WHERE reservation_id = ?
                """,
                (reservation_id,),
            ).fetchone()
        return self._payment_from_row(row) if row else None

    def list_payment_reservations_v2(
        self,
        *,
        states: Iterable[PaymentReservationState] | None = None,
        action_id: str | None = None,
        prepared_id: str | None = None,
        limit: int = 1_000,
    ) -> list[PaymentReservationV2]:
        clauses: list[str] = []
        parameters: list[object] = []
        state_values = tuple(state.value for state in states) if states is not None else ()
        if state_values:
            clauses.append(f"state IN ({', '.join('?' for _ in state_values)})")
            parameters.extend(state_values)
        if action_id is not None:
            clauses.append("action_id = ?")
            parameters.append(action_id)
        if prepared_id is not None:
            clauses.append("prepared_id = ?")
            parameters.append(prepared_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self._connection.execute(
                f"""
                SELECT state, updated_at, indeterminate_reason, payload_json
                FROM payment_reservations_v2 {where}
                ORDER BY created_at DESC, reservation_id LIMIT ?
                """,
                (*parameters, max(1, min(limit, 10_000))),
            ).fetchall()
        return [self._payment_from_row(row) for row in rows]

    def reserve_payment_v2(
        self,
        reservation: PaymentReservationV2,
        *,
        claim_token: str,
        budget_limit: CurrencyAmount | None,
        prepaid_limit: CurrencyAmount | None = None,
        unlimited_budget: bool = False,
        period_start: datetime | None = None,
    ) -> PaymentReservationV2:
        """Atomically check committed Decimal cash and insert one reservation."""

        if reservation.state is not PaymentReservationState.RESERVED:
            raise ConfigurationError("a new payment reservation must be RESERVED")
        if not claim_token or len(claim_token) > 256:
            raise ConfigurationError("payment reservation requires a bounded prepared claim token")
        if unlimited_budget == (budget_limit is not None):
            raise ConfigurationError("choose exactly one finite or unlimited budget policy")
        if (
            budget_limit is not None
            and reservation.maximum_amount.currency != budget_limit.currency
        ):
            raise ConfigurationError("payment reservation currency does not match budget currency")
        if (
            prepaid_limit is not None
            and reservation.maximum_amount.currency != prepaid_limit.currency
        ):
            raise ConfigurationError("payment reservation currency does not match prepaid currency")
        period_text = self._utc_text(period_start) if period_start is not None else None
        with self._immediate_transaction() as connection:
            prepared_row = connection.execute(
                """
                SELECT state, claim_token, claimed_at, expires_at, payload_json
                FROM prepared_route_decisions WHERE prepared_id = ?
                """,
                (reservation.prepared_id,),
            ).fetchone()
            if prepared_row is None:
                raise ConfigurationError("payment reservation prepared decision is missing")
            decision = self._prepared_from_row(prepared_row)
            if prepared_row["claim_token"] != claim_token:
                raise ConfigurationError("payment reservation does not own the prepared claim")
            existing = connection.execute(
                """
                SELECT state, updated_at, indeterminate_reason, payload_json, payload_digest
                FROM payment_reservations_v2
                WHERE reservation_id = ? OR idempotency_key = ?
                """,
                (reservation.reservation_id, reservation.idempotency_key),
            ).fetchone()
            if existing is not None:
                if (
                    existing["payload_digest"] != canonical_digest(reservation)
                    or existing["payload_json"] != reservation.model_dump_json()
                ):
                    raise ConfigurationError(
                        "payment reservation ID or idempotency key conflicts with existing content"
                    )
                stored_reservation = self._payment_from_row(existing)
                if stored_reservation.state in {
                    PaymentReservationState.SETTLED,
                    PaymentReservationState.RELEASED,
                } and decision.state in {
                    PreparedDecisionState.SETTLED,
                    PreparedDecisionState.RELEASED,
                }:
                    return stored_reservation
                if decision.state is PreparedDecisionState.PREPARED:
                    raise ConfigurationError("reservation exists without its prepared transition")
            elif decision.state is not PreparedDecisionState.PREPARED:
                raise ConfigurationError("payment reservation requires a PREPARED decision")
            reservation_time = self._utc_text(reservation.updated_at)
            if (
                prepared_row["claimed_at"] is None
                or prepared_row["claimed_at"] > reservation_time
            ):
                raise ConfigurationError("payment reservation predates its prepared claim")
            if prepared_row["expires_at"] <= reservation_time:
                raise ConfigurationError("payment reservation prepared decision has expired")
            if decision.action_id != reservation.action_id:
                raise ConfigurationError("payment reservation is not bound to the prepared action")
            if (
                reservation.authorization_kind is None
                or reservation.authorization_id is None
                or reservation.authorization_kind is not decision.authorization_kind
                or reservation.authorization_id != decision.authorization_id
            ):
                raise ConfigurationError(
                    "payment reservation authorization does not match prepared decision"
                )
            prepared_maximum = decision.maximum_cash_authorization
            if prepared_maximum is None or prepared_maximum != reservation.maximum_amount:
                raise ConfigurationError(
                    "payment reservation must equal the prepared maximum authorization"
                )

            authorized_maximum: CurrencyAmount
            if reservation.authorization_kind is AuthorizationKind.SIGNED_QUOTE:
                quote_row = connection.execute(
                    "SELECT payload_json FROM bounded_quotes WHERE quote_id = ?",
                    (reservation.authorization_id,),
                ).fetchone()
                if quote_row is None:
                    raise ConfigurationError("signed quote authorization is missing")
                quote = BoundedQuote.model_validate_json(quote_row["payload_json"])
                if (
                    reservation.quote_id != quote.quote_id
                    or decision.selected_quote_id != quote.quote_id
                    or quote.action_digest != decision.action_digest
                    or quote.executor_id != decision.selected_executor_id
                    or quote.executor_fingerprint != decision.selected_executor_fingerprint
                ):
                    raise ConfigurationError("signed quote authorization binding changed")
                if quote.issued_at > reservation.updated_at or quote.expires_at <= reservation.updated_at:
                    raise ConfigurationError("signed quote authorization is not currently valid")
                key = self._require_active_signing_key_locked(
                    connection,
                    provider_id=quote.provider_id,
                    key_id=quote.signature.key_id,
                    algorithm=quote.signature.algorithm.value,
                    at=reservation.updated_at,
                    capability=quote.capability,
                )
                self._require_valid_authorization_signature(
                    quote, key=key, at=reservation.updated_at
                )
                authorized_maximum = quote.maximum_amount
            elif reservation.authorization_kind is AuthorizationKind.PUBLISHED_OFFER:
                offer_row = connection.execute(
                    """
                    SELECT status, revoked_at, payload_json FROM capability_offers
                    WHERE offer_id = ?
                    """,
                    (reservation.authorization_id,),
                ).fetchone()
                if offer_row is None:
                    raise ConfigurationError("published offer authorization is missing")
                offer = CapabilityOffer.model_validate_json(offer_row["payload_json"])
                if (
                    decision.selected_offer_id != offer.offer_id
                    or offer.executor_id != decision.selected_executor_id
                    or offer.executor_fingerprint != decision.selected_executor_fingerprint
                ):
                    raise ConfigurationError("published offer authorization binding changed")
                if (
                    offer_row["status"] != "active"
                    or offer_row["revoked_at"] is not None
                    or offer.valid_from > reservation.updated_at
                    or offer.valid_until <= reservation.updated_at
                ):
                    raise ConfigurationError("published offer authorization is not active")
                key = self._require_active_signing_key_locked(
                    connection,
                    provider_id=offer.provider_id,
                    key_id=offer.signature.key_id,
                    algorithm=offer.signature.algorithm.value,
                    at=reservation.updated_at,
                    capability=offer.capability,
                )
                self._require_valid_authorization_signature(
                    offer, key=key, at=reservation.updated_at
                )
                authorized_maximum = self._offer_authorized_maximum(offer, decision)
            elif reservation.authorization_kind is AuthorizationKind.PINNED_RATE_CARD:
                rate_row = connection.execute(
                    "SELECT payload_json FROM rate_card_snapshots WHERE snapshot_id = ?",
                    (reservation.authorization_id,),
                ).fetchone()
                if rate_row is None:
                    raise ConfigurationError("pinned rate-card authorization is missing")
                snapshot = RateCardSnapshot.model_validate_json(rate_row["payload_json"])
                if decision.selected_rate_card_id != snapshot.snapshot_id:
                    raise ConfigurationError("pinned rate-card authorization binding changed")
                if (
                    snapshot.effective_from.tzinfo is None
                    or snapshot.effective_from.utcoffset() is None
                    or (
                        snapshot.effective_until is not None
                        and (
                            snapshot.effective_until.tzinfo is None
                            or snapshot.effective_until.utcoffset() is None
                        )
                    )
                    or snapshot.effective_from > reservation.updated_at
                    or (
                        snapshot.effective_until is not None
                        and snapshot.effective_until <= reservation.updated_at
                    )
                ):
                    raise ConfigurationError("pinned rate-card authorization is not active")
                authorized_maximum = self._rate_card_authorized_maximum(snapshot, decision)
            else:  # pragma: no cover - model enum and validator are exhaustive
                raise ConfigurationError("unsupported payment authorization basis")
            if authorized_maximum != reservation.maximum_amount:
                raise ConfigurationError(
                    "payment reservation does not equal its immutable authorization maximum"
                )
            if existing is not None:
                return self._payment_from_row(existing)

            def committed_amount(*, since: str | None) -> Decimal:
                currency = reservation.maximum_amount.currency
                outstanding = sum(
                    (
                        Decimal(row["maximum_amount"])
                        for row in connection.execute(
                            """
                            SELECT maximum_amount FROM payment_reservations_v2
                            WHERE currency = ? AND state NOT IN (?, ?)
                            """,
                            (
                                currency,
                                PaymentReservationState.SETTLED.value,
                                PaymentReservationState.RELEASED.value,
                            ),
                        )
                    ),
                    Decimal(0),
                )
                missing_settlement = connection.execute(
                    """
                    SELECT 1 FROM payment_reservations_v2 AS reservation
                    LEFT JOIN settlement_receipts AS settlement
                      ON settlement.reservation_id = reservation.reservation_id
                    WHERE reservation.currency = ? AND reservation.state = ?
                      AND settlement.settlement_id IS NULL LIMIT 1
                    """,
                    (currency, PaymentReservationState.SETTLED.value),
                ).fetchone()
                if missing_settlement is not None:
                    raise ConfigurationError(
                        "settled reservation is missing immutable settlement evidence"
                    )
                capture_query = """
                    SELECT settlement.captured_amount
                    FROM settlement_receipts AS settlement
                    JOIN payment_reservations_v2 AS reservation
                      ON reservation.reservation_id = settlement.reservation_id
                    WHERE settlement.currency = ? AND reservation.state = ?
                """
                capture_parameters: list[object] = [
                    currency,
                    PaymentReservationState.SETTLED.value,
                ]
                refund_query = """
                    SELECT refund.amount
                    FROM refund_receipts_v2 AS refund
                    JOIN settlement_receipts AS settlement
                      ON settlement.settlement_id = refund.settlement_id
                    JOIN payment_reservations_v2 AS reservation
                      ON reservation.reservation_id = settlement.reservation_id
                    WHERE refund.currency = ? AND reservation.state = ?
                """
                refund_parameters: list[object] = [
                    currency,
                    PaymentReservationState.SETTLED.value,
                ]
                if since is not None:
                    capture_query += " AND settlement.settled_at >= ?"
                    capture_parameters.append(since)
                    refund_query += " AND refund.refunded_at >= ?"
                    refund_parameters.append(since)
                captured = sum(
                    (
                        Decimal(row["captured_amount"])
                        for row in connection.execute(
                            capture_query, capture_parameters
                        )
                    ),
                    Decimal(0),
                )
                refunded = sum(
                    (
                        Decimal(row["amount"])
                        for row in connection.execute(
                            refund_query, refund_parameters
                        )
                    ),
                    Decimal(0),
                )
                return outstanding + max(Decimal(0), captured - refunded)

            if budget_limit is not None and (
                committed_amount(since=period_text) + reservation.maximum_amount.amount
                > budget_limit.amount
            ):
                raise ConfigurationError("payment reservation exceeds available daily budget")
            if prepaid_limit is not None and (
                committed_amount(since=None) + reservation.maximum_amount.amount
                > prepaid_limit.amount
            ):
                raise ConfigurationError("payment reservation exceeds available prepaid balance")

            self._immutable_insert_locked(
                connection,
                table="payment_reservations_v2",
                identity={"reservation_id": reservation.reservation_id},
                indexed=self._payment_indexed(reservation),
                value=reservation,
            )
            self._transition_prepared_locked(
                connection,
                PreparedRouteTransition(
                    prepared_id=reservation.prepared_id,
                    from_state=PreparedDecisionState.PREPARED,
                    to_state=PreparedDecisionState.RESERVED,
                    occurred_at=reservation.updated_at,
                    reason=f"payment reservation {reservation.reservation_id}",
                ),
                required_claim_token=claim_token,
            )
        return reservation

    def transition_payment_reservation_v2(
        self,
        reservation_id: str,
        *,
        expected_state: PaymentReservationState,
        updated: PaymentReservationV2,
    ) -> PaymentReservationV2:
        allowed: dict[PaymentReservationState, frozenset[PaymentReservationState]] = {
            PaymentReservationState.RESERVED: frozenset(
                {
                    PaymentReservationState.INDETERMINATE,
                    PaymentReservationState.DISPUTED,
                }
            ),
            PaymentReservationState.SETTLING: frozenset(
                {
                    PaymentReservationState.INDETERMINATE,
                    PaymentReservationState.DISPUTED,
                }
            ),
            PaymentReservationState.INDETERMINATE: frozenset(
                {
                    PaymentReservationState.RESERVED,
                    PaymentReservationState.DISPUTED,
                }
            ),
            PaymentReservationState.DISPUTED: frozenset(),
            PaymentReservationState.SETTLED: frozenset(),
            PaymentReservationState.RELEASED: frozenset(),
        }
        if updated.reservation_id != reservation_id:
            raise ConfigurationError("updated reservation identity does not match")
        if updated.state in {
            PaymentReservationState.SETTLING,
            PaymentReservationState.SETTLED,
            PaymentReservationState.RELEASED,
        }:
            raise ConfigurationError(
                "payment operation state requires an operation-specific atomic method"
            )
        if updated.state not in allowed[expected_state]:
            raise ConfigurationError(
                f"illegal payment reservation transition: {expected_state} -> {updated.state}"
            )
        with self._immediate_transaction() as connection:
            row = connection.execute(
                """
                SELECT state, updated_at, indeterminate_reason, payload_json
                FROM payment_reservations_v2 WHERE reservation_id = ?
                """,
                (reservation_id,),
            ).fetchone()
            if row is None:
                raise ConfigurationError("payment reservation does not exist")
            current = self._payment_from_row(row)
            stable_fields = {"state", "updated_at", "indeterminate_reason"}
            if current.model_dump(exclude=stable_fields) != updated.model_dump(
                exclude=stable_fields
            ):
                raise ConfigurationError("payment reservation immutable fields cannot change")
            if updated.updated_at < current.updated_at:
                raise ConfigurationError("payment reservation update cannot move backward in time")
            if current.state is not expected_state:
                if (
                    current.state is updated.state
                    and current.updated_at == updated.updated_at
                    and current.indeterminate_reason == updated.indeterminate_reason
                ):
                    return current
                raise ConfigurationError("payment reservation transition lost its state race")
            cursor = connection.execute(
                """
                UPDATE payment_reservations_v2
                SET state = ?, updated_at = ?, indeterminate_reason = ?
                WHERE reservation_id = ? AND state = ?
                """,
                (
                    updated.state.value,
                    self._utc_text(updated.updated_at),
                    updated.indeterminate_reason,
                    reservation_id,
                    expected_state.value,
                ),
            )
            if cursor.rowcount != 1:
                raise ConfigurationError("payment reservation transition lost its state race")
        return updated

    def _claim_payment_intent_v2(
        self,
        reservation_id: str,
        *,
        intent_type: str,
        idempotency_key: str,
        required_prepared_state: PreparedDecisionState,
        updated_at: datetime,
    ) -> PaymentReservationV2:
        if intent_type not in {"release", "settle"}:
            raise ConfigurationError("unknown payment operation intent")
        if not idempotency_key or len(idempotency_key) > 256:
            raise ConfigurationError("payment operation intent requires a bounded idempotency key")
        intent = f"{intent_type}:{idempotency_key}"
        updated_text = self._utc_text(updated_at)
        with self._immediate_transaction() as connection:
            row = connection.execute(
                """
                SELECT reservation.state, reservation.updated_at,
                       reservation.indeterminate_reason, reservation.operation_intent,
                       reservation.payload_json, reservation.prepared_id,
                       reservation.action_id, reservation.attempt_id,
                       reservation.charge_id, prepared.state AS prepared_state,
                       prepared.selected_executor_id,
                       prepared.payload_json AS prepared_payload_json
                FROM payment_reservations_v2 AS reservation
                JOIN prepared_route_decisions AS prepared
                    ON prepared.prepared_id = reservation.prepared_id
                WHERE reservation.reservation_id = ?
                """,
                (reservation_id,),
            ).fetchone()
            if row is None:
                raise ConfigurationError("payment reservation does not exist")
            current = self._payment_from_row(row)
            if (
                current.state is PaymentReservationState.SETTLING
                and row["operation_intent"] == intent
            ):
                return current
            if (
                current.state is PaymentReservationState.INDETERMINATE
                and row["operation_intent"] == intent
            ):
                if row["prepared_state"] != required_prepared_state.value:
                    raise ConfigurationError(
                        f"{intent_type} recovery requires prepared state "
                        f"{required_prepared_state.value}"
                    )
                if updated_at < current.updated_at:
                    raise ConfigurationError("payment intent cannot move backward in time")
                cursor = connection.execute(
                    """
                    UPDATE payment_reservations_v2
                    SET state = ?, updated_at = ?, indeterminate_reason = NULL
                    WHERE reservation_id = ? AND state = ? AND operation_intent = ?
                    """,
                    (
                        PaymentReservationState.SETTLING.value,
                        updated_text,
                        reservation_id,
                        PaymentReservationState.INDETERMINATE.value,
                        intent,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ConfigurationError(
                        "payment reservation recovery intent lost its state race"
                    )
                return current.model_copy(
                    update={
                        "state": PaymentReservationState.SETTLING,
                        "updated_at": updated_at,
                        "indeterminate_reason": None,
                    }
                )
            if (
                current.state is PaymentReservationState.INDETERMINATE
                and row["operation_intent"] is None
            ):
                if (
                    intent_type != "settle"
                    or required_prepared_state is not PreparedDecisionState.SETTLING
                    or row["prepared_state"] != PreparedDecisionState.SETTLING.value
                ):
                    raise ConfigurationError(
                        "an intent-free indeterminate hold may only resume settlement"
                    )
                receipt_rows = connection.execute(
                    """
                    SELECT payload_json FROM receipts
                    WHERE action_id = ? AND executor_id = ?
                    """,
                    (row["action_id"], row["selected_executor_id"]),
                ).fetchall()
                receipts = [
                    ExecutionReceipt.model_validate_json(receipt_row["payload_json"])
                    for receipt_row in receipt_rows
                ]
                authorization_kind = current.authorization_kind
                authorization_id = current.authorization_id
                if authorization_kind is None or authorization_id is None:
                    raise ConfigurationError(
                        "indeterminate settlement recovery authorization is missing"
                    )
                receipt_exists = any(
                    receipt.metadata.get("prepared_id") == row["prepared_id"]
                    and receipt.metadata.get("attempt_id") == row["attempt_id"]
                    and receipt.metadata.get("charge_id") == row["charge_id"]
                    and receipt.metadata.get("authorization_kind")
                    == authorization_kind.value
                    and receipt.metadata.get("authorization_id")
                    == authorization_id
                    for receipt in receipts
                )
                decision = PreparedRouteDecision.model_validate_json(
                    row["prepared_payload_json"]
                )
                basis_reproduced = False
                usage_exists: sqlite3.Row | None = None
                if authorization_kind is AuthorizationKind.SIGNED_QUOTE:
                    usage_exists = connection.execute(
                        """
                        SELECT 1 FROM usage_statements
                        WHERE prepared_id = ? AND attempt_id = ? LIMIT 1
                        """,
                        (row["prepared_id"], row["attempt_id"]),
                    ).fetchone()
                    basis_reproduced = usage_exists is not None
                elif authorization_kind is AuthorizationKind.PUBLISHED_OFFER:
                    offer_row = connection.execute(
                        "SELECT payload_json FROM capability_offers WHERE offer_id = ?",
                        (authorization_id,),
                    ).fetchone()
                    if offer_row is not None:
                        offer = CapabilityOffer.model_validate_json(offer_row["payload_json"])
                        basis_reproduced = (
                            decision.selected_offer_id == offer.offer_id
                            and decision.selected_executor_id == offer.executor_id
                            and decision.selected_executor_fingerprint
                            == offer.executor_fingerprint
                            and self._offer_authorized_maximum(offer, decision)
                            == current.maximum_amount
                        )
                elif authorization_kind is AuthorizationKind.PINNED_RATE_CARD:
                    rate_row = connection.execute(
                        "SELECT payload_json FROM rate_card_snapshots WHERE snapshot_id = ?",
                        (authorization_id,),
                    ).fetchone()
                    if rate_row is not None:
                        snapshot = RateCardSnapshot.model_validate_json(rate_row["payload_json"])
                        basis_reproduced = (
                            decision.selected_rate_card_id == snapshot.snapshot_id
                            and self._rate_card_authorized_maximum(snapshot, decision)
                            == current.maximum_amount
                        )
                if not basis_reproduced or not receipt_exists:
                    raise ConfigurationError(
                        "indeterminate settlement recovery lacks durable execution evidence"
                    )
                if updated_at < current.updated_at:
                    raise ConfigurationError("payment intent cannot move backward in time")
                cursor = connection.execute(
                    """
                    UPDATE payment_reservations_v2
                    SET state = ?, operation_intent = ?, updated_at = ?,
                        indeterminate_reason = NULL
                    WHERE reservation_id = ? AND state = ?
                      AND operation_intent IS NULL
                    """,
                    (
                        PaymentReservationState.SETTLING.value,
                        intent,
                        updated_text,
                        reservation_id,
                        PaymentReservationState.INDETERMINATE.value,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ConfigurationError(
                        "payment reservation recovery intent lost its state race"
                    )
                return current.model_copy(
                    update={
                        "state": PaymentReservationState.SETTLING,
                        "updated_at": updated_at,
                        "indeterminate_reason": None,
                    }
                )
            if current.state is not PaymentReservationState.RESERVED:
                raise ConfigurationError("payment reservation operation intent lost its state race")
            if row["operation_intent"] is not None:
                raise ConfigurationError("payment reservation already has an operation intent")
            if row["prepared_state"] != required_prepared_state.value:
                raise ConfigurationError(
                    f"{intent_type} intent requires prepared state "
                    f"{required_prepared_state.value}"
                )
            if updated_at < current.updated_at:
                raise ConfigurationError("payment intent cannot move backward in time")
            cursor = connection.execute(
                """
                UPDATE payment_reservations_v2
                SET state = ?, operation_intent = ?, updated_at = ?
                WHERE reservation_id = ? AND state = ? AND operation_intent IS NULL
                """,
                (
                    PaymentReservationState.SETTLING.value,
                    intent,
                    updated_text,
                    reservation_id,
                    PaymentReservationState.RESERVED.value,
                ),
            )
            if cursor.rowcount != 1:
                raise ConfigurationError("payment reservation operation intent lost its state race")
        return current.model_copy(
            update={"state": PaymentReservationState.SETTLING, "updated_at": updated_at}
        )

    def claim_payment_release_v2(
        self,
        reservation_id: str,
        *,
        idempotency_key: str,
        updated_at: datetime,
    ) -> PaymentReservationV2:
        """Claim full release before contacting an external payment adapter."""

        return self._claim_payment_intent_v2(
            reservation_id,
            intent_type="release",
            idempotency_key=idempotency_key,
            required_prepared_state=PreparedDecisionState.RESERVED,
            updated_at=updated_at,
        )

    def claim_payment_settlement_v2(
        self,
        reservation_id: str,
        *,
        idempotency_key: str,
        updated_at: datetime,
    ) -> PaymentReservationV2:
        """Claim capture/settlement after execution reaches durable SETTLING."""

        return self._claim_payment_intent_v2(
            reservation_id,
            intent_type="settle",
            idempotency_key=idempotency_key,
            required_prepared_state=PreparedDecisionState.SETTLING,
            updated_at=updated_at,
        )

    def payment_reservation_operation_intent(self, reservation_id: str) -> str | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT operation_intent FROM payment_reservations_v2
                WHERE reservation_id = ?
                """,
                (reservation_id,),
            ).fetchone()
        return row["operation_intent"] if row else None

    def save_usage_statement(self, statement: UsageStatement) -> UsageStatement:
        try:
            with self._immediate_transaction() as connection:
                binding = connection.execute(
                    """
                    SELECT quote.provider_id, quote.executor_id,
                           quote.executor_fingerprint, prepared.action_id,
                           prepared.selected_quote_id, prepared.authorization_kind,
                           prepared.authorization_id,
                           reservation.attempt_id AS reservation_attempt_id
                    FROM bounded_quotes AS quote
                    JOIN prepared_route_decisions AS prepared ON prepared.prepared_id = ?
                    LEFT JOIN payment_reservations_v2 AS reservation
                        ON reservation.prepared_id = prepared.prepared_id
                    WHERE quote.quote_id = ?
                    """,
                    (statement.prepared_id, statement.quote_id),
                ).fetchone()
                if binding is None:
                    raise ConfigurationError("usage statement quote or prepared decision is missing")
                expected = {
                    "provider_id": binding["provider_id"],
                    "executor_id": binding["executor_id"],
                    "executor_fingerprint": binding["executor_fingerprint"],
                    "action_id": binding["action_id"],
                    "attempt_id": binding["reservation_attempt_id"],
                }
                if any(getattr(statement, field) != value for field, value in expected.items()):
                    raise ConfigurationError("usage statement does not match its execution binding")
                if (
                    binding["selected_quote_id"] != statement.quote_id
                    or binding["authorization_kind"] != AuthorizationKind.SIGNED_QUOTE.value
                    or binding["authorization_id"] != statement.quote_id
                ):
                    raise ConfigurationError("usage statement requires the selected signed quote")
                self._immutable_insert_locked(
                    connection,
                    table="usage_statements",
                    identity={"usage_statement_id": statement.usage_statement_id},
                    indexed={
                        "quote_id": statement.quote_id,
                        "prepared_id": statement.prepared_id,
                        "action_id": statement.action_id,
                        "attempt_id": statement.attempt_id,
                        "provider_id": statement.provider_id,
                        "executor_id": statement.executor_id,
                        "executor_fingerprint": statement.executor_fingerprint,
                        "execution_status": statement.execution_status.value,
                        "issued_at": self._utc_text(statement.issued_at),
                        "signature_algorithm": statement.signature.algorithm.value,
                        "signature_key_id": statement.signature.key_id,
                        "evidence_level": statement.evidence_level.value,
                    },
                    value=statement,
                )
        except sqlite3.IntegrityError as exc:
            raise ConfigurationError(
                "immutable usage_statements violates its execution bindings"
            ) from exc
        return statement

    def get_usage_statement(self, usage_statement_id: str) -> UsageStatement | None:
        return self._get_typed(
            table="usage_statements",
            identity={"usage_statement_id": usage_statement_id},
            model=UsageStatement,
        )

    def list_usage_statements(
        self, *, prepared_id: str | None = None, limit: int = 1_000
    ) -> list[UsageStatement]:
        return self._list_typed(
            table="usage_statements",
            model=UsageStatement,
            clauses=("prepared_id = ?",) if prepared_id is not None else (),
            parameters=(prepared_id,) if prepared_id is not None else (),
            order_by="issued_at DESC, usage_statement_id",
            limit=limit,
        )

    def save_settlement_receipt(self, receipt: SettlementReceipt) -> SettlementReceipt:
        if receipt.authorization_kind is None or receipt.authorization_id is None:
            raise ConfigurationError("settlement authorization basis is missing")
        terminal = {
            SettlementStatus.COMPLETED: PaymentReservationState.SETTLED,
            SettlementStatus.SETTLED: PaymentReservationState.SETTLED,
            SettlementStatus.RELEASED: PaymentReservationState.RELEASED,
            SettlementStatus.DISPUTED: PaymentReservationState.DISPUTED,
            SettlementStatus.REFUNDED: PaymentReservationState.SETTLED,
        }
        target_state = terminal.get(receipt.status, PaymentReservationState.INDETERMINATE)
        prepared_terminal = {
            SettlementStatus.COMPLETED: PreparedDecisionState.SETTLED,
            SettlementStatus.SETTLED: PreparedDecisionState.SETTLED,
            SettlementStatus.RELEASED: PreparedDecisionState.RELEASED,
            SettlementStatus.DISPUTED: PreparedDecisionState.DISPUTED,
            SettlementStatus.REFUNDED: PreparedDecisionState.SETTLED,
        }
        prepared_target = prepared_terminal.get(receipt.status, PreparedDecisionState.INDETERMINATE)
        allowed_sources = {
            PaymentReservationState.SETTLED: {
                PaymentReservationState.SETTLING,
                PaymentReservationState.INDETERMINATE,
                PaymentReservationState.DISPUTED,
            },
            PaymentReservationState.RELEASED: {
                PaymentReservationState.SETTLING,
                PaymentReservationState.INDETERMINATE,
            },
            PaymentReservationState.DISPUTED: {
                PaymentReservationState.RESERVED,
                PaymentReservationState.SETTLING,
                PaymentReservationState.INDETERMINATE,
            },
            PaymentReservationState.INDETERMINATE: {
                PaymentReservationState.RESERVED,
                PaymentReservationState.SETTLING,
            },
        }
        prepared_sources = {
            PreparedDecisionState.SETTLED: {
                PreparedDecisionState.SETTLING,
                PreparedDecisionState.INDETERMINATE,
                PreparedDecisionState.DISPUTED,
            },
            PreparedDecisionState.RELEASED: {PreparedDecisionState.RESERVED},
            PreparedDecisionState.DISPUTED: {
                PreparedDecisionState.INVOKING,
                PreparedDecisionState.AWAITING_USAGE,
                PreparedDecisionState.SETTLING,
                PreparedDecisionState.INDETERMINATE,
            },
            PreparedDecisionState.INDETERMINATE: {
                PreparedDecisionState.INVOKING,
                PreparedDecisionState.AWAITING_USAGE,
                PreparedDecisionState.SETTLING,
            },
        }
        with self._immediate_transaction() as connection:
            binding = connection.execute(
                """
                SELECT
                    reservation.charge_id,
                    reservation.prepared_id,
                    reservation.quote_id,
                    reservation.authorization_kind,
                    reservation.authorization_id,
                    reservation.attempt_id,
                    reservation.maximum_amount,
                    reservation.currency,
                    reservation.state,
                    reservation.updated_at,
                    reservation.operation_intent,
                    prepared.state AS prepared_state,
                    prepared.authorization_kind AS prepared_authorization_kind,
                    prepared.authorization_id AS prepared_authorization_id,
                    prepared.maximum_amount AS prepared_maximum_amount,
                    prepared.currency AS prepared_currency
                FROM payment_reservations_v2 AS reservation
                JOIN prepared_route_decisions AS prepared
                    ON prepared.prepared_id = reservation.prepared_id
                WHERE reservation.reservation_id = ?
                """,
                (receipt.reservation_id,),
            ).fetchone()
            if binding is None:
                raise ConfigurationError("settlement reservation or prepared decision does not exist")
            bindings = (
                (receipt.charge_id, binding["charge_id"], "charge"),
                (receipt.prepared_id, binding["prepared_id"], "prepared decision"),
                (receipt.quote_id, binding["quote_id"], "quote"),
                (
                    receipt.authorization_kind.value,
                    binding["authorization_kind"],
                    "authorization kind",
                ),
                (receipt.authorization_id, binding["authorization_id"], "authorization ID"),
                (
                    receipt.authorization_kind.value,
                    binding["prepared_authorization_kind"],
                    "prepared authorization kind",
                ),
                (
                    receipt.authorization_id,
                    binding["prepared_authorization_id"],
                    "prepared authorization ID",
                ),
                (receipt.attempt_id, binding["attempt_id"], "attempt"),
                (receipt.reserved_amount.currency, binding["currency"], "reservation currency"),
                (
                    receipt.reserved_amount.currency,
                    binding["prepared_currency"],
                    "prepared currency",
                ),
            )
            for actual, expected, label in bindings:
                if actual != expected:
                    raise ConfigurationError(f"settlement {label} does not match reservation")
            maximum = Decimal(binding["maximum_amount"])
            if (
                binding["prepared_maximum_amount"] is None
                or maximum != Decimal(binding["prepared_maximum_amount"])
                or receipt.reserved_amount.amount != maximum
            ):
                basis = (
                    "signed quote"
                    if receipt.authorization_kind is AuthorizationKind.SIGNED_QUOTE
                    else "prepared authorization"
                )
                raise ConfigurationError(
                    f"settlement reservation must equal the {basis} maximum"
                )
            if receipt.authorization_kind is AuthorizationKind.SIGNED_QUOTE:
                quote_row = connection.execute(
                    "SELECT maximum_amount, currency FROM bounded_quotes WHERE quote_id = ?",
                    (receipt.authorization_id,),
                ).fetchone()
                if (
                    quote_row is None
                    or receipt.quote_id != receipt.authorization_id
                    or Decimal(quote_row["maximum_amount"]) != maximum
                    or quote_row["currency"] != receipt.reserved_amount.currency
                ):
                    raise ConfigurationError(
                        "settlement reservation must equal the signed quote maximum"
                    )
            elif receipt.quote_id is not None:
                raise ConfigurationError("non-quote settlement cannot carry a quote ID")
            if receipt.captured_amount.amount > maximum:
                label = (
                    "signed quote"
                    if receipt.authorization_kind is AuthorizationKind.SIGNED_QUOTE
                    else "authorization"
                )
                raise ConfigurationError(f"settlement capture exceeds the {label} maximum")

            existing = connection.execute(
                """
                SELECT payload_digest, payload_json FROM settlement_receipts
                WHERE settlement_id = ? OR reservation_id = ? OR charge_id = ?
                """,
                (receipt.settlement_id, receipt.reservation_id, receipt.charge_id),
            ).fetchone()
            if existing is not None:
                if (
                    existing["payload_digest"] != canonical_digest(receipt)
                    or existing["payload_json"] != receipt.model_dump_json()
                ):
                    raise ConfigurationError(
                        "settlement ID or reservation was reused with different content"
                    )
                if PaymentReservationState(binding["state"]) is not target_state:
                    raise ConfigurationError("settlement exists without its reservation transition")
                if PreparedDecisionState(binding["prepared_state"]) is not prepared_target:
                    raise ConfigurationError(
                        "settlement exists without its prepared-decision transition"
                    )
                return receipt

            source_state = PaymentReservationState(binding["state"])
            if source_state not in allowed_sources[target_state]:
                raise ConfigurationError(
                    f"reservation cannot settle from state {source_state.value}"
                )
            prepared_source = PreparedDecisionState(binding["prepared_state"])
            if prepared_source not in prepared_sources[prepared_target]:
                raise ConfigurationError(
                    f"prepared decision cannot settle from state {prepared_source.value}"
                )
            operation_intent = binding["operation_intent"]
            expected_intent = (
                "release:"
                if (
                    target_state is PaymentReservationState.RELEASED
                    or prepared_source is PreparedDecisionState.RESERVED
                )
                else "settle:"
            )
            if not isinstance(operation_intent, str) or not operation_intent.startswith(
                expected_intent
            ):
                raise ConfigurationError(
                    "settlement does not match the claimed payment operation intent"
                )
            operation, idempotency_key = operation_intent.split(":", 1)
            if (
                not idempotency_key
                or receipt.settlement_id
                != self._payment_operation_result_id(operation, idempotency_key)
            ):
                raise ConfigurationError(
                    "settlement ID does not match the claimed payment operation"
                )
            settled_at = self._utc_text(receipt.settled_at)
            if settled_at < binding["updated_at"]:
                raise ConfigurationError("settlement cannot precede the reservation update")
            self._immutable_insert_locked(
                connection,
                table="settlement_receipts",
                identity={"settlement_id": receipt.settlement_id},
                indexed={
                    "charge_id": receipt.charge_id,
                    "prepared_id": receipt.prepared_id,
                    "quote_id": receipt.quote_id,
                    "authorization_kind": receipt.authorization_kind.value,
                    "authorization_id": receipt.authorization_id,
                    "reservation_id": receipt.reservation_id,
                    "attempt_id": receipt.attempt_id,
                    "reserved_amount": self._amount_text(receipt.reserved_amount.amount),
                    "captured_amount": self._amount_text(receipt.captured_amount.amount),
                    "released_amount": self._amount_text(receipt.released_amount.amount),
                    "currency": receipt.reserved_amount.currency,
                    "status": receipt.status.value,
                    "evidence_level": receipt.evidence_level.value,
                    "settled_at": settled_at,
                },
                value=receipt,
            )
            cursor = connection.execute(
                """
                UPDATE payment_reservations_v2
                SET state = ?, updated_at = ?, indeterminate_reason = ?, operation_intent = NULL
                WHERE reservation_id = ? AND state = ?
                """,
                (
                    target_state.value,
                    settled_at,
                    (
                        f"settlement status {receipt.status.value}"
                        if target_state is PaymentReservationState.INDETERMINATE
                        else None
                    ),
                    receipt.reservation_id,
                    source_state.value,
                ),
            )
            if cursor.rowcount != 1:  # pragma: no cover - protected by BEGIN IMMEDIATE
                raise ConfigurationError("reservation settlement transition lost its state race")
            transition = PreparedRouteTransition(
                prepared_id=receipt.prepared_id,
                from_state=prepared_source,
                to_state=prepared_target,
                occurred_at=receipt.settled_at,
                reason=f"settlement {receipt.settlement_id}: {receipt.status.value}",
            )
            self._immutable_insert_locked(
                connection,
                table="prepared_route_transitions",
                identity={"transition_id": transition.transition_id},
                indexed={
                    "prepared_id": transition.prepared_id,
                    "from_state": transition.from_state.value,
                    "to_state": transition.to_state.value,
                    "occurred_at": self._utc_text(transition.occurred_at),
                    "reason": transition.reason,
                },
                value=transition,
            )
            cursor = connection.execute(
                """
                UPDATE prepared_route_decisions SET state = ?
                WHERE prepared_id = ? AND state = ?
                """,
                (prepared_target.value, receipt.prepared_id, prepared_source.value),
            )
            if cursor.rowcount != 1:  # pragma: no cover - protected by BEGIN IMMEDIATE
                raise ConfigurationError("prepared settlement transition lost its state race")
        return receipt

    store_settlement_and_transition = save_settlement_receipt

    def get_settlement_receipt(self, settlement_id: str) -> SettlementReceipt | None:
        return self._get_typed(
            table="settlement_receipts",
            identity={"settlement_id": settlement_id},
            model=SettlementReceipt,
        )

    def list_settlement_receipts(
        self, *, prepared_id: str | None = None, limit: int = 1_000
    ) -> list[SettlementReceipt]:
        return self._list_typed(
            table="settlement_receipts",
            model=SettlementReceipt,
            clauses=("prepared_id = ?",) if prepared_id is not None else (),
            parameters=(prepared_id,) if prepared_id is not None else (),
            order_by="settled_at DESC, settlement_id",
            limit=limit,
        )

    def save_billing_reconciliation(
        self, reconciliation: BillingReconciliation
    ) -> BillingReconciliation:
        return self._save_immutable(
            table="billing_reconciliations",
            identity={"reconciliation_id": reconciliation.reconciliation_id},
            indexed={
                "settlement_id": reconciliation.settlement_id,
                "provider_id": reconciliation.provider_id,
                "expected_amount": self._amount_text(reconciliation.expected_amount.amount),
                "billed_amount": self._amount_text(reconciliation.billed_amount.amount),
                "discrepancy": self._amount_text(reconciliation.discrepancy.amount),
                "currency": reconciliation.expected_amount.currency,
                "status": reconciliation.status.value,
                "reconciled_at": self._utc_text(reconciliation.reconciled_at),
                "evidence_level": reconciliation.status.economic_evidence_level.value,
            },
            value=reconciliation,
        )

    def get_billing_reconciliation(self, reconciliation_id: str) -> BillingReconciliation | None:
        return self._get_typed(
            table="billing_reconciliations",
            identity={"reconciliation_id": reconciliation_id},
            model=BillingReconciliation,
        )

    def list_billing_reconciliations(
        self, *, settlement_id: str | None = None, limit: int = 1_000
    ) -> list[BillingReconciliation]:
        return self._list_typed(
            table="billing_reconciliations",
            model=BillingReconciliation,
            clauses=("settlement_id = ?",) if settlement_id is not None else (),
            parameters=(settlement_id,) if settlement_id is not None else (),
            order_by="reconciled_at DESC, reconciliation_id",
            limit=limit,
        )

    def save_market_aggregate(self, aggregate: MarketAggregate) -> MarketAggregate:
        return self._save_immutable(
            table="market_aggregates",
            identity={"aggregate_id": aggregate.aggregate_id},
            indexed={
                "capability": aggregate.capability,
                "provider_id": aggregate.provider_id,
                "executor_id": aggregate.executor_id,
                "executor_fingerprint": aggregate.executor_fingerprint,
                "region": aggregate.region,
                "account_tier": aggregate.account_tier,
                "input_bucket": aggregate.input_bucket,
                "sample_size": aggregate.sample_size,
                "window_start": self._utc_text(aggregate.window_start),
                "window_end": self._utc_text(aggregate.window_end),
                "generated_at": self._utc_text(aggregate.generated_at),
                "expires_at": self._utc_text(aggregate.expires_at),
                "signature_algorithm": aggregate.signature.algorithm.value,
                "signature_key_id": aggregate.signature.key_id,
                "evidence_level": "STATIC_PRIOR",
            },
            value=aggregate,
        )

    def get_market_aggregate(self, aggregate_id: str) -> MarketAggregate | None:
        return self._get_typed(
            table="market_aggregates",
            identity={"aggregate_id": aggregate_id},
            model=MarketAggregate,
        )

    def list_market_aggregates(
        self, *, capability: str | None = None, limit: int = 1_000
    ) -> list[MarketAggregate]:
        return self._list_typed(
            table="market_aggregates",
            model=MarketAggregate,
            clauses=("capability = ?",) if capability is not None else (),
            parameters=(capability,) if capability is not None else (),
            order_by="generated_at DESC, aggregate_id",
            limit=limit,
        )

    def save_pricing_dispute(self, dispute: PricingDispute) -> PricingDispute:
        return self._save_immutable(
            table="pricing_disputes",
            identity={"dispute_id": dispute.dispute_id},
            indexed={
                "prepared_id": dispute.prepared_id,
                "quote_id": dispute.quote_id,
                "usage_statement_id": dispute.usage_statement_id,
                "provider_id": dispute.provider_id,
                "quoted_maximum": self._amount_text(dispute.quoted_maximum.amount),
                "provider_claimed_amount": self._amount_text(
                    dispute.provider_claimed_amount.amount
                ),
                "currency": dispute.quoted_maximum.currency,
                "status": dispute.status.value,
                "created_at": self._utc_text(dispute.created_at),
                "resolved_at": self._utc_text(dispute.resolved_at) if dispute.resolved_at else None,
            },
            value=dispute,
        )

    def get_pricing_dispute(self, dispute_id: str) -> PricingDispute | None:
        return self._get_typed(
            table="pricing_disputes",
            identity={"dispute_id": dispute_id},
            model=PricingDispute,
        )

    def list_pricing_disputes(
        self, *, prepared_id: str | None = None, limit: int = 1_000
    ) -> list[PricingDispute]:
        return self._list_typed(
            table="pricing_disputes",
            model=PricingDispute,
            clauses=("prepared_id = ?",) if prepared_id is not None else (),
            parameters=(prepared_id,) if prepared_id is not None else (),
            order_by="created_at DESC, dispute_id",
            limit=limit,
        )

    def save_economic_evidence_link(self, link: EconomicEvidenceLink) -> EconomicEvidenceLink:
        return self._save_immutable(
            table="economic_evidence_links",
            identity={"link_id": link.link_id},
            indexed={
                "charge_id": link.charge_id,
                "evidence_type": link.evidence_type,
                "evidence_id": link.evidence_id,
                "evidence_level": link.evidence_level.value,
                "evidence_payload_digest": link.payload_digest,
                "authoritative": int(link.authoritative),
                "supersedes_link_id": link.supersedes_link_id,
                "created_at": self._utc_text(link.created_at),
            },
            value=link,
        )

    def get_economic_evidence_link(self, link_id: str) -> EconomicEvidenceLink | None:
        return self._get_typed(
            table="economic_evidence_links",
            identity={"link_id": link_id},
            model=EconomicEvidenceLink,
        )

    def list_economic_evidence_links(
        self, *, charge_id: str | None = None, limit: int = 1_000
    ) -> list[EconomicEvidenceLink]:
        return self._list_typed(
            table="economic_evidence_links",
            model=EconomicEvidenceLink,
            clauses=("charge_id = ?",) if charge_id is not None else (),
            parameters=(charge_id,) if charge_id is not None else (),
            order_by="created_at, link_id",
            limit=limit,
        )

    def save_refund_receipt_v2(self, refund: RefundReceiptV2) -> RefundReceiptV2:
        """Import refund evidence while respecting completed and pending refunds."""

        with self._immediate_transaction() as connection:
            self._insert_refund_receipt_locked(connection, refund)
        return refund

    def _insert_refund_receipt_locked(
        self,
        connection: sqlite3.Connection,
        refund: RefundReceiptV2,
        *,
        completing_authorization_id: str | None = None,
    ) -> None:
        existing = connection.execute(
            """
            SELECT payload_digest, payload_json FROM refund_receipts_v2
            WHERE refund_id = ? OR idempotency_key = ?
            """,
            (refund.refund_id, refund.idempotency_key),
        ).fetchone()
        if existing is not None:
            if (
                existing["payload_digest"] != canonical_digest(refund)
                or existing["payload_json"] != refund.model_dump_json()
            ):
                raise ConfigurationError(
                    "refund ID or idempotency key was reused with different content"
                )
            return
        settlement = connection.execute(
            """
            SELECT charge_id, captured_amount, currency FROM settlement_receipts
            WHERE settlement_id = ?
            """,
            (refund.settlement_id,),
        ).fetchone()
        if settlement is None:
            raise ConfigurationError("refund settlement does not exist")
        if settlement["charge_id"] != refund.charge_id:
            raise ConfigurationError("refund charge does not match settlement charge")
        if settlement["currency"] != refund.amount.currency:
            raise ConfigurationError("refund currency does not match settlement currency")
        refunded = sum(
            (
                Decimal(row[0])
                for row in connection.execute(
                    "SELECT amount FROM refund_receipts_v2 WHERE settlement_id = ?",
                    (refund.settlement_id,),
                )
            ),
            Decimal(0),
        )
        authorization_query = """
            SELECT amount FROM refund_authorizations_v2
            WHERE settlement_id = ? AND state IN ('AUTHORIZED', 'INDETERMINATE')
        """
        authorization_parameters: list[object] = [refund.settlement_id]
        if completing_authorization_id is not None:
            authorization_query += " AND refund_id != ?"
            authorization_parameters.append(completing_authorization_id)
        pending = sum(
            (
                Decimal(row[0])
                for row in connection.execute(
                    authorization_query, authorization_parameters
                )
            ),
            Decimal(0),
        )
        if refunded + pending + refund.amount.amount > Decimal(settlement["captured_amount"]):
            raise ConfigurationError("refund exceeds captured settlement amount")
        self._immutable_insert_locked(
            connection,
            table="refund_receipts_v2",
            identity={"refund_id": refund.refund_id},
            indexed={
                "settlement_id": refund.settlement_id,
                "charge_id": refund.charge_id,
                "amount": self._amount_text(refund.amount.amount),
                "currency": refund.amount.currency,
                "idempotency_key": refund.idempotency_key,
                "refunded_at": self._utc_text(refund.refunded_at),
            },
            value=refund,
        )

    @staticmethod
    def _refund_authorization_from_row(row: sqlite3.Row) -> RefundAuthorizationRecord:
        return RefundAuthorizationRecord(
            refund_id=row["refund_id"],
            settlement_id=row["settlement_id"],
            charge_id=row["charge_id"],
            amount=CurrencyAmount(amount=Decimal(row["amount"]), currency=row["currency"]),
            idempotency_key=row["idempotency_key"],
            request_digest=row["request_digest"],
            state=row["state"],
            authorized_at=datetime.fromisoformat(row["authorized_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def authorize_refund_v2(
        self,
        *,
        refund_id: str,
        settlement_id: str,
        amount: CurrencyAmount,
        idempotency_key: str,
        request_digest: str,
        authorized_at: datetime,
    ) -> RefundAuthorizationRecord:
        """Atomically reserve refundable capture before an external rail call."""

        if amount.amount <= 0:
            raise ConfigurationError("refund authorization amount must be positive")
        if (
            not refund_id
            or len(refund_id) > 200
            or not idempotency_key
            or len(idempotency_key) > 256
            or len(request_digest) != 71
            or not request_digest.startswith("sha256:")
        ):
            raise ConfigurationError("refund authorization identifiers must be non-empty")
        authorized_text = self._utc_text(authorized_at)
        with self._immediate_transaction() as connection:
            existing = connection.execute(
                """
                SELECT * FROM refund_authorizations_v2
                WHERE refund_id = ? OR idempotency_key = ?
                """,
                (refund_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                record = self._refund_authorization_from_row(existing)
                if (
                    record["refund_id"] != refund_id
                    or record["settlement_id"] != settlement_id
                    or record["amount"] != amount
                    or record["idempotency_key"] != idempotency_key
                    or record["request_digest"] != request_digest
                ):
                    raise ConfigurationError(
                        "refund authorization ID or idempotency key conflicts"
                    )
                return record
            settlement = connection.execute(
                """
                SELECT charge_id, captured_amount, currency FROM settlement_receipts
                WHERE settlement_id = ?
                """,
                (settlement_id,),
            ).fetchone()
            if settlement is None:
                raise ConfigurationError("refund settlement does not exist")
            if settlement["currency"] != amount.currency:
                raise ConfigurationError("refund currency does not match settlement currency")
            completed = sum(
                (
                    Decimal(row[0])
                    for row in connection.execute(
                        "SELECT amount FROM refund_receipts_v2 WHERE settlement_id = ?",
                        (settlement_id,),
                    )
                ),
                Decimal(0),
            )
            pending = sum(
                (
                    Decimal(row[0])
                    for row in connection.execute(
                        """
                        SELECT amount FROM refund_authorizations_v2
                        WHERE settlement_id = ?
                          AND state IN ('AUTHORIZED', 'INDETERMINATE')
                        """,
                        (settlement_id,),
                    )
                ),
                Decimal(0),
            )
            if completed + pending + amount.amount > Decimal(settlement["captured_amount"]):
                raise ConfigurationError("refund exceeds unrefunded captured amount")
            connection.execute(
                """
                INSERT INTO refund_authorizations_v2
                    (refund_id, settlement_id, charge_id, amount, currency,
                     idempotency_key, request_digest, state, authorized_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'AUTHORIZED', ?, ?)
                """,
                (
                    refund_id,
                    settlement_id,
                    settlement["charge_id"],
                    self._amount_text(amount.amount),
                    amount.currency,
                    idempotency_key,
                    request_digest,
                    authorized_text,
                    authorized_text,
                ),
            )
            row = connection.execute(
                "SELECT * FROM refund_authorizations_v2 WHERE refund_id = ?",
                (refund_id,),
            ).fetchone()
        return self._refund_authorization_from_row(row)

    def complete_refund_v2(self, refund: RefundReceiptV2) -> RefundReceiptV2:
        """Persist rail evidence and consume the matching refund authorization."""

        with self._immediate_transaction() as connection:
            row = connection.execute(
                """
                SELECT * FROM refund_authorizations_v2
                WHERE refund_id = ? OR idempotency_key = ?
                """,
                (refund.refund_id, refund.idempotency_key),
            ).fetchone()
            if row is None:
                raise ConfigurationError("refund was not authorized before external execution")
            authorization = self._refund_authorization_from_row(row)
            if (
                authorization["refund_id"] != refund.refund_id
                or authorization["settlement_id"] != refund.settlement_id
                or authorization["charge_id"] != refund.charge_id
                or authorization["amount"] != refund.amount
                or authorization["idempotency_key"] != refund.idempotency_key
            ):
                raise ConfigurationError("refund receipt does not match its authorization")
            if authorization["state"] == "RELEASED":
                raise ConfigurationError("released refund authorization cannot complete")
            self._insert_refund_receipt_locked(
                connection,
                refund,
                completing_authorization_id=refund.refund_id,
            )
            connection.execute(
                """
                UPDATE refund_authorizations_v2
                SET state = 'COMPLETED', updated_at = ?
                WHERE refund_id = ? AND state IN ('AUTHORIZED', 'INDETERMINATE', 'COMPLETED')
                """,
                (self._utc_text(refund.refunded_at), refund.refund_id),
            )
        return refund

    def mark_refund_authorization_indeterminate(
        self, refund_id: str, *, updated_at: datetime
    ) -> RefundAuthorizationRecord:
        updated_text = self._utc_text(updated_at)
        with self._immediate_transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE refund_authorizations_v2
                SET state = 'INDETERMINATE', updated_at = ?
                WHERE refund_id = ? AND state IN ('AUTHORIZED', 'INDETERMINATE')
                """,
                (updated_text, refund_id),
            )
            row = connection.execute(
                "SELECT * FROM refund_authorizations_v2 WHERE refund_id = ?",
                (refund_id,),
            ).fetchone()
            if row is None or cursor.rowcount != 1:
                raise ConfigurationError("refund authorization cannot become indeterminate")
        return self._refund_authorization_from_row(row)

    def release_refund_authorization_v2(
        self,
        refund_id: str,
        *,
        request_digest: str,
        released_at: datetime,
    ) -> RefundAuthorizationRecord:
        released_text = self._utc_text(released_at)
        with self._immediate_transaction() as connection:
            row = connection.execute(
                "SELECT * FROM refund_authorizations_v2 WHERE refund_id = ?",
                (refund_id,),
            ).fetchone()
            if row is None:
                raise ConfigurationError("refund authorization does not exist")
            if row["request_digest"] != request_digest:
                raise ConfigurationError("refund authorization request digest conflicts")
            if row["state"] == "COMPLETED":
                raise ConfigurationError("completed refund authorization cannot be released")
            connection.execute(
                """
                UPDATE refund_authorizations_v2
                SET state = 'RELEASED', updated_at = ?
                WHERE refund_id = ? AND state IN ('AUTHORIZED', 'INDETERMINATE', 'RELEASED')
                """,
                (released_text, refund_id),
            )
            row = connection.execute(
                "SELECT * FROM refund_authorizations_v2 WHERE refund_id = ?",
                (refund_id,),
            ).fetchone()
        return self._refund_authorization_from_row(row)

    def get_refund_authorization_v2(
        self, refund_id: str
    ) -> RefundAuthorizationRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM refund_authorizations_v2 WHERE refund_id = ?",
                (refund_id,),
            ).fetchone()
        return self._refund_authorization_from_row(row) if row else None

    def pending_refund_authorizations_v2(
        self, *, limit: int = 1_000
    ) -> list[RefundAuthorizationRecord]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM refund_authorizations_v2
                WHERE state IN ('AUTHORIZED', 'INDETERMINATE')
                ORDER BY authorized_at, refund_id LIMIT ?
                """,
                (max(1, min(limit, 10_000)),),
            ).fetchall()
        return [self._refund_authorization_from_row(row) for row in rows]

    def get_refund_receipt_v2(self, refund_id: str) -> RefundReceiptV2 | None:
        return self._get_typed(
            table="refund_receipts_v2",
            identity={"refund_id": refund_id},
            model=RefundReceiptV2,
        )

    def list_refund_receipts_v2(
        self, *, settlement_id: str | None = None, limit: int = 1_000
    ) -> list[RefundReceiptV2]:
        return self._list_typed(
            table="refund_receipts_v2",
            model=RefundReceiptV2,
            clauses=("settlement_id = ?",) if settlement_id is not None else (),
            parameters=(settlement_id,) if settlement_id is not None else (),
            order_by="refunded_at DESC, refund_id",
            limit=limit,
        )

    @staticmethod
    def _payment_operation_key(operation: str, idempotency_key: str) -> str:
        if not operation or ":" in operation or not idempotency_key:
            raise ConfigurationError("payment operation and idempotency key must be non-empty")
        return f"payment:{operation}:{idempotency_key}"

    def claim_payment_operation(
        self, operation: str, idempotency_key: str, request_digest: str
    ) -> dict[str, object] | None:
        return self.claim_idempotency(
            self._payment_operation_key(operation, idempotency_key), request_digest
        )

    def complete_payment_operation(
        self,
        operation: str,
        idempotency_key: str,
        *,
        result_type: str,
        result_id: str,
    ) -> None:
        if not result_type or not result_id:
            raise ConfigurationError("payment operation result must be identified")
        key = self._payment_operation_key(operation, idempotency_key)
        with self._immediate_transaction() as connection:
            row = connection.execute(
                """
                SELECT state, decision_id, status, receipt_ids_json
                FROM idempotency_records WHERE idempotency_key = ?
                """,
                (key,),
            ).fetchone()
            if row is None:
                raise ConfigurationError("payment operation was not claimed")
            if row["state"] == "complete":
                if (
                    row["decision_id"] == operation
                    and row["status"] == result_type
                    and json.loads(row["receipt_ids_json"]) == [result_id]
                ):
                    return
                raise ConfigurationError(
                    "payment operation idempotency key conflicts with an existing result"
                )
            cursor = connection.execute(
                """
                UPDATE idempotency_records
                SET state = 'complete', decision_id = ?, status = ?, receipt_ids_json = ?
                WHERE idempotency_key = ? AND state IN ('claimed', 'executing', 'indeterminate')
                """,
                (operation, result_type, json.dumps([result_id]), key),
            )
            if cursor.rowcount != 1:
                raise ConfigurationError("payment operation is not completable")

    def mark_payment_operation_executing(self, operation: str, idempotency_key: str) -> None:
        key = self._payment_operation_key(operation, idempotency_key)
        with self._immediate_transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE idempotency_records SET state = 'executing'
                WHERE idempotency_key = ? AND state IN ('claimed', 'indeterminate')
                """,
                (key,),
            )
            if cursor.rowcount != 1:
                raise ConfigurationError("payment operation claim is not executable")

    def mark_payment_operation_indeterminate(
        self, operation: str, idempotency_key: str
    ) -> None:
        self.mark_idempotency_indeterminate(
            self._payment_operation_key(operation, idempotency_key)
        )

    def abandon_payment_operation(self, operation: str, idempotency_key: str) -> None:
        self.abandon_idempotency(self._payment_operation_key(operation, idempotency_key))

    def get_payment_operation(
        self, operation: str, idempotency_key: str
    ) -> dict[str, object] | None:
        key = self._payment_operation_key(operation, idempotency_key)
        with self._lock:
            row = self._connection.execute(
                """
                SELECT request_hash, state, decision_id, status, receipt_ids_json
                FROM idempotency_records WHERE idempotency_key = ?
                """,
                (key,),
            ).fetchone()
        if row is None:
            return None
        return {
            "request_digest": row["request_hash"],
            "state": row["state"],
            "operation": row["decision_id"],
            "result_type": row["status"],
            "result_ids": json.loads(row["receipt_ids_json"]),
        }

    def protocol_cutover(self, name: str) -> datetime | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT occurred_at FROM protocol_cutovers WHERE name = ?",
                (name,),
            ).fetchone()
        return datetime.fromisoformat(row[0]) if row else None

    def save_action_approval(self, approval: ActionApprovalRecord) -> None:
        payload = approval.model_dump_json()
        with self._immediate_transaction() as connection:
            row = connection.execute(
                "SELECT payload_json FROM action_approval_records WHERE approval_id = ?",
                (approval.approval_id,),
            ).fetchone()
            if row is not None and row[0] != payload:
                raise ConfigurationError("approval ID conflicts with prior content")
            connection.execute(
                """
                INSERT OR IGNORE INTO action_approval_records(
                    approval_id, action_digest, prepared_id, attempt_id,
                    granted_at, expires_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval.approval_id,
                    approval.action_digest,
                    approval.prepared_id,
                    approval.attempt_id,
                    approval.granted_at.isoformat(),
                    approval.expires_at.isoformat() if approval.expires_at else None,
                    payload,
                ),
            )

    def get_action_approval(self, approval_id: str) -> ActionApprovalRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM action_approval_records WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
        return ActionApprovalRecord.model_validate_json(row[0]) if row else None

    def save_provider_package_ingest(
        self,
        package: ProviderPackage,
        verification: PackageVerificationResult,
        *,
        source_id: str,
        imported_at: datetime,
        content_artifacts: list[tuple[ArtifactReference, str, str]],
        artifact_results: list[tuple[ArtifactReference, ArtifactVerificationResult]],
        evidence_records: list[tuple[EvidenceReference, str, str]],
        acceptances: list[EvidenceAcceptance],
        candidates: list[RouteCandidate],
        snapshots: list[CandidateVerificationSnapshot],
    ) -> None:
        """Atomically publish a fully evaluated package ingest into trusted state."""

        package_payload = package.model_dump_json(by_alias=True)
        with self._immediate_transaction() as connection:
            row = connection.execute(
                "SELECT payload_json FROM provider_packages WHERE package_digest = ?",
                (verification.package_digest,),
            ).fetchone()
            if row is not None and row[0] != package_payload:
                raise ConfigurationError("provider package digest collides with different content")
            connection.execute(
                """
                INSERT OR IGNORE INTO provider_packages(
                    package_digest, package_id, package_version, provider_id, source_id,
                    imported_at, integrity_status, effective_identity_trust, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    verification.package_digest,
                    package.metadata.package_id,
                    package.metadata.version,
                    package.spec.provider.provider_id,
                    source_id,
                    imported_at.isoformat(),
                    verification.integrity_status.value,
                    verification.effective_identity_trust.value,
                    package_payload,
                ),
            )
            for signature_result in verification.signatures:
                self._save_package_signature_locked(
                    connection,
                    verification.package_digest,
                    signature_result,
                    imported_at,
                )

            for reference, cas_path, source_kind in content_artifacts:
                existing = connection.execute(
                    """
                    SELECT media_type, size_bytes, cas_path FROM content_artifacts
                    WHERE artifact_digest = ?
                    """,
                    (reference.digest,),
                ).fetchone()
                expected = (reference.media_type, reference.size_bytes, cas_path)
                if existing is not None and tuple(existing) != expected:
                    raise ConfigurationError(
                        "content artifact digest collides with different metadata"
                    )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO content_artifacts(
                        artifact_digest, media_type, size_bytes, cas_path,
                        source_kind, verified_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        reference.digest,
                        reference.media_type,
                        reference.size_bytes,
                        cas_path,
                        source_kind,
                        imported_at.isoformat(),
                    ),
                )
            for reference, artifact_result in artifact_results:
                connection.execute(
                    """
                    INSERT INTO provider_package_artifacts(
                        package_digest, artifact_id, artifact_digest, required, status,
                        failure_code, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(package_digest, artifact_id) DO UPDATE SET
                        status = excluded.status,
                        failure_code = excluded.failure_code,
                        payload_json = excluded.payload_json
                    """,
                    (
                        verification.package_digest,
                        reference.artifact_id,
                        reference.digest,
                        int(reference.required),
                        artifact_result.status.value,
                        artifact_result.failure_code,
                        artifact_result.model_dump_json(),
                    ),
                )
            for evidence, artifact_digest, effective_trust in evidence_records:
                payload = evidence.model_dump_json()
                existing = connection.execute(
                    """
                    SELECT payload_json FROM evidence_records
                    WHERE package_digest = ? AND evidence_id = ?
                    """,
                    (verification.package_digest, evidence.evidence_id),
                ).fetchone()
                if existing is not None and existing[0] != payload:
                    raise ConfigurationError("evidence identity collides with different content")
                connection.execute(
                    """
                    INSERT OR IGNORE INTO evidence_records(
                        package_digest, evidence_id, artifact_digest, evidence_type, route_id,
                        route_fingerprint, workload_digest, producer_id, declared_trust,
                        effective_trust, valid_from, expires_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        verification.package_digest,
                        evidence.evidence_id,
                        artifact_digest,
                        evidence.evidence_type.value,
                        evidence.subject.route_id,
                        evidence.subject.route_fingerprint,
                        evidence.subject.workload_digest,
                        evidence.producer.producer_id,
                        evidence.trust_claim.value,
                        effective_trust,
                        (evidence.validity.not_before or evidence.validity.issued_at).isoformat(),
                        (
                            evidence.validity.expires_at.isoformat()
                            if evidence.validity.expires_at is not None
                            else None
                        ),
                        payload,
                    ),
                )
            for acceptance in acceptances:
                payload = acceptance.model_dump_json()
                existing = connection.execute(
                    "SELECT payload_json FROM evidence_acceptances WHERE acceptance_id = ?",
                    (acceptance.acceptance_id,),
                ).fetchone()
                if existing is not None and existing[0] != payload:
                    raise ConfigurationError(
                        "evidence acceptance ID conflicts with prior content"
                    )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO evidence_acceptances(
                        acceptance_id, package_digest, evidence_id, executor_id, metric,
                        status, reason_code, applicability, confidence, effective_trust,
                        evaluated_at, rate_card_snapshot_id, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        acceptance.acceptance_id,
                        acceptance.package_digest,
                        acceptance.evidence_id,
                        acceptance.candidate_id,
                        acceptance.metric,
                        acceptance.status.value,
                        acceptance.reason_code,
                        acceptance.applicability,
                        str(acceptance.confidence),
                        acceptance.effective_trust.value,
                        acceptance.evaluated_at.isoformat(),
                        acceptance.rate_card_snapshot_id,
                        payload,
                    ),
                )
            for snapshot in snapshots:
                payload = snapshot.model_dump_json()
                existing = connection.execute(
                    """
                    SELECT payload_json FROM candidate_verification_snapshots
                    WHERE snapshot_id = ?
                    """,
                    (snapshot.snapshot_id,),
                ).fetchone()
                if existing is not None and existing[0] != payload:
                    raise ConfigurationError(
                        "verification snapshot ID conflicts with prior content"
                    )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO candidate_verification_snapshots(
                        snapshot_id, executor_id, package_digest, route_fingerprint,
                        created_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot.snapshot_id,
                        snapshot.candidate_id,
                        snapshot.package_digest,
                        snapshot.route_fingerprint,
                        snapshot.created_at.isoformat(),
                        payload,
                    ),
                )
            for candidate in candidates:
                connection.execute(
                    """
                    INSERT INTO route_candidates(
                        executor_id, source_id, fingerprint, status, package_digest,
                        package_fingerprint, verification_snapshot_id, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(executor_id) DO UPDATE SET
                        source_id = excluded.source_id,
                        fingerprint = excluded.fingerprint,
                        status = excluded.status,
                        package_digest = excluded.package_digest,
                        package_fingerprint = excluded.package_fingerprint,
                        verification_snapshot_id = excluded.verification_snapshot_id,
                        payload_json = excluded.payload_json
                    """,
                    (
                        candidate.executor_id,
                        candidate.source_id,
                        candidate.behavior_fingerprint,
                        candidate.status.value,
                        candidate.package_digest,
                        candidate.package_fingerprint,
                        candidate.verification_snapshot_id,
                        candidate.model_dump_json(),
                    ),
                )

    def save_provider_package_audit_event(
        self,
        *,
        event_id: str,
        event_type: str,
        occurred_at: datetime,
        package_digest: str | None = None,
        executor_id: str | None = None,
        reason_code: str | None = None,
    ) -> None:
        payload = json.dumps(
            {
                "event_id": event_id,
                "event_type": event_type,
                "package_digest": package_digest,
                "executor_id": executor_id,
                "reason_code": reason_code,
                "occurred_at": occurred_at.isoformat(),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT OR IGNORE INTO provider_package_audit_events(
                    event_id, package_digest, executor_id, event_type,
                    reason_code, occurred_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    package_digest,
                    executor_id,
                    event_type,
                    reason_code,
                    occurred_at.isoformat(),
                    payload,
                ),
            )

    def save_provider_package(
        self,
        package: ProviderPackage,
        verification: PackageVerificationResult,
        *,
        source_id: str,
        imported_at: datetime,
    ) -> ProviderPackage:
        payload = package.model_dump_json(by_alias=True)
        with self._immediate_transaction() as connection:
            row = connection.execute(
                "SELECT payload_json FROM provider_packages WHERE package_digest = ?",
                (verification.package_digest,),
            ).fetchone()
            if row is not None and row[0] != payload:
                raise ConfigurationError("provider package digest collides with different content")
            connection.execute(
                """
                INSERT OR IGNORE INTO provider_packages(
                    package_digest, package_id, package_version, provider_id, source_id,
                    imported_at, integrity_status, effective_identity_trust, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    verification.package_digest,
                    package.metadata.package_id,
                    package.metadata.version,
                    package.spec.provider.provider_id,
                    source_id,
                    imported_at.isoformat(),
                    verification.integrity_status.value,
                    verification.effective_identity_trust.value,
                    payload,
                ),
            )
            for result in verification.signatures:
                self._save_package_signature_locked(
                    connection,
                    verification.package_digest,
                    result,
                    imported_at,
                )
        return package

    @staticmethod
    def _save_package_signature_locked(
        connection: sqlite3.Connection,
        package_digest: str,
        result: SignatureVerificationResult,
        verified_at: datetime,
    ) -> None:
        payload = result.model_dump_json()
        row = connection.execute(
            """
            SELECT payload_json FROM provider_package_signatures
            WHERE package_digest = ? AND signature_id = ?
            """,
            (package_digest, result.signature_id),
        ).fetchone()
        if row is not None and row[0] != payload:
            raise ConfigurationError("package signature verification conflicts with prior result")
        connection.execute(
            """
            INSERT OR IGNORE INTO provider_package_signatures(
                package_digest, signature_id, key_id, role, status, effective_trust,
                verified_at, failure_code, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                package_digest,
                result.signature_id,
                result.key_id,
                "package_publisher",
                result.status.value,
                result.effective_trust.value,
                verified_at.isoformat(),
                result.failure_code,
                payload,
            ),
        )

    def get_provider_package(self, package_digest: str) -> ProviderPackage | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM provider_packages WHERE package_digest = ?",
                (package_digest,),
            ).fetchone()
        return ProviderPackage.model_validate_json(row[0]) if row else None

    def save_content_artifact(
        self,
        reference: ArtifactReference,
        *,
        cas_path: str,
        source_kind: str,
        verified_at: datetime,
    ) -> None:
        with self._immediate_transaction() as connection:
            row = connection.execute(
                """
                SELECT media_type, size_bytes, cas_path FROM content_artifacts
                WHERE artifact_digest = ?
                """,
                (reference.digest,),
            ).fetchone()
            expected = (reference.media_type, reference.size_bytes, cas_path)
            if row is not None and tuple(row) != expected:
                raise ConfigurationError("content artifact digest collides with different metadata")
            connection.execute(
                """
                INSERT OR IGNORE INTO content_artifacts(
                    artifact_digest, media_type, size_bytes, cas_path, source_kind, verified_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    reference.digest,
                    reference.media_type,
                    reference.size_bytes,
                    cas_path,
                    source_kind,
                    verified_at.isoformat(),
                ),
            )

    def save_package_artifact_result(
        self,
        package_digest: str,
        reference: ArtifactReference,
        result: ArtifactVerificationResult,
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO provider_package_artifacts(
                    package_digest, artifact_id, artifact_digest, required, status,
                    failure_code, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(package_digest, artifact_id) DO UPDATE SET
                    status = excluded.status,
                    failure_code = excluded.failure_code,
                    payload_json = excluded.payload_json
                """,
                (
                    package_digest,
                    reference.artifact_id,
                    reference.digest,
                    int(reference.required),
                    result.status.value,
                    result.failure_code,
                    result.model_dump_json(),
                ),
            )

    def save_evidence_record(
        self,
        package_digest: str,
        evidence: EvidenceReference,
        *,
        artifact_digest: str,
        effective_trust: str,
    ) -> None:
        payload = evidence.model_dump_json()
        with self._immediate_transaction() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM evidence_records
                WHERE package_digest = ? AND evidence_id = ?
                """,
                (package_digest, evidence.evidence_id),
            ).fetchone()
            if row is not None and row[0] != payload:
                raise ConfigurationError("evidence identity collides with different content")
            connection.execute(
                """
                INSERT OR IGNORE INTO evidence_records(
                    package_digest, evidence_id, artifact_digest, evidence_type, route_id,
                    route_fingerprint, workload_digest, producer_id, declared_trust,
                    effective_trust, valid_from, expires_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    package_digest,
                    evidence.evidence_id,
                    artifact_digest,
                    evidence.evidence_type.value,
                    evidence.subject.route_id,
                    evidence.subject.route_fingerprint,
                    evidence.subject.workload_digest,
                    evidence.producer.producer_id,
                    evidence.trust_claim.value,
                    effective_trust,
                    (evidence.validity.not_before or evidence.validity.issued_at).isoformat(),
                    (
                        evidence.validity.expires_at.isoformat()
                        if evidence.validity.expires_at is not None
                        else None
                    ),
                    payload,
                ),
            )

    def save_evidence_acceptance(self, acceptance: EvidenceAcceptance) -> None:
        payload = acceptance.model_dump_json()
        with self._immediate_transaction() as connection:
            row = connection.execute(
                "SELECT payload_json FROM evidence_acceptances WHERE acceptance_id = ?",
                (acceptance.acceptance_id,),
            ).fetchone()
            if row is not None and row[0] != payload:
                raise ConfigurationError("evidence acceptance ID conflicts with prior content")
            connection.execute(
                """
                INSERT OR IGNORE INTO evidence_acceptances(
                    acceptance_id, package_digest, evidence_id, executor_id, metric, status,
                    reason_code, applicability, confidence, effective_trust, evaluated_at,
                    rate_card_snapshot_id, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    acceptance.acceptance_id,
                    acceptance.package_digest,
                    acceptance.evidence_id,
                    acceptance.candidate_id,
                    acceptance.metric,
                    acceptance.status.value,
                    acceptance.reason_code,
                    acceptance.applicability,
                    str(acceptance.confidence),
                    acceptance.effective_trust.value,
                    acceptance.evaluated_at.isoformat(),
                    acceptance.rate_card_snapshot_id,
                    payload,
                ),
            )

    def list_evidence_acceptances(self, executor_id: str) -> list[EvidenceAcceptance]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT payload_json FROM evidence_acceptances
                WHERE executor_id = ? ORDER BY evaluated_at, acceptance_id
                """,
                (executor_id,),
            ).fetchall()
        return [EvidenceAcceptance.model_validate_json(row[0]) for row in rows]

    def get_evidence_acceptance(self, acceptance_id: str) -> EvidenceAcceptance | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM evidence_acceptances WHERE acceptance_id = ?",
                (acceptance_id,),
            ).fetchone()
        return EvidenceAcceptance.model_validate_json(row[0]) if row else None

    def list_evidence_records(self, executor_id: str) -> list[EvidenceReference]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT payload_json FROM evidence_records
                WHERE route_id = ? ORDER BY evidence_type, evidence_id
                """,
                (executor_id,),
            ).fetchall()
        return [EvidenceReference.model_validate_json(row[0]) for row in rows]

    def get_evidence_record(self, evidence_id: str) -> EvidenceReference | None:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload_json FROM evidence_records WHERE evidence_id = ?",
                (evidence_id,),
            ).fetchall()
        if len(rows) > 1:
            raise ConfigurationError("evidence ID is ambiguous across package revisions")
        return EvidenceReference.model_validate_json(rows[0][0]) if rows else None

    def list_evidence_artifact_paths(self, evidence_type: str) -> list[Path]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT DISTINCT content_artifacts.cas_path
                FROM evidence_records
                JOIN content_artifacts
                  ON content_artifacts.artifact_digest = evidence_records.artifact_digest
                WHERE evidence_records.evidence_type = ?
                ORDER BY content_artifacts.cas_path
                """,
                (evidence_type,),
            ).fetchall()
        return [Path(row[0]) for row in rows]

    def save_smoke_test_report(self, report: SmokeTestReport) -> None:
        payload = report.model_dump_json()
        with self._immediate_transaction() as connection:
            row = connection.execute(
                "SELECT payload_json FROM smoke_test_reports WHERE smoke_report_id = ?",
                (report.smoke_report_id,),
            ).fetchone()
            if row is not None and row[0] != payload:
                raise ConfigurationError("smoke report ID conflicts with prior content")
            connection.execute(
                """
                INSERT OR IGNORE INTO smoke_test_reports(
                    smoke_report_id, executor_id, route_fingerprint, status,
                    finished_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    report.smoke_report_id,
                    report.candidate_id,
                    report.route_fingerprint,
                    report.status.value,
                    report.finished_at.isoformat(),
                    payload,
                ),
            )

    def save_smoke_candidate_result(
        self,
        reports: tuple[SmokeTestReport, ...],
        snapshot: CandidateVerificationSnapshot,
        candidate: RouteCandidate,
    ) -> None:
        with self._immediate_transaction() as connection:
            for report in reports:
                payload = report.model_dump_json()
                row = connection.execute(
                    "SELECT payload_json FROM smoke_test_reports WHERE smoke_report_id = ?",
                    (report.smoke_report_id,),
                ).fetchone()
                if row is not None and row[0] != payload:
                    raise ConfigurationError("smoke report ID conflicts with prior content")
                connection.execute(
                    """
                    INSERT OR IGNORE INTO smoke_test_reports(
                        smoke_report_id, executor_id, route_fingerprint, status,
                        finished_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report.smoke_report_id,
                        report.candidate_id,
                        report.route_fingerprint,
                        report.status.value,
                        report.finished_at.isoformat(),
                        payload,
                    ),
                )
            snapshot_payload = snapshot.model_dump_json()
            connection.execute(
                """
                INSERT OR IGNORE INTO candidate_verification_snapshots(
                    snapshot_id, executor_id, package_digest, route_fingerprint,
                    created_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.snapshot_id,
                    snapshot.candidate_id,
                    snapshot.package_digest,
                    snapshot.route_fingerprint,
                    snapshot.created_at.isoformat(),
                    snapshot_payload,
                ),
            )
            connection.execute(
                """
                INSERT INTO route_candidates(
                    executor_id, source_id, fingerprint, status, package_digest,
                    package_fingerprint, verification_snapshot_id, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(executor_id) DO UPDATE SET
                    status = excluded.status,
                    fingerprint = excluded.fingerprint,
                    verification_snapshot_id = excluded.verification_snapshot_id,
                    payload_json = excluded.payload_json
                """,
                (
                    candidate.executor_id,
                    candidate.source_id,
                    candidate.behavior_fingerprint,
                    candidate.status.value,
                    candidate.package_digest,
                    candidate.package_fingerprint,
                    candidate.verification_snapshot_id,
                    candidate.model_dump_json(),
                ),
            )

    def latest_smoke_test_report(self, executor_id: str) -> SmokeTestReport | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT payload_json FROM smoke_test_reports
                WHERE executor_id = ? ORDER BY finished_at DESC, smoke_report_id DESC LIMIT 1
                """,
                (executor_id,),
            ).fetchone()
        return SmokeTestReport.model_validate_json(row[0]) if row else None

    def save_candidate_verification_snapshot(
        self,
        snapshot: CandidateVerificationSnapshot,
    ) -> None:
        payload = snapshot.model_dump_json()
        with self._immediate_transaction() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM candidate_verification_snapshots
                WHERE snapshot_id = ?
                """,
                (snapshot.snapshot_id,),
            ).fetchone()
            if row is not None and row[0] != payload:
                raise ConfigurationError("verification snapshot ID conflicts with prior content")
            connection.execute(
                """
                INSERT OR IGNORE INTO candidate_verification_snapshots(
                    snapshot_id, executor_id, package_digest, route_fingerprint,
                    created_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.snapshot_id,
                    snapshot.candidate_id,
                    snapshot.package_digest,
                    snapshot.route_fingerprint,
                    snapshot.created_at.isoformat(),
                    payload,
                ),
            )

    def get_candidate_verification_snapshot(
        self,
        snapshot_id: str,
    ) -> CandidateVerificationSnapshot | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT payload_json FROM candidate_verification_snapshots
                WHERE snapshot_id = ?
                """,
                (snapshot_id,),
            ).fetchone()
        return CandidateVerificationSnapshot.model_validate_json(row[0]) if row else None

    def save_route_candidate(self, candidate: RouteCandidate) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO route_candidates
                    (executor_id, source_id, fingerprint, status, package_digest,
                     package_fingerprint, verification_snapshot_id, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(executor_id) DO UPDATE SET
                    source_id = excluded.source_id,
                    fingerprint = excluded.fingerprint,
                    status = excluded.status,
                    package_digest = excluded.package_digest,
                    package_fingerprint = excluded.package_fingerprint,
                    verification_snapshot_id = excluded.verification_snapshot_id,
                    payload_json = excluded.payload_json
                """,
                (
                    candidate.executor_id,
                    candidate.source_id,
                    candidate.behavior_fingerprint,
                    candidate.status.value,
                    candidate.package_digest,
                    candidate.package_fingerprint,
                    candidate.verification_snapshot_id,
                    candidate.model_dump_json(),
                ),
            )

    def get_route_candidate(self, executor_id: str) -> RouteCandidate | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM route_candidates WHERE executor_id = ?",
                (executor_id,),
            ).fetchone()
        return RouteCandidate.model_validate_json(row[0]) if row else None

    def list_route_candidates(self) -> list[RouteCandidate]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload_json FROM route_candidates ORDER BY executor_id"
            ).fetchall()
        return [RouteCandidate.model_validate_json(row[0]) for row in rows]

    def save_qualification_report(self, report: QualificationReport) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO qualification_reports
                    (report_id, candidate_id, fingerprint, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    report.report_id,
                    report.candidate_id,
                    report.behavior_fingerprint,
                    report.model_dump_json(),
                ),
            )

    def get_qualification_report(self, report_id: str) -> QualificationReport | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM qualification_reports WHERE report_id = ?",
                (report_id,),
            ).fetchone()
        return QualificationReport.model_validate_json(row[0]) if row else None

    def save_rate_card_snapshot(self, snapshot: RateCardSnapshot) -> None:
        if snapshot.snapshot_id is None:  # pragma: no cover - model validator derives it
            raise ConfigurationError("rate-card snapshot has no digest")
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT payload_json FROM rate_card_snapshots WHERE snapshot_id = ?",
                (snapshot.snapshot_id,),
            ).fetchone()
            payload = snapshot.model_dump_json()
            if row is not None and row[0] != payload:
                raise ConfigurationError("immutable rate-card snapshot digest collision")
            self._connection.execute(
                "INSERT OR IGNORE INTO rate_card_snapshots (snapshot_id, payload_json) VALUES (?, ?)",
                (snapshot.snapshot_id, payload),
            )

    def get_rate_card_snapshot(self, snapshot_id: str) -> RateCardSnapshot | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM rate_card_snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
        return RateCardSnapshot.model_validate_json(row[0]) if row else None

    def save_workflow_checkpoint(
        self,
        *,
        workflow_id: str,
        workflow_hash: str,
        status: str,
        waiting_step_id: str | None = None,
        waiting_decision_id: str | None = None,
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO workflow_checkpoints
                    (workflow_id, workflow_hash, status, waiting_step_id, waiting_decision_id)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(workflow_id) DO UPDATE SET
                    workflow_hash = excluded.workflow_hash,
                    status = excluded.status,
                    waiting_step_id = excluded.waiting_step_id,
                    waiting_decision_id = excluded.waiting_decision_id
                """,
                (workflow_id, workflow_hash, status, waiting_step_id, waiting_decision_id),
            )

    def get_workflow_checkpoint(self, workflow_id: str) -> dict[str, str | None] | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT workflow_hash, status, waiting_step_id, waiting_decision_id
                FROM workflow_checkpoints WHERE workflow_id = ?
                """,
                (workflow_id,),
            ).fetchone()
        return dict(row) if row else None

    def claim_idempotency(self, key: str, request_hash: str) -> dict[str, object] | None:
        """Claim a key atomically; return its existing record on duplicate."""

        # ponytail: pending records fail closed after a crash; add expiring leases
        # when multi-process recovery is required.

        try:
            with self._lock, self._connection:
                self._connection.execute(
                    """
                    INSERT INTO idempotency_records (idempotency_key, request_hash, state)
                    VALUES (?, ?, 'claimed')
                    """,
                    (key, request_hash),
                )
            return None
        except sqlite3.IntegrityError:
            with self._lock:
                row = self._connection.execute(
                    """
                    SELECT request_hash, state, decision_id, status, receipt_ids_json
                    FROM idempotency_records WHERE idempotency_key = ?
                    """,
                    (key,),
                ).fetchone()
            if row is None:  # pragma: no cover - protected by the unique constraint
                raise ConfigurationError("idempotency record disappeared during lookup") from None
            if row["request_hash"] != request_hash:
                raise ConfigurationError(
                    f"idempotency key {key!r} was already used for a different action"
                ) from None
            return {
                "state": row["state"],
                "decision_id": row["decision_id"],
                "status": row["status"],
                "receipt_ids": json.loads(row["receipt_ids_json"]),
            }

    def complete_idempotency(
        self,
        key: str,
        *,
        decision_id: str,
        status: str,
        receipt_ids: list[str],
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE idempotency_records
                SET state = 'complete', decision_id = ?, status = ?, receipt_ids_json = ?
                WHERE idempotency_key = ? AND state IN ('claimed', 'executing')
                """,
                (decision_id, status, json.dumps(receipt_ids), key),
            )

    def abandon_idempotency(self, key: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM idempotency_records WHERE idempotency_key = ? AND state = 'claimed'",
                (key,),
            )

    def mark_idempotency_executing(self, key: str) -> None:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE idempotency_records SET state = 'executing'
                WHERE idempotency_key = ? AND state = 'claimed'
                """,
                (key,),
            )
            if cursor.rowcount != 1:
                raise ConfigurationError("idempotency claim is not executable")

    def mark_idempotency_indeterminate(self, key: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE idempotency_records SET state = 'indeterminate'
                WHERE idempotency_key = ? AND state = 'executing'
                """,
                (key,),
            )

    def save_quota_observation(self, observation: QuotaObservation) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO quota_observations
                    (observation_id, resource_id, observed_at, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    observation.observation_id,
                    observation.resource_id,
                    observation.observed_at.isoformat(),
                    observation.model_dump_json(exclude_computed_fields=True),
                ),
            )

    def latest_quota_observation(self, resource_id: str) -> QuotaObservation | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT payload_json FROM quota_observations
                WHERE resource_id = ? ORDER BY observed_at DESC LIMIT 1
                """,
                (resource_id,),
            ).fetchone()
        return QuotaObservation.model_validate_json(row[0]) if row else None

    def save_cache_affinity_observation(
        self,
        observation: CacheAffinityObservation,
    ) -> None:
        payload = observation.model_dump_json()
        with self._immediate_transaction() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM cache_affinity_observations
                WHERE observation_id = ?
                """,
                (observation.observation_id,),
            ).fetchone()
            if row is not None and row[0] != payload:
                raise ConfigurationError("cache observation ID conflicts with prior content")
            connection.execute(
                """
                INSERT OR IGNORE INTO cache_affinity_observations(
                    observation_id, scope_key_hmac, route_id, observed_at, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    observation.observation_id,
                    observation.scope_key_hmac,
                    observation.route_id,
                    observation.observed_at.isoformat(),
                    payload,
                ),
            )

    def latest_cache_affinity_observation(
        self,
        scope_key_hmac: str,
        route_id: str,
    ) -> CacheAffinityObservation | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT payload_json FROM cache_affinity_observations
                WHERE scope_key_hmac = ? AND route_id = ?
                ORDER BY observed_at DESC, observation_id DESC LIMIT 1
                """,
                (scope_key_hmac, route_id),
            ).fetchone()
        return CacheAffinityObservation.model_validate_json(row[0]) if row else None

    def save_registry_candidate(self, candidate: RegistryCandidate) -> None:
        payload = candidate.model_dump_json()
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO registry_candidates(
                    registry_candidate_id, adapter_id, retrieved_at,
                    raw_metadata_digest, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(registry_candidate_id) DO UPDATE SET
                    adapter_id = excluded.adapter_id,
                    retrieved_at = excluded.retrieved_at,
                    raw_metadata_digest = excluded.raw_metadata_digest,
                    payload_json = excluded.payload_json
                """,
                (
                    candidate.registry_candidate_id,
                    candidate.adapter_id,
                    candidate.retrieved_at.isoformat(),
                    candidate.raw_metadata_digest,
                    payload,
                ),
            )

    def get_registry_candidate(self, candidate_id: str) -> RegistryCandidate | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT payload_json FROM registry_candidates
                WHERE registry_candidate_id = ?
                """,
                (candidate_id,),
            ).fetchone()
        return RegistryCandidate.model_validate_json(row[0]) if row else None

    def save_decision(self, decision: RouteDecision) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO decisions
                    (decision_id, action_id, capability, created_at, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    decision.decision_id,
                    decision.action.action_id,
                    decision.action.capability,
                    decision.created_at.isoformat(),
                    decision.model_dump_json(),
                ),
            )

    def save_receipt(self, receipt: ExecutionReceipt) -> None:
        payload = receipt.model_dump_json()
        with self._immediate_transaction() as connection:
            existing = connection.execute(
                "SELECT payload_json FROM receipts WHERE receipt_id = ?",
                (receipt.receipt_id,),
            ).fetchone()
            if existing is not None and existing["payload_json"] != payload:
                completed_action = connection.execute(
                    """
                    SELECT 1
                    FROM prepared_action_idempotency AS binding
                    JOIN idempotency_records AS action
                      ON action.idempotency_key = binding.idempotency_key
                    WHERE action.state = 'complete' AND action.receipt_ids_json = ?
                    LIMIT 1
                    """,
                    (json.dumps([receipt.receipt_id]),),
                ).fetchone()
                if completed_action is not None:
                    raise ConfigurationError(
                        "completed action receipt is immutable"
                    )
            connection.execute(
                """
                INSERT OR REPLACE INTO receipts
                    (receipt_id, decision_id, action_id, capability, executor_id,
                     status, started_at, ended_at, executor_fingerprint,
                     cohort_digest, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt.receipt_id,
                    receipt.decision_id,
                    receipt.action_id,
                    receipt.capability,
                    receipt.executor_id,
                    receipt.status.value,
                    receipt.started_at.isoformat(),
                    receipt.ended_at.isoformat(),
                    receipt.executor_fingerprint,
                    receipt.cohort_digest,
                    payload,
                ),
            )

    def save_external_receipt_once(self, receipt: ExecutionReceipt) -> None:
        """Atomically reserve and persist one external report per decision/route."""

        try:
            with self._lock, self._connection:
                self._connection.execute(
                    """
                    INSERT INTO external_reports (decision_id, executor_id, receipt_id)
                    VALUES (?, ?, ?)
                    """,
                    (receipt.decision_id, receipt.executor_id, receipt.receipt_id),
                )
                self._connection.execute(
                    """
                    INSERT INTO receipts
                        (receipt_id, decision_id, action_id, capability, executor_id,
                         status, started_at, ended_at, executor_fingerprint,
                         cohort_digest, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        receipt.receipt_id,
                        receipt.decision_id,
                        receipt.action_id,
                        receipt.capability,
                        receipt.executor_id,
                        receipt.status.value,
                        receipt.started_at.isoformat(),
                        receipt.ended_at.isoformat(),
                        receipt.executor_fingerprint,
                        receipt.cohort_digest,
                        receipt.model_dump_json(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ConfigurationError(
                f"an external outcome was already reported for decision "
                f"{receipt.decision_id!r} and executor {receipt.executor_id!r}"
            ) from exc

    def get_decision(self, decision_id: str) -> RouteDecision | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM decisions WHERE decision_id = ?", (decision_id,)
            ).fetchone()
        return RouteDecision.model_validate_json(row[0]) if row else None

    def get_receipt(self, receipt_id: str) -> ExecutionReceipt | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM receipts WHERE receipt_id = ?", (receipt_id,)
            ).fetchone()
        return ExecutionReceipt.model_validate_json(row[0]) if row else None

    def list_receipts(
        self,
        *,
        limit: int = 50,
        executor_id: str | None = None,
        capability: str | None = None,
        decision_id: str | None = None,
    ) -> list[ExecutionReceipt]:
        clauses: list[str] = []
        parameters: list[object] = []
        if executor_id:
            clauses.append("executor_id = ?")
            parameters.append(executor_id)
        if capability:
            clauses.append("capability = ?")
            parameters.append(capability)
        if decision_id:
            clauses.append("decision_id = ?")
            parameters.append(decision_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(max(1, min(limit, 10_000)))
        with self._lock:
            rows = self._connection.execute(
                f"SELECT payload_json FROM receipts {where} ORDER BY started_at DESC LIMIT ?",
                parameters,
            ).fetchall()
        return [ExecutionReceipt.model_validate_json(row[0]) for row in rows]

    def list_receipts_for_prepared(
        self,
        prepared_id: str,
        *,
        action_id: str,
        executor_id: str,
        attempt_id: str,
        charge_id: str,
        limit: int = 2,
    ) -> list[ExecutionReceipt]:
        """Return only local receipts with the complete prepared-attempt binding."""

        bounded_limit = max(1, min(limit, 100))
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT payload_json FROM receipts
                WHERE action_id = ? AND executor_id = ?
                ORDER BY started_at DESC
                """,
                (action_id, executor_id),
            ).fetchall()
        matches: list[ExecutionReceipt] = []
        for row in rows:
            receipt = ExecutionReceipt.model_validate_json(row["payload_json"])
            if (
                receipt.metadata.get("prepared_id") == prepared_id
                and receipt.metadata.get("attempt_id") == attempt_id
                and receipt.metadata.get("charge_id") == charge_id
            ):
                matches.append(receipt)
                if len(matches) == bounded_limit:
                    break
        return matches

    def list_receipts_for_prepared_action(
        self,
        prepared_id: str,
        *,
        action_id: str,
        executor_id: str,
        limit: int = 2,
    ) -> list[ExecutionReceipt]:
        """Return bounded receipts with a complete prepared-action binding."""

        bounded_limit = max(1, min(limit, 100))
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT payload_json FROM receipts
                WHERE action_id = ? AND executor_id = ?
                ORDER BY started_at DESC LIMIT 10000
                """,
                (action_id, executor_id),
            ).fetchall()
        matches: list[ExecutionReceipt] = []
        for row in rows:
            receipt = ExecutionReceipt.model_validate_json(row["payload_json"])
            if (
                receipt.metadata.get("prepared_id") == prepared_id
                and isinstance(receipt.metadata.get("attempt_id"), str)
                and receipt.metadata.get("attempt_id")
                and isinstance(receipt.metadata.get("charge_id"), str)
                and receipt.metadata.get("charge_id")
            ):
                matches.append(receipt)
                if len(matches) == bounded_limit:
                    break
        return matches

    def receipts_for_executor(
        self, executor_id: str, *, limit: int = 200
    ) -> list[ExecutionReceipt]:
        receipts = self.list_receipts(limit=limit, executor_id=executor_id)
        receipts.reverse()
        return receipts

    def receipts_for_cohort(
        self,
        executor_id: str,
        *,
        executor_fingerprint: str,
        cohort_digest: str,
        limit: int = 200,
    ) -> list[ExecutionReceipt]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT payload_json FROM receipts
                WHERE executor_id = ? AND executor_fingerprint = ? AND cohort_digest = ?
                ORDER BY started_at DESC LIMIT ?
                """,
                (
                    executor_id,
                    executor_fingerprint,
                    cohort_digest,
                    max(1, min(limit, 10_000)),
                ),
            ).fetchall()
        receipts = [ExecutionReceipt.model_validate_json(row[0]) for row in rows]
        receipts.reverse()
        return receipts

    def list_decisions(self, *, limit: int = 50) -> list[RouteDecision]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload_json FROM decisions ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 10_000)),),
            ).fetchall()
        return [RouteDecision.model_validate_json(row[0]) for row in rows]

    def save_quote(self, quote: Quote) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO quotes (quote_id, expires_at, payload_json) VALUES (?, ?, ?)",
                (quote.quote_id, quote.expires_at.isoformat(), quote.model_dump_json()),
            )

    def get_quote(self, quote_id: str) -> Quote | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM quotes WHERE quote_id = ?", (quote_id,)
            ).fetchone()
        return Quote.model_validate_json(row[0]) if row else None

    def save_quote_acceptance(self, acceptance: QuoteAcceptance) -> None:
        try:
            with self._lock, self._connection:
                self._connection.execute(
                    """
                    INSERT INTO quote_acceptances
                        (acceptance_id, quote_id, accepted_at, payload_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        acceptance.acceptance_id,
                        acceptance.quote_id,
                        acceptance.accepted_at.isoformat(),
                        acceptance.model_dump_json(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ConfigurationError(f"quote {acceptance.quote_id!r} was already accepted") from exc

    def save_payment_object(
        self, value: PaymentReservation | PaymentCapture | PaymentRefund
    ) -> None:
        object_id = (
            value.reservation_id
            if isinstance(value, PaymentReservation)
            else value.capture_id
            if isinstance(value, PaymentCapture)
            else value.refund_id
        )
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO payment_objects (object_id, object_type, payload_json) VALUES (?, ?, ?)",
                (object_id, type(value).__name__, value.model_dump_json()),
            )

    def get_payment_reservation(self, reservation_id: str) -> PaymentReservation | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM payment_objects WHERE object_id = ? AND object_type = ?",
                (reservation_id, "PaymentReservation"),
            ).fetchone()
        return PaymentReservation.model_validate_json(row[0]) if row else None

    def get_payment_capture(self, capture_id: str) -> PaymentCapture | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM payment_objects WHERE object_id = ? AND object_type = ?",
                (capture_id, "PaymentCapture"),
            ).fetchone()
        return PaymentCapture.model_validate_json(row[0]) if row else None

    def save_ledger_event(self, event: LedgerEvent) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO ledger_events (event_id, event_type, occurred_at, payload_json) VALUES (?, ?, ?, ?)",
                (
                    event.event_id,
                    event.event_type,
                    event.occurred_at.isoformat(),
                    event.model_dump_json(),
                ),
            )

    def list_ledger_events(self, *, limit: int = 10_000) -> list[LedgerEvent]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload_json FROM ledger_events ORDER BY occurred_at DESC LIMIT ?",
                (max(1, min(limit, 10_000)),),
            ).fetchall()
        return [LedgerEvent.model_validate_json(row[0]) for row in rows]

    def save_observation(self, observation: Observation) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO observations
                    (observation_id, provider_id, capability, observed_at,
                     executor_fingerprint, cohort_digest, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation.observation_id,
                    observation.provider_id,
                    observation.capability,
                    observation.observed_at.isoformat(),
                    observation.executor_fingerprint,
                    observation.cohort_digest,
                    observation.model_dump_json(),
                ),
            )

    def list_observations(
        self,
        *,
        provider_id: str | None = None,
        capability: str | None = None,
        limit: int = 10_000,
    ) -> list[Observation]:
        clauses: list[str] = []
        parameters: list[object] = []
        if provider_id is not None:
            clauses.append("provider_id = ?")
            parameters.append(provider_id)
        if capability is not None:
            clauses.append("capability = ?")
            parameters.append(capability)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(max(1, min(limit, 10_000)))
        with self._lock:
            rows = self._connection.execute(
                f"SELECT payload_json FROM observations {where} ORDER BY observed_at DESC LIMIT ?",
                parameters,
            ).fetchall()
        return [Observation.model_validate_json(row[0]) for row in rows]

    def save_capacity_observation(
        self, observation: CapacityObservation
    ) -> CapacityObservation:
        with self._immediate_transaction() as connection:
            row = connection.execute(
                "SELECT canonical_digest, payload_json FROM capacity_observations "
                "WHERE observation_id = ?",
                (observation.observation_id,),
            ).fetchone()
            if row is not None:
                if row["canonical_digest"] != observation.canonical_digest:
                    raise ConfigurationError("capacity observation ID was reused with different data")
                return CapacityObservation.model_validate_json(row["payload_json"])
            connection.execute(
                """
                INSERT INTO capacity_observations (
                    observation_id, resource_id, observed_at, canonical_digest, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    observation.observation_id,
                    observation.resource_id,
                    self._utc_text(observation.observed_at),
                    observation.canonical_digest,
                    observation.model_dump_json(exclude_computed_fields=True),
                ),
            )
        return observation

    def list_capacity_observations(
        self, *, resource_id: str | None = None, limit: int = 10_000
    ) -> list[CapacityObservation]:
        where = "WHERE resource_id = ?" if resource_id is not None else ""
        parameters: tuple[object, ...] = (resource_id,) if resource_id is not None else ()
        with self._lock:
            rows = self._connection.execute(
                f"SELECT payload_json FROM capacity_observations {where} "
                "ORDER BY observed_at DESC, rowid DESC LIMIT ?",
                (*parameters, max(1, min(limit, 10_000))),
            ).fetchall()
        return [CapacityObservation.model_validate_json(row["payload_json"]) for row in rows]

    def latest_capacity_observation(
        self, resource_id: str
    ) -> CapacityObservation | None:
        values = self.list_capacity_observations(resource_id=resource_id, limit=1)
        return values[0] if values else None

    @staticmethod
    def _capacity_reservation_from_row(row: sqlite3.Row) -> CapacityReservation:
        value = CapacityReservation.model_validate_json(row["payload_json"])
        return value.model_copy(
            update={
                "status": CapacityReservationStatus(row["state"]),
                "claim_token": row["claim_token"],
                "version": int(row["version"]),
                "updated_at": datetime.fromisoformat(row["updated_at"]),
            }
        )

    def reserve_capacity(
        self,
        reservation: CapacityReservation,
        *,
        known_available: Decimal | None,
        now: datetime | None = None,
    ) -> CapacityReservation:
        current_time = (now or datetime.now(UTC)).astimezone(UTC)
        if reservation.expires_at <= current_time:
            raise ConfigurationError("capacity reservation is already expired")
        available = Decimal(str(known_available)) if known_available is not None else None
        if available is not None and (not available.is_finite() or available < 0):
            raise ConfigurationError("known capacity must be finite and non-negative")
        if reservation.maximum_quantity and available is None:
            raise ConfigurationError("unknown capacity cannot be reserved")
        with self._immediate_transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM capacity_reservations WHERE idempotency_key = ?",
                (reservation.idempotency_key,),
            ).fetchone()
            if existing is not None:
                stored = self._capacity_reservation_from_row(existing)
                binding = (
                    stored.resource_id,
                    stored.execution_id,
                    stored.maximum_quantity,
                    stored.unit,
                    stored.expires_at,
                )
                requested = (
                    reservation.resource_id,
                    reservation.execution_id,
                    reservation.maximum_quantity,
                    reservation.unit,
                    reservation.expires_at,
                )
                if binding != requested:
                    raise ConfigurationError(
                        "capacity reservation idempotency key was reused with different data"
                    )
                return stored
            held_rows = connection.execute(
                """
                SELECT maximum_quantity FROM capacity_reservations
                WHERE resource_id = ? AND unit = ? AND state IN (?, ?)
                  AND expires_at > ?
                """,
                (
                    reservation.resource_id,
                    reservation.unit,
                    CapacityReservationStatus.RESERVED.value,
                    CapacityReservationStatus.CLAIMED.value,
                    self._utc_text(current_time),
                ),
            ).fetchall()
            held = sum((Decimal(row["maximum_quantity"]) for row in held_rows), Decimal(0))
            if available is not None and held + reservation.maximum_quantity > available:
                raise ConfigurationError("capacity reservation exceeds known available capacity")
            connection.execute(
                """
                INSERT INTO capacity_reservations (
                    reservation_id, resource_id, execution_id, maximum_quantity, unit,
                    expires_at, state, idempotency_key, claim_token, version,
                    created_at, updated_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reservation.reservation_id,
                    reservation.resource_id,
                    reservation.execution_id,
                    str(reservation.maximum_quantity),
                    reservation.unit,
                    self._utc_text(reservation.expires_at),
                    CapacityReservationStatus.RESERVED.value,
                    reservation.idempotency_key,
                    None,
                    0,
                    self._utc_text(reservation.created_at),
                    self._utc_text(reservation.updated_at),
                    reservation.model_dump_json(),
                ),
            )
        return reservation

    def get_capacity_reservation(
        self, reservation_id: str
    ) -> CapacityReservation | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM capacity_reservations WHERE reservation_id = ?",
                (reservation_id,),
            ).fetchone()
        return self._capacity_reservation_from_row(row) if row else None

    def list_capacity_reservations(
        self, *, resource_id: str | None = None, limit: int = 10_000
    ) -> list[CapacityReservation]:
        where = "WHERE resource_id = ?" if resource_id is not None else ""
        parameters: tuple[object, ...] = (resource_id,) if resource_id is not None else ()
        with self._lock:
            rows = self._connection.execute(
                f"SELECT * FROM capacity_reservations {where} "
                "ORDER BY created_at DESC LIMIT ?",
                (*parameters, max(1, min(limit, 10_000))),
            ).fetchall()
        return [self._capacity_reservation_from_row(row) for row in rows]

    def claim_capacity_reservation(
        self,
        reservation_id: str,
        *,
        claim_token: str,
        expected_version: int,
        now: datetime | None = None,
    ) -> CapacityReservation:
        current_time = (now or datetime.now(UTC)).astimezone(UTC)
        with self._immediate_transaction() as connection:
            row = connection.execute(
                "SELECT * FROM capacity_reservations WHERE reservation_id = ?",
                (reservation_id,),
            ).fetchone()
            if row is None:
                raise ConfigurationError("capacity reservation does not exist")
            stored = self._capacity_reservation_from_row(row)
            if stored.status is CapacityReservationStatus.CLAIMED:
                if stored.claim_token != claim_token:
                    raise ConfigurationError("capacity reservation is claimed by another worker")
                return stored
            if stored.expires_at <= current_time:
                connection.execute(
                    "UPDATE capacity_reservations SET state = ?, version = version + 1, "
                    "updated_at = ? WHERE reservation_id = ?",
                    (CapacityReservationStatus.EXPIRED.value, self._utc_text(current_time), reservation_id),
                )
                raise ConfigurationError("capacity reservation expired before claim")
            if stored.status is not CapacityReservationStatus.RESERVED:
                raise ConfigurationError(f"cannot claim {stored.status.value} capacity")
            cursor = connection.execute(
                """
                UPDATE capacity_reservations
                SET state = ?, claim_token = ?, version = version + 1, updated_at = ?
                WHERE reservation_id = ? AND version = ? AND state = ?
                """,
                (
                    CapacityReservationStatus.CLAIMED.value,
                    claim_token,
                    self._utc_text(current_time),
                    reservation_id,
                    expected_version,
                    CapacityReservationStatus.RESERVED.value,
                ),
            )
            if cursor.rowcount != 1:
                raise ConfigurationError("capacity reservation compare-and-set failed")
            claimed = connection.execute(
                "SELECT * FROM capacity_reservations WHERE reservation_id = ?",
                (reservation_id,),
            ).fetchone()
        return self._capacity_reservation_from_row(claimed)

    def release_capacity_reservation(
        self,
        reservation_id: str,
        *,
        expected_version: int,
        now: datetime | None = None,
    ) -> CapacityReservation:
        current_time = (now or datetime.now(UTC)).astimezone(UTC)
        with self._immediate_transaction() as connection:
            row = connection.execute(
                "SELECT * FROM capacity_reservations WHERE reservation_id = ?",
                (reservation_id,),
            ).fetchone()
            if row is None:
                raise ConfigurationError("capacity reservation does not exist")
            stored = self._capacity_reservation_from_row(row)
            if stored.status is CapacityReservationStatus.RELEASED:
                return stored
            if stored.status not in {
                CapacityReservationStatus.RESERVED,
                CapacityReservationStatus.CLAIMED,
            }:
                raise ConfigurationError(f"cannot release {stored.status.value} capacity")
            cursor = connection.execute(
                """
                UPDATE capacity_reservations
                SET state = ?, version = version + 1, updated_at = ?
                WHERE reservation_id = ? AND version = ? AND state = ?
                """,
                (
                    CapacityReservationStatus.RELEASED.value,
                    self._utc_text(current_time),
                    reservation_id,
                    expected_version,
                    stored.status.value,
                ),
            )
            if cursor.rowcount != 1:
                raise ConfigurationError("capacity reservation compare-and-set failed")
            released = connection.execute(
                "SELECT * FROM capacity_reservations WHERE reservation_id = ?",
                (reservation_id,),
            ).fetchone()
        return self._capacity_reservation_from_row(released)

    def save_capacity_authorization_evidence(
        self, evidence: CapacityAuthorizationEvidence
    ) -> CapacityAuthorizationEvidence:
        return self._save_immutable(
            table="capacity_authorization_evidence",
            identity={"evidence_id": evidence.evidence_id},
            indexed={
                "provider_id": evidence.provider_id,
                "resource_id": evidence.resource_id,
                "resource_fingerprint": evidence.resource_fingerprint,
                "expires_at": self._utc_text(evidence.expires_at),
            },
            value=evidence,
        )

    def save_execution_entitlement(
        self, entitlement: ExecutionEntitlement
    ) -> ExecutionEntitlement:
        with self._immediate_transaction() as connection:
            if entitlement.authorization_evidence_id:
                row = connection.execute(
                    "SELECT payload_json FROM capacity_authorization_evidence WHERE evidence_id = ?",
                    (entitlement.authorization_evidence_id,),
                ).fetchone()
                if row is None:
                    raise ConfigurationError("entitlement authorization evidence is missing")
                evidence = CapacityAuthorizationEvidence.model_validate_json(row["payload_json"])
                if (
                    evidence.resource_id != entitlement.backing_resource_id
                    or evidence.resource_fingerprint != entitlement.backing_resource_fingerprint
                    or evidence.issuer_principal_digest != entitlement.issuer_principal_digest
                    or evidence.expires_at < entitlement.expires_at
                ):
                    raise ConfigurationError("entitlement authorization evidence does not match")
            digest = entitlement.canonical_digest
            existing = connection.execute(
                "SELECT payload_digest, payload_json FROM execution_entitlements "
                "WHERE entitlement_id = ? OR nonce = ?",
                (entitlement.entitlement_id, entitlement.nonce),
            ).fetchone()
            if existing is not None:
                if existing["payload_digest"] != digest:
                    raise ConfigurationError("entitlement ID or nonce was reused with different data")
                return ExecutionEntitlement.model_validate_json(existing["payload_json"])
            connection.execute(
                """
                INSERT INTO execution_entitlements (
                    entitlement_id, resource_id, resource_fingerprint, nonce,
                    maximum_quantity, remaining_quantity, unit, expires_at, state,
                    version, authorization_evidence_id, payload_digest, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', 0, ?, ?, ?)
                """,
                (
                    entitlement.entitlement_id,
                    entitlement.backing_resource_id,
                    entitlement.backing_resource_fingerprint,
                    entitlement.nonce,
                    str(entitlement.maximum_quantity),
                    str(entitlement.maximum_quantity),
                    entitlement.unit,
                    self._utc_text(entitlement.expires_at),
                    entitlement.authorization_evidence_id,
                    digest,
                    entitlement.model_dump_json(exclude_computed_fields=True),
                ),
            )
        return entitlement

    def redeem_entitlement(
        self,
        entitlement_id: str,
        *,
        attempt_id: str,
        quantity: Decimal,
        now: datetime | None = None,
    ) -> EntitlementRedemptionReceipt:
        current_time = (now or datetime.now(UTC)).astimezone(UTC)
        requested = Decimal(str(quantity))
        if not requested.is_finite() or requested <= 0:
            raise ConfigurationError("redemption quantity must be finite and positive")
        with self._immediate_transaction() as connection:
            replay = connection.execute(
                "SELECT * FROM entitlement_redemptions WHERE attempt_id = ?",
                (attempt_id,),
            ).fetchone()
            if replay is not None:
                if replay["entitlement_id"] != entitlement_id or Decimal(
                    replay["quantity_consumed"]
                ) != requested:
                    raise ConfigurationError("redemption attempt was reused with different data")
                return EntitlementRedemptionReceipt.model_validate_json(replay["payload_json"])
            row = connection.execute(
                "SELECT * FROM execution_entitlements WHERE entitlement_id = ?",
                (entitlement_id,),
            ).fetchone()
            if row is None:
                raise ConfigurationError("execution entitlement does not exist")
            if datetime.fromisoformat(row["expires_at"]) <= current_time:
                connection.execute(
                    "UPDATE execution_entitlements SET state = 'expired', version = version + 1 "
                    "WHERE entitlement_id = ? AND state = 'active'",
                    (entitlement_id,),
                )
                raise ConfigurationError("execution entitlement is expired")
            if row["state"] != "active":
                raise ConfigurationError(f"execution entitlement is {row['state']}")
            remaining = Decimal(row["remaining_quantity"])
            if requested > remaining:
                raise ConfigurationError("redemption exceeds entitlement maximum")
            new_remaining = remaining - requested
            status = (
                EntitlementRedemptionStatus.CONSUMED
                if new_remaining == 0
                else EntitlementRedemptionStatus.PARTIAL
            )
            evidence_digest = capacity_digest(
                {
                    "entitlement_digest": row["payload_digest"],
                    "attempt_id": attempt_id,
                    "quantity": str(requested),
                    "remaining": str(new_remaining),
                }
            )
            redemption_id = self._payment_operation_result_id("redemption", attempt_id)
            receipt = EntitlementRedemptionReceipt(
                redemption_id=redemption_id,
                entitlement_id=entitlement_id,
                attempt_id=attempt_id,
                quantity_consumed=requested,
                remaining_quantity=new_remaining,
                status=status,
                evidence_digest=evidence_digest,
                timestamp=current_time,
            )
            connection.execute(
                """
                INSERT INTO entitlement_redemptions (
                    redemption_id, entitlement_id, attempt_id, quantity_consumed,
                    remaining_quantity, status, timestamp, payload_digest, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt.redemption_id,
                    entitlement_id,
                    attempt_id,
                    str(requested),
                    str(new_remaining),
                    status.value,
                    self._utc_text(current_time),
                    capacity_digest(receipt),
                    receipt.model_dump_json(),
                ),
            )
            connection.execute(
                """
                UPDATE execution_entitlements
                SET remaining_quantity = ?, state = ?, version = version + 1
                WHERE entitlement_id = ? AND version = ? AND state = 'active'
                """,
                (
                    str(new_remaining),
                    "consumed" if new_remaining == 0 else "active",
                    entitlement_id,
                    int(row["version"]),
                ),
            )
        return receipt

    def list_entitlement_redemptions(
        self, entitlement_id: str, *, limit: int = 10_000
    ) -> list[EntitlementRedemptionReceipt]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload_json FROM entitlement_redemptions "
                "WHERE entitlement_id = ? ORDER BY timestamp LIMIT ?",
                (entitlement_id, max(1, min(limit, 10_000))),
            ).fetchall()
        return [
            EntitlementRedemptionReceipt.model_validate_json(row["payload_json"])
            for row in rows
        ]

    def create_execution_attempt(self, attempt: ExecutionAttempt) -> ExecutionAttempt:
        payload = attempt.model_dump_json()
        with self._immediate_transaction() as connection:
            existing = connection.execute(
                "SELECT payload_json FROM execution_attempts WHERE attempt_id = ?",
                (attempt.attempt_id,),
            ).fetchone()
            if existing is not None:
                stored = ExecutionAttempt.model_validate_json(existing["payload_json"])
                immutable = (
                    "decision_id",
                    "prepared_id",
                    "action_digest",
                    "executor_id",
                    "executor_fingerprint",
                    "side_effect",
                    "idempotent",
                )
                if any(getattr(stored, field) != getattr(attempt, field) for field in immutable):
                    raise ConfigurationError(
                        "execution attempt ID was reused with different authority"
                    )
                return stored
            connection.execute(
                """
                INSERT INTO execution_attempts (
                    attempt_id, decision_id, prepared_id, action_digest, executor_id,
                    executor_fingerprint, state, owner_id, lease_expires_at,
                    heartbeat_at, version, updated_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt.attempt_id,
                    attempt.decision_id,
                    attempt.prepared_id,
                    attempt.action_digest,
                    attempt.executor_id,
                    attempt.executor_fingerprint,
                    attempt.state.value,
                    attempt.owner_id,
                    self._utc_text(attempt.lease_expires_at)
                    if attempt.lease_expires_at
                    else None,
                    self._utc_text(attempt.heartbeat_at) if attempt.heartbeat_at else None,
                    attempt.version,
                    self._utc_text(attempt.updated_at),
                    payload,
                ),
            )
        return attempt

    def get_execution_attempt(self, attempt_id: str) -> ExecutionAttempt | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM execution_attempts WHERE attempt_id = ?",
                (attempt_id,),
            ).fetchone()
        return ExecutionAttempt.model_validate_json(row["payload_json"]) if row else None

    def claim_execution_attempt(
        self,
        attempt_id: str,
        *,
        owner_id: str,
        claimed_at: datetime,
        lease_expires_at: datetime,
    ) -> ExecutionAttempt:
        if lease_expires_at <= claimed_at:
            raise ConfigurationError("execution-attempt lease must expire after claim")
        with self._immediate_transaction() as connection:
            row = connection.execute(
                "SELECT payload_json FROM execution_attempts WHERE attempt_id = ?",
                (attempt_id,),
            ).fetchone()
            if row is None:
                raise ConfigurationError("execution attempt does not exist")
            current = ExecutionAttempt.model_validate_json(row["payload_json"])
            if current.state is ExecutionAttemptState.CLAIMED and current.owner_id == owner_id:
                return current
            if current.state is not ExecutionAttemptState.CREATED or current.version != 0:
                raise ConfigurationError("execution attempt is already claimed")
            updated = ExecutionAttempt.model_validate(
                {
                    **current.model_dump(mode="python"),
                    "state": ExecutionAttemptState.CLAIMED,
                    "owner_id": owner_id,
                    "lease_expires_at": lease_expires_at,
                    "heartbeat_at": claimed_at,
                    "version": 1,
                    "updated_at": claimed_at,
                }
            )
            self._save_attempt_update_locked(connection, current, updated, reason="claimed")
        return updated

    def transition_execution_attempt(
        self,
        attempt_id: str,
        *,
        expected_state: ExecutionAttemptState,
        expected_version: int,
        target_state: ExecutionAttemptState,
        updated_at: datetime,
        reason: str | None = None,
        cash_reservation_ids: tuple[str, ...] | None = None,
        capacity_reservation_ids: tuple[str, ...] | None = None,
        invocation_start_digest: str | None = None,
        external_attempt_digest: str | None = None,
        external_thread_digest: str | None = None,
        external_turn_digest: str | None = None,
        terminal_receipt_ids: tuple[str, ...] | None = None,
    ) -> ExecutionAttempt:
        with self._immediate_transaction() as connection:
            row = connection.execute(
                "SELECT payload_json FROM execution_attempts WHERE attempt_id = ?",
                (attempt_id,),
            ).fetchone()
            if row is None:
                raise ConfigurationError("execution attempt does not exist")
            current = ExecutionAttempt.model_validate_json(row["payload_json"])
            if current.state is not expected_state or current.version != expected_version:
                raise ConfigurationError("execution-attempt compare-and-set failed")
            if not current.can_transition_to(target_state):
                raise ConfigurationError(
                    f"illegal execution-attempt transition: {current.state} -> {target_state}"
                )
            changes: dict[str, object] = {
                "state": target_state,
                "version": current.version + 1,
                "updated_at": updated_at,
                "heartbeat_at": updated_at,
            }
            optional = {
                "cash_reservation_ids": cash_reservation_ids,
                "capacity_reservation_ids": capacity_reservation_ids,
                "invocation_start_digest": invocation_start_digest,
                "external_attempt_digest": external_attempt_digest,
                "external_thread_digest": external_thread_digest,
                "external_turn_digest": external_turn_digest,
                "terminal_receipt_ids": terminal_receipt_ids,
            }
            changes.update({key: value for key, value in optional.items() if value is not None})
            if reason is not None:
                changes["recovery_reason"] = reason[:2000]
            updated = ExecutionAttempt.model_validate(
                {**current.model_dump(mode="python"), **changes}
            )
            self._save_attempt_update_locked(connection, current, updated, reason=reason)
        return updated

    def _save_attempt_update_locked(
        self,
        connection: sqlite3.Connection,
        current: ExecutionAttempt,
        updated: ExecutionAttempt,
        *,
        reason: str | None,
    ) -> None:
        cursor = connection.execute(
            """
            UPDATE execution_attempts
            SET state = ?, owner_id = ?, lease_expires_at = ?, heartbeat_at = ?,
                version = ?, updated_at = ?, payload_json = ?
            WHERE attempt_id = ? AND state = ? AND version = ?
            """,
            (
                updated.state.value,
                updated.owner_id,
                self._utc_text(updated.lease_expires_at) if updated.lease_expires_at else None,
                self._utc_text(updated.heartbeat_at) if updated.heartbeat_at else None,
                updated.version,
                self._utc_text(updated.updated_at),
                updated.model_dump_json(),
                current.attempt_id,
                current.state.value,
                current.version,
            ),
        )
        if cursor.rowcount != 1:
            raise ConfigurationError("execution-attempt compare-and-set failed")
        connection.execute(
            """
            INSERT INTO execution_attempt_transitions (
                transition_id, attempt_id, from_state, to_state, version, occurred_at, reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{current.attempt_id}:{updated.version}",
                current.attempt_id,
                current.state.value,
                updated.state.value,
                updated.version,
                self._utc_text(updated.updated_at),
                reason[:2000] if reason is not None else None,
            ),
        )

    def list_recoverable_execution_attempts(
        self, *, now: datetime, limit: int = 100
    ) -> list[ExecutionAttempt]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT payload_json FROM execution_attempts
                WHERE state IN ('CLAIMED', 'RESERVED', 'INVOKING', 'VALIDATING',
                                'SETTLING', 'INDETERMINATE')
                  AND lease_expires_at IS NOT NULL AND lease_expires_at <= ?
                ORDER BY updated_at, attempt_id LIMIT ?
                """,
                (self._utc_text(now), max(1, min(limit, 10_000))),
            ).fetchall()
        return [ExecutionAttempt.model_validate_json(row["payload_json"]) for row in rows]

    def execution_attempt_for_decision(self, decision_id: str) -> ExecutionAttempt | None:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload_json FROM execution_attempts WHERE decision_id = ? "
                "ORDER BY updated_at DESC, rowid DESC LIMIT 1",
                (decision_id,),
            ).fetchall()
        return ExecutionAttempt.model_validate_json(rows[0]["payload_json"]) if rows else None

    def execution_attempt_for_prepared(self, prepared_id: str) -> ExecutionAttempt | None:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload_json FROM execution_attempts WHERE prepared_id = ? "
                "ORDER BY updated_at DESC, rowid DESC LIMIT 1",
                (prepared_id,),
            ).fetchall()
        return ExecutionAttempt.model_validate_json(rows[0]["payload_json"]) if rows else None

    def save_receipts(self, receipts: Iterable[ExecutionReceipt]) -> None:
        for receipt in receipts:
            self.save_receipt(receipt)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> ReceiptStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
