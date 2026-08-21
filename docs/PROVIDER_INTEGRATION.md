# Provider economic evidence integration

A provider can publish AEEP 0.4 economic evidence without adopting AEEP route
qualification, scoring, payment custody, or the complete router. The protocol is
transport-neutral and works behind HTTP, MCP, a CLI broker, or a hosted-agent
gateway.

The Python helper currently ships in the main distribution, but it does not
instantiate the router or require provider-side route policy. It is not yet a
separately published minimal provider package. Non-Python or dependency-minimal
providers may implement the generated 0.4 schemas, canonicalization vectors,
and Ed25519 envelopes directly.

## Provider responsibilities

A provider supplies only its side of the evidence boundary:

- an exact versioned capability, executor ID, and behavior fingerprint;
- structured pricing and billing/failure/retry policies;
- an explicit signed `fixed_attempt_fee` exactly when failed attempts use
  `CHARGE_FIXED_ATTEMPT_FEE`;
- a reusable signed `CapabilityOffer`;
- a short-lived request-bound signed `BoundedQuote`;
- a signed `UsageStatement` for the exact execution attempt when available;
- a billing record/reconciliation reference through an authenticated channel.

The provider does not qualify or activate itself. It cannot change the buyer's
success, quality, risk, approval, or security evidence. Its signature proves
that it made a statement, not that the statement is independently true.

## Keys and canonical signatures

Use a maintained Ed25519 implementation and protect the private key outside
ordinary application configuration. Publish only the public key plus key ID,
provider identity, validity window, exact capabilities, and expected quote
hosts. Plan rotation/revocation before production.

Signed records use `aeep-canonical-json-v1`. Do not sign an ordinary
`json.dumps()` result from a different serialization profile. Decimals are JSON
strings, timestamps are aware UTC, Unicode is NFC, nulls are explicit, floats
are forbidden, and the root `signature` field is excluded from the payload.
Keep the fixed vectors in `tests/test_v04_signing.py` in cross-language CI.

## Lightweight Python helper

`EconomicProvider` validates bindings and handles deterministic signing and
idempotent duplicate requests. The handler returns an unsigned mapping; the SDK
validates and signs it.

```python
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from aeep import (
    BillingTrigger,
    CurrencyAmount,
    FailureChargePolicy,
    ProviderExecutionStatus,
    RetryChargePolicy,
)
from aeep.economic.signing import Ed25519Signer
from aeep.sdk import EconomicProvider

signer = Ed25519Signer.generate(key_id="provider-example-2026")
provider = EconomicProvider("provider.example", signer)

offer = provider.register_offer(
    {
        "offer_id": "offer-text-statistics-1",
        "capability": "text.statistics@1",
        "executor_id": "provider.http.text-statistics",
        "executor_fingerprint": "sha256:" + "1" * 64,
        "pricing_rules": [
            {
                "rule_id": "request",
                "fixed_amount": {"amount": "0.0010", "currency": "USD"},
            }
        ],
        "billing_trigger": BillingTrigger.ON_SUCCESS,
        "failure_charge_policy": FailureChargePolicy.NO_CHARGE,
        "retry_charge_policy": RetryChargePolicy.EACH_ATTEMPT,
        "settlement_currency": "USD",
        "valid_from": datetime(2026, 1, 1, tzinfo=UTC),
        "valid_until": datetime(2027, 1, 1, tzinfo=UTC),
        "terms_digest": "sha256:" + "2" * 64,
        "issued_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
)


async def quote_handler(request):
    now = datetime.now(UTC)
    expected = CurrencyAmount(amount=Decimal("0.0038"), currency="USD")
    return {
        "quote_id": f"quote-{request.quote_request_id}",
        "quote_request_id": request.quote_request_id,
        "offer_id": offer.offer_id,
        "capability": request.capability,
        "executor_id": request.executor_id,
        "executor_fingerprint": request.executor_fingerprint,
        "action_digest": request.action_digest,
        "nonce": request.nonce,
        "expected_amount": expected,
        "maximum_amount": CurrencyAmount(amount=Decimal("0.0050"), currency="USD"),
        "estimated_meters": [],
        "billing_trigger": offer.billing_trigger,
        "failure_charge_policy": offer.failure_charge_policy,
        "retry_charge_policy": offer.retry_charge_policy,
        "terms_digest": offer.terms_digest,
        "issued_at": now,
        "expires_at": now + timedelta(minutes=5),
    }


async def usage_handler(request, quote, prepared_id, attempt_id):
    now = datetime.now(UTC)
    # Read these values from the provider's completed attempt record.
    return {
        "usage_statement_id": f"usage-{attempt_id}",
        "quote_id": quote.quote_id,
        "prepared_id": prepared_id,
        "action_id": request.action_id,
        "attempt_id": attempt_id,
        "executor_id": quote.executor_id,
        "executor_fingerprint": quote.executor_fingerprint,
        "execution_status": ProviderExecutionStatus.SUCCESS,
        "meters": [
            {
                "meter": "provider.example.input_bytes",
                "unit": "byte",
                "quantity": str(request.input_features.input_bytes),
            }
        ],
        "provider_calculated_amount": {
            "amount": "0.0038",
            "currency": quote.maximum_amount.currency,
        },
        "started_at": now,
        "completed_at": now,
        "issued_at": now,
    }


provider.register_quote_handler(
    offer.capability,
    offer.executor_id,
    offer.executor_fingerprint,
    quote_handler,
)
provider.register_usage_handler(
    offer.capability,
    offer.executor_id,
    offer.executor_fingerprint,
    usage_handler,
)
```

