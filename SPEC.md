# AEEP 0.2 protocol specification

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
9. Represent host-owned subscription resources without converting them into money.
10. Exchange capabilities, quotes, receipts, observations, and payment lifecycle events.

## 2. Non-goals

AEEP 0.2 does not define:

- model prompts or planner behavior;
- semantic equivalence discovery for arbitrary tools;
- transport framing beyond the included adapters;
- custody, payout, or rail-specific settlement;
- a transferable token;
- identity, OAuth, or global trust infrastructure;
- public marketplace governance.

## 3. Capability

A `capability` is a stable semantic action name such as `text.stats`, `github.issue.create`, or the versioned `weather.current@1`. Shared network definitions use a namespace, name, input/output schemas, side-effect class, and version.

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
- kind: `python`, `command`, `http`, `mcp`, `host`, or legacy `delegate`;
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
- `subscription_units`

Implementations MUST NOT silently represent one provider's model token or subscription unit as another provider's. `subscription_units` are provider-local capacity measurements, not money or transferable credits. Conversion through a caller's private shadow price is permitted, but the raw fields MUST remain available.

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

The reference scorer applies a configurable penalty to low-confidence estimates. Confidence is not an observation and MUST NOT bypass hard constraints.

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

An explicitly supplied available resource capacity, including zero GPU capacity, MUST reject a route whose estimate exceeds it.

Every rejection MUST include a machine-readable candidate entry and human-readable reason.

## 9. Ranking

Only feasible routes are ranked.

The reference implementation computes burden components for monetary cost, latency, compute pressure, subscription pressure, unreliability, low quality, risk, and locality. Resource and monetary burden are adjusted by expected attempts using `1 / P(success)`. Subscription pressure remains a separate score component and MUST NOT be published as an exchange rate.

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

If an output schema exists, a successful transport result MUST be validated. Transport success, execution success, schema validity, task validity, and quality MUST remain distinct in the receipt. Schema, exact-match, range, state-transition, callback, downstream, optional LLM, and optional human validators use the same result envelope.

## 12. Fallback

Fallback MAY proceed to the next ranked feasible route after clear failure, timeout, rejection, or invalid output when policy allows.

Fallback MUST NOT automatically retry a non-idempotent action unless explicitly enabled. A timeout is ambiguous for remote side effects.

When an `idempotency_key` is present, the reference implementation atomically claims it against a hash of the capability and canonical input. Reuse with different input MUST fail closed. Completed duplicate calls return the stored receipt set without re-execution; action output is unavailable because outputs are not persisted by default. HTTP, command, and MCP adapters propagate the key without shell interpolation.

## 13. ExecutionReceipt

A receipt records:

- decision/action/capability/executor identifiers;
- executor kind;
- status and attempt number;
- start/end timestamps;
- estimate used for the decision;
- observed resource vector;
- transport/execution/schema/task validity and quality;
- validation results;
- bounded error data;
- trace ID;
- adapter metadata.

A host/delegated placeholder receipt MUST NOT be treated as a failed observation. The later externally reported receipt is the observed result and MUST apply only to the selected feasible host/delegate exactly once.

## 14. Historical learning

The reference estimator blends static priors with an exponentially weighted history conditioned on a privacy-preserving input-size bucket. Invalid outputs count against successful completion. Host-selected, delegated, and unknown placeholder statuses are ignored.

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
- `aeep_request_quotes`
- `aeep_get_metrics`

Provider-specific declaration shapes are projections of the same JSON contracts.

Capability listing MUST support progressive disclosure. The reference tools accept search, prefix, pagination, and detail controls. Route and execute tools return compact decision/outcome objects by default; full decisions remain available through explicit detail or inspection.

Quote acceptance, payment authorization, reservation, capture, refund, and benchmarking MUST NOT be exposed as unrestricted model tools.

## 18. MCP transport

The reference implementation supports newline-delimited stdio and Streamable HTTP. It implements the stateless `2026-07-28` request model and a compatibility path for legacy `2025-11-25` servers/clients that use `initialize` and `notifications/initialized`.

For `2026-07-28`:

- every request MUST carry `io.modelcontextprotocol/protocolVersion` and `io.modelcontextprotocol/clientCapabilities` in `params._meta`;
- HTTP requests MUST carry the same protocol version in `MCP-Protocol-Version`;
- HTTP requests MUST mirror the JSON-RPC method in `Mcp-Method`; tool calls MUST mirror the tool name in `Mcp-Name`;
- a client SHOULD use `server/discover` for stdio version negotiation and MAY cache discovery/list results according to `ttlMs` and `cacheScope`;
- every successful result MUST include `resultType`; the reference implementation emits `complete` and rejects `input_required` because multi-round tool continuation is outside `0.2`;
- when a tool schema declares `x-mcp-header`, only statically reachable primitive string, integer, or boolean parameters are projected into `Mcp-Param-*` headers. Header names are case-insensitively unique, values use the MCP encoding rules, and header/body disagreement MUST fail closed.

