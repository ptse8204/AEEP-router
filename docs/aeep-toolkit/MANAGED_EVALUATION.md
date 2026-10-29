# Compare a skill through an existing AEEP assessment

This optional backend connects a reviewed controlled-agent skill plan to the
existing AssessmentService and BenchmarkRunner. It uses their workers, grants,
receipts, graders and recovery. Agent-skill-eval remains the scripted backend;
its tested Codex contract gaps and this fallback choice are recorded in D40.

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
