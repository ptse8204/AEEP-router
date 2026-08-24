# Local economic evidence reference service

This service demonstrates AEEP 0.5 offers, request-bound quotes, provider usage,
billing reconciliation, and privacy-safe aggregates. It is an in-memory local
example: its deterministic private key is public test material and must never be
used for production trust or payment.

Install and start it on loopback:

```bash
python3 -m pip install -e '.[http-server]'
python3 examples/economic_market/server.py --unsafe-allow-unauthenticated-evidence
```

The operator CLI starts the same loopback provider; without a token, direct
usage/reconciliation ingestion remains locked:

```bash
aeep market serve
```

With the service running, prepare and execute the checked-in bounded action in
another terminal (replace the two displayed IDs with the prior command output):

```bash
aeep economic prepare text.statistics@1 \
  --manifest examples/economic_market/aeep.yaml \
  --request @examples/economic_market/action.json --json

aeep run-prepared PREPARED_ID \
  --manifest examples/economic_market/aeep.yaml \
  --request @examples/economic_market/action.json \
  --approve-payment --json

aeep settlement show SETTLEMENT_ID \
  --manifest examples/economic_market/aeep.yaml --json
```

For `action.json`, the deterministic result is expected/captured USD 0.0012,
maximum/reserved USD 0.0030, and released USD 0.0018. The settlement evidence
level is `PAYMENT_SETTLEMENT`.

That long flag is intentionally test-only. For an authenticated end-to-end
router flow, export the same locally chosen token in both terminals, start the
operator server, and use the separate authenticated manifest:

```bash
export AEEP_REFERENCE_MARKET_TOKEN='locally-chosen-test-token'
aeep market serve

aeep economic prepare text.statistics@1 \
  --manifest examples/economic_market/aeep-authenticated.yaml \
  --request @examples/economic_market/action.json --json
aeep run-prepared PREPARED_ID \
  --manifest examples/economic_market/aeep-authenticated.yaml \
  --request @examples/economic_market/action.json \
  --approve-payment --json
aeep settlement show SETTLEMENT_ID \
  --manifest examples/economic_market/aeep-authenticated.yaml --json
```

`aeep-authenticated.yaml` references the environment name; it does not contain
the token. It sends bearer authorization on offer, quote, and execution calls.

In another terminal, run the deterministic provider-evidence loop:

```bash
python3 examples/economic_market/demo.py
```

The 14 KiB example is quoted at expected USD 0.0038 and maximum USD 0.0050.
Execution returns text statistics plus a signed usage statement for USD 0.0038;
reconciliation records the external billing reference without storing an invoice.
The demo itself does not move or reserve money. Its aggregate payment-settlement
coverage is therefore zero; the external billing-reference coverage is reported
separately. In the prepared-router/payment
path the corresponding settlement reserves USD 0.0050, captures USD 0.0038, and
releases USD 0.0012.

Set `AEEP_REFERENCE_MARKET_TOKEN` before both the server and client/demo commands
to require bearer authentication. Non-loopback startup is refused without that
token. Requests must be `application/json` and are bounded to 256 KiB by default.

The unauthenticated operator-authored route is in `aeep.yaml`; the authenticated
variant is `aeep-authenticated.yaml`. Each offer fingerprint is derived from its
exact executor behavior. Both files opt into loopback economic network access,
declare only `action_features.input_bytes` for quote disclosure, and use a
synthetic USD 1.00 prepaid test balance with a USD 0.01 per-action ceiling. No
real payment rail or production credential is involved.
Routes imported from a provider descriptor remain inactive until the ordinary
qualification and activation flow; this manifest is the explicit trusted boundary.

The quote endpoint accepts only counts and the declared `input_bytes` disclosure.
It never accepts the action text. `/v1/execute` receives text only for execution;
the service retains no input or output. Aggregates are published only after at
least 20 billing-reconciled, task-valid records in one coarse input-size bucket,
and expose no action identifiers or digests. A settlement identifier is linkage,
not proof that a payment rail captured money.
