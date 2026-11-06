# SkillRank native carrier and ordinary workflow binding

The pinned SkillRank core compiled offline for macOS ARM64. AEEP can now
prepare an ordinary workflow configuration with `evaluator: skillrank`
and an exact native scheduler definition. The new plan version binds one
fresh control and one fresh required-use treatment for the same case.
This is an engineering diagnostic. The existing ASE and managed plan
versions keep their earlier route semantics.

The coordinator sends opaque case and arm identifiers to SkillRank.
Existing AEEP workers and protected graders still own the trial results.
The child can read the two grade certificates and cannot modify them.
A reordered request, an unknown grade or a verdict that differs from the
canonical grade stops dispatch. The scheduler receipt and ledger exclude
nested trial intervals from the scheduler overhead charge.

## Build evidence

- [Native build review](execution-review.json) binds the retained Cargo
  lock, vendor tree, compiler, Apple SDK and first-party bridge.
- [Build receipt](build-receipt.json) and [ledger](operation-ledger.json)
  show one settled operation, 29.85 measured seconds and zero model turns.
- [Binary identity](result.json) pins the retained ARM64 executable.
- [Preflight](preflight.json) used a first-party compiler fixture and
  checked denied network bind and unrelated file reads. The original
  driver stopped before registering a grant because the receipt store
  requires a typed record. The original intent is preserved. The
  corrected review reached the first actual Cargo launch.

The [native sandbox check](runtime-boundary.json) verified read-only
certificates, denied unrelated reads, denied networking and denied child
execution. macOS needed read access to the root directory entry to start
its loader. The corrected policy keeps file contents outside the allowed
paths inaccessible.

The [actual native coordinator check](native-check-result.json) prepared a
v9 plan and ran the real pinned SkillRank process on two synthetic grade
certificates. Its one [scheduler operation](native-check-ledger.json)
settled and the recorded trial hashes match the grades. Later source
guards require a runtime containing only the bridge and accept the
protected container grader used by the managed workflow. Focused
first-party checks exercise both guards without replaying the native run.

The first-party protocol fixtures cover reversed order, missing child
completion and a forged verdict. The earlier
[Linux upstream check](../skillrank-callback-proof-20261105/README.md)
remains bound to its original artifacts. The live ordinary CLI diagnostic
still requires a current worker pair, a reviewed public case and bounded
model authority. Neither check establishes candidate or selection benefit.


## Current-source verification

All 13 [source and packaging checks](source-verification.json) passed on
`91cf3e9`. Both full runs passed 2,142 tests with 21 skips. The combined
coverage and both branch gates passed. The wheel and sdist are built.
The new wheel has a separate installed-runtime check pending.
