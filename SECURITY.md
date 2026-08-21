# Security policy and deployment guidance

AEEP can launch commands, call remote services, and advise another agent. Treat its manifest and database as security-sensitive control-plane assets.

## Supported version

The repository is an alpha. Security fixes target the latest commit/version only until a stable release policy is published.

## Reporting

Do not open a public issue containing a working exploit, credential, or private endpoint. Use the repository's private security-advisory channel when one is established; until then, contact the repository owner privately.

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

## HTTP/SSRF

- Public remote calls require HTTPS by default.
- Private, loopback, link-local, multicast, reserved, and non-public targets are blocked unless explicitly enabled.
- Use `allowed_hosts` even when private networks are intentionally enabled.
- Redirects are disabled by default. Avoid enabling them for agent-controlled URLs.
- Production deployments should enforce egress policy outside the process because application-level DNS checks cannot eliminate every rebinding/race condition.

## MCP

Connecting an MCP server grants it an integration boundary. Review its command, environment, working directory, transport URL, authentication, and exposed tool behavior. Remote content can contain prompt injection; AEEP routing does not sanitize an agent's interpretation of returned data.

Remote MCP HTTP clients use the ordinary HTTP executor's HTTPS, allowlist, IP-classification, redirect, response-size, and no-ambient-proxy defaults. Modern MCP request headers are derived only from validated primitive schema properties; duplicate case-insensitive names, unsafe names, unsupported schemas, or header/body disagreement are rejected. Stdio and HTTP messages are bounded, but production deployments still need process, ingress, and egress limits outside Python.

The built-in HTTP MCP server uses a static bearer token as a minimum guard. Put it behind TLS, authentication, Origin validation/policy, request-body limits, rate limits, logging, and network policy. Do not expose it directly as a public multi-tenant service.

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

`aeep_record_outcome` changes future estimates. Treat access to it as write access to routing policy. Authenticate remote callers, rate-limit reports, preserve provenance, and do not merge unauthenticated reports into shared reputation. The reference implementation accepts an external report only for the selected feasible delegate and only once per decision/executor pair, but a compromised authorized caller can still fabricate that one report. Use `ActionProfiler` for trusted operator-owned measurement outside the delegate flow.

Provider descriptors and estimates are claims, not observations. Local reputation excludes untrusted and self-asserted observations. The compatibility HMAC signature proves possession of one shared secret only; it is not public-key identity or a global trust system. Cross-provider 0.4 economic evidence uses locally trusted Ed25519 keys bound to provider identity, capability, validity period, revocation metadata, and approved quote hosts.

Imported traces and SDK measurements also influence local history. Treat trace files and instrumented client access as trusted measurement inputs. The built-in instrumentation stores resource metadata and identifiers, not action payloads or model outputs; trace attributes can still contain sensitive data and should be filtered at the telemetry collector.

## Subscription resources

- Treat quota state as private routing data, not currency or transferable value.
- Prefer explicit user/host/official signals; do not scrape undocumented billing dashboards.
- A host selection does not grant the host new permissions. Keep its normal approval UI and sandbox enabled.
- Authenticate host outcome reporting and accept only the selected route once.

## Registries and imported providers

- Review local registry files as control-plane configuration.
- Remote registries use bounded HTTPS requests, no redirects, no ambient proxies, and the same DNS/IP/allowlist controls as HTTP execution.
- Imported OpenAPI writes are unsafe for automatic execution by default.
- CLI import accepts argv arrays and JSON stdin only; shell interpolation remains unsupported.
- Discovery/import never activates a route. Qualification is read-only,
  fingerprint-bound, and followed by a separate operator activation.
- Endpoint, argv, MCP tool/schema/protocol, image, or version drift suspends an active imported route.

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

`aeep benchmark` executes more than one feasible route. Even read-only routes can incur fees, consume quota, or disclose the same input to several providers. The CLI requires explicit confirmation, keeps hard constraints active, and skips non-idempotent/delegated routes by default. Do not expose benchmark invocation as an unrestricted model tool.

## Data policy

Set `data_sensitivity`, locality, and allowed residency on requests/policies. These fields are enforcement inputs only when executor metadata is trustworthy. A production network needs provider attestation and independent audit.

## Resource exhaustion

Set command/HTTP/MCP timeouts and output limits. Apply OS/container memory, CPU, process, file, and network quotas for stronger enforcement. AEEP estimates are not a substitute for kernel-level limits.

## Dependency and release hygiene

Before production:

- pin dependencies with hashes;
- enable automated vulnerability scanning;
- build reproducible signed artifacts;
- run tests on supported Python versions;
- review optional HTTP-server dependencies;
- restrict who can edit manifests and policies.
