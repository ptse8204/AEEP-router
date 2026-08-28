# Migrating to AEEP 0.6

AEEP 0.6 keeps SQLite schema version 5 and all readable manifest versions. It
changes the default provider-package wire version to `aeep.dev/v0.6` and adds
estimate uncertainty, router abstention, signed provider discovery, conformance
checks, and isolated packaged Python execution.

## Provider packages

- Reissue provider packages as `aeep.dev/v0.6`.
- Add `authority_class` and an exact `aeep-evidence-cohort-v1` declaration to
  every evidence reference, then recompute the package digest and signature.
- Version 0.5 packages remain parseable. Evidence missing the new declarations
  is capped as a weak prior and cannot satisfy evidence-assisted qualification.
- Run `aeep provider conformance PATH` before publication.
- Optionally publish the signed `/.well-known/aeep-provider.json` discovery
  document. Consumers still establish trust locally.

Package-managed Python routes now execute through a bounded subprocess. Review
their timeout, environment, and optional POSIX limits; use a container or VM
when filesystem or network isolation is required.

## Routing and estimates

After five exact-cohort observations, `RouteEstimate.uncertainty` may contain
empirical p50/p95 resources, observed cash p95, and success/quality lower bounds.
These fields are evidence, not authorization.

Policies may configure a feasible baseline and an optimization-value threshold.
`RouteDecision.disposition` reports `SELECTED` or `BYPASS_ROUTER`; a bypass still
selects the feasible baseline and never restores a rejected route.

Cache affinity now records compaction generation and reusable-token/switch-cost
estimates. A generation mismatch forces the soft estimate cold. Hard feasibility
continues to use cold resources.

## Agent integrations

Use `aeep_estimate_route_prices` for local, non-binding price estimates.
`aeep_request_quotes` remains a deprecated alias and still performs no remote
quote request. The model-facing surface now contains ten operations.
