# AEEP Toolkit V2 — authoritative checkpoint state

**Status as of 2026-10-09:** C00-C02 retain their recorded PASS. C03 now includes selected local-wheel installation and conflict-preserving removal; its corrected preflight passed both full suites and coverage gates. C04 now dispatches the actual upstream fake harness into separate Docker workers with per-trial reservations, receipts and durable events. C05 connects those fixed trials to existing AEEP analysis and local reports. General candidate/Codex dispatch, complete comparison economics and C06-C13 remain unfinished. No V2 live efficacy or release claim is established.

```yaml
schema: aeep.toolkit-progress.v1
plan_date: '2026-10-08'
repository: https://github.com/ptse8204/AEEP-router
observed_main_sha_at_plan: 8b015bf0247d4d9f49038982c49f3711a2802d97
plan_branch: codex/toolkit-v2-implementation
implementation_base_sha: 8b015bf0247d4d9f49038982c49f3711a2802d97
current_checkpoint: C04
checkpoint_status:
  C00: PASS
  C01: PASS
  C02: PASS
  C03: PASS
  C04: IN_PROGRESS
  C05: IN_PROGRESS
  C06: IN_PROGRESS
  C07: TODO
  C08: TODO
  C09: TODO
  C10: TODO
  C11: TODO
  C12: TODO
  C13: TODO
last_verified_commit: '29dff45'
last_check_command: 'Framework Python 3.13; reports/toolkit-v2/c03/preflight-correction/validation/checks.json'
last_check_result: '1444 passed, 21 skipped in each full suite; both branch coverage gates, all 11 driver checks, standalone 48-test integration, Node 13 tests, docs (64 files, 571 links, zero errors) and builds passed. Source remained unchanged. General synthetic adapter increment now needs its own checks.'
next_action: 'Verify the integrated D34 installer preflight correction and D33 receipt-backed cash report. Then complete general controlled candidate dispatch and the three-family C06 journey. Existing AssessmentService/BenchmarkRunner own authority, budgets, worker checks and accounting; avoid duplicating those controls. No architecture decision is pending.'
blocked_actions: []
missing_permissions: []
unknowns:
  - 'No upstream evaluators have been compatibility-qualified inside AEEP.'
  - 'No new live cost/token benefit comparison was performed for this plan.'
  - 'C01 pins source and primary licenses; transitive distribution rights, installed compatibility and resources still need C03/C04 checks.'
```

## Append-only checkpoint journal

| UTC date | Checkpoint | Status | Commit | Verified command/output | Outstanding action |
|---|---|---|---|---|---|
| 2026-10-08 | C00 | TODO | None | Planning documents only, not code/test results | Establish working branch and inspect repo |

### Current handoff

- Worktree: `/Users/edwintse/Documents/aeep-toolkit-v2`.
- Source baseline and GitHub main: `8b015bf0247d4d9f49038982c49f3711a2802d97`.
- Imported all nine toolkit documents from the supplied archive; see bundle digest in `reports/toolkit-v2/c00/workspace.json`.
- Inventory and import map written. Original checkout edits remain untouched.
- Initial managed-worktree tests failed because executable identity inspection refuses `.codex` state. Full logs remain under `reports/toolkit-v2/c00/location-failure`. Never weaken that guard for this task.
- Baseline commands passed in the replacement worktree; see `reports/toolkit-v2/c00/summary.json` and individual logs.
- Read-only upstream research is under `reports/toolkit-v2/c01`. No third-party code installed or executed.
- No live trial, grant amendment, credentials, payment, publication or host configuration change authorized by these records.

## C01 checkpoint record

C01 source investigation passed. Exact pins, license scope, observed interfaces
and remaining unknowns are in `UPSTREAM_MATRIX.md` and `reports/toolkit-v2/c01`.
Agent-skill-eval is the first external candidate; AEEP is the fallback (D13).
No candidate is runtime-qualified. Unresolved transitive dependencies, installed
host compatibility, footprint, issue triage and rollback must be checked before
installation or C04 conformance. This does not pass a live gate.

| UTC date | Checkpoint | Status | Commit | Verified evidence | Outstanding action |
|---|---|---|---|---|---|
| 2026-10-08 | C00 | IN_PROGRESS | 2755e49 | Inventory, initial failed-location logs, ongoing baseline | Finish source-bound baseline |
| 2026-10-08 | C01 | PASS (source review) | 92be11c | 17 immutable repository pins and hashed source files | C04 executable conformance remains open |

## C02 completed implementation

Code is in `src/aeep_toolkit/models.py`, with 26 synthetic tests and seven schema
exports through the existing generator. `CONTRACTS.md` describes trust limits.
No existing runtime module changed. `pyproject.toml` includes the new namespace
in coverage. Both final full runs passed 1,319 tests, with 21 skips and one existing
Starlette dependency warning. Combined line/branch coverage was 81.41%; the new
model module reached 98.48%. Both required coverage gates, Ruff, mypy, schemas,
policy, retained proof checks, Node tests and wheel/sdist builds passed.
[The C02 summary](../../reports/toolkit-v2/c02/summary.json) binds the exact logs,
source commit and build artifacts. Executable source stayed unchanged throughout.
The expanded documentation check covers 58 documents and passed with no lint or
local-link errors. External URLs were not fetched by the offline link checker.

The checks use `.coverage-toolkit` separately from the C00 data. Both local
coverage databases and JSON files are ignored; committed text reports, hashes and
gate outputs retain the results. The temporary Node dependency symlink was removed
without touching the original installed tree. No verification process remains
running for this checkpoint.
C00 ordinary pytest: 1,293 passed, 21 skipped, one existing dependency warning in
626.52 seconds. Initial failures under `.codex` remain retained. C00 coverage was
collected before the new tests existed; it describes the legacy source only.
The final C02 run checks the integrated tree separately. No fixture is live evidence.

