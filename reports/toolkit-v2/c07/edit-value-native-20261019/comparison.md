# Four-arm editing comparison

Canonical verdict: INCONCLUSIVE (insufficient_evidence). No automatic admission or candidate activation occurred.

This completed study contains 564 real Codex task runs on bounded synthetic recipes: 32 screening, 112 training and 420 held-out arm runs. The holdout contains 105 distinct cases, 35 per family, assigned to all four arms. The separate required-use qualification passed 141/141 tasks including 105 disjoint holdouts.

Task correctness and runner wall time are measured. Token counts below come from protocol reports with provider_report/self_asserted provenance; their coverage is shown. They are excluded from strict observed/verified utility. The formal verdict retains the original token guardrails; this report cannot establish verified token savings or monetary savings.

## Held-out results for all four arms

| Arm | Verified success | Median wall seconds | Median reported input tokens | Median reported output tokens | Reported input/output coverage | Trusted input coverage |
| --- | --- | --- | --- | --- | --- | --- |
| Ordinary agent | 105/105 | 8.94 | 8,162.00 | 82.00 | 105/105 | 0/105 |
| Optional Ponytail | 105/105 | 8.75 | 8,373.00 | 82.00 | 105/105 | 0/105 |
| Higher effort | 105/105 | 9.00 | 8,162.00 | 82.00 | 105/105 | 0/105 |
| Optional generated tool | 105/105 | 8.79 | 8,162.00 | 82.00 | 105/105 | 0/105 |

Wall time includes routing and preflight; independent grading is measured separately. Medians in this table describe the assigned runs. They do not replace paired confidence bounds. Cached input is included in input; reasoning is included in output. Unknown categories stay unknown.

## Task-family results

| Family | Arm | Verified success | Median wall seconds | Median reported input tokens | Median reported output tokens |
| --- | --- | --- | --- | --- | --- |
| edit:adjacent | Higher effort | 35/35 | 8.06 | 8,124.00 | 75.00 |
| edit:adjacent | Optional Ponytail | 35/35 | 7.97 | 8,336.00 | 75.00 |
| edit:adjacent | Ordinary agent | 35/35 | 8.21 | 8,124.00 | 75.00 |
| edit:adjacent | Optional generated tool | 35/35 | 7.86 | 8,124.00 | 75.00 |
| edit:easy | Higher effort | 35/35 | 8.29 | 8,162.00 | 80.00 |
| edit:easy | Optional Ponytail | 35/35 | 8.15 | 8,373.00 | 80.00 |
| edit:easy | Ordinary agent | 35/35 | 8.21 | 8,162.00 | 80.00 |
| edit:easy | Optional generated tool | 35/35 | 7.98 | 8,162.00 | 80.00 |
| edit:multi_file | Higher effort | 35/35 | 10.55 | 8,241.00 | 256.00 |
| edit:multi_file | Optional Ponytail | 35/35 | 10.79 | 8,452.00 | 256.00 |
| edit:multi_file | Ordinary agent | 35/35 | 10.81 | 8,241.00 | 256.00 |
| edit:multi_file | Optional generated tool | 35/35 | 10.58 | 8,240.00 | 256.00 |

Easy cases edit one literal while preserving another file. Multi-file cases rename Python NAME tokens across three files while preserving comments, strings, whitespace and notes. Adjacent cases count matching log lines without changing files. Seven template variants per family do not establish arbitrary repository debugging or general programming competence. Returned Python is inert data; its exact artifact is checked without executing it.

## Frozen paired analysis

| Comparison | Dimension | Distinct measured pairs | Paired estimate | Corrected interval |
| --- | --- | --- | --- | --- |
| Optional Ponytail vs ordinary | input_tokens | 0 | unknown | unavailable |
| Optional Ponytail vs ordinary | output_tokens | 0 | unknown | unavailable |
| Optional Ponytail vs ordinary | task_success | 105 | 0.00% | 0.00% to 0.00% |
| Optional Ponytail vs ordinary | wall_time_ms | 105 | 0.79% | -4.61% to 6.52% |
| Higher effort vs Ponytail | input_tokens | 0 | unknown | unavailable |
| Higher effort vs Ponytail | output_tokens | 0 | unknown | unavailable |
| Higher effort vs Ponytail | task_success | 105 | 0.00% | 0.00% to 0.00% |
| Higher effort vs Ponytail | wall_time_ms | 105 | 0.43% | -7.58% to 4.60% |
| Generated tool vs Ponytail | input_tokens | 0 | unknown | unavailable |
| Generated tool vs Ponytail | output_tokens | 0 | unknown | unavailable |
| Generated tool vs Ponytail | task_success | 105 | 0.00% | 0.00% to 0.00% |
| Generated tool vs Ponytail | wall_time_ms | 105 | 1.03% | -4.64% to 7.19% |

Positive resource estimates favor the first arm; negative estimates favor the second. Task success uses percentage-point gain. These are the unchanged canonical hierarchical paired intervals, with correction across dimensions and comparators at family error rate 0.05. Admission needs a confidence-supported 10% resource benefit or five-point success gain, no more than 10% regression on other declared resource guardrails, complete evidence and no dominating feasible challenger. Missing trusted token intervals remain missing. Family tables above add no new admission tests.

