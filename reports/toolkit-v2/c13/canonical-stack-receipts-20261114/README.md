# C13 readiness from retained receipts

The ordinary CLI accepts 33 of 39 checks across 16 of 19 entries in the
managed ledger. Registration adds exact evidence definitions and reviews.
A before-and-after audit verified that every existing ledger row, grant,
operation and reservation was preserved. Comparisons remain paused.

- **Langfuse and OpenTelemetry.** The Excel trial's minimized OTLP payload
  matches the settled private export. The transport receipt identifies a
  Langfuse queue acknowledgement. Independent readback verifies the linked
  trace and span. A separate wrapper receipt verifies export disablement.
  These give both telemetry components two accepted checks each.
- **Reused integrations.** Managed AEEP, SkillRank, SkillsBench, MCPMark,
  MCP-Universe, ToolHive, LangGraph, Agent Framework, EvoAgentX, AFlow,
  optional Router and Sponsors use their original version pins and
  canonical receipts. The checks apply to the recorded engineering runs.
  LangGraph recovery was within its retained runtime. The MCP packs each
  have one reviewed reference task. The ToolHive stop verdict verifies the
  terminal container state even though the stop command reported a timeout.
- **Composed workflows.** Sales Pivot and Spring Boot keep their original
  0/1 and 1/1 protected grades, reports and independent trace readbacks.
  Their earlier transport statuses stay as recorded. The Excel
  acknowledgement separately supplies both telemetry components' checks.

The [managed registration](registration-result.json) lists the exact
component references. The [readiness snapshot](stack-status.json) gives the
39 check statuses and evidence references. The [reuse audit](reuse-audit.json)
gives the original checkout fingerprints and upstream versions for the
accepted component records. These definitions apply to the observed working
tree, which includes pre-existing CI dependency and test edits. Those edits
contribute to the source fingerprint and remain outside this commit.

## Remaining checks

| Component | Current gap | Next action |
| --- | --- | --- |
| Cisco Skill Scanner | Docker's executable changed since the successful static scan. | Run one approved scan on the retained image and validate its new receipt. |
| agent-skill-eval | macOS replaced the launcher since the successful controlled scheduler run. The retained scheduler runtime still matches its tree fingerprint. | Verify the current launcher with a first-party native boundary check. Join that receipt to the historical controlled scheduler evidence without replaying its model turn. |
| Waza | Native client bootstrap and the offline text grader passed. The supported backend still needs operator sign-in and a live grade. | Use the [protected operator sign-in guide](../waza-native-backend-20261104/operator-setup-20261113/README.md), then review the real backend check separately. |

The [paired local review](boundary-review.json) covers Cisco and
agent-skill-eval. The [preflight](boundary-preflight.json) and
[copied-ledger accounting check](boundary-accounting-preflight.json) passed.
The review expires November 15 at 8:22 p.m. Vancouver time. Execution
requires the operator's repeat approval. Stack completion remains open.

## Verification

The [source checks](source-verification.json) passed. Both full runs passed
2,156 tests with 21 skips. Combined line and branch coverage was 81.43 percent,
and both branch coverage gates passed. The wheel and source distribution built.
The [committed source smoke check](committed-source-check.json) verified the
CLI entry point and generated schemas.
The prior [offline docs retry](../canonical-stack-verification-20261114/docs-pipe-result.json)
passed on its 72 pinned documents. This update carries those results at their
original input scope.

The [copied-ledger check](copied-ledger-result.json) validated all 16 accepted
entries through the ordinary CLI. Unreviewed records count for zero checks.
The controls rejected mismatched components, source drift, unknown exports,
forged transport, readback and disablement, changed observation bytes, and a
revoked exact review.

For the retained host, set `LEDGER` to the canonical ledger path and use a
fresh output directory:

```bash
folder=reports/toolkit-v2/c13/canonical-stack-receipts-20261114
PYTHONPATH=src python3 -B "$folder/prepare-receipt-records.py" \
  --store "$LEDGER" .aeep/receipt-records-copy-check
PYTHONPATH=src python3 -B "$folder/register-receipt-records.py" \
  --store "$LEDGER" --evidence .aeep/receipt-records-copy-check \
  .aeep/receipt-registration-copy-check
```

The preparation step reads existing assets and ledgers. The second step uses
a copy by default. Previously reviewed records remain reviewed when copied.
