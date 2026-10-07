# Set up AEEP and control agent access

AEEP uses your existing agent to understand the task. It searches catalog metadata,
records a comparison, and helps you configure selected components. A recommendation
can include tools you have not installed. It does not grant execution authority.

## Start

For a source checkout with AEEP installed, run `aeep setup` in your project.
Choose Codex, Claude Code, DeepSeek Harness, or an API application. Setup offers
existing marketplaces reported by the selected host and an optional repository,
HTTPS catalog URL, or local catalog directory. Review the summary once.

For an unattended configuration:

```bash
aeep setup --agent codex --agent claude --project "$PWD" --yes
aeep doctor --setup
```

The installer supports macOS and Linux/WSL on arm64 and x86_64. Windows without
WSL is not an onboarding target. It keeps 50 GiB free, uses checksum-pinned uv
0.8.22 and Python 3.12.11, and installs hashed dependencies in AEEP-owned storage.
Agent applications and sign-in remain your responsibility. No background service,
third-party plugin installation, paid call, or assessment campaign starts at setup.

Run `aeep` for the guided menu. If your shell does not include `~/.local/bin`, use
`~/.local/bin/aeep`; virtualenv activation is unnecessary. Restart connected agents
and open a new session to load the planning skill. `aeep agents launch CONNECTION`
opens the selected project; for DSH it supplies the generated Cordis MCP overlay.

## Search and compare

```bash
aeep catalogs list
aeep catalogs add team owner/repository
aeep catalogs add local /absolute/path/to/marketplace
aeep discover playwright video narration --json
aeep catalogs refresh team --query video
```

