# Preserve integration task preparation in scoped snapshots

Finite integration plans can now prepare their selected grader without losing
their original task-set dependency. The snapshot resolver accepts only the exact
content-addressed integration set bound by a v7 or v8 plan and its matching
request ID. Unrelated sets and legacy records with the same name stay outside
the snapshot. Older plan and materialization meanings are preserved.

The previous [actual check](../worker-readiness-correction-20261103/RESULTS.md)
passed image, worker readiness, installed-wheel and offline-docs checks. Its
engine phase stopped before any grader, upstream scheduler or model invocation:
the resolver had no integration-set preparation case. All costs and terminal
records remain; no successful component is replayed here.

Twenty-three focused snapshot/foundation tests pass. The corrected first-party
constructor also [accepts the actual stored plan](constructor-result.json),
retains only its selected integration set and leaves the real grant unchanged.
This check creates and removes one owned temporary database; it dispatches no
executor and establishes no new worker qualification.

All thirteen source gates passed on
`cfc36a2aeda4e220046722dbdbc81fbf2376deb12b9f7266abdab81bddcec9e1`.
Both full runs passed 2,052 tests with 21 skips. Combined coverage is82.63%,
and both required branch gates pass. The [verification record](verification/checks.json)
is authoritative. Unrelated CI edits remain preserved outside these commits.
The new verification is required because snapshot authority code changed. It
adds no benchmark or model observations.

The exact tested source is retained in a [private local inventory](source-snapshot.json),
including the unrelated CI edits excluded from this feature commit. The new wheel
is `b182d50675a0debd572f99d1d4204835372697c04c5c25f5d7c38618df4a8e51`;
its 32 dependency wheels are unchanged. Installation and execution are unstarted.

Next: obtain approval for the [grouped current-source continuation](operation-review.json). Reuse the retained corrected image;
no image build is needed. Bind fresh worker evidence and at most the two unstarted model
turns, with the original cumulative ceiling and all fourteen charged operations
preserved. The remaining130 operations cannot promise both worst-case previews
simultaneously: each engine must fit after prior actual costs settle. If it does
not fit, preserve the unstarted phase; never enlarge the ceiling automatically. Inspect canonical previews before either engine; do not enlarge the
review or reset counters if the remaining allowance cannot fit.

The old wheel/docs and SDK evidence keep their source scope. Any changed installed
artifact or fresh engine attempt needs applicable review. Candidate usefulness,
selection usefulness, both SkillsBench journeys, complete stack integration,
resource qualification and release remain open. Comparisons stay paused.

After the exact approval is recorded, run `run.py REVIEW_SHA256` in this directory,
then `run-components.py --component package --execute-approved REVIEW_SHA256` and
the corresponding `--component docs` command. Inspect started/result files before
any invocation. Component retries are not implied. Successful old components
retain their old scope and are not replayed.
