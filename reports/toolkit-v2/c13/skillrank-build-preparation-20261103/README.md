# Prepare the pinned SkillRank runtime

This check prepares a reusable SkillRank runtime and verifies search/show against
its own upstream local registry. It uses first-party catalog records and makes no
capability-benefit claim. The registry runs inside an owned container with no
external network or published host port, then stops. Its built binary, source,
dependencies and compiler image remain available for the callback integration.

The source pin stays `5216bae9149b4ff8a7f9e014b6889fb094cee8e1`. The
[release audit](release-compatibility.json) found that the published0.1.5 binary
comes from another commit, with six compiled files changed. Substituting it would
change the selected source. Instead, all35 build-file Git blobs are verified and
staged privately. The lock names86 exact registry archives; none has been fetched
or executed by this preparation. No Cargo/Rust command has run.

The proposed runtime uses official Rust1.94.1 on Linux arm64, pinned by its image
manifest digest. This adds a compiler image to the existing Docker installation;
it does not add another scheduler, registry implementation or evidence store.
Cargo builds offline with the unchanged upstream lock. Untrusted build scripts
stay inside the reviewed Docker boundary, away from host home, credentials and
the Docker socket. The local CLI's catalog `safe` labels remain unverified claims,
separate from Cisco scan findings.

The grouped review also covers the corrected AEEP wheel with32 unchanged cached
dependencies and current cached offline documentation checking. These components
have separate attempts and outputs. A known SkillRank failure does not invalidate
their results; unresolved accounting or cleanup stops further dispatch.

Before approval, only first-party archive-safety, inert-definition and source
checks run. The eight [archive controls](vendor-controls.json) use synthetic input
and test checksum, traversal, link and duplicate rejection. They establish no
upstream runtime pass. The source verification record is
`../report-family-serialization-20261103/verification/checks.json`.

After exact approval is recorded, inspect every started/result file first. Run
`run-components.py --component package --execute-approved REVIEW_SHA256`, then the
corresponding `--component docs` command, and
`run-runtime.py --execute-approved REVIEW_SHA256`. Package/docs may run independently.
Do not replay terminal attempts. No program above executes a model task.

The bounded SkillRank evaluation callback and its ordinary workflow selection
remain open. Search/show alone cannot close that integration. Both SkillsBench
domain journeys, remaining integrations, candidate usefulness, selection
usefulness, resource qualification and release also remain open. Comparisons
stay paused. Waza still lacks a supported backend subscription.
