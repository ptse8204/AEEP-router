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
   ┌──────┼────────┬────────┬───────────┬──────────────┐
 Python  CLI      HTTP     MCP     host/delegate   managed host
                                      │                 │
                              browser/model/GUI     reviewed adapter
```

AEEP belongs below planning and above execution adapters. It does not tell an agent how to decompose an open-ended goal; it optimizes bounded actions after decomposition.

Native Tool Search remains above this boundary. It may discover a capability,
then pass the bounded `ActionRequest` to AEEP; implementation discovery and
selection do not add a model-facing meta-router round.

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

Cold-start estimates come from executor configuration. Real receipts are
blended only from the exact versioned evidence cohort, including behavior
fingerprint, provider/model/adapter identity, region/account tier, input-size
bucket, validators, cache profile, and economic-evidence level. Legacy-unbound
or mismatched rows remain auditable but cannot influence live routing. A
provider's advertised number remains a prior; it is not copied into observed
performance. Low-confidence estimates carry a configurable uncertainty burden.

After five exact-cohort samples the estimator also exposes deterministic
empirical p50/p95 resources, observed cash p95, and reliability/quality lower
bounds. These are descriptive bounds, never payment authorization.

The router may retain a feasible operator baseline when the score improvement
does not cover measured routing overhead and policy margin. This abstention runs
after feasibility, so it cannot restore a rejected baseline. More adaptive
selection remains shadow-only until paired reports demonstrate positive value
without hiding negative outcomes.

## Execution boundaries

### Python

Reviewed manifest callables may still run in process for compatibility.
Provider-package Python routes are forced through an argv-only worker
subprocess with bounded JSON pipes and timeout termination. Optional POSIX
CPU/memory limits improve containment but do not replace a container or VM for
untrusted filesystem/network access.

### Command

Uses `create_subprocess_exec`, never a shell. It offers process isolation, timeouts, bounded output, and host metrics. It is the preferred local boundary for tools with meaningful side effects or dependencies.

### HTTP

Uses bounded streaming and conservative target validation. It is appropriate for ordinary REST APIs. Provider cost headers remain claims unless reconciled by trusted accounting evidence.

### MCP

Discovers the configured tool, measures schema/context overhead, invokes it over stdio or Streamable HTTP, reads optional AEEP usage claims, and caches discovery/tool schemas according to protocol hints and credential scope. Protocol mode can be pinned; automatic legacy fallback requires an unambiguous method-not-found response.

The modern path mirrors protocol version, method, tool name, and schema-authorized primitive parameters into HTTP headers; validates header/body consistency; bounds messages; and applies the same SSRF/allowlist/HTTPS policy as the HTTP executor. AEEP accepts only complete single-round tool results; multi-round `input_required` continuation belongs to the host agent until a later protocol adapter is defined.

For DeepSeek Harness, the preferred adapter runs at the host's model/tool
dispatch boundary. Its `/aeep` command preflights one exact capability/input,
then exposes only the canonical source tool for that turn. One argv-only,
bounded JSONL `aeep host-bridge` keeps a Router and event loop alive for the
plugin lifetime. The model-facing MCP bridge remains historical negative-control
material, not the ordinary route.

The adapter pins source and selected-target parameter/output digests and
validates the hinted or rerouted arguments against both live schemas. Hidden
targets are permitted only for the nested call admitted by the current AEEP
decision. Output schemas must match exactly unless the one reviewed
`read-url-to-web-fetch-v1` adapter is configured; that adapter requires the
target's real status, final URL, text, truncation state, and content type.
Preflight, drift, mapping, adapter, or bridge failure rejects the routed action
without falling back to an unreviewed implementation.

### Delegate

Represents an execution surface owned by the host agent: browser, GUI, computer-use, model reasoning, or an unavailable native tool. AEEP returns instructions and a decision ID; the host reports the outcome later. To prevent arbitrary history injection, external reports are accepted only for the selected, feasible delegate and only once per decision/executor pair. Trusted out-of-band measurement uses `ActionProfiler` instead.

### Host subscription

`host` formalizes current-agent execution without calling a model API. It references a user-owned `SubscriptionResource`, returns `HOST_SELECTED`, and consumes provider-local `subscription_units`. Quota pressure changes the preference score or rejects an exhausted resource; it is never converted into a public cash value.

### Managed host

`host_managed` invokes a reviewed, locally configured adapter directly and does
not change legacy `host` behavior. Adapters expose probe, capacity snapshot,
runtime model discovery, bounded execution, interruption, and close operations.
The first reference adapter targets the official Codex App Server. Codex owns
authentication; AEEP persists only HMAC principal correlation and sanitized
operational evidence. A provider package cannot authorize this local boundary.

Subscription capacity is provider-local. Reservations and entitlements retain
its raw unit and resource fingerprint. Personal subscription resources default
to `SELF_ONLY`; private valuation may affect scoring but cannot become cash or
settlement evidence.

x402 support binds only eligible provider-authorized capacity to an offline,
disabled-by-default batch-settlement contract. Marketplace, wallet, custody,
payout, cryptocurrency, and live transfer behavior are outside 0.7.

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

Versioned capabilities define what is offered; expiring quotes bound price;
settlement and validation results provide distinct delivery/economic evidence.
Local/remote registries load only providers relevant to the requested
capability. Provider claims remain priors, while measured or attested
observations drive reputation.

Payment adapters sit behind an operator budget and a separate financial
approval. The OSS ledger records reservation, capture, release, refund, and
reconciliation events but does not hold funds, create accounts, pay providers,
or clear between providers.

## Prepared economic routing

Prepared routing is explicit so ordinary `route()` remains offline. It has two
durable halves separated by a caller-controlled boundary:

```text
prepare_route(action)                 execute_prepared(prepared_id)
        │                                        │