Temporary drafts and import experiment: `/tmp/aeep-toolkit-v2-contracts.py`,
`/tmp/aeep-toolkit-v2-tests.py`, `/tmp/aeep-toolkit-v2-init.py` and
`/tmp/aeep-toolkit-v2-contract-check`. The initializer experiment is rejected;
never copy it into production. The checked-in source is authoritative.

## Next eligible work after C02 validation

C03 starts in `INSTALLATION_DESIGN.md`, then `src/aeep/component_setup.py` and
`src/aeep/onboarding.py`. Keep preview pure: constructing a Router or opening a
store can write state, so do not do that merely to list a proposed stack.
Resolve exact dependency manifest digests, cycles, missing components, licenses,
platforms, permissions, effects and rollback before offering installation.
Observe installed/enabled state separately from manifest declarations. A source
commit/README hash is not a downloadable package artifact hash. An unresolved
external candidate belongs in the blocked catalog, not a fabricated install plan.
Essentials' package dependency footprint is still a C06/C13 requirement; an
independent import test alone does not establish minimal installation.

The C03 source follow-up found that `component_setup.apply` pins the selected
npm/Python version but does not supply a complete transitive artifact-hash lock.
Do not treat that path as a fully verified V2 installer. Preserve its existing
review/journal behavior, then either enforce the V2 resolved lock before effects
or expose the proposed install as blocked. `onboarding.inventory` returns bounded
connection names/control states; `check_setup` constructs a Router and is unsuitable
for the promised zero-write preview. The first new preview tests should intercept
process/network calls and compare filesystem/config snapshots, including failure
cases for missing dependencies, cycles, stale hashes and incompatible policy.

The managed worktree under `.codex` was archived after its
failed-location logs and research were copied. The app artifact list confirmed archival. The implementation worktree remains
`/Users/edwintse/Documents/aeep-toolkit-v2`. Do not restore the managed worktree
for assessment tests; its location still triggers the safety guard.

If a fresh chat starts in the original checkout, recover this state with:

```bash
git show codex/toolkit-v2-implementation:docs/aeep-toolkit/STATE.md
git worktree list
cd /Users/edwintse/Documents/aeep-toolkit-v2
```

The app cannot attach the external checkout as a managed worktree (the attach
call returned “not a managed worktree”). Git retains the branch and worktree;
this does not block development or require moving code back beneath `.codex`.

## C00 completed verification

All 13 baseline/check commands exited zero. Each full legacy suite passed 1,293
tests with 21 skips and one dependency warning. Combined line/branch coverage
was 81.31%; both required branch gates passed. The baseline covers legacy source;
later quality/build commands also saw the additive C02 contracts.
[The summary](../../reports/toolkit-v2/c00/summary.json) binds exact logs and scope.
The original checkout status still matches the initial snapshot. Retained failures
and skipped real-boundary tests remain separate; no live or release gate closes.

## Future authority gates

- C03 may implement and test a pure preview now. Executing a third-party installer
  needs review of the exact artifact, complete dependency effects and requested
  permissions; C01 source research does not grant that authority.
- C07 needs a new frozen V2 comparison plan, applicable controlled-worker
  conformance and specific operator-approved model/billing allowances. None was
  created or used in C00-C02. Existing campaign grants must not be reset or reused
  by assumption.
- C13 needs the remaining functionality, compatibility and human checks, followed
  by explicit release/publication review. No release or push occurred here.

These are future prerequisites, not reasons to stop C03-C06 offline work.

## Verified checkpoint journal and resumption boundary

| UTC date | Checkpoint | Status / tier | Implementation or evidence commit | Evidence | Next |
|---|---|---|---|---|---|
| 2026-10-08 | C00 | PASS / OFFLINE | c7033b1; baseline 8b015bf | `reports/toolkit-v2/c00/summary.json` | Source audit complete |
| 2026-10-08 | C01 | PASS / source review | 92be11c | `UPSTREAM_MATRIX.md`; 55 retained source hashes verified | Executable qualification remains C04 |
| 2026-10-08 | C02 | PASS / OFFLINE contracts | 91f74de | `reports/toolkit-v2/c02/summary.json` and `acceptance.md` | C03 pure preview |

The prior session ended at the verified C02 boundary. The continuation below
starts C03 from those source findings. Host conformance,
live value, human usability and release remain TODO for V2. No work runs in the
background. Use `git status --short` and the source-hash record before continuing;
do not repeat the full C00 audit or completed checks unless relevant source changes.

## Continuation started October 8

Operator requests continuous implementation until genuine intervention is needed
and confirms local CLI plus HTML/Markdown reports first (D16). C03 implementation
has started under D17. Prior completed evidence remains source-bound to its
recorded commits; new changes require new checks before checkpoint PASS.

## Current continuation evidence

C03 source commit: `a534023`. The pure preview and local CLI now exist, with
47 focused tests passing. Catalog records retain 18 upstream pins plus two legacy
AEEP roles and stay blocked where artifacts or conformance are unavailable.
`reports/toolkit-v2/c03` contains the finite review, dry-run fixture snapshots,
source hashes and progressive check logs. Full regression/coverage is running;
source is frozen while it runs. Supplemental Node/proof/docs checks passed.

C03 is still IN_PROGRESS: real installed-state observations and the reviewed
installer bridge are not connected. Metadata declarations do not authenticate
installed state. Profile dependency closure must be finalized with the selected
evaluator and its mandatory controlled-worker support. No install command or
V2 runtime qualification is advertised.

Local CLI delivery is confirmed. A proposed shared-service extraction question
was withdrawn under D18. [ARCHITECTURE_LOCK.md](ARCHITECTURE_LOCK.md) records the
correction; the [legacy source audit](../../reports/toolkit-v2/c04/extraction-audit.json)
is retained as a coupling observation, not an architecture decision. Continue
with the preferred external evaluator spike; no architecture choice is pending.

