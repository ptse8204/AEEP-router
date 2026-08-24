# AEEP 0.5 provider and economic evidence threat model

This document scopes the new economic evidence path. It complements
`SECURITY.md`; it is not a penetration-test report or a production certification.

## Security objectives

1. Only active, qualified, exact-fingerprint routes can become prepared runtime
   candidates.
2. Only locally authorized providers/endpoints can receive a bounded quote
   request.
3. A quote is authentic, fresh, request-bound, replay-resistant, and capped
   before it influences selection or reservation.
4. Capture never exceeds its immutable quote, offer, or pinned-rate-card
   maximum; unused authorization is released.
5. Unknown execution or billing stays unknown and cannot trigger a blind retry.
6. Evidence provenance remains auditable without storing raw action input,
   output, invoices, credentials, or unrestricted provider payloads.
7. Economic evidence cannot qualify/activate routes or grant side-effect,
   financial, or human approval.

## Assets

- operator manifest, policy, route activation, and behavior fingerprints;
- provider trust store and signing private/public keys;
- quote host allowlist, credentials, and egress policy;
- action payload, action digest, quote disclosures, and user privacy;
- budgets, reservations, settlements, refunds, and billing references;
- prepared-decision state, attempt identity, nonces, and idempotency keys;
- local usage/task-valid observations and historical reputation;
- provider offers, quotes, usage statements, reconciliations, and aggregates;
- SQLite availability, integrity, and migration state.

## Trust boundaries and actors

| Actor/boundary | Trust |
|---|---|
| Operator manifest, approval ceiling, reviewed trust store | trusted control plane |
| Action/model input | untrusted |
| Qualified/active local registry record | trusted only for its reviewed fingerprint/policy |
| Remote provider and endpoint | partially trusted; signed claims still claims |
| DNS, network, proxy, redirect, HTTP response | untrusted |
| Payment adapter | trusted for its local orchestration record; external rail needs independent authentication |
| Provider usage/aggregate | provider assertion, not local observation or invoice proof |
| Billing record/invoice reference | stronger external evidence after authentication/reconciliation |
| MCP/model tool caller | cannot elevate approval or financial authority |

## Data flow and enforcement points

```text
ActionRequest
  | canonical digest; raw input stays local
  v
active exact routes -- qualification/policy/fingerprint --> feasible shortlist
  | operator-declared primitive disclosure only
  v
approved quote host -- network policy --> signed BoundedQuote
  | signature/key/host/binding/expiry/nonce/currency/maximum verification
  v
PreparedRouteDecision -- atomic claim + revalidation --> reservation maximum
  | persist INVOKING before call
  v
executor result + local meters + provider UsageStatement
  | structured billing policy; actual <= maximum
  v
SettlementReceipt -- optional external comparison --> BillingReconciliation
```

## Threats and mitigations

### Evidence tampering and identity

- **Offer/quote/usage/aggregate modification:** canonicalize with one version
  and verify Ed25519 over every signed field. Reject unknown algorithms,
  malformed base64url, floats, non-finite decimals, ambiguous timestamps, and
  signature/provider mismatch.
- **Provider/key impersonation:** trust keys only through operator review or a
  verified rotation chain. Bind keys to provider ID, exact capabilities, exact
  hosts, validity, status, and revocation. A quote response/key-discovery
  document cannot introduce trust.
- **Compromised key:** revoke it, invalidate unexecuted prepared decisions, stop
  its quote hosts, and retain old metadata for historical signing-time checks.
  Rotation from a compromised key still requires operator judgment.
- **Terms or executor substitution:** quote validation binds request ID,
  capability, executor ID, behavior fingerprint, action digest, nonce, terms,
  currency, structured billing policies, and any fixed attempt fee. The fee is
  present only for `CHARGE_FIXED_ATTEMPT_FEE`, uses the same currency, and cannot
  exceed the signed maximum. Drift fails before reservation.

### Freshness, replay, and concurrency

- **Expired/future quote:** enforce issue-time skew and bounded TTL during quote
  acceptance and again immediately before execution.
- **Nonce/quote replay:** use high-entropy nonces and atomic durable consumption;
  bind quote/reservation to one action/prepared decision/attempt.
- **Double execution:** claim prepared decisions transactionally and make them
  single-use by default. Conflicting claim/idempotency reuse fails.
- **Concurrent budget exhaustion:** combine budget check and reservation insert
  inside one SQLite `BEGIN IMMEDIATE` transaction. Outstanding/indeterminate
  reservations count against availability.

### Network and secret exposure

- **SSRF/cloud metadata/private scan:** require an operator-configured absolute
  endpoint and exact host, HTTPS by default, DNS/IP revalidation before each
  request, and block loopback/private/link-local/metadata/multicast/reserved/
  other non-public addresses unless specifically allowed for local testing.
- **DNS rebinding/connect race:** revalidate per request and enforce external
  egress/firewall policy. Application checks alone cannot fully remove the race.
- **Redirect abuse:** redirects are disabled. A future redirect-capable adapter
  must revalidate every hop and avoid credential forwarding across origins.
- **Ambient proxy leakage:** `trust_env` is disabled; injected clients must also
  disable it. Authentication is explicit and error/log output is sanitized.
- **Slow/oversized/malformed service:** per-provider and total timeouts, bounded
  concurrency/body bytes, strict content type/UTF-8/object validation, and
  structured errors prevent unbounded waits/memory/log data.
- **Advertised endpoint pivot:** a `ProviderDescriptor.quote_endpoint` is data,
  not permission; local network configuration and trust-key host scope are both
  required.
