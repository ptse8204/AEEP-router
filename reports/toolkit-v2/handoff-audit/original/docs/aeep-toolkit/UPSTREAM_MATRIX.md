# Upstream replacement and extension-candidate matrix

**Important:** This is a research *candidate list*, not an assertion of qualified compatibility, safe packaging, version locks or release licenses. For each row C01 must inspect exact repository/release, dependencies, CLI/API, transitive/data license, host behavior and runtime confinement. Put observed versions/SHAs in the table; do not guess from project names.

| Responsibility | Candidate and official source | Suggested role | Initial risks / proof required | C01 status |
|---|---|---|---|---|
| Native skill value tests | [agent-skill-eval](https://github.com/tardigrde/agent-skill-eval) | First evaluator adapter candidate for Codex/Claude/OpenCode | Verify real CLI/version, natural-selection flags, reported usage, isolation vs AEEP's controlled-worker policy, hooks, failure/cost behavior | UNQUALIFIED |
| Skill eval + task scaffolding | [Microsoft Waza](https://github.com/microsoft/waza) | Optional evaluator and generated task pack | Verify Copilot SDK/backend dependence, metrics, licensing, CLI and host support | UNQUALIFIED |
| Skill search/eval/publish | [SkillRank core](https://github.com/buildbetter-app/skillrank) | Optional local skill catalog/evaluation backend | Core CLI MIT; hosted registry/website separately Elastic License 2.0; forced-mode primary eval not adequate for natural selection; inspect integration/version | UNQUALIFIED |
| Existing AEEP runner | `src/aeep/assessment/`, `benchmarking.py` | Reuse if other evaluators insufficient | Real AEEP containment, evidence/reviewer gates, integration cost | LOCAL AUDIT REQUIRED |
| Reusable benchmark tasks | [SkillsBench](https://www.skillsbench.ai/) | Optional task/benchmark pack | Exact benchmark version, task/grader license, heldouts, approved fixtures | UNQUALIFIED |
| MCP task benchmark | [MCPMark](https://github.com/eval-sys/mcpmark) | Optional MCP benchmark pack | Confirm current canonical repo/source, verifier containment and real MCP authority | UNQUALIFIED |
| MCP development/eval | [MCP-Universe](https://github.com/SalesforceAIResearch/MCP-Universe) | Optional extra benchmark source | Expensive/heavy setup, benchmark-to-user-task transfer | UNQUALIFIED |
| Generalized skill evaluations | [OpenSkillEval paper](https://arxiv.org/abs/2605.23657) | Research benchmark/method reference, optional pack | Verify official code repository, benchmark data terms; noncommercial data may restrict bundling | UNQUALIFIED |
| Skill safety checks | [Cisco AI Defense Skill Scanner](https://github.com/cisco-ai-defense/skill-scanner) | Optional scanner | License, package size, version, false negatives; scan != containment | UNQUALIFIED |
| Discovery | [Official MCP Registry](https://github.com/modelcontextprotocol/registry) + existing AEEP ARD/catalog adapters | Optional discovery sources | Search is inert, ecosystem API/version drift, avoid transmitting private prompts | EXISTING AEEP ADAPTERS; REVALIDATE |
| Tracing conventions | [OpenTelemetry](https://opentelemetry.io/) + AEEP telemetry | Use existing instrumentation inside core, optional exporters | Exact genAI semconv version/units; cardinality, privacy, source completeness | PARTIALLY EXISTING |
| Tracing/evals backend | [Langfuse](https://github.com/langfuse/langfuse) | Optional external observability backend | Hosted/self-hosted requirements; MIT core vs separately licensed enterprise components; privacy | UNQUALIFIED |
| Alternative trace backend | [Arize Phoenix](https://github.com/Arize-ai/phoenix) | Optional, not simultaneous mandatory dependency | Check version/license, storage/system requirements | UNQUALIFIED |
| MCP gateway & isolation | [ToolHive](https://github.com/stacklok/toolhive) | Optional MCP runtime/registry | Actual auth/network/filesystem isolation, container deps, host support | UNQUALIFIED |
| Multi-agent workflow runner | [LangGraph](https://github.com/langchain-ai/langgraph) | Optional workflow adapter | Dynamic loops differ from static AEEP DAG; prevent bypass of AEEP authority | UNQUALIFIED |
| Dynamic workflow proposer | [EvoAgentX](https://github.com/ANative-Lab/EvoAgentX) | Optional architecture proposer | Generated code execution risks, paid planning budget, schema conversion | UNQUALIFIED |
| Workflow optimizer | [AFlow](https://github.com/FoundationAgents/AFlow) | Optional offline optimizer (or reuse via EvoAgentX) | Experiments costly; task verifiers and safe code isolation | UNQUALIFIED |
| Alternative orchestration | [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) | Optional executor | Verify SDK API/version/host support and permission boundary | UNQUALIFIED |
| Legacy policy routing | Existing `src/aeep/router.py`, `stack_planning.py`, `stack_runtime.py` | Keep as optional AEEP extensions | Existing evidence, serial DAG, backwards compatibility | EXISTING; MODULE BOUNDARY REQUIRED |
| Alternative governance | [Archestra](https://github.com/archestra-ai/archestra) | Research competitor or external integration | AGPL/enterprise code and deployments; not default bundled replacement | DEFERRED |
| Developer support | [GitHub Sponsors](https://github.com/sponsors) | External authorized support link | Identity, fraud, payout eligibility; do not assert cash/token transfer | EXTERNAL LINK ONLY |

## C01 required decision worksheet (complete for every mandatory candidate)

- Canonical upstream URL, release and commit SHA; last maintenance, open issues relevant to selected integration.
- License of code, benchmark datasets, registry, assets and transitive packages, with compliant redistributability summary.
- Exact host CLI/SDK versions supported, OS, architecture and authentication model; verify in installed environment.
- Exposed entry point: library import, subprocess CLI with machine output, JSONL protocol, MCP or HTTP.
- Supported candidate types: `SKILL.md`, MCP, plugin bundle, API, arbitrary executable (not all should be assumed equivalent).
- Comparison semantics: natural selection vs forced; ordinary tools visible to both arms; controls for state, outputs, evaluator independence, permissions and context.
- Observed metrics and missingness: token categories, wall clock, source, actual/estimated cash, retries, failures, tool exposure/usage.
- Side-effect containment, setup/teardown, crash/restart, parallelism, resource limits, test cost.
- Dependency footprint and user install preview data; rollback/uninstall constraints.
- Integration proof: offline conformance or real-host evidence and exact logs; status YES/NO/UNKNOWN, not marketing copy.
- Final choice: REUSE (existing AEEP), WRAP (external), REPLACE, KEEP, ARCHIVE, or DEFER, with rationale, risks and migration plan.

## Principle

A package being open source does not imply its hosted service, datasets, benchmark tasks or pretrained assets can be bundled or sold. Optional adapters can interface with externally installed software without redistributing its implementation; still check interface terms and user consent.
