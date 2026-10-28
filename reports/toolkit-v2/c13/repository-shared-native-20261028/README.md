# Shared native observer and repository runtime check

The normal CLI exporter now uses the fixed repository path that passed the
actual 171-test JSON-logger check. The packaged v6 change is two lines: create
`/tmp/aeep-repository-native-v6` exclusively with mode `0700` in each fresh
contained worker. An existing directory or symlink fails closed. Host tests use
only owned scratch. Legacy observer/parser bytes and version-1 through version-5
contracts retain their existing meanings.

The compiled default program is byte-for-byte identical to the checked raw
profile, SHA-256 `1f099dfb9eee49db52c631a2c59f56c45f933e15bb6b4f1be35b86f5b8a84ba2`.
Old source-M1 evidence remains attached to its original source and image.
New source verification is recorded in `validation/`; a corrected wheel needs
its own private installation check. Source-M1 gates do not qualify new bytes.

The earlier unapproved Git/docs bundle `765e28e7` was withdrawn before execution.
Its exact upstream component design is retained in the new review, together
with the corrected wheel and current offline docs.

| Component | Exact scope |
| --- | --- |
| Git archive | Official Debian arm64 Git `1:2.47.3-0+deb13u1`, 8,665,568 bytes, SHA-256 `8c6b1e96b226211260d7814472215a8a1ed38ee37400c421d454391c1807cb5a`; at most two exact-URL requests, redirects denied |
| Preparation | System `ar` reads package data; pinned Apple LLVM inspects ELF. Require the exact inherited libc/PCRE2/zlib closure before building; no Linux binary or package script executes on the Mac |
| Image | One COPY-only local image from retained `9f473c49`, with unchanged inherited configuration/layers, three COPY layers and at most 16 MiB growth. Keep both images |
| Runtime | Both diagnostic and canonical shared-default profiles each get four fresh boundary/state/transport probes and two event fixtures |
| Dead | Real Git version/linker/init/add/ls-files/Identify-origin check, native collection, frozen mapping, reference/original pair and raw reference; all 38 obligations remain |
| Shared default | Frozen JSON-logger reference and original-source controls, each retaining all 171 obligations. These repeats add no independent cases |
| Package | Corrected wheel with the same 32 pinned cached dependencies; 20 private offline checks, including exact shared-default program identity from the installed CLI export. Remove only unchanged owned runtime/scratch |
| Docs | Cached pinned Lychee 0.24.2, network denied, 69 current documents. Reuse the known standalone version; Makefile checks version and links |

The Git component contains the unmodified main binary, regular template files
and publisher copyright. Its Perl/Curl helper stack and a full Debian package
installation are outside scope. The actual output-image digest and selected
content hashes are bound before any worker call. Directory permissions are
explicit, including under a restrictive host umask. No speculative libraries,
resolver, host installation or source build is permitted.

Initial runtime allowance: **19 calls, 22 operations, 1,115 reserved seconds**.
Including two optional immutable-payload report controls and one additional
setup/analysis phase, the cumulative ceiling is **21 calls, 26 existing-grant
operations, 1,335 reserved seconds**. Download/preparation/build is one
300-second operation. Package/docs checks are separately bounded. These are
execution allowances, not product resource acceptance thresholds.

Zero model calls or cash. No credentials, new model destinations, services,
activation, publication, release, retained-image/volume/backup deletion, budget
reset, allowance refund or uncertain replay. Keep at least 50 GiB host free.
Keep the prepared component cache, context, new image, old images and evidence;
remove only newly owned containers and unchanged test runtimes/canary.

Current pool: **64 provisional snapshots, 77 cases still missing**. New-source
reference checks, comparative usefulness, correct live selection, resource
acceptance, human control and release are separate gates. Passing these
engineering checks establishes no capability benefit or savings.
