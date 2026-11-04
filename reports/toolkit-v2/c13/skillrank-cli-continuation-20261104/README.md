# Finish the unstarted SkillRank CLI phases

The preceding [approved results](../workflow-skillrank-20261103/RESULTS.md) retain
successful setup/idempotency/readiness, wheel and documentation checks. Only the
runtime continuation is pending; it does not rebuild, install or rerun those
completed components.

The old probe's underlying failure is unknown because its driver did not retain
the inner error. Its write check handles `PermissionError` but misses `EROFS`.
The new probe accepts only actual write denial (`EACCES`, `EPERM` or `EROFS`),
records the errno, and rejects other errors or a successful write. Network refusal
or timeout cannot pass as a permission denial. It records permission denial or
an absent namespace route distinctly, and verifies the pinned binary's actual
version before any catalog query. It retains bounded failure diagnostics.

[Boundary controls](boundary-controls.json) are first-party substitutions, not
container evidence. [Driver controls](driver-controls.json) use the actual CLI
with substituted upstream execution. They preserve 24 prior operations and
complete the remaining journey in 18 additional operations. Neither is upstream
functional qualification or candidate-value evidence.

[operation-review.json](operation-review.json) binds one fresh containment/version
check and the three unstarted catalog queries, then shared-runtime preservation
and selective removal of a newly owned disposable copy. All old charges remain.
The prepared finite budget amendment increases the original operation ceiling
from 40 to 42 for the two extra probe/driver operations. It uses the standing
engineering delegation; no model, time or cash ceiling is raised and no counter
is reset. It has not been applied.

Same product source, binary, worker image, catalog, permissions and CLI definitions.
No package/docs reruns, downloads, builds, pulls, new dependencies, credentials,
models, host activation, release or existing-resource deletion. Keep the 50 GiB
actual host reserve and all reusable runtimes. Only new owned check containers,
the explicitly authored preservation-control note and unchanged disposable copy
may be removed. No automatic runtime retry is authorized.

Bounded SkillRank evaluation and the remaining upstream integrations stay open.
Both task domains and every required integration still need functional evidence
before comparisons can resume. Waza remains blocked without supported Copilot
backend access.
