# AEEP Agent Router

Pick the best way for an AI agent to perform an action.

AEEP compares available routes—local Python, command-line tools, HTTP APIs, MCP tools, or an existing AI subscription—and chooses the best one for the current job. It considers cost, speed, reliability, quality, privacy, risk, and remaining quota.

It rejects routes that break your limits before scoring the rest.

> **Status:** AEEP 0.3 is working alpha software. Imported routes fail closed; review qualification evidence and policies before production use.

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
- Quotes, budgets, payments, provider discovery, and signed receipts when needed.

Commands use argument arrays, not shell interpolation. Requests cannot loosen manifest policy. Writes and payments require operator approval. Inputs and outputs are not stored by default.

## Learn more

- [Examples](examples/quickstart/README.md)
- [Protocol specification](SPEC.md)
- [Architecture](ARCHITECTURE.md)
- [Security](SECURITY.md)
- [Economic accounting](docs/ACCOUNTING.md)
- [0.3 proof harness and controlled campaign](examples/proof/README.md)
- [Economic network features](docs/ECONOMIC_NETWORK.md)
- [Changelog](CHANGELOG.md)

## Development

```bash
pip install -e '.[dev,http-server]'
ruff check .
mypy src
pytest
```

Licensed under [Apache-2.0](LICENSE).
