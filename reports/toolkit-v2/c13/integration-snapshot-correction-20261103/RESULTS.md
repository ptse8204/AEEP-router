# Controlled evaluator journeys completed

Both selected engines completed the same public Markdownify task with protected
grading. Each scored **1 (binary pass)** with zero retries and confirmed worker
cleanup. This demonstrates the evaluator bridge, not capability usefulness or
selection usefulness. Comparisons remain paused.

| Engineering journey | Score | Input tokens | Cached input | Output tokens | Reasoning output | Agent seconds | Grading seconds |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Real agent-skill-eval scheduler and graders | 1 | 128,909 | 111,232 | 1,444 | 68 | 49.341 | 2.091 |
| Explicitly selected managed engine | 1 | 190,532 | 145,920 | 1,647 | 39 | 63.996 | 2.037 |

Cached input is included in input; reasoning output is included in output. These
are provider-reported quantities whose receipt/journal consistency passed, not
independently verified provider metering. Cash measurement remains unavailable.
The two runs are engineering checks of one task, not paired usefulness trials;
no token, time or monetary savings claim follows from this table.

The [read-only completion audit](completion-audit.json) binds every score to its
canonical plan, trial, independent grader, receipt and execution journal. Both
runs positively recorded instruction loading. Semantic invocation remains unknown;
the separate full-catalog-delivery field remains false. Neither field is rewritten
to improve the result.

## Reports and actual upstream behavior

- [ASE engineering report](unstarted-engines/ase-uri-report/report.html): actual
  agent-skill-eval 0.7.0 scheduler and JSONPath grader drove controlled dispatch.
  The upstream process receipt is
  `a6e59aa8e1c26e7d7a4fc136a7430c50f5eaf6936fd563e6b7ffc50c24e68704`.
  Its scheduler summary records one pass, zero failures and zero skips.
- [Managed engineering report](managed-unstarted/result-managed/report.html):
  the separately selected existing engine completed its normal CLI export.
  No automatic evaluator switch occurred.

Native upstream Codex harness behavior remains unsupported. The working ASE path
uses AEEP's reviewed controlled-worker bridge. Neither report closes the complete
stack gate or either SkillsBench domain journey.

## Failures retained, without task replay

The initial preparation attempt reused an immutable scope identifier from an
older plan and stopped before any engine/model execution. A recorded delegated
correction gave each unstarted plan a unique scope identifier. No scope or
allowance was overwritten.

The completed ASE trial then exposed a report-only defect: a repository URL was
rejected by the legacy task-family identifier field. Its original failed export
remains. [The read-only adapter](report-uri-family.py) encoded the family label
one-to-one, retaining the original in
[the source map](unstarted-engines/ase-uri-report/source-family-map.json).
Canonical task bytes, grading, receipts and trial records were unchanged.
The managed definition received the same metadata-only encoding before its first
trial; its ordinary export passed. No task was replayed to repair reporting.

The managed controller subsequently failed while hashing an already written
evidence bundle. The completed job, grading and ordinary report survived; the
read-only audit reconciled them. All controller failures and partial costs remain.
The two successful model turns exhaust this review's two-turn allowance.

## Verification, accounting and retained resources

All thirteen source checks passed on
`cfc36a2aeda4e220046722dbdbc81fbf2376deb12b9f7266abdab81bddcec9e1`:
2,052 tests /21 skips in both full runs,82.63% combined coverage and both branch
gates. Fresh eleven-probe worker checks, collector denial and ordinary CLI
readiness consumption passed on that source. No source suite was replayed after
execution.

The [installed package check](package-execution/summary.json) passed with wheel
`b182d50675a0debd572f99d1d4204835372697c04c5c25f5d7c38618df4a8e51`
and 32 unchanged cached dependencies. Its private runtime is retained. The cached
offline docs check passed on attempt one; [the exact 72 checked inputs](completed-docs-snapshot.json)
were preserved before later progress-note edits. Later prose is outside that
completed check's scope.

The original cumulative envelope used **57 operations, two model reservations
and 234.26983733428642 grant seconds**, within144/2/6,200 and $0 cash authority.
Grant seconds are not whole-session elapsed time or complete product overhead.
The current ledger is13,718 operations /3,798 turns /125,509.3967908104 seconds.
Both pre-existing unresolved reservations remain; no new operation is unresolved.

The exact proxy is stopped. SDK and package runtimes, all images, volumes,
historical results and unrelated edits remain. No build, download, new dependency,
credential access, admission, activation, publication or release occurred.

## Remaining delivery work

Fix URI-family serialization in the ordinary reporting adapter without weakening
its legacy contract. Continue SkillRank's controlled bridge and concrete retained
runtime preparation, and complete the other upstream integrations independently.
SkillsBench asset rights, reviewed runtimes, protected reference/counterexample
checks and both ordinary CLI domain journeys remain open. Waza still requires a
supported backend subscription the operator does not currently have.

Stack integration, candidate usefulness, selection usefulness, resource
qualification and release remain separate, open gates. No additional model turn
is authorized by this completed bundle.