active exact routes                  atomic single-use claim
        │                                        │
non-price hard constraints           expiry/policy/route/key revalidation
        │                                        │
local shortlist + top-K quotes       reserve immutable authorized maximum
        │                                        │
quote verification + cash limits     persist INVOKING, then invoke once
        │                                        │
final score + sanitized record       usage + settlement + accounting
```

The action digest binds canonical input without persisting it. The effective
policy digest makes material policy drift detectable. The behavior fingerprint
makes executor drift detectable. Quote acquisition only replaces the cash
estimate; it cannot change qualification, quality, reliability, or safety.

### Static-price route

```text
Caller          Router          Registry/Policy       Store
  | prepare       |                    |                 |
  |-------------->| exact active route |                 |
  |               |------------------->|                 |
  |               | offer/pinned-rate cash; no remote call|
  |               | hard cash check + score              |
  |               |-------------------- prepared ------->|
  |<--------------| decision                              |
```

A verified fixed offer may avoid a live request when policy allows its maximum.
A static prior remains non-binding and cannot silently satisfy a policy that
requires a signed quote.

A paid prepared decision carries exactly one immutable authorization basis:
`SIGNED_QUOTE`, `PUBLISHED_OFFER`, or `PINNED_RATE_CARD`. Quote and offer bases
bind their immutable record ID. A pinned rate-card basis additionally binds the
snapshot, exact rate IDs, and bounded native quantities used for the maximum.
An anonymous static prior can rank a route but cannot authorize nonzero cash.

### Dynamic-price route

```text
Caller       Router      Qualified shortlist     Quote providers       Store
  | prepare    |                 |                    |                  |
  |----------->| non-price hard filtering            |                  |
  |            |---- rank/select top K ------------->|                  |
  |            |======== concurrent bounded quotes ==>|                  |
  |            | verify trust/binding/nonce/expiry    |                  |
  |            | maximum for feasibility; expected for rank             |
  |            |---------------- sanitized decision + evidence -------->|
  |<-----------|                                                         |
```

Provider endpoints need both trust-store authorization and local network
allowlisting. Request disclosure contains only operator-declared bounded
features; the action payload remains local.

### Prepared execution

```text
Caller       Router/Store      Payment adapter       Executor       Accounting
  | execute       |                   |                 |               |
  |-------------->| claim + revalidate|                 |               |
  |               | reserve authorized maximum -------->|               |
  |               |<---------------- reservation -------|               |
  |               | persist RESERVED then INVOKING      |               |
  |               |------------------------------------>| invoke once   |
  |               |<------- result/local usage/provider statement ------|
  |               | persist SETTLING; settle actual ---->|               |
  |               |<---- capture + release receipt ------|               |
  |               |---------------- authoritative cash ---------------->|
  |<--------------| receipt                                               |
```

External execution and payment calls cannot share a SQLite transaction. State
is therefore persisted before and after each external boundary.

### Partial capture

```text
signed maximum USD 0.0050
          |
          v
reservation USD 0.0050
          |
actual billable usage USD 0.0038
          |
          +--> capture USD 0.0038
          `--> release USD 0.0012
```

