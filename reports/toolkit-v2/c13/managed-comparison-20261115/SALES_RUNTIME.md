# Sales Pivot timeout diagnosis

The original treatment was still working when its 300-second deadline
expired. It completed a command at 295.49 seconds on the adapter clock
and recorded 25 tool calls. The control recorded 11. The treatment reached
the deadline before returning a final answer or a turn-completion event,
so no workbook reached the protected grader. Its native catalog snapshot
reported a positive implicit Spreadsheets instruction load. The timeout
journal is incomplete and this observation does not establish use of the
artifact-tool library. The receipts retain neither the command text nor
the durations of individual commands.

The [offline worker probe](check_sales_runtime.py) reproduced a separate
module resolution problem. A clean workspace could not resolve
`@oai/artifact-tool` through a bare ESM import in either image. The
package was present only in the treatment image under the existing
launcher-installed runtime fallback. A workspace-local `node_modules`
symlink to that immutable dependency tree allowed treatment to export a
synthetic XLSX and the same worker reopened it successfully with openpyxl.
Control still had no candidate package. The [probe
result](sales-runtime-offline-evidence.json) records zero model turns,
no network or credential mounts, and cleanup of both disposable workers.
This establishes a reproducible setup issue. The earlier timeout's
retained metadata cannot establish that module resolution caused it.

The [new exact review](sales-window-review.json) binds a fresh matched
480-second pair on the two existing worker images. Both prompts include
the same conditional hint about the existing local module path. Use of
the candidate stays optional. Inputs, output contract, grader, model,
reasoning effort and sandbox stay fixed. The earlier 300-second attempt
and all incurred charges stay in the ledger.

Both fresh runs delivered readable workbooks. The unchanged protected
grader scored both 0/1 with `upstream_rejected`. Control used 214,063 input
tokens and 6,419 output tokens in 169.80 seconds. Treatment used 602,911
input tokens and 9,980 output tokens in 283.06 seconds. The treatment
used 388,848 more input tokens and 3,561 more output tokens and took
113.26 seconds longer. The treatment journal verifies implicit
Spreadsheets instruction loading. It contains no direct record of
library invocation.

The [canonical result](sales-window-result.json) and [receipt and ledger
audit](sales-window-audit.json) bind both verified grades and token
captures. The fresh pair settled 11 operations, two model turns and
477.24 summed operation seconds at $0 cash. The proxy returned to
stopped. Both earlier outstanding reservations remain and no new
reservation is unresolved.
