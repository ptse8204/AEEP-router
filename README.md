# AEEP Agent Router

AEEP chooses how an AI agent action should run—before the model sees a large
tool catalog.

```mermaid
flowchart LR
    A[Exact action] --> B{AEEP policy gate}
    B -->|Reject| C[No execution]
    B -->|Select| D[One compatible route]
    D --> E[Validated result + receipt]
```

AEEP can route to local Python, CLI, HTTP, MCP, browser, or subscription-backed
implementations. Its preferred role is host-native execution routing beneath
native Tool Search: the host identifies a bounded capability, then AEEP applies
policy and selects one reviewed implementation without adding a routing-model
round. Unsafe or unaffordable routes are rejected before scoring.

It is an execution control layer—not a planner, marketplace, or model-specific
wrapper.

> **Status:** AEEP 0.7 is source-complete alpha software. Review policy, trust, approval, and
> recovery settings before production use.

## What works today

- Host-native routing that keeps hidden tool and router schemas out of model
  context.
- OpenAI/ChatGPT subscription execution through the official local Codex App
  Server boundary; Codex owns authentication and model discovery.
- Provider-neutral capacity reservations and durable execution-attempt recovery.
- Fail-closed provider packages with signatures, evidence, smoke checks, and
  explicit activation.
- Economic routing with hard limits, approvals, usage receipts, and recovery.
- Offline x402 capacity contract/conformance with live marketplace networking
  disabled by default.

## Measured result

This test asks one narrow question: when an exact deterministic tool already
exists, can routing before the model avoid the model's tool-selection loop?

| 20 matched actions | Codex + exact tool | AEEP + same tool |
|---|---:|---:|
| Exact results | 20/20 | 20/20 |
| Verified local-tool executions | 20/20 | 20/20 |
| Provider input + output tokens | 584,449 | 0 |
| Median tokens per action | 28,888 | 0 |
| Median latency | 8,324.9 ms | 5.47 ms |

Both sides were installed before measurement. Codex was given the exact command
and forbidden from discovering or installing anything; it still needed the
model → tool → model loop. AEEP received the structured `text.stats@1` action
and invoked the same underlying Python function without a provider call.

This tested saving applies only to the explicitly measured deterministic
`text.stats@1` action class. It does not measure clean-machine installation,
natural-language intent recognition, or work requiring model judgment. Provider
totals include Codex's full host context; the meter cannot attribute every token
to an individual schema. Unknown usage remains unknown, and live-market
readiness is never inferred from local conformance. [Method, exclusions, and raw
accounting](reports/v06/codex/tool-ready-campaign.md).

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

Preview the decision without executing:

```bash
aeep route text.stats --input '{"text":"hello world"}'
```

## Connect an agent host

Use `aeep host-bridge` for host-native pre-model routing. DeepSeek Harness has a
bundled adapter in [`integrations/dsh-aeep-router`](integrations/dsh-aeep-router/).

A local MCP server is also available when model-facing integration is required.
See [integration guidance](docs/INTEGRATIONS.md).

## Safety defaults

- Hard constraints run before scoring.
- Requests cannot loosen manifest policy.
- Imported routes are inert until qualified and activated.
- Writes and payments require operator approval.
- Inputs and outputs are not persisted by default.
- Commands use argv arrays, never shell interpolation.
- Personal subscription capacity is `SELF_ONLY` and cannot be resold or used to
  issue an external entitlement.
- Marketplace/x402 networking and value movement are absent and disabled by
  default.

## Documentation

- [Specification](SPEC.md)
- [Architecture](ARCHITECTURE.md)
- [Security](SECURITY.md)
- [Provider packages](docs/PROVIDER_PACKAGES.md)
- [Evidence reuse](docs/EVIDENCE_REUSE.md)
- [Economic accounting](docs/ACCOUNTING.md)
- [Migration to 0.7](docs/MIGRATION_0.7.md)
- [Examples](examples/quickstart/README.md)
- [Changelog](CHANGELOG.md)

## Development

```bash
pip install -e '.[dev,http-server]'
ruff check .
mypy src
coverage run --branch -m pytest
coverage json -o reports/v07/coverage.json
python3 scripts/check_critical_coverage.py reports/v07/coverage.json
aeep verify router-complete --profile all --strict --json
```

Licensed under [Apache-2.0](LICENSE).
