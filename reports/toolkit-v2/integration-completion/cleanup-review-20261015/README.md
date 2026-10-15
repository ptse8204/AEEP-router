# Specific cleanup review — October 15

Prepared only. Nothing in this review has been deleted. The request authorizes
inspection and preparation, not execution. Exact review SHA-256:
`b9d61fd76f37593d9ae402153f26362105f6479309553f93bfbbbb988cec4632`.

At this snapshot the host had 29.24 GiB available.
Reaching 70 GiB requires another 40.76 GiB.
The six cache roots below occupy 2.72 GiB. Even if
every allocated block were reclaimed immediately, free space would reach only
31.95 GiB, leaving
38.05 GiB still needed. This cleanup
cannot restore even the 50 GiB reserve. Actual reclamation may be lower because
allocated size does not establish exclusive ownership of filesystem blocks.

## Exact candidates

| Cache root | Allocated GiB | Consequence of removal |
|---|---:|---|
| `/Users/edwintse/.cache/winetricks/win7sp1` | 1.407 | Removes cached installers only. Future Wine setup may need to download them again; offline availability is lost. |
| `/Users/edwintse/.cache/winetricks/win2ksp4` | 0.126 | Removes cached installer only; installed Wine prefixes remain untouched. Future redownload availability is not verified. |
| `/Users/edwintse/.cache/trivy/trivy/db` | 1.156 | Future scans must refresh the database; offline scans requiring this cache will be unavailable until then. |
| `/Users/edwintse/Documents/aeep-toolkit-v2/.mypy_cache` | 0.026 | Next type check rebuilds the cache. |
| `/Users/edwintse/Documents/aeep-toolkit-v2/.pytest_cache` | 0.000 | Loses last-failed and cached node-selection hints; committed test reports and canonical evidence remain. |
| `/Users/edwintse/Documents/aeep-toolkit-v2/.ruff_cache` | 0.000 | Next lint run rebuilds the cache. |

The Windows cache contains three service-pack installer executables, not Wine
prefixes or user documents. Trivy's directory contains its database and metadata;
its other cache directories remain outside this review. The three AEEP cache
roots are Git-ignored. No tracked source, test reports or assessment records are
included. Inactive status is a point-in-time observation: the process check found
no relevant tool running and all six `lsof` probes reported no open files.

[review.json](review.json) binds canonical paths, device/inode/owner, complete
metadata inventory hashes and hashes of the installer/database files. Before
any approved deletion, repeat all checks and stop on drift, open files, a new
relevant process or uncertain ownership. Record removal and measured free space
separately. Future downloads or replacement software execution are not authorized
by a cache-deletion approval.

## Preserved resources

[Docker inventory](docker-preservation.json) records all 13 container references,
including stopped containers, and all listed image identities. Four containers
are running; other containers retain recovery or historical evidence. No Docker
container, image, volume, network or build-cache record is proposed for deletion.
Current/rollback image ownership has not been established for unrelated releases.

Docker reports 23.31 GB of reclaimable images and 16.32 GB of reclaimable build
cache. Those are not safe-removal estimates. They include resources outside this
task, and shared layers cannot be counted twice. All 27 cache records whose
instruction text names AEEP are shared; none is both unshared and reclaimable.
The other 164 unshared reclaimable records lack verified obsolete-task ownership.
Persistent volumes, recovery databases and unfinished work remain untouched.

All backups and 25 observed APFS snapshots are excluded. The original AEEP state
directory occupies about 29.45 GiB and contains canonical/historical evidence;
it is preserved. Sweet Saver Fare state/recovery storage, other project release
directories, Codex runtimes and configuration, application caches of uncertain
ownership, and the staged VS Code update are also excluded.

Docker.raw occupies 221,415,079,936 allocated bytes; its 994,662,416,384-byte logical
capacity is not reclaimable free space. Docker documents this distinction and a
privileged reclamation helper. No helper was pulled or executed, no Docker setting
was changed, and no Docker.raw operation is proposed. Its benefit is unmeasured.
[Docker's Mac storage documentation](https://docs.docker.com/desktop/troubleshoot-and-support/faqs/macfaqs/)
also documents moving the disk through Desktop settings; such a migration would
need a selected destination and a separate plan protecting active workloads.

## Remaining work

[Read-only prerequisite checks](remaining-work-preflight.json) confirm unchanged
AEEP executable source, the three required worker/runtime images still present,
zero jobs for either prepared campaign and a stopped model proxy. Existing exact
training approval remains valid. No new model turn, install, build or cleanup ran.
The missing pinned link checker still prevents the full docs check; do not install
it while below the storage reserve.

This review is ready for a cache-only decision, but approval will not solve the
capacity requirement. Reaching 70 GiB while preserving the excluded resources
requires owner-confirmed obsolete data beyond this list or a separately reviewed
storage relocation. Do not broaden the deletion list to meet the target. The
training and qualification guards remain unchanged at 55 and 69.77 GiB minimum
free space respectively, with fresh preflights required before execution.
