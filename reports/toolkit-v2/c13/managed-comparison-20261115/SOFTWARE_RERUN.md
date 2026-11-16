# Instrumented CANopen and Xsdata rerun

Four fresh GPT-6.1 Sol medium turns completed under the [exact
review](software-observation-review.json). Both arms used the same
public task inputs, 300-second limits, protected tests and grading
rules as the earlier software study. Both received the same optional
tool guidance. Treatment added the read-only LibCST preview helper
to the retained 1.8.6 environment. Control kept its existing local
editing tools.

| Task | Control score | Treatment score | Δ input tokens | Δ output tokens | Agent time control / treatment |
| --- | ---: | ---: | ---: | ---: | ---: |
| CANopen 613 | 0/1 | 0/1 | +51,896 | +526 | 60.28 s / 74.43 s |
| Xsdata 1126 | 0/1 | 0/1 | −23,960 | −209 | 78.33 s / 76.99 s |

Deltas are treatment minus control. Agent times exclude the separately
recorded protected grading interval. The [canonical result](software-observation-result.json)
contains all required test statuses, raw token categories and receipt
references. All four pytest runs exited 1.

- Both CANopen arms passed six of eight required tests. The PDO
  indexing and iteration regressions `test_pdo_getitem` and
  `test_pdo_iterate` failed in both arms.
- Both Xsdata arms passed 28 of 29 required tests, including the
  distinct nested-enum behavior test. The sole failure in both arms
  was `UnnestInnerClassesTests::test_update_types`.

## What was observed

The grader took the test identities and statuses from the existing
protected runner response. AEEP retained the declared test IDs, their
statuses and the pytest exit code. The host ledger binds each record
to its protected request, grader receipt and trial. Source patches and
raw pytest output remain transient.

The same host observer watched both arms. Positive LibCST evidence
requires a paired App Server command start and terminal outcome for
the exact reviewed helper and interpreter within the same worker,
thread and turn. The observer records import and parse separately
from a rename transform and a changed preview. The helper performs
no source writes. The execution journal binds the observer record
and the two native event digests.

[Offline checks](software-observer-offline-evidence.json) demonstrated
an actual parse, changed rename preview and no-op through the pinned
helper. Controls rejected traversal, symlinks, shell login framing and
composition, and mismatched evidence. Neither live treatment recorded
a verified helper invocation or a name-specific native instruction
load. Other command forms and direct Python imports remain outside
this observer's coverage, so actual LibCST use by those paths is
unknown. The rerun does not supply new evidence about the earlier
trials.

The [readback audit](software-observation-audit.json) verified token
capture, grader and worker cleanup, and all four canonical receipts.
The rerun settled 21 operations and four model turns in 326.25 summed
operation seconds with $0 cash. The proxy returned to exactly its
earlier stopped state. Both historical reservations remain and
there are no new unresolved reservations.
