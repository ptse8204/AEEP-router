# Plugin assessment in AEEP 0.8

Use assessment to decide whether a new capability earns a place in your agent's
workflow. Compare it with the tools the agent already has, including the effort
and resources needed to add it. A useful outcome can be keeping the existing tools.

For a first connection, use [onboarding](ONBOARDING.md). Operators preparing a
comparison or scoped task tool should read the [testing policy](ASSESSMENT_TESTING.md)
before running the commands here.

[Documentation index](README.md).

Assessment runs separately from ordinary work so trials and their costs stay
distinct from production history. AEEP records the comparison and its reviewed
authorization; ordinary tasks can run without an assessment worker.

```text
Selected subject → recipe and mapping review → standing authorization
→ isolated BenchmarkRunner campaign → comparative report → scoped admission

Task tool → applicability and policy checks → approved implementation
→ validation and production receipt
```

<details>
<summary>Contents</summary>

- [Project-local task operation](#project-local-task-operation)
- [Available implementation](#available-implementation)
- [Configured assessment setup](#configured-assessment-setup)
- [Legacy initializer](#legacy-initializer)
- [Explicit host and container execution](#explicit-host-and-container-execution)
- [Remaining release gates](#remaining-release-gates)
- [Historical live validation on Codex 0.154.0](#historical-live-validation-on-codex-01540)
- [Migration and rollback](#migration-and-rollback)
- [Choosing a comparison structure](#choosing-a-comparison-structure)
- [Host conformance is a separate gate](#host-conformance-is-a-separate-gate)
- [Test layers and release evidence](#test-layers-and-release-evidence)
- [Historical temporary-directory diagnostics](#historical-temporary-directory-diagnostics)
- [Incremental-capability revision](#incremental-capability-revision)

</details>

## Project-local task operation

Give an agent a useful project tool with a defined allowance, then inspect,
pause or remove that access through the same task controls. The native path runs
on demand on the tested macOS/Codex profile and reuses existing route approvals.

Configure an eligible native command and a scope conforming to
schemas/task-scope.schema.json. The scope binds the project, exact executor
fingerprints, permission ceiling, expiry, attempt allowance and time cap.
Reviewing it does not qualify a new route.

These operator commands were exercised in the
[retained CLI journey](../reports/v08/steering-v1-delivery-validation/final/cli-journey.json):

```bash
python3 -m aeep task -m PROJECT/aeep.json define PROJECT/scope.json
python3 -m aeep assess -m PROJECT/aeep.json review EXACT_SCOPE_DIGEST
python3 -m aeep task -m PROJECT/aeep.json activate SCOPE_ID
python3 -m aeep tool-call aeep_csv --profile task --task-activation ACTIVATION_ID -m PROJECT/aeep.json -a '{"text":"name\nAda\n","delimiter":","}'
python3 -m aeep task -m PROJECT/aeep.json control pause ACTIVATION_ID
python3 -m aeep task -m PROJECT/aeep.json control resume ACTIVATION_ID
python3 -m aeep task -m PROJECT/aeep.json control inspect ACTIVATION_ID
python3 -m aeep task -m PROJECT/aeep.json control uninstall ACTIVATION_ID
```

Each activation ID identifies one AEEP-owned overlay under the project's
.aeep/task-profiles directory. `control stop` also cancels that activation's
current session-owned command. `activate SCOPE_ID --replace ACTIVATION_ID`
revokes the previous activation and creates a new one. Replacement retains the
previous overlay for explicit cleanup. `control rollback` and `control uninstall`
remove an unchanged owned overlay; edited overlays remain with a conflict.
None of these controls refunds task allowance or removes recovery evidence.
The CLI tests cover stop, replacement, rollback and restoration conflicts.

The same activation adds a named stdio MCP entry to the trusted project's
`.codex/config.toml`. Each activation has its own entry, so concurrent sessions
keep their own authority. Codex discovers the task-only tools when it next loads
that project configuration; an already running client may retain its earlier
tool inventory. Activation includes native approval rules for the exact tools
exposed by the reviewed task scope. The task service still checks the scope,
expiry, remaining allowance and revocation before dispatch. These rules do not
approve other servers or tools, and administrator restrictions still apply.
The entry launches the existing service with this syntax, also
exercised by the [stdio journey](../reports/v08/steering-v1-delivery-validation/final/mcp-journey.json):

```bash
python3 -I -m aeep serve --transport stdio --profile task --task-activation ACTIVATION_ID -m PROJECT/aeep.json
```

The host receives structured tool output, with a text fallback. AEEP cannot
inject trusted Codex approval controls. Uninstall removes only AEEP's unchanged
MCP entry and overlay; edits to its entry, including its tool approval rules,
cause a conflict and remain for operator inspection. Other TOML settings and other activations' entries are
preserved. The shared `.aeep/task-profiles/codex-config.lock` remains after
uninstall because deleting a lock file while another session uses it can split
synchronization. No global Codex setting is changed. The host still owns
planning and the selected service's launch lifecycle.

Successful CSV output in the retained journey says “Completed; task verification
is incomplete.” Its schema check does not establish broader preservation. The
fixed native workbook test says “Completed; recorded non-schema task checks
passed.” That statement covers only its declared independent grader checks.
Model-facing task arguments cannot activate, review, reconcile or enlarge scope.

A failed scoped write remains unresolved even after a normal nonzero exit.
Operator effect inspection may produce an inert task-reconciliation definition
through the existing repository and review path. The supported reconciliation
closes only the exact unresolved local attempt with retained terminal receipts
and no cash/capacity reservation. It preserves used allowance and labels the
resolution as operator-reviewed, not automated verification. Missing accounting
or uncertain effects remain blocked.

ARD discovery is optional preparation. The existing `registry search` command
accepts `--registry ard --base-url HTTPS_REGISTRY`; an explicit `--fixture FILE`
provides local fallback. Use only public search terms. Candidate metadata never
installs or approves a capability. See [plan coverage](../reports/v08/plan-coverage.md)
for the bounded compatibility decisions, tested syntax and remaining gates.

## Available implementation

`AssessmentService` shares the existing router and benchmark runner. Its three
deterministic recipes cover CSV records, labeled-text extraction, and disposable
file-tree search. The runner uses eight screening cases, 28 training cases and
105 distinct held-out cases. A screening failure can reject a route early.
Grader checks run before candidate execution. Repetitions do not increase the
number of independent correctness cases. Reviewed DAG implementations use the
same cases through explicit JSON Pointer bindings, including the case's request
restrictions at every step. Step executor identities are fixed in the mapping.

The `record_template:1` generator lets an agent propose new labeled-record
definitions using literal templates and exact ground truth. Definitions are inert
until reviewed. Their implementation digest, templates, mappings and environment
are included in the reviewed plan. Arbitrary generated Python code is not loaded
by this generator. `prepare-planning` creates an inert, reviewable Codex planning
request. After its mapping and grant are reviewed, `generate-definition` makes one
bounded planning call. Its output remains inert. Review the proposal, recipe and
candidate digests before `install-definition` stores an inactive candidate.
No model-facing tool can perform those review or installation operations.

Each fresh campaign router gets an isolated, durable SQLite store containing
its qualification, package, trust and artifact dependencies. The campaign
database's `trial_stores` table links each trial to its attempts, including
interrupted attempts with unknown outcomes. An internal trial grant permits only
the supplied exact route fingerprints in that router. Production eligibility
stays unchanged.

The plan freezes the AEEP files used for execution and evidence evaluation.
Campaign receipts remain separate, with sanitized case-validation results; they
retain native resource dimensions even if later grading fails. `router-fresh`
means a fresh router, not a fresh Python process. The legacy condition enum
keeps that meaning.

Authorization binds subject, recipe and environment digests, operation limits,
model-turn limits, elapsed time, cash and disclosure. Every trial and grader check
reserves budget transactionally before starting. Uncertain work retains its
reservation. Reusing an operation ID cannot spend again. Revocation stops new
operations and invalidates scoped admissions.

Reports calculate paired differences and resample template families and distinct
cases for uncertainty. Cash currencies, model identities and subscription pools
remain separate. Measurement coverage accompanies known subtotals; incomplete
measurements cannot establish complete totals or a native-resource savings claim.
The immutable campaign retains its original accounting evidence and trust
labels. Missing production measurements stay unknown. The immutable operation
ledger separates trial usage from inspection, generation, planning, fresh-router
setup, grading and report-generation overhead. Break-even calculations charge
that recorded overhead once. Incomplete native measurements leave their totals and
break-even values unknown; reserved limits are never presented as measured usage.

Successful local reports may create scoped admissions when the standing grant
permits it. Admission and a stored candidate's activation are atomic. The selection,
prepared execution, fallback and workflow paths check applicability; invocation
rechecks it. Verified production validation failures and implementation drift
revoke admission without running comparison calls. Restoring an old file does
not undo revocation. The scope marker remains, preventing a route from becoming
unrestricted when it loses admission.

## Configured assessment setup

Prepare a comparison from the routes and workers your operator has already
configured. The setup flow returns what is available and identifies missing
configuration before trials begin.

After an operator has selected the local subject, configured the routes and
workers, stored the recipe and environment, and granted finite scope, setup can
use those existing IDs without an authored benchmark suite:

```bash
aeep assess -m MANIFEST setup-options GRANT_ID
aeep assess -m MANIFEST setup SUBJECT_ID RECIPE_ID CANDIDATE_ID BASELINE_ID GRANT_ID ENVIRONMENT_ID --structure workflow --experiment EXPERIMENT_DIGEST
```

`setup-options` is paginated (`--after`, `--limit`) and returns descriptions and
IDs, not executable configurations, local paths or task contents. The same flow
is available through `aeep_assessment_options` and `aeep_assessment_setup`.
Agent comparisons require capable container profiles. The command returns a
specific missing configuration or review requirement if these are unavailable.
Use the operator-only `define-experiment FILE` and `review DIGEST` commands to
store and review the experiment; neither model tool approves it.

For an executable recipe, including workbooks, setup first prepares the existing
contained generator request. Review the returned definition digests, then use
`generate-cases MATERIALIZATION_ID` or `aeep_assessment_generate_cases`. The model
tool returns only the case-set ID, count and recipe digest. Call setup again with
its returned `next_setup_arguments` (or the equivalent CLI flags). The proposed
plan includes structure choices, dependency requirements, adapter eligibility
and the existing budget preview. New definitions still require operator review;
setup does not spend or replace the grant. The generator reserves and accounts
for its work on that same grant.

This path covers the three shipped recipes and reviewed executable recipes.
Worker installation, protected sign-in and conformance remain operator setup
requirements. Actual model-driven onboarding and all-family release evidence
must be verified independently.

## Legacy initializer

The compatible `init-assessment` command still creates the original three-family
read-only host draft. It does not provision capable container workers and is not
the incremental agent-comparison completion path:

```bash
aeep init-assessment ./assessment-workspace /absolute/path/to/skill-directory \
  --family csv --max-model-turns 300 --max-elapsed-seconds 3600
```

Those values are explicit ceilings chosen by the operator; adjust them before
approving the bundle. Initialization performs static inspection only. Read
`assessment-workspace/assessment-review.json`, then approve its exact definitions
and standing grant with:

```bash
aeep assess -m assessment-workspace/aeep.json approve-bundle assessment-workspace/assessment-review.json
aeep assess -m assessment-workspace/aeep.json run PLAN_ID
```

Configure the plugin MCP process with `AEEP_MANIFEST` set to the initialized
manifest's absolute path, or pass `--manifest` explicitly in its local server args.

The initialized manifest includes deterministic references for all three task
families and configured Codex baselines. An installed skill is an inactive
candidate until assessment and scoped admission succeed. Where a deterministic
reference is configured, its paired comparison can establish that it is faster
than the plugin; a plugin does not become preferred merely by beating a slower
agent baseline.

The group options precede the subcommand:

```bash
aeep assess -m aeep.yaml inspect /absolute/path/to/plugin
aeep assess -m aeep.yaml propose SUBJECT_ID csv CANDIDATE_ID BASELINE_ID GRANT_ID environment.json
aeep assess -m aeep.yaml show plan PLAN_ID
aeep assess -m aeep.yaml show recipe RECIPE_DIGEST
aeep assess -m aeep.yaml show mapping MAPPING_DIGEST
aeep assess -m aeep.yaml review RECIPE_DIGEST
aeep assess -m aeep.yaml review MAPPING_DIGEST
aeep assess -m aeep.yaml review ENVIRONMENT_DIGEST
aeep assess -m aeep.yaml authorize authorization.json
aeep assess -m aeep.yaml run PLAN_ID
aeep assess -m aeep.yaml revoke GRANT_ID
```

An environment for operator-configured local routes can be:

```json
{"environment_id":"local-reviewed","kind":"trusted_local","identity":{"runtime":"operator-reviewed-local"}}
```

Set `identity.approved_root` explicitly for production search admission. Synthetic
fixture directories do not authorize reading arbitrary production directories.
Use `schemas/assessment-authorization.schema.json` for the grant format. An absent
model-turn allowance means zero subscription execution. Cash defaults to zero,
remote disclosure to false, and automatic admission to false.

The MCP profile adds start/status/report/cancel operations under existing reviewed
plans. Start returns an assessment ID and launches a local worker using the exact
operator manifest. It never exposes grant creation or review as model tools.
Repeated starts reuse the plan's existing job, including terminal jobs. New
evidence after cancellation requires a new plan. A worker must claim a job
atomically.
After a crash, running work requires inspection and is not blindly rerun.
Workers record their process identity. A vanished worker becomes indeterminate;
PID reuse cannot establish that it is still running. `aeep assess -m aeep.json
recover ASSESSMENT_ID` removes containers belonging to retained attempts after
the worker has stopped. It retains uncertain attempts and never repeats their
candidate calls. Worker cancellation and grant revocation interrupt in-flight
work; durable receipts and reservations remain available for inspection.

## Explicit host and container execution

A managed-host route may add an `invocation` object. Omission preserves the legacy
turn behavior and fingerprint. `mode: "turn"` requests an isolated turn;
`mode: "skill"` requires `skill_name`, absolute `skill_path` ending in `SKILL.md`,
and `skill_sha256`; `mode: "mcp_tool"` requires `server`, `tool`, and
`tool_sha256` over the advertised tool contract. Target drift fails closed.

The optional managed-host adapter uses `skills/list`, `app/installed`, and `mcpServerStatus/list`.
As checked on 2026-09-19, OpenAI labels the `app-server` command experimental and
unsupported for production workloads. That limitation applies to host-driven
planning, skill execution and baselines; the normal external MCP plugin path is
supported. See the [current host support notice](https://learn.chatgpt.com/docs/mcp-server).
Protocol capability checks establish available methods, not production support.
`aeep assess -m aeep.yaml inspect-host PLAN_ID EXECUTOR_ID` requires an existing
reviewed plan and grant and debits an operation before introspection. Tool
schemas and descriptions remain untrusted declarations. No authentication fields
are retained in inventory records. Direct tool calls use `mcpServer/tool/call`;
skills use an explicit skill input item. The implementation follows the
[Codex App Server API](https://learn.chatgpt.com/docs/app-server) and
[thread configuration controls](https://learn.chatgpt.com/docs/config-file/config-reference).

Thread-local overrides disable unrelated apps, MCP servers, skills, hooks,
subagents, shell execution, and web search. The effective MCP/app inventory is
checked before invocation. Skill dependencies that require additional tools need
a separately reviewed workflow mapping. Host admission binds the resolved model,
adapter configuration, sandbox, working directory and an AEEP-owned HMAC account
correlation. Missing identity keeps the estimator on its prior. Resolved identities
use a separate cohort digest; historical cohort digests are unchanged. Invocation
rechecks admission identity, and model rerouting outside the assessed identity
retains incurred usage while rejecting the result as qualification evidence.

An `assessment_adapter` in an operator-reviewed executor configuration supports
an `input_template`, optional `target_input_schema`, and either `output_pointer`
or `output_fields`. Templates use the existing literal substitution helper;
projections use JSON Pointers. A projection failure retains execution accounting.
The reviewed mapping includes executable dependency hashes. Admission checks the
canonical recipe input and output schemas even when a plugin advertises a looser
schema; a verified output-contract violation revokes scoped use.
For a configured Codex search baseline, `input_transform: "local_search_tree:1"`
reads at most 1,000 entries and 100 KB under explicit `read_only_roots`, then sends
the files to an isolated model turn. The model needs no filesystem tool access.
A workflow summary identifies its component receipts so aggregate accounting
counts the work once when both summary and component records are present.
An `assessment_workflow` binds an existing `WorkflowRequest`, `case_input_bindings`
and exact `executor_fingerprints`. Nested workflow dispatch is rejected.

A `container` environment requires `container_runtime`, a local Unix
`container_socket`, and `container_image` with an exact SHA256 digest. The image
must already contain Python and AEEP's dependencies. `read_only_roots` explicitly
selects available directories. The installed AEEP source and disposable fixture
root are mounted read-only for trials. Native command, Python and stdio MCP
adapters run through the existing router inside this boundary; admission keeps
the same environment for later execution. The container has a read-only root,
non-root user, dropped capabilities, process/CPU/memory limits, bounded temporary
storage and no network by default. Enabling network also requires the standing
grant's disclosure authorization. Container-reported resource values are not
adopted as local observations; Docker-client CPU/RSS is not presented as the
candidate's usage.

## Remaining release gates

The complete 0.8 product release is not yet verified. Its release requirements
include the checks below. The [plan coverage record](../reports/v08/plan-coverage.md)
tracks current results and source bindings; earlier results apply to their
recorded revisions.

- Resolve the production-support limitation of the optional App Server integration,
  or explicitly scope the release as an experimental host integration.

- Live verification of the supported Codex inventory and invocation modes, including
  effective tool isolation across installed host configurations.
- Final coverage and fault checks for planning lineage, setup accounting, generated
  definitions, source drift and the supported intake paths. Planning requests bind
  the reviewed planner and executable dependency hashes before any model call.
- The opt-in real-container checks cover filesystem/network denial, resource
  limits, timeout, cancellation, worker death and cleanup without retry. Refresh
  their source-bound result after changes. Container-native CPU and memory usage
  remain unknown unless independently measured; limits are not usage measurements.
- Live validation of resolved host identity and scoped admission after model or
  account changes. Unknown identity still blocks automatic admission.
- An explicitly capped, authorized live Codex campaign covering assessment through
  subsequent automatic use. Offline tests do not prove this integration or savings.

Run `aeep verify assessment-product` for the offline product checks. Add
`--real-container` with explicit `AEEP_CONTAINER_IMAGE`, `AEEP_CONTAINER_RUNTIME`
and `AEEP_CONTAINER_SOCKET` values to include the real isolation and crash checks.
The report includes a source digest and separates offline protocol tests from
live host verification. Its accounting flag means the evidence-handling tests
passed; it does not claim that every native resource meter supplied a value.

No legacy router completion report establishes these new release gates. Current
compatibility reports and CI coverage are written under `reports/v08`; the
historical `reports/v07` artifacts remain unchanged.

## Historical live validation on Codex 0.154.0

The authorized release campaign reached the host but did not start a model turn.
This installation required a 16 MiB protocol frame bound for its installed MCP
inventory. Onboarding now uses that bound, while recipe input/output schemas
continue to constrain task data. Host-qualified skill names are resolved only
against the reviewed absolute path and content digest. Plugin MCP policy uses
`plugins.<plugin>.mcp_servers.<server>` as documented in the
[Codex MCP reference](https://learn.chatgpt.com/docs/extend/mcp#plugin-provided-mcp-servers).
Host-generated servers use their feature controls and must pass the effective
inventory check; AEEP does not create incomplete transport definitions for them.

Thread-level and dedicated-process restriction probes still advertised 16 tools
outside the approved inventory. AEEP therefore could not verify isolation and
blocked execution. Approval is already recorded; increasing the budget does not
resolve this host capability limitation. The three capability tools separately
passed actual stdio MCP calls. See `reports/v08/live-assessment.json` for the
sanitized evidence and the distinction between reserved and started model turns.
Execution/environment failures now remain separate from verified wrong outputs;
a missing result cannot establish plugin incorrectness.

## Migration and rollback

Opening a schema 7 database with 0.8 transactionally adds assessment records,
reviews, grants, reservations, jobs, admissions and an AEEP-owned host correlation
key. Existing evidence and signatures are not rewritten. The host key is unrelated
to Codex authentication; credentials and raw account identifiers remain host-owned.

Back up the database with SQLite's backup API before upgrading, while the old
binary still understands it. Keep that backup and the corresponding manifest.
For a binary downgrade, stop all workers and MCP servers, restore the pre-upgrade
database backup and restore the prior package. An older binary rejects schema 8;
editing `PRAGMA user_version` is not a downgrade procedure.

For an operational rollback on 0.8, revoke assessment grants and use the legacy
tool profile. Scoped alternatives remain excluded and feasible configured
baselines remain available. Historical assessment records are retained.

## Choosing a comparison structure

Choose what you want the comparison to tell you: how a callable implementation
performs, whether a skill helps an agent, or how a complete workflow performs.
Set that structure at the start for each plugin, capability and environment.
AEEP recommends `direct`, `controlled_agent` or `workflow` accordingly;
recommendations never approve dependency metadata.

- `direct` compares a callable implementation with the configured baseline and
  deterministic reference, where present.
- `controlled_agent` holds model settings, task instructions, permissions and
  supporting tools constant. Only the selected skill differs. Required supporting
  MCP tools use exact server/tool identities and contract digests in the operator
  invocation configuration.
- `workflow` compares the complete mapped workflows. Benefits belong to the whole
  workflow, including dependency and setup costs; they do not establish the
  plugin's individual contribution.

Use `--structure` with `aeep init-assessment` or `aeep assess ... propose`.
`aeep assess -m <manifest> structures <plan-id>` explains availability and missing
requirements. `select-structure <plan-id> <structure>` creates a new plan and a
new holdout seed under the existing grant. Review its changed comparison digest
before starting it. Historical plans and grant usage counters stay unchanged.
The corresponding model tools are `aeep_assessment_structures`,
`aeep_assessment_select_structure`, and `aeep_assessment_budget`. They cannot
approve definitions or enlarge grants. Capability tools still accept task
arguments only.

`budget <plan-id>` preserves the trial-only counts and also returns a
`campaign_allowance`: fresh-schedule reservation bounds for trials, warm-ups,
router setup, independent grader validation, contained reference/grader calls,
per-case grading and reporting. Artifact grader batching depends on reference
outputs, so it has a minimum and a conservative finite ceiling. These bounds
are not predictions of measured consumption.

The preview lists linked preparation operations separately, with missing elapsed
measurements left unknown. Completed setup, planning, generation, conformance and
prior-stage costs are not charged again. Remaining allowance includes held
reservations and all four grant dimensions. A started campaign or uncertain
lineage produces an unknown fit result; the preview cannot authorize a replay.
Future planning, conformance, reusable-tool construction and interventions need
separate reviewed allowances. Automatic retries are zero. A smaller budget never
reduces correctness or savings thresholds; exhaustion yields insufficient evidence.

New plans, reports and admissions use v2 comparison bindings. Old v1 records do
not acquire a structure by default. New recipes use v2 generators with explicit
variation/template identifiers, multiple input shapes, independently reviewed
fixtures and deliberate grader faults. Trials alternate arm ordering within
seeded case blocks. Search trials receive separate copies of fingerprinted input
trees. Scoped admission matches joint feature combinations, rather than accepting
untested combinations of individually observed features. Reports separate
execution conditions and use the frozen primary condition for admission.

## Host conformance is a separate gate

An advertised tool is not proof that a model can invoke it. A trace showing no
calls is not proof that access was denied. AEEP records advertised inventory,
availability when established, and observed tool identities separately; task
arguments and tool results remain excluded from receipts.

The current Codex adapter can check paginated advertised inventories and request
exact supporting-tool allowlists. These checks alone do not attest the model's
complete execution boundary or prevent reads of benchmark answers outside the
workspace. Scoped model trials return
`environment_verification_unavailable` before `turn/start` when the required
boundary cannot be established. An empty inventory is not an exception. Direct host-owned MCP
dispatch does not start a model turn. Legacy unscoped turn execution remains
available under its existing policy.

The installed Spreadsheets skill explicitly requires `@oai/artifact-tool`, a
JavaScript runtime, dependency discovery and a writable working directory for
workbook work. A tool-free read-only trial cannot establish its practical
usefulness. Its runtime mapping and sandbox need review before a representative
campaign; missing front-matter dependencies do not imply that none are needed.

## Test layers and release evidence

Existing pytest modules carry these markers without moving the suite:

| Marker | Evidence |
| --- | --- |
| `assessment_contract` | Offline recipe, comparison, mapping and protocol behavior |
| `assessment_lifecycle` | Authorization, admission, accounting, cancellation and recovery |
| `assessment_boundary` | Subprocess, filesystem and opt-in real-container boundaries |
| `codex_conformance` | Reserved for authorized checks of the installed host; mocks do not qualify |
| `live_acceptance` | Reserved for source-bound live product checks; offline campaigns do not qualify |

For example, run `python3 -m pytest -m assessment_contract`. Real-container tests
still require the explicit image, runtime and socket environment variables.

`aeep verify assessment-product --manifest <manifest> --assessment <assessment-id>
--receipt <production-receipt-id>` reads stored reports, campaign receipts and
source bindings. Repeat the IDs to include multiple families. It recomputes
comparison outcomes and keeps missing host evidence as an open gate. Add
`--release-checks` to execute compatibility, coverage, proof, Node and build checks;
this is an instruction to run checks, not a supplied success flag. Add
`--real-container` for the configured container checks. `--strict` fails while any
release gate is open. Demonstrated savings remain separate from product readiness.

## Historical temporary-directory diagnostics

The current comparison method uses separate immutable container workers, as
specified in [the assessment testing policy](ASSESSMENT_TESTING.md). The local
process diagnostics below remain useful for host troubleshooting. They cannot
establish the new container-conformance or live product gates.

New skill onboarding assigns `codex-app-server:baseline` and
`codex-app-server:candidate` to separate App Server processes. Both use the same
model constraints and task contract. Each invocation gets a fresh temporary
working directory and conversation. The campaign still runs through
`BenchmarkRunner`, with sequential timed trials and alternating arm order.
Historical configurations retain their original behavior.

A temporary worker requests a named permission profile with minimal system reads,
access to its own workspace, optional access to the exact selected skill file,
and no network. The adapter checks that the host acknowledges the requested
profile, working directory and non-escalating approval settings. Supporting tools
remain separately reviewed. A matching profile acknowledgement does not establish
complete tool isolation.

Run the harmless CLI filesystem checks without starting a model:

```bash
PYTHONPATH=src python3 -m aeep.assessment.conformance --codex /absolute/path/to/codex --output /new/path/worker-filesystem.json
```

Add `--sessions` to check two empty App Server sessions as well. This can start
host-owned servers while collecting inventory, but never starts a model. Session
results retain acknowledged permissions even if a later inventory check fails.

The probe gives each worker a local canary, checks its own read/write access, and
checks that reads and writes into the other worker's directory are denied. It
stores booleans, return codes, profile and source/executable digests. It does not
read authentication files, modify global configuration, or invoke installed
plugin tools. Output files are created exclusively to preserve older evidence.
`AEEP_CODEX_EXECUTABLE=/absolute/path/to/codex python3 -m pytest tests/test_v08_workers.py`
runs the same installed-host boundary check alongside offline worker regressions.

This report verifies only the CLI filesystem profile. It does not prove network
isolation, App Server enforcement, or the model's complete callable tool set.
Scoped model trials remain blocked until tool restrictions can be verified.
Tool advertisements and absence of observed calls cannot fill that gap.

`aeep assess --manifest PATH budget PLAN_ID` shows candidate/baseline worker
profiles, screening turns, full-trial turns and remaining allowances. Eight
screening cases require 16 turns when both arms use one model turn per case;
141 cases require 282 before setup, warm-ups and retries. More worker processes
do not reduce total model work. Existing grants and usage counters are retained.

Read the [assessment testing policy](ASSESSMENT_TESTING.md) before changing or running
assessment, execution-adapter or release-verification work in this repository.

## Incremental-capability revision

Use the [testing policy](ASSESSMENT_TESTING.md) for the capable shared environment,
qualification/value/catalog stages and four-arm evidence rules. The CLI accepts
`propose --experiment FILE` for an explicit reviewed experiment and shows its
required trial allowance. `workbook-definition` exports the fourth recipe;
`define`, `prepare-recipe` and `generate-cases` use the existing controlled path.
`amend-budget` is operator-only and preserves the current grant counters.

The complete authenticated four-family onboarding journey remains unfinished. See
[the incremental status](../reports/v08/incremental-status.md) for remaining code
and live gates. Existing manifests, schema-8 records and legacy tools continue to
use their original contracts. Rollback revokes new scoped use while preserving
evidence and feasible baselines. Restore a pre-upgrade database backup before
using an older binary; do not rewrite historical records or lower its schema tag.

### Timing and protected login

A reviewed `--pilot-policy FILE` proposal runs eight timing cases through the
normal campaign engine. Read `pilot-timing REPORT`, then propose the full main
campaign with `--pilot-report REPORT`. This preserves pilot costs and excludes
its inputs from holdout; it never lowers acceptance thresholds or changes a grant.
The new v6 main plan can apply the calculated deadline while keeping the rest
of each primary implementation unchanged. Review the new mapping and obtain
conformance for its exact task profile. Old timing records cannot authorize
that profile. Historical v5 plans keep their original rules.

Protected Codex sign-in uses `signin-worker REQUEST` in the operator's own
terminal after scope approval. Login output stays with Codex and the operator.
Setup uses the existing allowance and does not establish conformance. Follow the
[testing runbook](ASSESSMENT_TESTING.md#protected-worker-sign-in) for the exact
limits and the subsequent worker checks.

For post-login checks that do not need model turns, use
`prepare-worker-inspection SOURCE_REQUEST`, review the resulting exact definition,
then `inspect-worker REQUEST`. The operator-only command inspects the existing
worker and runs a fixed harmless sandbox command. Its report does not approve
an environment or candidate. See [the testing policy](ASSESSMENT_TESTING.md#turn-free-post-login-inspection).

Four-arm local-search setup requires `search_roots` in the inert
`incremental-routes` definition. These are explicit coordinator roots the operator
will review; omitted roots block proposal export. Each invocation reads only its
selected case root and stages a bounded private tree through the worker transport.
The task prompt receives `/workspace/case-tree`, the query and relative path;
no coordinator root or file contents are included. Paths that attempt to escape
that tree remain task inputs for correctness testing. Unsafe source trees fail
before model execution. The legacy `local_search_tree:1` prompt mapping retains
its original semantics.

The operator can prepare a combined protected-worker inspection with
`aeep assess prepare-pair-inspection CONTROL_SOURCE TREATMENT_SOURCE DEFINITION`
and run its two reviewed requests with
`aeep assess inspect-pair CONTROL_REQUEST TREATMENT_REQUEST`. The JSON definition
uses `assessment.worker-pair-inspection.v1`; the generated requests use conformance
request v3. Preparing a bundle is inert. Execution uses the original grant and
counters, fixed bounded probes and no model turns. Passing observations retain
per-probe event lineage; they do not create conformance or admission authority.
App Server's `command/exec` runs sandboxed commands without creating a model turn;
the probes retain the configured policy rather than overriding it.
[OpenAI App Server documentation](https://learn.chatgpt.com/docs/app-server).
