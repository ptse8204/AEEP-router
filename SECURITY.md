# Security policy and deployment guidance

AEEP can launch commands, call remote services, and advise another agent. Its
manifest and database control these operations, so protect both as
security-sensitive assets.

## Supported version

AEEP is alpha software. Until the project publishes a stable release policy,
security fixes target only the latest commit/version.

## Reporting

Do not include working exploits, credentials, or private endpoints in public
issues. Contact the repository owner privately until the project establishes a
private security-advisory channel, then use that channel.

## Trust boundaries

### Trusted

- The AEEP package and reviewed dependencies.
- The operator-written manifest.
- Explicitly registered Python callables and command paths.
- Operator-approved remote endpoints and MCP servers.

### Untrusted or partially trusted

- Action input from an agent/model.
- API/MCP output.
- Remote cost/reliability claims and externally reported outcomes.
- Browser content and delegated instructions.
- Environment values and secrets.

## Command execution

- Shell execution is unsupported.
- Arguments are rendered independently into an argv list.
- Use absolute executable paths in high-assurance deployments.
- Keep `inherit_env: false`; pass only required variables.
- Put untrusted tools in containers/VMs with filesystem, network, process, and syscall controls.
- Do not use in-process Python for untrusted code.

Packaged Python callables run in a killable subprocess with bounded JSON pipes
and optional POSIX CPU/memory limits. This prevents a timed-out worker from
remaining in the router process, but it is not a cross-platform filesystem or
network sandbox. Use a container or VM for untrusted code.

## Project task lifecycle

Each project activation creates only a new AEEP-owned overlay. The control-plane
manifest, overlay directory and store must remain outside the task child's
writable boundary. Missing or edited overlays and manifest drift stop dispatch.
Rollback compares applied/current bytes and preserves edits as a conflict. It
never restores a saved copy of host authentication or global configuration.

Pause rejects new dispatch. Stop also signals the current session's owned
execution handle through a durable event. The command sampler retains observed
process handles with creation-time identity so a detached observed child is also
signaled. Native commands leaving observed background children are rejected.
Polling can miss rapid forks; this does not establish containment
of detached adversarial descendants or cleanup after coordinator death. Those
boundaries require their own conformance evidence before support is claimed.
Unresolved writes stay blocked until exact operator-reviewed effect inspection;
absence of accounting is not evidence that nothing happened.

## HTTP/SSRF

- Public remote calls require HTTPS by default.
- Private, loopback, link-local, multicast, reserved, and non-public targets are blocked unless explicitly enabled.
- Use `allowed_hosts` even when private networks are intentionally enabled.
- Redirects are disabled by default. Avoid enabling them for agent-controlled URLs.
- Production deployments should enforce egress policy outside the process because application-level DNS checks cannot eliminate every rebinding/race condition.

## MCP

Before connecting an MCP server, review its command, environment, working
directory, transport URL, authentication, and exposed tool behavior. The
connection gives that server access through the integration boundary. Returned
content can contain prompt injection; AEEP routing cannot sanitize how an agent
interprets it.

Remote MCP HTTP clients use the ordinary HTTP executor's HTTPS, allowlist, IP-classification, redirect, response-size, and no-ambient-proxy defaults. Modern MCP request headers are derived only from validated primitive schema properties; duplicate case-insensitive names, unsafe names, unsupported schemas, or header/body disagreement are rejected. Stdio and HTTP messages are bounded, but production deployments still need process, ingress, and egress limits outside Python.

The built-in HTTP MCP server has only a static bearer token as its minimum guard.
Deploy it behind TLS, authentication, Origin validation/policy, request-body
limits, rate limits, logging, and network policy. Do not expose it directly as a
public multi-tenant service.

## Side effects

- Keep default policy at `read` or lower.
- Define explicit policies for writes/destructive/financial actions.
- Require a separate operator-controlled runtime approval. Model/MCP/function-call arguments cannot raise that ceiling.
- Use idempotency keys at the downstream service when possible.
- AEEP binds a key to one capability/input hash and fails closed on mismatches or unfinished prior claims. Protect the receipt database from deletion or tampering.
- Never opt into non-idempotent fallback without understanding duplicate-action risk.

