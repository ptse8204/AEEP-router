# AEEP Toolkit V2 — authoritative checkpoint state

**Status as of 2026-10-08:** C00, C01 and C02 passed their offline gates. C03 preview passed its software checks; its installer integration is unfinished. C04 now has an executable upstream development demo. The evaluation journey and C03-C13 remain unfinished; no V2 live efficacy or release claim is established.

```yaml
schema: aeep.toolkit-progress.v1
plan_date: '2026-10-08'
repository: https://github.com/ptse8204/AEEP-router
observed_main_sha_at_plan: 8b015bf0247d4d9f49038982c49f3711a2802d97
plan_branch: codex/toolkit-v2-implementation
implementation_base_sha: 8b015bf0247d4d9f49038982c49f3711a2802d97
current_checkpoint: C03
checkpoint_status:
  C00: PASS
  C01: PASS
  C02: PASS
  C03: IN_PROGRESS
  C04: IN_PROGRESS
  C05: TODO
  C06: TODO
  C07: TODO
  C08: TODO
  C09: TODO
  C10: TODO
  C11: TODO
  C12: TODO
  C13: TODO
last_verified_commit: '75d1961'
last_check_command: 'COVERAGE_FILE=/tmp/aeep-toolkit-v2-c03-final.coverage PYTHONPATH=src python3 -m coverage run --branch -m pytest'
last_check_result: '1343 passed, 21 skipped; 81.50% combined coverage; both required branch gates and all 12 final quality/build commands passed. Separate stack checks: 10 passed plus fresh upstream fixture execution.'
next_action: 'Use integrations/toolkit as the executable development foundation. Connect the qualified fixture artifact path to the general EvaluatorAdapter and existing controlled-worker/receipt boundary; continue C03-C06 acceptance without claiming the demo completes them.'
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
