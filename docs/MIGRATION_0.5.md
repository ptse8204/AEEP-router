# Migrating to AEEP 0.5

AEEP 0.5 adds signed provider packages, RFC 8785 signatures, portable evidence,
cache-affinity scoring, durable approvals, and SQLite schema version 5. Existing
manifest versions `0.1`, `0.15`, `0.2`, `0.3`, and `0.4` remain readable.

## Signature cutover

All newly issued 0.5 offers, quotes, usage statements, aggregates, evidence, and
package records use `rfc8785-jcs-v1`. The old `aeep-canonical-json-v1` profile is
historical-only immediately after upgrading:

- it may verify settled records and reporting history;
- it may settle/reconcile an attempt durably invoked before the cutover;
- it cannot authorize a new preparation, reservation, invocation, aggregate
  prior, evidence acceptance, or key rotation;
- an uninvoked legacy prepared decision is cancelled; an existing reservation
  is released through recovery.

Providers must reissue live offers, quotes, aggregates, and attestations. Run
`aeep economic doctor` to list legacy historical-only records.

## Database

Opening a schema-v3 database performs transactional v3→v4→v5 migrations.
Version 4 adds protocol-cutover, provider-package, content-artifact, evidence,
smoke, cache, registry, and approval tables, then records
`rfc8785_live_cutover_at`. Version 5 adds nullable immutable fingerprint/cohort
provenance to receipts and observations. Historical rows and payload digests
are not rewritten; unbound legacy rows remain reportable but do not affect live
routing.

## Provider packages

The attached design-only `aeep.dev/v0.4` package format was never released.
AEEP 0.5 accepts only `aeep.dev/v0.5`; convert and re-sign old design fixtures.
Legacy `ProviderDescriptor` import remains available and inert.
