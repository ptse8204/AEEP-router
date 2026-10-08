# AEEP Toolkit V2 — authoritative checkpoint state

**Status as of 2026-10-08:** C00, C01 and C02 passed their offline gates. C03 is next. The evaluation journey and C03-C13 remain unfinished; no V2 live efficacy or release claim is established.

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
  C03: TODO
  C04: TODO
  C05: TODO
  C06: TODO
  C07: TODO
  C08: TODO
  C09: TODO
  C10: TODO
  C11: TODO
  C12: TODO
  C13: TODO
last_verified_commit: '91f74de3f9a5fa2a9dbb708686bd8bc55ac8568c'
last_check_command: 'COVERAGE_FILE=.coverage-toolkit PYTHONPATH=src python3 -m coverage run --branch -m pytest'
last_check_result: '1319 passed, 21 skipped; 81.41% combined coverage; both required branch gates and all recorded quality/build checks passed.'
next_action: 'Implement C03 pure installer preview: read INSTALLATION_DESIGN.md, component_setup.py and onboarding.py; first freeze dependency and no-effect tests. No third-party install is authorized.'
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

This session ends at the verified C02 boundary. C03 is safe and eligible, with
source findings above, but its implementation has not begun. Host conformance,
live value, human usability and release remain TODO for V2. No work runs in the
background. Use `git status --short` and the source-hash record before continuing;
do not repeat the full C00 audit or completed checks unless relevant source changes.
