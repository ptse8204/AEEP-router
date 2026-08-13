# AEEP 0.1 protocol specification

AEEP is an open, provider-neutral contract for profiling and choosing execution routes for bounded agent actions. It complements MCP/HTTP/CLI transports and payment systems rather than replacing them.

Normative keywords **MUST**, **SHOULD**, and **MAY** follow RFC 2119 usage.

## 1. Goals

A conforming implementation can:

1. Represent a semantic action and hard constraints.
2. Advertise multiple executor routes for that action.
3. Preserve estimates in raw resource dimensions.
4. reject infeasible routes before preference scoring.
5. Produce an explainable, deterministic decision.
6. Record actual execution receipts.
7. Update future estimates from observed outcomes without treating provider claims as observations.
8. Calibrate safe alternatives sequentially without weakening routing constraints.

## 2. Non-goals

AEEP 0.1 does not define:

- model prompts or planner behavior;
- semantic equivalence discovery for arbitrary tools;
- transport framing beyond the included adapters;
- money transmission or settlement;
- a transferable token;
- identity, OAuth, attestation, or global trust;
- public marketplace governance.

## 3. Capability

A `capability` is a stable semantic action name such as `text.stats`, `github.issue.create`, or `weather.current`.

An operator MUST only register executors under the same capability when they consider their input/output contracts equivalent enough for the application. Capability names SHOULD be namespaced in shared ecosystems.

## 4. ActionRequest

Required:

- `action_id`: unique request identifier; generated when omitted.
- `capability`: requested semantic action.
- `input`: JSON object.
- `policy`: policy name.

Optional:

- hard constraints;
- action context including data sensitivity, state locality, region, available compute/quota, labels, and trace context;
- `idempotency_key`.

A router MUST validate the input against every candidate's `input_schema`. A contract failure for one candidate MUST NOT invalidate compatible candidates.

## 5. ExecutorSpec

An executor declares:

- unique `id`;
- `capability`;
- kind: `python`, `command`, `http`, `mcp`, or `delegate`;
- input and optional output JSON Schema;
- cold-start `RouteEstimate`;
- side effect level;
- locality and network requirement;
- data residency claims;
- idempotence and automatic-execution flags;
- adapter configuration.

Provider-declared estimates MUST be treated as priors, not verified observations.

## 6. Raw resources

`ResourceVector` fields:

- `monetary_usd`
- `latency_ms`
- `cpu_ms`
- `memory_mb_seconds`
- `peak_memory_mb`
- `gpu_ms`
- `network_bytes`
- `context_tokens`
- `input_tokens`
- `output_tokens`

Implementations MUST NOT silently represent one provider's model token as another provider's token. Conversion through a caller's private shadow price is permitted, but the raw fields MUST remain available.

## 7. RouteEstimate

A route estimate contains:

- resource vector;
- probability of successful completion;
- expected output quality;
- risk score;
- confidence;
- source (`static`, `historical`, `blended`, `quote`, `observed`);
- historical sample size.

Probability and scores are in `[0,1]`.

## 8. Feasibility

A route MUST be rejected when it violates an effective hard constraint. The effective constraint is the strictest combination of manifest policy and request constraint; a request MUST NOT weaken operator guardrails.

Constraint classes include:

- cash, latency, CPU, memory, GPU, network, and context maxima;
- minimum success and quality;
- maximum risk;
- side-effect ceiling;
- network/local-only policy;
- executor-kind and executor-ID allowlists plus explicit ID denylists;
- data residency;
- restricted-data handling;
- currently remaining monetary/context/memory capacity.

Every rejection MUST include a machine-readable candidate entry and human-readable reason.

## 9. Ranking

Only feasible routes are ranked.

The reference implementation computes burden components for monetary cost, latency, compute pressure, unreliability, low quality, risk, and locality. Resource and monetary burden are adjusted by expected attempts using `1 / P(success)`.

A custom implementation MAY use a different ranking algorithm if it:

- preserves hard constraints;
- returns score/explanation components;
- is deterministic for equivalent inputs when configured as deterministic;
- does not discard raw measurements.

## 10. Runtime approval

Routing permission and execution approval are separate.