## Secrets

- Do not place secrets directly in YAML committed to source control.
- Use `${ENV:NAME}` only in supported environment/header fields.
- Prefer a secret manager and short-lived credentials.
- Stored action input/context are redacted by default; enable persistence only with a defined retention purpose.
- Output previews are off by default; keep them off for sensitive actions.
- Protect `.aeep/aeep.db`; receipts reveal operational metadata even without payloads.

## Outcome integrity and history poisoning

`aeep_record_outcome` changes future estimates, so access to it is write access
to routing policy. Authenticate remote callers, rate-limit reports, and preserve
provenance. Keep unauthenticated reports out of shared reputation. The reference
implementation accepts one external report per decision/executor pair, only for
the selected feasible delegate. A compromised authorized caller can still
fabricate that report. Use `ActionProfiler` for trusted operator-owned
measurement outside the delegate flow.

Local reputation excludes provider descriptors, estimates, and other untrusted
or self-asserted claims from observed results. The compatibility HMAC signature
proves only possession of a shared secret; it supplies neither public-key
identity nor global trust. Cross-provider 0.4 economic evidence uses locally
trusted Ed25519 keys bound to provider identity, capability, validity period,
revocation metadata, and approved quote hosts.

Live historical estimates use only receipts bound to the exact versioned
evidence cohort and behavior fingerprint. Legacy-unbound or mismatched rows stay
available for audit but cannot affect selection. This prevents a route ID,
provider, model, validator, or cache-scope change from inheriting unrelated
performance history.

Empirical p95 and lower-bound estimates describe exact-cohort history only.
They cannot replace signed payment maxima or weaken hard constraints. Router
abstention may retain only a baseline that already passed those constraints.

Imported traces and SDK measurements remain audit evidence unless a trusted
ingestion path binds them to the exact runtime fingerprint and evidence cohort.
The built-in instrumentation stores resource metadata and identifiers, not
action payloads or model outputs; trace attributes can still contain sensitive
data and should be filtered at the telemetry collector.

## Subscription resources

- Treat quota state as private routing data, not currency or transferable value.
- Prefer explicit user/host/official signals; do not scrape undocumented billing dashboards.
- A host selection does not grant the host new permissions. Keep its normal approval UI and sandbox enabled.
- Authenticate host outcome reporting and accept only the selected route once.
- Default personal subscription resources to `SELF_ONLY`; reject external
  entitlements before serialization.
- Keep Codex login and reusable authentication state inside Codex. Never read its
  authentication files or copy browser cookies.
- Intersect AEEP's operator approval ceiling with the managed host's approval;
  rejection, expiry, or disconnection fails closed.

Managed-host executables are trusted local control-plane dependencies. Pin or
validate their configured path, pass an allowlisted environment, bound every
protocol frame and stderr buffer, and persist invocation state before starting a
turn. Runtime model and quota claims remain observations with provenance; an
account/principal change invalidates cached capacity.

### Managed-host and capacity threat closure

