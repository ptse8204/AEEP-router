# AEEP economic accounting

AEEP 0.5 keeps resource dimensions and their evidence separate. It does not
produce one universal dollar score.

| Ledger | What it records | Routing | Cash claim |
|---|---|---:|---:|
| Actual provider cash | Charge attributable to the executed route | yes | yes, with eligible evidence |
| Outstanding reservation | Authorized but not yet settled cash | budget only | no |
| Subscription usage | Provider-local credits, messages, or allowance | yes | no |
| Model/tool usage | Input, output, cached, schema, and result tokens | yes | no |
| Native resource usage | Requests, bytes, pages, seconds, CPU, memory, GPU, and network | yes | no |
| API-equivalent counterfactual | Pinned-tariff value of measured usage | no | no |
| Policy valuation | Operator opportunity value | yes | no |

There is no combined dollar total. A subscription action can have evidenced
zero incremental cash and positive scarce usage. When funding or billing is
unknown, actual cash is unavailable—not zero. Fixed monthly fees are campaign
context and are never amortized per action.

For managed subscription routes, AEEP retains every provider window and scores the
most constraining one. The exact opportunity burden is
`log1p(scarcity_multiplier × pool_weight × pressure × reset_factor + uncertainty)
/ success_probability`. Pressure uses exact remaining capacity when available,
otherwise the reported used percentage, otherwise a conservative unknown-state
penalty. `reset_factor` is 1–2 from the observed reset distance and window duration;
uncertainty is `1 - confidence`, plus 0.25 when exact remaining capacity is unknown
and another 0.25 when percentage is also unknown. Private per-unit values remain
labelled policy valuations and never become cash or settlement evidence.

## Estimate versus actual

Before execution, `RouteEstimate.cash` can be supported by a static prior,
published offer, signed quote, or market aggregate. These are predictions or
bounds. A binding quote's maximum is used for hard budget feasibility; its
expected amount is used for ranking when present. A prepared decision preserves
the expected/maximum/evidence on `CandidateRanking`; it does not relabel them as
authoritative actual `ResourceAccounting`.

After execution, `ExecutionReceipt.accounting.cash` can be supported by a
provider usage statement, payment settlement, billing reconciliation, or
operator attestation. Local and provider measurements remain separate.
`cash_estimate_from_offer`, `cash_estimate_from_quote`,
`cash_estimate_from_market_aggregate`,
`cash_accounting_from_usage_statement`, `cash_accounting_from_settlement`, and
`cash_accounting_from_reconciliation` centralize those conversions so router
paths cannot silently change trust labels.

## Evidence hierarchy

| Level | Meaning | Actual billed cash? |
|---|---|---:|
| `UNKNOWN` | no usable amount | no |
| `STATIC_PRIOR` | local/operator estimate | no |
| `PUBLISHED_OFFER` | reusable provider pricing claim | no |
| `SIGNED_QUOTE` | request-specific expected value and/or bound | no |
| `SIGNED_USAGE_STATEMENT` | provider asserts native usage/charge | provider-reported only |
| `OPERATOR_ATTESTED` | explicit manual human/operator assertion | no; visibly labeled, not rail proof |
| `PAYMENT_SETTLEMENT` | adapter recorded capture and release | yes, for that adapter |
| `BILLING_RECONCILED` | external billing record matched/resolved | yes |

The order describes provenance strength for automated economic proof.
`OPERATOR_ATTESTED` is intentionally below payment settlement and billing
reconciliation even though its enum declaration appears later for compatibility.
It may supply visibly manual actual-cost context, but it cannot satisfy a
payment/billing-evidence requirement, prove a capture, or support an automated
cash-savings claim about a charge. A signature identifies the asserting provider;
it does not independently verify meters or billing. Reconciliation may disagree
with settlement and must preserve the discrepancy rather than erase it.

## Unknown and confirmed zero

Unknown actual cash stays `None`/unavailable through routing, metrics,
reputation, counterfactuals, and reports. It cannot satisfy a known-cash policy,
become a free route, enter a cost average, or support a cash-savings claim.

