# Preserve published package-local test layouts

Suite case v4 lets the existing grader evaluate packages whose protected tests
live in directories such as `gabbi/tests`, `src/icalendar/tests` or `test`.
Operators declare exact `test_roots` in protected truth. Every selected module
and overlay member must lie below those roots. Candidate edits still cannot
replace tests or configuration. No test path, identity or assertion is renamed.

V1–v3 keep their fixed `tests/` root and reject the new field. [The actual retained
v3 recipe](legacy-compatibility.json) rebuilds with identical canonical digest
`d02cb9538fe9a42470612f799912b7907c3b72ffd6a8ab0c42661b22e3ab4b0f`.
The existing observer, container adapter, accounting, archive bounds and acceptance
thresholds remain. No service or product dependency was added.

## Source verification

[All13 checks](validation/checks.json) passed on source
`86012b45856c2ceea8c123a008e5dbbb30e12adac8e816de8ff80500976d4e9b`.
Both full runs passed1703 tests with21 skips and the existing dependency warning.
Coverage is82%; both branch gates passed. Compile, schema freshness, integration
fixtures, Ruff, assessment policy, mypy and wheel/sdist builds passed. The77 suite
contract tests include24 new v4 cases. The source stayed unchanged throughout;
session42772 is terminal and must not be repeated without a new reason.

These are engineering checks. They do not qualify an upstream workload, prove
capability usefulness or validate resource acceptance. The current44-case pool
retains its old source/runtime bindings; a changed grader inherits no conformance.

## Workload and runtime preparation

[Metadata review](layout-inventory.json) identifies213 candidate rows across97
repository groups with supported nonstandard test-root names. That is metadata,
not a runtime-fit or reproduction count. Bounded source reads retained5,110,797
bytes from18 rows:12 need static review, four are partial/unparsed and two fail
existing archive safety rules.

Nine cases were prepared as inert v4 data. Raygun and Skelebot need separate
non-source-reference scope review; Towncrier's test overlay also needs further
scope review. Those failures remain. Sopel is excluded from the proposed runtime:
it needs SQLAlchemy1.4 and installed distribution metadata; the existing image
has SQLAlchemy2.0.44. No downgrade or project installer is proposed.

Eight other cases are being assembled for one finite execution review: Gabbi342,
iCalendar878/880/921, SQL-Metadata552/553/583 and RO-Crate248. Together they retain
1033 required identities across eight tasks; the915 identities in one iCalendar
case are not915 independent workload cases. No new case joins the pool yet.

[Runtime metadata](runtime-support-review.json) pins12 optional support wheels,
1,743,060 bytes, with static dependency closure. These are private grader supports,
not AEEP core requirements. [JSONPath source review](jsonpath-source-review.json)
binds the source-only1.4.0 distribution to six unchanged library files, all matched
to publisher commit `5a4b2c7053ceeb1ea5d30abb019dfb7b2c2e31bb`. The publisher license
was recovered from that same commit. The embedded module version is1.3.0; it is
recorded without alteration. Proposed deployment copies those bytes read-only,
without executing setup.py, generating entry points or running a source build.
The initial incomplete support triage remains as an unexecuted record.

## Failure evidence

The next exact review will explicitly request operator-only retention of at most
8192 bytes of each failed public test log. [The proposed observer](operator-observer-review.json)
wraps the same five-field evaluation and changes no grading rule. The operator
driver unwraps evaluation for the protected grader and retains the separate log
tail. Default product retention remains unchanged. Logs are untrusted data and
never instructions or model-facing answers.

[Four synthetic checks](operator-observer-check.json) verified identical stock
and wrapped evaluations, bounded tails and no child/third-party execution. These
fixtures are not benchmark evidence. Actual build, install, source execution,
updated-wheel checks and offline docs checking still need one concrete exact
approval after the combined review is prepared. No architecture decision is needed.

## Exact execution review

[The combined review](approval-bundle.json) binds three offline components. It is
prepared for approval; none has executed. [The runtime component](runtime-review.json)
permits one private build from retained `f60342e9`, twelve cached wheels and a COPY
of the unchanged JSONPath modules and license. It then permits three fresh probes
and twenty exact repair/regression variants for the eight cases above. The bound
is26 existing-grant operations and1135 reserved seconds, zero models or cash.
All images remain. Only new owned containers and the unchanged canary are removed.

[The package component](../../integration-completion/package-review-test-roots-20261027/operation-review.json)
checks wheel `ce0a1290c30190cf56d87de6e058faa3837269cf2f47c0c97c67a5c55b3b00bb`
with32 unchanged cached dependencies through19 private offline checks. V4 recipe
export and exact test roots are checked as inert data; no repository code executes
in this component. [The docs component](../../integration-completion/lychee-test-roots-review-20261027/operation-review.json)
uses the cached pinned Lychee0.24.2 executable in its tested offline sandbox.
Unchanged private package/checker runtimes are removed; receipts and caches remain.

Approval also opts into the bounded public failure tails described above. There
is one terminal attempt, with no automatic retry or reassignment of unused calls.
A rejected workload does not stop independent cases or package/docs checks after
verified cleanup. Common authority, accounting, binding or cleanup uncertainty
stops external dispatch. No downloads, pulls, model calls, credentials, new
services, activation, release or old-resource deletion are covered.

## Direction after execution

The current reproduced pool remains44 snapshots across29 repository groups:
16 single-file repairs,18 multi-file repairs and10 audits. Ninety-seven cases
remain before the unchanged141-case balanced design can be frozen. If all eight
new cases reproduce, the pool becomes52; that outcome is not assumed. Repository
groups stay in one stage, and prior observations retain their source/runtime pins.
The new operator profile cannot silently qualify a default-observer campaign.

Continue independent corpus preparation, then freeze source-bound stages and
qualify the actual worker/grader composition before a formal optional-use
comparison. Evaluate selection against independently established, applicable
usefulness labels. A rejection or abstention is useful evidence but cannot stand
in for positive task-specific value. Keep whole-host resource acceptance and the
remaining human control exercise separate. No scientific gate closes here.