C03 follow-up reproduced unstable sibling ordering and case-sensitive credential
filename exclusion in the first preview revision. The initial full validation was
interrupted and retained. Corrections and three regression checks now pass all
50 focused cases; authoritative replacement validation uses
`reports/toolkit-v2/c03/final`. Never count the interrupted run as PASS.

## October 8 correction: upstream integration before internal refactoring

The operator challenged the lack of working upstream integrations. The proposed
shared-service extraction and its two-option architecture question are withdrawn.
The source audit establishes legacy coupling; it does not establish that extracting
Router is preferable to integrating the external candidate. No extraction was
implemented. D13 remains the evaluator decision: test agent-skill-eval first.
D16 remains confirmed: local Python CLI and HTML/Markdown reports. No further
architecture choice is required to prepare the bounded external spike.

C03 remains IN_PROGRESS, and C04 has no executable qualification yet. The catalog
and synthetic tests do not demonstrate an upstream integration. Prepare exact
pinned upstream commands, dependencies, fixture-only effects and authority scope
before execution; use the external runner's existing fake harness for engineering
checks. Keep controlled real-host conformance separate. Do not replace this spike
with another custom runner, installer, workflow engine or broad Router refactor.

The [bounded upstream spike review](../../reports/toolkit-v2/c04/SPIKE_REVIEW.md)
now specifies agent-skill-eval's actual fake-harness CLI, 17 hashed source/test
files, nine hash-locked dependency wheels, two synthetic fixtures and private
scratch effects. Metadata resolution completed; no upstream execution or install
occurred. The operator has been asked for that specific third-party execution
authority. While pending, complete C03 verification and inspect adapter/report
interfaces; do not assume permission or substitute a fake AEEP runner.

### Handoff after the reuse-first correction

Correction and bounded review committed as `d26fa0a`. Documentation validation
passed: 60 documents, zero lint issues and zero local-link errors; external links
were not fetched. C04 is IN_PROGRESS with source review and a concrete execution
review prepared, not a runtime-qualified adapter. The execution response remains
pending; do not infer approval from the architecture confirmation.

The C03 validation driver is still running: PID 76258, command
`python3 /tmp/aeep-toolkit-v2-c03-final-checks.py`, tool session 27297. At handoff,
compile and schema checks passed; ordinary pytest was incomplete. Its sequential
coverage/quality/build checks have not yet reported. Read
`reports/toolkit-v2/c03/final/checks.json` and `source-stability.json` when present.
Source remains `75d1961` for these checks; the correction changes documentation
and review artifacts only. Do not start a duplicate validation or claim PASS.

The task-owned Node dependency symlink under
`integrations/dsh-aeep-router/node_modules` is still present. Remove only that link
after checks finish, preserving its original-checkout target. New full-check logs
remain uncommitted while being written. Preserve the interrupted validation logs
and the original checkout's unrelated edits.

### Product-stack clarification

The operator requested a concrete product and stack explanation, rather than
another checkpoint-only response. ARCHITECTURE_LOCK.md now maps the complete
skill-to-report journey to Python/Pydantic, agent-skill-eval, existing Docker worker
controls, SQLite/artifact storage, comparison/reporting and the three selectable
profiles. The external-dispatch integration is unresolved; no broad refactor is
authorized by this design. The next product deliverable is the complete synthetic
journey, not merely a successful upstream smoke test. The original bounded
third-party execution question remains pending; this clarification is not approval.

C03's ordinary full pytest completed with exit 0 in 633.33 seconds. Coverage and
remaining validation are still running; consult the progressive final checks.

## Executable development stack delivered

The operator's follow-up requested actually building and showcasing the stack
after the concrete private setup was described. That authorizes the bounded local
fixture build; the earlier execution question is no longer pending. D19 records
the scope and full private dependency closure. No live model, credential, public
service or release authority was inferred.

`integrations/toolkit/` is the single development entry point: a complete 24-wheel
lock, standard private venv setup, exact upstream source/fixture pins, real
agent-skill-eval CLI execution, independent fixed-fixture checks and HTML/Markdown
report generation. Both a first environment and a fresh rebuild ran the four
expected trial records. Ten dedicated offline checks passed. The
[showcase](../../reports/toolkit-v2/stack-showcase/index.html) links actual upstream
artifacts; the [summary](../../reports/toolkit-v2/c04/stack-summary.json) states
source hashes, scope, checks and remaining integrations. The synthetic metrics
are not imported as actual model observations.

The first sandbox probe mistakenly tested socket allocation instead of connection
denial; its failure is retained. The corrected connection/home/write probes pass.
The first upstream CLI returned zero despite four Git initialization failures;
those artifacts remain under C04. Using the existing Command Line Tools Git
directly fixed the fixture run without changing the sandbox. The bridge now
rejects missing, mismatched or unverified trial artifacts regardless of CLI exit.

C03 source at `75d1961` stayed unchanged during both full suites: 1,343 passed,
21 skipped, 81.50% combined coverage, both branch gates and all 12 final commands
passed. Supplemental Node/proof checks passed. Its temporary Node link is removed;
no validation process remains running. C03 remains IN_PROGRESS because the general
installed inventory and reviewed production installer bridge are unfinished.

C04 remains IN_PROGRESS. The development demo is not the general EvaluatorAdapter,
a controlled Docker comparison, canonical assessment receipts, or a C06-complete
user journey. The next work uses this tested upstream path instead of creating
a replacement runner. General evidence normalization/comparison and worker/receipt
integration remain safe implementation work; real-host execution needs its own
conformance and applicable authority.

