# Toolkit V2 status and recent grader results

November 20, 2026

**C13 is open. There is no approval pending from the operator.** The
approved Locify and EOS run finished under the temporary storage
exception. It exposed problems with two prospective benchmark cases.
The verified evaluation stack remains available for the private beta
scope described below.

## Why two cases have no grade

These checks try a known published repair and the buggy original before a
repository task enters a live comparison. The repair must pass the
required tests. The original must show the expected bug while the
preservation checks still pass. A valid 0/1 is a verified negative
result. An ungraded case still needs a usable verifier result.

| Case | What the run established | Grade |
| --- | --- | --- |
| Optype | The published repair passed all 416 required tests. The original passed 404 preservation tests and had the 12 expected issue tests absent. The reviewed checker accepted that original-source outcome. | Repair **1/1**, original **0/1** |
| Locify | The corrected launcher loaded successfully. Both reference tests returned errors in setup or teardown, and the original remains unstarted. A separate check in the same image reproduced a Git commit failure from missing author identity. The same check passed with a synthetic identity. | Ungraded |
| EOS | The environment ran the protected suite. The latest check matched 44 truncated test identifiers uniquely. The other 16 each matched two tests. Seven reference tests still failed, and the diagnostic saved none of their failure locations. | Ungraded |

The first Locify carrier put Pydantic in the task environment and left
it out of the Python process that starts the grader. The launcher now
loads. Both affected tests use fixtures that create a Git commit.
The separate Git check identifies a concrete setup fix to verify. The
protected run retained error statuses without the original exception,
so the exact cause of both protected errors still needs confirmation.

For EOS, the benchmark listing has incomplete parameterized test
identifiers. Selecting one of the 16 ambiguous matches by guesswork
would change the test set. Our diagnostic also failed to extract the
seven failure locations from pytest's text output. The next diagnostic
should capture the phase, exception category and location from pytest's
test reports. EOS can stay out of the eligible pool while that is
resolved.

All five operations in the group had a recorded finish and verified
worker cleanup. That accounting includes the failed Locify reference.
The group used no model calls or cash. [Receipt audit](rebench-storage-exception-result-20261119.json)
and [Optype evidence](optype-and-storage-20261119.json)

## What needs approval

I asked for too many approvals after using one-attempt reviews on
drivers that still had setup and reporting bugs. The completed group
and the temporary storage exception already have your approval.
Finding the cause, fixing the test harness, and verifying those fixes
locally are delegated C13 engineering work.

The completed group authorized zero automatic retries. A new protected
run needs applicable execution authority. Use the existing C13
delegation where it covers the run. Bring any work outside that scope
in one review after the driver passes its local checks. There is no
permission request for this handoff. [C13 delegation](c13-offline-approval-20261117.json)
and [execution boundaries](../../../../docs/aeep-toolkit/CONTINUATION.md)

## Where the project stands

| Deliverable | Status |
| --- | --- |
| Reusable evaluation stack | All **37 required checks** passed on the verified source with Waza excluded. Both document/data and software workflows reached protected grading and produced ordinary CLI reports. |
| New intake draft | **2,196 regression tests passed**, with 21 skipped. Documentation and package builds passed. Storage interrupted branch coverage before it produced a report, so the draft is still awaiting that check. |
| Candidate usefulness and AEEP selection | The last group prepared potential test cases for these separate studies. It supplied no candidate or selection result. Comparisons are paused while the formal workload and evidence requirements remain open. |
| Release | The recorded decision is **LIMITED_BETA** for private evaluation with the reviewed macOS ARM64 runtime. Production release and public benefit claims remain **NO_GO**. |

Locify and EOS are two options for expanding the benchmark pool. No
acceptance gate names either repository. Qualified cases with the
required workload coverage can fill those slots. The immediate goal
is to admit only cases whose tests reproduce, then measure candidate
usefulness and selection usefulness on independently assigned tasks.
[Stack readiness and release scope](README.md#retained-stack-and-lifecycle-evidence)
and [formal evaluation requirements](README.md#formal-candidate-and-selection-gates)
