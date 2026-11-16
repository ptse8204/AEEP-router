# Delegated Sol comparison results

The subagent ran all eight planned control and treatment slots on
GPT-6.1 Sol at medium reasoning. Seven produced protected grades.
Three tasks have complete matched pairs. Sales Pivot's treatment
timed out. The [machine-readable result](comparison-continuation-result.json)
retains raw token categories, grader times and receipt references.

| Task | Control score | Treatment score | Δ input tokens | Δ output tokens | Agent time control / treatment | Δ agent time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Sales Pivot | 0/1 | Ungraded, timeout | Unavailable | Unavailable | 173.32 s / 300.63 s timeout | Unavailable |
| Excel in PowerPoint | 1/1 | 1/1 | +27,748 | +104 | 47.42 s / 57.23 s | +9.82 s |
| Canopen 613 | 0/1 | 0/1 | −14,148 | +302 | 83.38 s / 87.02 s | +3.63 s |
| Xsdata 1126 | 0/1 | 0/1 | −8,494 | −1,137 | 107.67 s / 88.56 s | −19.11 s |

Deltas are treatment minus control. Agent wall time excludes the
separately recorded protected grading interval. Token deltas use
matched provider counts verified against the corresponding event
journal and receipt. The provider's internal meter was not
independently measured.

The [Sales handoff repair](SALES_HANDOFF.md) restored the previously
verified workbook path and output checks in both arms, preserving the
task and immutable grader. The replacement control delivered a
296,189-byte workbook and received its verified grade. The fixed
300-second limit ended treatment before artifact delivery. Its
[timeout receipt and settlement](sales-treatment-timeout.json) retain
partial provider counts and elapsed time. No treatment score or
matched difference is available.

Scores were identical in the three complete pairs. Excel's treatment
loaded the Spreadsheets instructions implicitly. Native loading or
invocation of LibCST was unverified on both software tasks. These
single development pairs establish observed outcomes for the tested
settings. They do not establish capability or selection usefulness.

The [repair review](sales-handoff-continuation-review.json) authorized
one additional charged turn to replace the failed Sales control
under the operator's direction to repair and finish the study.
The [remaining-slots review](remaining-three-review.json) reused
the six unchanged worker and collector proofs, preserved the
timed-out Sales treatment and sent only the six untouched slots.
All charges from [the initial run](RESULT.md) remain in the ledger.

Total recorded costs were 46 settled operations, nine charged model
turns, 1,197.25 summed operation seconds and $0 cash. The proxy was
restored to stopped. No new unresolved reservation remains, and the
two older reservations were preserved.
