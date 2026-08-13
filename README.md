# AEEP Agent Router

**A working open-source economic profiler and policy router for agent actions across Python, CLI, HTTP APIs, MCP tools, and host-controlled browser/computer-use routes.**

AEEP answers a question most agent runtimes do not currently ask:

> Of the ways this action can be completed, which route is feasible and best **for this user, at this moment**, after accounting for money, time, compute pressure, quotas, reliability, quality, privacy, and side-effect risk?

It is not an API marketplace, model router, or MCP gateway by itself. It is the decision and measurement layer that can sit above all three.

> Project status: **working 0.2 alpha**. Local routing, subscription-aware host execution, capability quotes, validators, signed receipts, lazy provider discovery, counterfactual profiling, payment/budget interfaces, provider importers, and the test suite are implemented. Hosted marketplace accounts, custody, payouts, fraud systems, and clearing remain separate services.

## Why this exists

General-purpose agents can often complete the same semantic action through several surfaces:

```text
                         semantic action
                               │
        ┌──────────────┬───────┼────────┬──────────────┐
        │              │       │        │              │
   local Python       CLI     HTTP      MCP       host browser/
                                                   computer use
```

The seemingly "more structured" route is not always cheaper:

- An MCP server can inject a large schema for a trivial action.
- An API can return 30 KB when the visible page already shows the one needed value.
- A local CLI can finish deterministically without another model round trip.
- A browser route can be cheapest when the page is already open and the next action is one click.
- A paid specialist API can be far cheaper and more reliable than frontier-model computer use.

AEEP preserves the raw resource measurements and lets the caller decide their value. It does **not** claim that all model tokens are interchangeable or invent a speculative currency.

## Design correction: constraints first, score second

A naïve weighted average can select a fast route that violates privacy, a cheap route that exceeds memory, or a reliable route that performs an unapproved write.

AEEP therefore uses a two-stage decision:

1. **Feasibility gates** reject routes that violate hard limits: budget, latency, context, CPU/GPU/memory, network, privacy/residency, minimum reliability/quality, risk, executor allowlists, and side-effect policy.
2. **Multi-objective ranking** scores only feasible routes.

The default `balanced` policy ranks expected burden using:

- cash cost,
- latency,
- compute and quota pressure,
- probability of success,
- output quality,
- risk,
- locality/state locality.

All estimates are adjusted by probability of success so a cheap route that repeatedly fails is not treated as cheap.

The built-in presets are:

| Policy | Primary preference |
|---|---|
| `balanced` | Cost + latency + compute pressure |
| `cheapest` | Expected economic cost |
| `fastest` | End-to-end latency |
| `resource_saver` | Context/CPU/memory/GPU/network conservation |
| `reliable` | Valid, high-quality outcomes |

Custom policies, hard constraints, reference scales, shadow prices, and fallback rules live in YAML or can be supplied through the Python API.

## Working in 60 seconds

Python 3.11+ is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .

aeep init
aeep doctor
```

The generated manifest contains two real routes for the same `text.stats` capability: an in-process Python function and a local CLI.

Inspect without execution:

```bash
aeep route text.stats \
  --input '{"text":"hello from an agent"}'
```

Execute the selected route:

```bash
aeep run text.stats \
  --input '{"text":"hello from an agent"}'
```

Both commands emit machine-readable JSON. Add `--compact` for one-line JSON.

A route decision includes:

```json
{
  "selected_executor_id": "builtin.text-stats",
  "candidates": [
    {
      "executor_id": "builtin.text-stats",
      "feasible": true,
      "rank": 1,
      "estimate": {
        "resources": {
          "monetary_usd": 0.0,
          "latency_ms": 2.0,
          "cpu_ms": 1.0,
          "peak_memory_mb": 32.0,
          "context_tokens": 0
        },
        "success_probability": 0.999
      },
      "score": {
        "monetary": 0.0,
        "latency": 0.00026,
        "compute": 0.01,
        "reliability": 0.0001,
        "total": -0.036
      }
    }
  ]
}
```

An execution also returns validated receipts containing the estimate, actual resource use, status, latency, trace ID when available, and safe metadata.

## The low-level package job

For one `ActionRequest`, AEEP performs:

```text
validate input
    ↓
