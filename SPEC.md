# AEEP 0.7 protocol specification

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
11. Bind a signed expected/maximum charge to one action and exact executor fingerprint.
12. Prepare a single-use route without making ordinary routing perform network I/O.
13. Reserve the maximum, capture verified actual cost, and release the remainder.
14. Preserve an auditable evidence chain without treating unknown cash as zero.

## 2. Non-goals

AEEP 0.7 does not define:

- model prompts or planner behavior;
- semantic equivalence discovery for arbitrary tools;
- transport framing beyond the included adapters;
- custody, payout, or rail-specific settlement;
- a transferable token;
- identity, OAuth, or global trust infrastructure;
- public marketplace governance.

It also does not define cryptocurrency, blockchain settlement, transferable
consumer tokens, custody, provider payouts, exchange rates, autonomous provider
onboarding, or automatic route qualification/activation. The 0.4 network is an
economic evidence exchange, not a public marketplace or financial product.

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
- `cached_input_tokens`
- `output_tokens`
- `subscription_units`

Typed `ModelTokenUsage` evidence additionally records
`cache_write_input_tokens` so cache reads, writes, and uncached input can be
priced without double counting.

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

After at least five exact-cohort observations, an estimate MAY also include
empirical nearest-rank p50/p95 resources, observed cash p95, a Wilson success
lower bound, and a quality lower bound. These bounds describe history; observed
cash p95 MUST NOT authorize payment or replace an immutable signed maximum.

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

The reference implementation computes separate burden components for attributable cash, private policy valuation, latency, compute pressure, subscription pressure, unreliability, low quality, risk, and locality. Burden is adjusted by expected attempts using `1 / P(success)`. Subscription pressure remains a separate score component and MUST NOT be published as an exchange rate. API-equivalent counterfactuals are never scorer inputs.

A custom implementation MAY use a different ranking algorithm if it:

- preserves hard constraints;
- returns score/explanation components;
- is deterministic for equivalent inputs when configured as deterministic;
- does not discard raw measurements.

An implementation MAY abstain from optimization and retain an
operator-configured baseline only when that baseline is itself feasible. The
reference implementation returns `BYPASS_ROUTER` for a pinned route, a sole
feasible route, or a score improvement that does not exceed measured routing
overhead plus policy margin. Abstention MUST happen after hard constraints and
MUST NOT restore a rejected route.

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

The reference estimator blends static priors with exponentially weighted
history only from the exact `aeep-evidence-cohort-v1`: capability, executor,
behavior fingerprint, provider/model/adapter, region/account tier, action-size
bucket, validator digest, cache namespace/profile, and economic-evidence level.
Invalid outputs count against successful completion. Host-selected, delegated,
unknown placeholder, legacy-unbound, and cohort-mismatched rows are ignored for
live routing.

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
- `aeep_estimate_route_prices`
- `aeep_request_quotes` (deprecated alias)
- `aeep_get_metrics`
- `aeep_show_prepared_decision`
- `aeep_show_quote`
- `aeep_show_settlement`

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
- every successful result MUST include `resultType`; the reference implementation emits `complete` and rejects `input_required` because multi-round tool continuation remains outside the router;
- when a tool schema declares `x-mcp-header`, only statically reachable primitive string, integer, or boolean parameters are projected into `Mcp-Param-*` headers. Header names are case-insensitively unique, values use the MCP encoding rules, and header/body disagreement MUST fail closed.

MCP stdio and HTTP messages MUST be bounded. Remote MCP HTTP targets MUST pass the same network/SSRF policy as ordinary HTTP executors; the reference client disables redirects and ambient proxy inheritance by default.

AEEP-specific usage can be returned under `_meta["org.aeep/usage"]` as a `ResourceVector` object. A client MUST treat unrecognized metadata as optional.

## 19. Subscription resources and hosts

A `SubscriptionResource` identifies a provider/product, host/CLI/MCP access mode, capabilities, and quota state. Valid quota states are `abundant`, `normal`, `tight`, `critical`, `exhausted`, and `unknown`, with confidence and source. An exhausted resource MUST be infeasible. Runtime quota data MAY override a manifest prior. Implementations MUST NOT scrape undocumented consumer billing dashboards or convert quota into cash.

A `host` executor references one subscription resource. Selection returns `HOST_SELECTED`; AEEP does not call a model API. The current host performs the bounded action and reports one terminal outcome.

