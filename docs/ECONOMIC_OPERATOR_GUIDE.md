# Economic evidence operator guide

This guide covers AEEP 0.5 economic evidence plus AEEP 0.7 subscription capacity
operations for already qualified and active routes. It does not qualify routes,
grant approval, move real money, or turn a provider quote into permission to
execute.

## Subscription-native diagnostics

For a reviewed Codex App Server manifest, inspect the local host without using a
model turn:

```bash
aeep hosts codex doctor --manifest aeep.yaml --json
aeep hosts codex account --manifest aeep.yaml --json
aeep hosts codex models --manifest aeep.yaml --json
aeep hosts codex quota --manifest aeep.yaml --json
aeep capacity list --manifest aeep.yaml --json
aeep capacity status RESOURCE_ID --manifest aeep.yaml --json
aeep capacity reservations --manifest aeep.yaml --json
```

Only `aeep hosts codex login` may start the interactive Codex-owned login flow;
run it only with explicit operator intent. Personal subscription capacity is
`SELF_ONLY`. The `aeep x402 conformance --binding aeep-local --json` command is
offline proof only and cannot transfer or settle value.

## 1. Keep the default offline first

Install and validate the manifest before enabling networking:

```bash
aeep doctor --manifest aeep.yaml
aeep economic doctor --manifest aeep.yaml --json
```

With `economic_evidence.enabled: false`, existing `aeep route` and `aeep run`
behavior is unchanged. `route()` never requests a live quote even when economic
configuration exists; only explicit prepared routing may do so.

## 2. Establish provider trust

The trust store is operator-owned JSON:

```json
{
  "schema_version": "0.4",
  "keys": [
    {
      "provider_id": "provider.example",
      "key_id": "provider-example-2026",
      "algorithm": "ed25519",
      "public_key": "BASE64URL_ED25519_PUBLIC_KEY",
      "valid_from": "2026-08-01T00:00:00Z",
      "valid_until": "2027-08-01T00:00:00Z",
      "revoked_at": null,
      "status": "active",
      "allowed_capabilities": ["text.statistics@1"],
      "allowed_quote_hosts": ["quotes.provider.example"],
      "rotation_from_key_id": null,
      "rotation_signed_at": null,
      "rotation_signature": null
    }
  ]
}
```

Obtain and compare the key through an authenticated operator channel. The
provider's key-discovery endpoint is useful for distribution but does not make
the key trusted. Use exact versioned capabilities and exact hosts—no wildcards.
Keep old/revoked metadata so historical evidence remains auditable.

## 3. Configure a bounded network path

Enable the minimum required surface:

```yaml
budget:
  budget_id: economic-local
  daily_marketplace_limit_usd: 1.00
  max_per_action_usd: 0.05
  prepaid_balance_usd: 1.00
  authorization:
    auto_approve_under_usd: 0
    financial_actions_require_human: true

economic_evidence:
  enabled: true
  settlement_currency: USD
  live_quotes:
    enabled: true
    top_k: 3
    per_provider_timeout_seconds: 2
    total_timeout_seconds: 4
    maximum_response_bytes: 262144
    maximum_clock_skew_seconds: 30
    maximum_quote_ttl_seconds: 600
  requirements:
    require_binding_quote_for_paid_routes: true
    allow_verified_static_offer: true
    allow_static_prior: false
    minimum_evidence_level: SIGNED_QUOTE
    quote_failure_policy: REQUIRE_BINDING_QUOTE
    pinned_rate_cards: {}
  market_aggregates:
    enabled: false
  network:
    allowed_quote_hosts: [quotes.provider.example]
    allow_private_addresses: false
    allow_redirects: false
    trust_environment_proxy: false
  trust_store:
    path: ~/.config/aeep/provider-keys.json
  payment:
    adapter: prepaid
```

The host allowlist and trusted key host scope must both authorize the endpoint.
Private addresses are for controlled local tests only. A provider descriptor's
advertised endpoint is never sufficient authority. The prepaid adapter is a
deterministic local ledger backed by the explicit AEEP budget above; it does not
hold or transfer real funds.

