# Changelog

## Unreleased — 0.7.0

### 0.7 subscription-native router

- preferred host-native routing beneath Tool Search, with exact local bypass and
  at most one managed model turn for the measured reference paths;
- provider-neutral capacity observations, reservations, transferability,
  authorization evidence, entitlements, and atomic redemptions;
- an official local Codex App Server adapter with Codex-owned authentication,
  runtime model discovery, multi-window quota evidence, approval intersection,
  bounded JSONL transport, and observed token/model accounting;
- shared durable execution attempts with compare-and-set transitions, leases,
  invocation evidence, terminal receipts, and no blind duplicate after an
  indeterminate external call;
- offline x402 capacity batch conformance, disabled by default, with no wallet,
  custody, payout, live marketplace, or value movement;
- operator diagnostics and a digest-bound `router-complete` verifier whose live
  account proof remains an explicit skip until separately authorized;
- SQLite schema versions 6 and 7, generated capacity/attempt/x402/report schemas,
  cross-platform offline CI, a fault-injection matrix, and per-critical-module
  branch-coverage gates.

The prior `0.6.0` heading described repository development state. No Git tag or
published release exists for it; those changes remain listed here as inherited
0.7 development history rather than a fabricated release.

### Incorporated 0.6 development work

- deterministic empirical p50/p95 resource estimates, observed cash p95, Wilson
  reliability lower bounds, and quality lower bounds after five exact-cohort
  samples; distributions never become payment authorization;
- explicit `SELECTED`/`BYPASS_ROUTER` decisions with routing overhead, feasible
  operator baseline, net-benefit threshold, and signed-delta routing-value
  report contracts that retain negative outcomes;
- v0.6 provider packages with explicit evidence authority/cohort declarations,
  a signed `/.well-known/aeep-provider.json` document, provider conformance CLI,
  SDK package/evidence builders, and durable SQLite provider idempotency records;
- isolated Python callable execution using an argv-only subprocess, bounded JSON
  pipes, timeout termination, and optional POSIX CPU/memory limits; packaged
  Python routes always use it;
- unambiguous `aeep_estimate_route_prices` model tool; the older
  `aeep_request_quotes` name remains a deprecated non-binding alias.
- pre-model DSH `/aeep` routing with empty default tool exposure, exact live
  schema pins, guarded hidden implementations, one explicit web-result adapter,
  persistent JSONL host bridge, route-pressure correlation, and a two-arm
  30-pair campaign contract whose savings claim requires a positive 95% interval.
- reproducible GPT-5.6 Terra Medium Codex comparison: 20 matched direct/AEEP
  pairs passed exact correctness and receipt gates; the compatible local AEEP
  route avoided 287,104 measured provider tokens without claiming a universal
  savings rate.

## 0.5.1 — 2026-08-26

- exact `aeep-evidence-cohort-v1` binding for every new receipt and observation;
  legacy or fingerprint-mismatched rows cannot affect live estimates;
- host-native DeepSeek Harness adapter for model and tool routing without
  exposing AEEP control schemas to the model;
- corrected three-arm, 30-case DSH campaign plan with fixed paired ordering,
  separate pilot accounting, and an explicit approval gate before live use;
- SQLite schema v5 migration for immutable receipt/observation fingerprint and
  cohort provenance.

## 0.5.0 — 2026-08-24

- native `aeep.dev/v0.5` provider packages with bounded strict YAML, RFC 8785
  digests, role-scoped Ed25519 signatures, portable route fingerprints, and
  zero-execution inert ingest;
- immutable local/opt-in-HTTPS artifact CAS, independent evidence attestations,
  per-metric acceptance, bounded smoke qualification, refresh, and explicit
  activation/revocation gates;
- immediate live-authorization cutoff for legacy canonical signatures while
  retaining historical audit and pre-cutover settlement recovery;
- privacy-preserving cache-affinity soft ranking, cache-read/write/reasoning
  resource dimensions, registry metadata adapters, and durable action approvals;
- deterministic DSH and job-application sandbox proofs with no live credentials,
  real external writes, duplicate submissions, or unsupported resume facts;
- request-bound, Ed25519-signed capability offers and bounded quotes with exact
  action, capability, executor, fingerprint, nonce, currency, terms, and expiry
  binding;
