# Steering amendment v1 — lightweight, understandable, bounded-autonomous AEEP

Apply this to the existing AEEP continuation prompt and the consolidated implementation and delivery plan. Continue in the current ptse8204/AEEP-router checkout; do not restart the project.

This is a targeted amendment, not a replacement specification. It changes integration priorities, the first user-facing milestone, and acceptance criteria for footprint, usability, and autonomy. Preserve the original requirements wherever this amendment does not explicitly change them.

## 1. Reconcile authority and inspect the actual working state

Record this amendment alongside the original plan. Replace the claim that the governing direction is entirely “unchanged” with a versioned explanation of what this amendment changes. Do not rewrite historical campaign definitions, results, accounting, or qualification decisions.

Read AGENTS.md, the existing architecture/security/specification documents, relevant tests, docs/ASSESSMENT_TESTING.md, and reports/v08/plan-coverage.md where present. Extend existing status records rather than create another competing roadmap.

The supplied consolidation reports main at cdb0d989, substantial uncommitted work, Codex CLI 0.154.0, 967 passing Python tests, 15 skipped tests, approximately 82% coverage, 22 successful software checks, and 12 passing container tests. These are reported historical observations, not newly verified facts. Inspect the actual checkout, preserve uncommitted work, and distinguish inherited failures from regressions.

Carry forward the historical no-benefit workbook/CSV results, baseline task successes, controlled lifecycle fixture, absence of a recorded Sol live experiment, and the interrupted campaign’s unknown accounting. A candidate does not need to win for a campaign to be complete.

Preserve the recorded gpt-6-sol experimental selection subject to actual worker/model availability. Do not silently substitute a model, host, authentication method, or paid API. Earlier model evidence does not qualify a new model/configuration.

Retain the original hard constraints, qualification/activation thresholds, operator approval ceilings, argv-only execution, privacy defaults, durable recovery, and prohibition on blind consequential retries. Codex owns authentication: never read, copy, persist, or expose its authentication state.

## 2. Make the product outcome the organizing milestone

The first user-facing outcome is:

“A user enables AEEP for a supported project, completes ordinary tasks without managing plugins manually, understands consequential capability decisions, and can leave eligible work operating within declared limits—without a large mandatory infrastructure stack.”

Treat three properties as release criteria: acceptable whole-system footprint, understandable in-agent explanations, and demonstrated unattended operation within a defined scope.

Keep the larger mission: help useful independent capabilities earn selection and eventually authorized support, while improving outcomes for users with constrained resources. Preserve contributor identity and future support references. Do not introduce live payments, redeemable balances, automatic financial allocations, or subscription resale in this increment.

AEEP remains the evidence/admission/configuration and bounded execution-decision layer. The host owns overall planning. ARD supplies external discovery. Neither a new marketplace nor a second general agent runtime is required.

## 3. Use existing solutions selectively; do not install an ecosystem by default

Create a short integration decision record in existing documentation. For each proposed dependency, identify the specific gap, existing AEEP component it extends, version/license, mutations and privileges, overhead, failure behavior, and removal path.

Use a bounded compatibility check, not an open-ended survey. Revalidate the prior research against primary documentation and the installed implementation. Documentation alone does not establish runtime support. Do not freeze an old upstream limitation as permanent, or assume a newly documented feature exists in the installed host.

Apply these decisions:

NATIVE CODEX CONTROLS FIRST

Inspect task/project configuration, permission profiles, MCP filters, skill exposure, effective-state reporting, and supported App Server methods before implementing equivalents. Verify filesystem and network behavior, including any proxy requirement for domain filtering. Respect existing administrator policy and configuration precedence. Do not force a host upgrade without authorization.

Use the host’s actual progressive disclosure and tool-search behavior as the baseline. Do not manufacture an expensive control by loading every full skill into context. Current routing must not require a new model call just to ask which routing mechanism to use.

SKILLSPEC IS OPTIONAL, INITIALLY READ-ONLY

Evaluate its inventory, Doctor/boundary output, contract metadata, and alignment reports as inputs to existing candidate, assessment, and evidence records. Missing SkillSpec must not prevent normal AEEP operation.

