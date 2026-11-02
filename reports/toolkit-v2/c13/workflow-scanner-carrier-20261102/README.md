# Correct the scanner protocol interpreter

The actual approved check exposed an invalid launch: the adapter used Cisco's
private Python environment to load AEEP's containment protocol. The reviewed
92-wheel Cisco environment has no `psutil`, which AEEP imports. The original
Docker failure is recorded as `CommandExitError`; its stderr was not retained,
so no specific missing-module exception is claimed as an observed diagnostic.
The installed dependency inventory and import chain establish the invalid choice.

The adapter now retains the existing parent-image `python3` for AEEP's protocol.
The scanner child still uses `/opt/aeep-scanner/bin/python` and the same reviewed
Cisco wheel. The regression asserts both interpreter choices. No dependency,
image, permission, model, destination or candidate changed. Forty focused tests
pass. Current source is `2df307d7be87d442e5795a0dc085282816944a41f64eb965a861780f629f2cd2`.

## Actual approved bundle results

Review `8f4ab6d3` ran once. Its containment probe failed before Cisco or the scan;
cleanup was verified. The one boundary operation is settled and remains charged.
The actual candidate scan was never started. The completed packet is
[the prior increment](../workflow-scanner-20261102/README.md).

Offline docs passed on attempt 1, with unchanged tools and the recorded 72 input
hashes. Do not replay that success. Later progress notes retain their own scope;
operator guide commands did not change for this internal correction.

The old wheel stayed uninstalled because its required headroom was unavailable.
That pending package artifact is superseded by this correction; do not install
it as the new current-source check. A new wheel/review is needed after source
verification completes. Both old runtimes and every Docker resource remain.

## Capacity and verification

Compile, schemas, assessment policy, Ruff and mypy pass on the corrected source.
The subsequent full suite was stopped at the host reserve: 1,666 passed, 41 failed
at the real free-space guard, one skipped, then KeyboardInterrupt. This is not a
passing full run. Its complete logs and cleanup record remain in `verification/`.
No test threshold, assertion or installer reserve was weakened.

The approved [b1a3e671 cleanup](space-review/operation-review.json) removed exactly
283 obsolete first-party CSV-test SQLite copies. Both primary campaign databases
and all other resources were preserved. Allocated size was 669,085,696 bytes;
the immediate observed free-space change was negative 446,464 bytes. This is
not demonstrated space savings. The host subsequently reported about 47.4 GiB
free. Twenty-five local Time Machine snapshots were observed and left untouched;
this audit does not establish their per-file contribution or recovery potential.
No current test/assessment worker is running; unrelated existing processes stay.

Restore at least 52 GiB of actual usable host space before the remaining large
checks. This is working headroom for the observed test fixtures and installation,
not a product resource-acceptance threshold. The 50 GiB reserve remains unchanged.
No further older-resource or backup deletion is authorized by b1a3e671.

## Resume without replay

1. Check actual free space, Git status and all current execution markers.
2. After adequate space is available, run `verify-source-resume.py`. It reuses
   only the five unchanged successful source gates, then runs full pytest,
   branch coverage and downstream gates with post-teardown fixture cleanup.
3. Retain the corrected source snapshot and build one updated-wheel review with
   the same 32 cached dependencies. Never install the superseded old artifact.
4. Prepare one correction review for a fresh containment/bootstrap probe and
   one actual CLI scan on retained image `1cf3c440`. Keep the private scanner
   interpreter separate from the parent protocol interpreter. The bootstrap
   probe should retain a minimized missing-module category before attempting
   the scan. No extra diagnostic execution is authorized yet.
5. Reuse the existing canonical repository, request and ledger. The old boundary
   charge stays. Record a finite budget amendment on the existing scanner grant
   if needed; never recreate it to reset counters. Review new runtime/accounting
   definitions against the corrected source before dispatch.
6. Obtain applicable exact execution approval for changed source/launch/wheel
   bytes. Previous terminal scanner approval cannot be retried. Successful docs
   need no replay merely to increase counts.

Both real SkillsBench domains, remaining upstream components and the all-stack
completion gate stay open. Candidate and selection comparisons remain paused.
Source verification includes preserved unrelated local CI edits; they remain
outside these implementation commits. Parent implementation commit: `9f6244b`.
