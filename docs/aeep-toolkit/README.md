# AEEP Evaluation Toolkit — durable product plan

**Plan date:** 2026-10-08  
**Target:** `https://github.com/ptse8204/AEEP-router`  
**Track:** evidence-first modularization, preserving the existing repository and historical evidence.  
**Implementation status:** C00-C06 and C08-C12 have recorded passes at their stated evidence tiers. The upstream scripted journey and managed fallback are implemented. The three-family live qualification passed 141 trials; the separate four-arm comparison completed 564 valid runs. C07 campaign delivery passed with an inconclusive efficacy verdict. C13 human/resource/release gates remain open. See [STATE.md](STATE.md) for actual evidence, limitations and remaining gates, and [worker readiness](WORKER_READINESS.md) before starting another live study.

## Mission (fixed unless the owner changes it)

Help users determine **whether a candidate plugin/skill/MCP service/tool makes their existing AI agent meaningfully better**—for which tasks, on which host/model, by how much in **verified success, tokens, elapsed time, retries, and real economic cost**. Help independent developers show attributable, reproducible evidence so users can decide to install, buy, or support their work. This is not a general-purpose orchestration product first.

The user-facing deliverable is a trustworthy per-capability comparison report with task-family breakdowns and an authorized developer support/purchase link. AEEP's distinctive work is **normalizing heterogeneous evaluations, interpreting comparable evidence, checking applicability, making honest value/economic claims, and tying results to developers**. Reuse upstream software for evaluation harnesses, discovery, isolation, observability, routing, and orchestration whenever it meets the actual requirements.

## Architectural approach

Delivery now prioritizes an [assembled, reusable evaluation workflow](STACK_DELIVERY.md).
Its [component audit](../../reports/toolkit-v2/c13/stack-delivery-20261030/README.md)
separates executed integrations from imports, mock fixtures and research. Working
stack integration, candidate usefulness and AEEP selection usefulness are three
independent acceptance gates. Ponytail's completed results remain preserved;
replaying them is outside this delivery work.

One product, **two plugin categories**:

1. **Candidate capabilities:** what AEEP evaluates (initially one local `SKILL.md`; later MCP servers, other skills and tools).
2. **AEEP extensions:** optional components used by the evaluator (evaluation engines, benchmark packs, scanners, catalogs, trace backends, routers, orchestrators, compensation adapters).

**Minimal ownable core:** extension manifest/installer preview, versioned canonical evidence, comparison and value calculations, evidence provenance/applicability, human-readable report, verified developer links, adapter interface and a thin CLI. Retain existing AEEP code when it is smaller/safer than replacing it. Move existing router, stack planning, payments, and advanced hosts into optional, compatible extension paths; DO NOT delete or rewrite proven components just because a package has overlapping marketing language.

### Installation profiles

- **Evaluation Essentials:** AEEP core + one *qualified* evaluator adapter + local report/verification. Only the minimum required agent host and its prerequisites. Target Codex/macOS initially.
- **Evaluation Toolkit:** Essentials + opt-in skill/MCP discovery, vetted scanner, benchmark packs and advanced observability.
- **Full Toolkit:** A chooser/catalog containing **all supported compatible extensions**, including Waza, SkillRank, ToolHive, LangGraph, EvoAgentX, Microsoft Agent Framework, and the legacy AEEP Router. Full does **not** mean force-installing expensive, incompatible or unsafe components. Every selected item is disclosed before install.

Every installation path is **plan/preview -> explicit operator authorization -> bounded install -> verify -> rollback/uninstall**; source discovery is not permission to install or execute. Report installed vs enabled vs ready vs permitted vs actually used separately.

### Boundaries

- Preserve `AGENTS.md`, `docs/ASSESSMENT_TESTING.md`, `SECURITY.md`, and current standing approval/budget/invariant constraints. This plan reorients product scope, **not** permissions or live experiment approvals.
- Current AEEP assessment policy requires separate controlled workers for comparable agent/plugin tests. A temporary Git directory is **not** a security sandbox or proof of equal host exposure. Verify an external evaluator's execution boundary; wrap inside the existing approved containment where needed, or mark strict comparative qualification **BLOCKED**.
- Ordinary skill discovery/test results do not establish use value. Primary value trials must allow **natural candidate selection**, retaining other normal tools in both arms. Forced invocation is diagnostic only.
- Never assume subscriptions yield realizable per-task cash savings. Distinguish provider-reported tokens, estimates, billing, wall time, task quality and the total cost of doing the experiment.
- Do not store user task contents/prompts/results by default in public evidence. Hash/minimize. Protect verifier and holdout cases.
- No unattended paid calls, installing unreviewed third-party code, user credentials, host-global edits, publication/payout, altering historical frozen tests, or scope expansion without proper authorization.

## Durable documents and precedence

Read in this order after EVERY context reset or restart:

1. Existing repository `AGENTS.md` and `docs/ASSESSMENT_TESTING.md` (safety/authority).
2. `docs/aeep-toolkit/STATE.md` (actual implementation and blockers, not aspirations).
3. `docs/aeep-toolkit/CHECKPOINTS.md` (next gate and dependencies).
4. `docs/aeep-toolkit/CONTINUATION.md` (execution/recovery protocol).
5. This README and `ACCEPTANCE.md` (mission/contracts).
6. `UPSTREAM_MATRIX.md`, `INSTALLATION_DESIGN.md`, `DECISIONS.md` (choices and pending research).

`MASTER_PROMPT.md` is a self-contained one-time steering prompt, not a replacement for checked-in progress. **Commit progress and state at every checkpoint**. Never treat chat history or README claims as passing test evidence. `STATE.md` is initially a placeholder and must only be advanced by verified work.

