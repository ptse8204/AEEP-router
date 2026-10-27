# Larger repository workload check — prepared, not executed

This check prepares six larger public repository tasks for later capability
comparisons. The compact prototype excluded many real snapshots at its 650 KB
source cap. An explicit suite-case v5 and operator-owned archive mapper now allow
larger inputs while preserving the earlier profiles and their serialized recipes.
AEEP still uses its existing runner, accounting, protected grader and container
executor with upstream pytest and the pinned SWE-rebench parser.

## Completed engineering evidence

Source `1fde951724c1096e404f27e7013df1470d62a24b35589030362369122d02e7a7`
passed [all 13 source checks](validation/checks.json). Both full runs passed
1,724 tests with 21 skips and one existing warning; coverage is 82%, and both
branch gates passed. Compilation, schemas, integration checks, Ruff, mypy and
wheel/sdist builds passed. The actual frozen `d02cb953` recipe reconstructs
identically in [the legacy check](legacy-compatibility.json). The first attempt
used a mutable later cache with different historical fault bytes; that failed
comparison is retained and did not alter the frozen evidence.

The [new wheel](build-artifacts.json) is built with SHA-256
`60466c129f114ee10be053331ef7e9d29016723eb39c5a6f4ae7c5e95db1459c`.
Its installation check is prepared, not run. No new subject, image build, package
installation or model turn has run under this review.

## Exact proposed execution

The [combined approval bundle](approval-bundle.json) binds three components:

- [Runtime review](runtime-review.json): six snapshots from Cyclopts, NetworkX and
  Isort, with twelve fixed reference/counterexample variants. Four fresh probes
  check containment, state isolation, actual image dependencies and a 2.7 MB input.
- [Installed package review](../../integration-completion/package-review-large-archives-20261027/operation-review.json):
  one current AEEP wheel plus 32 unchanged cached dependencies, 19 private offline
  checks, then removal of the unchanged owned runtime.
- [Offline documentation review](../../integration-completion/lychee-large-archives-review-20261027/operation-review.json):
  cached Lychee 0.24.2 and markdownlint, with the reviewed sandbox and current
  document fingerprints. The first-party sandbox preflight passed separately.

The runtime needs six cached optional wheels and one exact 35,174,018-byte SciPy
1.15.3 CPython 3.13 Linux aarch64 wheel. [The fetch pin](pending-wheel-fetch.json)
binds its official URL, hash, target, dependency and publisher license. SciPy has
not been downloaded. Up to two fetch attempts may retrieve only that artifact as
data; size, hash, wheel metadata and licenses must verify before the offline image
build. No package is installed on the host. All existing and new images remain.
The retained parent is `df79d0f3`, through its existing checked local tag.

The cumulative maximum is one build, 20 contained calls, 27 existing-grant
operations and 1,420 reserved seconds, with zero models or cash. The initial phase
has 16 calls; with one fetch its maximum reservation is 20 operations and 1,010
seconds. Four extra calls and one additional setup/analysis phase are reserved
only for recorded first-party control repairs after known completion and cleanup.
They cannot replay uncertain attempts or change software, task bytes, assertions,
permissions, product source or wheel. All charges remain. The initial driver does
not automatically spend this diagnostic allowance.

Image growth is capped at 256 MiB and the host must retain 50 GiB free. SciPy's
expanded footprint remains unknown until the exact artifact is read. These are
finite execution bounds, not production resource acceptance thresholds.

## Exclusions and open gates

Smart-open's two S3 cases remain inert and deferred because their selected tests
need boto3, botocore and moto. Pexpect occurs only in an unrelated Cyclopts test
subtree and is not added. Anyio's protected-path and plugin-layout exclusions stay
recorded. NetworkX retains full source and tests, with editable directories scoped
to published source changes; no assertion is removed to fit the profile.

The historical pool remains 51 snapshots across 33 repositories, with 90 cases
missing from the balanced 141-case design. Its original source/runtime bindings
remain. These six cases are unadopted; reproducing their graders would not prove
capability usefulness or selector quality. Qualification, comparative value,
selection, resource acceptance, unaided human controls and release remain open.
No savings are inferred. The older editing comparison stays inconclusive.

## Resume

Read the exact bundle and static checks, then record an actual approval before
running `run-integration-bundle.py` with the bundle file's SHA-256. No approval for
this new bundle is present. Terminal review `27efdd79` cannot cover changed source,
software or tests. Standing authority covers routine finite definitions and budget
amendments; it does not authorize the new download, installation or upstream test
execution. No architecture or budget decision is needed.