Treat scanner findings and declared contracts as evidence with provenance, not permissions or proof of safety. Lexical matching is relevance, not demonstrated economic value. Contract adherence, task success, and marginal benefit remain separate questions.

Do not enable SkillSpec’s global router, visibility mutation, prompt/repair hooks, or guard by default. Check their actual behavior: native implicit/manual/off states may still leave files accessible; hook-level grants may be combined across policies rather than scoped to the current task. Neither behavior satisfies a strict exclusion claim without additional enforcement.

If evaluating compiled contracts or thin loaders, retain the original skill and identify the transformed artifact separately. Do not require developers to rewrite skills into a new format before AEEP can assess them. Compare conversion independently from routing.

OTHER INTEGRATIONS CLOSE DEMONSTRATED GAPS ONLY

Consider FastMCP for scoped MCP exposure, ToolHive for managed MCP workloads, and an existing sandbox runtime for a specific unresolved isolation requirement. Do not make all three dependencies. Evaluate session overrides, HTTP versus stdio enforcement, platform restrictions, and control-method authority where applicable.

Reuse SkillsBench tasks/oracles/verifiers through existing campaign machinery. Keep heavyweight desktop/multi-application suites in the later sequence. Evaluate Inspect AI only where its provider/authentication assumptions fit; it must not silently replace subscription-backed Codex execution.

Keep MCP Apps, tracing exporters, and hosted/self-hosted observability optional. Do not require a multi-service monitoring stack or a separate dashboard for basic use.

Prefer an adapter over a fork. Upstream generally useful fixes when appropriate. Retire existing code only after a replacement demonstrates compatibility and net benefit.

## 4. Preserve one profile authority while separating runtime from the assessment lab

Experiments and production must share profile validation, authorization, host-control compilation, effective-state inspection, activation, dispatch checks, lifecycle operations, and evidence semantics.

They do not need identical infrastructure for every task. Keep a small production path and an optional bounded assessment path:

Production:
Existing task context → policy and applicable evidence → native profile activation → execution → required verification → receipt/explanation.

Assessment:
Authorized trigger → bounded worker/environment → controlled comparison → evidence → existing qualification/admission workflow.

Do not scan the whole skill library, query global discovery, start benchmark workers, or run a judge model for every ordinary request. Keep normal route() offline and deterministic. Discovery and expensive assessment remain explicit preparation operations.

Use existing environment, invocation, admission, worker, and recovery contracts. Do not create parallel profile managers, registries, ledgers, workflow engines, or evidence stores. One AEEP-controlled lifecycle owns activation and rollback; third-party hooks must not independently “repair” the same configuration.

Retain installed/discoverable/permitted/exposed/used distinctions, and deferred/hidden/call-blocked/absent exclusion semantics. A hidden skill is not inaccessible; a profile directory is not a sandbox; disabling instructions does not remove them from an existing conversation. Strict comparisons use fresh contexts and declared execution boundaries.

Bind evidence to the effective enforcement backend as well as the profile. A container-tested profile does not prove equivalent isolation when production runs directly on the host. Demonstrate the relevant equivalence, retest, or mark applicability limited. Unsupported boundaries remain unsupported.

Native baseline fallback is allowed only when it is still qualified and permitted. Never bypass a mandatory boundary because it is slow, or restore a revoked route merely because it worked previously.

## 5. Make installation and operation minimally invasive

Aim for a usable local workflow without a new cloud account, external telemetry service, permanent daemon, or container stack unless the selected supported profile genuinely requires it. Prefer an on-demand process or one scoped to the host session.

Use execution/project-local overlays where supported. Never toggle the user’s global skill configuration between concurrent trials. Avoid new prompt hooks or first-hop router instructions unless a measured experiment justifies them and the user authorizes the mutation.

Record AEEP-owned configuration changes, files, hooks, services, ports, and privileges. Provide inspection, pause, cleanup, rollback, and uninstall through existing interfaces. Restoration must preserve unrelated and subsequently edited user configuration; detect conflicts rather than overwrite them.

Bound caches, downloads, indexes, workers, concurrency, logs, and evidence retention. Use targeted invalidation instead of full rescans on every prompt, while retaining required integrity checks at activation and dispatch. Cleanup must not discard unresolved attempts, approvals, reservations, or accounting needed for recovery.

