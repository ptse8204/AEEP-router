# Toolkit V2 status and next work — October 19, 2026

Storage no longer blocks the project. The first preflight measured 166.45 GiB
free and found all four required image pins. The terminal check measured 164.43
GiB free, still above both reviewed execution allowances. No cleanup occurred in
this resumption. Production source remains `d2c406f`, digest
`d05541e90d2e200ba1ea61b4169a8ebcdf62fd96217fdbe35a81e42accd4d1b0`.

The immediate blocker is the pinned Codex worker's readiness RPC:
`account/rateLimits/read` fails with `CodexRequestError`. The adapter treats the
failed readiness probe as unsupported and blocks task generation. The retained
classification does not establish exhausted quota, missing authentication or a
particular network/API cause. Do not expand budget or request sign-in based only
on that label.

## What was completed in this resumption

- Restored the reviewed source fingerprint by preserving two Finder metadata
  files outside source directories. All tracked source bytes were unchanged.
- Completed the previously approved generated-tool training check: generated
  outputs passed 24/28, independent reference 28/28; four correctness failures,
  zero execution failures and zero model turns. The frozen tool was not repaired.
- Corrected the launch guard that mistook completed storage preparation for a
  started campaign. Exact preparation, remaining allowance and no-replay guards
  passed 11 focused checks; arbitrary prior trials remained rejected.
- Restored the missing pinned candidate file at its frozen temporary location,
  verified all 6,637 bytes against the recorded hash and retained a durable
  source/license copy. This is inert candidate evidence, not agent instructions
  or an activated skill. Temporary-source recovery remains a durability concern.
- Resumed the same queued, unstarted job under an exact reviewed guard. Ten
  focused checks rejected started jobs, prior trials, changed/unresolved
  preparation and insufficient allowance.
- Ran the first real editing-qualification case. It ended in host preflight
  rejection, with no output to grade. The remaining 140 cases did not run.
- Isolated the failed readiness RPC in a separately reviewed zero-model probe.
  Thread/turn creation and task replay were denied. Raw account responses,
  principal values, errors, credentials and authentication output were not stored.

The qualification is terminal, `insufficient_evidence`, not a candidate
correctness failure or a passed qualification. Its job must never be replayed.
The proxy was restored, no assessment job remains active and counters were not
reset. Total reserved model turns increased by one for the rejected trial; no
successful inference or billed-cash amount is inferred.

## Unfinished plan

| Plan area | Actual state | Remaining work |
|---|---|---|
| C00–C06 foundation and offline journey | Implemented and source-bound verification retained | Preserve those results; repeat checks only for relevant changes or drift |
| C07 live value | Text forced-use qualification completed earlier; editing qualification stopped at host readiness | Repair/readiness-qualify the worker, fresh three-family qualification, task-matched optional-use four-arm study and analysis |
| C08–C12 optional components | Applicable bounded acceptance recorded | Supported scope stays narrow; unqualified/deferred software cannot be advertised as working |
| C13 adoption and release | Installation/removal and software evidence retained | Actual comparison and overhead accounting, human comprehension, supported-platform evidence, final documentation checks and operator go/no-go |

The implemented stack remains local Python CLI plus private HTML/Markdown
reports, existing SQLite/receipt storage, agent-skill-eval for scripted dispatch
and the existing AEEP runner for managed Codex evaluation. Waza mock conformance,
bounded LangGraph execution, configured discovery and local telemetry preview are
recorded. Cisco report import is not scanner execution. ToolHive and hosted
observability are unselected/unqualified. SkillRank, public MCP benchmark packs
and generated-workflow engines retain their recorded licensing, task-mapping,
optional-choice or execution-boundary exclusions. No new architecture choice is
needed to repair the current worker.

## Next sequence

1. Obtain a more specific content-free diagnostic of the failing readiness RPC.
   Resolve its cause without changing authentication boundaries or assuming
   quota exhaustion. This is the next engineering action.
2. Review any necessary exact worker/source change and its relevant conformance.
   Prepare a fresh plan and disjoint cases; retain this terminal failure and cost.
3. Complete the easy-edit, bounded refactor and adjacent-task qualification. Keep
   forced use separate from optional-access value.
4. Freeze and execute the four-arm study: capable normal agent, optional skill,
   higher-compute normal agent and a reviewed task-matched training-built tool.
   New generated-code execution/image/model exposure needs its concrete review;
   the completed text training approval does not authorize those later effects.
5. Produce task-family quality/time/token comparisons, missingness and uncertainty.
   Retain negative results and keep assessment overhead separate. No favorable
   result is required for an honest report.
6. Finish C13 resource/platform/documentation evidence, actual human comprehension
   and the operator's private-beta/release decision.

Broad software regressions and private package installs were not repeated. Earlier
runs verified fixes to schema handling, usage accounting, reports and packaging;
they do not establish marginal plugin value. The focused checks here tested
specific launch/recovery safety changes. They cannot close C07 or C13.

## Evidence

- [Current status and counters](status.json)
- [Storage/source/image preflight](preflight.json)
- [Generated-tool training summary](training-summary.json)
- [Training execution result](../../c07/text-reusable-review/training-result.json)
- [Editing terminal summary](editing-summary.json)
- [Editing terminal execution result](../../c07/edit-study-preparation/qualification-resumed-result.json)
- [Prepared-plan rejection diagnosis](editing-preflight-blocker.json)
- [Candidate source restoration](candidate-restoration.json)
- [Exact queued-job resumption review](../../c07/edit-study-preparation/qualification-resumed-execution-review.json)
- [Zero-model readiness review](readiness-review.json)
- [Zero-model readiness result](readiness-result.json)

The initial readiness-script invocation used an incorrect supplied review hash
and stopped before its one-shot marker or any effects. Only the subsequent exact
hash invocation performed the diagnostic. Its result and grant operation remain
retained. The pinned Lychee 0.24.2 documentation checker remains missing; that
minor tooling gate is separate from the live worker failure.
