# Contributing

You can contribute adapters, benchmarks, policy research, security reviews, or
real execution traces with sensitive data removed.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,http-server]'
PYTHONPATH=src python scripts/generate_schemas.py --check
pytest
coverage run -m pytest
coverage report -m
```

## Principles

1. Preserve raw resource measurements.
2. Hard constraints precede scoring.
3. Every selection must be explainable.
4. Fail safely; never fall back silently.
5. Do not make one provider's token a universal currency.
6. Protocol objects remain provider-neutral.
7. New execution boundaries require explicit security analysis.
8. Tests must exercise real behavior, not only object construction.

## Documentation

Start with the [documentation index](docs/README.md). Follow
[Diátaxis](https://diataxis.fr/): keep tutorials, how-to guides, reference and
explanations distinct, using existing paths where possible.
Lead with what AEEP is meant to change in the reader's workflow: less manual
tool selection, useful capabilities and execution within limits they control.
Present these as goals, with measured results in the evidence guide. Each
section should explain why a step matters before introducing its mechanisms.
Keep paragraphs short and use examples to illustrate the general workflow.
The README should explain the product and get a reader connected to an agent;
benchmark tables and engineering history belong in linked evidence records.

Before submitting a documentation change:

1. Check factual claims against code, CLI help and completed, source-bound
   evidence. Distinguish configured, available, permitted and observed behavior.
2. State the intended reader, prerequisites, useful result and relevant limits.
   Use plain language and explain technical terms at first use.
3. Keep commands runnable from the stated directory. Verify corrections separately
   from prose editing; do not execute sign-in, live trials or paid examples merely
   to check their documentation.
4. Update the affected guide and index when behavior changes. Prefer a link to
   the canonical explanation over copying it. Preserve old heading anchors when
   reorganizing a linked section.
5. Keep measured results attached to their dates, source and conditions. Unknown
   measurements remain unknown; negative qualifications and open gates stay
   visible. Older subsystem versions can still describe supported contracts.
6. Use the installed humanizer skill in embedded mode when useful. Preserve facts,
   uncertainty, quotations, commands, data and necessary terminology. Installing
   a community authoring skill is optional, never a runtime requirement.
7. Run the checks below and inspect rendered navigation, tables, code blocks and
   media. Record unresolved discrepancies in `reports/v08/plan-coverage.md`.

Local checks require GNU Make, Node.js 22 or newer, npm/npx, and
[Lychee 0.24.2](https://github.com/lycheeverse/lychee/releases/tag/lychee-v0.24.2).
Install the matching Lychee release binary after checking its published SHA-256.
`npx` downloads the pinned `markdownlint-cli2@0.23.3` on first use and reuses its
cache. These are authoring tools; AEEP's Python dependencies are unchanged.

```bash
make docs-lint
make docs-links
make docs-check
```

For a binary outside `PATH`, use `make docs-check LYCHEE=/absolute/path/to/lychee`.
Both checks use the active-document list in the Makefile. The testing policy,
adopted ADRs, versioned roadmap/status records, changelog, historical reports and
packaged skills are excluded as inputs. Links from active docs to those files
are still checked. Link checking is offline and includes local files, images
and heading fragments; URLs in code blocks are examples, not check inputs.
Review changed external links separately against their authoritative sources.
CI is unchanged, and the commands do not rewrite files.

Run the required repository checks when executable files or packaged integration
assets change. Integration READMEs contribute to the verification source digest:
old live evidence keeps its original binding and may require renewal. Never edit
historical records or verification locks to make an editorial change appear
qualified. Agent review cannot supply human-usability evidence.

## Pull requests

Describe the problem, your design, and the alternatives you considered. Explain
any compatibility or security impact and record the tests you ran. Update the
documentation and specification when the change affects them.

Keep provider-specific logic in adapters/integrations so the core scorer stays
independent of any model vendor, payment rail, or marketplace.

Read the [assessment testing policy](docs/ASSESSMENT_TESTING.md) before changing or running
assessment, execution-adapter or release-verification work in this repository.

## Stack changes

Read [STACK_PLANNING.md](docs/STACK_PLANNING.md) and
[ADR-011](docs/adr/ADR-011-stack-synthesis-preflight.md) before extending the planner
or setup boundary. Keep planning inert and keep vendor behavior in adapters.
Record exact implementation reviews, tests and remaining gates in
`reports/v08/plan-coverage.md`. Run the repository checks plus the stack fixture
suite. A mocked provider check cannot satisfy the real onboarding gate.
