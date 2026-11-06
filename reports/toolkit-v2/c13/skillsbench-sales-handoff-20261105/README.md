# Sales Pivot workbook handoff correction

The [review](operation-review.json) keeps the original task inputs,
worker images, artifact size limit and protected grader. The new
instructions map the task's original absolute paths to the exact
workspace paths and require a file check before the completion
message. The prior receipt identified the handoff stage. The
[offline check](../skillsbench-sales-artifact-diagnostic-20261105/result.json)
proved the carrier can return a workbook-sized payload.

The approval covers one fresh Sales worker pair and one required-use
engineering turn through the ordinary CLI. Spring's passing result
is retained. The prior Sales attempt remains ungraded and charged.

## Observed result

The [ordinary CLI run](result.json) delivered a 267,664-byte workbook.
The protected verifier scored it **0/1**. Artifact handoff and grading
completed, and the task failed. The verifier's binary score and receipt
were retained. Per-assertion details were absent from the retained trial.

The provider reported 273,093 input and 5,440 output tokens. The journal
and receipt matched all five captured categories. The agent took 146.77
seconds, and protected grading took 2.47 seconds. No retry ran inside the
new plan. The proxy stopped and all charges settled. This is a single
required-use engineering run, without a paired baseline.