discover equivalent executors
    ↓
blend configured estimates with observed receipts
    ↓
apply hard safety/capacity/privacy constraints
    ↓
score feasible routes with caller policy
    ↓
select and explain
    ↓
obtain runtime approval for side effects
    ↓
execute through Python / argv CLI / HTTP / MCP / delegate
    ↓
validate output contract
    ↓
persist receipt
    ↓
fall back only when safe
    ↓
update future estimates from observations
```

## Core objects

### `ActionRequest`

A bounded semantic action, not an arbitrary prompt:

```json
{
  "capability": "github.current_branch",
  "input": {"repository": "/workspace/app"},
  "policy": "balanced",
  "constraints": {
    "max_latency_ms": 2000,
    "max_cost_usd": 0.02,
    "max_side_effect": "read",
    "allow_network": false
  },
  "context": {
    "data_sensitivity": "internal",
    "state_locality": "local",
    "compute": {
      "context_tokens_remaining": 5000,
      "available_memory_mb": 1024,
      "network_metered": false
    }
  }
}
```

### `ExecutorSpec`

One route capable of fulfilling the action. Executor kinds:

- `python`: reviewed in-process callable.
- `command`: local argv execution; shell interpolation is intentionally unsupported.
- `http`: bounded REST/HTTP call with HTTPS and SSRF-conscious defaults.
- `mcp`: stdio or Streamable HTTP MCP tool call.
- `delegate`: return instructions to the host agent for browser, computer-use, model-only, GUI, or another runtime that AEEP cannot directly control.

### `ResourceVector`

AEEP preserves raw dimensions:

```yaml
monetary_usd: 0.012
latency_ms: 820
cpu_ms: 40
memory_mb_seconds: 12
peak_memory_mb: 128
gpu_ms: 0
network_bytes: 24000
context_tokens: 3100
input_tokens: 900
output_tokens: 180
```

`context_tokens` represents context footprint such as tool schemas/results. `input_tokens` and `output_tokens` can hold exact provider usage when known. The included tokenizer-independent estimate is clearly identified as an estimate.

### `RouteDecision`

Contains every candidate, rejection reasons, score components, selected executor, and effective policy.

### `ExecutionReceipt`

Records predicted versus actual usage and whether the output contract was valid. Receipts are persisted in SQLite and feed future estimates. Provider claims and observed performance remain separate.

### `BenchmarkResult`

Records a deliberately sequential calibration run across feasible alternatives. It preserves both predicted and observed resources and ranks only routes that actually ran. Delegates and non-idempotent executors are excluded by default.

### `PersistenceConfig`

Controls what enters SQLite. Full action input and context are redacted by default, while live decisions returned to the caller remain complete. Output previews remain opt-in per executor.

## Manifest example

```yaml
version: "0.2"
database: .aeep/aeep.db
default_policy: balanced
persistence:
  store_action_inputs: false
  store_action_context: false

resources:
  - id: openai.chatgpt
    kind: subscription
    provider: openai
    product: chatgpt
    access: {mode: host}
    quota: {state: normal, confidence: 0.7, source: user}
    capabilities: {reasoning: true, coding: true, browser: true}

policies:
  constrained_laptop:
    description: Prefer low context, memory and network use on a laptop.
    weights:
      monetary: 0.15
      latency: 0.15
      compute: 0.50
      reliability: 0.10
      quality: 0.05
      risk: 0.05
    constraints:
      max_peak_memory_mb: 1024
      max_context_tokens: 12000
      max_side_effect: read
    resource_scarcity_multiplier: 5.0

