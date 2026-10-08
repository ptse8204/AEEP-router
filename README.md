# AEEP Agent Router

AEEP aims to let you focus on the work you want done while your agent finds
and uses suitable capabilities within limits you control.

The goal is better results with less manual tool selection and wasted resources,
while you retain control over access and spending.

**Status:** AEEP 0.8 is experimental. APIs, configuration and stored data may
change incompatibly. See [progress and evidence](#test-results-and-current-limits)
for what has been tested and what remains open.

[Connect your agent](#set-up-agents-and-searchable-catalogs) · [Documentation index](docs/README.md)

<a id="when-to-use-it"></a>

## From a goal to approved execution

1. Your agent works out what the task needs and searches for useful capabilities.
2. You can evaluate a new capability against the tools the agent already has.
3. You approve its access and limits. AEEP selects an approved way to run each action.
4. Execution records show what ran, what was checked and which resources it used.

For multi-step work, your agent supplies a plan and AEEP checks how the configured
tools fit together. You can also route a known action directly;
assessment runs separately when you want to evaluate a new capability.

## Watch it run

[![AEEP terminal recording: preview a route, execute it, inspect a receipt, and run three offline stacks](docs/media/aeep-demo.gif)](https://github.com/ptse8204/AEEP-router/raw/refs/heads/main/docs/media/aeep-demo.mp4)

[MP4 recording](https://github.com/ptse8204/AEEP-router/raw/refs/heads/main/docs/media/aeep-demo.mp4)
· [Commands and transcript](docs/media/README.md)

These are actual local commands with synthetic fixtures and no paid provider
calls. The media stack produces an edit timeline, not a generated video.

<a id="quick-start"></a>
<a id="install-in-codex"></a>
<a id="set-up-agents-and-searchable-catalogs"></a>

## Get started

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
proposed configuration, restart your agent application, and open a new session.
Keep the virtual environment: setup records its absolute interpreter path.
API applications need to wire the generated connection descriptor into their loop.

Check the connection:

```bash
aeep doctor --setup
```

Then ask your connected agent:

> Use AEEP to search the configured catalogs for video narration tools. Report
> named candidates, their sources and any setup still required.

Expect named candidates and setup requirements from the Official MCP Registry
and Anthropic's official plugin marketplace. Search reads metadata; review
installation and execution separately. The prompt checks that your reloaded
agent can use the connection; `doctor --setup` checks the local service.

See [setup and controls](docs/ONBOARDING.md) for component setup, updates and removal,
or the marketplace launcher's [dedicated-runtime prerequisites](integrations/aeep/README.md).
The public installer command awaits publication and platform verification.

## Connect an agent

| Host | Connection path |
|---|---|
| Codex | Guided setup for your project. |
| Claude Code | Guided setup for your project. |
| DeepSeek Harness | Guided MCP connection, or a native bridge for known actions. |
| API application | Use AEEP tools inside your application's own model loop. |

[Integration guidance](docs/INTEGRATIONS.md) covers manual stdio/HTTP MCP,
provider-native schemas, host-native dispatch and compatibility limits.
For a deterministic CLI action, try the [local quickstart](examples/quickstart/README.md).

<a id="stack-proposals"></a>

Use [stack planning](docs/STACK_PLANNING.md) to compose multi-step work from
configured capabilities and review its execution requirements.

<a id="how-it-works"></a>
<a id="permissions-and-data"></a>

## Stay in control

Set access and spending limits before execution. AEEP rejects routes that break
hard constraints before ranking eligible choices. New imported routes remain
inactive until qualified and activated; model requests cannot raise your limits.

Writes and payments require operator approval. Task inputs and outputs are not
persisted by default. Receipts retain outcomes and resource measurements so you
can inspect how approved work ran.

Read the [security policy](SECURITY.md) and [assessment guide](docs/ASSESSMENT.md)
before enabling new execution. [Per-agent controls](docs/ONBOARDING.md#control-tools-per-agent)
explain how to inspect, revoke and restore access.

<a id="measured-examples"></a>
<a id="native-workbook-comparison"></a>
<a id="direct-execution-of-a-known-tool"></a>
<a id="test-results-and-current-limits"></a>

## Progress and evidence

AEEP has recorded successful local text operations, two native workbook tasks
and access-control checks. The larger DOCX and composed workbook studies found
failures and did not qualify their candidates.

The normal-agent / discovery-only / discovery-plus-AEEP comparison remains
unrun. Read the [evidence guide](docs/EVIDENCE.md) for measurements and limits,
including missing savings and human-usability evidence. [Plan coverage](reports/v08/plan-coverage.md)
tracks remaining release gates.

<a id="development"></a>

## Documentation

Find your next step in the [documentation index](docs/README.md).
To contribute, follow [Contributing](CONTRIBUTING.md) and the
[assessment testing policy](docs/ASSESSMENT_TESTING.md).

Licensed under [Apache-2.0](LICENSE).
