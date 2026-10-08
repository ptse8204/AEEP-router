# Bring your own subscription

Put the subscriptions and local tools you already have to work. AEEP can take
remaining capacity into account when choosing a route, helping you reserve
scarce usage for work that needs it.

Start with [onboarding](ONBOARDING.md#start) for a host connection. Use this guide
to configure delegated or managed execution and understand its quota signals.

[Documentation index](README.md).

AEEP can route work through resources you already have: ChatGPT/Codex, Claude/Claude Code, local models, MCP servers, and local software. It never extracts consumer credentials or converts subscription capacity into currency.

## Codex or ChatGPT

1. [Install from source](ONBOARDING.md#start) with Python 3.11 or newer.
   Keep the environment available to the host.
2. Copy `examples/subscriptions/openai-codex-app-server.yaml` and replace the
   absolute Codex executable path. Keep argv as an array.
3. Run `aeep hosts codex doctor`, `account`, `models`, and `quota` against the
   manifest. These diagnostics consume no model turn and redact account identity.
4. Use the reviewed `host_managed` route when AEEP should invoke one Codex turn,
   or retain a legacy `host` route when the current agent will execute and report
   the outcome itself.

Codex owns login and credentials. AEEP never reads Codex credential files.
`aeep hosts codex login` starts the official interactive flow and is operator-only;
it is not exported as a model tool. Personal OpenAI capacity remains `SELF_ONLY`.

## Claude Code

1. Sign Claude Code into the user's existing Claude subscription.
2. Install AEEP locally and run `aeep skill install claude`.
3. Register `aeep serve --transport stdio` as an MCP server, or use the CLI from the installed skill.
4. Configure Claude as a host subscription resource; no Anthropic API key is required.

## Quota signals

Set quota state from user declarations, official host metadata, official CLI output, rate-limit responses, or conservative heuristics. Do not scrape undocumented billing dashboards. `subscription_units` and quota pressure are private routing signals in provider-local units. They are neither cash nor transferable credits.

```bash
aeep subscriptions add claude-max --provider anthropic --product claude-max --state normal
aeep subscriptions status
aeep quota observe claude-max tight --source rate_limit
aeep quota observe claude-max abundant --source official_cli --reset-at 2026-08-13T08:00:00Z
```

Host outcome reports can include `--quota-state` and `--quota-reset-at`; AEEP applies that observation only to the selected host resource.

Managed-host observations preserve every provider window. Use `aeep capacity
status RESOURCE_ID` and `aeep capacity reservations` for sanitized local state.
Unknown remaining usage is reported as unknown, never zero.
