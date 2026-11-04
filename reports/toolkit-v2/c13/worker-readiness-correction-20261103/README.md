# Canonical worker readiness and permission correction

The ordinary workflow CLI now drafts canonical readiness from settled paired
inspections. It reuses the existing worker, probe, journal, operation, conformance
and review contracts. No service, database, scheduler or model-facing authority
was added. Existing v1/v2 workflow definitions keep their meanings.

`workflow prepare-worker-readiness` requires the actual two request IDs and a
new output file. It verifies all eleven probe identities per worker, the matching
terminal journal, current source dependencies and settled charges on the same
grant. Selected collectors also require a denial observation in that journal.
It creates unreviewed definitions and an amendment proposal. The existing
operator review and conformance checks still control consumption. It never starts
workers, grants access, replays inspections or overwrites output files.

Twenty focused first-party tests pass, including journal/worker drift, missing
or conflicting probes, source drift, foreign grants, unmeasured costs and a
collector flag without journal evidence. Synthetic grants and protocol substitutes
stay inside temporary test databases. These tests are not actual conformance.
The full thirteen source gates are running on `c48e931b47647a400d87f7e1236821ff4243c2ca20f2d6f1dd8f5e4ec5d10659`;
[checks.json](verification/checks.json) is the current record. All old results keep
their original source scope. Unrelated CI edits are preserved outside these
implementation commits.

The approved `b01793ac` attempt built image `10a756a7d479`, then stopped at worker
readiness before models. Its [results](../ase-controlled-workflow-20261103/RESULTS.md)
retain four operations and zero model turns. Read-only layer inspection proved
that three directories have mode0444. The proposed Dockerfile changes only those
directories to0555, keeps file bytes/modes unchanged, and returns to the original
nonroot user. It uses the existing `/bin/chmod`, with no download or installation.
This build is not authorized or executed yet.

Next: complete source verification, bind the new wheel and unchanged cached
dependencies, then prepare one grouped correction/build/containment/CLI/wheel/docs
review. Include the ordinary readiness command and the original two unstarted
engine turns. Keep the original cumulative144-operation/6,200-second ceiling and
all charges. Verify directory modes before fresh workers; keep every image.
No comparative campaign resumes. Both SkillsBench journeys, other upstream
integrations, usefulness, resource acceptance and release remain open.
