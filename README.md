# AEEP Agent Router

Pick the best way for an AI agent to perform an action.

AEEP compares available routes—local Python, command-line tools, HTTP APIs, MCP tools, or an existing AI subscription—and chooses the best one for the current job. It considers cost, speed, reliability, quality, privacy, risk, and remaining quota.

It rejects routes that break your limits before scoring the rest.

> **Status:** AEEP 0.5 is working alpha software. Signed provider packages still ingest inert; remote artifacts and economic networking are disabled by default. Review qualification, trust, payment, approval, and recovery policy before production use.

## Quick start

Python 3.11 or newer is required.

```bash
git clone https://github.com/ptse8204/AEEP-router.git
cd AEEP-router

python3 -m venv .venv
source .venv/bin/activate
pip install -e .

aeep init
aeep doctor
aeep run text.stats --input '{"text":"hello world"}'
```

`aeep init` creates a ready-to-run `aeep.yaml` with two local ways to calculate text statistics. AEEP chooses one and returns a JSON result with an execution receipt.

Want to see the choice without running anything?

```bash
aeep route text.stats --input '{"text":"hello world"}'
```

For the smaller response intended for an agent:

```bash
aeep route text.stats --input '{"text":"hello world"}' --agent
```

Useful commands:

```bash
aeep search     # find an action without loading the whole catalog
aeep list       # browse available actions
aeep route      # choose a route without running it
aeep run        # choose and execute a route
aeep history    # recent decisions and receipts
aeep metrics    # cost, time, and quota totals
aeep doctor     # check your configuration
aeep candidate  # qualify and activate imported routes
aeep workflow   # run a caller-authored action DAG
aeep campaign   # run an isolated repeated benchmark suite
```

## Try subscription-aware routing

This example compares local execution with the current Claude subscription. It needs no API key.

```bash
aeep route text.stats \
  --manifest examples/subscriptions/aeep.yaml \
  --input '{"text":"hello from Claude"}'
```

See [the subscription example](examples/subscriptions/README.md) to change the available quota and watch the selected route change.

Manage named subscriptions and quota signals:

```bash
aeep subscriptions status --manifest examples/subscriptions/aeep.yaml
aeep quota observe claude-max tight --manifest examples/subscriptions/aeep.yaml
```

## Try a real action

Route the current repository's default branch across local Git, GitHub HTTP, MCP, host subscription, and browser options:

```bash
aeep run github.repository.default-branch@1 \
  --manifest examples/github/aeep.yaml \
  --input '{"repository":".","owner":"ptse8204","name":"AEEP-router"}'
```

## Use it from Python

```python
import asyncio

from aeep import ActionRequest, Router


async def main():
    async with Router.from_manifest("aeep.yaml") as router:
        result = await router.execute(
            ActionRequest(
                capability="text.stats",
                input={"text": "hello from Python"},
            )
        )
        print(result.output)


asyncio.run(main())
```

## Verify a provider package without executing it

```bash
aeep provider verify examples/provider_package/aeep-provider.yaml -m examples/provider_package/aeep.yaml
aeep candidate ingest examples/provider_package/aeep-provider.yaml -m examples/provider_package/aeep.yaml
aeep candidate inspect fixture.command.text-statistics -m examples/provider_package/aeep.yaml
aeep candidate smoke fixture.command.text-statistics -m examples/provider_package/aeep.yaml
aeep candidate qualify fixture.command.text-statistics --reuse-evidence -m examples/provider_package/aeep.yaml
aeep candidate activate fixture.command.text-statistics -m examples/provider_package/aeep.yaml
```

Package and artifact signatures, exact fingerprints, evidence, and smoke results
are independent gates. Ingest never runs or activates imported code. New 0.5
records use RFC 8785; legacy signatures are historical/recovery-only.

## Prepare a route with economic evidence

Ordinary `route()` remains deterministic and network-free. Use the explicit
prepared API when a paid/dynamic route needs a request-bound quote:

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
    print("expected", selected.expected_amount)
    print("maximum", prepared.maximum_cash_authorization)
    outcome = await router.execute_prepared(
        prepared.prepared_id,
        payment_approved=True,
        human_approved=True,
    )
    print(outcome.receipts)
