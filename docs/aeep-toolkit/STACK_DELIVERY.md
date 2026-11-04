# Run an assembled evaluation workflow

New comparisons are paused by the [complete-stack gate](STACK_COMPLETION.md).
`run` now requires `--stack-readiness` with current canonical completion evidence.
A separate `--engineering-review` permits only an exact bounded required-use
qualification check; it cannot resume optional-use/value trials. Existing grant,
disclosure and worker controls still apply. Report export does not run tasks.

Use one reviewed workflow to choose a capability configuration, run its existing
assessment and inspect canonical results. The Toolkit connects benchmark inputs,
workers, protected grading, telemetry and reporting. It reuses AssessmentService
and BenchmarkRunner; it adds no scheduler, database or hosted service.

The [component audit](../../reports/toolkit-v2/c13/stack-delivery-20261030/README.md)
distinguishes actual upstream execution from report import, fixtures and research.
The managed fallback remains selected under D40. Agent-skill-eval 0.7.0 also has
a controlled AEEP worker bridge. Its upstream-native Codex harness remains
unsupported. The [two-engine engineering record](../../reports/toolkit-v2/c13/integration-snapshot-correction-20261103/RESULTS.md)
records actual scheduling and grading through each explicitly selected engine.

## Select an existing assessment

Start with exported, reviewed AssessmentPlan and SourcePin JSON files. They must
describe the same canonical skill/plugin assessment stored in the existing
assessment directory. SourcePin binds the inspected subject's complete dependency
map. Preparing that plan, inspecting dependencies, reviewing authority and
qualifying its workers remain the existing assessment operations described in
[managed evaluation](MANAGED_EVALUATION.md).

From the repository root:

```bash
PYTHONPATH=src python3 -m aeep_toolkit workflow bind \
  --configuration repository-helper \
  --plan /absolute/reviewed-plan.json \
  --source /absolute/reviewed-source.json
```

This prints a workflow definition with exact file hashes. Save it privately as
`workflow.json`. Its `configurations` object can contain up to 16 named entries
produced this way, each with its own frozen plan and source. Names select plans;
they do not enable components, prove usefulness or grant execution authority.
Absolute paths are local bindings; relative paths resolve beside the workflow
file. Traversal, linked input paths and credential metadata are rejected.

Review the selected configuration without starting a worker or opening a database:

```bash
PYTHONPATH=src python3 -m aeep_toolkit workflow plan \
  --workflow /absolute/workflow.json \
  --configuration repository-helper
```

The preview shows the existing backend review, task families, candidate inventory
and exposure mode. Its review digest binds the workflow, selected files and
current adapter source. A changed configuration or file needs a new preview.
All three acceptance gates remain unassessed by this command.

## Execute and inspect

After obtaining applicable exact execution authority, run the selected plan:

```bash
PYTHONPATH=src python3 -m aeep_toolkit workflow run \
  --workflow /absolute/workflow.json \
  --configuration repository-helper \
  --reviewed-digest WORKFLOW_REVIEW_SHA256 \
  --manifest /absolute/aeep.yaml \
  --directory /absolute/existing-assessments \
  --output /absolute/new-private-report
```

This delegates to `eval managed run`. The existing service rechecks canonical
definitions, grant, accounting, worker identity, conformance and recovery. The
workflow file cannot install software, start supporting services or amend grants.
An interrupted or denied invocation is not retried by this command. Inspect its
canonical job and retained attempts before any further execution.

The new private output directory contains normalized evidence, original analysis
references, accounting records and `report.html`/`report.md`. Missing telemetry
and unnormalized trials remain visible. Auxiliary arms stay in canonical analysis
and accounting. They are not silently treated as normalized primary-arm evidence.

To export an existing completed report without dispatch, use the same arguments
with `workflow report` instead of `workflow run`, adding `--report-id REPORT_ID`.
Current-source and canonical binding checks still apply. Old terminal campaigns
retain their own source scope; do not rerun them to make a new export pass.

## Acceptance gates

These three gates are independent. Historical checkpoint passes retain their
original definitions and evidence tiers.

| Gate | What must be demonstrated | What cannot pass it |
| --- | --- | --- |
| Working stack integration | An operator selects a bound configuration and completes the actual CLI path through applicable workers, benchmark/grader, receipt-bound telemetry and canonical HTML/Markdown; failure/recovery preserves costs | A catalog, installed package, preview, mock result or independently tested components |
| Candidate usefulness | Qualified capability versus the capable shared baseline on independent representative tasks, with optional use in value trials and frozen utility/guardrails | Stack operation, forced invocation, instruction loading or more repetitions of exposed tasks |
| AEEP selection usefulness | Same candidate inventory and authority for discovery/fixed-policy and AEEP arms; actual pre-task selections, independent outcomes and complete decision overhead demonstrate AEEP's increment | An oracle choosing after outcomes, discovery's gain, refusal to admit one bad report or a selector scoring fixture |

Resource qualification and public release retain separate records. Whole-system
budgets require representative workload measurements. Proposed thresholds do not
become product requirements because a fixture meets them.

## Differentiated capabilities and configurations