Runtime `QuotaObservation` records override manifest priors until replaced. A terminal selected-host outcome MAY include one quota observation for its own resource.

## 20. Legacy quotes and signed receipts

The pre-0.4 `QuoteRequest`, `Quote`, and `QuoteAcceptance` objects remain readable
for compatibility. They do not provide the request binding, public-key trust, or
guaranteed maximum required by the 0.4 prepared-routing path. An implementation
MUST NOT relabel a legacy/static quote as a binding `SIGNED_QUOTE`.

The local `hmac-sha256` signer remains available for compatibility and
single-trust-domain testing. It MUST NOT be represented as cross-organization
identity. Provider economic evidence accepted by the 0.4 trust store MUST use an
allowed public-key algorithm; the reference algorithm is Ed25519.

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

The current manifest/spec version is `0.5`; `0.1`, `0.15`, `0.2`, `0.3`, and
`0.4` manifests remain loadable. New economic schemas use `schema_version:
"0.5"`;
older schemas are not silently redefined. Backward-incompatible object changes
require a new version. New optional resource dimensions or metadata MAY be added
without invalidating older clients when unknown fields are handled at a
negotiated boundary.

## 27. Economic evidence

Actual cash, provider-local subscription usage, API-equivalent counterfactuals, and policy valuations are non-interchangeable ledgers. Missing cash evidence is unavailable, never zero. A zero cash total requires complete verified or billing-reconciled evidence. Counterfactual and policy values MUST NOT enter actual-cash totals, cash constraints, or public cash-savings claims.

`ResourceVector.monetary_usd` and `subscription_units` remain compatibility mirrors. New implementations MUST inspect `ResourceAccounting` before interpreting either mirror. Model-facing outcome reports are self-asserted and cannot create verified accounting evidence.

## 28. Rate cards

Rate cards are canonical, content-addressed snapshots. Calculations use decimal arithmetic and retain snapshot, meter, and applied-rate identifiers. Historical reports retain the original snapshot and value; revaluation creates a derived report. Applying an API tariff to a subscription-backed model route creates an API-equivalent counterfactual, not actual cash.

## 29. Qualification lifecycle

Imported and discovered routes enter as inert candidates. Qualification binds reviewed schemas, adapter identity, validators, side effects, idempotency, safety properties, and dynamic cases to an exact behavior fingerprint. Qualification never activates. Execution requires an active local record with the same fingerprint; drift suspends the route before another invocation.

## 30. Workflows and campaigns

Workflow requests contain caller-authored bounded DAGs. Every step uses the ordinary route/execute enforcement path. Bindings are RFC 6901 JSON Pointers and replace existing input slots only. Workflow accounting includes every retry and fallback, groups subscription usage by pool and unit, and never sums parallel wall time or memory peaks.

Repeated benchmark campaigns use an isolated database, immutable suite inputs and rate snapshots, deterministic route order, distinct cold/warm conditions, and raw trial retention without action inputs or outputs. Qualification, activation, workflow resume, campaign execution, and accounting trust elevation remain outside model-facing tools.

## 31. Economic primitive types

All 0.4 economic records are strict and immutable. Monetary values MUST use
`CurrencyAmount` with a non-negative finite decimal string and an uppercase
three-letter currency code. Implementations MUST reject binary floats, NaN,
infinity, currency mixing, and ambiguous negative zero. A router instance MUST
use one configured settlement currency and MUST NOT perform implicit conversion.
The 0.4 reference router is USD-only because its compatibility policy, budget,
and history fields are USD-denominated; enabling economic routing with another
currency MUST fail at startup. Protocol models MAY parse another internally
consistent three-letter currency for interoperability/future versions, but that
does not authorize routing, conversion, or settlement in the 0.4 router.

Native provider usage uses `MeterQuantity(meter, unit, quantity)`. Quantity MUST
be a non-negative finite decimal string, units MUST be explicit, duplicate
`(meter, unit)` pairs MUST be rejected, and custom meters MUST be provider
namespaced. Model tokens are only some of the valid meters.

`PricingRule` supports fixed and linear per-unit charges, free quantity, minimum
and maximum amounts, quantity increments, and explicit decimal rounding. All
amounts in one rule MUST use one currency. Executable billing behavior MUST use
the structured `BillingTrigger`, `FailureChargePolicy`, and `RetryChargePolicy`
enums; display text MUST NOT decide whether a failed attempt is billed.