executors:
  - id: git.local-current-branch
    capability: github.current_branch
    kind: command
    description: Read the current branch from the local Git worktree.
    input_schema:
      type: object
      properties:
        repository: {type: string}
      required: [repository]
      additionalProperties: false
    output_schema:
      type: object
      properties:
        branch: {type: string}
      required: [branch]
      additionalProperties: false
    estimate:
      resources:
        latency_ms: 20
        cpu_ms: 5
        peak_memory_mb: 12
      success_probability: 0.995
      quality_score: 1.0
      risk_score: 0.005
      confidence: 0.8
    side_effect: none
    locality: local
    idempotent: true
    safe_to_auto_execute: true
    config:
      argv:
        - python
        - scripts/current_branch.py
        - "{input.repository}"
      output: {type: json}
      timeout_seconds: 5

  - id: github.remote-mcp-current-branch
    capability: github.current_branch
    kind: mcp
    description: Query a configured GitHub MCP server.
    input_schema:
      type: object
      properties:
        repository: {type: string}
      required: [repository]
      additionalProperties: false
    estimate:
      resources:
        monetary_usd: 0.001
        latency_ms: 350
        context_tokens: 900
        network_bytes: 12000
      success_probability: 0.99
      quality_score: 0.99
      risk_score: 0.03
    side_effect: read
    locality: internet
    requires_network: true
    data_residency: [US]
    config:
      transport: stdio
      command: github-mcp-server
      args: [stdio]
      tool: get_current_branch
      arguments:
        repository: "{input.repository}"
      timeout_seconds: 20

  - id: host.browser-current-branch
    capability: github.current_branch
    kind: host
    resource_pool: openai.chatgpt
    description: Use the host agent's existing browser state.
    input_schema:
      type: object
      properties:
        repository: {type: string}
      required: [repository]
      additionalProperties: false
    estimate:
      resources:
        latency_ms: 6000
        context_tokens: 3000
        subscription_units: 1
      success_probability: 0.90
      quality_score: 0.92
      risk_score: 0.08
    side_effect: read
    locality: local
    config:
      instructions: >-
        Use the already-open GitHub tab for {input.repository}. Read the current
        branch without changing page state. Return {"branch":"..."}, then call
        aeep_record_outcome with the observed model/browser usage.
```

Manifest paths are resolved relative to `aeep.yaml`. Environment variables are only expanded in explicit `env` and header fields using `${ENV:NAME}`; arbitrary expression evaluation is never used.

## Custom decision policy

A policy is not a single currency conversion. It combines normalized burdens while preserving measurements.

```yaml
policies:
  almost_out_of_context:
    weights:
      monetary: 0.10
      latency: 0.10
      compute: 0.65
      reliability: 0.10
      quality: 0.025
      risk: 0.025
    shadow_prices:
      context_token_usd: 0.00002
      input_token_usd: 0.00001
      output_token_usd: 0.00003
    constraints:
      max_context_tokens: 4000
      min_success_probability: 0.90
      max_risk_score: 0.20
```

Shadow prices are local opportunity-cost values. They let one user treat a nearly exhausted model quota as scarce while another treats unused subscription capacity as cheap. Tool developers still settle in ordinary money outside AEEP.

CLI constraints can tighten—but never weaken—manifest guardrails:

```bash
aeep route research.company \
  --input @request.json \
  --policy resource_saver \
  --max-cost-usd 0.05 \
  --max-latency-ms 5000 \
  --max-context-tokens 6000 \
  --executor-id reviewed.executor-id \
  --no-network
```

## Conservative fallback

AEEP falls back to the next feasible route after a clear failure or invalid result when policy allows it.

It does **not** automatically retry a non-idempotent action after failure/timeout unless the policy explicitly opts into that risk. A remote write can succeed even when the response is lost; replaying it may duplicate the side effect.

Side effects have two independent gates:

1. Routing policy/request `max_side_effect`.
2. Runtime `--approve` level.

Example for a reviewed write policy:

```bash
aeep run github.issue.create \
  --input @issue.json \
  --policy reviewed_writes \
  --max-side-effect write \
  --approve write
```

Executors not marked `safe_to_auto_execute` require the separate `--approve-unsafe-executor` flag. Host/delegate routes only return a plan; the host runtime remains responsible for its own approval controls.

## Calibration and counterfactual comparison

Static estimates are only cold-start priors. For safe, equivalent read-only routes, AEEP can execute alternatives **sequentially** and compare their observed cost, latency, compute use, validation result, and risk-adjusted score:

```bash
aeep benchmark text.stats \
  --input '{"text":"calibrate this action"}' \
  --confirm-all-routes \
  --max-routes 3