Local resources: private runtimes and retained probe evidence under
`/private/tmp/aeep-ase-c04-tt14mj6r` (about 178 MiB observed; no global package
changes); the useful reproducible runtime is its `rebuild` child. A loopback-only
static report server runs in tool session 16821 at `http://127.0.0.1:8765/`, serving
only `reports/toolkit-v2/stack-showcase`. Its browser tab is marked as a deliverable.
Stop that owned preview process when no longer needed. Runtime removal is scoped
to these task-owned directories; preserve original checkout work and all historical
production evidence. No build, model trial or background implementation is running.

## Operator-restated component map

The operator restated the 14 preferred component assignments, including GitHub
Sponsors for initial developer support. The development manifest and showcase
now enumerate each assignment and its actual integration status. The earlier
showcase omitted Sponsors and grouped several different responsibilities; that
was a presentation/scope error, not evidence that those integrations were complete.
ToolHive remains the optional MCP isolation component; it is not replaced by the
existing comparative-trial workers. The runtime remains fixture-only, with the
same unfinished C03-C13 gates. No additional optional package was installed by
this clarification.

The component-map implementation is committed as `9bccd94`. Its ten dedicated
tests and repeated actual upstream synthetic run passed. All five required
repository checks passed again; ordinary and coverage runs each recorded 1,343
passes, 21 skips and the existing Starlette warning. Combined coverage remains
81.50%; both branch-coverage gates passed. That percentage covers the configured
core packages, not the standalone development integration. Source hashes stayed
unchanged during verification. Exact commands and scope are in
[the correction review](../../reports/toolkit-v2/c04/component-map-review.json)
and its linked logs. No validation process remains running. The loopback report
preview remains available; all outstanding C03-C13 gates remain open.

## Original ZIP audit and corrected research status

The operator requested a fresh audit of the supplied archive. All ten files were
read directly and all nine imported planning documents compared with `d97086d`.
The archive and each preserved original have recorded SHA-256 hashes under
`reports/toolkit-v2/handoff-audit`. [HANDOFF_AUDIT.md](HANDOFF_AUDIT.md) reconciles
the document changes, all fourteen checkpoints and all fourteen acceptance
examples with actual source and existing evidence.

The C01 rewrite had omitted GitHub Sponsors, the already-deferred Archestra
research entry, the eleven-item candidate worksheet and the license/bundling
principle. These are restored. The underlying master, acceptance and continuation
instructions survived import; they were not missing from the workspace. The
implementation misapplied their reuse-first direction and over-presented the
fixed evaluator demo. D21 records the correction.

C01 is IN_PROGRESS until the restored worksheet is reconciled for each mandatory
candidate. Its earlier PASS/source-review journal entries are retained as history,
not the current status. This correction does not invalidate existing pins,
baseline tests or C02 schemas, and does not authorize additional installations.
The audit itself changes no executable source. C03-C13 remain open. The next
implementation remains the upstream adapter and complete evaluation journey;
there is no pending architecture question for the operator.

## C01 worksheet reconciliation and C04 receipt connection

The operator authorized the audit correction. All 21 original responsibilities
now have the eleven required source-review fields in
`reports/toolkit-v2/c01/review-worksheet.json`. Seventeen bounded GitHub issue
snapshots record relevant reported concerns and their limits. Exact source pins
remain unchanged; unknown installed compatibility, transitive/data rights and
rollback remain explicit future installation/conformance gates. Agent-skill-eval
stays preferred, BenchmarkRunner stays fallback, optional components stay visible.
C01 returns to PASS for source selection only; no new runtime qualification is
inferred. The earlier omission and reopening remain in this journal.

The C04 development bridge now launches the pinned evaluator through the existing
`CommandExecutor` and stores a canonical coordinator receipt, execution journal,
immutable fixture records and a C02 `EvidenceBundle` in the existing store. It
creates no Router instance, routing configuration, second runner or new database
schema. All four runs reference one batch receipt; that receipt is not individual
model accounting. Synthetic token/time constants remain unavailable, and the
comparison stays NOT_ASSESSED. General `EvaluatorAdapter` dispatch, independent
controlled workers and real-host accounting are still unfinished.

Seventeen dedicated checks pass, including real subprocess recording, retained
failure/timeout receipts, artifact/receipt/bundle drift and read-only verification.
A filesystem snapshot caught SQLite WAL sidecars in the initial read-only reader;
verification now requires a closed snapshot and uses immutable read-only access.
Fresh actual upstream artifacts are in `reports/toolkit-v2/receipt-showcase`.
Historical showcases were preserved. Source is frozen during required checks in
`reports/toolkit-v2/c04/receipt-bridge-validation`; do not infer full PASS until
`checks.json` and `source-stability.json` finish. Driver:
`/tmp/aeep-toolkit-receipt-checks.py`, tool session 38828.

The coordinator checks use the existing Python at
`/Library/Frameworks/Python.framework/Versions/3.13/bin/python3`; the shell's
Homebrew Python lacks the project dependencies. No package was installed to fix
that PATH mismatch. The upstream runtime remains the approved private `rebuild`
environment. Temporary initial bridge runs remain under
`/tmp/aeep-toolkit-receipt-demo-01` and `-02`; no live calls or grant changes ran.

### Continuation: read-only project doctor

C01 reconciliation is committed as `1eb11cd`; the C04 receipt bridge as `67cc2cf`;
its POSIX CI inclusion as `9a3eab8`. Continuing safe work, C03 now adds
`aeep-toolkit doctor --host ... --project ...`, reusing `onboarding.inventory`
without calling the state-creating `check_setup`. Twelve new cases cover existing
host formats, secret exclusion, malformed metadata, missing projects and zero
process/network/store effects; the full focused toolkit suite passes 62 cases.
Configured/enabled facts remain distinct from unknown installation, exposure and
qualification. C03 is still IN_PROGRESS.

