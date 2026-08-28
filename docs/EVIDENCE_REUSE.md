# AEEP 0.6 portable evidence reuse

Evidence acceptance is metric-specific. It never activates a route and it is
never inserted as a local observation.

Version 0.6 evidence declares both an authority class and an exact portable
cohort. Version 0.5 evidence without those declarations is capped as a weak
prior and cannot qualify a route by itself.

| Metric | Reuse rule |
|---|---|
| Correctness/compatibility | Exact fingerprint/workload plus verified or attested evidence and a current local smoke |
| Tokens | Exact model, protocol, and accounting semantics |
| Actual cash | Historical fact only |
| API-equivalent cash | Recomputed from raw usage and the selected current rate card |
| Subscription use | Preserved as provider-local capacity, never API cash |
| Latency/CPU/memory/network | Environment-sensitive prior; local receipts dominate |
| Side effects/approval | Never imported |

Accepted priors blend into the existing estimator with their own sample count,
applicability, confidence, and source IDs. Local receipts then use the existing
history formula and increasingly dominate. A summary and the campaign behind it
are never counted twice. A live bounded quote remains authoritative for a
maximum cash authorization.

Local history is reused only within the exact `aeep-evidence-cohort-v1` bound
to the receipt at execution time. Route ID reuse, fingerprint drift, provider or
model changes, validator changes, cache-profile changes, and legacy rows without
a cohort binding cannot leak observations into a live estimate.

After five exact-cohort local observations, the estimator exposes empirical
p50/p95 resources and reliability/quality lower bounds. Observed cash p95 is
descriptive only; payment authorization still requires an immutable signed
quote, offer, or pinned-rate-card maximum.

Evidence-assisted qualification requires trusted exact correctness evidence and
one or two successful local smoke executions. Self-asserted evidence can be a
weak prior when policy permits, but cannot qualify by default.
Provider-self and distributor authority classes remain prior-only even when the
signing key is locally trusted; independent-lab, organization-admin, or local-
operator evidence may satisfy correctness gates under local trust policy.
