# Bounded task-plan transport and Agent Framework adapter

The v7 plan reader accepts files up to32MiB so the original reconciliation input
can pass through the ordinary workflow and managed CLI. Ordinary metadata and
historical plans keep their1MiB limit. Both readers retain credential, Codex-state,
link and file-type exclusions. Oversized input is rejected before JSON parsing.
Canonical preparation checks its output size before publishing the workflow.

The large-input fixture uses1.2MB of reproducible binary data. Its canonical v7
plan exceeds1MiB, reaches both CLI previews without initializing a worker, and
retains the exact original case input. Other versions cannot borrow the larger
limit. These are source checks, not an upstream task journey or benchmark score.

The optional Agent Framework adapter targets the actual core1.21.0 API over an
operator-supplied approved dispatcher. Each step binds an executor fingerprint;
returned canonical receipts must match that executor and invocation action ID.
Only task/receipt references cross the SDK. Predecessor references reach each
next dispatch so the existing runtime can resolve verified output handles.
Unknown/mismatched receipts stop the pipeline. Failure stops subsequent steps;
cancellation keeps the run claimed and cannot silently restart it. The adapter
adds no provider or service. SDK checkpoint restoration is unsupported.

The dispatcher remains responsible for current authority, durable reservations,
attempts, receipt storage, transient artifact handles, cleanup and recovery.
The adapter has not been run against the real SDK. Its test builder is explicitly
a first-party fixture and cannot close the integration gate. Ordinary-workflow
selection and real runtime checks are still required. Candidate and selection
usefulness remain NOT_ASSESSED.

The source-lock/artifact preparation in
[the upstream packet](../upstream-source-preparation-20261031/README.md) resolves
Agent Framework core plus msgspec0.22.0, python-dotenv1.2.4 and regex2026.9.29.
The three dependency wheels were retrieved and hash-checked for static inspection;
no package was installed or imported. Existing reviewed common dependencies can
be reused in a retained private runtime after an exact review. Preserve the older
LangGraph runtime unchanged.

Focused checks passed 92 tests. All 13 current-source checks passed on unchanged
source 0cb8f956171e0b52de07a50ad9d328d02ed98309d0fd5e29f7ea8eae6a350e85:
1,906 tests passed and 21 skipped in each full run, 82% combined coverage, both
branch gates and the build. [verification/checks.json](verification/checks.json)
records the exact commands and durations. This digest includes the separately
preserved CI changes; those changes are excluded from the stack commit.
No model, service, Docker change, credential access, activation or release occurs
in these checks. The next permissioned LangGraph operation remains the exact
[SQLite bootstrap review](../full-stack-20261030/langgraph-sqlite-bootstrap/operation-review.json).