The following repository-specialist proposal is parked until the
[complete-stack gate](STACK_COMPLETION.md) passes. It describes a later comparison,
not the current delivery step. The proposal targets repository maintenance with executable specialists:
Ruff's selected safe automatic fixes and LibCST's structural codemods. Their
mechanisms differ from a general instruction skill: one applies lint-rule fixes;
the other transforms Python syntax with metadata. These are candidate hypotheses,
not established improvements to an already capable agent. See the primary
[Ruff](https://docs.astral.sh/ruff/linter/) and
[LibCST](https://libcst.readthedocs.io/en/latest/codemods.html) interfaces.

Reuse public repository snapshots and their existing protected regression tests.
Include tasks requiring lint cleanup, API migration across files, both operations
and neither. Added intent checks must be independently validated against correct,
partial and destructive repairs before model assessment. Authored maintenance
tasks must be labeled separately from published upstream issues. Protect answers
and future cases, and retain existing exposure exclusions.

Evaluate ordinary tools, optional specialist A, optional specialist B and optional
A+B as distinct frozen configurations. Keep the ordinary baseline capable. Compare
the bundle with its useful individual components; adding two tools does not imply
that their combination helps. First validate the implementations and boundaries,
then measure optional-use value. The current skill bridge does not by itself
qualify arbitrary tool bundles or multi-tool exposure telemetry.

Ruff is already a development dependency in this checkout. Preserve it wherever
the target's ordinary environment provides it. There, Ruff availability belongs
to the shared baseline, and an added Ruff wrapper is a duplicate-capability
negative control or a separately labeled skill-only contrast. Do not remove the
existing binary, count it as a new capability or spend trials to manufacture an
availability benefit. Inventory the actual target before freezing configurations.

Only after candidate evidence exists should a frozen task-specific AEEP selector
be compared with discovery-only and a strong fixed policy chosen from prior data.
Use the existing three-way assessment and selection-report contracts. Give those
policies equal inventory, models, budgets and permissions. Grade inappropriate
selection, missed useful capability and abstention separately from task success.
Never supply held-out usefulness labels to the selector.

The existing Ponytail comparisons remain valid negative/inconclusive evidence for
their tested scopes. Preserve their reports, charged turns and source bindings.
They are not another run in this demonstration or a reason to fill test counts.

## Retain and query a selected local catalog

An operator can retain a reviewed upstream executable without installing it in
the host environment. The file-runtime plan copies exact local artifacts into
an owned private directory. Prepare it with `install-files-plan`, then bind its
`installation` object as a JSON file under the selected configuration's `runtimes`.
See the [installation guide](INSTALLATION_DESIGN.md#reviewed-file-runtimes).

The existing `workflow setup`, `workflow readiness` and `workflow remove` commands
accept both wheel and file installations. Select each runtime with `--runtime`.
Omit `--reviewed-digest` for a preview. Setup and removal require the exact preview
digest and a reviewed accounting scope. Readiness checks bytes and ownership;
it does not establish functional readiness or execution permission. Removal
preserves changed files and runtimes referenced by other configurations.

For local SkillRank queries, select `skillrank`, its runtime binding, and an exact
`catalog` file reference in the configuration. The referenced
`aeep.toolkit.catalog-runtime.v1` definition binds the source revision, reviewed
catalog data and rights, worker image, Docker executable, controller and existing
authorization. Store that inert definition with the following command; it neither
reviews nor executes it. Create the reviewed control directory before dispatch.

```bash
PYTHONPATH=src python3 -m aeep_toolkit workflow define-catalog \
  --file /absolute/catalog-runtime.json --manifest /absolute/aeep.yaml
```

```bash
PYTHONPATH=src python3 -m aeep_toolkit workflow catalog \
  --workflow /absolute/workflow.json \
  --configuration document-data \
  --mode search --value spreadsheet
```

This previews the selected lookup without opening Docker or starting SkillRank.
To execute after applicable approval, supply `--reviewed-digest` from that preview,
`--accounting /absolute/accounting-v4.json` and a fresh `--operation-id`. Use
`--mode show --value owner/skill` for one record. Accounting v4 adds explicit
catalog authority; older accounting scopes keep their original stages.

Execution mounts only the verified binary and AEEP packages read-only in the
existing offline worker. SkillRank's upstream local server starts on container
loopback, serves the reviewed catalog, and stops before worker removal. Every
query reserves an operation; receipts and execution journals persist. Wrapper
overhead excludes the nested lookup interval. Failed or interrupted work retains
its charge, and uncertain cleanup blocks another dispatch. Catalog contents and
query text are transient; canonical records retain their digests and references.
Search results and upstream ratings do not establish safety or usefulness.

## Current verification boundary

Actual evaluator journeys and the pinned SkillRank build/search/show checks have
their own source-bound records. The new file lifecycle and workflow catalog
wiring have first-party checks; actual current-source CLI catalog execution still
needs its reviewed functional check. SkillRank bounded evaluation remains open.
The component audit and [persistent state](STATE.md) identify the remaining work.
Neither component checks nor this guide close the complete-stack gate.
