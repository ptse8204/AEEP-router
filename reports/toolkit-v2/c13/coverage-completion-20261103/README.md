# Finish source coverage, then verify the scanner and retained wheel

The ordinary CLI scanner and corrected-wheel checks remain unstarted. This
review permits only the interrupted branch-coverage run and downstream checks,
then carries forward those two original component attempts. Comparisons stay
paused. There are no new application changes, dependencies or model calls.

The approved `6265bd49` run passed the full regression suite: 2,021 passed and
21 skipped. Its coverage run stopped after 1,539 passes when net host free space
dropped by 1.25 GiB. The smallest sampled free space was 61.88 GiB, above the
normal 50 GiB reserve. No failing test caused that interruption. Raw logs, partial
coverage, controller samples and all old charges remain. A copy of the partial
coverage database is bound in this review.

The completion restores the normal 50 GiB actual usable-space floor for source
execution and component dispatch. Net host-space changes remain diagnostics;
they cannot identify task allocations on this shared computer. Source execution
is limited to one attempt and 3,600 seconds. Source drift, expiry and bounded-log
checks remain active. A sampled guard is not a guarantee about the continuous
peak. The original installation plan retains its narrower, expiring 42 GiB /
1 GiB controls; the dispatch guard here requires at least 50 GiB plus headroom.

The six completed source checks, including full pytest, and the completed build
are reused at exact source `c2eb4a3d`. Only coverage, its reports and branch gates,
and the existing toolkit integration fixture suite run again. All 13 gates must
pass before any scanner or package execution. The documentation check already
passed on its recorded inputs and is not repeated; later handoff notes are not
those original inputs.

The scanner uses the unchanged context from
`../scanner-fixture-continuation-20261103/`: one parent-Python containment/bootstrap
probe, then one actual Cisco 2.2.1 scan through the ordinary workflow CLI. The
retained image ID is
`sha256:1cf3c4405db2f9b4721a35e10534f72a6b428fda49b3ee1114ef27d4f8a17eb4`.
Only the prepared finite amendments to the original grants are applied. The old
failed operation and 0.511 seconds remain. New reservations are bounded at three
operations and 240 seconds, with zero models or cash. Unknown accounting or
container ownership stops dispatch. The scan checks applicability to both named
configurations; it is not a SkillsBench task journey.

The package step uses the original approved wheel and 32 unchanged cached
wheels, original sandbox, programs, prepared workspace, installation plan and
expiry. Runtime code and execution assets match current source. Three progress
documents and RECORD differ in the later build; that later build is not installed.
The reusable runtime remains. No image, volume, backup, old runtime or unrelated
work is removed. Cleanup remains limited to passing owned current test fixtures
and newly owned containers whose identity is verified.

Before execution, inspect `preflight.json`, `interruption-analysis.json` and
`operation-review.json`; verify the full review hash and obtain approval. This
review does not authorize an automatic retry or source repair. It expires with
the original plan at `2026-11-04T19:05:52.620563Z`.

```bash
python3 reports/toolkit-v2/c13/coverage-completion-20261103/run-completion.py
python3 reports/toolkit-v2/c13/coverage-completion-20261103/run-completion.py --execute-approved DIGEST --component all
```

A failure with settled accounting leaves independent unstarted components
eligible, subject to the source gate. Historical attempt markers are never
removed or allowances refunded. Preserve unrelated local CI work. Stack
integration, candidate usefulness, selection usefulness, resource acceptance and
release remain separate open gates.
