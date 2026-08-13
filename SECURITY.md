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
