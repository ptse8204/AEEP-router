# AEEP Agent Router

AEEP helps an AI agent find capabilities, compare them with its existing tools,
and run approved actions under operator limits. The agent plans the work; AEEP
checks permissions, selects a compatible implementation and records the result.

**Status:** AEEP 0.8 is experimental. APIs, configuration and stored data may
change incompatibly, including workflows that currently work. General benefits
from plugin selection remain unproven.

[Connect your agent](#set-up-agents-and-searchable-catalogs) · [Documentation index](docs/README.md)

## When to use it

An agent discovers a plugin that claims to improve spreadsheet work. Before
granting automatic access, you need to know what it requires, whether it meets
the task's correctness requirements, and whether optional access helps an
already capable agent. AEEP provides separate discovery, assessment and scoped
execution controls for that process.

You can also route a known action directly, restrict a project tool's access,
and inspect its execution receipt. Ordinary routing works without assessment
workers. Controlled comparisons require separate reviewed workers and evidence.

## Watch it run

[![AEEP terminal recording: preview a route, execute it, inspect a receipt, and run three offline stacks](docs/media/aeep-demo.gif)](https://github.com/ptse8204/AEEP-router/raw/refs/heads/main/docs/media/aeep-demo.mp4)

[MP4 recording](https://github.com/ptse8204/AEEP-router/raw/refs/heads/main/docs/media/aeep-demo.mp4)
· [Commands and transcript](docs/media/README.md)
· [Connect your agent](#set-up-agents-and-searchable-catalogs)

These are actual local commands with synthetic fixtures and no paid provider
calls. The media stack produces an edit timeline, not a generated video.

<a id="quick-start"></a>
<a id="install-in-codex"></a>

## Set up agents and searchable catalogs

Use macOS or Linux/WSL, Python 3.11 or newer, Git, and an installed agent
application. Native Windows onboarding is outside the supported setup target.
Install from source:

```bash
git clone https://github.com/ptse8204/AEEP-router.git
cd AEEP-router
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

From the project where your agent will work, run:

```bash
aeep setup
```

Choose Codex, Claude Code, DeepSeek Harness or an API application. Review the
proposed configuration, restart the selected host, and open a new session.
Keep the virtual environment: setup records its absolute interpreter path.
API applications need to wire the generated connection descriptor into their loop.

Check the connection:

```bash
aeep doctor --setup
```

Then ask your connected agent:

> Use AEEP to search the configured catalogs for video narration tools. Report
> named candidates, their sources and any setup still required.

The default catalogs are the Official MCP Registry and Anthropic's official
plugin marketplace. Searching reads metadata. A new connection allows planning
and search; installation and execution keep their separate review requirements.
`doctor --setup` checks local service readiness, while effective host exposure
still needs a reload and an actual host observation.

See [setup and controls](docs/ONBOARDING.md) for connection names, catalog sources,
component setup, troubleshooting, update and removal. The public installer
download command remains withheld until release assets are published and verified.
For an existing marketplace launcher, see its [dedicated-runtime prerequisites](integrations/aeep/README.md).

## Connect an agent

| Host | Connection path |
|---|---|
| Codex | Guided project MCP connection and planning instructions. |
| Claude Code | Guided project MCP connection and planning instructions. |
| DeepSeek Harness | Guided Cordis MCP overlay; a separate native bridge supports exact actions before a model call. |
| API application | Connection-bound declarations and guarded dispatch; the application owns its model loop and credentials. |

[Integration guidance](docs/INTEGRATIONS.md) covers manual stdio/HTTP MCP,
provider-native schemas, host-native dispatch and compatibility limits.
For a deterministic CLI action, try the [local quickstart](examples/quickstart/README.md).

<a id="stack-proposals"></a>

For multi-step work, [stack planning](docs/STACK_PLANNING.md) supports host-supplied
task graphs, inert recommendations and explicitly reviewed execution. Catalog
connectivity does not prove provider readiness, task quality or permission to run.

<a id="how-it-works"></a>

## Permissions and data

A **route** connects an action to an **executor**, the implementation that runs it.
AEEP rejects routes that violate hard constraints before ranking eligible choices.
A **receipt** records the selected implementation, outcome, verification and
measured resource use.

- Requests cannot weaken manifest policy or raise operator approval ceilings.
- Imported routes remain inactive until qualified and activated. Scoped tasks
  bind exact executors, permissions, attempt limits, runtime and expiry.
- Writes and payments require operator approval. Inputs and outputs are not
  persisted by default, and command execution uses argv arrays.
- Personal subscription capacity defaults to `SELF_ONLY`. Economic evidence
  and the disabled, offline x402 binding grant no marketplace or payment authority.

Read the [security policy](SECURITY.md) and [assessment guide](docs/ASSESSMENT.md)
before enabling new execution. [Per-agent controls](docs/ONBOARDING.md#control-tools-per-agent)
describe access inspection, revocation and restoration limits.

<a id="measured-examples"></a>
<a id="native-workbook-comparison"></a>
<a id="direct-execution-of-a-known-tool"></a>

## Test results and current limits

Known local text operations and two native workbook tasks passed their recorded
checks. The completed DOCX study passed 137/141 cases and did not qualify; the
composed workbook study passed 136/141 and returned `insufficient_evidence`.
Successful child operations do not turn timed-out workflows into passing trials.

The normal-agent / discovery-only / discovery-plus-AEEP comparison remains
unrun. Missing measurements prevent savings claims for those qualification
studies. Human comprehension and general workbook preservation remain unproven.
Detailed measurements, methods and dated software results are in the
[evidence guide](docs/EVIDENCE.md); [plan coverage](reports/v08/plan-coverage.md)
records exact references and open release gates. Passing software tests does not
establish a completed product release.

<a id="development"></a>

## Documentation

Use the [documentation index](docs/README.md) to find tutorials, how-to guides,
reference, explanations and version-specific migration instructions.
For development, follow [Contributing](CONTRIBUTING.md) and the
[assessment testing policy](docs/ASSESSMENT_TESTING.md) before changing or running
assessment, execution-adapter or release-verification work.

Licensed under [Apache-2.0](LICENSE).
