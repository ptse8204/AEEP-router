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

All thirteen source gates are running on
`cfc36a2aeda4e220046722dbdbc81fbf2376deb12b9f7266abdab81bddcec9e1`.
The [verification record](verification/checks.json) is authoritative. Source is
frozen while it runs; unrelated CI edits remain preserved outside these commits.
The new verification is required because snapshot authority code changed. It
adds no benchmark or model observations.

Next: finish source verification, retain the new wheel and source inventory, and
prepare a grouped current-source continuation. Reuse the retained corrected image;
no image build is needed. Bind fresh worker evidence and the two unstarted model
turns, with the original cumulative ceiling and all fourteen charged operations
preserved. Inspect canonical previews before either engine; do not enlarge the
review or reset counters if the remaining allowance cannot fit.

The old wheel/docs and SDK evidence keep their source scope. Any changed installed
artifact or fresh engine attempt needs applicable review. Candidate usefulness,
selection usefulness, both SkillsBench journeys, complete stack integration,
resource qualification and release remain open. Comparisons stay paused.
