# AEEP 0.8 implementation evidence

Start with [plan coverage](plan-coverage.md) for the current state of the work.
Each report applies to its recorded source and execution environment. A later
successful check does not erase an earlier failure.

## Latest recorded results

- [Software validation](delivery-boundary-validation-5fffda8a3210-audit.json):
  1,160 tests passed, 15 skipped, and 21 native/software phases passed. The 12
  container checks failed while Docker was unresponsive. Full release readiness
  remains false.
- [Native workbook comparison](native-model-resource-evaluation-5fff-comparison.json):
  both routes completed two workbooks correctly. AEEP used less elapsed time and
  fewer reported tokens, with higher peak memory and CPU in this fixed-order pair.
  Required invocation and the small sample limit what this result establishes.
- [Resource acceptance](native-model-resource-evaluation-5fff-acceptance-interpretation.json):
  the declared workload passed its frozen numeric budgets. Unavailable telemetry
  stays unknown; the result does not qualify other workloads or backends.
- [Autonomy scenarios](native-sol61-autonomy-four-scenarios-5fff-canonical-audit.json):
  one verified completion and three safe stops, with two fixed-condition passes
  and two failures.
- [Lifecycle footprint](native-resource-lifecycle-profile-5fff-summary.json):
  idle, cold activation and interrupted-write recovery measurements.

Human comprehension remains unmeasured. Broader qualification and composed
boundary conformance remain separate requirements.

## Earlier evidence

`implementation-validation.json` records the earlier implementation checks and
unfinished work. `assessment-product.json` contains the separate assessment
verifier result. These files do not establish a completed 0.8 release.

`router-complete.json` and its Markdown companion verify the preserved legacy
router contract. That contract retains its 0.7 version and readiness flag. The
older reports under `reports/v07` remain unchanged.

Package hashes identify locally built artifacts. Earlier real-container isolation
and worker-crash checks retain their original source bindings and need fresh
results after code changes. `live-assessment.json` records the historical campaign
that reached Codex preflight but produced no model output because tool isolation
could not be verified. That run establishes no live economic benefit. The
upstream App Server support limitation recorded with it is separate from the
protocol fixtures; those fixtures cannot establish production support.

`selectable-structures-validation.json` records the subsequent selectable-structure
checks. Treat all earlier reports as evidence for their recorded revisions.
