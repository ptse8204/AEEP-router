# Migrating to AEEP 0.7

AEEP 0.7 preserves manifests, receipts, and SQLite databases from 0.1 through
0.6. Regenerate a manifest only when adopting new managed-host or capacity
features.

## Existing manifests

- Existing executor kinds keep their behavior. In particular, `host` remains a
  delegated selection completed by one external outcome report.
- Existing subscription resources load as `transferability: self_only` and
  `settlement_mode: subscription_usage`.
- Raw `subscription_units`, token dimensions, quota observations, receipts, and
  accounting records are not rewritten or converted.
- Imported providers remain inert until local qualification and activation.

## New managed-host routes

Use `host_managed` only for a locally reviewed adapter. Configure the executable
as argv, exact capability and schemas, resource pool, model/reasoning constraints,
working-directory and sandbox policy, approval ceiling, limits, and persistence
policy. Provider packages cannot create authority for these routes.

The Codex adapter uses the official App Server and runtime model discovery.
Continue managing authentication in Codex. AEEP does not accept copied API keys,
cookies, or authentication files as migration input.

## Capacity and x402

Capacity reservations are distinct from cash reservations. External entitlements
require a resource more permissive than `SELF_ONLY` plus provider authorization
evidence. x402 compatibility is local and disabled by default; migration enables
no network, wallet, payment, or marketplace behavior.

## Rollback and mixed versions

Schema migrations are additive and transactional. Back up the SQLite file before
opening it with 0.7. A 0.6 binary can still read its historical tables but will
ignore new 0.7 tables and executor kinds; use 0.7 for any database containing
active managed-host attempts or capacity reservations.

SQLite schema version 6 adds capacity observations, reservations, authorization
evidence, execution entitlements, and redemption receipts. Existing rows and
tables are not rewritten.
