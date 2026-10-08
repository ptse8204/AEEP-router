# Tests, use cases and known limits

[Documentation index](README.md).

AEEP aims to improve the work your agent can do with the tools available to it.
Use this guide to judge how far the recorded results support that goal and which
questions still need testing.

Recorded checks cover known text operations, scoped native workbook tasks and
reversible access controls. The larger Luna studies found failures and did not
approve either candidate for automatic use. Each result applies to its linked
source, task and environment. The [plan coverage record](../reports/v08/plan-coverage.md)
retains the full history, including failed attempts and remaining work.

<details>
<summary>Contents</summary>

- [Use cases supported by evidence](#use-cases-supported-by-evidence)
- [Software checks](#software-checks)
- [Worker and native execution checks](#worker-and-native-execution-checks)
- [Native workbook execution](#native-workbook-execution)
- [Live completion diagnostic](#live-completion-diagnostic)
- [Direct execution of a known text operation](#direct-execution-of-a-known-text-operation)
- [Discovery, approval and removal](#discovery-approval-and-removal)
- [Completed studies that did not qualify](#completed-studies-that-did-not-qualify)
- [Diagnosing completion timeouts](#diagnosing-completion-timeouts)
- [Remaining evidence](#remaining-evidence)
- [Run the developer checks](#run-the-developer-checks)
- [Stack planning evidence](#stack-planning-evidence)

</details>

## Use cases supported by evidence

| Use case | Why use AEEP | What has been demonstrated |
|---|---|---|
| Run an already identified, repeatable operation | The host can send a structured action to an approved implementation without asking a model to choose the same tool again. | Twenty matched `text.stats@1` actions returned exact results on both routes. The direct AEEP route made no provider calls during those measured actions. |
| Give an agent a bounded workbook tool | An operator can approve one implementation with defined permissions and attempt limits, then inspect receipts for its use. | Native Codex invoked the scoped workbook tool and produced two independently checked workbooks. The larger workflow study also exposed completion timeouts. |
| Evaluate a skill before enabling automatic use | Correctness and comparison records determine whether a candidate can advance. Failed results stay in the record. | The DOCX and workbook studies completed without admitting their failing candidates. |
| Pause, replace or remove project access | A project can withdraw access while retaining receipts, attempt counts and unrelated user configuration. | Automated lifecycle and recovery tests cover these controls; a synthetic discovery-to-use experiment also verified revocation and teardown. |

These are useful when the task contract can be stated precisely and its result
can be checked. Open-ended work still needs the host agent's judgment. Evidence
for a fixed workbook recipe does not establish arbitrary spreadsheet editing,
general skill quality or a speed improvement for every user.

## Software checks

The [October 7 local verification record](../reports/v08/windows-ci-20261007/summary.md)
reports 1,293 passed and 21 skipped in both ordinary pytest and branch coverage
on source `41531fc`, with both required coverage gates passing. Its runner results
and subsequent fixture changes are recorded separately. Native Windows CI does
not establish supported native Windows onboarding; the setup target remains
macOS and Linux/WSL. These are recorded software results, not a new verification
of this documentation revision or a completed release.

The documentation refresh has its own [validation record](../reports/v08/documentation-refresh-20261007/summary.md).
Changes to fingerprinted integration READMEs require new applicable evidence
before a historical live result can be applied to the new source.

### Earlier diagnostic validation

The [October 4 validation record](../reports/v08/outer-worker-delay-20261004/validation-terminal.json)
binds the October 4 diagnostic implementation to source
`e6b71acba487280dfe50057d17379e5994c9113bc651a262935474f656a5dba6`.

| Check | Recorded result |
|---|---|
| Full suite under branch coverage | 1,219 passed, 21 skipped, 1 warning |
| Overall coverage, including branches | 81.8925% |
| Critical-code and assessment coverage requirements | Both passed |
| Compilation, generated schemas, assessment policy, Ruff and mypy | Passed |
| Node integration tests | 13 passed |
| Offline integration proofs, provider-package verification, wheel and source builds, retained artifact checks | Passed |

The first ordinary pytest run had 1,218 passes and one failure: the README rewrite
removed a literal status marker required by the version-consistency test. Restoring
that marker passed both version tests; the subsequent full coverage run passed all
1,219 tests. The [original failure log](../reports/v08/outer-worker-delay-20261004/06-pytest.log)
is retained. The one warning concerns a dependency's deprecated test-client usage.

The earlier [October 3 validation](../reports/v08/luna-c-boundary-cost-validation-20261003/terminal-summary.json)
recorded 1,214 passes, 21 skips and 81.8666% combined coverage on source `50de999e…`,
plus 28 focused boundary-cost and conformance integration checks.
Its [supplemental record](../reports/v08/luna-c-supplemental-validation-20261003/supplemental-results.json)
retains ten additional offline checks. Those results remain historical.
Skipped opt-in tests are not passing live tests. Software checks do not establish
model reliability or production readiness. The dated diagnostic below renewed
the boundaries needed for its narrow scope; a full paired assessment still needs
its own applicable conformance evidence.

The tests also check specific failure conditions:

| Behavior | What the tests verify | Test definitions |
|---|---|---|
| Permission and attempt limits | Unreviewed, expired, revoked, exhausted or changed scopes cannot dispatch; model arguments cannot raise the approval ceiling; pause/resume does not restore spent attempts. | [Task profiles](../tests/test_v08_task_profile.py) |
| Project activation and removal | Pausing one session leaves another usable; uninstall preserves unrelated configuration and receipts; conflicting user edits stop rollback. | [Task lifecycle](../tests/test_v08_task_lifecycle.py) |
| Interrupted writes | An exit or timeout after a write requires recovery; restart does not repeat the write; reviewed reconciliation retains the receipt and spent allowance. | [Task recovery tests](../tests/test_v08_task_profile.py) |
| Discovery | Results remain untrusted metadata; queries are explicit and bounded; failure uses only the configured local fallback; redirects are not followed. | [ARD discovery tests](../tests/test_v08_ard.py) |
| Nested execution accounting | A callback's child evidence must resolve to the exact completed, measured parent operation; missing or mismatched links are rejected. | [Cost resolution](../tests/test_v08_boundary_costs.py), [callback binding](../tests/test_v08_composed_cost_binding.py) |

Some unit fixtures replace the native sandbox to isolate router behavior. Actual
environment checks provide separate evidence for the tested execution boundary.

## Worker and native execution checks

The [composed conformance audit](../reports/v08/luna-docx-stage/c-all-probes-parent-cost-audit.json)
records 30 passing probes on source `50de999e…`: 22 controlled-worker checks,
six native-component checks, and two actual Luna/xhigh callback checks. They
cover allowed and denied operations, separation between workers, protected
answers and synthetic credential canaries, network restrictions, configuration,
resource limits, cleanup, events and callback authority.

All 30 probes resolve to six measured parent operations. The
[acceptance record](../reports/v08/luna-docx-stage/c-boundary-conformance-apply-result-v1.json)
confirms that the exact worker records and their comparison definition passed
verification. This establishes the tested environment and callback connection.
It does not establish that a candidate completes its assigned tasks reliably.

## Native workbook execution

A small live comparison gave native Codex and Codex with AEEP the same two
workbook tasks. Both produced workbooks that passed independent grading. The
recipe checks values, supported formulas and cached results, required formatting,
workbook structure and the specified preserved sheet.

| Measurement | Native Codex | Codex with AEEP |
|---|---:|---:|
| Correct workbooks | 2/2 | 2/2 |
| Production host lifespan | 79.355 s | 17.717 s |
| Peak sampled process-tree memory | 404.59 MiB | 592.93 MiB |
| Observed CPU time | 2.148 s | 3.550 s |
| Provider-reported total tokens | 123,203 | 60,201 |

The [comparison record](../reports/v08/native-model-resource-evaluation-5fff-comparison.json)
contains raw measurements, separate assessment costs and output-validation
results. The [independent audit](../reports/v08/native-model-resource-evaluation-5fff-terminal-independent-audit.json)
checked outcomes, accounting and cleanup. Both routes passed the
[resource budgets frozen for this workload](../reports/v08/native-model-resource-evaluation-5fff-acceptance-interpretation.json).

AEEP completed this pair faster with fewer reported tokens, while using more
sampled memory and CPU. It was one fixed-order pair with AEEP invocation required,
on source `5fffda8a…`. It does not measure optional tool selection or general
savings. Process sampling can miss short-lived activity; provider cash,
subscription consumption and whole-machine costs were unavailable. The recipe
also excludes macros and external links.

Four separate native autonomy scenarios produced one verified task completion
and three safe stops. Ordinary work and the paused case passed their fixed
conditions. Permission-expansion and recovery cases stopped safely but failed
two strict response or behavior conditions. See the
[scenario audit](../reports/v08/native-sol61-autonomy-four-scenarios-5fff-canonical-audit.json).

## Live completion diagnostic

An [October 4 diagnostic](../reports/v08/live-delay-diagnostic-20261004/findings.md)
renewed 22 worker and three native boundary checks, then used Luna at xhigh with
fresh workbook inputs and one-attempt scopes.

| Case | Result | What it establishes |
|---|---|---|
| First input, containing unsupported fractional prices | Native task validation failed; outer host timed out after 203.231 s | This was a test-preparation error and a failed-helper recovery path. It does not reproduce the earlier task-valid-child timeouts. |
| New integer-only input, checked before execution | Passed in 23.510 s; turn completed 2.727 s after callback response write | One current-source valid callback completed naturally, returned an artifact and cleaned up. |

Both results and their costs are retained. A report serialization error was
recovered without repeating the model call. The final audit records 18 settled
operations and two model turns, including prerequisite checks. These cases do not
establish qualification, general reliability or a performance improvement. The
five historical timeouts remain unexplained; artifact retrieval and cleanup
still lack separate duration measurements.

## Direct execution of a known text operation

An earlier experiment tested an already installed `text.stats@1` implementation.
Codex received its exact command. AEEP received the corresponding structured
action and selected the same Python function directly.

| Measurement across 20 matched actions | Codex with exact tool | AEEP with same tool |
|---|---:|---:|
| Exact results and verified tool executions | 20/20 | 20/20 |
| Provider input plus output tokens | 584,449 | 0 |
| Median tokens per action | 28,888 | 0 |
| Median wall time | 8,324.9 ms | 5.47 ms |

The [method and accounting record](../reports/v06/codex/tool-ready-campaign.md)
identifies Codex 0.147.0, GPT-5.6 Terra with medium reasoning, randomized order,
ten cold pairs and ten warm pairs. It also retains 719,101 provider tokens used
in excluded pilots, a rejected run and warm-up.

This demonstrates avoiding a model/tool/model loop when the action is already
known. It excludes installation and natural-language interpretation. Codex's
token totals include its full host context; they cannot be attributed to one
tool schema. No reconciled cash comparison was available.

## Discovery, approval and removal

A [synthetic native integration experiment](../reports/v08/luna-docx-stage/discovery-profile-bridge-terminal-audit.json)
connected fixture discovery, explicit local intake, qualification, admission,
task-profile dispatch, receipt capture, revocation and uninstall. The retained
records link the same executor to the approval, scope and successful receipt.
The completed runner also checked that revocation prevented another invocation.

This verifies that the components work together. Its candidate was a fixed
fixture, its mapping was supplied by the operator, and its baseline was
deliberately slower. It does not demonstrate automatic matching of a discovered
plugin or real capability benefit.

A separate [live ARD search](../reports/v08/luna-docx-stage/discovery-live-result.json)
returned four candidates for `docx`. None identified the selected SkillsBench
skill, so no association or activation was created from those results.

## Completed studies that did not qualify

Both studies used Luna at xhigh with eight screening cases, 28 training cases
and 105 holdout cases. Holdouts are cases kept separate from development and
training. Neither study retried its failed trials or changed its thresholds to
obtain a pass.

| Study | Result | Qualification decision |
|---|---|---|
| SkillsBench-adapted DOCX offer-letter task | 137/141 passed; two text-preservation failures and two timeouts; 101/105 holdouts passed | `unsuitable`; no admission |
| AEEP workbook workflow | 136/141 passed; five timeouts, including four holdouts; no graded incorrect answers | `insufficient_evidence`; no admission |

The [DOCX terminal record](../reports/v08/luna-docx-stage/successor-qualification-terminal.json)
retains the negative result on source `eaad5bc7…`. A separate public fixture
passed all 18 assertions in the
[unchanged pinned upstream verifier](../reports/v08/luna-docx-stage/upstream-verifier-terminal-audit.json).
That compatibility check does not erase the failed holdouts or constitute an
official full SkillsBench benchmark run.

The [workbook terminal audit](../reports/v08/luna-docx-stage/c-workbook-qualification-terminal-audit-20261003-v3.json)
reconciles all 141 trials and 436 completed, measured plan operations. The
[timeout audit](../reports/v08/luna-docx-stage/c-workbook-timeout-task-scope-terminal-audit.json)
found a successful, valid native child receipt for every timeout. Those native
operations finished 146 to 175 seconds before the surrounding agent workflow
timed out. The retained metadata does not identify the exact cause of that delay.
Successful child execution does not turn a timed-out workflow into a passing trial.

Both studies lack complete resource measurements. Provider usage-complete flags
do not establish the missing coverage, so neither supports a savings claim.
The failing qualifications cannot authorize the planned value comparison.

## Diagnosing completion timeouts

The [October 4 metadata investigation](../reports/v08/luna-docx-stage/c-workbook-callback-delay-metadata-diagnostic.json)
examines the existing five failed trials without replaying them. Their event records show that AEEP completed the callback and
the host continued producing action and usage events afterward. The callback
completion point follows artifact transfer and validation of the tool response.
The retained records do not identify the later actions or explain why the host
did not finish within the deadline. One passing trial also took 122.627 seconds
after its native child finished. A long delay alone does not identify the cause.

A [follow-up audit](../reports/v08/outer-worker-followup-20261004/investigation.md)
compared the receipts with the exact packaged source from the live run. All five
failures have the partial-timeout metadata pattern; the passing comparison has
the normal completion fields. This supports an earlier-stage diagnosis: the
host turn timed out or was cancelled before the wrapper retrieved its final
output. A returned timeout also implies that worker cleanup succeeded in that
code path, although its separate duration was not recorded. Eight tiny offline
probes confirmed the relevant return and cancellation behavior. The reason the
host continued working after the callback remains unknown.

The adapter now saves a structured summary in the receipt’s `host_progress`
metadata field, encoded as compact JSON text.
It contains the workflow stage, callback counts and elapsed times, the last
recognized event type, and whether an output message and terminal notification
arrived. The final-message flag accepts explicit final answers and legacy
unphased messages; the terminal flag also includes interrupted or failed turns.
It excludes task contents, messages, tool arguments and credentials. A written
response means the local pipe accepted it; that alone does not prove the host
received or acted on it. Counts aggregate callback replies, including concurrent
request rejections; they do not identify an individual reply. Timeout snapshots are taken before interruption so
cleanup events cannot be mistaken for timely completion.

The snapshot covers the model turn and callback. It does not time subsequent
worker artifact retrieval or cleanup, and those stages can fail without an
updated snapshot. A small, fixed-field summary is produced by the Codex adapter;
the receipt store itself only filters metadata keys and scalar types.

These diagnostics improve the information available from a future failure.
They do not repair or reclassify the historical timeouts. The changed adapter
needs fresh applicable environment checks before another live assessment.
Four [scripted transport tests](../tests/test_codex_dynamic_tools.py) exercise a
written callback response followed by a stall, a rejected callback, a final
message without turn completion, and cancellation during a callback. A separate
[database test](../tests/test_codex_progress_persistence.py) verifies that the
summary survives closing and reopening the receipt database. These are offline
regressions, not new model trials.

For a future failure, compare callback completion and response-write times with
the last host event, final-message flag and turn-completion flag. That can
help distinguish a callback delay from continued host activity or an absent
completion signal, within the stages recorded.
Any proposed change to the workflow then needs a separately reviewed experiment;
the existing failed holdouts remain part of the record.

## Remaining evidence

The normal-agent / discovery-only / discovery-plus-AEEP value comparison has not
run. It must test optional use after matching qualification and environment
checks pass. General improvements in agent quality, representative resource
savings, native catalog selection and human comprehension remain unproven.

The current controlled workbook experiment combines container workers with a
native macOS callback. Running it unchanged entirely on Linux cloud is not
supported. A complete cloud setup needs an applicable backend, independently
verified worker boundaries, operator-managed authentication, and durable transfer
of the existing assessment ledger without resetting its counters. Portable core
and offline checks do not establish those runtime requirements. See the
[cloud feasibility audit](../reports/v08/ard-skillsbench-cloud-audit-20261002.md)
for the dated assessment and the [current coverage record](../reports/v08/plan-coverage.md)
for subsequent implementation and experiment results.

## Run the developer checks

From the repository root, the required checks in [AGENTS.md](../AGENTS.md) are:

```bash
python3 -m compileall -q src examples tests
PYTHONPATH=src python3 scripts/generate_schemas.py --check
python3 -m pytest
python3 -m coverage run --branch -m pytest
python3 -m coverage report -m
```

These commands do not reproduce the live studies. Follow the
[assessment testing policy](ASSESSMENT_TESTING.md) for pinned environments,
reviewed definitions, finite budgets and separate live checks. Existing completed
campaigns and consumed task scopes must not be replayed as fresh evidence.

## Stack planning evidence

The [stack implementation record](../reports/v08/stack-implementation-checklist.md)
separates software tests, offline domain fixtures and actual free provider checks.
The fixtures check an edit timeline, grouped report and referenced facts. They do
not generate production video, fetch live research or establish marginal benefit.

Sanitized existing-connection checks and a pinned local-runtime observation are in
`reports/v08/stack-readiness/`. Their scope and source digests are part of the
record. They do not prove a new operator-completed sign-in handoff, credential-bound
metered billing readiness or provider task quality. Those release gates remain
open. Current-source stack tests do not renew historical live qualifications or
production conformance evidence.