```

This command can incur API charges and disclose the same input to multiple providers. It therefore requires `--confirm-all-routes`, honors all hard constraints, and skips delegated and non-idempotent routes by default. It is a calibration tool, not an autonomous production fallback mechanism. Use `--executor-id` on `route` or `run` to pin execution to a reviewed route.

## Agent integration

AEEP exposes the same six operations everywhere:

1. `aeep_list_capabilities`
2. `aeep_route_action`
3. `aeep_execute_action`
4. `aeep_record_outcome`
5. `aeep_request_quotes`
6. `aeep_get_metrics`

Quote acceptance and every payment operation remain operator-only CLI/embedded APIs and are intentionally absent from model-facing schemas.

### MCP: ChatGPT/Codex, Claude, OpenClaw, and other clients

Start a local stdio server:

```bash
python -m aeep serve --transport stdio --manifest /absolute/path/aeep.yaml
```

The server permits only `read` side effects by default. An operator—not the model—can raise the runtime ceiling after reviewing the manifest:

```bash
python -m aeep serve --transport stdio \
  --manifest /absolute/path/aeep.yaml \
  --approve write
```

A model cannot self-approve a write, destructive action, financial action, or unsafe executor through MCP/function arguments. Host-level approvals should remain enabled as a second boundary.

Configure the MCP client with:

```text
command: /absolute/path/to/python
args: -m aeep serve --transport stdio --manifest /absolute/path/aeep.yaml
```

Current Codex/ChatGPT developer surfaces, Claude Code, and OpenClaw support adding stdio or Streamable HTTP MCP servers. Their UI/CLI configuration changes independently, so this repository keeps the stable server command above and points to each platform's current documentation:

- OpenAI/Codex MCP: <https://developers.openai.com/codex/mcp>
- Anthropic Claude Code MCP: <https://docs.anthropic.com/en/docs/claude-code/mcp>
- OpenClaw MCP: <https://docs.openclaw.ai/cli/mcp>

AEEP's MCP implementation speaks both the stateless `2026-07-28` revision and the legacy initialized flow. In modern mode it supports `server/discover`, per-request protocol/client metadata, `resultType`, list cache hints, required HTTP method/name/version mirrors, and validated `x-mcp-header` projection for primitive tool parameters. HTTP and stdio messages are bounded. Remote MCP URLs use the same HTTPS, host-allowlist, DNS/IP, redirect, and ambient-proxy protections as ordinary HTTP executors.

For a remote server:

```bash
export AEEP_BEARER_TOKEN='replace-with-a-long-secret'
aeep serve --transport http --host 0.0.0.0 --port 8765
```

The endpoint is `/mcp`. AEEP refuses non-loopback binding without a bearer token. Put TLS and production authentication in front of it; the built-in HTTP service is an integration starter, not a complete public multi-tenant control plane.

### Provider-native function declarations

Export tool schemas without MCP:

```bash
aeep tools export openai-responses > openai-tools.json
aeep tools export openai-chat > openai-chat-tools.json
aeep tools export anthropic > anthropic-tools.json
aeep tools export deepseek > deepseek-tools.json
aeep tools export zai > zai-tools.json
```

DeepSeek and Z.AI use OpenAI-compatible function-tool shapes; separate export names make intended integration explicit and leave room for provider-specific changes.

Execute a returned function call through plain JSON:

```bash
aeep tool-call aeep_execute_action \
  --arguments '{
    "capability":"text.stats",
    "input":{"text":"called by an agent skill"},
    "policy":"balanced"
  }'