| Threat | Control |
|---|---|
| Codex authentication-token theft | Codex owns login; AEEP never reads credential files, cookies, or raw auth responses. |
| Cross-account/principal confusion | Account identity is a process-local salted HMAC; a change invalidates the cached probe before more routing. |
| Malicious or replaced App Server executable | The path is absolute and executable; high-assurance manifests may pin `executable_sha256`. A valid pin does not make a compromised binary trustworthy. |
| Stdout/stderr protocol injection | Stdout accepts bounded protocol JSON only; malformed, oversized, duplicate, and unknown frames fail closed. Stderr is separate and bounded. |
| Approval laundering or replay | AEEP and host ceilings intersect; approval request IDs are single-use and raw commands are replaced by digests. |
| Prompt/action over-disclosure | Only the selected route's bounded template and action fields cross the host boundary. |
| Output persistence leakage | Prompt and output persistence default off; receipts retain only redacted operational metadata and digests. |
| Model reroute outside policy | Models are runtime-discovered under declared constraints and the actual rerouted model remains an observation. Unknown reroutes stay unknown. |
| Rate-limit race, spoofing, or staleness | Capacity is refreshed before scoring and revalidated before invocation; exhausted reports hard-reject and stale/partial evidence carries uncertainty. |
| Capacity double reservation | SQLite immediate transactions, idempotency binding, expiry, and compare-and-set versions serialize claims and release. |
| Entitlement replay or SELF_ONLY conversion | Nonces, action/beneficiary/resource binding, authority evidence, expiry, attempt-bound redemption, and atomic remaining quantity fail closed. |
| x402 overclaim | Local reconciliation disputes claims above the maximum or observed redemption; no live rail can capture value. |
| Crash after external invocation | Durable `INVOKING` evidence precedes the boundary; unknown outcomes become `INDETERMINATE` and execution is not silently repeated. |
| Imported package authorizes local host | Imported managed-host and in-process routes remain inert and cannot qualify themselves; only reviewed local configuration constructs the adapter. |

Residual risk remains with a compromised executable, operator manifest, local
database, clock, or approval UI. Executable hashing detects replacement only
when an operator pins a trusted digest; it is not code signing, sandboxing, or
attestation. Subscription telemetry may be delayed or dishonest, so it cannot
authorize transfer or cash settlement.

## Registries and imported providers

- Review local registry files as control-plane configuration.
- Remote registries use bounded HTTPS requests, no redirects, no ambient proxies, and the same DNS/IP/allowlist controls as HTTP execution.
- Imported OpenAPI writes are unsafe for automatic execution by default.
- CLI import accepts argv arrays and JSON stdin only; shell interpolation remains unsupported.
- Discovery/import never activates a route. Qualification is read-only,
  fingerprint-bound, and followed by a separate operator activation.
- Endpoint, argv, MCP tool/schema/protocol, image, or version drift suspends an active imported route.
- Provider-package ingest accepts only bounded strict YAML and executes zero
  provider code. Package signatures prove provenance; separate evidence
  attestations prove only their exact artifact/subject claim.
- Local artifact paths cannot be absolute, traverse, or use symlinks. Accepted
  bytes are hashed and copied to immutable CAS before parsing.
- Remote artifacts are disabled by default, HTTPS-only, exact-host allowlisted,
  byte/decompression bounded, and connected to a validated resolved address
  while retaining original TLS SNI.
- Registry labels and container provenance never grant qualification, economic
  trust, activation, or approval.
- Signed provider discovery documents remain inert provenance metadata. Their
  keys and endpoints do not become trusted until local policy recognizes them.
- Version 0.5 package evidence that lacks the version 0.6 authority/cohort
  declaration is capped as a weak prior and cannot qualify a route by itself.

## DeepSeek Harness host adapter

The host-native DSH adapter keeps AEEP routing outside model context. It uses
one argv-only persistent child, bounded JSONL stdin/stdout, exact
operator-authored executor mappings, transient action hints, per-turn tool
allowlists, and a nested-call guard. It never persists prompts, action inputs,
outputs, or session IDs and never discovers, installs, qualifies, activates, or
widens approval. If AEEP, the bridge, or the live DSH inventory disagrees with
the configured input or output contracts, `/aeep` fails closed before the model
call or routed execution. A failed consequential call is never retried. Live
campaigns require a separate operator approval.

## RFC 8785 cutover

AEEP 0.5 issues only RFC 8785 signatures. Legacy canonicalization is accepted
for historical audit and for settlement/reconciliation of an attempt durably
invoked before the cutover. It cannot authorize new preparation, reservation,
invocation, evidence use, aggregate scoring, or key rotation. Do not rewrite or
re-sign historical records in place.

## Cache affinity and approvals

