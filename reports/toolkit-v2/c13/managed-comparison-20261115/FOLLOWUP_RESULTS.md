# Sales Pivot follow-up and software diagnosis

The subagent completed a fresh matched Sales Pivot pair on GPT-6.1 Sol
at medium reasoning. Both arms used a 480-second deadline and the same
conditional hint for the existing local Node dependency path. Task inputs,
worker images and the protected grader stayed fixed. The
[exact review](sales-window-review.json) and
[receipt audit](sales-window-audit.json) bind the conditions and evidence.

| Arm | Protected score | Input tokens | Output tokens | Agent wall time |
| --- | ---: | ---: | ---: | ---: |
| Control | 0/1 | 214,063 | 6,419 | 169.80 s |
| Spreadsheets treatment | 0/1 | 602,911 | 9,980 | 283.06 s |
| Treatment minus control | 0 | +388,848 | +3,561 | +113.26 s |

The unchanged verifier rejected both delivered workbooks. The treatment
loaded the Spreadsheets instructions implicitly. Library invocation remains unknown. The [canonical result](sales-window-result.json)
retains all measured token categories, separate grader times and receipt
references.

The [earlier timeout](SALES_RUNTIME.md) remains a separate 300-second
observation. The treatment completed a command at 295.49 seconds and
had no final response or workbook when the deadline expired. The
offline probe reproduced a separate import issue in the task workspace
and verified a workspace-local link to the existing cached runtime.
The historic trace cannot establish which command or issue consumed
the most time. The new treatment finished within 300 seconds under the
revised conditions. The effect of the larger deadline on completion
remains unknown.

The [software audit](SOFTWARE_OUTCOMES.md) verified that both Canopen
arms and both Xsdata arms delivered valid patches and reached the
protected grader. All eight required Canopen test identities and all
29 Xsdata identities were present. The retained failure reason was
`test_failure` in every arm. Per-test statuses and patch bytes were
transient. LibCST was available in both treatments. Actual invocation
or import remains unknown. The audit used zero software replays.

The new Sales pair settled 11 operations and two model turns at $0.
Cumulative accounting is 57 operations, 11 charged turns, 1,674.49
summed operation seconds and $0 cash. This includes the original Sales
handoff failure and treatment timeout. The proxy was restored to its
exact stopped state. The two historical reservations were preserved
and no new reservation remains open. The follow-up runner settles a
verified, cleaned-up attempt before interpreting grade and token evidence.