```

This is useful for agents that can run a CLI but do not expose a local MCP client. `tool-call` also defaults to a read-only operator ceiling; approval flags belong to the trusted process invocation and are intentionally absent from model-facing tool schemas.

### Agent Skills / `SKILL.md`

A tiny BYOS skill is included at [`skills/aeep-minimal/SKILL.md`](skills/aeep-minimal/SKILL.md); the fuller reference skill remains at [`skills/aeep-router/SKILL.md`](skills/aeep-router/SKILL.md). Installation paths for Codex/ChatGPT and Claude Code are in [`docs/BYOS.md`](docs/BYOS.md).

The skill invokes `python -m aeep` rather than relying on shell-specific aliases. It can be adapted to OpenAI/Codex skills, Claude Skills, and OpenClaw skills.

## Python embedding API

```python
import asyncio

from aeep import ActionRequest, Router


async def main() -> None:
    async with Router.from_manifest("aeep.yaml") as router:
        request = ActionRequest(
            capability="text.stats",
            input={"text": "hello from Python"},
            policy="balanced",
        )

        decision = await router.route_with_discovery(request)
        print(decision.selected_executor_id)

        outcome = await router.execute(decision)
        print(outcome.output)


asyncio.run(main())
```

Executors can also be registered dynamically:

```python
from aeep import ExecutorSpec

router.register(ExecutorSpec.model_validate(spec_dict))
```

For work executed outside built-in adapters, use `ActionProfiler`. Use a delegate plus `record_external_outcome` only for the selected delegated route represented by that decision; each decision/executor pair accepts one final external report:

```python
from aeep.models import ExecutorKind
from aeep.profiler import ActionProfiler

with ActionProfiler(
    store=router.store,
    capability="browser.read_price",
    executor_id="host.browser",
    executor_kind=ExecutorKind.HOST,
) as profile:
    value = host_agent_reads_page()
    profile.add_tokens(input_tokens=1200, output_tokens=90)
    profile.add_cost(0.012)
    profile.succeed(output_valid=True)