Cache scope, prefix, and state identities are local keyed HMACs. Never persist
raw prompts, email, job postings, resumes, reasoning, or tool output as cache
identity. Warm estimates affect soft scoring only; cold values remain hard
limits.

Consequential execution writes an immutable approval record bound to the exact
action/policy/attempt. Model/package/registry input cannot create or raise an
approval. A timeout remains indeterminate and cannot be retried merely because
an approval exists.

## Economic evidence

- Treat provider usage metadata and model-facing outcome values as claims, not observations or billing evidence.
- Persist bounded evidence identifiers/digests, never invoices, account identifiers, credentials, or raw provider payloads.
- Unknown cash is not zero. Confirmed zero cash does not erase subscription or model-resource pressure.
- API-equivalent counterfactuals and policy valuations never enter cash totals, budget checks, payment ledgers, or cash-savings claims.
- Pin rate-card content and retain applied meters/rates; never silently reprice historical campaigns.
- Capability offers and market aggregates cannot qualify or activate a route.
- A provider signature proves who asserted a statement, not whether its meters,
  result, or billing claim is truthful.

## Payments and budgets

- Quote retrieval is read-only; acceptance and payment operations are not model tools.
- Require the separate `financial` runtime ceiling plus configured human approval.
- Treat the local prepaid adapter and ledger as reference orchestration, not custody or accounting software.
- Rail callbacks for x402, MPP, invoice, or enterprise settlement must authenticate counterparties, enforce idempotency, and reconcile independently.
- Use the immutable quote, offer, or pinned-rate-card maximum for reservation
  and budget feasibility. Never capture above it, even when a provider reports
  more. An anonymous static prior cannot authorize nonzero cash.
- Outstanding and indeterminate reservations reduce available budget. Treat the
  local adapter as orchestration evidence, not a bank or general ledger.

## Economic evidence threat model

| Threat | Required mitigation |
|---|---|
| Quote/offer tampering | Canonicalize once, verify Ed25519 before use, and bind provider, capability, executor, fingerprint, action digest, terms, currency, billing policy, fixed attempt fee when selected, amount, and expiry. |
| Replay or nonce reuse | Use high-entropy request nonces, persist accepted use atomically, reject reuse across quotes/actions, and make prepared decisions single-use. |
| Expired/future-dated evidence | Enforce bounded quote TTL, clock-skew limits, offer/key validity, and recheck immediately before execution. |
| Binding-to-static downgrade | Configure explicit failure behavior; a failed live quote must not silently become a static prior or zero. Label every evidence source, require one matching `SIGNED_QUOTE`, `PUBLISHED_OFFER`, or `PINNED_RATE_CARD` authorization for nonzero cash, and bind exact rates/quantities for a rate card. |
| Provider/key impersonation | Trust keys locally, bind each key to one provider/capability/host, allowlist algorithms, and reject keys supplied only by the quote response. |
| Signing-key compromise | Support validity bounds, revocation, retained historical metadata, and verified rotation from an already trusted key; revoke prepared but unexecuted work. |
| Malicious endpoint/SSRF | Require operator-configured endpoints and exact hosts; use HTTPS by default; revalidate DNS and block private, loopback, link-local, metadata, multicast, reserved, and other non-public IPs unless narrowly enabled. |
| Cross-provider source confusion | Dispatch by the operator-configured executor-to-quote-source mapping; never let a provider response select another executor's client or endpoint. |
| DNS rebinding | Resolve and validate before each connection and enforce network-layer egress policy in production; application checks cannot remove the final DNS/connect race. |
| Redirect abuse | Disable redirects. If a future adapter permits them, revalidate every target and strip authorization across origins. |
| Proxy credential leakage | Disable ambient proxy inheritance and use explicit sanitized headers only. |
| Oversized/malformed response | Bound request/response bytes and concurrency, require JSON content type/UTF-8/object shape, apply per-provider and total deadlines, and return sanitized structured errors. |
| Raw-input disclosure | Send only operator-declared bounded primitive features; deny prompts, resumes, secrets, personal data, file contents, secret URLs, and arbitrary free-form strings by default. Never log or persist raw quote input. |
| Meter manipulation/under-reporting | Keep local and provider meters separate, retain native units and task-valid observations, and do not treat provider usage as payment evidence. |
| Missing/invalid usage after invocation | Preserve the reservation and mark the decision indeterminate when signed policy cannot determine billing. Never turn missing usage into zero or retry the action. Accepted-result billing requires both a bound local task-valid receipt and signed provider evidence; provider-start billing requires explicit start evidence. |
| Over-reporting/overcapture | Enforce `captured <= reserved <= immutable authorized maximum`; retain the provider statement, cap capture, and open a dispute/reconciliation record. |
| Duplicate capture/release/refund | Use immutable operation IDs, transactionally stored idempotency keys, compare retry payloads, and reject conflicting reuse or illegal terminal transitions. |
| Crash-window double execution | Persist `INVOKING` before the external call; recovery inspects attempt/payment state and resumes settlement only. Never re-execute a consequential action from recovery. |
| Currency confusion | One configured settlement currency per router; strict uppercase codes and Decimal values; reject mismatch and perform no implicit FX. |
| Aggregate privacy leakage | Bucket inputs, enforce minimum cohorts and retention, include only settled task-valid runs, and omit action IDs/digests, inputs, and outputs. |
| Market-data poisoning/collusion | Verify aggregate signatures/scope/freshness/coverage, treat aggregates as priors only, require local qualification/quality evidence, and prefer local settlement/reconciliation. |
| Marketplace activation | Discovery, offers, quotes, and aggregates never qualify or activate a route. Operator qualification and activation remain separate. |
| Billing discrepancy | Link one charge across quote, usage, settlement, and reconciliation without summing stages; preserve differences and require operator resolution for disputes. |
| Approval laundering | Economic evidence and model arguments cannot raise side-effect or financial ceilings. Consequential execution requires independent approval. |

