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

Provider descriptors and estimates are claims, not observations. Local reputation excludes untrusted and self-asserted observations. The built-in HMAC signature proves possession of one shared secret only; it is not public-key identity or a global trust system.

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
- Discovery/import never activates a route. Qualification is read-only in 0.3, fingerprint-bound, and followed by a separate operator activation.
- Endpoint, argv, MCP tool/schema/protocol, image, or version drift suspends an active imported route.

## Economic evidence

- Treat provider usage metadata and model-facing outcome values as claims, not observations or billing evidence.
- Persist bounded evidence identifiers/digests, never invoices, account identifiers, credentials, or raw provider payloads.
- Unknown cash is not zero. Confirmed zero cash does not erase subscription or model-resource pressure.
- API-equivalent counterfactuals and policy valuations never enter cash totals, budget checks, payment ledgers, or cash-savings claims.
- Pin rate-card content and retain applied meters/rates; never silently reprice historical campaigns.

## Payments and budgets

- Quote retrieval is read-only; acceptance and payment operations are not model tools.
- Require the separate `financial` runtime ceiling plus configured human approval.
- Treat the local prepaid adapter and ledger as reference orchestration, not custody or accounting software.
- Rail callbacks for x402, MPP, invoice, or enterprise settlement must authenticate counterparties, enforce idempotency, and reconcile independently.

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