```text
BillingTrigger:
  ON_SUCCESS | ON_ATTEMPT | ON_ACCEPTED_RESULT | ON_PROVIDER_START |
  MANUAL_RECONCILIATION
FailureChargePolicy:
  NO_CHARGE | CHARGE_ACTUAL_USAGE | CHARGE_FIXED_ATTEMPT_FEE |
  CHARGE_MAXIMUM | MANUAL_RECONCILIATION
RetryChargePolicy:
  EACH_ATTEMPT | FIRST_ATTEMPT_ONLY | SUCCESSFUL_ATTEMPT_ONLY |
  MANUAL_RECONCILIATION
```

`CapabilityOffer.fixed_attempt_fee` and `BoundedQuote.fixed_attempt_fee` MUST be
present exactly when `failure_charge_policy` is
`CHARGE_FIXED_ATTEMPT_FEE`, MUST use the settlement/quote currency, and in a
quote MUST NOT exceed `maximum_amount`. When a quote references an offer, the
fee and the other structured billing terms MUST match the offer. Free-form terms
MUST NOT supply a missing executable attempt fee.

## 32. Canonicalization and signatures

Signed economic records MUST use `aeep-canonical-json-v1`: UTF-8 JSON, NFC
Unicode, stable key ordering, normalized UTC timestamps, decimal strings,
explicit nulls, no floats, and no non-finite values. The root `signature` field
is excluded from the signed payload; the envelope carries the canonicalization
version, algorithm, key ID, and base64url value.

The reference cross-provider algorithm is Ed25519. Verifiers MUST allowlist
algorithms and MUST bind a trusted key to one provider identity. Trust metadata
includes validity bounds, status, revocation time, allowed capabilities, and
allowed quote hosts. Unknown, expired, revoked, provider-mismatched, or
endpoint-mismatched keys MUST fail closed for new preparation/execution.
Historical evidence MAY remain verifiable at its signing time using retained
revocation metadata. A response endpoint MUST NOT introduce a new trusted key.
Rotation requires a verified chain from an already trusted provider key.

## 33. Capability offers

A `CapabilityOffer` is a reusable provider claim for an exact versioned
capability, executor ID, and behavior fingerprint. It contains structured
pricing and billing policies, including the signed fixed attempt fee when that
failure policy is selected, settlement currency, validity bounds, terms digest,
provider identity, and signature.

An offer MUST be valid at use time, signed by a trusted key authorized for its
provider/capability/host, and not locally revoked. A duplicate identical offer
is idempotent. Reusing an offer ID with different canonical content MUST fail.
An offer is `PUBLISHED_OFFER` evidence only: it does not qualify or activate a
route and does not prove performance or actual billing.

## 34. Quote requests and disclosure

`QuoteRequestV2` binds one short-lived request ID and nonce to the action ID,
versioned capability, executor ID, executor fingerprint, canonical action
digest, settlement currency, approved action features, approved disclosed quote
features, and optional maximum acceptable amount.

The action digest MUST cover capability/version, canonical input, relevant
execution constraints, and any idempotency key. Raw input MUST stay local unless
an operator explicitly declares a disclosure mapping. Default disclosure MAY
include bounded counts, byte lengths, size buckets, booleans, and enumerated
categories. Free-form prompts, resumes, job text, credentials, email addresses,
file contents, and secret-bearing URLs MUST be denied by default. A provider
MUST NOT dynamically expand disclosure. Persisted preparation audit data MUST
record disclosed primitives, never the undisclosed input.

## 35. Bounded quotes

A `BoundedQuote` is a short-lived signed provider statement for exactly one
`QuoteRequestV2`. It MUST bind the quote request ID, offer ID when used,
provider, versioned capability, executor ID, executor fingerprint, action
digest, nonce, terms digest, currency, structured billing policies, issue time,
and expiry. A dynamically priced paid route MUST carry a guaranteed
`maximum_amount`. `expected_amount` MAY be absent but MUST NOT exceed the
maximum and MUST use the same currency. A selected fixed-attempt failure charge
MUST be an explicit signed `fixed_attempt_fee`; descriptive terms alone are not
billable input.