Keep sensitive payloads out of default logs and discovery queries. Separate optional detailed tracing from required authorization, outcome, and accounting records. Uninstall must not erase financial or recovery evidence indiscriminately.

## 6. Measure footprint across the entire added system

Add an incremental footprint report to existing profiling/reporting machinery. Measure the native baseline and the baseline plus AEEP on a declared reference environment. Identify the process boundary and shared resources so measurements are neither omitted nor double-counted.

Cover:

- Cold startup, warm decision latency, profile activation, and end-to-end task time.
- Idle/active memory, CPU, and child-process or VM overhead where observable.
- Installation/dependency/image storage, evidence growth, cache limits, and cleanup.
- Added instructions, exposed schemas, model/reviewer/verifier calls, retries, and cache usage.
- Network requests, downloads, telemetry, and private-data disclosure.
- Configuration mutations, hooks, services, privileges, restarts, and user effort.

Report production costs separately from assessment-lab costs. Include discovery, setup, verification, adapters, stronger-model supervision, and optional reviewers. Distinguish one-time costs, recurring costs, and explicitly assumed amortization. Do not subtract speculative future savings from measured current overhead.

Measure idle, warm ordinary work, cold activation, assessment, and failure/recovery scenarios. Do not infer low memory usage from programming language or packaging. Mark unavailable telemetry unknown; subscription usage is not API cash.

Establish baseline-informed resource budgets before scored comparisons or release decisions, and record them. Do not invent attractive numerical limits or choose thresholds afterward merely to pass. Exploratory calibration and held-out evaluation are separate.

Time remains a preference or operational cap, not the universal objective. Retain raw resource dimensions and quality floors. Where optional optimization costs exceed its benefit, retain an eligible baseline without dropping mandatory authorization checks.

## 7. Put explanations in the actual agent experience

Add a small presentation layer over existing decision/outcome receipts, not a new model-driven narrator or reporting database.

Expose sanitized fields for the chosen route, reason, scope of permissions, changes made, verification outcome/limits, recorded resources, outstanding approval, and recovery state. Clearly separate observed results, estimates from prior evidence, and controlled comparative findings.

Default to a short task-level explanation after consequential decisions, with detail on demand. Ordinary operations should not produce repetitive routing chatter. Never claim a percentage saving without relevant comparative evidence or claim preservation beyond the checks actually performed.

Examples of intended presentation, not mandatory wording:

“Updated the two cells and checked the rest of the workbook. I used your existing tools and installed nothing.”

“The update requests network access. I retained the still-approved version; your permissions have not changed.”

“The preview is ready. Publishing requires approval for the destination account.”

Render through supported host events/UI where possible. Otherwise provide a compact structured result the host can summarize, plus a usable text/CLI fallback. Declare whether direct rendering is supported; do not pretend an arbitrary plugin can inject trusted interface elements into every host.

An optional MCP App can display evidence or controls, but must not be a prerequisite or require an extra model-facing invocation solely to show status. UI controls use the same authorization path; untrusted tool text must not become a trusted approval instruction.

Test summaries against receipts. Evaluate whether users can identify what changed, what was verified, whether extra access/spending was approved, and how to pause or undo AEEP-owned changes. Automated wording tests do not constitute completed human usability testing; report these separately.

## 8. Deliver bounded unattended operation, not unlimited authority

Separate task autonomy from maintenance/improvement autonomy, using existing policy and approval structures rather than introducing another permissions engine.

Task autonomy permits selection, execution, required checks, and safe recovery for qualified capabilities within a standing user-approved scope. Do not ask the user to approve every routine choice already authorized by that scope.

Improvement autonomy is separately opt-in and budgeted. It may inspect drift, assess candidates, and propose or promote changes only through existing qualification/activation operations when operator delegation permits it. No threshold relaxation, self-approved permission expansion, or silent addition of external services.

If the current implementation cannot represent standing delegation safely, document that limitation and extend the existing contract minimally. Until then, preserve the existing approval behavior rather than simulate autonomous authority.

Track execution and assessment allowances separately while retaining all aggregate limits and budget counters. Assessment exhaustion stops assessment, not unrelated permitted work. Bound retries, exploration, concurrency, candidate count, and re-evaluation frequency. Do not continuously test every possible plugin combination.

