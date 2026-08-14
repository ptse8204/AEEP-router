# Architecture and design decisions

## Placement in an agent stack

```text
agent planner / user intent
          │
          ▼
semantic ActionRequest
          │
          ▼
AEEP feasibility + economic policy
          │
     selected route
          │
   ┌──────┼────────┬────────┬───────────┐
 Python  CLI      HTTP     MCP     host/delegate
                                      │
                              browser/model/GUI host
```

AEEP belongs below planning and above execution adapters. It does not tell an agent how to decompose an open-ended goal; it optimizes bounded actions after decomposition.

## Why a semantic action rather than a tool name

Tool names bind a decision to one transport/provider. A capability such as `github.current_branch` can have local CLI, REST, MCP, cached-state, and browser routes. The semantic contract is the comparison boundary.

Automatic equivalence inference is deliberately absent. Silent substitution between almost-equivalent actions is more dangerous than asking operators to register contracts explicitly.

## Why raw resources rather than one credit

A scalar is useful for ranking but destructive as an interchange format. Raw dimensions preserve:

- auditability;
- policy changes without rewriting history;
- different user opportunity costs;
- model-provider independence;
- hard resource caps;
- future metrics.

The scorer can derive a local scalar at decision time. Receipts retain the vector.

## Why feasibility precedes scoring

Weighted averages allow compensation: enough speed can mathematically offset a privacy violation. A hard constraint must never be offset by a preference. Therefore rejected candidates have no total score.

## Expected cost per success

A route that costs half as much but succeeds half as often can be more expensive after retries. The scorer scales consumable burden by inverse success probability and separately penalizes unreliability.

This is still a model, not a guarantee. Correlated failures, fallback cost, and side-effect ambiguity require richer planning in later versions.

## Locality and current state

Local execution receives a small configurable preference because it often avoids network, data disclosure, and context overhead. If caller state is already local to an execution surface, a second locality bonus can represent reuse of current state.

The bonus is intentionally small and never bypasses hard constraints.

## Static priors and observations

Cold-start estimates come from executor configuration. Real receipts are blended using sample-aware history and the action's privacy-preserving input-size bucket. A provider's advertised number remains a prior; it is not copied into observed performance. Low-confidence estimates carry a configurable uncertainty burden.

A production network can replace the local EWMA with confidence intervals, task-conditioned models, quantile latency, drift detection, and signed attestations without changing the core objects.

## Execution boundaries

### Python

Best for trusted, deterministic in-process work. It has low overhead but weak isolation. A timed-out worker thread cannot be forcibly killed safely.

### Command

Uses `create_subprocess_exec`, never a shell. It offers process isolation, timeouts, bounded output, and host metrics. It is the preferred local boundary for tools with meaningful side effects or dependencies.

### HTTP

Uses bounded streaming and conservative target validation. It is appropriate for ordinary REST APIs. Provider cost headers remain claims unless reconciled by trusted accounting evidence.

### MCP

Discovers the configured tool, measures schema/context overhead, invokes it over stdio or Streamable HTTP, reads optional AEEP usage claims, and caches discovery/tool schemas according to protocol hints and credential scope. Protocol mode can be pinned; automatic legacy fallback requires an unambiguous method-not-found response.

The modern path mirrors protocol version, method, tool name, and schema-authorized primitive parameters into HTTP headers; validates header/body consistency; bounds messages; and applies the same SSRF/allowlist/HTTPS policy as the HTTP executor. AEEP 0.3 accepts only complete single-round tool results; multi-round `input_required` continuation belongs to the host agent until a later protocol adapter is defined.

### Delegate

Represents an execution surface owned by the host agent: browser, GUI, computer-use, model reasoning, or an unavailable native tool. AEEP returns instructions and a decision ID; the host reports the outcome later. To prevent arbitrary history injection, external reports are accepted only for the selected, feasible delegate and only once per decision/executor pair. Trusted out-of-band measurement uses `ActionProfiler` instead.