The first validation driver's ordinary run passed 1,343 tests. Its coverage began
before the doctor change and is superseded as a final-tree result. Preserve its
logs and source-change record; do not claim whole-tree stability. Final validation
will run on the completed doctor and receipt bridge together. During that first
run, the standalone receipt reader/template also received metadata hardening and
explicit artifact links; its 18 dedicated checks and fresh actual upstream run
at `reports/toolkit-v2/receipt-showcase-verified` passed on the final bridge source.

The loopback preview now serves that verified report only in session 18321 at
`http://127.0.0.1:8765/`; earlier owned preview processes were stopped. Existing
Docker image IDs were inspected read-only for future reuse; no image was built,
pulled, run or removed. See `existing-worker-inventory.json` in the bridge checks.

The first bridge driver's two legacy suites both finished (1,343 passes, 21 skips),
but its coverage/source snapshot is superseded because safe doctor development
continued during it. `source-stability.json` records the drift. The final combined
validation is separate under `reports/toolkit-v2/c03/doctor-validation`; never
substitute the earlier coverage for the final source. No source changes are
planned during the replacement run.

### Selection-bound receipt verification

The doctor is committed as `56ff281`. The subsequent bridge correction `44da49f`
stores the existing `RouteDecision` before the fixed coordinator dispatch and
binds its immutable snapshot to the receipt. Verification now resolves that
selection, the receipt, C02 records and upstream artifact hashes. Nineteen
standalone tests pass, including rejection of a changed selection. A fresh actual
upstream fake-harness run is preserved in
`reports/toolkit-v2/receipt-bound-showcase`; its four records verify with the
current bridge. Prior reports retain their original source and weaker evidence
format. None of these results establishes individual agent measurements.

Final core validation uses the existing Framework Python 3.13 and is recorded in
`reports/toolkit-v2/c03/doctor-validation`. Its ordinary suite passed 1,355 tests
with 21 skips. Core source/tests stayed fixed; only the two standalone bridge
files changed during that driver and received the separate final checks above.
Read the driver's completed results before asserting coverage or quality PASS.
Do not describe this as whole-tree source stability. The source bindings and
verification scope are in `selection-review.json` and
`selection-source-hashes.json` under the receipt-bridge validation directory.

The current loopback preview serves only `receipt-bound-showcase` in tool session
43386 at `http://127.0.0.1:8765/`. No package installation, image/container change,
model request, credential access or publication was needed for this correction.
The Waza asset review records its release-tag source separately from the reviewed
branch source; no Waza binary has run. Original-checkout edits remain untouched.

Next open `src/aeep_toolkit/installation.py`, `src/aeep/component_setup.py` and
the pinned upstream `agent_skill_eval/harnesses/__init__.py`. Reuse the existing
installation journal and assessment authority. The existing MCP installer also
registers a connection, so it cannot be applied unchanged to an evaluator-only
package. The upstream `HARNESSES`/`get_harness` seam is source-inspected; a general
adapter must bind each scheduled trial to its reviewed worker and receipt before
it may claim isolation. Preserve upstream scheduling and grading rather than
adding a replacement runner. No new architecture decision is pending.

### Completed correction validation

All eleven commands in `c03/doctor-validation/checks.json` finished successfully.
Ordinary and branch-coverage suites each passed 1,355 tests with 21 skips and the
existing Starlette dependency warning. Compilation, schema generation checks,
both branch-coverage gates, Ruff, assessment-policy checks and mypy passed. Core
coverage totals and the exact scope are in `coverage-summary.json`; standalone
bridge coverage is recorded separately. This does not change the skipped live,
platform or release gates. The first superseded driver remains preserved.

The final core source is `56ff281`; final standalone bridge source is `44da49f`.
The core driver's source-stability record lists only the two bridge files changed
while it ran; its core source/tests did not change. Current bridge/fixture hashes
match `selection-source-hashes.json`, nineteen bridge checks pass and the latest
saved upstream run verifies. No validation process remains running. The loopback
static preview remains available; it performs no background implementation.

C00/C01/C02 retain their scoped PASS. C03/C04 remain IN_PROGRESS and C05-C13
remain open. The next action above is safe implementation work, not a request for
another steering prompt. Retain the approved private runtime and existing worker
assets; do not reinstall them merely because the chat context changed.

Documentation checks passed on the completed handoff: 62 Markdown files, zero
lint issues and zero link errors (66 configured exclusions). See
`c03/doctor-validation/docs-completed.log`. No documentation discrepancy remains
from this correction; the unfinished product and evidence gates above remain open.

## Read-only installed-runtime inventory

The next C03 increment replaces the development bridge's pre-sandbox interpreter
probe with bounded filesystem inspection. `stack.py inventory --runtime` and
`plan --runtime` report all 24 locked packages, declared versions/licenses,
dependency requirements and the sixteen pinned evaluator source hashes. Package
metadata is now hash-bound to the existing wheel lock. Source matches remain
separate from unknown dependency/interpreter integrity and host conformance.
Unexpected distributions, startup hooks, changed source and unsafe metadata block
fixture dispatch. The shared metadata reader also rejects hard links.

Thirty-one standalone tests and 63 focused core tests pass. Both actual inspection
commands left the existing runtime's 7,105-entry snapshot unchanged. A fresh
actual upstream fake-harness run and receipt verification passed at
`reports/toolkit-v2/runtime-inventory-showcase`. Commands and observations are in
`reports/toolkit-v2/c03/runtime-inventory`. No package/image installation, model
request or credential access was needed. D25 records the finite test review.
C03 remains IN_PROGRESS: general reviewed installation/rollback and other
extension runtimes are still unfinished. Required full verification follows on
fixed source; do not transfer the previous run's coverage to this increment.

### Runtime inventory validation and dependency artifact audit

