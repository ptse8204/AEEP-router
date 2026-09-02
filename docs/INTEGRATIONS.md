# Agent integration guide

AEEP 0.6 exposes the same ten operations across MCP, provider-native function tools, and a plain JSON CLI. The MCP endpoint supports stateless `2026-07-28` clients and legacy initialized clients; provider-native schemas remain useful where the application owns the model/tool loop:

- `aeep_list_capabilities`
- `aeep_route_action`
- `aeep_execute_action`
- `aeep_record_outcome`
- `aeep_estimate_route_prices`
- `aeep_request_quotes` (deprecated alias)
- `aeep_get_metrics`
- `aeep_show_prepared_decision`
- `aeep_show_quote`
- `aeep_show_settlement`

The three economic inspection tools read already-persisted, sanitized records. They do not contact providers, prepare or execute routes, reserve or settle funds, reconcile billing, mutate trust, recover attempts, activate routes, or run benchmarks. `aeep_estimate_route_prices` and its legacy `aeep_request_quotes` alias are local, non-binding estimate lookups; neither invokes the remote quote client.

Financial acceptance, reservations, captures, releases, refunds, and reconciliation are operator-only and are not model tools. Raw action input, output, credentials, and external billing references are not returned by the economic inspection tools.

This keeps the routing contract stable even when an agent host changes. The host remains responsible for its own sandbox and approval UI; AEEP independently enforces manifest constraints and its operator-configured execution ceiling.

## Preferred host-native dispatch

For an exact action already classified by the host, call AEEP directly with the
bounded `ActionRequest`; a deterministic local winner requires no model call. If
model judgment is required, native Tool Search or the host planner first chooses
the semantic capability, then AEEP selects the reviewed implementation and starts
at most one managed-host execution turn. Implementation routes and the full AEEP
control schema stay outside model input unless the selected host explicitly needs
a canonical source tool.

MCP and provider-native function exports remain supported compatibility surfaces.
Putting `aeep_route_action` in a separate model-facing meta-router round is the
documented negative control, not the default integration. The offline campaign in
`reports/v07/host-native-routing.json` records model turns, tool-selection rounds,
implementation-schema bytes, and result bytes for the tested exact-local and
bounded-model action classes; it makes no universal token-savings claim.

For DeepSeek Harness, prefer `integrations/dsh-aeep-router/`. That Cordis plugin
accepts an exact `/aeep` capability envelope and routes it before the model call
through one persistent, bounded JSONL `aeep host-bridge`. The model sees only
the configured canonical tool; AEEP and hidden implementation schemas are not
model input. A rejected preflight makes no model call, and a bridge failure
during a routed action fails that action closed. Ordinary model routing may keep
its operator baseline. Installation into a running Harness and any live
campaign are separate operator-approved steps.

## Start a local MCP server

Use an absolute interpreter and manifest path so GUI applications do not depend on a shell's working directory or `PATH`:

```bash
/absolute/path/to/.venv/bin/python -m aeep serve \
  --transport stdio \
  --manifest /absolute/path/to/aeep.yaml
```

The server is read-only by default. An operator can raise the ceiling only after reviewing the manifest:

```bash
/absolute/path/to/.venv/bin/python -m aeep serve \
  --transport stdio \
  --manifest /absolute/path/to/aeep.yaml \
  --approve write
```

A model cannot elevate that ceiling through tool arguments.

## ChatGPT desktop and Codex

Current Codex hosts support local stdio and remote Streamable HTTP MCP servers. Add the local server from the UI, or use the CLI:

```bash
codex mcp add aeep -- \
  /absolute/path/to/.venv/bin/python -m aeep serve \
  --transport stdio \
  --manifest /absolute/path/to/aeep.yaml
```

Equivalent `~/.codex/config.toml`:

```toml
[mcp_servers.aeep]
command = "/absolute/path/to/.venv/bin/python"
args = [
  "-m", "aeep", "serve",
  "--transport", "stdio",
  "--manifest", "/absolute/path/to/aeep.yaml",
]
default_tools_approval_mode = "writes"
```

Keep the Codex/ChatGPT host approval mode enabled even though AEEP has its own controls. The two layers address different risks.

Official reference: <https://developers.openai.com/codex/mcp>

## Claude Code

Project `.mcp.json`:

```json
{
  "mcpServers": {
    "aeep": {
      "type": "stdio",
      "command": "/absolute/path/to/.venv/bin/python",
      "args": [
        "-m", "aeep", "serve",
        "--transport", "stdio",
        "--manifest", "/absolute/path/to/aeep.yaml"
      ]
    }
  }
}
```

Claude Code also supports remote HTTP MCP servers and its own per-tool permission rules. Keep those rules enabled; do not treat a tool call selected by the model as user approval.

Official reference: <https://docs.anthropic.com/en/docs/claude-code/mcp>

## OpenClaw

```bash
openclaw mcp add aeep \
  --command /absolute/path/to/.venv/bin/python \
  --arg -m \
  --arg aeep \
  --arg serve \
  --arg --transport \
  --arg stdio \
  --arg --manifest \
  --arg /absolute/path/to/aeep.yaml

openclaw mcp doctor aeep --probe
```

OpenClaw applies its normal tool profiles and policies to MCP tools. Connecting AEEP should not bypass those policies.

Official reference: <https://docs.openclaw.ai/cli/mcp>

## OpenAI Responses API

Generate the function declarations:

```bash
aeep tools export openai-responses > /tmp/aeep-openai-tools.json
```

When the model returns one of those function calls, pass the name and arguments to the deterministic bridge:

```bash
aeep tool-call aeep_route_action \
  --arguments '{
    "capability":"text.stats",
    "input":{"text":"hello"},
    "policy":"balanced"
  }'
```

Production applications can call `AEEPToolService` directly instead of spawning the CLI.

## Anthropic Messages API

```bash
aeep tools export anthropic > /tmp/aeep-anthropic-tools.json
```

The export uses Anthropic's `name`, `description`, and `input_schema` declaration shape. Execute returned `tool_use` blocks through `aeep tool-call` or `AEEPToolService`, then return the result as a `tool_result` block.

## DeepSeek

```bash
aeep tools export deepseek > /tmp/aeep-deepseek-tools.json
```

The export uses the OpenAI-compatible Chat Completions function-tool shape. DeepSeek chooses a function and arguments; the application still performs the call and returns the tool result. Do not expose `--approve write` to an untrusted model-generated shell command.

Official reference: <https://api-docs.deepseek.com/guides/tool_calls/>

## Z.AI / GLM

```bash
aeep tools export zai > /tmp/aeep-zai-tools.json
```

The local bridge uses the OpenAI-compatible function shape. Z.AI can also connect to remote MCP servers directly. For that mode, deploy AEEP behind HTTPS and production authentication; the built-in HTTP server is only an integration starter.

Official references:

- <https://docs.z.ai/guides/capabilities/mcp-call>
- <https://docs.z.ai/devpack/quick-start>

## Agent Skills

Copy [`../skills/aeep-router`](../skills/aeep-router) into the host's supported skills directory. The included `SKILL.md` teaches the agent to:

1. list or route before executing when alternatives are unclear;
2. pass current quota and resource pressure in `context.compute`;
3. never self-approve writes or unsafe executors;
4. report the selected delegated browser/computer-use outcome exactly once;
5. use `benchmark` only during explicit calibration.

The skill uses `python -m aeep` and JSON output, so it does not depend on shell aliases or prose scraping.
