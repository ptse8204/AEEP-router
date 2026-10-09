# Inspect normalized evaluation evidence

Use the local report command to see which supplied runs can be paired and which
measurements are missing. It reads one C02 evidence bundle and writes JSON,
Markdown or HTML to standard output. It starts no evaluator or service.

From the repository root, inspect the recorded synthetic demonstration:

```bash
PYTHONPATH=src python3 -B -m aeep_toolkit report \
  --evidence reports/toolkit-v2/descriptive-report-showcase/toolkit-evidence.json \
  --format markdown
```

Use `--format json` for the complete structured summary or `--format html` to
redirect a standalone page to a new file. Reports use no remote scripts, fonts
or telemetry. The development stack also generates `toolkit-summary.json`,
`toolkit-summary.md` and `toolkit-summary.html` beside each new fixture report.

Runs are grouped by exact plan, candidate, adapter, host/version, model, effort,
shared environment, verifier, experiment mode and evidence kind. Task families
stay separate. An observed pair needs one run in each arm, the same prompt,
optional invocation and observed candidate exposure. Missing or repeated arms,
unresolved execution and retries remain visible as rejected pairs. Repetitions
have no pairing index in the current contract; the report cannot guess one.

Each arm shows execution and grading counts. Token totals respect explicit cache
and reasoning overlap semantics. Unknown categories do not become zero. Timing
and token summaries distinguish a known subtotal from a complete total and show
measurement coverage, medians and maxima in JSON. Agent, verification and setup
times stay separate. JSON also includes descriptive differences for measured
pairs; these do not override task failures or establish benefit.

The verdict is always `NOT_ASSESSED`. This command validates record structure,
not the referenced receipts, worker conformance, grading evidence or expected
case list. A complete pair missing from the supplied bundle is undetectable.
Use the development stack's separate `verify` command to resolve its fixed
synthetic receipt/artifact records before inspecting them.

Confidence intervals, actual billing, recurring fees, cost per verified success
and break-even remain unknown. The existing reviewed assessment reporting and
accounting path must supply those conclusions; a reference to a record is not
an observation. Synthetic and replay results cannot establish real model value.
This increment does not complete C05's comparison-analysis acceptance checks.

The controlled development fixture now supplies a stronger, separate path:
`integrations/toolkit/verify_controlled.py` resolves each trial's receipt, redacted
selection decision, durable execution events, independently graded output and
operation accounting. It checks all expected positions from the plan frozen before
dispatch and recomputes existing AEEP `fit_report`. Its generated HTML/Markdown
reports remain explicitly synthetic. The two-case suite returns insufficient
evidence with the existing qualification thresholds unchanged. General live
campaign binding and the remaining economics acceptance cases are still open.