## Benchmarking

`aeep benchmark` executes multiple feasible routes. Read-only routes can still
incur fees, consume quota, or disclose the same input to several providers. The
CLI requires explicit confirmation and enforces hard constraints throughout. It
skips non-idempotent/delegated routes by default. Do not expose benchmark
invocation as an unrestricted model tool.

## Data policy

Set `data_sensitivity`, locality, and allowed residency on requests/policies.
Enforcement through these fields depends on trustworthy executor metadata.
Production networks need provider attestation and independent audit.

## Resource exhaustion

Set command/HTTP/MCP timeouts and output limits. For stronger enforcement, apply
OS/container quotas for memory, CPU, processes, files, and network access.
Resource estimates cannot replace kernel-level limits.

## Dependency and release hygiene

Before production:

- pin dependencies with hashes;
- enable automated vulnerability scanning;
- build reproducible signed artifacts;
- run tests on supported Python versions;
- review optional HTTP-server dependencies;
- restrict who can edit manifests and policies.


## Assessment authorization (0.8)

Installed plugin metadata, declared side effects and model-generated recipes are
untrusted inputs. Reviews bind exact definitions; standing authorizations bind
subjects, recipes, environments and finite ceilings. Model-facing tools cannot
expand those grants. New declarative recipes require review before generation.
Untrusted executable adapters without supported containment remain blocked.
Destination grants default to local execution and Codex. Remote origins must be
explicitly permitted as well as having disclosure authorization. Host-owned MCP
targets require operator-reviewed locality; advertised safety hints cannot supply
it. An unrestricted container network requires the explicit `network:any` grant.

Trial receipts and assessment operations are distinct from production history.
Cancellation and revocation stop new admissions to work; uncertain in-flight work
retains its budget reservation. Revoked scoped routes retain their admission
marker and cannot silently become unrestricted. Verified receipt validation
failures revoke scoped use without launching baseline calls.
Resolved host identities use a separate evidence cohort and are checked again
before invocation. Runtime model changes preserve incurred usage but cannot count
as evidence for the earlier identity. Recovery checks worker creation time as
well as PID, retains ambiguous attempts, and addresses only their own container
names. It does not retry candidate execution.

