# Toolkit V2 status and recent grader results

November 20, 2026

**The adapted offline EOS grader now scores the published repair 1/1 and
the buggy original 0/1.**
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
| EOS | The published repair passed all 359 required native tests. The original failed the expected optimization test and passed all 358 preservation checks. | Adapted offline repair **1/1**, original **0/1** |

The earlier Locify attempts stopped on a missing launcher dependency and
then on test fixture errors. The corrected run used the retained image
and the same protected tests. It supplied an identity only inside the
worker so the fixtures could make their commits.

| Locify test | Published repair | Original |
| --- | --- | --- |
| Rank repository symbols with references | Pass | Expected failure with `AttributeError` |
| Rank repository symbols without references | Pass | Pass |

## What broke in EOS and what fixed it

| Tests | Failure | Repair verified |
| --- | --- | --- |
| Two energy simulations and optimization inputs 1 and 2 | Four `AttributeError` failures at `interpolator.py:28`. The saved SciPy object stores `grid`, while SciPy 1.18.1 reads `_grid`. | Reused the verified SciPy 1.14.1 wheel. All four tests passed. |
| OpenAPI Markdown | `ModuleNotFoundError: git` at `generate_openapi_md.py:8`. The runtime lacked the publisher's GitPython development dependency. | Added the pinned GitPython 3.1.44 and its verified dependencies. The document test passed. |
| Electricity-price cache and array resampling | Two `ConnectionError` failures at `elecpriceakkudoktor.py:112`. Both tests called the live price endpoint inside an offline worker. | Replayed the publisher's existing price sample for these two tests with a fixed date and checked request parameters. Both passed. |

The earlier diagnostic used a working-directory call that EOS mocks.
That dropped all seven locations. The corrected diagnostic uses the
repository path fixed at launch. The first repair run cleared five
tests and exposed a timezone assumption in the price replay. The next
run corrected the date calculation, passed all seven checks, and ran
both full roles.

The 16 names with two matches were all preservation tests. The grader
required both matches for each name to pass. The adapted suite kept the
original test assertions. The original failed at `visualize.py:455`
because the chart used the full hourly tariff list for a shorter
interval. The published repair slices the list from the start hour.
The grades apply to this documented offline adaptation.
[EOS receipt audit](eos-repaired-grader-result-20261120.json),
[Locify receipt audit](grader-repair-result-20261120.json), and
[Optype evidence](optype-and-storage-20261119.json)

## What a comparison would establish

Grader repair checks use a known fix and a known buggy version to make
sure the tests can tell them apart. The formal study tests a different
question. Does giving an already capable agent a skill improve its
results, and does AEEP choose better than a fixed policy with the same
options? That study fixes the workloads, scores, and decision rules
before execution and uses independent held-out tasks. The software
protocol requires eight qualification cases, 28 training cases, and
105 held-out cases for each formal study.
[Formal evaluation requirements](README.md#formal-candidate-and-selection-gates)

## What needs approval

I asked for too many approvals after using one-attempt reviews on
drivers that still had setup and reporting bugs. The completed group
and the temporary storage exception already have your approval.
Finding the cause, fixing the test harness, and verifying those fixes
locally are delegated C13 engineering work.

The EOS repair used the existing C13 delegation. It settled six
operations, including the five-of-seven attempt, with zero model turns
and zero cash. One local image layer carries the verified dependency
files. The test workers stayed offline. [C13 delegation](c13-offline-approval-20261117.json)
and [GitPython 3.1.44 publisher release](https://pypi.org/project/GitPython/3.1.44/)

## Where the project stands

| Deliverable | Status |
| --- | --- |
| Reusable evaluation stack | All **37 required checks** passed on the verified source with Waza excluded. Both document/data and software workflows reached protected grading and produced ordinary CLI reports. |
| Repository and document intake | The feature branch includes reviewed source-file additions, longer publisher statements, and reviewed supplemental document sources. **2,196 tests passed**, with 21 skipped, **81.55% coverage**, and both branch-coverage checks passed. |
| Candidate usefulness and AEEP selection | The last group prepared potential test cases for these separate studies. It supplied no candidate or selection result. Comparisons are paused while the formal workload and evidence requirements remain open. |
| Release | The recorded decision is **LIMITED_BETA** for private evaluation with the reviewed macOS ARM64 runtime. Production release and public benefit claims remain **NO_GO**. |

The coverage run finished with at least 39.19 GiB free. The earlier runs
exposed an installer test fixture that used actual free space and a
verification flag that blocked the test suite's local HTTP servers. The
fixture now supplies its own capacity reading, and the full run used
the normal test configuration. All 414 tracked code and test files
matched the tested copy. [Source verification](intake-source-verification-20261120.json)

Locify and adapted EOS have protected case evidence. Formal assignment
still requires the corpus, runtime, and exposure checks shared by
other cases. Candidate and selection usefulness need independent task
assignments and separate results.
[Stack readiness and release scope](README.md#retained-stack-and-lifecycle-evidence)
and [formal evaluation requirements](README.md#formal-candidate-and-selection-gates)
