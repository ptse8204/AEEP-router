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

By default, cash and break-even remain unknown. To inspect resolved receipt
accounting, add `--accounting receipts.json --currency USD`. The file maps each
receipt content digest to its complete receipt JSON. The command checks those
hashes and uses existing AEEP cash resolution. It rejects shared receipts or
charges across runs, missing retry receipts and workflow summary receipts.
Incomplete, estimated, conflicting or different-currency accounting stays unknown.
Hash consistency does not authenticate the source or billing provider.

Cost per verified success includes failed-run costs. It is unavailable with zero
successes, missing grades or incomplete price coverage. For an explicit scenario,
add `--recurring-fee fee.json`, containing a decimal-string `amount`, a `period`
of `month` or `year`, and a 64-character hexadecimal `source_ref`. The currency
is the selected report currency. This records a supplied price assumption; it
does not verify a developer's price or create a charge.

Break-even divides that fee by the observed difference in cost per verified
success, rounded up to whole successes per fee period. It requires a complete
matched cohort, positive difference and no observed success regression. It assumes
the same future task mix and success rates, excludes evaluation overhead, and
is not a confidence-supported production forecast. Source records marked synthetic
remain synthetic throughout these calculations.

Confidence intervals and overall value verdicts still require the existing
reviewed analysis. Evaluation overhead remains separate in that path. This
increment does not complete C05's comparison-analysis acceptance checks.

The controlled development fixture now supplies a stronger, separate path:
`integrations/toolkit/verify_controlled.py` resolves each trial's receipt, redacted
selection decision, durable execution events, independently graded output and
operation accounting. It checks all expected positions from the plan frozen before
dispatch and recomputes existing AEEP `fit_report`. Its generated HTML/Markdown
reports remain explicitly synthetic. The two-case suite returns insufficient
evidence with the existing qualification thresholds unchanged. General live
campaign binding and the remaining economics acceptance cases are still open.
