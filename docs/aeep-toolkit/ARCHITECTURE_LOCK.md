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
| Evaluation engine | agent-skill-eval 0.7.0, source `59de161f657b82bfaf8f6abe83dfff38552deb21` | Reuse upstream trial scheduling, skill setup, harnesses and grading/artifact interfaces through a small adapter. |
| Actual agent | Codex first, using existing host integration | Preserve the normal tools in both arms. Host/model versions and settings must match. |
| Execution boundary | Docker and existing AEEP managed-worker/assessment-runtime assets | Separate control and treatment workers; protect grading inputs. External-harness dispatch integration must be proven. |
| Review and accounting | Existing AEEP assessment definitions, finite allowances and receipts | Reuse current authority and recovery behavior; preserve historical records. |
| Evidence storage | Existing SQLite receipt store and content-addressed local artifacts | Normalize upstream evidence with source references; task contents remain transient by default. |
| Comparison | AEEP evidence checks and task-family analysis, reusing existing analysis helpers where applicable | Match conditions, handle missing measurements, compare verified success/time/tokens and supported costs. This is the product-specific work. |
| Report | Local static HTML and Markdown | Explain results, uncertainty, applicability, permissions and developer attribution. |
| Setup | Existing component setup/recovery plus pinned Python environments | Preview the selected dependency closure and configuration effects, then apply only the reviewed changes. |

The engine adapter must demonstrate that the upstream runner can use the existing
controlled boundary without pulling optional Router configuration into Essentials.
That is a bounded integration question to test. It does not justify extracting
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

## What exists and what is being built next

The independent contracts, partial non-mutating setup preview and an executable
[development stack](../../integrations/toolkit/README.md) exist. The development
stack uses the actual pinned external package, verifies its fixed synthetic trials
and writes the [local showcase](../../reports/toolkit-v2/stack-showcase/index.html).
The fixed synthetic batch now uses the existing command executor, selection
decision, journal and receipt store, and exports C02 evidence. General V2 evaluator
dispatch, per-trial worker receipts, controlled real-agent comparison and the
complete installation journey remain unfinished.

The next product deliverable is one continuous, fixture-labeled journey from
candidate input through the actual upstream evaluator to an AEEP comparison
report. The prepared upstream fake-harness run is the first integration check in
that work, not the completed deliverable. Real-host qualification and a separately
authorized live study follow; synthetic results cannot establish plugin benefit.

## Withdrawn proposal

The implementation agent proposed extracting shared execution/evidence services
from Router before testing the external evaluator, and asked the operator to
choose extraction or a temporary legacy backend. That question omitted the
preferred external integration path and is withdrawn following the operator's
correction. No extraction was implemented, and no answer to that question is
needed. The [legacy source audit](../../reports/toolkit-v2/c04/extraction-audit.json)
records coupling, not a justification for a new execution architecture.

## Next implementation proof

The bounded engineering spike now runs agent-skill-eval's existing fake harness
and deterministic graders through the consolidated development stack. Inspect its actual control/treatment
artifacts, optional exposure, failures and missing telemetry before writing the
small adapter. Retain upstream orchestration where it works. Add only the AEEP
validation and controlled-worker integration that the acceptance gates require.

External execution needs the exact reviewed scope. Fixture success will not
qualify host isolation, establish model savings or close C07. Broad internal
refactoring is not a prerequisite for preparing or reviewing this spike.
