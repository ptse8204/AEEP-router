# Managed Sol comparison stopped during Sales Pivot

The approved [dispatch review](sol-dispatch-review.json) `bd939ed7`
passed all 88 authenticated probes across eight workers. Both workers
for each task denied access to the collector. The run stopped after
the first Sales Pivot control turn. The worker adapter returned
`worker_artifact_failed` during workbook retrieval, before protected
grading. The receipt preserves the failure category. The exact
retrieval reason cannot be recovered from the retained evidence.

| Task | Control score | Treatment score | Paired token delta | Agent wall time |
| --- | --- | --- | --- | --- |
| Sales Pivot | Unknown | Unstarted | Unavailable | Control 154.54 s |
| Excel in PowerPoint | Unstarted | Unstarted | Unavailable | Unavailable |
| Canopen 613 | Unstarted | Unstarted | Unavailable | Unavailable |
| Xsdata 1126 | Unstarted | Unstarted | Unavailable | Unavailable |

The Sales Pivot control receipt captured 150,671 input tokens,
including 109,696 cached input tokens, and 5,580 output tokens.
The receipt also records 345 reasoning output tokens and zero cache
write input tokens. These are provider-reported fields from a failed
trial. The capture status is partial and there is no matched treatment.
There are zero completed pairs and no candidate-value or selection
conclusion.

The [reconciliation](dispatch-outcome.json) checks the trial database,
receipt, event journal and operational ledger. The 12 settled
operations include eight worker inspections, two router setups, the
proxy lifecycle and one model turn. The ledger charges 210.99 operation
seconds and $0 cash. Its time total includes both workers' overlapping
inspection intervals. The exact expiry-only amendment took effect.
The two earlier reservations are unchanged. The worker was removed,
the proxy was restored to stopped, and seven turns remain unstarted.

The shell wrapper used zsh's read-only `status` variable after the
driver exited. The driver's retained report, trial receipt and
reconciled ledger establish the result independently of the wrapper.

Before further live work, verify the exact workbook handoff offline
and make artifact failures report a bounded cause code. The next review
must explicitly authorize any further live turn. Keep the original
task, grader and stop rule intact.
