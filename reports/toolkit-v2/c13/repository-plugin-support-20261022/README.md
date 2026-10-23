# Explicit pytest plugin support and repository runtime checks

The grader can now load operator-declared pytest plugins while keeping automatic
plugin discovery off. Version1 definitions and observer bytes are unchanged.
The core still uses AEEP AssessmentService/BenchmarkRunner and the reused
SWE-rebench pytest parser. These runtime libraries are optional grader supports;
they are not new host or Essentials dependencies.

Source `f694024c` is committed in `a6ed14a`. All13 configured checks passed without
drift:1673 tests in each full run,21 skips,82% total coverage,both branch gates,
Ruff,layering,mypy and wheel/source builds. Fifty focused tests and the exact
legacy-serialization comparison passed. See validation/ and the two serialization
records. Do not repeat broad verification on unchanged source.

Actual approval038b2af9 ran each component once. The25-wheel offline image build
passed and the resulting image is retained. Three fresh containment/state/runtime
probes passed, including the actual mocker fixture and native-library checks.
Twenty-two physical calls completed; all canonical attempts/receipts were reopened,
raw replies retained and owned containers absent. Seven of eight repository cases
reproduced, including all four AbsaOSS/Foamlib per-file partial-repair rejections.
Leanclient's14 required identities passed, but three additional Lean-server tests
errored. Its whole-module reference remains rejected at exit1. The complete bundle
is therefore not marked passed. The source is unchanged.

The installed wheel passed18 CLI/identity checks and one retained capture check.
The cached offline docs check passed69 listed documents. Both private runtimes
were removed unchanged; exact documentation input hashes are retained. These
checks do not need repeating for the new protected test-scope data.

The image build and grader calls charged25 canonical operations and
47.86661691684276 seconds. The final grant record is12880 operations,3744 model
turns,118273.29034517473 seconds and0.0 cash. No model or cash delta occurred.
Unused call slots remain unused; the completed review cannot replay.

A new declared-node Leanclient adaptation completed separately under
../repository-declared-tests-20261022/. It keeps all14 required identities and
assertions, declares the task scope publicly, and appends a protected collection
hook that excludes only other identities. The old failed observation remains.
Source, observer, image, zero-exit and missing/error guards are unchanged. Exact
approval7bbc9678 ran once: the reference passed and original/two partial repairs
were rejected, each observing exactly14 required identities. All receipts and
cleanup were verified. Eight provisional screening cases now reproduce; no
full campaign stages have been frozen.

No full8/28/105 cohort is frozen. No new model qualification, comparative
usefulness, selection quality, resource acceptance, human-control or release gate
passes from these checks. Historical model results remain INCONCLUSIVE.
