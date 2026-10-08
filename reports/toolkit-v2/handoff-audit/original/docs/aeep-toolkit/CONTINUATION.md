# Codex continuation and checkpoint protocol

This file makes the work resumable **without referencing any prior chat**. A Codex session may stop or compact; it cannot be assumed to run in the background. Later sessions must recover from the repository.

## At the start of each session or after compaction

1. Check working tree, branch, latest commit, local environment and pending user edits. Use a dedicated feature branch; do not overwrite unrelated work or force-push.
2. Read repository `AGENTS.md`, `docs/ASSESSMENT_TESTING.md`, `SECURITY.md` as applicable. Read `docs/aeep-toolkit/STATE.md`, then `CHECKPOINTS.md`, current checkpoint description, `DECISIONS.md`, `UPSTREAM_MATRIX.md`, and `ACCEPTANCE.md`.
3. Verify any PASS status against its cited commit/log/artifact and actual code, not self-reported text. If code changed after evidence, mark evidence **STALE** and recheck. Never declare live efficacy from fixture tests.
4. Pick the earliest unblocked checkpoint whose prerequisites are PASS. Prefer the critical path through C06. Continue independent tasks when a live/permissioned stage is blocked, without silently skipping the gate.
5. Work through the checkpoint and its acceptance tests. Reuse upstream tools/code unless a documented proof shows this would be a bad fit. Avoid broad rewrites unrelated to the checkpoint.
6. Before ending work or moving to the next checkpoint, update `STATE.md`, `DECISIONS.md`, `UPSTREAM_MATRIX.md` and relevant checkpoint evidence links; commit a coherent change with message prefix `[AEEP-CNN]`.

## After every checkpoint or substantial work unit

Record a compact handoff in `STATE.md`:

- `checkpoint`, status (TODO/IN_PROGRESS/PASS/BLOCKED/DEFERRED/STALE), definition and acceptance gates.
- Git commit SHA / parent, changed paths, adapter/source pins.
- Exact commands, environment and results (successes, failures, skips, coverage when relevant), artifact/log paths.
- Remaining unknowns, risks, licenses and blockers.
- Permission/budget needed if blocked; no assumed authorization.
- Current next independent action, next file to open, and minimal next command.

Require evidence before setting **PASS**. A generated README, registry listing, installed package, or mock harness is not a passed live comparison. Do not overwrite historical results, downgrade controls, reset budget counters, or change frozen benchmark outcomes.

## Resume decision rules

- If the current checkpoint is **IN_PROGRESS**, first inspect the working tree and outputs to avoid duplicating side effects; continue from the first unmet acceptance gate.
- If **BLOCKED** on authorization/payment/credentials, document exactly what the operator must approve, stop the dependent action, and continue the next safe independent checkpoint. Do not assume the owner granted permission because of an earlier context or because a prior tool succeeded.
- If upstream version/contract drift breaks an adapter, pin the observed versions, mark STALE/BLOCKED and keep the previous working version available. Never silently switch backends after test failure.
- If work contradicts the original AEEP mission, stop feature expansion and record an ADR. Every new core service must justify why an upstream adapter could not suffice.
- Before declaring a checkpoint complete, compare the resulting user-facing behavior with `ACCEPTANCE.md` and run relevant regression/security tests. Respect full checks from `AGENTS.md` when code changes.

## Research and change authorization

Read-only audits, drafting plans, writing deterministic tests and local non-metered tests may proceed inside granted workspace authority. Reviewing third-party READMEs does **not** authorize their installers or executing untrusted packages. Large downloads, image/container provisioning, service startup, full-host configuration changes, public publication, real payment setup, paid model trials, or privileged credential access require applicable user/operator authorization. Preserve exact reproducibility pins and license/redistribution notes.

Existing AEEP documentation distinguishes delegated routine assessment-definition work from authorization for cash/credentials/release. New this-track checklists do not expand it. Review `reports/v08/plan-coverage.md` for legacy gates; keep v2 gates separate and linked rather than rewriting historical evidence.

## Status report to user (concise)

`Checkpoint: Cnn — state | Implemented: ... | Proven by: ... | Blocked: ... | Next: ... | Commit: ...`.

Don't ask the user for each checkpoint. Ask only where a required external permission or decision is absent and no safe alternative exists. Do not imply autonomous background execution; resume occurs when an actual Codex session runs.

## Copy-paste resume instruction for a fresh Codex session

> Continue the AEEP Evaluation Toolkit rearchitecture in the current repository. Read AGENTS.md and docs/ASSESSMENT_TESTING.md, then docs/aeep-toolkit/STATE.md, CHECKPOINTS.md, CONTINUATION.md, README.md and ACCEPTANCE.md. Verify the latest checkpoint evidence, use the recorded next action, and advance through as many consecutive safe checkpoints as the current session allows. Update and commit repository state after each gate. Respect all existing spending, isolation, installation, and review boundaries; do not ask me to reconstruct earlier context or mark untested work complete.
