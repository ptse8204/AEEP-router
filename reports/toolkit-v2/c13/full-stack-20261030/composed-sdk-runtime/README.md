# Current-source composed SDK runtime review

Approval is required before installation or real SDK execution. The exact
[operation review](operation-review.json) has SHA-256
`fb7fc581114945988267cac35513f8235f757d325d3253dd0aa3bbfe6bb60801`.
The review uses one retained private runtime for both workflow adapters. It
supersedes the unexecuted SQLite-only proposal on the older AEEP wheel. Earlier
LangGraph attempts, receipts and the older runtime remain unchanged.

The operation installs the current AEEP wheel and 60 exact cached dependency
wheels through the existing installer, checks idempotent setup, then runs:

- A standard-library containment check: SQLite creation/read/write succeeds;
  home-file reads, outside writes and networking are denied.
- Real LangGraph 1.2.14 conditional flow, bounded loops, interruption/resumption,
  lost-checkpoint refusal and denied dispatch, through at most six owned calls.
- Real Agent Framework core 1.21.0 successor consumption, command-failure stops,
  interruption with receipt retention, restart refusal, a separate reviewed
  continuation, and denied dispatch, through at most five owned calls.
- An independent installed-package/source identity check after successful setup.

Both SDKs use existing AEEP command execution, reservations and receipts. The
maximum is 11 owned command calls, 16 isolated engineering-grant operations and
240 reserved seconds across the two grants. These grants cannot authorize an
existing assessment. There are no model turns or cash spending. Outer SDK and
nested command resource intervals overlap and must not be summed.

The 61-wheel closure preserves reviewed common pins and adds Agent Framework
core, msgspec 0.22.0, python-dotenv 1.2.4 and regex 2026.9.29. Artifact URLs,
licenses, notices and dependency edges are in [packages.json](packages.json).
No provider extras are selected. The new runtime stays available for reuse;
the older runtime, all images, volumes, user work and backups are preserved.
The installer reserves 829,490,420 bytes above the 50 GiB host reserve and checks
free space again before execution. The last read-only check observed 64 GiB free.

[Preparation checks](preparation-checks.json) verify the bindings and refusal
without approval. A standard-library-only check passes the exact boundary.
The Agent Framework check program also passed with an explicitly first-party
builder fixture. That fixture is not real SDK evidence. The original LangGraph
worker bytes are unchanged. Neither SDK has run under this new review.

All 13 product checks passed on frozen source `0cb8f956`, including 1,906 tests
and 21 skips in each full run, 82% combined coverage, both branch gates and build.
The frozen coordinator lets unrelated implementation continue without silently
changing this execution scope. Source verification includes preserved CI edits;
those edits are excluded from the stack implementation commits.

A failed component retains its receipts and state. After successful setup and
containment, a terminal SDK failure does not prevent the other SDK or package
check. Common boundary or accounting uncertainty stops further dispatch. There
is no automatic retry, source repair, reinstall, download, service, Docker change,
credential access, activation, publication, release or cleanup.

A pass would establish these two bounded SDK journeys on this source. Ordinary
workflow composition, both actual SkillsBench domain journeys and the other
required integrations remain open. Candidate and selection usefulness remain
NOT_ASSESSED; comparisons stay paused. Current-input documentation verification
also remains open; the previous docs pass covers its original 72 inputs only.