Implementation is committed as `5c647dd`. The ordinary full suite passed 1,356
tests with 21 skips; branch coverage and remaining quality checks are running in
`c03/runtime-inventory/validation`. Driver:
`/tmp/aeep-toolkit-runtime-inventory-checks.py`, tool session 7775. Core and Python
bridge source stayed fixed. Browser verification found two report command examples
missing `PYTHONPATH`; only `report.html` changed after validation began. A fresh
upstream run with that correction is in `reports/toolkit-v2/runtime-inspected-showcase`.
Do not overwrite the preceding report or claim whole-tree source stability.

A separate read-only artifact audit checked the exact 24 locked wheels against
the existing runtime: 2,906 archive payload files matched. It downloaded no new
versions, installed nothing and executed no package code. The 7,467,556-byte wheel
cache is `/private/tmp/aeep-toolkit-wheel-audit-ofr3udoo`; retain it for later reuse.
Exact hashes, original/final audit scripts and exclusions are in
`c03/runtime-inventory/wheel-audit.json` and adjacent records. RECORD, generated
console scripts, bytecode caches, unlisted files and the interpreter are outside
that proof. License files are hashed for review, not a redistribution approval.
The product inventory's integrity unknowns are not silently upgraded by this
separate audit.

Read-only C04 findings are recorded in `c04/worker-seam-review.json`. Upstream
`get_harness` is the per-trial integration point; its post-run budget checks cannot
replace existing AEEP reservations. Retain existing managed-worker controls and
keep grading inputs outside trial workers. A Docker daemon socket must not be
exposed to the evaluator coordinator to bypass this integration. No container or
image was provisioned. The existing image was inspected by exact ID only.

The current preview is tool session 41767 at `http://127.0.0.1:8765/`, serving only
`runtime-inspected-showcase`. Its inventory link and corrected commands were
checked in the browser; the screenshot and matching HTTP byte hashes are in the
runtime-inventory evidence directory. No human-usability gate is inferred.

### Completed runtime-inventory verification

Both full suites passed 1,356 tests with 21 skips and one existing Starlette
deprecation warning. Combined coverage was 81.524875%; both required branch
gates passed. All eleven commands in `validation/checks.json` succeeded, including
schemas, compileall, Ruff, policy and mypy. The driver completed; no test remains
running. Python source stayed fixed at `5c647dd`; `report.html` alone changed,
and the fresh upstream execution, artifact verification and browser check cover
that command-example correction. Standalone tests passed 31 cases; runtime.py
reached 93% combined coverage in that separate run. Neither result establishes
worker conformance or live model value. C03/C04 remain IN_PROGRESS.

## C05 descriptive reporting increment

D26 connects normalized C02 records to local JSON, Markdown and HTML summaries.
Exact cohorts and task families stay separate; invalid pairs remain visible.
Token overlap semantics, missing grades and partial timing coverage are explicit.
No confidence, actual billing or value verdict is inferred from metadata.
The existing reviewed campaign analysis remains the intended inference path.
C05 is IN_PROGRESS; full comparison math and accounting remain unfinished.
Focused reporting checks passed 27 tests. The complete repository verification
is being run on the final implementation; its outcome must be recorded separately.

### Upstream nested-payload finding and bounded fixture correction

The actual pinned `SkillInstaller` copies nested evals/.git/cache directories
that its content hash excludes. A synthetic probe reproduced the mismatch in
the existing network-denied sandbox; its temporary scratch was removed. Evidence
and an unpublished upstream issue draft are in `c04/nested-payload-probe`.
No real private files, answers, models or containers were involved. D27 records
the corrective scope: reject unlisted fixture entries and stage only captured,
hash-checked bytes. This is an integration-only change during the C05 full
validation; core Python and core tests stayed fixed. Verify the final bridge
separately and do not claim whole-tree source stability. Arbitrary candidate
payload verification and controlled-worker conformance remain unfinished.

The final fixture guard passed 35 standalone tests and a fresh actual upstream
run with four normalized records and receipt verification. The current source
report is `reports/toolkit-v2/bound-payload-showcase`. The C05 ordinary full suite
passed 1,383 tests with 21 skips; branch coverage is still running. Preserve the
separate source scopes when recording the final result.

## C03 development setup recovery

D28 reuses the existing disk-space and atomic JSON helpers to record private
setup state before package installation. Existing/failed runtimes cannot be
automatically overwritten or retried; concurrent journal edits are preserved.
Pip configuration, cache and inherited provider environment are excluded.
Forty-one standalone checks pass using installer doubles for setup; no new
package installation is claimed. A fresh real upstream fixture run on the
retained runtime is recorded separately. General extension apply/uninstall and
other-platform installation remain unfinished. The full core verification still
uses unchanged C05 source; these further integration changes are checked separately.

### Completed setup replay under existing D19 authority

The subsequent replay performed the same approved 24-wheel private installation
on final setup code. All installed archive hashes matched the lock; the fresh
runtime ran the actual upstream fixture and passed four-record receipt
verification. Its 7,108-entry snapshot was unchanged after execution. The test
runtime `/private/tmp/aeep-toolkit-setup-replay-fza0ph0f/runtime` and empty parent
were removed after that comparison; the original runtime and wheel cache remain.
The target filesystem retained more than 50 GiB free. Exact results, pip report,
journal and file snapshot are in `c03/setup-recovery/replay.json` and adjacent
artifacts. This is bounded fresh-setup/manual-cleanup evidence, not a general
conflict-preserving uninstall command. No model call, credential access, image
pull, container launch or release occurred.

The final integration tests passed 41 cases. An intermediate failure showed that
a concurrent journal edit needed checking before pip bootstrap; the bootstrapping
state transition now performs that CAS check first. Failed test/lint logs are
retained beside the passing `coverage-tests-checked.log` and `ruff-checked.log`.
The fresh source-bound report is `reports/toolkit-v2/setup-replayed-showcase`.