### Host subscription

`host` formalizes current-agent execution without calling a model API. It references a user-owned `SubscriptionResource`, returns `HOST_SELECTED`, and consumes provider-local `subscription_units`. Quota pressure changes the preference score or rejects an exhausted resource; it is never converted into a public cash value.

## Persistence

SQLite provides a zero-service local deployment. Decisions and receipts are stored as validated JSON plus indexed lookup columns. The store can be replaced later by an interface-backed service.

Action input and context are redacted from persisted decisions by default, and outputs are not persisted by default. The live decision returned to the invoking process still contains the request needed for immediate execution. Stored redacted decisions are intentionally non-replayable. This limits accidental sensitive-data retention and keeps the receipt database focused on economics.

Idempotency records atomically bind a caller key to a canonical action hash and its receipt IDs. Replays avoid execution and return those receipts, but cannot reconstruct output unless an operator later enables a separate output store.

## Agent interfaces

- Python API for embedded runtimes.
- JSON CLI for skills and shell-capable agents.
- MCP server for standard tool clients.
- Native tool schema exports for providers whose application owns the function-call loop.

All call the same service methods to prevent behavioral drift. Model tools use paginated capability search and compact route/run envelopes by default; complete decisions remain queryable by ID. Runtime approval ceilings are process/operator configuration and are not exposed as model-controlled function arguments.

## Existing-agent instrumentation

OpenAI and Anthropic clients can be wrapped at their normal `create` calls without adding those SDKs as dependencies. The wrapper records usage, timing, and terminal status but never prompts or outputs. The trace ingestor accepts OTLP JSON or JSON Lines, reconstructs common call types, and compares only capabilities the operator has explicitly registered. This is passive profiling, not semantic equivalence inference.

## Calibration

Cold-start manifests contain priors, not truth. `Router.benchmark` executes feasible alternatives sequentially and produces comparable observed receipts. Sequential execution reduces contention bias; explicit confirmation, normal hard constraints, and approval ceilings remain in force. Delegates and non-idempotent routes are skipped by default. Benchmarking is deliberately outside the model-facing tool surface so an agent cannot silently multiply paid calls.

## Qualification and workflows

External supply is persisted separately from the runtime Registry. Discovery creates disabled candidates; qualification and activation are explicit operator transitions bound to a canonical behavior fingerprint. The Registry contains only trusted manifest routes and active, fingerprint-matching candidates. `Router.execute` rechecks current policy, capability, active state, and fingerprint at the invocation boundary.

Workflow execution is an additive SDK/CLI layer above the existing action router. The caller supplies the DAG. Steps are routed just in time and reuse approvals, fallback, validation, receipts, idempotency, and observation. Inputs and intermediate outputs stay in memory; checkpoints contain only hashes, status, and selected IDs.

## Economic accounting

`ResourceVector` remains the raw compatibility vector. `ResourceAccounting` is the authoritative evidence sidecar. Cash evidence, pool-local subscription usage, measured model usage, and tool footprint remain separable. Rate-card and benchmark stores are immutable/isolated from production history. Counterfactual and private policy valuations are report/scoring views, not execution charges.

## Economic interoperability

Versioned capabilities define what is offered; expiring quotes define price; signed receipts and validation results define delivery evidence. Local/remote registries load only providers relevant to the requested capability. Provider claims remain priors, while measured or attested observations drive reputation.

Payment adapters sit behind an operator budget and a separate financial approval. The OSS ledger records reservation/capture/refund events but does not hold funds, create accounts, or clear between providers.

## Future extension points

1. Confidence intervals and contextual bandit routing.
2. Learned goal decomposition and persistent result caching.
3. Sandboxed hosted executors.
4. Organization policy services and private catalogs.
5. Public-key identity and cross-organization attestation.
6. Hosted marketplace accounts, custody, payouts, and fraud controls.
7. Richer OpenTelemetry semantic events, exporters, and trace-to-action correlation.
