# Architecture for the first complete toolkit

AEEP helps a user decide whether a skill improves an already capable agent enough
to justify its cost and permissions. A developer can use the resulting evidence
to explain where that skill helps, where it hurts, and how to reproduce the result.

The first completed product accepts a local `SKILL.md` or reviewed source
reference, previews setup and trial expenses, runs an authorized comparison, and
writes a private HTML/Markdown report. The report must be useful when the result
is no benefit, a regression or insufficient evidence.

## Operator-specified component map

The operator restated these 14 assignments. They govern component selection and
must not be collapsed into a generic extension list. Optional means selectively
installed and qualified, not automatically outside the implementation scope.
The local fake-harness demonstration covers only part of the primary engine row.

| Function | Preferred solution | Implementation responsibility |
|---|---|---|
| Primary evaluation engine | agent-skill-eval | Test first; verify Codex integration and isolation |
| Evaluation fallback | Existing AEEP BenchmarkRunner | Reuse if external evaluators fail requirements |
| Additional evaluation | Microsoft Waza | Optional extension |
| Skill discovery and evaluation | SkillRank core | Optional integration; verify licensing |
| MCP benchmarking | MCPMark, MCP-Universe | Optional benchmark packs |
| Security scanning | Cisco Skill Scanner | Optional security extension |
| MCP isolation | ToolHive | Optional execution extension |
| Telemetry | OpenTelemetry + existing AEEP instrumentation | Reuse existing code |
| Advanced observability | Langfuse or Phoenix | Optional extension |
| Workflow execution | LangGraph | Optional orchestration |
| Workflow generation | EvoAgentX | Optional architecture proposer |
| Workflow optimization | AFlow | Optional optimizer |
| Routing | Existing AEEP Router | Preserve as optional extension |
| Developer compensation | GitHub Sponsors | Initial external support mechanism |

ToolHive's MCP isolation and AEEP's paired-trial worker isolation are separate
responsibilities. GitHub Sponsors is an external support link after developer
identity is verified; it does not require an AEEP payout service. Source review
and catalog presence are not working integrations. The executable manifest and
showcase expose an actual status for each row.

## First delivery stack

The operator selected the component assignments above and local CLI/report
delivery. The boundaries below implement those choices under D13, D16, D18 and
D20. Upstream real-host compatibility remains unverified; the table describes
the target stack rather than completed features.

| Layer | Software and responsibility | Implementation boundary |
|---|---|---|
| User interface | Local Python CLI; Pydantic for validated inputs | AEEP connects candidate intake, preview, evaluation and reporting. |
| Scripted evaluation | agent-skill-eval 0.7.0, source `59de161f657b82bfaf8f6abe83dfff38552deb21` | Connected upstream scheduler and graders dispatch fixed trials into separate AEEP workers. No model-value claim. |
| First managed-model evaluation | Existing AEEP AssessmentService + BenchmarkRunner (D40 fallback) | Selected after the installed upstream Codex parser/launch contract failed requirements. The integrated CLI reuses existing authority and execution and exports canonical reports. The integrated source `f3b7f50` passed full software verification. Authenticated V2 conformance remains open. |
| Actual agent | Codex first, using existing host integration | Preserve the normal tools in both arms. Host/model versions and settings must match. |
| Execution boundary | Docker and existing AEEP managed-worker/assessment-runtime assets | Separate control and treatment workers protect grading inputs. Actual scripted upstream dispatch and cleanup are recorded; native command inspection is separate from live conformance. |
| Review and accounting | Existing AEEP assessment definitions, finite allowances and receipts | Reuse current authority and recovery behavior; preserve historical records. |
| Evidence storage | Existing SQLite receipt store and content-addressed local artifacts | Normalize upstream evidence with source references; task contents remain transient by default. |
| Comparison | AEEP evidence checks and task-family analysis, reusing existing analysis helpers where applicable | Match conditions, handle missing measurements, compare verified success/time/tokens and supported costs. This is the product-specific work. |
| Report | Local static HTML and Markdown | Explain results, uncertainty, applicability, permissions and developer attribution. |
| Setup | Existing component setup/recovery plus pinned Python environments | Preview the selected dependency closure and configuration effects, then apply only the reviewed changes. |

The scripted adapter has demonstrated upstream dispatch through the existing
controlled boundary without constructing Router. Managed-model conformance
remains a separate gate. It does not justify extracting
Router services in advance or inventing another evaluation framework. Keep the
legacy runner as an explicitly recorded fallback; it does not automatically pass
Essentials' independence requirement.

## The user journey

1. Select a skill and the task families relevant to the user's work.
2. Inspect its source, required permissions and the complete selected setup.
3. Review the comparison plan: same agent, ordinary tools, task inputs, model,
   settings and verifier; the treatment adds optional access to the candidate.
4. Run the authorized trials in separate controlled workers and verify outputs.
5. Read a report showing task-family success, time, tokens, failures, available
   costs and uncertainty. Candidate exposure and invocation remain distinct.
