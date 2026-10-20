# Token capture and candidate-use correction

All 564 token captures match their original terminal execution journals and receipts. No model was rerun.

This verifies capture consistency. OpenAI’s reported token quantities remain independently unverified; the original inconclusive verdict is unchanged.

| Holdout arm | Captures verified | Median reported input | Median reported output | Mean reported input difference, ordinary minus arm |
|---|---:|---:|---:|---:|
| higher_compute | 105/105 | 8162 | 82 | 0.0286 |
| optional_candidate | 105/105 | 8373 | 82 | -210.9048 |
| ordinary | 105/105 | 8162 | 82 | 0.0000 |
| reusable_tool | 105/105 | 8162 | 82 | 0.0476 |

Cached input is included in input; reasoning is included in output. Do not add them to the parent totals.

Candidate use was not collected in this completed study. The collector was disabled, and the router previously discarded its snapshot. The corrected implementation retains bounded snapshots and can verify a positive instruction-loading event against the exact skill and execution journal. Missing events stay unknown; instruction loading does not prove semantic use or causal benefit.

The paired counts above are descriptive. They do not replace the frozen strict-token utility gate or establish savings.

Source evidence: capture-audit.json, execution-journals.json and receipt-records.json in this directory. Original comparison files are unchanged.