## Critical path and future tracks

**C00-C06:** inventory -> reuse decisions -> extension/evidence contracts -> non-mutating installer preview -> evaluator adapter -> reliable savings report -> Essentials offline E2E. This is the first useful deliverable.  
**C07:** live, permissioned, budgeted Codex comparison; if blocked, record as blocked and continue independent work.  
**C08-C12:** optional discovery/security, other evaluation backends, observability/isolation, routing/orchestration, developer support.  
**C13:** compatibility, usability and beta packaging; evidence and permissions gate any release.

No timeline promises; advance only on passing checkpoint evidence. The goal is a **usable evaluation product**, not passing synthetic tests or collecting plugins.

## Example user story

> "Is this spreadsheet skill worth installing in my existing Codex setup?"

The user submits a candidate path or URL, reviews prerequisites and permitted setup, sees the proposed tests and budget, and receives a report separating small-cell edits from complex workbooks. The report shows verification outcomes, actual/estimated tokens and time, retries, uncertainty, missing measurements, purchase/break-even implications where supported, and developer attribution. AEEP may legitimately say *no demonstrated benefit*, *worse*, *inconclusive*, or *not assessable*.

The [three-case offline journey](../../examples/toolkit_offline/README.md) now
connects a reviewed captured candidate to the upstream evaluator, individual
controlled workers and a verified HTML/Markdown report. Its outcomes are scripted;
real-host value remains unassessed.

The optional [managed evaluation bridge](MANAGED_EVALUATION.md) connects existing
reviewed skill plans to the AEEP fallback, using the same workers and grants.
Its file-based preview is inert. Native value and release gates remain open.

[Token capture and candidate loading](TELEMETRY_REPAIR.md) explains the corrected
retention path, the 564-run retrospective capture audit and the prospective live
collector check. Capture verification does not upgrade provider metering trust.

## Prepare a local sharing preview

From the repository checkout, minimize a normalized evidence bundle before
deciding what to share:

```bash
PYTHONPATH=src python3 -m aeep_toolkit export-preview \
  --evidence /absolute/toolkit-evidence.json
```

The command prints content-addressed JSON and publishes nothing. It omits task
labels, prompts, paths, run identifiers, receipt references and host/model names.
Cohort hashes keep incompatible measurements separate; private source records
are still needed to interpret their applicability. Aggregate measurements and
digests can identify a study, so this is not guaranteed anonymity.

Add `--disclose-source` to include the supplied candidate source metadata. An
optional `--developer /absolute/developer.json` uses the existing DeveloperIdentity
contract and requires that flag plus an exact source match. Ownership and support
links remain unverified assertions. Donation links are optional support; purchase
links do not establish a price or permission to pay. The preview retains synthetic
labels and unknown measurements and makes no independent efficacy claim.

## Search and inspect optional upstream results

Discovery reuses the existing configured ARD, MCP Registry and local readers. It
writes provenance to the database you select, but never downloads or executes a
candidate. Relative catalog paths resolve beside the discovery configuration.
Remote queries require `allow_remote` in the operator's configuration; use only
public search phrases. This command is not an installation preview.

```bash
PYTHONPATH=src python3 -m aeep_toolkit discover \
  --config /absolute/discovery.json --store /absolute/discovery.sqlite3 \
  --source local --query 'CSV helper'
```

An absent source is unavailable. Upstream verification badges are metadata, not
AEEP admission. The existing `DiscoveryConfig` schema bounds sources, results
and deadlines; the CLI returns a failure status when a source fails or times out.

`import-report` reads Waza or Cisco Skill Scanner JSON without installing or
executing either tool. Supply the exact supported upstream revision and candidate
hash; both remain supplier assertions. For example, a Waza 0.38.9 source result:

```bash
PYTHONPATH=src python3 -m aeep_toolkit import-report waza \
  --input /absolute/waza-results.json \
  --revision e534d149d89ae77ea158469fb4d2003804b2ee76 \
  --candidate-sha256 CANDIDATE_SHA256 --format html
```

Replace `CANDIDATE_SHA256` with the captured candidate's 64-character SHA-256.
Use `cisco-skill-scanner` with revision
`c3d7fd9fee50cf2ea45f0b381eb61f857360f825` for a single-skill JSON scan.
Formats are `json`, `markdown` and `html`; output goes to stdout. Imports omit
paths, prompts, outputs and diagnostic text. Missing usage remains unknown;
cached Waza diagnostics are not added to session billing. Scanner suppressions
and analyzer failures remain visible as counts. No imported status establishes
independent verification, worker isolation, safety, cost savings or permission
to execute. These are report adapters, not qualified execution backends.

## Preview a trace without exporting it

`trace-preview --receipt /absolute/receipt.json` prints a minimized OTLP/HTTP JSON
body for the recorded execution. It reads no exporter credentials and sends
nothing. Only observed local resource dimensions are included; absent counters
stay absent. The supplied receipt is unverified. Langfuse is the selected optional
OTLP destination, but no destination or disclosure permission is configured.

The packaged CLI now includes the existing scripted evaluator bridge and fixed
fixtures. It still requires the separately reviewed agent-skill-eval runtime and
worker image; installing Essentials does not install or authorize those tools.
The installed-source fingerprint covers actual package code and execution assets,
so checkout conformance cannot be reused for a wheel installation.

[Current upstream dispositions](../../reports/toolkit-v2/integration-completion/README.md)
distinguish report import, bounded executable conformance and remaining live gates.