Host correlation uses an AEEP-owned SQLite key. No Codex authentication file is
read, copied, returned or persisted. Codex itself owns authentication. The
assessment guide lists the remaining containment and live integration gates.

Separate agent sessions and fresh directories do not establish tool isolation.
Temporary Codex workers request minimal filesystem permissions, no network and
non-escalating approvals. Host acknowledgement and harmless local filesystem
probes are recorded separately from complete tool-access verification. An
incomplete inventory or unverified invocation path keeps scoped model trials
blocked. Boundary probes never read Codex authentication state or invoke
unrelated installed tools.

Managed-host containers use immutable image references and no host bind mounts.
Code and configuration digests are checked inside the launcher. Separate homes,
workspaces and optional credential volumes prevent accidental shared state;
they do not prove that agent commands cannot access credentials or use hosted
tools. Those boundaries require independently reviewed enforcement and actual
conformance evidence. Default networking is disabled. A selected network ID is
not proof of restricted egress. Scoped admission and routing reject missing or
changed worker conformance even when host identity is known.

Canonical event writes happen before publication to the invocation consumer.
Storage failure stops further execution; interruption retains the events already
committed. Cumulative usage is labelled separately from incremental usage, and
event replay cannot double-charge a completed operation. Operator scope
amendments share the original grant's counters and ceilings. Bundle review and
amendment application occur in one transaction.

### Differential environments and budget amendments

A capable control can use approved shell, files and Python libraries. Treatment
adds only the reviewed candidate bundle; candidate files, aliases and discovery
paths must be absent from control. Both workers require independently verified
post-login policy and immutable image bindings. Inventory equality and synthetic
probe success alone are insufficient. New differential records cannot upgrade
historical permission claims.

Budget amendments are operator-only, immutable and serialized against a checked
predecessor. They preserve the original ledger and do not credit consumed usage.
Models cannot approve definitions, amendments or adapters. Worker authentication,
model-service connectivity and command egress remain separate verified boundaries.
Workbook archives are byte/member/expanded-size bounded; macros, external links,
XML entity declarations and unsafe paths are outside the reviewed recipe.

Catalog metrics are opt-in and require the exact collector source in the worker's
reviewed file bindings. The local relay discards raw payloads and unknown tags,
bounds HTTP bodies and observations, and rejects child protocol frames that try
to impersonate its reserved notification. The coordinator rejects misbound or
regressing snapshots. Collector closure is not upstream export acknowledgement.
Task-command and supporting-integration access to the collector still require
verified enforcement; receipt observations do not grant themselves trust or
complete discovery status. Fresh telemetry settings need effective-policy review
and cannot widen the authorized remote destinations.

## Stack and setup boundaries

Treat goal metadata and discovery descriptions as untrusted data. Hosts must keep
private prompts and values out of persistent goal metadata and public capability
queries. A selected executor is fingerprint-bound; runtime inputs cannot broaden
the proposal's executor set. Exact proposal review does not grant a task scope or
raise a side-effect ceiling. Stack execution is opt-in in an already reviewed,
activated capability profile. Models have no setup, review or amendment tool.

Default progress records retain no output contents. Resume requires matching
artifacts; uncertain operations are not automatically replayed. The first runtime
accepts confirmed-free operations and serializes dispatch. It does not claim
containment for untrusted in-process Python or remote production support.

Provider readiness definitions bind reviewed adapter code and exact destinations.
HTTPS checks disable redirects and proxy environment inheritance, bound response
bytes and store only readiness states. Local runtime checks pin an executable hash
and argv. Sign-in stays with the provider/host; Codex authentication is never read.
Provider setup is not qualification or permission to spend. Unsupported installers
remain explicit blockers. See [STACK_PLANNING.md](docs/STACK_PLANNING.md).
