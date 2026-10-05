# Architecture and design decisions

## Discovery and admission boundary

[ADR-010](docs/adr/ADR-010-ard-discovery-boundary.md) selects ARD as the primary
external discovery protocol, with local/manual sources and other adapters kept
available. Discovery is an explicit preparation step. The host owns task
planning; `ActionRequest` remains the semantic execution contract, and ordinary
routing neither contacts a registry nor launches assessment.

Registry metadata supplies inert identities and provenance. Artifact inspection
and reviewed mappings connect those candidates to existing assessment subjects.
Applicable evidence must bind artifact and behavior fingerprints as well as the
task/model/configuration cohort. Discovery rank and publisher trust claims never
become observed resources or local qualification. Admission, activation and
dispatch keep their existing authority checks; a recommendation alone cannot
activate a route.

`discovery_service.py` stores source/query/result lineage through the existing
assessment repository; query text and cursor text are represented by digests.
`capability_lifecycle.py` binds a discovered candidate to an operator-selected
local inspection and optional mapping, then looks up existing applicable
admission. Its returned disposition is advice at lookup time, never an execution
grant. Metadata and identity remain separate from inspected artifact bytes.

`profiles.py` wraps existing task scopes and activation with exact manifest,
executor and tool-schema bindings. It supports AEEP task-service schema exposure
and call enforcement. Whole-host catalog filtering, native skill/hook/file
exclusion and context reset are unsupported in this profile implementation;
strict requests stop at preflight. Existing managed-host invocation adapters
separately compile native controls for their reviewed invocation targets.
Installed, discoverable, permitted, exposed and used remain separate facts, with
unobserved host states left unknown. A component toggle does not establish
whole-plugin absence, and a fresh directory provides no credential isolation.