An implementation MUST NOT execute a route whose side-effect level exceeds the explicit runtime approval. An executor marked unsafe for automatic execution requires a separate explicit approval. Model-supplied tool arguments MUST NOT raise either approval ceiling; approval is operator/host configuration. Delegated routes return instructions and remain subject to host-runtime permissions.

Side-effect order:

```text
none < read < write < destructive < financial
```

## 11. Execution and validation

An adapter returns a `RawExecution` with status, output, actual resources, bounded diagnostics, and metadata.

If an output schema exists, a successful transport result MUST be validated. Transport success and output validity MUST remain distinct in the receipt.

## 12. Fallback

Fallback MAY proceed to the next ranked feasible route after clear failure, timeout, rejection, or invalid output when policy allows.

Fallback MUST NOT automatically retry a non-idempotent action unless explicitly enabled. A timeout is ambiguous for remote side effects.

## 13. ExecutionReceipt

A receipt records:

- decision/action/capability/executor identifiers;
- executor kind;
- status and attempt number;
- start/end timestamps;
- estimate used for the decision;
- observed resource vector;
- output validity;
- bounded error data;
- trace ID;
- adapter metadata.

A delegated placeholder receipt MUST NOT be treated as a failed observation. The later externally reported receipt is the observed result.

## 14. Historical learning

The reference estimator blends static priors with an exponentially weighted history. Invalid outputs count against successful completion. Delegated and unknown placeholder statuses are ignored.

Implementations SHOULD expose sample size and estimate source. They MUST avoid presenting learned estimates as exact guarantees. Externally reported outcomes are untrusted input unless authenticated or attested and MAY be excluded from shared reputation.

## 15. Persistence and minimization

The reference implementation redacts action input and action context from persisted decisions by default. Implementations SHOULD minimize stored task data and MUST make full-payload persistence an explicit operator choice. Output previews are opt-in. Redacted stored decisions are audit records and MUST NOT be re-executed as if they contained the original request.

## 16. Benchmarking

A benchmark sequentially executes feasible alternatives to reduce resource-contention bias and produces a `BenchmarkResult`. Implementations MUST preserve all hard constraints and runtime approvals. They SHOULD exclude delegated and non-idempotent routes by default and MUST require an explicit operator confirmation because calibration may incur charges or disclose input to multiple providers.

## 17. Agent tools

The reference server exposes:

- `aeep_list_capabilities`
- `aeep_route_action`
- `aeep_execute_action`
- `aeep_record_outcome`

Provider-specific declaration shapes are projections of the same JSON contracts.

## 18. MCP transport

The reference implementation supports newline-delimited stdio and Streamable HTTP. It implements the stateless `2026-07-28` request model and a compatibility path for legacy `2025-11-25` servers/clients that use `initialize` and `notifications/initialized`.

For `2026-07-28`:

- every request MUST carry `io.modelcontextprotocol/protocolVersion` and `io.modelcontextprotocol/clientCapabilities` in `params._meta`;
- HTTP requests MUST carry the same protocol version in `MCP-Protocol-Version`;
- HTTP requests MUST mirror the JSON-RPC method in `Mcp-Method`; tool calls MUST mirror the tool name in `Mcp-Name`;
- a client SHOULD use `server/discover` for stdio version negotiation and MAY cache discovery/list results according to `ttlMs` and `cacheScope`;
- every successful result MUST include `resultType`; the reference implementation emits `complete` and rejects `input_required` because multi-round tool continuation is outside `0.1`;
- when a tool schema declares `x-mcp-header`, only statically reachable primitive string, integer, or boolean parameters are projected into `Mcp-Param-*` headers. Header names are case-insensitively unique, values use the MCP encoding rules, and header/body disagreement MUST fail closed.

MCP stdio and HTTP messages MUST be bounded. Remote MCP HTTP targets MUST pass the same network/SSRF policy as ordinary HTTP executors; the reference client disables redirects and ambient proxy inheritance by default.

AEEP-specific usage can be returned under `_meta["org.aeep/usage"]` as a `ResourceVector` object. A client MUST treat unrecognized metadata as optional.

## 19. Versioning

The manifest/spec version is `0.1`. Backward-incompatible object changes require a new version. New optional resource dimensions or metadata MAY be added without invalidating older clients when unknown fields are handled at a negotiated boundary.