The consumer MUST verify signature trust, endpoint authorization, request
binding, bounded TTL, issue-time skew, expiry, and nonce freshness before use.
An accepted nonce MUST be consumed atomically. A replay, altered field,
different action, different executor/fingerprint, stale quote, or currency
mismatch MUST be rejected before reservation.

## 36. Quote acquisition and scoring

Ordinary `route()` MUST remain deterministic and network-free. Remote economic
networking is disabled by default and requires operator configuration.
`prepare_route()` MUST first find active, qualified, exact-capability routes and
apply every non-price hard constraint. Only a bounded leading shortlist may be
contacted; the reference default is at most three live quotes, requested
concurrently within per-provider and total deadlines.

Quote-acquisition failure behavior is explicit:
`REQUIRE_BINDING_QUOTE`, `ALLOW_VERIFIED_OFFER`, `ALLOW_STATIC_PRIOR`, or
`TREAT_AS_UNAVAILABLE`. A request MAY tighten this operator policy but MUST NOT
weaken it.

`ALLOW_STATIC_PRIOR` permits estimate/ranking use only. An anonymous static
prior MUST NOT authorize a nonzero reservation. A locally pinned immutable rate
card may authorize only when the prepared record binds its snapshot, exact rate
IDs, and bounded meter quantities as described below.

Remote quote clients MUST use locally configured HTTPS endpoints and exact host
allowlists, revalidate DNS/IP policy, block non-public and metadata addresses by
default, disable redirects and ambient proxies, bound request/response bytes,
validate content type, sanitize errors, and verify signatures before use. An
advertised endpoint alone grants no network authority.

Preparation MUST record live quote request count and quote/preparation latency.
Workflow and proof reporting MUST use non-overlapping components and report
total completion time as local preparation plus quote acquisition plus execution
plus settlement. A wall-clock duration for the whole `prepare_route()` call MAY
also be reported, but MUST NOT be added to quote latency a second time.

For a valid binding quote, hard cash feasibility MUST use `maximum_amount`.
Ranking SHOULD use `expected_amount`; when absent it MUST use the maximum plus
uncertainty rather than inventing a lower amount. Quotes MAY update provider
cash estimates only. They MUST NOT alter qualification, task success, quality,
reliability, latency observations, or safety evidence. A quote failure MUST
follow the configured failure policy and MUST NOT turn unknown paid cost into
zero.

## 37. Prepared route decisions

`prepare_route(request)` returns an immutable `PreparedRouteDecision` without
executing it. The record contains action and effective-policy digests, selected
executor/fingerprint and authorization, all quote IDs, candidate rankings,
rejections, quote failures, approved disclosure, expected accounting, maximum
authorization, preparation/quote latency, timestamps, expiry, and state.
Infeasible decisions carry no selected route or cash authorization.

Pre-execution expected/maximum cash and its evidence level MUST remain estimate
fields on the candidate ranking/quote. They MUST NOT be placed into post-execution
actual cash accounting or reported as settlement.

Every nonzero `maximum_cash_authorization` MUST identify exactly one immutable
authorization basis through `authorization_kind` and `authorization_id`:
`SIGNED_QUOTE`, `PUBLISHED_OFFER`, or `PINNED_RATE_CARD`. The corresponding
`selected_quote_id`, `selected_offer_id`, or `selected_rate_card_id` MUST match
that ID, and no second basis may be selected. A 0.4 `PUBLISHED_OFFER` basis is
limited to fixed pricing that determines an exact maximum; a usage-priced offer
requires a request-bound quote. A pinned rate-card basis MUST also bind the exact
ordered rate IDs and bounded native meter quantities used to derive the maximum.
Only current, unconditional monetary rates MAY authorize in 0.4;
subscription-unit or conditional tier/region/tool/context/rule rates MUST fail
closed. An anonymous static prior MUST NOT authorize nonzero cash. A
confirmed-zero route MAY omit an authorization basis.

Immediately before `execute_prepared(prepared_id)`, an implementation MUST
atomically claim the single-use decision and revalidate decision/quote expiry,
action and policy digests, activation, exact route fingerprint, key status,
currency and budget, approval, and idempotency. Provider price evidence MUST NOT
grant execution approval. Consequential actions still require the independent
operator/host approval ceiling.

A `PREPARED` decision MAY be cancelled. A reserved but not-yet-invoked decision MUST
release its reservation. Once invocation may have started, cancellation MUST
NOT assert that the external effect failed. Re-execution is forbidden by default;
idempotent retry requires an explicitly valid new attempt identity.

