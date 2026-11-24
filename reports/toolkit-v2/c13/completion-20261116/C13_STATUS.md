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
| A2A streaming error handling | The repair scored 1/1 with 39 passes. The original scored 0/1 with two expected failures and 37 passes. |
| A2A transport context manager | The repair scored 1/1 with seven passes. The original scored 0/1 with two expected failures and five passes. |
| Pyfakefs file-open behavior | The repair scored 1/1 on all 432 required tests. The original scored 0/1 with one expected failure and 431 passes. |
| PyGLS standard-I/O contract | The reference scored 1/1 with 87 passes. The original-source control scored 0/1 with five expected failures and 82 passes. |
| Census September retail sales | Twelve output rows matched the source PDF and workbook. The exact extraction scored 1/1. Missing data and invalid JSON scored 0/1. |
| BEA third-quarter GDP | Five rows matched the PDF and publisher release narrative. The exact extraction scored 1/1. Missing data and invalid JSON scored 0/1. |
| Treasury October receipts and outlays | Eight rows matched the PDF and the Fiscal Data API. The exact extraction scored 1/1. Missing data and invalid JSON scored 0/1. |
| EIA November petroleum and gas balances | Eight rows matched annual figures calculated from the publisher's monthly workbook. The exact extraction scored 1/1. Missing data and invalid JSON scored 0/1. |

The software inventory added six pairs on the current ordinary grader
and reconciled three already settled pairs for Optype, Locify and
adapted EOS. Both A2A pairs reused the pinned dependency files. A single
offline image build and four grader operations settled on a copy of the
original ledger. Its five historical operations and the original ledger
were preserved. The documents passed the local binary extraction rubric
and still need case-specific asset-use review and a common cohort
grading contract.

Pyfakefs's earlier reference stopped at the assertion that pytest's
metadata must exist on disk. The protected runtime now expands the same
pinned pytest wheel into private scratch for this case. Both roles
keep their original source, tests, dependencies, and payload hashes.
The diagnostic and two graded runs retain their own receipts.

PyGLS's two countdown fixtures account for 20 seconds of intentional
waiting. The old 22-second child limit expired during the second fixture.
A 55-second child limit let the unchanged suite finish. The first completed
reference exposed five truncated publisher labels. A collection-only
check recovered all 87 native identities and mapped the five labels
uniquely. Both protected roles then settled in about 27 seconds each.
The 52 GiB preflight review stopped before launch. The replacement used
the 50 GiB host reserve, the retained read-only image, and the same
64 MiB temporary filesystem. The earlier receipts and charges remain.

EIA's complete tables PDF fits the transport ceiling as a 3,379,714-byte
task ZIP. The workbook stays in the protected reference path. Housing
and wholesale release files returned HTTP 403 in the local intake and
remain outside the verified pool.