At the transport boundary call `await provider.process_quote(request)`. After a
known attempt, call `await provider.process_usage(quote_id,
prepared_id=prepared_id, attempt_id=attempt_id)`. The helper never invents
missing execution status, meters, or provider-calculated amount. Its in-memory
idempotency is suitable for examples; distributed providers need a durable
atomic store keyed by request, nonce, quote, and attempt.

## Quote request privacy

Quote handlers receive:

- action/quote request identifiers;
- exact capability, executor, and fingerprint;
- opaque action digest and nonce;
- bounded structural `ActionFeatures`;
- only operator-approved primitive disclosures;
- desired currency and optional acceptable maximum;
- creation/expiry times.

Do not request or infer the raw prompt/document merely for pricing. Reject
unknown disclosure fields. Bound counts and strings again at the provider
boundary. Never log authorization headers, raw action payloads, secrets, or
full quote request bodies.

## HTTP reference surface

A versioned provider/market service can expose:

```text
GET  /health
GET  /.well-known/aeep-keys.json
GET  /v1/offers?capability=...&executor_ids=...
POST /v1/quotes
POST /v1/usage-statements
POST /v1/reconciliations
GET  /v1/aggregates
```

Use HTTPS, authentication where appropriate, strict JSON content types, request
size/deadline/concurrency limits, stable structured errors, and no redirect to a
new signing/quote origin. Key discovery is informational; consumers still
establish trust locally.

An MCP or CLI transport carries the same strict models and signatures. Do not
weaken action/executor binding because a transport already has a session.

## Usage and settlement are different

`UsageStatement.provider_calculated_amount` is the provider's assertion. It
must never be labeled as payment proof. A buyer-side `SettlementReceipt` records
what its configured adapter reserved, captured, and released. A later
`BillingReconciliation` compares that settlement with an invoice/payment/billing
record. Link these stages using stable identifiers; do not add them as separate
charges.

When the provider's amount exceeds the signed maximum, return the statement for
audit but expect the buyer to cap capture and open a dispute. When the actual
amount cannot be safely determined, return an explicit indeterminate status or
manual-reconciliation policy—not zero.

## Market aggregates

Publish aggregates only for exact fingerprint/scope cohorts with enough
settled, task-valid samples. The reference minimum is 20. Bucket input size;
omit action IDs, action digests, prompts, and outputs; report sample/window,
quantiles, success confidence, settlement coverage, reconciliation coverage,
generation time, and expiry; sign the aggregate.

Aggregates are priors. Providers must not claim they qualify a route or replace
the buyer's validation evidence.

## Compatibility and conformance

- Keep legacy HMAC only for local/shared-secret compatibility.
- Do not redefine an old quote or receipt schema; use `schema_version: "0.4"`.
- Serialize money and meter quantities as decimal strings.
- Make identical retries idempotent and reject altered ID reuse.
- Test every signed field for tampering, expiry, wrong provider/fingerprint,
  replay, amount/currency mismatch, and non-finite input.
- Require `fixed_attempt_fee` exactly with `CHARGE_FIXED_ATTEMPT_FEE`, keep its
  currency consistent, and bound it by the quote maximum.
- Test against the local reference service in `examples/economic_market/` before
  connecting a production endpoint.
