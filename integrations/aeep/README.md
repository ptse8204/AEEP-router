# AEEP Codex plugin

For a new source checkout, use [guided setup](../../docs/ONBOARDING.md#start).
It registers that environment's interpreter and a named connection directly.
This directory instead contains the `aeep-router` marketplace plugin's fixed
launcher for an operator-installed dedicated runtime. The plugin starts the existing
stdio MCP server through `serve.py`, using the dedicated runtime at
`~/.local/share/aeep/venv` and the operator manifest at
`~/.config/aeep/config.yaml`. Missing setup stops startup with a diagnostic on
stderr. Startup never installs dependencies or updates code.

An editable source installation alone does not create those dedicated paths.
The [local installer build](../../docs/ONBOARDING.md#release-preparation-and-verification)
documents that runtime. The public download command remains withheld pending
published, verified assets. See [integration guidance](../../docs/INTEGRATIONS.md)
for a manual connection using an existing interpreter and manifest.

The default profile exposes ordinary routing, receipts and inert stack planning.
It does not intercept unrelated Codex tools. The manifest starts with local
`text.stats`; other capabilities need operator configuration and their applicable
reviews. Assessment and scoped task profiles remain separate: see
[the integration guide](../../docs/INTEGRATIONS.md) and
[assessment guide](../../docs/ASSESSMENT.md).

Follow [update and removal guidance](../../docs/ONBOARDING.md#repair-update-and-remove)
for installer-managed runtimes. Update an editable source environment with Git
and pip separately; refreshing a marketplace updates neither Python nor its
dependencies. Bump the plugin manifest version when changing bundled behavior;
refreshing a marketplace does not itself install Python dependencies. Reopen Codex
after an update. Do not edit installed cache files or replace existing manifests,
receipts, approvals or credentials.

[Documentation index](../../docs/README.md).