## Verified continuation state after setup recovery and descriptive reports

Core implementation and tests stayed fixed at `5cb863e` through both complete
runs: 1,383 passed, 21 skipped and one existing Starlette deprecation warning.
Combined coverage was 81.591766%; the new reporting module reached 100%. Both
required branch gates, schemas, compileall, Ruff, assessment policy and mypy
passed. All eleven results are in `c05/descriptive-report/validation/checks.json`.
The driver completed; no validation remains running.

The final integration code is `0353188`. `stack.py` and `test_stack.py` changed
during core verification, and `test_setup.py` was added. Those changes were
verified by 41 standalone tests, final compilation/lint, the actual same-pin
installation replay, four-record upstream fixture run, receipt verification and
unchanged-runtime cleanup. The 302 recorded core/test/script/config files stayed
unchanged. Do not describe this as a wholly unchanged source tree.

C00/C01/C02 retain their scoped PASS. C03/C04/C05 remain IN_PROGRESS; C06-C13
remain TODO. General installation/removal, arbitrary candidate intake, controlled
per-trial dispatch and inferential/accounting integration are unfinished code,
not fabricated permission blockers. No architecture decision is pending. Live
model execution and release still require their later exact review.

Keep `/private/tmp/aeep-ase-c04-tt14mj6r/rebuild` and the 7.1 MiB wheel cache
`/private/tmp/aeep-toolkit-wheel-audit-ofr3udoo`. The newer setup-replay runtime was
removed after its unchanged-tree check. Other temporary probe/demo scratch was
removed by its owning operation. Existing unrelated checkout changes remain
untouched in `/Users/edwintse/Documents/aeep-agent-router`.

The current loopback preview is tool session 18722 at `http://127.0.0.1:8765/`,
serving only `reports/toolkit-v2/setup-replayed-showcase`. The browser was refreshed;
HTML/inventory responses match saved artifact hashes. The final screenshot and
HTTP checks are in `c05/descriptive-report`. Documentation checks passed 63 files
and 571 links with zero errors and 66 configured exclusions. This is not a human
usability exercise or an external release.

## October 9 continuation: reason for the prior stop

The operator asked what actually prevented completion. There was no external
blocker: `blocked_actions` and `missing_permissions` were empty. The implementation
agent ended at a handoff with safe work remaining, contrary to the instruction to
continue. General reviewed installation/removal, per-trial dispatch from
agent-skill-eval into existing controlled workers, and binding the existing AEEP
analysis to toolkit evidence are engineering work, not pending architecture or
permission decisions. No V2 worker launch had failed; that dispatch was not built.
The passing fixture suites did not establish controlled-worker conformance or
comparative benefit. Preserve this distinction after every resumption.

The operator now explicitly requests continuing with that conclusion retained.
Continue safe implementation and tests without requesting another architecture
choice. Exact live execution, protected sign-in, additional unreviewed third-party
effects and release retain their applicable authority gates; none blocks writing
or testing the missing integration. Existing grants/counters and unrelated work
remain unchanged.

### General private installer implementation

The toolkit CLI now has `install-plan`, `install` and `remove`. It accepts an
explicit manifest closure and local wheel inventory, binds exact policy, platform,
interpreter, artifacts and destination, then uses the existing space check and
durable file helpers with offline standard venv/pip. Successful replay checks the
whole applied runtime tree. Changed files/modes, additions, links, special files,
failed installs and interrupted removal are preserved rather than blindly retried.
Startup hooks and wheel `.data` relocation are rejected. Host activation is separate.

Focused verification: 51 tests passed (26 lifecycle plus 25 preview tests), including
an actual no-index synthetic-wheel install/remove, dependency failure and durable
replay refusal. An initial test found that a `sitecustomize` package directory
escaped the first startup-hook check; all path components are now checked and the
regression passes. Ruff and mypy passed for the toolkit before the final small
input-hardening additions; full required verification is next. C03 remains
IN_PROGRESS pending complete checks and replay of the approved evaluator closure.
No new third-party package, image, model call or host configuration was installed.

### October 9 controlled-worker and analysis evidence

The actual pinned agent-skill-eval scheduler dispatched both arms of both fixed
cases through four separate local Docker workers. `reports/toolkit-v2/c04/controlled-trials`
retains every replay, intermediate test failure and its charges. Attempt 1 predates
the decision-redaction/event-persistence repair; attempt 2 predates separating
worker source from coordinator-write scope. Attempt 3 checks that separation.
Attempt 4 connects the predeclared fixture positions to existing `fit_report`.
Attempt 5 also binds the descriptive report for read-only integrity verification.
These remain synthetic records, not capable-agent conformance or live holdouts.

The fixed suite retains the existing 100-case/20-pair thresholds and returns
insufficient evidence. Each C02 run names its individual worker receipt. Model
tokens, model wall time, billing and savings remain unavailable. Seven focused
bridge/analysis tests pass, including authority, budget, replay, failed output,
interruption, redacted persistence and missing/changed analysis inputs.

The approved 24-wheel closure installed from the existing local cache through the
general installer, passed idempotent verification and was removed with the owned
journal retained. Exact plan, wheel/license hashes and replay results are under
`reports/toolkit-v2/c03/general-installer`. Original runtime/cache and all unrelated
user work remain intact. The ordinary full suite passed 1,409 tests with 21 skips;
coverage and remaining required checks are still running under tool session 13190
and `/tmp/aeep-toolkit-general-installer-checks.py`. Do not claim those checks pass
until the progressive result and source-stability records say so.

### Space and candidate-intake hardening

