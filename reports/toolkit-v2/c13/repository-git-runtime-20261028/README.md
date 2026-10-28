# Provide real local Git for Dead's repository fixtures

Dead204 cannot be reproduced on the retained grader image because its fixtures
call `git init`, `git add` and `git ls-files`. Its previous reference produced
5 passes and 33 fixture errors. This review supplies upstream Git's real local
command component and preserves all 38 task obligations.

The read-only image audit verified the OCI manifest, configuration and every
layer digest, then read the Debian package inventory without starting a
container. All 87 package records are retained. Git is absent; the inherited
libc, PCRE2, zlib and linker packages are identified by version. The unchanged
230,109,184-byte temporary export was removed. All images stayed untouched.

| Component | Exact reviewed scope |
| --- | --- |
| Download | Official Debian arm64 Git `1:2.47.3-0+deb13u1`, 8,665,568 bytes, SHA-256 `8c6b1e96b226211260d7814472215a8a1ed38ee37400c421d454391c1807cb5a`; at most two exact-URL requests, with redirects denied |
| Host inspection | System `ar` reads package data; pinned Apple LLVM reads ELF metadata. No Linux binary or Debian maintainer script executes on the Mac |
| Selected files | Unmodified main `git` binary, regular template files and publisher copyright. Context is private; copied template directories have explicit traversal permissions |
| Static closure | Require exactly `libc.so.6`, `libpcre2-8.so.0` and `libz.so.1`; an unexpected dependency stops before building |
| Image | One local COPY-only build from retained `9f473c49`, no network/pull. Require unchanged inherited configuration, the exact parent layers, three added COPY layers and at most 16 MiB growth |
| Fresh checks | Four boundary/state/transport probes and two event fixtures in each stable profile; one Git version/linker/init/add/ls-files/Identify-origin check |
| Task | Native collection, frozen exhaustive mapping, reference/original pair and raw reference. Every one of the 38 obligations remains required |
| Docs | Exact cached Lychee 0.24.2, offline, same sandbox, 69 current documents. Reuse the completed standalone version evidence; Makefile checks version and links |

This is a local-command component. The full Debian Git package's Perl/Curl
helper stack is outside scope. Source/archive pins and publisher license notices
are retained; private local use is authorized only after approval. No image,
binary or source publication is included.

After building, the existing AEEP operator path binds the actual output image,
selected content hashes, recipe and environment before dispatch. Both worker
profiles remain rootless, offline and fresh. The protected source, assertions,
reference, original-source control and native expansion rule stay unchanged.

Initial allowance: **17 calls, 20 operations and 1,045 reserved seconds**.
Including two optional immutable-payload report controls and one additional
setup/analysis phase, the cumulative ceiling is **19 calls, 24 existing-grant
operations and 1,265 reserved seconds**. Download/preparation/build is one
300-second operation. These are finite execution allowances, not product
resource requirements. Preserve all prior charges; no automatic replay, refund
or counter reset.

Keep the new image, old images, prepared context, component cache and evidence.
Remove only new owned containers and the unchanged canary. Keep at least 50 GiB
host free. Zero models or cash; no credentials, new model destinations, services,
activation or release. No other package, host installation or source build.

Preparation checked component selection, path escapes, duplicates, symlinks,
setuid bits and directory traversal under a restrictive umask. The actual image
binding derivation and cumulative budget guard were exercised with removed,
explicitly synthetic fixture data. A trusted Apple tool read a cached Linux
wheel member as ELF data; that member was never executed or imported.
These checks do not certify Git or Dead. Their actual execution awaits approval.

The old preparation draft `29941bc9` was withdrawn before approval or execution
to make directory modes independent of the host umask. Never execute that draft.
Current unchanged core source and wheel checks are reused. No package reinstall
or broad source rerun is proposed. The pool remains 64 provisional snapshots,
with 77 cases missing. Comparative usefulness, selection and release remain open.
