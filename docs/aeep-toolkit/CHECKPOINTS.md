# Checkpoint roadmap — AEEP evidence-first evaluation toolkit

**Read `STATE.md` first.** The entries below are required delivery/acceptance gates, not claims of completion. `TODO` is the default until independently evidenced. Stages can be worked on within one Codex session; update durable progress and commit each finished gate. Do not require the owner to resupply prompts after every stage.

**Status vocabulary:** `TODO`, `IN_PROGRESS`, `PASS`, `BLOCKED` (explicit unmet dependency), `DEFERRED` (operator explicitly defers), `STALE` (evidence doesn't apply to current code). A checkpoint passes only when all required exit checks pass and the relevant files/artifacts/commands are recorded in `STATE.md`. Maintain separate labels `OFFLINE`, `HOST_CONFORMANCE`, `LIVE_VALUE`, `HUMAN_USABILITY`, `RELEASE`—success in one is not evidence for another.

## Critical path — first actually useful evaluation product

### C00 — Snapshot, constraints, and current AEEP inventory

**Dependencies:** none.
**Do:** Create/resume a feature branch, observe current main SHA, worktree cleanliness, Python/platform and test environment. Read `AGENTS.md`, `docs/ASSESSMENT_TESTING.md`, `SPEC.md`, `ARCHITECTURE.md`, `SECURITY.md`, `docs/ASSESSMENT.md`, `docs/EVIDENCE.md`, `docs/ONBOARDING.md`, `docs/STACK_PLANNING.md`, `reports/v08/plan-coverage.md`. Inventory modules/dependencies/CLI, background processes, installer state, historical tests, accounting constraints and current supported hosts. Run the existing non-metered verification commands per policy (record environment/exact failures; do not erase prior results). Capture base SHA.
**Exit:** `docs/aeep-toolkit/INVENTORY.md` maps modules (KEEP/REUSE/WRAP/REPLACE/ARCHIVE), risk/owners/import dependencies and evidence of actual behavior; baseline test/quality outcome recorded; no unrelated files changed; history intact.
**If blocked:** Record missing local tools and explicit reproduction commands; proceed with source-only audit but leave baseline gate BLOCKED.

### C01 — Upstream competitive replacement matrix and make-vs-buy ADR

**Dependencies:** C00 source inventory available.
**Do:** Verify up-to-date repositories, licenses (including data vs code), maintenance, supported OS/hosts, eval methodology, version pins, integration mechanism, runtime isolation, exposure, token/time/cost completeness, expense/footprint, and install/rollback. Compare agent-skill-eval, Waza, SkillRank core, current AEEP BenchmarkRunner for first evaluator. Inspect Cisco scanner, official MCP Registry/ARD, MCPMark/MCP-Universe, SkillsBench, OpenSkillEval, OpenTelemetry, Langfuse, ToolHive, LangGraph, EvoAgentX, Microsoft Agent Framework, AFlow, and existing router as optional packs. Identify already-implemented native-host functionality that should not be reimplemented.
**Exit:** `UPSTREAM_MATRIX.md` has exact source+license+compatibility facts, current pins, a preferred evaluator **candidate** and 1 fallback, clear evidence gaps, and rearchitect/reuse decisions in `DECISIONS.md`. A component is not considered qualified because its README says it supports a feature.
**If blocked:** Preserve UNKNOWN fields; do not invent a pin or compatibility assertion.

### C02 — Freeze narrow core contracts and extension interface

**Dependencies:** C01 decisions documented.
**Do:** Design stable/versioned `ExtensionManifest`, `AdapterCapabilities`, `EvaluationRun`, `EvidenceBundle`, `ComparisonReport` and developer identity contracts. Prefer existing data models/storage and OpenTelemetry conventions. Separate candidate capabilities from AEEP extensions; eval runners from graders; verifier results from self-claims; observations from estimates. Document how tasks, host/model settings, artifact hashes and exposure states bind a comparison. Add schema validators and test fixtures, maintaining migrations to existing persistence if needed.
**Exit:** schemas/tests reject malformed versions, missing provenance, counterfeit actual-cost claims, double-counted cached tokens, unsupported telemetry, incompatible host adapters, unclear install permissions; schema changes don't break legacy receipts. Core has no required orchestration/marketplace/payment/server dependencies.

### C03 — Install inventory and entirely non-mutating preview

**Dependencies:** C02 extension manifest.
**Do:** Wrap existing `component_setup` / `onboarding`/install machinery. Create profile manifests `Evaluation Essentials`, `Evaluation Toolkit`, `Full Toolkit`. Show direct and transitive dependencies, exact versions/hashes, current installed/enabled state, license & redistributed-data restrictions, permission/network/filesystem/secret requirements, expected disk/memory, provider charges, side effects, rollback, and blocked/unknown status. Dry-run/plan modes MUST do zero install/network execution apart from explicitly allowed read-only metadata lookups and must not mutate host configs. User selects exact components; Full lists all supported choices, NOT an implicit bulk-install.
**Exit:** golden-file test of honest preview; disabled/unsupported extension never installed; installer aborts before effects on conflicting license, platform, scope or cost; no secrets in preview. Record before/after filesystem/config snapshots for dry-run.

### C04 — Qualify and integrate one real-harness evaluation adapter

**Dependencies:** C02 and candidate evaluation research C01.
**Do:** Run a tightly bounded local capability spike comparing `agent-skill-eval`, Waza, SkillRank and existing AEEP runner **without unnecessary paid calls**; use fake/replay harnesses for engineering tests, real CLI and controlled worker where allowed for actual conformance. Choose simplest working backend; implement `EvaluatorAdapter` (normalized run events, host/model pins, control/treatment, error and timeout), leaving other backends separate extension entries. Ensure natural-selection experiments differ only by candidate exposure. Check containment against `docs/ASSESSMENT_TESTING.md`; transient repo clones alone don't count as isolated workers. If upstream cannot satisfy isolation/metrics or current host version, retain AEEP's verified runner or build a small shim, not a second framework.
**Exit:** tests demonstrate both arms, exact subject/version, intact normal toolset, no forced invocation for primary tests, same prompt/fixture/grader, no leaked answers/credentials, deterministic failure/timeout handling, traceable token/time observations (or correct unavailable), and honest worker-conformance status. No live efficacy claim yet.
**If blocked:** Record which runner behavior or safety requirement cannot be met; switch only after a recorded comparison decision, never silently after a failed campaign.

### C05 — Comparison math, validity checks and trustworthy reports

**Dependencies:** C02 schemas, C04 standardized fixtures.
**Do:** Build the differentiating AEEP logic: matched-cohort aggregations; pass/fail/skip/missing graders; run cost vs eval cost; token categories and sources; end-to-end agent wall time; task-family slices; uncertainty and sample-size caution; cost per verified success; value-per-task/break-even when real billing and plugin price exist; authorized developer identity/support. Generate local Markdown and static HTML, avoiding hosted stack dependencies.
**Exit:** precision/unit/property tests cover: (a) fewer tokens but worse success, (b) cached/reasoning token overlaps, (c) zero successes, (d) unknown costs, (e) missing exposure, (f) missing result, (g) recurring plugin fee, (h) host/model/version mismatch, (i) long-tailed runtimes. Reports include no invented cash savings and allow BENEFIT/REGRESSION/NO_DEMONSTRATED_DIFFERENCE/INCONCLUSIVE/NOT_ASSESSED.

### C06 — Evaluation Essentials: first offline end-to-end user journey

**Dependencies:** C03 preview, C04 runner adapter, C05 report.
**Do:** One command/config flows: choose `SKILL.md` candidate -> show setup/approval preview -> run approved, deterministic no-charge control/treatment fixtures in isolated/tested boundary -> verify outputs -> emit source-grounded report. Include at least a trivial edit, a complex edit, and an adjacent negative-control task (fixtures may be synthetic; label prominently). CLI basics: `aeep toolkit list`, `aeep toolkit plan`, `aeep eval plan`, `aeep eval run` (only when authorized), `aeep eval report` — exact names may adapt to actual CLI to minimize breakage. Keep existing AEEP CLI working. Include `doctor` and non-destructive uninstall checks.
**Exit:** Complete repeatable offline demonstration with saved artifacts and CLI transcript; `Essentials` works without router, LangGraph, Waza, ToolHive, Langfuse, marketplace, or payments. All current repository required checks and docs checks pass, with failures explicitly retained. No claims of real model savings from synthetic outputs.

## Evidence gate

### C07 — Controlled real-host comparative value pilot

**Dependencies:** C06 offline working and actual host/worker conformance.
**Do:** After explicit operator-approved model/billing budget, pre-register 3 task families (easy, complex, adjacent/no benefit), matching prompts, environment, model/effort, host version, ordinary tools, verifiers, caps, trial count, randomized/balanced order, primary endpoints (verified success/time/tokens), minimum effect of interest and stop rules. Freeze holdouts. Execute natural-selection CONTROL vs TREATMENT through genuine Codex host inside reviewed controlled environments. Measure plugin discovery/exposure and full relevant resource consumption. Keep assessment spend and time separately from production savings. Include negative and inconclusive findings.
**Exit:** Raw signed/hashed evidence and readable report with actual host version, run outcomes, telemetry provenance, missing values, costs, confidence, fairness, and adjudication. If not enough trials or measurement quality, state `INCONCLUSIVE` / `BLOCKED`, not PASS for efficacy. Campaign completion may be PASS while demonstrated positive benefit is NOT ESTABLISHED.
**Hard barrier:** No paid/live requests, authentication capture, broad filesystem/network privileges or third-party plugin execution without current specific authority. If blocked, continue C08-C12 offline; C13 production-efficacy gate remains open.

## Modular ecosystem beyond the critical path

### C08 — Optional discovery and security packs

**Dependencies:** C03 extension contract and installer.
**Do:** Wrap existing ARD/MCP Registry/marketplace readers, optionally SkillRank core search, and Cisco Skill Scanner as an optional pack. Discovery is inert; a scanner finding is evidence/risk advice, not proof of safety. Demonstrate permission diff and provenance. Maintain search failure/cached-source limits.
**Exit:** An uninstalled discovery pack is unavailable; installed pack can list candidates without executing candidate code, honors sources and permissions, and adds reviewed facts to the report.

### C09 — Optional evaluation engines and public benchmark packs

**Dependencies:** C04 adapter contract and C05 schema.
**Do:** Add Waza and/or SkillRank eval CLI where qualified; import selected SkillsBench, MCPMark/MCP-Universe/OpenSkillEval fixtures and graders only with verified licensing and task mappings. Benchmark packs do not silently authorize paid agents or inherit other backends' success claims. Decline copies of noncommercial datasets in commercial distribution without permission.
**Exit:** At least one additional backend or benchmark pack has isolated conformance and normalized equivalent reporting; unsupported backends remain visible but BLOCKED/NOT_INSTALLED rather than faked as usable.

### C10 — Optional observability and isolation packs

**Dependencies:** C02/C03/C05.
**Do:** Reuse existing OpenTelemetry-compatible instrumentation; optionally integrate Langfuse/Phoenix and ToolHive with exact version/permissions. Trace export defaults to private/minimized. Distinguish data-plane permission enforcement from visible-tool catalog filtering; container presence doesn't prove credentials/context isolation.
**Exit:** Optional installation/revocation works; no telemetry service/database is required for Essentials; no unsupported claim of host process/network containment.

### C11 — Optional router, architecture and orchestration packs

**Dependencies:** C03 plus existing safe module boundaries.
**Do:** Keep current `Router`, `StackService`, `StackRuntime` accessible as versioned optional extension(s). Expose LangGraph, EvoAgentX, Microsoft Agent Framework/AFlow through small tested adapters only where justified; preserve producer/consumer schema and authority. A static AEEP DAG cannot be assumed equivalent to dynamic looping, subagent delegation or parallel execution; unsupported graphs stay external bounded delegations or fail closed. No mandatory full workflow builder.
**Exit:** Essentials works with all orchestration disabled; a legacy fixture still passes using optional router; one real compatible external workflow fixture records verification and clear permissions without requiring developer payment features.

### C12 — Developer provenance, support and portable evidence

**Dependencies:** C05 and C06.
**Do:** Bind candidate source/package/version and maintainer identity to developer-provided/confirmed links. Export appropriately anonymized, opt-in, portable, content-addressed reports with explicit trust tiers (self-reported, reproducible by independent reviewer, unverified) and task applicability. Start with external GitHub Sponsors/authorized purchase links; do not create transfer markets, payouts or subscription-charge integrations.
**Exit:** No unsupported claim of developer ownership, measurement attestation or payment authority; no private task material published by default; public-vs-local preview; links distinguish donations from required plugin fees.

### C13 — Beta handoff, adoption and go/no-go review

**Dependencies:** C06; C07 for claims of live measurable impact; C03/C08-C12 only for features advertised as supported.
**Do:** Run required repo software checks, cross-platform supported-host tests, installer replay/rollback, external link/docs checks, simple user comprehension trial, cost/overhead accounting and head-to-head against a native agent plus an upstream evaluator. Report total maintenance/stack footprint. Publish a readable functionality matrix: implemented/qualified/offline-only/live-tested/not assessed. Preserve existing v0.8 evidence records.
**Exit:** A user can install Essentials, submit a candidate, understand a report, and uninstall safely; benchmark claims backed by appropriately budgeted actual trials; developer identity and support path work. Operator explicitly reviews release/publication. Record GO / LIMITED_BETA / NO_GO and why. No silent public release.

## Global acceptance and no-go checks

- The entire value-report journey must work without the router, a hosted database, payment infrastructure, or full orchestration.
- Hard permissions checked before ranking/utility; no model request can expand limits.
- No mandatory arbitrary tool/plugin installation by following a discovery result.
- Missing exact host evidence -> unknown, never success/savings.
- `candidate available` isn't the same as `actually invoked`, and `actually invoked` isn't `caused verified improvement`.
- A high pass rate is not evidence of marginal plugin benefit when control passes equally well.
- Every visible public claim must specify test scope, environment, versions, date and evidence authority.
- Before adding a new internal module, log a make-vs-buy comparison in `DECISIONS.md`.
