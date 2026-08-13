# Bring Your Own Subscription

AEEP treats ChatGPT/Codex, Claude/Claude Code, local models, MCP servers, and local software as resources the user already owns. It never extracts consumer credentials or converts subscription capacity into currency.

## Codex or ChatGPT

1. Install AEEP with `pip install aeep-agent-router` (or `pip install -e .` from source).
2. Run `aeep skill install codex`.
3. Configure the AEEP MCP server with `aeep serve --transport stdio`, or use `aeep route` and `aeep run` from the skill.
4. Add a `subscription` resource and `host` executor to `aeep.yaml`.

## Claude Code

1. Sign Claude Code into the user's existing Claude subscription.
2. Install AEEP locally and run `aeep skill install claude`.
3. Register `aeep serve --transport stdio` as an MCP server, or use the CLI from the installed skill.
4. Configure Claude as a host subscription resource; no Anthropic API key is required.

## Quota signals

Set quota state from user declarations, official host metadata, official CLI output, rate-limit responses, or conservative heuristics. Do not scrape undocumented billing dashboards. `subscription_units` and quota pressure remain provider-local, private routing signals—not cash or transferable credits.

```bash
aeep subscriptions add claude-max --provider anthropic --product claude-max --state normal
aeep subscriptions status
aeep quota observe claude-max tight --source rate_limit
aeep quota observe claude-max abundant --source official_cli --reset-at 2026-08-13T08:00:00Z
```

Host outcome reports can include `--quota-state` and `--quota-reset-at`; AEEP applies that observation only to the selected host resource.
