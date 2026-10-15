# Training-built text baseline

The candidate-absent builder received only the completed qualification's 28
training inputs and task contract. It returned [source](generated-source.py.txt)
and [usage](generated-usage.txt) in one existing-model call. Its
[result](builder-result.json) confirms proxy restoration and unchanged source.
All costs remain on the original grant. No generated code has executed.

Static review found two semantic differences from the independent reference:
bare requested labels are ignored, and the tool trims both ends of values.
These are findings to retain, not reasons to alter the frozen grader or silently
repair the tool. A reusable baseline may offer an imperfect optional tool; its
actual training results must be disclosed before later experimental use.

The [exact execution review](generated-tool-execution-review.json) was approved;
[the approval record](../../integration-completion/operator-approval-continuation.json)
binds its unchanged hash. Execution is blocked by available storage. It uses AssessmentService and BenchmarkRunner to compare
28 training cases against the independent reference in the existing offline
container. It includes no holdouts, model calls, credentials or installation.
The full automatically generated proposal stays inert; only the separately
recorded 28-case plan is eligible. No request may be replayed after it starts.

The builder execution-review summary incorrectly listed 808 reserved seconds.
The actual reviewed planner timeout was 600 seconds, its call reserved 605,
and proxy lifecycle reserved 600: 1,205 seconds in total. Actual measured
operation time was 60.92 seconds, within both totals and the existing grant.
The exact planner definition, reservations and original review are preserved;
this correction does not alter costs or claim a new authorization.