The default sources are the [Official MCP Registry](https://registry.modelcontextprotocol.io)
and [Anthropic's official plugin marketplace](https://github.com/anthropics/claude-plugins-official).
They are searchable metadata sources, not preinstalled plugins. Claude and Codex
marketplace files are supported. ARD, MCP, Smithery and Docker source types remain
available through `aeep catalogs add --kind`; Smithery requires an operator-selected
token environment variable. AEEP has no invented API for OpenAI's hosted directory.

Queries contain short public capability terms, not private prompts. Searches have
source deadlines, result ceilings, source errors and labelled cached fallbacks.
The MCP registry searches names; marketplace readers also search descriptions.
An outage never erases another source's results. Missing coverage should trigger
host web search for public documentation and repositories. Hosts without web
search must say that the remaining candidates are unresolved.

In your connected agent, ask:

> Use AEEP to recommend a high-quality narrated educational video introducing a
> website feature. Inspect existing tools, search catalogs and public sources,
> compare named candidates for every stage, and explain what needs setup.

The stages must cover website inspection, scripting/storyboarding, screen capture,
narration, editing/motion, captions, and quality review. `text.stats` can count
script words; it cannot establish that the video workflow is complete.

For automation, `aeep stack recommend examples/video-recommendation.json` accepts
public semantic requirements from the host. The record includes preferred
components, alternatives, sources, evidence, readiness and next actions. Priorities
help the host make the comparison; lexical relevance is not measured quality.
Prices and quality stay unknown unless supported by applicable evidence.

- **Recommendation ready:** a comparison exists; output contracts and authority
  still need checking.
- **Setup required:** selected components need installation or connection.
- **Ready to run:** reserved for a registered executable proposal with passing
  current preflight and its required execution authority.
- **Blocked:** a stage has no compatible candidate or an execution requirement
  remains unresolved.

The existing `stack propose`, `preflight`, `assemble`, and reviewed execution
commands retain their contracts. Recommendation records never become executable
just because a package was installed.

## Configure a selected component

```bash
aeep stack setup guided CANDIDATE_ID --connection codex
```

The guide displays the saved candidate metadata, asks for its exact package/version
or HTTPS endpoint, and previews the effects before review. Supported installers
use argv-based commands for npm, binary Python packages, exact Git revisions of
native Codex/Claude marketplaces, or explicit HTTPS MCP endpoints. npm lifecycle
scripts are disabled by default; Python source builds are disabled. Native plugins must be contained in the pinned catalog. Command-based catalog
sources and unresolved native plugin dependencies require a separate handoff.
Claude uses project scope; Codex native installation uses user scope and can
affect other projects. [Claude documents these scopes](https://code.claude.com/docs/en/plugins/cli-reference).
For Claude, AEEP copies the selected plugin from the reviewed commit into an
owned local catalog named `aeep-reviewed-…`. The preview shows that name.
This preserves the commit pin because Claude's remote catalog references accept
branches and tags. Upstream updates require a new setup review.
Native plugin hooks may run when the host loads the plugin and are part of the review.

Native component connections are separate from AEEP's execution router. Configure
native filters through explicit adoption below. For API applications, setup writes
an MCP connection descriptor for application integration; that descriptor alone
is not a registered executor or a working application loop. Unsupported formats
need an explicit handoff. A failed or interrupted package installation is retained
for inspection; retry requires `stack setup component DEFINITION --retry-failed`.

## Control tools per agent

```bash
aeep agents list
aeep agents connect reviewer --host codex --project /path/to/project
aeep access show reviewer
aeep access deny reviewer aeep_stack_recommend
aeep access explain reviewer
aeep access allow reviewer aeep_stack_recommend
```

Each named connection has its own tool inventory and exact executor fingerprints.
A running server or application binds the identity; model arguments cannot select
another connection. Listing, exported declarations, direct tool calls, generic
routing, and stack dispatch all retain the connection restrictions. Calls recheck
revocation even when an agent has cached an old declaration. Allowing a tool does
not enable an executor, qualify it, or increase a grant or approval ceiling.

For an existing native MCP connection:

```bash
aeep agents inspect reviewer
aeep agents adopt reviewer existing-server write_tool
aeep agents adopt reviewer existing-server write_tool --restore
```

This previews and manages one native deny rule. Codex uses `disabled_tools`;
Claude uses its MCP permission rules. Unrelated settings and subsequent user
edits remain intact. Native visibility/enforcement must be verified after reload;
AEEP does not claim control over an unmanaged alternative connection. Skill or
hook changes may require a new session because already-loaded instructions cannot
be removed from a conversation. Whole-agent isolation is outside this release.

DeepSeek applications use `aeep.integrations.connected_tools.ConnectedTools` for
both schema declarations and guarded dispatch. See
[`examples/deepseek_connection.py`](../examples/deepseek_connection.py). Running it
without `--prompt` prints declarations without a paid call. With `--prompt`, the
application explicitly owns the model request loop, API key and model selection.
The DSH native router also accepts a `connection` path and retains its existing
dispatch guard.

## Repair, update and remove

Rerun setup to repair unchanged AEEP-owned entries. It stops on conflicting user
edits and preserves existing manifests, grants and receipts. Multiple projects
should use distinct connection names through `agents connect`.

```bash
aeep agents disconnect reviewer
aeep update
aeep uninstall
```

Disconnect revokes calls immediately, then removes unchanged owned host entries.
Uninstall removes the unchanged installer launcher and disconnects AEEP-managed
connections. It retains runtime directories, selected third-party components,
receipts, grants, and recovery records for inspection. It never prunes Docker or
unknown files. Updates require published checksum-verified installer assets;
unpublished assets cannot be downloaded with `aeep update`.

## Release preparation and verification

The public one-command download is a release interface, not yet a verified
published installation route. Do not advertise the latest-release curl command
until its assets exist and pass platform smoke checks.

Build without publishing:

```bash
PYTHONPATH=src python3 scripts/build_installer.py \
  --uv /absolute/path/to/pinned/uv --tag v0.8.2 --output /absolute/path/to/release
sh /absolute/path/to/release/install.sh --bundle /absolute/path/to/release/bundle
```

The builder produces a wheel, hashed dependency requirements, a bundle, an
installer with an immutable release URL, and `SHA256SUMS`. Release metadata records
the source revision and whether the source was dirty. A dirty-source build is a
local candidate, not release evidence. Preserve rollback runtimes until verification.

The [implementation and gate record](../reports/v08/plan-coverage.md) separates
mocked tests, real local installer checks, live host checks, platform checks and
human usability. A service self-check is not proof of host visibility after reload.
Follow [the assessment testing policy](ASSESSMENT_TESTING.md) for comparisons;
installing or connecting a candidate is not comparative evidence.
