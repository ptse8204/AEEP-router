# Audit of the original handoff

The ZIP already specified the upstream stack and the first user journey. The
implementation did not follow that direction closely enough. This audit reads
all ten files directly from the ZIP and compares them with commit `d97086d`,
including the source code and recorded checks. It separates lost requirements,
misinterpreted decisions and unfinished implementation.

The archive SHA-256 is
`913b998ffdf3860a3feb3de00e5e37ebb31806bf5ecd7cbaedcd6560e2cc03bc`.
[The inventory](../../reports/toolkit-v2/handoff-audit/inventory.json) records
each file's hash, an unchanged snapshot and its checkout diff. Original documents
describe the plan at handoff; their initial TODO values are not current progress.
Their contents do not grant new installation, credential, spending or release
authority. The operator's request governs this audit.

## What went wrong

1. **The research rewrite lost requirements.** Commit `92be11c` replaced the
   original upstream matrix. It omitted GitHub Sponsors, the already-deferred
   Archestra research entry, the eleven-item C01 decision worksheet and the
   concluding license/bundling principle. Sponsors reappeared only after the
   operator's correction. This audit restores both rows and the worksheet in
   [UPSTREAM_MATRIX.md](UPSTREAM_MATRIX.md). Archestra remains deferred research.
2. **Optional components were treated too broadly as deferred work.** The ZIP
   gives Waza an evaluator/task-scaffolding role, SkillRank search/evaluation,
   ToolHive MCP isolation, LangGraph execution, EvoAgentX proposal and AFlow
   optimization. The source-review table's broad DEFER labels obscured those
   responsibilities. They remain conditional integration targets. The ZIP does
   not require installing every candidate or pretending each will qualify.
3. **The proposed architecture question omitted the preferred route.** Asking
   the operator to choose a Router extraction or temporary legacy backend before
   proving the external adapter did not follow the handoff. D18 withdrew that
   proposal. The source audit of Router coupling remains valid, but it did not
   justify that choice. Local CLI and static reports were also already the
   handoff's default under D11; a new delivery decision was unnecessary.
4. **The working demo did not satisfy the first product journey.** It executes
   the real agent-skill-eval package against a fixed fake harness. It accepts no
   user-selected candidate, has two cases rather than easy/complex/adjacent
   coverage, uses a development evidence format, and does not connect the general
   adapter, canonical receipts or comparison engine. The current source labels
   these limits; calling that demo the completed stack would be incorrect.
5. **Setup remains split.** The toolkit CLI exposes list/plan; a separate
   development script exposes setup/demo. Profile role filters and an explicit
   metadata dependency preview exist, but the preview, installed inventory and
   existing reviewed installer/recovery path are not joined. The ZIP asks for
   one continuous experience with doctor, rollback and non-destructive removal.
6. **The displayed fourteen-row map was not the whole ZIP inventory.** The ZIP
   additionally includes SkillsBench, OpenSkillEval, MCP Registry/ARD, Microsoft
   Agent Framework and the deferred Archestra reference. The first four were
   retained in research/catalog records; they were not newly discovered here.
7. **Progress reporting needs a narrower claim.** C01 had a PASS/source-review
   label even though its required per-candidate worksheet was incomplete and
   lost from the living document. C01 is reopened as IN_PROGRESS. Existing source
   pins and license observations remain valid within their recorded scope;
   C00's checks and C02's contract tests are not invalidated by this correction.
8. **Stopping and requesting steering became part of the problem.** The supplied
   continuation procedure already requires consecutive safe work, with exact
   external blockers recorded separately. A checkpoint report or polished
   showcase is not a reason to ask the operator to restate the architecture.

The error was in applying and maintaining the plan. All nine planning documents
were imported. The master instructions, acceptance criteria and continuation
rules remained available while the implementation drifted.

## Every archive file checked

| ZIP file | Comparison with `d97086d` |
|---|---|
| `CODEX_START.md` | Not copied to the repository root. It is the import/start/resume wrapper and suggests an optional AGENTS pointer; the ZIP directs copying `docs/aeep-toolkit`, so this alone is not a missing runtime deliverable. Its original is now retained in the audit. |
| `README.md` | Only the implementation-status sentence changed. Product purpose, two plugin categories and three profiles survived. |
| `MASTER_PROMPT.md` | Status wording, URL formatting and one heading changed. Product and implementation requirements survived. |
| `DECISIONS.md` | Original D01-D11 retained; later entries appended. D18 records the withdrawn extraction proposal. |
| `UPSTREAM_MATRIX.md` | Substantially replaced. The omitted rows, worksheet and principle above are restored; original role details remain available in the immutable snapshot. |
| `CHECKPOINTS.md` | Blank-line formatting added; all fourteen stages and their gates survived. |
| `ACCEPTANCE.md` | Byte-identical to the ZIP. Required comparison behavior remains mostly unimplemented. |
| `INSTALLATION_DESIGN.md` | Byte-identical to the ZIP. Its complete setup/recovery experience is still unfinished. |
| `CONTINUATION.md` | Byte-identical to the ZIP. Autonomous continuation requirements were present throughout. |
| `STATE.md` | Expected progress updates, evidence and journal additions. This audit corrects the overbroad C01 completion status without removing historical entries. |

## Checkpoint delivery reconciliation

