# Agent integration guide

[Documentation index](README.md).

For a new host connection, start with [guided setup](ONBOARDING.md#start).
This guide is for developers configuring a manual MCP connection, native dispatch
or an application's model/tool loop. Install AEEP first and review the manifest
before enabling execution.

The exposed tools depend on the selected legacy, assessment or task profile,
configured discovery and connection allowlist. Named connections start with
planning and search access; the list below describes the ten legacy routing and
economic operations retained from 0.7, not every tool in 0.8. The MCP endpoint
supports stateless `2026-07-28` clients and legacy initialized clients.
Applications that manage their own model/tool loop can use provider-native schemas:

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

The same routing contract applies across agent hosts. Each host manages its sandbox and approval UI; AEEP separately enforces manifest constraints and the execution ceiling configured by the operator.

Use [per-agent controls](ONBOARDING.md#control-tools-per-agent) for named
connections, [project-local task operation](ASSESSMENT.md#project-local-task-operation)
for scoped execution, and [native-control compatibility](#native-control-compatibility)
for the limits of host filtering. A ready server does not establish isolation.

<details>
<summary>Contents</summary>

- [Preferred host-native dispatch](#preferred-host-native-dispatch)
- [Start a local MCP server](#start-a-local-mcp-server)
- [ChatGPT desktop and Codex](#chatgpt-desktop-and-codex)
- [Native-control compatibility](#native-control-compatibility)
- [Discovery, intake and local evidence lookup](#discovery-intake-and-local-evidence-lookup)
- [Claude Code](#claude-code)
- [OpenClaw](#openclaw)
- [OpenAI Responses API](#openai-responses-api)
- [Anthropic Messages API](#anthropic-messages-api)
- [DeepSeek](#deepseek)
- [Z.AI / GLM](#zai--glm)
- [Agent skills](#agent-skills)
- [Stack service integration](#stack-service-integration)

</details>

## Preferred host-native dispatch

Once the host has classified an action, call AEEP with the bounded
`ActionRequest`. AEEP can select a local implementation deterministically without
a model call. When the action needs model judgment, native Tool Search or the
host planner chooses the semantic capability first. AEEP then selects a reviewed
implementation and starts at most one managed-host execution turn. Implementation
routes and the full AEEP control schema stay outside model input unless the
selected host explicitly needs a canonical source tool.

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

For a reviewed `host_managed` route, start from
`examples/subscriptions/openai-codex-app-server.yaml`, replace the absolute Codex
executable path, and use the operator diagnostics before routing:

```bash
aeep hosts codex doctor --manifest aeep.yaml --json
aeep hosts codex account --manifest aeep.yaml --json
aeep hosts codex models --manifest aeep.yaml --json
aeep hosts codex quota --manifest aeep.yaml --json
```

These diagnostics perform no model turn. `aeep hosts codex login` is the sole
interactive login entry point and is intentionally not a model tool. Codex owns
the authentication state; AEEP receives only redacted account observations and
does not read Codex credential files.

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

The managed subscription adapter uses the official Codex App Server protocol,
not MCP, for Codex-owned authentication, runtime model/quota discovery, and one
bounded turn. Official reference: <https://learn.chatgpt.com/docs/app-server>

## Native-control compatibility

The task-scoped profile in `aeep.profiles` currently enforces AEEP task-service
schema exposure and calls. It does not apply the wider Codex controls below to
the user's running host. `profile-compile` and `profile-preflight` expose this
limit and reject strict whole-host isolation, native artifact exclusion or
requested model/effort changes. The matrix also describes the existing separate
managed-host invocation adapter; its capabilities must not be attributed to the
new task profile.

For an execution-local assessment composition, export a profile with
`host: "task-service"`, store it with `task define-profile`, and review its exact
digest. `aeep.profiles.bind_service(router, profile_id)` returns an activation and
the ordinary task service without installing a Codex project entry. The caller
owns teardown through the same task controls. A fixed-helper control can receive
that reviewed activation through `FixedHelperService(..., task_activation=...)`.
Its existing campaign reservation and fixed dispatch still apply.

Before reviewing a dynamic callback binding, set its operator-owned identity's
`capability_profile_behavior_digest` from
`CodexDynamicTools.profile_behavior(service)`. Construction and callbacks check
that pin, the exact profile review and the current activation. Fresh execution
scope IDs do not replace behavior evidence or reset used allowances. Existing
unprofiled campaign definitions retain their original contract; no historical
result is promoted by this integration.

`aeep task --manifest MANIFEST profile-capture PROFILE --activation ACTIVATION
--receipt RECEIPT` saves a content-free configuration observation. Repeat
`--receipt` for up to 100 selected, exactly scoped receipts. Compiled schema
bytes, requested permission, observed invocation, task verification and measured
resources remain separate. This is not a complete host-use census or a measure
of comparative benefit.

`aeep assess --manifest MANIFEST skillsbench-definition` exports the pinned
offer-letter adaptation and its contained generator/reference/grader definition.
Bundled inputs work in installed packages; `--asset-root PATH` additionally
checks an existing pinned upstream copy. The definition has seven variations of
one template, balanced 8/28/105 generation, and explicit Yes/No relocation
semantics. It requires the existing review, protected grader validation and
materialization steps before any trial. It is not an official SkillsBench score.

Research date: October 2, 2026. The local `codex --version` command returned
`codex-cli 0.154.0`. This observes the executable version only. The official
documentation below is a dated documentation snapshot, not a claim that every
method was exercised on this binary. No host configuration, sign-in state or
plugin installation was changed during this inspection.

| Source/interface | Version and scope | Documented behavior | AEEP implementation and limits | Fallback |
|---|---|---|---|---|
| ARD `POST /search` | v0.91, exact [ADR-010 pin](adr/ADR-010-ard-discovery-boundary.md) | Entry discovery with optional filters and federation | Bounded client subset; candidates remain inert; no upstream conformance observation | Explicit local fixture or manual intake |
| Codex `mcp_servers.<id>.enabled`, `enabled_tools`, `disabled_tools` | Docs reviewed against local 0.154.0; process/configuration scope | Server enablement, tool allowlist, then denylist | `hosts/codex_invocation.py` compiles selected server/tool overrides and compares thread inventory; catalog agreement alone cannot prove process containment | Reject unsupported strict use |
| Codex `skills.config` | Same version record; skill folder path | Per-skill enablement | Exact skill content and dependencies are checked before invocation; disabling does not delete files or erase loaded instructions | Fresh reviewed context and independent filesystem boundary |
| Codex project and plugin controls | Same version record; trusted project/configuration layers | Plugin-scoped MCP enablement, allow/deny lists and approval modes | Compiler targets `plugins.<plugin>.mcp_servers.<server>`; it does not install or uninstall plugins | Operator configuration outside the model toolset |
| App Server `skills/config/write` | Documentation snapshot; path scope | Enable or disable a skill | No production dependency on mutating a shared user's skill configuration | Invocation-local overrides |
| App Server `config/mcpServer/reload` | Documentation snapshot; loaded threads | Reload configuration and queue refresh | Acknowledgement cannot establish immediate revocation or context erasure; not used as an AEEP authority barrier | Revoke AEEP authority before cleanup; fresh process/context |
| App Server `config/read` | Documentation snapshot; layered on-disk state | Resolve effective stored configuration | Existing worker inspection reads selected policy facts; requested state alone is insufficient | Stop when effective state cannot be established |
| App Server `mcpServerStatus/list`, `skills/list`, `app/installed` | Documentation snapshot; thread/inventory scope | Inspect MCP inventory, skills and callable app state | Existing invocation/inspection code bounds pagination and omits authentication details from retained inventory; no fresh enforcement observation in this build | Fail closed on incomplete or conflicting inventory |
| App Server `plugin/list`, `plugin/read`, `plugin/install`, `plugin/uninstall` | Documentation snapshot | Under development; production clients should not call them | Excluded from production dependencies | Reviewed native configuration and inert local intake |

Configuration semantics come from the official
[configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
Method descriptions and the plugin-method restriction come from the official
[App Server reference](https://learn.chatgpt.com/docs/app-server).
These sources provide interface documentation, not AEEP qualification evidence.

Codex applies layered configuration and administrator requirements. CLI overrides
have highest configuration precedence, but cannot override enforced requirements.
Project configuration loads only for trusted projects. AEEP must preserve user
and administrator policy when compiling its narrower controls. See
[configuration precedence](https://learn.chatgpt.com/docs/config-file/config-basic).

Record support separately for catalog filtering, schema exposure, skill/file
exclusion, dispatch enforcement, filesystem/network isolation, credential scope,
hooks, fresh context and resource observation. A tool filter controls only its
own call surface. General-purpose shell access, aliases, other servers, readable
package files or existing conversation history can defeat stronger exclusion
claims. AEEP's strict profiles must reject those unresolved boundaries.

### Other OpenAI runtimes

The Responses API has three distinct controls. MCP `allowed_tools` narrows
imported server tools; function `tool_choice` restrictions constrain eligible
calls among supplied definitions; `tool_search` with `defer_loading` postpones
definition loading while leaving discovery possible. None establishes candidate
artifact absence. See the official [MCP guide](https://developers.openai.com/api/docs/guides/tools-connectors-mcp),
[function calling guide](https://developers.openai.com/api/docs/guides/function-calling)
and [tool search guide](https://developers.openai.com/api/docs/guides/tools-tool-search).
Responses adapters remain optional and separately authorized; configuring them
must not replace subscription execution with paid API calls.

The [Agents SDK integration guide](https://developers.openai.com/api/docs/guides/agents/integrations-observability)
places local/private MCP connection ownership in the SDK application's runtime.
The steering plan names `MCPServerManager` and static/dynamic `tool_filter` as
possible connection/exposure helpers. Their exact Python SDK version and method
contracts have not been verified in this checkout, so AEEP does not depend on
them. Any later adapter must pin and inspect those interfaces before use. Such
helpers would not evaluate plugin value or control an existing Codex/ChatGPT
session. No externally callable ChatGPT internal plugin manager is assumed.

### Cloud deployment boundary

The provider-neutral discovery, intake, evidence and routing code can be
developed and packaged on Linux. Deployment still needs a reviewed executor and
an operator-owned durable store. The native task backend in
`hosts/codex_sandbox.py` and `hosts/codex_native_process.py` explicitly requires
macOS. Its evidence and profiles cannot be transferred to a Linux cloud host by
changing paths or copying the database.

A cloud Linux VM is a possible home for the existing container-worker design,
provided its operator supplies the reviewed runtime, isolated workers, persistent
ledger and permitted model connection. This is an architecture fit, not a tested
deployment. A complete cloud-only replacement of the current Mac callback path
requires an implemented Linux execution boundary and fresh applicable evidence.
Mac production acceptance must still be measured on the Mac target.

The current official [cloud environments guide](https://learn.chatgpt.com/docs/environments/cloud-environments)
describes Codex cloud configuration. The earlier singular
[cloud-environment page](https://learn.chatgpt.com/docs/environments/cloud-environment)
now documents legacy Code Review, Linear and GitHub environments. Neither page
establishes availability of AEEP's required nested container boundary, protected
sign-in arrangement or durable campaign storage for this account. Those remain
deployment prerequisites. AEEP must not copy Codex authentication state, reset
grant counters or assume cloud storage is a sandbox for trial tools.

No cloud service was provisioned or benchmark run for this implementation
increment. The [coverage record](../reports/v08/plan-coverage.md) tracks the
implementation and outstanding evidence separately.

## Discovery, intake and local evidence lookup

Search uses ARD by default and requires an explicit endpoint. Supply a public
capability phrase, never a private task description. The endpoint below is a
placeholder to replace with an operator-approved registry:

```bash
aeep registry search "document editing" --base-url https://registry.example.org --envelope --manifest aeep.yaml
aeep registry search "document editing" --registry fixture --fixture candidates.json --envelope --manifest aeep.yaml
aeep registry show-discovery DISCOVERY_ID --manifest aeep.yaml
aeep candidate intake CANDIDATE_ID /absolute/path/to/reviewed-skill --kind skill --manifest aeep.yaml
aeep evidence lookup CANDIDATE_ID --intake INTAKE_ID --request @action.json --manifest aeep.yaml
```

`--envelope` returns durable source/result references, timing and unknown costs.
The candidate list remains the default output. Intake inspects only the explicit
local artifact; it never follows a discovery URL or installs code. `--mapping`
can name a reviewed-mapping JSON file. Intake and mapping definitions require
their own exact reviews through `aeep assess review`; creation does not review
them. Lookup returns conditional evidence, reasons and a next action. It performs
no assessment or execution, and ordinary execution rechecks authority.

An operator can make bounded discovery available to a non-task service with
`aeep serve --discovery-config discovery.json --manifest aeep.yaml`. A minimal
offline configuration is:

```json
{
  "schema_version": "discovery.config.v1",
  "sources": [{"source_id": "local", "kind": "fixture", "path": "candidates.json"}],
  "max_results": 20,
  "timeout_seconds": 10
}
```

For ARD, a source uses `kind: "ard"`, `base_url`, and explicit
`allow_remote: true`; it may also name `artifact_types` and a local
`fallback_path`. Model arguments cannot add sources, grant network disclosure or
raise these ceilings. The configured service exposes `aeep_discover_resources`;
`aeep_lookup_capability` reads local evidence. The task-only profile exposes
neither preparation tool.

For an existing task scope, use `aeep task --manifest aeep.yaml profile-from-scope SCOPE_ID --profile-id PROFILE_ID` to export an inert
profile, `define-profile` to save it, and `profile-compile`, `profile-diff` or
`profile-preflight` to inspect it. Review the exact returned profile digest using
`aeep assess --manifest aeep.yaml review DIGEST` before `activate-profile`. Activation
retains the scope's durable allowances and review requirements. `profile-inspect`
reports intended configuration separately from observed use; missing host
exposure or installation evidence stays unknown.

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

## Agent skills

Copy `skills/aeep-router` from the repository into the host's supported skills
directory. The included [SKILL.md](../skills/aeep-router/SKILL.md) teaches the agent to:

1. list or route before executing when alternatives are unclear;
2. pass current quota and resource pressure in `context.compute`;
3. never self-approve writes or unsafe executors;
4. report the selected delegated browser/computer-use outcome exactly once;
5. use `benchmark` only during explicit calibration.

The skill uses `python -m aeep` and JSON output, so it does not depend on shell aliases or prose scraping.

## Stack service integration

Use `aeep.stack_planning.StackService` for inert planning and
`aeep.stack_runtime.StackRuntime` for operator-controlled execution. The host
supplies semantic graphs, separately retains actual task values and presents
preflight's consolidated setup and review requirements. Shared preparation schemas
are exported for MCP and supported provider formats. The optional
`tools.stack-task.mcp.json` includes execution; existing task schemas stay unchanged.

Enable `stack_execution` explicitly in a reviewed capability profile (or generate
it with `aeep task profile-from-scope --stack-execution`). Activation still requires
an applicable native scope. A host-managed setup adapter needs an explicitly
versioned trusted callback; inject its `ProviderSetupService` into `StackService`.
Unsupported callbacks are blockers. [The stack guide](STACK_PLANNING.md) provides
CLI examples and recovery constraints.
