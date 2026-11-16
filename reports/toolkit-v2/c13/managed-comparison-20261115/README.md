# Managed Codex comparison proposal

The operational ledger now accepts all 37 checks required for the
managed Codex workflow. The reviewed [v2 completion](stack-completion-v2.json)
has canonical digest
`81e3ebd64ad53518026bf7e8b1374cc564fbc4f768c0e255646fb38bbc117031`.
It binds the current source and 18 component records. The
[registration audit](operational-completion.json) confirms that the
previous ledger rows were preserved and selection of Waza still requires
its two checks. Live dispatch remains paused.

## Proposed GPT-6.1 Sol run

The exact [design](sol-comparison-design.json) has file SHA-256
`08613f4efd26fbf6ee10e6713acaf74adb7bafb8b8c721e00de8d526825ac0a6`.
It freezes a four-task development comparison with AEEP's existing
AssessmentService and BenchmarkRunner on managed Codex. Both arms use
GPT-6.1 Sol at medium reasoning. Baselines keep their ordinary task
tools. Treatments make one domain-relevant capability optional.

| Domain | Frozen tasks | Optional capability | Protected score |
| --- | --- | --- | --- |
| Document and data | SkillsBench Sales Pivot Analysis and Excel in PowerPoint | Retained Spreadsheets skill and runtime | Original verifier, including real pivot structure, formulas, untouched cells and presentation structure where applicable |
| Software engineering | Canopen 613 and Xsdata 1126 | LibCST 1.8.6 with the reviewed syntax-aware migration skill | Existing protected issue and preservation tests, including the explicitly authored Xsdata behavior guard |

Each case runs once per arm in a fresh worker. The order alternates
between baseline-first and treatment-first. The proposal binds the
public archive and historical protected-grade inputs for every task.
It also pins the retained worker parents, reviewed Sol client bytes,
local candidate artifacts, offline grader images, and stopped model
proxy. Candidate and control build outputs and fresh conformance must
be bound after preparation.

The primary result is each task's protected binary grade. The report
shows matched differences in scores, token categories and wall time,
plus failures, missing measurements, operation costs and receipt links.
It records observed candidate listing, retrieval and invocation where
evidence exists. All four tasks have prior exposure and serve as
development observations. The formal qualification, candidate-value
and AEEP-selection requirements retain their original thresholds and
independence rules.

## Limits and dispatch gates

The proposed ceiling is eight model-turn reservations, 640 operations
and 32,000 reserved seconds across readiness, grading, task execution
and reporting. Each model turn has a 300-second timeout. This ceiling
is based on a conservative allowance of 80 operations and 4,000
seconds per trial-equivalent. The executable review must derive its
actual upper reservation from the exact schedule and fit within that
ceiling. Cash authority is $0.

Only the four bound public task inputs and any license-cleared
candidate instructions may reach the existing Codex destination.
Protected tests and reference outputs stay with the network-denied
grader. Permission and fingerprint drift, a failed readiness check,
an unresolved relevant reservation, or a missed grade, telemetry,
accounting or cleanup check stops dispatch. A settled task failure
still counts as a task outcome. There are no automatic retries or
model substitutions. Keep the 50 GiB host reserve and preserve
existing Docker resources.

The onboarding grant expired before preparation. A final review
needs an expiry-only amendment retaining its original limits,
counters and charges. Before requesting live approval, bind the
actual candidate pairs, verify optional access and matched baselines,
validate the protected graders, and exercise success, failure and
interruption in the local driver. The final dispatch digest will
cover those results and the exact canonical plan. This design
authorizes zero provider calls.