```

## CLI reference

```text
aeep init                 create a runnable manifest
aeep doctor               validate manifest/database/integrations
aeep list                 list capabilities and executors
aeep policies             show effective policies
aeep metrics              aggregate savings and conserved subscription capacity
aeep route                rank without execution
aeep run                  route + execute + validate + persist
aeep quote                request expiring provider quotes
aeep accept-quote         operator-only quote acceptance
aeep reserve-payment      budget and financial-approval gated reservation
aeep capture-payment      capture after validated delivery
aeep refund-payment       refund a prior capture
aeep benchmark            sequentially calibrate feasible alternatives
aeep counterfactual       compare an observed action with feasible alternatives
aeep reputation           aggregate measured/verified provider outcomes
aeep history              list decisions or receipts
aeep show                 fetch one decision/receipt
aeep record               report delegated execution outcome
aeep tool-call            invoke one AEEP agent tool over JSON
aeep tools export         emit provider-native tool declarations
aeep import               build descriptors from CLI, MCP, or OpenAPI
aeep publish              generate a local provider descriptor
aeep serve                run stdio or HTTP MCP server
```

Inputs accept inline JSON, `@file.json`, `@file.yaml`, or `-` for stdin.

```bash
cat action.json | aeep run text.stats --input - --compact
```

Exit codes:

- `0`: completed successfully.
- `1`: validation/doctor/not-found result.
- `2`: configuration, approval, or protocol error.
- `3`: route decision had no feasible executor.
- `4`: execution/tool call completed but failed.

## Security model

The repository includes conservative defaults, but a router is an execution control plane and must be treated accordingly.

Implemented protections include:

- Commands are argv arrays; `shell: true` is rejected.
- Minimal subprocess environment by default.
- Explicit environment interpolation only.
- Command timeouts, process-group termination, and bounded stdout/stderr capture.
- HTTPS required for non-local HTTP by default.
- Private/reserved HTTP destinations blocked unless explicitly reviewed.
- Optional HTTP host allowlists and bounded response size.
- The same network policy and message bounds for Streamable HTTP MCP clients.
- Redirects and ambient HTTP proxy inheritance off by default.
- JSON Schema validation on inputs and outputs.
- Network, residency, data sensitivity, resource, reliability, and side-effect gates.
- Separate operator-controlled runtime side-effect and unsafe-executor approvals; model tool arguments cannot elevate them.
- No automatic fallback for non-idempotent actions by default.
- Action input/context are redacted in stored decisions by default.
- Output previews are not persisted unless explicitly enabled.
- Non-loopback HTTP MCP serving requires a bearer token.

Read [`SECURITY.md`](SECURITY.md) before production use.

Important limitations:

- A manifest is trusted code/configuration. A Python callable can do anything the process account can do.
- An in-process Python timeout cannot forcibly stop a worker thread; use a command/container boundary for untrusted or side-effecting work.
- DNS rebinding, egress control, container isolation, OAuth, secret vaulting, policy distribution, and multi-tenant sandboxing require infrastructure outside this starter.
- A delegated browser route is advisory until the host reports its outcome; AEEP cannot enforce a different agent runtime's permissions.
- Static estimates are cold-start priors. Routing improves only when real outcomes are reported. Untrusted or fabricated outcome reports can poison local history, so protect write access to the store/server.
- `benchmark` deliberately executes multiple alternatives and may incur charges or disclose data to several providers; use it only for explicit calibration.
- The built-in HTTP MCP app must sit behind an ingress/reverse proxy that enforces request-body limits, Origin policy, TLS, authentication, and rate limits for public deployment.
- MCP multi-round `input_required` results are rejected in `0.1`; the host must complete elicitation/sampling outside AEEP or expose a single-round tool contract.
- Automatic semantic equivalence between arbitrary tools is not solved. Capabilities and schemas are explicit contracts reviewed by the operator.

## Why no universal "agent token"

AEEP deliberately does not collapse every resource into one public token:

- Model input, cached input, reasoning, and output have different costs.
- A subscription user's marginal quota value differs from an API customer's cash rate.
- Local CPU/GPU, browser runtime, data egress, and latency matter independently.
- A transferable redeemable credit creates payment/regulatory concerns unrelated to routing.

Instead, AEEP standardizes raw measurements and offers private policy weights and shadow prices. A future marketplace can quote ordinary money or closed-loop credits without changing the routing protocol.

## What remains outside the OSS `0.2` package

- Hosted buyer/provider accounts, custody, payouts, fraud systems, and public marketplace operations.
- Rail-specific x402/MPP network credentials and settlement logic; callback adapters are provided.
- Automatic semantic matching of unrelated tool schemas.
- A hosted arbitrary-code execution platform.
- Centralized reputation aggregation or global PKI; local measured reputation and explicit trust/attestation schemas are provided.
- A guarantee that a provider's declared estimate is truthful.

The repository is structured so these can be separate adapters/services rather than hard-coded into the open protocol.

## Repository layout

```text
src/aeep/
├── models.py              protocol/runtime objects
├── policy.py              built-in and custom policies
├── scoring.py             feasibility + explainable ranking
├── estimator.py           static/history blending
├── router.py              selection, execution, benchmark, fallback, receipts
├── store.py               redacted SQLite persistence
├── profiler.py            external action profiling
├── discovery.py           local/remote provider discovery
├── economics.py           quotes and signing
├── payments.py            budgets and payment adapters
├── sdk.py                 provider decorator/import/publish helpers
├── validators.py          schema/task/quality validation
├── executors/
│   ├── python.py
│   ├── command.py
│   ├── http.py
│   ├── mcp.py
│   ├── host.py
│   └── delegate.py
├── mcp/
│   ├── client.py          stdio + HTTP, modern + legacy
│   └── server.py          six AEEP tools
├── integrations/
│   └── tool_schemas.py    OpenAI/Anthropic/DeepSeek/Z.AI/MCP exports
└── cli.py
```

The protocol objects and state machine are described in [`SPEC.md`](SPEC.md). Design trade-offs are in [`ARCHITECTURE.md`](ARCHITECTURE.md), security guidance in [`SECURITY.md`](SECURITY.md), and host-specific setup in [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md).

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,http-server]'
PYTHONPATH=src python scripts/generate_schemas.py --check
pytest
coverage run -m pytest
coverage report -m
python -m build
```

The test suite includes real subprocess command execution and a real stdio MCP round trip.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
