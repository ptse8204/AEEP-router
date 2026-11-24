# Toolkit V2 status and recent grader results

November 24, 2026

**The current stack passed all 37 required checks across 18 components
with Waza excluded.** The current wheel passed private installation,
reapply and removal on macOS ARM64 and the reviewed Linux ARM64 carrier.
C13 remains open for comparative evidence.

## What passed on the current build

- **Stack readiness.** The ordinary CLI accepted all 37 checks in a private
  ledger copy on commit `943016e0`. Sales Pivot and Spring Boot still bind
  their original protected scores, settled charges, reports and verified
  telemetry. Both asset-use reviews passed on the current source. The old
  source binding, an unreviewed completion and a request selecting Waza
  were rejected. The operational ledger was left intact.
- **Essentials installation.** The same wheel installed using 32 unchanged
  dependency wheels for each platform. Immediate reapply preserved the
  install journal. Candidate inspection stayed inert, both report hashes
  matched, and removal preserved the neighboring file. macOS passed
  seven phases in 8.16 seconds. The pinned Linux ARM64 container finished
  in 14.96 seconds and was removed after its receipt settled.
- **Release scope.** Private beta remains limited to the reviewed macOS
  runtime. The Linux result covers the tested carrier and Python 3.13.15.
  These checks consumed zero model turns and zero cash.

[Current stack and installation evidence](current-intake-readiness-20261124.json)

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
| Reusable evaluation stack | **37/37** on the current source with Waza excluded. Both ordinary CLI workflows retain protected grading, telemetry and reports. |
| Private installation | The current wheel passed on macOS ARM64 and in the pinned Linux ARM64 carrier. |
| Repository and document intake | The feature branch includes reviewed source-file additions, longer publisher statements, and reviewed supplemental document sources. **2,196 tests passed**, with 21 skipped, **81.55% coverage**, and both branch-coverage checks passed. |
| Candidate usefulness and AEEP selection | The last group prepared potential test cases for these separate studies. It supplied no candidate or selection result. Comparisons are paused while the formal workload and evidence requirements remain open. |
| Release | The recorded decision is **LIMITED_BETA** for private evaluation with the reviewed macOS ARM64 runtime. Production release and public benefit claims remain **NO_GO**. |

The coverage run finished with at least 39.19 GiB free. The earlier runs
exposed an installer test fixture that used actual free space and a
verification flag that blocked the test suite's local HTTP servers. The
fixture now supplies its own capacity reading, and the full run used
the normal test configuration. All 414 tracked code and test files
matched the tested copy. [Source verification](intake-source-verification-20261120.json)

## USDA document grading

The ordinary CLI staged the USDA WASDE task as a reviewed document pack.
The worker ZIP contains the PDF, instruction and output schema. The
reference answer and verifier stayed in the separate protected directory.

| Protected check | Result |
| --- | --- |
| Exact extraction | 1/1 |
| One row missing | 0/1 |
| Invalid JSON | 0/1 |

All four operations settled offline, including the reference command.
The result verifies one local grader. The task still needs a case-specific
asset-use review before provider dispatch or formal assignment.
[USDA publisher listing](https://esmis.nal.usda.gov/publication/world-agricultural-supply-and-demand-estimates)
and [protected calibration evidence](wasde-reviewed-pack-result-20261124.json)

## Cohort batch results

| Case | Protected result |
| --- | --- |
| Param configuration API | The repair scored 1/1 across 29 required tests. The original scored 0/1 with the expected issue failure and 28 passes. |
| Django Bird component props | The repair scored 1/1 across 74 native tests. The original scored 0/1 with one issue failure and 73 preservation passes. The publisher's added test row identified the issue among five matches for its truncated name. |
| Census September retail sales | Twelve output rows matched the source PDF and workbook. The exact extraction scored 1/1. Missing data and invalid JSON scored 0/1. |
| BEA third-quarter GDP | Five rows matched the PDF and publisher release narrative. The exact extraction scored 1/1. Missing data and invalid JSON scored 0/1. |
| Treasury October receipts and outlays | Eight rows matched the PDF and the Fiscal Data API. The exact extraction scored 1/1. Missing data and invalid JSON scored 0/1. |

The software inventory gained two newly verified pairs and reconciled
three already settled pairs for Optype, Locify and adapted EOS. The
documents passed the local binary extraction rubric. They still need
case-specific asset-use review and a common cohort grading contract.
[Federal retail archive](https://www.census.gov/retail/marts/historic_releases.html)
· [BEA release](https://www.bea.gov/news/2026/gdp-advance-estimate-3rd-quarter-2026)
· [Treasury statement and data](https://fiscaldata.treasury.gov/datasets/monthly-treasury-statement/)

PyPA Build remains ungraded. The retained offline backend reduced the
reference failures from five to two. Passing the same reviewed source
and dependency paths to the test subprocesses cleared one more failure.
An earlier attempt at that adapter change stopped before pytest because
it referenced an unavailable import. That attempt remains recorded.
All 69 assertions stayed in scope. The final diagnostic found one
remaining failure, `test_build_with_dep_on_console_script[False]`.
The test raised `IndexError` at line 519 while reading the expected
console-script output. The grader keeps its non-executable scratch
boundary. The original-source check has yet to run.
[Batch receipts and diagnosis](cohort-batch-20261124.json)

## What still blocks formal comparisons

| Workload | Remaining gap |
| --- | --- |
| Software | The audited pool contains 59 reproduced cases across 38 repositories. Two independent holdouts and shared early stages require at least 246 distinct cases. That leaves a minimum gap of 187 against this pool. Contract audits have the largest holdout gap, at 56 cases before early-stage needs. |
| Document/data | The 18 annual disclosures remain held on source and asset-use grounds. The remaining ExtractBench metadata has 108 multiple-collection slots at stored ZIP size, or at most 113 if compression is favorable. The design needs 122. If Census, BEA, Treasury and WASDE all qualify under the same cohort contract, the remaining gap is 10 at stored ZIP size or five with favorable compression. |

Live comparisons remain paused. Candidate benefit and selection benefit
each need a separate result on frozen eligible tasks. Finishing the
stack or approving more runs cannot fill either workload gap.
[Corpus audit](recovery-67a93f4c-result-20261119.json)
and [document rights review](extractbench-disclosure-source-review-20261119.json)
[Stack readiness and release scope](README.md#retained-stack-and-lifecycle-evidence)
and [formal evaluation requirements](README.md#formal-candidate-and-selection-gates)