MCP stdio and HTTP messages MUST be bounded. Remote MCP HTTP targets MUST pass the same network/SSRF policy as ordinary HTTP executors; the reference client disables redirects and ambient proxy inheritance by default.

AEEP-specific usage can be returned under `_meta["org.aeep/usage"]` as a `ResourceVector` object. A client MUST treat unrecognized metadata as optional.

## 19. Subscription resources and hosts

A `SubscriptionResource` identifies a provider/product, host/CLI/MCP access mode, capabilities, and quota state. Valid quota states are `abundant`, `normal`, `tight`, `critical`, `exhausted`, and `unknown`, with confidence and source. An exhausted resource MUST be infeasible. Runtime quota data MAY override a manifest prior. Implementations MUST NOT scrape undocumented consumer billing dashboards or convert quota into cash.

A `host` executor references one subscription resource. Selection returns `HOST_SELECTED`; AEEP does not call a model API. The current host performs the bounded action and reports one terminal outcome.

Runtime `QuotaObservation` records override manifest priors until replaced. A terminal selected-host outcome MAY include one quota observation for its own resource.

## 20. Quotes and signed receipts

A `QuoteRequest` identifies an action and optional executor set. A `Quote` identifies provider, executor, capability, cash amount, estimate, terms, expiry, and optional signature. A `QuoteAcceptance` binds an action to one unexpired amount. Acceptance MUST NOT silently exceed an operator maximum.

The reference local signer uses an explicit `hmac-sha256` envelope and secret environment variable. It provides tamper evidence inside a shared trust domain; it MUST NOT be represented as public-key provider identity or global attestation.

## 21. Provider discovery and trust

A `ProviderDescriptor` supplies versioned capability definitions and executor descriptors. Local and reviewed remote registries MAY be combined. Discovery SHOULD be capability-scoped and lazy so irrelevant schemas are not exposed to the model. Remote registries MUST use bounded responses and the ordinary HTTPS, allowlist, DNS/IP, redirect, and proxy policy.

Provider descriptors and declared estimates are claims. Reputation MUST use measured, verified, or attested `Observation` objects and MUST exclude untrusted/self-asserted claims from observed statistics.

## 22. Counterfactual profiling

A counterfactual report compares an observed receipt only with routes that were feasible in its original decision. Cash savings and subscription capacity conservation remain separate fields; subscription units MUST NOT be labeled as currency.

## 23. Payments, budgets, and ledger events

The OSS protocol defines a rail-neutral `PaymentAdapter`, `AgentBudget`, `AuthorizationPolicy`, `PaymentReservation`, `PaymentCapture`, `PaymentRefund`, and append-only ledger event shape. Financial reservations require an operator-controlled `financial` ceiling and any configured human approval. Model arguments MUST NOT raise either ceiling.

Free, prepaid, invoice, x402, MPP, and enterprise rails MAY implement the adapter. AEEP does not define custody, provider accounts, payouts, fraud systems, or clearing operations.

## 24. Provider supply

Provider descriptors MAY be generated from decorated Python callables or imported from reviewed argv-only CLI, MCP, or OpenAPI definitions. CLI imports MUST use argv and MUST NOT introduce shell interpolation. Imported writes MUST default to non-automatic execution.

An MCP server importer MAY inspect `tools/list` and generate reviewed local descriptors. OpenAPI importers SHOULD accept an explicit operation-to-capability map; generated names are provider-local and do not establish semantic equivalence.

## 25. Existing-agent profiling

The reference trace ingestor accepts OTLP JSON, plain span JSON, and JSON Lines. It reconstructs model, tool, browser, command, HTTP, and MCP calls from standard or AEEP attributes, retaining resource totals and retry/failure counts without persisting payloads or outputs. Recommendations MUST be limited to explicitly registered equivalent capabilities.

OpenAI and Anthropic SDK wrappers record latency, usage, outcome, and optionally operator-supplied monetary calculation. Unavailable provider billing is recorded as unknown, not inferred from a static price table.

## 26. Versioning

The manifest/spec version is `0.2`; `0.1` and `0.15` manifests remain loadable. Backward-incompatible object changes require a new version. New optional resource dimensions or metadata MAY be added without invalidating older clients when unknown fields are handled at a negotiated boundary.
