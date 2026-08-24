# AEEP 0.5 portable evidence reuse

Evidence acceptance is metric-specific. It never activates a route and it is
never inserted as a local observation.

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

Evidence-assisted qualification requires trusted exact correctness evidence and
one or two successful local smoke executions. Self-asserted evidence can be a
weak prior when policy permits, but cannot qualify by default.
