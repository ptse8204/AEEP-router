# Toolkit V2 status and recent grader results

November 20, 2026

**Locify now has verified grades. EOS remains outside the benchmark pool.**
C13 is open. There is no approval pending from the operator.

<a id="why-two-cases-have-no-grade"></a>

## What the protected grader found

These checks try a known published repair and the buggy original before a
repository task enters a live comparison. The repair must pass the
required tests. The original must show the expected bug while the
preservation checks still pass. A valid 0/1 is a verified negative
result. An ungraded case still needs a usable verifier result.

| Case | What the run established | Grade |
| --- | --- | --- |
| Optype | The published repair passed all 416 required tests. The original passed 404 preservation tests and had the 12 expected issue tests absent. The reviewed checker accepted that original-source outcome. | Repair **1/1**, original **0/1** |
| Locify | The published repair passed both required tests after the runner supplied a synthetic Git author. The original reproduced the expected failure and passed the preservation test. | Repair **1/1**, original **0/1** |
| EOS | The reference still has seven failures. Of 60 truncated test identifiers, 44 map uniquely and 16 each match two tests. | Ungraded |

The earlier Locify attempts stopped on a missing launcher dependency and
then on test fixture errors. The corrected run used the retained image
and the same protected tests. It supplied an identity only inside the
worker so the fixtures could make their commits.

| Locify test | Published repair | Original |
| --- | --- | --- |
| Rank repository symbols with references | Pass | Expected failure with `AttributeError` |
| Rank repository symbols without references | Pass | Pass |

The EOS diagnostic captured four `AttributeError` failures in simulation
and optimization, one `ModuleNotFoundError` in OpenAPI documentation, and
two `ConnectionError` failures in electricity-price tests. It identified
the tests and exception categories. Their exact failure lines remain
unavailable. Confirming the intended test identities and reproducing
the reference are still required before EOS can supply a score.

The three operations finished and their receipts reconcile with the
saved test observations. Worker cleanup was verified. No models or
paid services were used. [Latest receipt audit](grader-repair-result-20261120.json),
[earlier attempts](rebench-storage-exception-result-20261119.json), and
[Optype evidence](optype-and-storage-20261119.json)

## What needs approval

I asked for too many approvals after using one-attempt reviews on
drivers that still had setup and reporting bugs. The completed group
and the temporary storage exception already have your approval.
Finding the cause, fixing the test harness, and verifying those fixes
locally are delegated C13 engineering work.

The latest correction used the existing C13 delegation and the operator's
direction to continue at the available space. Its storage cap was
768 MiB of additional host use for the three retained-image calls.
A scope expansion would need one review after the driver passes its
local checks. [C13 delegation](c13-offline-approval-20261117.json) and
[execution boundaries](../../../../docs/aeep-toolkit/CONTINUATION.md)

## Where the project stands

| Deliverable | Status |
| --- | --- |
| Reusable evaluation stack | All **37 required checks** passed on the verified source with Waza excluded. Both document/data and software workflows reached protected grading and produced ordinary CLI reports. |
| New intake draft | **2,196 regression tests passed**, with 21 skipped. Documentation and package builds passed. The first branch coverage attempt stopped at the storage guard. A fresh coverage-only run is in progress. |
| Candidate usefulness and AEEP selection | The last group prepared potential test cases for these separate studies. It supplied no candidate or selection result. Comparisons are paused while the formal workload and evidence requirements remain open. |
| Release | The recorded decision is **LIMITED_BETA** for private evaluation with the reviewed macOS ARM64 runtime. Production release and public benefit claims remain **NO_GO**. |

Locify's protected pair can now support case intake. Formal assignment
still requires the corpus and exposure checks shared by other cases.
EOS can be replaced with a verified task that covers the same kind of
work. Candidate and selection usefulness need independently assigned
tasks and separate results.
[Stack readiness and release scope](README.md#retained-stack-and-lifecycle-evidence)
and [formal evaluation requirements](README.md#formal-candidate-and-selection-gates)
