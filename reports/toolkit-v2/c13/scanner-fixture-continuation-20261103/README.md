# Continue after two test-harness failures

Approved review `1ca962cc` completed full pytest with **2 failed, 2,019 passed and
21 skipped**. Coverage did not start. The source gate kept both scanner calls,
the installation and real grant amendments unstarted. The storage monitor did
not stop the run: its minimum observed usable space was 42.399 GiB.

The candidate-staging unit test still called the default 50 GiB capacity guard
without a synthetic capacity fixture. Separately, placing the fixture in root
`conftest.py` changed the fingerprint pinned by the core verifier. These were
engineering-test defects. No candidate output or benchmark threshold changed.

The correction moves synthetic capacity into the installer test module and
imports it explicitly only where needed. Candidate staging requests that fixture.
Root `conftest.py` is restored byte for byte to its original locked hash. No
verification lock is rewritten. Both failing tests and three related fixture
checks now pass. Production `src` bytes are unchanged from approved source1503d8d2.

Docs attempt1 found one extra blank line. The already-approved whitespace repair
and attempt2 passed. Tools were unchanged. Those completed results are retained;
this continuation does not rerun docs or claim that later status notes were inputs
to the old check. Failure logs and capacity samples remain. Some temporary unit
directories may expire through nested pytest's ordinary retention; they are not
real benchmark evidence. The new controller propagates the retention setting to
nested checks as well as the outer suite, preserving older roots going forward.

## Proposed bounded continuation

Authorize one fresh source-verification attempt, then the two unstarted scanner
calls and the original unstarted package component. All 13 source gates must pass
before either component starts. The proposed **source-test-only floor is 41 GiB**;
scanner and native installation keep their original **42 GiB floor and expiry**.
A fresh monitor baseline has a **1.25 GiB net-capacity stop threshold**, providing
margin above the observed 0.943 GiB peak drop after usable space fell to about
42.83 GiB. The floor still applies if less than 1.25 GiB is available. This is engineering working headroom,
not a product resource budget or guaranteed continuous peak limit.

The native installation keeps the exact parent wheel, 32 dependencies, plan,
storage exception, sandbox, programs and workspace. Its 1 GiB reservation/stop
controls are unchanged. The new packaging build is a source-build check only;
its wheel is not substituted for the already-reviewed installation artifact.
Member-by-member comparisons bind current code and execution assets to that
original wheel. Three progress-document snapshots and the wheel RECORD differ
from the new build; those differences are recorded. The parent wheel retains
its earlier documentation snapshot.

Original grants and counters stay: one old failed scanner operation and its
0.5110439579002559 seconds; wrapper unused. Prepared amendments preserve those
values and the already-reviewed absolute ceilings. No real amendment ran during
preparation. Source history, old failed attempt and all measurements remain.

This review is unapproved and unexecuted. It adds no model turns, cash, downloads,
image builds/pulls, credentials, services, release or older-resource deletion.
Keep all images, volumes, backups and runtimes. Preserve uncertain work. Only
newly owned containers and passing current unit fixtures have scoped cleanup.
Comparisons remain paused; all-stack and both SkillsBench journeys remain open.

## Resume

Approve the exact `operation-review.json` digest, record matching operator approval,
check component markers and expiry, then run
`run-continuation.py --execute-approved REVIEW_SHA256 --component all` with
`PYTHONPATH=src`. Never rerun the terminal parent source attempt. The parent
package marker remains the single package-attempt authority; this continuation
cannot provide a second installation attempt.
