# C13 completed workflow evidence

`aeep-toolkit workflow evidence` validates an existing managed run against its
named configuration. It resolves the frozen plan, original trial and protected
grade, settled accounting, and the HTML and Markdown reports. It attaches the
reviewed runtime lifecycle and receipt-linked telemetry. `stack-verify record`
registers the resulting definition. The regular assessment review and
`stack-status` apply the current-source and compatibility checks.

| Configuration | Completed task | Protected score | Current checks |
| --- | --- | --- | --- |
| Document/data | Sales Pivot Analysis | 0/1 | `ordinary_cli`, `canonical_report` |
| Software engineering | Spring Boot/Jakarta Migration | 1/1 | `ordinary_cli`, `canonical_report` |

The [managed registration](registration-result.json) accepted both records.
The [readiness snapshot](stack-status.json) accepts 4 of 39 required checks.
Neither operation counts nor assessment grants changed. The selected
configuration receipts verify setup and readiness. The removal result comes
from the separately installed disposable Sales configuration. Both records
keep the original transport failure, verified Langfuse readback and verified
disablement as separate facts.

The [document/data record](document-data-record.json) and
[software record](software-engineering-record.json) include each report hash,
original source, trial receipt, raw token categories and recorded timing. Scope
is the completed engineering runs, including the Sales task failure. No task
was replayed. No token difference or usefulness conclusion follows from
comparing these distinct tasks.

## Reproduce the copied-ledger check

Set `LEDGER` to the path to the retained managed SQLite ledger. The request
files refer to retained runtime, report and receipt assets on the original host.

```bash
PYTHONPATH=src python3 -B \
  reports/toolkit-v2/c13/canonical-stack-verification-20261114/check-workflow-evidence.py \
  .aeep/workflow-evidence-check --store "$LEDGER"
```

The script copies the ledger into a new directory and also copies both reports.
The [copied-ledger result](copied-ledger-result.json) verifies review gating,
mismatched transport and report rejection, missing readback, changed HTML,
an interrupted job, source drift and revocation. The application reads the
original attempt and lifecycle stores without changing them. A change to the
checkout fingerprint or required evidence invalidates the reviewed binding.

The tested working tree includes separately preserved CI dependency/test edits.
Those inputs contribute to the checkout fingerprint and are outside this feature
commit. The recorded evidence applies to that observed checkout. Current
package verification and docs have separate input bindings.

All 13 [source checks](source-verification.json) passed. Both full runs
passed 2,156 tests with 21 skips. Branch coverage was 82.19
percent and both branch gates passed. The wheel and source distribution
built, and the offline wheel smoke verified the CLI entry point. The
[docs repeat](docs-review-summary.json) is bound to the revised guide and state.

## Remaining checks

The [reviewed Excel receipt check](langfuse-review-summary.json) is the
remaining live test of acknowledgement parsing. The Sales and Spring readbacks already substantiate
their recorded ingestion. Waza still requires
[protected operator sign-in](../waza-native-backend-20261104/operator-setup-20261113/README.md)
and a supported backend grade. The remaining component evidence, stack
assembly and comparison authorization are still open. Comparisons stay paused.
