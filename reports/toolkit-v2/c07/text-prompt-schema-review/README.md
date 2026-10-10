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

The campaign is active. Read `qualification-result.json` when present, otherwise
inspect the existing job `assessment_f4520c24bfc04ecca66e34ec7c67cd30` without
restarting it. The runner owns proxy restoration and cleanup. Do not alter source
while it runs or replay its request. Screening receipts initially passed schema
and task validation and included token fields; this is not a terminal verdict.

The full software checks run concurrently. These qualification timings are not
comparative performance evidence. Task outputs, credentials and expected answers
are not saved in this report directory.
