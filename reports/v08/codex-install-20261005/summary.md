# Codex installation and README delivery — October 5, 2026

AEEP is installed as `aeep@aeep-router`, using the repository marketplace and a
dedicated Python runtime at `~/.local/share/aeep/venv`. Its default manifest is
`~/.config/aeep/config.yaml`. The installed stdio server exposed 15 tools and
successfully ran `text.stats` on `hello world`: 11 characters, 2 words, 1 line,
and a successful verified receipt. Both modern and legacy MCP discovery passed.

The README includes marketplace installation, conversational examples, update
commands, and an actual 27-second terminal recording with a GIF preview, MP4 and
text transcript. The video shows local execution and synthetic stack fixtures.
It does not establish provider onboarding, paid execution or comparative value.

The `update-aeep-router` Codex automation is active daily at 09:00 Vancouver time.
It updates only a clean, fast-forwardable main checkout, validates changes,
updates the dedicated runtime and marketplace, and preserves operator state.
It requires the Codex scheduler to be available and reports meaningful updates
or failures. Restart Codex after installation or an update to load the server.

Both plain and coverage runs passed 1,267 tests with 21 skipped and one existing
Starlette/httpx deprecation warning. Coverage is 82.08%; both required branch
coverage gates passed. Exact commands and results are recorded in `checks.json`. Compile, generated schemas, Ruff, mypy,
assessment policy and strict router verification passed. Package builds passed;
exact artifacts are in `packaging.json`. Source hashes are in `source-index.json`.

A direct standalone App Server inventory attempt encountered the existing
embedded `node_repl` transport configuration. No unrelated settings were changed.
The supported plugin command lists AEEP as enabled; installed-cache server startup
and tool execution passed independently. The current desktop chat still needs
its normal plugin reload/restart.

See `installation.json` for the explicit implementation review, exact plugin
fingerprints, resources and recording provenance. Historical skill fingerprints
remain in the recursion guard alongside the new bundled-skill fingerprint.
No credential files, grants or existing manifests were replaced. No Docker
operations, paid calls, provider setup, model assessments or cleanup were run.

The published GitHub marketplace was installed and refreshed successfully. Its
cache matches the published plugin files, and MCP startup passed again. See
`published-installation.json`. The daily updater compares origin/main with the
installed-runtime revision, including when the development checkout is already
current. The README, marketplace catalog, GIF and MP4 each returned HTTP 200.