## Optional access, failures and verification

Candidate exposed fields in held-out receipts: {"None": 105}. These recorded fields are distinct from causal benefit.

Candidate retrieved fields in held-out receipts: {"None": 105}. These recorded fields are distinct from causal benefit.

Candidate invoked fields in held-out receipts: {"None": 105}. These recorded fields are distinct from causal benefit.

Generated-tool files were verified in the immutable worker image. Its actual invocation is not separately instrumented; candidate-discovery fields on auxiliary arms do not measure generated-tool use. All assigned cases are included regardless of invocation.

| Phase | Assigned arm runs | Verified passes | Failed or unknown verification |
| --- | --- | --- | --- |
| Screening | 32 | 32 | 0 |
| Training | 112 | 112 | 0 |
| Holdout | 420 | 420 | 0 |

All 564 canonical positions matched retained original receipts and source/cohort/conformance bindings. The standard managed export normalizes 282 primary trials; this supplement verifies the 282 auxiliary trials with the same existing receipt verifier and their exact frozen executor definitions. No canonical mapping, evidence trust or verdict is changed.

## Study costs and limits

2836 unique canonical operations are included in the supplemental editing-study ledger; 0 have unresolved duration. Known charged operation seconds: 9,924.50. These lifecycle intervals overlap, so their sum is not elapsed study wall time.

The ledger includes linked preparation, failed readiness/profile predecessors, qualification, builder, training, image operations, the cancelled 46-run pre-holdout value attempt and post-report cleanup. The original grant and incurred counters were retained. This is not the cost of every historical experiment in the repository.

One initial public nonroot metadata diagnostic lacked advance reservation. Its retained tool wall measurement was 0.112110291 seconds. It is recorded separately, not relabeled as pre-reserved. Engineering time and whole-host CPU, memory and energy are incompletely measured. Subscription consumption and a zero cash ceiling do not establish a dollar saving or verified break-even.

## Exact stack and study scope

This study reuses the existing AEEP AssessmentService and BenchmarkRunner fallback selected in D40. agent-skill-eval 0.7.0 remains the tested scripted upstream path; its pinned Codex launch/usage contract remains unqualified. Waza mock and LangGraph fixture conformance are separate engineering evidence and supply no live benefit claim here.

Candidate: https://github.com/DietrichGebert/ponytail at 1d95ff7d39de12d87014ea40d4e22201bddc501b. Ponytail 4.10.0 SKILL.md SHA-256: 1316a2f3f95741d2300b116fe0c2d81ce4a9568656ed0a62643f54aaf09957f2. Source rights are recorded as MIT assertions; developer ownership is not attested.

Host versions: aeep-agent-router/0.154.0 (Debian 13.0.0; aarch64) unknown (aeep-agent-router; 0.8); model: gpt-6-astra. Ordinary, candidate and reusable arms use medium effort; higher-compute uses high effort and twice the 203-second task timeout. All four task prompts match. Workers are distinct and fresh; future cases, grader answers and shared writable state remain outside trial workers.

Generated source SHA-256: 3360c74f1be036ba1e61ceb1ba3cf362d7258c11dbd2cbde5d7672fe4e38e2f6. It was built from the original 28 qualification training inputs and task contract before holdout, never expected outputs or candidate source. Its 28/28 training diagnostic on Python 3.13 does not establish general compatibility with the usage text's requested Python 3.11.

## Permissions, stop and recovery

The exact reviews authorize the frozen workers/tool and finite model turns on the existing subscription grant, with a cash ceiling of zero and no new destinations. Codex owns authentication; the implementation agent did not inspect, copy or return its contents. No global installation, hosted telemetry, publication or release occurred. The study never admits the candidate automatically.

The campaign is terminal. Its driver stopped the task-owned proxy and restored its prior stopped state; the approved 512 MiB/no-swap cap remains. No assessment dispatch is active for this completed plan. Generated images and evidence are retained; their deletion needs a separate exact cleanup decision. The current AEEP package, Waza and LangGraph test runtimes were removed by their recorded installation checks.

For a future active assessment, the existing assess cancel command stops subsequent dispatch; a cancellation does not prove an in-flight effect was absent. Inspect canonical status and retained receipts before the existing assess recover operation. Never rerun a started driver, reset a grant or delete uncertain state. Ordinary routing continues independently of assessment workers. Private installation removal uses its exact installation record and reviewed digest; preserve changed environments and unrelated configuration.

## Evidence and remaining acceptance

Plan: plan_017bce61874c437296c66276e91876d6; report: fit_1dc2c008986c4096bbf0f23b7ce05e16; executable source: d05541e90d2e200ba1ea61b4169a8ebcdf62fd96217fdbe35a81e42accd4d1b0. Hashes bind local evidence; they are not signatures or independent attestation. Human comprehension, broader platform claims and publication require their own evidence or authorization.

- [Verified managed export](report/report.html)
- [All four arms and receipt references](all-four-evidence.json)
- [Supplemental cost ledger](study-accounting-ledger.json)
- [Cost scope and source hashes](accounting-scope.json)
- [Frozen plan](plan.json)
- [Exact execution review](value-execution-review.json)
- [Analysis plan](analysis-plan.json)
- [Terminal cleanup](value-result.json)