Feature-detect any supported native automatic approval review before creating an AEEP reviewer. Treat it as optional: it changes who reviews eligible requests, not the user’s authority or the need for enforcement. Account for its calls and latency. The evaluated agent must not edit its own policy or access privileged configuration methods.

Reuse durable attempts and recovery for model/tool drift, unavailable servers, timeout ambiguity, process crashes, authentication expiry, evidence staleness, full storage, and interrupted accounting. Reconcile external effects before consequential retries. Stop safely when no authorized route exists; do not quietly abandon work or substitute a paid provider.

Provide understandable exception messages, a pause/kill control, and a resumable state where supported. Required consequential approvals remain legitimate checkpoints, not failures to be hidden.

Declare the operating lifecycle. Session-scoped autonomy does not promise progress while the host is stopped; a scheduled background mode requires a separately enabled, bounded deployment using existing host supervision where supported. Do not introduce an always-on service merely to label a session autonomous.

Measure verified unattended completion over a predeclared representative task set, with eligibility rules fixed in advance. Report safe stops, necessary approvals, unnecessary prompts, human intervention effort, recovery success, and unresolved outcomes separately. Do not inflate autonomy by excluding difficult cases after seeing results.

## 9. Strengthen comparisons without multiplying every campaign

Preserve the original paired candidate/no-candidate comparisons and the three-way normal-host / discovery-host / equivalent-discovery-plus-AEEP experiment. Preserve realistic baseline tools, optional invocation, independent helpers, normal/larger budgets, fresh state, frozen holdouts, uncertainty, and negative findings.

Before adopting SkillSpec’s fuller runtime integration, run a small diagnostic comparison where feasible:

A. Native host.
B. Native host plus the explicitly selected SkillSpec feature set.
C. Native host plus AEEP.
D. Native host plus AEEP and that same SkillSpec feature set.

Specify the exact feature set and artifact versions. Keep candidate access, task contracts, model settings, applicable authority, resource budgets, and verifiers comparable. Account for each component’s own overhead. Do not turn this into a mandatory four-way matrix for every future campaign.

Original versus contract-compiled skills are a separate intervention. Keep instruction adherence, actual task outcome, and marginal value distinct. A bundle’s gain is not automatic causal credit for each constituent.

Use a small task, a larger structured task, and a crowded/conflicting-capability scenario. Add controlled failures and model/resource variation as bounded extensions. Reuse existing synthetic fixtures for regression and SkillsBench for pinned external tasks; protect oracles and trusted verifiers from the evaluated agent.

Do not claim official benchmark reproduction when the host or task protocol changes. Do not call a synthetic fixture a live-agent result. A passing local suite proves its tested properties, not general product usefulness.

AEEP itself may provide no net benefit in a task family. Report that and retain the eligible native route. No release gate should require manufactured positive results; no usefulness claim should rely on mere implementation completeness.

## 10. Amend delivery order without discarding existing work

Use a compact dependency map and implement the smallest coherent increment:

FIRST: RECONCILE AND BASELINE

Record the amendment, actual checkout state, existing checks, native behavior, initial footprint, and integration decisions. Select one supported host/profile and one user journey; avoid a general rewrite.

SECOND: COMPLETE THE SHARED PRODUCTION PATH

Reuse current profiles, native controls, effective-state inspection, authorization, receipts, and lifecycle. Include reversible configuration, concise in-agent explanations, and bounded task autonomy in the first demonstration.

THIRD: COMPLETE ASSESSMENT REUSE

Retain the planned ARD adapter/local fallback and pinned SkillsBench adapter through existing machinery. External discovery must not block local work when known capabilities/evidence suffice. Add the read-only SkillSpec adapter only where the compatibility check establishes useful input.

FOURTH: PROVE THE USER JOURNEY AND FAILURE HANDLING

Demonstrate small and larger spreadsheet tasks with preservation checks, eligible native fallback, prohibited-operation rejection, understandable outcomes, pause/rollback, and interrupted-work recovery. Run authorized live tasks separately from offline proofs.

FIFTH: EVALUATE EXPANSION

