# What the paired repository failures show

Both arms failed the same five tasks. These are protected-test failures on completed task artifacts. The two earlier controller-censored cases remain outside this analysis.

| Task | Ordinary / optional skill | Remaining bug tests in the two artifacts | Preservation failures in the two artifacts |
| --- | --- | --- | --- |
| AbsaOSS__generate-release-notes-207 | FAIL / FAIL | 14, 14 | 0, 0 |
| canopen-python__canopen-613-declared-tests | FAIL / FAIL | 2, 2 | 0, 0 |
| jpadilla__pyjwt-1040-declared-tests | FAIL / FAIL | 1, 2 | 0, 0 |
| lincolnloop__goodconf-51-aeep-contract-audit | FAIL / FAIL | 0, 0 | 2, 2 |
| tefra__xsdata-1126-issue-behavior-audit | FAIL / FAIL | 1, 1 | 0, 0 |

The two counts in each cell are unordered. Existing observer logs lack a direct trial/arm reference, so this diagnosis does not assign partial progress to a specific arm. Canonical pass/fail verdicts remain independently bound to their trials. Detailed test identities and observation hashes are in [the data](retained-failure-analysis.json).

Partial fixes can differ even when both artifacts fail. They do not satisfy the frozen task-success endpoint and cannot be promoted to a demonstrated benefit after seeing the results. Failure identities alone do not reveal why the model chose a repair or whether skill text influenced it.

The supported selection decision is to keep the ordinary baseline for this tested scope: optional Ponytail has no observed success gain, and neither format group establishes resource savings. This is an evidence-bound non-admission, not a claim that the skill has no value on other work. AEEP has not yet demonstrated a positive live selection benefit.

No new models, graders, installations or resource-qualification tests were run for this analysis.
