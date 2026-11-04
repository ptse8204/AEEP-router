# Export repository-family reports through the ordinary CLI

The managed adapter now accepts repository URLs and other task-family labels
without changing the existing identifier contract. It preserves valid identifiers,
encodes other labels one-to-one and includes the original labels in detailed
and readable reports. Canonical tasks, scores, receipts and analysis remain intact.

The earlier actual ASE task passed, but its URI label prevented ordinary report
normalization. Its read-only repaired report and original failure remain in the
[completed execution record](../integration-snapshot-correction-20261103/RESULTS.md).
No model task will be replayed to test this formatting correction.

Focused synthetic checks cover the ordinary CLI export without dispatch, unchanged
legacy identifiers, long/Unicode labels and collisions with existing hash-shaped
names. All thirteen source gates passed on
`e48eec5f3039cfdbb8dcf24145e1b8835b3b4057de4f21eb7bf598fa22948c74`:
2,054 tests/21 skips in both full runs,82.64% combined coverage,both branch gates,
schema checks and package build. See `verification/checks.json`. The initial
lint-only stop is retained in `verification-lint-stop`; no upstream call occurred.
No current-wheel installation or new upstream execution is authorized yet.
Comparative campaigns remain paused. The existing two-turn bundle is exhausted.


The exact tested source is retained in `source-snapshot.json`, including unrelated
CI edits preserved locally and excluded from this feature commit. The
[grouped next review](../skillrank-build-preparation-20261103/operation-review.json)
binds the corrected wheel,32 unchanged cached dependencies, current offline docs
and a separate pinned SkillRank runtime build. None has executed under that review.
Earlier actual evaluator results retain their original source and adapted-report
scope. The new report helper has not been installed or tested with another model.
