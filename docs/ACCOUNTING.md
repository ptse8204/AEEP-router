# AEEP economic accounting

AEEP 0.3 keeps four ledgers separate:

| Ledger | What it records | Routing | Cash claim |
|---|---|---:|---:|
| Actual cash | Money attributable to the executed route | yes | yes, with eligible evidence |
| Subscription usage | Provider-local credits, messages, or allowance | yes | no |
| API-equivalent counterfactual | Pinned-tariff value of observed usage | no | no |
| Policy valuation | Operator opportunity value | yes | no |

There is no combined dollar total. A subscription action can have evidenced zero incremental cash and positive scarce usage. If its funding state is unknown, actual cash is unavailable—not zero. Fixed monthly fees are campaign context and are never amortized per action.

## Evidence and mirrors

`ResourceAccounting` is authoritative. Every known cash or usage value retains status, source, trust, and an opaque evidence reference when available. `ResourceVector.monetary_usd` and `subscription_units` remain compatibility mirrors; zero in a legacy mirror does not prove zero cash or zero quota use.

Provider reports remain provider reports. Static estimates remain estimates. A model-facing outcome cannot elevate either into verified evidence.

## Pricing

`RateCardSnapshot` canonicalizes a provider/product/model tariff and derives a SHA-256 snapshot ID. Calculations use `Decimal`, retain applied meter quantities and rate IDs, and never mutate historical rows. The same token calculation is attributable cash only when the pinned tariff governed the API route that ran. Applied to subscription Codex usage, it is an API-equivalent counterfactual. `aeep campaign revalue @report.json @snapshot.json` creates a separate derived view; it never edits the original campaign.

For models that report cache writes, `ModelTokenUsage.cache_write_input_tokens`
is a separate subset of input. Pricing subtracts both cached reads and cache
writes from uncached input, then applies each pinned meter exactly once.

Monthly subscription fees are contextual campaign metadata only. They are not divided by action count. Subscription pressure is computed inside each `(resource_pool, unit)` pair; unrelated plans and providers are never combined. An optional operator `policy_value_usd_per_unit` can affect rank, but remains a private policy valuation and cannot satisfy a cash budget or claim.

## Codex capture and campaigns

The campaign harness consumes bounded `codex exec --json` terminal usage first, then uses correlated fallback usage only for missing dimensions. Overlapping sources are never added; disagreement is marked `conflict`. Raw JSONL, prompts, outputs, diffs, commands, credentials, and invoice contents are not stored.

Campaigns pin their suite digest, route fingerprint, quota context, and rate-card snapshots in an isolated benchmark database. Process-cold trials create a fresh router. Router-warm requests perform a separate setup execution. When an adapter exposes cache telemetry, only confirmed hits enter statistics labeled warm; misses remain visible in raw trials and evidence coverage. `aeep campaign prove` evaluates the locked thresholds without filling unavailable evidence.

Reports render separate correctness/time, model-resource, actual-cash, subscription, API-equivalent, policy, and setup sections. There is deliberately no combined dollar total.

## Reporting language

Valid claims include “73% fewer Codex credits,” “24% fewer measured tokens,” and “68% lower API-equivalent value under snapshot X.” “Cash savings” requires eligible actual-cash evidence for both compared legs. “No incremental charge” requires per-trial evidence; “free” is not used for subscription execution.
