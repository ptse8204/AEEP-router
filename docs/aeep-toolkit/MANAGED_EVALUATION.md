# Compare a skill through an existing AEEP assessment

New comparisons are paused by the [complete-stack gate](STACK_COMPLETION.md).
`run` now requires `--stack-readiness` with current canonical completion evidence.
A separate `--engineering-review` permits only an exact bounded required-use
qualification check; it cannot resume optional-use/value trials. Existing grant,
disclosure and worker controls still apply. Report export does not run tasks.

This optional backend connects a reviewed controlled-agent skill plan to the
existing AssessmentService and BenchmarkRunner. It uses their workers, grants,
receipts, graders and recovery. Agent-skill-eval remains the scripted backend;
its tested Codex contract gaps and this fallback choice are recorded in D40.

Use [named workflow configurations](STACK_DELIVERY.md) to bind and select these
same plan/source files through the Toolkit CLI. That interface delegates to the
commands below; it introduces no runner or additional execution authority.

The managed path requires a reviewed repository checkout because existing
assessment evidence binds its executable source. It does not prepare a new
experiment, sign in, amend a grant, install a skill or replace worker conformance.
The first implementation accepts skill comparisons with a frozen incremental
experiment. Other candidate types and workflow normalization remain unsupported.

## Review without effects

Export the existing canonical AssessmentPlan JSON through the assessment workflow.
Supply a SourcePin JSON with repository, revision, artifact_sha256,
license_expression and data_rights. For this adapter, artifact_sha256 is the
canonical SHA-256 of the inspected subject's complete dependency_digests map.
The candidate's reviewed SKILL.md hash must also occur in that map. Repository
and license attribution are operator-supplied assertions, not proof of ownership.

```bash
PYTHONPATH=src python3 -m aeep_toolkit eval managed plan \
  --plan /absolute/reviewed-plan.json \
  --source /absolute/reviewed-source.json
```

This command reads the supplied files and source hashes. It creates no Router,
database, output directory or host process. Its review digest binds the exact
plan, source association and adapter implementation. It cannot establish that a
grant is current, that a budget remains, or that worker conformance passes.

## Inspect a pinned ExtractBench workflow

An ExtractBench pack can select the original document, JSON schema and
instructions for each task through the ordinary workflow. The worker
archive retains `instruction.md`, `environment/document.pdf` and
`environment/schema.json`. Grading uses the protected native score
recipe and reads the worker's `output.json`.

Run `aeep-toolkit workflow plan --workflow WORKFLOW --configuration NAME`
against the exact workflow file. Its preview lists the selected tasks
and pending rights and setup. Canonical preparation requires reviewed
asset-use records, the exact recipe and case set, and a bound runtime.
The [CFPB preflight](../../reports/toolkit-v2/c13/completion-20261116/extractbench-ordinary-pack-preflight.json)
shows the three currently staged inputs. Their native grading remains
pending.

## Prepare a formal native-score document cohort

Use the pinned ExtractBench pack to stage one public archive and print its
formal task descriptor. Create the destination as a dedicated directory
for public ZIP files.

```bash
aeep-toolkit benchmark stage-document --pack PACK.json --root PACK_ASSETS \
  --task TASK_ID --family CASE_FAMILY --destination PUBLIC_ZIPS
```

The descriptor binds the exact pack, document, instructions and ZIP by
hash. The worker's reviewed `assessment_adapter` uses
`input_transform: document_archive:1` and the public ZIP directory as its
sole `read_only_roots` entry. Its existing artifact transport uses
`task_archive_b64` as the input field and `output.json` as the output
filename. The adapter loads the current task's public bytes when its
worker starts. Keep the references and verifiers in the protected grader
image.

A formal recipe uses `assessment.recipe-extension.v8` and
`curated_document:1`. Put each descriptor in the `input` field of its
`generator_config.cases` entry. Set `split` to `qualification`, `training`
or `holdout`, and set `template_family` to the reviewed source family.
Use 8, 28 and 105 cases respectively. The case `family` is the reviewed
variation label. The source family groups related documents and stays
within one split. Keep the independent and transformed grader fixtures
outside the holdout.