## 38. Reservation, settlement, and budget

Before paid invocation, the router MUST atomically check available budget and
reserve the maximum from the selected immutable authorization using immutable
IDs and an idempotency key. For a quote this is its exact signed maximum. For a
fixed offer or pinned rate card, the maximum MUST be deterministically derived
from its bound rules/rates and the prepared request's bounded quantities.
Outstanding and indeterminate reservations reduce available budget; released
amounts do not count as spent. Unlimited credit MUST be an explicit policy, not
an infinite float.

After execution the adapter settles an independently determined actual amount:

```text
0 <= captured_amount <= immutable_authorization_maximum
released_amount = reserved_amount - captured_amount
```

All amounts MUST use the reservation currency. A completed settlement MUST
account for the full reservation. Duplicate identical operations MUST return
the prior result; a conflicting reuse of an idempotency key MUST fail. Capture
after full release, release after full capture, overcapture, excess refund,
quote/action reuse, and altered settlement-ID reuse MUST fail closed. Legacy
full capture remains equivalent to settling at the reservation maximum.

Reservations and settlements MUST retain the same `authorization_kind` and
`authorization_id` as the prepared decision. `quote_id` is mandatory for a
`SIGNED_QUOTE` basis and MUST match it; it is absent for `PUBLISHED_OFFER` and
`PINNED_RATE_CARD` bases. This linkage is the overcapture boundary and MUST NOT
be reconstructed from an unpinned estimate after invocation.

## 39. Usage statements and billable amount

Local execution evidence and provider evidence MUST remain separate. Local
measurement records model-token dimensions, tool-token dimensions, CPU, memory,
network, latency, retries, fallbacks, transport/execution/task validity, and
attempt status where available.

A signed `UsageStatement` binds provider, quote, prepared decision, action,
attempt, executor, fingerprint, execution status, native meter quantities,
provider-calculated amount when present, timestamps, and signature. It means the
provider asserted that usage; it does not prove payment or invoice billing.

The actual billable amount MUST follow the signed billing trigger, failure
policy, and retry policy. `NO_CHARGE` may produce evidenced zero. Actual-usage
billing requires adequate usage evidence. Manual or otherwise unsafe
determination remains unknown and MUST NOT default to zero or maximum unless the
signed policy explicitly requires maximum.

Missing or invalid provider usage after invocation MUST preserve the reservation
and become indeterminate when the structured policy cannot establish a charge;
it MUST NOT trigger an execution retry. `ON_ACCEPTED_RESULT` billing requires a
bound local task-valid receipt plus signed provider evidence. `ON_PROVIDER_START`
billing requires explicit provider-start evidence; a timeout alone is not proof
that the trigger occurred.

## 40. Settlement, uncertainty, and recovery

A `SettlementReceipt` binds one charge, prepared decision, quote, reservation,
and attempt to the reserved, captured, and released amounts, rail, status,
evidence level, time, and optional external reference/signature. It proves only
what the payment adapter recorded.

If invocation outcome or billing is uncertain, the implementation MUST retain
the reservation/evidence and mark the attempt `INDETERMINATE` or `DISPUTED`.
It MUST NOT report zero cost, blindly capture maximum contrary to the quote, or
blindly retry a consequential/non-idempotent action. A provider amount above the
quote maximum MUST never be captured above the maximum and MUST open a dispute.

Prepared transitions are append-only and MUST follow:

```text
PREPARED -> RESERVED -> INVOKING -> AWAITING_USAGE -> SETTLING -> SETTLED
PREPARED -> EXPIRED | CANCELLED
RESERVED -> RELEASED | CANCELLED | INDETERMINATE
INVOKING | AWAITING_USAGE | SETTLING -> INDETERMINATE | DISPUTED
INDETERMINATE -> SETTLING | SETTLED | DISPUTED
DISPUTED -> SETTLED
```

External execution and settlement are not one database transaction. Recovery
MUST inspect durable attempt/payment state, resume only idempotent settlement or
release work, and MUST NOT re-execute an external action merely because local
persistence stopped after invocation.

## 41. Reconciliation and evidence hierarchy

`BillingReconciliation` compares a settlement amount with an external invoice,
provider billing record, or operator-reviewed reference. Raw invoices are not
stored by default. Status is one of `MATCHED`, `UNDERCHARGED`, `OVERCHARGED`,
`MISSING_BILLING_RECORD`, `PENDING`, `DISPUTED`, or `RESOLVED`.