The [integration compatibility record](docs/INTEGRATIONS.md#native-control-compatibility)
separates documented host methods from observed enforcement. Implementation
status and unmeasured gates remain in [plan coverage](reports/v08/plan-coverage.md).

## Native task increment (steering amendment v1)

Production and assessment share Router eligibility, approvals, execution attempts,
receipts and the existing exact-definition repository. Task scopes use that
repository for review and revocation; durable attempts record their usage. This
adds no separate budget database, profile manager or worker scheduler.

The task-only MCP service exposes configured capability tools and returns their
results with sanitized receipt evidence. It generates explanations deterministically,
without a narrator model. Legacy and assessment interfaces keep their existing outputs.
Provider-specific native control compilation lives in the Codex sandbox adapter.
Executors must explicitly support bounded task scopes; unsupported adapters
reject them. Native controls are invocation-local and include managed host policy.
Project activation stores an immutable intent in the existing repository and
creates one owned overlay. Dispatch checks the activation review, overlay bytes
and both effective and on-disk manifest identity. Lifecycle controls revoke
authority before cleanup, preserve edited overlays as conflicts and retain
accounting. Native host controls remain invocation-local; arbitrary host
configuration is not edited.
Session-owned stop events cancel only that activation's current command handle.
The existing sampler retains observed descendants by process identity for cleanup,
including children that change process sessions. Native commands with observed
background children fail. This does not replace an enforced process boundary.
Reviewed local effect reconciliation uses the existing attempt journal in one
transaction and never refunds used task allowance.

Native routing compiles permission rules without rereading the launcher on every
eligibility check. Actual launch verifies its full pinned hash after the final
authority check. Scoped writes that fail after dispatch retain an indeterminate
attempt and block further scoped work until reconciliation, including after
restart or pause/resume. Prepared and ordinary paths share terminal classification.

The selected production target remains native Codex on macOS. Passing command
canaries and synthetic workbook tasks proves the tested command arrangement;
it does not complete model qualification, effective host equivalence, resource
acceptance, usability or unattended live-operation gates. See the current
[coverage record](reports/v08/plan-coverage.md).

The [assessment testing policy](docs/ASSESSMENT_TESTING.md) defines the current
worker and release boundaries. `aeep.execution` supplies provider-neutral
capabilities, handles, ordered events and evidence. Explicit host registrations
own adapter construction and identity resolution. Existing `execute` methods
remain compatibility entry points. App Server support is assessed per method and
installed version; its under-development plugin-management methods are excluded
from production dependencies. Codex Exec and MCP report only the capabilities
they implement.

Controlled invocations persist sanitized journal events through the existing
assessment repository. Completed receipts link to immutable execution evidence.
Worker images, binary/configuration/dependency digests and resource restrictions
are bound by `ManagedWorkerBinding`. Conformance records remain separate from
those declarations. Scoped managed-host admission and subsequent routing require
current conformance for the configured worker, identity and adapter.

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

The host planner decomposes an open-ended goal into bounded actions. AEEP then
selects execution routes for those actions and passes them to adapters.

Native Tool Search remains above this boundary. It may discover a capability,
then pass the bounded `ActionRequest` to AEEP; implementation discovery and
selection do not add a model-facing meta-router round.

## Why a semantic action rather than a tool name

A tool name identifies one transport or provider. A capability such as
`github.current_branch` can have local CLI, REST, MCP, cached-state, and browser
routes. AEEP compares routes that share this semantic contract.

Operators register equivalent contracts explicitly. AEEP does not infer
equivalence, because substituting an almost-equivalent action can change its effects.

## Why raw resources rather than one credit

A scalar supports ranking, but cannot carry every resource measurement. Keeping
the raw dimensions supports:

- auditability;
- policy changes without rewriting history;
- different user opportunity costs;
- model-provider independence;
- hard resource caps;
- future metrics.

The scorer can derive a local scalar at decision time. Receipts retain the vector.

## Why feasibility precedes scoring

A weighted average could let speed offset a privacy violation. AEEP checks hard
constraints before preferences, so rejected candidates receive no total score.

## Expected cost per success

A route that costs half as much but succeeds half as often can be more expensive after retries. The scorer scales consumable burden by inverse success probability and separately penalizes unreliability.

The estimate cannot guarantee the cost of success. Later versions need richer
planning to account for correlated failures, fallback cost, and ambiguous side effects.

## Locality and current state

Local execution receives a small configurable preference because it often avoids network, data disclosure, and context overhead. If caller state is already local to an execution surface, a second locality bonus can represent reuse of current state.

The small bonus applies only after hard constraints pass.

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

The command executor uses `create_subprocess_exec` without a shell. It provides
process isolation, timeouts, bounded output, and host metrics. Use this local
boundary for tools with meaningful side effects or dependencies.

### HTTP

The HTTP executor uses bounded streaming and conservative target validation for
ordinary REST APIs. Provider cost headers remain claims until trusted accounting
evidence reconciles them.

### MCP

The MCP executor discovers the configured tool and measures its schema/context
overhead before invoking it over stdio or Streamable HTTP. It reads optional AEEP
usage claims and caches discovery/tool schemas according to protocol hints and
credential scope. Operators can pin the protocol mode. Automatic legacy fallback
requires an unambiguous method-not-found response.

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

A delegate represents a surface owned by the host agent: browser, GUI,
computer-use, model reasoning, or an unavailable native tool. AEEP returns
instructions and a decision ID; the host reports the outcome later. To prevent
arbitrary history injection, AEEP accepts external reports only for the selected,
feasible delegate and only once per decision/executor pair. Trusted out-of-band
measurement uses `ActionProfiler`.

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

SQLite stores decisions and receipts locally as validated JSON with indexed
lookup columns, so deployment needs no separate database service. A future
service can implement the same store interface.

By default, stored decisions redact action input and context, and the store omits
outputs. The live decision returned to the invoking process contains the request
needed for immediate execution. Redacted stored decisions cannot be replayed.
These defaults limit accidental retention of sensitive data while preserving
economic records.

Idempotency records atomically bind a caller key to a canonical action hash and its receipt IDs. Replays avoid execution and return those receipts, but cannot reconstruct output unless an operator later enables a separate output store.

## Agent interfaces

- Python API for embedded runtimes.
- JSON CLI for skills and shell-capable agents.
- MCP server for standard tool clients.
- Native tool schema exports for providers whose application owns the function-call loop.

All interfaces call the same service methods to keep behavior consistent. Model
tools default to paginated capability search and compact route/run envelopes;
complete decisions remain queryable by ID. The process or operator configures
runtime approval ceilings. Model-controlled function arguments cannot change them.

## Existing-agent instrumentation

Wrappers around OpenAI and Anthropic clients' normal `create` calls record usage,
timing, and terminal status without storing prompts or outputs or adding those
SDKs as dependencies. The trace ingestor accepts OTLP JSON or JSON Lines and
reconstructs common call types. This passive profiling compares only capabilities
the operator has explicitly registered; it cannot infer semantic equivalence.

## Calibration

Cold-start manifest estimates are priors. `Router.benchmark` measures feasible
alternatives sequentially and produces comparable receipts. Sequential execution
reduces contention bias. Every run still requires explicit confirmation and must
respect normal hard constraints and approval ceilings. Benchmarks skip delegates
and non-idempotent routes by default. Model-facing tools cannot start benchmarks
and silently multiply paid calls.

## Qualification and workflows

The store keeps external supply separate from the runtime Registry. Discovery
creates disabled candidates. Operators qualify and activate them through explicit
transitions bound to a canonical behavior fingerprint. The Registry contains only
trusted manifest routes and active candidates with matching fingerprints.
`Router.execute` rechecks current policy, capability, active state, and fingerprint
immediately before invocation.

The workflow SDK/CLI runs caller-supplied DAGs through the existing action router.
It routes each step when ready, using the same approvals, fallback, validation,
receipts, idempotency, and observation. Inputs and intermediate outputs stay in
memory; checkpoints contain only hashes, status, and selected IDs.

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


## Assessment boundary (0.8)

`aeep.assessment` owns immutable definitions, operator reviews, authorizations,
job state and comparative reports. Its service calls `BenchmarkRunner`, which
executes through isolated `Router` instances. `ReceiptStore.campaign_snapshot`
copies authority dependencies but excludes production observations and attempts.
Qualification also uses this controlled execution path.

The assessment repository uses `ReceiptStore._immediate_transaction` for
budget admission and activation. Runtime applicability checks do not start a
worker or invoke a planner. The legacy tool profile remains available; the
assessment profile provides direct capability tools and bounded job controls.
The worker's state is durable while its process is replaceable; an uncertain
invocation is retained rather than retried automatically.

Static intake retains declared contracts without starting a process. The bounded
planner emits inert definitions; operator review and candidate installation are
separate operations. Declarative adapters reuse the template and JSON Pointer
helpers. Workflow mappings reuse the workflow engine and campaign case bindings.
An immutable operation ledger connects setup and planning costs to comparisons
without copying campaign observations into production history.

Codex adapter IDs may use `codex-app-server:<worker>` to select independent
App Server processes. New skill onboarding separates baseline and candidate
workers. Temporary invocation workspaces use explicit named permission profiles;
conversation and filesystem checks remain separate from tool-access verification.
The same campaign runner schedules both workers and records their usage.

### Incremental-capability assessment

`assessment.comparison` compiles the four reviewed arm definitions into the
existing BenchmarkRunner. `assessment.boundary` validates each worker and the
reviewed difference between workers; inventories do not substitute for effective
permissions. `assessment.reporting` evaluates optional availability across all
assigned cases, with missing measurements retained and utility dimensions kept
separate. Reusable-tool construction operations are linked into the same ledger.

The contained recipe extension can distinguish semantic truth from output
artifacts. Workbook generation/reference run with pinned openpyxl; a separate
bounded OOXML program checks formulas, caches, values and required structure.
The coordinator performs bounded structural extraction, not workbook cleaning.
These offline mechanisms do not establish authenticated host or catalog evidence.

App Server's optional catalog metrics relay runs beside Codex inside the existing
worker. The image pins the stdlib-only collector module. Sanitized OTLP snapshots
share the bounded stdio transport; the adapter verifies their scope and monotonic
history, binds canonical event digests and retains partial receipt metadata.
The coordinator does not interpret native metric names when ranking or admitting
routes. Counts and injection events do not establish complete discovery evidence.

## Stack orchestration

`stack_models.py` contains the provider-neutral goal, artifact, proposal and
preflight contracts. `stack_planning.py` applies existing eligibility and policy
scoring to configured candidates. It compiles pinned configurations into transient
`WorkflowRequest` objects. `stack_runtime.py` uses the workflow engine and durable
`ReceiptStore` progress; it does not own another executor or approval system.
`provider_setup.py` keeps non-charging readiness and operator handoffs separate
from routing and admission.

The canonical discovery adapter factory lives in `discovery_service.py`.
`legacy_discovery.py` preserves the old provider-registry interfaces through
compatibility re-exports. Ordinary routing does not enter stack search.
[ADR-011](docs/adr/ADR-011-stack-synthesis-preflight.md) records the boundary and
[STACK_PLANNING.md](docs/STACK_PLANNING.md) describes current support and gaps.
