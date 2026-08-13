# Economic interoperability

The OSS package now implements the roadmap's provider-neutral execution path:

```text
subscription/local/API resources
            ↓
versioned capability + lazy provider discovery
            ↓
hard constraints + opportunity-cost routing
            ↓
quote + operator acceptance + budget reservation
            ↓
execution + layered validation
            ↓
signed receipt + trusted observation + reputation
            ↓
counterfactual savings + aggregate metrics
```

## Provider supply

Use `@aeep.capability(...)` for Python functions, or generate provider descriptors from existing software:

```bash
aeep import cli --provider-id demo --capability demo.echo@1 --argv '["demo-echo"]'
aeep import mcp --provider-id demo --capability demo.echo@1 --tool echo --endpoint demo-mcp
aeep import openapi openapi.yaml --provider-id demo
aeep publish --provider-id demo --name "Demo Provider" --output provider.json
```

Local or reviewed remote registries can expose that descriptor. AEEP fetches only the requested capability.

## Buyer flow

```bash
aeep quote demo.echo@1 --input '{"text":"hello"}'
aeep accept-quote quote_... act_... --max-amount-usd 0.02
aeep reserve-payment quote_... act_... --approve financial --human-approved
aeep capture-payment reserve_...
```

Refunds use `aeep refund-payment`. Financial commands are not model tools.

## Service boundary

The repository supplies protocols, local registries, adapters, descriptors, validation, signatures, budgets, and a local ledger. A commercial AEEP Network would operate public accounts, custody, payment collection, payouts, fraud detection, global reputation, dashboards, hosted sandboxes, provider-funded budgets, and clearing. Those stateful services intentionally remain outside the OSS control plane.
