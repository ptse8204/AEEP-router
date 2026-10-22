# Repository usefulness and selection evaluations

The next comparison should tell an operator whether adding a capability helps
with repository maintenance, and whether AEEP chooses it on tasks where it helps.
This plan is for the implementation coordinator. It does not authorize execution
or claim that the cohort is ready.

## Source and present status

Use the public SWE-rebench issue pool as a candidate source, with its real base
commits, repair patches, tests and test identities. Keep the existing
`AssessmentService`, `BenchmarkRunner`, controlled workers and receipts. The
agent-skill-eval managed-host fallback remains in force; this is a benchmark pack,
not another evaluation engine.

The source is `nebius/SWE-rebench-leaderboard`, revision
`34d5a58864acf91613740a09ec5d205228dcfa39`, licensed CC-BY-4.0. Its versioned card
requires respecting the underlying repositories' licenses. The recommended
SWE-rebench harness fork is MIT licensed at
`980d0cca8aa4e73f1d9f894e906370bef8c4de8a`.
The exact public URLs and response hashes are in the JSON records here.

The deduplicated `test` split contains 860 unique issue IDs from 413 repositories.
Monthly splits are parts of that union, not extra tasks. Seven extra rows share
a repository/base-commit origin with another row. Forty-seven tasks have no
PASS_TO_PASS identities, so they do not by themselves establish regression
preservation. Only 112 declare Python 3.13 or 3.13.1; other tasks need an explicit
runtime compatibility decision and check before adoption. None is adopted yet.
There are no frozen holdouts.

Do not assume that a split name is its chronology. One observed `2026_03` task
has a May 2026 creation timestamp. Public, recent tasks also do not establish
absence of model training contamination.

SWE-bench Verified is not the default corpus: OpenAI documented contamination
and test-quality problems for frontier evaluation. This does not disqualify every
task, but it prevents treating its name as sufficient validity evidence.
[Primary explanation](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/).

## Work that must precede model turns

1. Run the exact offline upstream compatibility review in
   [the development pack](../rebench-grader-20261022/README.md), once approved.
   It checks real tests against unchanged, published-repair and broken-repair
   source. It is not qualification. Both inspected task IDs are excluded from
   all later holdouts.
2. Complete the repository-pack adapter using that result. The current v4
   callable-snapshot grader cannot run arbitrary repository suites. The pack
   must safely import pinned source, accept only reviewed source edits, protect
   test configuration and oracle files, bind test identities and runtime, and
   fail on missing, skipped, errored or unverifiable required results. Reuse the
   existing recipe/attempt/grading paths. Do not silently enlarge their input,
   timeout or output bounds. Any needed versioned contract change precedes the
   cohort freeze and gets its own source verification.
3. Curate a licensed, reproducible workload. Validate exact dependency closures,
   baseline failures, published-repair successes and preservation tests before
   selecting a task. Predeclare exclusions and strata before model outcomes.
   Keep public issue text and base source apart from gold patches and protected
   tests in worker inputs. No generic editable install or repository installer
   is authorized by metadata inspection.
   Review embedded agent instructions and configuration as untrusted source;
   freeze the same applicable instructions in both arms and expose no host setup.
4. Freeze source-disjoint stage assignments, worker definitions, candidate pin,
   generated challenger, stronger compute baseline, utility dimensions and stop
   rules. Use the existing 8 screening, 28 training and 105 holdout structure.
   Preserve the minimum 100 distinct qualification holdouts and all other
   existing scientific thresholds. Do not fill counts with renamed fixtures or
   repeat a task from development, qualification or training as a new holdout.
5. Run fresh applicable worker conformance, then qualification and comparative
   usefulness through the ordinary managed assessment path. Candidate use is
   required only in qualification and optional in value trials. Freeze the
   reusable challenger from training inputs before its holdout. Materialize and
   review the actual operation count and finite budget before any model run.

The development check uses the full Loguru source tree, its actual selected test
module, and exact upstream parsing/resolution functions. Its adapted pytest
version does not establish equivalence to the official upstream image. A broad
production adapter and a reproducible cohort remain engineering work after that
check. Passing a three-variant check alone cannot make them complete.

## Workload coverage

Include bounded single-file regression repair and changes that propagate across
modules or public interfaces. Add separate, source-grounded contract audits where
the correct action can be no change. SWE-rebench's nonempty FAIL_TO_PASS sets are
repair tasks; relabeling some as negative controls would be misleading. Independently
curate audit controls with passing protected tests and reviewed preservation scope.
Keep their authored-control provenance visible.

Group related issues, shared base commits and repositories when splitting and
estimating uncertainty. The same issue, copied snapshot, repair or oracle cannot
appear on both sides of a stage boundary. Source availability inside the shared
agent environment is an exposure risk to inspect, not evidence of independent
competence. Prefer tasks whose solution is not already in that environment.

Report results by repository and task family. The primary usefulness question is
verified task success; wall time and provenance-qualified token counts supplement
it under the existing utility policy. Missing categories remain unknown. Neither
subscription usage nor a test receipt supplies monetary savings.

Bind token captures to actual turns and canonical receipts, preserving provider
trust levels and cached/reasoning-category semantics. Require the existing minimum
fully measured pairs before a resource-benefit claim. Capture actual skill
loading and generated-tool invocation against their frozen identities. Catalog
availability does not prove use; missing events are unknown unless capture
completeness is established. Loading instructions does not prove semantic
contribution. The historical missing measurements remain missing.

## Selection evaluation follows usefulness evidence

Freeze policy definitions before a separate selection cohort. Compare a credible
fixed task-family dispatch learned from training, discovery without comparative
value information, and AEEP's evidence-based policy. Use the same physical
capabilities, model, shared runtime, task inputs, permissions and common execution
instrumentation. Freeze the policy differences explicitly. An actual AEEP route
decision must bind the current task; an ideal hand-authored selector is not AEEP.

Determine task-specific usefulness labels from independent earlier evidence.
The historical Ponytail comparison is INCONCLUSIVE and cannot label Ponytail
useful, useless, or a correct abstention on every new task. If no positive value
is demonstrated, report that limitation and test admission restraint. Do not force
a positive label to make a selector comparison possible.

Record useful choices, missed applicable value, ineligible choices, unnecessary
choices, abstentions and unknown value separately. Independently grade the tasks
after selection, and include decision overhead. An always-abstaining policy must
show its missed useful choices when such evidence exists. A complete descriptive
decision matrix does not itself establish a statistically supported selection
benefit. Use the existing controlled three-way assessment and analysis paths for
the prospective task-outcome comparison.

## Resource qualification stays separate

Observe task size, test duration, model work and coordinator/worker overhead on
the selected workloads. Distinguish whole-host baseline, ordinary task execution
and assessment overhead. Do not call Docker-client CPU or RSS container usage.
Choose operational acceptance targets from these workloads and expected usage
before the resource holdout. Existing storage, permission and execution limits
remain binding safety constraints. The earlier proposed production latency and
memory budgets remain unaccepted hypotheses.

## Current intervention

Only the exact six-call upstream development review needs an execution approval
now. No infrastructure choice, credential access, model run, new image or paid
service is requested. The human control response remains pending separately.
Release and publication remain unauthorized.
