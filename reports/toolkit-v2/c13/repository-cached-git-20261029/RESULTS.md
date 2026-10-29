# Actual cached Git runtime result

The approved `d1caf28b` review completed once. Its COPY-only image and all 19
contained calls passed. The image is retained as
`aeep-toolkit-v2/repository-grader:py313-shared-native-git-20261028`, image ID
`sha256:35dc1bcb7e8162c2a0cef6cbd30bc4bf276c082b11b6e5fc259b6800e8c5ca04`.
Inherited configuration and parent layers matched the reviewed `9f473c49` image.
The build used the existing context; no download, dependency installation or
new library was needed.

| Check | Actual result |
| --- | --- |
| Two observer profiles | Both passed four fresh boundary/state/transport checks and two native-event fixtures |
| Git support | Version, linking, local init/add/ls-files and Identify origin checks passed |
| Dead reference | All 38 required native identities passed |
| Dead original | The one bug test failed; 37 preservation tests passed |
| Shared raw/default reference | All 38 passed |
| Frozen JSON-logger controls | Reference passed 171; original failed the expected 12 while 159 preservation tests passed |
| Canonical evidence | All 19 receipt/attempt/evidence chains reopened; zero failed or uncertain attempts |
| Accounting | All 22 operations complete; 41.88380412571132 seconds charged; zero model turns or cash |
| Cleanup | New owned containers and unchanged canary absent; images, cache, context and receipts retained |

The earlier failed `a11807f2` operation remains charged separately. The new
attempt made no network request and did not reset or refund any counters.
Current grant totals are 13,327 operations, 3,755 model turns,
120,125.71116234409 seconds and $0.

[Consolidation](provisional-pool.json) adds only the independently reproduced Dead
snapshot. The pool is now **65 snapshots, 41 repositories and 5,075 required
identities**: 27 single-file repairs, 23 multi-file repairs and 15 audits. The
frozen cohort still needs **76 cases: 20 single-file, 24 multi-file and 32 audits**.
Repeated controls add no independent cases. Older source/runtime bindings remain
attached to their original evidence.

This is grader/runtime reproduction, not model qualification or comparative
usefulness. Stages remain unfrozen, no candidate is adopted, and correct live
selection, resource acceptance, human control and release remain open. Completed
source, installed-package and offline-docs checks were not repeated.
