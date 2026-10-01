# Live workbook timing pilot

All 16 assigned task runs completed. Control passed 8/8 correctness checks; the
Spreadsheets-enabled treatment passed 0/8. All returned workbooks successfully.
This exploratory result is not qualification or a savings claim.

| Arm | Correct | Median task wall time |
| --- | --- | --- |
| control | 8/8 | 49.7 seconds |
| treatment | 0/8 | 77.0 seconds |

The fixed pooled p95 was 101.42 seconds, yielding a 203-second normal deadline.
Incorrect outputs remain in the timing calculation. The candidate was available
optionally; retrieval and invocation telemetry remain unobserved. These results
do not establish why the treatment failed or general plugin reliability.

[Immutable report](workbook-pilot-report.json), [timing calculation](workbook-pilot-timing.json),
[validated summary and ledger](workbook-pilot-result.json), [approval](workbook-pilot-execution-approval.json).

No candidate was activated. The original grant has 276 turn allowances and
2,203.74 seconds remaining. Required-invocation qualification is a separate
experiment with fresh cases; the main four-arm program needs expanded resources.