Economic evidence levels are:

```text
UNKNOWN
STATIC_PRIOR
PUBLISHED_OFFER
SIGNED_QUOTE
SIGNED_USAGE_STATEMENT
OPERATOR_ATTESTED
PAYMENT_SETTLEMENT
BILLING_RECONCILED
```

These labels describe provenance, not an unconditional truth ordering.
`OPERATOR_ATTESTED` MUST remain visibly distinct and MUST rank below payment
settlement and billing reconciliation for paid/captured-cash proof, savings, and
release gates. Manual attestation MUST NOT satisfy a policy requiring payment or
billing evidence. A narrow exact local-zero oracle MAY use visibly labeled
operator attestation only when expected and maximum are zero and no reservation,
capture, or release exists; this is confirmed-free context, not payment evidence
or proof of savings from a charge. Stronger evidence for one stable `charge_id`
MAY supersede an earlier value for reporting, while all stages remain auditable;
estimates, usage, settlement, and reconciliation MUST NOT be summed as independent
charges. A discrepancy MUST remain visible.

Unknown actual cash remains unavailable. Confirmed zero requires complete
eligible evidence. Cash-savings claims require suitable actual evidence for
both compared charges. Subscription capacity, model tokens, native meters,
latency, CPU, memory, GPU, network, quality, reliability, and risk remain
separate dimensions.

## 42. Market aggregates

A `MarketAggregate` is a signed, privacy-safe prior keyed by exact capability,
provider, executor, fingerprint, region/tier where relevant, and input bucket.
It includes cohort/window bounds, sample size, cost and latency quantiles,
success statistics, evidence coverage, generation time, and expiry.

An aggregate MAY inform an estimate or uncertainty only when its signature,
key, capability/fingerprint/scope, freshness, minimum cohort, and coverage meet
local policy. It MUST NOT activate or qualify a route, override minimum quality,
replace a live quote, or be treated as local task-valid observation. Published
aggregates SHOULD include only settled task-valid runs and MUST NOT expose
action IDs, action digests, inputs, or outputs.

## 43. Workflows and fallback with economic evidence

Workflow steps are prepared only when their required inputs exist. Quotes are
request-specific and MUST NOT be reused across step inputs. Ready independent
steps MAY prepare concurrently within a workflow budget; only executable steps
SHOULD reserve funds, and skipped branches MUST release reservations.

After failure, the router MUST first determine effect/idempotency and settle or
reconcile the current attempt. It then checks remaining budget and fallback
authority and obtains a fresh required quote. It MUST NOT reserve every possible
fallback maximum unless operator policy explicitly requests that conservative
behavior.

The reference `execute_prepared_with_fallback()` helper performs at most one
fresh preparation only after a durably settled `FAILED` or `REJECTED` result on
an idempotent read route with operator fallback enabled. It excludes the failed
executor and creates a new action attempt, idempotency binding, digest, and quote.
It MUST NOT run after timeout/indeterminate outcome or for a consequential route.
The workflow executor remains conservative and does not call this helper
automatically.

## 44. Persistence and compatibility

Signed offers, quotes, usage statements, settlement receipts, and prepared
authorization bases are immutable.
Stores MUST retain canonical payload digests/signature metadata and reject an ID
collision with altered content. `INSERT OR REPLACE` MUST NOT be used for signed
evidence. Reconciliation changes SHOULD append a new status/evidence record
rather than overwrite history. Expired temporary quote requests MAY be pruned
only after retaining the evidence needed to audit accepted quotes/decisions.
Nonces, prepared claims, state transitions, and budget reservations
require atomic operations so concurrent workers cannot execute or overspend.
Only action digests and approved quote features are stored by default.

SQLite schema upgrades MUST be versioned, idempotent, transactional where
supported, safe after interruption, and tested from realistic prior databases. Existing
0.1-0.4 manifests, route behavior, static quote readers, receipts, and payment
adapters remain supported through documented compatibility paths. Economic
networking remains opt-in, and existing offline `route()` behavior does not
acquire quotes.

Legacy 0.4 records that already contain a quote ID but predate explicit
authorization fields MAY be read as `SIGNED_QUOTE` with that same ID. This is a
representation migration only: it MUST NOT upgrade a static prior, offer, or
unidentified amount into binding quote evidence.