```

Preparation quotes only a bounded shortlist after qualification and non-price
hard constraints. Execution rechecks route, policy, fingerprint, authorization,
key, budget, idempotency, and approval; reserves the immutable quote, offer, or
pinned-rate-card maximum; captures actual cost; and releases the remainder.
Anonymous static priors cannot authorize nonzero cash. Provider economic
evidence never qualifies or activates a route and cannot grant approval.

## Try the local economic evidence service

The deterministic loopback service needs no external key or payment rail:

```bash
pip install -e '.[http-server]'
aeep market serve
```

The repository includes this bounded request in
`examples/economic_market/action.json`:

```json
{
  "action_id": "action-reference-cli-1",
  "capability": "text.statistics@1",
  "input": {"text": "one two\nthree"},
  "policy": "balanced",
  "constraints": {"max_cost_usd": 0.01},
  "idempotency_key": "economic-reference-cli-1"
}
```

In another terminal, prepare and execute the exact same request. Substitute the
IDs printed by each JSON response:

```bash
aeep economic prepare text.statistics@1 \
  --request @examples/economic_market/action.json \
  --manifest examples/economic_market/aeep.yaml \
  --json
aeep run-prepared PREPARED_ID \
  --request @examples/economic_market/action.json \
  --approve-payment \
  --manifest examples/economic_market/aeep.yaml \
  --json
aeep settlement show SETTLEMENT_ID \
  --manifest examples/economic_market/aeep.yaml \
  --json
```

The deterministic result is:

```text
expected: USD 0.0012
maximum/reserved: USD 0.0030
captured: USD 0.0012
released: USD 0.0018
cash evidence: PAYMENT_SETTLEMENT
```

The reference service's deterministic private key is public test material and
the local prepaid adapter does not move real money. The CLI does not persist or
print the action result payload in its economic records. See
[the local market example](examples/economic_market/README.md).

The 0.4 router is USD-only because existing policy/budget/history fields are
USD-denominated. Economic protocol models retain explicit currency codes for
future interoperability, but AEEP performs no FX or implicit conversion.

## Connect an AI client

Run AEEP as a local MCP server:

```bash
python3 -m aeep serve \
  --transport stdio \
  --manifest /absolute/path/to/aeep.yaml
```

Add that command to your MCP client. Setup notes for Codex, Claude, and other clients are in [Integration guides](docs/INTEGRATIONS.md) and [Bring Your Own Subscription](docs/BYOS.md).

Install the bundled minimal skill after a normal wheel install:

```bash
aeep skill install codex
```

Profile an existing OpenTelemetry trace without storing prompts or outputs:

```bash
aeep ingest otel trace.json
```

## What AEEP gives you

- One action name across Python, CLI, HTTP, MCP, and host-controlled routes.
- Hard limits for money, latency, network access, privacy, resources, and side effects.
- Actual cash, subscription quota, API-equivalent counterfactuals, and private policy valuations kept in separate ledgers.
- Isolated repeated campaigns with immutable pricing snapshots and `aeep campaign prove` release-gate evaluation.
- Output validation and receipts showing estimated versus actual use.
- Safe fallback when another route fails.
- Signed offers and request-bound quotes, prepared decisions, partial
  settlement, reconciliation, and evidence-safe reporting when explicitly
  enabled.

Commands use argument arrays, not shell interpolation. Requests cannot loosen manifest policy. Writes and payments require operator approval. Inputs and outputs are not stored by default.

## Learn more

- [Examples](examples/quickstart/README.md)
- [Protocol specification](SPEC.md)
- [Architecture](ARCHITECTURE.md)
- [Security](SECURITY.md)
- [Economic accounting](docs/ACCOUNTING.md)
- [0.4 proof harness and controlled campaigns](examples/proof/README.md)
- [0.5 economic evidence proof campaign](examples/economic_evidence/README.md)
- [Provider packages](docs/PROVIDER_PACKAGES.md)
- [Migration to 0.5](docs/MIGRATION_0.5.md)
- [Evidence reuse](docs/EVIDENCE_REUSE.md)
- [Cache affinity](docs/CACHE_AFFINITY.md)
- [DSH proof](docs/DSH_VALIDATION.md)
- [Job sandbox](docs/JOB_APPLICATION_DEMO.md)
- [Economic network features](docs/ECONOMIC_NETWORK.md)
- [Economic operator guide](docs/ECONOMIC_OPERATOR_GUIDE.md)
- [Provider integration guide](docs/PROVIDER_INTEGRATION.md)
- [0.4 migration guide](docs/MIGRATION_0.4.md)
- [Economic threat model](docs/THREAT_MODEL.md)
- [Changelog](CHANGELOG.md)

## Development

```bash
pip install -e '.[dev,http-server]'
ruff check .
mypy src
pytest
```

Licensed under [Apache-2.0](LICENSE).