6. Decide whether to enable the skill, restrict it to particular tasks, support
   its developer, or leave it unused. Publication is a separate action.

## Three selectable profiles

| Profile | Selected software | Purpose |
|---|---|---|
| Evaluation Essentials | AEEP CLI/evidence/reporting, agent-skill-eval and required controlled-worker support | Complete the skill-to-comparison-report journey. |
| Evaluation Toolkit | Essentials plus existing ARD/MCP Registry discovery, Cisco Skill Scanner, selected SkillsBench tasks and OpenTelemetry | Find candidates, inspect risk, broaden tasks and inspect trial traces. Each added component requires a working adapter. |
| Full Toolkit | Selectable evaluation, discovery, runtime, observability and orchestration extensions below | Assemble only the compatible components needed for a larger workflow. |

Full Toolkit keeps Waza and SkillRank as additional evaluation/search adapters;
MCPMark and MCP-Universe as task sources; Langfuse or Phoenix as optional trace
backends; and ToolHive as an optional MCP runtime. OpenSkillEval data remains
subject to its noncommercial license. None of these entries is currently qualified
for V2 merely because it appears in the catalog.

For workflow execution, integrate LangGraph where dynamic graphs are needed.
EvoAgentX and AFlow can supply optional workflow proposal/optimization, and
Microsoft Agent Framework remains a separately qualified workflow alternative.
Existing AEEP Router and StackRuntime remain optional consumers of approved
capabilities and evidence. Integration must preserve each engine's actual graph
semantics; unsupported behavior stays blocked. No duplicate graph engine,
optimizer, tracing server, registry service or payout system is part of this build.

## What works now

The [offline journey](../../examples/toolkit_offline/README.md) accepts captured
candidate bytes, previews the exact trial plan, dispatches the real
agent-skill-eval scheduler into six separate workers, verifies canonical receipts
and writes HTML/Markdown. The unified `aeep-toolkit eval scripted` entry point
completed that journey with default task-output retention disabled. The separate
Router-disabled replay proves this path does not construct Router.

The [managed bridge](MANAGED_EVALUATION.md) connects existing reviewed skill plans
to AssessmentService and BenchmarkRunner. It preserves their grants, workers,
grading and accounting, and reproduces canonical statistics before exporting
readable intervals, guardrails, costs and coverage. This implementation has
synthetic regression evidence and zero-turn native worker checks; it has no new
V2 authenticated-model comparison or efficacy result.

The general private installer handles selected, hash-locked wheel closures and
removes only an unchanged owned environment. The complete 33-wheel AEEP package
closure has passed artifact/dependency inspection; its bounded installation test
awaits the exact operator review. The separate 24-wheel agent-skill-eval runtime
already has recorded installation and fixture-execution evidence.

Existing registry readers and OpenTelemetry instrumentation remain the optional
discovery and telemetry foundations. A local discovery replay confirms inert
results, recorded provenance and unavailable/unauthorized-source rejection. Waza,
Cisco scanning, hosted telemetry and external workflow integrations still need
their own executable qualification. Catalog presence is not that qualification.

## Withdrawn proposal

The implementation agent proposed extracting shared execution/evidence services
from Router before testing the external evaluator, and asked the operator to
choose extraction or a temporary legacy backend. That question omitted the
preferred external integration path and is withdrawn following the operator's
correction. No extraction was implemented, and no answer to that question is
needed. The [legacy source audit](../../reports/toolkit-v2/c04/extraction-audit.json)
records coupling, not a justification for a new execution architecture.

## Next implementation proof

Complete the exact reviewed private package installation/removal after the
pending operator response. Then bind the exact live study to the existing
canonical grant and current authenticated worker conformance. Routine finite
scope/budget amendments are already delegated; do not invent a new architecture
or budget-approval blocker. Credentials, wider disclosure, cash and release retain
their own boundaries. Independent optional-extension work continues meanwhile.

## First managed-model backend: recorded fallback

D40 selects the existing AEEP AssessmentService/BenchmarkRunner for the first
managed-model adapter after executable checks reproduced upstream missing-usage
and worker-binding gaps. The actual agent-skill-eval scripted integration remains
available. The fallback reuses existing controlled Codex execution, grading,
reservations and receipts; it does not add a runner or new infrastructure.
A follow-up audit found a related partial-usage bug in AEEP's App Server adapter,
which D41 corrected and regression-tested. No V2 live comparison has started.

The integrated adapters retain this boundary: Waza/Cisco JSON imports are inert,
LangGraph's finite graph runs wholly inside CommandExecutor, and OTLP preparation
uses existing telemetry without a service. Toolkit discovery calls existing
readers with configured source authority. The wheel ships the existing scripted
bridge as data assets; installed verification hashes actual code/assets rather
than an absent checkout. Exact upstream executable evidence and exclusions are
linked from `reports/toolkit-v2/integration-completion/README.md`.
