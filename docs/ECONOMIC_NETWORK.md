# Economic evidence exchange

AEEP 0.5 adds portable signed provider evidence while retaining provider-neutral economics. It is not a cryptocurrency,
blockchain, transferable token, public storefront, payment custodian, provider
payout service, or autonomous tool marketplace.

AEEP 0.7 additionally defines a provider-neutral capacity entitlement and an
offline `aeep-local` x402 batch mapping. The mapping commits, accumulates, and
reconciles already-authorized capacity records only. It is disabled by default,
performs no network call or value movement, and rejects `SELF_ONLY` resources
before serialization. Local conformance is not evidence of live-market readiness.

The exchange answers two bounded questions for an already qualified route:

1. What is the expected and guaranteed maximum provider charge for this exact
   action and executor fingerprint?
2. What amount did the local payment adapter capture after execution, and what
   later billing evidence agrees or disagrees with it?

```text
qualified and active route
        ↓
signed capability offer
        ↓
request-bound bounded quote
        ↓
prepared route decision
        ↓
maximum reservation
        ↓
execution + local/provider usage
        ↓
actual capture + unused release
        ↓
optional billing reconciliation
```

Marketplace evidence never qualifies or activates a route. AEEP retains exact
capability matching, security policy, task-valid success, local token/resource
measurement, subscription accounting, approval, and final selection.

## Disabled by default

Existing manifests and `route()` stay offline. Remote offers/quotes and market
aggregates require `economic_evidence.enabled: true`, live-quote/aggregate
enablement, explicit exact host allowlists, and a local trust store. HTTPS,
bounded bodies, no redirects, no ambient proxies, DNS/IP revalidation, and
minimal operator-declared disclosure are the defaults.

Provider-advertised URLs do not grant authority. Unknown providers and keys are
untrusted. The local deterministic reference service deliberately permits
loopback HTTP only when the operator starts it; its test key is public material.

## Evidence, not truth by signature

Ed25519 signatures make offer, quote, usage, and aggregate tampering detectable
and bind statements to a trusted provider identity. They prove the provider
made the statement, not that the route is correct, the meter is honest, or an
invoice charged that amount.

Evidence remains staged:

```text
static prior → offer → quote → usage statement → settlement → reconciliation
```

Stages share one charge linkage and are not summed. Local observations remain
separate. Market aggregates are scoped, stale-able priors with minimum cohorts;
they cannot override a live quote or local quality threshold.

## Provider supply

Providers can use `EconomicProvider` without instantiating router policy or
route selection. The helper currently ships in the main AEEP distribution; a
standalone minimal provider package is deferred. It validates and signs exact
offers, invokes a registered quote handler for one
capability/executor/fingerprint, and creates bound usage statements. The same
records can be served by an MCP server, HTTP API, CLI broker, or hosted-agent
gateway.

The local reference service exposes:

```text
GET  /health
GET  /.well-known/aeep-keys.json
GET  /v1/offers
POST /v1/quotes
POST /v1/usage-statements
POST /v1/reconciliations
GET  /v1/aggregates
```

It provides deterministic pricing and privacy-bucketed aggregates for tests.
It does not move money.

## Buyer and settlement boundary

`prepare_route()` performs the bounded network work explicitly after local
qualification/policy filtering. A nonzero reservation requires one immutable
signed-quote, published-offer, or pinned-rate-card authorization. Its maximum
governs feasibility and reservation; expected cost only affects ranking. An
anonymous static prior cannot authorize cash. `execute_prepared()` rechecks
route, policy, key, authorization, budget, idempotency, and approval, then
reserves, invokes, measures, and settles.

Payment adapters are rail-neutral orchestration. The free/prepaid/invoice/local
callback adapters enforce Decimal currency, idempotency, partial capture,
release, refund, and reconciliation invariants. They are not custody or
financial-accounting systems. Production rails must authenticate callbacks and
reconcile against their own authoritative records.

The 0.4 reference router enables this path only for USD because existing hard
budget, history, and compatibility fields are USD-denominated. Models retain an
explicit currency code for future interoperability, but no FX or non-USD router
settlement is implemented.

## Roadmap boundary

The roadmap deliberately separates protocol evidence from financial products:

- **0.4 — Economic evidence:** offers, quotes, prepared decisions, usage,
  reservation/settlement, reconciliation, aggregates, and local trust.
- **0.5 — Provider interoperability and aggregate trust:** broader provider
  compatibility, rotation/discovery governance, and stronger aggregate quality
  controls.
- **0.7 — Capacity contract conformance:** provider-authorized mock entitlement
  and replay-safe local x402 batch mapping, with live networking disabled.
- **Later — Provider settlement and marketplace governance:** optional hosted
  accounts, clearing, payouts, fraud controls, disputes, and governance, if a
  separate service is justified.
- **Later — Optional transferable marketplace credits:** only after explicit
  legal, security, governance, and product design. AEEP 0.7 makes no promise to
  create them.

See [Operator guide](ECONOMIC_OPERATOR_GUIDE.md), [Provider integration](PROVIDER_INTEGRATION.md),
[Accounting](ACCOUNTING.md), and [Threat model](THREAT_MODEL.md).
