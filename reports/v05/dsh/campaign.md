# AEEP 0.5 DSH deterministic proof

- PASS — every-attempt-has-receipt: 19 receipt(s) for all attempts
- PASS — shared-evidence-smoke-bound: 11 shared trial(s), maximum two smoke executions
- PASS — deterministic-aeep-task-valid: 17/17
- PASS — no-auto-activation-or-side-effect: signed package ingest produced zero receipts and activation was explicit
- PASS — unqualified-cheap-route-blocked: the inert package route was unavailable before qualification and activation
- PASS — package-tamper-rejected: changing signed package metadata invalidated integrity
- PASS — safe-validation-fallback: static-vs-JS and malformed local output each fell back once to the valid model route
- PASS — route-order-deterministic: fixed-seed route permutation preserved 3 selections
- PASS — cache-affinity-soft-only: cold, warm, eviction, and compaction vectors passed with cold hard feasibility
- PASS — rate-card-revaluation-without-rerun: new pricing changed only derived API-equivalent value; correctness trials were unchanged

Synthetic token result

These fixture token counts test accounting and routing structure; they are not a claim about live DSH savings.
