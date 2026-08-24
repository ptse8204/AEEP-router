# Changelog

## Unreleased — 0.5.0

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