The first full ordinary suite passed 1,409 tests at f454a00. Its coverage run was
intentionally interrupted during review, before changing source: actual wheel
sizes must set the disk reservation even when metadata understates them. The
retained validation directory records exit 2 for that interrupted run; it is not
a coverage PASS. The corrected installer includes measured archive/expanded byte
bounds and explicit unsupported-platform handling. A fresh complete verification
will use a separate `validation-final` directory.

General local candidate inspection now captures a bounded SKILL.md tree, hashes
exactly the files it stages and excludes nested evals/Git/cache data from both.
Eight synthetic regressions cover the observed upstream copy/hash defect, links,
credentials, changed captured bytes and content-free CLI output. Twenty-eight
installer lifecycle tests pass after space/portability hardening. No arbitrary
candidate has been executed; connecting this intake to managed Codex dispatch
remains engineering work, not a permission blocker.

### Current verification and next reporting increment

The final ordinary suite at `4ddf045` passed 1,419 tests with 21 skips and one
existing dependency warning in 637.35 seconds. The corresponding coverage run and
remaining gates are still running under tool session 94691; do not mark them
passed prematurely. The current driver is
`/tmp/aeep-toolkit-general-installer-final-checks.py`.

The hardened installer replay again installed the same 24 reviewed wheels from
the existing cache, verified idempotence and removed the unchanged runtime. It
retained its journal at
`/private/var/folders/_g/bvzl9cms7cx1d0wdpc981n9w0000gn/T/aeep-general-installer-replay-749ebinz`.
The original runtime and cache remain unchanged. The final documentation check
passed 63 files and 571 links with zero errors; wheel/sdist builds also passed.
See the new `replay-final`, `docs-final.log` and `build-final.log` evidence under
`reports/toolkit-v2/c03/general-installer`.

The next cost-report change is staged for development under
`/tmp/aeep-toolkit-economics-draft`, outside the fixed implementation being
verified. These drafts are not shipped features or checkpoint evidence. They
reuse existing cash resolution, preserve failed-run costs, reject shared charges,
and keep explicit recurring-fee scenarios separate from observed billing and
statistical benefit. Integrate and verify before claiming support.

The `4ddf045` verification completed: both full suites passed 1,419 tests with
21 skips, all eleven driver commands passed, and source hashes stayed unchanged.
The combined coverage was 81.6868%. The coverage run took 905.73 seconds.
No validation process remains for that source. C03 stays IN_PROGRESS because the
subsequent audit identified D34; passing existing tests does not erase that gap.

### Integrated preflight correction and descriptive costs

D34 now uses installed `packaging==24.2` for actual platform/wheel tags, Python
requirements and dependency closure. Pip dependency discovery is disabled; active
URL requirements and extras fail before effects. Case-insensitive archive
collisions and startup-hook aliases are rejected. No new package was downloaded
or installed to develop this correction. The library's local source/license
hashes are retained under `c03/preflight-correction`.

The report CLI now accepts digest-keyed receipt records and explicit recurring-fee
scenarios. It reuses existing cash resolution, includes failed-run costs and keeps
unknown billing, missing grades, zero successes and quality regressions from
creating a break-even claim. Supplied records remain unauthenticated; synthetic
amounts remain synthetic. Full integrated verification must finish before a new
checkpoint PASS. General candidate dispatch and C05 inferential integration remain
unfinished engineering work.

The new `29dff45` ordinary suite passed 1,444 tests with 21 skips in 637.00 seconds.
Coverage and the remaining gates are running under tool session 86777, driver
`/tmp/aeep-toolkit-preflight-correction-checks.py`; retain its source snapshot.
The corrected 24-wheel replay also passed and retained its removal journal at
`/private/var/folders/_g/bvzl9cms7cx1d0wdpc981n9w0000gn/T/aeep-general-installer-replay-f8evt07j`.
The controlled receipt cost example stays unknown; a separate example uses
explicitly invented bill/fee inputs to test arithmetic, never measured savings.

The next upstream adapter increment is being developed separately in
`/tmp/aeep-toolkit-general-adapter` while this verification runs. It is not yet
integrated or a checkpoint PASS. It captures arbitrary local candidate payloads
and bounded reviewed suites, stages exact treatment bytes, keeps prompts
transient, and adds real scripted file edits for the future three-family offline
journey. The existing 38 focused draft/bridge tests pass. Run a fresh source-bound
Docker replay after integration; unit fixtures are not worker conformance.

### D34/D33 verification completed

The corrected installer and receipt-cost reporting at `29dff45` passed both full
suites (1,444 passed, 21 skipped), all 11 checks, both coverage gates and eight
supplemental proof/build commands. The private 24-wheel replay, repeat verification
and unchanged-runtime removal passed. Evidence is under
`reports/toolkit-v2/c03/preflight-correction`; synthetic cash arithmetic is separately
labeled under `reports/toolkit-v2/c05/cash-report`. No model or billing calls ran.

The next integration now includes all toolkit tests in the default pytest suite
and switches the standalone CI invocation to pytest so function-style regression
tests cannot silently go uncollected. C06 remains in progress until actual replay.

### General offline journey: executed, verification pending

C03 passes its OFFLINE gate with the D34 regression, exact local-wheel replay,
non-mutating preview tests and conflict-preserving removal evidence above.
This does not qualify installed evaluators for real hosts.

The D35 adapter completed two three-case runs through agent-skill-eval 0.7.0:
12 distinct Docker workers, all removed. One run explicitly retains synthetic
outputs; the other uses the default of no content retention. The audit resolved
all receipts, checked treatment payload hashes, scanned decoded saved records
for task content, and rejected six tampering cases. See
`reports/toolkit-v2/c06/offline-journey/audit.json` and both CLI transcripts.
A following import-format-only correction changes the adapter source hash; the
reviewed plans preserve the exact executed bytes. Full regression verification
for this increment remains pending. C04/C05/C06 remain IN_PROGRESS.
