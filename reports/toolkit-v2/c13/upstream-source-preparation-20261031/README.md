# Pinned upstream implementation preparation

Read-only source inspection continues while current first-party verification
runs. No upstream module, installer, task, verifier or candidate executes here.
`source-files.json` binds the retrieved files; the Cisco pyproject and SkillRank
agent source match the earlier C01 hashes. `scanner-lock.json` binds the upstream
lock. Private source copies remain under `.aeep/upstream-stack-source-20261031`.

## Runtime work identified

- Cisco's pinned scanner requires its declared dependency closure even for a
  static-only CLI invocation. Its upstream lock contains179 packages across all
  extras/dev groups; that is not the static runtime installation count. Project
  the selected mandatory graph before preparing an exact installation review.
  Model analyzers stay disabled; installed model SDKs grant no provider authority.
- Microsoft Agent Framework core1.21.0 declares seven direct dependencies and
  exposes its workflow builder separately from provider extras. Use this core
  adapter over existing approved dispatch, rather than introducing a provider.
- SkillRank core search/show actually calls its configured registry API; it has
  no local catalog fallback on those paths. Use the upstream registry/service
  contract under a specific review. Do not replace it with a fabricated local
  registry or silently treat Elastic-licensed registry code/data as MIT core.

## SkillsBench verifier/runtime contracts

`skillsbench-runtime-static.json` records original source hashes, imports, test
identities, skip calls and process launches for all six selected tasks.

| Task | Execution that must be preserved |
| --- | --- |
| Financial-modeling QA | Original PDF/XLSX inputs and protected numeric-answer checks |
| PDF–Excel reconciliation | Original external input bytes and typed change-list checks; external input rights remain unresolved |
| Sales pivot analysis | Actual workbook pivot/cache structures; retain the original conditional skip on a nonmatrix pivot |
| Spring/Jakarta migration | Static migration assertions plus real Maven compile/test with Java21; upstream setup also contains Java8 and Maven3.9.6 |
| React performance debugging | Local simulator and production app, original browser/functional/latency assertions and preserved test IDs |
| Dependency audit | Original lockfile and protected CSV truth; freeze the scanner/database artifacts currently obtained through mutable setup |

Replace mutable setup with exact reviewed artifacts. Preserve assertions and
record any runtime/path adaptation separately; adapted runs are not official
benchmark reproductions. The worker receives public instructions/inputs only.
Keep references, expected answers, verifiers, registry credentials and unrelated
host files outside it. Services internal to an isolated task still require
appropriate lifecycle/permission review; source inspection does not launch them.

## Existing authority and next work

The next executable operation currently awaiting approval is the narrow
[LangGraph SQLite bootstrap correction](../full-stack-20261030/langgraph-sqlite-bootstrap/operation-review.json).
These source records are preparation, not an installation/service/model review.
Complete the runtime artifact closures and ordinary workflow adapters before
requesting their grouped, component-scoped execution authority. No comparative
campaign is resumed by this work.


## Waza backend setup findings

The selected Waza source embeds Copilot runtime1.0.85 through Copilot Go SDK1.0.15.
Its session code explicitly accepts `auto` when reasoning effort is unset. This
removes one source-level compatibility uncertainty; it does not establish account
eligibility or successful execution. The pinned README requires `copilot login`.
`waza dev copilot` generates suggestions and is not a sign-in command. Do not run
it as an authentication check.

No model endpoint is substituted. Prepare the native protected sign-in workflow
and exact artifacts before asking the operator to act. Never capture sign-in
output, inspect credentials, copy Codex authentication or infer paid authority.
The upstream engine defaults to approving tool requests when no handler/policy
is selected; a reviewed tool policy and independent execution containment remain
required. A normal host invocation without those boundaries is not the next step.
Source identity is recorded in `waza-source-files.json` and `waza-setup-source.json`.


The official Agent Framework core1.21.0 wheel was retrieved for static inspection
(812842bytes; no installation/import). Its112 members include the MIT license
matching the selected source. The workflow-builder file exactly matches source
2d9cc3f8. This establishes that API file's identity, not whole-package source
equivalence. `agent-framework-artifact.json` and `agent-framework-static-artifact.json`
retain the exact artifact and findings. The optional core workflow adapter still
needs implementation and a reviewed real SDK check.