These are implementation observations, not new acceptance definitions. Refer to
the [original checkpoints](../../reports/toolkit-v2/handoff-audit/original/docs/aeep-toolkit/CHECKPOINTS.md)
and [current state](STATE.md) for the gates and authoritative statuses.

| Stage | Observed delivery | Unmet requirement |
|---|---|---|
| C00 | Inventory, isolated feature checkout, source-bound baseline and preservation records | Existing PASS remains scoped to the recorded audit/software evidence. |
| C01 | Seventeen remote source pins, adopted ARD pin, legacy audit and preferred evaluator/fallback | Complete the restored per-candidate worksheet, including relevant issue triage and explicit compatibility, footprint, rights and rollback findings or unknowns. |
| C02 | Validated inert contracts and schemas; independent imports tested | Runtime authentication of evidence references belongs to C04/C05; a hash-shaped string is not verified evidence. |
| C03 | Pure dependency/permission preview and three role-filter profiles | Authenticated installation observations, concrete profile manifests, reviewed installer bridge, recovery/rollback and removal integration. |
| C04 | Actual agent-skill-eval 0.7.0 CLI, four fixed synthetic arm records and independent output checks | Executable common EvaluatorAdapter, current-host/controlled-worker conformance, complete normalization and canonical receipts. |
| C05 | ComparisonReport schema and a fixed NOT_ASSESSED development report | Matched-cohort analysis, quality/resource tradeoffs, uncertainty, missingness, task-family reports and defensible economics. |
| C06 | Reproducible private development setup and report | User-supplied skill through one reviewed journey; three task families; doctor/removal; Essentials independence demonstrated for the whole flow. |
| C07 | No new V2 live study | Frozen plan, applicable worker conformance, specific authority/budget and genuine paired evidence. |
| C08 | Existing discovery/scanner source research | Integrated inert discovery/security pack with provenance and permission-difference evidence. |
| C09 | Optional evaluator/benchmark candidates recorded | At least one additional backend or pack with isolated conformance and equivalent normalized reporting. |
| C10 | Existing OTel code retained; optional backends researched | Connect instrumentation, qualify optional export/isolation behavior, installation and revocation. |
| C11 | Existing Router/StackRuntime retained; external workflow sources pinned | Optional V2 boundaries and one real compatible external workflow fixture; preserve graph semantics and authority. |
| C12 | DeveloperIdentity assertion schema; Sponsors restored to component map | Authenticate attribution/support links; private/public preview and opt-in portable evidence. |
| C13 | Regression evidence and truthful development-only labels | Installer replay, supported-host checks, user comprehension, overhead/competitive comparison and explicit go/no-go/release review. |

## Acceptance behavior reconciliation

The following checks map all fourteen examples in the
[original acceptance file](../../reports/toolkit-v2/handoff-audit/original/docs/aeep-toolkit/ACCEPTANCE.md).
Existing legacy functionality is not counted as connected V2 behavior without an
adapter and a test of that path.

| Example | Current V2 coverage |
|---|---|
| 1. Trivial task passes both arms but treatment costs more | No comparison decision implementation. |
| 2. Fewer tokens with worse success | No comparison decision implementation. |
| 3. Complex-task gain versus easy-task loss | No task-family aggregation or complex fixture in the demo. |
| 4. Missing cash stays unavailable | Contracts preserve missingness; demo cash is null. Canonical billing resolution remains absent. |
| 5. Overlapping token categories | Contract tests reject inconsistent subsets and invented totals; runtime normalization remains absent. |
| 6. Subscription capacity is not billed-cash saving | No invented saving in the demo; the general economic resolver is unfinished. |
| 7. One favorable pair is insufficient | Synthetic reports cannot claim demonstrated benefit; live statistical interpretation is unfinished. |
| 8. Different model/catalog/worker cohorts | Fields exist and adapter/subject mismatches are checked; general comparability/cohort logic is absent. |
| 9. Missing/skipped grading | Schemas represent these states; the fixed collector rejects unexpected artifacts. General missingness analysis is absent. |
| 10. Recurring fee and break-even | Not implemented. |
| 11. Candidate update invalidates applicability | Fixed demo checks exact hashes; general prior-report applicability is absent. |
| 12. Recommend no plugin when baseline suffices | Not implemented as a general decision. |
| 13. Timeout with uncertain effects requires reconciliation | Fixed demo timeout/artifact checks exist; the canonical attempt/reconciliation connection is absent. |
| 14. Incompatible/nonfree install blocks before effects | Pure preview policy tests exist; the production apply/recovery boundary is unfinished. |

## Corrections and continuation

The restored source snapshot prevents future summaries from replacing the supplied
requirements. Keep source research, intended component roles and runtime status
separate. Every optional component needs a recorded integration, qualification
gap or justified unsupported status; Archestra retains its original deferred
research role. The ZIP allows conditional optional support, not an unconditional
promise to install every listed tool.

Reconcile the restored C01 worksheet first, using existing pinned evidence rather
than repeating completed downloads. Continue the actual upstream adapter and
C03-C06 journey. The developer-only bootstrap/report must not grow into a second
runner, installer or evidence database. No new architecture answer is needed from
the operator for that work.

This audit changes documentation and evidence records only. It reread all ten ZIP
files, compared all nine imported documents, inspected toolkit source/tests, and
ran the existing CLI help, Full catalog and development plan without installation.
It does not qualify an upstream host, execute a new benchmark or close a product
gate. The latest full code verification remains bound to `9bccd94`.
