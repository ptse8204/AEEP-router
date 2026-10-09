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
PYTHONPATH=src python3 -m aeep_toolkit.managed plan \
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
PYTHONPATH=src python3 -m aeep_toolkit.managed run \
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

Missing host identity, task-prompt digest, current conformance or receipt binding
produces an explicit gap. Missing token categories remain unknown. A timeout or
execution failure is not a failed independent grader. Only recorded, matching
grader results supply pass/fail. Invocation and exposure remain unknown unless
observed; installed candidate files are not a substitute.

To regenerate exports from a completed canonical report without dispatching:

```bash
PYTHONPATH=src python3 -m aeep_toolkit.managed report \
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
