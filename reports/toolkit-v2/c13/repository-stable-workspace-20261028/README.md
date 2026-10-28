# Stable workspace check for JSON logging

This review tests whether collection and execution retain the same complete
pytest identities in fresh containers. The previous reference passed 168 tests
but could not match three traceback parameter names containing a random worker
path. That result stays excluded. All 171 test obligations and upstream
assertions remain required.

The optional reviewed profile sets the repository path to
`/tmp/aeep-repository-native-v6` inside each worker's private tmpfs. Exclusive
mode-0700 creation rejects an existing path or symlink. It adds no caller path
argument, host mount, identity rewriting, package, image or service. Only the
repository assignment and mkdir differ from the existing program; the AST
check proves the remaining program is identical. This profile does not alter
the packaged default or historical executor fingerprints.

| Check | Exact initial scope |
| --- | --- |
| Containment | Four fresh boundary/state/transport probes in each of the raw and diagnostic profiles |
| Native events | Two existing event fixtures in each profile |
| Runtime | One inherited JSON-backend version/import probe |
| Collection | One public JSON-logger snapshot; exhaustive native mapping frozen before body calls; exactly 171 required names |
| Reproduction | Published reference and unchanged original source, with all required assertions and predeclared negative outcomes |
| Raw reference | Same reference through the raw profile, retaining no diagnostic log |

Initial scope: **17 calls, 19 operations, 745 reserved seconds**. Two optional
immutable-payload report controls and one extra setup/analysis phase bring the
cumulative ceiling to **19 calls, 23 existing-grant operations, 965 reserved
seconds**. These are execution allowances, not product resource requirements.
No automatic retry, uncertain replay, allowance refund or counter reset.

Use only retained image `9f473c49`. Zero models or cash. No installation,
download, image build/pull/deletion, credential reading, service, new destination,
activation or release. Keep all images and at least 50 GiB host free. Remove
only new owned containers and the unchanged host canary; retain receipts and
up to 8 KiB of each failed public log.

Authored host fixtures passed ten checks, including stable traceback identity
across fresh processes, default/diagnostic equivalence, exclusive creation and
preservation of existing directories/symlinks. Seven terminal-receipt fixtures
and the real budget guard passed; operation 24 is rejected. These fixtures do
not certify the container or public source.

The unchanged core source's 13 gates and wheel's 20 installed checks are reused.
No package/source/docs repetition is part of this review. Dead remains excluded
because Git is absent; Sopel remains excluded for its incompatible dependency
and missing distribution metadata. Neither task runs under this review.

The pool remains 63 provisional snapshots, with 78 cases missing. This check
does not close model qualification, comparative usefulness, selection, resource,
human-control or release gates. New observer bytes and public-source execution
need this exact approval: the completed `ca2a06cc` review forbids program changes
in its optional control slots. No architecture or budget decision is needed.