The settlement invariant is enforced by typed Decimal/currency models and the
adapter/store state machine; a provider assertion above the maximum opens a
dispute and never authorizes overcapture.

### Indeterminate execution

```text
INVOKING -- timeout/unknown external outcome --> INDETERMINATE
    |                                             |
    | no blind non-idempotent retry               +--> operator evidence
    |                                             +--> payment lookup
    `---------------------------------------------+--> usage/billing lookup
                                                      |
                                            SETTLED or DISPUTED
```

Unknown outcome and unknown billing remain explicit. The reservation remains
outstanding until the signed policy and available evidence permit settlement or
release.

### Crash recovery

```text
process crash after invoke
          |
          v
scan durable RESERVED/INVOKING/AWAITING_USAGE/SETTLING/INDETERMINATE
          |
          +--> inspect attempt/provider receipt (never invoke again)
          +--> inspect adapter idempotency/settlement
          +--> resume settlement or release only
          `--> leave unresolved state INDETERMINATE
```

### Workflow step routing

```text
ready DAG step -> bind real upstream inputs -> prepare -> reserve -> execute -> settle
       |                                                            |
       +-- independent ready steps may prepare concurrently --------+
       +-- skipped branch releases an existing safe reservation
       `-- fallback gets a fresh input-bound quote after prior settlement
```

The current router prepares only a dependency-resolved wave. It may prepare
independent read-only steps concurrently, while any wave containing a potentially
consequential, delegated, hosted, or exclusive-resource route is serialized
before quote acquisition. Prior settled actual cash plus every prepared maximum
must fit the workflow budget; otherwise the still-uninvoked prepared decisions
are cancelled before reservation. Future steps are not quoted against guessed
payloads. The router executes each selected prepared ID at most once and does not
reserve every possible fallback in advance. The current workflow implementation
stops after a selected prepared step fails or becomes uncertain; a caller that
is allowed to recover must first settle or reconcile that attempt and explicitly
prepare a fresh fallback action.

## Economic persistence

SQLite `user_version` migrations preserve the legacy tables and add normalized
0.4 trust keys, offers, quote requests, bounded quotes, nonce uses, prepared
decisions/transitions, reservations, usage, settlements, reconciliations,
aggregates, disputes, and evidence links. Canonical signed payloads are
immutable: identical inserts are idempotent and altered ID reuse fails.
Prepared claims, nonce consumption, and budget reservation use transactional
compare-and-set operations so concurrent workers cannot execute twice or
over-reserve.

## Future extension points

1. Drift-aware bounds and contextual-bandit shadow evaluation.
2. Result caching within explicit bounded actions.
3. Sandboxed hosted executors.
4. Organization policy services and private catalogs.
5. Federated provider identity and aggregate-trust governance beyond the local
   Ed25519 trust store.
6. Hosted marketplace accounts, custody, payouts, and fraud controls.
7. Richer OpenTelemetry semantic events, exporters, and trace-to-action correlation.

## Provider-package supply chain (0.6)

```text
aeep-provider.yaml
  -> bounded strict YAML
  -> RFC 8785 digest + publisher signature/trust
  -> portable route fingerprint
  -> local/HTTPS artifact hash -> immutable CAS
  -> independent evidence attestation + per-metric acceptance
  -> atomic package/evidence/snapshot + inert CANDIDATE
  -> operator smoke (one cold, optional warm)
  -> evidence-assisted QUALIFIED
  -> explicit ACTIVE
```

Package parsing/signing is isolated from artifact resolution; artifact bytes are
finalized in CAS before one SQLite transaction publishes trusted metadata.
External evidence feeds the existing estimator as a prior. It does not enter
the observations table and does not create a second scorer.

New signatures use RFC 8785. Verification dispatches on the signed profile;
legacy signatures are historical/recovery-only. Database schema v5 records the
cutover, package revisions, artifacts, evidence decisions, smoke results, cache
observations, registry metadata, durable approvals, and immutable evidence
cohort provenance on receipts and observations.

Cache affinity follows the same hard/soft split as every other routing signal:
cold resources decide feasibility, while a privacy-safe warm expectation may
change the score of an already feasible route.

Version 0.6 adds explicit evidence authority/cohort declarations, signed
provider discovery, and provider conformance checks. A v0.5 package remains
readable, but evidence that lacks the new declarations is accepted only as a
low-confidence prior and cannot qualify a route.