The invoice adapter is disabled unless `payment.unlimited_budget: true` is set
explicitly and the router is constructed with matching operator authority. Do
not use invoice/unlimited mode as a shortcut around a missing budget.

For a trusted fixed local tariff, an operator may provision an immutable
`RateCardSnapshot` into the same `ReceiptStore` and bind one exact executor:

```yaml
economic_evidence:
  requirements:
    pinned_rate_cards:
      provider.http.fixed:
        # Replace this illustrative digest with the stored snapshot's exact ID.
        rate_card_snapshot_id: rate_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
        meter_quantities:
          - rate_id: request-fixed
            meter: requests
            unit: request
            quantity: "1"
```

Only unconditional monetary rates are valid payment authority in 0.4.
Subscription-unit, region/tier/tool/long-context/rule-conditioned, expired,
missing, or meter-mismatched snapshots fail closed. The configured quantities
are hard bounds, not post-hoc provider claims.

## 4. Declare quote disclosure

A quote request always sends bounded structural `ActionFeatures`. Additional
features require operator-declared route configuration. Prefer counts and
booleans:

```yaml
executors:
  - id: provider.http.extract
    # ...normal executor fields...
    config:
      economic:
        quote_disclosure:
          fields:
            - source: action_features.input_bytes
              name: input_bytes
            - source: action_input.page_count
              name: page_count
              type: integer
```

Do not disclose prompts, resumes, job descriptions, names, email addresses,
credentials, file contents, secret-bearing URLs, or unbounded strings. Inspect
the prepared decision's `disclosed_quote_features` before execution.

## 5. Import and inspect evidence

Signed evidence is immutable. An exact duplicate import is idempotent; altered
reuse of an ID fails.

```bash
aeep offer import provider-offer.json --manifest aeep.yaml
aeep offer verify offer-123 --manifest aeep.yaml --json
aeep offer show offer-123 --manifest aeep.yaml
aeep offer list --capability text.statistics@1 --manifest aeep.yaml
```

Market aggregates are imported only from a bounded local JSON envelope; the CLI
does not fetch an advertised URL:

```bash
aeep market aggregate-import aggregates.json --manifest aeep.yaml --json
aeep market aggregate-list --capability text.statistics@1 --manifest aeep.yaml
aeep market aggregate-show AGGREGATE_ID --manifest aeep.yaml
aeep market aggregate-verify AGGREGATE_ID --manifest aeep.yaml --json
```

Successful import preserves `STATIC_PRIOR` provenance. It does not qualify or
activate a route, make the aggregate binding, or prove that every local selector
coverage/freshness requirement is met.

Verification output must show provider, evidence level, key/signature status,
validity, and expiry. Never include secret keys or raw action input in an
operator ticket.

## 6. Prepare, review, then execute

For a process-safe prepare/execute pair, save the complete bounded
`ActionRequest` locally and use the same file for both commands. For example:

```json
{
  "action_id": "action-cli-live-001",
  "capability": "text.statistics@1",
  "input": {"text": "one two three"},
  "policy": "balanced"
}
```

Prepare and retain the returned `prepared_id`:

```bash
aeep economic prepare text.statistics@1 \
  --request @action.json \
  --max-cost-usd 0.005 \
  --quote-policy REQUIRE_BINDING_QUOTE \
  --manifest aeep.yaml \
  --json
aeep economic prepared-show PREPARED_ID --manifest aeep.yaml
```

`aeep economic quote-request` accepts the same capability/input/budget/policy
options and uses the same qualified top-K preparation path. Inspect a stored
quote with `aeep economic quote-show QUOTE_ID` and
`aeep economic quote-verify QUOTE_ID`.

After review, execute the prepared ID with that same local request and the
required independent approvals:

```bash
aeep run-prepared PREPARED_ID \
  --request @action.json \
  --approve-payment \
  --manifest aeep.yaml \
  --json
aeep settlement show SETTLEMENT_ID --manifest aeep.yaml --json
```

Use `--approve SIDE_EFFECT` only up to the existing operator ceiling and add
`--human-approved` only after the required human approval occurred. These flags
cannot raise manifest policy.