[Federal retail archive](https://www.census.gov/retail/marts/historic_releases.html)
· [BEA release](https://www.bea.gov/news/2026/gdp-advance-estimate-3rd-quarter-2026)
· [Treasury statement and data](https://fiscaldata.treasury.gov/datasets/monthly-treasury-statement/)
· [EIA tables](https://www.eia.gov/outlooks/steo/data.php)

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

Pyserde issue 657 joined the reproduced software pool. The published
repair passed all 12 required tests. The original failed the five
issue assertions and passed all seven preservation tests. The first
reference attempt hit a collection error because the test module
imports MsgPack, an optional dependency absent from the retained image.
A read-only projection of the publisher's MsgPack Python fallback
allowed the same tests to run. The retained reference receipt contained
all 12 passing statuses. I corrected the grader's reply formatting and
recovered the 1/1 reference grade from that receipt before running the
unstarted original, which scored 0/1. Both Pyserde revisions belong to
the same repository family and must stay in the same study stage.
[Protected pair and diagnostics](protected-cohort-followup-20261124.json)
· [MsgPack publisher package](https://pypi.org/project/msgpack/1.1.2/)

C++ linter hooks issue 142 stays outside the pool. Its published reference
passed 28 of 29 required tests. The remaining test mocked tool discovery
but reached the installer. The install path returned no executable, and
the assertion tried to convert that empty result into a path. The
protected run kept the assertion and isolation intact. The reference and
diagnostic settled without a grade, and the original was never dispatched.

SQLacodegen issue 391 passed all seven unchanged SQLite CLI tests on the
published repair. The original reproduced both issue failures and kept
all five preservation tests passing. A read-only launcher and locally
derived package metadata supplied the project's published entry points
without installing it. Keep all SQLacodegen revisions in one study stage.
[Protected pair and settled receipts](protected-cohort-expansion-20261124.json)

### Avro model generation

Two cases from the same repository passed protected grading on the
retained Linux grader with their original dependency locks.

| Case | Published repair | Buggy original |
| --- | --- | --- |
| 835, one-to-one relationships | **1/1**, all 44 tests passed | **0/1**, the relationship assertion failed at line 475. The other 43 tests passed. |
| 870, Python keywords in generated models | **1/1**, all 14 tests passed | **0/1**, the keyword assertion failed at line 137. The other 13 tests passed. |

All four operations settled in 10.50 seconds in total. Both worker
profiles used the retained image and checksum-verified publisher wheels
from read-only mounts. The two cases must stay in the same study stage.
[Grader results and receipts](protected-avroschema-batch-20261124.json)

### Confluence exporter configuration

The published repair scored **1/1** with all nine protected checks passing.
The original scored **0/1**. The upstream configuration-display test
failed, and the authored snapshot guard detected the original file.
The other seven tests passed. Both offline operations settled in
4.05 seconds total. The runtime reused the publisher's 36 locked wheels.
It excluded the JMESPath command wrapper and kept the matching tqdm
source license with the importable libraries. No package was installed.
[Protected CLI grades and receipts](protected-confluence-cli-20261124.json)

### Towncrier configuration fallback

The published repair scored **1/1** on all 17 checks. The original
scored **0/1** because the two expected pyproject configuration tests
and the authored snapshot guard failed. The other 14 checks passed.
Both operations settled in 3.48 seconds total. The import-only
dependency tree excluded interpreter startup hooks, and the protected
grader verified the expected native imports before testing.
[Protected grades and receipts](protected-towncrier-contract-20261124.json)

### Shared carrier batch

Skelebot's packaging repair scored **1/1** with all seven checks
passing. The original scored **0/1**. Its overwrite test and the
authored snapshot guard failed as expected, and five checks passed.
Collection first needed the project's version metadata. The startup
trace then located the remaining failure at the Artifactory client's
use of `pathlib._Flavour`, which Python 3.13 removed. The passing run
used the same image and unchanged tests with the compatible
`dohq-artifactory` 1.0.2 wheel and read-only project metadata.

AnyIO issue 935 remained ungraded after that batch. The offline startup probe loaded the
pinned dependencies and the grader's plugin from the protected snapshot.
Pytest still exited before emitting collection results. The original
was never dispatched. Eleven operations settled across the two cases,
including diagnostics, with zero model turns or cash.
[Batch receipts and per-test results](protected-retained-carrier-batch-20261124.json)

### AnyIO and SQLacodegen dialects

| Case | Protected result |
| --- | --- |
| AnyIO 935 | The repair scored **1/1** on all 30 required checks. The original scored **0/1** on the three expected RunVar failures. Ten additional checks ran, including one extra failure on the eager-loop variant of the original. |
| SQLacodegen 368 | The repair passed all 39 checks for **1/1**. The original failed only the expected PostgreSQL type assertion for **0/1**. The real PostgreSQL and MySQL drivers supported dialect compilation in the network-disabled carrier without database services. |
| SQLacodegen 371 and 375 | Both published repairs failed the preserved PostgreSQL type assertion. The original sources were never dispatched. Both cases remain outside the pool. |

The AnyIO fixture explicitly loads `pytest_mock`. Supplying that wheel
exposed a pytest assertion-rewrite warning from importing the case
plugin too early. The final run preserved the publisher's flags and used
its declared pytest entry point with read-only metadata. All eight
operations in this increment settled with zero model turns and cash.
[Protected results and ledgers](protected-anyio-and-dialect-batch-20261124.json)

### AnyIO task-group reference remains ungraded

The AnyIO 975 published snapshot passed 345 of 386 required checks.
Forty failures were on Trio, and one was the asyncio test that checks
an exception raised before a task reports it has started. Four skips
and four expected failures were outside the required set. The one
offline operation settled in 16.19 seconds. The original stayed
unstarted, so this case does not change the software pool.

The carrier reused Trio 0.30.0 from AnyIO 935. The newer snapshot
declares Trio 0.31 or later and calls `CancelScope.cancel(reason)`,
which Trio introduced in 0.31.0. The carrier should have checked
that requirement before it started the reference. The prepared
continuation changes that one dependency, preserves all assertions
and captures test failure categories and locations. The asyncio
failure remains unexplained. The replay requires approval and has
not started. [Run audit and exact continuation](protected-anyio-taskgroups-20261124.json)
· [Trio 0.31.0 release](https://github.com/python-trio/trio/releases/tag/v0.31.0)

### SQLacodegen 419 generated-code assertions

The published reference passed 21 of 64 required checks. Forty tests
failed at the shared exact generated-source assertion. Three more
failed at the exact output assertions for the declarative, dataclass
and SQLModel command-line generators. All required tests ran. The
grader retained each failing test and assertion location. The single
operation settled in 9.54 seconds, and the original remained
unstarted. This case has no verified grade.

The contained run used SQLAlchemy 2.0.41 within the snapshot's
declared range and SQLModel 0.0.24. It reused the pinned driver
packages and original CLI and generator tests. The CLI used local
SQLite, and the generator tests made no external database connections.
The source-output mismatch still needs diagnosis before any replay.
[Protected reference, accounting and dependency pins](protected-sqlacodegen-419-20261124.json)
· [SQLAlchemy 2.0.41](https://pypi.org/project/SQLAlchemy/2.0.41/)
· [SQLModel 0.0.24](https://pypi.org/project/sqlmodel/0.0.24/)

### Next scientific Python cases

**Nested Pandas joined the reproduced pool.** The reference passed all
56 required assertions. The original failed the reduction test and the
snapshot-preservation check as expected, passing the other 54. The two
offline operations settled in 6.44 seconds. The worker generated the
publisher's version file from the archive's verified tag and commit
before grading. The staged source still matches the publisher tree
after restoration of one Git-substituted metadata file.
[Intake and assertion bindings](scientific-python-source-intake-20261124.json)
· [Protected Nested Pandas pair](protected-nested-pandas-20261124.json)

**VirtualiZarr remains ungraded.** The first offline reference ran all
78 required assertions. Forty-four passed, 21 had setup errors, and
13 failed during execution. The failures were import errors from calls
to Xarray's tutorial datasets and the Kerchunk Parquet export. The
retained environment lacks Pooch and Fastparquet. The operation settled
in 3.88 seconds. The original stayed unstarted.

The case's three network-marked tests are outside the required set
and follow the publisher's default skip. Some required fixtures still
call `xarray.tutorial.open_dataset`. The two required data blobs,
`air_temperature.nc` and `ROMS_example.nc`, now have publisher tree
pins and byte counts. Their use review and offline cache setup come
before a protected replay. No tutorial dataset was downloaded.
NOAA documents the NCEP/NCAR data-use terms. The Xarray tutorial
identifies the ROMS subset, and the reviewed sources lack a use record
for those exact bytes. VirtualiZarr stays out of the pool while that
fixture is unresolved.

[VirtualiZarr fixture review](virtualizarr-fixture-use-review-20261124.json)
· [Protected VirtualiZarr result and diagnosis](protected-virtualizarr-20261124.json)
· [Xarray tutorial cache behavior](https://docs.xarray.dev/en/v2024.11.0/generated/xarray.tutorial.open_dataset.html)

### Parser and documentation batch

The protected grader verified two more software cases on the same
offline Linux ARM64 carrier.

| Case | Repaired source | Original source |
| --- | --- | --- |
| Pyformlang grammar concatenation | **1/1**, all 48 checks passed | **0/1**, 46 passed. The original reproduced the variable-naming bug and failed the snapshot guard. |
| pdoc table of contents | **1/1**, all 31 checks passed | **0/1**, 29 passed. Mixed Markdown headings produced the wrong table of contents, and the snapshot guard rejected it. |

Pyformlang used the Pydot 4.0.1 wheel with both notices from the same
published release. All seven wheel modules matched the source
distribution. The four grader calls settled in 7.69 seconds. They used
zero model turns and zero cash.

The published pdoc records truncate five autolink test names. The grader
ran all seven original parameter cases, including all three beginning
with the ambiguous `See` prefix. It kept the original test code and
binary grading. Exstruct and spec2nexus stopped during source acquisition
with a retained `ValueError` and no archive or grade.

[Pyformlang protected grades](protected-pyformlang-20261124.json)
· [pdoc protected grades](protected-pdoc-20261124.json)
· [Batch source and license evidence](parser-documentation-source-intake-20261124.json)
· [Pydot 4.0.1 release](https://pypi.org/project/pydot/4.0.1/)

## What still blocks formal comparisons

| Workload | Remaining gap |
| --- | --- |
| Software | The current inventory reconciles 75 reproduced cases, 49 repository families and 152 distinct protected receipts. The two holdouts and shared early stages need at least 246 distinct cases, leaving a minimum gap of 171. Contract audits have the largest holdout gap, at 49 cases before early-stage needs. |
| Document/data | The 246 VAREX archives now have a verified provisional allocation. It keeps the known related forms in one stage and excludes both calibration cases. Final source-lineage review, asset-use decisions and study assignment remain open. The 18 ExtractBench annual disclosures remain held on source and asset-use grounds. |

The software inventory records source revisions, task families and
receipt IDs for each reproduced case. Its audit rejects duplicate
cases, reused receipts and development-exposed repositories. Keep
all revisions from the same repository in one study stage.
[Current software inventory](software-inventory-with-parser-audits-20261124.json)

VAREX now has 133 multi-collection prospects with distinct schema hashes.
The audit matched all 1,777 schema IDs to exact publisher PDF paths. It
read 813,498 bytes of pinned Parquet ranges for document IDs, splits and
schemas. The largest of the 133 prospective PDFs is 2,402,382 bytes in
the publisher metadata. The protected check below exercised two of the
prospects. Distinct schema hashes leave template lineage and independent
stage assignment open.
[VAREX dataset revision](https://huggingface.co/datasets/ibm-research/VAREX/tree/ff36b6cd232efd401b3f4a20272a07bf2b749914)
· [VAREX evaluator revision](https://github.com/udibarzi/varex-bench/tree/3cce9c18530748cfc843f38c02e2f43e0694d167)

### VAREX protected grading

Two VAREX forms passed ordinary CLI staging. Both exact references scored
12/12 with the original evaluator and its published field exclusions.
Each archive contains the pinned PDF, schema and local instructions. The
reference answers and scorer stayed in the protected grader. The two PDF
downloads matched their complete publisher hashes. Three bounded reads
retrieved 136,972 bytes of reference columns from one pinned Parquet shard.
Only the two selected reference records were staged for grading.
[Data license](https://cdla.dev/permissive-2-0/)

| Case | Exact reference | Reordered collection | Missing row or entry | Missing or malformed output |
| --- | --- | --- | --- | --- |
| GSA 3418 | 12/12 | 11/12 | 11/12 | 0/12 each |
| HUD 11706 | 12/12 | 12/12 | 11/12 | 0/12 each |

The grader aligns HUD's rows as objects. GSA's collection contains
strings, which the scorer compares in their submitted order. My first
readback expected both rearrangements to score 12/12. The verified
receipt retained all ten observations, so the corrected readback
recovered the actual scores without rerunning either case. The run used
one offline container on the retained runtime and took 2.44 seconds from
reservation to settlement.
[Scores, source bindings and receipt](varex-calibration-20261124.json)

The full VAREX metadata screen found 131 other multiple-collection
prospects and 1,638 with at most one collection. The design needs
at least 122 multiple-collection cases. A VAREX-only document cohort
could retain one native normalized exact-match contract across both
holdouts. Source-family grouping, asset-use decisions, staged ZIPs
and protected grades still determine how many cases qualify. The two
calibration forms stay outside that prospective count.
[Full catalog capacity audit](varex-cohort-capacity-20261124.json)

All 131 candidate PDF bodies now match the pinned publisher objects.
The two acquisition paths verified 93 LFS SHA-256 digests and 38 Git
blob IDs, covering 54,191,882 bytes. A local first-page text screen found
eight groups of related forms. It flagged the published variants of
Standard Forms 1152, 1153 and 85PS, as well as several FDA, GSA and
California forms. One case lacked enough first-page text to screen.
Counting one case per flagged group would leave 120, two short of the
122-case minimum. The review still needs to distinguish distinct
workloads from alternate versions of the same form before cohort
assignment. No candidate PDFs from this batch went to a model or grader.
[Verified PDF inventory and source-family screen](varex-source-family-screen-20261124.json)

The protected batch read nine bound reference ranges totaling 353,767
bytes and graded all 131 documents offline. Of those, 130 references
passed their published schema and the native grader's missing-field,
missing-output and malformed-output checks. GSA 50A scored 18/18 on the
native metric. Its distribution details are an object where the schema
requires a string, so it stays outside the pool.

The publisher review treats seven repeat forms as alternate versions of
the same task. One form remains unresolved because its first page could
not be screened. The FDA inspection forms and the two California storage
applications cover different workflows. Keep those related forms within
one study stage. [GSA forms library](https://www.gsa.gov/forms-library)
· [FDA form guidance](https://www.fda.gov/media/182173/download)
· [California cold-storage application](https://www.cdph.ca.gov/Programs/CEH/DFDCS/Pages/FDBPrograms/FoodSafetyProgram/ColdStorageFacilities.aspx)
· [California frozen-locker application](https://www.cdph.ca.gov/Programs/CEH/DFDCS/Pages/FDBPrograms/FoodSafetyProgram/FrozenFoodLockerFacilities.aspx)

The 122 multiple-collection prospects have staged document archives
containing only the PDF, schema and instructions. The first
staging attempt hit the existing hard-link guard. Independent APFS
copies passed the same guard and kept all publisher hashes.
[Native scores and form review](varex-protected-cohort-result-20261124.json)
· [Archive readback](protected-cohort-expansion-20261124.json)

The complementary batch verified 144 more VAREX PDFs with at most one
collection. It reused the retained publisher reference ranges. The
protected grader accepted 141 references. Cases 307, CDPH 263 and DS500
had objects in fields the schema declares as strings. Four other forms
lacked enough first-page text for the lineage screen, and one related
form was held out. The remaining 136 prospects
allow a provisional source-group allocation with 124 complementary
cases. [Complementary grades and capacity](varex-balanced-capacity-20261124.json)

The combined local pack has 246 staged document archives. The capacity
check fits the shared 8-case qualification and 28-case training sets and
both 105-case holdouts without splitting a provisional source group.
The ordinary CLI reproduced an archive and its compact task descriptor.
Complete source-lineage review, case-specific asset-use approval and
frozen study assignments are still open.
[Balanced archive verification](varex-balanced-archives-20261124.json)

The full-page screen checked all 246 staged PDFs and found readable text
in every document. The whole-document and page-level checks found no
additional related forms at their recorded thresholds. The known FDA
and California form groups still fit without splitting. Text similarity
alone cannot establish independent source lineage.
[Full-page lineage screen](varex-full-page-lineage-20261124.json)

The earlier form-number filter used a literal `d` in place of a digit.
The corrected audit checked all 246 staged PDFs for numbered variants
and compared them with both earlier calibration PDFs. It found no
additional relatives to hold. Both calibration cases stay outside the
staged pack. [Calibration lineage check](varex-calibration-lineage-20261124.json)

Ordinary pack inspection verified 1,476 asset hashes across all 246
cases. The unsigned review inventory binds each PDF, its case assets
and the accompanying CDLA-Permissive-2.0 notice to the exact source pin.
The inventory grants zero execution or disclosure approvals and
assigns no study stages. [Asset-use inventory proof](varex-asset-use-inventory-20261124.json)

The provisional allocation uses each staged case once. None of the
three known related form groups crosses stages. The counts below
show the available workload balance. Approval of individual assets
and a frozen study design still come before assignment.

| Stage | Multiple collections | At most one collection | Total |
| --- | ---: | ---: | ---: |
| Qualification | 4 | 4 | 8 |
| Training | 14 | 14 | 28 |
| Candidate holdout | 52 | 53 | 105 |
| Selection holdout | 52 | 53 | 105 |

[Allocation verification](varex-packing-witness-20261124.json)

The document notice screen checked all 246 pinned PDFs. It found one
phrase mentioning written consent. In context, HUD requires that consent
to release a construction payment. The phrase concerns the payment
process rather than reuse of the form.

The grouped proposal covers a single operator decision about local
asset-use records for the 246 cases and their 1,476 verified assets.
The proposed records retain the publisher's license notice. The review
grants no trial execution or provider transfer. Formal assignment still
requires a frozen study and final lineage verification.

[Document notice screen](varex-document-notice-screen-20261124.json)
· [Grouped local-use review](varex-local-use-review-20261124.json)
· [CDLA Permissive 2.0 terms](https://cdla.dev/permissive-2-0/)

Live comparisons remain paused. Candidate benefit and selection benefit
each need a separate result on frozen eligible tasks. Finishing the
stack or approving more runs cannot fill either workload gap.
[Corpus audit](recovery-67a93f4c-result-20261119.json)
and [document rights review](extractbench-disclosure-source-review-20261119.json)
[Stack readiness and release scope](README.md#retained-stack-and-lifecycle-evidence)
and [formal evaluation requirements](README.md#formal-candidate-and-selection-gates)
