# Fixed local website task service

[Documentation index](../../docs/README.md) · [Scoped task operations](../../docs/ASSESSMENT.md#project-local-task-operation).

This operator-owned example completes two fixed HTML edits and verifies their
files independently in a fresh CLI or MCP process. It reuses `AEEPToolService`,
reviewed task scopes, the native single-process command boundary, durable
attempts and receipts, and the existing callback validator. It adds no core API
or callback importer.

The fixture is synthetic. It does not establish arbitrary website support,
browser rendering, live model competence, publishing readiness, qualification,
resource acceptance, or benefit. Publishing is absent from the tool profile.
The supported execution backend is non-root macOS with the pinned installed
Codex and Python executables. No authentication setup is performed here.

Run from a checkout with `PYTHONPATH=src`. Prepare only a new directory that you own:

```bash
python3 examples/native_website/task_service.py prepare \
  --root /absolute/new/website-fixture \
  --codex /absolute/installed/codex \
  --python /absolute/installed/python3
```

Preparation returns an inert task scope and recipe digest. Review the exact
manifest, module and oracle hashes before using the existing operator controls:

```bash
python3 -m aeep assess -m /absolute/new/website-fixture/aeep.json review RECIPE_DIGEST
python3 -m aeep assess -m /absolute/new/website-fixture/aeep.json review SCOPE_DIGEST
python3 -m aeep task -m /absolute/new/website-fixture/aeep.json activate website-build-edit
```

Use the returned activation ID to run a fresh process:

```bash
python3 examples/native_website/task_service.py call \
  --manifest /absolute/new/website-fixture/aeep.json --activation ACTIVATION_ID build
```

Before the later edit, create `data/later-note.txt` containing exactly
`Added after build; keep.` followed by a newline. This fixture checks that a
user file added between stages survives. Run the same command with `edit`.
The output contains ordinary task receipts and independent callback checks.
The oracle and state remain outside the child's allowed data root.

For an operator-configured stdio MCP process, use the `mcp` subcommand with the
same manifest and activation arguments. It delegates messages to the existing
`MCPProtocolApp` and exposes only the reviewed recipe task tool. This composition
is a separate entry point: the generic `aeep serve` command does not register
this example's callback. The example does not alter the generated project MCP
launcher or user/global configuration.

Module or oracle drift rejects startup and is rechecked during validation.
A command that reports success must still pass file verification. The fixed
callback accepts only the exact HTML, stylesheet and notes; it never imports
another callback. Use the existing `aeep task control` commands to inspect,
pause, resume, roll back or uninstall the activation. Uninstall removes the
owned overlay and retains task files, receipts and the consumed allowance.
Remove the owned fixture directory only after preserving any evidence you need.