Define and review the recipe with `aeep assess define` and
`aeep assess review`. Use the existing `prepare-recipe`, `generate-cases`
and `propose --case-set` commands. Select the resulting canonical plan
in the workflow. Review the grader, exact asset-use scope and grant
before execution. The preview reserves one reference call per native-score
case, including the protected fixtures. Formal case materialization
creates no native grade on its own.

## Run the existing plan

After reviewing that exact binding and the existing assessment authority:

```bash
PYTHONPATH=src python3 -m aeep_toolkit eval managed run \
  --plan /absolute/reviewed-plan.json \
  --source /absolute/reviewed-source.json \
  --manifest /absolute/aeep.yaml \
  --reviewed-digest REVIEW_SHA256 \
  --output /absolute/new-private-report
```

The service directory defaults to `.aeep/assessments` beside the manifest;
`--directory` selects an existing assessment directory when necessary. Execution
reuses enqueue/run and their existing job identity. A denied grant, changed
source, cancelled job or uncertain operation is never repaired by resetting
allowances or retrying a model call. Run and report use ordinary assessment-store
initialization; only the file-based plan command promises zero mutations.

The output directory must be new. It is created with owner-only access. Its
operation record stays incomplete when execution, normalization or export is
interrupted. The canonical assessment remains the source of incurred costs and
recovery state even if file export fails.

## Inspect the result

The directory contains normalized evidence, canonical analysis references,
receipt accounting, a descriptive summary and HTML/Markdown reports. The readable
reports state how many trials could be normalized and list gaps. Auxiliary arms
and unresolved costs remain in the complete canonical campaign and operation
ledger; primary-arm tables do not replace that accounting.

Keep screening, training and holdout results separate when making a value claim.
Protocol token counts retain their receipt provenance. Complete
`provider_report/self_asserted` usage can appear in descriptive tables while
remaining unavailable to the strict observed/verified utility. A count being
present does not establish verified token savings. Native metric names and
preflight checks are described in [worker readiness](WORKER_READINESS.md).

Missing host identity, task-prompt digest, current conformance or receipt binding
produces an explicit gap. Missing token categories remain unknown. A timeout or
execution failure is not a failed independent grader. Only recorded, matching
grader results supply pass/fail. Invocation and exposure remain unknown unless
observed; installed candidate files are not a substitute.

To regenerate exports from a completed canonical report without dispatching:

```bash
PYTHONPATH=src python3 -m aeep_toolkit eval managed report \
  --plan /absolute/reviewed-plan.json \
  --source /absolute/reviewed-source.json \
  --manifest /absolute/aeep.yaml \
  --report-id EXISTING_REPORT_ID \
  --output /absolute/another-new-private-report
```

Normalization requires the same source revision as the recorded campaign.
Historical reports keep their original bindings. A local digest check is not a
signature or independent attestation. The descriptive report does not adjudicate
live efficacy or close the release gate; the original assessment analysis remains
available alongside it. Synthetic tests of this adapter establish software
behavior only, even when their fixture records simulate native-host metadata.

## Canonical analysis in the readable report

HTML and Markdown also show the existing assessment verdict, distinct holdouts,
paired-case counts, uncertainty intervals, utility guardrails, challenger results,
condition-specific comparisons and operation costs. The bridge recomputes these
statistics from the retained campaign and rejects mismatches. The service's
explicit incomplete-preparation-cost downgrade remains unknown.

Expected positions come from the frozen suite, including its conditions and
repetitions. Missing, unexpected and duplicate positions and unresolved operations
remain visible. Per-task descriptive slices use the case's template family. Their
current contract rejects repetitions it cannot pair; the separate canonical
analysis retains the established repeated-case analysis.

A canonical service verdict is not an independent attestation or release approval.
The descriptive summary remains `NOT_ASSESSED`. Resource break-even uses from the
assessment are separate from a plugin-price scenario and never imply billed-cash
savings. The original `python3 -m aeep_toolkit.managed` entry point still works.

For source-archive tasks, use the separately reviewed
[repository suite mapping](REPOSITORY_EVALUATION.md#prepare-real-repository-test-suites).
It reuses the existing single-file artifact bridge; a suite definition alone
does not establish worker conformance, qualification or comparative usefulness.
For standard repository patch artifacts, budget preview and dispatch require
the worker's output field to match every scheduled task's plain or gzip codec.
Use separate matching profiles for mixed encodings. Incompatible definitions
fail before model-turn reservations; existing decoder meanings stay unchanged.