The Python API makes the network boundary explicit:

```python
prepared = await router.prepare_route(action_request)
if not prepared.feasible:
    for rejected in prepared.rejected_candidates:
        print(rejected.executor_id, rejected.reasons)
else:
    selected = next(
        item
        for item in prepared.candidate_rankings
        if item.executor_id == prepared.selected_executor_id
    )
    print(selected.expected_amount, selected.evidence_level)
    print(prepared.maximum_cash_authorization)
    outcome = await router.execute_prepared(
        prepared.prepared_id,
        payment_approved=True,
        human_approved=True,
    )
    print(outcome.receipts)
```

An operator that has explicitly enabled ordinary fallback policy may instead
call `execute_prepared_with_fallback(...)` for one bounded action. The helper
fresh-prepares at most once, excludes the failed executor, and uses a new action
attempt, idempotency binding, digest, and quote. It is allowed only after a
durably settled `FAILED`/`REJECTED` result from an idempotent read route. It never
falls back after timeout/indeterminate outcome or for a consequential route.

Preparation applies qualification and non-price hard constraints before any
provider is contacted, quotes at most the configured top-K candidates, validates
signatures/binding/replay/expiry, uses the maximum for budget feasibility, and
persists only digests and approved features.

Pre-execution cash remains an estimate/bound on `CandidateRanking` (and its
immutable quote), not authoritative actual `ResourceAccounting`. Actual
accounting is attached only after usage/settlement/reconciliation evidence.

For every nonzero maximum, inspect `authorization_kind` and `authorization_id`
on the prepared decision. The accepted bases are `SIGNED_QUOTE`,
`PUBLISHED_OFFER`, and `PINNED_RATE_CARD`. A quote/offer must match its selected
record ID. Published-offer authorization is fixed-price only in 0.4; usage
pricing requires a request-bound quote. A rate-card basis also records the
snapshot, exact rate IDs, and bounded meter quantities used to calculate the
maximum. A generic static prior may help ranking but is never payment authority.

Immediately before execution AEEP rechecks decision/quote expiry, action and
policy digests, active route/fingerprint, key status, budget, approval, and
idempotency. Paid execution reserves the immutable authorized maximum first.
Consequential capabilities still need the host/operator approval token; the
provider cannot grant it.

Because raw action input is not persisted, normal `execute_prepared()` follows
`prepare_route()` in the same live router process. A persisted prepared record
is an audit/recovery record, not a replayable payload. After a restart, recovery
may resolve reservation/settlement state but must not reconstruct or re-execute
the action from its digest.

For a deliberately separate CLI process, the operator must resupply the full
`ActionRequest` from a local file. Reuse the same stable `action_id`; if the run
document omits it, the CLI fills the stored ID, while an explicitly different ID
fails closed. AEEP also validates capability, input, constraints, context,
idempotency, and effective policy against the stored digests. It still does not
add the raw request to the economic tables. Treat that local file under the same
confidentiality policy as the original action and delete it according to
operator retention policy.

Cancel a decision while it is `PREPARED` when it is no longer needed. The async
cancellation path may also release a reservation only while durable state shows
invocation has not begun. It rejects casual cancellation after `INVOKING`; an
external effect with an uncertain outcome is not relabeled failed or retried.

```bash
aeep economic prepared-cancel PREPARED_ID --manifest aeep.yaml --json
```

When economic evidence is enabled, the existing caller-authored workflow API
uses the same prepared boundary one dependency-resolved wave at a time. It binds
real upstream outputs before quoting, may prepare independent read-only steps
concurrently, and serializes a wave before quoting when any compatible route
could be consequential, delegated, hosted, or resource-exclusive. The workflow
checks prior settled actual cash plus all maxima in the wave against
`WorkflowBudget.max_cash_usd`; an unusable or over-budget wave is cancelled
before reservation. Payment and human approvals remain explicit workflow-call
arguments. Economic evidence disabled preserves the legacy offline workflow
path.

## 7. Inspect settlement and reconciliation

For maximum USD 0.0050 and actual USD 0.0038, a completed receipt must show:

```text
reserved: USD 0.0050
captured: USD 0.0038
released: USD 0.0012
evidence: PAYMENT_SETTLEMENT
```

Use settlement inspection to verify the one-currency invariant, charge/attempt
binding, adapter, external reference, status, and evidence level. Reconciliation
adds a later billing record reference/digest; it does not overwrite or delete
the quote, usage, or settlement.

Do not upload raw invoices by default. Store only the external reference and
evidence digest needed for audit. Overcharge, missing record, or amount mismatch
remains visible as a discrepancy/dispute.

When the configured adapter supports an authenticated billing lookup:

```bash
aeep settlement reconcile SETTLEMENT_ID --manifest aeep.yaml --json
```

This command does not accept a model-supplied amount or grant payment authority;
it asks the configured adapter to compare its existing external record.

## 8. Recovery runbook

After an interrupted process, do not rerun the action. Run the economic recovery
operation, then review every unresolved decision:

```text
RESERVED          check whether invocation began; otherwise release
INVOKING          inspect provider attempt/outcome; never assume failure
AWAITING_USAGE    retrieve/verify the existing attempt's usage only
SETTLING          query adapter idempotency and resume settlement only
INDETERMINATE     reconcile or escalate; keep reservation outstanding
DISPUTED          resolve against signed quote and billing evidence
```

Recovery may settle or release idempotently when evidence permits. It must not
execute a job submission, payment, email, destructive command, or other external
action again.

Embedded recovery is `await router.economic_recover()`. It returns a sanitized
summary of resolved and still-indeterminate decisions; it never returns or
reconstructs action payloads.

The CLI equivalent is:

```bash
aeep economic recover --manifest aeep.yaml --json
```

## 9. Key and endpoint incidents

- **Suspected key compromise:** mark the key revoked, stop live quotes for the
  provider, invalidate unexecuted prepared decisions, retain historical
  metadata, and rotate only through a verified chain or fresh operator review.
- **Endpoint compromise/SSRF alert:** remove the host from local configuration,
  block it at egress, cancel only safe pre-invocation decisions, and review
  quote disclosures/logs without printing credentials.
- **Amount above maximum:** do not capture above the maximum; preserve the usage
  assertion and open a pricing dispute/reconciliation.
- **Adapter failure after execution:** preserve reservation and execution
  evidence as indeterminate. Do not report zero.
- **Policy or fingerprint drift:** execution must stop; requalify/reactivate and
  prepare a fresh action-bound decision.

## 10. Reference service

For local deterministic testing only:

```bash
python3 -m pip install -e '.[http-server]'
aeep market serve --host 127.0.0.1 --port 8787
python3 examples/economic_market/demo.py
```

The test key is public, loopback HTTP is intentional, and the in-memory ledger
is not a production payment rail or privacy system. See
`examples/economic_market/README.md`.

To exercise bearer authentication, export a locally chosen test token before
starting the service and use the separate manifest whose quote and execution
clients reference that environment variable:

```bash
export AEEP_REFERENCE_MARKET_TOKEN='locally-chosen-test-token'
aeep market serve
aeep economic prepare text.statistics@1 \
  --request @examples/economic_market/action.json \
  --manifest examples/economic_market/aeep-authenticated.yaml --json
```

Use the same authenticated manifest and request file for `run-prepared`. The
manifest stores only `auth_token_env`; the token remains in the environment.

## Current limitations

- Enabled 0.4 economic routing/settlement is USD-only. `CurrencyAmount` can
  validate other internally consistent currencies as protocol evidence, but the
  router rejects a non-USD economic configuration and never converts currencies.
- Rehydrating a prepared action across a CLI process requires the original full
  `ActionRequest` file. It is digest/policy-checked and not persisted.
- The built-in prepared workflow path does not automatically prepare or execute
  a fallback after its selected step fails or becomes uncertain. Resolve the
  prior attempt, then have the authorized caller prepare a fresh bounded action;
  never infer that a consequential effect did not occur.
- The local reference ledger/trust key/aggregate cohort demonstrate protocol
  behavior; they are not payment custody, high availability, or a formal privacy
  guarantee.
