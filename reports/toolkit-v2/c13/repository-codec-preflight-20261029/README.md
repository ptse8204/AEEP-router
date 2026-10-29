# Reject incompatible patch formats before model work

The assessment service now checks that each standard managed-worker patch field
matches the encoding expected by every scheduled repository task. This prevents
the controller mistake that invalidated two cases in the completed development
comparison. It does not convert patches or change their graders.

Both budget preview and dispatch verification reject an incompatible definition
before reserving model work. Mixed plain/gzip tasks require matching separate
static worker profiles. Direct outputs and reviewed custom artifact fields retain
their existing contracts.

## Evidence

- [Actual archived definitions](actual-definition-regression.json): the failed
  21-case mixed definition is rejected; corrected 13-case plain and six-case gzip
  definitions are accepted. The actual invalid plan's budget preview is refused,
  with canonical grant counters unchanged.
- Eleven first-party regression tests cover matching formats, mismatches in either
  arm, mixed tasks, invalid truth, compatible unrelated paths and early refusal.
- [Integrated checks](validation/checks.json) and
  [source stability](validation/source-stability.json) record current completion.
  All 13 gates passed: 1786 tests/21 skips in each full run, 82% coverage, both
  branch gates, schemas, lint, policy, mypy and build. The source stayed unchanged.

This source is `5a4257e3dc4abab14fcb70cfdfd86542790cb82333c42f78c42bf5a590be613b`.
The completed [19-pair comparison](../repository-usefulness-pilot-20261029/comparison.html)
retains source `b09911a0`; its live evidence is not transferred to this change.
No additional models, workers, images or external source execution are needed
to test this definition guard. Exact bundle `88e5c1b9` was approved and completed
once: three installed checks and the 69-input cached offline docs check passed. Both private runtimes were
removed unchanged. See the [completion audit](completion-audit.json).

## Current artifact

The wheel is 1992312 bytes, SHA-256
`ee1fdba5f1f9479e0c205b9eae29adc71ae6416458ac407778221d6bbfa9fd75`.
The sdist is 2174456 bytes, SHA-256
`72b09cdbf3b2f8d57a484f4e3d89b2ab7070968eb4c71e5284ac9c52b8ffc127`.
These are local build artifacts, not published releases. The approved package
review passed three focused installed checks with the same 32 cached dependencies.
The earlier 20-check CLI journey and model studies were not repeated.

## Completed local handoff

The [beta assessment](BETA_ASSESSMENT.md) separates implemented paths, executed
engineering checks, live development observations and unqualified claims. Current
source, installation and docs verification are complete within their recorded
scope. The docs scan precedes subsequent status prose; its input hashes remain.
No further execution or installation approval is pending for this increment.
C13 stays IN_PROGRESS for its unmet acceptance gates; no production release,
formal qualification or positive selection benefit is claimed.
