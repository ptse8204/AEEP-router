# Text qualification with the reviewed prompt-schema option

This run checks the adapter correction after the
[response-schema failure](../text-task-review/README.md). Both existing workers
select `adapter_options.output_schema_mode: prompt`. Their recipe, independent
grader, model/effort, permissions and immutable images remain unchanged. The
default adapter behavior remains structured output.

Source digest: `d05541e90d2e200ba1ea61b4169a8ebcdf62fd96217fdbe35a81e42accd4d1b0`.
[Focused checks](focused-checks.json) passed 132 synthetic tests. The
[actual paired inspection](pair-result.json) passed all 11 probes per worker,
confirmed cleanup and restored the proxy. The [boundary record](boundary-result.json)
binds those observations to the current profiles.

[Qualification review](qualification-execution-review.json) uses the existing
September 25/27 authority and original grant. It freezes a new plan and seed,
with at most 141 model turns and no automatic retry. Required candidate exposure
checks correctness; it cannot demonstrate optional choice or benefit.

The [completed campaign](qualification-result.json) passed all 141 cases, including
105 distinct holdouts, with no correctness or execution failures. All expected
trial positions are present. The proxy returned to its prior stopped state and
source stability passed. The [toolkit report](report/report.html) normalized all
141 trials without gaps.

The canonical value verdict remains `insufficient_evidence`: there are no control
pairs in this qualification. Token fields retain provider-reported provenance;
they do not satisfy independently observed resource coverage. Billed cash,
subscription units and whole-host resource totals remain unknown.

The full software checks ran concurrently. These qualification timings are not
comparative performance evidence. Task outputs, credentials and expected answers
are not saved in the exported report. The separately stored reviewed plan retains
its protected fixture definitions and is not a public evidence export.