Run the bounded dependency comparison and three-way AEEP-value campaign. Continue website build/verify/publish/later-edit profiles and broader benchmarks without making every backend a first-release prerequisite.

Keep the broader original roadmap visible. A blocker remains blocked, not passed. Narrow support only through an explicit, documented scope change—not by relabeling an intended requirement after it fails.

## 11. Add adoption gates to the existing acceptance suite

Retain all original isolation, concurrency, schema, policy, accounting, recovery, benchmark, and release tests. Add:

1. Minimal operation:
The declared local workflow works without optional integrations; absent integrations produce explicit fallback or unsupported states.

2. Footprint:
Measured whole-system costs satisfy predeclared budgets for the supported scope, with production and assessment costs separated.

3. Reversibility:
Activation, replacement, crash cleanup, rollback, and uninstall preserve user edits and other sessions’ authority.

4. Explainability:
Summaries match recorded evidence, disclose limits, and do not overstate savings, security, or autonomy.

5. Unattended operation:
Eligible tasks finish and verify under standing authority, while failure scenarios recover or stop correctly without duplicate effects or hidden escalation.

6. Evidence transfer:
Different host/isolation backends cannot silently reuse qualification beyond demonstrated applicability.

Keep existing admission thresholds and historical results unchanged. Older four-family campaigns retain their definitions and applicable regression role. A small release may have a narrower declared support envelope, but cannot claim untested broader readiness.

Separate software readiness, offline conformance, live qualification, measured benefit, resource acceptance, usability evidence, and autonomy evidence. A result in one category does not pass the others automatically.

## 12. Work instructions and completion report

Start with a concise change map identifying existing files/contracts to reuse and the next bounded increment. Verify only the upstream behavior needed for that increment; do not restart an unlimited research cycle.

Then implement safe local changes and run the applicable compile, schema, static/type, test, coverage, integration, packaging, and release checks. Publish command syntax only after implementation and testing. Do not stop at an architecture proposal when local implementation can proceed.

Keep installation of unreviewed software, global environment changes, paid calls, consequential live operations, publishing, and releases behind existing authorization. Absence of authorization is a recorded blocker, not a reason to simulate success.

Update existing coverage/status documentation with changed files, reused components, dependency decisions, exact commands/results, footprint measurements, sample receipt-derived responses, autonomy/failure results, and remaining work. Distinguish implemented-and-tested, offline-only, live-verified, and blocked; include not-yet-measured findings explicitly.

The completion question is not “Did we integrate all the projects?” It is:

“Does this supported AEEP workflow improve capability decisions while imposing acceptable resources and authority, explaining consequential choices, and operating reliably within the user’s delegated scope?”

## Primary-source follow-up list

These are references from the preceding research, not a statement that every feature is currently supported or a list of dependencies to install. Verify only relevant interfaces, pin versions, and inspect licenses. Keep the original prompt’s ARD and benchmark references as well.

Codex permissions:
https://learn.chatgpt.com/codex/permissions

Codex MCP:
https://developers.openai.com/codex/mcp

Codex skills:
https://developers.openai.com/codex/skills

Codex App Server:
https://developers.openai.com/codex/app-server

Codex automatic review:
https://learn.chatgpt.com/docs/sandboxing/auto-review

SkillSpec:
https://github.com/modiqo/skillspec

SkillSpec router:
https://github.com/modiqo/skillspec/blob/main/docs/design/router/14-skill-router.md

SkillSpec guard:
https://github.com/modiqo/skillspec/blob/main/crates/skillspec-boundary/src/guard/decide.rs

FastMCP visibility:
https://gofastmcp.com/servers/visibility

FastMCP authorization:
https://gofastmcp.com/servers/authorization

ToolHive configuration:
https://github.com/stacklok/toolhive/blob/main/docs/arch/05-runconfig-and-permissions.md

Sandbox Runtime:
https://github.com/anthropics/sandbox-runtime

SkillsBench:
https://github.com/benchflow-ai/skillsbench

Inspect AI agent bridge:
https://inspect.aisi.org.uk/agent-bridge.html

MCP Apps:
https://modelcontextprotocol.io/extensions/apps/overview

Langfuse deployment:
https://langfuse.com/self-hosting
