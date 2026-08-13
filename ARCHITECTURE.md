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
 Python  CLI      HTTP     MCP       delegate
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

Cold-start estimates come from executor configuration. Real receipts are blended using sample-aware history. A provider's advertised number remains a prior; it is not copied into observed performance.

A production network can replace the local EWMA with confidence intervals, task-conditioned models, quantile latency, drift detection, and signed attestations without changing the core objects.

## Execution boundaries

### Python

Best for trusted, deterministic in-process work. It has low overhead but weak isolation. A timed-out worker thread cannot be forcibly killed safely.

### Command

Uses `create_subprocess_exec`, never a shell. It offers process isolation, timeouts, bounded output, and host metrics. It is the preferred local boundary for tools with meaningful side effects or dependencies.

### HTTP

Uses bounded streaming and conservative target validation. It is appropriate for ordinary REST APIs and can learn monetary cost from a trusted response header.

### MCP

Discovers the configured tool, measures schema/context overhead, invokes it over stdio or Streamable HTTP, reads optional AEEP usage metadata, and caches discovery/tool schemas according to protocol hints. The client probes modern stateless MCP first and falls back to the legacy initialize lifecycle where required.

The modern path mirrors protocol version, method, tool name, and schema-authorized primitive parameters into HTTP headers; validates header/body consistency; bounds messages; and applies the same SSRF/allowlist/HTTPS policy as the HTTP executor. AEEP accepts only complete single-round tool results in `0.1`; multi-round `input_required` continuation belongs to the host agent until a later protocol adapter is defined.

### Delegate

Represents an execution surface owned by the host agent: browser, GUI, computer-use, model reasoning, or an unavailable native tool. AEEP returns instructions and a decision ID; the host reports the outcome later. To prevent arbitrary history injection, external reports are accepted only for the selected, feasible delegate and only once per decision/executor pair. Trusted out-of-band measurement uses `ActionProfiler` instead.

## Persistence

SQLite provides a zero-service local deployment. Decisions and receipts are stored as validated JSON plus indexed lookup columns. The store can be replaced later by an interface-backed service.

Action input and context are redacted from persisted decisions by default, and outputs are not persisted by default. The live decision returned to the invoking process still contains the request needed for immediate execution. Stored redacted decisions are intentionally non-replayable. This limits accidental sensitive-data retention and keeps the receipt database focused on economics.

## Agent interfaces

- Python API for embedded runtimes.
- JSON CLI for skills and shell-capable agents.
- MCP server for standard tool clients.
- Native tool schema exports for providers whose application owns the function-call loop.

All call the same service methods to prevent behavioral drift. Runtime approval ceilings are process/operator configuration and are not exposed as model-controlled function arguments.

## Calibration

Cold-start manifests contain priors, not truth. `Router.benchmark` executes feasible alternatives sequentially and produces comparable observed receipts. Sequential execution reduces contention bias; explicit confirmation, normal hard constraints, and approval ceilings remain in force. Delegates and non-idempotent routes are skipped by default. Benchmarking is deliberately outside the model-facing tool surface so an agent cannot silently multiply paid calls.

## Future extension points

1. Async live quote adapters.
2. Capability registry and semantic versioning.
3. Confidence intervals and contextual bandit routing.
4. x402/MPP/payment adapters.
5. Signed receipts and provider reputation.
6. Workflow-level optimization across action DAGs.
7. Sandboxed hosted executors.
8. Organization policy and private catalogs.
9. Counterfactual profiler that recognizes waste in completed traces.
10. Richer OpenTelemetry semantic events, exporters, and trace-to-action correlation.
