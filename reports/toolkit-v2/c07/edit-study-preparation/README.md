# Three-family editing study preparation

This first-party recipe adds the task families required for the live study without
adding a new evaluator. It uses AssessmentService's existing executable-recipe
contract, managed workers and separate grader.

- Easy: replace a literal in one file while preserving another matching file.
- Multi-file: rename Python identifiers across three files while preserving
  comments, strings, whitespace and an unrelated notes file.
- Adjacent: count log lines while preserving every file.

The multi-file family is a bounded mechanical refactor. It does not represent
arbitrary repository debugging. Returned Python remains inert text; the grader
compares artifacts without executing them.

[Offline checks](checks.json) cover three independent literals, 141 generated
cases, deterministic/disjoint seeds and 566 rejected artifact mutations. The
[contained check](contained-result.json) ran the generator, independent tokenizer
reference and grader in the existing offline image: 141 reference agreements,
141 accepted correct outputs and 141 rejected empty outputs. These are software
fixture results, not model outcomes. Seeds 7 and 8 are excluded from live work.
The initial definition failure (missing description and cash-evidence fields)
is preserved separately; the corrected definition passed validation.

The [preregistration](preregistration.json) records family limits, counts,
seeds, utility, arms and stop rules. Both actual task profiles passed all 11
boundary probes and cleanup; the proxy returned to its stopped state. The
[qualification proposal](qualification-review.json) freezes plan
`plan_0a8359a155184098ad3ba790f8a77f55`, with 141 model turns and 105 distinct
holdouts. It has no configuration blockers and has **not** been enqueued.

[Storage preflight](storage-preflight.json) measured a 7,356,416-byte scoped
snapshot. The 285-copy allowance, including the existing 64 MiB per-copy margin,
requires 74,909,696,000 free bytes to preserve 50 GiB. Only 61,896,175,616 bytes
were available: a 13,013,520,384-byte shortfall. This is a conservative execution
allowance, not a prediction of actual consumption. Do not reduce it merely to
make the campaign fit. The pending exact older-fixture cleanup may cover it;
recheck capacity and the fresh snapshot after any approved cleanup.

Once capacity fits, the prepared runner uses execution-review SHA-256
`98f878a69f511d9da151c3416e04cf73f2be35a51d4574b64a8fd35fca7ab81c`.
It has a one-shot start marker, the existing service's stop rules, a 51 GiB
storage guard and proxy restoration. Review records retain the exact grant and
source. No new model, credential, cash or installation authority is inferred.
This qualification cannot establish optional-use value; its subsequent four-arm
plan needs separate reusable-tool lineage and fresh holdouts.