- **Cross-provider source confusion:** dispatch uses the operator-configured
  executor-to-quote-source mapping. A provider response cannot redirect another
  executor to its endpoint or choose the client used for a different provider.

### Action and disclosure privacy

- **Raw prompt/document exfiltration:** quote requests contain a digest,
  structural features, and only operator-declared bounded primitives. Secret
  paths and arbitrary/free-form strings are denied by default.
- **Path traversal/dynamic field request:** disclosure sources are parsed from a
  small approved root set and the provider cannot request extra fields at
  runtime.
- **Sensitive persistence/logging:** prepared/economic tables store action
  digest and approved disclosure only. No raw input/output/invoice/secret is
  stored by default. Quote errors omit credentials and bodies.
- **Digest correlation:** action digests can still correlate identical bounded
  actions within the holder's database. Protect retention/access and do not
  publish digests in market aggregates.

### Metering, charge, and settlement

- **Meter under-reporting/false success:** keep provider statements separate
  from local meters and task-valid evidence; do not let provider claims update
  quality/reliability qualification.
- **Missing/invalid usage after invocation:** preserve the reservation and mark
  the case indeterminate when signed policy cannot determine the charge. Do not
  report zero or retry. Accepted-result billing needs both a bound local
  task-valid receipt and signed provider evidence; provider-start billing needs
  explicit evidence that the provider started.
- **Meter over-reporting/amount above maximum:** preserve the signed statement,
  never capture above the immutable authorized maximum, mark a dispute, and
  reconcile.
- **Unknown billed amount:** do not assume zero or capture maximum unless the
  signed failure policy explicitly requires it. Keep the reservation
  outstanding/indeterminate and seek evidence.
- **Anonymous estimate used as payment authority:** require one matching
  `SIGNED_QUOTE`, `PUBLISHED_OFFER`, or `PINNED_RATE_CARD` basis for every
  nonzero authorization. A rate-card basis binds the immutable snapshot, exact
  rate IDs, and bounded meter quantities. Static priors may rank but may not
  reserve cash.
- **Currency confusion/float error:** strict `CurrencyAmount`, Decimal strings,
  USD-only 0.4 router settlement, exact equality checks, no FX, no infinity.
- **Duplicate settlement/release/refund:** immutable operation IDs and
  idempotency-key payload comparison return identical retries and reject
  conflicts/illegal terminal transitions. Refund totals cannot exceed capture.
- **Payment callback spoofing:** production callback adapters authenticate
  counterparties, validate references/amount/currency, use idempotency, and
  reconcile with their authoritative rail. The local adapter is not custody.
- **Billing discrepancy:** link quote, usage, settlement, and reconciliation to
  one charge without addition. Preserve matched/under/over/missing/pending/
  disputed status and evidence digest.

### Crash and side-effect ambiguity

- **Crash after reserve:** recovery may release only after durable evidence says
  invocation did not begin.
- **Crash/timeout after invocation:** `INVOKING` is persisted before the external
  call. Recovery checks the existing attempt/provider/payment state and resumes
  settlement only; it never re-executes a consequential/non-idempotent action.
- **Settlement failure after successful execution:** keep reservation and
  execution evidence as `SETTLING`/`INDETERMINATE`; do not emit a false free or
  successful-settlement result.
- **Approval laundering:** quote, provider terms, market data, or MCP/model
  arguments cannot raise effect/financial approval. Preparation may succeed
  while execution remains blocked on an operator token.

### Marketplace and aggregate abuse

- **Untrusted marketplace activation:** offers/quotes/aggregates cannot qualify
  or activate. Imported routes remain inactive until operator qualification and
  activation bind the exact behavior fingerprint.
- **Aggregate privacy leakage:** publish only coarse buckets above a minimum
  settled task-valid cohort, omit action identifiers/digests/input/output, and
  report evidence coverage and time window.
- **Poisoning/collusion:** verify signature/fingerprint/scope/freshness/cohort and
  treat aggregate as a prior. It cannot override a binding quote, local quality
  floor, or task correctness. Stronger local settlement/reconciliation remains
  separate.
- **Provider reputation from self-claims:** provider offers, projected metrics,
  and usage assertions are not execution observations. Reputation excludes
  unknown/untrusted amounts and uses local or independently attested evidence.

## Residual risks

- A valid provider key can sign dishonest prices, meters, or aggregates.
- App-level SSRF/DNS checks cannot replace network egress controls.
- SQLite and the in-process/local payment adapters are single-host reference
  components, not high-availability financial infrastructure.
- The reference aggregate service's minimum cohort and buckets demonstrate data
  minimization; they are not a formal differential-privacy guarantee.
- A compromised operator manifest/trust store/approval channel can authorize
  unsafe endpoints or routes.
- Clock rollback, filesystem rollback, or database tampering can undermine
  freshness/idempotency unless the host protects time and storage.
- External invoice/payment authentication and dispute handling are adapter/
  operator responsibilities.

## Deployment checklist

- Separate trust-store/manifest write access from model/tool callers.
- Use TLS, explicit authentication, external egress policy, and secret-manager
  references for every production quote/provider endpoint.
- Back up and integrity-check SQLite; monitor incomplete prepared/payment states.
- Alert on signature/binding/replay/overcapture/settlement failures and key
  revocation.
- Require explicit approval for consequential action and financial rails.
- Keep remote economic networking and market aggregates disabled until their
  providers, keys, hosts, disclosure, budgets, and retention are reviewed.
- Test tampering, replay, drift, timeout, crash recovery, and partial settlement
  in staging using deterministic local keys/providers.