Confirmed zero is a numeric zero plus eligible provenance—for example a
completed no-charge settlement. Estimated zero is still an estimate. Reports
must label all three cases separately:

```text
confirmed zero | estimated zero | unknown
```

The deterministic proof oracle has one narrow non-payment exception: an exact
operator-attested local zero with expected and maximum both zero and no
reservation, capture, or release may be a confirmed-free oracle candidate. It
does not become payment evidence and cannot establish cash saved from a paid
charge. Any paid/nonzero actual or captured amount requires settlement or
billing evidence.

`ResourceVector.monetary_usd` and `subscription_units` remain compatibility
mirrors. Zero in a mirror proves neither free cash nor unused quota. New logic
must inspect `ResourceAccounting`.

`PassiveRecommendation.estimated_cash_saving_usd` is nullable in 0.4. `null`
means either comparison leg lacks suitable cash evidence; numeric `0` means a
known comparison found no saving. Counterfactual reports follow the same rule.

## One charge, several stages

Offer, quote, usage statement, settlement, and reconciliation records share a
stable `charge_id`/evidence link. They are stages of one charge, not independent
costs. Stronger evidence can become authoritative while prior records remain
immutable for audit. Accounting resolves the authoritative value once and
does not add stages together. Differences remain explicit conflicts or
reconciliation discrepancies.

For a normal completed settlement:

```text
reserved = immutable authorization maximum
captured = actual billable amount
released = reserved - captured
captured + released = reserved
```

A nonzero authorization has exactly one immutable basis:
`SIGNED_QUOTE`, `PUBLISHED_OFFER`, or `PINNED_RATE_CARD`. Reservation and
settlement preserve that kind and ID. A quote binds its signed maximum; a 0.4
offer authorization binds fixed signed rules; a pinned rate card binds its
snapshot, exact rate IDs, and bounded native meter quantities. An anonymous
static prior remains an estimate and cannot authorize nonzero cash. This
prevents later estimate drift from changing the overcapture boundary.

Outstanding reservations reduce available budget but are not spent cash.
Released amounts restore availability. Refunds reduce net captured cash and
must never exceed capture. Indeterminate reservations remain outstanding until
recovery or reconciliation resolves them.

## Native meters and rate cards

`MeterQuantity` preserves provider-native meter name, unit, and Decimal
quantity. Provider custom meters are namespaced. A page, request, browser
minute, compute second, or byte is not converted into model tokens.

`RateCardSnapshot` canonicalizes a provider/product/model tariff and derives a
SHA-256 snapshot ID. Calculations use `Decimal`, retain applied meter quantities
and rate IDs, and never mutate historical rows. The same token calculation is
attributable cash only when that pinned tariff governed the API route that ran.
Applied to subscription-backed model usage, it is an API-equivalent
counterfactual. `aeep campaign revalue @report.json @snapshot.json` creates a
derived view; it never edits the original campaign.

For models that report cache writes,
`ModelTokenUsage.cache_write_input_tokens` is a separate subset of input.
Pricing subtracts cached reads and cache writes from uncached input and applies
each meter once.

Monthly subscription fees are contextual campaign metadata only. Subscription
pressure is computed inside each `(resource_pool, unit)` pair; unrelated plans
and providers are never combined. An optional operator
`policy_value_usd_per_unit` may affect rank but remains a private policy
valuation and cannot satisfy cash budget or settlement.

## Campaigns and reporting

Campaign capture retains bounded usage/evidence metadata but not prompts,
outputs, credentials, invoices, or raw provider payloads. Campaigns pin suite
digest, route fingerprint, quota context, and rate-card snapshots in an isolated
database. `aeep campaign prove` evaluates locked thresholds without filling
unavailable evidence.

Reports keep correctness/time, model resource, actual cash, reservation,
subscription, API-equivalent, policy, and setup sections separate. Valid claims
include “24% fewer measured tokens” and “68% lower API-equivalent value under
snapshot X.” “Cash savings” requires settlement or billing evidence for both
legs. “No incremental charge” requires per-trial evidence; “free” is not used
for subscription execution.
