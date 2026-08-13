# Bring Your Own Subscription

AEEP treats ChatGPT/Codex, Claude/Claude Code, local models, MCP servers, and local software as resources the user already owns. It never extracts consumer credentials or converts subscription capacity into currency.

## Codex or ChatGPT

1. Install AEEP with `pip install -e .`.
2. Install `skills/aeep-minimal` in the host's supported skills directory.
3. Configure the AEEP MCP server with `aeep serve --transport stdio`, or use `aeep route` and `aeep run` from the skill.
4. Add a `subscription` resource and `host` executor to `aeep.yaml`.

## Claude Code

1. Sign Claude Code into the user's existing Claude subscription.
2. Install AEEP locally with `pip install -e .`.
3. Register `aeep serve --transport stdio` as an MCP server, or use the CLI from the minimal skill.
4. Configure Claude as a host subscription resource; no Anthropic API key is required.

## Quota signals

Set quota state from user declarations, official host metadata, official CLI output, rate-limit responses, or conservative heuristics. Do not scrape undocumented billing dashboards. `subscription_units` and quota pressure remain provider-local, private routing signals—not cash or transferable credits.
