# AEEP Codex plugin

Install from the `aeep-router` repository marketplace with the commands in
[the main README](../../README.md#install-in-codex). The plugin starts the existing
stdio MCP server through `serve.py`, using the dedicated runtime at
`~/.local/share/aeep/venv` and the operator manifest at
`~/.config/aeep/config.yaml`. Missing setup stops startup with a diagnostic on
stderr. Startup never installs dependencies or updates code.

The default profile exposes ordinary routing, receipts and inert stack planning.
It does not intercept unrelated Codex tools. The manifest starts with local
`text.stats`; other capabilities need operator configuration and their applicable
reviews. Assessment and scoped task profiles remain separate: see
[the integration guide](../../docs/INTEGRATIONS.md) and
[assessment guide](../../docs/ASSESSMENT.md).

Update both the Python runtime and the marketplace using the main README's
commands. Bump the plugin manifest version when changing bundled plugin files;
refreshing a marketplace does not itself install Python dependencies. Reopen Codex
after an update. Do not edit installed cache files or replace existing manifests,
receipts, approvals or credentials.