## 45. Provider packages

`aeep-provider.yaml` defaults to `apiVersion: aeep.dev/v0.6` and `kind:
ProviderPackage`. It publishes provider identity, exact capability contracts,
inert routes, content-addressed artifacts, evidence subjects, and bounded smoke
definitions. It MUST NOT contain an activation or approval control. Version
0.6 evidence declares an authority class and exact cohort. Version 0.5 packages
remain parseable, but incomplete evidence is capped as a weak prior and cannot
qualify a route by itself.

The signed payload contains exactly `apiVersion`, `kind`, `metadata`, and
`spec`, encoded with RFC 8785. Ed25519 signs a domain-separated SHA-256 digest.
Package integrity and local identity trust are separate results; an embedded
unknown key provides at most `self_asserted` trust.

Ingest MUST bound and strictly parse YAML, reject duplicate keys and aliases,
recompute every package and route digest, hash artifacts before parsing, and
atomically persist only inert candidates. It MUST NOT execute, authenticate,
install, qualify, activate, or raise an approval ceiling.

Published Python routes MUST resolve to subprocess isolation with bounded JSON
pipes and timeout termination. This process boundary is not a filesystem or
network sandbox; untrusted code still requires an OS container or VM.

## 46. Canonicalization transition

New 0.5 economic, package, and evidence signatures use `rfc8785-jcs-v1` with
purpose-specific domain separation. The 0.4 `aeep-canonical-json-v1` profile is
historical-only: it may verify reporting history and settle/reconcile an attempt
durably invoked before the 0.5 cutover, but it MUST NOT authorize new live work.
Historical payloads and digests are never rewritten.

## 47. Portable evidence and smoke

Evidence binds an artifact digest to an exact route fingerprint, capability,
workload, producer, validity, and applicable environment. Publisher package
signatures and independent evidence attestations are distinct. Acceptance is
per metric; external evidence remains a prior and MUST NOT be stored as a local
observation.

Verified or attested correctness/compatibility evidence plus a current safe
local smoke MAY qualify a read-only idempotent route. Smoke runs only after an
operator command, performs at most one cold and one warm execution, uses no
fallback, and never activates. Self-asserted evidence cannot qualify by default.

## 48. Cache affinity

Cache affinity is optional soft-ranking context. Hard feasibility always uses
the cold estimate. Stored identifiers are keyed local HMAC digests; raw prompts,
messages, resumes, job data, reasoning, and tool output MUST NOT enter the cache
store. Receipts retain predicted warmth and actual cache-read/write token
dimensions without double counting.

## 49. Registry discovery

Registry adapters return bounded metadata and provider-package locations only.
They MUST NOT install, start, execute, qualify, activate, or grant trust. Registry
verification labels, image provenance, usage counts, and popularity remain
metadata until local policy recognizes a specific signer and role.

A provider MAY publish a signed RFC-8785
`/.well-known/aeep-provider.json` discovery document containing exact protocol,
endpoint, capability, fingerprint, and signing-key metadata. Discovery proves
only document provenance. It MUST NOT grant local trust, install code, qualify a
route, activate a route, or authorize execution.

## 50. Durable approvals and proof campaigns

Every consequential invocation records an immutable approval bound to the
action/policy digest, prepared attempt, granted side-effect ceiling, payment
approval, source, and validity. Package, provider, registry, model, and workflow
data cannot create or raise this record.

The deterministic DSH and job-application campaigns are validation clients of
the Router. The version 2 live DSH campaign compares only direct DSH and
host-native AEEP: ten randomized pairs for each of three read capabilities,
with one excluded warm-up pair per capability. AEEP routes before tool exposure,
so the model receives one canonical source schema and no AEEP or hidden-target
schema. Provider token buckets remain authoritative; route-level tool pressure
and next-call correlation are reported separately. Savings may be claimed only
when all hard gates pass and the fixed-seed 95% bootstrap interval is wholly
positive. Model-facing AEEP MCP is retained only as historical negative-control
material. Offline plan validation is safe, but the 60-session live execution
requires a separate operator approval. These campaigns do not
add planner semantics. Default and CI campaigns use only
synthetic routes, identities, mail, browser/form behavior, and resume facts; no
real submission, email send, CAPTCHA bypass, or credential is permitted.
