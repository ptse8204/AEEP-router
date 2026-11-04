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

Managed exports preserve existing task-family identifiers. Other labels, including
repository URLs, receive deterministic identifiers; `task_family_labels` retains
their original text in the detailed evidence and summary. Readable reports show
both. Encoding cannot merge distinct families, even when an original identifier
resembles an encoded label. Canonical tasks, scores and receipt references do not
change. Earlier exports retain their original bytes and source scope.

Each arm shows execution and grading counts. Token totals respect explicit cache
and reasoning overlap semantics. Unknown categories do not become zero. Timing
and token summaries distinguish a known subtotal from a complete total and show
measurement coverage, medians and maxima in JSON. Agent, verification and setup
times stay separate. Matched measurements show control and treatment means,
mean and median differences, and the relative mean difference when the control
mean is positive. Both means use the same measured pairs. A zero control mean
leaves the relative difference unknown. Reports also show the verified-success
difference in percentage points and observed/absent/unknown candidate-use counts.
These observations do not override task failures or establish benefit.

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

Confidence intervals and overall value verdicts come from the existing reviewed
analysis, which the managed backend now includes and verifies as described below.
Evaluation overhead remains separate from task-run costs.

The controlled development fixture now supplies a stronger, separate path:
`integrations/toolkit/verify_controlled.py` resolves each trial's receipt, redacted
selection decision, durable execution events, independently graded output and
operation accounting. It checks all expected positions from the plan frozen before
dispatch and recomputes existing AEEP `fit_report`. Its generated HTML/Markdown
reports remain explicitly synthetic. The three-case user journey returns insufficient
evidence with the existing qualification thresholds unchanged. The managed backend supplies canonical inferential reporting; current live
worker qualification and the V2 comparative study remain open.

A stopped controlled fixture also produces a partial report when its receipt
store remains writable. It lists missing expected positions and unresolved
operations, keeps unknown grading results unknown, and preserves prior charges.
The verifier checks its immutable completion record before accepting a partial
result. A failed reporting write leaves the original exception and receipt store
for inspection. There is no automatic retry.

New controlled runs also export `comparison.json` using the C02 comparison
contract. Its references resolve to the canonical bundle, frozen plan and AEEP
analysis. The verifier checks the exported bytes and those references. A scripted
run with observations is `INCONCLUSIVE` about real value; a stopped run with no
observed trial is `NOT_ASSESSED`. The readable report shows the engineering
comparison status separately from the unassessed real-model value. Earlier
artifacts retain their original format and evidence meaning.

## Missing native token measurements

New Codex App Server receipts retain the exact supplied token-field names in
`codex_token_fields`. Missing categories leave accounting partial; legacy numeric
defaults are not observations. A missing final snapshot leaves the final field
list empty while retaining earlier raw counts as partial evidence. Unknown model
identity likewise preserves known raw counts without inventing model accounting.
Historical receipts retain their original bytes and source bindings. The toolkit
must not infer zero usage from an older receipt without field-level evidence.

The [managed backend](MANAGED_EVALUATION.md) now includes canonical assessment
intervals, guardrails, measurement coverage, costs and trial-position coverage in
HTML/Markdown. It reproduces retained statistics and costs before exporting.
Missing measurements and incomplete cost lineage remain unknown; its recorded
service verdict is separate from the descriptive summary and release readiness.

For local sharing, use the [minimized export preview](README.md#prepare-a-local-sharing-preview).
It publishes nothing and omits private identifiers; aggregates and digests can
still identify a study. It does not elevate a supplied record's trust tier.
