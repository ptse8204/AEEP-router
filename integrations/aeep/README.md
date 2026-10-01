# AEEP Codex plugin

Install the AEEP Python package, then make an operator manifest available through
the existing project `aeep.yaml` lookup or `~/.config/aeep/config.yaml`. The local
MCP server runs `aeep serve --transport stdio --profile assessment`.
For an initialized assessment workspace, set the MCP process's `AEEP_MANIFEST`
environment variable to the absolute path of its `aeep.json`, or add
`--manifest /absolute/path/to/aeep.json` to the server's locally configured args.

The plugin includes three task tools, onboarding instructions, and bounded tools
to start, inspect, report on and cancel assessments. Reviewed declarative recipe
definitions add task tools to this profile. `--profile legacy` retains the existing exports.

The plugin selects implementations behind its own tools. It does not replace
unrelated Codex tools or provide access to Codex authentication state. See
[the assessment guide](../../docs/ASSESSMENT.md) for the supported local assessment
path. Live Codex assessment remains a separate release gate. Local container boundaries
and crash recovery have explicit opt-in release tests.
