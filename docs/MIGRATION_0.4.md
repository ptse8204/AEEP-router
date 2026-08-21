# Migrating to AEEP 0.4

AEEP 0.4 is additive for existing offline routing. It accepts manifests from
0.1, 0.15, 0.2, and 0.3, retains legacy quotes/receipts/payment objects, and
does not make `route()` contact an economic provider.

## Before upgrading

1. Stop all processes using the SQLite database.
2. Make a SQLite-consistent backup. Prefer the SQLite backup API/CLI; if copying
   files directly, copy the database and any `-wal`/`-shm` files together while
   no process is writing.
3. Save the current package version, manifest, trust-store file, and database
   path in the change record.
4. Install 0.4 in a staging environment and run the existing manifest/tests.

No external credentials are required. `cryptography` is now a core dependency
for Ed25519 verification.

## Database migration

Opening `ReceiptStore` performs a transactional SQLite `user_version` upgrade.
Internal database schema version `1` adds the 0.4 evidence tables:

- `provider_signing_keys`
- `capability_offers`
- `quote_requests_v2`
- `bounded_quotes`
- `quote_nonce_uses`
- `prepared_route_decisions`
- `prepared_route_transitions`
- `payment_reservations_v2`
- `usage_statements`
- `settlement_receipts`
- `refund_receipts_v2`
- `billing_reconciliations`
- `market_aggregates`
- `pricing_disputes`
- `economic_evidence_links`

The existing `idempotency_records` table is reused for durable payment-operation
claims. Internal version `2` adds the explicit `authorization_kind` and
`authorization_id` linkage, makes `quote_id` optional for reservations and
settlements authorized by a fixed signed offer or pinned rate card, and migrates
earlier quote-linked 0.4 development records as `SIGNED_QUOTE`. Internal version
`3` adds `prepared_action_idempotency`, which durably binds one prepared
decision to its claimed action idempotency key and action digest.

Legacy tables and rows are retained. The migration uses `BEGIN IMMEDIATE`,
rolls back on failure, checks every foreign-key relationship before commit, and
is idempotent when reopened. SQLite foreign-key enforcement is enabled during
normal operation. The version-2 table rebuild temporarily disables enforcement
before its transaction, runs `foreign_key_check` before committing, and restores
enforcement afterward. A database with a newer `user_version` is rejected rather
than guessed at.

Verify after staging startup:

```bash
sqlite3 .aeep/aeep.db 'PRAGMA integrity_check; PRAGMA foreign_key_check; PRAGMA user_version;'
aeep economic doctor --manifest aeep.yaml --json
```

The expected `user_version` is `3`; this is an internal storage version, not the
protocol `schema_version: "0.4"`.

## Manifest and configuration

Existing manifests may remain at their supported version. To author a current
manifest, use `version: "0.4"`. Economic networking remains off unless explicitly
enabled:

```yaml
economic_evidence:
  enabled: false
  settlement_currency: USD
  live_quotes:
    enabled: false
    top_k: 3
    per_provider_timeout_seconds: 2
    total_timeout_seconds: 4
    maximum_response_bytes: 262144
    maximum_clock_skew_seconds: 30
    maximum_quote_ttl_seconds: 600
  requirements:
    require_binding_quote_for_paid_routes: true
    allow_verified_static_offer: true
    allow_static_prior: false
    minimum_evidence_level: SIGNED_QUOTE
    quote_failure_policy: REQUIRE_BINDING_QUOTE
    pinned_rate_cards: {}
  market_aggregates:
    enabled: false
    maximum_age_seconds: 86400
    minimum_sample_size: 20
    minimum_settlement_verified_fraction: "0.80"
  network:
    allowed_quote_hosts: []
    allow_private_addresses: false
    allow_redirects: false
    trust_environment_proxy: false
  trust_store:
    path: ~/.config/aeep/provider-keys.json
  payment:
    adapter: free
```

Live quotes require a non-empty exact host allowlist. Redirects and environment
proxy trust are rejected for the live-quote path. Secrets remain environment or
secret-manager references, not ordinary manifest values.

Keep `settlement_currency: USD` in 0.4. Economic models carry explicit
three-letter currencies, but the enabled router rejects non-USD because the
existing hard-budget/history fields are USD-specific; no exchange-rate path is
provided.

## Behavioral compatibility

- `Router.route()` remains synchronous/offline and does not request quotes.
- Prepared networking uses the explicit async `prepare_route()` path.
- Legacy static `QuoteService`/quote objects remain readable. A static estimate
  is not upgraded to binding evidence.
- Every new nonzero maximum uses one explicit immutable basis:
  `SIGNED_QUOTE`, `PUBLISHED_OFFER`, or `PINNED_RATE_CARD`. Legacy 0.4
  quote-linked records are read as `SIGNED_QUOTE` with the same quote ID; this
  compatibility conversion never upgrades an anonymous prior. Pinned rate-card
  authorization also stores exact rate IDs and bounded meter quantities.
- Legacy payment adapters retain full-capture behavior; prepared execution uses
  the Decimal/currency-safe V2 settle path.
- Legacy `ResourceVector.monetary_usd` remains a compatibility mirror. New
  routing, reporting, reputation, and savings logic uses `ResourceAccounting`.
- Existing receipts remain readable. New economic evidence uses immutable 0.4
  records and does not redefine an old schema under the same version.
- Imported routes remain inactive until separately qualified and activated.

## Trust-store migration

HMAC keys can continue to verify legacy/local records but are not accepted as
cross-provider trust. Create or import an operator-reviewed Ed25519 public key
record with exact provider, versioned capabilities, quote hosts, validity
window, and revocation status. Never trust `/.well-known/aeep-keys.json` merely
because a remote service returned it; compare it through an authenticated
operator channel before adding it.

Protect the trust store as control-plane configuration. Its writer uses an
atomic replacement and restrictive file mode, but directory permissions,
backup, review, and deployment remain operator responsibilities.

## Rollback

There is no in-place downgrade migration. To return to 0.3, stop AEEP, archive
the upgraded database for investigation/audit, restore the pre-upgrade backup,
and restore the prior package/config. Do not open an upgraded database with an
older release and do not delete incomplete reservations to force a rollback.

Before switching versions after any paid invocation, resolve or explicitly
record all `RESERVED`, `INVOKING`, `AWAITING_USAGE`, `SETTLING`, and
`INDETERMINATE` decisions. Recovery must never re-execute the action.
