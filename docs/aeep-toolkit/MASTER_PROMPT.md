# AEEP Evaluation Toolkit V2 — one-time Codex master steering prompt

**Repository:** [AEEP-router](https://github.com/ptse8204/AEEP-router)

**Purpose:** A long-lived, checkpointed product rearchitecture plan.  
**As-of:** October 8, 2026. Confirm current repo and upstream releases before executing.  
**Original handoff status:** Planning instructions only. This bundle was imported on October 8, 2026; [STATE.md](STATE.md) records subsequent implementation. The instructions below remain the product plan.

You are Codex, the primary implementing agent for this repository. Carry out a scoped, incremental rearchitecture of AEEP into **one modular plugin-value evaluation toolkit**. Do not expect new prompts from the owner after each milestone. Use durable on-disk checkpoint files as the project record, and actively continue through safe eligible checkpoints while this Codex session is running. Do not claim work continues asynchronously after the session ends. If authorization, unknown third-party effects, or spending blocks a checkpoint, record exactly what is needed and work on independent safe tasks.

## 1. North star — non-negotiable product definition

AEEP was conceived to let users and developers **understand and demonstrate the value of adding a specific plugin/skill/tool to an already capable AI agent**. Users should see what tasks improve, tokens saved or added, wall-clock time saved or added, verified success and reliability changes, permissions, cost/price implications and uncertainty. Developers need attributable evidence and legitimate ways to receive value (e.g., authorized sponsorship or purchase), not a speculative token-transfer network.

The router, stack orchestrator, marketplace browser, security scanning, profiling, payment adapters and automated architecture generation are **supporting modules or optional AEEP extensions**. Do not make them required to test a skill. Do not abandon useful existing functionality: move it behind versioned extension boundaries where possible and maintain backward compatibility. Do not build a general-purpose planner or a duplicate LangGraph/EvoAgentX/Waza/Langfuse/SkillRank if a small tested adapter works. The value of the product is credible, reusable **comparison evidence plus an understandable decision**, not the number of installed tools.

A user's first complete journey should be: give a candidate `SKILL.md` path or GitHub reference -> inspect candidate and environment -> preview all components/permissions and experiment expenses -> review/authorize a controlled evaluation -> compare normal agent without vs with optional access to candidate -> verify outputs independently -> report task-family quality/tokens/time/cost/uncertainty and developer link. The user may decide **do not install**. Support MCP/tool/plugin evaluation through later extension adapters rather than pretending all formats are equivalent on day one.

## 2. Read real repo policy before anything else

Start with repository files `AGENTS.md`, `docs/ASSESSMENT_TESTING.md`, `SPEC.md`, `ARCHITECTURE.md`, `SECURITY.md`, `docs/ASSESSMENT.md`, `docs/EVIDENCE.md`, `docs/EVIDENCE_REUSE.md`, `docs/ONBOARDING.md`, `docs/STACK_PLANNING.md`, `reports/v08/plan-coverage.md`. Their existing security/authority/evidence constraints prevail over this planning prompt. The product steering here **does not expand** earlier delegated benchmark spending, credential, install, publication or release authority.

Also read every file in `docs/aeep-toolkit/`, especially `README.md`, `STATE.md`, `CHECKPOINTS.md`, `CONTINUATION.md`, `UPSTREAM_MATRIX.md`, `ACCEPTANCE.md`, `INSTALLATION_DESIGN.md`, `DECISIONS.md`. Those are now the development steering specification. Confirm all paths are committed in the working branch. If any are missing, recreate them from the supplied plan bundle, not from conversational memory.

Use a dedicated feature branch off a verified current main SHA, preserve unrelated changes, all historical receipts and tests. Do not rewrite AEEP 0.8's past verification records. Stay in the monorepo unless a defensible package boundary specifically requires extraction. This plan favors refactoring/retaining tested code rather than destructive rewrite. A dry run must not silently mutate host state. Never confuse local temporary directories with full execution isolation, or filtered tool exposure with permission enforcement.

## 3. Technical architecture to implement

### AEEP-owned minimal core

- A versioned **extension manifest + capability registry**, stating purpose, source/hash, license/data rights, host/OS compatibility, dependency/version constraints, permissions, authentication, disk/memory needs, runtime/financial exposures, status and rollback.
- A common **EvaluatorAdapter** interface, so existing assessment runners, agent-skill-eval, Waza and others can return evidence without custom product-level logic for each backend.
- A **normalized evidence contract** for candidate version + exact host/model/effort/configuration + workload + control/treatment + verification + raw token/time/cost/error observations + provenance and uncertainty. Reuse existing AEEP receipt persistence and OpenTelemetry semantics wherever suitable; avoid a second general-purpose event database.
- An **evidence comparison engine**: trustworthy differential task success, tokens, latency, retries, and real cost per verified success. Detect non-comparable environments and missing telemetry. Interpret task-specific benefit, regression, no demonstrated difference, inconclusive and not assessed; never choose positive merely because tokens decreased.
- A **local HTML/Markdown report** and CLI presenting results simply enough for users deciding whether to install/pay, with verified developer identity and optional authorized support link.
- One **preview-first installation experience** across three profiles (Essentials, Evaluation Toolkit, Full Toolkit), showing the *entire* resolved selected stack and all install/permission/billing changes before applying anything.

**Optional AEEP extensions**, with real version/compatibility checks: existing AEEP router/stack code, Waza, SkillRank core, MCP registry/ARD and other catalogs, Cisco Skill Scanner, SkillsBench/MCPMark/MCP-Universe task fixtures, OpenSkillEval reference material (data license check!), OpenTelemetry exporters/Langfuse/Phoenix, ToolHive, LangGraph, EvoAgentX, AFlow, Microsoft Agent Framework, developer payment adapters. The Full Toolkit should list and selectively allow these, not download/activate everything by default. Explicitly mark incompatible/unqualified/paid entries and why they cannot run.

Keep adapter boundaries narrow: prefer pinned subprocess JSON/JSONL/CLI or stable SDK methods over vendoring whole frameworks. New dependencies should be optional groups/processes and should not increase minimal CLI cold-start or host footprint substantially. Retire duplicate AEEP infrastructure **only after** the replacement passes tests and migration/rollback has been verified.

## 4. Mandatory upstream make-or-buy investigation

Inspect source, documentation, actual interfaces, releases, licenses, dependencies and supported metrics of:

- [agent-skill-eval](https://github.com/tardigrde/agent-skill-eval): candidate first real-host Codex/Claude skill evaluator. Check its container separation, natural selection, grading, token sources and run artifacts; don't assume temporary git checkouts meet AEEP's controlled-worker isolation.
- [Microsoft Waza](https://github.com/microsoft/waza): evaluation and test scaffolding; verify Copilot SDK and real Codex portability, not its marketing claim.
- [SkillRank core](https://github.com/buildbetter-app/skillrank): search/evaluation; separate MIT open-source CLI/core from the separately licensed Elastic-2.0 hosted registry; forced-use trials do not alone establish autonomous selection value.
- Existing AEEP BenchmarkRunner; benchmark sources [SkillsBench](https://www.skillsbench.ai/), [MCPMark](https://github.com/eval-sys/mcpmark), [MCP-Universe](https://github.com/SalesforceAIResearch/MCP-Universe) and [OpenSkillEval research](https://arxiv.org/abs/2605.23657). Confirm code vs noncommercial-data permissions.
- [Cisco Skill Scanner](https://github.com/cisco-ai-defense/skill-scanner), [OpenTelemetry](https://opentelemetry.io/), [Langfuse](https://github.com/langfuse/langfuse), [Phoenix](https://github.com/Arize-ai/phoenix), [ToolHive](https://github.com/stacklok/toolhive), [LangGraph](https://github.com/langchain-ai/langgraph), [EvoAgentX](https://github.com/ANative-Lab/EvoAgentX), [AFlow](https://github.com/FoundationAgents/AFlow), [Microsoft Agent Framework](https://github.com/microsoft/agent-framework).
- Existing discovery/integration/installation code (ARD, MCP Registry, Claude/Codex and DeepSeek Harness connections) and existing economic/developer attribution logic.

For every component produce KEEP, REUSE, WRAP, REPLACE, ARCHIVE or DEFER, and explain why reuse actually reduces maintenance/security/stack cost. Fix exact compatible versions/revisions only after inspection. Do not use mutable HEAD installers or unreviewed lifecycle scripts. One proven evaluator first; do not install all candidates to compare READMEs.

## 5. Evaluation methodology is the product contract

For each paired value trial, compare the exact same normal agent setup and ordinary tools: CONTROL without candidate; TREATMENT with candidate *available, not forced*. Keep same task, prompt, model/effort, harness and versions, run ceiling, ordinary competing tools, fixtures, verifier, execution permissions and environmental conditions. Inspect effective exposure vs actual invocation; failing to invoke a plugin is part of the value result, not a reason to force it. Forced calls can be separately labeled diagnostics/qualification.

Protect independent verifiers, holdout cases, private user data and credentials from tested agent. Use reviewed controlled workers, reset workspaces and captured environment fingerprints. Include trivial, complex and unrelated/negative tasks, with developer-authored and independent tasks distinguished. Pre-register outcomes, trials, budgets, randomization/order and acceptance before a holdout; don't adjust after seeing failure. No arbitrary untrusted binary/plugin execution without bounded reviewed containment.

Record provider-reported input/output/cached/reasoning tokens with source semantics and coverage, not an invented sum; execution time, verification time and setup time separately; known actual charges vs model-rate estimates vs subscription-unpriced vs unknown; failure/retry, usage and quality. Cost per verified success counts failures and retries; if missing price or zero successes, say N/A. A fixed subscription's reduced tokens are not automatically dollar savings. Calculate matched per-task and task-family differences with sample size/uncertainty; expose negative findings. Distinguish engineering fixtures from completed live model experiments. See `ACCEPTANCE.md` for exact cases and formulas.

## 6. Checkpoint roadmap (run all safe eligible stages in order)

The authoritative detailed exit gates are in `CHECKPOINTS.md`:

- **C00 Inventory and baseline:** Git/host state, module map, current policy and test evidence.
- **C01 Replacement research:** pinned/licensed upstream matrix; make-vs-buy decisions and chosen first evaluator candidate/fallback.
- **C02 Versioned contracts:** extension manifests, result schemas, provenance, invalid-value rejection, legacy migration.
- **C03 Installation preview:** three profile manifests, full transitive stack and exact effects preview; no mutation until approved.
- **C04 Eval engine spike:** verify one real-harness evaluator compatibility, natural choice, isolation, error accounting; implement thin adapter.
- **C05 Comparative engine and report:** robust metrics, missingness, task slices, provenance, economics, developer links, local HTML/Markdown.
- **C06 Offline Essentials E2E:** one user flow with real installed code and controlled no-charge fixtures, no optional router/hosts/services mandatory; legacy regressions green.
- **C07 Live verification gate:** pre-registered genuine Codex with/without task study, **only within separately approved cost/credential/runtime authority**; negative/no-effect cases; never fake success from fixtures. If blocked, record and continue C08-C12 without implying it passed.
- **C08 Discovery and security pack:** existing registries + optional SkillRank/Cisco scanner, inert search and truthful risk claims.
- **C09 Additional evaluator/benchmark packs:** Waza/SkillRank/SkillsBench/MCPMark/etc. only after proven adapters and licensing.
- **C10 Observability/isolation pack:** OTel export, optional Langfuse/Phoenix/ToolHive; no mandatory hosted service or magical sandbox claims.
- **C11 Routing/orchestration pack:** existing AEEP Router/StackRuntime plus optional LangGraph/EvoAgentX/Microsoft/AFlow; static vs dynamic graph limits explicit.
- **C12 Developer support and evidence publication:** consent-based privacy-minimized reusable evidence, verified attribution, external sponsor/purchase links. No novel internal payout ledger initially.
- **C13 Beta and go/no-go:** supported host installers, compatibility/rollback, measured overhead, user comprehension and competitive comparison. Real-benefit and release gates separately stated; do not auto-publish.

C00-C06 are the initial critical path. Do not block them on Full Toolkit or payments. Stages C08-C12 should be implemented only to the extent supported by verified components and warranted effort; declare unsupported entries in the Full Toolkit accurately. All stages have objective, artifact, dependencies and explicit exit tests in `CHECKPOINTS.md`. Avoid calendar estimates. Do not mark PASS because a unit test or doc exists when the gate needs a live human or provider test.

## 7. Durable automatic handoff and context-window discipline

Use `docs/aeep-toolkit/STATE.md` as **authoritative progress**, and `CONTINUATION.md` for resume procedure. After every checkpoint (and periodically for long ones), commit durable, self-contained state including: current base/commit, checkpoint status, produced files, tests + exact commands/results, what passed/failed/skipped, source/version pins, known blockers, permission/budget gates, next instruction. Keep an append-only checkpoint journal and a `DECISIONS.md` trail. Don't trust chat summaries over repo commits and artifacts. Re-read status after compaction. Verify reports against pinned implementation; mark stale results STALE after source drift.

Do not ask the owner to approve each normal implementation stage; make grounded independent choices, record rationales and continue. Ask only for actual external authorization or a materially irreversible product decision. Never assert you can keep working while no Codex session is executing. Do not silently bypass a paid/live or unsafe gate; record it BLOCKED and work on independent safe steps.

At the end of any session, provide a concise current checkpoint/state, actual changes and test evidence, blockers, and next work. At the start of a new Codex session, re-read state and continue. Prefer local commits by checkpoint; pushing feature branch/publication requires normal repo permissions and explicit authorization.

## 8. Required testing and implementation rules

Follow existing `AGENTS.md` checks after changing code (compile, schema validation, pytest, branch coverage; documentation checks as appropriate). Preserve historical evaluation policy, hard constraints before scoring, argv-only command execution, no credentials logged, no hidden cash/permitted scope expansion, no output file leakage, exact artifact and adapter fingerprints and recovery semantics. Monitor installation footprint and source-defined host resource reserves. Check input/output/schema compatibility, versions and migrations. Test install preview/rollback, unknown telemetry, regression despite token savings, 0 successes, task-family reversal, candidate not invoked, negative controls, host mismatch, interrupted trials, duplicate side effects and source drift.

If a third-party engine doesn't meet the current containment or instrumentation requirements, do not mark the corresponding strict gate PASS. Either wrap in reviewed existing AEEP controlled-worker boundary, keep the native verified runner, or mark the backend experimental and unqualified. Do not let vendor integrations dictate new always-on services, hosted registries or a shared payments database.

## 9. Milestone deliverables and product acceptance

Place code/tests in existing idiomatic paths; keep these docs under `docs/aeep-toolkit/`; store sanitized, version-pinned checkpoint evidence in `reports/toolkit-v2/` (avoid raw secret/task data). Add a thin status/CLI interface with appropriate help. Deliver a package/installer preview that shows every selected extension and its transitive effects; a working `SKILL.md` comparison integrated with one real evaluator; normalizer and economic comparison tests; human-readable per-task report; optional extension catalog/status; clear migration mapping from old modules; safe rollback and docs; and an honest list of unimplemented or unqualified extension entries.

The ultimate success is that a normal user can decide whether a candidate plugin is worth installing or paying for, and a developer can demonstrate independently reproducible impact. If existing software completely meets a feature, prefer integrating it and removing duplicate complexity. If the independent value-evidence layer fails to improve user outcomes against existing evaluators, report that honestly and recommend reuse/upstream contribution rather than expanding architecture to justify AEEP.

## 10. Start now and keep going within the current session

1. Inspect the current checkout and create a non-destructive feature branch if needed. Confirm all `docs/aeep-toolkit/` files exist and read current authority and state.
2. Begin C00. Produce the inventory and baseline verification evidence; update `STATE.md` and commit checkpoint records.
3. Proceed directly to C01, then onward for as many safe gates as can be genuinely completed. Do not finish after only drafting a new plan unless a real blocker prevents implementation.
4. Mark each checkpoint with exact evidence, blockers and next step; maintain the checkpoint journal before any context reset.
5. At the end, provide one factual checkpoint status and what actually changed. Do not ask me to come back to ChatGPT for the next steering prompt.
