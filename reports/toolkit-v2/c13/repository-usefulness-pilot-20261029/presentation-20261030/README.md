# Task scores and token differences

The [comparison report](../comparison.html) now shows the frozen task score and
reported token difference for each task. It adds the two arm totals, absolute
differences and percentages for each format condition. JSON and CSV retain all
five raw token fields and the canonical trial/receipt references.

The task score is the existing binary endpoint: one for a protected-grader pass,
zero for failure. Both arms scored 14/19 (73.68%). No partial-credit rubric was
declared for this experiment. Supplemental test logs cannot supply one: their
observations lack direct arm references, so partial results remain unordered.
The two engineering-censored tasks have unknown scores and tokens in this view;
they are excluded from the task-performance denominator. Their charges remain.

The token metric retains the original analysis's input-plus-output definition.
Difference is treatment minus control; percentage divides that difference by
control. Cached input, cache writes and reasoning output remain separate fields.
All completed task pairs and the both-successful subset appear separately. Plain
and gzip conditions remain separate. Neither has 20 successful measured pairs,
so these descriptive numbers do not establish confidence-supported savings or
regression. Provider meter accuracy and monetary savings remain unverified.

The [read-only check](canonical-check.json) reopened all 38 canonical trials,
receipts and final journals. Capture chains, independent grades and raw usage
match the retained analysis. Grant counters and the implementation source digest
are unchanged. No model, grader, installer or container ran.

The original [HTML](original-comparison.html) and [Markdown](original-comparison.md)
are byte-preserved snapshots; their links retain their original relative context.
The original analysis, generators, thresholds and admission records are unchanged.
Do not rerun those historical execution/analysis drivers to refresh this view.
Presentation updates read the retained analysis and canonical records only.

This presentation does not complete the assembled-stack, candidate-usefulness
or selection-usefulness gates. The [stack audit](../../stack-delivery-20261030/README.md)
records each integration's actual scope and remaining work.

The [presentation check](presentation-check.json) compares JSON, CSV and HTML
values and local links. Changed report documentation and all configured active
documents pass Markdownlint. Full `make docs-check` still needs the absent
Lychee 0.24.2 tool. Browser policy denied local-file navigation; no visual browser
verification is claimed. See [verification notes](verification-notes.json) for
the exact scope and preserved diagnostics. Product source did not change.