- explicit prepared routing that keeps ordinary `route()` offline, applies hard
  constraints before a bounded top-K quote fan-out, and persists sanitized,
  single-use decisions;
- caller-authored workflow integration that quotes only dependency-resolved
  inputs, prepares safe ready steps concurrently, checks settled cash plus wave
  maxima against the workflow budget, and cancels uninvoked over-budget work;
- Decimal/currency-safe maximum reservation, partial settlement, unused release,
  refunds, reconciliation, dispute, and indeterminate crash-recovery records;
- explicit immutable cash-authorization bases for signed quotes, published
  offers, and pinned rate cards; anonymous static priors remain non-authorizing;
- immutable SQLite economic evidence, transactional schema migration, replay
  tracking, atomic prepared claims, and concurrent budget reservations;
- provider usage statements, settlement receipts, market aggregates, and an
  evidence hierarchy that keeps unknown cash distinct from confirmed zero;
- nullable passive/counterfactual cash savings: `null` now means either side
  lacks eligible evidence, while numeric zero means a known comparison found no
  saving;
- operator-gated remote quote networking with host allowlists, SSRF/DNS checks,
  bounded bodies, no redirects, no ambient proxies, and declared disclosure only;
- a deterministic local reference provider/market, provider SDK helpers,
  operator CLI surfaces, generated 0.5 schemas, and settlement-backed proof
  assets;
- compatibility for 0.1 through 0.4 manifests, legacy quotes and receipts, and
  legacy full-capture payment adapters.

## 0.3.0 — 2026-08-13

- evidence-aware cash, provider-local subscription, model-token, counterfactual, and policy-valuation ledgers;
- immutable, scope-checked Decimal rate-card snapshots, explicit derived revaluation, and bounded Codex JSONL usage capture;
- exact Codex cache-write metering and pinned official `gpt-5.6-sol` API-equivalent proof campaigns for local-data and GitHub domains;
- inert imported candidates with fingerprint-bound qualification, activation, drift suspension, and execution-time revalidation;
- isolated repeated benchmark campaigns with cache-hit-qualified warm statistics, and caller-authored workflow DAG execution with WAITING/resume;
- indeterminate post-invocation idempotency, sanitized persistence, and stricter MCP protocol/cache/credential boundaries;
- compatibility for 0.1, 0.15, and 0.2 manifests and versioned signed receipt envelopes.

- compact agent decisions, paginated capability search, and detailed inspection by ID;
- confidence-aware scoring, zero-capacity GPU enforcement, input-conditioned history, and atomic idempotency;
- OpenTelemetry trace ingestion plus OpenAI and Anthropic SDK instrumentation;
- runtime subscription quota observations and packaged skill installation;
- MCP server discovery import and a real GitHub default-branch routing example;
- full Apache-2.0 license text and Ruff/mypy cross-platform CI checks.

## 0.2.0 — 2026-08-12

- subscription resources, explicit quota pressure, host executors, and BYOS skills/examples;
- versioned capabilities, quotes and acceptance, signed receipts, validators, and trust observations;
- local/remote provider registries with lazy capability discovery and measured reputation;
- counterfactual reports and subscription-aware economic metrics;
- payment adapter, agent budget, reservation/capture/refund, and local ledger contracts;
- provider SDK plus CLI, MCP, and OpenAPI importers and local descriptor publication;
- six shared MCP/CLI/provider tools, with financial operations kept outside model control.

## 0.1.0 — 2026-08-10

Initial working alpha:

- hard-constraint-first, multi-objective action routing;
- Python, argv CLI, HTTP, MCP, and host-delegate executors;
- cost, latency, CPU, memory, GPU, network, and context/token accounting;
- SQLite decisions and receipt-based historical learning;
- conservative fallback and separate operator approval ceilings;
- finite resource validation and atomic, terminal-only delegated outcome reporting;
- privacy-preserving decision persistence by default;
- sequential route benchmarking for cold-start calibration;
- dual-era stdio/Streamable HTTP MCP client/server with stateless `2026-07-28` discovery, legacy initialization fallback, bounded messages, cache hints, validated header mirroring, and MCP SSRF controls;
- provider-native tool declarations;
- ChatGPT/Codex, Claude, DeepSeek, Z.AI, and OpenClaw integration material;
- generated JSON Schemas, examples, security guidance, and tests.
